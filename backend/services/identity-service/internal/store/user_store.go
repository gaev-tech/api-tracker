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
	user := &domain.User{}
	err := row.Scan(
		&user.ID, &user.Email, &user.Theme, &user.Language,
		&user.ParentUserID, &user.IsActive, &user.EmailVerifiedAt, &user.CreatedAt,
	)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, ErrNotFound
	}
	return user, err
}

// Create inserts a new unverified user with an email verification token.
func (store *UserStore) Create(ctx context.Context, email, passwordHash, verificationToken string) (*domain.User, error) {
	now := time.Now()
	row := store.db.QueryRowContext(ctx, `
		INSERT INTO users (email, password_hash, email_verification_token, created_at, updated_at)
		VALUES (LOWER($1), $2, $3, $4, $4)
		RETURNING `+userColumns,
		email, passwordHash, verificationToken, now,
	)
	u, err := scanUser(row)
	if err != nil && isPgUniqueViolation(err) {
		return nil, ErrConflict
	}
	return u, err
}

// VerifyEmail confirms a user's email using the verification token.
// Returns the updated user on success, ErrNotFound if the token is invalid.
func (store *UserStore) VerifyEmail(ctx context.Context, token string) (*domain.User, error) {
	row := store.db.QueryRowContext(ctx, `
		UPDATE users
		SET email_verified_at = now(), email_verification_token = NULL, updated_at = now()
		WHERE email_verification_token = $1 AND email_verified_at IS NULL
		RETURNING `+userColumns,
		token,
	)
	u, err := scanUser(row)
	if errors.Is(err, ErrNotFound) {
		return nil, ErrNotFound
	}
	return u, err
}

func (store *UserStore) FindByEmail(ctx context.Context, email string) (*domain.User, string, error) {
	var passwordHash string
	row := store.db.QueryRowContext(ctx, `
		SELECT `+userColumns+`, password_hash
		FROM users WHERE LOWER(email) = LOWER($1)`, email)

	user := &domain.User{}
	err := row.Scan(
		&user.ID, &user.Email, &user.Theme, &user.Language,
		&user.ParentUserID, &user.IsActive, &user.EmailVerifiedAt, &user.CreatedAt,
		&passwordHash,
	)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, "", ErrNotFound
	}
	return user, passwordHash, err
}

func (store *UserStore) FindByID(ctx context.Context, id string) (*domain.User, error) {
	row := store.db.QueryRowContext(ctx, `
		SELECT `+userColumns+` FROM users WHERE id = $1`, id)
	return scanUser(row)
}

func (store *UserStore) UpdateProfile(ctx context.Context, id, theme, language string) (*domain.User, error) {
	row := store.db.QueryRowContext(ctx, `
		UPDATE users SET theme = $2, language = $3, updated_at = now()
		WHERE id = $1
		RETURNING `+userColumns,
		id, theme, language,
	)
	return scanUser(row)
}

func (store *UserStore) UpdatePassword(ctx context.Context, id, newHash string) error {
	_, err := store.db.ExecContext(ctx, `
		UPDATE users SET password_hash = $2, updated_at = now() WHERE id = $1`, id, newHash)
	return err
}

func (store *UserStore) GetPasswordHash(ctx context.Context, id string) (string, error) {
	var hash string
	err := store.db.QueryRowContext(ctx, `SELECT password_hash FROM users WHERE id = $1`, id).Scan(&hash)
	if errors.Is(err, sql.ErrNoRows) {
		return "", ErrNotFound
	}
	return hash, err
}

func isPgUniqueViolation(err error) bool {
	var pqErr *pq.Error
	return errors.As(err, &pqErr) && pqErr.Code == "23505"
}
