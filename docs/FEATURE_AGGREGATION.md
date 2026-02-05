# Feature Aggregation System - User-Post Engagement & User Profile Features

## Tổng quan

Hệ thống **Feature Aggregation** chuẩn hóa dữ liệu từ events thô thành các bảng aggregate để phục vụ:
- **User-Post Engagement**: Đo lường mức độ tương tác giữa user và post (cho feed ranking)
- **User Profile Features**: Tính toán profile features của user từ lịch sử tương tác

Hệ thống này là **bước 2** trong pipeline đề xuất post cho trang chủ (feed recommendation).

---

## Kiến trúc

### Input
- Bảng `user_interaction_events` (events thô)
- Các events có `content_id` (post_id) để tính user-post engagement

### Output
- `user_post_engagement`: Bảng aggregate engagement giữa user và post
- `user_profile_features`: Bảng profile features của user

### Quy trình xử lý

```
Events (raw) 
  ↓
Aggregate theo (user_id, post_id, day, event_type) → count
  ↓
Tính score với time-decay
  ↓
Upsert vào user_post_engagement
  ↓
Tính user profile features
  ↓
Upsert vào user_profile_features
```

---

## Schema Database

### 1. Bảng `user_post_engagement`

Bảng này lưu trữ **engagement score** giữa mỗi cặp (user, post) với time-decay.

#### Cấu trúc

| Column | Type | Description |
|--------|------|-------------|
| `user_id` | BIGINT | ID của user (PK) |
| `post_id` | BIGINT | ID của post (PK) |
| `engagement_score` | DOUBLE PRECISION | Tổng engagement score với time-decay |
| `interaction_count` | INTEGER | Tổng số lượng interactions |
| `last_interaction_at` | TIMESTAMP(6) WITH TIME ZONE | Thời gian tương tác gần nhất |
| `event_breakdown` | JSONB | Phân bố theo event_type: `{"like": 5, "comment": 2, "share": 1}` |
| `updated_at` | TIMESTAMP(6) WITH TIME ZONE | Thời gian cập nhật record |

#### Indexes

- `idx_upe_user_score`: `(user_id, engagement_score DESC)` - Để query top posts cho user
- `idx_upe_post_score`: `(post_id, engagement_score DESC)` - Để query top users cho post
- `idx_upe_last_interaction`: `(user_id, last_interaction_at DESC)` - Để query recent interactions

#### Ví dụ dữ liệu

```json
{
  "user_id": 123,
  "post_id": 456,
  "engagement_score": 8.5,
  "interaction_count": 12,
  "last_interaction_at": "2026-01-15T10:30:00Z",
  "event_breakdown": {
    "like": 5,
    "comment": 2,
    "share": 1,
    "view_post": 4
  }
}
```

### 2. Bảng `user_profile_features`

Bảng này lưu trữ **profile features** của user tính từ lịch sử tương tác.

#### Cấu trúc

| Column | Type | Description |
|--------|------|-------------|
| `user_id` | BIGINT | ID của user (PK) |
| `total_interactions` | INTEGER | Tổng số interactions user đã thực hiện |
| `avg_engagement_score` | DOUBLE PRECISION | Engagement score trung bình (từ user_post_engagement) |
| `event_type_distribution` | JSONB | Phân bố theo event_type (normalized): `{"like": 0.4, "comment": 0.3}` |
| `topic_distribution` | JSONB | Phân bố theo topic/category (nếu có) |
| `last_active_at` | TIMESTAMP(6) WITH TIME ZONE | Thời gian active gần nhất |
| `unique_posts_interacted` | INTEGER | Số lượng post unique user đã tương tác |
| `unique_users_interacted` | INTEGER | Số lượng user unique user đã tương tác |
| `updated_at` | TIMESTAMP(6) WITH TIME ZONE | Thời gian cập nhật record |

#### Indexes

- `idx_upf_last_active`: `(last_active_at DESC)` - Để query active users
- `idx_upf_total_interactions`: `(total_interactions DESC)` - Để query power users

#### Ví dụ dữ liệu

```json
{
  "user_id": 123,
  "total_interactions": 1500,
  "avg_engagement_score": 5.2,
  "event_type_distribution": {
    "like": 0.5,
    "comment": 0.2,
    "share": 0.1,
    "view_post": 0.2
  },
  "topic_distribution": {},
  "last_active_at": "2026-01-15T10:30:00Z",
  "unique_posts_interacted": 450,
  "unique_users_interacted": 120
}
```

---

## Logic tính toán

### 1. User-Post Engagement Score

#### Bước 1: Aggregate events theo ngày

Gom events theo `(user_id, post_id, day, event_type)` → count:

```sql
SELECT 
  actor_user_id AS user_id,
  content_id AS post_id,
  DATE(occurred_at) AS day,
  event_type,
  COUNT(*) AS cnt,
  MAX(occurred_at) AS last_occurred_at
FROM user_interaction_events
WHERE occurred_at >= cutoff_date
  AND content_id IS NOT NULL
GROUP BY user_id, post_id, day, event_type
```

#### Bước 2: Tính base score cho mỗi ngày

Với mỗi `(user_id, post_id, day)`, tính:

```
base_score_day = Σ event_score_from_count(event_type, count)
```

Trong đó `event_score_from_count()` áp dụng:
- **Weight theo event_type**: `message=2.0`, `comment=2.0`, `share=1.5`, `like=1.0`, `view_post=0.1`
- **Log-scale**: `score = weight * log(1 + count)`
- **Cap**: Giới hạn count theo event_type (vd: `message <= 20/day`, `view_post <= 50/day`)

#### Bước 3: Áp dụng time-decay

Với mỗi ngày, tính decay factor:

```
decay = 2^(-days_ago / half_life_days)
```

Mặc định `half_life_days = 30.0` (tương tác 30 ngày trước có weight = 0.5).

#### Bước 4: Tổng hợp engagement score

```
engagement_score = Σ (base_score_day * decay)
```

#### Ví dụ tính toán

Giả sử user 123 tương tác với post 456:
- **Ngày 1** (10 ngày trước): 5 likes, 2 comments
  - Base: `1.0 * log(1+5) + 2.0 * log(1+2) = 1.0*1.79 + 2.0*1.10 = 3.99`
  - Decay: `2^(-10/30) = 0.79`
  - Score: `3.99 * 0.79 = 3.15`
  
- **Ngày 2** (5 ngày trước): 3 likes, 1 share
  - Base: `1.0 * log(1+3) + 1.5 * log(1+1) = 1.0*1.39 + 1.5*0.69 = 2.42`
  - Decay: `2^(-5/30) = 0.89`
  - Score: `2.42 * 0.89 = 2.15`

- **Tổng**: `engagement_score = 3.15 + 2.15 = 5.30`

### 2. User Profile Features

#### Total Interactions

Đếm tổng số events của user trong cửa sổ thời gian:

```sql
SELECT COUNT(*) 
FROM user_interaction_events
WHERE actor_user_id = user_id
  AND occurred_at >= cutoff_date
```

#### Event Type Distribution

Tính tỷ lệ mỗi event_type:

```
event_type_distribution[event_type] = count(event_type) / total_interactions
```

Ví dụ: Nếu user có 100 interactions: 50 likes, 20 comments, 10 shares, 20 views
→ `{"like": 0.5, "comment": 0.2, "share": 0.1, "view_post": 0.2}`

#### Average Engagement Score

Lấy trung bình từ `user_post_engagement`:

```sql
SELECT AVG(engagement_score)
FROM user_post_engagement
WHERE user_id = user_id
```

#### Unique Posts/Users Interacted

Đếm số lượng unique `content_id` và `target_user_id`:

```sql
SELECT 
  COUNT(DISTINCT content_id) AS unique_posts,
  COUNT(DISTINCT target_user_id) AS unique_users
FROM user_interaction_events
WHERE actor_user_id = user_id
  AND occurred_at >= cutoff_date
```

---

## API & Service Functions

### Service: `app/services/feature_aggregation.py`

#### `compute_user_post_engagement()`

Tính toán và cập nhật bảng `user_post_engagement`.

**Parameters:**
- `db: Session` - Database session
- `window_days: int = 90` - Cửa sổ thời gian (ngày)
- `half_life_days: float = 30.0` - Half-life cho time-decay
- `user_id: Optional[int] = None` - Chỉ tính cho user này (nếu chỉ định)
- `post_id: Optional[int] = None` - Chỉ tính cho post này (nếu chỉ định)

**Logic:**
1. Query events trong `window_days` gần đây
2. Aggregate theo `(user_id, post_id, day, event_type)`
3. Tính score với time-decay
4. Upsert vào `user_post_engagement`

**Ví dụ:**

```python
from app.services.feature_aggregation import compute_user_post_engagement
from app.utils.database import SessionLocal

db = SessionLocal()
compute_user_post_engagement(
    db,
    window_days=90,
    half_life_days=30.0,
    user_id=123  # Chỉ tính cho user 123
)
db.close()
```

#### `compute_user_profile_features()`

Tính toán và cập nhật bảng `user_profile_features`.

**Parameters:**
- `db: Session` - Database session
- `window_days: int = 90` - Cửa sổ thời gian (ngày)
- `user_id: Optional[int] = None` - Chỉ tính cho user này (nếu chỉ định)

**Logic:**
1. Query events của user trong `window_days`
2. Tính các metrics: total_interactions, event_type_distribution, unique_posts/users
3. Tính avg_engagement_score từ `user_post_engagement`
4. Upsert vào `user_profile_features`

**Ví dụ:**

```python
from app.services.feature_aggregation import compute_user_profile_features
from app.utils.database import SessionLocal

db = SessionLocal()
compute_user_profile_features(
    db,
    window_days=90,
    user_id=123
)
db.close()
```

#### `refresh_all_features()`

Refresh tất cả features (dùng cho batch job).

**Parameters:**
- `db: Session` - Database session
- `window_days: int = 90` - Cửa sổ thời gian
- `half_life_days: float = 30.0` - Half-life cho time-decay

**Returns:**
```python
{
    "user_post_engagement_records": 10000,
    "user_profile_records": 5000
}
```

**Ví dụ:**

```python
from app.services.feature_aggregation import refresh_all_features
from app.utils.database import SessionLocal

db = SessionLocal()
result = refresh_all_features(db, window_days=90, half_life_days=30.0)
print(f"Updated {result['user_post_engagement_records']} user-post records")
db.close()
```

---

## Sử dụng trong Feed Recommendation

### 1. Candidate Generation

Dùng `user_post_engagement` để lấy top posts user đã tương tác:

```sql
-- Lấy top posts user đã engage (để tìm similar posts)
SELECT post_id, engagement_score
FROM user_post_engagement
WHERE user_id = :user_id
ORDER BY engagement_score DESC
LIMIT 100
```

### 2. Ranking Features

Dùng cả 2 bảng làm features cho ranking model:

- **User-Post Features**:
  - `engagement_score`: Mức độ user quan tâm post này
  - `last_interaction_at`: Recency
  - `event_breakdown`: Loại tương tác (like vs comment vs share)

- **User Profile Features**:
  - `event_type_distribution`: User thích loại tương tác nào
  - `avg_engagement_score`: User có hay engage không
  - `unique_posts_interacted`: User có explore nhiều không

### 3. Cold-start Handling

Với user mới (chưa có trong `user_profile_features`):
- Dùng default features hoặc features từ similar users
- Fallback về popular posts

---

## Triển khai & Vận hành

### 1. Migration Database

Chạy SQL script để tạo bảng:

```bash
psql -U postgres -d lumi_cf_dev -f sql/002_user_post_features.sql
```

### 2. Batch Job (Cron/Periodic)

Chạy định kỳ để refresh features:

```python
# app/jobs/refresh_features.py
from app.services.feature_aggregation import refresh_all_features
from app.utils.database import SessionLocal

def run_refresh():
    db = SessionLocal()
    try:
        result = refresh_all_features(db, window_days=90, half_life_days=30.0)
        print(f"Refresh completed: {result}")
    finally:
        db.close()

if __name__ == "__main__":
    run_refresh()
```

**Lịch chạy khuyến nghị:**
- **Incremental**: Mỗi giờ (chỉ refresh users/posts có events mới)
- **Full refresh**: Mỗi ngày (refresh toàn bộ)

### 3. Real-time Updates (Optional)

Khi có event mới, có thể trigger incremental update:

```python
# Sau khi ingest event
from app.services.feature_aggregation import (
    compute_user_post_engagement,
    compute_user_profile_features
)

# Update cho user và post cụ thể
compute_user_post_engagement(db, user_id=actor_user_id, post_id=content_id)
compute_user_profile_features(db, user_id=actor_user_id)
```

### 4. Monitoring

Theo dõi các metrics:

- **Data Quality**:
  - Số lượng records trong `user_post_engagement`
  - Số lượng users có profile features
  - Distribution của `engagement_score` (phát hiện outliers)

- **Performance**:
  - Thời gian chạy batch job
  - Query latency khi lấy features

- **Business Metrics**:
  - Average engagement score theo user segment
  - Top posts theo engagement score

---

## Tuning Parameters

### Time Window (`window_days`)

- **Nhỏ (30-60 ngày)**: Tập trung vào tương tác gần đây, tốt cho trending content
- **Lớn (90-180 ngày)**: Bao quát hơn, tốt cho long-tail content

**Khuyến nghị**: Bắt đầu với `90 ngày`, điều chỉnh theo data distribution.

### Half-life (`half_life_days`)

- **Ngắn (15-20 ngày)**: Ưu tiên tương tác rất gần đây
- **Dài (45-60 ngày)**: Giữ lại tương tác cũ hơn

**Khuyến nghị**: `30 ngày` là baseline tốt cho hầu hết use cases.

### Event Weights

Điều chỉnh trong `app/services/constants.py`:

```python
EVENT_WEIGHTS = {
    "message": 2.0,      # Tăng nếu message quan trọng
    "comment": 2.0,      # Tăng nếu comment quan trọng
    "share": 1.5,
    "like": 1.0,
    "view_post": 0.1     # Giảm nếu view ít ý nghĩa
}
```

---

## Troubleshooting

### Vấn đề: Engagement score = 0

**Nguyên nhân:**
- Events không có `content_id` (post_id)
- Events ngoài cửa sổ thời gian
- Event type không có trong `EVENT_WEIGHTS`

**Giải pháp:**
- Kiểm tra events có `content_id IS NOT NULL`
- Tăng `window_days` nếu cần
- Thêm event type vào `EVENT_WEIGHTS`

### Vấn đề: Batch job chạy quá lâu

**Nguyên nhân:**
- Quá nhiều events trong cửa sổ thời gian
- Thiếu indexes trên `user_interaction_events`

**Giải pháp:**
- Giảm `window_days`
- Thêm indexes: `(actor_user_id, occurred_at)`, `(content_id, occurred_at)`
- Chạy incremental updates thay vì full refresh

### Vấn đề: Memory error khi aggregate

**Nguyên nhân:**
- Quá nhiều unique (user_id, post_id) pairs

**Giải pháp:**
- Xử lý theo batch (chunk users)
- Tăng memory limit hoặc dùng streaming aggregation

---

## Tài liệu liên quan

- `docs/CF_SYSTEM_STEPS.md` - Hệ thống CF user-to-user
- `docs/CF_API.md` - API documentation
- `app/services/scoring.py` - Event scoring logic
- `app/services/time_utils.py` - Time-decay utilities
