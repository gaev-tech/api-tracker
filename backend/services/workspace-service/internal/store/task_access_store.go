package store

import (
	"context"
	"database/sql"
	"errors"

	"github.com/gaev-tech/api-tracker/workspace-service/internal/domain"
)

type TaskAccessStore struct {
	db *sql.DB
}

func NewTaskAccessStore(db *sql.DB) *TaskAccessStore {
	return &TaskAccessStore{db: db}
}

const taskAccessColumns = `id, task_id, grantee_user_id, grantee_team_id, granted_by,
	edit_title, edit_description, edit_tags, edit_blockers,
	edit_assignee, edit_status, share, delete_task,
	created_at, updated_at`

func scanTaskAccess(row interface{ Scan(dest ...any) error }) (*domain.TaskDirectAccess, error) {
	access := &domain.TaskDirectAccess{}
	err := row.Scan(
		&access.ID, &access.TaskID, &access.GranteeUserID, &access.GranteeTeamID, &access.GrantedBy,
		&access.Permissions.EditTitle, &access.Permissions.EditDescription,
		&access.Permissions.EditTags, &access.Permissions.EditBlockers,
		&access.Permissions.EditAssignee, &access.Permissions.EditStatus,
		&access.Permissions.Share, &access.Permissions.DeleteTask,
		&access.CreatedAt, &access.UpdatedAt,
	)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, ErrNotFound
	}
	return access, err
}

func (store *TaskAccessStore) Create(ctx context.Context, tx *sql.Tx, taskID, grantedBy string, req *domain.CreateTaskAccessRequest) (*domain.TaskDirectAccess, error) {
	row := tx.QueryRowContext(ctx, `
		INSERT INTO task_direct_accesses (task_id, grantee_user_id, grantee_team_id, granted_by,
			edit_title, edit_description, edit_tags, edit_blockers,
			edit_assignee, edit_status, share, delete_task)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
		RETURNING `+taskAccessColumns,
		taskID, req.GranteeUserID, req.GranteeTeamID, grantedBy,
		req.Permissions.EditTitle, req.Permissions.EditDescription,
		req.Permissions.EditTags, req.Permissions.EditBlockers,
		req.Permissions.EditAssignee, req.Permissions.EditStatus,
		req.Permissions.Share, req.Permissions.DeleteTask,
	)
	access, err := scanTaskAccess(row)
	if err != nil && isPgUniqueViolation(err) {
		return nil, ErrConflict
	}
	return access, err
}

func (store *TaskAccessStore) ListByTask(ctx context.Context, taskID string) ([]*domain.TaskDirectAccess, error) {
	rows, err := store.db.QueryContext(ctx, `
		SELECT `+taskAccessColumns+` FROM task_direct_accesses
		WHERE task_id = $1 ORDER BY created_at`, taskID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var accesses []*domain.TaskDirectAccess
	for rows.Next() {
		access := &domain.TaskDirectAccess{}
		if err := rows.Scan(
			&access.ID, &access.TaskID, &access.GranteeUserID, &access.GranteeTeamID, &access.GrantedBy,
			&access.Permissions.EditTitle, &access.Permissions.EditDescription,
			&access.Permissions.EditTags, &access.Permissions.EditBlockers,
			&access.Permissions.EditAssignee, &access.Permissions.EditStatus,
			&access.Permissions.Share, &access.Permissions.DeleteTask,
			&access.CreatedAt, &access.UpdatedAt,
		); err != nil {
			return nil, err
		}
		accesses = append(accesses, access)
	}
	return accesses, rows.Err()
}

func (store *TaskAccessStore) FindByID(ctx context.Context, accessID string) (*domain.TaskDirectAccess, error) {
	row := store.db.QueryRowContext(ctx, `SELECT `+taskAccessColumns+` FROM task_direct_accesses WHERE id = $1`, accessID)
	return scanTaskAccess(row)
}

func (store *TaskAccessStore) Update(ctx context.Context, tx *sql.Tx, accessID string, req *domain.UpdateTaskAccessRequest) (*domain.TaskDirectAccess, error) {
	row := tx.QueryRowContext(ctx, `
		UPDATE task_direct_accesses SET
			edit_title = $2, edit_description = $3, edit_tags = $4, edit_blockers = $5,
			edit_assignee = $6, edit_status = $7, share = $8, delete_task = $9,
			updated_at = now()
		WHERE id = $1
		RETURNING `+taskAccessColumns,
		accessID,
		req.Permissions.EditTitle, req.Permissions.EditDescription,
		req.Permissions.EditTags, req.Permissions.EditBlockers,
		req.Permissions.EditAssignee, req.Permissions.EditStatus,
		req.Permissions.Share, req.Permissions.DeleteTask,
	)
	return scanTaskAccess(row)
}

func (store *TaskAccessStore) Delete(ctx context.Context, tx *sql.Tx, accessID string) error {
	res, err := tx.ExecContext(ctx, `DELETE FROM task_direct_accesses WHERE id = $1`, accessID)
	if err != nil {
		return err
	}
	rowsAffected, err := res.RowsAffected()
	if err != nil {
		return err
	}
	if rowsAffected == 0 {
		return ErrNotFound
	}
	return nil
}

// HasAnyAccess checks if the task has any remaining direct access with at least one permission true.
func (store *TaskAccessStore) HasAnyAccess(ctx context.Context, tx *sql.Tx, taskID string) (bool, error) {
	var exists bool
	err := tx.QueryRowContext(ctx, `
		SELECT EXISTS(
			SELECT 1 FROM task_direct_accesses
			WHERE task_id = $1
			AND (edit_title OR edit_description OR edit_tags OR edit_blockers
				OR edit_assignee OR edit_status OR share OR delete_task)
		)`, taskID).Scan(&exists)
	return exists, err
}
