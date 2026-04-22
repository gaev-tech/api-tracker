package kafka

import (
	"github.com/segmentio/kafka-go"
)

// NewWriter creates a Kafka producer for the given topic.
// The writer uses async batching with required-acks=all for durability.
func NewWriter(brokers []string, topic string) *kafka.Writer {
	return &kafka.Writer{
		Addr:                   kafka.TCP(brokers...),
		Topic:                  topic,
		Balancer:               &kafka.LeastBytes{},
		RequiredAcks:           kafka.RequireAll,
		AllowAutoTopicCreation: false,
	}
}

// NewMultiWriter creates a Kafka producer without a fixed topic.
// Each kafka.Message must set its own Topic field.
// Used by the outbox relay which writes to multiple topics.
func NewMultiWriter(brokers []string) *kafka.Writer {
	return &kafka.Writer{
		Addr:                   kafka.TCP(brokers...),
		Balancer:               &kafka.LeastBytes{},
		RequiredAcks:           kafka.RequireAll,
		AllowAutoTopicCreation: false,
	}
}
