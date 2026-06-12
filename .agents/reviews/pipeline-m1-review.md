# Code Review: Pipeline M1 Foundation

**Scope**: feat/pipeline branch — M1 Foundation (vs M1 plan at `.agents/plans/completed/2026-06-06-pipeline-m1-foundation.plan.md`)
**Recommendation**: APPROVE with notable issues

## Summary

M1 delivers all required files: data models (TargetSchema, PipelineRun, StageResult, FieldMapping, audit
models), async session helper, PydanticAI LLM client with Langfuse tracing + LLMCall logging, Extract +
Map nodes, LangGraph Extract→Map→interrupt pipeline, seed data, 5 ACORD/schema fixtures, Alembic
setup with initial migration, and the pipeline REST API. All 31 backend tests pass offline (TestModel +
MemorySaver + SQLite). Code is tight and follows established patterns. One architectural deviation from
the plan stands out as a High issue.

## Issues Found

### Critical
None

### High Priority

1. **`pipeline.py` — `BackgroundTasks` declared but unused; `start_run` called synchronously**
   - `create_run` signature includes `background_tasks: BackgroundTasks` but never uses it
   - `await start_run(...)` runs inline — the HTTP request blocks for the full graph execution
   - Plan spec: "schedule `start_run(run_id, ...)` via `BackgroundTasks`"
   - Root cause: sharing a `session` object between the handler and `start_run` is simpler sync,
     but background execution requires `start_run` to open its own session
   - Fix: remove `background_tasks` from signature (dead param), add a comment explaining why
     it's synchronous, OR properly background it with an independent session. For M1, removing
     the dead param and documenting the sync choice is the minimal fix.

2. **`graph/build.py:139` — bare `except Exception: pass` swallows real failures**
   - `NodeInterrupt` from LangGraph is the expected signal; catching all `Exception` hides
     bugs in extract/map nodes
   - Fix: `from langgraph.errors import NodeInterrupt` then `except NodeInterrupt: pass`
     (re-raise anything else)

3. **`db.py` — `_engine` global mutation** (carried from M0, not addressed in M1)
   - Module-level mutable singleton with `global` mutation; leaks across test sessions
   - Plan M1 prerequisite note says "M1 builds on M0" but this was flagged as M1 fix target
   - Fix: use `@functools.lru_cache(maxsize=1)` on `get_engine()` or a lifespan-managed singleton

### Medium Priority

4. **`main.py:17` — `except Exception: pass` in lifespan swallows all startup DB errors**
   - If `SQLModel.metadata.create_all` fails (misconfigured URL, down DB), the app starts
     silently with no tables and no warning
   - Fix: at minimum `import logging; logger.warning("DB create_all failed: %s", e)`

5. **`alembic/env.py:15` — `get_settings()` called at import time**
   - If `DATABASE_URL` is not in the environment when `alembic` CLI runs (e.g., no `.env` file),
     pydantic-settings raises a validation error before any alembic command runs
   - Fix: wrap in a try/except or guard with `config.get_main_option("sqlalchemy.url")` as
     fallback before calling `get_settings()`

6. **`pipeline.py` — no `target_schema_id` existence check before creating `PipelineRun`**
   - If the schema ID doesn't exist, a FK constraint error surfaces during `start_run` as a 500,
     not a clean 404/422 before the run is even created
   - Fix: `SELECT 1 FROM targetschema WHERE id = ?` before `session.add(run)`

7. **CORS `allow_origins` still hardcoded** (M0 Medium #3, not fixed in M1)
   - `http://localhost:5174` is still hardcoded in `main.py`

### Suggestions

- `pipeline.py` — `get_checkpointer()` returns a new `MemorySaver()` per request; in production
  this should be an `AsyncPostgresSaver` from `langgraph-checkpoint-postgres`. Fine for M1, but
  the provider function is the right hook point — add a TODO.
- `graph/build.py` — `session` is captured in closure by `extract_node`/`map_node`; passed in
  from `start_run`. This means the graph cannot be used with `BackgroundTasks` without a session
  factory. Documenting this constraint would clarify the sync-only design choice.
- `models/run.py` — `StageResult.status` default is `"pending"` but the graph immediately sets
  it to `"approved"` (extract) or `"awaiting_review"` (map); `"pending"` rows never persist.
  Minor, but could remove the default since the graph always provides explicit status.
- `alembic/versions/c0c37cb17507_initial_schema.py` — exists and covers all 7 tables. Good.

## Validation Results

| Check | Status |
|-------|--------|
| Backend tests (pytest) | PASS — 31/31 |
| Frontend tests (vitest) | (not re-run; no M1 frontend changes) |
| TypeScript (`tsc --noEmit`) | (not re-run; no M1 frontend changes) |

## What's Good

- All M1 files present and all 7 acceptance criteria achievable
- `alembic/env.py` correctly swaps `+asyncpg` → `+psycopg` for the sync migration engine
- `get_langfuse()` wrapped in `@lru_cache` — avoids recreating on every call
- `run_structured` uses `getattr(usage, "input_tokens", 0)` — handles PydanticAI API variance safely
- `test_pipeline_api.py` correctly isolates via `dependency_overrides` and cleans up after each test
- `seed.py` idempotent on `(name, version)` — safe to call at startup
- Extract node: QName stripping for namespace-qualified tags is correct lxml pattern
- All M1 test files use in-memory SQLite + `TestModel` + `MemorySaver` — zero network, fast
- `models/__init__.py` re-exports all tables, guaranteeing they register on `SQLModel.metadata`

## Recommendation

Fix the dead `BackgroundTasks` parameter (#1) and the bare `except Exception` in graph (#2) before
M2. The `_engine` global (#3) should be addressed at the start of M2 since M2 adds more DB-heavy
routes. Items #4–#7 are low-blast-radius but should be cleaned before M3/M4.
