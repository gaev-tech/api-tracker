package consumer

import (
	"context"
	"encoding/json"
	"log/slog"
	"time"

	kafkapkg "github.com/gaev-tech/api-tracker/backend/pkg/kafka"
	"github.com/gaev-tech/api-tracker/events-service/internal/domain"
	"github.com/gaev-tech/api-tracker/events-service/internal/store"
	"github.com/segmentio/kafka-go"
)

// topics lists all Kafka topics that events-service consumes.
var topics = []string{
	// identity-service
	"identity.user.registered",
	"identity.user.deleted",
	"identity.user.email_verified",
	"identity.pat.created",
	"identity.pat.revoked",
	// workspace-service
	"workspace.task.created",
	"workspace.task.updated",
	"workspace.task.deleted",
	"workspace.task.access.granted",
	"workspace.task.access.updated",
	"workspace.task.access.revoked",
	"workspace.project.created",
	"workspace.project.updated",
	"workspace.project.deleted",
	"workspace.project.member.updated",
	"workspace.project.member.removed",
	"workspace.project.invitation.created",
	"workspace.project.invitation.accepted",
	"workspace.project.invitation.declined",
	"workspace.project.ownership_transfer.created",
	"workspace.project.ownership_transfer.accepted",
	"workspace.project.ownership_transfer.declined",
	"workspace.project.ownership_transfer.cancelled",
	"workspace.project.owner_changed",
	"workspace.team.created",
	"workspace.team.updated",
	"workspace.team.deleted",
	"workspace.team.member.updated",
	"workspace.team.member.removed",
	"workspace.team.invitation.created",
	"workspace.team.invitation.accepted",
	"workspace.team.invitation.declined",
	"workspace.team.ownership_transfer.created",
	"workspace.team.ownership_transfer.accepted",
	"workspace.team.ownership_transfer.declined",
	"workspace.team.ownership_transfer.cancelled",
	"workspace.team.owner_changed",
	// billing-service
	"billing.entity.frozen",
	"billing.entity.unfrozen",
	"billing.tariff.changed",
	// automations-service
	"automations.automation.enabled",
	"automations.automation.disabled",
	"automations.automation.frozen",
}

// EventsConsumer consumes all domain events from Kafka and stores them.
type EventsConsumer struct {
	readers []*kafka.Reader
	store   *store.EventStore
	logger  *slog.Logger
}

// NewEventsConsumer creates a consumer for all domain event topics.
func NewEventsConsumer(brokers []string, eventStore *store.EventStore, logger *slog.Logger) *EventsConsumer {
	groupID := "events-service-consumer"
	readers := make([]*kafka.Reader, 0, len(topics))
	for _, topic := range topics {
		readers = append(readers, kafkapkg.NewReader(brokers, topic, groupID))
	}
	return &EventsConsumer{
		readers: readers,
		store:   eventStore,
		logger:  logger,
	}
}

// Start begins consuming messages from all topics. Blocks until context is cancelled.
func (c *EventsConsumer) Start(ctx context.Context) {
	for _, reader := range c.readers {
		go c.consume(ctx, reader)
	}
	<-ctx.Done()
	for _, reader := range c.readers {
		reader.Close()
	}
}

func (c *EventsConsumer) consume(ctx context.Context, reader *kafka.Reader) {
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

		event, err := c.parseEvent(topic, msg.Value, msg.Time)
		if err != nil {
			c.logger.Error("failed to parse event", "topic", topic, "error", err)
			continue
		}

		if err := c.store.Insert(ctx, event); err != nil {
			c.logger.Error("failed to store event", "topic", topic, "error", err)
		}
	}
}

func (c *EventsConsumer) parseEvent(topic string, value []byte, msgTime time.Time) (*domain.Event, error) {
	var payload map[string]string
	if err := json.Unmarshal(value, &payload); err != nil {
		return nil, err
	}

	event := &domain.Event{
		Type:      topic,
		Payload:   value,
		CreatedAt: msgTime,
	}

	if v := payload["actor_id"]; v != "" {
		event.ActorID = &v
	} else if v := payload["author_id"]; v != "" {
		event.ActorID = &v
	} else if v := payload["user_id"]; v != "" {
		event.ActorID = &v
	} else if v := payload["invited_by"]; v != "" {
		event.ActorID = &v
	} else if v := payload["from_user_id"]; v != "" {
		event.ActorID = &v
	}

	if v := payload["task_id"]; v != "" {
		event.TaskID = &v
	}
	if v := payload["project_id"]; v != "" {
		event.ProjectID = &v
	}
	if v := payload["team_id"]; v != "" {
		event.TeamID = &v
	}
	if v := payload["automation_id"]; v != "" {
		event.AutomationID = &v
	}
	if v := payload["target_user_id"]; v != "" {
		event.TargetUserID = &v
	}

	return event, nil
}
