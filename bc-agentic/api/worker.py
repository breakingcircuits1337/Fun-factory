import asyncio
import os
from celery import Celery
from api.settings import settings

celery_app = Celery("bc-agentic", broker=settings.REDIS_URL, backend=settings.REDIS_URL)
celery_app.conf.task_serializer = "json"
celery_app.conf.result_serializer = "json"


@celery_app.task(name="run_task", bind=True, max_retries=3)
def run_task(self, task_id: str):
    """Main orchestration task: plan → code → review → janitor → PR."""
    asyncio.run(_run_task_async(task_id))


async def _run_task_async(task_id: str):
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlmodel.ext.asyncio.session import AsyncSession
    from datetime import datetime

    from api.models import Task, TaskNode, TaskStatus, AuditLog
    from api.agents.planner import plan_task
    from api.agents.coder import run_coder
    from api.agents.reviewer import run_reviewer
    from api.agents.janitor import run_janitor
    from api.core.sandbox import create_sandbox, destroy_sandbox
    from api.core.indexer import search_codebase
    from api.core.integrations.github import clone_repo, create_pr, push_branch, get_repo_full_name

    engine = create_async_engine(settings.DATABASE_URL)

    async with AsyncSession(engine) as session:
        task = await session.get(Task, task_id)
        if not task:
            return

        workspace = os.path.join(settings.WORKSPACE_BASE, task_id)
        os.makedirs(workspace, exist_ok=True)

        try:
            # Clone repo
            task.status = TaskStatus.PLANNING
            session.add(task)
            await session.commit()

            clone_repo(task.repo_url, workspace)

            # Index repo (quick in-process for now)
            from api.core.indexer import index_repo
            index_result = index_repo(workspace, task_id)

            # Get codebase summary for planner
            search_results = search_codebase(task.goal, repo_id=task_id, n_results=10)
            codebase_summary = "\n".join(r["content"][:200] for r in search_results) or "No index available"

            # Plan
            subtasks = await plan_task(task.goal, codebase_summary, task.model_used or "claude-sonnet")

            # Create TaskNode records
            nodes = []
            for st in subtasks:
                node = TaskNode(
                    task_id=task_id,
                    description=st["description"],
                    agent_type=st.get("agent_type", "coder"),
                    depends_on=st.get("depends_on", []),
                )
                session.add(node)
                nodes.append((st["id"], node))
            await session.commit()

            # Create sandbox
            create_sandbox(workspace, task_id)

            task.status = TaskStatus.RUNNING
            session.add(task)
            await session.commit()

            # Execute coder on each task node (respecting dependencies)
            node_map = {st_id: node for st_id, node in nodes}
            completed = set()

            for st, node in nodes:
                # Wait for dependencies
                deps = [d for d in node.depends_on if d not in completed]
                while deps:
                    await asyncio.sleep(1)
                    deps = [d for d in node.depends_on if d not in completed]

                node.status = TaskStatus.RUNNING
                session.add(node)
                await session.commit()

                output = await run_coder(
                    task_id=task_id,
                    description=node.description,
                    repo_id=task_id,
                    model=task.model_used or "claude-sonnet",
                )
                node.output = output
                node.status = TaskStatus.COMPLETE
                session.add(node)
                await session.commit()
                completed.add(st)

            # Review
            review_result = await run_reviewer(task_id, task.goal, task.model_used or "claude-sonnet")

            if review_result.get("verdict") == "fail":
                critical = [i for i in review_result.get("issues", []) if i.get("severity") in ("critical", "high")]
                if critical:
                    task.status = TaskStatus.FAILED
                    task.error = f"Review failed: {review_result.get('summary')}"
                    task.completed_at = datetime.utcnow()
                    session.add(task)
                    await session.commit()
                    return

            # Janitor gate
            janitor_result = await run_janitor(task_id)

            if janitor_result.get("verdict") == "fail":
                task.status = TaskStatus.FAILED
                task.error = f"Janitor failed: {janitor_result.get('summary')}"
                task.completed_at = datetime.utcnow()
                session.add(task)
                await session.commit()
                return

            # Human-in-the-loop approval
            task.status = TaskStatus.AWAITING_APPROVAL
            session.add(task)
            await session.commit()

            # Wait for approval via SSE queue
            from api.routes.tasks import get_or_create_queue
            queue = get_or_create_queue(task_id)
            approval_event = await asyncio.wait_for(queue.get(), timeout=3600)  # 1hr timeout

            if not approval_event.get("approved", False):
                task.status = TaskStatus.CANCELLED
                task.completed_at = datetime.utcnow()
                session.add(task)
                await session.commit()
                return

            # Push branch and create PR
            branch_name = f"bc-agent/{task_id[:8]}"
            push_branch(workspace, task.repo_url, branch_name, settings.GITHUB_TOKEN or "")
            repo_full_name = get_repo_full_name(task.repo_url)
            pr_url = create_pr(repo_full_name, branch_name, task)

            task.status = TaskStatus.COMPLETE
            task.pr_url = pr_url
            task.completed_at = datetime.utcnow()
            session.add(task)
            await session.commit()

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            task.completed_at = datetime.utcnow() if hasattr(datetime, 'utcnow') else None
            session.add(task)
            await session.commit()
        finally:
            destroy_sandbox(task_id)
            await engine.dispose()


@celery_app.task(name="index_repo")
def index_repo(repo_id: str, repo_url: str):
    """Clone and index a repository for semantic search."""
    import asyncio
    asyncio.run(_index_repo_async(repo_id, repo_url))


async def _index_repo_async(repo_id: str, repo_url: str):
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlmodel.ext.asyncio.session import AsyncSession
    from datetime import datetime
    from api.models import IndexedRepo
    from api.core.integrations.github import clone_repo
    from api.core.indexer import index_repo as do_index
    import tempfile, subprocess

    engine = create_async_engine(settings.DATABASE_URL)

    async with AsyncSession(engine) as session:
        repo = await session.get(IndexedRepo, repo_id)
        if not repo:
            return

        with tempfile.TemporaryDirectory() as tmpdir:
            clone_repo(repo_url, tmpdir)

            # Get HEAD SHA
            result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmpdir, capture_output=True, text=True)
            sha = result.stdout.strip()

            stats = do_index(tmpdir, repo_id, commit_sha=sha)

            repo.last_indexed_at = datetime.utcnow()
            repo.last_commit_sha = sha
            repo.file_count = stats["file_count"]
            repo.chunk_count = stats["chunk_count"]
            session.add(repo)
            await session.commit()

    await engine.dispose()


@celery_app.task(name="create_task_from_issue")
def create_task_from_issue(
    issue_number: int,
    title: str,
    body: str,
    repo_url: str,
    repo_full_name: str,
):
    """Create a BC-Agentic task from a GitHub/GitLab issue."""
    asyncio.run(_create_task_from_issue_async(issue_number, title, body, repo_url, repo_full_name))


async def _create_task_from_issue_async(issue_number, title, body, repo_url, repo_full_name):
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlmodel.ext.asyncio.session import AsyncSession
    from api.models import Task

    engine = create_async_engine(settings.DATABASE_URL)
    goal = f"#{issue_number}: {title}\n\n{body[:500]}"

    async with AsyncSession(engine) as session:
        task = Task(
            goal=goal,
            repo_url=repo_url,
            created_by="github-webhook",
        )
        session.add(task)
        await session.commit()
        await session.refresh(task)
        run_task.delay(task.id)

    await engine.dispose()
