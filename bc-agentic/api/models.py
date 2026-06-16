from sqlmodel import SQLModel, Field, Column, JSON
from datetime import datetime
from enum import Enum
from typing import Optional
import uuid


class TaskStatus(str, Enum):
    PENDING = "pending"
    PLANNING = "planning"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Task(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    goal: str
    repo_url: str
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    pr_url: Optional[str] = None
    model_used: Optional[str] = None
    token_usage: int = 0
    error: Optional[str] = None
    created_by: str  # user ID
    github_issue_number: Optional[int] = None


class TaskNode(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    task_id: str = Field(foreign_key="task.id")
    description: str
    status: TaskStatus = TaskStatus.PENDING
    agent_type: str  # "coder" | "reviewer" | "janitor"
    depends_on: list[str] = Field(default=[], sa_column=Column(JSON))
    output: Optional[str] = None
    files_changed: list[str] = Field(default=[], sa_column=Column(JSON))


class AuditLog(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    task_id: Optional[str] = Field(default=None, foreign_key="task.id")
    agent_type: Optional[str] = None
    tool_call: Optional[str] = None
    input_hash: Optional[str] = None
    output_hash: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    model: Optional[str] = None
    details: Optional[str] = None


class IndexedRepo(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    url: str
    name: str
    last_indexed_at: Optional[datetime] = None
    last_commit_sha: Optional[str] = None
    file_count: int = 0
    chunk_count: int = 0
