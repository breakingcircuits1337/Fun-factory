import os
from typing import TypedDict
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, END, START
from langgraph.prebuilt import ToolNode

from api.core.sandbox import exec_in_sandbox, write_file_in_sandbox
from api.core.indexer import search_codebase as _search_codebase

CODER_SYSTEM = """
You are an expert software engineer. You have access to a code repository.
Your job is to implement the described task by reading relevant files,
writing changes, running tests, and iterating until the task is complete.

Use tools to:
1. Read files to understand current code
2. Search the codebase for relevant functions/classes
3. Write/patch files to implement changes
4. Run tests to verify your changes
5. Fix any failures and re-run

When you are satisfied the task is complete and tests pass, respond with:
TASK_COMPLETE: <brief summary of changes>
"""

MAX_TURNS = 20


@tool
def read_file(path: str, task_id: str = "") -> str:
    """Read a file from the workspace."""
    result = exec_in_sandbox(task_id, ["cat", path])
    return result.get("stdout", "") or result.get("stderr", "File not found")


@tool
def write_file(path: str, content: str, task_id: str = "") -> str:
    """Write content to a file in the workspace."""
    result = write_file_in_sandbox(task_id, path, content.encode("utf-8"))
    return "File written successfully" if result.get("exit_code") == 0 else result.get("stderr", "Write failed")


@tool
def run_command(command: str, task_id: str = "") -> str:
    """Run a bash command in the workspace. Restricted to workspace directory."""
    safe_cmd = f"cd /workspace && {command}"
    result = exec_in_sandbox(task_id, safe_cmd)
    output = []
    if result.get("stdout"):
        output.append(result["stdout"])
    if result.get("stderr"):
        output.append(f"STDERR: {result['stderr']}")
    output.append(f"Exit code: {result.get('exit_code', -1)}")
    return "\n".join(output)


@tool
def search_codebase(query: str, repo_id: str = "") -> str:
    """Semantic search across the codebase index."""
    results = _search_codebase(query, repo_id=repo_id, n_results=5)
    if not results:
        return "No results found"
    output = []
    for r in results:
        output.append(f"File: {r['file']}\n{r['content']}\n---")
    return "\n".join(output)


tools = [read_file, write_file, run_command, search_codebase]


def _estimate_tokens(messages: list) -> int:
    """Rough token estimate: 4 chars ≈ 1 token."""
    return sum(len(str(getattr(m, "content", ""))) for m in messages) // 4


class CoderState(TypedDict):
    task_id: str
    task_description: str
    repo_id: str
    model: str
    api_key: str | None
    messages: list
    turn_count: int
    complete: bool
    output: str | None
    session_count: int
    handoff_summary: str | None


async def coder_node(state: CoderState) -> CoderState:
    from api.core.llm import get_llm_client
    from api.core.observability import get_langfuse_callbacks
    from api.settings import settings

    client = get_llm_client(api_key=state.get("api_key")).bind_tools(tools)

    if not state["messages"]:
        messages = [
            SystemMessage(content=CODER_SYSTEM),
            HumanMessage(content=f"Task: {state['task_description']}\nTask ID: {state['task_id']}"),
        ]
    else:
        messages = state["messages"]

    callbacks = get_langfuse_callbacks(state["task_id"], "coder")
    invoke_config = {"callbacks": callbacks} if callbacks else {}
    response = await client.ainvoke(messages, config=invoke_config)
    messages = messages + [response]

    # Check for completion signal
    if isinstance(response.content, str) and "TASK_COMPLETE:" in response.content:
        summary = response.content.split("TASK_COMPLETE:", 1)[1].strip()
        return {**state, "messages": messages, "complete": True, "output": summary,
                "handoff_summary": None}

    # Check if context is approaching token limit — trigger session handoff
    if _estimate_tokens(messages) > settings.CODER_TOKEN_LIMIT and not state.get("complete"):
        summary_client = get_llm_client(api_key=state.get("api_key"))
        summary_resp = await summary_client.ainvoke([
            SystemMessage(content=(
                "Summarize what has been accomplished so far and what still needs to be done. "
                "Be specific about files modified and remaining steps."
            )),
            *messages[-8:],
        ])
        return {**state, "messages": messages, "complete": False,
                "handoff_summary": summary_resp.content,
                "turn_count": state["turn_count"] + 1}

    return {**state, "messages": messages, "turn_count": state["turn_count"] + 1,
            "handoff_summary": None}


async def handoff_node(state: CoderState) -> CoderState:
    """Start a fresh LangGraph session with the progress summary as new context.

    Rather than compressing history in-place, we hand off to a clean session —
    this gives the LLM full context window for the remaining work with no
    degradation from accumulated tool outputs.
    """
    from api.settings import settings
    if state.get("session_count", 0) >= settings.CODER_MAX_SESSIONS:
        return {**state, "complete": True,
                "output": f"Max sessions ({settings.CODER_MAX_SESSIONS}) reached. "
                          f"Final progress: {state.get('handoff_summary', '')}"}
    new_messages = [
        SystemMessage(content=CODER_SYSTEM),
        HumanMessage(content=(
            f"Task: {state['task_description']}\nTask ID: {state['task_id']}\n\n"
            f"PROGRESS FROM PREVIOUS SESSION:\n{state['handoff_summary']}\n\n"
            "Continue from where the previous session left off. Do not repeat completed work."
        )),
    ]
    return {
        **state,
        "messages": new_messages,
        "handoff_summary": None,
        "session_count": state.get("session_count", 0) + 1,
    }


def should_continue(state: CoderState) -> str:
    if state.get("handoff_summary"):
        return "handoff"
    if state["complete"]:
        return END
    if state["turn_count"] >= MAX_TURNS:
        return END
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    return "coder"


def build_coder_graph(checkpointer=None):
    graph = StateGraph(CoderState)
    graph.add_node("coder", coder_node)
    graph.add_node("tools", ToolNode(tools))
    graph.add_node("handoff", handoff_node)
    graph.add_edge(START, "coder")
    graph.add_conditional_edges("coder", should_continue,
                                {"tools": "tools", "coder": "coder",
                                 "handoff": "handoff", END: END})
    graph.add_edge("tools", "coder")
    graph.add_edge("handoff", "coder")
    return graph.compile(checkpointer=checkpointer)


async def run_coder(
    task_id: str,
    description: str,
    repo_id: str = "",
    model: str = "claude-sonnet",
    api_key: str | None = None,
) -> str:
    import psycopg
    from langgraph.checkpoint.postgres import PostgresSaver
    from api.settings import settings

    with psycopg.connect(settings.LANGGRAPH_CHECKPOINTER_URL) as conn:
        checkpointer = PostgresSaver(conn)
        checkpointer.setup()  # idempotent DDL — safe to call each time
        graph = build_coder_graph(checkpointer=checkpointer)
        config = {"configurable": {"thread_id": task_id}}
        result = await graph.ainvoke(
            {
                "task_id": task_id,
                "task_description": description,
                "repo_id": repo_id,
                "model": model,
                "api_key": api_key,
                "messages": [],
                "turn_count": 0,
                "complete": False,
                "output": None,
                "session_count": 0,
                "handoff_summary": None,
            },
            config=config,
        )
    return result.get("output") or "Coder reached max turns without completing"
