from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader
from api.settings import settings

api_key_header = APIKeyHeader(name="Authorization", auto_error=False)


async def verify_token(token: str = Security(api_key_header)) -> None:
    if not token or token != f"Bearer {settings.API_BEARER_TOKEN}":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing bearer token",
        )
