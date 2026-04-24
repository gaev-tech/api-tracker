-- +goose Up
CREATE TABLE billing_outbox (
    id         BIGSERIAL PRIMARY KEY,
    topic      TEXT NOT NULL,
    payload    JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    sent_at    TIMESTAMPTZ
);

CREATE INDEX idx_billing_outbox_unsent ON billing_outbox(id) WHERE sent_at IS NULL;

-- +goose Down
DROP TABLE billing_outbox;
