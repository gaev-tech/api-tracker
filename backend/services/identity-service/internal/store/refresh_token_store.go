package store

import (
	"context"
	"database/sql"
	"errors"
	"time"
)

type RefreshTokenStore struct {
	db *sql.DB
}

func NewRefreshTokenStore(db *sql.DB) *RefreshTokenStore {
	return &RefreshTokenStore{db: db}
}

func (store *RefreshTokenStore) Create(ctx context.Context, userID, tokenHash string, expiresAt time.Time) error {
	_, err := store.db.ExecContext(ctx, `
		INSERT INTO refresh_tokens (user_id, token_hash, expires_at)
		VALUES ($1, $2, $3)`,
		userID, tokenHash, expiresAt,
	)
	return err
}

// FindByHash returns user_id for a valid (non-revoked, non-expired) refresh token hash.
func (store *RefreshTokenStore) FindByHash(ctx context.Context, tokenHash string) (userID string, err error) {
	err = store.db.QueryRowContext(ctx, `
		SELECT user_id FROM refresh_tokens
		WHERE token_hash = $1
		  AND revoked_at IS NULL
		  AND expires_at > now()`,
		tokenHash,
	).Scan(&userID)
	if errors.Is(err, sql.ErrNoRows) {
		return "", ErrNotFound
	}
	return userID, err
}

func (store *RefreshTokenStore) Revoke(ctx context.Context, tokenHash string) error {
	_, err := store.db.ExecContext(ctx, `
		UPDATE refresh_tokens SET revoked_at = now()
		WHERE token_hash = $1 AND revoked_at IS NULL`,
		tokenHash,
	)
	return err
}

func (store *RefreshTokenStore) RevokeAllForUser(ctx context.Context, userID string) error {
	_, err := store.db.ExecContext(ctx, `
		UPDATE refresh_tokens SET revoked_at = now()
		WHERE user_id = $1 AND revoked_at IS NULL`,
		userID,
	)
	return err
}
