# Alert delivery channels

Entrega real de las `AlertDelivery` pendientes (feature `alert-delivery`, v1: webhook + email).

## Architecture

```text
workers/alerts.py                        workers/delivery_runner.py
  evaluate_alerts()  ──creates──▶  AlertDelivery(pending)
                                          │  deliver_alerts() — cron alert-delivery-1m
                                          ▼
                                  workers/delivery/__init__.py
                                    DeliveryChannel protocol + registry
                                          │
                        ┌─────────────────┴─────────────────┐
                        ▼                                   ▼
             delivery/webhook.py                    delivery/email.py
             POST JSON 10s timeout                  SMTP via to_thread
```

- **Producer**: `evaluate_alerts()` creates one `AlertDelivery(status="pending")` per channel key in `rule.channels` when an alert fires (see `workers/alerts.py`).
- **Consumer**: `deliver_alerts()` (in `workers/delivery_runner.py`) processes all pending deliveries once per minute (`cron alert-delivery-1m`). Cross-tenant by design: it serves every tenant, same pattern as the evaluation runner.
- **Outcome**: success → `sent` + `external_ref` + `delivered_at`; failure → `failed` + `error` (`reason: message`). No unbounded retries in v1; a failed delivery is only retried if a new alert re-creates one.

## Channel contract

```python
class DeliveryChannel(Protocol):
    name: str
    async def send(self, *, alert: Alert, rule: AlertRule, server: Server | None, channel_config: dict) -> str: ...
```

- Receives the domain objects plus the channel's own config from `rule.channels[<name>]`.
- Returns the `external_ref` string on success.
- Raises `DeliveryError(message, reason)` on failure; `reason` is one of `http_error | timeout | connection_error | config_missing | unknown_channel`.

## Config model

- Per rule: `rule.channels` JSON, validated by `app/api/v1/schemas.py`:
  - `{"webhook": {"url": "...", "headers": {...}?}}`
  - `{"email": {"to": ["a@b.c", ...]}}`
  - Allowed keys: exactly `webhook`, `email`; at least one required.
- Global SMTP: `core/config.py` (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_STARTTLS`); email is disabled (`config_missing`) unless `smtp_enabled` is true.
- Secrets never leave the config: payloads and error messages exclude `SMTP_PASSWORD` and any auth material.

## Adding a new channel (e.g. Telegram)

1. Create `workers/delivery/telegram.py` implementing `DeliveryChannel`.
2. Register it in `workers/delivery/__init__.py` (auto-register on import, like the existing channels).
3. Extend the schema whitelist and shape in `app/api/v1/schemas.py` (new channel model + `ALLOWED_CHANNEL_KEYS`).
4. Add unit tests (see `tests/test_delivery_webhook.py` / `tests/test_delivery_email.py` for stub patterns).
5. The runner needs no changes: it dispatches by registry name from `rule.channels` keys.