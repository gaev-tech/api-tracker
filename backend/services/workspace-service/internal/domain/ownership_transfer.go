package domain

import "time"

type ProjectOwnershipTransfer struct {
	ID         string    `json:"id"`
	ProjectID  string    `json:"project_id"`
	FromUserID string    `json:"from_user_id"`
	ToUserID   string    `json:"to_user_id"`
	Status     string    `json:"status"`
	CreatedAt  time.Time `json:"created_at"`
}

type TeamOwnershipTransfer struct {
	ID         string    `json:"id"`
	TeamID     string    `json:"team_id"`
	FromUserID string    `json:"from_user_id"`
	ToUserID   string    `json:"to_user_id"`
	Status     string    `json:"status"`
	CreatedAt  time.Time `json:"created_at"`
}
