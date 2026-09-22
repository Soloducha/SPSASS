package sender

import (
	"time"
)

// MetricsBatch mirrors collector.MetricsBatch for the sender package.
// This avoids a circular dependency.
type MetricsBatch struct {
	ServerID string    `json:"server_id"`
	TS       time.Time `json:"ts"`
	Metrics  []Metric  `json:"metrics"`
}

type Metric struct {
	Type  string            `json:"type"`
	Value float64           `json:"value"`
	Tags  map[string]string `json:"tags"`
}