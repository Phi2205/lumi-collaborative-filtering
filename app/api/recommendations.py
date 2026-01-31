"""API routes cho recommendations."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db, verify_internal_key
from app.models import RecommendUsersResponse, SimilarUsersResponse, UserScore
from app.utils.config import settings
from app.services.recommend_db import (
    get_similar_users_shared_targets,
    recommend_popular_users,
    recommend_users_neighbors_2hop_weighted,
)

router = APIRouter(prefix="/api", tags=["recommendations"], dependencies=[Depends(verify_internal_key)])


@router.get("/similar-users/{user_id}", response_model=SimilarUsersResponse)
def similar_users(
    user_id: int,
    k: int = settings.DEFAULT_K,
    window_days: int = 30,
    db: Session = Depends(get_db),
) -> SimilarUsersResponse:
    """Lấy danh sách users tương tự với user_id (neighbors)."""
    if k < 1:
        raise HTTPException(status_code=400, detail="k must be >= 1")
    k = min(k, settings.MAX_K)
    if window_days < 1 or window_days > 365:
        raise HTTPException(status_code=400, detail="window_days must be in [1, 365]")

    neighbors, generated_at = get_similar_users_shared_targets(
        db, user_id=user_id, k=k, window_days=window_days
    )
    return SimilarUsersResponse(
        user_id=user_id,
        window_days=window_days,
        neighbors=[UserScore(user_id=n.user_id, score=n.score, reason=n.reason) for n in neighbors],
        generated_at=generated_at,
    )


@router.get("/recommend-users/{user_id}", response_model=RecommendUsersResponse)
def recommend_users(
    user_id: int,
    k: int = settings.DEFAULT_K,
    window_days: int = 30,
    neighbor_k: int = 100,
    db: Session = Depends(get_db),
) -> RecommendUsersResponse:
    """Đề xuất users cho user_id dựa trên CF (neighbors-of-neighbors)."""
    if k < 1:
        raise HTTPException(status_code=400, detail="k must be >= 1")
    k = min(k, settings.MAX_K)
    neighbor_k = max(1, min(neighbor_k, 500))
    if window_days < 1 or window_days > 365:
        raise HTTPException(status_code=400, detail="window_days must be in [1, 365]")

    recs, generated_at = recommend_users_neighbors_2hop_weighted(
        db,
        user_id=user_id,
        k=k,
        window_days=window_days,
        neighbor_k=neighbor_k,
    )
    # Fallback: nếu CF không tìm được candidate, dùng popular users
    if not recs:
        fallback_recs, generated_at = recommend_popular_users(
            db,
            exclude_user_ids={user_id},
            k=k,
            window_days=window_days,
        )
        recs = fallback_recs

    return RecommendUsersResponse(
        user_id=user_id,
        window_days=window_days,
        recommendations=[UserScore(user_id=r.user_id, score=r.score, reason=r.reason) for r in recs],
        generated_at=generated_at,
    )
