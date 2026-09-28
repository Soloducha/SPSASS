# Feature: alert-timestamp-timezone-drift — Align ORM alert timestamp columns with the `timestamptz` schema

## Objective
Declare the four alert timestamp columns in the SQLAlchemy models as `DateTime(timezone=True)` so the ORM matches the database schema that the migration already created, and prove the alert lifecycle works end-to-end against real Postgres.

## Problem
The entire alert lifecycle is dead in the backend, for reasons unrelated to any web UI. **No alert is ever created**, and `POST /api/v1/alerts/{id}/ack` returns HTTP 500.

Discovered 2026-09-25 while live-verifying the `alert-web-ui` feature (see `odd/tasks/alert-web-ui.md`, T2 recorded as blocked). Confirmed preexisting on `main` via `git show main:api/app/repositories/alert.py`.

## Root Cause
ORM/migration type drift — **the database is correct, the model is wrong**.

| Column | Migration | ORM declaration | Result |
|---|---|---|---|
| `alerts.triggered_at` | `sa.DateTime(timezone=True)` | bare `Mapped[datetime]` | SQLAlchemy infers naive `DateTime()` |
| `alerts.resolved_at` | `sa.DateTime(timezone=True)` | bare `Mapped[datetime \| None]` | idem |
| `alerts.acknowledged_at` | `sa.DateTime(timezone=True)` | bare `Mapped[datetime \| None]` | idem |
| `alert_deliveries.delivered_at` | `sa.DateTime(timezone=True)` | bare `Mapped[datetime \| None]` | idem |

Aware `datetime.now(UTC)` values written into those ORM-typed columns then fail against `timestamptz` with
`DataError: can't subtract offset-naive and offset-aware datetimes`.

`TimestampMixin` (`api/app/models/base.py:14-27`) already declares `DateTime(timezone=True)` and does **not** fail. That asymmetry is the diagnostic tell: `created_at`/`updated_at` work, the four hand-written columns do not.

### Write sites (all write aware values — all are correct)
| File | Lines | Value |
|---|---|---|
| `api/app/repositories/alert.py` | 69 | `alert.acknowledged_at = datetime.now(UTC)` |
| `api/app/repositories/alert.py` | 81 | `alert.resolved_at = datetime.now(UTC)` |
| `api/app/workers/alerts.py` | 120 | `triggered_at=now` (from `:175`) |
| `api/app/workers/alerts.py` | 151 | `active_alert.resolved_at = now` |

**Do NOT strip `tzinfo` at these write sites.** That discards UTC and fights the schema. The model annotation is the outlier.

## Rationale
- The schema is already right, so **no new migration is needed**. Alembic autogenerate must report an empty diff after the model change — that is itself a check.
- A tz-aware column does not change the HTTP response shape. `AlertResponse` / `AlertAckResponse` (`api/app/api/v1/schemas.py:181-220`) use bare `datetime` and Pydantic v2 serializes aware values as ISO 8601. The delivery formatters (`api/app/workers/delivery/email.py:110,130`, `webhook.py:122`) do `.isoformat().replace("+00:00", "Z")`, which still matches an aware `+00:00` suffix.
- `delivered_at` is included because it is the same defect, same root cause, same file. A partial fix would knowingly leave the delivery path broken.

## Tasks
| ID | Task | Status |
|----|------|--------|
| T1 | Model: add `DateTime(timezone=True)` to the 4 alert timestamp columns + import `DateTime` | ✅ |
| T2 | Regression test: assert the ORM declares timezone-aware columns for all 4 (runs in CI on SQLite) | ✅ |
| T3 | Static + test gate green: `ruff check --exit-non-zero-on-fix app/`, `mypy app`, full `pytest` | ✅ |
| T4 | Runtime proof against real Postgres: empty autogenerate diff, alert actually CREATED end-to-end, ack → resolve round trip, `delivered_at` populated | ✅ |
| T4b | `/alertas` SSR re-checked with a real alert row, on `feat/alert-web-ui` | ✅ |
| T5 | Work-unit commit on the feature branch | ✅ |

## Authorized Scope
- **T1**: `api/app/models/alert.py` only — the import line and 4 column declarations. No other production file.
- **T2**: a test that pins the ORM declaration. No new test framework, no Postgres-backed test profile.
- **T3**: the CI-exact gate commands.
- **T4**: read-only runtime verification against the existing compose stack. Seeding throwaway data is allowed; the demo stack is not a production surface.
- **T5**: one work-unit commit, local only.

### T4b is deferred, not skipped
This branch is based on `main`, where `web/src/app/alertas/` does not exist (0 files — the alerts UI lives only in `feat/alert-web-ui`, which has since been merged to `main` as PRs #17–#26). The `/alertas` SSR re-check was therefore **not runnable on this branch**. It is also not this task's responsibility: it verifies the *web* feature, not the backend fix. It becomes a follow-up on `feat/alert-web-ui` once this fix lands there, and it is what unblocks that feature's T2.

## Out of Scope
- **A new Alembic migration.** The database is already correct. Creating one would be wrong, not just unnecessary.
- Stripping `tzinfo` at write sites, or any "fix" on the write path.
- Rewriting `TimestampMixin`, `TenantAwareMixin`, or any other model.
- A Postgres-backed test suite / compose test profile. Worth doing eventually, but it is infrastructure, not this bug.
- Changing `AlertResponse` / `AlertAckResponse` schemas or delivery formatters — verified compatible.
- Touching the `alert-web-ui` feature, its branch, or its stacked PR slices.
- Push and PR creation were unauthorized while this work unit was local-only. The user authorized the P0 PR on 2026-09-26, and this branch is that PR. The web feature's own delivery stays out of scope here.

## Constraints
| Constraint | Detail |
|------------|--------|
| Branch | New branch `fix/alert-timestamp-timezone-drift` off `main`, NOT on top of `feat/alert-web-ui`. This is a backend prerequisite, a different concern, and must not pollute the web feature's stacked slices. |
| TDD | OFF. No test framework additions. The regression test in T2 is a type assertion, not a RED/GREEN cycle. |
| RDD | Clone-local OFF. Do not start native review, do not change the mode. |
| Commits | Local commit authorized as an ODD work unit. Conventional Commits, English, no AI attribution. Push and the P0 PR against `main` authorized by the user on 2026-09-26. |
| Test runner | No local venv, no global `ruff`/`mypy`/`pytest`, and the host Python is 3.14 (project targets 3.12). **All checks run in a `python:3.12` container** replicating `.github/workflows/ci.yml`. |
| Artifacts | Code, tests, this doc and the commit message in English. |

### The Fix
```python
# api/app/models/alert.py — add to the sqlalchemy import block
from sqlalchemy import JSON, DateTime, ForeignKey, String, Text

# api/app/models/alert.py:100-103
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

# api/app/models/alert.py:128 (AlertDelivery)
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
```

## Verification

### ⚠ The test suite cannot catch this bug on its own
`api/tests/conftest.py:5` forces `DATABASE_URL=sqlite+aiosqlite:///:memory:`. SQLite ignores the `timezone=True` flag, so the suite passes identically with the naive columns. **A green pytest run is NOT evidence that the fix works.** The real proof is T4.

What T2 *can* legitimately do: assert the ORM *declaration* (`Alert.__table__.c.triggered_at.type.timezone is True`). That runs in CI, needs no Postgres, and prevents the regression from silently returning.

### T3 — static + test gate (CI-exact replica)
Working directory `api/`, inside a `python:3.12` container:
```bash
pip install -e ".[dev]"
ruff check --exit-non-zero-on-fix app/
mypy app
pytest -v --tb=short
```
Baseline recorded 2026-09-25: alerts tests 20/20, full suite 119 passed, ruff and mypy clean. Root README states `117 passed, 1 skipped, 1 xfailed, 2 xpass` as a preexisting baseline — record the ACTUAL numbers observed, do not assume.

### T4 — runtime proof (the real gate)
1. `alembic revision --autogenerate` must produce an **empty** migration (ORM now matches DB). Delete the generated stub.
2. Bring up the stack (db, redis, api, worker, web).
3. Seed: user → API key → server → rule → sustained metrics that breach the rule, with the **`worker` container running** (the alert engine only runs there).
4. Confirm an alert row is actually **CREATED** — this is the step that was silently failing. Not just an HTTP 200.
5. Re-run the ack → resolve round trip that returned 500.
6. Re-check `/alertas` SSR with a real alert row.
7. Confirm the delivery row's `delivered_at` is populated.

Operational notes carried from 2026-09-25:
- Docker Desktop is installed **per-user** at `C:\Users\Qchara\AppData\Local\Programs\DockerDesktop\`, not `C:\Program Files\Docker\`. Engine needs 60–90s to accept connections after launch.
- API health is `/healthz` or `/readyz`, not `/health`.
- `POST /auth/api-keys` returns the full key in `raw_key`, on creation only.
- `POST /api/v1/servers/register` returns the id as `id`, not `server_id`.
- No local `psql` or `redis-cli`. Compose is the only viable path.
- **PowerShell 5.1 JSON gotcha:** use `curl.exe --data-binary "@file"` for POSTs. Inline `-d '{...}'` gets mangled, `<` is a parse error, and `Invoke-WebRequest` leaked a FileSystem provider object graph into a payload producing a baffling 400.
- The demo JWT has a 12h TTL (compose override) and is almost certainly expired. Re-login as `verify.alertwebui@example.com` instead of debugging a 401. Demo credentials live outside the repo in `C:\Users\Qchara\AppData\Local\Temp\opencode\awui.*`.

## Evidence

### T1 — diff (38 insertions, 5 deletions, 2 files)
```
 api/app/models/alert.py  | 18 +++++++++++++-----
 api/tests/test_alerts.py | 25 +++++++++++++++++++++++++
```
- `api/app/models/alert.py` — `DateTime` added to the sqlalchemy import; the 4 columns now declare `DateTime(timezone=True)`. `nullable=` values untouched.
- `api/tests/test_alerts.py` — one new test, `test_alert_timestamp_columns_are_timezone_aware`, asserting `timezone is True` on the 4 columns via `Alert.__table__.c` / `AlertDelivery.__table__.c`.
- No other file touched. No migration created. Write sites untouched.

### T2 — the regression test can actually fail
| Scenario | Result |
|---|---|
| `triggered_at` reverted to naive `mapped_column(nullable=False)` | **FAIL** — `AssertionError: Alert.triggered_at must be DateTime(timezone=True)` |
| Fix restored | **PASS** |

### T3 — CI-exact gate, `python:3.12-slim` container, working dir `api/`
| Command | Observed result |
|---|---|
| `ruff check --exit-non-zero-on-fix app/` | All checks passed (it also alphabetized the import to `JSON, DateTime, ForeignKey, String, Text` — expected, the gate runs with `--fix`) |
| `mypy app` | Success: no issues found in 53 source files |
| `pytest tests/test_alerts.py -q` | **19 passed** (18 pre-existing + 1 new), 1 warning, 8.70s |
| `pytest -q` (full) | **118 passed, 1 skipped, 1 xfailed, 2 xpassed**, 1 warning, 32.40s |

Re-verified independently by the orchestrator (second container run, `--collect-only` included): 19 collected / 19 passed in `test_alerts.py`, 118 passed in the full suite.

**Pre-push gate (2026-09-26).** Re-run in a detached worktree at `91e8633` — the exact tree being pushed, not the feature branch — with ruff, mypy and both pytest scopes: `All checks passed!`, `no issues found in 53 source files`, `19 passed`, `118 passed, 1 skipped, 1 xfailed, 2 xpassed`. The counts matching this table, not the feature branch's 21/120, is what confirms the right tree was tested; `feat/alert-web-ui` carries 2 additional `test_alerts.py` tests from the ack-actor hardening.

**Baseline reconciliation:** root README records `117 passed, 1 skipped, 1 xfailed, 2 xpass` as preexisting. `117 + 1 new test = 118` — the suite is consistent and there is no regression. The "20/20 alerts" figure noted in the 2026-09-25 session was inaccurate; the real pre-change count was 18.

**Repo hygiene:** no `*.egg-info`, `__pycache__`, `.pytest_cache`, `.mypy_cache` or `.ruff_cache` leaked. Only untracked files are the two `odd/tasks/*.md` feature docs, which are untracked by design.

### Environment facts
- Docker Desktop is **per-user** at `C:\Users\Qchara\AppData\Local\Programs\DockerDesktop\`, not `C:\Program Files\Docker\`. Engine needs 60–90s after launch.
- `docker-compose.override.yml` is gitignored but present on disk, so the demo JWT TTL and `SPSAAS_DASHBOARD_TOKEN` injection survive a branch switch.
- Demo credentials from the 2026-09-25 session still on disk: `awui.apikey`, `awui.ruleid`, `awui.serverid`, `awui.token` under `C:\Users\Qchara\AppData\Local\Temp\opencode\`. The token is almost certainly expired (12h TTL) — re-login rather than debugging a 401.
- `main` does NOT contain the D1 Option A actor-identity hardening commit (the `fix(api): derive alert acknowledgement actor from the authenticated user` commit, +109/−13, 3 files). On this branch the ack endpoint still derives the actor from the request body — read the actual handler before calling it.

## Decisions
- 2026-09-26: user chose to include `AlertDelivery.delivered_at` in this fix rather than defer it — same defect, same root cause, same file; a partial fix would knowingly leave the delivery path broken.
- 2026-09-25: user chose to open this as a **distinct ODD task in `api/`** instead of silently folding a backend defect into the closed `alert-web-ui` feature.
- 2026-09-25: fix is on the ORM side, not the write sites. Aligning the model to the schema is correct; stripping UTC at the writers is not.
- 2026-09-26: this task branches off `main` rather than stacking onto `feat/alert-web-ui`, so the backend prerequisite lands independently of the web feature's chained PR slices.

### T4 — runtime proof against real Postgres
Stack: `db`, `redis`, `api`, `worker` (no `web` — irrelevant on this branch). Verified live on 2026-09-26.

**Ground truth first** — `psql \d alerts` and `\d alert_deliveries` confirm all four columns are `timestamp with time zone`, plus `created_at`/`updated_at` with `now()` defaults. The schema was never the problem.

**Step 1 — ORM now matches the schema.** `alembic revision --autogenerate` inside the `api` container produced a migration with **zero operations** touching the four columns. Only pre-existing unrelated diffs (RLS foreign keys, `JSON` vs `JSONB`, Python-side vs server-side defaults, indexes). Generated stub deleted; working tree restored.

**Step 2 — an alert is actually CREATED.** Engine facts read from the code, not guessed: evaluation runs on a **1-minute cron** (`alert-eval-1m`), and the rule's `duration_s` window requires every sample in it to breach. Rule `cpu_usage > 50`, `duration_s=10s`, severity `warning`. Ingested 4 samples of `cpu_usage=60`. Worker log:

```
alert_created alert_id=38ad9632-738e-452c-a01c-7c77c24ccb47 rule_id=535c1d6f-... severity=warning value=60.0
INSERT INTO alerts ... triggered_at=datetime.datetime(2026, 9, 26, 13, 25, 0, 342995, tzinfo=datetime.timezone.utc)
```

Postgres row:
```
 id                                    | status  | severity | triggered_at
 38ad9632-738e-452c-a01c-7c77c24ccb47 | open    | warning  | 2026-09-26 13:25:00.342995+00
```

**This is the step that was silently failing before. An alert now exists.**

**Step 3 — ack → resolve, the round trip that returned 500.**
| Call | HTTP | Response |
|---|---|---|
| `POST /api/v1/alerts/{id}/ack` | **200** | `{"status":"acknowledged","acknowledged_at":"2026-09-26T13:25:29.278926Z",...}` |
| `POST /api/v1/alerts/{id}/resolve` | **200** | `{"status":"resolved","resolved_at":"2026-09-26T13:25:36.192787Z",...}` |

Persisted state, all three carrying a `+00` offset:
```
 status    | triggered_at                  | acknowledged_at           | resolved_at
 resolved  | 2026-09-26 13:25:00.342995+00 | 2026-09-26 13:25:29.278926+00 | 2026-09-26 13:25:36.192787+00
```

Note the ack body contract: on this branch (off `main`, which lacks the D1 Option A actor-identity hardening commit) the handler still takes `acknowledged_by` from the request body.

**Step 4 — `delivered_at` proven.** The first delivery attempt used an unreachable dummy URL and failed, so `delivered_at` stayed NULL — a failed delivery never exercises the write. The rule's webhook channel was repointed at a reachable receiver, a new alert was triggered, and the delivery succeeded:
```
 id                                    | channel | status | delivered_at                   | external_ref
 532c9893-0291-4263-9e43-abad66e4683e | webhook | sent   | 2026-09-26 13:47:00.445788+00 | test-123
```
`delivered_at` persists with an explicit `+00` offset, and `external_ref` captured the receiver's `X-Request-Id`. All four columns are now proven, including the one this task added to scope.

**Step 5 — the error is gone.** `docker compose logs api` and `... worker` scanned for `DataError`, `offset-naive`, `offset-aware`, `traceback`: **zero occurrences**. Every logged SQL statement binds `datetime.datetime(..., tzinfo=datetime.timezone.utc)`.

**Orchestrator re-verification.** Independently re-queried Postgres and the git tree rather than trusting the worker's report: both alert rows and both delivery rows confirmed, `git status --short` shows exactly the 2 modified tracked files + 2 untracked docs, and only the 4 compose containers are running. Temp probe files were confirmed to predate this session (2026-09-25 20:43), so the workers did clean up after themselves.

### Residual gaps
- `web` alert channel, webhook retry/backoff, and multi-tenant isolation under concurrent load are untouched by this fix and remain unverified here.
- T4b is closed. The `/alertas` SSR check no longer gates anything on this feature; how it ran is recorded below.

### T4b — why it was deferred, and then how it ran
This branch is based on `main`, where `web/src/app/alertas/` does not exist (0 files — the alerts UI lives only in `feat/alert-web-ui`, which has since been merged to `main` as PRs #17–#26). The `/alertas` SSR re-check was therefore **not runnable here**, and it is not this task's responsibility: it verifies the *web* feature, not the backend fix.

T5 was therefore followed by a **cherry-pick of the timestamp fix (commit `91e8633`) onto `feat/alert-web-ui`**, and T4b ran there. Cherry-pick rather than merge, to keep the stacked-PR branch's history linear. The cherry-pick auto-merged `api/tests/test_alerts.py`, so the combination was re-verified: **21 alerts tests passed, 120 full suite passed** (the 2 extra tests over the fix branch belong to the `alert-web-ui` branch's D1 Option A actor-identity hardening commit).

That cherry-pick is now redundant. This feature shipped to `main` as PR #16 (merge `b1a2197`), so rebasing `feat/alert-web-ui` onto `main` drops it as an already-applied patch instead of duplicating it. The 21/120 counts stay valid, because the tests the dropped patch added are already on `main`.

T4b result: `/alertas` server-renders both real alert rows, and the filters and pagination work server-side.

| Request | Rows returned | Correct |
|---|---|---|
| `/alertas` | 2 | ✅ |
| `/alertas?status=open` | 1 — only `456dcf2e` | ✅ |
| `/alertas?status=resolved` | 1 — only `38ad9632` | ✅ |
| `/alertas?severity=warning` | 2 | ✅ |
| `/alertas?offset=1&limit=1` | 1, `hasNext=true` | ✅ |

Orchestrator re-verification with its own `curl.exe`: the SSR HTML is 25,742 bytes and contains both alert ids, the alert message and 7 status/severity badge occurrences; `?status=open` contains the open alert and **zero** occurrences of the resolved one. Tenant alignment was established explicitly — the dashboard token's tenant and the alert rows' tenant are the same (`1f350381-dea0-4f2f-8a29-7daab42225bf`), which is the thing this page actually exercises.

This unblocks T2 of `alert-web-ui`. See `odd/tasks/alert-web-ui.md` for the updated status and for what still needs a real browser.

## Next Steps
1. **The `alert-web-ui` chain has been opened and merged as stacked PRs #17–#26 against `main`**. Chain strategy `stacked-to-main` was confirmed. Slice #1 was split into three independently-green commits: typed server-only alerts API client (109 lines), read-only overview page + table (444), app shell + navigation (42). Slices #3 and #4 carried a recorded `size:exception`; the 444-line commit was deliberately not reduced further because the only smaller seam breaks the page-to-table import.
2. Nothing is pending on the backend side. This fix is on `main` via PR #16, merge `b1a2197`, and the push/PR authorization is spent.
3. Browser-verification status for the alerts UI is no longer tracked here — it lives in `odd/tasks/alert-web-ui.md`, which records the click-through and its findings.
4. Worth considering separately: a Postgres-backed test profile. SQLite ignoring the timezone flag is why this defect could sit unnoticed behind a fully green suite — and it is the second time this suite has hidden Postgres-only bugs (see `T9`).
