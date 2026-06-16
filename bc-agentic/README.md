# BC-Agentic

A self-hosted, multi-LLM AI coding agent platform — Breaking Circuits LLC's open-source equivalent of cto.new.

## Architecture

```
Web UI (React) → FastAPI Orchestrator → LiteLLM Proxy → Anthropic / OpenAI / Ollama
                        ↓
                  Task Graph (LangGraph DAG)
                 /         |          \
            Coder       Reviewer    Janitor
            Agent        Agent       Agent
                \           |          /
                 Docker Sandbox (isolated)
                  git · pytest · ruff · mypy · bandit
```

## Quick Start

```bash
cp .env.example .env
# Fill in ANTHROPIC_API_KEY, GITHUB_TOKEN, etc.

# Build sandbox image
docker build -t bc-agent-sandbox:latest sandbox/

# Start full stack
docker compose -f infra/docker-compose.yml up -d

# UI available at http://localhost:3000
# API at http://localhost:8000
# LiteLLM proxy at http://localhost:4000
```

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
| LLM routing | LiteLLM proxy |
| Agents | LangGraph (ReAct + DAG) |
| Code index | ChromaDB + tree-sitter |
| Sandbox | Docker SDK |
| UI | React + Vite + Tailwind + D3 |

## Features

- **Multi-provider LLM routing** — Claude, GPT-4o, local Ollama with fallbacks
- **Task DAG planning** — LLM decomposes goals into parallelizable subtasks
- **ReAct coder agent** — reads files, writes patches, runs tests, iterates
- **Reviewer agent** — security-focused diff review (injection, secrets, SSRF, path traversal)
- **Janitor gate** — pytest + ruff + mypy + bandit must all pass before PR
- **Human-in-the-loop** — approve/reject before PR is pushed
- **GitHub/GitLab/Linear** — issue ingestion via webhooks, PR creation
- **Codebase index** — semantic search across full repo (not just open files)
- **Network-isolated sandboxes** — containers run with `network_mode=none`
- **Full audit trail** — every agent action logged with input/output hashes

## Build Phases

- [x] **Phase 1** — Core: FastAPI, Celery, Docker sandbox, GitHub integration
- [x] **Phase 2** — Intelligence: LangGraph planner/coder/reviewer/janitor, ChromaDB
- [x] **Phase 3** — UI: React DAG visualizer, SSE live stream, PR approval flow
- [ ] **Phase 4** — BC Production: Vault secrets, VGLF integration, Helm/k3s charts

## Security

- Sandbox containers: `network_mode=none`, 2GB RAM cap
- Webhook HMAC validation (GitHub SHA-256, GitLab token)
- API keys in Vault or env — never in code
- Reviewer agent scans for prompt injection in code comments/strings
- Row-level PostgreSQL security ready for multi-tenant isolation

---

*Breaking Circuits LLC — Internal Use*
