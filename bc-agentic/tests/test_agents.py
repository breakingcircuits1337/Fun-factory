import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.mark.asyncio
async def test_planner_parses_valid_json():
    from api.agents.planner import plan_task

    mock_response = MagicMock()
    mock_response.content = json.dumps({
        "tasks": [
            {
                "id": "t1",
                "description": "Add login endpoint",
                "depends_on": [],
                "files_likely_affected": ["api/auth.py"],
                "agent_type": "coder",
            },
            {
                "id": "t2",
                "description": "Add tests for login",
                "depends_on": ["t1"],
                "files_likely_affected": ["tests/test_auth.py"],
                "agent_type": "tester",
            },
        ]
    })

    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock(return_value=mock_response)

    with patch("api.agents.planner.get_llm_client", return_value=mock_llm):
        tasks = await plan_task("Add user authentication", "Python FastAPI project")

    assert len(tasks) == 2
    assert tasks[0]["id"] == "t1"
    assert tasks[1]["depends_on"] == ["t1"]


@pytest.mark.asyncio
async def test_planner_handles_no_json():
    from api.agents.planner import plan_task

    mock_response = MagicMock()
    mock_response.content = "I cannot decompose this task."

    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock(return_value=mock_response)

    with patch("api.agents.planner.get_llm_client", return_value=mock_llm):
        with pytest.raises(RuntimeError, match="Planning failed"):
            await plan_task("goal", "summary")


@pytest.mark.asyncio
async def test_reviewer_parses_verdict():
    from api.agents.reviewer import review_diff

    mock_response = MagicMock()
    mock_response.content = json.dumps({
        "verdict": "pass",
        "issues": [],
        "summary": "Clean implementation, no issues found.",
    })

    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock(return_value=mock_response)

    with patch("api.agents.reviewer.get_llm_client", return_value=mock_llm):
        result = await review_diff("diff --git a/auth.py b/auth.py\n+def login(): pass", "Add login")

    assert result["verdict"] == "pass"
    assert result["issues"] == []


@pytest.mark.asyncio
async def test_reviewer_flags_critical():
    from api.agents.reviewer import review_diff

    mock_response = MagicMock()
    mock_response.content = json.dumps({
        "verdict": "fail",
        "issues": [
            {"severity": "critical", "type": "security", "message": "Hardcoded API key detected", "file": "auth.py", "line": 5}
        ],
        "summary": "Critical security issue found.",
    })

    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock(return_value=mock_response)

    with patch("api.agents.reviewer.get_llm_client", return_value=mock_llm):
        result = await review_diff("+API_KEY = 'sk-hardcoded'", "Update config")

    assert result["verdict"] == "fail"
    assert result["issues"][0]["severity"] == "critical"
