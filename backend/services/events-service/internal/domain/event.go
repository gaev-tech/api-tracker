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
