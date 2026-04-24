package store

import (
	"context"
	"database/sql"
	"errors"

	"github.com/gaev-tech/api-tracker/billing-service/internal/domain"
)

type UsageStore struct {
	db *sql.DB
}

func NewUsageStore(db *sql.DB) *UsageStore {
	return &UsageStore{db: db}
}

// GetCount returns the current count for a user and entity type. Returns 0 if no record exists.
func (s *UsageStore) GetCount(ctx context.Context, userID, entityType string) (int, error) {
	var count int
	err := s.db.QueryRowContext(ctx, `
		SELECT current_count FROM usage_counters
		WHERE user_id = $1 AND entity_type = $2`,
		userID, entityType,
	).Scan(&count)
	if errors.Is(err, sql.ErrNoRows) {
		return 0, nil
	}
	return count, err
}

// Increment adds delta to the counter, creating the record if it doesn't exist (upsert).
func (s *UsageStore) Increment(ctx context.Context, userID, entityType string, delta int) (int, error) {
	var count int
	err := s.db.QueryRowContext(ctx, `
		INSERT INTO usage_counters (user_id, entity_type, current_count, updated_at)
		VALUES ($1, $2, $3, now())
		ON CONFLICT (user_id, entity_type)
		DO UPDATE SET current_count = usage_counters.current_count + $3, updated_at = now()
		RETURNING current_count`,
		userID, entityType, delta,
	).Scan(&count)
	return count, err
}

// Decrement subtracts delta from the counter. Never goes below 0.
func (s *UsageStore) Decrement(ctx context.Context, userID, entityType string, delta int) (int, error) {
	var count int
	err := s.db.QueryRowContext(ctx, `
		UPDATE usage_counters
		SET current_count = GREATEST(current_count - $3, 0), updated_at = now()
		WHERE user_id = $1 AND entity_type = $2
		RETURNING current_count`,
		userID, entityType, delta,
	).Scan(&count)
	if errors.Is(err, sql.ErrNoRows) {
		return 0, nil
	}
	return count, err
}

// FindByUserID returns all usage counters for a user.
func (s *UsageStore) FindByUserID(ctx context.Context, userID string) ([]*domain.UsageCounter, error) {
	rows, err := s.db.QueryContext(ctx, `
		SELECT id, user_id, entity_type, current_count, updated_at
		FROM usage_counters
		WHERE user_id = $1
		ORDER BY entity_type`,
		userID,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var counters []*domain.UsageCounter
	for rows.Next() {
		c := &domain.UsageCounter{}
		if err := rows.Scan(&c.ID, &c.UserID, &c.EntityType, &c.CurrentCount, &c.UpdatedAt); err != nil {
			return nil, err
		}
		counters = append(counters, c)
	}
	return counters, rows.Err()
}
