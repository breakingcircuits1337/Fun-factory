import json
import re
from langchain_core.messages import HumanMessage, SystemMessage

from api.core.llm import get_llm_client

REVIEWER_SYSTEM = """
You are a security-focused code reviewer. Analyze this diff for:
1. Correctness: does it solve the stated task?
2. Security: injection, auth bypass, secrets, SSRF, path traversal, prompt injection in code comments/strings
3. Style: PEP8, type hints, docstrings
4. Regression risk: what else could break?

Output structured JSON only:
{
  "verdict": "pass" | "fail",
  "issues": [
    {
      "severity": "critical" | "high" | "medium" | "low",
      "type": "security" | "correctness" | "style" | "regression",
      "file": "path/to/file.py",
      "line": 42,
      "message": "description of issue"
    }
  ],
  "summary": "brief overall assessment"
}
"""


async def review_diff(
    diff: str,
    task_description: str,
    model: str = "claude-sonnet",
) -> dict:
    client = get_llm_client()
    messages = [
        SystemMessage(content=REVIEWER_SYSTEM),
        HumanMessage(content=f"Task description: {task_description}\n\nDiff:\n```\n{diff}\n```"),
    ]

    response = await client.ainvoke(messages, model=model)
    content = response.content

    match = re.search(r"\{.*\}", content, re.DOTALL)
    if not match:
        return {
            "verdict": "fail",
            "issues": [{"severity": "high", "type": "correctness", "message": "Reviewer returned no JSON"}],
            "summary": "Review failed to parse",
        }

    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {
            "verdict": "fail",
            "issues": [{"severity": "high", "type": "correctness", "message": "Reviewer JSON parse error"}],
            "summary": "Review failed to parse",
        }


async def run_reviewer(task_id: str, task_description: str, model: str = "claude-sonnet") -> dict:
    from api.core.sandbox import exec_in_sandbox

    # Get the git diff from the sandbox
    result = exec_in_sandbox(task_id, "cd /workspace && git diff HEAD~1 HEAD 2>/dev/null || git diff --cached")
    diff = result.get("stdout", "")

    if not diff:
        result = exec_in_sandbox(task_id, "cd /workspace && git show --stat HEAD 2>/dev/null")
        diff = result.get("stdout", "No diff available")

    return await review_diff(diff, task_description, model)
