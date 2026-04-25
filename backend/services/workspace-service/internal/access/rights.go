package access

import (
	"context"
	"database/sql"

	"github.com/gaev-tech/api-tracker/workspace-service/internal/domain"
)

// RightsService computes effective rights by unioning all access sources.
type RightsService struct {
	db *sql.DB
}

func NewRightsService(db *sql.DB) *RightsService {
	return &RightsService{db: db}
}

// GetTaskRights computes the effective task permissions for a user on a task.
// Union of 4 sources:
//  1. Direct task access to user
//  2. Project membership of user (via task_projects)
//  3. Project team membership (user is in team that is project member)
//  4. Direct task access to team that user is in
func (service *RightsService) GetTaskRights(ctx context.Context, taskID, userID string) (*domain.TaskPermissions, error) {
	permissions := &domain.TaskPermissions{}
	err := service.db.QueryRowContext(ctx, `
		SELECT
			COALESCE(bool_or(edit_title), false),
			COALESCE(bool_or(edit_description), false),
			COALESCE(bool_or(edit_tags), false),
			COALESCE(bool_or(edit_blockers), false),
			COALESCE(bool_or(edit_assignee), false),
			COALESCE(bool_or(edit_status), false),
			COALESCE(bool_or(share), false),
			COALESCE(bool_or(delete_task), false)
		FROM (
			SELECT edit_title, edit_description, edit_tags, edit_blockers,
				edit_assignee, edit_status, share, delete_task
			FROM task_direct_accesses
			WHERE task_id = $1 AND grantee_user_id = $2

			UNION ALL

			SELECT pm.edit_title, pm.edit_description, pm.edit_tags, pm.edit_blockers,
				pm.edit_assignee, pm.edit_status, pm.share, pm.delete_task
			FROM project_members pm
			JOIN task_projects tp ON tp.project_id = pm.project_id
			WHERE tp.task_id = $1 AND pm.user_id = $2

			UNION ALL

			SELECT ptm.edit_title, ptm.edit_description, ptm.edit_tags, ptm.edit_blockers,
				ptm.edit_assignee, ptm.edit_status, ptm.share, ptm.delete_task
			FROM project_team_members ptm
			JOIN team_members tm ON ptm.team_id = tm.team_id
			JOIN task_projects tp ON tp.project_id = ptm.project_id
			WHERE tp.task_id = $1 AND tm.user_id = $2

			UNION ALL

			SELECT tda.edit_title, tda.edit_description, tda.edit_tags, tda.edit_blockers,
				tda.edit_assignee, tda.edit_status, tda.share, tda.delete_task
			FROM task_direct_accesses tda
			JOIN team_members tm ON tda.grantee_team_id = tm.team_id
			WHERE tda.task_id = $1 AND tm.user_id = $2
		) all_rights`,
		taskID, userID,
	).Scan(
		&permissions.EditTitle, &permissions.EditDescription,
		&permissions.EditTags, &permissions.EditBlockers,
		&permissions.EditAssignee, &permissions.EditStatus,
		&permissions.Share, &permissions.DeleteTask,
	)
	return permissions, err
}

// GetProjectRights computes the effective project permissions for a user.
// Union of 2 sources:
//  1. Direct project membership
//  2. Project team membership (user is in team that is project member)
func (service *RightsService) GetProjectRights(ctx context.Context, projectID, userID string) (*domain.ProjectPermissions, error) {
	permissions := &domain.ProjectPermissions{}
	err := service.db.QueryRowContext(ctx, `
		SELECT
			COALESCE(bool_or(edit_title), false),
			COALESCE(bool_or(edit_description), false),
			COALESCE(bool_or(edit_tags), false),
			COALESCE(bool_or(edit_blockers), false),
			COALESCE(bool_or(edit_assignee), false),
			COALESCE(bool_or(edit_status), false),
			COALESCE(bool_or(share), false),
			COALESCE(bool_or(delete_task), false),
			COALESCE(bool_or(rename_project), false),
			COALESCE(bool_or(manage_members), false),
			COALESCE(bool_or(manage_automations), false),
			COALESCE(bool_or(manage_attachments), false),
			COALESCE(bool_or(delete_project), false),
			COALESCE(bool_or(import_tasks), false)
		FROM (
			SELECT edit_title, edit_description, edit_tags, edit_blockers,
				edit_assignee, edit_status, share, delete_task,
				rename_project, manage_members, manage_automations,
				manage_attachments, delete_project, import_tasks
			FROM project_members
			WHERE project_id = $1 AND user_id = $2

			UNION ALL

			SELECT ptm.edit_title, ptm.edit_description, ptm.edit_tags, ptm.edit_blockers,
				ptm.edit_assignee, ptm.edit_status, ptm.share, ptm.delete_task,
				ptm.rename_project, ptm.manage_members, ptm.manage_automations,
				ptm.manage_attachments, ptm.delete_project, ptm.import_tasks
			FROM project_team_members ptm
			JOIN team_members tm ON ptm.team_id = tm.team_id
			WHERE ptm.project_id = $1 AND tm.user_id = $2
		) all_rights`,
		projectID, userID,
	).Scan(
		&permissions.EditTitle, &permissions.EditDescription,
		&permissions.EditTags, &permissions.EditBlockers,
		&permissions.EditAssignee, &permissions.EditStatus,
		&permissions.Share, &permissions.DeleteTask,
		&permissions.RenameProject, &permissions.ManageMembers,
		&permissions.ManageAutomations, &permissions.ManageAttachments,
		&permissions.DeleteProject, &permissions.ImportTasks,
	)
	return permissions, err
}

// CanSeeTask checks if a user can see a task (has any access through any source, or is author).
func (service *RightsService) CanSeeTask(ctx context.Context, taskID, userID string) (bool, error) {
	var visible bool
	err := service.db.QueryRowContext(ctx, `
		SELECT EXISTS(
			SELECT 1 FROM tasks WHERE id = $1 AND author_id = $2
		) OR EXISTS(
			SELECT 1 FROM task_direct_accesses WHERE task_id = $1 AND grantee_user_id = $2
		) OR EXISTS(
			SELECT 1 FROM task_projects tp
			JOIN project_members pm ON tp.project_id = pm.project_id
			WHERE tp.task_id = $1 AND pm.user_id = $2
		) OR EXISTS(
			SELECT 1 FROM task_projects tp
			JOIN project_team_members ptm ON tp.project_id = ptm.project_id
			JOIN team_members tm ON ptm.team_id = tm.team_id
			WHERE tp.task_id = $1 AND tm.user_id = $2
		) OR EXISTS(
			SELECT 1 FROM task_direct_accesses tda
			JOIN team_members tm ON tda.grantee_team_id = tm.team_id
			WHERE tda.task_id = $1 AND tm.user_id = $2
		)`,
		taskID, userID,
	).Scan(&visible)
	return visible, err
}

// IsProjectMember checks if a user is a member of a project (directly or via team).
func (service *RightsService) IsProjectMember(ctx context.Context, projectID, userID string) (bool, error) {
	var isMember bool
	err := service.db.QueryRowContext(ctx, `
		SELECT EXISTS(
			SELECT 1 FROM project_members WHERE project_id = $1 AND user_id = $2
		) OR EXISTS(
			SELECT 1 FROM project_team_members ptm
			JOIN team_members tm ON ptm.team_id = tm.team_id
			WHERE ptm.project_id = $1 AND tm.user_id = $2
		)`,
		projectID, userID,
	).Scan(&isMember)
	return isMember, err
}

// TaskPermissionsContain checks that all granted rights are within the grantor's rights.
func TaskPermissionsContain(grantor, granted domain.TaskPermissions) bool {
	if granted.EditTitle && !grantor.EditTitle {
		return false
	}
	if granted.EditDescription && !grantor.EditDescription {
		return false
	}
	if granted.EditTags && !grantor.EditTags {
		return false
	}
	if granted.EditBlockers && !grantor.EditBlockers {
		return false
	}
	if granted.EditAssignee && !grantor.EditAssignee {
		return false
	}
	if granted.EditStatus && !grantor.EditStatus {
		return false
	}
	if granted.Share && !grantor.Share {
		return false
	}
	if granted.DeleteTask && !grantor.DeleteTask {
		return false
	}
	return true
}

// ProjectPermissionsContain checks that all granted rights are within the grantor's rights.
func ProjectPermissionsContain(grantor, granted domain.ProjectPermissions) bool {
	if granted.EditTitle && !grantor.EditTitle {
		return false
	}
	if granted.EditDescription && !grantor.EditDescription {
		return false
	}
	if granted.EditTags && !grantor.EditTags {
		return false
	}
	if granted.EditBlockers && !grantor.EditBlockers {
		return false
	}
	if granted.EditAssignee && !grantor.EditAssignee {
		return false
	}
	if granted.EditStatus && !grantor.EditStatus {
		return false
	}
	if granted.Share && !grantor.Share {
		return false
	}
	if granted.DeleteTask && !grantor.DeleteTask {
		return false
	}
	if granted.RenameProject && !grantor.RenameProject {
		return false
	}
	if granted.ManageMembers && !grantor.ManageMembers {
		return false
	}
	if granted.ManageAutomations && !grantor.ManageAutomations {
		return false
	}
	if granted.ManageAttachments && !grantor.ManageAttachments {
		return false
	}
	if granted.DeleteProject && !grantor.DeleteProject {
		return false
	}
	if granted.ImportTasks && !grantor.ImportTasks {
		return false
	}
	return true
}
