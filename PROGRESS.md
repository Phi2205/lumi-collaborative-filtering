## Lumi CF Progress (user-to-user)

Mục tiêu: gợi ý **user-to-user** cho Lumi (mạng xã hội) dựa trên implicit signals: like/comment/share/message/...

### Trạng thái hiện tại

- **Đang làm**: thiết kế schema dữ liệu + mapping trọng số event + (tuỳ chọn) time-decay.
- **Tiếp theo**: build pipeline tạo ma trận tương tác sparse (actor -> target) và huấn luyện user-user similarity (cosine).

### Checklist theo bước (đánh dấu khi xong)

- [ ] 1) Chốt schema log tương tác (CSV/DB):
  - `actor_user_id`, `target_user_id`, `event_type`, `timestamp`
  - (tuỳ chọn) `value`/`count`, `metadata`
- [ ] 2) Chốt trọng số event (ví dụ, có thể chỉnh):
  - Gợi ý set để **tránh message lấn át** (kèm normalize/cap ở bước 4):
    - `message`: 2.0
    - `comment`: 2.0
    - `share`: 1.5
    - `like`: 1.0
    - `view`: 0.1
  - Tuỳ chọn tách message:
    - `message_exists` (có nhắn trong 30 ngày): 1.5
    - `message_count`: 0.3 (áp dụng log-scale/cap)
- [ ] 3) Time-decay (tuỳ chọn):
  - Ví dụ: weight *= exp(-lambda * age_days)
- [ ] 4) Preprocess:
  - remove self-interaction
  - dedup/aggregate theo (actor, target)
  - loại bot/spam (nếu có rule)
  - chống “message dominance” (khuyến nghị):
    - log-scale: dùng \(log(1 + count)\) cho `message_count`/`view`
    - cap theo ngày/tuần: ví dụ `message_count <= 20/day`, `view <= 50/day`
    - time-decay để tương tác gần đây có trọng số cao hơn
  - (tuỳ chọn) outliers:
    - cap theo IQR để tránh điểm bất thường (spam/abuse)
  - (tuỳ chọn) sparse-data handling:
    - cảnh báo sparsity cao
    - rule loại user quá ít tương tác (nếu cần)
  - (tuỳ chọn) normalize:
    - row-normalize / log-scale để giảm bias user “siêu hoạt động”

### Gợi ý rule cụ thể cho message (để 10 tin/ngày vẫn “cao”, nhưng không bùng nổ)

- Bucket theo ngày cho từng cặp (actor, target):
  - `m = min(message_count_per_day, 20)`
  - điểm message theo ngày: \(score_msg_day = 2.0 * log(1 + m)\)
- Tổng điểm theo 30 ngày gần nhất (kèm decay nếu muốn):
  - \(score_msg_30d = \sum_{d=1..30} score\_msg\_day(d)\)

- [ ] 5) Tạo sparse matrix M (actor x target) và normalize (tuỳ chọn)
- [ ] 6) Train similarity:
  - cosine similarity trên vector tương tác
  - lấy top-N neighbors cho mỗi user
- [ ] 7) Candidate generation:
  - từ neighbors → đề xuất user mới
  - filter: đã connect/follow, blocked, privacy, ...
- [ ] 7.1) Ranking (baseline + heuristic):
  - score = tổng đóng góp từ neighbors (weighted by similarity)
  - (tuỳ chọn) freshness/diversity/penalty spam
- [ ] 7.2) Fallback / cold-start:
  - user mới/ít data → popular/graph heuristic
  - similarity ~ 0 → co-occurrence
- [ ] 8) Lưu model artifact (joblib) + versioning
- [ ] 9) API inference:
  - `/recommend-users/{user_id}?k=...`
  - `/similar-users/{user_id}?k=...`
- [ ] 10) Đánh giá + theo dõi:
  - offline metrics (precision@k/recall@k)
  - online A/B + guardrails
  - hiệu năng: caching, batch inference, monitoring drift

### Notes / quyết định

- Model ban đầu: **user-user cosine** (nhanh, dễ vận hành).
- Nâng cấp sau: graph-based (PPR), hoặc MF (BPR/ALS) khi data lớn.

