# Feature: quality-gate — Sanear deuda mypy + ruff y subir el estándar del CI

## Objetivo
Corregir la deuda de calidad estática de la API (41 errores mypy, ~240 hallazgos ruff con valor real) y subir el gate del CI: `mypy app` a 0 errores + `ruff` con selectores de valor real sobre `app/`, sin lavar estilo puro.

## Alcance
- **SÍ**: errores mypy (app/core, app/db, app/models, app/repositories, app/workers, app/main.py), F401, F821, UP042 (StrEnum), PLC0415, TRY301, RET505/RET504, F841, PTH, F541, PLC0207, I001/W292/UP035/UP007/UP017 (auto-fix).
- **NO**: `alembic/` (migraciones generadas — excluidas del lint), E501 (línea larga, estilo), ANN* (anotaciones, estilo), PLR2004 en tests/scripts (códigos HTTP idiomáticos), T201 en scripts (print CLI legítimo).

## Tareas
| ID | Tarea | Estado |
|----|-------|--------|
| T1 | Config: pyproject [tool.ruff] extend-exclude alembic + ignores E501/E402 + per-file-ignores scripts/tests; ci.yml: gate ruff config-driven + mypy app | ✅ |
| T2 | Auto-fix ruff (I001, W292, UP035, UP007, UP017, F401, PLC0207, UP017=71 fixes) sin tocar alembic | ✅ |
| T3 | Models: forward refs con TYPE_CHECKING (F821 + mypy name-defined) + enums str→StrEnum (UP042) + UUIDMixin Uuid(as_uuid=True) | ✅ |
| T4 | Mypy core: repos/base genérico, auth UUID, db/session kwargs, config RedisUrl, no-any-return, workers tipos arq | ✅ |
| T5 | Misc ruff app/scripts/tests: PLC0415, TRY301, RET504, ANN, F811, F841, PTH, F541 | ✅ |
| T6 | Gate + verificación completa (pytest CI-replica, mypy 0, ruff 0) + commit | ✅ |

## Evidencia verificada (gatekeeper re-run, python:3.12 Docker)
- `mypy app` → Success: no issues found in 37 source files (MYPY_EXIT:0)
- `ruff check .` → All checks passed (RUFF_EXIT:0)
- `pytest --tb=short -q` → 28 passed, 1 xfailed, 2 xpassed (PYTEST_EXIT:0) — nota: 2 tests que antes eran xfail ahora PASAN porque `Uuid(as_uuid=True)` soporta UUID en SQLite (mejora colateral del fix de tipos).

## Decisiones tomadas durante implementación
- Repositorio genérico: `class TenantScopedRepository[ModelT]` (PEP 695), `TypeVar` bound a TenantAwareMixin. Atributos de clase (`id`, `tenant_id`) accedidos con `cast(Any, self.model)` puntual.
- Método `TenantScopedRepository.list` renombrado a `list_all` (shadowing del builtin `list` causaba valid-type/iterable en mypy). Callers y docstring actualizados.
- `engine_kwargs` heterogéneo eliminado: kwargs tipados directos a `create_async_engine` (rama sqlite/else).
- `REDIS_URL`: `RedisDsn` → `RedisUrl = Annotated[str, StringConstraints(pattern=...)]` (pydantic valida scheme; evita incompat str/RedisDsn en mypy).
- `get_current_user` del `auth/__init__.py`: se elimina export desde `service` (firma vieja `(session, token)`); prevalece la de `dependencies` (Request-based). `service_get_current_user` sigue usándose internamente con alias.
- `decode_token`: validación de tipo movida fuera del try (TRY301), mismo comportamiento.
- `# type: ignore[no-any-return]` en logging.get_logger (structlog no tipa); variables intermedias tipadas en security en vez de casts.
- per-file-ignore `ANN401` en `app/repositories/base.py`: el repo genérico necesita `**filters: Any` / `**data: Any` (flexibilidad SQLAlchemy). Documentado en pyproject.

## Verificación (checks)
- `pytest -v --tb=short` → 28 passed / 3 xfailed (base) — ahora 28 passed / 1 xfailed / 2 xpassed
- `mypy app` → 0 errores
- `ruff check .` (config nueva) → 0 errores
- Gate CI aplicado: ruff config-driven `app/` + `mypy app`

## Decisiones
- 2026-09-21: vía pragmática elegida por el usuario (vs lavado total): se corrigen lints con valor real; estilo puro (E501, ANN) y opinables (PLR2004 tests, T201 scripts) quedan fuera del gate documentados.
- 2026-09-21: alembic/ queda excluido del lint (generado); como el CI hoy ya corre solo app/, el gate no pierde nada.
- 2026-09-21: enums `class X(str, Enum)` → `enum.StrEnum` (Python ≥3.12 OK, serialización str idéntica).

## Evidencia
- Baseline (2026-09-21, python:3.12 Docker): mypy 41 errores en 20 archivos (37 checkeados); ruff 321 totales / 311 con gate propuesto.
- Archivos de detalle: `C:\Users\Qchara\AppData\Local\Temp\opencode\mypy-detail.txt`, `ruff-detail.txt` (backup de la clasificación).