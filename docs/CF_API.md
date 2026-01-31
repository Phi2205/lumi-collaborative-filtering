## Lumi CF Service API (for Lumi BE)

Base URL ví dụ: `http://cf-service:8000`

### Authentication

Tất cả các API endpoints đều yêu cầu header xác thực để đảm bảo an toàn truy cập nội bộ (internal only).

**Header bắt buộc:**
`x-internal-key: <INTERNAL_SHARED_SECRET>`

Giá trị `INTERNAL_SHARED_SECRET` được cấu hình trong file `.env`.

#### Ví dụ gọi API (cURL):

```bash
# Lấy danh sách users tương đồng
curl -X GET "http://localhost:8000/api/similar-users/123" \
     -H "x-internal-key: my_secret_key_123"

# Log sự kiện tương tác
curl -X POST "http://localhost:8000/api/events" \
     -H "x-internal-key: my_secret_key_123" \
     -H "Content-Type: application/json" \
     -d '{
           "actor_user_id": 1,
           "target_user_id": 2,
           "event_type": "view",
           "timestamp": "2023-10-27T10:00:00Z"
         }'
```

#### Hướng dẫn Postman:

1. **Tab Headers**:
   - Key: `x-internal-key`
   - Value: `<INTERNAL_SHARED_SECRET>` (lấy từ file `.env`)

2. **Tab Body** (đối với POST request):
   - Chọn **raw**
   - Chọn định dạng **JSON** từ dropdown (thay vì Text)
   - Paste JSON vào ô nội dung.

### 1) Healthcheck

- **GET** `/health`

Response:

```json
{ "status": "ok" }
```

### 2) Ingest interaction event (logging)

- **POST** `/events`

Body:

```json
{
  "actor_user_id": 123,
  "target_user_id": 456,
  "event_type": "message",
  "timestamp": "2026-01-01T00:00:00Z",
  "value": 1,
  "content_id": 999,
  "session_id": "abc",
  "metadata": { "source": "chat" }
}
```

Notes:
- **Header bắt buộc**: `x-internal-key: <INTERNAL_SHARED_SECRET>`
- `event_type` hỗ trợ: `like`, `comment`, `share`, `message`, `view`
- chặn self-interaction (`actor_user_id != target_user_id`)

#### Giải thích tham số request:

| Tham số | Kiểu | Bắt buộc | Mô tả |
| :--- | :--- | :--- | :--- |
| `actor_user_id` | Int | Có | ID người thực hiện hành động |
| `target_user_id` | Int | Có | ID người nhận tương tác |
| `event_type` | String | Có | Loại tương tác (`message`, `like`, `view`,...) |
| `timestamp` | DateTime | Có | Thời gian (ISO 8601) |
| `value` | Float | Không | Giá trị/trọng số (VD: rating) |
| `content_id` | Int | Không | ID bài viết/nội dung (nếu có) |
| `content_type` | String | Không | Loại nội dung (`post`, `comment`, `video`,...) để phân biệt content_id |
| `session_id` | String | Không | ID phiên làm việc |
| `metadata` | JSON | Không | Dữ liệu bổ sung |

### 3) Similar users (neighbors)

- **GET** `/similar-users/{user_id}?k=20&window_days=30`

Response:

```json
{
  "user_id": 123,
  "window_days": 30,
  "neighbors": [
    { "user_id": 888, "score": 12.0, "reason": "shared_targets" }
  ],
  "strategy": "shared_targets_count",
  "generated_at": "2026-01-01T00:00:01Z"
}
```

### 4) Recommend users (friend suggestion candidates)

- **GET** `/recommend-users/{user_id}?k=20&window_days=30&neighbor_k=100`

Response:

```json
{
  "user_id": 123,
  "window_days": 30,
  "recommendations": [
    { "user_id": 999, "score": 4.12, "reason": "neighbors_2hop_weighted" }
  ],
  "strategy": "neighbors_2hop_weighted",
  "generated_at": "2026-01-01T00:00:02Z"
}
```

### OpenAPI / Swagger

- Swagger UI: `/docs`
- OpenAPI JSON: `/openapi.json`

