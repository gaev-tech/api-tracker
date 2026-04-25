package store

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"strings"

	"github.com/gaev-tech/api-tracker/workspace-service/internal/domain"
)

const projectColumns = "id, name, description, owner_id, created_at, updated_at"

type ProjectStore struct {
	db *sql.DB
}

func NewProjectStore(db *sql.DB) *ProjectStore {
	return &ProjectStore{db: db}
}

func scanProject(row interface{ Scan(dest ...any) error }) (*domain.Project, error) {
	var p domain.Project
	err := row.Scan(&p.ID, &p.Name, &p.Description, &p.OwnerID, &p.CreatedAt, &p.UpdatedAt)
	if err != nil {
		return nil, err
	}
	return &p, nil
}

// Create inserts a new project.
func (s *ProjectStore) Create(ctx context.Context, tx *sql.Tx, ownerID string, req *domain.CreateProjectRequest) (*domain.Project, error) {
	row := tx.QueryRowContext(ctx, fmt.Sprintf(`
		INSERT INTO projects (name, description, owner_id)
		VALUES ($1, $2, $3)
		RETURNING %s`, projectColumns),
		req.Name, req.Description, ownerID,
	)
	return scanProject(row)
}

// FindByID returns a project by its ID.
func (s *ProjectStore) FindByID(ctx context.Context, projectID string) (*domain.Project, error) {
	row := s.db.QueryRowContext(ctx, fmt.Sprintf(`
		SELECT %s FROM projects WHERE id = $1`, projectColumns), projectID)
	p, err := scanProject(row)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, ErrNotFound
	}
	return p, err
}

// ListByOwner returns projects owned by the given user with cursor pagination.
func (s *ProjectStore) ListByOwner(ctx context.Context, params *domain.ProjectListParams) (*domain.ProjectListResult, error) {
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
	if err := s.db.QueryRowContext(ctx, "SELECT COUNT(*) FROM projects WHERE owner_id = $1", params.OwnerID).Scan(&total); err != nil {
		return nil, err
	}

	limit := params.Limit
	if limit <= 0 || limit > 100 {
		limit = 50
	}

	query := fmt.Sprintf(`
		SELECT %s FROM projects
		WHERE %s
		ORDER BY created_at ASC, id ASC
		LIMIT %d`, projectColumns, where, limit+1)

	rows, err := s.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var projects []*domain.Project
	for rows.Next() {
		p, err := scanProject(rows)
		if err != nil {
			return nil, err
		}
		projects = append(projects, p)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}

	var nextCursor *string
	if len(projects) > limit {
		projects = projects[:limit]
		last := projects[limit-1]
		c := encodeCursor(last.CreatedAt, last.ID)
		nextCursor = &c
	}

	if projects == nil {
		projects = []*domain.Project{}
	}

	return &domain.ProjectListResult{
		Items:      projects,
		NextCursor: nextCursor,
		Total:      total,
	}, nil
}

// Update updates project fields. Only non-nil fields in req are updated.
func (s *ProjectStore) Update(ctx context.Context, tx *sql.Tx, projectID string, req *domain.UpdateProjectRequest) (*domain.Project, error) {
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
	args = append(args, projectID)

	query := fmt.Sprintf(`
		UPDATE projects SET %s WHERE id = $%d
		RETURNING %s`,
		strings.Join(sets, ", "), argN, projectColumns)

	row := tx.QueryRowContext(ctx, query, args...)
	p, err := scanProject(row)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, ErrNotFound
	}
	return p, err
}

// Delete removes a project.
func (s *ProjectStore) Delete(ctx context.Context, tx *sql.Tx, projectID string) error {
	res, err := tx.ExecContext(ctx, `DELETE FROM projects WHERE id = $1`, projectID)
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

// ListByMember returns projects where the user is a member (directly or via team).
func (s *ProjectStore) ListByMember(ctx context.Context, params *domain.ProjectListParams) (*domain.ProjectListResult, error) {
	memberCondition := `(
		EXISTS(SELECT 1 FROM project_members pm WHERE pm.project_id = p.id AND pm.user_id = $1)
		OR EXISTS(SELECT 1 FROM project_team_members ptm JOIN team_members tm ON ptm.team_id = tm.team_id WHERE ptm.project_id = p.id AND tm.user_id = $1)
	)`

	where := memberCondition
	args := []any{params.OwnerID} // reusing OwnerID field as userID

	if params.Cursor != "" {
		cursorTime, cursorID, err := decodeCursor(params.Cursor)
		if err == nil {
			args = append(args, cursorTime, cursorID)
			where += fmt.Sprintf(" AND (p.created_at > $%d OR (p.created_at = $%d AND p.id > $%d))",
				len(args)-1, len(args)-1, len(args))
		}
	}

	var total int
	countQuery := fmt.Sprintf("SELECT COUNT(*) FROM projects p WHERE %s", memberCondition)
	if err := s.db.QueryRowContext(ctx, countQuery, params.OwnerID).Scan(&total); err != nil {
		return nil, err
	}

	limit := params.Limit
	if limit <= 0 || limit > 100 {
		limit = 50
	}

	query := fmt.Sprintf(`
		SELECT %s FROM projects p
		WHERE %s
		ORDER BY p.created_at ASC, p.id ASC
		LIMIT %d`, projectColumns, where, limit+1)

	rows, err := s.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var projects []*domain.Project
	for rows.Next() {
		project, err := scanProject(rows)
		if err != nil {
			return nil, err
		}
		projects = append(projects, project)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}

	var nextCursor *string
	if len(projects) > limit {
		projects = projects[:limit]
		last := projects[limit-1]
		cursor := encodeCursor(last.CreatedAt, last.ID)
		nextCursor = &cursor
	}

	if projects == nil {
		projects = []*domain.Project{}
	}

	return &domain.ProjectListResult{
		Items:      projects,
		NextCursor: nextCursor,
		Total:      total,
	}, nil
}
