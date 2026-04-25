package store

import (
	"context"
	"database/sql"
	"errors"

	"github.com/gaev-tech/api-tracker/workspace-service/internal/domain"
)

const projectTransferColumns = "id, project_id, from_user_id, to_user_id, status, created_at"
const teamTransferColumns = "id, team_id, from_user_id, to_user_id, status, created_at"

type OwnershipTransferStore struct {
	db *sql.DB
}

func NewOwnershipTransferStore(db *sql.DB) *OwnershipTransferStore {
	return &OwnershipTransferStore{db: db}
}

func scanProjectTransfer(row interface{ Scan(dest ...any) error }) (*domain.ProjectOwnershipTransfer, error) {
	var transfer domain.ProjectOwnershipTransfer
	err := row.Scan(&transfer.ID, &transfer.ProjectID, &transfer.FromUserID, &transfer.ToUserID, &transfer.Status, &transfer.CreatedAt)
	if err != nil {
		return nil, err
	}
	return &transfer, nil
}

func scanTeamTransfer(row interface{ Scan(dest ...any) error }) (*domain.TeamOwnershipTransfer, error) {
	var transfer domain.TeamOwnershipTransfer
	err := row.Scan(&transfer.ID, &transfer.TeamID, &transfer.FromUserID, &transfer.ToUserID, &transfer.Status, &transfer.CreatedAt)
	if err != nil {
		return nil, err
	}
	return &transfer, nil
}

// CreateProjectTransfer inserts a new pending project ownership transfer.
func (store *OwnershipTransferStore) CreateProjectTransfer(ctx context.Context, tx *sql.Tx, projectID, fromUserID, toUserID string) (*domain.ProjectOwnershipTransfer, error) {
	row := tx.QueryRowContext(ctx, `
		INSERT INTO project_ownership_transfers (project_id, from_user_id, to_user_id)
		VALUES ($1, $2, $3)
		RETURNING `+projectTransferColumns,
		projectID, fromUserID, toUserID,
	)
	return scanProjectTransfer(row)
}

// FindProjectTransfer returns a project ownership transfer by ID.
func (store *OwnershipTransferStore) FindProjectTransfer(ctx context.Context, transferID string) (*domain.ProjectOwnershipTransfer, error) {
	row := store.db.QueryRowContext(ctx, `
		SELECT `+projectTransferColumns+` FROM project_ownership_transfers WHERE id = $1`, transferID)
	transfer, err := scanProjectTransfer(row)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, ErrNotFound
	}
	return transfer, err
}

// DeleteProjectTransfer removes a project ownership transfer (cancel).
func (store *OwnershipTransferStore) DeleteProjectTransfer(ctx context.Context, tx *sql.Tx, transferID string) error {
	res, err := tx.ExecContext(ctx, `DELETE FROM project_ownership_transfers WHERE id = $1`, transferID)
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

// AcceptProjectTransfer marks the transfer as accepted and updates the project owner.
func (store *OwnershipTransferStore) AcceptProjectTransfer(ctx context.Context, tx *sql.Tx, transferID string) (*domain.ProjectOwnershipTransfer, error) {
	var transfer domain.ProjectOwnershipTransfer
	err := tx.QueryRowContext(ctx, `
		UPDATE project_ownership_transfers SET status = 'accepted'
		WHERE id = $1
		RETURNING `+projectTransferColumns, transferID,
	).Scan(&transfer.ID, &transfer.ProjectID, &transfer.FromUserID, &transfer.ToUserID, &transfer.Status, &transfer.CreatedAt)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, ErrNotFound
	}
	if err != nil {
		return nil, err
	}

	_, err = tx.ExecContext(ctx, `UPDATE projects SET owner_id = $1, updated_at = now() WHERE id = $2`, transfer.ToUserID, transfer.ProjectID)
	if err != nil {
		return nil, err
	}

	return &transfer, nil
}

// DeclineProjectTransfer marks the transfer as declined.
func (store *OwnershipTransferStore) DeclineProjectTransfer(ctx context.Context, tx *sql.Tx, transferID string) (*domain.ProjectOwnershipTransfer, error) {
	var transfer domain.ProjectOwnershipTransfer
	err := tx.QueryRowContext(ctx, `
		UPDATE project_ownership_transfers SET status = 'declined'
		WHERE id = $1
		RETURNING `+projectTransferColumns, transferID,
	).Scan(&transfer.ID, &transfer.ProjectID, &transfer.FromUserID, &transfer.ToUserID, &transfer.Status, &transfer.CreatedAt)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, ErrNotFound
	}
	if err != nil {
		return nil, err
	}
	return &transfer, nil
}

// CreateTeamTransfer inserts a new pending team ownership transfer.
func (store *OwnershipTransferStore) CreateTeamTransfer(ctx context.Context, tx *sql.Tx, teamID, fromUserID, toUserID string) (*domain.TeamOwnershipTransfer, error) {
	row := tx.QueryRowContext(ctx, `
		INSERT INTO team_ownership_transfers (team_id, from_user_id, to_user_id)
		VALUES ($1, $2, $3)
		RETURNING `+teamTransferColumns,
		teamID, fromUserID, toUserID,
	)
	return scanTeamTransfer(row)
}

// FindTeamTransfer returns a team ownership transfer by ID.
func (store *OwnershipTransferStore) FindTeamTransfer(ctx context.Context, transferID string) (*domain.TeamOwnershipTransfer, error) {
	row := store.db.QueryRowContext(ctx, `
		SELECT `+teamTransferColumns+` FROM team_ownership_transfers WHERE id = $1`, transferID)
	transfer, err := scanTeamTransfer(row)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, ErrNotFound
	}
	return transfer, err
}

// DeleteTeamTransfer removes a team ownership transfer (cancel).
func (store *OwnershipTransferStore) DeleteTeamTransfer(ctx context.Context, tx *sql.Tx, transferID string) error {
	res, err := tx.ExecContext(ctx, `DELETE FROM team_ownership_transfers WHERE id = $1`, transferID)
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

// AcceptTeamTransfer marks the transfer as accepted and updates the team owner.
func (store *OwnershipTransferStore) AcceptTeamTransfer(ctx context.Context, tx *sql.Tx, transferID string) (*domain.TeamOwnershipTransfer, error) {
	var transfer domain.TeamOwnershipTransfer
	err := tx.QueryRowContext(ctx, `
		UPDATE team_ownership_transfers SET status = 'accepted'
		WHERE id = $1
		RETURNING `+teamTransferColumns, transferID,
	).Scan(&transfer.ID, &transfer.TeamID, &transfer.FromUserID, &transfer.ToUserID, &transfer.Status, &transfer.CreatedAt)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, ErrNotFound
	}
	if err != nil {
		return nil, err
	}

	_, err = tx.ExecContext(ctx, `UPDATE teams SET owner_id = $1, updated_at = now() WHERE id = $2`, transfer.ToUserID, transfer.TeamID)
	if err != nil {
		return nil, err
	}

	return &transfer, nil
}

// DeclineTeamTransfer marks the transfer as declined.
func (store *OwnershipTransferStore) DeclineTeamTransfer(ctx context.Context, tx *sql.Tx, transferID string) (*domain.TeamOwnershipTransfer, error) {
	var transfer domain.TeamOwnershipTransfer
	err := tx.QueryRowContext(ctx, `
		UPDATE team_ownership_transfers SET status = 'declined'
		WHERE id = $1
		RETURNING `+teamTransferColumns, transferID,
	).Scan(&transfer.ID, &transfer.TeamID, &transfer.FromUserID, &transfer.ToUserID, &transfer.Status, &transfer.CreatedAt)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, ErrNotFound
	}
	if err != nil {
		return nil, err
	}
	return &transfer, nil
}
