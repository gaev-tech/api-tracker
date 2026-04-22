package store

import (
	"context"
	"database/sql"
	"errors"
	"time"

	"github.com/gaev-tech/api-tracker/backend/services/identity-service/internal/domain"
	"github.com/lib/pq"
)

var ErrNotFound = errors.New("not found")
var ErrConflict = errors.New("conflict")

type UserStore struct {
	db *sql.DB
}

func NewUserStore(db *sql.DB) *UserStore {
	return &UserStore{db: db}
}

const userColumns = `id, email, theme, language, parent_user_id, is_active, email_verified_at, created_at`

func scanUser(row interface {
	Scan(dest ...any) error
}) (*domain.User, error) {
	u := &domain.User{}
	err := row.Scan(
		&u.ID, &u.Email, &u.Theme, &u.Language,
		&u.ParentUserID, &u.IsActive, &u.EmailVerifiedAt, &u.CreatedAt,
	)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, ErrNotFound
	}
	return u, err
}

func (s *UserStore) Create(ctx context.Context, email, passwordHash string) (*domain.User, error) {
	now := time.Now()
	row := s.db.QueryRowContext(ctx, `
		INSERT INTO users (email, password_hash, email_verified_at, created_at, updated_at)
		VALUES (LOWER($1), $2, $3, $4, $4)
		RETURNING `+userColumns,
		email, passwordHash, now, now,
	)
	u, err := scanUser(row)
	if err != nil && isPgUniqueViolation(err) {
		return nil, ErrConflict
	}
	return u, err
}

func (s *UserStore) FindByEmail(ctx context.Context, email string) (*domain.User, string, error) {
	var passwordHash string
	row := s.db.QueryRowContext(ctx, `
		SELECT `+userColumns+`, password_hash
		FROM users WHERE LOWER(email) = LOWER($1)`, email)

	u := &domain.User{}
	err := row.Scan(
		&u.ID, &u.Email, &u.Theme, &u.Language,
		&u.ParentUserID, &u.IsActive, &u.EmailVerifiedAt, &u.CreatedAt,
		&passwordHash,
	)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, "", ErrNotFound
	}
	return u, passwordHash, err
}

func (s *UserStore) FindByID(ctx context.Context, id string) (*domain.User, error) {
	row := s.db.QueryRowContext(ctx, `
		SELECT `+userColumns+` FROM users WHERE id = $1`, id)
	return scanUser(row)
}

func (s *UserStore) UpdateProfile(ctx context.Context, id, theme, language string) (*domain.User, error) {
	row := s.db.QueryRowContext(ctx, `
		UPDATE users SET theme = $2, language = $3, updated_at = now()
		WHERE id = $1
		RETURNING `+userColumns,
		id, theme, language,
	)
	return scanUser(row)
}

func (s *UserStore) UpdatePassword(ctx context.Context, id, newHash string) error {
	_, err := s.db.ExecContext(ctx, `
		UPDATE users SET password_hash = $2, updated_at = now() WHERE id = $1`, id, newHash)
	return err
}

func (s *UserStore) GetPasswordHash(ctx context.Context, id string) (string, error) {
	var hash string
	err := s.db.QueryRowContext(ctx, `SELECT password_hash FROM users WHERE id = $1`, id).Scan(&hash)
	if errors.Is(err, sql.ErrNoRows) {
		return "", ErrNotFound
	}
	return hash, err
}

func isPgUniqueViolation(err error) bool {
	var pqErr *pq.Error
	return errors.As(err, &pqErr) && pqErr.Code == "23505"
}
