# Follow-ups review quality-gate — investigación de causalidad y fixes

> Estado: **en implementación** — investigación completada, 2 fixes delegados.
> Branch: `feature/review-followups` (base: `main`@`cd422c1`).
> Origen: review nativa RDD de `97fa18d` (lineage `review-488b6c35560cba57`), escalada a `stop` por causalidad desconocida. RDD desactivado clone-scoped (decisión del usuario); delivery por política ordinaria.

## Investigación de causalidad (completada — 2026-09-22)

Verificada contra `git diff e07b3fa 97fa18d` (antes/después) y código actual en `main`; sin cambios posteriores al merge en los archivos señalados.

**Descartados — falsos positivos (3):**
- **R3-5** (`bulk_delete` `cast(CursorResult, result).rowcount`): `cast()` es no-op en runtime; `execute(delete(...))` siempre devuelve `CursorResult` con `rowcount`. Solo typing.
- **R4-1** (SQLite sin `pool_pre_ping`): pre-existing (el base tampoco lo tenía; el diff solo refactoriza dict→if/else) y claim incoherente (SQLite solo tests/dev con `StaticPool`).
- **R4-3** (`refresh_access_token` sin cleanup): falso — la sesión se crea con `async with get_db_session()` y está **fuera** del try.

**Duplicados (4):** R3-2, R3-3, R4-2 = mismo cambio que R3-1 (type-check fuera del try en auth); R3-4 = duplicado de R2-2 (bounds del TypeVar garantizan tenant_id en typing/runtime).

**Válidos con severidad inflada (3):**
- **R2-1**: `list_all` mantiene paginación — naming cosmético; la docstring documenta paginación.
- **R2-2** (y R3-4): `cast(Any, self.model)` ×12 — deuda de tipado real. El TypeVar bound `_ModelT` está definido pero **sin usar**; la clase usa `[ModelT]` inline sin bound. Fix: Protocol con `id` + `tenant_id` y bound del TypeVar → eliminar casts si mypy pasa.
- **R3-1** (y duplicados): mensajes de error de token pierden el prefijo de contexto (`Token inválido:` / `Refresh token inválido:`) tras mover el type-check fuera del try. Fix: restaurar contexto en los raise.

## Tareas

| ID | Tarea | Estado | Evidencia |
|----|-------|--------|-----------|
| T1 | Restaurar mensajes de error con contexto en `decode_token`, `refresh_access_token`, `get_current_user` | ✅ | security.py:117 (`Token inválido: tipo de token inválido`), service.py:210 (prefijo `Refresh token inválido:`), service.py:244 (prefijo `Token inválido:`) |
| T2 | Eliminar `cast(Any, self.model)` del repo genérico | ✅ | base.py: 12 casts eliminados → `self.model.X` + 7 `# type: ignore[attr-defined]` documentados; `cast(CursorResult, result)` → `result.rowcount` con ignore. Protocol falló en mypy (no propaga ClassVar a `type[T]`); solución: TypeVar bound + PEP 695 `TenantScopedRepository[T]` |
| T3 | Actualizar tracker con resultados y commit work-unit | 🔲 | — |

### Verificación ejecutada (writer + spot check parent)
- `mypy app` → Success: no issues found in 37 source files
- `ruff check app` → All checks passed!
- `ruff check .` → All checks passed!
- `pytest -q` → 28 passed, 1 xfailed, 2 xpassed (20s)
- NOTA: los 2 xpassed son **pre-existentes** (verificado con `git stash` baseline: igual resultado). Vienen del bump pytest 8→9 (deps-refresh), no del fix. Los 3 tests xfail de UUID/SQLite: 2 ahora pasan, 1 sigue xfail. Fuera de alcance de este work-unit.

## Alcance autorizado
- Fixes solo en: `api/app/core/auth/security.py`, `api/app/core/auth/service.py`, `api/app/repositories/base.py` (+ tests si hace falta).
- NO tocar R3-5/R4-1/R4-3 (descartados) ni renombrar `list_all` (documentado, no se toca).
- Verificación: `mypy app` = 0, `ruff check app` = 0, `ruff check .` = 0, `pytest` = 28 passed / 3 xfailed.

## Verificación
- `mypy app` → 0 errores (en `api/`)
- `ruff check app` y `ruff check .` → 0
- `pytest -q` → 28 passed, 3 xfailed
- Commit work-unit en `feature/review-followups`, conventional commit.

## Enlace
- Feature doc mes 1: `odd/tasks/fundaciones.md`
- TODO mes 2: `odd/tasks/mes2-agente-ingesta.md`
- Roadmap: `propuesta.md` (sección 7)