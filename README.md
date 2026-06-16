# Fun Factory — Breaking Circuits LLC

Internal monorepo for BC tooling and platforms.

---

## Projects

### [`bc-agentic/`](./bc-agentic)

A self-hosted, multi-LLM AI coding agent platform — BC's open-source equivalent of cto.new.

**What it does:**
- Accepts a natural language goal + GitHub repo URL
- Decomposes the goal into a parallelizable task DAG using Claude
- Spins up isolated Docker sandboxes to run Coder agents (ReAct loop: read → write → test → iterate)
- Gates every change through a Reviewer agent (security-focused diff analysis) and a Janitor (pytest + ruff + mypy + bandit)
- Requires human approval before pushing a branch and opening a PR
- Streams all agent output live to a React UI

**Stack:** FastAPI · Celery · LangGraph · LiteLLM · ChromaDB · Docker · React + Vite + Tailwind · PostgreSQL · Redis

**Quick start:**
```bash
cd bc-agentic
cp .env.example .env          # add ANTHROPIC_API_KEY, GITHUB_TOKEN, etc.
docker build -t bc-agent-sandbox:latest sandbox/
docker compose -f infra/docker-compose.yml up -d
# UI → http://localhost:3000  |  API → http://localhost:8000
```

See [`bc-agentic/README.md`](./bc-agentic/README.md) for full docs.

---

*Breaking Circuits LLC — Internal Use*
