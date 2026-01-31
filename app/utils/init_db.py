"""Initialize database tables."""

from __future__ import annotations

from app.utils.database import Base, engine


def init_db() -> None:
    """Create all tables defined in models."""
    # Import models so they are registered on Base.metadata
    from app.models import UserInteractionEvent  # noqa: F401

    Base.metadata.create_all(bind=engine)
