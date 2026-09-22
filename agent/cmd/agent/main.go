package main

import (
	"context"
	"fmt"
	"log/slog"
	"os"
	"os/signal"
	"runtime"
	"syscall"
	"time"

	"github.com/spsaas/agent/internal/collector"
	"github.com/spsaas/agent/internal/config"
	"github.com/spsaas/agent/internal/sender"
)

func main() {
	cfg := config.Load()
	if err := cfg.Validate(); err != nil {
		fmt.Fprintf(os.Stderr, "config error: %v\n", err)
		os.Exit(1)
	}

	// Setup structured JSON logger
	logger := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{
		Level: slog.LevelInfo,
	}))
	slog.SetDefault(logger)

	logger.Info("starting agent",
		"hostname", cfg.Hostname,
		"api_url", cfg.APIURL,
		"interval", cfg.Interval,
		"agent_version", cfg.AgentVersion,
		"go_version", runtime.Version(),
	)

	// Create sender and collector
	snd := sender.NewSender(cfg.APIURL, cfg.APIKey, logger)
	collector.SetSystemStats(&collector.GopsutilSystemStats{})

	// Register server on startup
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	serverID, err := snd.Register(ctx, cfg.Hostname, cfg.IP, runtime.GOOS, cfg.AgentVersion)
	cancel()
	if err != nil {
		logger.Error("registration failed after retries", "error", err)
		os.Exit(1)
	}
	logger.Info("registered", "server_id", serverID)

	// Create context that listens for shutdown signals
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	// Metrics collection ticker
	metricsTicker := time.NewTicker(cfg.Interval)
	defer metricsTicker.Stop()

	// Heartbeat every 5 metrics intervals (or separate ticker)
	heartbeatInterval := cfg.Interval * 5
	heartbeatTicker := time.NewTicker(heartbeatInterval)
	defer heartbeatTicker.Stop()

	logger.Info("entering collection loop", "metrics_interval", cfg.Interval, "heartbeat_interval", heartbeatInterval)

	// Track if we've had at least one successful metrics send
	metricsSent := false

	for {
		select {
		case <-ctx.Done():
			logger.Info("shutdown signal received, draining...")
			// Drain: try one final metrics send if we have pending work
			// For simplicity, we just exit gracefully
			logger.Info("agent stopped")
			return

		case <-metricsTicker.C:
			batch, err := collector.Collect(ctx, serverID)
			if err != nil {
				logger.Error("collect failed", "error", err)
				continue
			}

			// Convert collector.MetricsBatch to sender.MetricsBatch
			senderBatch := sender.MetricsBatch{
				ServerID: batch.ServerID,
				TS:       batch.TS,
				Metrics:  make([]sender.Metric, len(batch.Metrics)),
			}
			for i, m := range batch.Metrics {
				senderBatch.Metrics[i] = sender.Metric{
					Type:  m.Type,
					Value: m.Value,
					Tags:  m.Tags,
				}
			}

			err = snd.SendMetrics(ctx, senderBatch)
			if err != nil {
				logger.Error("send metrics failed after retries", "error", err)
				continue
			}
			metricsSent = true
			logger.Debug("metrics sent successfully", "count", len(batch.Metrics))

		case <-heartbeatTicker.C:
			// Only send heartbeat after first successful metrics send
			// (server is guaranteed to exist after registration, but this follows the spec)
			if !metricsSent {
				logger.Debug("skipping heartbeat before first metrics send")
				continue
			}
			err := snd.Heartbeat(ctx, serverID)
			if err != nil {
				logger.Error("heartbeat failed after retries", "error", err)
				continue
			}
			logger.Debug("heartbeat sent successfully")
		}
	}
}