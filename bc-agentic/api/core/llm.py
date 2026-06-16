import httpx
from langchain_openai import ChatOpenAI
from api.settings import settings


def get_llm_client(model: str | None = None, api_key: str | None = None) -> ChatOpenAI:
    """Return a LangChain LLM client pointed at the LiteLLM proxy."""
    key = api_key or settings.LITELLM_MASTER_KEY or "sk-placeholder"
    return ChatOpenAI(
        model=model or settings.DEFAULT_MODEL,
        base_url=settings.LITELLM_BASE_URL,
        api_key=key,
        temperature=0,
        streaming=True,
    )


def get_llm_for_task(task_type: str, api_key: str | None = None) -> ChatOpenAI:
    """Return the recommended model for a specific task type."""
    model_map = {
        "planning": "claude-sonnet",
        "coding": "claude-sonnet",
        "review": "claude-sonnet",
        "janitor": "claude-sonnet",
        "fast": "claude-haiku",
    }
    return get_llm_client(model=model_map.get(task_type, settings.DEFAULT_MODEL), api_key=api_key)


async def create_task_virtual_key(task_id: str, budget_usd: float | None = None) -> str:
    """Create a LiteLLM virtual key scoped to this task with a budget limit."""
    budget = budget_usd or settings.TASK_BUDGET_USD
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.LITELLM_BASE_URL}/key/generate",
            headers={"Authorization": f"Bearer {settings.LITELLM_MASTER_KEY}"},
            json={
                "key_alias": f"task-{task_id}",
                "max_budget": budget,
                "metadata": {"task_id": task_id},
            },
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()["key"]


async def delete_task_virtual_key(virtual_key: str) -> None:
    """Delete a LiteLLM virtual key after task completion."""
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{settings.LITELLM_BASE_URL}/key/delete",
            headers={"Authorization": f"Bearer {settings.LITELLM_MASTER_KEY}"},
            json={"keys": [virtual_key]},
            timeout=10.0,
        )
