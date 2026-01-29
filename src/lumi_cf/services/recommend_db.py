from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from lumi_cf.core.time import days_ago, half_life_decay, utcnow
from lumi_cf.models import UserInteractionEvent
from lumi_cf.services.scoring import event_score_from_count


@dataclass(frozen=True)
class UserScoreRow:
    user_id: int
    score: float
    reason: str


def get_similar_users_shared_targets(
    db: Session,
    *,
    user_id: int,
    k: int,
    window_days: int,
) -> tuple[list[UserScoreRow], datetime]:
    cutoff = utcnow() - timedelta(days=window_days)

    user_targets_sq = (
        select(distinct(UserInteractionEvent.target_user_id).label("target_user_id"))
        .where(
            UserInteractionEvent.actor_user_id == user_id,
            UserInteractionEvent.occurred_at >= cutoff,
        )
        .subquery()
    )

    q = (
        select(
            UserInteractionEvent.actor_user_id.label("other_user_id"),
            func.count(distinct(UserInteractionEvent.target_user_id)).label("shared_targets"),
        )
        .where(
            UserInteractionEvent.occurred_at >= cutoff,
            UserInteractionEvent.actor_user_id != user_id,
            UserInteractionEvent.target_user_id.in_(select(user_targets_sq.c.target_user_id)),
        )
        .group_by(UserInteractionEvent.actor_user_id)
        .order_by(func.count(distinct(UserInteractionEvent.target_user_id)).desc())
        .limit(k)
    )

    rows = db.execute(q).all()
    neighbors = [
        UserScoreRow(user_id=int(r.other_user_id), score=float(r.shared_targets), reason="shared_targets")
        for r in rows
    ]
    return neighbors, utcnow()


def recommend_users_neighbors_2hop_weighted(
    db: Session,
    *,
    user_id: int,
    k: int,
    window_days: int,
    neighbor_k: int,
) -> tuple[list[UserScoreRow], datetime]:
    cutoff = utcnow() - timedelta(days=window_days)

    # Targets user already interacted with (exclude from recommendations)
    seen_q = select(distinct(UserInteractionEvent.target_user_id)).where(
        UserInteractionEvent.actor_user_id == user_id,
        UserInteractionEvent.occurred_at >= cutoff,
    )
    seen_targets = {int(r[0]) for r in db.execute(seen_q).all()}
    seen_targets.add(int(user_id))

    neighbors, generated_at = get_similar_users_shared_targets(
        db,
        user_id=user_id,
        k=neighbor_k,
        window_days=window_days,
    )
    neighbor_scores = {n.user_id: n.score for n in neighbors if n.score > 0}
    neighbor_ids = list(neighbor_scores.keys())
    if not neighbor_ids:
        return [], generated_at

    # Với mỗi (actor, target, event_type) của neighbors trong window:
    # - lấy tổng count
    # - lấy thời điểm tương tác gần nhất (max occurred_at) để tính time-decay
    agg_q = (
        select(
            UserInteractionEvent.actor_user_id,
            UserInteractionEvent.target_user_id,
            UserInteractionEvent.event_type,
            func.count().label("cnt"),
            func.max(UserInteractionEvent.occurred_at).label("last_occurred_at"),
        )
        .where(
            UserInteractionEvent.occurred_at >= cutoff,
            UserInteractionEvent.actor_user_id.in_(neighbor_ids),
        )
        .group_by(
            UserInteractionEvent.actor_user_id,
            UserInteractionEvent.target_user_id,
            UserInteractionEvent.event_type,
        )
    )

    now = utcnow()
    scores: dict[int, float] = {}
    for actor_id, target_id, event_type, cnt, last_occurred_at in db.execute(agg_q).all():
        target_id = int(target_id)
        if target_id in seen_targets:
            continue
        et = str(event_type).strip().lower()
        base = event_score_from_count(et, int(cnt))
        if base <= 0:
            continue
        d = days_ago(last_occurred_at, ref=now)
        decay = half_life_decay(d, half_life_days=float(window_days))
        contrib = float(neighbor_scores.get(int(actor_id), 0.0)) * base * decay
        if contrib <= 0:
            continue
        scores[target_id] = scores.get(target_id, 0.0) + contrib

    top = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:k]
    recs = [UserScoreRow(user_id=uid, score=sc, reason="neighbors_2hop_weighted") for uid, sc in top]
    return recs, generated_at

