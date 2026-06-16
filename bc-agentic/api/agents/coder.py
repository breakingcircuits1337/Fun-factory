import os
from typing import TypedDict, Annotated
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from api.core.sandbox import exec_in_sandbox
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
    result = exec_in_sandbox(task_id, f"cat {path}")
    return result.get("stdout", "") or result.get("stderr", "File not found")


@tool
def write_file(path: str, content: str, task_id: str = "") -> str:
    """Write content to a file in the workspace."""
    # Escape content for shell
    escaped = content.replace("'", "'\"'\"'")
    result = exec_in_sandbox(task_id, f"mkdir -p $(dirname '{path}') && cat > '{path}' << 'BCEOF'\n{content}\nBCEOF")
    return "File written successfully" if result.get("exit_code", 1) == 0 else result.get("stderr", "Write failed")


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


class CoderState(TypedDict):
    task_id: str
    task_description: str
    repo_id: str
    model: str
    messages: list
    turn_count: int
    complete: bool
    output: str | None


async def coder_node(state: CoderState) -> CoderState:
    from api.core.llm import get_llm_client
    client = get_llm_client().bind_tools(tools)

    if not state["messages"]:
        messages = [
            SystemMessage(content=CODER_SYSTEM),
            HumanMessage(content=f"Task: {state['task_description']}\nTask ID: {state['task_id']}"),
        ]
    else:
        messages = state["messages"]

    response = await client.ainvoke(messages)
    messages = messages + [response]

    # Check for completion
    if isinstance(response.content, str) and "TASK_COMPLETE:" in response.content:
        summary = response.content.split("TASK_COMPLETE:", 1)[1].strip()
        return {**state, "messages": messages, "complete": True, "output": summary}

    return {**state, "messages": messages, "turn_count": state["turn_count"] + 1}


def should_continue(state: CoderState) -> str:
    if state["complete"]:
        return END
    if state["turn_count"] >= MAX_TURNS:
        return END
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    return "coder"


def build_coder_graph():
    graph = StateGraph(CoderState)
    graph.add_node("coder", coder_node)
    graph.add_node("tools", ToolNode(tools))
    graph.set_entry_point("coder")
    graph.add_conditional_edges("coder", should_continue, {"tools": "tools", "coder": "coder", END: END})
    graph.add_edge("tools", "coder")
    return graph.compile()


async def run_coder(task_id: str, description: str, repo_id: str = "", model: str = "claude-sonnet") -> str:
    graph = build_coder_graph()
    result = await graph.ainvoke({
        "task_id": task_id,
        "task_description": description,
        "repo_id": repo_id,
        "model": model,
        "messages": [],
        "turn_count": 0,
        "complete": False,
        "output": None,
    })
    return result.get("output") or "Coder reached max turns without completing"
