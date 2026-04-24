-- +goose Up
CREATE TABLE subscriptions (
    user_id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plan                              TEXT NOT NULL DEFAULT 'free',
    period                            TEXT,
    current_period_start              TIMESTAMPTZ,
    current_period_end                TIMESTAMPTZ,
    planned_downgrade_plan            TEXT,
    planned_downgrade_at              TIMESTAMPTZ,
    enterprise_slots                  INTEGER NOT NULL DEFAULT 0,
    enterprise_slots_pending_decrease INTEGER,
    enterprise_slots_pending_at       TIMESTAMPTZ,
    created_at                        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- +goose Down
DROP TABLE subscriptions;
