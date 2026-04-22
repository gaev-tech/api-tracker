package outbox

import (
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"testing"

	sqlmock "github.com/DATA-DOG/go-sqlmock"
	"github.com/segmentio/kafka-go"
)

// mockWriter captures messages written to it.
type mockWriter struct {
	msgs []kafka.Message
	err  error
}

func (m *mockWriter) WriteMessages(_ context.Context, msgs ...kafka.Message) error {
	if m.err != nil {
		return m.err
	}
	m.msgs = append(m.msgs, msgs...)
	return nil
}

func TestFlush_PublishesAndMarksSent(t *testing.T) {
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatalf("sqlmock.New: %v", err)
	}
	defer db.Close()

	payload := json.RawMessage(`{"key":"val"}`)
	rows := sqlmock.NewRows([]string{"id", "topic", "payload"}).
		AddRow(int64(1), "user-events", payload)

	mock.ExpectQuery(`SELECT id, topic, payload FROM ping_outbox WHERE sent_at IS NULL`).
		WillReturnRows(rows)
	mock.ExpectExec(`UPDATE ping_outbox SET sent_at`).
		WithArgs(int64(1)).
		WillReturnResult(sqlmock.NewResult(0, 1))

	w := &mockWriter{}
	r := New(db, w, "ping_outbox", slog.Default())

	if err := r.flush(context.Background()); err != nil {
		t.Fatalf("flush: %v", err)
	}

	if len(w.msgs) != 1 {
		t.Fatalf("expected 1 message, got %d", len(w.msgs))
	}
	if w.msgs[0].Topic != "user-events" {
		t.Errorf("topic = %q, want %q", w.msgs[0].Topic, "user-events")
	}

	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unmet expectations: %v", err)
	}
}

func TestFlush_NoRecords(t *testing.T) {
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatalf("sqlmock.New: %v", err)
	}
	defer db.Close()

	rows := sqlmock.NewRows([]string{"id", "topic", "payload"})
	mock.ExpectQuery(`SELECT id, topic, payload FROM ping_outbox WHERE sent_at IS NULL`).
		WillReturnRows(rows)

	w := &mockWriter{}
	r := New(db, w, "ping_outbox", slog.Default())

	if err := r.flush(context.Background()); err != nil {
		t.Fatalf("flush: %v", err)
	}
	if len(w.msgs) != 0 {
		t.Errorf("expected 0 messages, got %d", len(w.msgs))
	}

	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unmet expectations: %v", err)
	}
}

func TestFlush_WriterError_DoesNotMarkSent(t *testing.T) {
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatalf("sqlmock.New: %v", err)
	}
	defer db.Close()

	payload := json.RawMessage(`{"key":"val"}`)
	rows := sqlmock.NewRows([]string{"id", "topic", "payload"}).
		AddRow(int64(2), "task-events", payload)

	mock.ExpectQuery(`SELECT id, topic, payload FROM ping_outbox WHERE sent_at IS NULL`).
		WillReturnRows(rows)

	w := &mockWriter{err: errors.New("kafka down")}
	r := New(db, w, "ping_outbox", slog.Default())

	if err := r.flush(context.Background()); err == nil {
		t.Fatal("expected error from writer, got nil")
	}

	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unmet expectations: %v", err)
	}
}
