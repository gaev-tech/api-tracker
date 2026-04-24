-- +goose Up
CREATE TABLE workspace_outbox (
    id         BIGSERIAL PRIMARY KEY,
    topic      TEXT NOT NULL,
    payload    JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    sent_at    TIMESTAMPTZ
);

CREATE INDEX idx_workspace_outbox_unsent ON workspace_outbox(id) WHERE sent_at IS NULL;

-- +goose Down
DROP TABLE workspace_outbox;
