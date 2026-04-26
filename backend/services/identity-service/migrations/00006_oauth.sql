-- +goose Up
CREATE TABLE oauth_clients (
    id            TEXT PRIMARY KEY,
    secret_hash   TEXT,
    redirect_uris TEXT[] NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE authorization_codes (
    code_hash      TEXT PRIMARY KEY,
    client_id      TEXT NOT NULL REFERENCES oauth_clients(id),
    user_id        UUID NOT NULL REFERENCES users(id),
    redirect_uri   TEXT NOT NULL,
    code_challenge TEXT,
    expires_at     TIMESTAMPTZ NOT NULL,
    used_at        TIMESTAMPTZ
);

INSERT INTO oauth_clients (id, redirect_uris) VALUES
    ('web-app', ARRAY['https://apitracker.ru/auth/callback']),
    ('cli', ARRAY['http://localhost']);

-- +goose Down
DROP TABLE IF EXISTS authorization_codes;
DROP TABLE IF EXISTS oauth_clients;
