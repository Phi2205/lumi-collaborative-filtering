from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence, Tuple

import numpy as np
from scipy.sparse import csr_matrix
from sklearn.metrics.pairwise import cosine_similarity

from lumi_cf.services.preprocess import PairScore


@dataclass(frozen=True)
class ActorTargetIndex:
    """Mapping giữa user_id thực tế và chỉ số hàng/cột trong ma trận."""

    actor_to_row: Dict[int, int]
    row_to_actor: List[int]
    target_to_col: Dict[int, int]
    col_to_target: List[int]


@dataclass(frozen=True)
class UserNeighbor:
    user_id: int
    neighbor_id: int
    score: float


def prune_topk_per_actor(pairs: Iterable[PairScore], k: int) -> List[PairScore]:
    """
    Edge pruning: với mỗi actor chỉ giữ top-k target có score cao nhất.
    """
    from collections import defaultdict

    by_actor: Dict[int, List[PairScore]] = defaultdict(list)
    for p in pairs:
        if p.score <= 0:
            continue
        by_actor[p.actor_user_id].append(p)

    pruned: List[PairScore] = []
    for actor, lst in by_actor.items():
        # sort desc theo score và cắt top-k
        lst_sorted = sorted(lst, key=lambda x: x.score, reverse=True)[:k]
        pruned.extend(lst_sorted)
    return pruned


def build_actor_target_index(pairs: Iterable[PairScore]) -> ActorTargetIndex:
    actor_ids = sorted({p.actor_user_id for p in pairs})
    target_ids = sorted({p.target_user_id for p in pairs})

    actor_to_row = {uid: i for i, uid in enumerate(actor_ids)}
    target_to_col = {uid: j for j, uid in enumerate(target_ids)}

    return ActorTargetIndex(
        actor_to_row=actor_to_row,
        row_to_actor=actor_ids,
        target_to_col=target_to_col,
        col_to_target=target_ids,
    )


def build_sparse_matrix(
    pairs: Sequence[PairScore],
    *,
    topk_per_actor: int = 1000,
) -> Tuple[csr_matrix, ActorTargetIndex]:
    """
    Bước 5: xây ma trận thưa M (actor x target) từ danh sách PairScore.

    - Áp dụng edge pruning (top-k per actor) để giảm kích thước.
    - Trả về:
        - M: csr_matrix với shape = (num_actors, num_targets)
        - index: mapping giữa user_id <-> row/col index
    """
    if not pairs:
        # empty matrix
        empty = csr_matrix((0, 0), dtype=np.float32)
        return empty, ActorTargetIndex({}, [], {}, [])

    if topk_per_actor > 0:
        pairs = prune_topk_per_actor(pairs, topk_per_actor)

    index = build_actor_target_index(pairs)

    rows: List[int] = []
    cols: List[int] = []
    data: List[float] = []

    for p in pairs:
        r = index.actor_to_row[p.actor_user_id]
        c = index.target_to_col[p.target_user_id]
        rows.append(r)
        cols.append(c)
        data.append(float(p.score))

    M = csr_matrix(
        (np.array(data, dtype=np.float32), (np.array(rows, dtype=np.int32), np.array(cols, dtype=np.int32))),
        shape=(len(index.row_to_actor), len(index.col_to_target)),
    )
    return M, index


def topk_user_neighbors(
    M: csr_matrix,
    index: ActorTargetIndex,
    *,
    k: int = 100,
) -> List[UserNeighbor]:
    """
    Bước 6: user-based CF với cosine similarity.

    - Tính cosine similarity giữa các hàng của M.
    - Với mỗi user (row), lấy top-k neighbors (loại bỏ self).
    - Trả về list UserNeighbor(user_id, neighbor_id, score).

    Lưu ý: hiện tại dùng cosine_similarity toàn cục, phù hợp cho scale vừa.
    Khi dữ liệu rất lớn nên chuyển sang ANN / block-wise.
    """
    if M.shape[0] == 0:
        return []

    # sklearn sẽ tự normalize L2 theo hàng trước khi tính cosine nếu cần.
    sim = cosine_similarity(M, dense_output=False)

    neighbors: List[UserNeighbor] = []
    n_users = M.shape[0]

    for row in range(n_users):
        row_vec = sim.getrow(row)
        idx = row_vec.indices
        vals = row_vec.data

        # loại self
        mask = idx != row
        idx = idx[mask]
        vals = vals[mask]

        if idx.size == 0:
            continue

        # sort desc theo similarity và lấy top-k
        order = np.argsort(-vals)
        top = order[:k]

        user_id = index.row_to_actor[row]
        for pos in top:
            neighbor_row = int(idx[pos])
            neighbor_id = index.row_to_actor[neighbor_row]
            score = float(vals[pos])
            neighbors.append(UserNeighbor(user_id=user_id, neighbor_id=neighbor_id, score=score))

    return neighbors

