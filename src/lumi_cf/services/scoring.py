from __future__ import annotations

from math import log1p

from lumi_cf.core.constants import EVENT_WEIGHTS, cap_for_event


def event_score_from_count(event_type: str, count: int) -> float:
    """
    Map (event_type, count) -> implicit score theo rule ở CF_SYSTEM_STEPS.md bước 2:
    - dùng weight theo loại event (message/comment/share/like/view)
    - log-scale: log(1 + count)
    - cap count tuỳ loại để tránh dominance (đặc biệt message/view)
    """
    et = event_type.strip().lower()
    w = EVENT_WEIGHTS.get(et)
    if w is None or count <= 0:
        return 0.0
    c = min(int(count), cap_for_event(et))
    return float(w * log1p(c))

