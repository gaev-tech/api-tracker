package domain

import "time"

type Team struct {
	ID          string    `json:"id"`
	Name        string    `json:"name"`
	Description string    `json:"description"`
	OwnerID     string    `json:"owner_id"`
	CreatedAt   time.Time `json:"created_at"`
	UpdatedAt   time.Time `json:"updated_at"`
}

type CreateTeamRequest struct {
	Name        string `json:"name"`
	Description string `json:"description"`
}

type UpdateTeamRequest struct {
	Name        *string `json:"name"`
	Description *string `json:"description"`
}

type TeamListParams struct {
	OwnerID string
	Cursor  string
	Limit   int
}

type TeamListResult struct {
	Items      []*Team `json:"items"`
	NextCursor *string `json:"next_cursor"`
	Total      int     `json:"total"`
}
