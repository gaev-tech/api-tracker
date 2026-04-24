package store

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"strings"

	"github.com/gaev-tech/api-tracker/workspace-service/internal/domain"
)

const teamColumns = "id, name, description, owner_id, created_at, updated_at"

type TeamStore struct {
	db *sql.DB
}

func NewTeamStore(db *sql.DB) *TeamStore {
	return &TeamStore{db: db}
}

func scanTeam(row interface{ Scan(dest ...any) error }) (*domain.Team, error) {
	var t domain.Team
	err := row.Scan(&t.ID, &t.Name, &t.Description, &t.OwnerID, &t.CreatedAt, &t.UpdatedAt)
	if err != nil {
		return nil, err
	}
	return &t, nil
}

// Create inserts a new team.
func (s *TeamStore) Create(ctx context.Context, tx *sql.Tx, ownerID string, req *domain.CreateTeamRequest) (*domain.Team, error) {
	row := tx.QueryRowContext(ctx, fmt.Sprintf(`
		INSERT INTO teams (name, description, owner_id)
		VALUES ($1, $2, $3)
		RETURNING %s`, teamColumns),
		req.Name, req.Description, ownerID,
	)
	return scanTeam(row)
}

// FindByID returns a team by its ID.
func (s *TeamStore) FindByID(ctx context.Context, teamID string) (*domain.Team, error) {
	row := s.db.QueryRowContext(ctx, fmt.Sprintf(`
		SELECT %s FROM teams WHERE id = $1`, teamColumns), teamID)
	t, err := scanTeam(row)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, ErrNotFound
	}
	return t, err
}

// ListByOwner returns teams owned by the given user with cursor pagination.
func (s *TeamStore) ListByOwner(ctx context.Context, params *domain.TeamListParams) (*domain.TeamListResult, error) {
	where := "owner_id = $1"
	args := []any{params.OwnerID}

	// Cursor
	if params.Cursor != "" {
		cursorTime, cursorID, err := decodeCursor(params.Cursor)
		if err == nil {
			args = append(args, cursorTime, cursorID)
			where += fmt.Sprintf(" AND (created_at > $%d OR (created_at = $%d AND id > $%d))",
				len(args)-1, len(args)-1, len(args))
		}
	}

	// Count total
	var total int
	if err := s.db.QueryRowContext(ctx, "SELECT COUNT(*) FROM teams WHERE owner_id = $1", params.OwnerID).Scan(&total); err != nil {
		return nil, err
	}

	limit := params.Limit
	if limit <= 0 || limit > 100 {
		limit = 50
	}

	query := fmt.Sprintf(`
		SELECT %s FROM teams
		WHERE %s
		ORDER BY created_at ASC, id ASC
		LIMIT %d`, teamColumns, where, limit+1)

	rows, err := s.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var teams []*domain.Team
	for rows.Next() {
		t, err := scanTeam(rows)
		if err != nil {
			return nil, err
		}
		teams = append(teams, t)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}

	var nextCursor *string
	if len(teams) > limit {
		teams = teams[:limit]
		last := teams[limit-1]
		c := encodeCursor(last.CreatedAt, last.ID)
		nextCursor = &c
	}

	if teams == nil {
		teams = []*domain.Team{}
	}

	return &domain.TeamListResult{
		Items:      teams,
		NextCursor: nextCursor,
		Total:      total,
	}, nil
}

// Update updates team fields. Only non-nil fields in req are updated.
func (s *TeamStore) Update(ctx context.Context, tx *sql.Tx, teamID string, req *domain.UpdateTeamRequest) (*domain.Team, error) {
	sets := []string{}
	args := []any{}
	argN := 1

	if req.Name != nil {
		sets = append(sets, fmt.Sprintf("name = $%d", argN))
		args = append(args, *req.Name)
		argN++
	}
	if req.Description != nil {
		sets = append(sets, fmt.Sprintf("description = $%d", argN))
		args = append(args, *req.Description)
		argN++
	}

	sets = append(sets, "updated_at = now()")
	args = append(args, teamID)

	query := fmt.Sprintf(`
		UPDATE teams SET %s WHERE id = $%d
		RETURNING %s`,
		strings.Join(sets, ", "), argN, teamColumns)

	row := tx.QueryRowContext(ctx, query, args...)
	t, err := scanTeam(row)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, ErrNotFound
	}
	return t, err
}

// Delete removes a team.
func (s *TeamStore) Delete(ctx context.Context, tx *sql.Tx, teamID string) error {
	res, err := tx.ExecContext(ctx, `DELETE FROM teams WHERE id = $1`, teamID)
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

// FindByIDForUpdate returns a team by its ID with a row-level lock (SELECT FOR UPDATE).
func (s *TeamStore) FindByIDForUpdate(ctx context.Context, tx *sql.Tx, teamID string) (*domain.Team, error) {
	row := tx.QueryRowContext(ctx, fmt.Sprintf(`
		SELECT %s FROM teams WHERE id = $1 FOR UPDATE`, teamColumns), teamID)
	t, err := scanTeam(row)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, ErrNotFound
	}
	return t, err
}

func (s *TeamStore) FindByIDTx(ctx context.Context, tx *sql.Tx, teamID string) (*domain.Team, error) {
	row := tx.QueryRowContext(ctx, fmt.Sprintf(`
		SELECT %s FROM teams WHERE id = $1`, teamColumns), teamID)
	t, err := scanTeam(row)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, ErrNotFound
	}
	return t, err
}
