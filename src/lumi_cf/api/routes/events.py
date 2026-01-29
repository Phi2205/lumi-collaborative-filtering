from __future__ import annotations

from fastapi import APIRouter

from lumi_cf.api.schemas import IngestResponse, InteractionEventIn
from lumi_cf.db import SessionLocal
from lumi_cf.services.ingest import ingest_event


router = APIRouter()


@router.post("/events", response_model=IngestResponse)
def post_event(evt: InteractionEventIn) -> IngestResponse:
    with SessionLocal() as db:
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

