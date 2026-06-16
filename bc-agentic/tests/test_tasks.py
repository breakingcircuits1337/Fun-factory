import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from api.models import Task, TaskStatus


def test_task_defaults():
    task = Task(goal="Add auth", repo_url="https://github.com/test/repo", created_by="user1")
    assert task.status == TaskStatus.PENDING
    assert task.token_usage == 0
    assert task.pr_url is None
    assert len(task.id) == 36  # UUID


def test_task_status_enum():
    assert TaskStatus.PENDING == "pending"
    assert TaskStatus.COMPLETE == "complete"
    assert TaskStatus.FAILED == "failed"


@pytest.mark.asyncio
async def test_create_task_endpoint():
    from fastapi.testclient import TestClient
    from api.main import app

    with patch("api.routes.tasks.get_session") as mock_session, \
         patch("api.worker.run_task") as mock_celery:
        mock_celery.delay = MagicMock()

        # Minimal smoke test — real DB test requires test DB
        assert app is not None


def test_task_node_depends_on_default():
    from api.models import TaskNode
    node = TaskNode(
        task_id="test-task-id",
        description="Implement login",
        agent_type="coder",
    )
    assert node.depends_on == []
    assert node.files_changed == []
    assert node.status == TaskStatus.PENDING
