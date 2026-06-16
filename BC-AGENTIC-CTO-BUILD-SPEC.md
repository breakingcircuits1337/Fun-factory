# BC-AGENTIC — Open Source CTO.new Equivalent
**Breaking Circuits LLC — Internal Build Specification**
Version 1.0 | June 2026

---

## What We're Building

A self-hosted, multi-LLM AI coding agent platform that replicates the core intelligence of cto.new:
- Multi-provider LLM routing (Anthropic, OpenAI, Gemini, Ollama/local)
- Intelligent task planning: decompose a goal into a task graph, execute agents per node
- Codebase-aware context (full repo ingestion, not just open files)
- GitHub/GitLab integration: read issues, create branches, push commits, open PRs
- Pre-merge quality gates (test runner, linter, type-checker, a "janitor" agent)
- Team-ready: web UI, multi-user, audit trail

This is **not** a Claude Code wrapper. It's a standalone agentic platform you own and operate.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        BC-AGENTIC                           │
│                                                             │
│  ┌──────────┐   ┌────────────────┐   ┌──────────────────┐  │
│  │  Web UI  │──▶│  Orchestrator  │──▶│   LLM Router     │  │
│  │ (React)  │   │  (FastAPI)     │   │ (LiteLLM proxy)  │  │
│  └──────────┘   └───────┬────────┘   └──────────────────┘  │
│                         │                                   │
│              ┌──────────▼──────────┐                        │
│              │    Task Graph (DAG)  │                        │
│              │  ┌────┐  ┌────┐     │                        │
│              │  │ N1 │  │ N2 │...  │                        │
│              │  └────┘  └────┘     │                        │
│              └──────────┬──────────┘                        │
│                         │                                   │
│         ┌───────────────┼───────────────┐                   │
│         ▼               ▼               ▼                   │
│    ┌─────────┐    ┌─────────┐    ┌─────────────┐           │
│    │  Coder  │    │Reviewer │    │   Janitor   │           │
│    │  Agent  │    │  Agent  │    │   Agent     │           │
│    └────┬────┘    └────┬────┘    └──────┬──────┘           │
│         │              │                │                   │
│    ┌────▼──────────────▼────────────────▼────┐              │
│    │           Sandbox (Docker)               │              │
│    │  git · bash · pytest · ruff · mypy       │              │
│    └──────────────────────────────────────────┘              │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Integrations: GitHub · GitLab · Linear · Jira · Slack│  │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## Tech Stack

| Layer | Choice | Why |
|---|---|---|
| Backend API | **FastAPI** (Python) | Async, fast, easy WebSocket support |
| Task Queue | **Celery + Redis** | Distributed async task execution |
| LLM Routing | **LiteLLM** (self-hosted proxy) | Unified API across 100+ providers |
| Agent Framework | **LangGraph** | Stateful DAG-based agents, production-ready |
| Codebase Index | **tree-sitter + ChromaDB** | Fast AST parsing + semantic vector search |
| Sandbox | **Docker SDK (Python)** | Isolated per-task containers |
| Web UI | **React + Vite + Tailwind** | Fast, hackable |
| Auth | **Authelia** or **Keycloak** | Self-hosted SSO, LDAP-ready for BC clients |
| DB | **PostgreSQL** | Task history, user state, audit logs |
| Secrets | **Vault (HashiCorp)** or `.env` behind BC firewall | Don't embed API keys |
| Observability | **Grafana + Loki + Tempo** | Logs, traces — hooks into BC monitoring stack |

---

## Component Breakdown

### 1. LLM Router (LiteLLM Proxy)

Run LiteLLM as a sidecar service. It normalizes all model APIs to the OpenAI spec so agents don't care which provider they're hitting.

```yaml
# litellm_config.yaml
model_list:
  - model_name: "claude-sonnet"
    litellm_params:
      model: "anthropic/claude-sonnet-4-6"
      api_key: "os.environ/ANTHROPIC_API_KEY"
  - model_name: "gpt-4o"
    litellm_params:
      model: "openai/gpt-4o"
      api_key: "os.environ/OPENAI_API_KEY"
  - model_name: "local-llm"
    litellm_params:
      model: "ollama/codellama:70b"
      api_base: "http://localhost:11434"
router_settings:
  routing_strategy: "usage-based-routing"
  fallbacks: [{"claude-sonnet": ["gpt-4o", "local-llm"]}]
```

### 2. Orchestrator (FastAPI)

Core API server. Receives task requests, manages agent lifecycle, streams output to UI.

**Key endpoints:**

```
POST /tasks              — create a new task (goal + repo + model prefs)
GET  /tasks/{id}         — task status, current graph state
GET  /tasks/{id}/stream  — SSE stream of agent events
POST /tasks/{id}/approve — human-in-the-loop merge approval
DELETE /tasks/{id}       — cancel task, clean up sandbox
GET  /repos              — list indexed repos
POST /repos/sync         — trigger re-index of a repo
```

### 3. Task Planner Agent

Receives a natural language goal and codebase context, outputs a DAG of subtasks.

**Prompt pattern (LangGraph node):**

```python
PLANNER_SYSTEM = """
You are a senior software architect. Given a goal and codebase summary,
decompose the work into atomic, parallelizable tasks.

Output JSON only:
{
  "tasks": [
    {
      "id": "t1",
      "description": "...",
      "depends_on": [],
      "files_likely_affected": ["src/auth.py"],
      "agent_type": "coder" | "researcher" | "tester"
    }
  ]
}
"""
```

LangGraph executes independent nodes in parallel, dependent nodes sequentially.

### 4. Coder Agent

Executes inside a Docker sandbox. Has tools:

```python
tools = [
    read_file,       # read any file in cloned repo
    write_file,      # write/patch files
    run_command,     # execute bash (restricted to repo dir)
    search_codebase, # semantic search via ChromaDB index
    web_search,      # optional: look up docs
]
```

The agent uses ReAct (Reason + Act) loops. It reads relevant files, writes changes, runs tests, iterates until the task passes or hits max turns.

### 5. Reviewer Agent

After Coder commits, Reviewer:
- Reads the diff
- Checks for security issues (hardcoded secrets, SQL injection patterns, unsafe deserialization)
- Checks style (calls ruff, mypy)
- Outputs PASS / FAIL with inline comments

```python
REVIEWER_SYSTEM = """
You are a security-focused code reviewer. Analyze this diff for:
1. Correctness: does it solve the stated task?
2. Security: injection, auth bypass, secrets, SSRF, path traversal
3. Style: PEP8, type hints, docstrings
4. Regression risk: what else could break?

Output structured JSON: { "verdict": "pass"|"fail", "issues": [...] }
"""
```

### 6. Janitor Agent (Pre-Merge Gate)

Final pass before PR creation. Runs in sandbox:

```bash
# Janitor runs all of these and reports aggregate pass/fail
pytest --tb=short -q
ruff check .
mypy . --ignore-missing-imports
bandit -r . -ll          # security lint
```

Only if all pass does the system push the branch and open a PR.

### 7. Codebase Indexer

Runs on repo clone/sync. Builds a searchable index.

```python
# indexer.py
import tree_sitter
import chromadb

# Parse repo with tree-sitter (supports Python, JS, TS, Go, Rust, etc.)
# Chunk by function/class boundaries (not arbitrary token windows)
# Embed with local model (nomic-embed-text via Ollama) or API
# Store in ChromaDB collection keyed by repo + commit SHA
```

This is what gives agents codebase-wide context without stuffing entire repos into prompts.

### 8. Sandbox (Docker)

Each task gets an ephemeral container:

```python
# sandbox.py
import docker

client = docker.from_env()

def create_sandbox(repo_path: str, task_id: str) -> docker.models.containers.Container:
    return client.containers.run(
        image="bc-agent-sandbox:latest",
        volumes={repo_path: {"bind": "/workspace", "mode": "rw"}},
        working_dir="/workspace",
        network_mode="none",          # no network by default
        mem_limit="2g",
        cpu_quota=100000,
        detach=True,
        name=f"bc-agent-{task_id}",
        labels={"managed-by": "bc-agentic"},
    )
```

Sandbox image (`Dockerfile`):
```dockerfile
FROM python:3.12-slim
RUN apt-get update && apt-get install -y git curl build-essential
RUN pip install pytest ruff mypy bandit
RUN npm install -g typescript eslint
WORKDIR /workspace
```

### 9. GitHub/GitLab Integration

Use **PyGithub** and **python-gitlab**. On task completion:

```python
def create_pr(repo_name: str, branch: str, task: Task) -> str:
    g = Github(settings.GITHUB_TOKEN)
    repo = g.get_repo(repo_name)
    pr = repo.create_pull(
        title=f"[bc-agent] {task.description[:72]}",
        body=render_pr_body(task),   # includes task graph, agent notes, test results
        head=branch,
        base=repo.default_branch,
    )
    return pr.html_url
```

For **issue ingestion** (task creation from tickets):
```python
# Webhook handler — GitHub sends issue events here
@router.post("/webhooks/github")
async def github_webhook(payload: dict):
    if payload["action"] == "labeled" and "bc-agent" in [l["name"] for l in payload["issue"]["labels"]]:
        await create_task_from_issue(payload["issue"])
```

---

## Data Models

```python
# models.py
from sqlmodel import SQLModel, Field
from datetime import datetime
from enum import Enum
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
    completed_at: datetime | None = None
    pr_url: str | None = None
    model_used: str | None = None
    token_usage: int = 0
    error: str | None = None
    created_by: str  # user ID

class TaskNode(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    task_id: str = Field(foreign_key="task.id")
    description: str
    status: TaskStatus = TaskStatus.PENDING
    agent_type: str  # "coder" | "reviewer" | "janitor"
    depends_on: list[str] = Field(default=[], sa_column_kwargs={"type_": "JSON"})
    output: str | None = None
    files_changed: list[str] = Field(default=[], sa_column_kwargs={"type_": "JSON"})
```

---

## Security Considerations

Since this will run on BC infrastructure and potentially process municipal client repos:

**Network isolation:**
- Sandbox containers run with `network_mode="none"` by default
- Only the orchestrator has outbound access (through BC's pfSense/VGLF)
- LiteLLM proxy sits between agents and external LLM APIs — all traffic goes through it, logged

**Secrets management:**
- API keys live in Vault, injected at runtime — never in code or `.env` files in repos
- GitHub tokens scoped to minimum required permissions (repo read + PR write)
- Webhook secrets validated via HMAC

**Agent prompt injection defense:**
- Repo content is passed to agents as structured tool outputs, not raw string interpolation into system prompts
- Reviewer agent specifically scans diffs for prompt injection patterns in comments/strings

**Audit trail:**
- Every agent action logged: tool call, input hash, output hash, timestamp, model
- Stored in PostgreSQL, queryable by task/user/repo
- Feeds into BC-VIS threat intel SaaS for anomaly detection on agent behavior

**Multi-tenancy (for future BC client deployments):**
- Namespace repos and tasks by `org_id`
- Row-level security in PostgreSQL
- Separate LiteLLM budget limits per org

---

## Repo Structure

```
bc-agentic/
├── api/
│   ├── main.py              # FastAPI app
│   ├── routes/
│   │   ├── tasks.py
│   │   ├── repos.py
│   │   └── webhooks.py
│   ├── agents/
│   │   ├── planner.py       # LangGraph planner node
│   │   ├── coder.py         # ReAct coder agent
│   │   ├── reviewer.py      # Diff review agent
│   │   └── janitor.py       # Pre-merge gate
│   ├── core/
│   │   ├── sandbox.py       # Docker sandbox management
│   │   ├── indexer.py       # tree-sitter + ChromaDB
│   │   ├── llm.py           # LiteLLM client wrapper
│   │   └── integrations/
│   │       ├── github.py
│   │       ├── gitlab.py
│   │       └── linear.py
│   ├── models.py
│   └── settings.py
├── ui/
│   ├── src/
│   │   ├── components/
│   │   │   ├── TaskGraph.tsx    # D3 DAG visualizer
│   │   │   ├── AgentStream.tsx  # SSE live output
│   │   │   └── PRPreview.tsx
│   │   └── pages/
│   │       ├── Dashboard.tsx
│   │       └── TaskDetail.tsx
│   └── package.json
├── sandbox/
│   └── Dockerfile              # Agent execution image
├── litellm/
│   └── litellm_config.yaml
├── infra/
│   ├── docker-compose.yml      # Full stack local dev
│   └── k8s/                    # Helm charts for production
├── tests/
└── README.md
```

---

## Open Source Components to Pull In

Don't reinvent — integrate:

| Component | Project | License |
|---|---|---|
| Terminal agent baseline | **OpenCode** (162k stars) | MIT |
| Editor extension | **Cline** (61k stars) | Apache-2.0 |
| Multi-file git agent | **Aider** | Apache-2.0 |
| Agent framework | **LangGraph** | MIT |
| LLM proxy | **LiteLLM** | MIT |
| Code indexing | **tree-sitter** | MIT |
| Vector store | **ChromaDB** | Apache-2.0 |
| Security scanner | **Bandit** | Apache-2.0 |
| Multi-agent planner | **Bernstein** (Apache-2.0) | Apache-2.0 |

---

## Build Phases

### Phase 1 — Core (2-3 weeks)
- [ ] LiteLLM proxy running, routing to Claude + local Ollama
- [ ] FastAPI orchestrator with task CRUD
- [ ] Docker sandbox creation/teardown
- [ ] Single-agent coder loop (no planning yet): give it a file + instruction, it edits + runs tests
- [ ] GitHub integration: clone repo, push branch, open PR

### Phase 2 — Intelligence (2-3 weeks)
- [ ] Task planner agent (LangGraph DAG)
- [ ] Parallel coder agents per DAG node
- [ ] Reviewer agent with security checks
- [ ] Janitor gate (pytest + ruff + bandit)
- [ ] ChromaDB codebase indexer

### Phase 3 — UI & Team Features (2 weeks)
- [ ] React UI: task creation, DAG visualizer, live agent stream
- [ ] Multi-user auth (Authelia)
- [ ] GitHub/GitLab webhook issue ingestion
- [ ] Audit log viewer

### Phase 4 — BC Production Hardening (ongoing)
- [ ] VGLF integration for outbound LLM traffic filtering
- [ ] BC-VIS integration for agent behavior anomaly detection
- [ ] Vault secrets backend
- [ ] Multi-tenant namespace isolation
- [ ] Helm chart for Proxmox/k3s deployment

---

## Key Differentiators vs cto.new

| Feature | cto.new | BC-Agentic |
|---|---|---|
| Self-hosted | No | Yes |
| Model lock-in | No (but cloud only) | No — local models supported |
| Source available | No | Yes (MIT) |
| Security scanning | Unknown | Built-in (Bandit + custom reviewer) |
| Air-gapped operation | No | Yes (Ollama + local ChromaDB) |
| Multi-tenant isolation | Yes | Yes (row-level PG security) |
| Audit trail | No (opaque) | Full agent action log |
| VGLF integration | No | Yes |

---

## Reference Projects

- **OpenCode**: https://github.com/sst/opencode — terminal-native, 75+ providers, client/server arch
- **Cline**: https://github.com/cline/cline — VS Code agent, MCP support, huge community
- **Aider**: https://github.com/paul-gauthier/aider — gold standard for git-aware multi-file edits
- **Bernstein**: https://github.com/chernistry/bernstein — planning-to-merge pipeline (Apache-2.0)
- **LangGraph**: https://github.com/langchain-ai/langgraph — stateful agent DAGs
- **LiteLLM**: https://github.com/BerriAI/litellm — unified LLM proxy

---

*Breaking Circuits LLC — Internal Use — Not for Distribution*
