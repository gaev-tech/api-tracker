package domain

import "time"

type Task struct {
	ID                string    `json:"id"`
	Title             string    `json:"title"`
	Description       string    `json:"description"`
	Status            string    `json:"status"`
	AuthorID          string    `json:"author_id"`
	AssigneeID        *string   `json:"assignee_id"`
	Tags              []string  `json:"tags"`
	ProjectIDs        []string  `json:"project_ids"`
	BlockingTaskIDs   []string  `json:"blocking_task_ids"`
	BlockedTaskIDs    []string  `json:"blocked_task_ids"`
	IsFrozenByTariff  bool      `json:"is_frozen_by_tariff"`
	CreatedAt         time.Time `json:"created_at"`
	UpdatedAt         time.Time `json:"updated_at"`
}

type CreateTaskRequest struct {
	Title           string   `json:"title"`
	Description     string   `json:"description"`
	Status          string   `json:"status"`
	AssigneeID      *string  `json:"assignee_id"`
	Tags            []string `json:"tags"`
	ProjectIDs      []string `json:"project_ids"`
	BlockingTaskIDs []string `json:"blocking_task_ids"`
}

type UpdateTaskRequest struct {
	Title           *string  `json:"title"`
	Description     *string  `json:"description"`
	Status          *string  `json:"status"`
	AssigneeID      **string `json:"assignee_id"` // double pointer: nil=not sent, *nil=set to null, *val=set to val
	Tags            *[]string `json:"tags"`
	BlockingTaskIDs *[]string `json:"blocking_task_ids"`
}

const (
	StatusOpened   = "opened"
	StatusProgress = "progress"
	StatusClosed   = "closed"
)

var ValidStatuses = map[string]bool{
	StatusOpened:   true,
	StatusProgress: true,
	StatusClosed:   true,
}

type TaskListParams struct {
	AuthorID  string // deprecated: use UserID with ListVisible
	UserID    string // for visibility-based listing
	Filter    string
	Cursor    string
	Limit     int
	SortField string
	SortDir   string
}

type TaskListResult struct {
	Items      []*Task `json:"items"`
	NextCursor *string `json:"next_cursor"`
	Total      int     `json:"total"`
}
