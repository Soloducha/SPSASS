package collector

import (
	"github.com/shirou/gopsutil/v3/cpu"
	"github.com/shirou/gopsutil/v3/disk"
	"github.com/shirou/gopsutil/v3/load"
	"github.com/shirou/gopsutil/v3/mem"
)

// GopsutilSystemStats implements SystemStats using gopsutil v3.
type GopsutilSystemStats struct{}

func (g *GopsutilSystemStats) CPUPercent() (float64, error) {
	percents, err := cpu.Percent(0, false)
	if err != nil {
		return 0, err
	}
	if len(percents) == 0 {
		return 0, nil
	}
	return percents[0], nil
}

func (g *GopsutilSystemStats) VirtualMemory() (float64, error) {
	v, err := mem.VirtualMemory()
	if err != nil {
		return 0, err
	}
	return v.UsedPercent, nil
}

func (g *GopsutilSystemStats) DiskUsage(path string) (float64, error) {
	d, err := disk.Usage(path)
	if err != nil {
		return 0, err
	}
	return d.UsedPercent, nil
}

func (g *GopsutilSystemStats) LoadAvg() (float64, float64, float64, error) {
	l, err := load.Avg()
	if err != nil {
		return 0, 0, 0, err
	}
	return l.Load1, l.Load5, l.Load15, nil
}

// init registers the gopsutil implementation as default.
// This runs automatically when the package is imported.
func init() {
	defaultSystemStats = &GopsutilSystemStats{}
}