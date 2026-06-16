import json
import re
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, END
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
    goal: str
    codebase_summary: str
    model: str
    task_graph: list[dict]
    error: str | None


async def plan_node(state: PlannerState) -> PlannerState:
    client = get_llm_client()
    messages = [
        SystemMessage(content=PLANNER_SYSTEM),
        HumanMessage(content=f"Goal: {state['goal']}\n\nCodebase summary:\n{state['codebase_summary']}"),
    ]

    response = await client.ainvoke(
        messages,
        model=state.get("model", "claude-sonnet"),
    )

    content = response.content
    # Extract JSON from response
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if not match:
        return {**state, "error": "Planner returned no JSON", "task_graph": []}

    try:
        data = json.loads(match.group(0))
        return {**state, "task_graph": data.get("tasks", []), "error": None}
    except json.JSONDecodeError as e:
        return {**state, "error": f"JSON parse error: {e}", "task_graph": []}


def build_planner_graph():
    graph = StateGraph(PlannerState)
    graph.add_node("plan", plan_node)
    graph.set_entry_point("plan")
    graph.add_edge("plan", END)
    return graph.compile()


async def plan_task(goal: str, codebase_summary: str, model: str = "claude-sonnet") -> list[dict]:
    graph = build_planner_graph()
    result = await graph.ainvoke({
        "goal": goal,
        "codebase_summary": codebase_summary,
        "model": model,
        "task_graph": [],
        "error": None,
    })

    if result.get("error"):
        raise RuntimeError(f"Planning failed: {result['error']}")

    return result["task_graph"]
