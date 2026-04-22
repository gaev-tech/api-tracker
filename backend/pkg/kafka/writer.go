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
