package collector

import (
	"bytes"
	"os/exec"
	"runtime"
	"strings"

	"github.com/shirou/gopsutil/v3/process"
)

// gopsutilProcessLister implements ProcessLister using gopsutil v3.
type gopsutilProcessLister struct{}

func (g *gopsutilProcessLister) ListProcesses() ([]ProcessInfo, error) {
	procs, err := process.Processes()
	if err != nil {
		return nil, err
	}

	result := make([]ProcessInfo, 0, len(procs))
	for _, p := range procs {
		name, err := p.Name()
		if err != nil {
			name = ""
		}

		cmdline, err := p.Cmdline()
		if err != nil {
			cmdline = ""
		}

		statusSlice, err := p.Status()
		if err != nil {
			statusSlice = []string{}
		}

		status := ""
		if len(statusSlice) > 0 {
			status = statusSlice[0]
		}

		result = append(result, ProcessInfo{
			Name:    name,
			Cmdline: cmdline,
			Status:  status,
		})
	}
	return result, nil
}

// systemdServiceLister implements ServiceLister using systemctl on Linux.
type systemdServiceLister struct {
	// cmdRunner allows injecting a fake command runner for tests.
	cmdRunner func(name string, args ...string) ([]byte, error)
}

func (s *systemdServiceLister) ListServices() ([]ServiceInfo, error) {
	// Only run on Linux; on other platforms return empty slice silently.
	if runtime.GOOS != "linux" {
		return []ServiceInfo{}, nil
	}

	runner := s.cmdRunner
	if runner == nil {
		runner = defaultCmdRunner
	}

	// systemctl list-units --type=service --all --no-legend --no-pager
	// Output columns: UNIT LOAD ACTIVE SUB DESCRIPTION
	out, err := runner("systemctl", "list-units", "--type=service", "--all", "--no-legend", "--no-pager")
	if err != nil {
		// On error (systemctl missing, permission denied, etc.), return empty slice
		// to not break the collection tick. Log at caller level if needed.
		return []ServiceInfo{}, nil
	}

	return parseSystemctlOutput(out), nil
}

// defaultCmdRunner is the production command runner using exec.Command.
func defaultCmdRunner(name string, args ...string) ([]byte, error) {
	cmd := exec.Command(name, args...)
	var out bytes.Buffer
	cmd.Stdout = &out
	cmd.Stderr = &out
	err := cmd.Run()
	return out.Bytes(), err
}

// parseSystemctlOutput parses the output of `systemctl list-units --type=service --all --no-legend --no-pager`.
// Expected columns: UNIT LOAD ACTIVE SUB DESCRIPTION
// - UNIT: e.g., nginx.service (first token)
// - LOAD: loaded/not-loaded (ignored)
// - ACTIVE: active/inactive/failed/activating/deactivating
// - SUB: running/exited/dead/failed/auto-restart/etc.
// - DESCRIPTION: rest of line (may contain spaces)
func parseSystemctlOutput(output []byte) []ServiceInfo {
	lines := bytes.Split(output, []byte{'\n'})
	result := make([]ServiceInfo, 0, len(lines))

	for _, line := range lines {
		line = bytes.TrimSpace(line)
		if len(line) == 0 {
			continue
		}

		// Split on whitespace; we need at least 4 fields: UNIT LOAD ACTIVE SUB
		fields := bytes.Fields(line)
		if len(fields) < 4 {
			// Malformed line, skip it
			continue
		}

		// Extract name from UNIT (e.g., "nginx.service" -> "nginx")
		unitName := string(fields[0])
		name := strings.TrimSuffix(unitName, ".service")

		active := string(fields[2]) // ACTIVE column
		sub := string(fields[3])    // SUB column

		state := mapSystemdState(active, sub)

		result = append(result, ServiceInfo{
			Name:  name,
			State: state,
		})
	}
	return result
}

// mapSystemdState maps systemd ACTIVE+SUB to our internal state.
// ACTIVE: active, inactive, failed, activating, deactivating
// SUB: running, exited, dead, failed, auto-restart, etc.
func mapSystemdState(active, sub string) string {
	switch {
	case active == "active" && sub == "running":
		return "running"
	case active == "inactive" && sub == "dead":
		return "stopped"
	case active == "failed":
		return "failed"
	default:
		return "unknown"
	}
}

// gopsutilServiceLister is kept for backward compatibility but is deprecated.
// It now wraps the systemd lister.
type gopsutilServiceLister struct {
	systemd *systemdServiceLister
}

func (g *gopsutilServiceLister) ListServices() ([]ServiceInfo, error) {
	if g.systemd == nil {
		g.systemd = &systemdServiceLister{}
	}
	return g.systemd.ListServices()
}

// init registers the gopsutil implementations as default.
// This runs automatically when the package is imported.
func init() {
	defaultProcessLister = &gopsutilProcessLister{}
	defaultServiceLister = &gopsutilServiceLister{systemd: &systemdServiceLister{}}
}