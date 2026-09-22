package config

import (
	"flag"
	"os"
	"testing"
	"time"
)

func TestLoad_Defaults(t *testing.T) {
	// Save and restore env
	oldEnv := map[string]string{
		"SPSAAS_API_URL":       os.Getenv("SPSAAS_API_URL"),
		"SPSAAS_API_KEY":       os.Getenv("SPSAAS_API_KEY"),
		"SPSAAS_HOSTNAME":      os.Getenv("SPSAAS_HOSTNAME"),
		"SPSAAS_INTERVAL":      os.Getenv("SPSAAS_INTERVAL"),
		"SPSAAS_AGENT_VERSION": os.Getenv("SPSAAS_AGENT_VERSION"),
		"SPSAAS_IP":            os.Getenv("SPSAAS_IP"),
	}
	defer func() {
		for k, v := range oldEnv {
			if v == "" {
				os.Unsetenv(k)
			} else {
				os.Setenv(k, v)
			}
		}
	}()

	// Clear all env vars
	os.Unsetenv("SPSAAS_API_URL")
	os.Unsetenv("SPSAAS_API_KEY")
	os.Unsetenv("SPSAAS_HOSTNAME")
	os.Unsetenv("SPSAAS_INTERVAL")
	os.Unsetenv("SPSAAS_AGENT_VERSION")
	os.Unsetenv("SPSAAS_IP")

	// Use a fresh FlagSet for testing
	fs := flag.NewFlagSet("test", flag.ContinueOnError)
	cfg := LoadWithFlags(fs, nil)

	if cfg.APIURL != "http://localhost:8000" {
		t.Errorf("APIURL = %q, want %q", cfg.APIURL, "http://localhost:8000")
	}
	if cfg.AgentVersion != "0.1.0" {
		t.Errorf("AgentVersion = %q, want %q", cfg.AgentVersion, "0.1.0")
	}
	if cfg.Interval != 30*time.Second {
		t.Errorf("Interval = %v, want %v", cfg.Interval, 30*time.Second)
	}
	if cfg.Hostname == "" {
		t.Error("Hostname should not be empty")
	}
}

func TestLoad_FlagOverridesEnv(t *testing.T) {
	os.Setenv("SPSAAS_API_URL", "http://env:8000")
	os.Setenv("SPSAAS_API_KEY", "env-key")
	os.Setenv("SPSAAS_HOSTNAME", "env-host")
	os.Setenv("SPSAAS_INTERVAL", "60s")
	os.Setenv("SPSAAS_AGENT_VERSION", "env-version")
	os.Setenv("SPSAAS_IP", "1.2.3.4")
	defer func() {
		os.Unsetenv("SPSAAS_API_URL")
		os.Unsetenv("SPSAAS_API_KEY")
		os.Unsetenv("SPSAAS_HOSTNAME")
		os.Unsetenv("SPSAAS_INTERVAL")
		os.Unsetenv("SPSAAS_AGENT_VERSION")
		os.Unsetenv("SPSAAS_IP")
	}()

	fs := flag.NewFlagSet("test", flag.ContinueOnError)
	cfg := LoadWithFlags(fs, []string{
		"--api-url", "http://flag:8000",
		"--api-key", "flag-key",
		"--hostname", "flag-host",
		"--interval", "45s",
		"--agent-version", "flag-version",
		"--ip", "5.6.7.8",
	})

	if cfg.APIURL != "http://flag:8000" {
		t.Errorf("APIURL = %q, want %q", cfg.APIURL, "http://flag:8000")
	}
	if cfg.APIKey != "flag-key" {
		t.Errorf("APIKey = %q, want %q", cfg.APIKey, "flag-key")
	}
	if cfg.Hostname != "flag-host" {
		t.Errorf("Hostname = %q, want %q", cfg.Hostname, "flag-host")
	}
	if cfg.Interval != 45*time.Second {
		t.Errorf("Interval = %v, want %v", cfg.Interval, 45*time.Second)
	}
	if cfg.AgentVersion != "flag-version" {
		t.Errorf("AgentVersion = %q, want %q", cfg.AgentVersion, "flag-version")
	}
	if cfg.IP != "5.6.7.8" {
		t.Errorf("IP = %q, want %q", cfg.IP, "5.6.7.8")
	}
}

func TestLoad_EnvOverridesDefault(t *testing.T) {
	os.Unsetenv("SPSAAS_API_URL")
	os.Unsetenv("SPSAAS_API_KEY")
	os.Unsetenv("SPSAAS_HOSTNAME")
	os.Unsetenv("SPSAAS_INTERVAL")
	os.Unsetenv("SPSAAS_AGENT_VERSION")
	os.Unsetenv("SPSAAS_IP")

	os.Setenv("SPSAAS_API_URL", "http://env:8000")
	os.Setenv("SPSAAS_API_KEY", "env-key")
	os.Setenv("SPSAAS_HOSTNAME", "env-host")
	os.Setenv("SPSAAS_INTERVAL", "60s")
	os.Setenv("SPSAAS_AGENT_VERSION", "env-version")
	os.Setenv("SPSAAS_IP", "1.2.3.4")
	defer func() {
		os.Unsetenv("SPSAAS_API_URL")
		os.Unsetenv("SPSAAS_API_KEY")
		os.Unsetenv("SPSAAS_HOSTNAME")
		os.Unsetenv("SPSAAS_INTERVAL")
		os.Unsetenv("SPSAAS_AGENT_VERSION")
		os.Unsetenv("SPSAAS_IP")
	}()

	fs := flag.NewFlagSet("test", flag.ContinueOnError)

	cfg := LoadWithFlags(fs, nil)

	if cfg.APIURL != "http://env:8000" {
		t.Errorf("APIURL = %q, want %q", cfg.APIURL, "http://env:8000")
	}
	if cfg.APIKey != "env-key" {
		t.Errorf("APIKey = %q, want %q", cfg.APIKey, "env-key")
	}
	if cfg.Hostname != "env-host" {
		t.Errorf("Hostname = %q, want %q", cfg.Hostname, "env-host")
	}
	if cfg.Interval != 60*time.Second {
		t.Errorf("Interval = %v, want %v", cfg.Interval, 60*time.Second)
	}
	if cfg.AgentVersion != "env-version" {
		t.Errorf("AgentVersion = %q, want %q", cfg.AgentVersion, "env-version")
	}
	if cfg.IP != "1.2.3.4" {
		t.Errorf("IP = %q, want %q", cfg.IP, "1.2.3.4")
	}
}

func TestValidate_MissingAPIKey(t *testing.T) {
	cfg := &Config{
		APIURL:       "http://localhost:8000",
		APIKey:       "",
		Hostname:     "test",
		Interval:     30 * time.Second,
		AgentVersion: "0.1.0",
	}

	err := cfg.Validate()
	if err == nil {
		t.Error("Validate() should return error for missing API key")
	}
	if err != ErrMissingAPIKey {
		t.Errorf("Validate() returned %v, want ErrMissingAPIKey", err)
	}
}

func TestValidate_ValidConfig(t *testing.T) {
	cfg := &Config{
		APIURL:       "http://localhost:8000",
		APIKey:       "valid-key",
		Hostname:     "test",
		Interval:     30 * time.Second,
		AgentVersion: "0.1.0",
	}

	err := cfg.Validate()
	if err != nil {
		t.Errorf("Validate() returned error for valid config: %v", err)
	}
}