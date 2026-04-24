package domain

import "time"

type Project struct {
	ID          string    `json:"id"`
	Name        string    `json:"name"`
	Description string    `json:"description"`
	OwnerID     string    `json:"owner_id"`
	CreatedAt   time.Time `json:"created_at"`
	UpdatedAt   time.Time `json:"updated_at"`
}

type CreateProjectRequest struct {
	Name        string `json:"name"`
	Description string `json:"description"`
}

type UpdateProjectRequest struct {
	Name        *string `json:"name"`
	Description *string `json:"description"`
}

type ProjectListParams struct {
	OwnerID string
	Cursor  string
	Limit   int
}

type ProjectListResult struct {
	Items      []*Project `json:"items"`
	NextCursor *string    `json:"next_cursor"`
	Total      int        `json:"total"`
}
