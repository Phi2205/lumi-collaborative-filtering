"""Service để generate reel candidates cho feed recommendation."""

from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Set

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.models.models import Friend, Reel, UserInteractionEvent, UserReelEngagement
from app.services.time_utils import days_ago, half_life_decay, utcnow


@dataclass(frozen=True)
class ReelScoreRow:
    reel_id: int
    score: float
    reason: str
    source: str  # "social", "cf", "trending", "content_based", "exploration"


def get_social_graph_reels(
    db: Session,
    *,
    user_id: int,
    exclude_reel_ids: Optional[Set[int]] = None,
    following_user_ids: Optional[Set[int]] = None,
    k: int = 100,
    window_days: int = 7,
) -> list[ReelScoreRow]:
    """
    Nguồn 1: Reels từ social graph (friends/following).
    """
    cutoff = utcnow() - timedelta(days=window_days)
    
    if following_user_ids is None:
        f1 = select(Friend.friend_id).where(Friend.user_id == user_id)
        f2 = select(Friend.user_id).where(Friend.friend_id == user_id)
        
        following_user_ids = {int(r[0]) for r in db.execute(f1).all()}
        following_user_ids.update({int(r[0]) for r in db.execute(f2).all()})
    
    if not following_user_ids:
        return []
    
    q = (
        select(
            Reel.id,
            Reel.created_at,
            func.count(UserReelEngagement.engagement_score).label("engagement_count"),
        )
        .join(UserReelEngagement, Reel.id == UserReelEngagement.reel_id, isouter=True)
        .where(
            Reel.user_id.in_(following_user_ids),
            Reel.created_at >= cutoff,
        )
        .group_by(Reel.id, Reel.created_at)
    )

    if exclude_reel_ids:
        q = q.where(Reel.id.notin_(exclude_reel_ids))

    q = q.order_by(Reel.created_at.desc()).limit(k)
    
    now = utcnow()
    candidates = []
    for row in db.execute(q).all():
        reel_id = int(row.id)
        created_at = row.created_at
        engagement_count = int(row.engagement_count or 0)
        
        days_old = days_ago(created_at, ref=now)
        recency_score = half_life_decay(days_old, half_life_days=7.0)
        engagement_score = min(engagement_count / 10.0, 1.0)
        
        score = recency_score * (1.0 + engagement_score)
        
        candidates.append(
            ReelScoreRow(
                reel_id=reel_id,
                score=score,
                reason="social_graph",
                source="social",
            )
        )
    
    return candidates


def get_cf_reels(
    db: Session,
    *,
    user_id: int,
    exclude_reel_ids: Optional[Set[int]] = None,
    k: int = 100,
    window_days: int = 30,
    neighbor_k: int = 50,
) -> list[ReelScoreRow]:
    """
    Nguồn 2: Reels từ Collaborative Filtering.
    """
    cutoff = utcnow() - timedelta(days=window_days)
    
    # 1. Tìm similar users (neighbors)
    user_targets_sq = (
        select(distinct(UserInteractionEvent.target_user_id).label("target_user_id"))
        .where(
            UserInteractionEvent.actor_user_id == user_id,
            UserInteractionEvent.occurred_at >= cutoff,
        )
        .subquery()
    )
    
    neighbors_q = (
        select(
            UserInteractionEvent.actor_user_id.label("neighbor_id"),
            func.count(distinct(UserInteractionEvent.target_user_id)).label("shared_targets"),
        )
        .where(
            UserInteractionEvent.occurred_at >= cutoff,
            UserInteractionEvent.actor_user_id != user_id,
            UserInteractionEvent.target_user_id.in_(select(user_targets_sq.c.target_user_id)),
        )
        .group_by(UserInteractionEvent.actor_user_id)
        .order_by(func.count(distinct(UserInteractionEvent.target_user_id)).desc())
        .limit(neighbor_k)
    )
    
    neighbors = db.execute(neighbors_q).all()
    if not neighbors:
        return []
    
    neighbor_ids = [int(r.neighbor_id) for r in neighbors]
    neighbor_scores = {int(r.neighbor_id): float(r.shared_targets) for r in neighbors}
    
    # 2. Lấy reels user đã tương tác (để exclude)
    # Join với Reel để đảm bảo đây là reels
    seen_reels_q = (
        select(distinct(UserInteractionEvent.content_id))
        .join(Reel, UserInteractionEvent.content_id == Reel.id)
        .where(
            UserInteractionEvent.actor_user_id == user_id,
            UserInteractionEvent.content_id.isnot(None),
            UserInteractionEvent.occurred_at >= cutoff,
        )
    )
    seen_reel_ids = {int(r[0]) for r in db.execute(seen_reels_q).all()}
    
    # 3. Lấy reels từ neighbors
    all_seen_ids = seen_reel_ids.copy()
    if exclude_reel_ids:
        all_seen_ids.update(exclude_reel_ids)

    q = (
        select(
            UserReelEngagement.reel_id,
            UserReelEngagement.engagement_score,
            UserReelEngagement.user_id,
        )
        .where(
            UserReelEngagement.user_id.in_(neighbor_ids),
            UserReelEngagement.reel_id.notin_(all_seen_ids) if all_seen_ids else True,
        )
        .order_by(UserReelEngagement.engagement_score.desc())
        .limit(k * 2)
    )
    
    reel_scores: dict[int, float] = defaultdict(float)
    for row in db.execute(q).all():
        reel_id = int(row.reel_id)
        engagement_score = float(row.engagement_score)
        neighbor_id = int(row.user_id)
        
        neighbor_weight = neighbor_scores.get(neighbor_id, 0.0)
        if neighbor_weight > 0:
            reel_scores[reel_id] += engagement_score * neighbor_weight
    
    top_reels = sorted(reel_scores.items(), key=lambda x: x[1], reverse=True)[:k]
    
    return [
        ReelScoreRow(
            reel_id=reel_id,
            score=score,
            reason="collaborative_filtering",
            source="cf",
        )
        for reel_id, score in top_reels
    ]


def get_trending_reels(
    db: Session,
    *,
    exclude_reel_ids: Optional[Set[int]] = None,
    k: int = 50,
    window_days: int = 7,
    min_engagement: float = 1.0,
) -> list[ReelScoreRow]:
    """
    Nguồn 3: Trending reels.
    """
    cutoff = utcnow() - timedelta(days=window_days)
    
    q = (
        select(
            UserReelEngagement.reel_id,
            func.sum(UserReelEngagement.engagement_score).label("total_score"),
            func.count(UserReelEngagement.user_id).label("user_count"),
            func.max(UserReelEngagement.last_interaction_at).label("last_interaction"),
        )
        .where(
            UserReelEngagement.last_interaction_at >= cutoff if cutoff else True,
        )
        .group_by(UserReelEngagement.reel_id)
        .having(func.sum(UserReelEngagement.engagement_score) >= min_engagement)
        .order_by(func.sum(UserReelEngagement.engagement_score).desc())
        .limit(k * 2)
    )
    
    if exclude_reel_ids:
        q = q.where(UserReelEngagement.reel_id.notin_(exclude_reel_ids))
    
    now = utcnow()
    candidates = []
    
    for row in db.execute(q).all():
        reel_id = int(row.reel_id)
        total_score = float(row.total_score)
        user_count = int(row.user_count)
        last_interaction = row.last_interaction
        
        recency_score = 1.0
        if last_interaction:
            days_old = days_ago(last_interaction, ref=now)
            recency_score = half_life_decay(days_old, half_life_days=3.0)
        
        diversity_bonus = min(user_count / 50.0, 1.0)
        
        score = total_score * recency_score * (1.0 + diversity_bonus * 0.2)
        
        candidates.append(
            ReelScoreRow(
                reel_id=reel_id,
                score=score,
                reason="trending",
                source="trending",
            )
        )
    
    candidates.sort(key=lambda x: x.score, reverse=True)
    return candidates[:k]


def get_content_based_reels(
    db: Session,
    *,
    user_id: int,
    exclude_reel_ids: Optional[Set[int]] = None,
    k: int = 50,
    window_days: int = 30,
) -> list[ReelScoreRow]:
    """
    Nguồn 4: Content-based (reels từ cùng authors mà user đã engage).
    """
    cutoff = utcnow() - timedelta(days=window_days)
    
    user_reels_q = (
        select(
            distinct(UserInteractionEvent.content_id).label("content_id"),
            Reel.user_id.label("author_id"),
        )
        .join(Reel, UserInteractionEvent.content_id == Reel.id)
        .where(
            UserInteractionEvent.actor_user_id == user_id,
            UserInteractionEvent.content_id.isnot(None),
            UserInteractionEvent.occurred_at >= cutoff,
        )
    )
    
    user_reels = db.execute(user_reels_q).all()
    if not user_reels:
        return []
    
    author_ids = {int(r.author_id) for r in user_reels if r.author_id}
    seen_reel_ids = {int(r.content_id) for r in user_reels if r.content_id}
    
    if not author_ids:
        return []
    
    all_exclude_ids = seen_reel_ids.copy()
    if exclude_reel_ids:
        all_exclude_ids.update(exclude_reel_ids)

    q = (
        select(Reel.id, Reel.created_at)
        .where(
            Reel.user_id.in_(author_ids),
            Reel.id.notin_(all_exclude_ids) if all_exclude_ids else True,
            Reel.created_at >= cutoff,
        )
        .order_by(Reel.created_at.desc())
        .limit(k)
    )
    
    now = utcnow()
    candidates = []
    
    for row in db.execute(q).all():
        reel_id = int(row.id)
        created_at = row.created_at
        
        days_old = days_ago(created_at, ref=now)
        score = half_life_decay(days_old, half_life_days=7.0)
        
        candidates.append(
            ReelScoreRow(
                reel_id=reel_id,
                score=score,
                reason="content_based_same_author",
                source="content_based",
            )
        )
    
    return candidates


def get_exploration_reels(
    db: Session,
    *,
    exclude_reel_ids: Optional[Set[int]] = None,
    k: int = 20,
    window_days: int = 7,
    min_engagement: float = 0.5,
) -> list[ReelScoreRow]:
    """
    Nguồn 5: Exploration (random reels nhưng có quality filter).
    """
    cutoff = utcnow() - timedelta(days=window_days)
    
    q = (
        select(
            UserReelEngagement.reel_id,
            func.avg(UserReelEngagement.engagement_score).label("avg_score"),
        )
        .where(
            UserReelEngagement.last_interaction_at >= cutoff if cutoff else True,
        )
        .group_by(UserReelEngagement.reel_id)
        .having(func.avg(UserReelEngagement.engagement_score) >= min_engagement)
        .limit(k * 3)
    )
    
    if exclude_reel_ids:
        q = q.where(UserReelEngagement.reel_id.notin_(exclude_reel_ids))
    
    all_rows = list(db.execute(q).all())
    random.shuffle(all_rows)
    rows = all_rows[:k]
    
    candidates = []
    for row in rows:
        reel_id = int(row.reel_id)
        avg_score = float(row.avg_score)
        
        candidates.append(
            ReelScoreRow(
                reel_id=reel_id,
                score=avg_score * 0.5,
                reason="exploration",
                source="exploration",
            )
        )
    
    return candidates


def generate_reel_candidates(
    db: Session,
    *,
    user_id: int,
    exclude_reel_ids: Optional[Set[int]] = None,
    k: int = 100,
    window_days: int = 30,
    following_user_ids: Optional[Set[int]] = None,
    strategy: str = "multi_source",
) -> list[ReelScoreRow]:
    """
    Generate reel candidates từ nhiều nguồn và merge lại.
    """
    all_candidates: list[ReelScoreRow] = []
    seen_reel_ids: Set[int] = set(exclude_reel_ids) if exclude_reel_ids else set()
    
    if strategy in ("multi_source", "social_only"):
        social_reels = get_social_graph_reels(
            db,
            user_id=user_id,
            exclude_reel_ids=seen_reel_ids,
            following_user_ids=following_user_ids,
            k=int(k * 0.3),
            window_days=min(window_days, 7),
        )
        all_candidates.extend(social_reels)
        seen_reel_ids.update(r.reel_id for r in social_reels)
    
    if strategy in ("multi_source", "cf_only"):
        cf_reels = get_cf_reels(
            db,
            user_id=user_id,
            exclude_reel_ids=seen_reel_ids,
            k=int(k * 0.4),
            window_days=window_days,
            neighbor_k=50,
        )
        cf_reels = [r for r in cf_reels if r.reel_id not in seen_reel_ids]
        all_candidates.extend(cf_reels)
        seen_reel_ids.update(r.reel_id for r in cf_reels)
    
    if strategy in ("multi_source", "trending_only"):
        trending_reels = get_trending_reels(
            db,
            exclude_reel_ids=seen_reel_ids,
            k=int(k * 0.2),
            window_days=min(window_days, 7),
        )
        all_candidates.extend(trending_reels)
        seen_reel_ids.update(r.reel_id for r in trending_reels)
    
    if strategy == "multi_source":
        content_reels = get_content_based_reels(
            db,
            user_id=user_id,
            exclude_reel_ids=seen_reel_ids,
            k=int(k * 0.05),
            window_days=window_days,
        )
        content_reels = [r for r in content_reels if r.reel_id not in seen_reel_ids]
        all_candidates.extend(content_reels)
        seen_reel_ids.update(r.reel_id for r in content_reels)
        
        exploration_reels = get_exploration_reels(
            db,
            exclude_reel_ids=seen_reel_ids,
            k=int(k * 0.05),
            window_days=min(window_days, 7),
        )
        all_candidates.extend(exploration_reels)
    
    reel_scores: dict[int, ReelScoreRow] = {}
    for candidate in all_candidates:
        if candidate.reel_id not in reel_scores:
            reel_scores[candidate.reel_id] = candidate
        else:
            existing = reel_scores[candidate.reel_id]
            if candidate.score > existing.score:
                reel_scores[candidate.reel_id] = candidate
    
    sorted_candidates = sorted(
        reel_scores.values(),
        key=lambda x: x.score,
        reverse=True,
    )[:k]
    
    return sorted_candidates
