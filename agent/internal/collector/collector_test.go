package collector

import (
	"context"
	"testing"
	"time"
)

type mockSystemStats struct {
	cpuPercent    float64
	memPercent    float64
	diskPercent   float64
	load1, load5, load15 float64
	err           error
}

func (m *mockSystemStats) CPUPercent() (float64, error) {
	return m.cpuPercent, m.err
}
func (m *mockSystemStats) VirtualMemory() (float64, error) {
	return m.memPercent, m.err
}
func (m *mockSystemStats) DiskUsage(path string) (float64, error) {
	return m.diskPercent, m.err
}
func (m *mockSystemStats) LoadAvg() (float64, float64, float64, error) {
	return m.load1, m.load5, m.load15, m.err
}

func TestCollect_ReturnsSixMetrics(t *testing.T) {
	mock := &mockSystemStats{
		cpuPercent:  12.345,
		memPercent:  63.123,
		diskPercent: 58.234,
		load1:       0.421,
		load5:       0.382,
		load15:      0.305,
	}
	SetSystemStats(mock)
	defer SetSystemStats(&GopsutilSystemStats{}) // restore

	batch, err := Collect(context.Background(), "test-server-id")
	if err != nil {
		t.Fatalf("Collect() error: %v", err)
	}

	if batch.ServerID != "test-server-id" {
		t.Errorf("ServerID = %q, want %q", batch.ServerID, "test-server-id")
	}

	if len(batch.Metrics) != 6 {
		t.Fatalf("len(Metrics) = %d, want 6", len(batch.Metrics))
	}

	expectedTypes := []string{
		"cpu_usage", "mem_usage", "disk_usage",
		"load_avg1", "load_avg5", "load_avg15",
	}
	for i, wantType := range expectedTypes {
		if batch.Metrics[i].Type != wantType {
			t.Errorf("Metrics[%d].Type = %q, want %q", i, batch.Metrics[i].Type, wantType)
		}
	}

	// Verify rounding to 2 decimal places
	if batch.Metrics[0].Value != 12.35 { // cpu_usage
		t.Errorf("cpu_usage = %v, want 12.35", batch.Metrics[0].Value)
	}
	if batch.Metrics[1].Value != 63.12 { // mem_usage
		t.Errorf("mem_usage = %v, want 63.12", batch.Metrics[1].Value)
	}
	if batch.Metrics[2].Value != 58.23 { // disk_usage
		t.Errorf("disk_usage = %v, want 58.23", batch.Metrics[2].Value)
	}
	if batch.Metrics[3].Value != 0.42 { // load_avg1
		t.Errorf("load_avg1 = %v, want 0.42", batch.Metrics[3].Value)
	}
	if batch.Metrics[4].Value != 0.38 { // load_avg5
		t.Errorf("load_avg5 = %v, want 0.38", batch.Metrics[4].Value)
	}
	if batch.Metrics[5].Value != 0.31 { // load_avg15
		t.Errorf("load_avg15 = %v, want 0.31", batch.Metrics[5].Value)
	}

	// Verify tags
	if batch.Metrics[0].Tags["mode"] != "total" {
		t.Errorf("cpu_usage tags = %v, want mode=total", batch.Metrics[0].Tags)
	}
	if batch.Metrics[2].Tags["mount"] != "/" {
		t.Errorf("disk_usage tags = %v, want mount=/", batch.Metrics[2].Tags)
	}
	for i := 1; i < 6; i++ {
		if i == 2 { continue } // skip disk_usage
		if len(batch.Metrics[i].Tags) != 0 {
			t.Errorf("Metrics[%d] tags = %v, want empty", i, batch.Metrics[i].Tags)
		}
	}

	// TS should be recent (within last second)
	if time.Since(batch.TS) > time.Second {
		t.Errorf("TS = %v, want recent", batch.TS)
	}
}

func TestCollect_ReturnsErrorOnFailure(t *testing.T) {
	mock := &mockSystemStats{err: errTest}
	SetSystemStats(mock)
	defer SetSystemStats(&GopsutilSystemStats{})

	_, err := Collect(context.Background(), "test-server-id")
	if err != errTest {
		t.Errorf("Collect() error = %v, want %v", err, errTest)
	}
}

func TestCollect_RespectsContextCancellation(t *testing.T) {
	mock := &mockSystemStats{cpuPercent: 10.0}
	SetSystemStats(mock)
	defer SetSystemStats(&GopsutilSystemStats{})

	ctx, cancel := context.WithCancel(context.Background())
	cancel() // cancel immediately

	_, err := Collect(ctx, "test-server-id")
	if err != context.Canceled {
		t.Errorf("Collect() error = %v, want context.Canceled", err)
	}
}

func TestRound2(t *testing.T) {
	tests := []struct {
		input    float64
		expected float64
	}{
		{12.345, 12.35},
		{12.344, 12.34},
		{0.0, 0.0},
		{100.0, 100.0},
		{99.999, 100.0},
		{-1.5, -1.5},
	}
	for _, tc := range tests {
		result := round2(tc.input)
		if result != tc.expected {
			t.Errorf("round2(%v) = %v, want %v", tc.input, result, tc.expected)
		}
	}
}

var errTest = &testError{"test error"}

type testError struct {
	msg string
}

func (e *testError) Error() string {
	return e.msg
}

// TestCollect_Integration runs with real gopsutil (skipped in -short mode).
func TestCollect_Integration(t *testing.T) {
	if testing.Short() {
		t.Skip("skipping integration test in -short mode")
	}
	SetSystemStats(&GopsutilSystemStats{})
	batch, err := Collect(context.Background(), "integration-test")
	if err != nil {
		t.Fatalf("Collect() error: %v", err)
	}
	if len(batch.Metrics) != 6 {
		t.Errorf("len(Metrics) = %d, want 6", len(batch.Metrics))
	}
	for _, m := range batch.Metrics {
		if m.Value < 0 {
			t.Errorf("metric %s has negative value: %v", m.Type, m.Value)
		}
	}
}