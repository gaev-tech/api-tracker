-- +goose Up
CREATE TABLE IF NOT EXISTS ping_outbox (
    id         BIGSERIAL PRIMARY KEY,
    topic      TEXT        NOT NULL,
    payload    JSONB       NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sent_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ping_outbox_unsent_idx ON ping_outbox (id) WHERE sent_at IS NULL;

-- +goose Down
DROP TABLE IF EXISTS ping_outbox;
