package kafka

import (
	"github.com/segmentio/kafka-go"
)

// NewReader creates a Kafka consumer for the given topic and consumer group.
func NewReader(brokers []string, topic, groupID string) *kafka.Reader {
	return kafka.NewReader(kafka.ReaderConfig{
		Brokers:     brokers,
		Topic:       topic,
		GroupID:     groupID,
		MinBytes:    1,
		MaxBytes:    10e6, // 10 MB
		StartOffset: kafka.FirstOffset,
	})
}
