-- +goose Up
CREATE TABLE users_cache (
    user_id    UUID PRIMARY KEY,
    email      TEXT NOT NULL,
    name       TEXT NOT NULL DEFAULT '',
    is_active  BOOLEAN NOT NULL DEFAULT true,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_users_cache_email ON users_cache(LOWER(email));

-- +goose Down
DROP TABLE users_cache;
