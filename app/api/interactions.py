"""API routes cho logging interactions (events)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db, verify_internal_key
from app.models import InteractionEventIn, IngestResponse
from app.services.ingest import ingest_event

router = APIRouter(prefix="/api", tags=["interactions"], dependencies=[Depends(verify_internal_key)])


@router.post("/events", response_model=IngestResponse)
def post_event(evt: InteractionEventIn, db: Session = Depends(get_db)) -> IngestResponse:
    """Log một interaction event giữa 2 users."""
    inserted_id = ingest_event(
        db,
        actor_user_id=evt.actor_user_id,
        target_user_id=evt.target_user_id,
        event_type=evt.event_type,
        timestamp=evt.timestamp,
        value=evt.value,
        content_id=evt.content_id,
        session_id=evt.session_id,
        metadata=evt.metadata,
    )
    return IngestResponse(inserted_id=inserted_id)
