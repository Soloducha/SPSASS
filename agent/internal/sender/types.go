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

// EntitiesBatch mirrors collector.EntitiesBatch for the sender package.
// This avoids a circular dependency.
type EntitiesBatch struct {
	ServerID  string            `json:"server_id"`
	TS        time.Time         `json:"ts"`
	Processes []ProcessState    `json:"processes"`
	Services  []ServiceState    `json:"services"`
}

type ProcessState struct {
	Name    string `json:"name"`
	Cmdline string `json:"cmdline"`
	State   string `json:"state"`
}

type ServiceState struct {
	Name  string `json:"name"`
	State string `json:"state"`
}