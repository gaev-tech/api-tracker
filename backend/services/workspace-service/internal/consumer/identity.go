package consumer

import (
	"context"
	"encoding/json"
	"log/slog"

	kafkapkg "github.com/gaev-tech/api-tracker/backend/pkg/kafka"
	"github.com/gaev-tech/api-tracker/workspace-service/internal/domain"
	"github.com/gaev-tech/api-tracker/workspace-service/internal/store"
	"github.com/segmentio/kafka-go"
)

// IdentityConsumer consumes identity.user.* events to maintain users_cache.
type IdentityConsumer struct {
	readers    []*kafka.Reader
	userCache  *store.UserCacheStore
	logger     *slog.Logger
}

// NewIdentityConsumer creates consumers for identity user events.
func NewIdentityConsumer(brokers []string, userCache *store.UserCacheStore, logger *slog.Logger) *IdentityConsumer {
	groupID := "workspace-identity-consumer"
	return &IdentityConsumer{
		readers: []*kafka.Reader{
			kafkapkg.NewReader(brokers, "identity.user.registered", groupID),
			kafkapkg.NewReader(brokers, "identity.user.deleted", groupID),
			kafkapkg.NewReader(brokers, "identity.user.email_verified", groupID),
		},
		userCache: userCache,
		logger:    logger,
	}
}

// Start begins consuming messages from all topics. Blocks until context is cancelled.
func (c *IdentityConsumer) Start(ctx context.Context) {
	for _, reader := range c.readers {
		go c.consume(ctx, reader)
	}
	<-ctx.Done()
	for _, reader := range c.readers {
		reader.Close()
	}
}

func (c *IdentityConsumer) consume(ctx context.Context, reader *kafka.Reader) {
	topic := reader.Config().Topic
	for {
		msg, err := reader.ReadMessage(ctx)
		if err != nil {
			if ctx.Err() != nil {
				return
			}
			c.logger.Error("kafka read error", "topic", topic, "error", err)
			continue
		}

		if err := c.handleMessage(ctx, topic, msg.Value); err != nil {
			c.logger.Error("failed to handle message", "topic", topic, "error", err)
		}
	}
}

func (c *IdentityConsumer) handleMessage(ctx context.Context, topic string, value []byte) error {
	var payload map[string]string
	if err := json.Unmarshal(value, &payload); err != nil {
		return err
	}

	switch topic {
	case "identity.user.registered", "identity.user.email_verified":
		userID := payload["user_id"]
		if userID == "" {
			return nil
		}
		return c.userCache.Upsert(ctx, &domain.UserCache{
			UserID:   userID,
			Email:    payload["email"],
			Name:     payload["name"],
			IsActive: true,
		})

	case "identity.user.deleted":
		userID := payload["user_id"]
		if userID == "" {
			return nil
		}
		return c.userCache.Delete(ctx, userID)
	}

	return nil
}
