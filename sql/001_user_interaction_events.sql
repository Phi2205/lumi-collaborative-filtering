-- PostgreSQL init for Lumi CF: user-to-user interaction events
-- Assumes you already have a `users` table with primary key `id` (BIGINT recommended).
-- If your users PK type/name differs, adjust the REFERENCES lines.

CREATE TABLE IF NOT EXISTS user_interaction_events (
  id              BIGSERIAL PRIMARY KEY,

  actor_user_id   BIGINT NOT NULL REFERENCES users(id),
  target_user_id  BIGINT NOT NULL REFERENCES users(id),

  event_type      TEXT NOT NULL,                 -- like/comment/share/message/view/...
  event_value     DOUBLE PRECISION,              -- optional: score/count/seconds...

  content_id      BIGINT,                        -- optional: post/comment/thread id...
  session_id      TEXT,                          -- optional: for view dedup

  occurred_at     TIMESTAMPTZ NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

  meta            JSONB NOT NULL DEFAULT '{}'::jsonb,

  CONSTRAINT chk_no_self_interaction CHECK (actor_user_id <> target_user_id)
);

-- Common query patterns:
-- 1) Pull recent events by actor (training/export)
CREATE INDEX IF NOT EXISTS idx_uie_actor_time
  ON user_interaction_events (actor_user_id, occurred_at DESC);

-- 2) Pull recent events by target (analytics/moderation)
CREATE INDEX IF NOT EXISTS idx_uie_target_time
  ON user_interaction_events (target_user_id, occurred_at DESC);

-- 3) Pull pair timeline (debugging/features)
CREATE INDEX IF NOT EXISTS idx_uie_pair_time
  ON user_interaction_events (actor_user_id, target_user_id, occurred_at DESC);

-- 4) Pull by event type in time range (ETL)
CREATE INDEX IF NOT EXISTS idx_uie_type_time
  ON user_interaction_events (event_type, occurred_at DESC);

-- Optional: if you expect huge `view` volume, you can add BRIN index by time for range scans:
-- CREATE INDEX IF NOT EXISTS brin_uie_occurred_at
--   ON user_interaction_events USING BRIN (occurred_at);

