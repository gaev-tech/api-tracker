-- +goose Up
CREATE TABLE subscription_history (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID NOT NULL,
    plan       TEXT NOT NULL,
    period     TEXT,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at   TIMESTAMPTZ,
    reason     TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_subscription_history_user_id ON subscription_history(user_id);

-- +goose Down
DROP TABLE subscription_history;
