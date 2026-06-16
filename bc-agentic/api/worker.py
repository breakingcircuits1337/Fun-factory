import asyncio
import json
import os
from celery import Celery
from loguru import logger
from api.settings import settings

celery_app = Celery("bc-agentic", broker=settings.REDIS_URL, backend=settings.REDIS_URL)
celery_app.conf.task_serializer = "json"
celery_app.conf.result_serializer = "json"


def _get_approval(task_id: str, timeout: int = 3600) -> dict | None:
    """Block on Redis list until approval is pushed or timeout expires."""
    import redis as sync_redis
    r = sync_redis.from_url(settings.REDIS_URL, decode_responses=True)
    raw = r.blpop(f"approval:{task_id}", timeout=timeout)
    r.close()
    if not raw:
        return None
    return json.loads(raw[1])


async def _publish_sse(task_id: str, event: dict) -> None:
    import redis.asyncio as aioredis
    r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    await r.xadd(f"sse:{task_id}", {"data": json.dumps(event)})
    await r.aclose()


@celery_app.task(name="run_task", bind=True, max_retries=3)
def run_task(self, task_id: str):
    """Main orchestration task: plan → code → review → janitor → PR."""
    asyncio.run(_run_task_async(task_id))


async def _run_task_async(task_id: str):
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlmodel.ext.asyncio.session import AsyncSession
    from datetime import datetime, timezone

    from api.models import Task, TaskNode, TaskStatus
    from api.agents.planner import plan_task
    from api.agents.coder import run_coder
    from api.agents.reviewer import run_reviewer
    from api.agents.janitor import run_janitor
    from api.core.sandbox import create_sandbox, destroy_sandbox
    from api.core.indexer import search_codebase
    from api.core.integrations.github import clone_repo, create_pr, push_branch, get_repo_full_name
    from api.core.llm import create_task_virtual_key, delete_task_virtual_key
    from api.core.audit import write_audit

    engine = create_async_engine(settings.DATABASE_URL)
    log = logger.bind(task_id=task_id)

    async with AsyncSession(engine) as session:
        task = await session.get(Task, task_id)
        if not task:
            return

        workspace = os.path.join(settings.WORKSPACE_BASE, task_id)
        os.makedirs(workspace, exist_ok=True)

        # Create a budget-scoped virtual key for this task
        virtual_key: str | None = None
        try:
            virtual_key = await create_task_virtual_key(task_id)
        except Exception as e:
            log.warning(f"virtual_key_failed: {e} — falling back to master key")

        try:
            task.status = TaskStatus.PLANNING
            session.add(task)
            await session.commit()
            log.info("task_started")
            await _publish_sse(task_id, {"type": "status", "status": "planning"})

            clone_repo(task.repo_url, workspace)

            from api.core.indexer import index_repo
            index_repo(workspace, task_id)

            search_results = search_codebase(task.goal, repo_id=task_id, n_results=10)
            codebase_summary = "\n".join(r["content"][:200] for r in search_results) or "No index available"

            subtasks = await plan_task(
                task.goal,
                codebase_summary,
                task.model_used or "claude-sonnet",
                task_id=task_id,
                api_key=virtual_key,
            )
            log.info(f"planning_complete subtask_count={len(subtasks)}")
            await write_audit(session, task_id, "planner", "plan_complete",
                              details={"subtask_count": len(subtasks)})

            # Plan Mode: post plan to GitHub and wait for label approval
            if settings.PLAN_MODE_ENABLED and task.github_issue_number:
                from api.core.integrations.github import post_plan_comment, poll_for_approval_label
                import re as _re
                match = _re.search(r"github\.com/([^/]+/[^/]+?)(?:\.git)?$", task.repo_url)
                if match:
                    repo_full_name = match.group(1)
                    post_plan_comment(repo_full_name, task.github_issue_number, subtasks)
                    task.status = TaskStatus.AWAITING_APPROVAL
                    session.add(task)
                    await session.commit()
                    await _publish_sse(task_id, {"type": "status", "status": "awaiting_plan_approval"})

                    approved = await asyncio.get_event_loop().run_in_executor(
                        None, poll_for_approval_label, repo_full_name, task.github_issue_number
                    )
                    if not approved:
                        task.status = TaskStatus.CANCELLED
                        task.completed_at = datetime.now(timezone.utc)
                        session.add(task)
                        await session.commit()
                        await _publish_sse(task_id, {"type": "done", "reason": "plan_rejected"})
                        return

                    await write_audit(session, task_id, "planner", "plan_approved",
                                      details={"github_issue": task.github_issue_number})

            # Persist task nodes
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

            create_sandbox(workspace, task_id)

            task.status = TaskStatus.RUNNING
            session.add(task)
            await session.commit()
            await _publish_sse(task_id, {"type": "status", "status": "running"})

            # Execute coder nodes (respecting dependency order)
            completed: set[str] = set()
            for st_id, node in nodes:
                # Wait for dependencies to complete
                deps = [d for d in node.depends_on if d not in completed]
                wait_iters = 0
                while deps:
                    await asyncio.sleep(1)
                    deps = [d for d in node.depends_on if d not in completed]
                    wait_iters += 1
                    if wait_iters > 3600:
                        raise RuntimeError(f"Dependency timeout waiting for: {deps}")

                node.status = TaskStatus.RUNNING
                session.add(node)
                await session.commit()
                await _publish_sse(task_id, {"type": "node_start", "node_id": str(node.id),
                                             "description": node.description})

                output = await run_coder(
                    task_id=task_id,
                    description=node.description,
                    repo_id=task_id,
                    model=task.model_used or "claude-sonnet",
                    api_key=virtual_key,
                )
                node.output = output
                node.status = TaskStatus.COMPLETE
                session.add(node)
                await session.commit()
                completed.add(st_id)

                await write_audit(session, task_id, "coder", "node_complete",
                                  details={"node_id": str(node.id),
                                           "description": node.description[:100]})
                await _publish_sse(task_id, {"type": "node_done", "node_id": str(node.id)})

            # Review gate
            review_result = await run_reviewer(
                task_id, task.goal, task.model_used or "claude-sonnet", api_key=virtual_key
            )
            await write_audit(session, task_id, "reviewer", "reviewer_verdict",
                              details={"verdict": review_result.get("verdict"),
                                       "summary": str(review_result.get("summary", ""))[:200]})
            await _publish_sse(task_id, {"type": "review_done", "verdict": review_result.get("verdict")})

            if review_result.get("verdict") == "fail":
                critical = [i for i in review_result.get("issues", [])
                            if i.get("severity") in ("critical", "high")]
                if critical:
                    task.status = TaskStatus.FAILED
                    task.error = f"Review failed: {review_result.get('summary')}"
                    task.completed_at = datetime.now(timezone.utc)
                    session.add(task)
                    await session.commit()
                    await _publish_sse(task_id, {"type": "done", "reason": "review_failed"})
                    return

            # Janitor gate
            janitor_result = await run_janitor(task_id, api_key=virtual_key)
            await write_audit(session, task_id, "janitor", "janitor_verdict",
                              details={"verdict": janitor_result.get("verdict"),
                                       "summary": str(janitor_result.get("summary", ""))[:200]})
            await _publish_sse(task_id, {"type": "janitor_done", "verdict": janitor_result.get("verdict")})

            if janitor_result.get("verdict") == "fail":
                task.status = TaskStatus.FAILED
                task.error = f"Janitor failed: {janitor_result.get('summary')}"
                task.completed_at = datetime.now(timezone.utc)
                session.add(task)
                await session.commit()
                await _publish_sse(task_id, {"type": "done", "reason": "janitor_failed"})
                return

            # Human-in-the-loop: wait for approval via Redis (survives API restarts)
            task.status = TaskStatus.AWAITING_APPROVAL
            session.add(task)
            await session.commit()
            await _publish_sse(task_id, {"type": "status", "status": "awaiting_approval"})

            approval_event = await asyncio.get_event_loop().run_in_executor(
                None, _get_approval, task_id
            )

            if not approval_event or not approval_event.get("approved", False):
                task.status = TaskStatus.CANCELLED
                task.completed_at = datetime.now(timezone.utc)
                session.add(task)
                await session.commit()
                await _publish_sse(task_id, {"type": "done", "reason": "rejected"})
                return

            # Push branch and open PR
            branch_name = f"bc-agent/{task_id[:8]}"
            push_branch(workspace, task.repo_url, branch_name, settings.GITHUB_TOKEN or "")
            repo_full_name = get_repo_full_name(task.repo_url)
            pr_url = create_pr(repo_full_name, branch_name, task)

            await write_audit(session, task_id, "coder", "pr_opened",
                              details={"pr_url": pr_url, "branch": branch_name})

            task.status = TaskStatus.COMPLETE
            task.pr_url = pr_url
            task.completed_at = datetime.now(timezone.utc)
            session.add(task)
            await session.commit()

            log.info(f"task_complete pr_url={pr_url}")
            await _publish_sse(task_id, {"type": "done", "pr_url": pr_url})

        except Exception as e:
            log.exception("task_failed")
            task.status = TaskStatus.FAILED
            task.error = str(e)
            task.completed_at = datetime.now(timezone.utc)
            session.add(task)
            await session.commit()
            await _publish_sse(task_id, {"type": "done", "reason": "error", "error": str(e)})
        finally:
            destroy_sandbox(task_id)
            if virtual_key:
                try:
                    await delete_task_virtual_key(virtual_key)
                except Exception:
                    pass
            await engine.dispose()


@celery_app.task(name="index_repo")
def index_repo(repo_id: str, repo_url: str):
    """Clone and index a repository for semantic search."""
    asyncio.run(_index_repo_async(repo_id, repo_url))


async def _index_repo_async(repo_id: str, repo_url: str):
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlmodel.ext.asyncio.session import AsyncSession
    from datetime import datetime, timezone
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
            result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmpdir,
                                    capture_output=True, text=True)
            sha = result.stdout.strip()
            stats = do_index(tmpdir, repo_id, commit_sha=sha)
            repo.last_indexed_at = datetime.now(timezone.utc)
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
    from api.core.audit import write_audit

    engine = create_async_engine(settings.DATABASE_URL)
    goal = f"#{issue_number}: {title}\n\n{body[:500]}"

    async with AsyncSession(engine) as session:
        task = Task(
            goal=goal,
            repo_url=repo_url,
            created_by="github-webhook",
            github_issue_number=issue_number,
        )
        session.add(task)
        await session.commit()
        await session.refresh(task)

        await write_audit(session, str(task.id), "webhook", "task_created",
                          details={"issue_number": issue_number, "repo": repo_url})

        run_task.delay(task.id)

    await engine.dispose()
