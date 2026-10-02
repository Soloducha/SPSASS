# Feature: Vitest Setup + Unit Tests for Web Validation Logic

## Objective
Set up Vitest in the web project and add unit tests for validation logic and FormData parsing (especially Telegram channel) in Server Actions.

## Problem
- Web project has **zero tests** — only lint + typecheck in CI
- New Telegram channel fields in Create/Edit rule forms need validation coverage
- Validation logic duplicated between client forms and Server Actions
- No regression safety for channel parsing (email, webhook, telegram)

## Why
- Telegram channel is new (chat_id, thread_id, silent) — must validate shape matches backend
- Server Actions parse FormData → typed objects; bugs here = silent data corruption
- Validation functions are pure → ideal for fast, deterministic unit tests
- CI currently misses logic errors that don't trigger typecheck

## Scope
- **In scope**: Vitest install/config, unit tests for `actions.ts` validation/parsing, shared validation lib extraction, CI integration
- **Out of scope**: React component tests (RTL), E2E, visual regression

## Constraints
- Node 24, pnpm 12.8.1 (pinned in CI/Dockerfile)
- Next.js 16.3.5, React 19.3.0
- TypeScript 5.7.2
- jsdom environment for React components later
- Alias `@/` → `src/` must work in tests

## Acceptance Criteria
1. `pnpm run test` passes in web/ directory
2. Unit tests cover:
   - `validateCreateRuleData` (all channels, edge cases)
   - `validateUpdateRuleData` (partial updates, clearing channels)
   - `validateEntityId` / `validateRuleId` (UUID guards)
   - FormData parsing → `AlertRuleCreate` / `AlertRuleUpdate` (Telegram shape: numeric ID or @username, thread_id positive int, silent boolean)
3. Shared validation extracted to `web/src/lib/validation.ts` (client + server reuse)
4. CI job `web` runs `pnpm run test`
5. All tests pass locally and in CI

## Tasks

### T1: Install Vitest + deps + config
- Add devDependencies to `web/package.json`
- Create `web/vitest.config.ts` (jsdom, @/ alias, setup file)
- Create `web/vitest.setup.ts` (jest-dom)
- Add scripts: `test`, `test:watch`, `test:ui`

### T2: Extract shared validation to `lib/validation.ts`
- Move `validateField` logic from CreateRuleForm/EditRuleForm to `web/src/lib/validation.ts`
- Export: `validateEntityType`, `validateEntityId`, `validateMetric`, `validateOperator`, `validateThreshold`, `validateDuration`, `validateSeverity`, `validateEmail`, `validateWebhookUrl`, `validateWebhookHeaders`, `validateTelegramChatId`, `validateTelegramThreadId`, `validateChannels`
- Update both forms to import from shared lib

### T3: Unit tests for Server Action validation (actions.ts)
- `web/src/app/alertas/reglas/actions.test.ts`
- Test `validateCreateRuleData`: valid/invalid entity_type, metric, operator, threshold, duration, severity, channels (email array, webhook URL+headers, telegram chat_id/thread_id/silent)
- Test `validateUpdateRuleData`: partial updates, clearing channels (empty string → undefined)
- Test `validateEntityId` / `validateRuleId` (UUID regex)
- Test `validateToken` (missing token error)

### T4: Unit tests for FormData parsing in Server Actions
- `createAlertRuleAction` FormData → `AlertRuleCreate` (all 3 channels, telegram shape validation)
- `updateAlertRuleAction` FormData → `AlertRuleUpdate` (partial, clearing channels)
- Edge cases: missing fields, empty strings, invalid JSON in webhook_headers, non-numeric thread_id

### T5: Unit tests for shared validation lib
- `web/src/lib/validation.test.ts`
- Mirror client-side validation rules (same as server but usable in React)

### T6: CI integration
- Add `pnpm run test` step to `.github/workflows/ci.yml` job `web`
- Ensure Node 24 + pnpm 12.8.1 cached

### T7: Verify locally
- Run `pnpm run test` in web/
- Run `pnpm run build` (typecheck)
- Run `pnpm run lint`

## Route Declaration
| Task | Route | Trigger Evidence |
|------|-------|------------------|
| T1 | Delegated direct (writer) | 2+ non-trivial files (package.json, vitest.config.ts, vitest.setup.ts) |
| T2 | Delegated direct (writer) | 2+ files (new lib + 2 form updates) |
| T3 | Delegated direct (writer) | New test file, ~100+ lines |
| T4 | Delegated direct (writer) | New test file, ~100+ lines |
| T5 | Delegated direct (writer) | New test file |
| T6 | Direct inline | 1 mechanical edit (CI yaml) |
| T7 | Delegated direct (verifier) | Commands: test, build, lint |

## Progress
- [x] T1: Install Vitest + deps + config — commit `ee8e3ee`
- [x] T2: Extract shared validation to lib/validation.ts — commit `f2bd335`
- [x] T3: Unit tests for Server Action validation — commit `81a2454`
- [x] T4: Unit tests for FormData parsing — commit `6c69e59`
- [x] T5: Unit tests for shared validation lib — commit `30b5ce6`
- [x] T6: CI integration — commit `e7ec4c9`
- [x] T7: Verify locally — 95 tests pass, lint clean, build ok

## Status
**COMPLETED** — All tasks done. Merged via PR #30 (`53e21a8`). Vitest infrastructure + 95 unit tests + CI integration + Telegram channel in web forms.