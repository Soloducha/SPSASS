# Mes 3 — Alertas

**Branch**: `feat/mes3-alertas`
**Fecha**: 2026-09-24
**Estado**: en progreso

## Objetivo

Motor de alertas funcional para SPSAAS: CRUD de reglas, evaluación periódica contra
métricas, ciclo de vida de alertas (open → acknowledged → resolved) y registro de
entregas (stub, sin envío real).

## Problema / Por qué

El producto monitorea servidores y métricas (meses 1-2) pero no avisa cuando algo
se sale de rango. El modelo de datos ya existe desde la migración 0001
(`alert_rules`, `alerts`, `alert_deliveries`) con RLS activo desde 0003; falta el
motor que las use.

## Alcance

- Evaluación de reglas activas de TODOS los tenants (worker sin contexto tenant).
- Entidades evaluadas en este slice: **SERVER** con métricas de tipo `MetricType`
  (cpu_usage, mem_usage, disk_usage, load_avg*). Reglas con `entity_id` concreto o
  `None` (aplica a todos los servers del tenant).
- Semántica de `duration_s`: la condición debe sostenerse durante la ventana
  — se evalúa contra TODAS las muestras del window `[now - duration_s, now]`
  (mínimo 1 muestra; sin muestras → no evalúa).
- Deduplicación: una regla+server no re-dispara mientras exista alerta
  OPEN/ACKNOWLEDGED. Cuando la condición deja de cumplirse, la alerta abierta se
  resuelve automáticamente.
- Deliveries: se registra una fila en `alert_deliveries` por canal configurado en
  `channels`, con estado `pending` (stub — sin envío real, por decisión del usuario).

## Fuera de alcance (este slice)

- Entrega real por canal (telegram/whatsapp/email/webhook) — slice futuro.
- Evaluación de entidades SERVICE/PROCESS/JOB/METRIC con estado (p.ej. service down).
- UI web de alertas (solo API).
- Sostenimiento temporal avanzado (re-armado, ventana deslizante, umbrales por rollout).

## Constraints

- Commits en inglés, docs en español.
- RLS: la API accede con `get_db_session` (SET LOCAL ROLE app_user); el worker usa
  `get_db_session_without_tenant` (multi-tenant).
- No se requieren migraciones: tablas + grants + políticas RLS ya existen (0001/0003).
- Tests: pytest (SQLite local o Postgres real vía `docker compose run --rm api python -m pytest`),
  mypy 0 errores, ruff 0 errores.

## TDD

- **Modo**: off (no hay config de TDD estricto en el repo).
- **Checks**: `mypy .` (api dir), `ruff check .`, `pytest` (51 tests base).

## Checklist

### T1 — Motor de evaluación (worker)
- [ ] `api/app/workers/alerts.py`: `evaluate_alerts(session) -> int`
  - [ ] Leer reglas activas de todos los tenants.
  - [ ] Para cada regla SERVER: resolver targets (entity_id o todos sus servers).
  - [ ] Query de métricas del window `duration_s`; condición `all(operador(value, threshold))`.
  - [ ] Disparo: crear `Alert` (sin duplicar si hay OPEN/ACKNOWLEDGED) + `AlertDelivery`s stub.
  - [ ] Resolución: cerrar alertas OPEN/ACKNOWLEDGED cuando la condición deja de cumplirse.

### T2 — Cron del worker
- [ ] Job `evaluate_alerts` cada minuto en `api/app/workers/main.py` (func + cron `alert-eval-1m`).

### T3 — API CRUD de reglas
- [ ] Schemas en `api/app/api/v1/schemas.py` (regla create/update/response).
- [ ] `api/app/repositories/alert.py`: `AlertRuleRepository` + `AlertRepository` (patrón TenantScopedRepository).
- [ ] `api/app/api/v1/alerts.py`: router `/api/v1/alerts` con:
  - [ ] `GET /rules`, `POST /rules`, `GET /rules/{id}`, `PATCH /rules/{id}`, `DELETE /rules/{id}`.
- [ ] Registrar router en `api/app/main.py`.

### T4 — API de alertas
- [ ] `GET /api/v1/alerts` (filtros: status, severity, rule_id, limit).
- [ ] `POST /api/v1/alerts/{id}/ack` y `POST /api/v1/alerts/{id}/resolve`.

### T5 — Tests y verificación
- [ ] `api/tests/test_alerts.py`: disparo sostenido, no-dedup, resolución, ack/resolve, CRUD.
- [ ] mypy 0, ruff 0, pytest completo verde.
- [ ] E2E manual contra Postgres real (opcional, si hay stack levantado).

## Delivery

- **Estrategia**: ask-on-risk (default).
- **Forecast**: ~600-800 líneas (motor ~150, API ~250, tests ~250) → supera 400 → chained PRs.
- **Chain strategy**: stacked-to-main (elegida por el usuario 2026-09-24). Cada PR mergea a main en orden.
- **Conteo real (work-unit commits)**: 2631261 engine+cron = 243 líneas; ab60dbf API slice = 392 líneas. Total ~635 sin tests. Con T5 (~250) ≈ 890 → 2-3 PRs en stack.

## Follow-ups del verificador independiente (T3/T4, no bloqueantes)

1. `repositories/alert.py:53` — `count_filtered` usa `where(Alert.tenant_id==...)` explícito en vez de `self._base_select()` (funcional; inconsistente con patrón base).
2. `schemas.py:99` — `AlertAckRequest.acknowledged_by: UUID` acepta cualquier UUID sin validar pertenencia al tenant (posible intención: service accounts).
3. `schemas.py:117` — `AlertListParams.offset` fuera de spec original (paginación estándar, sigue patrón existente).

## Progreso

<!-- actualizar por task -->
| Task | Estado | Evidencia |
|------|--------|-----------|
| T1   | ✅ hecho | `alerts.py`: motor `evaluate_alerts` + `_EvalContext`/`_evaluate_rule_for_server`; mypy/ruff 0 en `app/workers/`; pytest 50 passed/1 skipped/1 xfail/2 xpass |
| T2   | ✅ hecho | `main.py`: wrapper `evaluate_alerts_row` + `func` + cron `alert-eval-1m`; mypy/ruff 0 |
| T3   | ✅ hecho | `api/v1/alerts.py` (CRUD /rules), `repositories/alert.py`, schemas, router registrado; verificado independiente PASS; 3 follow-ups menores (ver abajo) |
| T4   | ✅ hecho | GET /alerts con filtros, POST /{id}/ack y /{id}/resolve; verificado independiente PASS |
| T5   | pendiente | |

## Criterios de aceptación

- Una regla con umbral superado de forma sostenida crea UNA alerta open + deliveries stub.
- La misma regla no re-dispara mientras la alerta siga abierta/acknowledged.
- Al volver la métrica a rango, la alerta se resuelve automáticamente.
- CRUD de reglas y ack/resolve funcionales vía API con aislamiento por tenant (RLS).
- Suite completa verde (mypy, ruff, pytest).