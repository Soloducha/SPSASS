# Feature: alert-web-ui — Web UI for Alert Management (list, ack/resolve, rules)

## Objective
Build a tenant-scoped web UI in the existing Next.js 16 dashboard (`web/`) that lets operators view alerts, acknowledge/resolve them, and manage alert rules — all against the already-complete backend `/api/v1/alerts` API.

## Problem
The backend exposes a full alerts API (list, acknowledge, resolve, rules CRUD) but the dashboard only has a single placeholder page. Operators cannot act on alerts from the web.

## Rationale
- Backend `/api/v1/alerts` is complete and tenant-scoped. The only backend change was the actor-identity hardening (D1 Option A), now landed in `fd84c7e`.
- Dashboard uses Next.js 16 App Router with Server Components and Server Actions — fits the architecture.
- `SPSAAS_DASHBOARD_TOKEN` must remain server-only; each Server Action independently validates it before calling the backend.
- **The acting user for an acknowledgement comes from the authenticated user's id, resolved server-side by the API.** The web never decodes the JWT and never sends an actor.
- Work-unit commits map to chained PR slices (`stacked-to-main`); forecast >400 lines triggers slice planning.

## Verified Auth Facts (2026-09-25, code inspection)
These replace any assumption derived from the env var name:
- **There is no dashboard/service token in the API.** `grep dashboard_token api/` → zero matches. `/api/v1/dashboard/overview` and every `/api/v1/alerts` endpoint require `user: CurrentUser` — a real user access JWT via `Authorization: Bearer <access_token>` (`api/app/core/auth/dependencies.py:45-81`).
- Therefore `SPSAAS_DASHBOARD_TOKEN` is a **misnomer**: it must hold a live, non-expired user access token or every dashboard call returns 401.
- `acknowledge_alert` (`api/app/api/v1/alerts.py:133-160`) **used to** take `acknowledged_by` from the request body, trusting the client about who acted. **This was the defect fixed in `fd84c7e`**: the actor is now always `user.id`. Kept here as the audit trail of what changed.
- `resolve_alert` takes no body. Both return `AlertAckResponse { id, status, acknowledged_at, resolved_at, acknowledged_by }`.
- Consequence: the dashboard has no login; a hand-copied expiring JWT is the entire auth story. T2 mutations make expiry immediately user-visible.

## Authorized Scope
- **T1**: Server-only typed alert/rule data access; root navigation; `/alertas` read-only list with GET filters and bounded offset pagination; config/error state consistent with current dashboard.
- **T2**: Acknowledge/resolve Server Actions; the acting user is resolved by the API from the authenticated principal (D1 Option A) — the web sends no actor; accessible pending/success/error feedback; refresh/revalidate after mutation.
- **T3**: `/alertas/reglas` list + create form; server selector from dashboard overview; actual schema/channel validation; no raw UUID entry when overview provides servers (entity_id may remain optional/all servers).
- **T4**: Edit active/channel fields + delete confirmation + responsive/accessibility polish.
- **T5**: Verify/update existing SMTP env documentation (`api/.env.example`, root README only if actually incomplete), record unresolved production activation inputs, run full web checks, finalize evidence.

## Out of Scope
- Backend API changes — **only** the D1 Option A actor-identity hardening, which is already implemented and committed (`fd84c7e`).
- New authentication flows — reuse existing dashboard auth (i.e. the JWT in `SPSAAS_DASHBOARD_TOKEN`); a real web login is a separate feature.
- Real-time updates (polling is sufficient for v1).
- Telegram/WhatsApp channels (future).
- Changes to `Tenant.settings` or evaluation engine.
- Reading `.env*` files or inventing secrets — only documented SMTP variables.
- Login middleware/redirect, Zod, toast library, axe-core, test framework, polling, skeletons, sortable columns, date filters, `/api/v1/servers` endpoint.
- There is no web auth/login UI.

## Constraints
| Constraint | Detail |
|------------|--------|
| Framework | Next.js 16 App Router — Server Components for reads, Server Actions for mutations |
| Token handling | `SPSAAS_DASHBOARD_TOKEN` server-only; never passed to client components |
| Validation | Each Server Action independently gets/validates token before backend call |
| User identity | Never client-supplied. The API resolves the actor from the authenticated principal (`user.id`); the web sends no `acknowledged_by` and decodes no JWT |
| Backend API | `/api/v1/alerts` — tenant-scoped and complete; the only change was the D1 actor-identity hardening in `fd84c7e` |
| SMTP variables | `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_STARTTLS` only |
| Testing | TDD OFF — no strict config, no SDD init. Ordinary checks from `web/`: `pnpm lint`, `pnpm exec tsc --noEmit`, `pnpm build`. API tests only if backend changes. |
| RDD | Clone-local OFF; do not start review or change it. |
| Commits | Local commits authorized as ODD work units; push/PR not authorized. |
| Delivery | Strategy `ask-on-risk`; chain preference `stacked-to-main`. |

## API/UI Contracts

### Backend Endpoints (existing — exact)
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/alerts/rules?offset=&limit=` (1..500) | List rules with pagination |
| POST | `/api/v1/alerts/rules` | Create rule |
| GET | `/api/v1/alerts/rules/{rule_id}` | Get single rule |
| PATCH | `/api/v1/alerts/rules/{rule_id}` | Update rule |
| DELETE | `/api/v1/alerts/rules/{rule_id}` | Delete rule (204) |
| GET | `/api/v1/alerts?status=&severity=&rule_id=&offset=&limit=` | List alerts with filters |
| POST | `/api/v1/alerts/{alert_id}/ack` | Acknowledge alert. Body `{}`; the `acknowledged_by` field is **deprecated and ignored** (actor = authenticated user) |
| POST | `/api/v1/alerts/{alert_id}/resolve` | Resolve alert (no body) |

All endpoints use JWT Bearer auth and tenant scoping. Common errors: 401, 404, 422.

**Not available**: `/api/v1/servers` (register/heartbeat only, API-key auth), `/api/v1/alert-rules`, `/acknowledge`, `{user_id}` ack body, `server_id` alert filter, `page`/`size` params.

### UI Routes (new — match existing root dashboard + Spanish copy)
| Route | Type | Purpose |
|-------|------|---------|
| `/alertas` | Server Component | Alerts list with filters, bounded offset pagination, actions |
| `/alertas/reglas` | Server Component | Rules list with create/edit/delete |
| `/alertas/reglas/nueva` | Server Component + Client | Create rule form with server selector |
| `/alertas/reglas/[id]/editar` | Server Component + Client | Edit rule form |

### Server Actions (new)
| Action | Input | Output | Auth |
|--------|-------|--------|------|
| `alertAction(alertId, intent)` | `alertId: string`, `intent: 'ack' \| 'resolve'` | `{ status: number \| null, message: string }` | `getDashboardToken()` only — **no actor, no JWT decoding** |
| `createAlertRule(data)` | `AlertRuleCreate` | `{rule: AlertRule, error?: string}` | Token |
| `updateAlertRule(id, data)` | `id: string, data: AlertRuleUpdate` | `{rule: AlertRule, error?: string}` | Token |
| `deleteAlertRule(id)` | `id: string` | `{success: boolean, error?: string}` | Token |

## Accessible Spanish-UI Requirements
- **Language**: All user-facing text in neutral/professional Spanish (no regional slang, no voseo in artifacts). Example: "Alertas", "Reglas", "Reconocer", "Resolver", "Crear regla", "Editar", "Eliminar".
- **Accessibility (verifiable without unrun axe)**: Semantic HTML, labels, keyboard access, visible focus, 44px touch targets, `aria-live` status feedback, responsive horizontal scrolling or card layouts, contrast-safe Tailwind classes.
- **Responsive**: Mobile-first; tables use horizontal scroll or card layout <768px; forms single-column; touch targets ≥44×44px.
- **Loading/Error states**: Inline error banners with dismiss; `aria-live` region for action feedback; no skeleton loaders, no toast library.
- **Empty states**: Illustrative empty states with primary action (e.g., "Crear primera regla").

## Stable Checklist (T1–T5)

### T1 — Server-Only Data Access + Navigation + Read-Only Alerts List
- [x] Reuse `web/src/lib/config.ts` helpers (`getDashboardToken`, `getSpsaasApiUrl`) for token/API URL — no duplicate auth helper. **No JWT-decoding helper was ever needed and none must be added** (D1 Option A removed that requirement).
- [x] `web/src/lib/api/alerts.ts`: Typed fetch wrappers for `/api/v1/alerts` (list only — read-only for T1) — server-only. `acknowledgeAlert`/`resolveAlert` and their types removed (T2 scope).
- [x] `web/src/lib/api/rules.ts`: **Deleted from T1** (T3 scope). Rule fetch wrappers will be added in T3.
- [x] `web/src/app/alertas/page.tsx`: Server Component — fetches alerts (offset=0, limit=50, default filters), renders table with bounded previous/next pagination (no total count), severity badges, status chips. Added `export const dynamic = 'force-dynamic';`.
- [x] `web/src/app/alertas/components/AlertsTable.tsx`: Client Component — interactive filters (status, severity, rule_id as UUID text input), bounded prev/next pagination controls. **No action buttons** (T2 scope). Date locale: neutral `es`, **formatted in UTC** (`timeZone: 'UTC'`, `hourCycle: 'h23'`, header "Disparada (UTC)") — corrected 2026-09-26 after the click-through proved a bare locale render produced a hydration mismatch and wrong local times.
- [x] Root navigation: Add "Alertas" nav item in existing dashboard layout (`web/src/app/layout.tsx`); highlight active.
- [x] Error state: Use existing missing-token error pattern from `web/src/app/page.tsx` (no new middleware/redirect).
- [x] Breadcrumb uses `next/link` `Link` (not plain `<a>`).
- [x] **Evidence placeholder**: Commit SHA; `pnpm lint` ✅ `pnpm exec tsc --noEmit` ✅ `pnpm build` ✅ from `web/`.

### T2 — Acknowledge/Resolve Actions with Accessible Feedback — ✅ DONE
- [x] `web/src/app/alertas/actions.ts`: **single** Server Action `alertAction` (the two near-duplicate exports were collapsed) — server-side validates `alertId` (UUID shape) and `intent` (`ack` | `resolve`) before any fetch, reads the token via `getDashboardToken()`. **Sends NO `acknowledged_by` and does NOT decode the JWT** — the API owns identity since `fd84c7e`. Calls `revalidatePath('/alertas')` on success. Returns a typed `{ status, message }`, never throws to the client.
- [x] HTTP status is a **typed value** (`FetchResult<T>.status: number | null`), never parsed out of an error string — `mapApiError` branches on 404 / 401 / 422 / other, and can only ever return a non-empty string. **Corrected 2026-09-26:** any other status used to return the raw API `detail`, which for a 422 is a Pydantic error *array* — rendering it as a React child threw `throwOnInvalidObjectType` and unmounted the whole table. Error prose stays neutral Spanish; raw backend English details never leak into the UI.
- [x] `web/src/app/alertas/components/AlertActions.tsx`: Client Component — one `<form>` per row, two submit buttons via `name="intent"`; both disabled during submission (no double-submit, no optimistic UI); "Procesando…" only on the submitted button (`pendingIntent` local state); `aria-live="polite"` region **always rendered**; `min-h-[44px] min-w-[44px]`; visible focus. "Reconocer" only when `open`, "Resolver" only when not `resolved`.
- [x] Revalidation: `revalidatePath('/alertas')` after success.
- [x] Evidence: `5c04948` (feature) → `72dda44` (corrective, −7 net lines). `pnpm lint` ✅ `pnpm exec tsc --noEmit` ✅ `pnpm build` ✅ from `web/` (orchestrator re-ran `pnpm build`, exit 0).

### T3 — Rules List + Create Flow with Server Selector from Overview — ✅ DONE
- [x] `web/src/lib/api/rules.ts`: NEW — typed server-only wrappers for the rule endpoints, reusing `config.ts` helpers and the `FetchResult<T>` typed-status pattern.
- [x] `web/src/lib/api/dashboard.ts`: NEW — reads the server list from `GET /api/v1/dashboard/overview` (`/api/v1/servers` does not exist).
- [x] `web/src/app/alertas/reglas/page.tsx`: Server Component — rules (bounded offset pagination) + servers from overview; renders entity_type, entity_id, metric, operator, threshold, duration_s, severity, channels, is_active, actions. `export const dynamic = 'force-dynamic'`.
- [x] `web/src/app/alertas/reglas/components/RulesTable.tsx`: Client Component — enable/disable toggle via Server Action, delete with native `confirm()`, no sortable columns, no optimistic UI, no polling, `aria-live` feedback, 44px targets.
- [x] `web/src/app/alertas/reglas/nueva/page.tsx`: Server Component — fetches servers for the selector, honest empty-state.
- [x] `web/src/app/alertas/reglas/nueva/components/CreateRuleForm.tsx`: Client Component — controlled form mirroring the backend schema, server selector from overview, `email.to[]` required when email chosen, optional webhook `url` + headers, ≥1 channel enforced client AND server, no invented `name` field, `entity_id` optional.
- [x] `web/src/app/alertas/reglas/actions.ts`: Server Actions `createAlertRule`, `toggleRuleEnabled`, `deleteAlertRule` — each validates the token independently before any fetch; input validated before fetch; errors mapped by typed HTTP status into neutral Spanish.
- [x] Nav: "Reglas" entry added to `web/src/app/layout.tsx` alongside "Alertas".
- [x] **Evidence**: `9236c16` — `feat(web): add alert rules list and create flow`. 1628 insertions / 5 deletions, 11 files, net +1674 vs `72dda44`. `corepack.cmd pnpm lint` ✅ 0 errors 0 warnings · `corepack.cmd pnpm exec tsc --noEmit` ✅ · `corepack.cmd pnpm build` ✅ 4 dynamic routes — **all three re-run by the orchestrator on the settled tree**, exit 0.
- [x] **Independent verification**: contract fidelity verified line-by-line against the backend (`api/app/schemas/`, `api/app/models/alert.py`, `api/app/api/v1/dashboard.py`) — all 11 claimed enum values, defaults, required/optional flags, channel shape and overview server fields **confirmed**. Token stays server-only, no JWT decoding anywhere, every Server Action re-validates independently: **confirmed**.

#### T3 findings carried into T4 (honest, not silently dropped)
| Finding | Evidence | Disposition |
|---------|----------|-------------|
| `entity_id` UUID shape is validated client-side but NOT re-validated in `createAlertRuleAction` before the fetch | `reglas/actions.ts` — backend returns 422, so it fails closed, but server-side defense-in-depth is missing | Fix in T4 alongside `updateAlertRule`, which needs the same guard |
| T4 forward-declarations present but unused: `getAlertRule`, `updateAlertRule`, `AlertRuleUpdate` | `web/src/lib/api/rules.ts` | Intentionally left: T4 wires them. Deleting and re-adding would be churn |
| `CreateRuleForm.tsx` is 617 lines with validation duplicated from the Server Action | `reglas/nueva/components/CreateRuleForm.tsx` | Accepted for T3 (instant feedback needs client validation). Extraction deferred; **Zod is explicitly out of scope** |
| No stacked/card layout below 768px, only `overflow-x-auto` | `reglas/components/RulesTable.tsx` | T4 responsive requirement; horizontal scroll satisfies the T3 slice |

### T4 — Rule Edit/Delete + Responsive/Accessibility Polish — ✅ DONE
- [x] `web/src/app/alertas/reglas/[id]/editar/page.tsx`: Server Component — fetches the single rule + servers from overview in parallel, renders the edit form pre-filled. `export const dynamic = 'force-dynamic'`. Distinct honest states: 404 → `notFound()`, missing token → the dashboard's missing-token pattern, other → neutral Spanish `role="alert"` banner.
- [x] `web/src/app/alertas/reglas/[id]/editar/components/EditRuleForm.tsx`: Client Component — pre-filled including the current channel config (email recipients, webhook url + headers). Editable: `is_active`, `channels`, `entity_type`, `entity_id`, `metric`, `operator`, `threshold`, `duration_s`, `severity`. Same validation semantics and constants as the create form. `entity_id` optional, ≥1 channel required, submit disabled while pending, accessible inline errors, `aria-live` feedback.
- [x] `web/src/app/alertas/reglas/actions.ts`: `updateAlertRule` Server Action — validates the token independently, validates rule id and payload (including the new `entity_id` UUID guard) before the fetch, maps errors by typed status, revalidates, never throws raw backend errors.
- [x] Carry-over from T3: **`entity_id` UUID guard added server-side to both `createAlertRuleAction` and `updateAlertRuleAction`** (T3 findings table).
- [x] Delete confirmation: native `confirm()` replaced with an accessible native `<dialog>` — labelled, `aria-modal`, focus moved in on open, focus restored to the trigger on close, Escape and backdrop dismissal, names the rule being deleted, full-screen below 640px.
- [x] Responsive: rules table gained a stacked card layout below 768px (`sm:hidden` / `hidden sm:block`) alongside horizontal scroll; forms single-column on mobile; touch targets ≥44×44px.
- [x] Accessibility: labels for all inputs, visible focus rings, `aria-live` for action feedback, semantic HTML. Severity chip contrast fixed to clear WCAG AA (`bg-gray-100 text-gray-800` → `text-gray-700`; info chip now `bg-blue-100 text-blue-800`).
- [x] Spanish copy reviewed: neutral/professional, consistent terminology throughout.
- [x] **Evidence**: `7ff278d` — `feat(web): add alert rule editing and accessible delete confirmation` (1245 insertions / 101 deletions, 4 files) + corrective **`89e7568`** — `fix(web): guard dialog open call and use typed status in rule edit page` (53 insertions / 31 deletions, 4 files). `corepack.cmd pnpm lint` ✅ 0 errors 0 warnings · `corepack.cmd pnpm exec tsc --noEmit` ✅ · `corepack.cmd pnpm build` ✅ 5 dynamic routes — **all three re-run by the orchestrator on the settled tree after the corrective**, exit 0.

#### T4 defects found by orchestrator code reading and fixed in `89e7568`
Both were invisible to lint, type-check and build — the same failure class as the T1 dead feature. Found by reading the code, not by trusting the writer's report.

1. **BLOCKER — the delete confirmation dialog could crash on use.** `ConfirmDialog`'s effect depended on `[isOpen, onClose, triggerElement]` and unconditionally called `dialog.showModal()`. `closeDeleteDialog` was a plain function with no `useCallback`, so it got a new identity on every render of `RulesTable`; every re-render while the dialog was open therefore re-ran the effect and called `showModal()` on an already-modal dialog, which throws `InvalidStateError` per the HTML spec. Concrete trigger: `handleDeleteConfirm` calls `setIsLoading(true)` → re-render → effect re-runs → throw. React StrictMode's dev double-invoke hits the same path. **Fixed** with `if (!dialog.open) dialog.showModal()` (and the symmetric guard on `close()`), plus `useCallback` on the handlers, plus deterministic focus via `useLayoutEffect` replacing a `setTimeout(..., 0)` hack. The misleading doc comment claiming "inert via aria-modal" was corrected: `aria-modal` makes nothing inert — native `<dialog>` + `showModal()` (top layer) is the real mechanism.
2. **BLOCKER — the edit page detected 404 by sniffing the error string** with `ruleError.includes('404')`, the exact anti-pattern `72dda44` removed from T2, while the typed `status` sat unused. `error` is populated as `err.detail ?? \`HTTP ${status}\`` (`web/src/lib/api/rules.ts:104-111`) — the **raw backend detail**, which for a FastAPI 422 can contain arbitrary submitted values. So a 422 whose detail happened to contain the substring "404" falsely rendered `notFound()`, and a genuine 404 without that substring rendered the wrong state. **Fixed** by destructuring `status` and branching on `status === 404`. The two raw-detail leaks (`No se pudo cargar la regla: {ruleError}` and the overview equivalent) were also closed by extracting the shared Spanish mapping into `web/src/app/alertas/reglas/utils.ts` (`mapApiError`), now used by both the page and the Server Actions.
   - Note: one string check intentionally remains — `ruleStatus === null && ruleError.includes('Token de dashboard no configurado')`. That sentinel is produced by **our own** code (`rules.ts:89`), not by the backend, and the missing-token case has no HTTP status by design. It is not status sniffing.

### T5 — SMTP Docs Verification + Full Web Checks + Evidence — ✅ DONE
- [x] `api/.env.example`: **all six SMTP variables were missing** and were added with placeholder values and inline comments: `SMTP_HOST=`, `SMTP_PORT=587`, `SMTP_USER=`, `SMTP_PASSWORD=`, `SMTP_FROM=`, `SMTP_STARTTLS=true`. No secrets invented, no `web/.env.example` created.
- [x] Root `README.md`: already complete (six variables, correct defaults, "empty = disabled" semantics, login-only-if-user-provided). **No change needed** — verified, not rewritten.
- [x] `api/app/workers/delivery/README.md`: already complete (lists all six from `core/config.py`, notes email is disabled → `config_missing` unless `smtp_enabled`). **No change needed.**
- [x] Production activation status: **BLOCKED**, recorded. Requires a destination address, real SMTP provider credentials, and explicit remote-operation authorization. No SMTP host was contacted, no account configured, nothing attempted outside the repository.
- [x] Full verification from `web/`: `corepack.cmd pnpm lint` ✅ **0 errors 0 warnings** · `corepack.cmd pnpm exec tsc --noEmit` ✅ · `corepack.cmd pnpm build` ✅ 5 dynamic routes — **re-run by the orchestrator on the final settled tree**, exit 0.
- [x] **Evidence**: `5bc5d00` — `docs: document SMTP configuration for alert email delivery` (+10/−1, `api/.env.example` only) + corrective **`aa16133`** — `docs: correct SMTP port comment to reflect STARTTLS-only support` (1 line, same file).

#### SMTP semantics as found in the code (source of truth for the docs)
| Variable | Type | Default | Semantics |
|----------|------|---------|-----------|
| `SMTP_HOST` | `str` | `""` | Required for email. Empty = email delivery disabled. Part of `smtp_enabled` |
| `SMTP_PORT` | `int` | `587` | Validated 1–65535 (`api/app/core/config.py:110`). Submission port with STARTTLS |
| `SMTP_USER` | `str` | `""` | Optional. Login attempted only when non-empty (`email.py:156`) |
| `SMTP_PASSWORD` | `str` | `""` | Used only when `SMTP_USER` is set |
| `SMTP_FROM` | `str` | `""` | Required for email. Empty = email delivery disabled. Part of `smtp_enabled` |
| `SMTP_STARTTLS` | `bool` | `true` | When true, calls `smtp.starttls()` after a plaintext connect |

`smtp_enabled` is true **only when both `SMTP_HOST` and `SMTP_FROM` are non-empty**; otherwise the email channel raises `DeliveryError(reason="config_missing")`.

#### Defect found by orchestrator and fixed in `aa16133`
The first pass documented `SMTP_PORT` as *"default 587; 465 for implicit TLS"*. **That was wrong.** `api/app/workers/delivery/email.py:153` uses a plain `smtplib.SMTP(...)` connection upgraded with `smtp.starttls()` (line 155); there is **no `SMTP_SSL` anywhere in `api/app`**. A plain socket cannot negotiate implicit TLS, so port 465 cannot work — the comment would have led an operator straight to a configuration this implementation cannot deliver. Corrected to state that 587 is the STARTTLS submission port and that implicit TLS on 465 is not supported.

## Acceptance Criteria
| ID | Criterion | Verification |
|----|-----------|--------------|
| AC1 | Alerts list loads with bounded pagination, filters (status, severity, rule_id) work, severity/status badges render correctly | ✅ **Real browser, 2026-09-26** — filters reach the URL, `limit=1` forces `hasNext` and both controls advance, 0 hydration errors |
| AC2 | Acknowledge action: button shows pending, on success `aria-live` feedback appears, row updates to `acknowledged`. Actor comes from the authenticated user server-side — the web sends no `acknowledged_by` (D1 Option A) | ✅ **Real browser** — `Abierta → Reconocida`, both buttons `disabled` + `aria-busy` in flight, `aria-live` announced, HTTP 200. ⚠️ The per-button pending label is verified by code review only; it needs a new alert in a mutable state |
| AC3 | Resolve action: same flow, row updates to `resolved` | ✅ **Real browser** — `Reconocida → Resuelta`, HTTP 200, `aria-live` announced |
| AC4 | Rules list loads, enable/disable toggles work, delete shows confirmation | Manual (static checks + API round trips) |
| AC5 | Create rule: form validates, server selector populated from dashboard overview, email/webhook channel config saved, requires ≥1 channel | Manual + backend check |
| AC6 | Edit rule: pre-fills data, updates active/channel fields correctly | Manual (HTTP 200 + `PATCH`/`DELETE` round trips) |
| AC7 | Spanish UI: all copy neutral/professional Spanish, no console errors | ✅ **Real browser** — 0 pageerrors, 0 hydration errors, 0 dev overlay |
| AC8 | Accessibility: semantic HTML, labels, keyboard nav, visible focus, 44px targets, `aria-live` feedback, responsive scroll/cards, contrast-safe classes | Manual audit |
| AC9 | Responsive: <768px tables→scroll/cards, forms stack, touch targets ≥44px | Manual resize + device toolbar |
| AC10 | SMTP docs verified in existing locations (`api/.env.example`, delivery README, root README if incomplete); production activation blocked recorded | File review |
| AC11 | All checks pass: `pnpm lint`, `pnpm exec tsc --noEmit`, `pnpm build` from `web/` | CI/local run |

## Exact Checks
Run from `web/` directory. **`pnpm.cmd`, not bare `pnpm`** (see Environment Note 1 — bare `pnpm` in PowerShell can resolve a `.PS1` shim and trigger the "Windows wants to run this script" prompt; `corepack.cmd pnpm` is a valid fallback):
```bash
pnpm.cmd lint                # ESLint — must report ZERO errors AND ZERO warnings
pnpm.cmd exec tsc --noEmit   # TypeScript type-check (zero errors)
pnpm.cmd build               # Next.js production build (success)
```
No test command required (TDD OFF). No web test framework exists. API tests only if backend changes (out of scope).

**These three are not sufficient on their own.** A green build proved nothing about T1: the filters and pagination were dead at runtime and every check still passed. Any UI wiring whose data path is not exercised against a live backend is **unverified** until clicked through.

This has now happened three times in this feature — T1's dead filters, T4's dialog crash, and six client-interaction defects in the 2026-09-26 click-through — with a fully green `lint` / `tsc` / `build` / test suite every time. Treat static checks as a floor, never as evidence of behaviour.

## Delegated-Direct Routing / Trigger Evidence
| Task | Routing | Writer | Files Touched (est.) | Trigger |
|------|---------|--------|---------------------|---------|
| T1 | delegated direct | general | 6–8 | ODD task start |
| T2 | delegated direct | general | 3–5 | T1 complete |
| T3 | delegated direct | general | 7–9 | T2 complete |
| T4 | delegated direct | general | 5–7 | T3 complete |
| T5 | delegated direct | general | 2–3 | T4 complete |
| T1+T2 click-through fix | delegated direct | general | 3 | Six defects found only by a real browser — 2+ non-trivial files, writer trigger fired |

Each task: 2+ files; mapping by orchestrator. The click-through fix was verified with `npm.cmd run lint` and `npm.cmd run build` (exit 0 both, 5 dynamic routes) and then reviewed line-by-line against the captured browser evidence.

## >400-Line Forecast and `stacked-to-main` Slice Boundaries

### Forecast
Estimated **~750–950 authored lines** across 5 tasks (components, actions, types, styles, docs). Exceeds 400-line review budget → chained PRs required. The ~400 threshold is a planning/delivery heuristic; honest count is higher.

### Slice Boundaries (stacked-to-main — CONFIRMED 2026-09-25, re-measured 2026-09-26)

Measured as real net diffs between adjacent commits, not estimates. **The 2026-09-25 estimates were materially wrong and are corrected here** — slice #4 was recorded as "~250–400" when it is actually 1.7× that.

| PR Slice | Tasks | **Measured lines** | vs ~400 budget | Base Branch | Notes |
|----------|-------|--------------------|----------------|-------------|-------|
| **#1** | T1 | **594** | ⚠️ 1.5× over | `main` | Foundation: `lib/api/alerts.ts`, `alertas/page.tsx`, `AlertsTable.tsx`, layout nav. Natural seams exist (data access / page / table) |
| **#1b** | D1 API hardening | **122** | ✅ | `#1` | Security fix landed in the same branch. Recommend cutting it as its own PR — it is an API audit-integrity change, not web scope |
| **#2** | T2 | **266** | ✅ | `#1` | Actions: ack/resolve Server Actions + accessible feedback |
| **#3** | T3 | **1.633** | ❌ **4× over** | `#2` | Rules: `lib/api/rules.ts` + `dashboard.ts`, Server Actions, `page.tsx` + `RulesTable.tsx`, `nueva/*`. Documented split already exists in the T3 checklist |
| **#4** | T1 fix + T4 + T5 | **1.494** | ❌ **3.7× over** | `#3` | ⚠️ **Was mis-estimated as ~250–400.** Really `589aab2` (T1 fix) + T4 edit form + delete dialog + a11y/responsive + SMTP docs. Three unrelated concerns in one slice |
| **#5** | timestamp fix | **298** | ✅ | `#4` | ⚠️ **Does not belong in this chain at all** — it is a P0 backend fix and must reach `main` independently and first |
| **#6** | click-through fix | **469** (56 code + 393 doc) | ⚠️ boundary | `#5` | Code is well under budget; the count is inflated by this tracking document. Recommend the doc lands with slice #1 or on its own |

**Total against `main`: 4.465 authored lines across 7 slices.** Three slices are materially over budget: #1 (1.5×), #3 (4×) and #4 (3.7×).

**Critical constraint, verified 2026-09-26: the branch has never been pushed.** `feat/alert-web-ui` has no upstream, and the only remote branch is `origin/main`. Local history rewriting is therefore free right now — no force-push, no shared history, no broken reviewers. This is the cheapest moment a split will ever be, and it stops being free the moment the first PR opens.

**Delivery strategy**: `ask-on-risk` — confirmed with the user on 2026-09-25, who chose **`stacked-to-main`** when shown the over-budget branch. Chain strategy is cached. Whether to split #1/#3/#4 or record a `size:exception` is the user's call and is still open. No PR is authorized.

## Progress / Evidence Placeholders

| Task | Status | Commit SHA | Checks | Notes |
|------|--------|------------|--------|-------|
| T1 | ✅ Done | **b8057e6** (corrects ecb92ab) | `pnpm lint` ✅ `pnpm exec tsc --noEmit` ✅ `pnpm build` ✅ | 594 authored lines (594 add, 1 del), 4 files. Original ecb92ab (845 lines, 5 files) contained T2/T3 scope removed by this correction: deleted `rules.ts`, removed `acknowledgeAlert`/`resolveAlert` and their types from `alerts.ts`, removed nonfunctional action buttons from `AlertsTable.tsx`, added `force-dynamic`, changed date locale to neutral `es`, replaced breadcrumb `<a>` with `Link`. Independent verifier: `pass-with-warnings`, no blockers/criticals after correction. Native assess on the correction: `medium`, `review_due: false`, `under_budget`. Parent spot check `pnpm lint` re-run by orchestrator: exit 0. |
| **D1 Resolution (Option A)** | ✅ Done | **fd84c7e** | `python -m pytest tests/test_alerts.py` ✅ 20/20 passed<br>`python -m pytest tests/` ✅ 119 passed<br>`ruff check app tests` ✅<br>`mypy app` ✅ | API hardening: `acknowledged_by` from `user.id`, body field deprecated/ignored, 404 preserved, log reports authoritative actor, 2 new regression tests + updated existing tests |
| T2 | ✅ Done | **5c04948** → **72dda44 (corrective)** | `pnpm lint` ✅ `pnpm exec tsc --noEmit` ✅ `pnpm build` ✅ | 259 authored lines (259 add, 4 del), 4 files. Added `AlertAckResponse` type, `acknowledgeAlert`/`resolveAlert` in `alerts.ts`; Server Actions `acknowledgeAlertAction`/`resolveAlertAction` in `actions.ts` (each validates token independently, UUID validation, intent validation, honest error mapping 404/401/other); `AlertActions` Client Component with single form per row, two submit buttons via `name="intent"`, `useFormStatus` for pending/disable, `aria-live` feedback, `min-h-[44px] min-w-[44px]` touch targets; `AlertsTable` adds actions column. Neutral/professional Spanish copy: "Reconocer", "Resolver", "Procesando…". **Corrective 72dda44 (-7 net lines, 3 files)**: (1) `FetchResult<T>` with typed `status: number | null` returned by `fetchWithAuth`/`acknowledgeAlert`/`resolveAlert` — eliminates regex parsing of error messages; `mapApiError` now branches on numeric status directly. (2) `actions.ts` uses `getDashboardToken()` helper (was direct `process.env` read). (3) Collapsed `acknowledgeAlertAction` + `resolveAlertAction` into single `alertAction` — server-side validates both `alertId` (UUID) and `intent` (`ack`|`resolve`); removed client-side intent dispatcher. (4) `AlertActions.tsx`: `aria-live` region always rendered (was conditional); per-button pending label via local `pendingIntent` state (was both buttons showing "Procesando…"). T1 behavior (filters, pagination, error/empty states) unchanged. |
| T3 | ✅ Done | **9236c16** | `corepack.cmd pnpm lint` ✅ 0/0<br>`corepack.cmd pnpm exec tsc --noEmit` ✅<br>`corepack.cmd pnpm build` ✅ | 1628 authored insertions, 11 files. Rules list + create flow with server selector from dashboard overview. Independent verifier **confirmed all 11 backend contract claims** against the API source. Native assess: `medium`, `review_due: true`, `slice_budget_reached` (1633 lines vs the ~400 budget). Four findings carried into T4 (see T3 findings table). |
| **T1 defect fix** | ✅ Done | **589aab2** | `corepack.cmd pnpm lint` ✅ **0 errors, 0 warnings**<br>`corepack.cmd pnpm exec tsc --noEmit` ✅<br>`corepack.cmd pnpm build` ✅ | **Discovered during T3 verification**: T1's filters and pagination were non-functional at runtime. `AlertsTable.fetchAlerts` called the `onFetch` prop, which was an EMPTY stub in `alertas/page.tsx` whose comment said *"In a full implementation with T2, we'd use Server Actions"*. `setAlerts`/`setHasNext` were therefore never called and the table always rendered `initialAlerts` — AC1 was not actually met, hidden behind a green build. Fix: URL-driven navigation via `useRouter`/`usePathname`; the dead `onFetch` prop, the empty stub, the unused `newParams` param and the unused `AlertResponse` import are gone. 46 insertions / 53 deletions. |
| **T1+T2 click-through fix** | ✅ Done | *(pending commit)* | `npm.cmd run lint` ✅ exit 0<br>`npm.cmd run build` ✅ exit 0, 5 dynamic routes<br>Real browser (Chrome) ✅ 0 hydration errors, 0 pageerrors, 0 dev overlay | **Discovered 2026-09-26 by the first real-browser click-through of this feature** — six defects that lint, tsc, build, 120 API tests, curl and SSR inspection all passed clean. (1) `toLocaleString('es', …)` with no `timeZone` → hydration mismatch, true `13:46` UTC re-rendered as `10:46` local; fixed with `timeZone: 'UTC'` + `hourCycle: 'h23'` (the `es` locale renders midnight as `24:00` on some ICU builds) and a "Disparada (UTC)" header. (2) `setIsLoading(true)` never reset and `useEffect` was not imported → Filtrar latched to "Cargando…" and pagination permanently disabled. (3) `handleFilterChange` passed the stale `filters` closure to `navigate()` → the selected filter never reached the URL, i.e. the exact T1 defect was still there. (4) `new FormData(form)` excludes the submit button, so client-side `intent` was `null` → "Procesando…" was dead code. (5) `mapApiError` returned the raw API `detail` for any non-404/401 status; a 422 detail is a Pydantic *array*, so rendering it threw `throwOnInvalidObjectType` and unmounted the whole table. (6) `filters`/`offset` were initialised once from `initialParams` and never re-derived from the URL, contradicting their own comments. 56 insertions / 20 deletions across 3 files. Fixes 4 and 5 are code-review verified only — both demo alerts are `resolved`, so no action buttons remain to click. |
| T4 | ✅ Done | **7ff278d** → **89e7568 (corrective)** | `corepack.cmd pnpm lint` ✅ 0/0<br>`corepack.cmd pnpm exec tsc --noEmit` ✅<br>`corepack.cmd pnpm build` ✅ 5 routes | 1245 insertions / 101 deletions, then +53/−31 corrective. Edit form pre-filled with current channel config, `updateAlertRule` action, `entity_id` UUID guard added to create AND update, native `<dialog>` delete confirmation with focus management, stacked card layout <768px, severity chip contrast fixed to WCAG AA. **Two blockers found by orchestrator code reading** (dialog `showModal()` crash + 404-by-string-sniffing) — both invisible to all three checks. See the T4 defects section. |
| T5 | ✅ Done | **5bc5d00** → **aa16133 (corrective)** | `corepack.cmd pnpm lint` ✅ 0/0<br>`corepack.cmd pnpm exec tsc --noEmit` ✅<br>`corepack.cmd pnpm build` ✅ 5 routes | All six SMTP variables were **missing** from `api/.env.example` and were added (+10/−1). Both READMEs verified already complete — no change. Production activation recorded as BLOCKED. Corrective `aa16133` (1 line) removed a misleading port comment that implied port 465 implicit TLS works, which this implementation cannot do. |

## Risks
| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Backend API drift (contract change) | Low | High | Pin API types from OpenAPI spec; integration test in T5 |
| Token validation complexity | Medium | Medium | Reuse `config.ts` helpers; each action re-validates |
| Spanish copy inconsistencies | Medium | Low | Single copy constants; review in T4 |
| Accessibility regressions | Medium | Medium | Manual audit checklist in T4; no axe-core CI gate |
| PR slice size creep | High | Medium | Monitor `git diff --stat` per task; stop at boundary |
| No web test framework | High | Low | Document honestly; rely on type-check + build + manual verification |
| **Green build hid a completely dead feature** (T1 filters/pagination) | ~~High~~ **Closed** | High | **Realized 2026-09-25 and fixed in `589aab2`.** T1 shipped a UI wired to an empty stub callback; every check passed. Do not treat lint/tsc/build as evidence that a data path works — a change to UI data flow needs a click-through or a real test |
| **Two more blockers hidden by the same green build** (T4 dialog crash, T4 status sniffing) | ~~High~~ **Closed** | High | **Realized 2026-09-25, fixed in `89e7568`.** `showModal()` on an open modal throws at runtime; 404 detection by `.includes('404')` on a raw backend detail misclassifies 422s. Neither is statically detectable. **Read the code for effect dependencies, native browser APIs, and any error classification** |
| **Six further defects hidden by the same green build, found only by a real browser** (timezone/hydration, latched `isLoading`, dead filter, dead pending label, error-detail crash, stale URL state) | ~~High~~ **Closed** | High | **Realized 2026-09-26.** All three static checks, 120 API tests, `curl` and SSR-only inspection were green. Filtering was entirely non-functional and a failed action unmounted the whole page. This is the **third** occurrence of the same class, which makes it a structural property of this feature rather than bad luck. **Any client-side data path, effect cleanup, or error-value render must be exercised in a browser before it is called verified** |
| Parallel writers can read each other's half-finished edits | Medium | Medium | **Realized 2026-09-25**: an independent verifier ran concurrently with a fix writer and reported a TS error that was a transient mid-edit state. The orchestrator re-verified on the settled tree. Do not run a read-only verifier against files another writer is still editing |
| `corepack.cmd pnpm` / `pnpm.cmd` / bare `pnpm` all fail on this machine | ~~High~~ **Closed** | Low | **Resolved 2026-09-26** — pnpm reinstalled as 9.15.9, matching `lockfileVersion: '9.0'`. See Environment Note 1 for the `.ps1` shim trap that must not be reintroduced |
| `acknowledged_by` was client-supplied → audit spoofing | ~~High~~ **Closed** | High | **Resolved 2026-09-25** by D1 Option A (`fd84c7e`): the API derives the actor from `user.id` and ignores the body |
| Dashboard depends on a hand-copied expiring JWT (no login) | High | High | Pre-existing and NOT fixed here. T2 is now done, so a 401 from an expired token surfaces as an honest Spanish error. Out of scope: separate web-auth feature |

## Open Decision D1 — Actor identity for acknowledgement — **RESOLVED 2026-09-25, Option A**
Question put to the user on 2026-09-25. **Resolved: Option A implemented.**

| Option | Change | Cost | Tradeoff |
|--------|--------|------|----------|
| **A. Harden the API (IMPLEMENTED)** | API uses `user.id` as the source of truth; body field `acknowledged_by` deprecated/ignored, kept for backward compatibility | Backend change + API test | Audit trail stops being falsifiable; 404-not-403 convention preserved |
| B. Web only | Decode `sub` server-side and send it in the body | Frontend only | Fastest, no contract change, but any valid token holder can acknowledge as another user and the log is untrustworthy |
| C. Real web login/session | Add login + session to the dashboard | Separate large feature | The actual root fix; pulls T2 into a much bigger dependency |

**Authoritative design implemented (Option A):**
1. `AlertAckRequest.acknowledged_by` → `UUID | None = None` (optional, deprecated, ignored, backward compat only)
2. `acknowledge_alert` **always** resolves actor from authenticated user (`user.id`); body value never used
3. No 403 mismatch check — preserves existing 404 convention for missing/cross-tenant alerts (`api/tests/test_api_keys.py:185`)
4. Log record reports resolved authoritative actor (`user.id`), not claimed one
5. Docstrings/comments updated unambiguously
6. Tests updated: existing ack tests send random UUID (now regression fixture) and assert stored actor = authenticated user's ID; new tests for empty body and mismatched body both assert 200 with authenticated user winning

## Environment Notes (read before running any command)

**1. `pnpm` was broken on this machine — RESOLVED 2026-09-26.** The corrupt global install (a batch shim invoking a missing `node_modules\pnpm\pnpm`) has been replaced: `pnpm@9` reinstalled globally, now reporting **9.15.9**, matched to the repo's `lockfileVersion: '9.0'`. Two related traps remain and must be respected:

- **Never invoke bare `pnpm` in PowerShell.** The global npm prefix at `C:\Users\Qchara\AppData\Roaming\npm` also generates a `pnpm.ps1` shim, and `PATHEXT` resolves `.PS1` before `.CMD`, so PowerShell picks the script — which is what produced the recurring "Windows wants to run this .ps1" prompt. The eight `.ps1` shims in that directory were deleted; `pnpm`, `npm`, `codegraph` and `opencode` all resolve to their `.cmd` counterparts and work normally. **`npm install -g` regenerates them — delete the new `.ps1` again afterwards.** `C:\Program Files\nodejs\npm.ps1` and `npx.ps1` still exist and need an elevated shell to remove; `npm` demonstrably works through them and never caused a prompt, so they were left alone.
- `corepack.cmd pnpm …` remains a valid fallback.

**1b. Do not start an application server by hand.** The full stack (db + redis + api + worker + web) runs under `docker compose`, with `SPSAAS_DASHBOARD_TOKEN` injected from `docker-compose.override.yml` (gitignored). Starting `node .next/standalone/server.js` by hand yields a token-less server that fights the container for port 3000, and any "missing token" error it produces is self-inflicted. `docker compose logs -f <service>` is the way to read output.

**2. Handoff to WSL.** The repo path becomes `/mnt/c/Users/Qchara/Documents/Proyectos/SPSAAS`. Git state is shared, so the branch and all four commits carry over unchanged. Bare `pnpm` inside WSL resolves to the Linux shim and is fine there, but `pnpm.cmd` is harmless either way.

**3. Engram may not be the same instance under WSL.** WSL has its own `HOME`, so the Engram database and the project key can differ (`/mnt/c/...` vs `C:\...`). **Verify memory before trusting it** — run a project-scoped search for `spsaas` and confirm `odd/alert-web-ui/tasks` is reachable. `odd/tasks/alert-web-ui.md` in the repo is the authoritative fallback and contains the same content.

## Runtime Verification (real stack, 2026-09-25 / 2026-09-26) — T1/T2/T3/T4/T5 PASS

Static checks had already let three real defects through, so this feature was verified against a **running stack** (db + redis + api + worker + web in Docker) with **seeded real data**: user → API key → server `verify-box-01` → rule → metrics. HTTP round trips, not type-checking.

| Task | Verdict | Evidence |
|------|---------|----------|
| T1 alerts list | ✅ PASS | `/alertas` SSR renders the full table (ID, Severidad, Estado, Regla, Servidor, Mensaje, Disparada, Valor, Acciones), the filter bar (Estado, Severidad, ID de regla, Filtrar), pagination ("Mostrando 1 - 1 (límite: 50)") and a real alert row. Full path browser → SSR → API → Postgres confirmed. |
| T2 ack/resolve | ✅ **PASS (browser) 2026-09-26** | Was ❌ BLOCKED on 2026-09-25: `POST /api/v1/alerts/{id}/ack` returned HTTP 500. Backend fixed in `bfa0d4d`; ack/resolve return 200 against real Postgres; and the full lifecycle was then driven **from a real browser** — `Abierta → Reconocida → Resuelta`, correct `aria-live` announcements, both buttons `disabled` + `aria-busy` in flight, Reconocer correctly hidden for non-open alerts. See "T2 browser click-through" below. |
| T3 rules list + create | ✅ PASS | A rule created through the API appears in `/alertas/reglas` SSR. `/alertas/reglas/nueva` populates the server selector with `verify-box-01` and its real id, proving the dashboard-overview → form wiring. |
| T4 edit + delete | ✅ PASS | `/alertas/reglas/{id}/editar` HTTP 200, pre-fills metric, threshold, server_id and the email channel. `PATCH` partial update applies threshold/severity/is_active while preserving nested `channels.webhook.headers`; `DELETE` → 204; invalid enum → 422 with the correct message. |
| T5 SMTP docs | ✅ PASS | Documentation only, verified earlier. |

### Backend defect blocking T2 — PREEXISTING, not from this branch

The **entire alert lifecycle is dead**, independent of the web UI:
- No alert is ever created — the engine detects the breach correctly (`cpu_usage > 80.0 sustained >= 60s`, value 97.4) and then dies on the INSERT.
- `ack` returns HTTP 500.
- `resolve` would fail the same way.

Root cause — **ORM/migration drift**. `api/app/models/alert.py:101-103` declares `triggered_at`, `resolved_at` and `acknowledged_at` as bare `Mapped[datetime]` with **no explicit type**, so SQLAlchemy infers a naive `DateTime()`. The migration created those columns as `timestamp with time zone` (confirmed with `\d alerts`). The model misdescribes the database, and the code then writes aware values:
- `api/app/repositories/alert.py:69` — `acknowledged_at = datetime.now(UTC)` ← the ack path
- `api/app/repositories/alert.py:81` — `resolved_at = datetime.now(UTC)` ← the resolve path
- `api/app/workers/alerts.py:120` / `:151` — `triggered_at` / `resolved_at`

asyncpg rejects it: `DataError: invalid input for query argument $N: ... (can't subtract offset-naive and offset-aware datetimes)`. Traceback: `api/v1/alerts.py:146` → `repositories/alert.py:71` (`session.flush()` inside `acknowledge`).

`TimestampMixin` (`created_at`/`updated_at`) declares timezone-aware columns correctly and does not fail — that asymmetry is the tell.

Confirmed preexisting: `git show main:api/app/repositories/alert.py` already contained `datetime.now(UTC)`. This branch's `fd84c7e` only changed the actor derivation to `user.id`; it did not touch the timestamp.

**Planned fix** (deferred to a separate ODD task in `api/`, by user decision): add `DateTime(timezone=True)` to the three columns, aligning the ORM with a database that is already `timestamptz`. Do **not** strip `tzinfo` at the write sites — that discards UTC and fights the schema.

## T2 Unblocked (2026-09-26) — the defect is fixed

Delivered as its own ODD task: `odd/tasks/alert-timestamp-timezone-drift.md`, commit `91e8633` on `fix/alert-timestamp-timezone-drift` and cherry-picked onto this branch as **`bfa0d4d`**.

| Fact | Value |
|---|---|
| Fix | `DateTime(timezone=True)` on `alerts.triggered_at`, `resolved_at`, `acknowledged_at` and `alert_deliveries.delivered_at`. The fourth column had the identical drift and was included on the user's decision. |
| Migration | **None needed.** The schema was already `timestamptz`; `alembic --autogenerate` now emits zero operations for these columns. |
| Alert creation | Engine now inserts: `triggered_at=2026-09-26 13:25:00.342995+00` |
| ack | **HTTP 200** — `acknowledged_at=2026-09-26T13:25:29.278926Z` |
| resolve | **HTTP 200** — `resolved_at=2026-09-26T13:25:36.192787Z` |
| Delivery | `delivered_at=2026-09-26 13:47:00.445788+00`, `status=sent` |
| Logs | Zero `DataError` / `offset-naive` traces in `api` or `worker` |
| Suite on this branch | 21 alerts tests, 120 full suite — green |

### T1 re-verified with real alert data
`/alertas` now server-renders actual rows, which was impossible on 2026-09-25 because no alert could exist. Filters and pagination verified server-side: `?status=open` returns only the open alert, `?status=resolved` only the resolved one, `?severity=warning` both, `?offset=1&limit=1` one row with `hasNext=true`. Tenant alignment was confirmed explicitly — dashboard token tenant and alert rows tenant are the same.

### T2 browser click-through (2026-09-26) — PASS, and it found six more defects

Driven with `playwright-core` against the **installed Chrome**: no browser download, no dependency added to `web/`, no test framework introduced, and the harness lives outside the repo in the OS temp directory. This respects the "No web test framework" constraint while still getting real-browser evidence.

The ack/resolve path works end-to-end. But exercising it surfaced **six client-interaction defects that lint, `tsc`, `build`, 120 API tests, `curl` and SSR-only inspection had all passed clean** — the same failure class as T1's dead filters and T4's dialog crash, now for the third time.

| # | Location | Defect | Impact |
|---|----------|--------|--------|
| 1 | `AlertsTable.tsx` `formatDate` | `toLocaleString('es', …)` with no `timeZone` | Hydration mismatch, and the displayed trigger time was wrong for every non-UTC viewer: server rendered the true `13:46` UTC, the browser re-rendered `10:46` local |
| 2 | `AlertsTable.tsx` `navigate` | `setIsLoading(true)` never reset; `useEffect` was not even imported | The "Filtrar" label latched to "Cargando…" and Anterior/Siguiente stayed permanently disabled after the first interaction |
| 3 | `AlertsTable.tsx` `handleFilterChange` | `navigate()` read the stale `filters` closure, so the newly selected filter never reached the URL | Filtering was entirely non-functional — the exact defect T1 was supposed to have fixed |
| 4 | `AlertActions.tsx` | `new FormData(form)` **excludes the submit button**, so `intent` was `null` client-side | "Procesando…" was dead code. The server received `intent` (React's own submission path includes it) while the client read `null` and could never pick the pending state |
| 5 | `actions.ts` `mapApiError` | Only 404/401 handled; every other status returned the raw API `detail` | A 422 renders a Pydantic error **array** as a React child → `throwOnInvalidObjectType` → React unmounts the table. One failed action destroyed the entire page |
| 6 | `AlertsTable.tsx` | `filters`/`offset` initialised once from `initialParams`, never re-derived from the URL | Back/forward navigation desynced the controls, contradicting the comments that claimed the state was "derived from the URL" |

**Fixes.** `timeZone: 'UTC'` + `hourCycle: 'h23'` (the latter is required — the `es` locale renders midnight as `24:00` on some ICU builds), and the column header now reads "Disparada (UTC)"; `isLoading` reset when `pathname`/`searchParams` change, plus a no-op navigation guard; `navigate` accepts explicit filter overrides; intent read from `event.nativeEvent.submitter`; `mapApiError` handles 422 and can now only ever return a non-empty string, with a `typeof` guard at the render site as defence in depth; `filters`/`offset` re-derived from `searchParams`.

| Browser check | Observed result |
|---|---|
| Console | 0 hydration errors, 0 pageerrors, 0 dev overlay. The residual 404 is the favicon and a later capture showed no 4xx/5xx and no failed requests |
| Timestamp | Date cell renders `13:46` — the true UTC value — instead of drifting to browser-local `10:46` |
| Filters | `?status=resolved&offset=0&limit=50`; the selection now reaches the URL |
| Pagination | `limit=1` forces `hasNext`: `offset=0 → 1` advances `456dcf2e… → 38ad9632…`; Anterior/Siguiente both work and the Filtrar label stays "Filtrar" throughout |
| Ack / resolve | `Abierta → Reconocida → Resuelta`; `aria-live` announcements correct; both submit buttons `disabled` + `aria-busy` during flight; Reconocer hidden for non-open alerts |
| `pnpm lint` / `pnpm build` | exit 0; 5 dynamic routes |

**Not browser-verified, stated honestly:** fix 4 and fix 5. Both demo alerts were already `resolved`, so no action buttons remained to click, and forcing a 422 would mean deliberately breaking the API. Both are covered by code review plus the captured pre-fix crash evidence. Fix 4's real proof needs a new alert in a mutable state.

## Next Step
**T1, T2, T3, T4 and T5 are all DONE and verified against a running stack, and the whole feature has now been clicked through in a real browser.** The six client-interaction defects found by that click-through are fixed on the working tree and awaiting commit. Nothing is pushed and no PR exists.

What remains is entirely the user's call, in this order:
1. **Verify fix 4 in a live browser** — needs a new alert in `Abierta` or `Reconocida` state so the Reconocer/Resolver buttons can be clicked again. Everything else is done.
2. **Decide the stacked-to-main slices.** Chain strategy is confirmed. Slice #1 (T1, whose history still contains the oversized `ecb92ab` at 845 lines) and slice #3 (T3, 1628 lines) both exceed the ~400-line budget and need an honest split or a recorded `size:exception` before their PRs can open.
3. **Decide how the backend fix reaches `main`.** It is backend bugfix scope and must not stay buried inside this web feature. It exists standalone on `fix/alert-timestamp-timezone-drift` (`91e8633`).
4. **Push / open PRs** — still unauthorized.

Unverified and honest:
- Fix 4 (submitter-derived intent) and fix 5 (422 error mapping) are verified by code review and the captured pre-fix crash evidence, not by a fresh browser reproduction. Both demo alerts are in `resolved` state, so no action buttons remain to click.
- No live 401 or missing-token round trip through the UI.
- No screen-reader announcement of any `aria-live` region or of the delete dialog.
- Focus restore, Escape dismissal, backdrop dismissal and the mobile full-screen dialog are type-correct and reasoned through, still never exercised.
- SMTP delivery: never exercised, and blocked on credentials plus explicit remote authorization.

---

*ODD feature document — `odd/tasks/alert-web-ui.md`*
*Repository: spsaas | Branch: feat/alert-web-ui (local, unpushed) | Created: 2026-09-25 | Updated: 2026-09-26*
*Commits: `ecb92ab` T1 → `b8057e6` T1 correction → `fd84c7e` D1 API hardening → `5c04948` T2 → `72dda44` T2 correction → `9236c16` T3 → `589aab2` T1 filter/pagination fix → `7ff278d` T4 → `89e7568` T4 corrective → `5bc5d00` T5 → `aa16133` T5 corrective → `bfa0d4d` alert timestamp drift fix (cherry-picked from `91e8633`) → click-through fixes pending commit*
*State at handoff: **T1, T2, T3, T4 and T5 verified against a live stack; the full UI has been clicked through in a real browser and the six client-interaction defects that surfaced are fixed.** Suite green on the settled tree: 21 alerts tests, 120 full API suite, web lint 0/0, tsc 0, build 5 routes, 0 hydration/page errors in Chrome. Chain strategy `stacked-to-main` confirmed. Nothing pushed. Next: verify fix 4 against a newly created alert, then decide the PR slices and how `91e8633` reaches `main`.*