package config

import (
	"flag"
	"os"
	"time"
)

type Config struct {
	APIURL       string
	APIKey       string
	Hostname     string
	Interval     time.Duration
	AgentVersion string
	IP           string
}

func Load() *Config {
	return LoadWithFlags(flag.CommandLine, nil)
}

func LoadWithFlags(fs *flag.FlagSet, args []string) *Config {
	cfg := &Config{}

	fs.StringVar(&cfg.APIURL, "api-url", "", "API base URL (default: http://localhost:8000)")
	fs.StringVar(&cfg.APIKey, "api-key", "", "API key for authentication (required)")
	fs.StringVar(&cfg.Hostname, "hostname", "", "Server hostname (default: os.Hostname())")
	fs.DurationVar(&cfg.Interval, "interval", 0, "Collection interval (default: 30s)")
	fs.StringVar(&cfg.AgentVersion, "agent-version", "", "Agent version (default: 0.1.0)")
	fs.StringVar(&cfg.IP, "ip", "", "Server IP address (optional, auto-detected if empty)")

	// Parse only if not already parsed
	if !fs.Parsed() {
		if args == nil {
			args = os.Args[1:]
		}
		fs.Parse(args)
	}

	// Apply env var fallbacks
	if cfg.APIURL == "" {
		cfg.APIURL = getEnv("SPSAAS_API_URL", "http://localhost:8000")
	}
	if cfg.APIKey == "" {
		cfg.APIKey = getEnv("SPSAAS_API_KEY", "")
	}
	if cfg.Hostname == "" {
		cfg.Hostname = getEnv("SPSAAS_HOSTNAME", "")
	}
	if cfg.Interval == 0 {
		if envInterval := getEnv("SPSAAS_INTERVAL", ""); envInterval != "" {
			if d, err := time.ParseDuration(envInterval); err == nil {
				cfg.Interval = d
			}
		}
	}
	if cfg.AgentVersion == "" {
		cfg.AgentVersion = getEnv("SPSAAS_AGENT_VERSION", "0.1.0")
	}
	if cfg.IP == "" {
		cfg.IP = getEnv("SPSAAS_IP", "")
	}

	// Apply defaults
	if cfg.Hostname == "" {
		hostname, err := os.Hostname()
		if err != nil {
			hostname = "unknown"
		}
		cfg.Hostname = hostname
	}
	if cfg.Interval == 0 {
		cfg.Interval = 30 * time.Second
	}

	return cfg
}

func (c *Config) Validate() error {
	if c.APIKey == "" {
		return ErrMissingAPIKey
	}
	return nil
}

func getEnv(key, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}

var ErrMissingAPIKey = &configError{"api-key is required (flag --api-key or env SPSAAS_API_KEY)"}

type configError struct {
	msg string
}

func (e *configError) Error() string {
	return e.msg
}