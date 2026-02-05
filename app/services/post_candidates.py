"""Service để generate post candidates cho feed recommendation."""

from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Set

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.models.models import Post, UserInteractionEvent, UserPostEngagement
from app.services.time_utils import days_ago, half_life_decay, utcnow


@dataclass(frozen=True)
class PostScoreRow:
    post_id: int
    score: float
    reason: str
    source: str  # "social", "cf", "trending", "content_based", "exploration"


def get_social_graph_posts(
    db: Session,
    *,
    user_id: int,
    following_user_ids: Optional[Set[int]] = None,
    k: int = 100,
    window_days: int = 7,
) -> list[PostScoreRow]:
    """
    Nguồn 1: Posts từ social graph (friends/following).
    
    Args:
        following_user_ids: Set các user_id mà user đang follow (nếu None, sẽ query từ events)
        k: Số lượng posts tối đa
        window_days: Chỉ lấy posts trong N ngày gần đây
    """
    cutoff = utcnow() - timedelta(days=window_days)
    
    # Nếu không có following_user_ids, lấy từ events (users user đã tương tác)
    if following_user_ids is None:
        following_q = (
            select(distinct(UserInteractionEvent.target_user_id))
            .where(
                UserInteractionEvent.actor_user_id == user_id,
                UserInteractionEvent.occurred_at >= cutoff,
            )
        )
        following_user_ids = {int(r[0]) for r in db.execute(following_q).all()}
    
    if not following_user_ids:
        return []
    
    # Lấy posts từ following users trong window_days
    q = (
        select(
            Post.id,
            Post.created_at,
            func.count(UserPostEngagement.engagement_score).label("engagement_count"),
        )
        .join(UserPostEngagement, Post.id == UserPostEngagement.post_id, isouter=True)
        .where(
            Post.user_id.in_(following_user_ids),
            Post.created_at >= cutoff,
        )
        .group_by(Post.id, Post.created_at)
        .order_by(Post.created_at.desc())
        .limit(k)
    )
    
    now = utcnow()
    candidates = []
    for row in db.execute(q).all():
        post_id = int(row.id)
        created_at = row.created_at
        engagement_count = int(row.engagement_count or 0)
        
        # Score dựa trên recency và engagement
        days_old = days_ago(created_at, ref=now)
        recency_score = half_life_decay(days_old, half_life_days=7.0)
        engagement_score = min(engagement_count / 10.0, 1.0)  # Normalize
        
        score = recency_score * (1.0 + engagement_score)
        
        candidates.append(
            PostScoreRow(
                post_id=post_id,
                score=score,
                reason="social_graph",
                source="social",
            )
        )
    
    return candidates


def get_cf_posts(
    db: Session,
    *,
    user_id: int,
    k: int = 100,
    window_days: int = 30,
    neighbor_k: int = 50,
) -> list[PostScoreRow]:
    """
    Nguồn 2: Posts từ Collaborative Filtering (posts mà similar users đã engage).
    
    Logic:
    1. Tìm similar users (neighbors) dựa trên shared targets
    2. Lấy posts mà neighbors đã engage với engagement_score cao
    3. Loại trừ posts user đã xem/tương tác
    """
    cutoff = utcnow() - timedelta(days=window_days)
    
    # 1. Tìm similar users (neighbors)
    user_targets_sq = (
        select(distinct(UserInteractionEvent.target_user_id))
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
    
    # 2. Lấy posts user đã tương tác (để exclude)
    seen_posts_q = (
        select(distinct(UserInteractionEvent.content_id))
        .where(
            UserInteractionEvent.actor_user_id == user_id,
            UserInteractionEvent.content_id.isnot(None),
            UserInteractionEvent.occurred_at >= cutoff,
        )
    )
    seen_post_ids = {int(r[0]) for r in db.execute(seen_posts_q).all()}
    
    # 3. Lấy posts từ neighbors với engagement_score cao
    q = (
        select(
            UserPostEngagement.post_id,
            UserPostEngagement.engagement_score,
            UserPostEngagement.user_id,
        )
        .where(
            UserPostEngagement.user_id.in_(neighbor_ids),
            UserPostEngagement.post_id.notin_(seen_post_ids) if seen_post_ids else True,
        )
        .order_by(UserPostEngagement.engagement_score.desc())
        .limit(k * 2)  # Lấy nhiều hơn để aggregate
    )
    
    # Aggregate scores từ nhiều neighbors
    post_scores: dict[int, float] = defaultdict(float)
    for row in db.execute(q).all():
        post_id = int(row.post_id)
        engagement_score = float(row.engagement_score)
        neighbor_id = int(row.user_id)
        
        # Weight bằng similarity của neighbor
        neighbor_weight = neighbor_scores.get(neighbor_id, 0.0)
        if neighbor_weight > 0:
            post_scores[post_id] += engagement_score * neighbor_weight
    
    # Sort và lấy top k
    top_posts = sorted(post_scores.items(), key=lambda x: x[1], reverse=True)[:k]
    
    return [
        PostScoreRow(
            post_id=post_id,
            score=score,
            reason="collaborative_filtering",
            source="cf",
        )
        for post_id, score in top_posts
    ]


def get_trending_posts(
    db: Session,
    *,
    exclude_post_ids: Optional[Set[int]] = None,
    k: int = 50,
    window_days: int = 7,
    min_engagement: float = 1.0,
) -> list[PostScoreRow]:
    """
    Nguồn 3: Trending/Popular posts (posts có engagement cao toàn hệ thống).
    
    Args:
        exclude_post_ids: Posts cần loại trừ
        k: Số lượng posts
        window_days: Chỉ tính posts trong N ngày gần đây
        min_engagement: Engagement score tối thiểu
    """
    cutoff = utcnow() - timedelta(days=window_days)
    
    # Aggregate engagement score theo post
    q = (
        select(
            UserPostEngagement.post_id,
            func.sum(UserPostEngagement.engagement_score).label("total_score"),
            func.count(UserPostEngagement.user_id).label("user_count"),
            func.max(UserPostEngagement.last_interaction_at).label("last_interaction"),
        )
        .where(
            UserPostEngagement.last_interaction_at >= cutoff if cutoff else True,
        )
        .group_by(UserPostEngagement.post_id)
        .having(func.sum(UserPostEngagement.engagement_score) >= min_engagement)
        .order_by(func.sum(UserPostEngagement.engagement_score).desc())
        .limit(k * 2)
    )
    
    if exclude_post_ids:
        q = q.where(UserPostEngagement.post_id.notin_(exclude_post_ids))
    
    now = utcnow()
    candidates = []
    
    for row in db.execute(q).all():
        post_id = int(row.post_id)
        total_score = float(row.total_score)
        user_count = int(row.user_count)
        last_interaction = row.last_interaction
        
        # Score kết hợp total_score và recency
        recency_score = 1.0
        if last_interaction:
            days_old = days_ago(last_interaction, ref=now)
            recency_score = half_life_decay(days_old, half_life_days=3.0)
        
        # Normalize user_count (diversity bonus)
        diversity_bonus = min(user_count / 50.0, 1.0)
        
        score = total_score * recency_score * (1.0 + diversity_bonus * 0.2)
        
        candidates.append(
            PostScoreRow(
                post_id=post_id,
                score=score,
                reason="trending",
                source="trending",
            )
        )
    
    # Sort lại và lấy top k
    candidates.sort(key=lambda x: x.score, reverse=True)
    return candidates[:k]


def get_content_based_posts(
    db: Session,
    *,
    user_id: int,
    k: int = 50,
    window_days: int = 30,
) -> list[PostScoreRow]:
    """
    Nguồn 4: Content-based (posts similar với posts user đã engage).
    
    Logic đơn giản: Lấy posts từ cùng authors mà user đã engage.
    """
    cutoff = utcnow() - timedelta(days=window_days)
    
    # Lấy posts user đã engage để tìm authors
    user_posts_q = (
        select(
            distinct(UserInteractionEvent.content_id),
            Post.user_id.label("author_id"),
        )
        .join(Post, UserInteractionEvent.content_id == Post.id)
        .where(
            UserInteractionEvent.actor_user_id == user_id,
            UserInteractionEvent.content_id.isnot(None),
            UserInteractionEvent.occurred_at >= cutoff,
        )
    )
    
    user_posts = db.execute(user_posts_q).all()
    if not user_posts:
        return []
    
    # Lấy authors và posts đã xem
    author_ids = {int(r.author_id) for r in user_posts if r.author_id}
    seen_post_ids = {int(r.content_id) for r in user_posts if r.content_id}
    
    if not author_ids:
        return []
    
    # Lấy posts mới từ các authors này
    q = (
        select(Post.id, Post.created_at)
        .where(
            Post.user_id.in_(author_ids),
            Post.id.notin_(seen_post_ids) if seen_post_ids else True,
            Post.created_at >= cutoff,
        )
        .order_by(Post.created_at.desc())
        .limit(k)
    )
    
    now = utcnow()
    candidates = []
    
    for row in db.execute(q).all():
        post_id = int(row.id)
        created_at = row.created_at
        
        # Score dựa trên recency
        days_old = days_ago(created_at, ref=now)
        score = half_life_decay(days_old, half_life_days=7.0)
        
        candidates.append(
            PostScoreRow(
                post_id=post_id,
                score=score,
                reason="content_based_same_author",
                source="content_based",
            )
        )
    
    return candidates


def get_exploration_posts(
    db: Session,
    *,
    exclude_post_ids: Optional[Set[int]] = None,
    k: int = 20,
    window_days: int = 7,
    min_engagement: float = 0.5,
) -> list[PostScoreRow]:
    """
    Nguồn 5: Exploration (random posts nhưng có quality filter).
    
    Lấy posts ngẫu nhiên nhưng có engagement tối thiểu để đảm bảo chất lượng.
    """
    cutoff = utcnow() - timedelta(days=window_days)
    
    # Lấy posts có engagement score >= min_engagement
    q = (
        select(
            UserPostEngagement.post_id,
            func.avg(UserPostEngagement.engagement_score).label("avg_score"),
        )
        .where(
            UserPostEngagement.last_interaction_at >= cutoff if cutoff else True,
        )
        .group_by(UserPostEngagement.post_id)
        .having(func.avg(UserPostEngagement.engagement_score) >= min_engagement)
        .limit(k * 3)  # Lấy nhiều hơn để random sau
    )
    
    if exclude_post_ids:
        q = q.where(UserPostEngagement.post_id.notin_(exclude_post_ids))
    
    # Random trong Python thay vì SQL để tránh compatibility issues
    all_rows = list(db.execute(q).all())
    random.shuffle(all_rows)
    rows = all_rows[:k]
    
    candidates = []
    for row in rows:
        post_id = int(row.post_id)
        avg_score = float(row.avg_score)
        
        candidates.append(
            PostScoreRow(
                post_id=post_id,
                score=avg_score * 0.5,  # Giảm score để không compete với các nguồn khác
                reason="exploration",
                source="exploration",
            )
        )
    
    return candidates


def generate_post_candidates(
    db: Session,
    *,
    user_id: int,
    k: int = 100,
    window_days: int = 30,
    following_user_ids: Optional[Set[int]] = None,
    strategy: str = "multi_source",
) -> list[PostScoreRow]:
    """
    Generate post candidates từ nhiều nguồn và merge lại.
    
    Strategies:
    - "multi_source": Kết hợp tất cả nguồn (recommended)
    - "social_only": Chỉ social graph
    - "cf_only": Chỉ collaborative filtering
    - "trending_only": Chỉ trending
    
    Args:
        user_id: User cần đề xuất posts
        k: Tổng số candidates muốn lấy
        window_days: Cửa sổ thời gian
        following_user_ids: Set users đang follow (optional)
        strategy: Strategy để generate candidates
    """
    all_candidates: list[PostScoreRow] = []
    seen_post_ids: Set[int] = set()
    
    if strategy in ("multi_source", "social_only"):
        # Nguồn 1: Social graph (30% của k)
        social_posts = get_social_graph_posts(
            db,
            user_id=user_id,
            following_user_ids=following_user_ids,
            k=int(k * 0.3),
            window_days=min(window_days, 7),
        )
        all_candidates.extend(social_posts)
        seen_post_ids.update(p.post_id for p in social_posts)
    
    if strategy in ("multi_source", "cf_only"):
        # Nguồn 2: Collaborative Filtering (40% của k)
        cf_posts = get_cf_posts(
            db,
            user_id=user_id,
            k=int(k * 0.4),
            window_days=window_days,
            neighbor_k=50,
        )
        # Loại trừ posts đã có từ social
        cf_posts = [p for p in cf_posts if p.post_id not in seen_post_ids]
        all_candidates.extend(cf_posts)
        seen_post_ids.update(p.post_id for p in cf_posts)
    
    if strategy in ("multi_source", "trending_only"):
        # Nguồn 3: Trending (20% của k)
        trending_posts = get_trending_posts(
            db,
            exclude_post_ids=seen_post_ids,
            k=int(k * 0.2),
            window_days=min(window_days, 7),
        )
        all_candidates.extend(trending_posts)
        seen_post_ids.update(p.post_id for p in trending_posts)
    
    if strategy == "multi_source":
        # Nguồn 4: Content-based (5% của k)
        content_posts = get_content_based_posts(
            db,
            user_id=user_id,
            k=int(k * 0.05),
            window_days=window_days,
        )
        content_posts = [p for p in content_posts if p.post_id not in seen_post_ids]
        all_candidates.extend(content_posts)
        seen_post_ids.update(p.post_id for p in content_posts)
        
        # Nguồn 5: Exploration (5% của k)
        exploration_posts = get_exploration_posts(
            db,
            exclude_post_ids=seen_post_ids,
            k=int(k * 0.05),
            window_days=min(window_days, 7),
        )
        all_candidates.extend(exploration_posts)
    
    # Deduplicate và sort theo score
    post_scores: dict[int, PostScoreRow] = {}
    for candidate in all_candidates:
        if candidate.post_id not in post_scores:
            post_scores[candidate.post_id] = candidate
        else:
            # Nếu có duplicate, giữ candidate có score cao hơn
            existing = post_scores[candidate.post_id]
            if candidate.score > existing.score:
                post_scores[candidate.post_id] = candidate
    
    # Sort và lấy top k
    sorted_candidates = sorted(
        post_scores.values(),
        key=lambda x: x.score,
        reverse=True,
    )[:k]
    
    return sorted_candidates
