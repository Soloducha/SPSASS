# SPSAAS API

Backend FastAPI async para el SaaS de monitoreo SPSAAS.

## Stack

- **Python 3.12+**
- **FastAPI** — Framework web async
- **Pydantic v2** — Validación y settings
- **SQLAlchemy 2.0 (async)** — ORM
- **Alembic** — Migraciones
- **PostgreSQL 16 + TimescaleDB** — Base de datos
- **Redis 7** — Broker + Cache
- **arq** — Workers async
- **structlog** — Logging estructurado

## Desarrollo local

```bash
# Desde la raíz del monorepo
docker compose up --build -d api db redis

# O solo API (requiere DB y Redis corriendo)
cd api
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
```

## Variables de entorno

Copiar `.env.example` a `.env` y ajustar:

```bash
cp .env.example .env
```

Variables críticas:

| Variable | Descripción | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL + asyncpg | `postgresql+asyncpg://spsaas:spsaas@localhost:5432/spsaas` |
| `REDIS_URL` | Redis | `redis://localhost:6379/0` |
| `JWT_SECRET` | Secreto JWT (min 32 chars) | `dev-secret-change-me-32-chars-minimum-length` |
| `ENVIRONMENT` | `development` \| `staging` \| `production` | `development` |

## Comandos útiles

```bash
# Tests
pytest -v
pytest --cov=app --cov-report=term-missing

# Lint
ruff check .
ruff format .

# Type check
mypy app

# Migraciones
alembic revision --autogenerate -m "descripción"
alembic upgrade head
alembic downgrade -1

# Shell
python -m app.main  # O uvicorn app.main:app --reload
```

## Estructura

```
api/
├── app/
│   ├── api/           # Routers (auth, servers, jobs, alerts, reports, ingest)
│   ├── core/          # Config, logging, security
│   ├── db/            # Session, base
│   ├── models/        # Modelos SQLAlchemy
│   ├── schemas/       # Pydantic schemas (request/response)
│   ├── services/      # Lógica de negocio
│   ├── middleware/    # Middlewares (tenant, auth, etc.)
│   └── workers/       # arq workers
├── alembic/           # Migraciones
├── tests/             # Tests pytest
├── pyproject.toml
├── Dockerfile
├── Dockerfile.worker
└── README.md
```

## Health Checks

- `GET /healthz` — Liveness: API + DB + Redis
- `GET /readyz` — Readiness: API lista para tráfico

## Docs

- Swagger UI: `http://localhost:8000/docs` (solo dev)
- ReDoc: `http://localhost:8000/redoc` (solo dev)