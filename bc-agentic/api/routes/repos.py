from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from pydantic import BaseModel

from api.models import IndexedRepo
from api.settings import settings

router = APIRouter()


async def get_session():
    from sqlalchemy.ext.asyncio import create_async_engine
    engine = create_async_engine(settings.DATABASE_URL)
    async with AsyncSession(engine) as session:
        yield session


class RepoSync(BaseModel):
    url: str
    name: str = ""


@router.get("", response_model=list[IndexedRepo])
async def list_repos(session: AsyncSession = Depends(get_session)):
    result = await session.exec(select(IndexedRepo).order_by(IndexedRepo.last_indexed_at.desc()))
    return result.all()


@router.post("/sync")
async def sync_repo(body: RepoSync, session: AsyncSession = Depends(get_session)):
    # Check if repo already tracked
    result = await session.exec(select(IndexedRepo).where(IndexedRepo.url == body.url))
    repo = result.first()

    if not repo:
        name = body.name or body.url.split("/")[-1].replace(".git", "")
        repo = IndexedRepo(url=body.url, name=name)
        session.add(repo)
        await session.commit()
        await session.refresh(repo)

    # Dispatch indexing to Celery
    from api.worker import index_repo
    index_repo.delay(repo.id, body.url)

    return {"status": "indexing", "repo_id": repo.id}


@router.get("/{repo_id}", response_model=IndexedRepo)
async def get_repo(repo_id: str, session: AsyncSession = Depends(get_session)):
    repo = await session.get(IndexedRepo, repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repo not found")
    return repo
