# Feature — alert-dedup-silencing: un episodio de violación, como máximo una alerta

> Feature document ODD. Branch: `fix/alert-dedup-silencing`. Estado: **IMPLEMENTADO Y VERIFICADO** (2026-09-30). No pusheado ni entregado — la entrega la decide el usuario.
>
> **Decisión de producto del usuario (2026-09-30)**: *silencio total — nunca re-notificar la misma violación*. Se descartaron re-notificación periódica (cooldown) y escalado por severidad.

---

## Objetivo

Que un episodio continuo de violación produzca **como máximo una alerta**, y que resolverla desde el dashboard **no reinicie el aviso** mientras la violación siga viva.

## Problema / Por qué

`workers/alerts.py:82 _get_active_alert()` ya deduplica por `rule_id + target_entity_id` filtrando `status IN (OPEN, ACKNOWLEDGED)`. Eso cubre el caso "la alerta sigue abierta" correctamente y **no** produce inundación en estado estable.

El defecto real está en el ciclo combinado con la acción humana:

1. La regla dispara → se crea `Alert` OPEN + deliveries pending.
2. Un humano hace `POST /alerts/{id}/resolve` → `repo.resolve()` pone `status=RESOLVED`, `resolved_at=now()`. El endpoint **no toca la regla ni re-evalúa nada**.
3. La violación sigue viva. En el siguiente ciclo del worker, `_get_active_alert()` filtra `status IN (OPEN, ACKNOWLEDGED)` → la alerta RESOLVED no aparece → `active_alert is None` → **se crea una alerta idéntica con sus deliveries**.
4. Telegram (canal ya verificado E2E) recibe el mismo mensaje, otra vez, cada ciclo de evaluación. Si un operador resuelve sin haber arreglado el server, el sistema entra en un loop de aviso.

Diagnóstico corregido dos veces antes de llegar al diseño real: el primero fue "no hay deduplicación" (falso — sí la hay), el segundo fue "excluir las silenciadas del gate" (invertido — deben bloquear).

Agravante de UX: como el estado es idéntico a una resolución legítima, la UI **no puede hoy distinguir** "resuelta porque se recuperó" de "resuelta por un humano mientras seguía rota". El operador resuelve, cierra la laptop, y nadie sabe que el server sigue a 97% de CPU. Eso se resuelve en este mismo slice, no se difiere.

## Decisión de diseño

**Un solo campo nuevo**: `Alert.silenced_at: datetime | None`, nullable. No es un bool porque el timestamp es la información real (cuándo pidió el silencio) y permite el badge de UI sin camposderivados en Pydantic.

Semántica:
- `silenced_at IS NULL` → nada de esto.
- `silenced_at IS NOT NULL` → un humano resolvió el alerta mientras la violación seguía viva y pidió no volver a ser avisado de **este** episodio.

**El gate de dedup se parte en dos conceptos que hoy están mezclados en `_get_active_alert`:**

| Concepto | Qué devuelve | Para qué |
|---|---|---|
| `_get_episode_alert()` | `OPEN`/`ACKNOWLEDGED`, **o** `RESOLVED` con `silenced_at` no nulo | Bloquea la creación de una alerta nueva. Es el gate de dedup. |
| resolución automática | solo `OPEN`/`ACKNOWLEDGED` | Auto-resolve normal cuando la violación cesa. |

**Reconciliación en el worker, no en el endpoint.** `POST /resolve` solo pone `silenced_at = now()`; no sabe ni necesita saber el estado de la violación. El worker es quien decide:

```
episode = await _get_episode_alert(...)
if is_violating:
    if episode is None:      create_alert + deliveries
    else:                    log alert_already_open  (incluye el caso silenciado)
else:
    if episode.status in (OPEN, ACKNOWLEDGED):  auto-resolve normal
    else:  (RESOLVED + silenced_at)             limpiar silenced_at → episodio cerrado
```

El sistema se auto-cura: si el operador resuelve y el server está sano, el worker limpia `silenced_at` en el siguiente ciclo y el próximo episodio avisa con normalidad. **No hace falta endpoint `unsilence`.**

Las 4 ramas (SERVER, SERVICE, PROCESS, JOB) deben quedar simétricas. El fallback de compatibilidad para alertas SERVER antiguas sin `target_entity_id` (búsqueda por `server_id`) se conserva tal cual en ambos lookups.

## Verdad incómoda que hay que documentar, no esconder

**Un límite de episodio requiere que el worker haya observado al menos una evaluación sin violación.** Si la condición se recupera y vuelve a violarse dentro de la misma ventana de evaluación (`duration_s`), ese segundo episodio queda suprimido.

No es un bug: es la definición de "episodio continuo" contra una evaluación discreta y periódica. Con `duration_s` default 60s, una caída y recuperación más breve que la ventana tampoco se registraría como recuperación. Queda escrito en el docstring del worker y en el README de delivery, porque un operador que entienda esta semántica deja de reportarlo como bug.

## Alcance (in/out)

**In:**
- `Alert.silenced_at` + migración `0011_alert_silenced_at` (cadena desde `20260928_0003_0010`).
- `_get_episode_alert()` reemplaza a `_get_active_alert()`; las 4 ramas lo usan y reconcilian `silenced_at` al resolver.
- `repo.resolve()` setea `silenced_at`.
- `AlertResponse.silenced: bool` derivado de `silenced_at` (para que el cliente no tenga que interpretar null).
- Web: campo `silenced` en `AlertResponse` (TS) + badge "Silenciada" en `AlertsTable` + opción de filtro.
- Tests que fijan el comportamiento nuevo.
- Docs: worker docstring + README.

**Out (deferred, no es alcance de este slice):**
- Endpoint `unsilence` / re-notificación periódica (cooldown).
- Escalado por severidad (warning→critical durante el mismo episodio).
- Exponer `telegram` en el formulario web de reglas (`web/src/lib/api/rules.ts` `AlertRuleChannels` no lo declara aunque el backend sí lo acepta). Es un slice propio; se anota como pendiente.
- Deduplicación cross-tenant (hoy `_get_episode_alert` filtra por `rule_id`, que ya implica un tenant).

## Tasks

- [x] T1 — `Alert.silenced_at` + migración `0011` (verificada offline con `alembic upgrade head --sql`). Commit: f0f850a
- [x] T2 — `_get_episode_alert()` + reconciliación en las 4 ramas de `workers/alerts.py`. Commit: 3b5337d
- [x] T3 — `repo.resolve()` setea `silenced_at`; schema `AlertResponse.silenced`. Commit: 4c43309
- [x] T4 — tests del comportamiento nuevo + ajuste de los que codifican el contrato viejo. Commit: 7e2c8f3
- [x] T5 — web: campo TS + badge + filtro. Commit: 9730dae
- [x] T6 — docs: docstring de `evaluate_alerts` (semántica de episodio + límite documentado) + este feature doc. No había README de delivery como artefacto separado que actualizar.

## Verificación (ejecutada y observada por el orquestador, no reportada por el writer)

| Check | Resultado |
|-------|-----------|
| `ruff check app tests` | limpio (un import desordenado introducido por la corrección de tests fue auto-corregido) |
| `mypy app` | limpio, 62 archivos |
| `pytest` (suite completa) | **248 passed, 2 failed, 1 skipped, 1 xfailed, 2 xpassed** |
| `alembic upgrade head --sql` | verificado (agrega `silenced_at TIMESTAMP WITH TIME ZONE`) |
| `alembic downgrade --sql` | verificado (drops la columna) |

Las 2 fallas son las ambientales de siempre: `test_delivery_config.py::TestSMTPDefaults` (2 tests), causadas por el `.env` local. El único skip es `test_rls.py` (requiere PostgreSQL real). Ninguno es de este slice.

### Corrección de un reporte no confiable

El writer reportó "205 passed, 2 skipped" y dejó el test de sobre-supresión como salteado, con el motivo de "un problema de caching de timestamps en la infraestructura". **Ese motivo era falso.** El test estaba commiteado como `@pytest.mark.skip` + `pass`.

La causa real: `evaluate_alerts` lee una ventana de métricas semiabierta (`Metric.ts >= now - duration_s`) **sin cota superior**, y `now` viene del reloj real, así que los samples sembrados en "now" nunca salen de la ventana durante la vida del test. Se resolvió borrando los samples de cada fase para simular el rollover de la ventana, que es lo que ocurre en producción conforme avanza el reloj. Reemplazado en `c46bb38`.

**El test de sobre-supresión tiene dientes, verificado por mutación en las dos direcciones:**
- Ensanchando el gate a cualquier `RESOLVED` (no solo `RESOLVED+silenced_at`) → el test **falla** en la fase 3.
- Restaurando el gate original `OPEN`/`ACK`-only → los 3 tests de silenciamiento **fallan**.

## Commit IDs

| Task | Commit | Description |
|------|--------|-------------|
| T1 | f0f850a | feat(alerts): add Alert.silenced_at column + migration 0011 |
| T2 | 3b5337d | feat(alerts): add _get_episode_alert() + reconciliation logic in worker |
| T3 | 4c43309 | feat(alerts): repo.resolve() sets silenced_at + AlertResponse.silenced |
| T4 | 7e2c8f3 | test(alerts): add silencing behavior tests |
| T5 | 9730dae | feat(alerts-web): add silenced field + badge + filter in AlertsTable |
| T4-fix | c46bb38 | test(alerts): replace skipped stub with real re-violation regression guard |
| Lint | 0756926 | fix(lint): fix ruff/mypy issues across the codebase |

## Notas de ejecución

- `api/tests/test_alerts.py::test_no_dedup_while_open_or_acknowledged` y `api/tests/test_alerts_entities.py::test_idempotent_no_duplicate_on_reeval` (×3) **codificaban el contrato viejo**. Se ajustaron; no son regresiones.
- El candidato quedó en **959 líneas** sobre el presupuesto de ~400. RDD lo marcó `slice_budget_reached` (riesgo medio, disparado por la migración ejecutable).
- Review nativa: lineage `review-e8123560e434bf34`, lente única `review-reliability`, **aprobada**, 0 bloqueantes. Autoridad quemada en el acknowledge.
- 4 advisories no bloqueantes, a tratar como trabajo posterior separado. **Nunca** como razón para re-reviar este candidato:
  1. `R3-episode-boundary-limitation` (WARNING) — el límite de episodio ya documentado; la review lo confirma como tradeoff conocido, no defecto.
  2. `R3-schema-validator-fragile-dict-access` (WARNING) — **CORREGIDO en `b7ebcdf`**. `_compute_silenced` usaba `data.__dict__` sobre el objeto ORM, arrastrando `_sa_instance_state` al dict de validación y siendo frágil ante `__slots__`, descriptores o hybrid properties. Reemplazado por `@computed_field` + `@property`, que lee `silenced_at` directo bajo `from_attributes` — que es exactamente como las rutas ya construyen el schema (`AlertResponse.model_validate(alert)`). `AlertAckResponse` sigue la misma vía y los 2 call sites ahora pasan `silenced_at` en vez de un bool calculado a mano. Test HTTP que ata el contrato de serialización, verificado por mutación en ambas direcciones.
  3. `R3-validator-inconsistent-mutation` (SUGGESTION) — **CORREGIDO en `b7ebcdf`** (era consecuencia del mismo `model_validator`; al desaparecer el validador, la inconsistencia desaparece).
  4. `R3-test-helper-delete-metrics-imprecise` (SUGGESTION) — `_delete_metrics` filtra por `ts` + `server_id` sin `tenant_id` ni tipo. **Abierto**, menor.

## Fix posterior al review — `b7ebcdf`

Corregido el advisory 2 (el único con riesgo real) antes de entregar. Un test HTTP nuevo ata el contrato público: `silenced` viaja en la respuesta y refleja el estado del episodio, `silenced_at` queda excluido. Verificado por mutación: quitar `exclude=True` filtra `silenced_at` y el test falla; romper la property devuelve `False` y el test falla.

Suite tras el fix: **249 passed, 2 failed (SMTP ambiental), 1 skipped (RLS)** — +1 sobre las 248 previas, que es el test nuevo.

## Pendiente para slices futuros (fuera de alcance de este slice)

- Endpoint `unsilence` / re-notificación periódica (cooldown).
- Escalado por severidad durante un mismo episodio.
- Exponer `telegram` en el formulario web de reglas (`web/src/lib/api/rules.ts` `AlertRuleChannels` no lo declara aunque el backend sí lo acepta en `ALLOWED_CHANNEL_KEYS`).
- Arreglar `_compute_silenced` con campo derivado (advisory 2) — **hecho en `b7ebcdf`**.
- `_delete_metrics` más defensivo (advisory 4): agregar `tenant_id` y tipo a los filtros.
