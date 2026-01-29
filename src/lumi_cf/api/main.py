from __future__ import annotations

from fastapi import FastAPI

from lumi_cf.api.routes import events, health, recommend
from lumi_cf.db import init_db


app = FastAPI(title="Lumi CF (user-to-user)")


@app.on_event("startup")
def _startup() -> None:
    init_db()


app.include_router(health.router)
app.include_router(events.router)
app.include_router(recommend.router)

