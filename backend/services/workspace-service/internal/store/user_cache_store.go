package store

import (
	"context"
	"database/sql"
	"errors"

	"github.com/gaev-tech/api-tracker/workspace-service/internal/domain"
)

type UserCacheStore struct {
	db *sql.DB
}

func NewUserCacheStore(db *sql.DB) *UserCacheStore {
	return &UserCacheStore{db: db}
}

// Upsert inserts or updates a user in the cache.
func (s *UserCacheStore) Upsert(ctx context.Context, u *domain.UserCache) error {
	_, err := s.db.ExecContext(ctx, `
		INSERT INTO users_cache (user_id, email, name, is_active, updated_at)
		VALUES ($1, $2, $3, $4, now())
		ON CONFLICT (user_id) DO UPDATE SET
			email = EXCLUDED.email,
			name = EXCLUDED.name,
			is_active = EXCLUDED.is_active,
			updated_at = now()`,
		u.UserID, u.Email, u.Name, u.IsActive,
	)
	return err
}

// Delete removes a user from the cache.
func (s *UserCacheStore) Delete(ctx context.Context, userID string) error {
	_, err := s.db.ExecContext(ctx, `DELETE FROM users_cache WHERE user_id = $1`, userID)
	return err
}

// FindByID returns a cached user.
func (s *UserCacheStore) FindByID(ctx context.Context, userID string) (*domain.UserCache, error) {
	u := &domain.UserCache{}
	err := s.db.QueryRowContext(ctx, `
		SELECT user_id, email, name, is_active, updated_at
		FROM users_cache WHERE user_id = $1`, userID,
	).Scan(&u.UserID, &u.Email, &u.Name, &u.IsActive, &u.UpdatedAt)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, ErrNotFound
	}
	return u, err
}
