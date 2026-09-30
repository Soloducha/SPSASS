package collector

import (
	"context"
	"time"
)

// ProcessState represents the state of a process.
type ProcessState struct {
	Name    string `json:"name"`
	Cmdline string `json:"cmdline"`
	State   string `json:"state"` // "running" or "unknown"
}

// ServiceState represents the state of a systemd service.
type ServiceState struct {
	Name  string `json:"name"`
	State string `json:"state"` // "running", "stopped", "failed", "unknown"
}

// EntitiesBatch holds process and service state for a server.
type EntitiesBatch struct {
	ServerID  string         `json:"server_id"`
	TS        time.Time      `json:"ts"`
	Processes []ProcessState `json:"processes"`
	Services  []ServiceState `json:"services"`
}

// ProcessLister lists processes with name, cmdline, and status.
type ProcessLister interface {
	ListProcesses() ([]ProcessInfo, error)
}

// ProcessInfo holds process information from the lister.
type ProcessInfo struct {
	Name    string
	Cmdline string
	Status  string // e.g., "R" for running
}

// ServiceLister lists systemd services with name and state.
type ServiceLister interface {
	ListServices() ([]ServiceInfo, error)
}

// ServiceInfo holds service information from the lister.
type ServiceInfo struct {
	Name  string
	State string // systemd state: "active", "inactive", "failed", etc.
}

// defaultProcessLister is the production implementation using gopsutil.
// It's a variable so tests can replace it.
var defaultProcessLister ProcessLister = &gopsutilProcessLister{}

// defaultServiceLister is the production implementation using gopsutil.
var defaultServiceLister ServiceLister = &gopsutilServiceLister{}

// SetProcessLister replaces the process lister implementation (for testing).
func SetProcessLister(l ProcessLister) {
	defaultProcessLister = l
}

// SetServiceLister replaces the service lister implementation (for testing).
func SetServiceLister(l ServiceLister) {
	defaultServiceLister = l
}

// CollectEntities gathers process and service state and returns an EntitiesBatch.
func CollectEntities(ctx context.Context, serverID string) (EntitiesBatch, error) {
	select {
	case <-ctx.Done():
		return EntitiesBatch{}, ctx.Err()
	default:
	}

	now := time.Now().UTC()

	// Collect processes
	processes, err := collectProcesses()
	if err != nil {
		return EntitiesBatch{}, err
	}

	// Collect services
	services, err := collectServices()
	if err != nil {
		return EntitiesBatch{}, err
	}

	return EntitiesBatch{
		ServerID:  serverID,
		TS:        now,
		Processes: processes,
		Services:  services,
	}, nil
}

func collectProcesses() ([]ProcessState, error) {
	procs, err := defaultProcessLister.ListProcesses()
	if err != nil {
		return nil, err
	}

	states := make([]ProcessState, 0, len(procs))
	for _, p := range procs {
		state := "unknown"
		if p.Status == "R" {
			state = "running"
		}
		states = append(states, ProcessState{
			Name:    p.Name,
			Cmdline: p.Cmdline,
			State:   state,
		})
	}
	return states, nil
}

func collectServices() ([]ServiceState, error) {
	svcs, err := defaultServiceLister.ListServices()
	if err != nil {
		return nil, err
	}

	states := make([]ServiceState, 0, len(svcs))
	for _, s := range svcs {
		state := "unknown"
		switch s.State {
		case "active":
			state = "running"
		case "inactive":
			state = "stopped"
		case "failed":
			state = "failed"
		}
		states = append(states, ServiceState{
			Name:  s.Name,
			State: state,
		})
	}
	return states, nil
}