## Lumi CF Service API (for Lumi BE)

Base URL ví dụ: `http://cf-service:8000`

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
- `event_type` hỗ trợ: `like`, `comment`, `share`, `message`, `view`
- chặn self-interaction (`actor_user_id != target_user_id`)

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

