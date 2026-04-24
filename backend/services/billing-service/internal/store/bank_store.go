package store

import (
	"context"
	"database/sql"
	"errors"

	"github.com/gaev-tech/api-tracker/billing-service/internal/domain"
)

type BankStore struct {
	db *sql.DB
}

func NewBankStore(db *sql.DB) *BankStore {
	return &BankStore{db: db}
}

// ListByUserID returns all bank layers for a user, ordered by layer_order.
func (s *BankStore) ListByUserID(ctx context.Context, userID string) ([]*domain.BankLayer, error) {
	rows, err := s.db.QueryContext(ctx, `
		SELECT id, user_id, plan, period, days_remaining, layer_order, created_at
		FROM subscription_bank_days
		WHERE user_id = $1
		ORDER BY layer_order`,
		userID,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var layers []*domain.BankLayer
	for rows.Next() {
		l := &domain.BankLayer{}
		if err := rows.Scan(&l.ID, &l.UserID, &l.Plan, &l.Period, &l.DaysRemaining, &l.LayerOrder, &l.CreatedAt); err != nil {
			return nil, err
		}
		layers = append(layers, l)
	}
	return layers, rows.Err()
}

// Create inserts a new bank layer.
func (s *BankStore) Create(ctx context.Context, l *domain.BankLayer) error {
	_, err := s.db.ExecContext(ctx, `
		INSERT INTO subscription_bank_days (user_id, plan, period, days_remaining, layer_order)
		VALUES ($1, $2, $3, $4, $5)`,
		l.UserID, l.Plan, l.Period, l.DaysRemaining, l.LayerOrder,
	)
	return err
}

// Delete removes a bank layer by ID.
func (s *BankStore) Delete(ctx context.Context, id string) error {
	res, err := s.db.ExecContext(ctx, `DELETE FROM subscription_bank_days WHERE id = $1`, id)
	if err != nil {
		return err
	}
	n, err := res.RowsAffected()
	if err != nil {
		return err
	}
	if n == 0 {
		return errors.New("bank layer not found")
	}
	return nil
}
