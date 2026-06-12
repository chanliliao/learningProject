# Plan Index: InfrasAI Parity Roadmap

## Summary

Master index for the 8-phase program that closes the gap between this learning project and InfrasAI's production product, as scoped in `.agents/docs/infrasai-comparison.md`. Each phase has its own detailed plan file with stories and atomic tasks. Build strictly in order — each phase depends on the prior.

## Locked Decisions (from planning Q&A)

| Decision | Choice |
|---|---|
| Lines of business | Life, P&C, Annuities/Retirement, Group/Health/Supplemental (all 4) |
| Input formats | ACORD XML, PDF (text), PDF (scanned/OCR), Excel/CSV (all 4) |
| Canonical Data Model | **Pragmatic ACORD-faithful subset** — correct ACORD entity/field names + structure, scoped to the ~20–30 entities the real sample docs use per LOB; extension points marked |
| Build strategy | **Vertical slice** — take Life through ALL phases end-to-end first, then replicate to P&C / Annuity / Group |
| Migrations | **Greenfield** — no production data; simple migrations, `recreate_tables.py` OK, data-backfill steps are fresh-DB assumptions |
| Transform DSL | **CEL / JMESPath** |
| SDK languages | **TypeScript + Python** |
| OCR engine | **OpenRouter vision/PDF** (vision LLM + `mistral-ocr` fallback; reuses `OPENROUTER_API_KEY`) |
| Gate auto-approval | **Confidence-threshold + exception escalation** — above `confidence_threshold` auto-approves (score+threshold+policy-version logged); below/flagged escalates to human. SOC 2-clean. |
| LOB detection | **User override + LLM default** — LLM classifies, user confirms/overrides at upload |
| PII at rest + outputs | **Dedicated Phase 8** — encrypt PII columns, mask/tokenize in partner SDK outputs unless authorized+audited |
| Frontend | **Per-phase UI tasks** — CDM review, outputs view, LOB+schema selectors planned alongside backend |

## Phase Order & Files

| Phase | File | Build | Effort | Depends on |
|---|---|---|---|---|
| 0 | `phase-0-pii-masking.plan.md` | PII masking before LLM | S | — |
| 1 | `phase-1-canonical-data-model.plan.md` | ACORD CDM + 4-LOB samples | XL | 0 |
| 2 | `phase-2-many-to-one-fanout.plan.md` | One carrier → many distributors | L | 1 |
| 3 | `phase-3-transform-dsl.plan.md` | CEL/JMESPath rule engine | M–L | 1, **then 2** |
| 4 | `phase-4-nl-rule-editing.plan.md` | English → rule + preview + redeploy | M | 3 |
| 5 | `phase-5-sdk-partner-layer.plan.md` | TS + Python SDK, OpenAPI, headless + auto-approval | L | 2 |
| 6 | `phase-6-multiformat-ingest.plan.md` | PDF/OCR/Excel extractors | L | 1 |
| 7 | `phase-7-eval-at-scale.plan.md` | Regression, drift, CI | M | all |
| 8 | `phase-8-pii-at-rest-output-policy.plan.md` | Encrypt PII at rest (+ key rotation) | M | 5 |

> **PII split**: partner-output masking moved INTO Phase 5 (ships with the SDK — no leak window). Phase 8 now covers only encryption-at-rest + key rotation.

> **Sequencing note**: Phases 2 and 3 both rewrite `transform.py`. Do **2 before 3** (not parallel) to avoid a merge conflict — Phase 2's projection reuses the existing engine; Phase 3 then extends it with rules.

## Why This Order

1. **PII first** — correctness/security bug, must precede anything touching real data.
2. **CDM is the foundation** — the N×M→N+M abstraction. Fan-out, SDK, and NL rules all sit on it. Nothing meaningful is buildable without it.
3. **Fan-out + DSL** can proceed in parallel after CDM (both depend only on CDM).
4. **NL editing** needs the DSL (rules must be data an LLM can author).
5. **SDK** needs fan-out (a clean model worth exposing to partners).
6. **Multi-format ingest** broadens inputs once the core is stable.
7. **Eval at scale** hardens continuously; finalized last.
8. **PII at rest + output policy** depends on the partner SDK + API keys (Phase 5) existing, since output masking keys off per-tenant authorization. Phase 0 covered prompt-time PII; Phase 8 covers storage + disclosure.

## Build Strategy — Vertical Slice (Life First)

Do NOT build each phase across all 4 LOBs before moving on. Instead:

1. **Slice 1 (Life)**: implement Phases 0→8 for the **Life** line of business only — one CDM, Life samples in all 4 formats, fan-out to Life distributors, DSL, NL editing, SDK, eval, PII. This proves the entire architecture end-to-end on a small surface and surfaces integration problems early.
2. **Slice 2+ (P&C → Annuity → Group/Health)**: replicate by adding each LOB's CDM, samples, and distributor views. By now the layers are stable, so adding a LOB is mostly data + a few mappings, not new architecture.

Each phase plan is written LOB-agnostic; apply it to Life first, then repeat the LOB-specific tasks (CDM schema, samples, views, fixtures) per additional line.

## Global Conventions (apply to every phase)

- **Validation commands** (this repo, not pnpm):
  - Backend: `cd backend && uv run pytest`
  - Frontend type/build: `cd frontend && npm run build`
  - Frontend lint: `cd frontend && npm run lint`
  - Frontend tests: `cd frontend && npm test`
- **Tests in test mode**: pass `mode="test"` to agent/graph calls so `TestModel` is used (no API key). See `tests/agents/test_transform_apply.py`.
- **New deps**: add to `backend/pyproject.toml` `dependencies`, then `uv sync`.
- **New routers**: create in `backend/app/routers/`, register in `backend/app/main.py` (per CLAUDE.md rule).
- **New models**: create in `backend/app/models/`, add an Alembic migration. **Greenfield**: migrations stay simple; where a phase calls for a data-backfill of existing rows (e.g. PII re-encrypt), it's acceptable to assume a fresh DB and skip the backfill — note it explicitly. `recreate_tables.py` may be used in dev.
- **Frontend tests**: every new/changed component gets at least one vitest test (mirror `frontend/src/**/*.test.tsx`). A frontend task isn't done until `npm test` covers it.
- **Internal route auth**: Phase 5 adds API-key auth for `/v1` partner routes. At that point also protect the existing internal `/api/*` routes (session/JWT or a dev bypass) — don't leave them open once auth exists.
- **Security (CLAUDE.md)**: no inline secrets (`.env` only); never pass user input to shell/`eval`. The DSL phase MUST use a sandboxed evaluator, never Python `eval`.
- **Tenant propagation**: every new row (mappings, views, rule versions, outputs) must set `tenant_id` from request context, not the `"default"` literal. Phase 5 introduces the API-key→tenant dependency; earlier phases thread a `tenant_id` parameter through node/agent calls so the switch in Phase 5 is wiring, not a rewrite.
- **Auto-approval policy (cross-cutting)**: introduced in Phase 5, but every gate-approval code path from Phase 2 onward must route through a single `should_auto_approve(stage, mappings, settings)` helper so the policy is enforced in one place and logged with score+threshold+`policy_version`.
- **Stage-result currency**: nodes currently *append* `StageResult` rows. Any re-run path (Phase 2 re-projection, Phase 4 redeploy) must either version stage results (`attempt` column) or upsert the latest — never leave ambiguous duplicate `build`/`project` rows. Decided: add an `attempt: int` and treat max(attempt) as current.

## Acceptance Criteria (program-level)

- [ ] All 8 phase plans implemented and archived to `.agents/plans/completed/`
- [ ] One sample document per LOB × per format exists and flows through the pipeline
- [ ] A single carrier mapping serves ≥2 distributor views with no extra LLM calls
- [ ] Business user can author a rule in English and preview its impact
- [ ] TS + Python SDK published with a ≤15-line quickstart
- [ ] Backend `uv run pytest` and frontend `npm test` green after every phase
