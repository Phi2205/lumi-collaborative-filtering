from __future__ import annotations

from sqlalchemy.engine import make_url
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from lumi_cf.config import settings


class Base(DeclarativeBase):
    pass


def _normalize_database_url(url: str) -> str:
    """
    Accept either:
    - postgresql://... (common in hosted providers)
    - postgresql+psycopg://... (SQLAlchemy explicit driver form)
    - sqlite:///...
    and normalize Postgres URLs to use psycopg driver.
    """
    u = make_url(url)
    if u.drivername == "postgresql":
        u = u.set(drivername="postgresql+psycopg")
    return str(u)


engine = create_engine(_normalize_database_url(settings.DATABASE_URL), future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_db() -> None:
    # Import models so they are registered on Base.metadata
    from lumi_cf import models  # noqa: F401

    Base.metadata.create_all(bind=engine)

