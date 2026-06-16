from langchain_openai import ChatOpenAI
from api.settings import settings


def get_llm_client(model: str | None = None) -> ChatOpenAI:
    """Return a LangChain LLM client pointed at the LiteLLM proxy."""
    return ChatOpenAI(
        model=model or settings.DEFAULT_MODEL,
        base_url=settings.LITELLM_BASE_URL,
        api_key=settings.LITELLM_MASTER_KEY or "sk-placeholder",
        temperature=0,
        streaming=True,
    )


def get_llm_for_task(task_type: str) -> ChatOpenAI:
    """Return the recommended model for a specific task type."""
    model_map = {
        "planning": "claude-sonnet",
        "coding": "claude-sonnet",
        "review": "claude-sonnet",
        "janitor": "claude-sonnet",
        "fast": "claude-haiku",
    }
    return get_llm_client(model=model_map.get(task_type, settings.DEFAULT_MODEL))
