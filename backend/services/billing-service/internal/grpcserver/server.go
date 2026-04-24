package grpcserver

import (
	"context"
	"errors"

	billingv1 "github.com/gaev-tech/api-tracker/contracts/proto/billing/v1"
	"github.com/gaev-tech/api-tracker/billing-service/internal/domain"
	"github.com/gaev-tech/api-tracker/billing-service/internal/store"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

type Server struct {
	billingv1.UnimplementedBillingServiceServer
	subscriptions *store.SubscriptionStore
	usage         *store.UsageStore
}

func New(subscriptions *store.SubscriptionStore, usage *store.UsageStore) *Server {
	return &Server{subscriptions: subscriptions, usage: usage}
}

var entityTypeMap = map[billingv1.EntityType]string{
	billingv1.EntityType_ENTITY_TYPE_TASK:       domain.EntityTypeTask,
	billingv1.EntityType_ENTITY_TYPE_PROJECT:    domain.EntityTypeProject,
	billingv1.EntityType_ENTITY_TYPE_TEAM:       domain.EntityTypeTeam,
	billingv1.EntityType_ENTITY_TYPE_AUTOMATION: domain.EntityTypeAutomation,
	billingv1.EntityType_ENTITY_TYPE_MEMBER:     domain.EntityTypeMember,
}

func (s *Server) CheckLimit(ctx context.Context, req *billingv1.CheckLimitRequest) (*billingv1.CheckLimitResponse, error) {
	if req.UserId == "" {
		return nil, status.Error(codes.InvalidArgument, "user_id is required")
	}
	entityType, ok := entityTypeMap[req.EntityType]
	if !ok || req.EntityType == billingv1.EntityType_ENTITY_TYPE_UNSPECIFIED {
		return nil, status.Error(codes.InvalidArgument, "valid entity_type is required")
	}

	// Get or create subscription (lazy creation)
	sub, err := s.getOrCreateSubscription(ctx, req.UserId)
	if err != nil {
		return nil, status.Error(codes.Internal, "failed to get subscription")
	}

	limit := domain.LimitForEntity(sub.Plan, entityType, sub.EnterpriseSlots)
	if limit == domain.Unlimited {
		return &billingv1.CheckLimitResponse{Allowed: true}, nil
	}

	currentCount, err := s.usage.GetCount(ctx, req.UserId, entityType)
	if err != nil {
		return nil, status.Error(codes.Internal, "failed to get usage count")
	}

	return &billingv1.CheckLimitResponse{Allowed: currentCount < limit}, nil
}

func (s *Server) getOrCreateSubscription(ctx context.Context, userID string) (*domain.Subscription, error) {
	sub, err := s.subscriptions.FindByUserID(ctx, userID)
	if err == nil {
		return sub, nil
	}
	if !errors.Is(err, store.ErrNotFound) {
		return nil, err
	}

	// Lazy creation: create free subscription
	sub, err = s.subscriptions.CreateFree(ctx, userID)
	if errors.Is(err, store.ErrConflict) {
		// Race condition: another request created it first
		return s.subscriptions.FindByUserID(ctx, userID)
	}
	return sub, err
}
