from api.settings import settings


def get_langfuse_callbacks(task_id: str, run_name: str) -> list:
    if not settings.LANGFUSE_ENABLED:
        return []
    from langfuse.callback import CallbackHandler
    return [CallbackHandler(
        public_key=settings.LANGFUSE_PUBLIC_KEY,
        secret_key=settings.LANGFUSE_SECRET_KEY,
        host=settings.LANGFUSE_HOST,
        session_id=task_id,
        trace_name=run_name,
    )]
