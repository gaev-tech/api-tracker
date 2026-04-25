package domain

import "time"

type TeamMember struct {
	TeamID   string    `json:"team_id"`
	UserID   string    `json:"user_id"`
	Email    string    `json:"email"`
	Name     string    `json:"name"`
	Role     string    `json:"role"`
	JoinedAt time.Time `json:"joined_at"`
}

const (
	TeamRoleAdmin  = "admin"
	TeamRoleMember = "member"
)

var ValidTeamRoles = map[string]bool{
	TeamRoleAdmin:  true,
	TeamRoleMember: true,
}
