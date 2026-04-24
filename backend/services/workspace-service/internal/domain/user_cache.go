package domain

import "time"

type UserCache struct {
	UserID    string    `json:"user_id"`
	Email     string    `json:"email"`
	Name      string    `json:"name"`
	IsActive  bool      `json:"is_active"`
	UpdatedAt time.Time `json:"updated_at"`
}
