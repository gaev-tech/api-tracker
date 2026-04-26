package store

import (
	"context"
	"database/sql"
	"encoding/base64"
	"fmt"
	"strings"
	"sync"
	"time"

	"github.com/gaev-tech/api-tracker/backend/pkg/rsql"
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

var allowedFields = map[string]string{
	"type":           "type",
	"actor_id":       "actor_id",
	"task_id":        "task_id",
	"project_id":     "project_id",
	"team_id":        "team_id",
	"automation_id":  "automation_id",
	"target_user_id": "target_user_id",
	"created_at":     "created_at",
}

// List returns a page of events matching the given parameters.
func (s *EventStore) List(ctx context.Context, params *domain.EventListParams) (*domain.EventListResult, error) {
	var conditions []string
	var args []any

	// RSQL filter
	if params.Filter != "" {
		node, err := rsql.Parse(params.Filter)
		if err != nil {
			return nil, fmt.Errorf("invalid filter: %w", err)
		}
		where, filterArgs, err := rsql.ToSQL(node, allowedFields)
		if err != nil {
			return nil, fmt.Errorf("invalid filter: %w", err)
		}
		conditions = append(conditions, where)
		args = append(args, filterArgs...)
	}

	// Pre-filters
	if params.ProjectID != "" {
		args = append(args, params.ProjectID)
		conditions = append(conditions, fmt.Sprintf("project_id = $%d", len(args)))
	}
	if params.TaskID != "" {
		args = append(args, params.TaskID)
		conditions = append(conditions, fmt.Sprintf("task_id = $%d", len(args)))
	}

	// Cursor pagination
	if params.Cursor != "" {
		decoded, err := base64.StdEncoding.DecodeString(params.Cursor)
		if err != nil {
			return nil, fmt.Errorf("invalid filter: invalid cursor")
		}
		cursorTime, err := time.Parse(time.RFC3339Nano, string(decoded))
		if err != nil {
			return nil, fmt.Errorf("invalid filter: invalid cursor")
		}
		args = append(args, cursorTime)
		conditions = append(conditions, fmt.Sprintf("created_at < $%d", len(args)))
	}

	query := "SELECT id, type, actor_id, task_id, project_id, team_id, automation_id, target_user_id, payload, created_at FROM events"
	if len(conditions) > 0 {
		query += " WHERE " + strings.Join(conditions, " AND ")
	}
	query += " ORDER BY created_at DESC"
	args = append(args, params.Limit+1)
	query += fmt.Sprintf(" LIMIT $%d", len(args))

	rows, err := s.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var events []domain.Event
	for rows.Next() {
		var e domain.Event
		if err := rows.Scan(&e.ID, &e.Type, &e.ActorID, &e.TaskID, &e.ProjectID, &e.TeamID, &e.AutomationID, &e.TargetUserID, &e.Payload, &e.CreatedAt); err != nil {
			return nil, err
		}
		events = append(events, e)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}

	result := &domain.EventListResult{}
	if len(events) > params.Limit {
		events = events[:params.Limit]
		cursorVal := base64.StdEncoding.EncodeToString([]byte(events[params.Limit-1].CreatedAt.Format(time.RFC3339Nano)))
		result.Cursor = &cursorVal
	}
	result.Data = events
	if result.Data == nil {
		result.Data = []domain.Event{}
	}

	return result, nil
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
