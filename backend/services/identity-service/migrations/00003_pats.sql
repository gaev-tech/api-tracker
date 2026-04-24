-- +goose Up
CREATE TABLE IF NOT EXISTS pats (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name       TEXT        NOT NULL,
    token_hash TEXT        NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS pats_user_id_idx ON pats (user_id);
CREATE INDEX IF NOT EXISTS pats_token_hash_idx ON pats (token_hash) WHERE revoked_at IS NULL;

-- +goose Down
DROP TABLE IF EXISTS pats;
