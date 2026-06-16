import hashlib
import json
from datetime import datetime, timezone
from sqlmodel.ext.asyncio.session import AsyncSession
from api.models import AuditLog


async def write_audit(
    session: AsyncSession,
    task_id: str,
    agent_type: str,
    tool_call: str,
    details: dict | None = None,
    input_data: str = "",
    output_data: str = "",
    model: str | None = None,
) -> None:
    input_hash = hashlib.sha256(input_data.encode()).hexdigest()[:16] if input_data else None
    output_hash = hashlib.sha256(output_data.encode()).hexdigest()[:16] if output_data else None
    log = AuditLog(
        task_id=task_id,
        agent_type=agent_type,
        tool_call=tool_call,
        input_hash=input_hash,
        output_hash=output_hash,
        timestamp=datetime.now(timezone.utc),
        model=model,
        details=json.dumps(details) if details else None,
    )
    session.add(log)
    await session.commit()
