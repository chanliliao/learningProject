# Plan: Pipeline — Milestone 1 (Foundation + Extract→Map Spine)

> **For implementers:** Execute tasks in order. Each task uses TDD: write failing test → run it (see it fail) → implement → run it (see it pass) → commit. Steps use checkbox (`- [ ]`) syntax. Reference spec: `.agents/specs/2026-06-06-pipeline-design.md`.

## Summary

Build the backend foundation and the deterministic-to-LLM spine of the schema mapping pipeline:
Dockerized Postgres+pgvector, SQLModel data models under Alembic migrations, an OpenRouter LLM
client that logs every call, two seeded distributor target schemas, the deterministic **Extract**
stage (ACORD XML → fields), the LLM-backed **Map** stage (fields → proposed mappings), an
orchestrator that runs Extract→Map asynchronously and pauses at gates, and a pipeline API to start
and inspect runs. No review UI and no confidence scoring yet (Milestone 2). Outcome: upload an ACORD
XML, pick a target schema, and get persisted proposed field mappings.

## User Story

As an integration engineer
I want to upload a carrier ACORD XML and select a distributor target schema and have the system
extract fields and propose a mapping
So that I can see a machine-proposed source→target mapping persisted for later review.

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | HIGH |
| Milestone | M1 of 4 |
| Systems Affected | backend (FastAPI, Postgres, Alembic, OpenRouter), docker |
| Jira Issue | N/A |

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
`asyncio_mode="auto"`. Deps in `[project].dependencies`, test deps in `[dependency-groups].dev`.

---

## Conventions for this milestone

- **Stage modules** live in `backend/app/agents/`. Each exposes a single callable conforming to the
  `Stage` protocol in `agents/base.py`: `run(ctx) -> StageOutput`.
- **LLM never writes final state.** Map produces `FieldMapping` rows with status `proposed`.
- **Every LLM call** goes through `app/llm/openrouter.py` and is recorded as an `LLMCall` row.
- **Tests run offline.** LLM-backed code is tested with a mock client (env `LLM_MODE=mock` or
  dependency injection); no network calls in tests.
- **DB in tests:** use a transactional SQLite or a disposable Postgres test DB; models must avoid
  Postgres-only types in M1 (pgvector/Embedding is M4, so SQLite is fine for M1 tests).

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `docker-compose.yml` | CREATE | Postgres + pgvector service |
| `backend/pyproject.toml` | UPDATE | Add sqlmodel, psycopg, alembic, lxml, python-dotenv deps |
| `backend/.env.example` | CREATE | Document OPENROUTER_API_KEY, DATABASE_URL |
| `backend/app/config.py` | CREATE | Settings loaded from env |
| `backend/app/db.py` | CREATE | Engine + session dependency |
| `backend/app/models/__init__.py` | CREATE | Model exports |
| `backend/app/models/schema.py` | CREATE | TargetSchema model |
| `backend/app/models/run.py` | CREATE | PipelineRun, StageResult models |
| `backend/app/models/mapping.py` | CREATE | FieldMapping model |
| `backend/app/models/audit.py` | CREATE | AuditEvent, ReviewAction, LLMCall models |
| `backend/alembic.ini`, `backend/alembic/` | CREATE | Migrations |
| `backend/app/llm/__init__.py`, `openrouter.py` | CREATE | LLM client + LLMCall logging + mock |
| `backend/app/schemas/` | CREATE | Sample ACORD XML + 2 target JSON schemas |
| `backend/app/agents/base.py` | CREATE | Stage protocol + context types |
| `backend/app/agents/extract.py` | CREATE | Deterministic XML extraction |
| `backend/app/agents/map.py` | CREATE | LLM mapping proposal |
| `backend/app/pipeline/orchestrator.py` | CREATE | Run Extract→Map, persist, gate |
| `backend/app/routers/pipeline.py` | CREATE | POST /runs, GET /runs/{id} |
| `backend/app/main.py` | UPDATE | Include pipeline router, create-tables on startup (dev) |
| `backend/tests/*` | CREATE | Tests per task |

---

## Story 1 — Infrastructure & database foundation

### Task 1.1: Docker Postgres + pgvector

- **File:** `docker-compose.yml` (CREATE)
- [ ] **Step 1 — write compose file**

```yaml
services:
  db:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: pipeline
      POSTGRES_PASSWORD: pipeline
      POSTGRES_DB: pipeline
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
volumes:
  pgdata:
```

- [ ] **Step 2 — verify** `docker-compose up -d` then `docker-compose ps` shows `db` healthy.
  Tear down with `docker-compose down`.
- [ ] **Step 3 — commit:** `chore: add postgres+pgvector docker-compose`

### Task 1.2: Backend dependencies

- **File:** `backend/pyproject.toml` (UPDATE)
- **Mirror:** existing `[project].dependencies` and `[dependency-groups].dev` blocks
  (`backend/pyproject.toml:7-15`)
- [ ] **Step 1 — add runtime deps** to `[project].dependencies`: `sqlmodel>=0.0.22`,
  `psycopg[binary]>=3.2`, `alembic>=1.13`, `lxml>=5.3`, `python-dotenv>=1.0`, `httpx>=0.28`.
- [ ] **Step 2 — run** `cd backend && uv sync` → succeeds, lockfile updated.
- [ ] **Step 3 — commit:** `chore: add db, migration, xml, llm backend deps`

### Task 1.3: Settings + env

- **Files:** `backend/app/config.py` (CREATE), `backend/.env.example` (CREATE)
- [ ] **Step 1 — write failing test** `backend/tests/test_config.py`:

```python
import os
from app.config import get_settings

def test_settings_reads_database_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("OPENROUTER_API_KEY", "x")
    get_settings.cache_clear()
    s = get_settings()
    assert s.database_url == "sqlite://"
    assert s.openrouter_api_key == "x"
    assert s.llm_mode in ("real", "mock")
```

- [ ] **Step 2 — run** `uv run pytest tests/test_config.py -v` → FAIL (no module).
- [ ] **Step 3 — implement** `app/config.py`:

```python
from functools import lru_cache
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str = "sqlite:///./pipeline.db"
    openrouter_api_key: str = ""
    openrouter_model: str = "openai/gpt-4o-mini"  # cheapest workable default
    llm_mode: str = "real"  # "mock" for offline tests
    confidence_threshold: float = 0.8

    class Config:
        env_file = ".env"

@lru_cache
def get_settings() -> Settings:
    return Settings()
```

(Add `pydantic-settings>=2.5` to deps in Task 1.2 if not present; if discovered here, add and re-sync.)

- [ ] **Step 4 — run** test → PASS.
- [ ] **Step 5 — write** `backend/.env.example`:

```
OPENROUTER_API_KEY=
DATABASE_URL=postgresql+psycopg://pipeline:pipeline@localhost:5432/pipeline
```

- [ ] **Step 6 — commit:** `feat: add settings module and env example`

### Task 1.4: DB engine + session

- **File:** `backend/app/db.py` (CREATE)
- [ ] **Step 1 — write failing test** `backend/tests/test_db.py`:

```python
from app.db import get_engine, get_session

def test_session_yields_usable_session(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    from app.config import get_settings
    get_settings.cache_clear()
    gen = get_session()
    session = next(gen)
    assert session is not None
    gen.close()
```

- [ ] **Step 2 — run** → FAIL.
- [ ] **Step 3 — implement** `app/db.py`:

```python
from sqlmodel import create_engine, Session
from app.config import get_settings

def get_engine():
    settings = get_settings()
    connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
    return create_engine(settings.database_url, connect_args=connect_args)

def get_session():
    with Session(get_engine()) as session:
        yield session
```

- [ ] **Step 4 — run** → PASS.
- [ ] **Step 5 — commit:** `feat: add database engine and session dependency`

---

## Story 2 — Data models & migrations

> All models use SQLModel `table=True`. JSON columns use `sqlalchemy.JSON`. All run-scoped tables
> include `tenant_id: str` (default `"default"`) for the multi-tenant story. Enums are stored as
> `str`.

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
- [ ] **Step 1 — write failing test** `backend/tests/models/test_run_model.py` covering: create a
  `PipelineRun` (status default `"running"`), add a `StageResult` with FK `run_id`, query it back,
  assert `stage` and `status` round-trip and `payload` JSON persists.
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
    prompt_version: str = "v1"
    target_schema_version: str = "1.0"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class StageResult(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="pipelinerun.id")
    stage: str  # extract|interpret|map|build|test|support
    status: str = "pending"  # pending|awaiting_review|approved|rejected
    payload: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
```

- [ ] **Step 4 — run** → PASS. **Step 5 — commit:** `feat: add PipelineRun and StageResult models`

### Task 2.3: FieldMapping model

- **File:** `backend/app/models/mapping.py` (CREATE)
- [ ] **Step 1 — write failing test** `backend/tests/models/test_mapping_model.py`: persist a
  `FieldMapping` with `run_id`, `source_path`, `target_path`, `transform`, `confidence` (nullable in
  M1), `flags` (JSON list), `status` default `"proposed"`; assert round-trip.
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
    confidence: float | None = None  # populated in M2
    flags: list = Field(default_factory=list, sa_column=Column(JSON))
    status: str = "proposed"  # proposed|approved|edited|rejected
```

- [ ] **Step 4 — run** → PASS. **Step 5 — commit:** `feat: add FieldMapping model`

### Task 2.4: Audit models (AuditEvent, ReviewAction, LLMCall)

- **File:** `backend/app/models/audit.py` (CREATE)
- [ ] **Step 1 — write failing test** `backend/tests/models/test_audit_model.py`: persist one of
  each; assert `AuditEvent.before`/`after` JSON round-trip and `LLMCall.prompt_tokens` int stores.
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
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
```

- [ ] **Step 4 — implement** `app/models/__init__.py` re-exporting all models so
  `SQLModel.metadata` sees them.
- [ ] **Step 5 — run** → PASS. **Step 6 — commit:** `feat: add audit, review, llmcall models`

### Task 2.5: Alembic setup + initial migration

- **Files:** `backend/alembic.ini`, `backend/alembic/env.py`, `backend/alembic/versions/*` (CREATE)
- [ ] **Step 1 — init:** `cd backend && uv run alembic init alembic`
- [ ] **Step 2 — wire** `alembic/env.py`: set `target_metadata = SQLModel.metadata` (import all
  models via `import app.models`), and read URL from `app.config.get_settings().database_url`.
- [ ] **Step 3 — generate:** `uv run alembic revision --autogenerate -m "initial schema"` →
  migration file lists all six M1 tables.
- [ ] **Step 4 — verify** against a real DB: `docker-compose up -d` then
  `DATABASE_URL=postgresql+psycopg://pipeline:pipeline@localhost:5432/pipeline uv run alembic upgrade head`
  → tables created (`\dt` in psql). Then `alembic downgrade base` works.
- [ ] **Step 5 — commit:** `feat: add alembic with initial schema migration`

---

## Story 3 — OpenRouter LLM client with observability

### Task 3.1: LLM client + mock + LLMCall logging

- **Files:** `backend/app/llm/__init__.py`, `backend/app/llm/openrouter.py` (CREATE)
- [ ] **Step 1 — write failing test** `backend/tests/llm/test_openrouter.py`:

```python
from app.llm.openrouter import LLMClient

def test_mock_mode_returns_canned_and_logs(tmp_path, monkeypatch):
    client = LLMClient(mode="mock")
    result = client.complete_json(
        stage="map", system="s", user="u",
        schema={"type": "object"}, run_id=None, session=None,
        mock_response={"ok": True},
    )
    assert result == {"ok": True}

def test_complete_json_records_llmcall_when_session(monkeypatch):
    from sqlmodel import SQLModel, Session, create_engine
    import app.models  # register tables
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    from app.models.audit import LLMCall
    client = LLMClient(mode="mock")
    with Session(engine) as s:
        client.complete_json(stage="map", system="x", user="y",
                             schema={}, run_id=None, session=s,
                             mock_response={"a": 1})
        s.commit()
        rows = s.query(LLMCall).all() if hasattr(s, "query") else None
    # use select() if query unavailable
```

(Implementer: prefer `sqlmodel.select(LLMCall)` for the assertion; pseudocode above shows intent —
assert exactly one `LLMCall` row with `stage == "map"`.)

- [ ] **Step 2 — run** → FAIL.
- [ ] **Step 3 — implement** `app/llm/openrouter.py`:

```python
import json, time
import httpx
from sqlmodel import Session
from app.config import get_settings
from app.models.audit import LLMCall

class LLMClient:
    def __init__(self, mode: str | None = None):
        s = get_settings()
        self.mode = mode or s.llm_mode
        self.api_key = s.openrouter_api_key
        self.model = s.openrouter_model

    def complete_json(self, *, stage, system, user, schema,
                      run_id=None, session: Session | None = None,
                      mock_response=None) -> dict:
        start = time.monotonic()
        if self.mode == "mock":
            content = mock_response if mock_response is not None else {}
            raw = json.dumps(content)
            prompt_tokens = completion_tokens = 0
        else:
            resp = httpx.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "response_format": {"type": "json_object"},
                },
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            raw = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            content = json.loads(raw)
        latency_ms = int((time.monotonic() - start) * 1000)
        if session is not None:
            session.add(LLMCall(
                run_id=run_id, stage=stage, model=self.model,
                prompt=f"{system}\n\n{user}", response=raw,
                prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
                latency_ms=latency_ms,
            ))
        return content
```

- [ ] **Step 4 — run** → PASS. **Step 5 — commit:** `feat: add OpenRouter client with LLMCall logging and mock mode`

---

## Story 4 — Sample data & target schemas

### Task 4.1: Sample ACORD XML + two target schemas

- **Files:** `backend/app/schemas/acord_life_sample.xml`,
  `backend/app/schemas/acord_messy_sample.xml`, `backend/app/schemas/acord_pc_real_sample.xml`,
  `backend/app/schemas/target_distributor_a.json`,
  `backend/app/schemas/target_distributor_b.json` (CREATE)
- [ ] **Step 1 — author** one clean synthetic life TXLife XML using authentic structure
  (`TXLife > OLifE > Holding > Policy`, `Party > Person`). Include policy number, product type code,
  face amount, issue date, and an insured party with first/last name, birth date, gender code.
- [ ] **Step 2 — author** one deliberately messy variant (missing a required field, an unexpected
  element) to later exercise the review gate.
- [ ] **Step 3 — add** the adapted minimal real P&C ACORD sample with a header comment citing
  source `appulate/appulate-acordxml-svc-sample` (no license — minimal/adapted).
- [ ] **Step 4 — author** two distributor JSON Schemas (`distributor_a`, `distributor_b`) with
  different field names/structure for the same concepts (e.g. `policyNumber` vs `policy_id`).
- [ ] **Step 5 — commit:** `feat: add sample ACORD xml and two distributor target schemas`

### Task 4.2: Seed target schemas into DB

- **File:** `backend/app/seed.py` (CREATE)
- [ ] **Step 1 — write failing test** `backend/tests/test_seed.py`: against an in-memory DB, run
  `seed_target_schemas(session)` and assert two `TargetSchema` rows exist with names
  `distributor_a` / `distributor_b`; running twice does not duplicate (idempotent on name+version).
- [ ] **Step 2 — run** → FAIL.
- [ ] **Step 3 — implement** `app/seed.py` reading the two JSON files and upserting by
  `(name, version)`.
- [ ] **Step 4 — run** → PASS. **Step 5 — commit:** `feat: add target schema seeding`

---

## Story 5 — Extract stage (deterministic)

### Task 5.1: Stage protocol + context

- **File:** `backend/app/agents/base.py` (CREATE)
- [ ] **Step 1 — write failing test** `backend/tests/agents/test_base.py`: construct an
  `ExtractedField(path=..., value=..., inferred_type=...)` and a `StageContext` carrying `run_id`,
  `source_xml`, `target_schema` (dict), and a `session`; assert attributes accessible.
- [ ] **Step 2 — run** → FAIL.
- [ ] **Step 3 — implement** `app/agents/base.py` with pydantic models `ExtractedField`,
  `InterpretedField` (used in M4), `FieldMappingProposal` (source_path, target_path, transform,
  llm_confidence), `StageContext` (dataclass), and a `Stage` Protocol with `name: str` and
  `run(ctx: StageContext) -> dict`.
- [ ] **Step 4 — run** → PASS. **Step 5 — commit:** `feat: add stage protocol and context types`

### Task 5.2: Extract stage

- **File:** `backend/app/agents/extract.py` (CREATE)
- [ ] **Step 1 — write failing test** `backend/tests/agents/test_extract.py`: feed the clean life
  TXLife sample (read fixture file), call `extract(xml_str)`, assert it returns a list of
  `ExtractedField` including the policy number path and the insured's last name with non-empty
  values and inferred types (`str`/`number`/`date`). Add a test that malformed XML raises a typed
  `ExtractError`.
- [ ] **Step 2 — run** → FAIL.
- [ ] **Step 3 — implement** `app/agents/extract.py` using `lxml.etree`: parse, walk leaf elements,
  build dotted/indexed path, capture text value, infer type (number if numeric, date if ISO-ish,
  else str). Raise `ExtractError` (define in `agents/base.py` or `agents/errors.py`) on parse
  failure or empty document.
- [ ] **Step 4 — run** → PASS. **Step 5 — commit:** `feat: add deterministic ACORD XML extract stage`

---

## Story 6 — Map stage (LLM)

### Task 6.1: Map stage

- **File:** `backend/app/agents/map.py` (CREATE)
- [ ] **Step 1 — write failing test** `backend/tests/agents/test_map.py`: build a small list of
  `ExtractedField`, a small target schema dict, and an `LLMClient(mode="mock")` whose
  `mock_response` returns a mappings array. Call `propose_mappings(fields, target_schema, llm,
  run_id, session)` and assert it returns `FieldMappingProposal` objects whose `source_path` /
  `target_path` match the mock, and that an `LLMCall` row was recorded.
- [ ] **Step 2 — run** → FAIL.
- [ ] **Step 3 — implement** `app/agents/map.py`: build a system+user prompt embedding the source
  fields and target JSON schema, call `llm.complete_json(stage="map", ..., schema=<mappings schema>,
  mock_response=...)`, parse the returned `{"mappings": [...]}` into `FieldMappingProposal` list. No
  confidence blending yet (M2) — keep `llm_confidence` from the response if present.
- [ ] **Step 4 — run** → PASS. **Step 5 — commit:** `feat: add LLM map stage proposing field mappings`

---

## Story 7 — Orchestrator & API

### Task 7.1: Orchestrator (Extract→Map)

- **File:** `backend/app/pipeline/orchestrator.py` (CREATE)
- [ ] **Step 1 — write failing test** `backend/tests/pipeline/test_orchestrator.py`: with in-memory
  DB seeded with a TargetSchema and a created PipelineRun, run
  `run_pipeline(run_id, session, llm=LLMClient(mode="mock", ...))`. Assert: a `StageResult` for
  `extract` (status `approved`/auto in M1 — see note) and one for `map` with status
  `awaiting_review` exist; `FieldMapping` rows persisted with status `proposed`; an `AuditEvent`
  recorded for the map proposal; run status becomes `awaiting_review`.
- [ ] **Step 2 — run** → FAIL.
- [ ] **Step 3 — implement** `app/pipeline/orchestrator.py`: load run + target schema, run Extract
  (deterministic → store StageResult, auto-advance), run Map (store proposals + StageResult
  `awaiting_review`), write AuditEvents, set run status `awaiting_review`. On any stage exception:
  set run `failed`, write AuditEvent, re-raise-safe (log).

  > **M1 gate note:** Map pauses at `awaiting_review` (the review/approve API arrives in M2). For M1,
  > the run legitimately ends in `awaiting_review` with proposals persisted — that is the milestone's
  > definition of done.

- [ ] **Step 4 — run** → PASS. **Step 5 — commit:** `feat: add orchestrator running extract then map`

### Task 7.2: Pipeline API

- **Files:** `backend/app/routers/pipeline.py` (CREATE), `backend/app/main.py` (UPDATE)
- **Mirror:** route/handler shape in `backend/app/main.py:1-8`
- [ ] **Step 1 — write failing test** `backend/tests/routers/test_pipeline_api.py` (use
  `TestClient`, dependency-override DB to in-memory + seed a target schema, override LLM to mock):
  - `POST /runs` with multipart file (the life XML) + `target_schema_id` → 201, returns `run_id`,
    status `awaiting_review` (BackgroundTasks runs synchronously under TestClient).
  - `GET /runs/{id}` → 200 with run status, stage results, and proposed mappings.
  - `GET /runs/{id}` for missing id → 404.
- [ ] **Step 2 — run** → FAIL.
- [ ] **Step 3 — implement** `app/routers/pipeline.py`:
  - `POST /runs`: accept `UploadFile` + `target_schema_id` (Form), create `PipelineRun`, schedule
    `run_pipeline` via `BackgroundTasks`, return run id + status.
  - `GET /runs/{run_id}`: return run + its `StageResult`s + `FieldMapping`s, 404 if absent.
  - Use `Depends(get_session)`; inject `LLMClient` via a `get_llm` dependency (overridable in tests).
- [ ] **Step 4 — update** `app/main.py`: `app.include_router(pipeline.router)`; on startup in dev,
  `SQLModel.metadata.create_all(get_engine())` (migrations remain source of truth for Postgres).
- [ ] **Step 5 — run** full suite `uv run pytest -v` → all PASS.
- [ ] **Step 6 — commit:** `feat: add pipeline run API (create + fetch)`

---

## Validation

```bash
# Backend
cd backend && uv sync
uv run pytest -v                 # all tests pass

# Migrations against real DB
docker-compose up -d
cd backend && uv run alembic upgrade head    # tables created
uv run alembic downgrade base                # reverts cleanly

# Manual smoke (optional)
uv run fastapi dev app/main.py
# POST /runs with a sample XML + target_schema_id, then GET /runs/{id}
```

## Acceptance Criteria

- [ ] `docker-compose up -d` brings up Postgres+pgvector
- [ ] `alembic upgrade head` creates all six M1 tables; `downgrade base` reverts
- [ ] All backend tests pass offline (LLM mocked, SQLite)
- [ ] `POST /runs` (ACORD XML + target schema) creates a run; orchestrator runs Extract→Map
- [ ] Map produces persisted `FieldMapping` rows with status `proposed`
- [ ] Every LLM call is recorded as an `LLMCall` row
- [ ] Each state change writes an append-only `AuditEvent`
- [ ] `GET /runs/{id}` returns run status, stage results, and proposed mappings
- [ ] Run ends in `awaiting_review` (review/approve API is Milestone 2)
- [ ] Follows existing FastAPI route + pytest patterns

---

## Out of Scope (later milestones)

- M2: hybrid confidence scoring, per-stage/per-field review + approve API, audit log view, React
  review console (Tailwind).
- M3: Build stage (transform + applier), Test stage, eval harness + dashboard.
- M4: Read & Interpret enrichment, embeddings + pgvector, Support RAG chat + UI.
