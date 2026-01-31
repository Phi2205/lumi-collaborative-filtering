from __future__ import annotations

from collections import defaultdict
from math import log2
from typing import Dict, Iterable, List, Sequence, Set, Tuple


def precision_at_k(recommended: Sequence[int], relevant: Set[int], k: int) -> float:
    if k <= 0:
        return 0.0
    top = recommended[:k]
    if not top:
        return 0.0
    hits = sum(1 for r in top if r in relevant)
    return float(hits) / float(len(top))


def recall_at_k(recommended: Sequence[int], relevant: Set[int], k: int) -> float:
    if not relevant:
        return 0.0
    top = recommended[:k]
    hits = sum(1 for r in top if r in relevant)
    return float(hits) / float(len(relevant))


def average_precision_at_k(recommended: Sequence[int], relevant: Set[int], k: int) -> float:
    """
    AP@k cho 1 user:
    AP = (1 / |rel|) * sum_{i: item_i in rel} precision@i
    """
    if not relevant:
        return 0.0
    top = recommended[:k]
    score = 0.0
    hits = 0
    for i, item in enumerate(top, start=1):
        if item in relevant:
            hits += 1
            score += hits / float(i)
    return float(score) / float(len(relevant))


def mean_average_precision_at_k(
    all_recommended: Iterable[Sequence[int]],
    all_relevant: Iterable[Set[int]],
    k: int,
) -> float:
    aps: List[float] = []
    for recs, rel in zip(all_recommended, all_relevant):
        aps.append(average_precision_at_k(recs, rel, k))
    if not aps:
        return 0.0
    return float(sum(aps)) / float(len(aps))


def ndcg_at_k(recommended: Sequence[int], relevant: Dict[int, float], k: int) -> float:
    """
    NDCG@k cho 1 user.
    `relevant` là dict: item_id -> gain (ví dụ: 1 nếu chỉ cần relevant/không, hoặc số lần tương tác).
    """
    def _dcg(items: Sequence[int]) -> float:
        dcg = 0.0
        for i, item in enumerate(items, start=1):
            gain = float(relevant.get(item, 0.0))
            if gain <= 0:
                continue
            dcg += (2.0**gain - 1.0) / log2(i + 1.0)
        return dcg

    top = recommended[:k]
    dcg = _dcg(top)
    if dcg == 0.0:
        return 0.0

    # ideal ranking: sort relevant items theo gain desc
    ideal_items = [item for item, _ in sorted(relevant.items(), key=lambda x: x[1], reverse=True)]
    ideal_top = ideal_items[:k]
    idcg = _dcg(ideal_top)
    if idcg == 0.0:
        return 0.0
    return float(dcg / idcg)

