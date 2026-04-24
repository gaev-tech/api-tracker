package domain

import "time"

type UsageCounter struct {
	ID           string    `json:"id"`
	UserID       string    `json:"user_id"`
	EntityType   string    `json:"entity_type"`
	CurrentCount int       `json:"current_count"`
	UpdatedAt    time.Time `json:"updated_at"`
}
