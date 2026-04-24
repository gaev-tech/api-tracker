package domain

import "time"

type Subscription struct {
	UserID                       string     `json:"user_id"`
	Plan                         string     `json:"plan"`
	Period                       *string    `json:"period"`
	CurrentPeriodStart           *time.Time `json:"current_period_start"`
	CurrentPeriodEnd             *time.Time `json:"current_period_end"`
	PlannedDowngradePlan         *string    `json:"planned_downgrade_plan,omitempty"`
	PlannedDowngradeAt           *time.Time `json:"planned_downgrade_at,omitempty"`
	EnterpriseSlots              int        `json:"enterprise_slots"`
	EnterpriseSlotsDecreasePending *int     `json:"enterprise_slots_pending_decrease,omitempty"`
	EnterpriseSlotsPendingAt     *time.Time `json:"enterprise_slots_pending_at,omitempty"`
	CreatedAt                    time.Time  `json:"created_at"`
	UpdatedAt                    time.Time  `json:"updated_at"`
}

type BankLayer struct {
	ID            string    `json:"id"`
	UserID        string    `json:"-"`
	Plan          string    `json:"plan"`
	Period        string    `json:"period"`
	DaysRemaining int       `json:"days_remaining"`
	LayerOrder    int       `json:"layer_order"`
	CreatedAt     time.Time `json:"created_at"`
}

type SubscriptionHistory struct {
	ID        string     `json:"id"`
	UserID    string     `json:"-"`
	Plan      string     `json:"plan"`
	Period    *string    `json:"period"`
	StartedAt time.Time  `json:"started_at"`
	EndedAt   *time.Time `json:"ended_at"`
	Reason    string     `json:"reason"`
	CreatedAt time.Time  `json:"created_at"`
}
