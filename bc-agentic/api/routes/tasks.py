import json
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import StreamingResponse
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from pydantic import BaseModel
import redis.asyncio as aioredis

from api.models import Task, TaskStatus, TaskNode
from api.settings import settings

router = APIRouter()


def _redis() -> aioredis.Redis:
    return aioredis.from_url(settings.REDIS_URL, decode_responses=True)


async def get_session():
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlmodel.ext.asyncio.session import AsyncSession
    engine = create_async_engine(settings.DATABASE_URL)
    async with AsyncSession(engine) as session:
        yield session


class TaskCreate(BaseModel):
    goal: str
    repo_url: str
    model: str = "claude-sonnet"
    created_by: str = "anonymous"
    github_issue_number: int | None = None


class TaskApprove(BaseModel):
    approved: bool
    comment: str = ""


@router.post("", response_model=Task)
async def create_task(body: TaskCreate, session: AsyncSession = Depends(get_session)):
    task = Task(
        goal=body.goal,
        repo_url=body.repo_url,
        model_used=body.model,
        created_by=body.created_by,
        github_issue_number=body.github_issue_number,
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)

    from api.core.audit import write_audit
    await write_audit(session, str(task.id), "api", "task_created",
                      details={"goal": body.goal[:200], "repo": body.repo_url},
                      model=body.model)

    from api.worker import run_task
    run_task.delay(task.id)

    return task


@router.get("/{task_id}", response_model=Task)
async def get_task(task_id: str, session: AsyncSession = Depends(get_session)):
    task = await session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("/{task_id}/nodes", response_model=list[TaskNode])
async def get_task_nodes(task_id: str, session: AsyncSession = Depends(get_session)):
    result = await session.exec(select(TaskNode).where(TaskNode.task_id == task_id))
    return result.all()


@router.get("/{task_id}/stream")
async def stream_task(task_id: str, request: Request):
    last_id = request.headers.get("Last-Event-ID", "0")

    async def event_generator():
        nonlocal last_id
        r = _redis()
        try:
            while True:
                if await request.is_disconnected():
                    break
                entries = await r.xread({f"sse:{task_id}": last_id}, count=10, block=30000)
                if not entries:
                    yield "event: ping\ndata: {}\n\n"
                    continue
                for _stream, messages in entries:
                    for msg_id, fields in messages:
                        last_id = msg_id
                        data = fields.get("data", "{}")
                        event = json.loads(data)
                        yield f"id: {msg_id}\ndata: {json.dumps(event)}\n\n"
                        if event.get("type") == "done":
                            return
        finally:
            await r.aclose()

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/{task_id}/approve")
async def approve_task(
    task_id: str, body: TaskApprove, session: AsyncSession = Depends(get_session)
):
    task = await session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status != TaskStatus.AWAITING_APPROVAL:
        raise HTTPException(status_code=400, detail="Task is not awaiting approval")

    r = _redis()
    await r.rpush(
        f"approval:{task_id}",
        json.dumps({"approved": body.approved, "comment": body.comment}),
    )
    await r.aclose()

    if not body.approved:
        task.status = TaskStatus.CANCELLED
        session.add(task)
        await session.commit()

    return {"status": "ok"}


@router.delete("/{task_id}")
async def cancel_task(task_id: str, session: AsyncSession = Depends(get_session)):
    task = await session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    task.status = TaskStatus.CANCELLED
    session.add(task)
    await session.commit()

    # Signal SSE stream to close via Redis
    r = _redis()
    await r.xadd(f"sse:{task_id}", {"data": json.dumps({"type": "done", "reason": "cancelled"})})
    await r.aclose()

    try:
        from api.core.sandbox import destroy_sandbox
        destroy_sandbox(task_id)
    except Exception:
        pass

    return {"status": "cancelled"}


@router.get("")
async def list_tasks(session: AsyncSession = Depends(get_session)):
    result = await session.exec(select(Task).order_by(Task.created_at.desc()).limit(100))
    return result.all()
