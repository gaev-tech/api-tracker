package store

import (
	"context"
	"database/sql"
	"errors"
	"time"

	"github.com/lib/pq"
)

type OAuthStore struct {
	db *sql.DB
}

func NewOAuthStore(db *sql.DB) *OAuthStore {
	return &OAuthStore{db: db}
}

// FindClient returns the allowed redirect URIs for the given client_id.
func (s *OAuthStore) FindClient(ctx context.Context, clientID string) ([]string, error) {
	var redirectURIs []string
	err := s.db.QueryRowContext(ctx, `
		SELECT redirect_uris FROM oauth_clients WHERE id = $1`,
		clientID,
	).Scan(pq.Array(&redirectURIs))
	if errors.Is(err, sql.ErrNoRows) {
		return nil, ErrNotFound
	}
	return redirectURIs, err
}

// CreateAuthCode stores a new authorization code hash.
func (s *OAuthStore) CreateAuthCode(ctx context.Context, codeHash, clientID, userID, redirectURI, codeChallenge string, expiresAt time.Time) error {
	_, err := s.db.ExecContext(ctx, `
		INSERT INTO authorization_codes (code_hash, client_id, user_id, redirect_uri, code_challenge, expires_at)
		VALUES ($1, $2, $3, $4, $5, $6)`,
		codeHash, clientID, userID, redirectURI, codeChallenge, expiresAt,
	)
	return err
}

// ExchangeAuthCode marks the code as used and returns its associated data.
// Returns ErrNotFound if the code does not exist, is already used, or is expired.
func (s *OAuthStore) ExchangeAuthCode(ctx context.Context, codeHash string) (clientID, userID, redirectURI, codeChallenge string, err error) {
	err = s.db.QueryRowContext(ctx, `
		UPDATE authorization_codes
		SET used_at = now()
		WHERE code_hash = $1
		  AND used_at IS NULL
		  AND expires_at > now()
		RETURNING client_id, user_id, redirect_uri, code_challenge`,
		codeHash,
	).Scan(&clientID, &userID, &redirectURI, &codeChallenge)
	if errors.Is(err, sql.ErrNoRows) {
		return "", "", "", "", ErrNotFound
	}
	return
}
