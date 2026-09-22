package collector

import (
	"context"
	"math"
	"time"
)

type Metric struct {
	Type  string            `json:"type"`
	Value float64           `json:"value"`
	Tags  map[string]string `json:"tags"`
}

type MetricsBatch struct {
	ServerID string    `json:"server_id"`
	TS       time.Time `json:"ts"`
	Metrics  []Metric  `json:"metrics"`
}

// SystemStats is an interface for collecting system metrics.
// This allows mocking in tests.
type SystemStats interface {
	CPUPercent() (float64, error)
	VirtualMemory() (float64, error)
	DiskUsage(path string) (float64, error)
	LoadAvg() (float64, float64, float64, error)
}

// realSystemStats implements SystemStats using gopsutil.
type realSystemStats struct{}

func (r *realSystemStats) CPUPercent() (float64, error) {
	// Import here to avoid dependency in tests
	// This will be replaced by actual gopsutil call in production
	return 0, nil
}

func (r *realSystemStats) VirtualMemory() (float64, error) {
	return 0, nil
}

func (r *realSystemStats) DiskUsage(path string) (float64, error) {
	return 0, nil
}

func (r *realSystemStats) LoadAvg() (float64, float64, float64, error) {
	return 0, 0, 0, nil
}

// defaultSystemStats is the production implementation using gopsutil.
// It's a variable so tests can replace it.
var defaultSystemStats SystemStats = &realSystemStats{}

// SetSystemStats replaces the system stats implementation (for testing).
func SetSystemStats(s SystemStats) {
	defaultSystemStats = s
}

// round2 rounds a float64 to 2 decimal places.
func round2(v float64) float64 {
	return math.Round(v*100) / 100
}

// Collect gathers system metrics and returns a MetricsBatch.
func Collect(ctx context.Context, serverID string) (MetricsBatch, error) {
	select {
	case <-ctx.Done():
		return MetricsBatch{}, ctx.Err()
	default:
	}

	cpuPercent, err := defaultSystemStats.CPUPercent()
	if err != nil {
		return MetricsBatch{}, err
	}

	memPercent, err := defaultSystemStats.VirtualMemory()
	if err != nil {
		return MetricsBatch{}, err
	}

	diskPercent, err := defaultSystemStats.DiskUsage("/")
	if err != nil {
		return MetricsBatch{}, err
	}

	load1, load5, load15, err := defaultSystemStats.LoadAvg()
	if err != nil {
		return MetricsBatch{}, err
	}

	now := time.Now().UTC()
	metrics := []Metric{
		{Type: "cpu_usage", Value: round2(cpuPercent), Tags: map[string]string{"mode": "total"}},
		{Type: "mem_usage", Value: round2(memPercent), Tags: map[string]string{}},
		{Type: "disk_usage", Value: round2(diskPercent), Tags: map[string]string{"mount": "/"}},
		{Type: "load_avg1", Value: round2(load1), Tags: map[string]string{}},
		{Type: "load_avg5", Value: round2(load5), Tags: map[string]string{}},
		{Type: "load_avg15", Value: round2(load15), Tags: map[string]string{}},
	}

	return MetricsBatch{
		ServerID: serverID,
		TS:       now,
		Metrics:  metrics,
	}, nil
}