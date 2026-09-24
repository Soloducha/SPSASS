# Feature: alert-delivery — Entrega real de alertas por canal (v1: webhook + email)

## Objetivo
Que las `AlertDelivery` en estado `pending` (creadas por `evaluate_alerts`) se envíen de verdad por canal, con estado `sent`/`failed`, `external_ref` y `delivered_at`.

## Problema
El Mes 3 crea entregas pendientes pero nadie las envía: el loop de alertas no avisa a nadie.

## Por qué / contexto
- Diseño v1 (#79): alertas Telegram/WhatsApp/Email. **Decisión del usuario (2026-09-24): v1 = Webhook + Email.** Telegram/WhatsApp quedan como canales futuros sobre la misma abstracción.
- `rule.channels` (JSON por regla) ya alimenta la creación de deliveries (`workers/alerts.py:126-135`): cada key del dict es un canal → el v1 define el shape de esas keys: `webhook` y `email`.
- El runner de evaluaciones es cross-tenant (sin RLS) porque dispara para todos los tenants; el runner de deliveries seguirá el mismo patrón.

## Alcance (autorizado)
- Motor de envío: abstracción de canal + canal **webhook** (POST JSON, timeout, non-2xx = error) + canal **email** (SMTP vía stdlib `smtplib` en `asyncio.to_thread`, sin dependencia nueva).
- Config SMTP global en `core/config.py` (env). Config de destino por regla en `rule.channels`: `{"webhook": {"url": ...}, "email": {"to": [...]}}`.
- Validación de `channels` en schemas (whitelist webhook/email + shape).
- Runner `deliver_alerts(session)` + cron en `workers/main.py`.
- Tests: unit por canal + integración pending→sent / pending→failed.
- Sin migración (reusa `external_ref`, `status`, `delivered_at`, `error`). Sin cambios al motor de evaluación. `Tenant.settings` no se toca en este slice.

## Restricciones
- Un intento por ciclo: éxito → `sent`; fallo → `failed` + `error` legible. Sin reintentos automáticos por ahora (cada ciclo nuevo intenta pendings; re-disparo de alertas crea deliveries nuevas).
- Email deshabilitado si falta config SMTP completa (error `config_missing` → `failed`, no crash del worker).
- Canal desconocido en `channels` → delivery `failed` con error (nunca crash).
- Mensajes en inglés (artefacto técnico); logs con el patrón estructurado existente.

## Checklist

### T1 — Config SMTP + validación de channels en schemas
- [x] `core/config.py`: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_STARTTLS` (defaults: vacíos/off = email disabled) + `smtp_enabled`.
- [x] `api/v1/schemas.py`: modelos `WebhookChannel`/`EmailChannel`, whitelist keys, validación en create y update (≥1 canal, url HttpUrl, to emails ≥1).
- [x] Tests: `test_delivery_config.py` (24) — settings defaults/overrides + validación.
- ✅ Evidencia: commit `d902e96`; 24 passed + test_alerts 18 passed; ruff 0; mypy 0 (archivos tocados); spot-check padre: 24 passed.
- Checks: pytest ✅ ruff ✅ mypy ✅

### T2 — Abstracción de canales + canal Webhook
- [x] `app/workers/delivery/__init__.py`: `DeliveryError` (message+reason), `DeliveryChannel` protocol, registry + `get_channel` (unknown → DeliveryError), auto-import webhook.
- [x] `app/workers/delivery/webhook.py`: `WebhookChannel` httpx AsyncClient (timeout 10s), payload JSON alert/rule/server sin secrets, 2xx → X-Request-Id|`webhook:{alert_id}`, non-2xx/timeout/conn → DeliveryError, config faltante → config_missing.
- [x] Tests: `test_delivery_webhook.py` (10) — mock transport: ref, http_error, timeout, connection_error, config_missing, unknown_channel.
- ✅ Evidencia: commit `f762904`; 10 passed + sin regresión (42 targeted); suite completa 102 passed/1 skipped/1 xfail/2 xpass; ruff 0; mypy 0; spot-check padre: 10 passed.
- Checks: pytest ✅ ruff ✅ mypy ✅

### T3 — Canal Email (SMTP stdlib)
- [x] `app/workers/delivery/email.py`: `EmailChannel` — EmailMessage (from SMTP_FROM, to channel_config["to"], subject conciso, body plano con alerta/regla/server); envío `smtplib` vía `asyncio.to_thread`; STARTTLS opcional; login solo con usuario; sin config global → `config_missing`; errores SMTP/OSError → `connection_error`; ref `email:{to}`.
- [x] Registro auto en `delivery/__init__.py`.
- [x] Tests: `test_delivery_email.py` (9) — stub smtplib: happy path (From/To/Subject/body), starttls/login condicional, config faltante, SMTPException → error.
- ✅ Evidencia: commit `68b116a`; 9 passed + 52 targeted sin regresión; ruff 0; mypy 0; spot-check padre: 9 passed.
- Checks: pytest ✅ ruff ✅ mypy ✅

### T4 — Runner de deliveries + cron
- [x] `app/workers/delivery_runner.py` (nuevo): `deliver_alerts(session) -> DeliveryRunSummary` (sent/failed/total); carga `pending` cross-tenant (sin RLS); por delivery: `get_channel`, config desde `rule.channels`, `server` solo si `server_id`; éxito → sent+external_ref+delivered_at; `DeliveryError` → failed + `reason: message`; excepción inesperada → failed + traceback (nunca crash); commit único al final.
- [x] `workers/main.py`: wrapper `deliver_alerts_row` + cron `alert-delivery-1m` (patrón de `alert-eval-1m`).
- [x] Tests: `test_delivery_runner.py` (6) — sent (mock get_channel), DeliveryError→failed, config_missing, unknown_channel, no-reselección de failed, mixto.
- ✅ Evidencia: commit `8aa4d4e`; 6 passed + 61 targeted sin regresión; suite completa **117 passed/1 skipped/1 xfail/2 xpass**; ruff 0 (todo app+tests); mypy 0 en áreas del feature (1 error PRE-EXISTENTE: stubs `jose` en `core/auth/security.py`, último touch `51a3904` mes 2, no tocar); spot-check padre: 6 passed.
- Checks: pytest ✅ ruff ✅ mypy ✅ (feature)

### T5 — Verificación completa + entrega
- [x] Suite completa verde: **117 passed / 1 skipped / 1 xfailed / 2 xpass** (baseline 68 + 49 nuevos); ruff 0 (app+tests); mypy 0 feature.
- [x] Feature doc actualizado con evidencias por tarea.
- [x] Work-unit commits por tarea: d902e96 (T1), f762904 (T2), 68b116a (T3), 8aa4d4e (T4).
- [x] PR stack stacked-to-main (estrategia confirmada por el usuario): **#12** config → **#13** webhook → **#14** email → **#15** runner (Chain Context + size:exception documentadas por work unit).
- [x] Doc de arquitectura de canales: `api/app/workers/delivery/README.md` (cómo sumar un canal nuevo).
- [x] **Mergeado en main** (autorización del usuario, 2026-09-24): #12 → `176137b` · #13 → `339b750` (rebase slice) · #14 → `c81bc2b` (rebase) · #15 → `c088da2` (rebase) — CI verde en cada uno y en main post-merge (`36073114962` success); ramas locales/remotas limpias.
- Checks: pytest ✅ ruff ✅ mypy ✅ CI ✅

## Progreso
- T1 ✅ (d902e96): SMTP settings + validación channels; 24 tests nuevos.
- T2 ✅ (f762904): abstracción de canales + webhook; 10 tests nuevos.
- T3 ✅ (68b116a): canal email SMTP stdlib; 9 tests nuevos.
- T4 ✅ (8aa4d4e): runner `deliver_alerts` + cron `alert-delivery-1m`; 6 tests nuevos.
- T5 ✅: suite completa 117/1/1/2, PR stack **#12→#13→#14→#15** creado, README de canales.

## Verificación evidenciada
- T1: pytest 24 passed (nuevos) + 18 (alerta regresión: ok); ruff 0; mypy 0; spot-check padre 24 passed.
- T2: pytest 10 passed (nuevos) + 42 targeted sin regresión; suite completa 102/1/1/2; ruff 0; mypy 0; spot-check padre 10 passed.
- T3: pytest 9 passed (nuevos) + 52 targeted sin regresión; ruff 0; mypy 0; spot-check padre 9 passed.
- T4: pytest 6 passed (nuevos) + 61 targeted sin regresión; **suite completa 117/1/1/2**; ruff 0 (app+tests); mypy 0 feature (baseline jose aparte); spot-check padre 6 passed.
- T5: suite completa en verde; ruff 0; mypy 0 feature.

## Siguiente paso
- ✅ Merge del stack completado: #12→#13→#14→#15 en main, CI verde, ramas limpias (2026-09-24).
- Próximo feature: **UI web de alertas** (sección reglas + listado/ack/resolve sobre la API existente; dashboard SSR web/ tiene una sola página `page.tsx`).

## Routing
- Cada tarea: **delegated direct** (writer `general`), 2+ archivos por tarea; mapping ya hecho por el orquestador.
- TDD: no estricto (sin sdd-init cacheado); tests acompañan cada tarea; runner: `pytest` (API dir).