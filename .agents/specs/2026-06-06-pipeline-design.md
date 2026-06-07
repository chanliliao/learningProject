# Pipeline — InfrasAI-style Schema Mapping Pipeline Design

**Date:** 2026-06-06
**Status:** Draft — awaiting user review

---

## Overview

`pipeline` is a learning project that mimics the core of InfrasAI's product: turning a carrier's
insurance data document into a distributor's target schema through a multi-stage AI pipeline with
human review and full auditability. It is also a deliberate vehicle for learning the current
(2026) industry AI-engineering stack.

A user uploads a carrier **ACORD (TXLife) XML** document and selects a **distributor JSON target
schema**. A six-stage pipeline — modeled as a **LangGraph state machine**, not autonomous agents —
extracts fields, interprets them, proposes a mapping with per-field confidence, generates a runnable
transform, validates it, and exposes a natural-language support interface over the result. A human
reviews and approves the output of every stage via LangGraph interrupts. Every state change is
recorded in an append-only audit log. An eval harness measures mapping accuracy against
hand-labeled golden data.

The point of the project is not the demo. It is to confront the unglamorous, interview-relevant
hard parts: confidence calibration, human-in-the-loop gating, determinism/auditability in a
regulated domain, schema/prompt versioning for maintainability, and evaluation of a
non-deterministic pipeline — using the same tools serious shops (and InfrasAI) use.

This project builds on the existing `learningProject` monorepo (FastAPI backend, Vite + React + TS
frontend).

---

## Technology Stack

Chosen to match the 2026 industry best-practice division of labor (LangGraph for orchestration +
LlamaIndex for retrieval + Langfuse for observability/eval + PydanticAI for structured output),
avoiding redundant overlap (no standalone LangChain chains; Qdrant instead of pgvector).

| Concern | Tool | Role |
|---|---|---|
| Orchestration | **LangGraph** | The pipeline is a LangGraph `StateGraph`; gates = `interrupt` + checkpointer. |
| Structured LLM output | **PydanticAI** | Schema-valid extraction/mapping with validation + retry, over OpenRouter. |
| Retrieval / RAG | **LlamaIndex** | Ingestion, chunking, retrieval for the Support stage (and future PDF/Excel parsing). |
| Vector DB | **Qdrant** | Stores embeddings for Support RAG. Runs as a Docker service. |
| Relational DB | **Postgres** | Runs, stages, mappings, audit, LLM-call log. Docker service. |
| Migrations | **Alembic** | Versioned Postgres schema. |
| Observability | **Langfuse** | Traces every LLM call + prompt versioning + eval UI. A thin local `LLMCall` table is kept as an audit mirror. |
| Evaluation | **Ragas** + custom harness | Ragas for Support/RAG metrics; custom golden-set precision/recall for Map. |
| LLM gateway | **OpenRouter** | Single API for chat + embeddings; cheapest workable model, per-stage configurable. |
| XML parsing | **lxml** | Deterministic ACORD XML parsing in Extract. |
| ORM | **SQLModel** | Postgres models. |

**Deliberately excluded:** standalone LangChain chains (LangGraph already builds on LangChain;
using both high-level is redundant) and pgvector (Qdrant fills the vector role).

---

## Goals

- Map carrier ACORD/TXLife XML to a selectable distributor JSON schema via a 6-stage LangGraph pipeline.
- Score every field mapping with a hybrid confidence metric that drives a human-review gate.
- Keep the LLM advisory only: it proposes, a human approves, nothing goes live silently.
- Record every decision in an append-only audit log; trace every LLM call in Langfuse.
- Prove correctness with an eval harness (field-level precision/recall + confidence calibration; Ragas for RAG).
- Provide a React review console for the full human-in-the-loop workflow.

## Non-Goals (Future Work)

- Real authentication / login. Data model is tenant-aware (`tenant_id` columns) but no auth is built.
- Cost / rate-limit guardrails (token budget caps). Observability lands first; caps come later.
- Idempotent partial re-runs of a single stage beyond what LangGraph checkpointing gives for free.
- Distributed/queued execution. v1 runs the graph in-process via FastAPI BackgroundTasks.
- Production deployment, horizontal scaling.

---

## Architecture

### Shape

The pipeline is a **LangGraph `StateGraph`** with one node per stage, run in a fixed order. Each
node is a focused module with its own prompt (if LLM-backed), a typed input/output contract, and its
own tests. Between nodes the graph uses **`interrupt`** to pause for human review; a checkpointer
persists graph state so a run can resume after approval.

This is deliberately a controlled state machine, not a swarm of autonomous agents. In a regulated,
auditable domain the value is control and traceability — exactly what LangGraph's interrupt +
checkpoint model provides.

### Execution model

Pipeline runs are **asynchronous**: starting a run returns a run id immediately; the LangGraph
execution runs via **FastAPI `BackgroundTasks`** (in-process) until it hits the first interrupt. The
frontend **polls** run status. Resuming after a human decision re-invokes the graph from the
checkpoint. A future swap to a real job queue is possible without changing node interfaces.

### Checkpointer

LangGraph state is persisted with a **Postgres checkpointer** so runs survive process restarts and
resume cleanly after a review gate. (A memory checkpointer is used in tests.)

### Review gate granularity

**Every stage is gated** via `interrupt`. Each stage's output pauses for human approve / edit /
reject before the next node runs. The Map stage additionally exposes **per-field** review (each
low-confidence `FieldMapping`); edits are re-scored and audited.

### Determinism guardrails (the core lesson)

- Deterministic code does deterministic work: XML parsing (Extract) and transform application
  (Build/Test) are plain Python, never the LLM.
- LLM output is always **structured + validated** via PydanticAI; the LLM only **proposes**.
- Proposals persist as `awaiting_review`. Only a human review action flips state to `approved`.
- Every flip is recorded in `AuditEvent` (append-only) and traced in Langfuse.

---

## The Six Stages (LangGraph nodes)

| Stage | LLM? | Input | Responsibility | Output |
|---|---|---|---|---|
| **1. Extract** | No | ACORD XML | Deterministic XML parse (`lxml`) → flat list of raw fields (path, value, inferred type). | `ExtractedField[]` |
| **2. Read & Interpret** | Yes (PydanticAI) | `ExtractedField[]` | Describe each field's meaning + business rules/constraints using ACORD context. | `InterpretedField[]` |
| **3. Map** | Yes (PydanticAI) | `InterpretedField[]` + selected target JSON schema | Propose source→target mapping + transform logic. **Core value.** Per-field confidence + review. | `FieldMapping[]` |
| **4. Build** | No (templated) | approved `FieldMapping[]` | Generate a runnable transform: a JSON mapping config + a Python applier converting source→target. | `TransformSpec` |
| **5. Test** | Partial | `TransformSpec` + sample values | Auto-generate test cases, run the transform, validate output against target schema constraints. | `TestReport` |
| **6. Support** | Yes (LlamaIndex + Qdrant) | a completed run | RAG + tool-calling chat over the run: answer "why was field X mapped to Y?", edit a mapping in plain English (which itself goes through the gate). | chat responses |

### Confidence scoring (cross-cutting)

Every `FieldMapping` from stage 3 gets a **hybrid confidence score**:

- **Deterministic heuristics:** source/target type compatibility, name similarity, required-field
  presence, enum/format validity.
- **LLM self-rating:** PydanticAI-extracted certainty per mapping.

The blended score (default flag threshold **0.8**, configurable) decides auto-accept vs **flag for
human review**. An eval calibration report checks whether low-confidence flags actually correlate
with wrong mappings.

---

## Data Model (Postgres via SQLModel)

Vectors live in **Qdrant**, not Postgres — so there is no embedding table here.

- **PipelineRun** — id, `tenant_id`, status (`running` / `awaiting_review` / `completed` /
  `failed`), source document ref, `target_schema_id`, `prompt_version`, `target_schema_version`,
  `thread_id` (LangGraph checkpoint thread), timestamps.
- **TargetSchema** — id, name, version, JSON Schema definition. Two seeded distributor schemas in v1.
- **StageResult** — id, run_id, stage name, status (`pending` / `awaiting_review` / `approved` /
  `rejected`), payload (JSON), timestamps.
- **FieldMapping** — id, run_id, source_path, target_path, transform, confidence, flags (JSON),
  status (`proposed` / `approved` / `edited` / `rejected`).
- **AuditEvent** — append-only. id, run_id, actor (`system` / `human`), action, before/after (JSON),
  timestamp. Never updated or deleted.
- **ReviewAction** — id, run_id, stage / field_mapping_id, reviewer, decision, note, timestamp.
- **LLMCall** — local observability mirror. id, run_id, stage, model, prompt, response,
  prompt_tokens, completion_tokens, latency_ms, estimated_cost, `langfuse_trace_id`, timestamp.

All run-scoped tables carry `tenant_id`. Schema managed by **Alembic**. LangGraph checkpoints are
stored by the LangGraph Postgres checkpointer in its own tables.

---

## LLM Integration

- Gateway: **OpenRouter** (`OPENROUTER_API_KEY` in `backend/.env`, never committed).
- Structured calls go through **PydanticAI** agents typed with output models, configured to use
  OpenRouter (OpenAI-compatible endpoint). Default model: cheapest workable, configurable per stage.
- Embeddings: **OpenRouter embedding endpoint**, indexed via LlamaIndex into Qdrant.
- Every call is traced in **Langfuse** and mirrored into the `LLMCall` table (with the Langfuse
  trace id) for local audit.

---

## Retrieval / RAG (Support stage)

- **LlamaIndex** builds an index over a completed run's artifacts (interpreted fields, mappings,
  audit notes), backed by a **Qdrant** collection per run (or per tenant).
- The Support agent answers questions and proposes plain-English edits (which re-enter the review
  gate). **Ragas** evaluates retrieval/answer quality on a small Q&A golden set.

---

## Eval Harness

- Location: `backend/eval/`.
- **Map accuracy (custom):** ~10 golden documents with hand-labeled correct mappings (both target
  schemas). Reports field-level **precision / recall**, **confidence calibration**, and aggregate
  **LLM cost** (from `LLMCall` / Langfuse).
- **RAG quality (Ragas):** small Q&A set over completed runs; faithfulness / answer-relevancy /
  context-precision.
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
  sample file header; kept minimal/adapted (repo states no license). Also proves the pipeline
  generalizes beyond life.
- **Two distributor JSON target schemas** authored for this project, selectable at upload.

If genuine ACORD member files become available later, they drop in unchanged.

---

## Frontend — Review Console (React + TS + Tailwind CSS)

Routes:

- **Upload** — pick ACORD source + select one of the target schemas, start a run.
- **Run view** — stage timeline with per-stage status/output; polls while running; approve / edit /
  reject each stage (resumes the LangGraph run).
- **Field review table** — Map stage: approve / edit / reject flagged low-confidence fields.
- **Audit log** — read-only append-only event trail per run.
- **Eval dashboard** — precision/recall + calibration + Ragas scores + LLM cost.
- **Support chat** — natural-language Q&A over a completed run.

Styling via **Tailwind CSS**. Reads backend base URL from `VITE_API_URL` (existing convention).

---

## Backend Layout

```
backend/app/
  graph/         build.py            # LangGraph StateGraph assembly, state schema, interrupts
  agents/        base.py, extract.py, interpret.py, map.py, transform.py, qa.py, support.py
                 # transform.py = "Build" stage; qa.py = "Test" stage (avoid pytest collection)
  pipeline/      confidence.py
  llm/           client.py           # PydanticAI + OpenRouter + Langfuse + LLMCall logging
  rag/           index.py            # LlamaIndex + Qdrant wiring
  models/        run.py, mapping.py, audit.py, schema.py
  routers/       pipeline.py, review.py, eval.py, support.py
  schemas/       sample ACORD xml + target JSON schemas
backend/alembic/ migrations
backend/eval/    golden/, runner.py, ragas_eval.py
docker-compose.yml                   # postgres + qdrant
```

Routes registered in `backend/app/main.py` per existing convention.

---

## Implementation Milestones

Four sequential milestones; each is independently shippable and gets its own implementation plan and
feature branch.

- **M1 — Foundation + spine:** Docker (Postgres + Qdrant), SQLModel models, Alembic, PydanticAI +
  OpenRouter client with Langfuse + LLMCall logging, target schemas, Extract node, Map node, a
  **LangGraph graph** (Extract→Map with an interrupt before review) + Postgres checkpointer, run +
  pipeline API. Outcome: upload → extract → mapping proposed, run paused at interrupt.
- **M2 — Confidence + review + frontend:** hybrid confidence scoring, resume-on-approval review API
  (per-stage + per-field), audit log, React review console (Tailwind).
- **M3 — Build + Test + eval:** Build node (transform + applier), Test node (auto cases + schema
  validation), custom eval harness (golden + calibration + cost), eval dashboard.
- **M4 — Support / RAG:** Read & Interpret node, LlamaIndex + Qdrant index, Support node (RAG +
  tool-calling chat, NL edits through the gate), Ragas eval, support chat UI.

---

## Error Handling

- Malformed XML, missing required fields, or schema mismatch produce graceful, typed errors — never
  unhandled 500s.
- A failed node sets the run `failed`, records an `AuditEvent`, surfaces the reason in the run view.
- LLM failures (timeout, rate limit, invalid output) are caught by PydanticAI retry, logged to
  `LLMCall` + Langfuse, and fail the node after bounded attempts.

---

## Testing Strategy

- **Backend:** pytest. Each node module unit-tested against its I/O contract. Deterministic nodes
  (Extract, Build, Test) use fixed fixtures. LLM nodes use a **PydanticAI `TestModel` / `FunctionModel`**
  (or mock) so tests run offline/deterministically. The LangGraph graph tested with a memory
  checkpointer for sequencing + interrupt behavior. Alembic migrations applied to a test DB.
- **Frontend:** vitest + @testing-library/react. Component tests for review table, run view polling,
  upload flow.
- **Eval:** custom harness + Ragas as integration-level correctness checks.

---

## Dev Commands (additions)

| Task | Command |
|---|---|
| Start Postgres + Qdrant | `docker-compose up -d` |
| Apply migrations | `cd backend && uv run alembic upgrade head` |
| Run eval harness | `cd backend && uv run python -m eval` |
| Start backend | `cd backend && uv run fastapi dev app/main.py` (existing) |
| Start frontend | `cd frontend && npm run dev` (existing) |

---

## Environment Variables

Backend `backend/.env` (gitignored):

- `OPENROUTER_API_KEY` — OpenRouter API key (chat + embeddings).
- `DATABASE_URL` — Postgres connection string (matches docker-compose).
- `QDRANT_URL` — Qdrant endpoint (default `http://localhost:6333`).
- `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` — Langfuse (Cloud free tier or
  self-hosted). Optional in dev; tracing no-ops if unset.

Frontend `frontend/.env.local` (existing): `VITE_API_URL`.
