# Plan: Phase 1 — Canonical Data Model (Pragmatic ACORD-Faithful Subset)

> **Vertical slice**: build this for **Life first** (one CDM + Life samples), prove Phases 1→8 on Life, then repeat the LOB-specific tasks (CDM schema, samples, views, fixtures) for P&C, Annuity, Group/Health. Tasks below are LOB-agnostic.

> **Fidelity (reconciled)**: "ACORD-faithful" = correct ACORD entity/field **names and nesting**, scoped to the **~20–30 entities the real sample docs actually use** per LOB. NOT the complete ACORD reference model (hundreds of entities). Mark unused branches as extension points. This resolves the earlier full-vs-subset contradiction in favour of the buildable subset.

## Summary

Introduce a **Canonical Data Model (CDM)** layer using ACORD-faithful structures (pragmatic subset, see note above), so every carrier document maps into ONE normalized model instead of directly into a distributor schema. This is the foundational abstraction (the N×M→N+M collapse). Adds ACORD-faithful canonical schemas per line of business (Life first; P&C, Annuities/Retirement, Group/Health/Supplemental in later slices), one industry sample document per LOB, and reorients the map agent to target the CDM. Distributor projection comes in Phase 2.

## User Story

As a platform engineer
I want carriers to map into one ACORD-faithful canonical model
So that a single mapping can later serve many distributors without rework

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY (architecture) |
| Complexity | HIGH |
| Systems Affected | models, schemas, seed, map agent, graph, sample docs, migration |
| Jira Issue | N/A |

---

## Patterns to Follow

### Versioned schema table (extend, don't replace)
```python
# SOURCE: backend/app/models/schema.py:14-35
class TargetSchema(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    tenant_id: str = "default"
    name: str
    version: str
    definition: dict = Field(sa_column=Column(JSON))
```

### Schema seeding
```python
# SOURCE: backend/app/seed.py:9-28
_SEED_DATA = [("distributor_a", "1.0", "target_distributor_a.json"), ...]
async def seed_target_schemas(session): ...
```

### Map agent target injection
```python
# SOURCE: backend/app/agents/map.py:70-77
user_msg = (f"Source fields...\nTarget JSON schema:\n{json.dumps(target_schema, indent=2)}\n\nPropose field mappings.")
```

### Sample doc location + style
```
# SOURCE: backend/app/schemas/acord_life_sample.xml  (TXLife namespace)
# SOURCE: backend/app/schemas/acord_pc_real_sample.xml  (ACORD P&C)
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `backend/app/schemas/cdm_life.json` | CREATE | ACORD-faithful canonical Life model |
| `backend/app/schemas/cdm_pc.json` | CREATE | Canonical P&C model |
| `backend/app/schemas/cdm_annuity.json` | CREATE | Canonical Annuity/Retirement model |
| `backend/app/schemas/cdm_group_health.json` | CREATE | Canonical Group/Health/Supplemental model |
| `backend/app/schemas/sample_annuity.xml` | CREATE | Industry sample: deferred annuity (TXLife) |
| `backend/app/schemas/sample_group_health.xml` | CREATE | Industry sample: group benefits census |
| `backend/app/models/schema.py` | UPDATE | Add `kind` field: `"canonical"` vs `"distributor"` |
| `backend/app/seed.py` | UPDATE | Seed the 4 CDM schemas |
| `backend/app/agents/map.py` | UPDATE | Accept a `canonical_schema` target; prompt tuning |
| `backend/app/graph/build.py` | UPDATE | Pass CDM as map target when run is CDM-mode |
| `backend/alembic/versions/xxxx_cdm_kind.py` | CREATE | Migration for `kind` column + `PipelineRun.lob` |
| `backend/app/pipeline/confidence.py` | UPDATE | Walk nested CDM schema (not flat `properties`) |
| `backend/app/agents/classify.py` | CREATE | LLM LOB classifier (user-overridable) |
| `backend/app/routers/pipeline.py` | UPDATE | Accept `lob` form field; classify as default |
| `frontend/src/pages/UploadPage.tsx` | UPDATE | LOB dropdown + canonical/distributor schema grouping |
| `frontend/src/api.ts` | UPDATE | `lob` in startRun; canonical mapping types |
| `backend/tests/agents/test_cdm_mapping.py` | CREATE | Map each LOB sample into its CDM |
| `backend/tests/pipeline/test_nested_confidence.py` | CREATE | Scoring against nested CDM schema |

---

## Tasks

### Task 1: Author the 4 canonical ACORD schemas
- **File**: `backend/app/schemas/cdm_life.json`, `cdm_pc.json`, `cdm_annuity.json`, `cdm_group_health.json`
- **Action**: CREATE
- **Implement**: JSON Schema (draft-07) per LOB using ACORD reference entity/field names — **pragmatic subset**: model only the entities the real sample docs use (~20–30), with correct ACORD naming/nesting; mark deeper ACORD branches as `// extension point`. Build **Life first**. Each models the canonical entities for that line:
  - **Life**: `Holding/Policy` (PolNumber, ProductCode, FaceAmt, PlanName, BillingMode, ContractTerm), `Party/Person` (FirstName, LastName, BirthDate, Gender, RiskClass), `Relation` (RelationRoleCode), `Coverage`.
  - **P&C**: `PersPolicy` (PolicyNumber, LOBCd, ContractTerm, CurrentTermAmt), `InsuredOrPrincipal/GeneralPartyInfo` (NameInfo, Addr), `Coverage`, `Location`, `Vehicle` (for auto).
  - **Annuity**: `Holding/Policy` annuity variant (AnnuityType, PremiumAmt, PayoutOption, SurrenderPeriod), `Party`, `Fund/SubAccount` allocations.
  - **Group/Health**: `GroupPolicy`, `Census/Member` (tiered coverage), `Plan` (PlanType, CoverageTier), `Eligibility`.
  - Use `required`, `enum` (ACORD `tc` code tables → enum values), `format: date` to match the existing `target_distributor_a.json` style.
- **Mirror**: `backend/app/schemas/target_distributor_a.json`
- **Validate**: JSON parses — `cd backend && uv run python -c "import json,glob; [json.load(open(f)) for f in glob.glob('app/schemas/cdm_*.json')]"`

### Task 2: Add two missing LOB sample documents
- **File**: `backend/app/schemas/sample_annuity.xml`, `sample_group_health.xml`
- **Action**: CREATE
- **Implement**: Realistic ACORD-style XML per LOB. Annuity = TXLife deferred annuity with premium/payout/subaccounts. Group/Health = group policy with a small member census (2–3 members, coverage tiers). Mirror the structure/namespace of existing `acord_life_sample.xml`. (Life + P&C samples already exist — now one per LOB = 4 total.)
- **Mirror**: `backend/app/schemas/acord_life_sample.xml`, `acord_pc_real_sample.xml`
- **Validate**: `cd backend && uv run python -c "from app.agents.extract import extract; print(len(extract(open('app/schemas/sample_annuity.xml').read())))"`

### Task 3: Add `kind` to schema model + migration
- **File**: `backend/app/models/schema.py`
- **Action**: UPDATE
- **Implement**: Add `kind: str = "distributor"` (values `"canonical"` | `"distributor"`) with Attributes docstring. Canonical schemas are map targets; distributor schemas are projection targets (Phase 2).
- **File**: `backend/alembic/versions/xxxx_cdm_kind.py` — CREATE migration adding the column (default `"distributor"`).
- **Mirror**: `backend/app/models/schema.py:30-35`, existing `backend/alembic/versions/c0c37cb17507_initial_schema.py`
- **Validate**: `cd backend && uv run alembic upgrade head`

### Task 4: Seed the canonical schemas
- **File**: `backend/app/seed.py`
- **Action**: UPDATE
- **Implement**: Extend `_SEED_DATA` to a 4-tuple including `kind`; add the 4 CDM rows with `kind="canonical"`. Update the loop to pass `kind`.
- **Mirror**: `backend/app/seed.py:9-28`
- **Validate**: `cd backend && uv run pytest`

### Task 5: Point the map agent at the CDM
- **File**: `backend/app/agents/map.py`, `backend/app/graph/build.py`
- **Action**: UPDATE
- **Implement**: `map_node` selects the canonical schema matching the run's LOB as the map target (instead of the distributor schema). Add LOB detection (root tag / namespace → LOB) or a `PipelineRun.lob` field set at upload. Keep the existing scoring; canonical `required`/`enum` now drive flags.
- **Mirror**: `backend/app/graph/build.py:214-279` (map_node), `backend/app/agents/map.py:70-77`
- **Validate**: `cd backend && uv run pytest tests/agents/test_cdm_mapping.py`

### Task 6: Nested-CDM confidence scoring
- **File**: `backend/app/pipeline/confidence.py`, `backend/app/graph/build.py`
- **Action**: UPDATE
- **Implement**: `score_mapping` and `map_node` currently read `target_schema["properties"]` flat (`build.py:240-241`). Full ACORD CDM is nested. Add a `resolve_schema_path(schema, dotted_path) -> prop_dict` helper that walks nested `properties`/`items` (and `$ref` if used) to fetch the target property for a dotted canonical path. Use it to feed `target_type`/`target_required`/`target_enum`. Without this, every nested CDM mapping mis-scores.
- **Mirror**: `backend/app/graph/build.py:239-254`, `backend/app/pipeline/confidence.py`
- **Validate**: `cd backend && uv run pytest tests/pipeline/test_nested_confidence.py`

### Task 7: LOB detection (LLM default + user override)
- **File**: `backend/app/agents/classify.py`, `backend/app/routers/pipeline.py`, `backend/app/models/run.py`
- **Action**: CREATE / UPDATE
- **Implement**: Add `PipelineRun.lob: str | None`. `classify.py`: `async def classify_lob(fields, *, mode) -> str` — small LLM call returning one of the 4 LOBs (works for any format, not just XML — sets up Phase 6). In `create_run`: accept optional `lob` form field; if absent, call `classify_lob` as the default. User selection always wins. Map node uses `run.lob` to pick the canonical schema.
- **Mirror**: `backend/app/agents/interpret.py` (single LLM call pattern), `backend/app/routers/pipeline.py:56-99`
- **Validate**: `cd backend && uv run pytest`

### Task 8: Frontend — LOB selector + CDM-aware upload
- **File**: `frontend/src/pages/UploadPage.tsx`, `frontend/src/api.ts`
- **Action**: UPDATE
- **Implement**: Add an LOB dropdown (Life/P&C/Annuity/Group-Health) defaulting to "Auto-detect"; pass `lob` to `startRun`. Group the schema selector by `kind` (canonical vs distributor) or hide canonical from the user (it's the internal target). Add `lob` param + canonical mapping types to `api.ts`.
- **Mirror**: `frontend/src/pages/UploadPage.tsx:56-92`, `frontend/src/api.ts:55-64`
- **Validate**: `cd frontend && npm run build && npm test`

### Task 9: Tests
- **File**: `backend/tests/agents/test_cdm_mapping.py`, `backend/tests/pipeline/test_nested_confidence.py`
- **Action**: CREATE
- **Implement**: For each of the 4 LOB samples, extract → map into its CDM (mode `"test"`), assert proposals target canonical paths and required canonical fields are covered. Separately, `test_nested_confidence` asserts `resolve_schema_path` finds a nested CDM property and scoring uses its type/required/enum.
- **Mirror**: `backend/tests/agents/test_map.py`, `backend/tests/agents/test_map_confidence.py`
- **Validate**: `cd backend && uv run pytest`

---

## Validation

```bash
cd backend && uv run alembic upgrade head && uv run pytest
```

## Risks

| Risk | Mitigation |
|------|------------|
| ACORD is huge | Resolved: pragmatic subset (~20–30 entities per LOB the samples actually use); correct ACORD naming/structure, not every optional element. Extension points marked. |
| LOB detection ambiguous | Add explicit `PipelineRun.lob` set at upload; detection is a fallback. |
| Existing distributor flow breaks | `kind` defaults to `"distributor"`; legacy runs still map to distributor schemas until Phase 2 wires projection. |

## Acceptance Criteria

- [ ] 4 canonical ACORD JSON schemas exist and validate
- [ ] One industry sample document per LOB (4 total) extracts cleanly
- [ ] `kind` column migrated; 4 canonical schemas seeded
- [ ] Each LOB sample maps into its CDM in test mode
- [ ] Confidence scoring resolves nested CDM paths correctly (not flat)
- [ ] LOB classified by LLM, overridable by user at upload
- [ ] Upload UI exposes LOB selector; canonical schemas hidden from partner choice
- [ ] `uv run pytest` + `npm test` green
