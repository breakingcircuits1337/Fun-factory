# BC-Agentic

A self-hosted, multi-LLM AI coding agent platform — Breaking Circuits LLC's open-source equivalent of [cto.new](https://cto.new).

Give it a goal and a GitHub repo URL. It plans, codes, reviews, and opens a PR — with human approval at every key step.

## Architecture

```
Web UI (React) → FastAPI Orchestrator → LiteLLM Proxy → Anthropic / OpenAI / Ollama
                        ↓
                  Task Graph (LangGraph DAG)
                 /         |          \
            Coder       Reviewer    Janitor
            Agent        Agent       Agent
                \           |          /
                 Docker / MicroVM Sandbox
                  git · pytest · ruff · mypy · bandit
                        ↓
               PostgreSQL Checkpointer
               (durable across restarts)
```

## Quick Start

```bash
cp .env.example .env
# Fill in ANTHROPIC_API_KEY, GITHUB_TOKEN, LITELLM_MASTER_KEY, API_BEARER_TOKEN

# Build sandbox image
docker build -t bc-agent-sandbox:latest sandbox/

# Start full stack (includes Langfuse observability on :3001)
docker compose -f infra/docker-compose.yml up -d

# UI available at        http://localhost:3000
# API at                 http://localhost:8000
# LiteLLM proxy at       http://localhost:4000
# Langfuse traces at     http://localhost:3001
```

### Authenticating API requests

All `/tasks` and `/repos` endpoints require a bearer token:

```bash
curl -H "Authorization: Bearer <API_BEARER_TOKEN>" http://localhost:8000/tasks
```

Set `API_BEARER_TOKEN` in your `.env` (default: `change-me-bearer-token`).

## Local Development

```bash
# Backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn api.main:app --reload

# Worker (separate terminal)
celery -A api.worker.celery_app worker --loglevel=info

# UI (separate terminal)
cd ui && npm install && npm run dev
```

## Stack

| Layer | Tech |
|---|---|
| API | FastAPI + SQLModel + PostgreSQL |
| Queue | Celery + Redis |
| LLM routing | LiteLLM proxy (virtual keys + budget enforcement) |
| Agents | LangGraph 1.x (ReAct + DAG + PostgresSaver checkpointing) |
| Code index | ChromaDB + tree-sitter |
| Sandbox | Docker SDK (plain container or MicroVM via `SANDBOX_BACKEND=microvm`) |
| Observability | Langfuse (self-hosted traces + cost tracking) |
| Logging | loguru structured JSON |
| UI | React + Vite + Tailwind + D3 |

## Features

### Agent pipeline
- **Task DAG planning** — LLM decomposes goals into parallelizable subtasks
- **Plan Mode** — planner posts its implementation plan as a GitHub issue comment; execution only begins after a human adds the `bc-approved` label
- **ReAct coder agent** — reads files, writes patches, runs tests, iterates
- **Session handoff** — when the coder approaches the token limit, it summarises progress and hands off to a fresh session (no context compression degradation)
- **Reviewer agent** — security-focused diff review (injection, secrets, SSRF, path traversal)
- **Janitor gate** — pytest + ruff + mypy + bandit must pass before PR
- **Human-in-the-loop** — final approve/reject before PR is pushed

### Infrastructure
- **Bearer token auth** — all task/repo endpoints protected
- **Redis Streams SSE** — live agent output with `Last-Event-ID` replay (survives API restarts)
- **Durable approvals** — approval gate uses Redis BLPOP instead of in-memory queues; survives restarts
- **PostgreSQL checkpointing** — full LangGraph agent state persisted via `PostgresSaver`; tasks resume after crashes
- **Per-task LLM budgets** — LiteLLM virtual key created per task with configurable USD cap (`TASK_BUDGET_USD`)
- **MicroVM sandboxes** — optional Docker Sandboxes runtime (`SANDBOX_BACKEND=microvm`) for kernel-level isolation
- **Langfuse tracing** — all agent LLM calls traced with session IDs, costs, and latency

### Integrations
- **GitHub/GitLab** — issue ingestion via webhooks, PR creation, Plan Mode label polling
- **Linear** — issue webhook trigger
- **Multi-provider LLM** — Claude, GPT-4o, local Ollama with fallbacks and usage-based routing
- **Codebase index** — semantic search across full repo (not just open files)

### Security
- Sandbox containers: `network_mode=none`, 2 GB RAM cap, no root capabilities
- MicroVM mode: per-agent Linux kernel — container escape can't reach host
- File writes via Docker `put_archive` — zero shell interpolation
- Reviewer agent scans for prompt injection, SSRF, path traversal, hardcoded secrets
- Webhook HMAC validation (GitHub SHA-256, GitLab token)
- API keys in Vault or env — never in code; missing `LITELLM_MASTER_KEY` fails fast at startup
- Full audit trail — `AuditLog` table records every lifecycle event with input/output hashes

## Configuration

Key environment variables (see `.env.example` for the full list):

| Variable | Default | Description |
|---|---|---|
| `API_BEARER_TOKEN` | `change-me-bearer-token` | Bearer token for all API calls |
| `LITELLM_MASTER_KEY` | *(required)* | LiteLLM proxy master key |
| `TASK_BUDGET_USD` | `5.0` | Per-task LLM spend cap in USD |
| `PLAN_MODE_ENABLED` | `true` | Post plan to GitHub before executing |
| `SANDBOX_BACKEND` | `docker` | `docker` or `microvm` |
| `CODER_TOKEN_LIMIT` | `80000` | Token threshold to trigger session handoff |
| `CODER_MAX_SESSIONS` | `5` | Max handoff chains per task |
| `LANGFUSE_ENABLED` | `false` | Enable Langfuse trace export |
| `LANGGRAPH_CHECKPOINTER_URL` | *(postgres DSN)* | PostgreSQL DSN for agent state (psycopg3 format) |

## Plan Mode

When `PLAN_MODE_ENABLED=true` and a task has a `github_issue_number`, the planner will:

1. Post the proposed subtask plan as a comment on the GitHub issue
2. Pause and poll for label changes
3. Resume execution when `bc-approved` is added; cancel if `bc-rejected` is added

This mirrors cto.new's Plan Mode and ensures humans review the approach before any code is written.

## Build Phases

- [x] **Phase 1** — Core: FastAPI, Celery, Docker sandbox, GitHub integration
- [x] **Phase 2** — Intelligence: LangGraph planner/coder/reviewer/janitor, ChromaDB
- [x] **Phase 3** — UI: React DAG visualizer, SSE live stream, PR approval flow
- [x] **Phase 3.5** — Hardening: auth, Redis Streams SSE, PostgresSaver, Plan Mode, session handoff, virtual keys, Langfuse, MicroVM support, AuditLog
- [ ] **Phase 4** — BC Production: Vault secrets, VGLF integration, Helm/k3s charts, multi-tenant RLS

---

*Breaking Circuits LLC — Internal Use*
