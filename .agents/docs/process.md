# System Architecture & Process Guide

**Audience**: New engineers onboarding to this codebase  
**Last updated**: 2026-06-09  
**Stack**: FastAPI · SQLModel · LangGraph · PydanticAI · React 19 · Qdrant

---

## Table of Contents

1. [What This System Does](#1-what-this-system-does)
2. [Industry Context: Where This Fits](#2-industry-context-where-this-fits)
3. [Architecture Overview](#3-architecture-overview)
4. [Data Model Deep Dive](#4-data-model-deep-dive)
5. [AI Agent Anatomy: Every Layer Explained](#5-ai-agent-anatomy-every-layer-explained)
6. [The LangGraph Orchestration Layer](#6-the-langgraph-orchestration-layer)
7. [End-to-End Request Flow](#7-end-to-end-request-flow)
8. [Human-in-the-Loop Review Gates](#8-human-in-the-loop-review-gates)
9. [RAG + Support Agent](#9-rag--support-agent)
10. [Confidence Scoring System](#10-confidence-scoring-system)
11. [Transform Pipeline](#11-transform-pipeline)
12. [Frontend Architecture](#12-frontend-architecture)
13. [Observability & Audit Trail](#13-observability--audit-trail)
14. [Industry Comparison: Standard vs. This System](#14-industry-comparison-standard-vs-this-system)
15. [Where to Start as a New Engineer](#15-where-to-start-as-a-new-engineer)

---

## 1. What This System Does

This system automates **document field mapping** — taking an ACORD XML insurance document (which has its own field naming conventions) and mapping its fields into a standard target JSON schema. Historically, this is done manually by data engineers who look at source fields and write transformation rules by hand. This system replaces that manual step with an LLM-driven pipeline that:

1. **Extracts** all data fields from the XML
2. **Interprets** what each field means in insurance domain terms
3. **Proposes** mappings to target schema fields with confidence scores
4. **Builds** a transformation spec from approved mappings
5. **Tests** that spec against the actual data
6. Provides a **support agent** that answers follow-up questions

A human reviewer oversees every stage. The LLM proposes; the human approves, edits, or rejects.

---

## 2. Industry Context: Where This Fits

### The Problem Domain

Insurers, banks, and healthcare systems constantly exchange data between legacy XML/EDI systems and modern JSON APIs. Field mapping — also called **schema matching** or **ETL (Extract-Transform-Load)** — is one of the most labor-intensive and error-prone tasks in data engineering. A single insurance policy has hundreds of fields with opaque names (`ACORD/InsuranceSvcRq/PersPkgPolicyRs/PersAutoLineBusiness/PersVeh/Cov/CovAmt`), and the target schema might call the same field `vehicle_coverage_premium`.

### Industry Standard Approaches

| Approach | What Companies Do | Limitations |
|---|---|---|
| **Manual ETL** | Data engineers write XSLT or Python transform scripts | Slow, expensive, requires deep domain knowledge |
| **Schema matching tools** | Tools like Informatica, MuleSoft match by name similarity | Low recall on opaque field names; no domain reasoning |
| **LLM-assisted mapping (emerging)** | GPT-4 generates mapping suggestions; engineer reviews | No orchestration, no human gate system, no audit trail |
| **This system** | LangGraph orchestrates a multi-stage LLM pipeline with full audit trail and human-in-the-loop gates | — |

### Where This Is Industry-Forward

- **Multi-stage reasoning**: Rather than one LLM call, the system separates extraction (deterministic), interpretation (domain reasoning), and mapping (structural alignment) into three discrete agent passes. This mirrors **chain-of-thought decomposition** in production AI systems.
- **Human-in-the-loop (HITL) as a first-class primitive**: Using LangGraph's `interrupt()` mechanism rather than bolting on review as an afterthought. This is how production-grade agentic systems handle trust boundaries.
- **Transform validation at two levels**: LLM suggestions normalized on input, then validated at compile time. Prevents garbage-in at the spec level.
- **Audit trail**: Every LLM call, reviewer action, and system event is logged. This is required in regulated industries (insurance, finance, health).
- **RAG-powered support**: Completed runs are indexed into a vector store, enabling a support agent to answer "why did field X get mapped to Y?" questions grounded in actual run data.

---

## 3. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        FRONTEND (React 19)                       │
│  UploadPage → RunPage (polling + review UI) → EvalPage          │
│  NavBar · FieldReviewTable · SupportChat · AuditLog             │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTP (REST)
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FASTAPI (Python 3.12)                         │
│  routers/                                                        │
│    pipeline.py  — POST /runs, GET /runs/:id                     │
│    review.py    — PATCH /fields/:id, POST /stages/:stage/…      │
│    support.py   — POST /support, POST /support/apply            │
│    health.py    — GET /health, /health/db, /health/llm          │
└───────────────┬──────────────────────┬──────────────────────────┘
                │                      │
       ┌────────▼──────────┐  ┌───────▼──────────┐
       │   LANGGRAPH        │  │   POSTGRESQL      │
       │   graph/build.py   │  │   (SQLModel)      │
       │   10-node pipeline │  │   5 tables        │
       │   with checkpoints │  │   + audit trail   │
       └────────┬──────────┘  └──────────────────┘
                │
    ┌───────────▼─────────────────────────────────┐
    │              AGENTS LAYER                    │
    │  extract.py  — XML parsing (no LLM)         │
    │  interpret.py — domain meaning (LLM)        │
    │  map.py      — schema matching (LLM)        │
    │  transform.py — spec compilation + apply    │
    │  qa.py       — schema validation (no LLM)  │
    │  support.py  — Q&A + edit proposals (LLM)  │
    └───────────┬────────────────┬────────────────┘
                │                │
    ┌───────────▼──────┐  ┌──────▼──────────────┐
    │  LLM (OpenRouter) │  │  QDRANT (vector DB) │
    │  llm/client.py   │  │  rag/index.py       │
    │  PydanticAI      │  │  LlamaIndex         │
    └──────────────────┘  └─────────────────────┘
```

### Key Directories

```
backend/app/
  agents/       # Individual AI task modules
  graph/        # LangGraph pipeline orchestration
  llm/          # LLM client abstraction
  models/       # SQLModel ORM tables
  pipeline/     # Cross-cutting concerns (confidence scoring)
  rag/          # Vector indexing + retrieval
  routers/      # FastAPI route handlers
  db.py         # Async DB engine + session factory
  config.py     # Pydantic-settings configuration

frontend/src/
  api.ts        # Typed API client
  components/   # Reusable UI components
  pages/        # Route-level page components
  main.tsx      # Router + QueryClient setup
```

---

## 4. Data Model Deep Dive

Understanding the data model is critical because the pipeline state lives entirely in the database — LangGraph reads from and writes to these tables at every node.

### Entity Relationship

```
TargetSchema (1) ──────── (N) PipelineRun
                                    │
                          ┌─────────┼─────────────┐
                          │         │             │
                     (N) StageResult  (N) FieldMapping  (N) AuditEvent
                                                   │
                                            (N) ReviewAction
                                            (N) LLMCall
```

### TargetSchema

Stores the JSON Schema definition for the target format. Seeded at app startup from a fixture file. Multiple schemas can coexist; the user picks one when uploading.

```python
class TargetSchema(SQLModel, table=True):
    id: int
    name: str          # e.g. "ACORD Auto Policy v2"
    version: str       # e.g. "2.1"
    definition: dict   # Full JSON Schema (stored as JSONB in Postgres)
```

### PipelineRun

One record per document upload. Acts as the top-level state container.

```
Status lifecycle:
  running → awaiting_review → running → awaiting_review → ... → completed
                                                                └─ failed
```

The `thread_id` field links this run to its LangGraph checkpoint. When `resume_run()` is called, it uses `thread_id` as the config to resume the correct graph execution.

### StageResult

One record per pipeline stage per run. There are five stages: `extract`, `interpret`, `map`, `build`, `test`.

```
Status lifecycle:
  pending → awaiting_review → approved
                            └─ rejected
```

The `payload` JSONB column stores stage-specific data:
- `extract`: extracted field count
- `map`: mapping count  
- `build`: the compiled `TransformSpec` (reloaded by test_node)
- `test`: the `TestReport` (per-record pass/fail)

A special synthetic stage `support_review` is created when the support agent proposes edits that need human approval.

### FieldMapping

The core output of the map stage. One per proposed source→target field pair.

```
Status lifecycle:
  proposed → approved (no changes)
           → edited   (reviewer modified target_path or transform)
           → rejected (reviewer excluded this mapping)
```

Key fields:
- `source_path`: Dotted XPath from extracted XML (e.g. `ACORD.InsuranceSvcRq.PersAutoPolicyQuoteInqRq.PersPolicy.PolicyNumber`)
- `target_path`: Dotted JSON path in target schema (e.g. `policy.number`)
- `transform`: Optional transform name from `_TRANSFORMS` registry (e.g. `"to_number"`, `"uppercase"`)
- `confidence`: Float `[0, 1]` — composite score from heuristics + LLM self-report
- `flags`: Array of quality flags — `type_mismatch`, `required_missing`, `enum_violation`

### AuditEvent, ReviewAction, LLMCall

These form the audit trail. Every significant action writes to one or more of these tables:

- **AuditEvent**: System + human actions. `actor` is `"system"`, `"reviewer"`, or `"support_agent"`. `action` is one of: `extract_completed`, `interpret_completed`, `map_completed`, `build_completed`, `test_completed`, `field_edited`, `map_approved`, `map_rejected`, `run_failed`, `run_completed`.
- **ReviewAction**: Finer-grained reviewer actions. Records `stage`, `action` (`approve`/`reject`/`edit`/`propose`), `field_id` (for field-level actions), and `notes`.
- **LLMCall**: Complete trace of every LLM call. Stores `prompt`, `response`, `model`, `input_tokens`, `output_tokens`, `cost_usd`, `latency_ms`, `langfuse_trace_id`. Essential for cost tracking and debugging.

---

## 5. AI Agent Anatomy: Every Layer Explained

An "AI agent" in this system means a Python module that wraps an LLM call with structured input/output contracts, error handling, and side effects (DB writes, audit logs). Here is every layer from bottom to top:

### Layer 1 — The LLM Provider (`llm/client.py`)

The lowest layer. Abstracts away which model is being called.

```python
# Resolves which backend to use
def _model(mode: str) -> Model:
    if mode == "test":
        return TestModel()          # Deterministic, no API calls — used in tests
    return OpenAIModel(             # OpenRouter endpoint (supports GPT-4o, Claude, etc.)
        model_name=settings.openrouter_model,
        base_url="https://openrouter.ai/api/v1",
        api_key=settings.openrouter_api_key,
    )
```

**Why OpenRouter?** It provides a unified OpenAI-compatible API surface for multiple model providers (Anthropic, OpenAI, Meta, Mistral). You can switch models by changing one config value without touching agent code.

**Why TestModel?** Unit tests should be fast, free, and deterministic. `TestModel` returns synthetic structured output that satisfies the Pydantic schema without touching the network.

### Layer 2 — The Structured Agent Builder

```python
def build_agent(output_type: type, system_prompt: str, mode: str) -> Agent:
    return Agent(
        model=_model(mode),
        output_type=output_type,   # Pydantic model — LLM must return valid JSON
        system_prompt=system_prompt,
    )
```

`output_type` is a Pydantic model. PydanticAI automatically:
1. Generates a JSON schema from the Pydantic model
2. Injects that schema into the LLM prompt as a response format constraint
3. Parses and validates the LLM's JSON response
4. Retries on parse failure (up to 3 times)

This is **structured output** — instead of raw text, the LLM returns a guaranteed-valid Python object.

### Layer 3 — The Master Wrapper (`run_structured`)

Every LLM call in this system goes through `run_structured()`. It:

1. Runs the agent with optional `deps` injection
2. Measures wall-clock latency
3. Extracts token counts from the usage object
4. Estimates USD cost (lookup table keyed by model name)
5. Emits a Langfuse trace for observability
6. Persists a `LLMCall` record to the database

This ensures every LLM interaction is traced, costed, and auditable — a requirement in regulated industries.

### Layer 4 — The Task Agents

Each agent in `agents/` is one LLM task:

#### `extract.py` — Deterministic Extraction (No LLM)

```python
def extract(xml_str: str) -> list[ExtractedField]:
```

Walks the XML DOM with `lxml`. Collects all leaf nodes (nodes with text content and no child elements). For each leaf: records its full XPath as `source_path`, its text value, and an inferred type:
- Matches `_DATE_RE` → `"date"`
- Matches `_NUM_RE` → `"number"`  
- Otherwise → `"string"`

**Why no LLM here?** Extraction is deterministic. The XML structure is authoritative. LLMs would add latency, cost, and non-determinism to a step that has a correct algorithmic answer.

#### `interpret.py` — Domain Interpretation (LLM)

```python
async def interpret_fields(
    fields: list[ExtractedField],
    run_id: int,
    session: AsyncSession,
) -> list[InterpretedField]:
```

Single LLM call per run. All extracted fields are sent in one prompt. The LLM enriches each field with:
- `semantic_label`: Human-readable name (e.g. `"Policy Number"`)
- `meaning`: Full sentence explaining what this field represents in insurance terms
- `rules`: Business constraints (e.g. `["Must be unique per policy period", "Alphanumeric, max 20 chars"]`)

**Why single call?** Batching all fields reduces latency (one round-trip instead of N), reduces cost, and allows the model to see cross-field context (field B might inform the meaning of field A).

#### `map.py` — Schema Matching (LLM)

```python
async def propose_mappings(
    fields: list[ExtractedField],
    target_schema: dict,
    interpreted: list[InterpretedField] | None = None,
) -> list[FieldMappingProposal]:
```

The LLM receives:
- All source fields (paths + values + inferred types)
- Optional interpretations (semantic labels + meanings)
- The full target JSON Schema definition

It returns proposals: `{source_path, target_path, transform, confidence}`.

**Important**: The LLM may suggest transform names that don't exist in the registry (e.g. `"to_boolean"` or `"date_format"`). The `map_node` in the graph normalizes unknown transform names to `None` before saving. This prevents `TransformError` at build time. This is the **transform validation at ingestion** pattern.

#### `transform.py` — Spec Compilation + Application

This module is **not** an LLM agent — it is a pure Python transform engine.

```
_TRANSFORMS registry:
  "to_number"    → float/int coercion
  "to_date_iso"  → ISO 8601 passthrough
  "uppercase"    → str.upper()
  "lowercase"    → str.lower()
  "trim"         → str.strip()
```

`build_transform(mappings)` compiles approved mappings into a `TransformSpec` (list of `{source_path, target_path, transform}`). Validates all transform names against `_TRANSFORMS`. Raises `TransformError` on unknown names.

`apply_transform(spec, source_dict)` applies a compiled spec to a record. Handles:
- Missing source keys (silent skip — source XML may not have every field)
- Optional transforms (passthrough if `None`)
- Dotted target paths → nested dict creation

#### `qa.py` — QA Testing (No LLM)

```python
def run_qa_checks(
    spec: TransformSpec,
    target_schema: dict,
    samples: list[dict],
) -> TestReport:
```

Applies the compiled transform spec to each sample, then validates the output against the JSON Schema. Also checks that required fields have non-empty values (JSON Schema `required` only checks presence, not content). Auto-generates edge-case samples (all-empty values) if fewer than 3 samples provided. Returns a `TestReport` with per-case pass/fail detail.

#### `support.py` — RAG + Tool-Use Agent (LLM)

The most complex agent. Combines retrieval-augmented generation (RAG) with tool use.

```python
async def answer_question(
    run_id: int,
    question: str,
    session: AsyncSession,
    retriever,          # Qdrant retriever for this run
    ...
) -> SupportAnswer:
```

Steps:
1. RAG retrieval: fetch top-3 documents from Qdrant's `run_{id}` collection (indexed at run completion)
2. Build PydanticAI agent with `lookup_mapping` tool (queries DB for live field details)
3. LLM reasons over retrieved context + can call `lookup_mapping` to fetch specific field data
4. Returns `SupportAnswer` with `answer` text and zero or more `EditIntent` proposals

`EditIntent` is a proposed field remap: run_id, field_id, new_target_path, optional new_transform, and a reason string. It is **not applied automatically** — it is queued as a `StageResult(stage="support_review")` and shown to the reviewer for approve/reject.

---

## 6. The LangGraph Orchestration Layer

LangGraph is the **state machine runtime** for this pipeline. It handles:
- Defining the execution graph (nodes + edges)
- Persisting state at checkpoints (survives process restarts)
- Human-in-the-loop interrupts (pause execution, wait for external signal)
- Resuming from any checkpoint with a command

### What Is LangGraph?

Think of LangGraph as a workflow engine like Airflow or Temporal, but designed specifically for LLM pipelines. The key difference: LangGraph supports **interrupts** — the graph can pause mid-execution and wait for a human signal before continuing. This is fundamentally different from batch workflows that run to completion.

**Industry comparison:**
| Tool | Best For | Interrupts? |
|---|---|---|
| Airflow | Batch ETL, data pipelines | No |
| Temporal | Long-running business workflows | Limited (via signals) |
| LangGraph | LLM pipelines with human-in-the-loop | Yes, first-class |
| Prefect | Data pipelines with observability | No |

### The 10-Node Pipeline

```
START
  │
  ▼
[extract_node]          — Deterministic XML parsing
  │
  ▼
[extract_interrupt_node] — PAUSE: human reviews extracted fields
  │  (resume with approve/reject)
  ▼
[interpret_node]        — LLM domain interpretation
  │
  ▼
[interpret_interrupt_node] — PAUSE: human reviews interpretations
  │  (resume with approve/reject)
  ▼
[map_node]              — LLM schema matching + confidence scoring
  │
  ▼
[review_interrupt_node] — PAUSE: human reviews + edits field mappings
  │  (resume with approve/reject)
  ▼
[build_node]            — Compile TransformSpec from approved mappings
  │
  ▼
[test_node]             — QA validation of compiled spec
  │
  ▼
[test_interrupt_node]   — PAUSE: human reviews test results
  │  (resume with approve/reject)
  ▼
END
```

### PipelineState

The shared data bag passed between nodes:

```python
class PipelineState(TypedDict):
    run_id: int
    source_xml: str
    target_schema: dict
    extracted: list[dict]    # Grows at extract_node
    interpreted: list[dict]  # Grows at interpret_node
    mappings: list[dict]     # Grows at map_node
```

Each node reads from state and returns a partial state update. LangGraph merges the updates.

### How Checkpointing Works

Every node execution writes a checkpoint to the database (using `AsyncPostgresSaver` in production, `MemorySaver` in tests). The checkpoint contains:
- The full `PipelineState` at that point
- The execution cursor (which node just ran, which is next)

When `resume_run()` is called, it loads the checkpoint for `thread_id`, replays to the interrupted node, applies the resume command, and continues.

```python
# Starting a run
config = {"configurable": {"thread_id": str(run.thread_id)}}
graph.invoke(initial_state, config)

# Resuming after human approval
graph.invoke(Command(resume={"decision": "approve"}), config)
```

This is why **process restarts don't lose work** — the full pipeline state is in Postgres.

### Session Factory Pattern

Each node opens its own `AsyncSession` to avoid sharing a session across async boundaries:

```python
async def _session_factory_from(session: AsyncSession):
    async with session.bind.connect() as conn:
        async with AsyncSession(conn) as s:
            yield s
```

`build_pipeline()` takes a `session_factory: Callable` parameter. Each node does `async with session_factory() as session:`. This prevents SQLAlchemy "session used across different tasks" errors that occur when an async session is shared between LangGraph nodes.

---

## 7. End-to-End Request Flow

### Step 1: Upload

```
User selects XML file + target schema
→ POST /api/runs  (multipart/form-data)
→ pipeline.py: create_run()
  → PipelineRun created in DB (status="running")
  → start_run() called
    → build_pipeline() returns compiled LangGraph app
    → graph.invoke(initial_state, config)
    → extract_node runs: lxml parses XML, writes StageResult(status="awaiting_review")
    → extract_interrupt_node runs: interrupt() raises NodeInterrupt
    → NodeInterrupt caught by start_run(), run status set to "awaiting_review"
← Response: {run_id: 42, status: "awaiting_review"}
```

### Step 2: Frontend Polls

```
RunPage mounts, starts polling GET /api/runs/42 every 2s
→ Returns run record + stage_results + mappings + audit
→ UI shows: Stage "extract" is awaiting_review
→ Approve/Reject buttons appear
```

### Step 3: Reviewer Approves Extract

```
User clicks "Approve"
→ POST /api/runs/42/stages/extract/approve
→ review.py: approve_stage()
  → resume_run(run_id=42, stage="extract", decision="approve")
    → Loads checkpoint, resumes graph with Command(resume={"decision": "approve"})
    → interpret_node runs: LLM call, writes StageResult
    → interpret_interrupt_node: interrupt() → NodeInterrupt
← Response 200 OK
```

### Step 4: Map Stage (the big one)

After interpret is approved, map_node runs:

```
map_node:
  → propose_mappings() called with all fields + target schema (LLM call)
  → For each proposal:
      → score_mapping() computes composite confidence
      → transform name validated against _TRANSFORMS, unknown → None
      → FieldMapping written to DB (status="proposed")
  → StageResult written
  → review_interrupt_node: pause
```

Now the reviewer can edit individual field mappings via `PATCH /api/runs/42/fields/{field_id}` before approving. The `FieldReviewTable` component shows all mappings, highlights low-confidence ones in red.

### Step 5: Build + Test

After map approval, resume_run promotes all still-"proposed" mappings to "approved":

```
resume_run() for map stage:
  → All mappings with status="proposed" → UPDATE status="approved"
  → Resume graph

build_node:
  → run_build(): reads approved/edited mappings (not rejected)
  → build_transform(): compiles TransformSpec
  → Writes TransformSpec to StageResult(stage="build").payload

test_node:
  → Re-extracts source XML (the actual data)
  → Loads TransformSpec from build StageResult
  → run_qa_checks(): applies spec to data, validates against JSON Schema
  → Writes TestReport to StageResult(stage="test").payload
```

### Step 6: Completion + Indexing

After test approval:

```
Graph reaches END
→ run.status = "completed"
→ _index_completed_run():
    → Reads all FieldMapping rows for this run
    → Converts each to a text document: "source_path → target_path (confidence: 0.92, transform: uppercase, status: approved)"
    → LlamaIndex indexes all docs into Qdrant collection "run_42"
```

---

## 8. Human-in-the-Loop Review Gates

### Why HITL?

LLMs make mistakes. In document mapping for regulated industries, an incorrect field mapping (e.g. mapping `premium_annual` to `coverage_limit`) can have financial or legal consequences. Human review at each stage ensures:
1. Extraction is correct before spending LLM tokens on interpretation
2. Interpretations are sensible before running schema matching
3. Mappings are correct before compiling a transform spec
4. Tests pass before the run is marked complete

### The Four Gates

| Gate | Stage | What Reviewer Sees | Can Edit? |
|---|---|---|---|
| Extract | `extract_interrupt` | List of extracted fields + inferred types | No — fixed from XML |
| Interpret | `interpret_interrupt` | Semantic labels + meanings for each field | No (display only) |
| Map | `review_interrupt` | All proposed mappings with confidence + flags | Yes — target_path + transform |
| Test | `test_interrupt` | Test report: per-record pass/fail | No |

### Map Gate Editing

The map gate is the most important. The reviewer can:
- Edit `target_path`: change where a source field maps to
- Edit `transform`: apply a transformation (e.g. `"uppercase"` for a code field)
- Reject individual mappings: excluded from the build spec

When editing, the frontend calls `PATCH /api/runs/{id}/fields/{field_id}`, which:
1. Updates the field in the DB
2. Recalculates confidence score and flags against the new target path
3. Sets `status = "edited"`
4. Invalidates the React Query cache so the UI refreshes

### Approve vs. Reject

- **Approve**: graph resumes, pipeline continues to next stage
- **Reject**: `resume_run` is called with `decision="reject"`. Currently the pipeline marks the run stage as rejected. Extension point: could restart the stage with the rejection as feedback (not yet implemented).

### Support Review Gate (Special)

The `support_review` gate is not part of the main pipeline graph. It is created on-demand when the support agent proposes field edits. It uses the same approve/reject mechanism but with different logic:
- **Approve**: applies the `EditIntent` directly (updates the FieldMapping record) without graph resume
- **Reject**: discards the `EditIntent` without touching any mapping

---

## 9. RAG + Support Agent

RAG = Retrieval-Augmented Generation. The support agent uses it to answer questions about a completed run grounded in actual run data.

### Why RAG Here?

The support agent needs to answer questions like "Why was PolicyNumber mapped to policy.number instead of policy.id?" The answer depends on run-specific data (the actual mapping, its confidence score, any edits the reviewer made). This data cannot be baked into the system prompt — it changes per run.

RAG solves this by:
1. Indexing the run's mapping data as text documents in Qdrant (at run completion)
2. At query time, embedding the question, searching Qdrant for similar documents, injecting the top-3 results as context

### Indexing (`rag/index.py`)

```python
# At run completion, _index_completed_run() calls:
await index_run(run_id, docs, client, embed_model)
```

Each document is a text string:
```
"source: ACORD.Policy.PolicyNumber → target: policy.number
 confidence: 0.94 | transform: None | status: approved"
```

These are embedded (converted to 384-dim or 1536-dim vectors) and stored in Qdrant collection `run_{id}`.

**Embedding model selection** (priority order):
1. Explicit override
2. OpenAI embeddings via OpenRouter (cloud, 1536-dim, requires API key)
3. FastEmbed local model (no API key, 384-dim, runs on CPU)

### Query Flow

```
User asks: "Why is premium mapped to coverage_amount?"
→ Embed the question (same model used for indexing)
→ Qdrant similarity search in collection "run_42": top-3 docs
→ Inject docs as context into LLM prompt
→ LLM also has access to lookup_mapping tool for live DB queries
→ LLM produces answer + optional EditIntent proposals
```

### Tool Use

The support agent has a `lookup_mapping` tool:

```python
@agent.tool
async def lookup_mapping(ctx: RunContext[_Deps], field_id: int) -> dict:
    # DB query: fetch FieldMapping by ID
    # Returns: source_path, target_path, transform, confidence, status
```

PydanticAI handles the tool call cycle automatically:
1. LLM decides to call `lookup_mapping` with `field_id=7`
2. PydanticAI executes the tool
3. Result injected back into the conversation
4. LLM continues reasoning

This allows the agent to fetch real-time data (not just indexed snapshots) when answering questions.

---

## 10. Confidence Scoring System

Every field mapping gets a composite confidence score `[0, 1]`.

### Why Composite?

The LLM reports its own confidence, but LLM self-reported confidence is poorly calibrated (models are often overconfident). Combining with heuristics that can be objectively computed creates a more reliable signal.

### Formula

```
heuristic_score = (type_score×2 + name_score + required_score + enum_score) / 5
final_score = 0.5 × heuristic_score + 0.5 × llm_confidence
```

### Component Scores

| Component | Weight | What It Measures |
|---|---|---|
| `type_score` | 2× | Can the source value parse as the target type? (number field → try float()) |
| `name_score` | 1× | Token overlap + character similarity of source vs. target path segments |
| `required_score` | 1× | Is the target required but the source value empty? (penalty) |
| `enum_score` | 1× | If target has enum constraint, is source value in the allowed set? |

### Flags

Score computation also generates quality flags:
- `type_mismatch`: type_score < 0.5
- `required_missing`: target is required, source value is empty
- `enum_violation`: target has enum, source value not in set

These flags drive the red row highlighting in `FieldReviewTable` — any row with flags or confidence < 0.8 is highlighted red to draw reviewer attention.

---

## 11. Transform Pipeline

The transform pipeline converts source field values to target field values during the build and test stages.

### Transform Registry (`_TRANSFORMS`)

```python
_TRANSFORMS = {
    "to_number":   lambda v: float(v) if "." in str(v) else int(v),
    "to_date_iso": lambda v: str(v),   # passthrough — assumes pre-formatted
    "uppercase":   lambda v: str(v).upper(),
    "lowercase":   lambda v: str(v).lower(),
    "trim":        lambda v: str(v).strip(),
}
```

This is the **single source of truth** for valid transform names. Any transform name that appears in the codebase must be a key in this dict.

### Two-Level Validation

**Level 1 — At ingestion (map_node):**
When the LLM proposes a mapping with `transform="to_boolean"` (not in registry):
```python
if transform not in _TRANSFORMS:
    transform = None  # normalize, don't reject the mapping
```

**Level 2 — At compile time (build_transform):**
```python
if transform and transform not in _TRANSFORMS:
    raise TransformError(f"Unknown transform: {transform}")
```

Level 1 is defensive (LLM output is untrusted). Level 2 is a hard error (should never happen if Level 1 is working correctly — but defends against direct DB edits).

### Dotted Path Target Expansion

`apply_transform` expands dotted target paths into nested dicts:

```python
# source_dict = {"ACORD.Policy.PolicyNumber": "POL-001"}
# target_path = "policy.number"
# Result:
{"policy": {"number": "POL-001"}}
```

This is how the flat source XML maps into the nested target JSON Schema.

---

## 12. Frontend Architecture

### Technology Choices

| Choice | Why |
|---|---|
| React 19 | Latest concurrent features, stable async transitions |
| Vite 8 | Fast HMR, native ESM, no Webpack overhead |
| TanStack Query v5 | Server-state management with polling, cache invalidation, mutation tracking |
| Tailwind CSS 4 | Zero-runtime utility classes, no CSS-in-JS overhead |
| React Router 7 | Declarative routing with type-safe params |
| TypeScript 6 | Type safety across API contract + component props |

### API Client (`api.ts`)

Central typed API client. All components use typed wrappers:

```typescript
export async function getRun(runId: number): Promise<RunDetail>
export async function approveStage(runId: number, stage: string): Promise<void>
export async function editFieldMapping(runId: number, fieldId: number, patch: FieldMappingPatch): Promise<FieldMapping>
```

The base URL is `VITE_API_URL` from `.env.local` (defaults to `http://localhost:8001`). This allows environment-specific backend targeting without code changes.

### React Query Patterns

**Polling**: RunPage polls while status is `"running"`:

```typescript
useQuery({
  queryFn: () => getRun(runId),
  refetchInterval: (query) => 
    query.state.data?.run.status === "running" ? 2000 : false
})
```

**Optimistic invalidation**: After mutation success, invalidate the relevant query key to force a fresh fetch:

```typescript
onSuccess: () => qc.invalidateQueries({ queryKey: ['run', runId] })
```

**Error display**: Mutations expose `isError` and `error` — displayed inline near the relevant action.

### Component Responsibilities

| Component | Responsibility |
|---|---|
| `NavBar` | Navigation links, active-link highlighting |
| `FieldReviewTable` | Mapping table with inline edit, confidence highlighting |
| `SupportChat` | Chat interface, message history, proposed edit actions |
| `AuditLog` | Read-only chronological event list |
| `RunPage` | Page orchestration — polling, approve/reject mutations, section assembly |
| `UploadPage` | Form handling, schema selection, file input |
| `EvalPage` | Eval report display (offline, no polling) |

---

## 13. Observability & Audit Trail

### What Gets Logged

| Event | Table | Actor |
|---|---|---|
| Every LLM call | `LLMCall` | system |
| Stage completion | `AuditEvent` | system |
| Field edit | `AuditEvent` + `ReviewAction` | reviewer |
| Stage approve/reject | `AuditEvent` + `ReviewAction` | reviewer |
| Run completion | `AuditEvent` | system |
| Support answer | `AuditEvent` | support_agent |

### Langfuse Integration (Optional)

If `langfuse_public_key` + `langfuse_secret_key` are set in config, every LLM call emits a trace to Langfuse (LLM observability platform). The `langfuse_trace_id` is stored in `LLMCall` so you can correlate a DB record with its Langfuse trace.

### Cost Tracking

`_COST_PER_1K` in `llm/client.py` maps model names to per-1K-token prices:

```python
_COST_PER_1K = {
    "gpt-4o": 0.005,
    "gpt-4o-mini": 0.00015,
    "claude-3-haiku-20240307": 0.00025,
    "claude-3-sonnet-20240229": 0.003,
}
```

Cost is estimated per call and stored in `LLMCall.cost_usd`. The eval dashboard aggregates `total_cost` across a run for reporting.

---

## 14. Industry Comparison: Standard vs. This System

### Standard Industry Pattern (What Most Companies Do)

```
XML file
  → Manual inspection by data engineer
  → Write XSLT or Python mapping script
  → Test manually
  → Deploy mapping script
  → No audit trail
  → When source schema changes: repeat manually
```

Timeline: days to weeks per schema. No traceability. No confidence scoring.

### This System vs. Industry Standard

| Dimension | Industry Standard | This System |
|---|---|---|
| **Mapping generation** | Manual, days/weeks | LLM-proposed, minutes |
| **Human oversight** | Full (engineer writes everything) | Partial (human reviews LLM proposals) |
| **Audit trail** | Typically none | First-class: every action logged |
| **Confidence scoring** | None | Composite heuristic + LLM score |
| **Process restarts** | Manual re-run | Automatic checkpoint resume |
| **Domain knowledge** | Engineer must know ACORD spec | LLM interprets during interpretation stage |
| **Transform validation** | At runtime (fails in prod) | At compile time + at ingestion |
| **Q&A on mappings** | Ask the engineer | RAG support agent |
| **Test automation** | Manual | JSON Schema + QA checks automated |
| **Cost tracking** | None | Per-call USD estimate + Langfuse |

### Where Industry Is Heading

This system represents the **emerging standard** for LLM-assisted data engineering:

1. **Agentic pipelines over monolithic LLM calls**: Instead of one giant prompt, decompose into discrete agents with clear responsibilities. Better debuggability, composability, and ability to substitute components.

2. **Human-in-the-loop as architecture**: Not as an afterthought but as a first-class graph primitive. LangGraph's `interrupt()` is how production AI systems handle trust boundaries.

3. **Structured output everywhere**: LLMs return Pydantic models, not raw text. Validation at the framework level (PydanticAI) rather than custom parsing logic.

4. **RAG + tool use for grounded Q&A**: Support agents that can retrieve context AND query live data are more reliable than agents relying purely on context window.

5. **Audit trails for regulated industries**: In insurance, finance, healthcare — every AI-assisted decision needs to be traceable. This system's audit model (AuditEvent + ReviewAction + LLMCall) is a template for compliance-ready AI pipelines.

---

## 15. Where to Start as a New Engineer

### Understanding Flow (Read in This Order)

1. **`backend/app/config.py`** — understand all configuration levers
2. **`backend/app/models/`** — understand the data model before any logic
3. **`backend/app/agents/extract.py`** — simplest agent, no LLM
4. **`backend/app/llm/client.py`** — understand how LLM calls work
5. **`backend/app/agents/interpret.py`** — first real LLM agent
6. **`backend/app/agents/map.py`** — the core mapping agent
7. **`backend/app/pipeline/confidence.py`** — understand scoring
8. **`backend/app/agents/transform.py`** — understand the transform registry
9. **`backend/app/graph/build.py`** — how everything is orchestrated
10. **`backend/app/routers/pipeline.py`** + **`review.py`** — API surface

### Running Locally

```bash
# Backend
cd backend
uv sync
uv run fastapi dev app/main.py   # starts on :8000

# Frontend  
cd frontend
npm install
npm run dev                       # starts on :5173

# Tests
cd backend && uv run pytest       # 72 tests
cd frontend && npm test           # 15 tests
```

Required services (Docker recommended):
- PostgreSQL on port 5433
- Qdrant on port 6433

### Key Environment Variables

```bash
# backend/.env
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5433/learningproject
OPENROUTER_API_KEY=sk-or-...
OPENROUTER_MODEL=gpt-4o-mini
QDRANT_URL=http://localhost:6433
LLM_MODE=real              # or "test" for deterministic testing
CONFIDENCE_THRESHOLD=0.8   # below this → red highlight in UI

# frontend/.env.local
VITE_API_URL=http://localhost:8000
```

### Common Debugging Paths

| Symptom | Where to Look |
|---|---|
| Run stuck in "running" | LangGraph checkpoint in Postgres — check `thread_id` in PipelineRun; check for NodeInterrupt being swallowed |
| Bad mapping proposals | `agents/map.py` system prompt + target schema definition |
| TransformError at build time | Check for unknown transform names in FieldMapping rows; `_TRANSFORMS` registry in `transform.py` |
| Low confidence scores | `pipeline/confidence.py` — examine which sub-score is low |
| LLM call failing | `llm/client.py` — check `LLMCall` table for error detail; check `OPENROUTER_API_KEY` |
| Support agent giving wrong answers | `rag/index.py` — check if `_index_completed_run` ran; check Qdrant collection `run_{id}` |
| Test failing in CI but passing locally | `LLM_MODE=test` in CI, `TestModel` returns synthetic data — check test fixtures |

### Extension Points

| Want to add... | Where to change |
|---|---|
| New transform type | Add to `_TRANSFORMS` dict in `transform.py` |
| New pipeline stage | Add node to graph in `build.py`, add `StageResult` insert |
| New target schema | Insert row into `TargetSchema` table |
| New LLM model | Update `_COST_PER_1K` in `llm/client.py`, set `OPENROUTER_MODEL` |
| New quality flag | Add to `score_mapping()` in `confidence.py`, add to `FieldMapping.flags` |
| New API endpoint | Add to appropriate router in `routers/`, register in `main.py` |
