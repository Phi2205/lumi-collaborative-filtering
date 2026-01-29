from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from lumi_cf.core.constants import ALLOWED_EVENT_TYPES
from lumi_cf.core.time import utcnow
from lumi_cf.models import UserInteractionEvent


def ingest_event(
    db: Session,
    *,
    actor_user_id: int,
    target_user_id: int,
    event_type: str,
    timestamp: datetime,
    value: Optional[float] = None,
    content_id: Optional[int] = None,
    session_id: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> int:
    if actor_user_id == target_user_id:
        raise HTTPException(status_code=400, detail="self-interaction is not allowed")

    et = event_type.strip().lower()
    if et not in ALLOWED_EVENT_TYPES:
        raise HTTPException(status_code=400, detail=f"unsupported event_type: {event_type}")

    occurred_at = timestamp
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=timezone.utc)
    occurred_at = occurred_at.astimezone(timezone.utc)

    row = UserInteractionEvent(
        actor_user_id=actor_user_id,
        target_user_id=target_user_id,
        event_type=et,
        event_value=value,
        content_id=content_id,
        session_id=session_id,
        occurred_at=occurred_at,
        created_at=utcnow(),
        meta=metadata or {},
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return int(row.id)

