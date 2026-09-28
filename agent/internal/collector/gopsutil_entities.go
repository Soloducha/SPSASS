package collector

import (
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

// gopsutilServiceLister implements ServiceLister using gopsutil v3.
type gopsutilServiceLister struct{}

func (g *gopsutilServiceLister) ListServices() ([]ServiceInfo, error) {
	// NOTE: host.Services() was added in gopsutil v3.22.0+ but may not be available
	// in all versions. The current version (v3.24.5) in this project's go.mod
	// does not export it. On non-Linux or when unavailable, return empty slice.
	// A future update to gopsutil or a platform-specific implementation can add support.
	// For now, return empty slice with no error to not break the collection tick.
	return []ServiceInfo{}, nil
}

// init registers the gopsutil implementations as default.
// This runs automatically when the package is imported.
func init() {
	defaultProcessLister = &gopsutilProcessLister{}
	defaultServiceLister = &gopsutilServiceLister{}
}