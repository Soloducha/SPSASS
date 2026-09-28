package collector

import (
	"context"
	"testing"
	"time"
)

type mockProcessLister struct {
	procs []ProcessInfo
	err   error
}

func (m *mockProcessLister) ListProcesses() ([]ProcessInfo, error) {
	return m.procs, m.err
}

type mockServiceLister struct {
	svcs []ServiceInfo
	err  error
}

func (m *mockServiceLister) ListServices() ([]ServiceInfo, error) {
	return m.svcs, m.err
}

func TestCollectEntities_ReturnsProcessesAndServices(t *testing.T) {
	mockProcs := &mockProcessLister{
		procs: []ProcessInfo{
			{Name: "nginx", Cmdline: "nginx: master process", Status: "R"},
			{Name: "redis", Cmdline: "redis-server *:6379", Status: "S"},
			{Name: "postgres", Cmdline: "postgres", Status: "R"},
		},
	}
	mockSvcs := &mockServiceLister{
		svcs: []ServiceInfo{
			{Name: "nginx", State: "active"},
			{Name: "redis", State: "inactive"},
			{Name: "postgresql", State: "failed"},
			{Name: "unknown-svc", State: "unknown"},
		},
	}
	SetProcessLister(mockProcs)
	SetServiceLister(mockSvcs)
	defer SetProcessLister(&gopsutilProcessLister{})
	defer SetServiceLister(&gopsutilServiceLister{})

	batch, err := CollectEntities(context.Background(), "test-server-id")
	if err != nil {
		t.Fatalf("CollectEntities() error: %v", err)
	}

	if batch.ServerID != "test-server-id" {
		t.Errorf("ServerID = %q, want %q", batch.ServerID, "test-server-id")
	}

	// Check processes: 3 total, 2 running (R), 1 unknown (S)
	if len(batch.Processes) != 3 {
		t.Fatalf("len(Processes) = %d, want 3", len(batch.Processes))
	}

	// Check first process (nginx, running)
	if batch.Processes[0].Name != "nginx" {
		t.Errorf("Processes[0].Name = %q, want nginx", batch.Processes[0].Name)
	}
	if batch.Processes[0].Cmdline != "nginx: master process" {
		t.Errorf("Processes[0].Cmdline = %q, want nginx: master process", batch.Processes[0].Cmdline)
	}
	if batch.Processes[0].State != "running" {
		t.Errorf("Processes[0].State = %q, want running", batch.Processes[0].State)
	}

	// Check second process (redis, unknown - S is not R)
	if batch.Processes[1].State != "unknown" {
		t.Errorf("Processes[1].State = %q, want unknown (S)", batch.Processes[1].State)
	}

	// Check third process (postgres, running)
	if batch.Processes[2].State != "running" {
		t.Errorf("Processes[2].State = %q, want running", batch.Processes[2].State)
	}

	// Check services: 4 total
	if len(batch.Services) != 4 {
		t.Fatalf("len(Services) = %d, want 4", len(batch.Services))
	}

	// nginx -> active -> running
	if batch.Services[0].State != "running" {
		t.Errorf("Services[0].State = %q, want running (active)", batch.Services[0].State)
	}
	// redis -> inactive -> stopped
	if batch.Services[1].State != "stopped" {
		t.Errorf("Services[1].State = %q, want stopped (inactive)", batch.Services[1].State)
	}
	// postgresql -> failed -> failed
	if batch.Services[2].State != "failed" {
		t.Errorf("Services[2].State = %q, want failed", batch.Services[2].State)
	}
	// unknown-svc -> unknown -> unknown
	if batch.Services[3].State != "unknown" {
		t.Errorf("Services[3].State = %q, want unknown", batch.Services[3].State)
	}

	// TS should be recent (within last second)
	if time.Since(batch.TS) > time.Second {
		t.Errorf("TS = %v, want recent", batch.TS)
	}
}

func TestCollectEntities_ReturnsErrorOnProcessListerFailure(t *testing.T) {
	mockProcs := &mockProcessLister{err: errTest}
	mockSvcs := &mockServiceLister{svcs: []ServiceInfo{{Name: "test", State: "active"}}}
	SetProcessLister(mockProcs)
	SetServiceLister(mockSvcs)
	defer SetProcessLister(&gopsutilProcessLister{})
	defer SetServiceLister(&gopsutilServiceLister{})

	_, err := CollectEntities(context.Background(), "test-server-id")
	if err != errTest {
		t.Errorf("CollectEntities() error = %v, want %v", err, errTest)
	}
}

func TestCollectEntities_ReturnsErrorOnServiceListerFailure(t *testing.T) {
	mockProcs := &mockProcessLister{procs: []ProcessInfo{{Name: "test", Status: "R"}}}
	mockSvcs := &mockServiceLister{err: errTest}
	SetProcessLister(mockProcs)
	SetServiceLister(mockSvcs)
	defer SetProcessLister(&gopsutilProcessLister{})
	defer SetServiceLister(&gopsutilServiceLister{})

	_, err := CollectEntities(context.Background(), "test-server-id")
	if err != errTest {
		t.Errorf("CollectEntities() error = %v, want %v", err, errTest)
	}
}

func TestCollectEntities_RespectsContextCancellation(t *testing.T) {
	mockProcs := &mockProcessLister{procs: []ProcessInfo{{Name: "test", Status: "R"}}}
	mockSvcs := &mockServiceLister{svcs: []ServiceInfo{{Name: "test", State: "active"}}}
	SetProcessLister(mockProcs)
	SetServiceLister(mockSvcs)
	defer SetProcessLister(&gopsutilProcessLister{})
	defer SetServiceLister(&gopsutilServiceLister{})

	ctx, cancel := context.WithCancel(context.Background())
	cancel() // cancel immediately

	_, err := CollectEntities(ctx, "test-server-id")
	if err != context.Canceled {
		t.Errorf("CollectEntities() error = %v, want context.Canceled", err)
	}
}

func TestCollectEntities_EmptyProcessList(t *testing.T) {
	mockProcs := &mockProcessLister{procs: []ProcessInfo{}}
	mockSvcs := &mockServiceLister{svcs: []ServiceInfo{{Name: "nginx", State: "active"}}}
	SetProcessLister(mockProcs)
	SetServiceLister(mockSvcs)
	defer SetProcessLister(&gopsutilProcessLister{})
	defer SetServiceLister(&gopsutilServiceLister{})

	batch, err := CollectEntities(context.Background(), "test-server-id")
	if err != nil {
		t.Fatalf("CollectEntities() error: %v", err)
	}
	if len(batch.Processes) != 0 {
		t.Errorf("len(Processes) = %d, want 0", len(batch.Processes))
	}
	if len(batch.Services) != 1 {
		t.Errorf("len(Services) = %d, want 1", len(batch.Services))
	}
}

func TestCollectEntities_EmptyServiceList(t *testing.T) {
	mockProcs := &mockProcessLister{procs: []ProcessInfo{{Name: "nginx", Status: "R"}}}
	mockSvcs := &mockServiceLister{svcs: []ServiceInfo{}}
	SetProcessLister(mockProcs)
	SetServiceLister(mockSvcs)
	defer SetProcessLister(&gopsutilProcessLister{})
	defer SetServiceLister(&gopsutilServiceLister{})

	batch, err := CollectEntities(context.Background(), "test-server-id")
	if err != nil {
		t.Fatalf("CollectEntities() error: %v", err)
	}
	if len(batch.Processes) != 1 {
		t.Errorf("len(Processes) = %d, want 1", len(batch.Processes))
	}
	if len(batch.Services) != 0 {
		t.Errorf("len(Services) = %d, want 0", len(batch.Services))
	}
}

// TestCollectEntities_Integration runs with real gopsutil (skipped in -short mode).
func TestCollectEntities_Integration(t *testing.T) {
	if testing.Short() {
		t.Skip("skipping integration test in -short mode")
	}
	SetProcessLister(&gopsutilProcessLister{})
	SetServiceLister(&gopsutilServiceLister{})
	batch, err := CollectEntities(context.Background(), "integration-test")
	if err != nil {
		t.Fatalf("CollectEntities() error: %v", err)
	}
	if len(batch.Processes) == 0 && len(batch.Services) == 0 {
		t.Log("No processes or services found (may be expected in test env)")
	}
	for _, p := range batch.Processes {
		if p.State != "running" && p.State != "unknown" {
			t.Errorf("process %s has invalid state: %s", p.Name, p.State)
		}
	}
	for _, s := range batch.Services {
		if s.State != "running" && s.State != "stopped" && s.State != "failed" && s.State != "unknown" {
			t.Errorf("service %s has invalid state: %s", s.Name, s.State)
		}
	}
}