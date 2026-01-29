## Hệ thống Collaborative Filtering (CF) cho Lumi (user-to-user)

Tài liệu này mô tả các bước end-to-end để xây hệ gợi ý **user-to-user** dựa trên tương tác (like/comment/share/message/view…).

### Combo khuyến nghị (để không “phình data” nhưng vẫn hiệu quả)

- **Aggregate theo ngày + cửa sổ thời gian**:
  - ETL từ event thô → bảng daily agg theo (actor, target, day)
  - Train/infer chỉ dùng **30–60 ngày gần nhất**
- **Cap + log-scale** cho event nhiều (đặc biệt `message`, `view`) để không bùng nổ:
  - `count_day = min(count_day, cap)`
  - điểm = `w * log(1 + count_day)`
- **Edge pruning Top-K per user**:
  - với mỗi `actor_user`, chỉ giữ **top K target** có điểm cao nhất trong cửa sổ (vd **K=300–1000**)
- **Candidate generation 2-hop**:
  - lấy neighbors của user u → mở rộng “neighbors-of-neighbors” → filter/ranking

### 1) Thu thập dữ liệu (logging)

- Schema tối thiểu mỗi event:
  - `actor_user_id`, `target_user_id`, `event_type`, `timestamp`
  - (tuỳ chọn) `value`/`count`, `session_id`, `content_id`, `metadata`
- Loại trừ:
  - self-interaction
  - bot/spam (rule hoặc model)
- Giảm tải logging (khuyến nghị):
  - với `view`: dedup theo session hoặc sampling (1/N), và đặt TTL ngắn hơn các event khác

### 2) Mapping event → điểm (implicit weights)

- Ví dụ baseline (tuỳ chỉnh):
  - `message`: 2.0
  - `comment`: 2.0
  - `share`: 1.5
  - `like`: 1.0
  - `view`: 0.1
- Chống “message dominance”:
  - bucket theo ngày + cap + log-scale:
    - `m = min(message_count_per_day, 20)`
    - \(score\_{msg,day} = 2.0 * log(1+m)\)

### 3) Time decay (khuyến nghị)

Cho tương tác gần đây quan trọng hơn:

- Dạng half-life:
  - \(decay = 2^{-(days\_ago / half\_life\_days)}\)
  - \(score = score * decay\)

### 4) Preprocessing (làm sạch & chuẩn hoá)

- **Dedup/Aggregate**:
  - gom theo (actor, target, day) rồi cộng điểm
  - sau đó gom theo (actor, target) trong 30/60/90 ngày
- **Outliers (tuỳ chọn)**:
  - cap theo IQR để tránh điểm bất thường (spam)
- **Sparse data**:
  - theo dõi sparsity (cảnh báo nếu quá thưa)
  - (tuỳ chọn) bỏ user quá ít tương tác
- **Normalize (tuỳ chọn)**:
  - giảm bias user “siêu hoạt động”:
    - log-scale tổng điểm
    - row-normalize (L2) hoặc TF-IDF-like weighting

### 5) Xây ma trận (sparse matrix)

Tạo ma trận thưa \(M\) kích thước (actor_user x target_user):

- \(M[u, v] = score(u \rightarrow v)\)
- (khuyến nghị) chỉ giữ các cạnh còn lại sau **Top-K per actor** để giảm kích thước (edge pruning)

### 6) User-based CF (similarity)

- Tính cosine similarity giữa các vector hàng của \(M\):
  - \(sim(u, v) = \frac{u \cdot v}{||u|| \; ||v||}\)
- Thực tế thường lưu **top-N neighbors** cho mỗi user (không lưu full matrix).

### 7) Candidate generation (đề xuất user)

- Candidate từ:
  - top neighbors của user u
  - mở rộng 1 bước: “neighbors-of-neighbors”
- Filter bắt buộc:
  - không đề xuất chính mình
  - đã follow/kết bạn rồi
  - blocked/muted
  - privacy rules (nếu có)

### 8) Ranking

Baseline:

- score = tổng đóng góp từ neighbors (weighted by similarity)
- cộng thêm heuristics:
  - freshness/recency
  - penalty cho spam
  - (tuỳ chọn) diversity

### 9) Fallback / Cold-start

- User mới/ít dữ liệu:
  - popular users trong khu vực/ngôn ngữ/interest
  - graph heuristic (friends-of-friends nếu có)
- Khi similarity ~ 0:
  - co-occurrence kiểu “users cùng tương tác với những người giống nhau”

### 10) Đánh giá & triển khai

- Offline:
  - precision@k/recall@k, MAP/NDCG, coverage/diversity
- Online:
  - A/B test: follow rate, message start, retention
- Deploy:
  - batch train định kỳ → artifact + version
  - service inference load artifact + cache
  - monitoring drift/latency/errors

### Quy trình triển khai theo bước (practical steps)

1) **Ingest events**
   - app ghi events (DB/stream)
   - áp dụng rule giảm tải cho `view` (dedup/sampling)

2) **ETL daily aggregate**
   - gom theo (actor, target, day):
     - counts theo event type
     - áp dụng cap/day (vd message<=20/day, view<=50/day)
     - tính điểm theo `w * log(1+count_day)` và (tuỳ chọn) time-decay theo ngày

3) **Build graph edges (Top-K)**
   - trong cửa sổ 30–60 ngày, với mỗi actor:
     - cộng điểm theo ngày → `score(actor,target)`
     - giữ top K target (K=300–1000)

4) **Train similarity / neighbors**
   - từ graph edges tạo sparse matrix M
   - tính cosine similarity và lưu top-N neighbors cho mỗi user (vd N=50–200)

5) **Inference**
   - input: `user_id`
   - lấy neighbors top-N của user → mở rộng 2-hop → filter follow/block/privacy → ranking → trả top k

6) **Fallback / cold-start**
   - user mới/ít data: popular users + friends-of-friends (nếu có)
   - similarity thấp: co-occurrence/graph heuristic

7) **Vận hành**
   - cache kết quả theo user (TTL)
   - retrain/rebuild theo lịch
   - monitoring chất lượng (offline + online)

