from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, Iterable, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.services.time_utils import days_ago, half_life_decay, utcnow
from app.models import UserInteractionEvent
from app.services.scoring import event_score_from_count


@dataclass(frozen=True)
class PairScore:
    actor_user_id: int
    target_user_id: int
    score: float


def aggregate_pair_scores(
    db: Session,
    *,
    window_days: int = 30,
    half_life_days: float = 30.0,
) -> list[PairScore]:
    """
    Bước 4: Preprocess (dedup/aggregate + time-decay + outlier cap/normalize input cho CF).

    - Dedup/Aggregate:
      + gom theo (actor, target, day, event_type) → count
      + tính score base bằng event_score_from_count(event_type, count)
    - Time-decay:
      + mỗi day có score_day * decay(day)
    - Trả về list PairScore(actor, target, score_raw) (chưa normalize theo actor).
    """
    cutoff = utcnow().date() - timedelta(days=window_days)

    # 1) Aggregate theo (actor, target, day, event_type)
    q = (
        select(
            UserInteractionEvent.actor_user_id,
            UserInteractionEvent.target_user_id,
            func.date(UserInteractionEvent.occurred_at).label("day"),
            UserInteractionEvent.event_type,
            func.count().label("cnt"),
            func.max(UserInteractionEvent.occurred_at).label("last_occurred_at"),
        )
        .where(UserInteractionEvent.occurred_at >= cutoff)
        .group_by(
            UserInteractionEvent.actor_user_id,
            UserInteractionEvent.target_user_id,
            func.date(UserInteractionEvent.occurred_at),
            UserInteractionEvent.event_type,
        )
    )

    # (actor, target, day) -> {event_type -> count}
    daily_counts: Dict[Tuple[int, int, date], Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    last_occurred: Dict[Tuple[int, int, date], date] = {}

    for actor_id, target_id, day_val, event_type, cnt, last_occurred_at in db.execute(q).all():
        actor = int(actor_id)
        target = int(target_id)
        d: date = day_val
        key = (actor, target, d)
        daily_counts[key][str(event_type).strip().lower()] += int(cnt)
        if last_occurred_at is not None:
            last_occurred[key] = last_occurred_at.date()

    now = utcnow()

    # 2) Tính score cho từng (actor, target) bằng cách cộng score_day * decay
    pair_scores: Dict[Tuple[int, int], float] = defaultdict(float)

    for (actor, target, d), counts_by_type in daily_counts.items():
        # base score trong 1 ngày: sum theo event_type
        base_day = 0.0
        for et, c in counts_by_type.items():
            base_day += event_score_from_count(et, c)
        if base_day <= 0:
            continue

        # days_ago tính từ ngày gần nhất (nếu có), fallback = d
        day_for_decay = last_occurred.get((actor, target, d), d)
        d_ago = days_ago(day_for_decay, ref=now)
        decay = half_life_decay(d_ago, half_life_days=half_life_days)

        pair_scores[(actor, target)] += base_day * decay

    return [
        PairScore(actor_user_id=actor, target_user_id=target, score=score)
        for (actor, target), score in pair_scores.items()
        if score > 0
    ]


def cap_outliers_iqr(values: Iterable[float], *, factor: float = 1.5) -> tuple[float, float]:
    """
    Tính ngưỡng IQR để cap outliers:
    - Q1, Q3, IQR = Q3 - Q1
    - lower = Q1 - factor * IQR
    - upper = Q3 + factor * IQR

    Trả về (lower, upper). Nếu số lượng điểm < 4 thì trả về (min, max).
    """
    data = sorted(float(v) for v in values if v is not None)
    n = len(data)
    if n == 0:
        return 0.0, 0.0
    if n < 4:
        return data[0], data[-1]

    def _percentile(sorted_vals: list[float], p: float) -> float:
        k = (len(sorted_vals) - 1) * p
        f = int(k)
        c = min(f + 1, len(sorted_vals) - 1)
        if f == c:
            return sorted_vals[f]
        d = k - f
        return sorted_vals[f] * (1 - d) + sorted_vals[c] * d

    q1 = _percentile(data, 0.25)
    q3 = _percentile(data, 0.75)
    iqr = q3 - q1
    if iqr <= 0:
        return data[0], data[-1]
    lower = q1 - factor * iqr
    upper = q3 + factor * iqr
    return float(lower), float(upper)


def normalize_by_actor_l2(pairs: list[PairScore]) -> list[PairScore]:
    """
    Normalize score theo từng actor (row-normalize, L2):
    - Với mỗi actor, chia score của từng target cho norm L2 của vector score.
    """
    from math import sqrt

    by_actor: Dict[int, Dict[int, float]] = defaultdict(dict)
    for p in pairs:
        by_actor[p.actor_user_id][p.target_user_id] = p.score

    normalized: list[PairScore] = []
    for actor, targets in by_actor.items():
        norm2 = sqrt(sum(v * v for v in targets.values()))
        if norm2 <= 0:
            # nếu actor chỉ có 1–2 điểm nhỏ, giữ nguyên
            for t, s in targets.items():
                normalized.append(PairScore(actor_user_id=actor, target_user_id=t, score=s))
            continue
        inv = 1.0 / norm2
        for t, s in targets.items():
            normalized.append(PairScore(actor_user_id=actor, target_user_id=t, score=s * inv))
    return normalized


def compute_sparsity(num_rows: int, num_cols: int, nnz: int) -> float:
    """
    Tính sparsity của ma trận:
    sparsity = 1 - (nnz / (num_rows * num_cols))
    """
    if num_rows <= 0 or num_cols <= 0:
        return 1.0
    total = float(num_rows) * float(num_cols)
    density = float(nnz) / total
    return float(1.0 - density)

