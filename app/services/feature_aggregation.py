"""Service để aggregate events thành user-post engagement và user profile features."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.models import (
    UserInteractionEvent,
    UserPostEngagement,
    UserReelEngagement,
    UserProfileFeatures,
    Reel,
)
from app.services.scoring import event_score_from_count
from app.services.time_utils import days_ago, half_life_decay, utcnow


def compute_user_post_engagement(
    db: Session,
    *,
    window_days: int = 90,
    half_life_days: float = 30.0,
    user_id: Optional[int] = None,
    post_id: Optional[int] = None,
) -> None:
    """
    Tính toán và cập nhật bảng `user_post_engagement` từ events.

    Logic:
    1. Aggregate events theo (user_id, post_id, day, event_type) -> count
    2. Tính score cho mỗi ngày: sum(event_score_from_count(event_type, count))
    3. Áp dụng time-decay cho mỗi ngày
    4. Tổng hợp thành engagement_score cho (user_id, post_id)

    Args:
        window_days: Chỉ xử lý events trong N ngày gần đây
        half_life_days: Half-life cho time-decay
        user_id: Nếu chỉ định, chỉ tính cho user này
        post_id: Nếu chỉ định, chỉ tính cho post này
    """
    cutoff = utcnow() - timedelta(days=window_days)

    # Build query với filters
    q = (
        select(
            UserInteractionEvent.actor_user_id,
            UserInteractionEvent.content_id.label("post_id"),
            func.date(UserInteractionEvent.occurred_at).label("day"),
            UserInteractionEvent.event_type,
            func.count().label("cnt"),
            func.max(UserInteractionEvent.occurred_at).label("last_occurred_at"),
        )
        .where(
            UserInteractionEvent.occurred_at >= cutoff,
            UserInteractionEvent.content_id.isnot(None),  # Chỉ lấy events có post_id
        )
        .group_by(
            UserInteractionEvent.actor_user_id,
            UserInteractionEvent.content_id,
            func.date(UserInteractionEvent.occurred_at),
            UserInteractionEvent.event_type,
        )
    )

    if user_id is not None:
        q = q.where(UserInteractionEvent.actor_user_id == user_id)
    if post_id is not None:
        q = q.where(UserInteractionEvent.content_id == post_id)

    # Aggregate theo (user_id, post_id, day, event_type)
    daily_data: dict[tuple[int, int, datetime.date], dict[str, int]] = defaultdict(
        lambda: defaultdict(int)
    )
    last_occurred: dict[tuple[int, int, datetime.date], datetime] = {}

    for row in db.execute(q).all():
        actor_id = int(row.actor_user_id)
        post_id_val = int(row.post_id)
        day_val = row.day
        event_type = str(row.event_type).strip().lower()
        cnt = int(row.cnt)
        last_at = row.last_occurred_at

        key = (actor_id, post_id_val, day_val)
        daily_data[key][event_type] += cnt
        if last_at and (key not in last_occurred or last_at > last_occurred[key]):
            last_occurred[key] = last_at

    now = utcnow()

    # Tính engagement score với time-decay
    engagement_data: dict[tuple[int, int], dict] = defaultdict(
        lambda: {
            "score": 0.0,
            "count": 0,
            "last_interaction_at": None,
            "event_breakdown": defaultdict(int),
        }
    )

    for (user_id_val, post_id_val, d), counts_by_type in daily_data.items():
        # Base score trong 1 ngày
        base_day = 0.0
        for et, c in counts_by_type.items():
            base_day += event_score_from_count(et, c)
            engagement_data[(user_id_val, post_id_val)]["event_breakdown"][et] += c

        if base_day <= 0:
            continue

        # Time-decay
        day_for_decay = last_occurred.get((user_id_val, post_id_val, d), d)
        d_ago = days_ago(day_for_decay, ref=now)

        decay = half_life_decay(d_ago, half_life_days=half_life_days)
        engagement_data[(user_id_val, post_id_val)]["score"] += base_day * decay
        engagement_data[(user_id_val, post_id_val)]["count"] += sum(counts_by_type.values())

        # Update last_interaction_at
        last_at = last_occurred.get((user_id_val, post_id_val, d))
        if last_at:
            current_last = engagement_data[(user_id_val, post_id_val)]["last_interaction_at"]
            if current_last is None or last_at > current_last:
                engagement_data[(user_id_val, post_id_val)]["last_interaction_at"] = last_at

    # Upsert vào database
    for (user_id_val, post_id_val), data in engagement_data.items():
        stmt = insert(UserPostEngagement).values(
            user_id=user_id_val,
            post_id=post_id_val,
            engagement_score=data["score"],
            interaction_count=data["count"],
            last_interaction_at=data["last_interaction_at"],
            event_breakdown=dict(data["event_breakdown"]),
            updated_at=now,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["user_id", "post_id"],
            set_=dict(
                engagement_score=stmt.excluded.engagement_score,
                interaction_count=stmt.excluded.interaction_count,
                last_interaction_at=stmt.excluded.last_interaction_at,
                event_breakdown=stmt.excluded.event_breakdown,
                updated_at=stmt.excluded.updated_at,
            ),
        )
        db.execute(stmt)

    db.commit()


def compute_user_reel_engagement(
    db: Session,
    *,
    window_days: int = 90,
    half_life_days: float = 30.0,
    user_id: Optional[int] = None,
    reel_id: Optional[int] = None,
) -> None:
    """
    Tính toán và cập nhật bảng `user_reel_engagement` từ events.
    """
    cutoff = utcnow() - timedelta(days=window_days)

    # Build query với filters - Join với Reel để đảm bảo content_id là reel_id
    q = (
        select(
            UserInteractionEvent.actor_user_id,
            UserInteractionEvent.content_id.label("reel_id"),
            func.date(UserInteractionEvent.occurred_at).label("day"),
            UserInteractionEvent.event_type,
            func.count().label("cnt"),
            func.max(UserInteractionEvent.occurred_at).label("last_occurred_at"),
        )
        .join(Reel, UserInteractionEvent.content_id == Reel.id)
        .where(
            UserInteractionEvent.occurred_at >= cutoff,
            UserInteractionEvent.content_id.isnot(None),
        )
        .group_by(
            UserInteractionEvent.actor_user_id,
            UserInteractionEvent.content_id,
            func.date(UserInteractionEvent.occurred_at),
            UserInteractionEvent.event_type,
        )
    )

    if user_id is not None:
        q = q.where(UserInteractionEvent.actor_user_id == user_id)
    if reel_id is not None:
        q = q.where(UserInteractionEvent.content_id == reel_id)

    daily_data: dict[tuple[int, int, datetime.date], dict[str, int]] = defaultdict(
        lambda: defaultdict(int)
    )
    last_occurred: dict[tuple[int, int, datetime.date], datetime] = {}

    for row in db.execute(q).all():
        actor_id = int(row.actor_user_id)
        reel_id_val = int(row.reel_id)
        day_val = row.day
        event_type = str(row.event_type).strip().lower()
        cnt = int(row.cnt)
        last_at = row.last_occurred_at

        key = (actor_id, reel_id_val, day_val)
        daily_data[key][event_type] += cnt
        if last_at and (key not in last_occurred or last_at > last_occurred[key]):
            last_occurred[key] = last_at

    now = utcnow()
    engagement_data: dict[tuple[int, int], dict] = defaultdict(
        lambda: {
            "score": 0.0,
            "count": 0,
            "last_interaction_at": None,
            "event_breakdown": defaultdict(int),
        }
    )

    for (u_id, r_id, d), counts_by_type in daily_data.items():
        base_day = 0.0
        for et, c in counts_by_type.items():
            base_day += event_score_from_count(et, c)
            engagement_data[(u_id, r_id)]["event_breakdown"][et] += c

        if base_day <= 0:
            continue

        day_for_decay = last_occurred.get((u_id, r_id, d), d)
        d_ago = days_ago(day_for_decay, ref=now)
        decay = half_life_decay(d_ago, half_life_days=half_life_days)
        engagement_data[(u_id, r_id)]["score"] += base_day * decay
        engagement_data[(u_id, r_id)]["count"] += sum(counts_by_type.values())

        last_at = last_occurred.get((u_id, r_id, d))
        if last_at:
            curr_last = engagement_data[(u_id, r_id)]["last_interaction_at"]
            if curr_last is None or last_at > curr_last:
                engagement_data[(u_id, r_id)]["last_interaction_at"] = last_at

    for (u_id, r_id), data in engagement_data.items():
        stmt = insert(UserReelEngagement).values(
            user_id=u_id,
            reel_id=r_id,
            engagement_score=data["score"],
            interaction_count=data["count"],
            last_interaction_at=data["last_interaction_at"],
            event_breakdown=dict(data["event_breakdown"]),
            updated_at=now,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["user_id", "reel_id"],
            set_=dict(
                engagement_score=stmt.excluded.engagement_score,
                interaction_count=stmt.excluded.interaction_count,
                last_interaction_at=stmt.excluded.last_interaction_at,
                event_breakdown=stmt.excluded.event_breakdown,
                updated_at=stmt.excluded.updated_at,
            ),
        )
        db.execute(stmt)

    db.commit()


def compute_user_profile_features(
    db: Session,
    *,
    window_days: int = 90,
    user_id: Optional[int] = None,
) -> None:
    """
    Tính toán và cập nhật bảng `user_profile_features` từ events.

    Logic:
    1. Aggregate tất cả events của user trong window_days
    2. Tính các metrics: total_interactions, event_type_distribution,
       unique_posts_interacted, unique_users_interacted, last_active_at
    3. Tính avg_engagement_score từ user_post_engagement

    Args:
        window_days: Chỉ xử lý events trong N ngày gần đây
        user_id: Nếu chỉ định, chỉ tính cho user này
    """
    cutoff = utcnow() - timedelta(days=window_days)

    # Query events của user, join với Post và Reel để phân loại
    from app.models.models import Post
    q = (
        select(
            UserInteractionEvent.actor_user_id,
            UserInteractionEvent.event_type,
            UserInteractionEvent.target_user_id,
            UserInteractionEvent.content_id,
            func.max(UserInteractionEvent.occurred_at).label("last_occurred_at"),
            func.count().label("cnt"),
            func.max(Post.id).label("is_post"),
            func.max(Reel.id).label("is_reel"),
        )
        .join(Post, UserInteractionEvent.content_id == Post.id, isouter=True)
        .join(Reel, UserInteractionEvent.content_id == Reel.id, isouter=True)
        .where(UserInteractionEvent.occurred_at >= cutoff)
        .group_by(
            UserInteractionEvent.actor_user_id,
            UserInteractionEvent.event_type,
            UserInteractionEvent.target_user_id,
            UserInteractionEvent.content_id,
        )
    )

    if user_id is not None:
        q = q.where(UserInteractionEvent.actor_user_id == user_id)

    # Aggregate theo user
    user_data: dict[int, dict] = defaultdict(
        lambda: {
            "total_interactions": 0,
            "event_type_counts": defaultdict(int),
            "unique_posts": set(),
            "unique_reels": set(),
            "unique_users": set(),
            "last_active_at": None,
        }
    )

    for row in db.execute(q).all():
        actor_id = int(row.actor_user_id)
        event_type = str(row.event_type).strip().lower()
        target_id = row.target_user_id
        content_id = row.content_id
        last_at = row.last_occurred_at
        cnt = int(row.cnt)
        is_post = row.is_post is not None
        is_reel = row.is_reel is not None

        user_data[actor_id]["total_interactions"] += cnt
        user_data[actor_id]["event_type_counts"][event_type] += cnt

        if content_id:
            if is_post:
                user_data[actor_id]["unique_posts"].add(int(content_id))
            if is_reel:
                user_data[actor_id]["unique_reels"].add(int(content_id))
        
        if target_id:
            user_data[actor_id]["unique_users"].add(int(target_id))

        if last_at:
            current_last = user_data[actor_id]["last_active_at"]
            if current_last is None or last_at > current_last:
                user_data[actor_id]["last_active_at"] = last_at

    # Tính avg_engagement_score từ user_post_engagement và user_reel_engagement
    for user_id_val in user_data.keys():
        avg_post_q = (
            select(func.avg(UserPostEngagement.engagement_score))
            .where(UserPostEngagement.user_id == user_id_val)
        )
        avg_reel_q = (
            select(func.avg(UserReelEngagement.engagement_score))
            .where(UserReelEngagement.user_id == user_id_val)
        )
        
        avg_post = db.execute(avg_post_q).scalar() or 0.0
        avg_reel = db.execute(avg_reel_q).scalar() or 0.0
        
        # Weighted average based on number of interactions? 
        # Tạm thời lấy trung bình cộng hoặc max.
        user_data[user_id_val]["avg_engagement_score"] = float((avg_post + avg_reel) / 2.0)

    # Tính event_type_distribution (normalize thành tỷ lệ)
    for user_id_val, data in user_data.items():
        total = data["total_interactions"]
        if total > 0:
            distribution = {
                et: float(count) / total
                for et, count in data["event_type_counts"].items()
            }
        else:
            distribution = {}

        data["event_type_distribution"] = distribution
        data["unique_posts_interacted"] = len(data["unique_posts"])
        data["unique_reels_interacted"] = len(data["unique_reels"])
        data["unique_users_interacted"] = len(data["unique_users"])

    # Upsert vào database
    now = utcnow()
    for user_id_val, data in user_data.items():
        stmt = insert(UserProfileFeatures).values(
            user_id=user_id_val,
            total_interactions=data["total_interactions"],
            avg_engagement_score=data["avg_engagement_score"],
            event_type_distribution=data["event_type_distribution"],
            topic_distribution={},  # TODO: Extract từ meta nếu có
            last_active_at=data["last_active_at"],
            unique_posts_interacted=data["unique_posts_interacted"],
            unique_reels_interacted=data["unique_reels_interacted"],
            unique_users_interacted=data["unique_users_interacted"],
            updated_at=now,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["user_id"],
            set_=dict(
                total_interactions=stmt.excluded.total_interactions,
                avg_engagement_score=stmt.excluded.avg_engagement_score,
                event_type_distribution=stmt.excluded.event_type_distribution,
                topic_distribution=stmt.excluded.topic_distribution,
                last_active_at=stmt.excluded.last_active_at,
                unique_posts_interacted=stmt.excluded.unique_posts_interacted,
                unique_reels_interacted=stmt.excluded.unique_reels_interacted,
                unique_users_interacted=stmt.excluded.unique_users_interacted,
                updated_at=stmt.excluded.updated_at,
            ),
        )
        db.execute(stmt)

    db.commit()


def refresh_all_features(
    db: Session,
    *,
    window_days: int = 90,
    half_life_days: float = 30.0,
) -> dict[str, int]:
    """
    Refresh tất cả features (có thể chạy định kỳ bằng cron job).

    Returns:
        dict với số lượng records được cập nhật
    """
    compute_user_post_engagement(
        db, window_days=window_days, half_life_days=half_life_days
    )

    compute_user_reel_engagement(
        db, window_days=window_days, half_life_days=half_life_days
    )

    compute_user_profile_features(db, window_days=window_days)

    # Đếm số records
    user_post_count = db.execute(select(func.count(UserPostEngagement.user_id))).scalar() or 0
    user_reel_count = db.execute(select(func.count(UserReelEngagement.user_id))).scalar() or 0
    user_profile_count = db.execute(select(func.count(UserProfileFeatures.user_id))).scalar() or 0

    print(f"User post engagement records: {user_post_count}")
    print(f"User reel engagement records: {user_reel_count}")
    print(f"User profile records: {user_profile_count}")

    return {
        "user_post_engagement_records": user_post_count,
        "user_reel_engagement_records": user_reel_count,
        "user_profile_records": user_profile_count,
    }
