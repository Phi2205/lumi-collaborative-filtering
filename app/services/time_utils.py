"""Time utilities for decay calculations."""

from __future__ import annotations

from datetime import date, datetime, timezone


def utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def days_ago(when: datetime | date, *, ref: datetime | None = None) -> float:
    """
    Số ngày đã trôi qua từ thời điểm `when` tới `ref` (mặc định = hiện tại).
    Trả về số thực (có thể có phần thập phân).
    """
    if ref is None:
        ref = utcnow()
    if isinstance(when, datetime):
        # luôn quy về UTC để nhất quán
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        when = when.astimezone(timezone.utc)
        delta = ref - when
    else:
        delta = ref.date() - when
    return delta.total_seconds() / 86400.0


def half_life_decay(days: float, half_life_days: float = 30.0) -> float:
    """
    Hệ số time-decay dạng half-life:
    - days = 0      → 1.0
    - days = T      → 0.5  (nếu T = half_life_days)
    - days = 2 * T  → 0.25
    """
    from math import pow

    if half_life_days <= 0 or days <= 0:
        return 1.0
    return pow(2.0, -(days / half_life_days))
