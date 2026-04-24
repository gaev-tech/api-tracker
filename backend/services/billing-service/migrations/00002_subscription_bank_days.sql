-- +goose Up
CREATE TABLE subscription_bank_days (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID NOT NULL REFERENCES subscriptions(user_id) ON DELETE CASCADE,
    plan          TEXT NOT NULL,
    period        TEXT NOT NULL,
    days_remaining INTEGER NOT NULL,
    layer_order   INTEGER NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_subscription_bank_days_user_id ON subscription_bank_days(user_id);

-- +goose Down
DROP TABLE subscription_bank_days;
