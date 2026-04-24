-- +goose Up
CREATE TABLE usage_counters (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID NOT NULL,
    entity_type   TEXT NOT NULL,
    current_count INTEGER NOT NULL DEFAULT 0,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, entity_type)
);

CREATE INDEX idx_usage_counters_user_id ON usage_counters(user_id);

-- +goose Down
DROP TABLE usage_counters;
