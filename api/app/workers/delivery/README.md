# Alert delivery channels

Entrega real de las `AlertDelivery` pendientes (v1: webhook + email + telegram).

## Architecture

```text
workers/alerts.py                        workers/delivery_runner.py
  evaluate_alerts()  ──creates──▶  AlertDelivery(pending)
                                          │  deliver_alerts() — cron alert-delivery-1m
                                          ▼
                                  workers/delivery/__init__.py
                                    DeliveryChannel protocol + registry
                                          │
              ┌──────────────────┬──────────────────┐
              ▼                  ▼                  ▼
     delivery/webhook.py   delivery/email.py   delivery/telegram.py
     POST JSON 10s timeout  SMTP via to_thread  sendMessage 10s timeout
```

- **Producer**: `evaluate_alerts()` creates one `AlertDelivery(status="pending")` per channel key in `rule.channels` when an alert fires (see `workers/alerts.py`).
- **Consumer**: `deliver_alerts()` (in `workers/delivery_runner.py`) processes all pending deliveries once per minute (`cron alert-delivery-1m`). Cross-tenant by design: it serves every tenant, same pattern as the evaluation runner.
- **Outcome**: success → `sent` + `external_ref` + `delivered_at`; failure → `failed` + `error` (`reason: message`). No unbounded retries in v1; a failed delivery is only retried if a new alert re-creates one.

## Channel contract

```python
class DeliveryChannel(Protocol):
    name: str
    async def send(self, *, alert: Alert, rule: AlertRule | None, server: Server | None, channel_config: dict) -> str: ...
```

- Receives the domain objects plus the channel's own config from `rule.channels[<name>]`.
- Returns the `external_ref` string on success.
- Raises `DeliveryError(message, reason)` on failure; `reason` is one of `http_error | timeout | connection_error | config_missing | unknown_channel | alert_missing`.

## Config model

- Per rule: `rule.channels` JSON, validated by `app/api/v1/schemas.py`:
  - `{"webhook": {"url": "...", "headers": {...}?}}`
  - `{"email": {"to": ["a@b.c", ...]}}`
  - `{"telegram": {"chat_id": "...", "thread_id": n?, "silent": bool?}}`
  - Allowed keys: exactly `webhook`, `email`, `telegram`; at least one required.
- Global SMTP: `core/config.py` (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_STARTTLS`); email is disabled (`config_missing`) unless `smtp_enabled` is true.
- Global Telegram: `core/config.py` (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_API_BASE`, `TELEGRAM_MAX_MESSAGE_CHARS`); telegram is disabled (`config_missing`) unless `telegram_enabled` is true. The bot token is global; `chat_id` is per rule.
- `PUBLIC_DASHBOARD_URL` is used by the telegram channel to link out when an alert body exceeds `TELEGRAM_MAX_MESSAGE_CHARS` (4096, the Bot API hard limit). The body is replaced by a short pointer instead of being silently cut.
- Secrets never leave the config: payloads and error messages exclude `SMTP_PASSWORD` and `TELEGRAM_BOT_TOKEN`. Note the bot token appears in the outbound URL path per the Bot API contract; it is never logged.

## Adding a new channel (e.g. WhatsApp)

1. Create `workers/delivery/telegram.py` implementing `DeliveryChannel`.
2. Register it in `workers/delivery/__init__.py` (auto-register on import, like the existing channels).
3. Extend the schema whitelist and shape in `app/api/v1/schemas.py` (new channel model + `ALLOWED_CHANNEL_KEYS`).
4. Add unit tests (see `tests/test_delivery_webhook.py` / `tests/test_delivery_email.py` for stub patterns).
5. The runner needs no changes: it dispatches by registry name from `rule.channels` keys.