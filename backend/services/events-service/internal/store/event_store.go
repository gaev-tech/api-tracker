package store

import (
	"context"
	"database/sql"
	"sync"

	"github.com/gaev-tech/api-tracker/events-service/internal/domain"
)

// EventStore handles persistence of events.
type EventStore struct {
	db               *sql.DB
	knownPartitions  map[string]struct{}
	mu               sync.Mutex
}

// NewEventStore creates a new EventStore.
func NewEventStore(db *sql.DB) *EventStore {
	return &EventStore{
		db:              db,
		knownPartitions: make(map[string]struct{}),
	}
}

// Insert stores an event, creating the monthly partition if needed.
func (s *EventStore) Insert(ctx context.Context, e *domain.Event) error {
	if err := s.ensurePartition(ctx, e.CreatedAt.Format("2006_01")); err != nil {
		return err
	}

	_, err := s.db.ExecContext(ctx, `
		INSERT INTO events (type, actor_id, task_id, project_id, team_id, automation_id, target_user_id, payload, created_at)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)`,
		e.Type, e.ActorID, e.TaskID, e.ProjectID, e.TeamID, e.AutomationID, e.TargetUserID, e.Payload, e.CreatedAt,
	)
	return err
}

func (s *EventStore) ensurePartition(ctx context.Context, monthKey string) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	if _, ok := s.knownPartitions[monthKey]; ok {
		return nil
	}

	_, err := s.db.ExecContext(ctx, "SELECT ensure_events_partition($1::timestamptz)",
		monthKey[:4]+"-"+monthKey[5:]+"-01")
	if err != nil {
		return err
	}
	s.knownPartitions[monthKey] = struct{}{}
	return nil
}
