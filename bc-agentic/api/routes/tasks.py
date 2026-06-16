import asyncio
import json
from typing import AsyncIterator
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from pydantic import BaseModel

from api.models import Task, TaskStatus, TaskNode
from api.settings import settings

router = APIRouter()

# In-memory SSE queues per task_id
_sse_queues: dict[str, asyncio.Queue] = {}


def get_or_create_queue(task_id: str) -> asyncio.Queue:
    if task_id not in _sse_queues:
        _sse_queues[task_id] = asyncio.Queue()
    return _sse_queues[task_id]


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
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)

    # Dispatch to Celery worker
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
async def stream_task(task_id: str):
    queue = get_or_create_queue(task_id)

    async def event_generator() -> AsyncIterator[str]:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
                if event is None:
                    yield "event: done\ndata: {}\n\n"
                    break
                yield f"data: {json.dumps(event)}\n\n"
            except asyncio.TimeoutError:
                yield "event: ping\ndata: {}\n\n"

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

    queue = get_or_create_queue(task_id)
    await queue.put({"type": "approval", "approved": body.approved, "comment": body.comment})

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

    # Signal SSE stream to close
    queue = get_or_create_queue(task_id)
    await queue.put(None)

    # Clean up sandbox if running
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
