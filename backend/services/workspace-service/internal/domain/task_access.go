package domain

import "time"

type TaskPermissions struct {
	EditTitle       bool `json:"edit_title"`
	EditDescription bool `json:"edit_description"`
	EditTags        bool `json:"edit_tags"`
	EditBlockers    bool `json:"edit_blockers"`
	EditAssignee    bool `json:"edit_assignee"`
	EditStatus      bool `json:"edit_status"`
	Share           bool `json:"share"`
	DeleteTask          bool `json:"delete_task"`
}

// HasAny returns true if at least one permission is set.
func (p TaskPermissions) HasAny() bool {
	return p.EditTitle || p.EditDescription || p.EditTags || p.EditBlockers ||
		p.EditAssignee || p.EditStatus || p.Share || p.DeleteTask
}

type TaskDirectAccess struct {
	ID             string          `json:"id"`
	TaskID         string          `json:"task_id"`
	GranteeUserID  *string         `json:"grantee_user_id"`
	GranteeTeamID  *string         `json:"grantee_team_id"`
	GrantedBy      string          `json:"granted_by"`
	Permissions    TaskPermissions `json:"permissions"`
	CreatedAt      time.Time       `json:"created_at"`
	UpdatedAt      time.Time       `json:"updated_at"`
}

type CreateTaskAccessRequest struct {
	GranteeUserID *string         `json:"grantee_user_id"`
	GranteeTeamID *string         `json:"grantee_team_id"`
	Permissions   TaskPermissions `json:"permissions"`
}

type UpdateTaskAccessRequest struct {
	Permissions TaskPermissions `json:"permissions"`
}
