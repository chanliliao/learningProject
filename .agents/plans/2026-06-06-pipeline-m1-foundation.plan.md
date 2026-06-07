# Plan: Pipeline — Milestone 1 (Foundation + Extract→Map Spine)

> **For implementers:** Execute tasks in order. Each task uses TDD: write failing test → run it (see it fail) → implement → run it (see it pass) → commit. Steps use checkbox (`- [ ]`) syntax. Reference spec: `.agents/specs/2026-06-06-pipeline-design.md`.

## Summary

Build the backend foundation and the deterministic-to-LLM spine of the schema mapping pipeline using
the 2026 industry stack: Dockerized **Postgres + Qdrant**, SQLModel models under **Alembic**, a
**PydanticAI + OpenRouter** LLM client traced by **Langfuse** and mirrored to a local `LLMCall`
table, two seeded distributor target schemas, the deterministic **Extract** node (ACORD XML →
fields), the LLM-backed **Map** node (fields → proposed mappings), and a **LangGraph `StateGraph`**
that runs Extract→Map with a human-review **interrupt** and a Postgres checkpointer, exposed through
a pipeline API. No review-resume API, confidence scoring, or RAG yet (later milestones). Outcome:
upload an ACORD XML, pick a target schema, and get persisted proposed field mappings with the run
paused at the review interrupt.

## User Story

As an integration engineer
I want to upload a carrier ACORD XML and select a distributor target schema and have the system
extract fields and propose a mapping, pausing for my review
So that I can see a machine-proposed source→target mapping persisted and awaiting approval.

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | HIGH |
| Milestone | M1 of 4 |
| Systems Affected | backend (FastAPI, Postgres, Qdrant, LangGraph, PydanticAI, Langfuse, Alembic) |
| Jira Issue | N/A |

---

## Prerequisites (delivered by M0)

M1 builds on the **M0 walking skeleton**. These already exist and are verified — do **not** recreate:

- `docker-compose.yml` (Postgres + Qdrant) — running.
- `backend/app/config.py` (`Settings` incl. `database_url`, `openrouter_*`, `qdrant_url`,
  `langfuse_*`, `llm_mode`, `confidence_threshold`) and `backend/.env.example`.
- `backend/app/db.py` with `get_engine()` (+ `ping_db()`); M1 adds `get_session()`.
- `backend/app/llm/client.py` minimal PydanticAI client (`_model`, `ping_llm`); M1 extends it with
  `build_agent` + `run_structured` (+ LLMCall logging, Langfuse).
- Base deps: `pydantic-settings`, `psycopg[binary]`, `sqlalchemy`, `qdrant-client`,
  `pydantic-ai-slim[openai]`, `langfuse`. M1 adds the rest below.
- CORS + `/health*` endpoints; Tailwind frontend status dashboard.

---

## Patterns to Follow

### Backend route + handler
```python
# SOURCE: backend/app/main.py:1-8
from fastapi import FastAPI

app = FastAPI(title="learningProject API")

@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
```
Routes live in `backend/app/routers/` and are included into `app` in `main.py` (per CLAUDE.md).

### Backend test style
```python
# SOURCE: backend/tests/test_health.py:1-10
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```
pytest config (`backend/pyproject.toml:17-20`): `testpaths=["tests"]`, `pythonpath=["."]`,
`asyncio_mode="auto"`. Runtime deps in `[project].dependencies`, test deps in `[dependency-groups].dev`.

---

## Conventions for this milestone

- **Stage nodes** live in `backend/app/agents/`; the **graph** that wires them lives in
  `backend/app/graph/build.py`. Each node is a pure-ish function `node(state) -> partial_state`.
- **LLM never writes final state.** Map produces `FieldMapping` rows with status `proposed`; the
  graph then hits `interrupt` and the run rests at `awaiting_review`.
- **Every LLM call** goes through `app/llm/client.py` (PydanticAI), is traced in Langfuse, and is
  mirrored as an `LLMCall` row.
- **Tests run offline.** LLM nodes use PydanticAI's `TestModel`/`FunctionModel`; the graph uses a
  `MemorySaver` checkpointer; the DB is in-memory SQLite. No network in tests. Langfuse no-ops when
  keys are unset.
- **M1 DB note:** no pgvector/Qdrant rows are written in M1 (RAG is M4). Qdrant runs in compose for
  completeness; its client is added in M4. SQLite (**`sqlite+aiosqlite://`**, async) is valid for all
  M1 tests.

### Async conventions (govern every M1 task — per spec)

- All node functions, the graph runner, and route handlers are **`async def`**.
- DB access is awaited: `await session.exec(select(...))`, `await session.commit()`, using
  `AsyncSession`. Model snippets in Story 2 that show sync `create_engine` are illustrative — in the
  actual tests use `create_async_engine("sqlite+aiosqlite://")` + `await conn.run_sync(metadata.create_all)`.
- LLM calls use `await run_structured(...)` (Story 3) — never `run_sync`.
- The LangGraph graph is invoked with `await graph.ainvoke(...)` and compiled with an **async
  checkpointer**: `AsyncPostgresSaver` in app, `MemorySaver` in tests. `start_run` is `async`.
- Tests for async code use `@pytest.mark.asyncio` (asyncio_mode="auto" is set); API tests may use
  FastAPI `TestClient` (it drives async endpoints) or `httpx.AsyncClient`.
- Add dev deps `aiosqlite` (+ `pytest-asyncio`, already present).

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `docker-compose.yml` | CREATE | Postgres + Qdrant services |
| `backend/pyproject.toml` | UPDATE | Add langgraph, checkpoint-postgres, pydantic-ai, langfuse, sqlmodel, psycopg, alembic, lxml, pydantic-settings |
| `backend/.env.example` | CREATE | OPENROUTER_API_KEY, DATABASE_URL, QDRANT_URL, LANGFUSE_* |
| `backend/app/config.py` | CREATE | Settings from env |
| `backend/app/db.py` | CREATE | Engine + session dependency |
| `backend/app/models/*` | CREATE | schema, run, mapping, audit models |
| `backend/alembic.ini`, `backend/alembic/` | CREATE | Migrations |
| `backend/app/llm/client.py` | CREATE | PydanticAI client + Langfuse + LLMCall logging + test model |
| `backend/app/schemas/*` | CREATE | Sample ACORD XML + 2 target JSON schemas |
| `backend/app/seed.py` | CREATE | Seed target schemas |
| `backend/app/agents/base.py` | CREATE | Typed I/O models + errors |
| `backend/app/agents/extract.py` | CREATE | Deterministic XML extraction |
| `backend/app/agents/map.py` | CREATE | PydanticAI mapping proposal |
| `backend/app/graph/build.py` | CREATE | LangGraph StateGraph + interrupt + checkpointer |
| `backend/app/routers/pipeline.py` | CREATE | POST /runs, GET /runs/{id} |
| `backend/app/main.py` | UPDATE | Include pipeline router, dev create-tables |
| `backend/tests/*` | CREATE | Tests per task |

---

## Story 1 — Dependencies & DB session (deltas over M0)

> M0 already provides docker-compose, `config.py`, `db.py` (`get_engine`/`ping_db`), `.env.example`,
> and base deps. This story only adds what M1 needs on top.

### Task 1.1: Add M1-specific dependencies

- **File:** `backend/pyproject.toml` (UPDATE)
- [ ] **Step 1 — add** to `[project].dependencies` (M0 deps already present):
  `sqlmodel>=0.0.22`, `alembic>=1.13`, `lxml>=5.3`, `langgraph>=0.2.50`,
  `langgraph-checkpoint-postgres>=2.0`.
- [ ] **Step 2 — verify (gate):** `cd backend && uv sync` succeeds; confirm
  `from langgraph.graph import StateGraph`, `from sqlmodel import SQLModel`, `import lxml.etree`
  all import. If `uv sync` resolves newer compatible versions, accept them.
- [ ] **Step 3 — commit:** `chore: add langgraph, sqlmodel, alembic, lxml deps`

### Task 1.2: Add async session helper

> **Async (per spec).** M0's `get_engine()` returns an async engine (`create_async_engine`,
> asyncpg). M1 adds an `AsyncSession` factory. Tests use `sqlite+aiosqlite://` (add `aiosqlite` to
> dev deps) so async sessions work offline. SQLModel models are plain table classes; they work with
> `AsyncSession` via `await session.exec(...)`.

- **File:** `backend/app/db.py` (UPDATE — extends M0's async `get_engine`/`ping_db`)
- [ ] **Step 1 — write failing test** `backend/tests/test_db_session.py`:

```python
import pytest
from sqlmodel import SQLModel

@pytest.mark.asyncio
async def test_async_session_works(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite://")
    from app.config import get_settings
    get_settings.cache_clear()
    from app.db import get_engine, get_session
    async with get_engine().begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    agen = get_session()
    session = await agen.__anext__()
    assert session is not None
    await agen.aclose()
```

- [ ] **Step 2 — run** → FAIL.
- [ ] **Step 3 — implement** in `app/db.py` (keep M0's async `get_engine`/`ping_db`):

```python
from sqlmodel.ext.asyncio.session import AsyncSession
from app.db import get_engine  # already defined in M0 (async engine)

async def get_session():
    async with AsyncSession(get_engine()) as session:
        yield session
```

  > Keep one `get_engine`; do not duplicate. Use `sqlmodel`'s `AsyncSession`. All DB access in M1+ is
  > `await`ed (`await session.exec(select(...))`, `await session.commit()`).

- [ ] **Step 4 — run** → PASS. **Step 5 — commit:** `feat: add async session dependency`

> **Test-DB note:** model tests in Story 2 below use an **async** in-memory engine
> (`create_async_engine("sqlite+aiosqlite://")`) and `await conn.run_sync(SQLModel.metadata.create_all)`
> inside an async test, rather than the sync `create_engine` shown in those snippets. Add
> `aiosqlite` + `pytest-asyncio` (already present) to dev deps.

---

## Story 2 — Data models & migrations

> All models use SQLModel `table=True`; JSON columns use `sqlalchemy.JSON`; run-scoped tables carry
> `tenant_id: str = "default"`; enums stored as `str`. `import app.models` must register every table
> on `SQLModel.metadata`.

### Task 2.1: TargetSchema model

- **File:** `backend/app/models/schema.py` (CREATE)
- [ ] **Step 1 — write failing test** `backend/tests/models/test_schema_model.py`:

```python
from sqlmodel import SQLModel, Session, create_engine
from app.models.schema import TargetSchema

def test_target_schema_persists():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        ts = TargetSchema(name="acme", version="1.0", definition={"type": "object"})
        s.add(ts); s.commit(); s.refresh(ts)
        assert ts.id is not None
        assert ts.definition["type"] == "object"
```

- [ ] **Step 2 — run** → FAIL.
- [ ] **Step 3 — implement** `app/models/schema.py`:

```python
from datetime import datetime, UTC
from sqlalchemy import JSON, Column
from sqlmodel import SQLModel, Field

class TargetSchema(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    tenant_id: str = "default"
    name: str
    version: str
    definition: dict = Field(sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
```

- [ ] **Step 4 — run** → PASS. **Step 5 — commit:** `feat: add TargetSchema model`

### Task 2.2: PipelineRun + StageResult models

- **File:** `backend/app/models/run.py` (CREATE)
- [ ] **Step 1 — write failing test** `backend/tests/models/test_run_model.py`: create a
  `PipelineRun` (status default `"running"`, `thread_id` settable), add a `StageResult` with FK
  `run_id`, query back, assert `stage`/`status` round-trip and `payload` JSON persists.
- [ ] **Step 2 — run** → FAIL.
- [ ] **Step 3 — implement** `app/models/run.py`:

```python
from datetime import datetime, UTC
from sqlalchemy import JSON, Column
from sqlmodel import SQLModel, Field

class PipelineRun(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    tenant_id: str = "default"
    status: str = "running"  # running|awaiting_review|completed|failed
    source_filename: str
    source_xml: str
    target_schema_id: int = Field(foreign_key="targetschema.id")
    thread_id: str | None = None          # LangGraph checkpoint thread
    prompt_version: str = "v1"
    target_schema_version: str = "1.0"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class StageResult(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="pipelinerun.id")
    stage: str   # extract|interpret|map|build|test|support
    status: str = "pending"  # pending|awaiting_review|approved|rejected
    payload: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
```

- [ ] **Step 4 — run** → PASS. **Step 5 — commit:** `feat: add PipelineRun and StageResult models`

### Task 2.3: FieldMapping model

- **File:** `backend/app/models/mapping.py` (CREATE)
- [ ] **Step 1 — write failing test** `backend/tests/models/test_mapping_model.py`: persist a
  `FieldMapping` with `run_id`, `source_path`, `target_path`, `transform`, `confidence` (nullable),
  `flags` (JSON list), `status` default `"proposed"`; assert round-trip.
- [ ] **Step 2 — run** → FAIL.
- [ ] **Step 3 — implement** `app/models/mapping.py`:

```python
from sqlalchemy import JSON, Column
from sqlmodel import SQLModel, Field

class FieldMapping(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="pipelinerun.id")
    source_path: str
    target_path: str
    transform: str | None = None
    confidence: float | None = None   # populated in M2
    flags: list = Field(default_factory=list, sa_column=Column(JSON))
    status: str = "proposed"          # proposed|approved|edited|rejected
```

- [ ] **Step 4 — run** → PASS. **Step 5 — commit:** `feat: add FieldMapping model`

### Task 2.4: Audit models (AuditEvent, ReviewAction, LLMCall)

- **File:** `backend/app/models/audit.py` (CREATE)
- [ ] **Step 1 — write failing test** `backend/tests/models/test_audit_model.py`: persist one of
  each; assert `AuditEvent.before/after` JSON round-trip, `LLMCall.langfuse_trace_id` stores.
- [ ] **Step 2 — run** → FAIL.
- [ ] **Step 3 — implement** `app/models/audit.py`:

```python
from datetime import datetime, UTC
from sqlalchemy import JSON, Column
from sqlmodel import SQLModel, Field

class AuditEvent(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="pipelinerun.id")
    actor: str  # system|human
    action: str
    before: dict | None = Field(default=None, sa_column=Column(JSON))
    after: dict | None = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class ReviewAction(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="pipelinerun.id")
    stage: str | None = None
    field_mapping_id: int | None = Field(default=None, foreign_key="fieldmapping.id")
    reviewer: str
    decision: str  # approve|edit|reject
    note: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class LLMCall(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    run_id: int | None = Field(default=None, foreign_key="pipelinerun.id")
    stage: str
    model: str
    prompt: str
    response: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0
    estimated_cost: float = 0.0
    langfuse_trace_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
```

- [ ] **Step 4 — implement** `app/models/__init__.py` re-exporting all models.
- [ ] **Step 5 — run** → PASS. **Step 6 — commit:** `feat: add audit, review, llmcall models`

### Task 2.5: Alembic setup + initial migration

- **Files:** `backend/alembic.ini`, `backend/alembic/env.py`, `backend/alembic/versions/*` (CREATE)
- [ ] **Step 1 — init:** `cd backend && uv run alembic init alembic`
- [ ] **Step 2 — wire** `alembic/env.py`: `import app.models` then
  `target_metadata = SQLModel.metadata`; read URL from `app.config.get_settings().database_url`.
- [ ] **Step 3 — generate:** `uv run alembic revision --autogenerate -m "initial schema"` → lists
  all six app tables (TargetSchema, PipelineRun, StageResult, FieldMapping, AuditEvent,
  ReviewAction, LLMCall).
- [ ] **Step 4 — verify** against real DB: `docker-compose up -d` then
  `DATABASE_URL=postgresql+psycopg://pipeline:pipeline@localhost:5432/pipeline uv run alembic upgrade head`
  → tables created; `alembic downgrade base` reverts.
- [ ] **Step 5 — commit:** `feat: add alembic with initial schema migration`

---

## Story 3 — LLM client (PydanticAI + Langfuse)

### Task 3.1: PydanticAI client with Langfuse tracing + LLMCall mirror

> Extends M0's `app/llm/client.py` (which already has `_model`/`ping_llm`). Keep those; add
> `build_agent` + `run_structured` with LLMCall logging here.

- **File:** `backend/app/llm/client.py` (UPDATE), `backend/app/llm/__init__.py` (CREATE)
- [ ] **Step 1 — write failing test** `backend/tests/llm/test_client.py`:

```python
import pytest
from pydantic import BaseModel
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
import app.models  # register tables
from app.models.audit import LLMCall
from app.llm.client import build_agent, run_structured

class Out(BaseModel):
    answer: str

@pytest.mark.asyncio
async def test_run_structured_uses_test_model_and_logs():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    agent = build_agent(Out, system="say hi", mode="test")  # PydanticAI TestModel
    async with AsyncSession(engine) as s:
        result = await run_structured(agent, "hello", stage="map", run_id=None, session=s)
        await s.commit()
        assert isinstance(result, Out)
        rows = (await s.exec(select(LLMCall))).all()
        assert len(rows) == 1
        assert rows[0].stage == "map"
```

- [ ] **Step 2 — run** → FAIL.
- [ ] **Step 3 — implement** `app/llm/client.py` (**async**):

```python
import time
from typing import TypeVar
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider
from sqlmodel.ext.asyncio.session import AsyncSession
from app.config import get_settings
from app.models.audit import LLMCall

T = TypeVar("T", bound=BaseModel)

def _model(mode: str | None = None):
    s = get_settings()
    mode = mode or s.llm_mode
    if mode == "test":
        return TestModel()
    return OpenAIModel(
        s.openrouter_model,
        provider=OpenAIProvider(base_url=s.openrouter_base_url, api_key=s.openrouter_api_key),
    )

def build_agent(output_type: type[T], system: str, mode: str | None = None) -> Agent:
    return Agent(_model(mode), output_type=output_type, system_prompt=system)

async def run_structured(agent: Agent, user: str, *, stage: str,
                         run_id: int | None, session: AsyncSession | None) -> BaseModel:
    start = time.monotonic()
    result = await agent.run(user)          # async; PydanticAI validates output_type
    latency_ms = int((time.monotonic() - start) * 1000)
    usage = result.usage()
    if session is not None:
        session.add(LLMCall(
            run_id=run_id, stage=stage, model=str(agent.model),
            prompt=user, response=str(result.output),
            prompt_tokens=getattr(usage, "request_tokens", 0) or 0,
            completion_tokens=getattr(usage, "response_tokens", 0) or 0,
            latency_ms=latency_ms,
            langfuse_trace_id=None,        # populated when Langfuse enabled (Task 3.2)
        ))
    return result.output
```

- [ ] **Step 4 — run** → PASS. **Step 5 — commit:** `feat: add PydanticAI LLM client with LLMCall logging`

### Task 3.2: Langfuse tracing wrapper

- **File:** `backend/app/llm/client.py` (UPDATE)
- [ ] **Step 1 — write failing test** `backend/tests/llm/test_langfuse.py`: assert `get_langfuse()`
  returns `None` when keys unset (no crash), and that `run_structured` still works + logs `LLMCall`
  with `langfuse_trace_id is None` in that case. (No live Langfuse in tests.)
- [ ] **Step 2 — run** → FAIL.
- [ ] **Step 3 — implement** a `get_langfuse()` helper returning a cached `Langfuse` client only when
  both keys are set, else `None`. In `run_structured`, when a client exists, create a trace/span,
  capture its id into `LLMCall.langfuse_trace_id`, and flush. When `None`, behave exactly as before.
- [ ] **Step 4 — run** → PASS. **Step 5 — commit:** `feat: add optional Langfuse tracing to LLM client`

---

## Story 4 — Sample data & target schemas

### Task 4.1: Sample ACORD XML + two target schemas

- **Files:** `backend/app/schemas/acord_life_sample.xml`, `acord_messy_sample.xml`,
  `acord_pc_real_sample.xml`, `target_distributor_a.json`, `target_distributor_b.json` (CREATE)
- [ ] **Step 1 — author** one clean synthetic life TXLife XML with authentic structure
  (`TXLife > OLifE > Holding > Policy`; `Party > Person`): policy number, product type code, face
  amount, issue date; insured party first/last name, birth date, gender code.
- [ ] **Step 2 — author** one deliberately messy variant (missing a required field + an unexpected
  element).
- [ ] **Step 3 — add** the adapted minimal real P&C ACORD sample with a header comment citing source
  `appulate/appulate-acordxml-svc-sample` (no license — minimal/adapted).
- [ ] **Step 4 — author** two distributor JSON Schemas with different field names for the same
  concepts (e.g. `policyNumber` vs `policy_id`).
- [ ] **Step 5 — commit:** `feat: add sample ACORD xml and two distributor target schemas`

### Task 4.2: Seed target schemas

- **File:** `backend/app/seed.py` (CREATE)
- [ ] **Step 1 — write failing test** `backend/tests/test_seed.py`: against in-memory DB,
  `seed_target_schemas(session)` creates two `TargetSchema` rows (`distributor_a`/`distributor_b`);
  running twice does not duplicate (idempotent on name+version).
- [ ] **Step 2 — run** → FAIL.
- [ ] **Step 3 — implement** `app/seed.py` reading the two JSON files, upsert by `(name, version)`.
- [ ] **Step 4 — run** → PASS. **Step 5 — commit:** `feat: add target schema seeding`

---

## Story 5 — Extract node (deterministic)

### Task 5.1: Typed I/O models + errors

- **File:** `backend/app/agents/base.py` (CREATE)
- [ ] **Step 1 — write failing test** `backend/tests/agents/test_base.py`: construct
  `ExtractedField(path=..., value=..., inferred_type=...)` and `FieldMappingProposal(source_path=...,
  target_path=..., transform=..., llm_confidence=...)`; assert attributes; assert `ExtractError` is
  an `Exception` subclass.
- [ ] **Step 2 — run** → FAIL.
- [ ] **Step 3 — implement** `app/agents/base.py` with pydantic models `ExtractedField`,
  `InterpretedField` (used M4), `FieldMappingProposal`, `MappingProposals` (wrapper:
  `mappings: list[FieldMappingProposal]`), and `class ExtractError(Exception): ...`.
- [ ] **Step 4 — run** → PASS. **Step 5 — commit:** `feat: add stage I/O models and errors`

### Task 5.2: Extract node

- **File:** `backend/app/agents/extract.py` (CREATE)
- [ ] **Step 1 — write failing test** `backend/tests/agents/test_extract.py`: read the clean life
  TXLife fixture, call `extract(xml_str)`, assert a list of `ExtractedField` including the policy
  number and the insured last name with non-empty values + inferred types
  (`str`/`number`/`date`). Add a test that malformed XML raises `ExtractError`.
- [ ] **Step 2 — run** → FAIL.
- [ ] **Step 3 — implement** `app/agents/extract.py` using `lxml.etree`: parse, walk leaf elements,
  build a dotted/indexed path, capture text value, infer type (number/date/str). Raise `ExtractError`
  on parse failure or empty document.
- [ ] **Step 4 — run** → PASS. **Step 5 — commit:** `feat: add deterministic ACORD XML extract node`

---

## Story 6 — Map node (PydanticAI)

### Task 6.1: Map node

- **File:** `backend/app/agents/map.py` (CREATE)
- [ ] **Step 1 — write failing test** `backend/tests/agents/test_map.py`: build a small list of
  `ExtractedField` + a small target schema dict; build the agent in `mode="test"` (PydanticAI
  `TestModel` returns schema-valid `MappingProposals`); call
  `propose_mappings(fields, target_schema, run_id=None, session=session, mode="test")`; assert it
  returns a non-empty `list[FieldMappingProposal]` and that one `LLMCall` row was logged.
- [ ] **Step 2 — run** → FAIL.
- [ ] **Step 3 — implement** `app/agents/map.py`: build a system prompt describing the mapping task,
  a user message embedding the source fields + target JSON schema, an agent via
  `build_agent(MappingProposals, system=..., mode=...)`, call `run_structured(...)`, return
  `.mappings`. No confidence blending yet (M2) — keep `llm_confidence` from output.
- [ ] **Step 4 — run** → PASS. **Step 5 — commit:** `feat: add PydanticAI map node proposing mappings`

---

## Story 7 — LangGraph pipeline & API

### Task 7.1: LangGraph graph (Extract→Map with interrupt)

- **File:** `backend/app/graph/build.py` (CREATE)
- [ ] **Step 1 — write failing test** `backend/tests/graph/test_graph.py`: build the graph with a
  `MemorySaver` checkpointer and `mode="test"`; seed an in-memory DB with a `TargetSchema` and a
  `PipelineRun`; invoke the graph with the run's xml + target schema + `run_id` and a
  `thread_id`. Assert:
  - after invoke, the graph is **interrupted** before review (graph state shows a pending interrupt),
  - a `StageResult` for `extract` (status `approved`/auto) and one for `map` (status
    `awaiting_review`) exist,
  - `FieldMapping` rows persisted with status `proposed`,
  - an `AuditEvent` recorded for the map proposal,
  - the `PipelineRun.status` is `awaiting_review`.
- [ ] **Step 2 — run** → FAIL.
- [ ] **Step 3 — implement** `app/graph/build.py`:
  - Define a `PipelineState` TypedDict: `run_id`, `source_xml`, `target_schema`, `extracted`,
    `mappings`.
  - `extract_node`: call `extract(...)`, persist `StageResult(stage="extract", status="approved")`,
    write `AuditEvent`, return `{"extracted": [...]}`.
  - `map_node`: call `propose_mappings(...)`, persist `FieldMapping` rows (`proposed`) +
    `StageResult(stage="map", status="awaiting_review")`, set run `awaiting_review`, write
    `AuditEvent`, return `{"mappings": [...]}`.
  - Wire `START → extract → map → <interrupt> → END`; compile with the provided checkpointer.
  - Expose `build_pipeline(session, checkpointer, mode)` returning the compiled graph, and a helper
    `start_run(run_id, session, checkpointer=None, mode=None)` that loads the run + target schema and
    invokes the graph with a `thread_id`, persisting `thread_id` on the run.
  - On node exception: set run `failed`, write `AuditEvent`, re-raise after logging.

  > **M1 gate note:** the run legitimately ends paused at the interrupt with proposals persisted —
  > that is M1's definition of done. The resume-on-approval API arrives in M2.

- [ ] **Step 4 — run** → PASS. **Step 5 — commit:** `feat: add LangGraph extract->map pipeline with review interrupt`

### Task 7.2: Pipeline API

- **Files:** `backend/app/routers/pipeline.py` (CREATE), `backend/app/main.py` (UPDATE)
- **Mirror:** route/handler shape in `backend/app/main.py:1-8`
- [ ] **Step 1 — write failing test** `backend/tests/routers/test_pipeline_api.py` (TestClient,
  dependency-override DB to in-memory + seed a target schema, force `mode="test"` +
  `MemorySaver`):
  - `POST /runs` multipart (life XML) + `target_schema_id` → 201, returns `run_id` and status
    `awaiting_review` (BackgroundTasks runs synchronously under TestClient).
  - `GET /runs/{id}` → 200 with run status, stage results, proposed mappings.
  - `GET /runs/{id}` missing → 404.
- [ ] **Step 2 — run** → FAIL.
- [ ] **Step 3 — implement** `app/routers/pipeline.py`:
  - `POST /runs`: accept `UploadFile` + `target_schema_id` (Form); create `PipelineRun`; schedule
    `start_run(run_id, ...)` via `BackgroundTasks`; return run id + status.
  - `GET /runs/{run_id}`: return run + `StageResult`s + `FieldMapping`s; 404 if absent.
  - Use `Depends(get_session)`; checkpointer + mode resolved from a small provider overridable in
    tests.
- [ ] **Step 4 — update** `app/main.py`: `app.include_router(pipeline.router)`; on startup in dev,
  `SQLModel.metadata.create_all(get_engine())` (Alembic remains source of truth for Postgres).
- [ ] **Step 5 — run** full suite `uv run pytest -v` → all PASS.
- [ ] **Step 6 — commit:** `feat: add pipeline run API (create + fetch)`

---

## Validation

```bash
# Backend
cd backend && uv sync
uv run pytest -v                 # all tests pass (offline: TestModel + MemorySaver + SQLite)

# Migrations against real DB
docker-compose up -d             # postgres + qdrant
cd backend && uv run alembic upgrade head
uv run alembic downgrade base

# Manual smoke (optional, needs OPENROUTER_API_KEY)
uv run fastapi dev app/main.py
# POST /runs with a sample XML + target_schema_id, then GET /runs/{id}
```

## Acceptance Criteria

- [ ] `docker-compose up -d` brings up Postgres + Qdrant
- [ ] `alembic upgrade head` creates all app tables; `downgrade base` reverts
- [ ] All backend tests pass offline (PydanticAI TestModel, LangGraph MemorySaver, SQLite)
- [ ] `POST /runs` (ACORD XML + target schema) creates a run; the LangGraph graph runs Extract→Map
- [ ] Map produces persisted `FieldMapping` rows with status `proposed`
- [ ] The run pauses at the review interrupt with status `awaiting_review`
- [ ] Every LLM call logs an `LLMCall` row (and a Langfuse trace when keys are set)
- [ ] Each state change writes an append-only `AuditEvent`
- [ ] `GET /runs/{id}` returns run status, stage results, and proposed mappings
- [ ] Follows existing FastAPI route + pytest patterns

---

## Out of Scope (later milestones)

- M2: hybrid confidence scoring, resume-on-approval review API (per-stage + per-field), audit log
  view, React review console (Tailwind).
- M3: Build node (transform + applier), Test node, custom eval harness + dashboard.
- M4: Read & Interpret node, LlamaIndex + Qdrant index, Support RAG chat + UI, Ragas eval.
