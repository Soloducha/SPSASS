package sender

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"math"
	"math/rand"
	"net/http"
	"time"
)

// Backoff defines the interface for retry backoff strategies.
type Backoff interface {
	Duration(attempt int) time.Duration
}

// ExponentialBackoff implements exponential backoff with jitter.
type ExponentialBackoff struct {
	BaseDelay time.Duration
	MaxDelay  time.Duration
	MaxAttempts int
	JitterFactor float64 // 0.0 to 1.0
}

func NewExponentialBackoff() *ExponentialBackoff {
	return &ExponentialBackoff{
		BaseDelay:     500 * time.Millisecond,
		MaxDelay:      8 * time.Second,
		MaxAttempts:   5,
		JitterFactor:  0.2,
	}
}

func (b *ExponentialBackoff) Duration(attempt int) time.Duration {
	if attempt >= b.MaxAttempts {
		return b.MaxDelay
	}
	delay := b.BaseDelay * time.Duration(math.Pow(2, float64(attempt)))
	if delay > b.MaxDelay {
		delay = b.MaxDelay
	}
	// Add jitter ±JitterFactor
	jitter := time.Duration(float64(delay) * b.JitterFactor * (rand.Float64()*2 - 1))
	delay += jitter
	if delay < 0 {
		delay = 0
	}
	if delay > b.MaxDelay {
		delay = b.MaxDelay
	}
	return delay
}

// Sender handles HTTP communication with the API.
type Sender struct {
	baseURL    string
	apiKey     string
	client     *http.Client
	logger     *slog.Logger
	backoff    Backoff
}

type registerRequest struct {
	Hostname      string `json:"hostname"`
	IP            string `json:"ip,omitempty"`
	OS            string `json:"os,omitempty"`
	AgentVersion  string `json:"agent_version,omitempty"`
}

type registerResponse struct {
	ID             string `json:"id"`
	Hostname       string `json:"hostname"`
	Status         string `json:"status"`
	AgentVersion   string `json:"agent_version"`
	LastHeartbeatAt string `json:"last_heartbeat_at"`
}

type heartbeatResponse struct {
	ServerID     string `json:"server_id"`
	HeartbeatAt  string `json:"heartbeat_at"`
}

type ingestResponse struct {
	Received  int    `json:"received"`
	Inserted  int    `json:"inserted"`
	ServerID  string `json:"server_id"`
}

// NewSender creates a new Sender.
func NewSender(baseURL, apiKey string, logger *slog.Logger) *Sender {
	if logger == nil {
		logger = slog.Default()
	}
	return &Sender{
		baseURL: baseURL,
		apiKey:  apiKey,
		client: &http.Client{
			Timeout: 10 * time.Second,
		},
		logger:  logger,
		backoff: NewExponentialBackoff(),
	}
}

// SetBackoff allows injecting a custom backoff (for testing).
func (s *Sender) SetBackoff(b Backoff) {
	s.backoff = b
}

// Register registers the server with the API.
func (s *Sender) Register(ctx context.Context, hostname, ip, os, agentVersion string) (string, error) {
	reqBody := registerRequest{
		Hostname:     hostname,
		IP:           ip,
		OS:           os,
		AgentVersion: agentVersion,
	}
	body, err := json.Marshal(reqBody)
	if err != nil {
		return "", fmt.Errorf("marshal register request: %w", err)
	}

	var resp registerResponse
	err = s.doWithRetry(ctx, http.MethodPost, s.baseURL+"/api/v1/servers/register", body, &resp)
	if err != nil {
		return "", err
	}
	s.logger.Info("register_ok", "server_id", resp.ID)
	return resp.ID, nil
}

// Heartbeat sends a heartbeat for the given server.
func (s *Sender) Heartbeat(ctx context.Context, serverID string) error {
	url := fmt.Sprintf("%s/api/v1/servers/%s/heartbeat", s.baseURL, serverID)
	var resp heartbeatResponse
	err := s.doWithRetry(ctx, http.MethodPost, url, nil, &resp)
	if err != nil {
		return err
	}
	s.logger.Info("heartbeat_ok", "server_id", serverID)
	return nil
}

// SendMetrics sends a batch of metrics to the API.
func (s *Sender) SendMetrics(ctx context.Context, batch MetricsBatch) error {
	body, err := json.Marshal(batch)
	if err != nil {
		return fmt.Errorf("marshal metrics batch: %w", err)
	}

	var resp ingestResponse
	err = s.doWithRetry(ctx, http.MethodPost, s.baseURL+"/api/v1/ingest/metrics", body, &resp)
	if err != nil {
		return err
	}
	s.logger.Info("metrics_sent", "server_id", batch.ServerID, "received", resp.Received, "inserted", resp.Inserted)
	return nil
}

func (s *Sender) doWithRetry(ctx context.Context, method, url string, body []byte, respBody interface{}) error {
	var lastErr error
	for attempt := 0; attempt < s.backoffDuration(attempt); attempt++ {
		select {
		case <-ctx.Done():
			return ctx.Err()
		default:
		}

		err := s.doRequest(ctx, method, url, body, respBody)
		if err == nil {
			return nil
		}

		lastErr = err
		s.logger.Warn("request_failed", "attempt", attempt+1, "url", url, "error", err)

		// Check if we should retry
		if !isRetryable(err) {
			return err
		}

		delay := s.backoff.Duration(attempt)
		s.logger.Debug("retrying", "attempt", attempt+1, "delay", delay)
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(delay):
		}
	}
	return fmt.Errorf("max retries exceeded: %w", lastErr)
}

// backoffDuration returns the max attempts from the backoff.
// This is a bit of a hack since Backoff interface doesn't expose MaxAttempts.
// We'll use the concrete type's MaxAttempts or default to 5.
func (s *Sender) backoffDuration(attempt int) int {
	if eb, ok := s.backoff.(*ExponentialBackoff); ok {
		return eb.MaxAttempts
	}
	return 5
}

func (s *Sender) doRequest(ctx context.Context, method, url string, body []byte, respBody interface{}) error {
	var reqBody *bytes.Reader
	if body != nil {
		reqBody = bytes.NewReader(body)
	} else {
		reqBody = bytes.NewReader(nil)
	}

	req, err := http.NewRequestWithContext(ctx, method, url, reqBody)
	if err != nil {
		return fmt.Errorf("create request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Api-Key", s.apiKey)

	resp, err := s.client.Do(req)
	if err != nil {
		return fmt.Errorf("do request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return &httpError{StatusCode: resp.StatusCode, URL: url}
	}

	if respBody != nil {
		if err := json.NewDecoder(resp.Body).Decode(respBody); err != nil {
			return fmt.Errorf("decode response: %w", err)
		}
	}
	return nil
}

type httpError struct {
	StatusCode int
	URL        string
}

func (e *httpError) Error() string {
	return fmt.Sprintf("HTTP %d for %s", e.StatusCode, e.URL)
}

func isRetryable(err error) bool {
	var httpErr *httpError
	if errors.As(err, &httpErr) {
		// Retry on 5xx, 429, 408
		return httpErr.StatusCode >= 500 || httpErr.StatusCode == 429 || httpErr.StatusCode == 408
	}
	// Retry on network errors (timeout, connection refused, etc.)
	return true
}