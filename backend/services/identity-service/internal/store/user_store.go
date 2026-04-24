package store

import (
	"context"
	"database/sql"
	"errors"
	"time"

	"github.com/gaev-tech/api-tracker/backend/services/identity-service/internal/domain"
	"github.com/lib/pq"
)

var ErrNotFound = errors.New("store: not found")
var ErrConflict = errors.New("store: conflict")

type UserStore struct {
	db *sql.DB
}

func NewUserStore(db *sql.DB) *UserStore {
	return &UserStore{db: db}
}

const userColumns = `id, name, email, theme, language, parent_user_id, is_active, email_verified_at, created_at`

func scanUser(row interface {
	Scan(dest ...any) error
}) (*domain.User, error) {
	user := &domain.User{}
	err := row.Scan(
		&user.ID, &user.Name, &user.Email, &user.Theme, &user.Language,
		&user.ParentUserID, &user.IsActive, &user.EmailVerifiedAt, &user.CreatedAt,
	)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, ErrNotFound
	}
	return user, err
}

// Create inserts a new unverified user with an email verification token.
func (s *UserStore) Create(ctx context.Context, email, passwordHash, verificationToken string) (*domain.User, error) {
	now := time.Now()
	row := s.db.QueryRowContext(ctx, `
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
func (s *UserStore) VerifyEmail(ctx context.Context, token string) (*domain.User, error) {
	row := s.db.QueryRowContext(ctx, `
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

func (s *UserStore) FindByEmail(ctx context.Context, email string) (*domain.User, string, error) {
	var passwordHash string
	row := s.db.QueryRowContext(ctx, `
		SELECT `+userColumns+`, password_hash
		FROM users WHERE LOWER(email) = LOWER($1)`, email)

	user := &domain.User{}
	err := row.Scan(
		&user.ID, &user.Name, &user.Email, &user.Theme, &user.Language,
		&user.ParentUserID, &user.IsActive, &user.EmailVerifiedAt, &user.CreatedAt,
		&passwordHash,
	)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, "", ErrNotFound
	}
	return user, passwordHash, err
}

func (s *UserStore) FindByID(ctx context.Context, id string) (*domain.User, error) {
	row := s.db.QueryRowContext(ctx, `
		SELECT `+userColumns+` FROM users WHERE id = $1`, id)
	return scanUser(row)
}

func (s *UserStore) UpdateProfile(ctx context.Context, id, name, theme, language string) (*domain.User, error) {
	row := s.db.QueryRowContext(ctx, `
		UPDATE users SET name = $2, theme = $3, language = $4, updated_at = now()
		WHERE id = $1
		RETURNING `+userColumns,
		id, name, theme, language,
	)
	return scanUser(row)
}

func (s *UserStore) UpdatePassword(ctx context.Context, id, newHash string) error {
	_, err := s.db.ExecContext(ctx, `
		UPDATE users SET password_hash = $2, updated_at = now() WHERE id = $1`, id, newHash)
	return err
}

func (s *UserStore) PasswordHash(ctx context.Context, id string) (string, error) {
	var hash string
	err := s.db.QueryRowContext(ctx, `SELECT password_hash FROM users WHERE id = $1`, id).Scan(&hash)
	if errors.Is(err, sql.ErrNoRows) {
		return "", ErrNotFound
	}
	return hash, err
}

// Delete removes a user and all associated data within identity-service (refresh tokens, PATs).
func (s *UserStore) Delete(ctx context.Context, tx *sql.Tx, id string) error {
	// Delete refresh tokens
	if _, err := tx.ExecContext(ctx, `DELETE FROM refresh_tokens WHERE user_id = $1`, id); err != nil {
		return err
	}
	// Delete PATs
	if _, err := tx.ExecContext(ctx, `DELETE FROM pats WHERE user_id = $1`, id); err != nil {
		return err
	}
	// Delete user
	res, err := tx.ExecContext(ctx, `DELETE FROM users WHERE id = $1`, id)
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

// SearchByEmail finds users by email prefix, excluding the caller, returning only verified and active users.
func (s *UserStore) SearchByEmail(ctx context.Context, excludeUserID, query string, limit int) ([]*domain.UserSearchResult, error) {
	rows, err := s.db.QueryContext(ctx, `
		SELECT id, name, email FROM users
		WHERE LOWER(email) LIKE LOWER($1) || '%'
		  AND id != $2
		  AND email_verified_at IS NOT NULL
		  AND is_active = true
		ORDER BY email
		LIMIT $3`,
		query, excludeUserID, limit,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var results []*domain.UserSearchResult
	for rows.Next() {
		r := &domain.UserSearchResult{}
		if err := rows.Scan(&r.ID, &r.Name, &r.Email); err != nil {
			return nil, err
		}
		results = append(results, r)
	}
	return results, rows.Err()
}

func isPgUniqueViolation(err error) bool {
	var pqErr *pq.Error
	return errors.As(err, &pqErr) && pqErr.Code == "23505"
}
