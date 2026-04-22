package outbox

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"log/slog"
	"strings"
	"time"

	"github.com/segmentio/kafka-go"
)

// Record represents a row in the outbox table.
type Record struct {
	ID      int64
	Topic   string
	Payload json.RawMessage
}

// Writer is the interface for publishing messages to Kafka.
type Writer interface {
	WriteMessages(ctx context.Context, msgs ...kafka.Message) error
}

// Relay polls an outbox table and publishes pending records to Kafka.
// The outbox table must have columns: id, topic, payload (JSONB), created_at, sent_at (nullable).
type Relay struct {
	db     *sql.DB
	writer Writer
	table  string
	logger *slog.Logger
}

// New creates a new Relay.
// table is the outbox table name (e.g. "identity_outbox").
func New(db *sql.DB, writer Writer, table string, logger *slog.Logger) *Relay {
	return &Relay{db: db, writer: writer, table: table, logger: logger}
}

// Start runs the relay loop until ctx is cancelled.
// It polls every second for unsent records, publishes them, and marks them sent.
func (r *Relay) Start(ctx context.Context) {
	ticker := time.NewTicker(time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			if err := r.flush(ctx); err != nil {
				r.logger.Error("outbox flush failed", "table", r.table, "error", err)
			}
		}
	}
}

func (r *Relay) flush(ctx context.Context) error {
	rows, err := r.db.QueryContext(ctx,
		"SELECT id, topic, payload FROM "+r.table+" WHERE sent_at IS NULL ORDER BY id LIMIT 100",
	)
	if err != nil {
		return err
	}
	defer rows.Close()

	var records []Record
	for rows.Next() {
		var rec Record
		if err := rows.Scan(&rec.ID, &rec.Topic, &rec.Payload); err != nil {
			return err
		}
		records = append(records, rec)
	}
	if err := rows.Err(); err != nil {
		return err
	}
	if len(records) == 0 {
		return nil
	}

	msgs := make([]kafka.Message, 0, len(records))
	for _, rec := range records {
		msgs = append(msgs, kafka.Message{
			Topic: rec.Topic,
			Value: rec.Payload,
		})
	}

	if err := r.writer.WriteMessages(ctx, msgs...); err != nil {
		return err
	}

	ids := make([]int64, len(records))
	for i, rec := range records {
		ids[i] = rec.ID
	}
	return r.markSent(ctx, ids)
}

func (r *Relay) markSent(ctx context.Context, ids []int64) error {
	placeholders := make([]string, len(ids))
	args := make([]any, len(ids))
	for i, id := range ids {
		placeholders[i] = fmt.Sprintf("$%d", i+1)
		args[i] = id
	}
	query := "UPDATE " + r.table + " SET sent_at = NOW() WHERE id IN (" + strings.Join(placeholders, ",") + ")"
	_, err := r.db.ExecContext(ctx, query, args...)
	return err
}
