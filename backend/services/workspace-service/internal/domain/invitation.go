package domain

import "time"

type ProjectInvitation struct {
	ID            string             `json:"id"`
	ProjectID     string             `json:"project_id"`
	InviteeUserID *string            `json:"invitee_user_id"`
	InviteeTeamID *string            `json:"invitee_team_id"`
	InvitedBy     string             `json:"invited_by"`
	Permissions   ProjectPermissions `json:"permissions"`
	Status        string             `json:"status"`
	CreatedAt     time.Time          `json:"created_at"`
}

type TeamInvitation struct {
	ID            string    `json:"id"`
	TeamID        string    `json:"team_id"`
	InviteeUserID string    `json:"invitee_user_id"`
	InvitedBy     string    `json:"invited_by"`
	Status        string    `json:"status"`
	CreatedAt     time.Time `json:"created_at"`
}
