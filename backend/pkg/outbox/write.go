package outbox

import (
	"context"
	"database/sql"
	"encoding/json"
)

// Write inserts one record into the outbox table within the provided transaction.
// table is the outbox table name (e.g. "ping_outbox").
// payload is marshalled to JSON and stored in the payload column.
func Write(ctx context.Context, tx *sql.Tx, table, topic string, payload any) error {
	data, err := json.Marshal(payload)
	if err != nil {
		return err
	}
	_, err = tx.ExecContext(ctx,
		"INSERT INTO "+table+" (topic, payload) VALUES ($1, $2)",
		topic, data,
	)
	return err
}
