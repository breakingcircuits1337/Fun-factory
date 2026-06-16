import docker
import os
import shutil
from api.settings import settings

client = docker.from_env()


def create_sandbox(repo_path: str, task_id: str) -> docker.models.containers.Container:
    os.makedirs(repo_path, exist_ok=True)
    return client.containers.run(
        image=settings.SANDBOX_IMAGE,
        volumes={repo_path: {"bind": "/workspace", "mode": "rw"}},
        working_dir="/workspace",
        network_mode="none",
        mem_limit=settings.SANDBOX_MEMORY_LIMIT,
        cpu_quota=100000,
        detach=True,
        name=f"bc-agent-{task_id}",
        labels={"managed-by": "bc-agentic"},
    )


def exec_in_sandbox(task_id: str, command: str) -> dict:
    try:
        container = client.containers.get(f"bc-agent-{task_id}")
        exit_code, output = container.exec_run(
            cmd=["bash", "-c", command],
            stdout=True,
            stderr=True,
        )
        # output is bytes; split stdout/stderr not directly available via exec_run basic API
        return {
            "stdout": output.decode("utf-8", errors="replace") if output else "",
            "stderr": "",
            "exit_code": exit_code,
        }
    except docker.errors.NotFound:
        return {"stdout": "", "stderr": f"Container bc-agent-{task_id} not found", "exit_code": -1}
    except Exception as e:
        return {"stdout": "", "stderr": str(e), "exit_code": -1}


def destroy_sandbox(task_id: str) -> None:
    try:
        container = client.containers.get(f"bc-agent-{task_id}")
        container.stop(timeout=5)
        container.remove(force=True)
    except docker.errors.NotFound:
        pass
    except Exception:
        pass

    # Clean up workspace directory
    workspace = os.path.join(settings.WORKSPACE_BASE, task_id)
    if os.path.exists(workspace):
        shutil.rmtree(workspace, ignore_errors=True)


def list_sandboxes() -> list[dict]:
    containers = client.containers.list(filters={"label": "managed-by=bc-agentic"})
    return [
        {
            "name": c.name,
            "status": c.status,
            "task_id": c.name.replace("bc-agent-", ""),
        }
        for c in containers
    ]
