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
    # Đợi 2 phút cho server khởi động ổn định trước khi chạy lần đầu
    await asyncio.sleep(120)
    while True:
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


async def self_ping_keep_alive() -> None:
    """Task tự ping chính nó để Render không 'đi ngủ' (cho gói Miễn phí)."""
    import os
    import urllib.request
    import asyncio
    
    # Lấy URL công khai của bạn
    url = os.getenv("RENDER_EXTERNAL_URL")
    if not url:
        print("💡 [Self-Ping] Bỏ qua vì RENDER_EXTERNAL_URL chưa được cấu hình.")
        return
    
    health_url = f"{url.rstrip('/')}/health"
    print(f"💓 [Self-Ping] Bắt đầu Keep-Alive cho: {health_url}")
    
    while True:
        try:
            # Gửi request trong một thread riêng để không làm treo server (non-blocking)
            def send_ping():
                with urllib.request.urlopen(health_url, timeout=15) as resp:
                    return resp.getcode()
            
            code = await asyncio.to_thread(send_ping)
            if code == 200:
                print(f"💓 [Self-Ping] Heartbeat thành công đến {health_url}")
        except Exception as e:
            print(f"⚠️ [Self-Ping] Lỗi ping: {e}")
            
        # Quay lại ngủ 5 phút (300s) - ngắn hơn để chắc chắn Render không scale-down
        await asyncio.sleep(300)


@app.on_event("startup")
async def _startup() -> None:
    """Initialize database on startup."""
    init_db()
    # Task refresh features
    asyncio.create_task(refresh_features_background_job())
    # Task keep-alive (chỉ nên bật trên Render)
    asyncio.create_task(self_ping_keep_alive())


# Include routers
app.include_router(interactions.router)
app.include_router(recommendations.router)


@app.get("/health")
def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}
