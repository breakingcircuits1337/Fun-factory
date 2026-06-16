import pytest
from unittest.mock import patch, MagicMock


def test_create_sandbox_calls_docker():
    from api.core.sandbox import create_sandbox

    mock_container = MagicMock()
    mock_client = MagicMock()
    mock_client.containers.run.return_value = mock_container

    with patch("api.core.sandbox.client", mock_client):
        container = create_sandbox("/tmp/test-workspace", "task-abc123")

    mock_client.containers.run.assert_called_once()
    call_kwargs = mock_client.containers.run.call_args
    assert call_kwargs.kwargs["network_mode"] == "none"
    assert call_kwargs.kwargs["mem_limit"] is not None
    assert call_kwargs.kwargs["detach"] is True
    assert container == mock_container


def test_exec_in_sandbox_returns_output():
    from api.core.sandbox import exec_in_sandbox

    mock_container = MagicMock()
    mock_container.exec_run.return_value = (0, b"hello world\n")

    mock_client = MagicMock()
    mock_client.containers.get.return_value = mock_container

    with patch("api.core.sandbox.client", mock_client):
        result = exec_in_sandbox("task-abc123", "echo hello world")

    assert result["exit_code"] == 0
    assert "hello world" in result["stdout"]


def test_exec_in_sandbox_not_found():
    import docker
    from api.core.sandbox import exec_in_sandbox

    mock_client = MagicMock()
    mock_client.containers.get.side_effect = docker.errors.NotFound("not found")

    with patch("api.core.sandbox.client", mock_client):
        result = exec_in_sandbox("missing-task", "ls")

    assert result["exit_code"] == -1
    assert "not found" in result["stderr"].lower()


def test_destroy_sandbox_removes_container():
    from api.core.sandbox import destroy_sandbox

    mock_container = MagicMock()
    mock_client = MagicMock()
    mock_client.containers.get.return_value = mock_container

    with patch("api.core.sandbox.client", mock_client):
        destroy_sandbox("task-abc123")

    mock_container.stop.assert_called_once()
    mock_container.remove.assert_called_once_with(force=True)
