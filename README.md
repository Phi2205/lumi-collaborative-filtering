## Lumi Collaborative Filtering (Python)

Dịch vụ gợi ý **collaborative filtering (user-to-user)** cho Lumi (mạng xã hội).

### Input dữ liệu

File CSV event tương tác dạng tối thiểu:

- `actor_user_id`: user thực hiện tương tác
- `target_user_id`: user nhận tương tác
- `event_type`: like/comment/share/message/view/...
- `timestamp`
- (tuỳ chọn) `value`/`count`, `session_id`, `metadata`

Tài liệu chi tiết các bước hệ thống: `lumi-collaborative-filtering/docs/CF_SYSTEM_STEPS.md`.

### Cài đặt

```bash
cd lumi-collaborative-filtering
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install -e .
```

### Thu thập data (logging events)

**Setup database** (PostgreSQL cho cả dev và prod):

1. Tạo database và user (nếu chưa có):
```sql
CREATE DATABASE lumi_cf_dev;
CREATE USER postgres WITH PASSWORD 'postgres';
GRANT ALL PRIVILEGES ON DATABASE lumi_cf_dev TO postgres;
```

2. Chạy migration script để tạo bảng:
```bash
psql -U postgres -d lumi_cf_dev -f sql/001_user_interaction_events.sql
```

**Chạy service ingest:**

```bash
:: PostgreSQL (dev/prod)
:: Default: postgresql://postgres:postgres@localhost:5432/lumi_cf_dev
:: Hoặc set custom URL:
set DATABASE_URL=postgresql://user:password@host:5432/dbname

uvicorn lumi_cf.api.main:app --host 0.0.0.0 --port 8000
```

### API cho Lumi BE gọi

Xem chi tiết: `docs/CF_API.md` (kèm Swagger `/docs`).

Gửi event mẫu:

```bash
curl -X POST http://127.0.0.1:8000/events ^
  -H "Content-Type: application/json" ^
  -d "{\"actor_user_id\":1,\"target_user_id\":2,\"event_type\":\"message\",\"timestamp\":\"2026-01-01T00:00:00Z\",\"value\":1}"
```

### Train model

```bash
python -m lumi_cf.train --input data/example_interactions.csv --out artifacts/model.joblib --neighbors 50
```

### Chạy API

```bash
set MODEL_PATH=artifacts/model.joblib
uvicorn lumi_cf.api.main:app --host 0.0.0.0 --port 8000
```

Endpoints:

- `GET /health`
- `GET /recommend/{user_id}?k=20`
- `GET /similar-items/{item_id}?k=20`

### Gợi ý tích hợp Lumi

- Lumi backend ghi log tương tác (view/add-to-cart/purchase) vào DB/queue → export CSV/Parquet theo batch.
- Chạy job train định kỳ (cron/airflow) → đẩy `artifacts/model.joblib` lên object storage → service API reload.

