-- +goose Up

CREATE TABLE IF NOT EXISTS users (
    id                       UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    email                    VARCHAR(255) NOT NULL UNIQUE,
    password_hash            VARCHAR(255) NOT NULL,
    theme                    VARCHAR(32)  NOT NULL DEFAULT 'light',
    language                 VARCHAR(8)   NOT NULL DEFAULT 'en',
    parent_user_id           UUID         REFERENCES users(id) ON DELETE CASCADE,
    is_active                BOOLEAN      NOT NULL DEFAULT true,
    email_verified_at        TIMESTAMPTZ,
    email_verification_token VARCHAR(128),
    created_at               TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at               TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT users_no_self_parent CHECK (parent_user_id <> id)
);

CREATE INDEX idx_users_email_lower ON users (LOWER(email));
CREATE INDEX idx_users_parent_user_id ON users (parent_user_id);
CREATE UNIQUE INDEX idx_users_email_verification_token
    ON users (email_verification_token)
    WHERE email_verification_token IS NOT NULL;

-- +goose Down

DROP TABLE IF EXISTS users;
