# Plan: Phase 2 — Many-to-One Fan-Out (CDM → Many Distributors)

## Summary

Build the projection layer that turns ONE canonical mapping into MANY distributor outputs. After a carrier document is mapped into the CDM (Phase 1), a `DistributorView` defines a CDM→distributor projection. A single completed carrier run produces outputs for every registered distributor view with **zero extra LLM calls** — this is the value-compounding step that realizes N×M→N+M. Projections are deterministic transforms (reuse the transform engine), not LLM calls.

## User Story

As an integration engineer
I want one carrier→CDM mapping to feed every distributor automatically
So that adding a distributor requires no carrier-side rework and no new LLM cost

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY (architecture) |
| Complexity | HIGH |
| Systems Affected | models, transform, graph (build/test nodes), routers, projection module |
| Jira Issue | N/A |

---

## Patterns to Follow

### Deterministic transform application (reuse for projection)
```python
# SOURCE: backend/app/agents/transform.py:94-136
def apply_transform(spec: TransformSpec, source: dict) -> dict:
    # dotted target paths → nested dicts; missing source skipped
```

### Build node reading approved mappings
```python
# SOURCE: backend/app/agents/transform.py:139-188  (run_build)
approved = (... status.in_(["approved","edited"]) ...)
spec = build_transform(mappings_data)
session.add(StageResult(... stage="build", payload={"spec": spec.model_dump()}))
```

### StageResult payload storage
```python
# SOURCE: backend/app/models/run.py:69-75
payload: dict = Field(default_factory=dict, sa_column=Column(JSON))
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `backend/app/models/projection.py` | CREATE | `DistributorView` table: CDM→distributor field map |
| `backend/app/pipeline/projection.py` | CREATE | Apply a `DistributorView` to a CDM record |
| `backend/app/schemas/projection_*.json` | CREATE | One projection per distributor (a, b) per LOB |
| `backend/app/graph/build.py` | UPDATE | After test gate, fan out CDM → each distributor view |
| `backend/app/models/run.py` | UPDATE | `StageResult` stage `"project"`; store per-distributor outputs |
| `backend/app/routers/pipeline.py` | UPDATE | `GET /runs/{id}/outputs` returns all distributor projections |
| `backend/app/seed.py` | UPDATE | Seed distributor views |
| `backend/app/models/run.py` | UPDATE | Add `StageResult.attempt: int` for re-run currency |
| `backend/alembic/versions/xxxx_projection.py` | CREATE | Migration for new table + `attempt` column |
| `frontend/src/pages/RunPage.tsx` | UPDATE | Render `project` stage + per-distributor outputs panel |
| `frontend/src/components/OutputsPanel.tsx` | CREATE | Show each distributor's normalized output |
| `frontend/src/api.ts` | UPDATE | `getRunOutputs` + types |
| `backend/tests/pipeline/test_projection.py` | CREATE | One CDM → 2 distributor outputs, no LLM |

---

## Tasks

### Task 1: DistributorView model + migration
- **File**: `backend/app/models/projection.py`
- **Action**: CREATE
- **Implement**: `class DistributorView(SQLModel, table=True)` with `id`, `tenant_id`, `name`, `lob`, `version`, `canonical_schema_id` (FK), `projection: dict` (JSON: list of `{cdm_path, distributor_path, transform}`). Docstring per repo convention.
- **File**: `backend/alembic/versions/xxxx_projection.py` — CREATE migration.
- **Mirror**: `backend/app/models/schema.py`, `backend/app/models/mapping.py`
- **Validate**: `cd backend && uv run alembic upgrade head`

### Task 2: Projection engine
- **File**: `backend/app/pipeline/projection.py`
- **Action**: CREATE
- **Implement**: `def project(view: DistributorView, cdm_record: dict) -> dict` — reuse `build_transform`/`apply_transform` from `transform.py` (a projection IS a transform spec from CDM paths to distributor paths). No LLM. Handle nested CDM paths (flatten CDM record to dotted keys first via a helper `flatten(d) -> dict`).
- **Mirror**: `backend/app/agents/transform.py:94-136`
- **Validate**: `cd backend && uv run pytest tests/pipeline/test_projection.py`

### Task 3: Projection definitions
- **File**: `backend/app/schemas/projection_distributor_a_life.json` (+ b, + other LOBs as needed)
- **Action**: CREATE
- **Implement**: JSON list mapping canonical Life paths → `target_distributor_a.json` keys (e.g. `Holding.Policy.PolNumber` → `policyNumber`). Reuse existing distributor schemas as the projection targets.
- **Mirror**: `backend/app/schemas/target_distributor_a.json` (target shape)
- **Validate**: JSON parses.

### Task 4: Stage-result `attempt` versioning
- **File**: `backend/app/models/run.py` + migration
- **Action**: UPDATE / CREATE
- **Implement**: Add `attempt: int = 1` to `StageResult`. Re-runs (re-projection here, redeploy in Phase 4) insert a new row with `attempt = max(existing)+1` rather than appending an ambiguous duplicate. "Current" = highest attempt per (run_id, stage, distributor). Add a helper `latest_stage(run_id, stage, session)`.
- **Mirror**: `backend/app/models/run.py:69-75`
- **Validate**: `cd backend && uv run alembic upgrade head`

### Task 5: Fan-out node in the graph (with partial-failure policy)
- **File**: `backend/app/graph/build.py`
- **Action**: UPDATE
- **Implement**: Add a `project_node` after test approval (in the `resume_run` completion path, before marking `completed`). For each `DistributorView` matching the run's `lob`/`canonical_schema_id`: build the CDM record from approved mappings, then `project(view, cdm_record)`, store as `StageResult(stage="project", attempt=…, payload={"distributor": view.name, "output": ...})`. **No LLM calls.**
  - **Partial-failure policy** (decided): a single distributor projection failure does NOT fail the run. Catch per-view, store `payload={"distributor": name, "error": str(e)}`, log an `AuditEvent`, continue other distributors. Run completes if ≥1 projection succeeded; if ALL fail, mark run `failed`.
- **Mirror**: `backend/app/graph/build.py:301-326` (build_node), `:631-644` (completion path)
- **Validate**: `cd backend && uv run pytest`

### Task 6: Outputs endpoint
- **File**: `backend/app/routers/pipeline.py`
- **Action**: UPDATE
- **Implement**: `GET /runs/{id}/outputs` → list of `{distributor, output | error}` from the latest-attempt `"project"` StageResults.
- **Mirror**: `backend/app/routers/pipeline.py:118-147`
- **Validate**: `cd backend && uv run pytest`

### Task 7: Frontend — outputs panel
- **File**: `frontend/src/components/OutputsPanel.tsx`, `frontend/src/pages/RunPage.tsx`, `frontend/src/api.ts`
- **Action**: CREATE / UPDATE
- **Implement**: Add `getRunOutputs(runId)` to `api.ts`. New `OutputsPanel` lists each distributor's normalized JSON output (or its error). Render the `project` stage in the timeline and the panel on completed runs.
- **Mirror**: `frontend/src/pages/RunPage.tsx:86-110` (timeline + table section), `frontend/src/components/AuditLog.tsx`
- **Validate**: `cd frontend && npm run build && npm test`

### Task 8: Seed views + tests
- **File**: `backend/app/seed.py`, `backend/tests/pipeline/test_projection.py`
- **Action**: UPDATE / CREATE
- **Implement**: Seed distributor_a + distributor_b views for Life. Test: build a CDM record, project to both distributors, assert both outputs correct and that the projection path made zero agent/LLM calls (assert no new `LLMCall` rows).
- **Mirror**: `backend/tests/agents/test_transform_apply.py`, `backend/app/seed.py:9-28`
- **Validate**: `cd backend && uv run pytest`

---

## Validation

```bash
cd backend && uv run alembic upgrade head && uv run pytest
```

## Risks

| Risk | Mitigation |
|------|------------|
| CDM record assembly duplicates build logic | Extract a shared `cdm_record_from_run(run_id, session)` helper used by both build and projection. |
| Distributor needs a field the CDM lacks | Projection leaves it absent + flags it; surfaces a CDM gap to fix in Phase 1 schema. |
| Fan-out cost creep | Hard rule + test: projection node makes zero LLM calls. |

## Acceptance Criteria

- [ ] `DistributorView` table migrated + seeded for ≥2 distributors
- [ ] One carrier run yields ≥2 distributor outputs via `GET /runs/{id}/outputs`
- [ ] Projection path makes **zero** LLM calls (asserted in test)
- [ ] Adding a new distributor view requires no carrier-side re-run
- [ ] One distributor failure doesn't fail the run; per-view error stored + audited
- [ ] Re-projection writes a new `attempt`, not a duplicate stage row
- [ ] Outputs panel shows each distributor's normalized output in the UI
- [ ] `uv run pytest` + `npm test` green
