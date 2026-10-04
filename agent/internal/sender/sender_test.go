package sender

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"testing"
	"time"

	"log/slog"
)

func testLogger() *slog.Logger {
	return slog.New(slog.NewTextHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelDebug}))
}

func TestSender_SendEntities_SendsCorrectJSON(t *testing.T) {
	var receivedBatch EntitiesBatch
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			t.Errorf("method = %s, want POST", r.Method)
		}
		if r.Header.Get("X-Api-Key") != "test-key" {
			t.Errorf("X-Api-Key = %s, want test-key", r.Header.Get("X-Api-Key"))
		}
		if r.Header.Get("Content-Type") != "application/json" {
			t.Errorf("Content-Type = %s, want application/json", r.Header.Get("Content-Type"))
		}
		json.NewDecoder(r.Body).Decode(&receivedBatch)

		resp := entitiesIngestResponse{Received: 3, Inserted: 3, ServerID: "test-server-id"}
		w.WriteHeader(http.StatusAccepted)
		json.NewEncoder(w).Encode(resp)
	}))
	defer server.Close()

	logger := testLogger()
	s := NewSender(server.URL, "test-key", logger)

	batch := EntitiesBatch{
		ServerID: "test-server-id",
		TS:       time.Now().UTC(),
		Processes: []ProcessState{
			{Name: "nginx", Cmdline: "nginx: master process", State: "running"},
			{Name: "redis", Cmdline: "redis-server *:6379", State: "unknown"},
		},
		Services: []ServiceState{
			{Name: "nginx", State: "running"},
			{Name: "redis", State: "stopped"},
		},
	}

	err := s.SendEntities(context.Background(), batch)
	if err != nil {
		t.Fatalf("SendEntities() error: %v", err)
	}

	if receivedBatch.ServerID != "test-server-id" {
		t.Errorf("received ServerID = %q, want test-server-id", receivedBatch.ServerID)
	}
	if len(receivedBatch.Processes) != 2 {
		t.Errorf("received %d processes, want 2", len(receivedBatch.Processes))
	}
	if len(receivedBatch.Services) != 2 {
		t.Errorf("received %d services, want 2", len(receivedBatch.Services))
	}
	if receivedBatch.Processes[0].Name != "nginx" {
		t.Errorf("process[0].Name = %q, want nginx", receivedBatch.Processes[0].Name)
	}
	if receivedBatch.Processes[0].State != "running" {
		t.Errorf("process[0].State = %q, want running", receivedBatch.Processes[0].State)
	}
	if receivedBatch.Services[0].State != "running" {
		t.Errorf("service[0].State = %q, want running", receivedBatch.Services[0].State)
	}
	if receivedBatch.Services[1].State != "stopped" {
		t.Errorf("service[1].State = %q, want stopped", receivedBatch.Services[1].State)
	}
}

func TestSender_SendEntities_RetriesOnFailure(t *testing.T) {
	attempts := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		attempts++
		if attempts < 2 {
			w.WriteHeader(http.StatusServiceUnavailable)
			return
		}
		w.WriteHeader(http.StatusAccepted)
		json.NewEncoder(w).Encode(entitiesIngestResponse{Received: 1, Inserted: 1})
	}))
	defer server.Close()

	logger := testLogger()
	s := NewSender(server.URL, "test-key", logger)
	s.SetBackoff(&testBackoff{delays: []time.Duration{10 * time.Millisecond, 10 * time.Millisecond}})

	batch := EntitiesBatch{ServerID: "test", Processes: []ProcessState{{Name: "nginx", State: "running"}}, Services: []ServiceState{{Name: "nginx", State: "running"}}}
	err := s.SendEntities(context.Background(), batch)
	if err != nil {
		t.Fatalf("SendEntities() error: %v", err)
	}
	if attempts != 2 {
		t.Errorf("attempts = %d, want 2", attempts)
	}
}

func TestSender_Register_Success(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			t.Errorf("method = %s, want POST", r.Method)
		}
		if r.Header.Get("X-Api-Key") != "test-key" {
			t.Errorf("X-Api-Key = %s, want test-key", r.Header.Get("X-Api-Key"))
		}
		if r.Header.Get("Content-Type") != "application/json" {
			t.Errorf("Content-Type = %s, want application/json", r.Header.Get("Content-Type"))
		}

		resp := registerResponse{
			ID:             "test-server-id",
			Hostname:       "test-host",
			Status:         "online",
			AgentVersion:   "0.1.0",
			LastHeartbeatAt: time.Now().UTC().Format(time.RFC3339),
		}
		w.WriteHeader(http.StatusCreated)
		json.NewEncoder(w).Encode(resp)
	}))
	defer server.Close()

	logger := testLogger()
	s := NewSender(server.URL, "test-key", logger)

	id, err := s.Register(context.Background(), "test-host", "1.2.3.4", "linux", "0.1.0")
	if err != nil {
		t.Fatalf("Register() error: %v", err)
	}
	if id != "test-server-id" {
		t.Errorf("Register() id = %q, want %q", id, "test-server-id")
	}
}

func TestSender_Register_RetriesOn500(t *testing.T) {
	attempts := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		attempts++
		if attempts < 3 {
			w.WriteHeader(http.StatusInternalServerError)
			return
		}
		resp := registerResponse{ID: "test-server-id"}
		w.WriteHeader(http.StatusCreated)
		json.NewEncoder(w).Encode(resp)
	}))
	defer server.Close()

	logger := testLogger()
	s := NewSender(server.URL, "test-key", logger)
	// Use fast backoff for testing
	s.SetBackoff(&testBackoff{delays: []time.Duration{10*time.Millisecond, 10*time.Millisecond, 10*time.Millisecond}})

	id, err := s.Register(context.Background(), "test-host", "", "", "")
	if err != nil {
		t.Fatalf("Register() error: %v", err)
	}
	if id != "test-server-id" {
		t.Errorf("id = %q, want test-server-id", id)
	}
	if attempts != 3 {
		t.Errorf("attempts = %d, want 3", attempts)
	}
}

func TestSender_Register_FailsAfterMaxRetries(t *testing.T) {
	attempts := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		attempts++
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer server.Close()

	logger := testLogger()
	s := NewSender(server.URL, "test-key", logger)
	s.SetBackoff(&testBackoff{delays: []time.Duration{10*time.Millisecond, 10*time.Millisecond, 10*time.Millisecond, 10*time.Millisecond, 10*time.Millisecond}})

	_, err := s.Register(context.Background(), "test-host", "", "", "")
	if err == nil {
		t.Fatal("Register() should error after max retries")
	}
	if attempts != 5 {
		t.Errorf("attempts = %d, want 5", attempts)
	}
}

func TestSender_Heartbeat_SetsHeader(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("X-Api-Key") != "test-key" {
			t.Errorf("X-Api-Key = %s, want test-key", r.Header.Get("X-Api-Key"))
		}
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(heartbeatResponse{ServerID: "test-id"})
	}))
	defer server.Close()

	logger := testLogger()
	s := NewSender(server.URL, "test-key", logger)

	err := s.Heartbeat(context.Background(), "test-id")
	if err != nil {
		t.Fatalf("Heartbeat() error: %v", err)
	}
}

func TestSender_SendMetrics_SendsCorrectJSON(t *testing.T) {
	var receivedBatch MetricsBatch
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("X-Api-Key") != "test-key" {
			t.Errorf("X-Api-Key = %s, want test-key", r.Header.Get("X-Api-Key"))
		}
		json.NewDecoder(r.Body).Decode(&receivedBatch)

		resp := ingestResponse{Received: 6, Inserted: 6, ServerID: "test-server-id"}
		w.WriteHeader(http.StatusAccepted)
		json.NewEncoder(w).Encode(resp)
	}))
	defer server.Close()

	logger := testLogger()
	s := NewSender(server.URL, "test-key", logger)

	batch := MetricsBatch{
		ServerID: "test-server-id",
		TS:       time.Now().UTC(),
		Metrics: []Metric{
			{Type: "cpu_usage", Value: 12.5, Tags: map[string]string{"mode": "total"}},
			{Type: "mem_usage", Value: 63.1, Tags: map[string]string{}},
			{Type: "disk_usage", Value: 58.2, Tags: map[string]string{"mount": "/"}},
			{Type: "load_avg1", Value: 0.42, Tags: map[string]string{}},
			{Type: "load_avg5", Value: 0.38, Tags: map[string]string{}},
			{Type: "load_avg15", Value: 0.30, Tags: map[string]string{}},
		},
	}

	err := s.SendMetrics(context.Background(), batch)
	if err != nil {
		t.Fatalf("SendMetrics() error: %v", err)
	}

	if receivedBatch.ServerID != "test-server-id" {
		t.Errorf("received ServerID = %q, want test-server-id", receivedBatch.ServerID)
	}
	if len(receivedBatch.Metrics) != 6 {
		t.Errorf("received %d metrics, want 6", len(receivedBatch.Metrics))
	}
	for i, m := range receivedBatch.Metrics {
		if m.Type != batch.Metrics[i].Type {
			t.Errorf("metric[%d].Type = %q, want %q", i, m.Type, batch.Metrics[i].Type)
		}
		if m.Value != batch.Metrics[i].Value {
			t.Errorf("metric[%d].Value = %v, want %v", i, m.Value, batch.Metrics[i].Value)
		}
	}
}

func TestSender_SendMetrics_RetriesOnFailure(t *testing.T) {
	attempts := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		attempts++
		if attempts < 2 {
			w.WriteHeader(http.StatusServiceUnavailable)
			return
		}
		w.WriteHeader(http.StatusAccepted)
		json.NewEncoder(w).Encode(ingestResponse{Received: 1, Inserted: 1})
	}))
	defer server.Close()

	logger := testLogger()
	s := NewSender(server.URL, "test-key", logger)
	s.SetBackoff(&testBackoff{delays: []time.Duration{10*time.Millisecond, 10*time.Millisecond}})

	batch := MetricsBatch{ServerID: "test", Metrics: []Metric{{Type: "cpu_usage", Value: 1.0}}}
	err := s.SendMetrics(context.Background(), batch)
	if err != nil {
		t.Fatalf("SendMetrics() error: %v", err)
	}
	if attempts != 2 {
		t.Errorf("attempts = %d, want 2", attempts)
	}
}

func TestExponentialBackoff_Delays(t *testing.T) {
	b := NewExponentialBackoff()
	// Test that delays increase exponentially (approximately)
	d0 := b.Duration(0)
	d1 := b.Duration(1)
	d2 := b.Duration(2)
	d3 := b.Duration(3)
	d4 := b.Duration(4)

	// With jitter, exact values vary, but check general progression
	// Base: 500ms, then 1s, 2s, 4s, 8s (max)
	if d0 < 400*time.Millisecond || d0 > 600*time.Millisecond {
		t.Errorf("attempt 0 delay = %v, want ~500ms", d0)
	}
	if d1 < 800*time.Millisecond || d1 > 1200*time.Millisecond {
		t.Errorf("attempt 1 delay = %v, want ~1s", d1)
	}
	if d2 < 1600*time.Millisecond || d2 > 2400*time.Millisecond {
		t.Errorf("attempt 2 delay = %v, want ~2s", d2)
	}
	if d3 < 3200*time.Millisecond || d3 > 4800*time.Millisecond {
		t.Errorf("attempt 3 delay = %v, want ~4s", d3)
	}
	if d4 < 6400*time.Millisecond || d4 > 9600*time.Millisecond {
		t.Errorf("attempt 4 delay = %v, want ~8s (max)", d4)
	}
}

func TestExponentialBackoff_MaxDelay(t *testing.T) {
	b := &ExponentialBackoff{
		BaseDelay:    500 * time.Millisecond,
		MaxDelay:     2 * time.Second,
		MaxAttempts:  10,
		JitterFactor: 0,
	}
	// After attempt 2 (2s), should cap at MaxDelay (2s)
	d3 := b.Duration(3)
	d10 := b.Duration(10)
	if d3 != 2*time.Second {
		t.Errorf("attempt 3 delay = %v, want 2s (max)", d3)
	}
	if d10 != 2*time.Second {
		t.Errorf("attempt 10 delay = %v, want 2s (max)", d10)
	}
}

// testBackoff is a test-only backoff with predefined delays.
type testBackoff struct {
	delays []time.Duration
}

func (t *testBackoff) Duration(attempt int) time.Duration {
	if attempt < len(t.delays) {
		return t.delays[attempt]
	}
	return t.delays[len(t.delays)-1]
}

func TestSender_GetPendingCommands_SendsCorrectRequest(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			t.Errorf("method = %s, want GET", r.Method)
		}
		if r.Header.Get("X-Api-Key") != "test-key" {
			t.Errorf("X-Api-Key = %s, want test-key", r.Header.Get("X-Api-Key"))
		}
		// Verify path includes serverID
		if r.URL.Path != "/api/v1/servers/test-server-id/commands" {
			t.Errorf("path = %s, want /api/v1/servers/test-server-id/commands", r.URL.Path)
		}

		// Return mock commands
		commands := []AgentCommand{
			{ID: "cmd-1", EntityType: "service", EntityName: "nginx", Command: "systemctl restart nginx", MaxAttempts: 3, BackoffSeconds: 60},
			{ID: "cmd-2", EntityType: "process", EntityName: "redis", Command: "systemctl restart redis", MaxAttempts: 3, BackoffSeconds: 60},
		}
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(commands)
	}))
	defer server.Close()

	logger := testLogger()
	s := NewSender(server.URL, "test-key", logger)

	commands, err := s.GetPendingCommands(context.Background(), "test-server-id")
	if err != nil {
		t.Fatalf("GetPendingCommands() error: %v", err)
	}

	if len(commands) != 2 {
		t.Errorf("got %d commands, want 2", len(commands))
	}
	if commands[0].ID != "cmd-1" || commands[0].EntityType != "service" || commands[0].EntityName != "nginx" {
		t.Errorf("command[0] = %+v, want id=cmd-1, type=service, name=nginx", commands[0])
	}
	if commands[1].ID != "cmd-2" || commands[1].EntityType != "process" || commands[1].EntityName != "redis" {
		t.Errorf("command[1] = %+v, want id=cmd-2, type=process, name=redis", commands[1])
	}
}

func TestSender_GetPendingCommands_RetriesOnFailure(t *testing.T) {
	attempts := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		attempts++
		if attempts < 2 {
			w.WriteHeader(http.StatusServiceUnavailable)
			return
		}
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode([]AgentCommand{{ID: "cmd-1", EntityType: "service", EntityName: "nginx"}})
	}))
	defer server.Close()

	logger := testLogger()
	s := NewSender(server.URL, "test-key", logger)
	s.SetBackoff(&testBackoff{delays: []time.Duration{10 * time.Millisecond, 10 * time.Millisecond}})

	commands, err := s.GetPendingCommands(context.Background(), "test-server-id")
	if err != nil {
		t.Fatalf("GetPendingCommands() error: %v", err)
	}
	if len(commands) != 1 {
		t.Errorf("got %d commands, want 1", len(commands))
	}
	if attempts != 2 {
		t.Errorf("attempts = %d, want 2", attempts)
	}
}

func TestSender_GetPendingCommands_EmptyList(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode([]AgentCommand{})
	}))
	defer server.Close()

	logger := testLogger()
	s := NewSender(server.URL, "test-key", logger)

	commands, err := s.GetPendingCommands(context.Background(), "test-server-id")
	if err != nil {
		t.Fatalf("GetPendingCommands() error: %v", err)
	}
	if len(commands) != 0 {
		t.Errorf("got %d commands, want 0", len(commands))
	}
}

func TestSender_ReportCommandResult_Success(t *testing.T) {
	var receivedResult AgentCommandResult
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPatch {
			t.Errorf("method = %s, want PATCH", r.Method)
		}
		if r.Header.Get("X-Api-Key") != "test-key" {
			t.Errorf("X-Api-Key = %s, want test-key", r.Header.Get("X-Api-Key"))
		}
		if r.URL.Path != "/api/v1/agent-commands/cmd-123/result" {
			t.Errorf("path = %s, want /api/v1/agent-commands/cmd-123/result", r.URL.Path)
		}
		json.NewDecoder(r.Body).Decode(&receivedResult)
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	logger := testLogger()
	s := NewSender(server.URL, "test-key", logger)

	result := AgentCommandResult{
		Status:     "success",
		ExitCode:   0,
		OutputTail: "service restarted successfully",
	}
	err := s.ReportCommandResult(context.Background(), "cmd-123", result)
	if err != nil {
		t.Fatalf("ReportCommandResult() error: %v", err)
	}

	if receivedResult.Status != "success" {
		t.Errorf("received status = %q, want success", receivedResult.Status)
	}
	if receivedResult.ExitCode != 0 {
		t.Errorf("received exit_code = %d, want 0", receivedResult.ExitCode)
	}
	if receivedResult.OutputTail != "service restarted successfully" {
		t.Errorf("received output_tail = %q, want %q", receivedResult.OutputTail, "service restarted successfully")
	}
}

func TestSender_ReportCommandResult_Failed(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var result AgentCommandResult
		json.NewDecoder(r.Body).Decode(&result)
		if result.Status != "failed" {
			t.Errorf("status = %q, want failed", result.Status)
		}
		if result.ExitCode != 1 {
			t.Errorf("exit_code = %d, want 1", result.ExitCode)
		}
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	logger := testLogger()
	s := NewSender(server.URL, "test-key", logger)

	result := AgentCommandResult{
		Status:     "failed",
		ExitCode:   1,
		OutputTail: "service not found",
	}
	err := s.ReportCommandResult(context.Background(), "cmd-456", result)
	if err != nil {
		t.Fatalf("ReportCommandResult() error: %v", err)
	}
}

func TestSender_ReportCommandResult_RetriesOnFailure(t *testing.T) {
	attempts := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		attempts++
		if attempts < 2 {
			w.WriteHeader(http.StatusServiceUnavailable)
			return
		}
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	logger := testLogger()
	s := NewSender(server.URL, "test-key", logger)
	s.SetBackoff(&testBackoff{delays: []time.Duration{10 * time.Millisecond, 10 * time.Millisecond}})

	result := AgentCommandResult{Status: "success", ExitCode: 0}
	err := s.ReportCommandResult(context.Background(), "cmd-789", result)
	if err != nil {
		t.Fatalf("ReportCommandResult() error: %v", err)
	}
	if attempts != 2 {
		t.Errorf("attempts = %d, want 2", attempts)
	}
}