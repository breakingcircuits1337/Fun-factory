from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import SQLModel
from sqlalchemy.ext.asyncio import create_async_engine

from api.settings import settings
from api.routes import tasks, repos, webhooks
from api.deps import verify_token
from api.core.logging import configure_logging

engine = create_async_engine(settings.DATABASE_URL, echo=settings.DEBUG)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(
    title="BC-Agentic",
    description="Self-hosted multi-LLM AI coding agent platform",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Tasks and repos require bearer token auth; webhooks use their own HMAC validation
app.include_router(tasks.router, prefix="/tasks", tags=["tasks"],
                   dependencies=[Depends(verify_token)])
app.include_router(repos.router, prefix="/repos", tags=["repos"],
                   dependencies=[Depends(verify_token)])
app.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])


@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}
