from __future__ import annotations

from fastapi import APIRouter, HTTPException

from lumi_cf.api.schemas import RecommendUsersResponse, SimilarUsersResponse, UserScore
from lumi_cf.config import settings
from lumi_cf.db import SessionLocal
from lumi_cf.services.recommend_db import (
    get_similar_users_shared_targets,
    recommend_users_neighbors_2hop_weighted,
)


router = APIRouter()


@router.get("/similar-users/{user_id}", response_model=SimilarUsersResponse)
def similar_users(
    user_id: int,
    k: int = settings.DEFAULT_K,
    window_days: int = 30,
) -> SimilarUsersResponse:
    if k < 1:
        raise HTTPException(status_code=400, detail="k must be >= 1")
    k = min(k, settings.MAX_K)
    if window_days < 1 or window_days > 365:
        raise HTTPException(status_code=400, detail="window_days must be in [1, 365]")

    with SessionLocal() as db:
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
) -> RecommendUsersResponse:
    if k < 1:
        raise HTTPException(status_code=400, detail="k must be >= 1")
    k = min(k, settings.MAX_K)
    neighbor_k = max(1, min(neighbor_k, 500))
    if window_days < 1 or window_days > 365:
        raise HTTPException(status_code=400, detail="window_days must be in [1, 365]")

    with SessionLocal() as db:
        recs, generated_at = recommend_users_neighbors_2hop_weighted(
            db,
            user_id=user_id,
            k=k,
            window_days=window_days,
            neighbor_k=neighbor_k,
        )
        return RecommendUsersResponse(
            user_id=user_id,
            window_days=window_days,
            recommendations=[UserScore(user_id=r.user_id, score=r.score, reason=r.reason) for r in recs],
            generated_at=generated_at,
        )

