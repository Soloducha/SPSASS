package collector

import (
	"bytes"
	"context"
	"os/exec"
	"runtime"
)

// CommandExecutor executes restart commands for services and processes.
type CommandExecutor interface {
	ExecuteRestart(ctx context.Context, entityType, entityName, customCommand string) (exitCode int, output string, err error)
}

// defaultCommandExecutor is the production implementation.
type defaultCommandExecutor struct{}

var defaultExecutor CommandExecutor = &defaultCommandExecutor{}

// SetCommandExecutor replaces the command executor (for testing).
func SetCommandExecutor(e CommandExecutor) {
	defaultExecutor = e
}

// ExecuteRestart executes a restart command using the default executor.
func ExecuteRestart(ctx context.Context, entityType, entityName, customCommand string) (int, string, error) {
	return defaultExecutor.ExecuteRestart(ctx, entityType, entityName, customCommand)
}

// ExecuteRestart executes a restart command for a service or process.
func (e *defaultCommandExecutor) ExecuteRestart(ctx context.Context, entityType, entityName, customCommand string) (int, string, error) {
	var cmd *exec.Cmd

	if customCommand != "" {
		// Custom command provided - execute as shell
		cmd = exec.CommandContext(ctx, "sh", "-c", customCommand)
	} else {
		// Default commands based on entity type and OS
		switch entityType {
		case "service":
			if runtime.GOOS == "windows" {
				// Windows: sc stop + sc start
				cmd = exec.CommandContext(ctx, "cmd", "/c", "sc stop "+entityName+" && sc start "+entityName)
			} else {
				// Linux: systemctl restart
				cmd = exec.CommandContext(ctx, "systemctl", "restart", entityName)
			}
		case "process":
			if runtime.GOOS == "windows" {
				// Windows: taskkill /F /IM
				cmd = exec.CommandContext(ctx, "cmd", "/c", "taskkill /F /IM "+entityName)
			} else {
				// Linux: pkill -f pattern
				cmd = exec.CommandContext(ctx, "pkill", "-f", entityName)
			}
		default:
			return -1, "", ErrUnknownEntityType
		}
	}

	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	err := cmd.Run()
	exitCode := 0
	if err != nil {
		if exitErr, ok := err.(*exec.ExitError); ok {
			exitCode = exitErr.ExitCode()
		} else {
			exitCode = -1
		}
	}

	output := stdout.String()
	if stderr.Len() > 0 {
		if output != "" {
			output += "\n"
		}
		output += stderr.String()
	}

	return exitCode, output, nil
}

// ErrUnknownEntityType is returned when entity type is not recognized.
var ErrUnknownEntityType = &collectorError{"unknown entity type"}

type collectorError struct {
	msg string
}

func (e *collectorError) Error() string {
	return e.msg
}