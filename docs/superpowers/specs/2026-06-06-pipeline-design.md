# Pipeline — InfrasAI-style Schema Mapping Pipeline Design

**Date:** 2026-06-06
**Status:** Draft — awaiting user review

---

## Overview

`pipeline` is a learning project that mimics the core of InfrasAI's product: turning a carrier's
insurance data document into a distributor's target schema through a multi-stage AI pipeline with
human review and full auditability.

A user uploads a carrier **ACORD (TXLife) XML** document and selects a **distributor JSON target
schema**. A six-stage pipeline — orchestrated as ordered steps, not autonomous agents — extracts
fields, interprets them, proposes a mapping with per-field confidence, generates a runnable
transform, validates it, and exposes a natural-language support interface over the result. A human
reviews and approves the output of every stage between stages. Every state change is recorded in an
append-only audit log. An eval harness measures mapping accuracy against hand-labeled golden data.

The point of the project is not the demo. It is to confront the unglamorous, interview-relevant
hard parts: confidence calibration, human-in-the-loop gating, determinism/auditability in a
regulated domain, schema/prompt versioning for maintainability, and evaluation of a
non-deterministic pipeline.

This project builds on the existing `learningProject` monorepo (FastAPI backend, Vite + React + TS
frontend).

---

## Goals

- Map carrier ACORD/TXLife XML to a selectable distributor JSON schema via a 6-stage pipeline.
- Score every field mapping with a hybrid confidence metric that drives a human-review gate.
- Keep the LLM advisory only: it proposes, a human approves, nothing goes live silently.
- Record every decision in an append-only audit log.
- Prove correctness with an eval harness (field-level precision/recall + confidence calibration).
- Provide a React review console for the full human-in-the-loop workflow.

## Non-Goals (Future Work)

- Real authentication / login. Data model is tenant-aware (`tenant_id` columns) but no auth is built.
- Cost / rate-limit guardrails (token budget caps). Observability lands first; caps come later.
- Idempotent partial re-runs of a single stage. Noted in the design; not built in v1.
- A real job queue (arq/Redis/Celery). v1 uses in-process background tasks.
- Production deployment, horizontal scaling.

---

## Architecture

### Shape

One **orchestrator** runs six stages in a fixed order. Each stage is a focused module with its own
prompt (if LLM-backed), a typed input/output contract, and its own tests. Between stages sits a
**human gate**: the run pauses in an `awaiting_review` state until a human approves (or edits) the
stage output, then advances.

This is deliberately a pipeline, not a swarm of autonomous agents. In a regulated, auditable domain
the value is control and traceability, not emergent agent behavior.

### Execution model

Pipeline runs are **asynchronous**, executed via **FastAPI `BackgroundTasks`** (in-process, no extra
infra — appropriate for a single-user learning app). Starting a run returns immediately with a run
id; stages execute in the background and pause at each gate. The frontend **polls** run status. This
is required because LLM stages are slow and would otherwise time out HTTP requests. A future swap to
a real job queue is possible without changing stage interfaces.

### Review gate granularity

**Every stage is gated.** Each stage's output enters `awaiting_review`; a human approves, edits, or
rejects before the next stage runs. The Map stage additionally exposes **per-field** review
(approve / edit / reject each low-confidence `FieldMapping`); edits are re-scored and audited. This
matches a strict regulated workflow and maximizes the auditability story.

### Determinism guardrails (the core lesson)

- Deterministic code does what code does well: XML parsing (Extract) and transform application
  (Build/Test) are plain Python, never the LLM.
- The LLM only **proposes**. Orchestrator persists proposals as `awaiting_review`. Only a human
  review action flips state to `approved`.
- Every flip is recorded in `AuditEvent` (append-only). The audit log is the source of truth for
  "who changed what, when, and why."

---

## The Six Stages

| Stage | LLM? | Input | Responsibility | Output |
|---|---|---|---|---|
| **1. Extract** | No | ACORD XML | Deterministic XML parse (`lxml`) → flat list of raw fields (path, value, inferred type). | `ExtractedField[]` |
| **2. Read & Interpret** | Yes | `ExtractedField[]` | Describe each field's meaning + business rules/constraints using ACORD context. | `InterpretedField[]` |
| **3. Map** | Yes | `InterpretedField[]` + selected target JSON schema | Propose source→target field mapping + transform logic. **Core value.** Per-field confidence + review. | `FieldMapping[]` |
| **4. Build** | No (templated) | approved `FieldMapping[]` | Generate a runnable transform: a JSON mapping config + a Python applier that converts source→target. | `TransformSpec` |
| **5. Test** | Partial | `TransformSpec` + sample values | Auto-generate test cases, run the transform, validate output against target schema constraints. | `TestReport` |
| **6. Support** | Yes | a completed run | Vector RAG + tool-calling chat over the run: answer "why was field X mapped to Y?", edit a mapping in plain English (which itself goes through the review gate). | chat responses |

### Confidence scoring (cross-cutting)

Every `FieldMapping` produced by stage 3 gets a **hybrid confidence score** combining:

- **Deterministic heuristics:** source/target type compatibility, name similarity, required-field
  presence, enum/format validity.
- **LLM self-rating:** the model's own stated certainty for the mapping.

The blended score (default flag threshold **0.8**, configurable) determines whether a field is
auto-accepted or **flagged for human review**. A calibration report (in eval) checks whether
low-confidence flags actually correlate with wrong mappings — teaching why naive LLM self-confidence
is insufficient.

---

## Data Model (Postgres + pgvector, via SQLModel)

- **PipelineRun** — id, `tenant_id`, status (`running` / `awaiting_review` / `completed` /
  `failed`), source document ref, `target_schema_id`, `prompt_version`, `target_schema_version`,
  timestamps.
- **TargetSchema** — id, name, version, JSON Schema definition. Two seeded distributor schemas in v1.
- **StageResult** — id, run_id, stage name, status (`pending` / `awaiting_review` / `approved` /
  `rejected`), payload (JSON), timestamps.
- **FieldMapping** — id, run_id, source_path, target_path, transform, confidence, flags (JSON),
  status (`proposed` / `approved` / `edited` / `rejected`).
- **AuditEvent** — append-only. id, run_id, actor (`system` / `human`), action, before/after (JSON),
  timestamp. Never updated or deleted.
- **ReviewAction** — id, run_id, stage / field_mapping_id, reviewer, decision, note, timestamp.
- **LLMCall** — observability. id, run_id, stage, model, prompt, response, prompt_tokens,
  completion_tokens, latency_ms, estimated_cost, timestamp.
- **Embedding** — pgvector store for Support RAG. id, run_id, source_ref, chunk text, vector.

All run-scoped tables carry `tenant_id` to keep the multi-tenant story design-ready without building
auth. Schema managed by **Alembic** migrations.

---

## LLM Integration

- Provider: **OpenRouter** (`OPENROUTER_API_KEY` in `backend/.env`, never committed).
- Default chat model: **cheapest workable**, configurable **per stage** so the cost-vs-quality
  tradeoff can be tuned later.
- Embeddings: **OpenRouter embedding endpoint**, stored in the `Embedding` table (pgvector).
- A thin client wraps OpenRouter with a structured-output helper (JSON schema / function-calling
  style) and records every call into `LLMCall` (observability).

---

## Eval Harness

- Location: `backend/eval/`.
- Golden dataset: ~10 sample documents with hand-labeled correct mappings (covering both target
  schemas).
- Runner executes the Map stage against each, compares to golden, and reports:
  - field-level **precision / recall**,
  - **confidence calibration** (do low-confidence flags predict errors?),
  - aggregate **LLM cost** for the run set (from `LLMCall`).
- Run via `uv run python -m eval`.

---

## Sample Data

Real, freely-licensed *life* TXLife sample instances are not publicly available (genuine files are
behind ACORD membership). Strategy:

- **Synthetic, real-structure life TXLife XML** authored from public ACORD schema documentation
  (authentic elements/codes: `TXLife > OLifE > Holding / Policy / Party / Person`, real type codes;
  synthetic field values). Includes a few deliberately **messy / non-standard** documents to
  exercise the confidence + review gate.
- **One genuinely-real ACORD XML instance** adapted from the public
  `appulate/appulate-acordxml-svc-sample` repo (Workers' Comp / P&C line). Source documented in the
  sample file header. Because that repo states no license, the sample is kept minimal and adapted
  rather than copied wholesale. Including a different ACORD line also proves the pipeline
  generalizes beyond life.
- **Two distributor JSON target schemas** authored for this project, selectable at upload — proving
  the "launch once, deploy everywhere" multi-target story.

If genuine ACORD member files become available later, they drop in unchanged.

---

## Frontend — Review Console (React + TS + Tailwind CSS)

Routes:

- **Upload** — pick ACORD source + select one of the target schemas, start a run.
- **Run view** — stage timeline with per-stage status and output; polls while running; approve /
  edit / reject each stage's output to advance the gate.
- **Field review table** — for the Map stage, approve / edit / reject flagged low-confidence fields.
- **Audit log** — read-only view of the append-only event trail for a run.
- **Eval dashboard** — precision/recall + calibration + LLM cost from the harness.
- **Support chat** — natural-language Q&A over a completed run.

Styling via **Tailwind CSS**. Reads backend base URL from `VITE_API_URL` (existing convention).

---

## Backend Layout

```
backend/app/
  agents/        base.py, extract.py, interpret.py, map.py, build.py, qa.py, support.py
                 # qa.py = the "Test" stage; named qa to avoid pytest collecting it
  pipeline/      orchestrator.py, confidence.py
  llm/           openrouter.py        # chat + embeddings + structured-output + LLMCall logging
  models/        run.py, mapping.py, audit.py, schema.py
  routers/       pipeline.py, review.py, eval.py, support.py
  schemas/       sample ACORD xml + target JSON schemas
backend/alembic/ migrations
backend/eval/    golden/, runner.py
docker-compose.yml                    # postgres + pgvector
```

Routes are registered in `backend/app/main.py` per existing project convention.

---

## Implementation Milestones

Built as four sequential milestones. Each is independently shippable and gets its own
implementation plan (via the writing-plans skill) and its own feature branch.

- **M1 — Foundation + spine:** Docker Postgres+pgvector, SQLModel models, Alembic, OpenRouter
  client + LLMCall logging, target schemas, Extract stage, Map stage, orchestrator skeleton, run +
  pipeline API. Outcome: upload → extract → mapping proposed (no review UI yet).
- **M2 — Confidence + review + frontend:** hybrid confidence scoring, per-stage + per-field review
  gates, audit log, React review console (upload, run timeline, field review, audit view) with
  Tailwind. Outcome: full human-in-the-loop mapping workflow.
- **M3 — Build + Test + eval:** Build stage (transform generation + applier), Test stage (auto test
  cases + schema validation), eval harness with golden data + calibration + cost, eval dashboard.
  Outcome: end-to-end runnable transform with measured accuracy.
- **M4 — Support / RAG:** Read & Interpret stage enrichment, embeddings + pgvector, Support stage
  (vector RAG + tool-calling chat, NL edits through the gate), support chat UI. Outcome: complete
  6-stage product.

---

## Error Handling

- Malformed XML, missing required fields, or source/target schema mismatch produce graceful,
  typed error responses — never unhandled 500s. A regulated-domain pipeline cannot crash on bad
  input.
- A failed stage marks the run `failed`, records an `AuditEvent`, and surfaces the reason in the
  run view.
- LLM call failures (timeout, rate limit, malformed output) are caught, logged to `LLMCall`, and
  retried with bounded attempts before failing the stage.

---

## Testing Strategy

- **Backend:** pytest. Each stage module has unit tests against its I/O contract. Deterministic
  stages (Extract, Build, Test) are tested with fixed fixtures. LLM-backed stages are tested with
  mocked LLM responses so tests run offline and deterministically. Orchestrator tested for correct
  sequencing and gate pausing. Alembic migrations applied to a test database.
- **Frontend:** vitest + @testing-library/react. Component tests for review table, run view polling,
  upload flow.
- **Eval:** the harness itself is the integration-level correctness check for mapping quality.

---

## Dev Commands (additions)

| Task | Command |
|---|---|
| Start Postgres+pgvector | `docker-compose up -d` |
| Apply migrations | `cd backend && uv run alembic upgrade head` |
| Run eval harness | `cd backend && uv run python -m eval` |
| Start backend | `cd backend && uv run fastapi dev app/main.py` (existing) |
| Start frontend | `cd frontend && npm run dev` (existing) |

---

## Environment Variables

Backend `backend/.env` (gitignored):

- `OPENROUTER_API_KEY` — OpenRouter API key (chat + embeddings).
- `DATABASE_URL` — Postgres connection string (matches docker-compose).

Frontend `frontend/.env.local` (existing): `VITE_API_URL`.
