from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class InteractionEventIn(BaseModel):
    actor_user_id: int = Field(..., ge=1)
    target_user_id: int = Field(..., ge=1)
    event_type: str
    timestamp: datetime

    value: Optional[float] = None
    content_id: Optional[int] = None
    session_id: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class IngestResponse(BaseModel):
    inserted_id: int


class UserScore(BaseModel):
    user_id: int
    score: float
    reason: Optional[str] = None


class SimilarUsersResponse(BaseModel):
    user_id: int
    window_days: int
    neighbors: list[UserScore]
    strategy: str = "shared_targets_count"
    generated_at: datetime


class RecommendUsersResponse(BaseModel):
    user_id: int
    window_days: int
    recommendations: list[UserScore]
    strategy: str = "neighbors_2hop_weighted"
    generated_at: datetime

