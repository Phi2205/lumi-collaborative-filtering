"""Main FastAPI application."""

from __future__ import annotations

from fastapi import FastAPI

from app.api import interactions, recommendations
from app.utils.init_db import init_db


app = FastAPI(title="Lumi CF (user-to-user)", version="1.0.0")


@app.on_event("startup")
def _startup() -> None:
    """Initialize database on startup."""
    init_db()


# Include routers
app.include_router(interactions.router)
app.include_router(recommendations.router)


@app.get("/health")
def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}
