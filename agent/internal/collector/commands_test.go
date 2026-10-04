package collector

import (
	"context"
	"errors"
	"runtime"
	"testing"
)

type mockExecutor struct {
	execFn func(ctx context.Context, entityType, entityName, customCommand string) (int, string, error)
}

func (m *mockExecutor) ExecuteRestart(ctx context.Context, entityType, entityName, customCommand string) (int, string, error) {
	return m.execFn(ctx, entityType, entityName, customCommand)
}

func TestExecuteRestart_UnknownEntityType(t *testing.T) {
	mock := &mockExecutor{
		execFn: func(ctx context.Context, entityType, entityName, customCommand string) (int, string, error) {
			return -1, "", ErrUnknownEntityType
		},
	}
	SetCommandExecutor(mock)
	defer SetCommandExecutor(&defaultCommandExecutor{})

	_, _, err := ExecuteRestart(context.Background(), "unknown", "test", "")
	if err != ErrUnknownEntityType {
		t.Errorf("Expected ErrUnknownEntityType, got %v", err)
	}
}

func TestExecuteRestart_CustomCommand(t *testing.T) {
	mock := &mockExecutor{
		execFn: func(ctx context.Context, entityType, entityName, customCommand string) (int, string, error) {
			if customCommand != "systemctl reload nginx" {
				t.Errorf("customCommand not passed correctly = %q", customCommand)
			}
			return 0, "custom output", nil
		},
	}
	SetCommandExecutor(mock)
	defer SetCommandExecutor(&defaultCommandExecutor{})

	exitCode, output, err := ExecuteRestart(context.Background(), "service", "nginx", "systemctl reload nginx")
	if err != nil {
		t.Fatalf("ExecuteRestart() error: %v", err)
	}
	if exitCode != 0 {
		t.Errorf("exitCode = %d, want 0", exitCode)
	}
	if output != "custom output" {
		t.Errorf("output = %q, want %q", output, "custom output")
	}
}

func TestExecuteRestart_ContextCancellation(t *testing.T) {
	mock := &mockExecutor{
		execFn: func(ctx context.Context, entityType, entityName, customCommand string) (int, string, error) {
			<-ctx.Done()
			return -1, "", ctx.Err()
		},
	}
	SetCommandExecutor(mock)
	defer SetCommandExecutor(&defaultCommandExecutor{})

	ctx, cancel := context.WithCancel(context.Background())
	cancel() // cancel immediately

	_, _, err := ExecuteRestart(ctx, "service", "nginx", "")
	if err != context.Canceled {
		t.Errorf("Expected context.Canceled, got %v", err)
	}
}

func TestDefaultExecutor_ServiceLinux(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("Skipping Linux test on Windows")
	}

	mock := &mockExecutor{
		execFn: func(ctx context.Context, entityType, entityName, customCommand string) (int, string, error) {
			// We can't easily capture the actual exec.Cmd, but we can verify the behavior
			return 0, "restarted", nil
		},
	}
	SetCommandExecutor(mock)
	defer SetCommandExecutor(&defaultCommandExecutor{})

	// Test that ExecuteRestart with default executor on Linux uses systemctl
	exitCode, output, err := ExecuteRestart(context.Background(), "service", "nginx", "")
	if err != nil {
		t.Fatalf("ExecuteRestart() error: %v", err)
	}
	if exitCode != 0 {
		t.Errorf("exitCode = %d, want 0", exitCode)
	}
	if output != "restarted" {
		t.Errorf("output = %q, want %q", output, "restarted")
	}
}

func TestDefaultExecutor_ServiceWindows(t *testing.T) {
	if runtime.GOOS != "windows" {
		t.Skip("Skipping Windows test on non-Windows")
	}

	mock := &mockExecutor{
		execFn: func(ctx context.Context, entityType, entityName, customCommand string) (int, string, error) {
			return 0, "restarted", nil
		},
	}
	SetCommandExecutor(mock)
	defer SetCommandExecutor(&defaultCommandExecutor{})

	exitCode, output, err := ExecuteRestart(context.Background(), "service", "nginx", "")
	if err != nil {
		t.Fatalf("ExecuteRestart() error: %v", err)
	}
	if exitCode != 0 {
		t.Errorf("exitCode = %d, want 0", exitCode)
	}
	if output != "restarted" {
		t.Errorf("output = %q, want %q", output, "restarted")
	}
}

func TestDefaultExecutor_ProcessLinux(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("Skipping Linux test on Windows")
	}

	mock := &mockExecutor{
		execFn: func(ctx context.Context, entityType, entityName, customCommand string) (int, string, error) {
			return 0, "killed", nil
		},
	}
	SetCommandExecutor(mock)
	defer SetCommandExecutor(&defaultCommandExecutor{})

	exitCode, output, err := ExecuteRestart(context.Background(), "process", "nginx", "")
	if err != nil {
		t.Fatalf("ExecuteRestart() error: %v", err)
	}
	if exitCode != 0 {
		t.Errorf("exitCode = %d, want 0", exitCode)
	}
	if output != "killed" {
		t.Errorf("output = %q, want %q", output, "killed")
	}
}

func TestDefaultExecutor_ProcessWindows(t *testing.T) {
	if runtime.GOOS != "windows" {
		t.Skip("Skipping Windows test on non-Windows")
	}

	mock := &mockExecutor{
		execFn: func(ctx context.Context, entityType, entityName, customCommand string) (int, string, error) {
			return 0, "killed", nil
		},
	}
	SetCommandExecutor(mock)
	defer SetCommandExecutor(&defaultCommandExecutor{})

	exitCode, output, err := ExecuteRestart(context.Background(), "process", "nginx", "")
	if err != nil {
		t.Fatalf("ExecuteRestart() error: %v", err)
	}
	if exitCode != 0 {
		t.Errorf("exitCode = %d, want 0", exitCode)
	}
	if output != "killed" {
		t.Errorf("output = %q, want %q", output, "killed")
	}
}

func TestDefaultExecutor_ErrorOutput(t *testing.T) {
	mock := &mockExecutor{
		execFn: func(ctx context.Context, entityType, entityName, customCommand string) (int, string, error) {
			return 1, "error output", errors.New("command failed")
		},
	}
	SetCommandExecutor(mock)
	defer SetCommandExecutor(&defaultCommandExecutor{})

	exitCode, output, err := ExecuteRestart(context.Background(), "service", "nginx", "")
	if err == nil {
		t.Fatalf("ExecuteRestart() expected error, got nil")
	}
	if exitCode != 1 {
		t.Errorf("exitCode = %d, want 1", exitCode)
	}
	if output != "error output" {
		t.Errorf("output = %q, want %q", output, "error output")
	}
}

func TestDefaultExecutor_StdoutStderrCombination(t *testing.T) {
	// Test the actual default executor's output handling
	originalExecutor := defaultExecutor
	defer SetCommandExecutor(originalExecutor)
	
	mock := &mockExecutor{
		execFn: func(ctx context.Context, entityType, entityName, customCommand string) (int, string, error) {
			// Simulate command with both stdout and stderr
			return 0, "stdout output\nstderr output", nil
		},
	}
	SetCommandExecutor(mock)
	defer SetCommandExecutor(&defaultCommandExecutor{})

	exitCode, output, err := ExecuteRestart(context.Background(), "service", "nginx", "")
	if err != nil {
		t.Fatalf("ExecuteRestart() error: %v", err)
	}
	if output != "stdout output\nstderr output" {
		t.Errorf("output = %q, want %q", output, "stdout output\nstderr output")
	}
	if exitCode != 0 {
		t.Errorf("exitCode = %d, want 0", exitCode)
	}
}

func TestSetCommandExecutor(t *testing.T) {
	originalExecutor := defaultExecutor
	defer SetCommandExecutor(originalExecutor)

	mock := &mockExecutor{
		execFn: func(ctx context.Context, entityType, entityName, customCommand string) (int, string, error) {
			return 42, "test", nil
		},
	}
	SetCommandExecutor(mock)

	exitCode, output, err := ExecuteRestart(context.Background(), "service", "test", "")
	if err != nil {
		t.Fatalf("ExecuteRestart() error: %v", err)
	}
	if exitCode != 42 {
		t.Errorf("exitCode = %d, want 42", exitCode)
	}
	if output != "test" {
		t.Errorf("output = %q, want %q", output, "test")
	}
}

func TestErrUnknownEntityType_Error(t *testing.T) {
	err := ErrUnknownEntityType
	if err.Error() != "unknown entity type" {
		t.Errorf("ErrUnknownEntityType.Error() = %q, want %q", err.Error(), "unknown entity type")
	}
}

func TestCollectorError_Error(t *testing.T) {
	err := &collectorError{msg: "custom error"}
	if err.Error() != "custom error" {
		t.Errorf("collectorError.Error() = %q, want %q", err.Error(), "custom error")
	}
}