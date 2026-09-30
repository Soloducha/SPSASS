# Feature — alert-dedup-silencing: un episodio de violación, como máximo una alerta

> Feature document ODD. Branch: `fix/alert-dedup-silencing`. Estado: **EN IMPLEMENTACIÓN**.
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

- [ ] T1 — `Alert.silenced_at` + migración `0011` (verificada offline con `alembic upgrade head --sql`).
- [ ] T2 — `_get_episode_alert()` + reconciliación en las 4 ramas de `workers/alerts.py`.
- [ ] T3 — `repo.resolve()` setea `silenced_at`; schema `AlertResponse.silenced`.
- [ ] T4 — tests del comportamiento nuevo + ajuste de los que codifican el contrato viejo.
- [ ] T5 — web: campo TS + badge + filtro.
- [ ] T6 — docs.

## Verificación

| Check | Resultado |
|-------|-----------|
| `ruff check app tests` | pendiente |
| `mypy app` | pendiente |
| `pytest` (suite completa) | baseline a confirmar: 216 passed / 2 failed (SMTP ambiental por `.env` local) |
| `alembic upgrade head --sql` | pendiente |

## Notas de ejecución

- Baseline conocido: `api/tests/test_alerts.py::test_no_dedup_while_open_or_acknowledged` y `api/tests/test_alerts_entities.py::test_idempotent_no_duplicate_on_reeval` (×3) **codifican el contrato viejo** y hay que ajustarlos — no son regresiones.
- La entrega sigue la política de 400 líneas/ PR; este slice se estima justo, con tests legítimos como grueso.
