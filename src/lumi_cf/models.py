from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, Float, Index, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from lumi_cf.db import Base


class UserInteractionEvent(Base):
    __tablename__ = "user_interaction_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    actor_user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    target_user_id: Mapped[int] = mapped_column(Integer, nullable=False)

    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    event_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    content_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    meta: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (
        Index("idx_uie_actor_time", "actor_user_id", "occurred_at"),
        Index("idx_uie_target_time", "target_user_id", "occurred_at"),
        Index("idx_uie_pair_time", "actor_user_id", "target_user_id", "occurred_at"),
        Index("idx_uie_type_time", "event_type", "occurred_at"),
    )

