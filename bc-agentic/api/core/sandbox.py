import docker
import io
import os
import posixpath
import shutil
import tarfile
from loguru import logger
from api.settings import settings

client = docker.from_env()


def create_sandbox(repo_path: str, task_id: str) -> docker.models.containers.Container:
    os.makedirs(repo_path, exist_ok=True)
    kwargs = dict(
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
    if settings.SANDBOX_BACKEND == "microvm":
        # Docker Sandboxes microVM isolation: each sandbox gets its own Linux kernel
        kwargs.update({
            "runtime": settings.MICROVM_RUNTIME,
            "security_opt": ["no-new-privileges:true"],
            "cap_drop": ["ALL"],
        })
    container = client.containers.run(**kwargs)
    logger.bind(task_id=task_id, backend=settings.SANDBOX_BACKEND).info("sandbox_created")
    return container


def exec_in_sandbox(task_id: str, command: str | list) -> dict:
    """Execute a command in the sandbox. Pass a list to avoid shell interpretation."""
    try:
        container = client.containers.get(f"bc-agent-{task_id}")
        cmd = command if isinstance(command, list) else ["bash", "-c", command]
        exit_code, output = container.exec_run(
            cmd=cmd,
            stdout=True,
            stderr=True,
        )
        return {
            "stdout": output.decode("utf-8", errors="replace") if output else "",
            "stderr": "",
            "exit_code": exit_code,
        }
    except docker.errors.NotFound:
        return {"stdout": "", "stderr": f"Container bc-agent-{task_id} not found", "exit_code": -1}
    except Exception as e:
        return {"stdout": "", "stderr": str(e), "exit_code": -1}


def write_file_in_sandbox(task_id: str, path: str, content: bytes) -> dict:
    """Write a file into the sandbox using Docker put_archive — no shell involved."""
    try:
        container = client.containers.get(f"bc-agent-{task_id}")
        dir_path = posixpath.dirname(path) or "."
        filename = posixpath.basename(path)
        # Ensure parent directory exists (safe: argv list, no shell)
        container.exec_run(cmd=["mkdir", "-p", dir_path])
        # Stream file content via tar archive — zero shell interpolation
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            info = tarfile.TarInfo(name=filename)
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
        buf.seek(0)
        container.put_archive(dir_path, buf.read())
        return {"exit_code": 0}
    except docker.errors.NotFound:
        return {"exit_code": -1, "stderr": f"Container bc-agent-{task_id} not found"}
    except Exception as e:
        return {"exit_code": 1, "stderr": str(e)}


def destroy_sandbox(task_id: str) -> None:
    try:
        container = client.containers.get(f"bc-agent-{task_id}")
        container.stop(timeout=5)
        container.remove(force=True)
        logger.bind(task_id=task_id).info("sandbox_destroyed")
    except docker.errors.NotFound:
        pass
    except Exception as e:
        logger.bind(task_id=task_id, error=str(e)).warning("sandbox_destroy_failed")

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
