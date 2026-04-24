package store

import (
	"context"
	"database/sql"
	"errors"

	"github.com/gaev-tech/api-tracker/billing-service/internal/domain"
)

type SubscriptionStore struct {
	db *sql.DB
}

func NewSubscriptionStore(db *sql.DB) *SubscriptionStore {
	return &SubscriptionStore{db: db}
}

const subscriptionColumns = `user_id, plan, period, current_period_start, current_period_end,
	planned_downgrade_plan, planned_downgrade_at,
	enterprise_slots, enterprise_slots_pending_decrease, enterprise_slots_pending_at,
	created_at, updated_at`

func scanSubscription(row interface{ Scan(dest ...any) error }) (*domain.Subscription, error) {
	s := &domain.Subscription{}
	err := row.Scan(
		&s.UserID, &s.Plan, &s.Period, &s.CurrentPeriodStart, &s.CurrentPeriodEnd,
		&s.PlannedDowngradePlan, &s.PlannedDowngradeAt,
		&s.EnterpriseSlots, &s.EnterpriseSlotsDecreasePending, &s.EnterpriseSlotsPendingAt,
		&s.CreatedAt, &s.UpdatedAt,
	)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, ErrNotFound
	}
	return s, err
}

// FindByUserID returns the subscription for a user.
func (st *SubscriptionStore) FindByUserID(ctx context.Context, userID string) (*domain.Subscription, error) {
	row := st.db.QueryRowContext(ctx, `SELECT `+subscriptionColumns+` FROM subscriptions WHERE user_id = $1`, userID)
	return scanSubscription(row)
}

// CreateFree creates a default free subscription for a user.
func (st *SubscriptionStore) CreateFree(ctx context.Context, userID string) (*domain.Subscription, error) {
	row := st.db.QueryRowContext(ctx, `
		INSERT INTO subscriptions (user_id, plan)
		VALUES ($1, 'free')
		RETURNING `+subscriptionColumns,
		userID,
	)
	sub, err := scanSubscription(row)
	if err != nil && isPgUniqueViolation(err) {
		return nil, ErrConflict
	}
	return sub, err
}

// Update updates subscription fields.
func (st *SubscriptionStore) Update(ctx context.Context, s *domain.Subscription) (*domain.Subscription, error) {
	row := st.db.QueryRowContext(ctx, `
		UPDATE subscriptions SET
			plan = $2, period = $3,
			current_period_start = $4, current_period_end = $5,
			planned_downgrade_plan = $6, planned_downgrade_at = $7,
			enterprise_slots = $8,
			enterprise_slots_pending_decrease = $9, enterprise_slots_pending_at = $10,
			updated_at = now()
		WHERE user_id = $1
		RETURNING `+subscriptionColumns,
		s.UserID, s.Plan, s.Period,
		s.CurrentPeriodStart, s.CurrentPeriodEnd,
		s.PlannedDowngradePlan, s.PlannedDowngradeAt,
		s.EnterpriseSlots,
		s.EnterpriseSlotsDecreasePending, s.EnterpriseSlotsPendingAt,
	)
	return scanSubscription(row)
}

// AddHistory inserts a subscription history record.
func (st *SubscriptionStore) AddHistory(ctx context.Context, h *domain.SubscriptionHistory) error {
	_, err := st.db.ExecContext(ctx, `
		INSERT INTO subscription_history (user_id, plan, period, started_at, ended_at, reason)
		VALUES ($1, $2, $3, $4, $5, $6)`,
		h.UserID, h.Plan, h.Period, h.StartedAt, h.EndedAt, h.Reason,
	)
	return err
}
