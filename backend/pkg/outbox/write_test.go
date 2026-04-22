package outbox

import (
	"context"
	"testing"

	sqlmock "github.com/DATA-DOG/go-sqlmock"
)

func TestWrite_InsertsRecord(t *testing.T) {
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatalf("sqlmock.New: %v", err)
	}
	defer db.Close()

	mock.ExpectBegin()
	mock.ExpectExec(`INSERT INTO ping_outbox`).
		WithArgs("ping-events", []byte(`{"status":"ok"}`)).
		WillReturnResult(sqlmock.NewResult(1, 1))
	mock.ExpectCommit()

	tx, _ := db.Begin()
	err = Write(context.Background(), tx, "ping_outbox", "ping-events", map[string]string{"status": "ok"})
	if err != nil {
		t.Fatalf("Write: %v", err)
	}
	if err := tx.Commit(); err != nil {
		t.Fatalf("Commit: %v", err)
	}

	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unmet expectations: %v", err)
	}
}

func TestWrite_MarshalError(t *testing.T) {
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatalf("sqlmock.New: %v", err)
	}
	defer db.Close()

	mock.ExpectBegin()
	tx, _ := db.Begin()

	// chan cannot be marshalled to JSON
	err = Write(context.Background(), tx, "ping_outbox", "ping-events", make(chan int))
	if err == nil {
		t.Fatal("expected marshal error, got nil")
	}
}
