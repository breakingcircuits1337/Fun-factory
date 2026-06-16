import json
import re
from typing import TypedDict
from langgraph.graph import StateGraph, END, START
from langchain_core.messages import HumanMessage, SystemMessage
from api.core.llm import get_llm_client

PLANNER_SYSTEM = """
You are a senior software architect. Given a goal and codebase summary,
decompose the work into atomic, parallelizable tasks.

Output JSON only:
{
  "tasks": [
    {
      "id": "t1",
      "description": "...",
      "depends_on": [],
      "files_likely_affected": ["src/auth.py"],
      "agent_type": "coder"
    }
  ]
}

agent_type must be one of: "coder", "researcher", "tester"
Keep tasks focused and achievable in a single agent session.
"""


class PlannerState(TypedDict):
    task_id: str
    goal: str
    codebase_summary: str
    model: str
    api_key: str | None
    task_graph: list[dict]
    error: str | None


async def plan_node(state: PlannerState) -> PlannerState:
    from api.core.observability import get_langfuse_callbacks
    client = get_llm_client(api_key=state.get("api_key"))
    messages = [
        SystemMessage(content=PLANNER_SYSTEM),
        HumanMessage(content=f"Goal: {state['goal']}\n\nCodebase summary:\n{state['codebase_summary']}"),
    ]

    callbacks = get_langfuse_callbacks(state.get("task_id", ""), "planner")
    invoke_config = {"callbacks": callbacks} if callbacks else {}
    response = await client.ainvoke(messages, config=invoke_config)

    content = response.content
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if not match:
        return {**state, "error": "Planner returned no JSON", "task_graph": []}

    try:
        data = json.loads(match.group(0))
        tasks = data.get("tasks", [])
        if not tasks:
            return {**state, "error": "Planner returned empty task list", "task_graph": []}
        return {**state, "task_graph": tasks, "error": None}
    except json.JSONDecodeError as e:
        return {**state, "error": f"JSON parse error: {e}", "task_graph": []}


def build_planner_graph():
    graph = StateGraph(PlannerState)
    graph.add_node("plan", plan_node)
    graph.add_edge(START, "plan")
    graph.add_edge("plan", END)
    return graph.compile()


async def plan_task(
    goal: str,
    codebase_summary: str,
    model: str = "claude-sonnet",
    task_id: str = "",
    api_key: str | None = None,
) -> list[dict]:
    graph = build_planner_graph()
    result = await graph.ainvoke({
        "task_id": task_id,
        "goal": goal,
        "codebase_summary": codebase_summary,
        "model": model,
        "api_key": api_key,
        "task_graph": [],
        "error": None,
    })

    if result.get("error"):
        raise RuntimeError(f"Planning failed: {result['error']}")

    return result["task_graph"]
