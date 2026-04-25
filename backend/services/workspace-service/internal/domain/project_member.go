package domain

import "time"

type ProjectPermissions struct {
	EditTitle          bool `json:"edit_title"`
	EditDescription    bool `json:"edit_description"`
	EditTags           bool `json:"edit_tags"`
	EditBlockers       bool `json:"edit_blockers"`
	EditAssignee       bool `json:"edit_assignee"`
	EditStatus         bool `json:"edit_status"`
	Share              bool `json:"share"`
	DeleteTask             bool `json:"delete_task"`
	RenameProject      bool `json:"rename_project"`
	ManageMembers     bool `json:"manage_members"`
	ManageAutomations bool `json:"manage_automations"`
	ManageAttachments bool `json:"manage_attachments"`
	DeleteProject     bool `json:"delete_project"`
	ImportTasks            bool `json:"import_tasks"`
}

// FullProjectPermissions returns permissions with all 14 rights set to true.
func FullProjectPermissions() ProjectPermissions {
	return ProjectPermissions{
		EditTitle: true, EditDescription: true, EditTags: true,
		EditBlockers: true, EditAssignee: true, EditStatus: true,
		Share: true, DeleteTask: true, RenameProject: true,
		ManageMembers: true, ManageAutomations: true,
		ManageAttachments: true, DeleteProject: true, ImportTasks: true,
	}
}

type ProjectMember struct {
	UserID            string             `json:"user_id"`
	Email             string             `json:"email"`
	Name              string             `json:"name"`
	Permissions       ProjectPermissions `json:"permissions"`
	IsFrozenByTariff  bool               `json:"is_frozen_by_tariff"`
	JoinedAt          time.Time          `json:"joined_at"`
}

type ProjectTeamMember struct {
	TeamID             string             `json:"team_id"`
	TeamName           string             `json:"team_name"`
	Permissions        ProjectPermissions `json:"permissions"`
	IsFrozenInProject  bool               `json:"is_frozen_in_project"`
	JoinedAt           time.Time          `json:"joined_at"`
}
