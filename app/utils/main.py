"""Main FastAPI application."""

from __future__ import annotations

from fastapi import FastAPI

import asyncio
from app.api import interactions, recommendations
from app.utils.init_db import init_db
from app.services.feature_aggregation import refresh_all_features
from app.utils.database import SessionLocal


app = FastAPI(title="Lumi CF (user-to-user)", version="1.0.0")


async def refresh_features_background_job() -> None:
    """Vòng lặp chạy ngầm để refresh features mỗi 1 tiếng."""
    while True:
        # Chờ 1 tiếng trước khi chạy lượt tiếp theo (hoặc chạy ngay lần đầu tùy logic)
        # Nếu muốn chạy ngay khi start thì đảo ngược sleep và logic
        try:
            db = SessionLocal()
            print(f"🔄 [Background Job] Bắt đầu refresh features định kỳ...")
            result = refresh_all_features(db)
            print(f"✅ [Background Job] Hoàn tất: {result}")
            db.close()
        except Exception as e:
            print(f"❌ [Background Job] Lỗi: {e}")
        
        # Chờ 3600 giây (1 tiếng)
        await asyncio.sleep(3600)


@app.on_event("startup")
async def _startup() -> None:
    """Initialize database on startup."""
    init_db()
    # Tạo task chạy ngầm không chặn luồng chính của server
    asyncio.create_task(refresh_features_background_job())


# Include routers
app.include_router(interactions.router)
app.include_router(recommendations.router)


@app.get("/health")
def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}
