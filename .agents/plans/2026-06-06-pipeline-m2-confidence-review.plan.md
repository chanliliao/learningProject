# Plan: Pipeline — Milestone 2 (Confidence Scoring + Review Gates + Console)

> **For implementers:** Execute in order. TDD: failing test → run (fail) → implement → run (pass) →
> commit. Builds on M0 + M1. Reference spec: `.agents/specs/2026-06-06-pipeline-design.md`.

## Summary

Make the pipeline reviewable by a human. Add **hybrid confidence scoring** (deterministic heuristics
blended with the LLM's self-rating) to every proposed `FieldMapping`, flagging low-confidence fields.
Add a **resume-on-approval review API** that advances a LangGraph run past its interrupt — per-stage
(approve / reject) and per-field for the Map stage (approve / edit / reject), writing `ReviewAction`
and append-only `AuditEvent` rows. Build the **React review console** (Tailwind + react-router):
upload a document, watch the run timeline (polling), review/edit flagged fields, approve to continue,
and read the audit log. Outcome: a full human-in-the-loop mapping workflow from upload to an approved
mapping.

## User Story

As an integration engineer
I want to see confidence-flagged mappings and approve, edit, or reject them in a UI
So that nothing goes live without my review and every decision is recorded.

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | HIGH |
| Milestone | M2 of (M0→M4) |
| Systems Affected | backend (confidence, LangGraph resume, review API), frontend (console) |
| Jira Issue | N/A |

---

## Prerequisites (from M0 + M1)

- M1: models (`PipelineRun`, `StageResult`, `FieldMapping`, `AuditEvent`, `ReviewAction`, `LLMCall`),
  Alembic, LangGraph graph (`extract→map→interrupt`), `start_run`, pipeline API
  (`POST /runs`, `GET /runs/{id}`), `confidence_threshold` setting.
- M0: frontend `src/api.ts`, Tailwind, status dashboard, CORS.

---

## Patterns to Follow

### Backend route + test
```python
# SOURCE: backend/app/main.py:1-8 / backend/tests/test_health.py:1-10
@app.get("/health")
def health() -> dict: return {"status": "ok"}
```

### Frontend component test
```tsx
# SOURCE: frontend/src/App.test.tsx:1-7
import { render, screen } from '@testing-library/react'
test('...', () => { render(<App />); expect(screen.getByRole('heading')).toBeInTheDocument() })
```
Scripts: `npm test` = `vitest run`; build = `tsc -b && vite build` (`frontend/package.json:6-13`).

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `backend/app/pipeline/confidence.py` | CREATE | Hybrid confidence scoring |
| `backend/app/agents/map.py` | UPDATE | Apply confidence + flags to proposals |
| `backend/app/agents/base.py` | UPDATE | Add scored mapping fields if needed |
| `backend/app/graph/build.py` | UPDATE | `resume_run` past interrupt; reflect review decisions |
| `backend/app/routers/review.py` | CREATE | Per-stage + per-field review endpoints |
| `backend/app/main.py` | UPDATE | Include review router |
| `frontend/package.json` | UPDATE | Add react-router-dom |
| `frontend/src/api.ts` | UPDATE | Run + review API calls |
| `frontend/src/main.tsx` | UPDATE | Router setup |
| `frontend/src/pages/UploadPage.tsx` | CREATE | Upload + start run |
| `frontend/src/pages/RunPage.tsx` | CREATE | Timeline + polling + approve |
| `frontend/src/components/FieldReviewTable.tsx` | CREATE | Per-field approve/edit/reject |
| `frontend/src/components/AuditLog.tsx` | CREATE | Audit trail view |
| tests (be + fe) | CREATE | per task |

---

## Story 1 — Hybrid confidence scoring

### Task 1.1: Confidence module

- **File:** `backend/app/pipeline/confidence.py` (CREATE)
- [ ] **Step 1 — failing test** `backend/tests/pipeline/test_confidence.py`:

```python
from app.pipeline.confidence import score_mapping

def test_exact_type_and_name_match_scores_high():
    s = score_mapping(
        source_path="Policy.PolicyNumber", source_type="str",
        target_path="policyNumber", target_type="string",
        target_required=True, target_enum=None, value="A123",
        llm_confidence=0.9,
    )
    assert s.score >= 0.8
    assert s.flags == []

def test_type_mismatch_lowers_and_flags():
    s = score_mapping(
        source_path="Policy.FaceAmount", source_type="str",
        target_path="faceAmount", target_type="number",
        target_required=True, target_enum=None, value="not-a-number",
        llm_confidence=0.9,
    )
    assert s.score < 0.8
    assert "type_mismatch" in s.flags
```

- [ ] **Step 2 — run** → FAIL.
- [ ] **Step 3 — implement** `score_mapping(...) -> ScoreResult` (pydantic: `score: float`,
  `flags: list[str]`). Heuristic signals (each 0..1, weighted, blended with `llm_confidence`):
  - `type_compatible` (str↔string, numeric value↔number, ISO date↔date) → flag `type_mismatch` if
    value can't coerce to target type;
  - `name_similarity` (normalize case/underscores, token overlap or difflib ratio);
  - `required_present` → flag `required_missing` if target required and value empty;
  - `enum_valid` → flag `enum_violation` if target enum present and value not in it.
  Final `score = 0.5*heuristic_mean + 0.5*llm_confidence` (constants named). Flag for review when
  `score < settings.confidence_threshold`.
- [ ] **Step 4 — run** → PASS. **Step 5 — commit:** `feat: add hybrid confidence scoring`

### Task 1.2: Apply confidence in Map node

- **File:** `backend/app/agents/map.py` (UPDATE)
- [ ] **Step 1 — failing test** `backend/tests/agents/test_map_confidence.py`: with `mode="test"`
  proposals + a target schema declaring types/required, call the map node path that persists
  mappings; assert each persisted `FieldMapping` has a non-null `confidence` and that a mapping with
  a type mismatch carries a `type_mismatch` flag and `status="proposed"`.
- [ ] **Step 2 — run** → FAIL.
- [ ] **Step 3 — implement** in `map.py` (or the map node in `graph/build.py` if persistence lives
  there): after getting `FieldMappingProposal`s, look up each target field's type/required/enum from
  the target JSON schema, call `score_mapping`, store `confidence` + `flags` on the `FieldMapping`.
- [ ] **Step 4 — run** → PASS. **Step 5 — commit:** `feat: score and flag mappings in map node`

---

## Story 2 — Review + resume (LangGraph)

### Task 2.1: Resume helper

- **File:** `backend/app/graph/build.py` (UPDATE)
- [ ] **Step 1 — failing test** `backend/tests/graph/test_resume.py`: build graph (MemorySaver,
  `mode="test"`), run a pipeline to the interrupt; call `resume_run(run_id, decision="approve",
  session=..., checkpointer=...)`; assert the graph completes past the interrupt, the map
  `StageResult.status` becomes `approved`, and `PipelineRun.status` becomes `completed` (M2 graph
  still ends after map until M3 adds nodes — `completed` is correct for M2).
- [ ] **Step 2 — run** → FAIL.
- [ ] **Step 3 — implement** `resume_run(run_id, decision, session, checkpointer, edits=None)`:
  load the run's `thread_id`, apply edits to `FieldMapping`s if provided, set the map
  `StageResult.status` to `approved`/`rejected`, then resume the compiled graph with
  `Command(resume=...)` from the checkpoint. On `reject`, mark run `failed` and do not resume.
- [ ] **Step 4 — run** → PASS. **Step 5 — commit:** `feat: add LangGraph resume after review`

### Task 2.2: Review API

- **Files:** `backend/app/routers/review.py` (CREATE), `backend/app/main.py` (UPDATE)
- [ ] **Step 1 — failing test** `backend/tests/routers/test_review_api.py` (TestClient, in-memory
  DB, `mode="test"`, MemorySaver): start a run to interrupt; then:
  - `PATCH /runs/{id}/fields/{field_id}` with `{target_path, transform}` → 200, mapping
    `status="edited"`, a `ReviewAction` + `AuditEvent` written.
  - `POST /runs/{id}/stages/map/approve` → 200, run resumes to `completed`.
  - `POST /runs/{id}/stages/map/reject` (separate run) → 200, run `failed`.
  - approve on a missing run → 404.
- [ ] **Step 2 — run** → FAIL.
- [ ] **Step 3 — implement** `routers/review.py`:
  - `PATCH /runs/{run_id}/fields/{field_id}`: update mapping, re-score via `score_mapping`, set
    `status="edited"`, write `ReviewAction(decision="edit")` + `AuditEvent`.
  - `POST /runs/{run_id}/stages/{stage}/approve|reject`: write `ReviewAction` + `AuditEvent`, call
    `resume_run(...)`. 404 if run/stage absent.
  Include router in `main.py`.
- [ ] **Step 4 — run** → PASS. **Step 5 — commit:** `feat: add review API (edit field, approve/reject stage)`

### Task 2.3: Expose audit + flagged fields in run fetch

- **File:** `backend/app/routers/pipeline.py` (UPDATE)
- [ ] **Step 1 — failing test** extend `test_pipeline_api.py`: `GET /runs/{id}` response includes an
  `audit` array (AuditEvent rows) and each mapping exposes `confidence` + `flags`.
- [ ] **Step 2 — run** → FAIL.
- [ ] **Step 3 — implement** add audit events + mapping confidence/flags to the run response model.
- [ ] **Step 4 — run** → PASS. **Step 5 — commit:** `feat: include audit and confidence in run response`

---

## Story 3 — React review console

### Task 3.1: Router + run API client

- **Files:** `frontend/package.json`, `frontend/src/api.ts`, `frontend/src/main.tsx` (UPDATE)
- [ ] **Step 1 — install:** `cd frontend && npm install react-router-dom`
- [ ] **Step 2 — implement** in `api.ts`: `startRun(file, targetSchemaId)`, `getRun(id)`,
  `editField(runId, fieldId, patch)`, `approveStage(runId, stage)`, `rejectStage(runId, stage)`,
  `listTargetSchemas()` — all using `VITE_API_URL`.
- [ ] **Step 3 — implement** `main.tsx`: `createBrowserRouter` with routes `/` (UploadPage),
  `/runs/:id` (RunPage). Keep the M0 dashboard at `/health` (optional).
- [ ] **Step 4 — verify:** `npm run build` passes. **Step 5 — commit:** `feat: add router and run API client`

### Task 3.2: Upload page

- **File:** `frontend/src/pages/UploadPage.tsx` (CREATE)
- [ ] **Step 1 — failing test** `frontend/src/pages/UploadPage.test.tsx`: mock `listTargetSchemas`
  + `startRun`; render; select a schema, choose a file, click Start; assert `startRun` called and
  navigation to `/runs/:id` triggered (mock `useNavigate`).
- [ ] **Step 2 — run** `npm test` → FAIL.
- [ ] **Step 3 — implement** Tailwind form: file input + schema `<select>` (from
  `listTargetSchemas`), Start button → `startRun` → navigate to run page.
- [ ] **Step 4 — run** → PASS. **Step 5 — commit:** `feat: add upload page`

### Task 3.3: Run page (timeline + polling + approve)

- **File:** `frontend/src/pages/RunPage.tsx` (CREATE)
- [ ] **Step 1 — failing test** `frontend/src/pages/RunPage.test.tsx`: mock `getRun` returning a run
  with map `awaiting_review` + flagged mappings; render; assert the stage timeline shows
  extract=approved, map=awaiting_review; assert an "Approve" button calls `approveStage`. Simulate a
  second `getRun` returning `completed` (advance polling) and assert UI updates.
- [ ] **Step 2 — run** → FAIL.
- [ ] **Step 3 — implement** Tailwind page: poll `getRun(id)` every ~2s while status is
  `running`/`awaiting_review`; render a stage timeline, the `FieldReviewTable` for the map stage, an
  Approve/Reject control, and the `AuditLog`.
- [ ] **Step 4 — run** → PASS. **Step 5 — commit:** `feat: add run page with polling and approval`

### Task 3.4: Field review table

- **File:** `frontend/src/components/FieldReviewTable.tsx` (CREATE)
- [ ] **Step 1 — failing test** `FieldReviewTable.test.tsx`: given mappings (one flagged), render a
  table with source/target/confidence/flags; editing a target path + saving calls `editField`;
  flagged rows are visually marked (assert a flag label renders).
- [ ] **Step 2 — run** → FAIL.
- [ ] **Step 3 — implement** Tailwind table; inline edit for `target_path`/`transform`; per-row
  approve/edit/reject calling the review API; highlight rows with `flags` or
  `confidence < threshold`.
- [ ] **Step 4 — run** → PASS. **Step 5 — commit:** `feat: add field review table`

### Task 3.5: Audit log component

- **File:** `frontend/src/components/AuditLog.tsx` (CREATE)
- [ ] **Step 1 — failing test** `AuditLog.test.tsx`: given audit events, render rows with actor,
  action, timestamp in order.
- [ ] **Step 2 — run** → FAIL.
- [ ] **Step 3 — implement** read-only Tailwind list of audit events.
- [ ] **Step 4 — run** → PASS. **Step 5 — commit:** `feat: add audit log component`

---

## Validation

```bash
cd backend && uv run pytest -v
cd frontend && npm test && npm run build
# Manual: upload sample XML -> review flagged fields -> approve -> run completes
```

## Acceptance Criteria

- [ ] Every proposed mapping has a hybrid `confidence` and `flags`
- [ ] Low-confidence mappings (`< threshold`) are flagged for review
- [ ] Editing a field re-scores it and writes `ReviewAction` + `AuditEvent`
- [ ] Approving the map stage resumes the LangGraph run past the interrupt
- [ ] Rejecting marks the run `failed`
- [ ] Console: upload → poll run → review/edit fields → approve → see audit log
- [ ] All backend + frontend tests pass offline
- [ ] Follows existing FastAPI + vitest patterns

---

## Out of Scope (later)

- M3: Build/Test nodes, eval harness + dashboard.
- M4: Interpret node, LlamaIndex+Qdrant Support RAG, Ragas, support chat UI.
