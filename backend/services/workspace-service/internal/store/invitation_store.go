package store

import (
	"context"
	"database/sql"
	"errors"

	"github.com/gaev-tech/api-tracker/workspace-service/internal/domain"
)

type InvitationStore struct {
	db *sql.DB
}

func NewInvitationStore(db *sql.DB) *InvitationStore {
	return &InvitationStore{db: db}
}

// --- Project Invitations ---

// CreateProjectInvitation inserts a new project invitation.
func (store *InvitationStore) CreateProjectInvitation(ctx context.Context, tx *sql.Tx, projectID, invitedBy string, req *domain.ProjectInvitation) (*domain.ProjectInvitation, error) {
	invitation := &domain.ProjectInvitation{}
	err := tx.QueryRowContext(ctx, `
		INSERT INTO project_invitations (project_id, invitee_user_id, invitee_team_id, invited_by,
			edit_title, edit_description, edit_tags, edit_blockers,
			edit_assignee, edit_status, share, delete_task,
			rename_project, manage_members, manage_automations,
			manage_attachments, delete_project, import_tasks)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18)
		RETURNING id, project_id, invitee_user_id, invitee_team_id, invited_by,
			edit_title, edit_description, edit_tags, edit_blockers,
			edit_assignee, edit_status, share, delete_task,
			rename_project, manage_members, manage_automations,
			manage_attachments, delete_project, import_tasks,
			status, created_at`,
		projectID, req.InviteeUserID, req.InviteeTeamID, invitedBy,
		req.Permissions.EditTitle, req.Permissions.EditDescription, req.Permissions.EditTags, req.Permissions.EditBlockers,
		req.Permissions.EditAssignee, req.Permissions.EditStatus, req.Permissions.Share, req.Permissions.DeleteTask,
		req.Permissions.RenameProject, req.Permissions.ManageMembers, req.Permissions.ManageAutomations,
		req.Permissions.ManageAttachments, req.Permissions.DeleteProject, req.Permissions.ImportTasks,
	).Scan(
		&invitation.ID, &invitation.ProjectID, &invitation.InviteeUserID, &invitation.InviteeTeamID, &invitation.InvitedBy,
		&invitation.Permissions.EditTitle, &invitation.Permissions.EditDescription,
		&invitation.Permissions.EditTags, &invitation.Permissions.EditBlockers,
		&invitation.Permissions.EditAssignee, &invitation.Permissions.EditStatus,
		&invitation.Permissions.Share, &invitation.Permissions.DeleteTask,
		&invitation.Permissions.RenameProject, &invitation.Permissions.ManageMembers,
		&invitation.Permissions.ManageAutomations, &invitation.Permissions.ManageAttachments,
		&invitation.Permissions.DeleteProject, &invitation.Permissions.ImportTasks,
		&invitation.Status, &invitation.CreatedAt,
	)
	return invitation, err
}

// ListProjectInvitations returns all pending project invitations.
func (store *InvitationStore) ListProjectInvitations(ctx context.Context, projectID string) ([]*domain.ProjectInvitation, error) {
	rows, err := store.db.QueryContext(ctx, `
		SELECT id, project_id, invitee_user_id, invitee_team_id, invited_by,
			edit_title, edit_description, edit_tags, edit_blockers,
			edit_assignee, edit_status, share, delete_task,
			rename_project, manage_members, manage_automations,
			manage_attachments, delete_project, import_tasks,
			status, created_at
		FROM project_invitations
		WHERE project_id = $1 AND status = 'pending'
		ORDER BY created_at`, projectID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var invitations []*domain.ProjectInvitation
	for rows.Next() {
		invitation := &domain.ProjectInvitation{}
		if err := rows.Scan(
			&invitation.ID, &invitation.ProjectID, &invitation.InviteeUserID, &invitation.InviteeTeamID, &invitation.InvitedBy,
			&invitation.Permissions.EditTitle, &invitation.Permissions.EditDescription,
			&invitation.Permissions.EditTags, &invitation.Permissions.EditBlockers,
			&invitation.Permissions.EditAssignee, &invitation.Permissions.EditStatus,
			&invitation.Permissions.Share, &invitation.Permissions.DeleteTask,
			&invitation.Permissions.RenameProject, &invitation.Permissions.ManageMembers,
			&invitation.Permissions.ManageAutomations, &invitation.Permissions.ManageAttachments,
			&invitation.Permissions.DeleteProject, &invitation.Permissions.ImportTasks,
			&invitation.Status, &invitation.CreatedAt,
		); err != nil {
			return nil, err
		}
		invitations = append(invitations, invitation)
	}
	return invitations, rows.Err()
}

// FindProjectInvitation returns a project invitation by ID.
func (store *InvitationStore) FindProjectInvitation(ctx context.Context, invitationID string) (*domain.ProjectInvitation, error) {
	invitation := &domain.ProjectInvitation{}
	err := store.db.QueryRowContext(ctx, `
		SELECT id, project_id, invitee_user_id, invitee_team_id, invited_by,
			edit_title, edit_description, edit_tags, edit_blockers,
			edit_assignee, edit_status, share, delete_task,
			rename_project, manage_members, manage_automations,
			manage_attachments, delete_project, import_tasks,
			status, created_at
		FROM project_invitations
		WHERE id = $1`, invitationID,
	).Scan(
		&invitation.ID, &invitation.ProjectID, &invitation.InviteeUserID, &invitation.InviteeTeamID, &invitation.InvitedBy,
		&invitation.Permissions.EditTitle, &invitation.Permissions.EditDescription,
		&invitation.Permissions.EditTags, &invitation.Permissions.EditBlockers,
		&invitation.Permissions.EditAssignee, &invitation.Permissions.EditStatus,
		&invitation.Permissions.Share, &invitation.Permissions.DeleteTask,
		&invitation.Permissions.RenameProject, &invitation.Permissions.ManageMembers,
		&invitation.Permissions.ManageAutomations, &invitation.Permissions.ManageAttachments,
		&invitation.Permissions.DeleteProject, &invitation.Permissions.ImportTasks,
		&invitation.Status, &invitation.CreatedAt,
	)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, ErrNotFound
	}
	return invitation, err
}

// DeleteProjectInvitation deletes a project invitation.
func (store *InvitationStore) DeleteProjectInvitation(ctx context.Context, tx *sql.Tx, invitationID string) error {
	result, err := tx.ExecContext(ctx, `DELETE FROM project_invitations WHERE id = $1`, invitationID)
	if err != nil {
		return err
	}
	rowsAffected, err := result.RowsAffected()
	if err != nil {
		return err
	}
	if rowsAffected == 0 {
		return ErrNotFound
	}
	return nil
}

// AcceptProjectInvitation updates a project invitation status to 'accepted' and returns it.
func (store *InvitationStore) AcceptProjectInvitation(ctx context.Context, tx *sql.Tx, invitationID string) (*domain.ProjectInvitation, error) {
	invitation := &domain.ProjectInvitation{}
	err := tx.QueryRowContext(ctx, `
		UPDATE project_invitations SET status = 'accepted'
		WHERE id = $1 AND status = 'pending'
		RETURNING id, project_id, invitee_user_id, invitee_team_id, invited_by,
			edit_title, edit_description, edit_tags, edit_blockers,
			edit_assignee, edit_status, share, delete_task,
			rename_project, manage_members, manage_automations,
			manage_attachments, delete_project, import_tasks,
			status, created_at`, invitationID,
	).Scan(
		&invitation.ID, &invitation.ProjectID, &invitation.InviteeUserID, &invitation.InviteeTeamID, &invitation.InvitedBy,
		&invitation.Permissions.EditTitle, &invitation.Permissions.EditDescription,
		&invitation.Permissions.EditTags, &invitation.Permissions.EditBlockers,
		&invitation.Permissions.EditAssignee, &invitation.Permissions.EditStatus,
		&invitation.Permissions.Share, &invitation.Permissions.DeleteTask,
		&invitation.Permissions.RenameProject, &invitation.Permissions.ManageMembers,
		&invitation.Permissions.ManageAutomations, &invitation.Permissions.ManageAttachments,
		&invitation.Permissions.DeleteProject, &invitation.Permissions.ImportTasks,
		&invitation.Status, &invitation.CreatedAt,
	)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, ErrNotFound
	}
	return invitation, err
}

// DeclineProjectInvitation updates a project invitation status to 'declined'.
func (store *InvitationStore) DeclineProjectInvitation(ctx context.Context, tx *sql.Tx, invitationID string) error {
	result, err := tx.ExecContext(ctx, `
		UPDATE project_invitations SET status = 'declined'
		WHERE id = $1 AND status = 'pending'`, invitationID)
	if err != nil {
		return err
	}
	rowsAffected, err := result.RowsAffected()
	if err != nil {
		return err
	}
	if rowsAffected == 0 {
		return ErrNotFound
	}
	return nil
}

// --- Team Invitations ---

// CreateTeamInvitation inserts a new team invitation.
func (store *InvitationStore) CreateTeamInvitation(ctx context.Context, tx *sql.Tx, teamID, invitedBy, inviteeUserID string) (*domain.TeamInvitation, error) {
	invitation := &domain.TeamInvitation{}
	err := tx.QueryRowContext(ctx, `
		INSERT INTO team_invitations (team_id, invitee_user_id, invited_by)
		VALUES ($1, $2, $3)
		RETURNING id, team_id, invitee_user_id, invited_by, status, created_at`,
		teamID, inviteeUserID, invitedBy,
	).Scan(
		&invitation.ID, &invitation.TeamID, &invitation.InviteeUserID,
		&invitation.InvitedBy, &invitation.Status, &invitation.CreatedAt,
	)
	return invitation, err
}

// ListTeamInvitations returns all pending team invitations.
func (store *InvitationStore) ListTeamInvitations(ctx context.Context, teamID string) ([]*domain.TeamInvitation, error) {
	rows, err := store.db.QueryContext(ctx, `
		SELECT id, team_id, invitee_user_id, invited_by, status, created_at
		FROM team_invitations
		WHERE team_id = $1 AND status = 'pending'
		ORDER BY created_at`, teamID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var invitations []*domain.TeamInvitation
	for rows.Next() {
		invitation := &domain.TeamInvitation{}
		if err := rows.Scan(
			&invitation.ID, &invitation.TeamID, &invitation.InviteeUserID,
			&invitation.InvitedBy, &invitation.Status, &invitation.CreatedAt,
		); err != nil {
			return nil, err
		}
		invitations = append(invitations, invitation)
	}
	return invitations, rows.Err()
}

// FindTeamInvitation returns a team invitation by ID.
func (store *InvitationStore) FindTeamInvitation(ctx context.Context, invitationID string) (*domain.TeamInvitation, error) {
	invitation := &domain.TeamInvitation{}
	err := store.db.QueryRowContext(ctx, `
		SELECT id, team_id, invitee_user_id, invited_by, status, created_at
		FROM team_invitations
		WHERE id = $1`, invitationID,
	).Scan(
		&invitation.ID, &invitation.TeamID, &invitation.InviteeUserID,
		&invitation.InvitedBy, &invitation.Status, &invitation.CreatedAt,
	)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, ErrNotFound
	}
	return invitation, err
}

// DeleteTeamInvitation deletes a team invitation.
func (store *InvitationStore) DeleteTeamInvitation(ctx context.Context, tx *sql.Tx, invitationID string) error {
	result, err := tx.ExecContext(ctx, `DELETE FROM team_invitations WHERE id = $1`, invitationID)
	if err != nil {
		return err
	}
	rowsAffected, err := result.RowsAffected()
	if err != nil {
		return err
	}
	if rowsAffected == 0 {
		return ErrNotFound
	}
	return nil
}

// AcceptTeamInvitation updates a team invitation status to 'accepted' and returns it.
func (store *InvitationStore) AcceptTeamInvitation(ctx context.Context, tx *sql.Tx, invitationID string) (*domain.TeamInvitation, error) {
	invitation := &domain.TeamInvitation{}
	err := tx.QueryRowContext(ctx, `
		UPDATE team_invitations SET status = 'accepted'
		WHERE id = $1 AND status = 'pending'
		RETURNING id, team_id, invitee_user_id, invited_by, status, created_at`, invitationID,
	).Scan(
		&invitation.ID, &invitation.TeamID, &invitation.InviteeUserID,
		&invitation.InvitedBy, &invitation.Status, &invitation.CreatedAt,
	)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, ErrNotFound
	}
	return invitation, err
}

// DeclineTeamInvitation updates a team invitation status to 'declined'.
func (store *InvitationStore) DeclineTeamInvitation(ctx context.Context, tx *sql.Tx, invitationID string) error {
	result, err := tx.ExecContext(ctx, `
		UPDATE team_invitations SET status = 'declined'
		WHERE id = $1 AND status = 'pending'`, invitationID)
	if err != nil {
		return err
	}
	rowsAffected, err := result.RowsAffected()
	if err != nil {
		return err
	}
	if rowsAffected == 0 {
		return ErrNotFound
	}
	return nil
}

// IsTeamAdmin checks if a user is an admin of the given team.
func (store *InvitationStore) IsTeamAdmin(ctx context.Context, teamID, userID string) (bool, error) {
	var isAdmin bool
	err := store.db.QueryRowContext(ctx, `
		SELECT EXISTS(
			SELECT 1 FROM team_members
			WHERE team_id = $1 AND user_id = $2 AND role = 'admin'
		)`, teamID, userID).Scan(&isAdmin)
	return isAdmin, err
}
