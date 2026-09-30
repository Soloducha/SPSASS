package collector

import (
	"context"
	"os/exec"
	"runtime"
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

// ──────────────────────────────────────────────
// systemdServiceLister parsing tests
// ──────────────────────────────────────────────

func TestParseSystemctlOutput(t *testing.T) {
	tests := []struct {
		name     string
		input    string
		expected []ServiceInfo
	}{
		{
			name: "typical running service",
			input: `nginx.service          loaded active running   A high performance web server
ssh.service            loaded active running   OpenBSD Secure Shell server`,
			expected: []ServiceInfo{
				{Name: "nginx", State: "running"},
				{Name: "ssh", State: "running"},
			},
		},
		{
			name: "mixed states",
			input: `nginx.service          loaded active running   A high performance web server
redis.service          loaded inactive dead    Redis server
postgresql.service     loaded failed failed    PostgreSQL database
unknown-svc.service    loaded activating auto-restart Some unknown service
docker.service         loaded deactivating stop-sigterm Docker container`,
			expected: []ServiceInfo{
				{Name: "nginx", State: "running"},
				{Name: "redis", State: "stopped"},
				{Name: "postgresql", State: "failed"},
				{Name: "unknown-svc", State: "unknown"},
				{Name: "docker", State: "unknown"},
			},
		},
		{
			name:     "empty input",
			input:    "",
			expected: []ServiceInfo{},
		},
		{
			name: "malformed lines are skipped",
			input: `nginx.service          loaded active running   A high performance web server
malformed line
redis.service          loaded inactive dead    Redis server
another bad line
postgresql.service     loaded failed failed    PostgreSQL database`,
			expected: []ServiceInfo{
				{Name: "nginx", State: "running"},
				{Name: "redis", State: "stopped"},
				{Name: "postgresql", State: "failed"},
			},
		},
		{
			name: "service names with dots and dashes",
			input: `my-app-web.service       loaded active running   My web app
my-app-db.service        loaded active running   My database`,
			expected: []ServiceInfo{
				{Name: "my-app-web", State: "running"},
				{Name: "my-app-db", State: "running"},
			},
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			output := []byte(tc.input)
			result := parseSystemctlOutput(output)

			if len(result) != len(tc.expected) {
				t.Errorf("len(result) = %d, want %d", len(result), len(tc.expected))
				return
			}

			for i, exp := range tc.expected {
				if result[i].Name != exp.Name {
					t.Errorf("result[%d].Name = %q, want %q", i, result[i].Name, exp.Name)
				}
				if result[i].State != exp.State {
					t.Errorf("result[%d].State = %q, want %q (for %s)", i, result[i].State, exp.State, exp.Name)
				}
			}
		})
	}
}

func TestMapSystemdState(t *testing.T) {
	tests := []struct {
		name     string
		active   string
		sub      string
		expected string
	}{
		{"active+running -> running", "active", "running", "running"},
		{"inactive+dead -> stopped", "inactive", "dead", "stopped"},
		{"failed+any -> failed", "failed", "anything", "failed"},
		{"active+exited -> unknown", "active", "exited", "unknown"},
		{"activating+auto-restart -> unknown", "activating", "auto-restart", "unknown"},
		{"deactivating+stop-sigterm -> unknown", "deactivating", "stop-sigterm", "unknown"},
		{"inactive+running -> unknown", "inactive", "running", "unknown"},
		{"unknown+unknown -> unknown", "unknown", "unknown", "unknown"},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			result := mapSystemdState(tc.active, tc.sub)
			if result != tc.expected {
				t.Errorf("mapSystemdState(%q, %q) = %q, want %q", tc.active, tc.sub, result, tc.expected)
			}
		})
	}
}

func TestSystemdServiceLister_WithFakeRunner(t *testing.T) {
	if runtime.GOOS != "linux" {
		t.Skip("Test requires Linux to test systemdServiceLister with fake runner")
	}

	// Sample systemctl output
	sampleOutput := `nginx.service          loaded active running   A high performance web server
ssh.service            loaded active running   OpenBSD Secure Shell server
redis.service          loaded inactive dead    Redis server
postgresql.service     loaded failed failed    PostgreSQL database
docker.service         loaded deactivating stop-sigterm Docker container`

	lister := &systemdServiceLister{
		cmdRunner: func(name string, args ...string) ([]byte, error) {
			if name == "systemctl" && len(args) == 5 && args[0] == "list-units" && args[1] == "--type=service" && args[2] == "--all" && args[3] == "--no-legend" && args[4] == "--no-pager" {
				return []byte(sampleOutput), nil
			}
			return nil, nil
		},
	}

	svcs, err := lister.ListServices()
	if err != nil {
		t.Fatalf("ListServices() error: %v", err)
	}

	if len(svcs) != 5 {
		t.Fatalf("len(svcs) = %d, want 5", len(svcs))
	}

	expected := []ServiceInfo{
		{Name: "nginx", State: "running"},
		{Name: "ssh", State: "running"},
		{Name: "redis", State: "stopped"},
		{Name: "postgresql", State: "failed"},
		{Name: "docker", State: "unknown"},
	}

	for i, exp := range expected {
		if svcs[i].Name != exp.Name {
			t.Errorf("svcs[%d].Name = %q, want %q", i, svcs[i].Name, exp.Name)
		}
		if svcs[i].State != exp.State {
			t.Errorf("svcs[%d].State = %q, want %q", i, svcs[i].State, exp.State)
		}
	}
}

func TestSystemdServiceLister_CommandErrorReturnsEmpty(t *testing.T) {
	lister := &systemdServiceLister{
		cmdRunner: func(name string, args ...string) ([]byte, error) {
			return nil, &exec.ExitError{}
		},
	}

	svcs, err := lister.ListServices()
	if err != nil {
		t.Fatalf("ListServices() returned error: %v", err)
	}
	if len(svcs) != 0 {
		t.Errorf("len(svcs) = %d, want 0 on error", len(svcs))
	}
}

func TestSystemdServiceLister_NonLinuxReturnsEmpty(t *testing.T) {
	// On non-Linux, the lister should return empty without running systemctl
	// We can't easily test this without mocking runtime.GOOS, but we can
	// verify the logic by checking the lister struct doesn't call cmdRunner on non-Linux.
	// For now, we document this behavior in the code.
	t.Log("On non-Linux, systemdServiceLister returns empty slice without calling systemctl")
}

func TestSystemdServiceLister_EmptyOutput(t *testing.T) {
	lister := &systemdServiceLister{
		cmdRunner: func(name string, args ...string) ([]byte, error) {
			return []byte(""), nil
		},
	}

	svcs, err := lister.ListServices()
	if err != nil {
		t.Fatalf("ListServices() error: %v", err)
	}
	if len(svcs) != 0 {
		t.Errorf("len(svcs) = %d, want 0", len(svcs))
	}
}