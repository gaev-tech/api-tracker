package store

import (
	"context"
	"database/sql"
	"errors"
	"time"

	"github.com/gaev-tech/api-tracker/backend/services/identity-service/internal/domain"
)

type PATStore struct {
	db *sql.DB
}

func NewPATStore(db *sql.DB) *PATStore {
	return &PATStore{db: db}
}

const patColumns = `id, name, created_at, revoked_at`

func scanPAT(row interface{ Scan(dest ...any) error }) (*domain.PAT, error) {
	pat := &domain.PAT{}
	err := row.Scan(&pat.ID, &pat.Name, &pat.CreatedAt, &pat.RevokedAt)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, ErrNotFound
	}
	return pat, err
}

// CreateTx inserts a new PAT within the provided transaction and returns it.
func (s *PATStore) CreateTx(ctx context.Context, tx *sql.Tx, userID, name, tokenHash string) (*domain.PAT, error) {
	row := tx.QueryRowContext(ctx, `
		INSERT INTO pats (user_id, name, token_hash)
		VALUES ($1, $2, $3)
		RETURNING `+patColumns,
		userID, name, tokenHash,
	)
	return scanPAT(row)
}

// ListByUser returns all PATs for a user (including revoked).
func (s *PATStore) ListByUser(ctx context.Context, userID string) ([]*domain.PAT, error) {
	rows, err := s.db.QueryContext(ctx, `
		SELECT `+patColumns+` FROM pats
		WHERE user_id = $1
		ORDER BY created_at DESC`,
		userID,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var pats []*domain.PAT
	for rows.Next() {
		pat := &domain.PAT{}
		if err := rows.Scan(&pat.ID, &pat.Name, &pat.CreatedAt, &pat.RevokedAt); err != nil {
			return nil, err
		}
		pats = append(pats, pat)
	}
	return pats, rows.Err()
}

// FindByID returns a PAT owned by the given user.
func (s *PATStore) FindByID(ctx context.Context, userID, patID string) (*domain.PAT, error) {
	row := s.db.QueryRowContext(ctx, `
		SELECT `+patColumns+` FROM pats
		WHERE id = $1 AND user_id = $2`,
		patID, userID,
	)
	return scanPAT(row)
}

// UpdateName changes the name of a PAT owned by the given user.
func (s *PATStore) UpdateName(ctx context.Context, userID, patID, name string) (*domain.PAT, error) {
	row := s.db.QueryRowContext(ctx, `
		UPDATE pats SET name = $3
		WHERE id = $1 AND user_id = $2 AND revoked_at IS NULL
		RETURNING `+patColumns,
		patID, userID, name,
	)
	return scanPAT(row)
}

// RevokeTx soft-deletes a PAT within the provided transaction.
func (s *PATStore) RevokeTx(ctx context.Context, tx *sql.Tx, userID, patID string) error {
	res, err := tx.ExecContext(ctx, `
		UPDATE pats SET revoked_at = $3
		WHERE id = $1 AND user_id = $2 AND revoked_at IS NULL`,
		patID, userID, time.Now(),
	)
	if err != nil {
		return err
	}
	n, err := res.RowsAffected()
	if err != nil {
		return err
	}
	if n == 0 {
		return ErrNotFound
	}
	return nil
}

// FindUserByTokenHash returns the user_id for a valid (non-revoked) PAT.
func (s *PATStore) FindUserByTokenHash(ctx context.Context, tokenHash string) (string, error) {
	var userID string
	err := s.db.QueryRowContext(ctx, `
		SELECT user_id FROM pats
		WHERE token_hash = $1 AND revoked_at IS NULL`,
		tokenHash,
	).Scan(&userID)
	if errors.Is(err, sql.ErrNoRows) {
		return "", ErrNotFound
	}
	return userID, err
}
