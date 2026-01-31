"""Dependencies for API routes."""

from __future__ import annotations

import os
from fastapi import Header, HTTPException

from app.utils.database import get_db

INTERNAL_SHARED_SECRET = os.getenv("INTERNAL_SHARED_SECRET")


async def verify_internal_key(x_internal_key: str | None = Header(default=None)):
    """
    Bảo vệ API nội bộ bằng shared secret.

    - Server Recommend chỉ phục vụ nếu header:
        x-internal-key: <INTERNAL_SHARED_SECRET>
    - INTERNAL_SHARED_SECRET cấu hình trong .env
    """
    if not INTERNAL_SHARED_SECRET:
        raise HTTPException(
            status_code=500,
            detail="INTERNAL_SHARED_SECRET is not configured on the server",
        )

    if x_internal_key != INTERNAL_SHARED_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")

    return True


# Re-export utils for convenience
__all__ = ["get_db", "verify_internal_key"]
