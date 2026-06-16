import subprocess
import gitlab
from api.settings import settings


def get_gitlab_client() -> gitlab.Gitlab:
    return gitlab.Gitlab(settings.GITLAB_URL, private_token=settings.GITLAB_TOKEN)


def clone_repo(repo_url: str, dest_path: str) -> str:
    token = settings.GITLAB_TOKEN or ""
    authenticated_url = repo_url.replace("https://", f"https://oauth2:{token}@") if token else repo_url
    result = subprocess.run(
        ["git", "clone", "--depth", "1", authenticated_url, dest_path],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Clone failed: {result.stderr}")
    return dest_path


def create_pr(project_id: str, branch: str, task) -> str:
    """Create a merge request on GitLab."""
    gl = get_gitlab_client()
    project = gl.projects.get(project_id)
    mr = project.mergerequests.create({
        "source_branch": branch,
        "target_branch": project.default_branch,
        "title": f"[bc-agent] {task.goal[:72]}",
        "description": f"Automated PR by BC-Agentic\n\nTask: {task.goal}\nTask ID: {task.id}",
    })
    return mr.web_url
