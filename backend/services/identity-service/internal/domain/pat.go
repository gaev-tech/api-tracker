package domain

import "time"

type PAT struct {
	ID        string     `json:"id"`
	Name      string     `json:"name"`
	Token     *string    `json:"token"`
	CreatedAt time.Time  `json:"created_at"`
	RevokedAt *time.Time `json:"revoked_at"`
}
