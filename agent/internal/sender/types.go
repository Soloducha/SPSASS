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

// AgentCommand represents a command for the agent to execute.
type AgentCommand struct {
	ID           string `json:"id"`
	EntityType   string `json:"entity_type"`
	EntityName   string `json:"entity_name"`
	Command      string `json:"command,omitempty"`
	MaxAttempts  int    `json:"max_attempts"`
	BackoffSeconds int  `json:"backoff_seconds"`
}

// AgentCommandResult represents the result of command execution.
type AgentCommandResult struct {
	Status     string `json:"status"`      // success, failed
	ExitCode   int    `json:"exit_code,omitempty"`
	OutputTail string `json:"output_tail,omitempty"`
}