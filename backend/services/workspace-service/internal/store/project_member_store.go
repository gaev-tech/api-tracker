package store

import (
	"context"
	"database/sql"
	"errors"

	"github.com/gaev-tech/api-tracker/workspace-service/internal/domain"
)

type ProjectMemberStore struct {
	db *sql.DB
}

func NewProjectMemberStore(db *sql.DB) *ProjectMemberStore {
	return &ProjectMemberStore{db: db}
}

const permissionColumns = `edit_title, edit_description, edit_tags, edit_blockers,
	edit_assignee, edit_status, share, delete_task,
	rename_project, manage_members, manage_automations,
	manage_attachments, delete_project, import_tasks`

func scanPermissions(row interface{ Scan(dest ...any) error }, p *domain.ProjectPermissions) error {
	return row.Scan(
		&p.EditTitle, &p.EditDescription, &p.EditTags, &p.EditBlockers,
		&p.EditAssignee, &p.EditStatus, &p.Share, &p.DeleteTask,
		&p.RenameProject, &p.ManageMembers, &p.ManageAutomations,
		&p.ManageAttachments, &p.DeleteProject, &p.ImportTasks,
	)
}

// AddMember inserts a user member into a project.
func (store *ProjectMemberStore) AddMember(ctx context.Context, tx *sql.Tx, projectID, userID string, p domain.ProjectPermissions) error {
	_, err := tx.ExecContext(ctx, `
		INSERT INTO project_members (project_id, user_id,
			edit_title, edit_description, edit_tags, edit_blockers,
			edit_assignee, edit_status, share, delete_task,
			rename_project, manage_members, manage_automations,
			manage_attachments, delete_project, import_tasks)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)`,
		projectID, userID,
		p.EditTitle, p.EditDescription, p.EditTags, p.EditBlockers,
		p.EditAssignee, p.EditStatus, p.Share, p.DeleteTask,
		p.RenameProject, p.ManageMembers, p.ManageAutomations,
		p.ManageAttachments, p.DeleteProject, p.ImportTasks,
	)
	if isPgUniqueViolation(err) {
		return ErrConflict
	}
	return err
}

// ListMembers returns all user members of a project with email/name from users_cache.
func (store *ProjectMemberStore) ListMembers(ctx context.Context, projectID string) ([]*domain.ProjectMember, error) {
	rows, err := store.db.QueryContext(ctx, `
		SELECT pm.user_id, COALESCE(uc.email, ''), COALESCE(uc.name, ''),
			pm.edit_title, pm.edit_description, pm.edit_tags, pm.edit_blockers,
			pm.edit_assignee, pm.edit_status, pm.share, pm.delete_task,
			pm.rename_project, pm.manage_members, pm.manage_automations,
			pm.manage_attachments, pm.delete_project, pm.import_tasks,
			pm.is_frozen_by_tariff, pm.joined_at
		FROM project_members pm
		LEFT JOIN users_cache uc ON uc.user_id = pm.user_id
		WHERE pm.project_id = $1
		ORDER BY pm.joined_at`, projectID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var members []*domain.ProjectMember
	for rows.Next() {
		member := &domain.ProjectMember{}
		if err := rows.Scan(
			&member.UserID, &member.Email, &member.Name,
			&member.Permissions.EditTitle, &member.Permissions.EditDescription,
			&member.Permissions.EditTags, &member.Permissions.EditBlockers,
			&member.Permissions.EditAssignee, &member.Permissions.EditStatus,
			&member.Permissions.Share, &member.Permissions.DeleteTask,
			&member.Permissions.RenameProject, &member.Permissions.ManageMembers,
			&member.Permissions.ManageAutomations, &member.Permissions.ManageAttachments,
			&member.Permissions.DeleteProject, &member.Permissions.ImportTasks,
			&member.IsFrozenByTariff, &member.JoinedAt,
		); err != nil {
			return nil, err
		}
		members = append(members, member)
	}
	return members, rows.Err()
}

// FindMember returns a single project member.
func (store *ProjectMemberStore) FindMember(ctx context.Context, projectID, userID string) (*domain.ProjectMember, error) {
	member := &domain.ProjectMember{}
	err := store.db.QueryRowContext(ctx, `
		SELECT pm.user_id, COALESCE(uc.email, ''), COALESCE(uc.name, ''),
			pm.edit_title, pm.edit_description, pm.edit_tags, pm.edit_blockers,
			pm.edit_assignee, pm.edit_status, pm.share, pm.delete_task,
			pm.rename_project, pm.manage_members, pm.manage_automations,
			pm.manage_attachments, pm.delete_project, pm.import_tasks,
			pm.is_frozen_by_tariff, pm.joined_at
		FROM project_members pm
		LEFT JOIN users_cache uc ON uc.user_id = pm.user_id
		WHERE pm.project_id = $1 AND pm.user_id = $2`, projectID, userID,
	).Scan(
		&member.UserID, &member.Email, &member.Name,
		&member.Permissions.EditTitle, &member.Permissions.EditDescription,
		&member.Permissions.EditTags, &member.Permissions.EditBlockers,
		&member.Permissions.EditAssignee, &member.Permissions.EditStatus,
		&member.Permissions.Share, &member.Permissions.DeleteTask,
		&member.Permissions.RenameProject, &member.Permissions.ManageMembers,
		&member.Permissions.ManageAutomations, &member.Permissions.ManageAttachments,
		&member.Permissions.DeleteProject, &member.Permissions.ImportTasks,
		&member.IsFrozenByTariff, &member.JoinedAt,
	)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, ErrNotFound
	}
	return member, err
}

// UpdateMember updates permissions for a user member.
func (store *ProjectMemberStore) UpdateMember(ctx context.Context, tx *sql.Tx, projectID, userID string, p domain.ProjectPermissions) (*domain.ProjectMember, error) {
	member := &domain.ProjectMember{}
	err := tx.QueryRowContext(ctx, `
		UPDATE project_members SET
			edit_title = $3, edit_description = $4, edit_tags = $5, edit_blockers = $6,
			edit_assignee = $7, edit_status = $8, share = $9, delete_task = $10,
			rename_project = $11, manage_members = $12, manage_automations = $13,
			manage_attachments = $14, delete_project = $15, import_tasks = $16
		WHERE project_id = $1 AND user_id = $2
		RETURNING user_id, edit_title, edit_description, edit_tags, edit_blockers,
			edit_assignee, edit_status, share, delete_task,
			rename_project, manage_members, manage_automations,
			manage_attachments, delete_project, import_tasks,
			is_frozen_by_tariff, joined_at`,
		projectID, userID,
		p.EditTitle, p.EditDescription, p.EditTags, p.EditBlockers,
		p.EditAssignee, p.EditStatus, p.Share, p.DeleteTask,
		p.RenameProject, p.ManageMembers, p.ManageAutomations,
		p.ManageAttachments, p.DeleteProject, p.ImportTasks,
	).Scan(
		&member.UserID,
		&member.Permissions.EditTitle, &member.Permissions.EditDescription,
		&member.Permissions.EditTags, &member.Permissions.EditBlockers,
		&member.Permissions.EditAssignee, &member.Permissions.EditStatus,
		&member.Permissions.Share, &member.Permissions.DeleteTask,
		&member.Permissions.RenameProject, &member.Permissions.ManageMembers,
		&member.Permissions.ManageAutomations, &member.Permissions.ManageAttachments,
		&member.Permissions.DeleteProject, &member.Permissions.ImportTasks,
		&member.IsFrozenByTariff, &member.JoinedAt,
	)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, ErrNotFound
	}
	return member, err
}

// RemoveMember removes a user member from a project.
func (store *ProjectMemberStore) RemoveMember(ctx context.Context, tx *sql.Tx, projectID, userID string) error {
	res, err := tx.ExecContext(ctx, `DELETE FROM project_members WHERE project_id = $1 AND user_id = $2`, projectID, userID)
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

// AddTeamMember inserts a team member into a project.
func (store *ProjectMemberStore) AddTeamMember(ctx context.Context, tx *sql.Tx, projectID, teamID string, p domain.ProjectPermissions) error {
	_, err := tx.ExecContext(ctx, `
		INSERT INTO project_team_members (project_id, team_id,
			edit_title, edit_description, edit_tags, edit_blockers,
			edit_assignee, edit_status, share, delete_task,
			rename_project, manage_members, manage_automations,
			manage_attachments, delete_project, import_tasks)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)`,
		projectID, teamID,
		p.EditTitle, p.EditDescription, p.EditTags, p.EditBlockers,
		p.EditAssignee, p.EditStatus, p.Share, p.DeleteTask,
		p.RenameProject, p.ManageMembers, p.ManageAutomations,
		p.ManageAttachments, p.DeleteProject, p.ImportTasks,
	)
	if isPgUniqueViolation(err) {
		return ErrConflict
	}
	return err
}

// ListTeamMembers returns all team members of a project with team name.
func (store *ProjectMemberStore) ListTeamMembers(ctx context.Context, projectID string) ([]*domain.ProjectTeamMember, error) {
	rows, err := store.db.QueryContext(ctx, `
		SELECT ptm.team_id, COALESCE(t.name, ''),
			ptm.edit_title, ptm.edit_description, ptm.edit_tags, ptm.edit_blockers,
			ptm.edit_assignee, ptm.edit_status, ptm.share, ptm.delete_task,
			ptm.rename_project, ptm.manage_members, ptm.manage_automations,
			ptm.manage_attachments, ptm.delete_project, ptm.import_tasks,
			ptm.is_frozen_in_project, ptm.joined_at
		FROM project_team_members ptm
		LEFT JOIN teams t ON t.id = ptm.team_id
		WHERE ptm.project_id = $1
		ORDER BY ptm.joined_at`, projectID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var members []*domain.ProjectTeamMember
	for rows.Next() {
		teamMember := &domain.ProjectTeamMember{}
		if err := rows.Scan(
			&teamMember.TeamID, &teamMember.TeamName,
			&teamMember.Permissions.EditTitle, &teamMember.Permissions.EditDescription,
			&teamMember.Permissions.EditTags, &teamMember.Permissions.EditBlockers,
			&teamMember.Permissions.EditAssignee, &teamMember.Permissions.EditStatus,
			&teamMember.Permissions.Share, &teamMember.Permissions.DeleteTask,
			&teamMember.Permissions.RenameProject, &teamMember.Permissions.ManageMembers,
			&teamMember.Permissions.ManageAutomations, &teamMember.Permissions.ManageAttachments,
			&teamMember.Permissions.DeleteProject, &teamMember.Permissions.ImportTasks,
			&teamMember.IsFrozenInProject, &teamMember.JoinedAt,
		); err != nil {
			return nil, err
		}
		members = append(members, teamMember)
	}
	return members, rows.Err()
}

// UpdateTeamMember updates permissions for a team member.
func (store *ProjectMemberStore) UpdateTeamMember(ctx context.Context, tx *sql.Tx, projectID, teamID string, p domain.ProjectPermissions) (*domain.ProjectTeamMember, error) {
	teamMember := &domain.ProjectTeamMember{}
	err := tx.QueryRowContext(ctx, `
		UPDATE project_team_members SET
			edit_title = $3, edit_description = $4, edit_tags = $5, edit_blockers = $6,
			edit_assignee = $7, edit_status = $8, share = $9, delete_task = $10,
			rename_project = $11, manage_members = $12, manage_automations = $13,
			manage_attachments = $14, delete_project = $15, import_tasks = $16
		WHERE project_id = $1 AND team_id = $2
		RETURNING team_id, edit_title, edit_description, edit_tags, edit_blockers,
			edit_assignee, edit_status, share, delete_task,
			rename_project, manage_members, manage_automations,
			manage_attachments, delete_project, import_tasks,
			is_frozen_in_project, joined_at`,
		projectID, teamID,
		p.EditTitle, p.EditDescription, p.EditTags, p.EditBlockers,
		p.EditAssignee, p.EditStatus, p.Share, p.DeleteTask,
		p.RenameProject, p.ManageMembers, p.ManageAutomations,
		p.ManageAttachments, p.DeleteProject, p.ImportTasks,
	).Scan(
		&teamMember.TeamID,
		&teamMember.Permissions.EditTitle, &teamMember.Permissions.EditDescription,
		&teamMember.Permissions.EditTags, &teamMember.Permissions.EditBlockers,
		&teamMember.Permissions.EditAssignee, &teamMember.Permissions.EditStatus,
		&teamMember.Permissions.Share, &teamMember.Permissions.DeleteTask,
		&teamMember.Permissions.RenameProject, &teamMember.Permissions.ManageMembers,
		&teamMember.Permissions.ManageAutomations, &teamMember.Permissions.ManageAttachments,
		&teamMember.Permissions.DeleteProject, &teamMember.Permissions.ImportTasks,
		&teamMember.IsFrozenInProject, &teamMember.JoinedAt,
	)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, ErrNotFound
	}
	return teamMember, err
}

// RemoveTeamMember removes a team member from a project.
func (store *ProjectMemberStore) RemoveTeamMember(ctx context.Context, tx *sql.Tx, projectID, teamID string) error {
	res, err := tx.ExecContext(ctx, `DELETE FROM project_team_members WHERE project_id = $1 AND team_id = $2`, projectID, teamID)
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
