# Feature: alert-web-ui — Web UI for Alert Management (list, ack/resolve, rules)

## Objective
Build a tenant-scoped web UI in the existing Next.js 16 dashboard (`web/`) that lets operators view alerts, acknowledge/resolve them, and manage alert rules — all against the already-complete backend `/api/v1/alerts` API.

## Problem
The backend exposes a full alerts API (list, acknowledge, resolve, rules CRUD) but the dashboard only has a single placeholder page. Operators cannot act on alerts from the web.

## Rationale
- Backend `/api/v1/alerts` is complete and tenant-scoped. The only backend change was the actor-identity hardening (D1 Option A), now landed in the `fix(api): derive alert acknowledgement actor from the authenticated user` commit (+109/−13, 3 files).
- Dashboard uses Next.js 16 App Router with Server Components and Server Actions — fits the architecture.
- `SPSAAS_DASHBOARD_TOKEN` must remain server-only; each Server Action independently validates it before calling the backend.
- **The acting user for an acknowledgement comes from the authenticated user's id, resolved server-side by the API.** The web never decodes the JWT and never sends an actor.
- Work-unit commits map to chained PR slices (`stacked-to-main`); forecast >400 lines triggers slice planning.

## Verified Auth Facts (2026-09-25, code inspection)
These replace any assumption derived from the env var name:
- **There is no dashboard/service token in the API.** `grep dashboard_token api/` → zero matches. `/api/v1/dashboard/overview` and every `/api/v1/alerts` endpoint require `user: CurrentUser` — a real user access JWT via `Authorization: Bearer <access_token>` (`api/app/core/auth/dependencies.py:45-81`).
- Therefore `SPSAAS_DASHBOARD_TOKEN` is a **misnomer**: it must hold a live, non-expired user access token or every dashboard call returns 401.
- `acknowledge_alert` (`api/app/api/v1/alerts.py:133-160`) **used to** take `acknowledged_by` from the request body, trusting the client about who acted. **This was the defect fixed in the D1 Option A actor-identity hardening commit** (`fix(api): derive alert acknowledgement actor from the authenticated user`, +109/−13, 3 files): the actor is now always `user.id`. Kept here as the audit trail of what changed.
- `resolve_alert` takes no body. Both return `AlertAckResponse { id, status, acknowledged_at, resolved_at, acknowledged_by }`.
- Consequence: the dashboard has no login; a hand-copied expiring JWT is the entire auth story. T2 mutations make expiry immediately user-visible.

## Authorized Scope
- **T1**: Server-only typed alert/rule data access; root navigation; `/alertas` read-only list with GET filters and bounded offset pagination; config/error state consistent with current dashboard.
- **T2**: Acknowledge/resolve Server Actions; the acting user is resolved by the API from the authenticated principal (D1 Option A) — the web sends no actor; accessible pending/success/error feedback; refresh/revalidate after mutation.
- **T3**: `/alertas/reglas` list + create form; server selector from dashboard overview; actual schema/channel validation; no raw UUID entry when overview provides servers (entity_id may remain optional/all servers).
- **T4**: Edit active/channel fields + delete confirmation + responsive/accessibility polish.
- **T5**: Verify/update existing SMTP env documentation (`api/.env.example`, root README only if actually incomplete), record unresolved production activation inputs, run full web checks, finalize evidence.

## Out of Scope
- Backend API changes — **only** the D1 Option A actor-identity hardening, which is already implemented and committed (the `fix(api): derive alert acknowledgement actor from the authenticated user` commit, +109/−13, 3 files).
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
| Backend API | `/api/v1/alerts` — tenant-scoped and complete; the only change was the D1 actor-identity hardening in the `fix(api): derive alert acknowledgement actor from the authenticated user` commit (+109/−13, 3 files) |
| SMTP variables | `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_STARTTLS` only |
| Testing | TDD OFF — no strict config, no SDD init. Ordinary checks from `web/`: `pnpm lint`, `pnpm exec tsc --noEmit`, `pnpm build`. API tests only if backend changes. |
| RDD | Clone-local OFF; do not start review or change it. |
| Commits | Local commits authorized as ODD work units; push/PR not authorized *at time of writing*. **Subsequently authorized and merged as PRs #17–#26.** |
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
- [x] `web/src/app/alertas/actions.ts`: **single** Server Action `alertAction` (the two near-duplicate exports were collapsed) — server-side validates `alertId` (UUID shape) and `intent` (`ack` | `resolve`) before any fetch, reads the token via `getDashboardToken()`. **Sends NO `acknowledged_by` and does NOT decode the JWT** — the API owns identity since the D1 Option A actor-identity hardening commit (`fix(api): derive alert acknowledgement actor from the authenticated user`, +109/−13, 3 files). Calls `revalidatePath('/alertas')` on success. Returns a typed `{ status, message }`, never throws to the client.
- [x] HTTP status is a **typed value** (`FetchResult<T>.status: number | null`), never parsed out of an error string — `mapApiError` branches on 404 / 401 / 422 / other, and can only ever return a non-empty string. **Corrected 2026-09-26:** any other status used to return the raw API `detail`, which for a 422 is a Pydantic error *array* — rendering it as a React child threw `throwOnInvalidObjectType` and unmounted the whole table. Error prose stays neutral Spanish; raw backend English details never leak into the UI.
- [x] `web/src/app/alertas/components/AlertActions.tsx`: Client Component — one `<form>` per row, two submit buttons via `name="intent"`; both disabled during submission (no double-submit, no optimistic UI); "Procesando…" only on the submitted button (`pendingIntent` local state); `aria-live="polite"` region **always rendered**; `min-h-[44px] min-w-[44px]`; visible focus. "Reconocer" only when `open`, "Resolver" only when not `resolved`.
- [x] Revalidation: `revalidatePath('/alertas')` after success.
- [x] Evidence: the T2 feature commit (`feat(web): add alert acknowledge and resolve actions`, +259/−4, 4 files) → its corrective commit (`fix(web): map alert action errors by HTTP status`, +68/−75, 3 files, −7 net lines). `pnpm lint` ✅ `pnpm exec tsc --noEmit` ✅ `pnpm build` ✅ from `web/` (orchestrator re-ran `pnpm build`, exit 0).

### T3 — Rules List + Create Flow with Server Selector from Overview — ✅ DONE
- [x] `web/src/lib/api/rules.ts`: NEW — typed server-only wrappers for the rule endpoints, reusing `config.ts` helpers and the `FetchResult<T>` typed-status pattern.
- [x] `web/src/lib/api/dashboard.ts`: NEW — reads the server list from `GET /api/v1/dashboard/overview` (`/api/v1/servers` does not exist).
- [x] `web/src/app/alertas/reglas/page.tsx`: Server Component — rules (bounded offset pagination) + servers from overview; renders entity_type, entity_id, metric, operator, threshold, duration_s, severity, channels, is_active, actions. `export const dynamic = 'force-dynamic'`.
- [x] `web/src/app/alertas/reglas/components/RulesTable.tsx`: Client Component — enable/disable toggle via Server Action, delete with native `confirm()`, no sortable columns, no optimistic UI, no polling, `aria-live` feedback, 44px targets.
- [x] `web/src/app/alertas/reglas/nueva/page.tsx`: Server Component — fetches servers for the selector, honest empty-state.
- [x] `web/src/app/alertas/reglas/nueva/components/CreateRuleForm.tsx`: Client Component — controlled form mirroring the backend schema, server selector from overview, `email.to[]` required when email chosen, optional webhook `url` + headers, ≥1 channel enforced client AND server, no invented `name` field, `entity_id` optional.
- [x] `web/src/app/alertas/reglas/actions.ts`: Server Actions `createAlertRule`, `toggleRuleEnabled`, `deleteAlertRule` — each validates the token independently before any fetch; input validated before fetch; errors mapped by typed HTTP status into neutral Spanish.
- [x] Nav: "Reglas" entry added to `web/src/app/layout.tsx` alongside "Alertas".
- [x] **Evidence**: the T3 feature commit (`feat(web): add alert rules list and create flow`, +1628/−5, 11 files). `corepack.cmd pnpm lint` ✅ 0 errors 0 warnings · `corepack.cmd pnpm exec tsc --noEmit` ✅ · `corepack.cmd pnpm build` ✅ 4 dynamic routes — **all three re-run by the orchestrator on the settled tree**, exit 0.
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
- [x] **Evidence**: the T4 feature commit (`feat(web): add alert rule editing and accessible delete confirmation`, +1245/−101, 4 files) + its corrective commit (`fix(web): guard dialog open call and use typed status in rule edit page`, +53/−31, 4 files). `corepack.cmd pnpm lint` ✅ 0 errors 0 warnings · `corepack.cmd pnpm exec tsc --noEmit` ✅ · `corepack.cmd pnpm build` ✅ 5 dynamic routes — **all three re-run by the orchestrator on the settled tree after the corrective**, exit 0.

#### T4 defects found by orchestrator code reading and fixed in the T4 corrective commit (`fix(web): guard dialog open call and use typed status in rule edit page`, +53/−31, 4 files)
Both were invisible to lint, type-check and build — the same failure class as the T1 dead feature. Found by reading the code, not by trusting the writer's report.

1. **BLOCKER — the delete confirmation dialog could crash on use.** `ConfirmDialog`'s effect depended on `[isOpen, onClose, triggerElement]` and unconditionally called `dialog.showModal()`. `closeDeleteDialog` was a plain function with no `useCallback`, so it got a new identity on every render of `RulesTable`; every re-render while the dialog was open therefore re-ran the effect and called `showModal()` on an already-modal dialog, which throws `InvalidStateError` per the HTML spec. Concrete trigger: `handleDeleteConfirm` calls `setIsLoading(true)` → re-render → effect re-runs → throw. React StrictMode's dev double-invoke hits the same path. **Fixed** with `if (!dialog.open) dialog.showModal()` (and the symmetric guard on `close()`), plus `useCallback` on the handlers, plus deterministic focus via `useLayoutEffect` replacing a `setTimeout(..., 0)` hack. The misleading doc comment claiming "inert via aria-modal" was corrected: `aria-modal` makes nothing inert — native `<dialog>` + `showModal()` (top layer) is the real mechanism.
2. **BLOCKER — the edit page detected 404 by sniffing the error string** with `ruleError.includes('404')`, the exact anti-pattern the T2 corrective commit (`fix(web): map alert action errors by HTTP status`, +68/−75, 3 files) removed from T2, while the typed `status` sat unused. `error` is populated as `err.detail ?? \`HTTP ${status}\`` (`web/src/lib/api/rules.ts:104-111`) — the **raw backend detail**, which for a FastAPI 422 can contain arbitrary submitted values. So a 422 whose detail happened to contain the substring "404" falsely rendered `notFound()`, and a genuine 404 without that substring rendered the wrong state. **Fixed** by destructuring `status` and branching on `status === 404`. The two raw-detail leaks (`No se pudo cargar la regla: {ruleError}` and the overview equivalent) were also closed by extracting the shared Spanish mapping into `web/src/app/alertas/reglas/utils.ts` (`mapApiError`), now used by both the page and the Server Actions.
   - Note: one string check intentionally remains — `ruleStatus === null && ruleError.includes('Token de dashboard no configurado')`. That sentinel is produced by **our own** code (`rules.ts:89`), not by the backend, and the missing-token case has no HTTP status by design. It is not status sniffing.

### T5 — SMTP Docs Verification + Full Web Checks + Evidence — ✅ DONE
- [x] `api/.env.example`: **all six SMTP variables were missing** and were added with placeholder values and inline comments: `SMTP_HOST=`, `SMTP_PORT=587`, `SMTP_USER=`, `SMTP_PASSWORD=`, `SMTP_FROM=`, `SMTP_STARTTLS=true`. No secrets invented, no `web/.env.example` created.
- [x] Root `README.md`: already complete (six variables, correct defaults, "empty = disabled" semantics, login-only-if-user-provided). **No change needed** — verified, not rewritten.
- [x] `api/app/workers/delivery/README.md`: already complete (lists all six from `core/config.py`, notes email is disabled → `config_missing` unless `smtp_enabled`). **No change needed.**
- [x] Production activation status: **BLOCKED**, recorded. Requires a destination address, real SMTP provider credentials, and explicit remote-operation authorization. No SMTP host was contacted, no account configured, nothing attempted outside the repository.
- [x] Full verification from `web/`: `corepack.cmd pnpm lint` ✅ **0 errors 0 warnings** · `corepack.cmd pnpm exec tsc --noEmit` ✅ · `corepack.cmd pnpm build` ✅ 5 dynamic routes — **re-run by the orchestrator on the final settled tree**, exit 0.
- [x] **Evidence**: the T5 feature commit (`docs: document SMTP configuration for alert email delivery`, +10/−1, 1 file) + its corrective commit (`docs: correct SMTP port comment to reflect STARTTLS-only support`, +1/−1, 1 file).

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

#### Defect found by orchestrator and fixed in the T5 corrective commit (`docs: correct SMTP port comment to reflect STARTTLS-only support`, +1/−1, 1 file)
The first pass documented `SMTP_PORT` as *"default 587; 465 for implicit TLS"*. **That was wrong.** `api/app/workers/delivery/email.py:153` uses a plain `smtplib.SMTP(...)` connection upgraded with `smtp.starttls()` (line 155); there is **no `SMTP_SSL` anywhere in `api/app`**. A plain socket cannot negotiate implicit TLS, so port 465 cannot work — the comment would have led an operator straight to a configuration this implementation cannot deliver. Corrected to state that 587 is the STARTTLS submission port and that implicit TLS on 465 is not supported.

## Acceptance Criteria
| ID | Criterion | Verification |
|----|-----------|--------------|
| AC1 | Alerts list loads with bounded pagination, filters (status, severity, rule_id) work, severity/status badges render correctly | ✅ **Real browser, 2026-09-26** — filters reach the URL, `limit=1` forces `hasNext` and both controls advance, 0 hydration errors |
| AC2 | Acknowledge action: button shows pending, on success `aria-live` feedback appears, row updates to `acknowledged`. Actor comes from the authenticated user server-side — the web sends no `acknowledged_by` (D1 Option A) | ✅ **Real browser, 2026-09-26, against a freshly created alert** — `Abierta → Reconocida`, both buttons `disabled` + `aria-busy` in flight, `aria-live` announced, HTTP 200. The **per-button pending label is now directly observed**: only the clicked submitter shows "Procesando…", the sibling is disabled but keeps its own text. Reproduced on both fresh alerts (`6fcc0fb4`, `41b29f74`) |
| AC3 | Resolve action: same flow, row updates to `resolved` | ✅ **Real browser** — `Reconocida → Resuelta`, HTTP 200, `aria-live` announced |
| AC4 | Rules list loads, enable/disable toggles work, delete shows confirmation | ✅ **Real browser, 2026-09-27** — toggle flipped both ways and returned to its original state with the `aria-live` region announcing each change; delete confirmation opened, dismissed by Escape and by backdrop, and the dialog row action was mutated by the round trip. The confirmation dialog itself found and fixed five real defects (see "Accessibility round #2") |
| AC5 | Create rule: form validates, server selector populated from dashboard overview, email/webhook channel config saved, requires ≥1 channel | Manual + backend check |
| AC6 | Edit rule: pre-fills data, updates active/channel fields correctly | Manual (HTTP 200 + `PATCH`/`DELETE` round trips) |
| AC7 | Spanish UI: all copy neutral/professional Spanish, no console errors | ✅ **Real browser** — 0 pageerrors, 0 hydration errors, 0 dev overlay |
| AC8 | Accessibility: semantic HTML, labels, keyboard nav, visible focus, 44px targets, `aria-live` feedback, responsive scroll/cards, contrast-safe classes | ✅ **Real browser keyboard measurement, 2026-09-27** — Tab ×10 and Shift+Tab ×6 cycle `Cancelar ⇄ Eliminar` and never escape to `<body>` (`defaultPrevented` on 16/16 events); initial focus lands on `[data-confirm]`; focus is restored to the row trigger after both dismissal paths; a single persistent `role="status"` region announces each toggle. **No screen reader was run**, so spoken output is unverified. |
| AC9 | Responsive: <768px tables→scroll/cards, forms stack, touch targets ≥44px | ✅ **Real browser, 2026-09-27** — dialog container and content measure `390×844` at a 390px viewport with `border-radius:0px`, and the keyboard trap and focus restore both hold on mobile. Desktop centering measured at `x:440, y:264` in a `1280×720` viewport after the Tailwind preflight fix. |
| AC10 | SMTP docs verified in existing locations (`api/.env.example`, delivery README, root README if incomplete); production activation blocked recorded | File review |
| AC11 | All checks pass: `pnpm lint`, `pnpm exec tsc --noEmit`, `pnpm build` from `web/` | ✅ `corepack.cmd pnpm lint` 0 errors / 0 warnings, `corepack.cmd pnpm exec tsc --noEmit` clean, `corepack.cmd pnpm build` exit 0 from a **deleted `web/.next`**. These three remain a floor, never evidence of behaviour — see the standing rule below |

## Exact Checks
Run from `web/` directory. **`pnpm.cmd`, not bare `pnpm`** (see Environment Note 1 — bare `pnpm` in PowerShell can resolve a `.PS1` shim and trigger the "Windows wants to run this script" prompt; `corepack.cmd pnpm` is a valid fallback):
```bash
pnpm.cmd lint                # ESLint — must report ZERO errors AND ZERO warnings
pnpm.cmd exec tsc --noEmit   # TypeScript type-check (zero errors)
pnpm.cmd build               # Next.js production build (success)
```
No test command required (TDD OFF). No web test framework exists. API tests only if backend changes (out of scope).

**These three are not sufficient on their own.** A green build proved nothing about T1: the filters and pagination were dead at runtime and every check still passed. Any UI wiring whose data path is not exercised against a live backend is **unverified** until clicked through.

**Delete `web/.next` first.** A build against a warm `.next` reuses cached generated types and can report success on code that does not compile — which is exactly how three commits carried a false `pnpm build` ✅ for a week. Always:
```powershell
Remove-Item -Recurse -Force web/.next
```

This has now happened three times in this feature — T1's dead filters, T4's dialog crash, and six client-interaction defects in the 2026-09-26 click-through — with a fully green `lint` / `tsc` / `build` / test suite every time. Treat static checks as a floor, never as evidence of behaviour.

**The same directory breaks the browser too, and that is the worse half.** `web` bind-mounts `./web:/app`, so a `pnpm build` leaves a production `.next` inside the directory the dev server reads. The dev server then serves the *built* bundle while the source on disk is something else — and a browser measures code that is not the code being edited. This surfaced on 2026-09-27 as three measurements of "the same" handler returning three different focus sequences, and it is the leading suspect for every confusing result in that round. Before recording any browser evidence here:

```powershell
Remove-Item -Recurse -Force web/.next
docker compose restart web
```

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
| **#1a** | T1 data layer | **109** | ✅ | `main` | `lib/api/alerts.ts` — typed server-only fetch wrappers. Deliberately inert: nothing imports it yet |
| **#1b** | T1 read-only UI | **444** | ⚠️ 1.11× | `#1a` | `alertas/page.tsx` + `AlertsTable.tsx` — the page and its table |
| **#1c** | T1 app shell | **42** | ✅ | `#1b` | `layout.tsx` — header, nav, main, footer. Lands **last** so the `/alertas` route exists before anything links to it |
| **#1b-alt** | *(not a slice)* D1 API hardening | **122** | ✅ | `#1` | Security fix in the same branch. Recommend cutting it as its own PR — it is an API audit-integrity change, not web scope |
| **#2** | T2 | **266** | ✅ | `#1` | Actions: ack/resolve Server Actions + accessible feedback |
| **#3** | T3 | **1.633** | ❌ **4× over** | `#2` | Rules: `lib/api/rules.ts` + `dashboard.ts`, Server Actions, `page.tsx` + `RulesTable.tsx`, `nueva/*`. Documented split already exists in the T3 checklist |
| **#4** | T1 fix + T4 + T5 | **1.494** | ❌ **3.7× over** | `#3` | ⚠️ **Was mis-estimated as ~250–400.** Really the T1 filter/pagination fix commit (`fix(web): make alert filters and pagination drive URL navigation`, +47/−54, 2 files) + T4 edit form + delete dialog + a11y/responsive + SMTP docs. Three unrelated concerns in one slice |
| **#5** | timestamp fix | **298** | ✅ | `#4` | ⚠️ **Does not belong in this chain at all** — it is a P0 backend fix and must reach `main` independently and first. Landed separately as PR #16 (merge `b1a2197`, commit `91e8633`) |
| **#6** | click-through fix | **469** (56 code + 393 doc) | ⚠️ boundary | `#5` | Code is well under budget; the count is inflated by this tracking document. Recommend the doc lands with slice #1 or on its own |

**Total against `main`: 4.465 authored lines across 7 slices.** Three slices are materially over budget: #1 (1.5×), #3 (4×) and #4 (3.7×).

**Historical note (2026-09-26):** At the time of writing, the branch had never been pushed — `feat/alert-web-ui` had no upstream, and the only remote branch was `origin/main`. The chain was subsequently delivered via `stacked-to-main` as 10 PRs (#17–#26), all merged to `main` (`e1bc567`). All merged chain branches were deleted. Local branches remaining: `main` and `agents/gentle-ai-integration`. Remote has only `main`.

## T1 evidence correction (2026-09-26) — three "build ✅" claims were FALSE

While splitting slice #1 into reviewable commits, each intermediate commit was built from a cleared `.next`. The original T1 tip commit (the superseded `refactor(web): keep alerts overview within read-only scope` commit) — whose evidence row claims `pnpm build` ✅ — **does not compile**:

```
src/app/alertas/page.tsx(114,11): error TS2322: Type 'AlertListParams' is not
assignable to type '{ status?: ...; offset: number; limit: number; }'
```

**Root cause.** `AlertListParams` declares `offset?` / `limit?` as optional, because `listAlerts` defaults them. `AlertsTableProps` requires them, because the page always resolves them through `parseOffset` / `parseLimit`. The runtime was never wrong — only the type declaration was. Passing `initialParams` straight through was a type error from T1 onward.

**Why nobody noticed.** The builds had been run against a **stale `web/.next`**, so `tsc` reused cached generated types and reported success. Clearing `.next` surfaces the real error immediately.

**Why the branch tip is green anyway.** The T3 feature commit (`feat(web): add alert rules list and create flow`, +1628/−5, 11 files) incidentally *removed* the `: AlertListParams` annotation from `const initialParams`, letting TypeScript infer a concrete object type with required `offset`/`limit`. That repaired the mismatch by accident, three commits later, with no one intending it.

| Commit | Annotation | Builds clean? | Evidence row claimed |
|---|---|---|---|
| Original T1 tip (superseded `refactor(web): keep alerts overview within read-only scope`) | `const initialParams: AlertListParams =` | ❌ | ✅ build |
| T2 feature commit (superseded `feat(web): add alert acknowledge and resolve actions`) | `const initialParams: AlertListParams =` | ❌ | ✅ build |
| T2 corrective commit (superseded, `fix(web): map alert action errors by HTTP status`) | `const initialParams: AlertListParams =` | ❌ | ✅ build |
| T3 feature commit (`feat(web): add alert rules list and create flow`, +1628/−5, 11 files) | `const initialParams =` | ✅ | ✅ build |

**Resolution.** Slice #1b passes `offset` and `limit` explicitly at the call site — `initialParams={{ ...initialParams, offset, limit }}` — which is also the honest statement of intent. The fix exists **only inside slice #1**, because that is where it is required for the slice to open with a green head. The T1 filter/pagination fix commit (`fix(web): make alert filters and pagination drive URL navigation`, +47/−54, 2 files) later rewrites that call site, so the final branch tree is byte-identical to the pre-split branch. The backup branches (`backup/feat-alert-web-ui`, `backup/pre-slice1-split`) were deleted after the PRs merged; the split is purely structural.

**Standing rule, added to Exact Checks: delete `web/.next` before believing any build result on this project.**

## Slice #1 split (2026-09-26) — done, verified green per commit

| Commit | Lines | Builds | Lint |
|---|---|---|---|
| `feat(web): add typed server-only client for the alerts API` (+109/−0, 1 file) | 109 | ✅ | ✅ 0/0 |
| `feat(web): add read-only alerts overview page and table` (+444/−0, 2 files) | 444 | ✅ | ✅ 0/0 |
| `feat(web): add app shell with header, navigation and footer` (+41/−1, 1 file) | 42 | ✅ | ✅ 0/0 |

`444` is 1.11× the soft ~400 heuristic on #1b. It was not reduced further on purpose: the only smaller seam would separate the page from the table it renders, producing an intermediate commit whose import does not resolve. A broken intermediate is strictly worse than a slightly oversized commit, and the heuristic is explicitly not an acceptance criterion.

**Rebase outcome.** 14 downstream commits replayed onto the new base. One conflict, in `alertas/page.tsx`, on exactly the line the fix touches. Resolved toward the T1 filter/pagination fix commit's side — that commit legitimately deletes the dead `onFetch` prop and rewrites the call site, and the type error is already gone by then via the T3 feature commit (`feat(web): add alert rules list and create flow`, +1628/−5, 11 files). Final tree verified byte-identical to the pre-split backup. Branch tip: lint 0/0, build exit 0, 23 files, 4.473 insertions.

The safety refs (`backup/pre-slice1-split` tag, `backup/feat-alert-web-ui` branch) were deleted after the PRs merged.

## Progress / Evidence Placeholders

| Task | Status | Commit SHA | Checks | Notes |
|------|--------|------------|--------|-------|
| T1 | ⚠️ **Done, build claim corrected** | **Slice #1: three commits** — `feat(web): add typed server-only client for the alerts API` (+109/−0, 1 file) → `feat(web): add read-only alerts overview page and table` (+444/−0, 2 files) → `feat(web): add app shell with header, navigation and footer` (+41/−1, 1 file) (split from the superseded `refactor(web): keep alerts overview within read-only scope` commit) | `pnpm lint` ✅ `pnpm exec tsc --noEmit` ✅ `pnpm build` ✅ — **re-verified 2026-09-26 per commit with `web/.next` deleted** | 594 authored lines (594 add, 1 del), 4 files. Original superseded `feat(web): add secure alerts overview` (845 lines, 5 files) contained T2/T3 scope removed by this correction: deleted `rules.ts`, removed `acknowledgeAlert`/`resolveAlert` and their types from `alerts.ts`, removed nonfunctional action buttons from `AlertsTable.tsx`, added `force-dynamic`, changed date locale to neutral `es`, replaced breadcrumb `<a>` with `Link`. Independent verifier: `pass-with-warnings`, no blockers/criticals after correction. Native assess on the correction: `medium`, `review_due: false`, `under_budget`. Parent spot check `pnpm lint` re-run by orchestrator: exit 0. **⚠️ The original `pnpm build` ✅ in this row was FALSE — the superseded T1 tip commit does not compile. See "T1 evidence correction". Slice #1 is now three commits, each independently green.** |
| **D1 Resolution (Option A)** | ✅ Done | **the D1 Option A actor-identity hardening commit** (`fix(api): derive alert acknowledgement actor from the authenticated user`, +109/−13, 3 files) | `python -m pytest tests/test_alerts.py` ✅ 20/20 passed<br>`python -m pytest tests/` ✅ 119 passed<br>`ruff check app tests` ✅<br>`mypy app` ✅ | API hardening: `acknowledged_by` from `user.id`, body field deprecated/ignored, 404 preserved, log reports authoritative actor, 2 new regression tests + updated existing tests |
| T2 | ✅ Done | **T2 feature commit** (`feat(web): add alert acknowledge and resolve actions`, +259/−4, 4 files) → **T2 corrective commit** (`fix(web): map alert action errors by HTTP status`, +68/−75, 3 files, −7 net lines) | `pnpm lint` ✅ `pnpm exec tsc --noEmit` ✅ `pnpm build` ✅ | 259 authored lines (259 add, 4 del), 4 files. Added `AlertAckResponse` type, `acknowledgeAlert`/`resolveAlert` in `alerts.ts`; Server Actions `acknowledgeAlertAction`/`resolveAlertAction` in `actions.ts` (each validates token independently, UUID validation, intent validation, honest error mapping 404/401/other); `AlertActions` Client Component with single form per row, two submit buttons via `name="intent"`, `useFormStatus` for pending/disable, `aria-live` feedback, `min-h-[44px] min-w-[44px]` touch targets; `AlertsTable` adds actions column. Neutral/professional Spanish copy: "Reconocer", "Resolver", "Procesando…". **Corrective commit** (`fix(web): map alert action errors by HTTP status`, +68/−75, 3 files, −7 net lines): (1) `FetchResult<T>` with typed `status: number | null` returned by `fetchWithAuth`/`acknowledgeAlert`/`resolveAlert` — eliminates regex parsing of error messages; `mapApiError` now branches on numeric status directly. (2) `actions.ts` uses `getDashboardToken()` helper (was direct `process.env` read). (3) Collapsed `acknowledgeAlertAction` + `resolveAlertAction` into single `alertAction` — server-side validates both `alertId` (UUID) and `intent` (`ack`|`resolve`); removed client-side intent dispatcher. (4) `AlertActions.tsx`: `aria-live` region always rendered (was conditional); per-button pending label via local `pendingIntent` state (was both buttons showing "Procesando…"). T1 behavior (filters, pagination, error/empty states) unchanged. |
| T3 | ✅ Done | **T3 feature commit** (`feat(web): add alert rules list and create flow`, +1628/−5, 11 files) | `corepack.cmd pnpm lint` ✅ 0/0<br>`corepack.cmd pnpm exec tsc --noEmit` ✅<br>`corepack.cmd pnpm build` ✅ | 1628 authored insertions, 11 files. Rules list + create flow with server selector from dashboard overview. Independent verifier **confirmed all 11 backend contract claims** against the API source. Native assess: `medium`, `review_due: true`, `slice_budget_reached` (1633 lines vs the ~400 budget). Four findings carried into T4 (see T3 findings table). |
| **T1 defect fix** | ✅ Done | **T1 filter/pagination fix commit** (`fix(web): make alert filters and pagination drive URL navigation`, +47/−54, 2 files) | `corepack.cmd pnpm lint` ✅ **0 errors, 0 warnings**<br>`corepack.cmd pnpm exec tsc --noEmit` ✅<br>`corepack.cmd pnpm build` ✅ | **Discovered during T3 verification**: T1's filters and pagination were non-functional at runtime. `AlertsTable.fetchAlerts` called the `onFetch` prop, which was an EMPTY stub in `alertas/page.tsx` whose comment said *"In a full implementation with T2, we'd use Server Actions"*. `setAlerts`/`setHasNext` were therefore never called and the table always rendered `initialAlerts` — AC1 was not actually met, hidden behind a green build. Fix: URL-driven navigation via `useRouter`/`usePathname`; the dead `onFetch` prop, the empty stub, the unused `newParams` param and the unused `AlertResponse` import are gone. 46 insertions / 53 deletions. |
| **T1+T2 click-through fix** | ✅ Done | **click-through fix commit** (`fix(web): correct client-reaction defects found in browser click-through`, +56/−20, 3 files) | `npm.cmd run lint` ✅ exit 0<br>`npm.cmd run build` ✅ exit 0, 5 dynamic routes<br>Real browser (Chrome) ✅ 0 hydration errors, 0 pageerrors, 0 dev overlay<br>**Fix 4 re-verified in browser 2026-09-26** | **Discovered 2026-09-26 by the first real-browser click-through of this feature** — six defects that lint, tsc, build, 120 API tests, curl and SSR inspection all passed clean. (1) `toLocaleString('es', …)` with no `timeZone` → hydration mismatch, true `13:46` UTC re-rendered as `10:46` local; fixed with `timeZone: 'UTC'` + `hourCycle: 'h23'` (the `es` locale renders midnight as `24:00` on some ICU builds) and a "Disparada (UTC)" header. (2) `setIsLoading(true)` never reset and `useEffect` was not imported → Filtrar latched to "Cargando…" and pagination permanently disabled. (3) `handleFilterChange` passed the stale `filters` closure to `navigate()` → the selected filter never reached the URL, i.e. the exact T1 defect was still there. (4) `new FormData(form)` excludes the submit button, so client-side `intent` was `null` → "Procesando…" was dead code. (5) `mapApiError` returned the raw API `detail` for any non-404/401 status; a 422 detail is a Pydantic *array*, so rendering it threw `throwOnInvalidObjectType` and unmounted the whole table. (6) `filters`/`offset` were initialised once from `initialParams` and never re-derived from the URL, contradicting their own comments. 56 insertions / 20 deletions across 3 files. **Corrected 2026-09-26:** fix 4 is now browser-verified against two freshly created alerts (`6fcc0fb4`, `41b29f74`) — only the clicked submitter shows "Procesando…" while the sibling is disabled but keeps its own text. Fix 5 remains code-review verified only, because forcing a 422 would mean deliberately breaking the API. |
| T4 | ✅ Done | **T4 feature commit** (`feat(web): add alert rule editing and accessible delete confirmation`, +1245/−101, 4 files) → **T4 corrective commit** (`fix(web): guard dialog open call and use typed status in rule edit page`, +53/−31, 4 files) | `corepack.cmd pnpm lint` ✅ 0/0<br>`corepack.cmd pnpm exec tsc --noEmit` ✅<br>`corepack.cmd pnpm build` ✅ 5 routes | 1245 insertions / 101 deletions, then +53/−31 corrective. Edit form pre-filled with current channel config, `updateAlertRule` action, `entity_id` UUID guard added to create AND update, native `<dialog>` delete confirmation with focus management, stacked card layout <768px, severity chip contrast fixed to WCAG AA. **Two blockers found by orchestrator code reading** (dialog `showModal()` crash + 404-by-string-sniffing) — both invisible to all three checks. See the T4 defects section. |
| T5 | ✅ Done | **T5 feature commit** (`docs: document SMTP configuration for alert email delivery`, +10/−1, 1 file) → **T5 corrective commit** (`docs: correct SMTP port comment to reflect STARTTLS-only support`, +1/−1, 1 file) | `corepack.cmd pnpm lint` ✅ 0/0<br>`corepack.cmd pnpm exec tsc --noEmit` ✅<br>`corepack.cmd pnpm build` ✅ 5 routes | All six SMTP variables were **missing** from `api/.env.example` and were added (+10/−1). Both READMEs verified already complete — no change. Production activation recorded as BLOCKED. T5 corrective commit (1 line) removed a misleading port comment that implied port 465 implicit TLS works, which this implementation cannot do. |
| **T4 a11y round #2** | ✅ Done | **delete-dialog accessibility commit** (`fix(web): restore dialog focus, trap Tab, and centre the confirmation`, +80/−20, 1 file) + `web/src/app/favicon.ico` (new) | `corepack.cmd pnpm lint` ✅ 0/0<br>`corepack.cmd pnpm exec tsc --noEmit` ✅<br>`corepack.cmd pnpm build` ✅ (clean, `web/.next` deleted first)<br>Real browser (Chrome) ✅ 0 pageerrors, 0 failed requests | **Fourth** occurrence of "green static checks, broken behaviour", and the first time the delete dialog was ever exercised. **Five real defects found and fixed:** focus restore dead (the unmount nulled the ref), initial confirm focus never applied (`useLayoutEffect` ran before the ref attached), Tab escaping to `<body>`, the desktop dialog pinned at `x:0, y:0` (Tailwind v4 preflight `margin:0` beat the native `dialog:modal { margin: auto }`), and a duplicated nested live region. Also closed the token round-trip gap (a real 401 and a missing-token run, both correct), identified the residual 404 as the favicon and moved the user's `favicon.ico` to the App Router convention, and established that the 422 branch is unreachable through a normal browser. **A sixth finding, about the tooling itself:** `web/.next` left by a production build shadows the dev server inside the bind mount, so a browser can measure code that is not on disk. That cost hours and is now a standing rule. Full evidence in "Accessibility round #2 (2026-09-27)". |

## Risks
| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| **A production `web/.next` makes the dev server serve code that is not on disk** | ~~High~~ **Closed** | High | **Realized 2026-09-27.** `web` bind-mounts `./web:/app`, so `pnpm build` writes a production `.next` into the directory the dev server reads. The dev server then serves the built bundle while the source is something else, and a browser measures the wrong handler. This cost hours: three measurements of "the same" code returned three different focus sequences. **Standing rule: delete `web/.next` and restart `web` in the same session before recording any browser evidence on this project.** This is a second, browser-facing dimension of the stale-`.next` risk below. |
| Backend API drift (contract change) | Low | High | Pin API types from OpenAPI spec; integration test in T5 |
| Token validation complexity | Medium | Medium | Reuse `config.ts` helpers; each action re-validates |
| Spanish copy inconsistencies | Medium | Low | Single copy constants; review in T4 |
| Accessibility regressions | Medium | Medium | Manual audit checklist in T4; no axe-core CI gate |
| PR slice size creep | High | Medium | Monitor `git diff --stat` per task; stop at boundary |
| No web test framework | High | Low | Document honestly; rely on type-check + build + manual verification |
| **A stale `web/.next` makes `tsc` report false passes** | ~~High~~ **Closed** | High | **Realized 2026-09-26.** Cached generated types under `.next` were reused across builds, so three commits whose evidence tables claim `pnpm build` ✅ in fact did not compile. **Standing rule: `Remove-Item -Recurse -Force web/.next` before believing any build or type-check result on this project.** A green build against a warm `.next` is not evidence |
| **Green build hid a completely dead feature** (T1 filters/pagination) | ~~High~~ **Closed** | High | **Realized 2026-09-25 and fixed in the T1 filter/pagination fix commit** (`fix(web): make alert filters and pagination drive URL navigation`, +47/−54, 2 files). T1 shipped a UI wired to an empty stub callback; every check passed. Do not treat lint/tsc/build as evidence that a data path works — a change to UI data flow needs a click-through or a real test |
| **Two more blockers hidden by the same green build** (T4 dialog crash, T4 status sniffing) | ~~High~~ **Closed** | High | **Realized 2026-09-25, fixed in the T4 corrective commit** (`fix(web): guard dialog open call and use typed status in rule edit page`, +53/−31, 4 files). `showModal()` on an open modal throws at runtime; 404 detection by `.includes('404')` on a raw backend detail misclassifies 422s. Neither is statically detectable. **Read the code for effect dependencies, native browser APIs, and any error classification** |
| **Six further defects hidden by the same green build, found only by a real browser** (timezone/hydration, latched `isLoading`, dead filter, dead pending label, error-detail crash, stale URL state) | ~~High~~ **Closed** | High | **Realized 2026-09-26.** All three static checks, 120 API tests, `curl` and SSR-only inspection were green. Filtering was entirely non-functional and a failed action unmounted the whole page. This is the **third** occurrence of the same class, which makes it a structural property of this feature rather than bad luck. **Any client-side data path, effect cleanup, or error-value render must be exercised in a browser before it is called verified** |
| Parallel writers can read each other's half-finished edits | Medium | Medium | **Realized 2026-09-25**: an independent verifier ran concurrently with a fix writer and reported a TS error that was a transient mid-edit state. The orchestrator re-verified on the settled tree. Do not run a read-only verifier against files another writer is still editing |
| `corepack.cmd pnpm` / `pnpm.cmd` / bare `pnpm` all fail on this machine | ~~High~~ **Closed** | Low | **Resolved 2026-09-26** — pnpm reinstalled as 9.15.9, matching `lockfileVersion: '9.0'`. See Environment Note 1 for the `.ps1` shim trap that must not be reintroduced |
| `acknowledged_by` was client-supplied → audit spoofing | ~~High~~ **Closed** | High | **Resolved 2026-09-25** by D1 Option A (the `fix(api): derive alert acknowledgement actor from the authenticated user` commit, +109/−13, 3 files): the API derives the actor from `user.id` and ignores the body |
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

Static checks had already let three real defects through, so this feature was verified against a **running stack** (db + redis + api + worker + web in Docker) with **seeded real data**: user → API key → server → rule → metrics. HTTP round trips, not type-checking.

**Tenant correction (2026-09-26).** The API-level lifecycle round trips below ran against `verify-box-01` (`2c1e028d-…`, tenant `verify.alertwebui`). The **dashboard token resolves to a different tenant, Test User** (`1f350381-…`), which owns `test-server-01` (`8908ae1d-…`), rule `535c1d6f` and both historical alerts. The two sets of data do not mix — ingesting against `verify-box-01` with a Test User API key returns 404 "Server no encontrado" because RLS isolates it. **Any UI-facing verification must use `test-server-01`.** See "The dashboard token does not point at verify.alertwebui".

| Task | Verdict | Evidence |
|------|---------|----------|
| T1 alerts list | ✅ PASS | `/alertas` SSR renders the full table (ID, Severidad, Estado, Regla, Servidor, Mensaje, Disparada, Valor, Acciones), the filter bar (Estado, Severidad, ID de regla, Filtrar), pagination ("Mostrando 1 - 1 (límite: 50)") and a real alert row. Full path browser → SSR → API → Postgres confirmed. |
| T2 ack/resolve | ✅ **PASS (browser) 2026-09-26** | Was ❌ BLOCKED on 2026-09-25: `POST /api/v1/alerts/{id}/ack` returned HTTP 500. Backend fixed in the alert timestamp fix commit (`91e8633` on `main`, PR #16 merge `b1a2197`); ack/resolve return 200 against real Postgres; and the full lifecycle was then driven **from a real browser** — `Abierta → Reconocida → Resuelta`, correct `aria-live` announcements, both buttons `disabled` + `aria-busy` in flight, Reconocer correctly hidden for non-open alerts. See "T2 browser click-through" below. **Re-verified 2026-09-26** against two freshly created alerts, which also closed the outstanding fix-4 gap: see "Fix 4 browser-verified against a fresh alert". |
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

Confirmed preexisting: `git show main:api/app/repositories/alert.py` already contained `datetime.now(UTC)`. This branch's D1 Option A actor-identity hardening commit (the `fix(api): derive alert acknowledgement actor from the authenticated user` commit, +109/−13, 3 files) only changed the actor derivation to `user.id`; it did not touch the timestamp.

**Planned fix** (deferred to a separate ODD task in `api/`, by user decision): add `DateTime(timezone=True)` to the three columns, aligning the ORM with a database that is already `timestamptz`. Do **not** strip `tzinfo` at the write sites — that discards UTC and fights the schema.

## T2 Unblocked (2026-09-26) — the defect is fixed

Delivered as its own ODD task: `odd/tasks/alert-timestamp-timezone-drift.md`, commit `91e8633` on `fix/alert-timestamp-timezone-drift` (merged to `main` via PR #16 as `b1a2197`). The branch no longer carries a copy of this fix — rebasing onto `main` dropped the cherry-pick as an already-applied patch.

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
| Console | 0 hydration errors, 0 pageerrors, 0 dev overlay. A later capture showed no 4xx/5xx and no failed requests on plain load. The residual 404 was originally attributed to the favicon; that attribution is **retracted** — see "Correction to the earlier 404 claim" |
| Timestamp | Date cell renders `13:46` — the true UTC value — instead of drifting to browser-local `10:46` |
| Filters | `?status=resolved&offset=0&limit=50`; the selection now reaches the URL |
| Pagination | `limit=1` forces `hasNext`: `offset=0 → 1` advances `456dcf2e… → 38ad9632…`; Anterior/Siguiente both work and the Filtrar label stays "Filtrar" throughout |
| Ack / resolve | `Abierta → Reconocida → Resuelta`; `aria-live` announcements correct; both submit buttons `disabled` + `aria-busy` during flight; Reconocer hidden for non-open alerts |
| `pnpm lint` / `pnpm build` | exit 0; 5 dynamic routes |

**Not browser-verified, stated honestly:** fix 5. Both demo alerts were already `resolved`, so no action buttons remained to click, and forcing a 422 would mean deliberately breaking the API. It is covered by code review plus the captured pre-fix crash evidence. Fix 4's real proof needs a new alert in a mutable state — the next section supplies it.

## Fix 4 browser-verified against a fresh alert (2026-09-26)

The blocker above was not the UI. Four facts had to be established before a mutable alert could exist, and three of them contradict assumptions recorded earlier in this document.

### There is no alert-creation endpoint
`api/app/api/v1/alerts.py` exposes only: list (`GET ""`), `POST /{alert_id}/ack`, `POST /{alert_id}/resolve`, and rules CRUD. The UI has no create action either. The only creator is the worker — `evaluate_alerts` in `api/app/workers/alerts.py`, the `cond_ok` branch at lines 110-146 — driven by the `alert-eval-1m` cron in `api/app/workers/main.py:102`, every 60s, with `run_at_startup=False`.

### The worker was down
`docker compose ps -a` showed `worker exited 255` 32 minutes earlier, with no traceback; the last healthy `alert-eval-1m ● 0` was at 18:02:00. **While the worker is down no alert can be created at all**, no matter how many metrics are ingested. This, not the UI, is why no alert could be produced on 2026-09-25 or earlier on 2026-09-26.

### The pre-existing rule is nearly impossible to trigger
`_evaluate_rule_for_server` opens a window `[now - duration_s, now]` and requires `cond_ok = all(matches(v, threshold) for v in values)` — **every** sample in the window must breach. Rule `535c1d6f` (`cpu_usage gt 50`, `duration_s 10`) therefore cannot fire reliably: the worker ticks every 60s, so a metric ingested "now" is already older than the 10s window when the eval runs; and `cpu_usage` history contains values below 50 (e.g. `42.5`) that would make `all()` false. The trigger rule used instead was `cpu_usage gt 0` with `duration_s 600` — threshold `0` makes `all()` trivially true, and a 10-minute window tolerates tick timing.

`metrics.type` is a 6-value Postgres enum (`cpu_usage`, `mem_usage`, `disk_usage`, `load_avg1`, `load_avg5`, `load_avg15`), so "use a fresh metric name to dodge contaminated history" is not available.

### The dashboard token does not point at `verify.alertwebui`
`SPSAAS_DASHBOARD_TOKEN` resolves to tenant **Test User** (`1f350381-…`), not `verify.alertwebui` (`692e38cf-…`). Everything the UI renders belongs to Test User: server `test-server-01` (`8908ae1d-…`), active rule `535c1d6f`, and both historical alerts. Ingesting against `verify-box-01` (`2c1e028d-…`, tenant `verify.alertwebui`) returns 404 "Server no encontrado" because RLS isolates it. **`verify-box-01` is a stale seed artifact the dashboard token never addressed; `test-server-01` is the correct target.** This corrects the earlier assumption in this document that `verify-box-01` was the demo server.

### What was done
1. `docker compose up -d worker` — worker running.
2. `POST /auth/api-keys` with the dashboard Bearer token mints an API key; `ApiKeyResponse.raw_key` is returned **once**, after which only `key_hash`/`prefix` persist and the secret is unrecoverable. Ingest needs the `X-Api-Key` header, not the dashboard Bearer token.
3. `POST /api/v1/alerts/rules` — the router prefix is `/api/v1/alerts`, not `/api/v1`. `channels` requires at least one channel or it 422s ("At least one channel (webhook or email) is required"); a webhook needs a `url`.
4. Ingested `cpu_usage=99` for `test-server-01` and waited for `alert-eval-1m`.

Two alerts resulted: `41b29f74-…` from the trigger rule, and `6fcc0fb4-…` from the pre-existing rule, whose 10s window happened to contain the ingest. The old rule firing by luck is direct confirmation of the timing analysis above.

### Observed ack sequence (Chrome via `playwright-core`, harness outside the repo)

| Step | Observed |
|---|---|
| Before | `status=Abierta`, `aria-live=""`, buttons `["Reconocer","Resolver"]` |
| On click | submitter BUTTON `txt="Procesando…"`, `disabled=true`, `aria-busy=true` |
| Sibling button | `Resolver` gets `disabled=true` / `aria-busy=true` but **keeps its own text** |
| After | `status=Reconocida`, `aria-live="Alerta reconocida correctamente"`, buttons `["Resolver"]` |
| Hygiene | 47 mutations, 0 pageerrors, POST 200 |

The submitter/sibling split is the direct proof of fix 4: "Procesando…" lands only on the clicked button, and the other is disabled without being relabelled. Reproduced identically on both fresh alerts.

### Correction to the earlier 404 claim
This document previously attributed the residual 404 to the favicon. That attribution is unsupported. `find404.cjs` on a plain load reports no 4xx/5xx and no failed requests, `page.on('response')` in the ack harness captures **no** 4xx despite the console error, and the web container logs **zero** 404 responses (every request 200). The 404 never reaches application code. It is cosmetic and pre-existing; its actual origin remains **unidentified**.

### Cleanup
- Trigger rule `e994092c-…` was **deactivated, not deleted**: `alerts.rule_id` is `ON DELETE CASCADE` (`pg_constraint.confdeltype='c'`), so deleting the rule would have destroyed alert `41b29f74-…` in cascade — the evidence itself. `is_active=false` preserves it.
- The 3 minted API keys (prefix `spsk_`) were revoked; 0 remain.
- Both alerts stay `acknowledged` as durable evidence, with UTC `acknowledged_at`.
- The worker is left **running**; it was crashed, so running is the correct state.

## Accessibility round #2 (2026-09-27) — the delete dialog, exercised for the first time

Every item this document previously listed as "never exercised" for the delete dialog was exercised. **Five real defects were found, four of them invisible to lint, `tsc`, `build` and the full 120-test API suite.** This is the **fourth** occurrence of the same structural failure class, not bad luck: the discipline in this feature has to be *exercise the path in a browser*, and static checks only ever prove the code parses.

| # | Defect | Root cause | Why the static checks missed it |
|---|--------|------------|----------------------------------|
| 1 | Focus restore on Escape/backdrop **never ran** | The component did `if (!isOpen) return null`, so React unmounted the dialog subtree on close. The ref was already `null` when the `finally` block tried to restore focus. | Type-correct: `ref.current?.focus()` on a nullable ref is valid. No rule flags an early return that silently disables a cleanup path. |
| 2 | Confirm button **never received initial focus** | `showModal()` and `.focus()` were in a `useLayoutEffect`, but the dialog is server-rendered with `showModal()` only after mount, so the ref was not yet attached. | A `useLayoutEffect` reading a ref looks more correct than a `useEffect`. The ordering bug is invisible to the type checker and to lint. |
| 3 | **Tab escaped the dialog to `<body>`** | No explicit focus containment. Native modal inertness was not holding under the dev cache in use. | Nothing in a linter or a build can observe runtime tab order. |
| 4 | Desktop dialog rendered at `x:0, y:0` | `web/src/app/globals.css` does `@import "tailwindcss"`, whose v4 preflight applies `margin:0` to every element. That overrode the native `dialog:modal { margin: auto }` from the UA stylesheet. | A CSS reset beating a UA default is a rendering-order fact. No static check models the cascade. |
| 5 | The delete dialog announced its own feedback **twice** | Two nested live regions carried the same text: a persistent outer `role="status"` and an inner `role="alert" aria-live="polite"`. | Both regions are individually correct ARIA. Only a live DOM inspection shows the duplication. |

**Fixes applied to `web/src/app/alertas/reglas/components/RulesTable.tsx`.** The dialog is always mounted (`showModal()` is idempotent while already open); `showModal()` and the `[data-confirm]` focus both run in `useEffect` after the ref attaches; a `FOCUSABLE_SELECTOR` constant enumerates visible focusables and an always-`preventDefault()` `keydown` handler wraps Tab and Shift+Tab manually; `tabIndex={-1}` on the dialog covers the all-disabled case. The redundant inner live region was removed, leaving one persistent `role="status" aria-live="polite" aria-atomic="true"`. The centering fix is in the inline `<style>` block: `margin:auto` restored on `.dialog-container`, kept at `margin:0` in the mobile media query.

### Observed in a real browser (Chrome via `playwright-core`, harness outside the repo)

| Check | Observed |
|---|---|
| Tab containment | `Tab` ×10 alternates `Cancelar ⇄ Eliminar`. Focus never reaches `<body>`. `defaultPrevented` observed on **16/16** Tab events. |
| Shift+Tab containment | `Shift+Tab` ×6 cycles backwards, never reaches `<body>`. |
| Focus restore | After **both** Escape and backdrop dismissal, focus lands on the row's `Eliminar` trigger button. |
| Initial focus | `[data-confirm]` holds focus on open. |
| Backdrop discrimination | Click **outside** the panel's `boundingBox` closes; click **inside** the content does not. |
| Closed state | `open=false`, computed `display:none`, and the page is freely focusable again — the trap does not leak past dismissal. |
| Mobile 390×844 | Container and content both `390×844`, `max-width:390px`, `border-radius:0px`, focus and trap correct. |
| Centering (1280×720) | Dialog at `x:440`, `y:264`, `400×192` — centered. |
| Reversible `aria-live` toggle | `Regla desactivada` then `Regla activada`; final toggle state restored to `["Desactivar regla","Activar regla"]`. |
| Hygiene | 0 pageerrors, 0 hydration errors, 0 failed requests, no dev overlay. |

**Honest limit on defect 3 — keyboard containment, now closed (2026-09-28):** keyboard containment is enforced by the manual `keydown` trap; programmatic containment is enforced by native modal inertness. A dedicated Playwright probe (`prog-focus.cjs`, kept in the scratch e2e dir) opened the delete dialog and called `element.focus()` on **8 elements behind it** (brand, nav links, `Crear regla`, row `Editar`) while the dialog matched `:modal`. All 8 attempts left `document.activeElement` inside the dialog (the confirm button) — **no escape**. Tab ×3 after the attempts still cycled `Cancelar ⇄ Eliminar(confirm)` inside; Escape closed with focus restored to the row trigger. Note: no attribute-level inert marking exists (`[inert]`, `aria-hidden` all absent) — the browser enforces inertness through the modal top-layer mechanism, exactly as specified. Measured in headless Chrome against the compose dev server with a dev cache compiled fresh at today's boot (route recompiled from current source); the host `web/.next` is an empty leftover and cannot shadow the container, whose `/app/.next` is an anonymous volume since the original compose commit (`88dc827`).

### The measurement trap that cost this round hours

Three consecutive measurements of "the same" code produced three different sequences. **Cause: `web/.next`.** The `web` service bind-mounts `./web:/app`, so a `pnpm build` leaves a production `.next` inside the directory the dev server uses. The dev server then serves the *built* bundle while the source on disk is something else entirely — the handler under test was not the handler in the file.

This is a **new dimension of the standing `.next` rule already recorded under Exact Checks**. That rule covered a stale `.next` making `tsc` report false passes; this case is worse, because it makes a **browser** measure code that is not on disk. Any browser evidence gathered on this project is only evidence of what was actually served, so the served code must be confirmed first:

```powershell
Remove-Item -Recurse -Force web/.next   # clear any production build
docker compose restart web               # then verify against the live source
```

**Standing rule, added 2026-09-27: never record a browser measurement on this project without having deleted `web/.next` and restarted `web` in the same session.** The T1 filters, the T4 dialog crash, the six click-through defects, and all five defects in this round were each found only by a real browser. None were found by a check.

### The residual 404 is identified: the favicon

The earlier correction in this document was right that the 404 was cosmetic and never reached application code, but it left the origin **unidentified**. It was the favicon: the only icon was the placeholder `web/src/app/icon.svg`, and no `favicon.ico` existed. The user's own `favicon.ico` was moved from the repository root to **`web/src/app/favicon.ico`** — the Next.js App Router convention, which serves it at `/favicon.ico` — and the placeholder `icon.svg` was deleted. `GET /favicon.ico` now returns `200 image/x-icon`, 32.038 bytes, and a plain load of `/alertas` reports no 4xx/5xx and no failed requests. **Correction to the correction: the favicon hypothesis was correct; it was only the earlier "does not reach application code" framing that made it look unsupported.**

### Token round trips, now exercised

The "no live 401 or missing-token round trip" gap is closed. Two distinct failure paths were driven through the UI:

| Scenario | Observed |
|---|---|
| Expired dashboard token (real 401 from the API) | UI surfaces the honest Spanish error; no crash, no unmounted table. |
| `SPSAAS_DASHBOARD_TOKEN` absent (temporary, backed up and restored) | `No se pudieron cargar las alertas: Token de dashboard no configurado (SPSAAS_DASHBOARD_TOKEN)`; 0 rows; 2 error boxes; **0 console errors**. |

The override was restored byte-for-byte and `/alertas` returned to 200 with no leftover backups. Per the existing environment rule, the token itself was never printed or read into any transcript.

### Why fix 5 (the 422 branch) is still not browser-reproducible

This was investigated rather than merely deferred. `mapApiError` in `web/src/app/alertas/reglas/utils.ts` maps 422 to `` `Datos inválidos: ${detail}` ``, and the create and update actions in `web/src/app/alertas/reglas/actions.ts` validate **the same constraints the API enforces**: entity type, metric in range 1–100, allowed operators, finite threshold, positive integer duration, valid severity, at least one channel, and UUID-validated `entity_id`. A normal browser user therefore has no path to a 422 — the client rejects first. Exercising the branch would require adding a test framework (none exists in `web/`, and introducing one is out of scope) or deliberately breaking the API. The branch is defensive code for a condition the UI cannot produce, and it stays covered by code review plus the captured pre-fix crash evidence.

---

## Next Step
**T1, T2, T3, T4 and T5 are all DONE and verified against a running stack. The feature SHIPPED as 10 merged PRs (#17–#26) to `main` (`e1bc567`).** The chain was delivered via `stacked-to-main` strategy with one main commit per PR, in order:
`e8c9e7e`(#17), `fcdea79`(#18), `ce72e67`(#19), `644e91a`(#20), `85e879a`(#21), `71949c3`(#22), `bf53fcb`(#23), `c953919`(#24), `f3c8aba`(#25), `e1bc567`(#26).

Total feature diff: 23 files, +4440/−25. All slice tips are confirmed ancestors of `origin/main`. The `5bd2017` slice 5 TypeScript compile fix (action state + submit handler typing) is on main; slice 5 went from 406 to 274 lines and no longer needs a `size:exception`. The alert timestamp/timezone fix landed independently as PR #16 (merge `b1a2197`, commit `91e8633`). Integrated-main gate after the merge: `tsc --noEmit`, lint and `pnpm run build` all exit 0 from a deleted `web/.next`; build emits `/`, `/alertas`, `/alertas/reglas`, `/alertas/reglas/[id]/editar`, `/alertas/reglas/nueva`.

All merged chain branches were deleted. Local branches remaining: `main` and `agents/gentle-ai-integration`. Remote has only `main`.

Unverified and honest — remaining verification limits of a shipped feature:
- Fix 5 (422 error mapping) is not browser-reproducible: the client validates every constraint the API enforces, so no browser user can reach a 422 without a deliberate API break. Covered by code review plus the captured pre-fix crash evidence. See "Why fix 5 (the 422 branch) is still not browser-reproducible". **Permanently discarded as a verification target by user decision (2026-09-27) — not deferred.**
- ~~**Programmatic** focus containment outside the dialog~~ — **closed 2026-09-28: measured, no defect** (native modal inertness held against 8 programmatic `focus()` attempts). Recorded under defect 3.
- No screen reader was run. `aria-live` announcements were verified at the DOM level only (one persistent `role="status"` region; observable text transitions on toggle), and dialog focus order was verified by measuring `document.activeElement`. Actual spoken output remains unverified. Deferred by user decision (2026-09-27).
- ~~SMTP delivery: never exercised, and blocked on credentials plus explicit remote authorization. Deferred by user decision (2026-09-27).~~ — **closed 2026-09-28: delivered end-to-end against real Gmail.** User authorized host `smtp.gmail.com` and provided the destination mailbox (`iasoloducha@gmail.com`, self-delivery). Two earlier app passwords from a different Google account produced `535 5.7.8 Username and Password not accepted` (correct typed failure: delivery `failed`, `connection_error`, error captured); after the app password was regenerated in the correct account, the delivery row transitioned `pending → sent` (`external_ref=email:iasoloducha@gmail.com`, `delivered_at=2026-09-28T18:40:00Z`) and the user received the email. **NEW standing rule: never fire repeated SMTP AUTH attempts — Gmail blocks the IP after several 535s and would also block a valid password.** SMTP config lives only in `api/.env` (gitignored, never committed).

---

*ODD feature document — `odd/tasks/alert-web-ui.md`*
*Repository: spsaas | Branch: `main` (`e220056`) — feature shipped via 10 stacked PRs #17–#26 | Created: 2026-09-25 | Updated: 2026-09-28*
*Merged PR chain (oldest first, merge commit SHAs): `e8c9e7e`(#17) → `fcdea79`(#18) → `ce72e67`(#19) → `644e91a`(#20) → `85e879a`(#21) → `71949c3`(#22) → `bf53fcb`(#23) → `c953919`(#24) → `f3c8aba`(#25) → `e1bc567`(#26). All merged chain branches deleted; remote has only `main`.*
*Feature work units (oldest first, subjects + measured net sizes — SHAs deliberately not tracked, per this document's convention against unstable SHA references): `feat(web): add typed server-only client for the alerts API` (+109/−0, 1 file) → `feat(web): add read-only alerts overview page and table` (+444/−0, 2 files) → `feat(web): add app shell with header, navigation and footer` (+41/−1, 1 file) → `fix(api): derive alert acknowledgement actor from the authenticated user` (+109/−13, 3 files) → `feat(web): add alert acknowledge and resolve actions` (+259/−4, 4 files) → `fix(web): map alert action errors by HTTP status` (+68/−75, 3 files) → `feat(web): add alert rules list and create flow` (+1628/−5, 11 files) → `fix(web): make alert filters and pagination drive URL navigation` (+47/−54, 2 files) → `feat(web): add alert rule editing and accessible delete confirmation` (+1245/−101, 4 files) → `fix(web): guard dialog open call and use typed status in rule edit page` (+53/−31, 4 files) → `docs: document SMTP configuration for alert email delivery` (+10/−1, 1 file) → `docs: correct SMTP port comment to reflect STARTTLS-only support` (+1/−1, 1 file) → `docs: record the alert timestamp fix evidence and the T2 unblock` (+29/−8, 1 file) → `fix(web): correct client-reaction defects found in browser click-through` (+56/−20, 3 files) → `docs(odd): track the browser click-through and the six defects it found` (+393/−0, 1 file) → `docs(odd): correct the slice size table with measured diffs` (+19/−11, 1 file) → `docs(odd): record the slice #1 split and a false build claim it exposed` (+53/−6, 1 file) → `docs(odd): verify fix 4 against a fresh alert and retract four stale claims` (+62/−13, 1 file).*
*State at handoff: **Feature SHIPPED on `main` (`e1bc567`). T1–T5 verified against a live stack; full UI clicked through in Chrome; all six click-through defects fixed; fix 4 browser-verified against a freshly created alert (`6fcc0fb4`, `41b29f74`, both left `acknowledged`); delete dialog exercised and its five defects fixed.** Suite green on the settled tree: 21 alerts tests, 120 full API suite, web lint 0/0, tsc 0, clean build from a deleted `.next`, 0 hydration/page errors, 0 failed requests. Token round trips (real 401, missing token) both correct; favicon served as `200 image/x-icon`; 422 branch proven unreachable through the UI. Chain strategy `stacked-to-main` confirmed.* **SMTP real-delivery verification closed 2026-09-28: delivered to Gmail, row `sent`, email received by the user — the last open verification limit of this feature.**