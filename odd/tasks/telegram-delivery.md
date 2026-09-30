# Telegram alert delivery channel

## Objective

Add a Telegram channel to the alert delivery engine so alerts can be delivered to a chat via the Bot API `sendMessage` method.

## Problem

The product vision (`propuesta.md`, v1) lists Telegram and WhatsApp as notification channels, but only `webhook` and `email` exist. Today a rule declaring `channels: {"telegram": {...}}` is rejected at the API layer, and a delivery row inserted directly fails with `unknown_channel`.

## Why

Telegram requires no external provider, no paid account and no message-template approval — a bot token plus a `chat_id` is the entire setup. WhatsApp has none of those properties and was explicitly deferred to the future by the user.

## Scope (in)

- `TelegramChannel` implementing the existing `DeliveryChannel` Protocol
- Global settings: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_API_BASE`, `TELEGRAM_MAX_MESSAGE_CHARS`, `PUBLIC_DASHBOARD_URL`
- Schema: `TelegramChannel` model + `ALLOWED_CHANNEL_KEYS` extension
- Registry auto-registration
- Unit tests
- README (root + delivery) and `.env.example`

## Out of scope

- WhatsApp (user decision, deferred)
- Web UI for creating telegram rules (the existing rules form is not extended)
- Real-token end-to-end delivery against a live chat (not performed; see Verification)
- Inline keyboards / callback buttons

## Constraints

| Item | Value |
|------|-------|
| Language | Plain text. No `parse_mode`. The user chose plain text deliberately: `alert.message` is free-form user data, and MarkdownV2 requires escaping every `_`, `*`, `` ` ``, `[`, `(` or the send fails with a 400 and the notification is lost. |
| Message limit | Telegram's hard limit is 4096 chars. Over-long bodies are **replaced** by a short pointer, not truncated, so the operator knows to go read the detail. Link included only when `PUBLIC_DASHBOARD_URL` is set. |
| Secrets | The bot token is global (like `SMTP_PASSWORD`), never per-rule. It appears in the outbound URL path per the Bot API contract and is never logged. |
| Retries | None. Matches existing v1 behaviour: one attempt per cycle, terminal `failed` state. |

## Authorized scope

- `api/app/workers/delivery/telegram.py` (new)
- `api/app/workers/delivery/__init__.py` (registry import)
- `api/app/core/config.py` (settings)
- `api/app/api/v1/schemas.py` (channel model + whitelist)
- `api/tests/test_delivery_telegram.py` (new)
- `api/tests/test_delivery_runner.py`, `api/tests/test_delivery_config.py` (fixture fixes)
- `README.md`, `api/app/workers/delivery/README.md`, `api/.env.example`

## Tasks

- [x] T1 — settings (`TELEGRAM_*`, `PUBLIC_DASHBOARD_URL`, `telegram_enabled`)
- [x] T2 — `TelegramChannel` with plain-text body, error mapping, truncation
- [x] T3 — registry auto-registration
- [x] T4 — schema model + whitelist + normalized optional fields
- [x] T5 — unit tests (20) + fix two pre-existing tests that used `telegram` as the "unregistered channel" example
- [x] T6 — docs (root README, delivery README, `.env.example`)

## Verification

| Check | Result |
|-------|--------|
| `ruff check app tests` | clean |
| `mypy app` | clean, 61 source files |
| `pytest tests/test_delivery_telegram.py` | 20 passed |
| Full suite | **216 passed, 2 failed** — the 2 failures are pre-existing environmental SMTP ones (`test_delivery_config.py::TestSMTPDefaults`), caused by a locally configured `.env`. Before this work the suite was 196 passed / same 2 failed. |

**Not verified**: a real delivery to a live Telegram chat. No bot token was available. All Telegram tests use `httpx.MockTransport`. Before relying on this in production, run one real send.

## Decisions

- Plain text over MarkdownV2 (user decision, with the escaping-fragility reason stated)
- Truncate-to-pointer over silent truncation (user decision)
- `PUBLIC_DASHBOARD_URL` added as a new setting rather than assuming a domain
- Optional `thread_id` (forum topics) and `silent` supported; omitted from stored config when unset

## Side effect worth recording

Adding `telegram` to `ALLOWED_CHANNEL_KEYS` broke two existing tests that had used `telegram` as the example of an **unregistered** channel (`test_unknown_channel_failed`, `test_update_unknown_channel_key_fails`). They now use `discord` / `sms`. This is the test suite encoding an assumption that stopped being true — not a regression in the feature.

## Next Steps

- Real-token end-to-end send to confirm the payload renders as intended
- Consider whether the rules web form should expose `telegram` (currently API-only)
