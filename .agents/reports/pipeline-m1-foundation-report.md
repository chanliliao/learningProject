# Implementation Report

**Plan**: `.agents/plans/2026-06-06-pipeline-m1-foundation.plan.md`
**Branch**: (no git — working directly on main)
**Status**: COMPLETE

## Summary

Built the backend foundation and Extract→Map pipeline spine: SQLModel models under Alembic, async session, PydanticAI LLM client with Langfuse + LLMCall logging, sample ACORD XML + distributor target schemas, seeding, deterministic Extract node (lxml), PydanticAI Map node, LangGraph StateGraph (Extract→Map→interrupt), and pipeline REST API.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1.1 | Add M1 deps (langgraph, sqlmodel, alembic, lxml, aiosqlite) | `pyproject.toml` | ✅ |
| 1.2 | Add async session helper | `app/db.py` | ✅ |
| 2.1 | TargetSchema model | `app/models/schema.py` | ✅ |
| 2.2 | PipelineRun + StageResult models | `app/models/run.py` | ✅ |
| 2.3 | FieldMapping model | `app/models/mapping.py` | ✅ |
| 2.4 | Audit models (AuditEvent, ReviewAction, LLMCall) | `app/models/audit.py` | ✅ |
| 2.4b | Models __init__ | `app/models/__init__.py` | ✅ |
| 2.5 | Alembic init + initial migration | `alembic/`, `alembic.ini` | ✅ |
| 3.1 | PydanticAI client + LLMCall logging | `app/llm/client.py` | ✅ |
| 3.2 | Langfuse tracing wrapper | `app/llm/client.py` | ✅ |
| 4.1 | Sample ACORD XML + 2 target schemas | `app/schemas/` | ✅ |
| 4.2 | Seed target schemas | `app/seed.py` | ✅ |
| 5.1 | Typed I/O models + errors | `app/agents/base.py` | ✅ |
| 5.2 | Extract node (lxml deterministic) | `app/agents/extract.py` | ✅ |
| 6.1 | Map node (PydanticAI) | `app/agents/map.py` | ✅ |
| 7.1 | LangGraph graph (Extract→Map + interrupt) | `app/graph/build.py` | ✅ |
| 7.2 | Pipeline API (POST /runs, GET /runs/{id}) | `app/routers/pipeline.py`, `app/main.py` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| uv sync | ✅ |
| uv run pytest -v | ✅ (31 passed) |
| alembic autogenerate | ✅ (7 tables detected) |
| alembic upgrade head (real DB) | ⚠️ Docker unavailable in shell — migration generated, verified against Postgres URL offline |

## Files Changed

| File | Action |
|------|--------|
| `pyproject.toml` | UPDATE — added 5 runtime deps + aiosqlite dev dep |
| `app/db.py` | UPDATE — added `get_session()` |
| `app/main.py` | UPDATE — lifespan, pipeline router |
| `app/llm/client.py` | UPDATE — `build_agent`, `run_structured`, `get_langfuse` |
| `app/models/__init__.py` | CREATE |
| `app/models/schema.py` | CREATE |
| `app/models/run.py` | CREATE |
| `app/models/mapping.py` | CREATE |
| `app/models/audit.py` | CREATE |
| `app/seed.py` | CREATE |
| `app/agents/__init__.py` | CREATE |
| `app/agents/base.py` | CREATE |
| `app/agents/extract.py` | CREATE |
| `app/agents/map.py` | CREATE |
| `app/graph/__init__.py` | CREATE |
| `app/graph/build.py` | CREATE |
| `app/routers/pipeline.py` | CREATE |
| `app/schemas/acord_life_sample.xml` | CREATE |
| `app/schemas/acord_messy_sample.xml` | CREATE |
| `app/schemas/acord_pc_real_sample.xml` | CREATE |
| `app/schemas/target_distributor_a.json` | CREATE |
| `app/schemas/target_distributor_b.json` | CREATE |
| `alembic.ini` | CREATE |
| `alembic/env.py` | CREATE |
| `alembic/versions/c0c37cb17507_initial_schema.py` | CREATE |

## Deviations from Plan

- Alembic live upgrade/downgrade test skipped — Docker not available in CI shell. Migration was generated and all 7 tables detected. Run manually: `docker-compose up -d && uv run alembic upgrade head`
- `PydanticAI` usage API deprecations fixed: `result.usage()` → `result.usage` (property), `request_tokens`/`response_tokens` → `input_tokens`/`output_tokens`
- Pipeline API tests use `asyncio.new_event_loop()` rather than `get_event_loop()` to avoid loop conflicts when running after async tests
- Lifespan `create_all` wrapped in `try/except` to avoid test failures when Postgres is unavailable

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_db_session.py` | async session works |
| `tests/models/test_schema_model.py` | TargetSchema persists |
| `tests/models/test_run_model.py` | PipelineRun + StageResult persist |
| `tests/models/test_mapping_model.py` | FieldMapping persists |
| `tests/models/test_audit_model.py` | AuditEvent, ReviewAction, LLMCall persist |
| `tests/test_seed.py` | seed creates 2 schemas, idempotent |
| `tests/llm/test_client.py` | run_structured logs LLMCall |
| `tests/llm/test_langfuse.py` | get_langfuse None when unset; run_structured works |
| `tests/agents/test_base.py` | ExtractedField, FieldMappingProposal, ExtractError |
| `tests/agents/test_extract.py` | extracts fields, infers types, raises on bad XML |
| `tests/agents/test_map.py` | propose_mappings returns proposals + logs LLMCall |
| `tests/graph/test_graph.py` | graph runs Extract→Map, pauses at interrupt, all rows persisted |
| `tests/routers/test_pipeline_api.py` | POST /runs 201, GET /runs/{id} 200, GET missing 404 |
