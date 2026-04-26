package domain

import "time"

// Event represents a domain event stored in the events table.
type Event struct {
	ID             string
	Type           string
	ActorID        *string
	TaskID         *string
	ProjectID      *string
	TeamID         *string
	AutomationID   *string
	TargetUserID   *string
	Payload        []byte
	CreatedAt      time.Time
}

// EventListParams holds parameters for listing events.
type EventListParams struct {
	UserID    string
	Filter    string
	ProjectID string // pre-filter for /projects/:id/events
	TaskID    string // pre-filter for /tasks/:id/events
	Cursor    string
	Limit     int
}

// EventListResult holds a page of events.
type EventListResult struct {
	Data   []Event `json:"data"`
	Cursor *string `json:"cursor"`
}
