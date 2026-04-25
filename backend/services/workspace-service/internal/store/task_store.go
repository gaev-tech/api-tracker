package store

import (
	"context"
	"database/sql"
	"encoding/base64"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/gaev-tech/api-tracker/backend/pkg/rsql"
	"github.com/gaev-tech/api-tracker/workspace-service/internal/domain"
	"github.com/lib/pq"
)

type TaskStore struct {
	db *sql.DB
}

func NewTaskStore(db *sql.DB) *TaskStore {
	return &TaskStore{db: db}
}

var rsqlFields = map[string]string{
	"id":          "t.id::text",
	"title":       "t.title",
	"description": "t.description",
	"status":      "t.status",
	"author_id":   "t.author_id::text",
	"assignee_id": "t.assignee_id::text",
	"created_at":  "t.created_at",
	"updated_at":  "t.updated_at",
}

var allowedSortFields = map[string]string{
	"created_at": "t.created_at",
	"updated_at": "t.updated_at",
	"title":      "t.title",
}

// Create inserts a new task with its project and blocker associations.
func (s *TaskStore) Create(ctx context.Context, tx *sql.Tx, authorID string, req *domain.CreateTaskRequest) (*domain.Task, error) {
	status := req.Status
	if status == "" {
		status = domain.StatusOpened
	}
	tags := req.Tags
	if tags == nil {
		tags = []string{}
	}

	var task domain.Task
	err := tx.QueryRowContext(ctx, `
		INSERT INTO tasks (title, description, status, author_id, assignee_id, tags)
		VALUES ($1, $2, $3, $4, $5, $6)
		RETURNING id, title, description, status, author_id, assignee_id, tags, is_frozen_by_tariff, created_at, updated_at`,
		req.Title, req.Description, status, authorID, req.AssigneeID, pq.Array(tags),
	).Scan(
		&task.ID, &task.Title, &task.Description, &task.Status,
		&task.AuthorID, &task.AssigneeID, pq.Array(&task.Tags),
		&task.IsFrozenByTariff, &task.CreatedAt, &task.UpdatedAt,
	)
	if err != nil {
		return nil, err
	}

	// Insert project associations
	for _, pid := range req.ProjectIDs {
		if _, err := tx.ExecContext(ctx, `INSERT INTO task_projects (task_id, project_id) VALUES ($1, $2)`, task.ID, pid); err != nil {
			return nil, err
		}
	}

	// Insert blocker associations
	for _, bid := range req.BlockingTaskIDs {
		if _, err := tx.ExecContext(ctx, `INSERT INTO task_blockers (task_id, blocking_task_id) VALUES ($1, $2)`, task.ID, bid); err != nil {
			return nil, err
		}
	}

	task.ProjectIDs = req.ProjectIDs
	if task.ProjectIDs == nil {
		task.ProjectIDs = []string{}
	}
	task.BlockingTaskIDs = req.BlockingTaskIDs
	if task.BlockingTaskIDs == nil {
		task.BlockingTaskIDs = []string{}
	}
	task.BlockedTaskIDs = []string{}

	return &task, nil
}

// FindByID returns a task with its project and blocker associations.
func (s *TaskStore) FindByID(ctx context.Context, taskID string) (*domain.Task, error) {
	var task domain.Task
	err := s.db.QueryRowContext(ctx, `
		SELECT id, title, description, status, author_id, assignee_id, tags, is_frozen_by_tariff, created_at, updated_at
		FROM tasks WHERE id = $1`, taskID,
	).Scan(
		&task.ID, &task.Title, &task.Description, &task.Status,
		&task.AuthorID, &task.AssigneeID, pq.Array(&task.Tags),
		&task.IsFrozenByTariff, &task.CreatedAt, &task.UpdatedAt,
	)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, ErrNotFound
	}
	if err != nil {
		return nil, err
	}

	if err := s.loadRelations(ctx, &task); err != nil {
		return nil, err
	}
	return &task, nil
}

// List returns tasks for the given author with RSQL filtering, cursor pagination, and sorting.
func (s *TaskStore) List(ctx context.Context, params *domain.TaskListParams) (*domain.TaskListResult, error) {
	sortCol, ok := allowedSortFields[params.SortField]
	if !ok {
		sortCol = "t.created_at"
	}
	sortDir := "ASC"
	if strings.EqualFold(params.SortDir, "desc") {
		sortDir = "DESC"
	}

	where := "t.author_id = $1"
	args := []any{params.AuthorID}

	// RSQL filter
	if params.Filter != "" {
		node, err := rsql.Parse(params.Filter)
		if err != nil {
			return nil, fmt.Errorf("invalid filter: %w", err)
		}
		filterSQL, filterArgs, err := rsql.ToSQL(node, rsqlFields)
		if err != nil {
			return nil, fmt.Errorf("invalid filter: %w", err)
		}
		// Rebase positional args
		for i, a := range filterArgs {
			args = append(args, a)
			filterSQL = strings.Replace(filterSQL, fmt.Sprintf("$%d", i+1), fmt.Sprintf("$%d", len(args)), 1)
		}
		where += " AND " + filterSQL
	}

	// Cursor
	if params.Cursor != "" {
		cursorTime, cursorID, err := decodeCursor(params.Cursor)
		if err == nil {
			args = append(args, cursorTime, cursorID)
			if sortDir == "ASC" {
				where += fmt.Sprintf(" AND (%s > $%d OR (%s = $%d AND t.id > $%d))",
					sortCol, len(args)-1, sortCol, len(args)-1, len(args))
			} else {
				where += fmt.Sprintf(" AND (%s < $%d OR (%s = $%d AND t.id > $%d))",
					sortCol, len(args)-1, sortCol, len(args)-1, len(args))
			}
		}
	}

	// Count total
	var total int
	countQuery := "SELECT COUNT(*) FROM tasks t WHERE t.author_id = $1"
	if err := s.db.QueryRowContext(ctx, countQuery, params.AuthorID).Scan(&total); err != nil {
		return nil, err
	}

	// Query
	limit := params.Limit
	if limit <= 0 || limit > 100 {
		limit = 50
	}

	query := fmt.Sprintf(`
		SELECT t.id, t.title, t.description, t.status, t.author_id, t.assignee_id,
		       t.tags, t.is_frozen_by_tariff, t.created_at, t.updated_at
		FROM tasks t
		WHERE %s
		ORDER BY %s %s, t.id ASC
		LIMIT %d`, where, sortCol, sortDir, limit+1)

	rows, err := s.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var tasks []*domain.Task
	for rows.Next() {
		t := &domain.Task{}
		if err := rows.Scan(
			&t.ID, &t.Title, &t.Description, &t.Status,
			&t.AuthorID, &t.AssigneeID, pq.Array(&t.Tags),
			&t.IsFrozenByTariff, &t.CreatedAt, &t.UpdatedAt,
		); err != nil {
			return nil, err
		}
		tasks = append(tasks, t)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}

	// Load relations for all tasks
	for _, t := range tasks {
		if err := s.loadRelations(ctx, t); err != nil {
			return nil, err
		}
	}

	var nextCursor *string
	if len(tasks) > limit {
		tasks = tasks[:limit]
		last := tasks[limit-1]
		var cursorTime time.Time
		switch params.SortField {
		case "updated_at":
			cursorTime = last.UpdatedAt
		default:
			cursorTime = last.CreatedAt
		}
		c := encodeCursor(cursorTime, last.ID)
		nextCursor = &c
	}

	if tasks == nil {
		tasks = []*domain.Task{}
	}

	return &domain.TaskListResult{
		Items:      tasks,
		NextCursor: nextCursor,
		Total:      total,
	}, nil
}

const visibilityCondition = `(
	t.author_id = $1
	OR EXISTS(SELECT 1 FROM task_direct_accesses WHERE task_id = t.id AND grantee_user_id = $1)
	OR EXISTS(SELECT 1 FROM task_projects tp JOIN project_members pm ON tp.project_id = pm.project_id WHERE tp.task_id = t.id AND pm.user_id = $1)
	OR EXISTS(SELECT 1 FROM task_projects tp JOIN project_team_members ptm ON tp.project_id = ptm.project_id JOIN team_members tm ON ptm.team_id = tm.team_id WHERE tp.task_id = t.id AND tm.user_id = $1)
	OR EXISTS(SELECT 1 FROM task_direct_accesses tda JOIN team_members tm ON tda.grantee_team_id = tm.team_id WHERE tda.task_id = t.id AND tm.user_id = $1)
)`

// ListVisible returns tasks visible to the user through any access source.
func (s *TaskStore) ListVisible(ctx context.Context, params *domain.TaskListParams) (*domain.TaskListResult, error) {
	sortCol, ok := allowedSortFields[params.SortField]
	if !ok {
		sortCol = "t.created_at"
	}
	sortDir := "ASC"
	if strings.EqualFold(params.SortDir, "desc") {
		sortDir = "DESC"
	}

	where := visibilityCondition
	args := []any{params.UserID}

	// RSQL filter
	if params.Filter != "" {
		node, err := rsql.Parse(params.Filter)
		if err != nil {
			return nil, fmt.Errorf("invalid filter: %w", err)
		}
		filterSQL, filterArgs, err := rsql.ToSQL(node, rsqlFields)
		if err != nil {
			return nil, fmt.Errorf("invalid filter: %w", err)
		}
		for i, filterArg := range filterArgs {
			args = append(args, filterArg)
			filterSQL = strings.Replace(filterSQL, fmt.Sprintf("$%d", i+1), fmt.Sprintf("$%d", len(args)), 1)
		}
		where += " AND " + filterSQL
	}

	// Cursor
	if params.Cursor != "" {
		cursorTime, cursorID, err := decodeCursor(params.Cursor)
		if err == nil {
			args = append(args, cursorTime, cursorID)
			if sortDir == "ASC" {
				where += fmt.Sprintf(" AND (%s > $%d OR (%s = $%d AND t.id > $%d))",
					sortCol, len(args)-1, sortCol, len(args)-1, len(args))
			} else {
				where += fmt.Sprintf(" AND (%s < $%d OR (%s = $%d AND t.id > $%d))",
					sortCol, len(args)-1, sortCol, len(args)-1, len(args))
			}
		}
	}

	// Count total visible
	var total int
	countQuery := fmt.Sprintf("SELECT COUNT(*) FROM tasks t WHERE %s", visibilityCondition)
	if err := s.db.QueryRowContext(ctx, countQuery, params.UserID).Scan(&total); err != nil {
		return nil, err
	}

	limit := params.Limit
	if limit <= 0 || limit > 100 {
		limit = 50
	}

	query := fmt.Sprintf(`
		SELECT t.id, t.title, t.description, t.status, t.author_id, t.assignee_id,
		       t.tags, t.is_frozen_by_tariff, t.created_at, t.updated_at
		FROM tasks t
		WHERE %s
		ORDER BY %s %s, t.id ASC
		LIMIT %d`, where, sortCol, sortDir, limit+1)

	rows, err := s.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var tasks []*domain.Task
	for rows.Next() {
		task := &domain.Task{}
		if err := rows.Scan(
			&task.ID, &task.Title, &task.Description, &task.Status,
			&task.AuthorID, &task.AssigneeID, pq.Array(&task.Tags),
			&task.IsFrozenByTariff, &task.CreatedAt, &task.UpdatedAt,
		); err != nil {
			return nil, err
		}
		tasks = append(tasks, task)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}

	for _, task := range tasks {
		if err := s.loadRelations(ctx, task); err != nil {
			return nil, err
		}
	}

	var nextCursor *string
	if len(tasks) > limit {
		tasks = tasks[:limit]
		last := tasks[limit-1]
		var cursorTime time.Time
		switch params.SortField {
		case "updated_at":
			cursorTime = last.UpdatedAt
		default:
			cursorTime = last.CreatedAt
		}
		cursor := encodeCursor(cursorTime, last.ID)
		nextCursor = &cursor
	}

	if tasks == nil {
		tasks = []*domain.Task{}
	}

	return &domain.TaskListResult{
		Items:      tasks,
		NextCursor: nextCursor,
		Total:      total,
	}, nil
}

// ListByProject returns tasks attached to a specific project with RSQL filtering, cursor pagination, and sorting.
func (s *TaskStore) ListByProject(ctx context.Context, params *domain.TaskListParams) (*domain.TaskListResult, error) {
	sortCol, ok := allowedSortFields[params.SortField]
	if !ok {
		sortCol = "t.created_at"
	}
	sortDir := "ASC"
	if strings.EqualFold(params.SortDir, "desc") {
		sortDir = "DESC"
	}

	where := "EXISTS(SELECT 1 FROM task_projects tp WHERE tp.task_id = t.id AND tp.project_id = $1)"
	args := []any{params.ProjectID}

	if params.Filter != "" {
		node, err := rsql.Parse(params.Filter)
		if err != nil {
			return nil, fmt.Errorf("invalid filter: %w", err)
		}
		filterSQL, filterArgs, err := rsql.ToSQL(node, rsqlFields)
		if err != nil {
			return nil, fmt.Errorf("invalid filter: %w", err)
		}
		for i, filterArg := range filterArgs {
			args = append(args, filterArg)
			filterSQL = strings.Replace(filterSQL, fmt.Sprintf("$%d", i+1), fmt.Sprintf("$%d", len(args)), 1)
		}
		where += " AND " + filterSQL
	}

	if params.Cursor != "" {
		cursorTime, cursorID, err := decodeCursor(params.Cursor)
		if err == nil {
			args = append(args, cursorTime, cursorID)
			if sortDir == "ASC" {
				where += fmt.Sprintf(" AND (%s > $%d OR (%s = $%d AND t.id > $%d))",
					sortCol, len(args)-1, sortCol, len(args)-1, len(args))
			} else {
				where += fmt.Sprintf(" AND (%s < $%d OR (%s = $%d AND t.id > $%d))",
					sortCol, len(args)-1, sortCol, len(args)-1, len(args))
			}
		}
	}

	var total int
	countQuery := "SELECT COUNT(*) FROM tasks t WHERE EXISTS(SELECT 1 FROM task_projects tp WHERE tp.task_id = t.id AND tp.project_id = $1)"
	if err := s.db.QueryRowContext(ctx, countQuery, params.ProjectID).Scan(&total); err != nil {
		return nil, err
	}

	limit := params.Limit
	if limit <= 0 || limit > 100 {
		limit = 50
	}

	query := fmt.Sprintf(`
		SELECT t.id, t.title, t.description, t.status, t.author_id, t.assignee_id,
		       t.tags, t.is_frozen_by_tariff, t.created_at, t.updated_at
		FROM tasks t
		WHERE %s
		ORDER BY %s %s, t.id ASC
		LIMIT %d`, where, sortCol, sortDir, limit+1)

	rows, err := s.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var tasks []*domain.Task
	for rows.Next() {
		task := &domain.Task{}
		if err := rows.Scan(
			&task.ID, &task.Title, &task.Description, &task.Status,
			&task.AuthorID, &task.AssigneeID, pq.Array(&task.Tags),
			&task.IsFrozenByTariff, &task.CreatedAt, &task.UpdatedAt,
		); err != nil {
			return nil, err
		}
		tasks = append(tasks, task)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}

	for _, task := range tasks {
		if err := s.loadRelations(ctx, task); err != nil {
			return nil, err
		}
	}

	var nextCursor *string
	if len(tasks) > limit {
		tasks = tasks[:limit]
		last := tasks[limit-1]
		var cursorTime time.Time
		switch params.SortField {
		case "updated_at":
			cursorTime = last.UpdatedAt
		default:
			cursorTime = last.CreatedAt
		}
		cursor := encodeCursor(cursorTime, last.ID)
		nextCursor = &cursor
	}

	if tasks == nil {
		tasks = []*domain.Task{}
	}

	return &domain.TaskListResult{
		Items:      tasks,
		NextCursor: nextCursor,
		Total:      total,
	}, nil
}

// Update updates task fields. Only non-nil fields in req are updated.
func (s *TaskStore) Update(ctx context.Context, tx *sql.Tx, taskID string, req *domain.UpdateTaskRequest) (*domain.Task, error) {
	sets := []string{}
	args := []any{}
	argN := 1

	if req.Title != nil {
		sets = append(sets, fmt.Sprintf("title = $%d", argN))
		args = append(args, *req.Title)
		argN++
	}
	if req.Description != nil {
		sets = append(sets, fmt.Sprintf("description = $%d", argN))
		args = append(args, *req.Description)
		argN++
	}
	if req.Status != nil {
		sets = append(sets, fmt.Sprintf("status = $%d", argN))
		args = append(args, *req.Status)
		argN++
	}
	if req.AssigneeID != nil {
		sets = append(sets, fmt.Sprintf("assignee_id = $%d", argN))
		if *req.AssigneeID == nil {
			args = append(args, nil)
		} else {
			args = append(args, **req.AssigneeID)
		}
		argN++
	}
	if req.Tags != nil {
		sets = append(sets, fmt.Sprintf("tags = $%d", argN))
		args = append(args, pq.Array(*req.Tags))
		argN++
	}

	sets = append(sets, "updated_at = now()")
	args = append(args, taskID)

	query := fmt.Sprintf(`
		UPDATE tasks SET %s WHERE id = $%d
		RETURNING id, title, description, status, author_id, assignee_id, tags, is_frozen_by_tariff, created_at, updated_at`,
		strings.Join(sets, ", "), argN)

	var task domain.Task
	err := tx.QueryRowContext(ctx, query, args...).Scan(
		&task.ID, &task.Title, &task.Description, &task.Status,
		&task.AuthorID, &task.AssigneeID, pq.Array(&task.Tags),
		&task.IsFrozenByTariff, &task.CreatedAt, &task.UpdatedAt,
	)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, ErrNotFound
	}
	if err != nil {
		return nil, err
	}

	// Update blockers if provided
	if req.BlockingTaskIDs != nil {
		if _, err := tx.ExecContext(ctx, `DELETE FROM task_blockers WHERE task_id = $1`, taskID); err != nil {
			return nil, err
		}
		for _, bid := range *req.BlockingTaskIDs {
			if _, err := tx.ExecContext(ctx, `INSERT INTO task_blockers (task_id, blocking_task_id) VALUES ($1, $2)`, taskID, bid); err != nil {
				return nil, err
			}
		}
	}

	if err := s.loadRelationsFromDB(ctx, s.db, &task); err != nil {
		return nil, err
	}
	return &task, nil
}

// Delete removes a task.
func (s *TaskStore) Delete(ctx context.Context, tx *sql.Tx, taskID string) error {
	res, err := tx.ExecContext(ctx, `DELETE FROM tasks WHERE id = $1`, taskID)
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

// AttachProject adds a project association to a task.
func (s *TaskStore) AttachProject(ctx context.Context, taskID, projectID string) error {
	_, err := s.db.ExecContext(ctx, `INSERT INTO task_projects (task_id, project_id) VALUES ($1, $2)`, taskID, projectID)
	if isPgUniqueViolation(err) {
		return ErrConflict
	}
	return err
}

// DetachProject removes a project association from a task.
func (s *TaskStore) DetachProject(ctx context.Context, taskID, projectID string) error {
	res, err := s.db.ExecContext(ctx, `DELETE FROM task_projects WHERE task_id = $1 AND project_id = $2`, taskID, projectID)
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

func (s *TaskStore) loadRelations(ctx context.Context, task *domain.Task) error {
	return s.loadRelationsFromDB(ctx, s.db, task)
}

func (s *TaskStore) loadRelationsFromDB(ctx context.Context, db interface {
	QueryContext(ctx context.Context, query string, args ...any) (*sql.Rows, error)
}, task *domain.Task) error {
	// Project IDs
	projRows, err := db.QueryContext(ctx, `SELECT project_id FROM task_projects WHERE task_id = $1`, task.ID)
	if err != nil {
		return err
	}
	defer projRows.Close()
	task.ProjectIDs = []string{}
	for projRows.Next() {
		var pid string
		if err := projRows.Scan(&pid); err != nil {
			return err
		}
		task.ProjectIDs = append(task.ProjectIDs, pid)
	}
	if err := projRows.Err(); err != nil {
		return err
	}

	// Blocking task IDs
	blockRows, err := db.QueryContext(ctx, `SELECT blocking_task_id FROM task_blockers WHERE task_id = $1`, task.ID)
	if err != nil {
		return err
	}
	defer blockRows.Close()
	task.BlockingTaskIDs = []string{}
	for blockRows.Next() {
		var bid string
		if err := blockRows.Scan(&bid); err != nil {
			return err
		}
		task.BlockingTaskIDs = append(task.BlockingTaskIDs, bid)
	}
	if err := blockRows.Err(); err != nil {
		return err
	}

	// Blocked task IDs (reverse)
	blockedRows, err := db.QueryContext(ctx, `SELECT task_id FROM task_blockers WHERE blocking_task_id = $1`, task.ID)
	if err != nil {
		return err
	}
	defer blockedRows.Close()
	task.BlockedTaskIDs = []string{}
	for blockedRows.Next() {
		var bid string
		if err := blockedRows.Scan(&bid); err != nil {
			return err
		}
		task.BlockedTaskIDs = append(task.BlockedTaskIDs, bid)
	}
	return blockedRows.Err()
}

func encodeCursor(t time.Time, id string) string {
	return base64.RawURLEncoding.EncodeToString([]byte(fmt.Sprintf("%s|%s", t.Format(time.RFC3339Nano), id)))
}

func decodeCursor(cursor string) (time.Time, string, error) {
	b, err := base64.RawURLEncoding.DecodeString(cursor)
	if err != nil {
		return time.Time{}, "", err
	}
	parts := strings.SplitN(string(b), "|", 2)
	if len(parts) != 2 {
		return time.Time{}, "", fmt.Errorf("invalid cursor format")
	}
	t, err := time.Parse(time.RFC3339Nano, parts[0])
	if err != nil {
		return time.Time{}, "", err
	}
	return t, parts[1], nil
}
