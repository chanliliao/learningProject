# Code Review: Pipeline M2 Confidence Scoring + Review Gates

**Scope**: feat/pipeline branch — M2 Confidence Scoring + Review Gates (vs M2 plan at
`.agents/plans/completed/2026-06-06-pipeline-m2-confidence-review.plan.md`)
**Recommendation**: NEEDS WORK — one critical missing endpoint blocks the upload flow at runtime

---

## Summary

M2 delivers hybrid confidence scoring, `resume_run`, review API (edit/approve/reject), and the full
React review console (UploadPage, RunPage, FieldReviewTable, AuditLog). All 44 backend tests and 9
frontend tests pass; frontend build is clean. One critical gap: `GET /schemas` is called by the
frontend but the endpoint does not exist in the backend, making the UploadPage non-functional at
runtime. The `edit_field` endpoint does not re-score after edits (plan spec requires it). The rest
is minor.

---

## Issues Found

### Critical

1. **`GET /schemas` endpoint missing — UploadPage non-functional at runtime**
   - `frontend/src/api.ts:55` — `listTargetSchemas()` fetches `GET /schemas`
   - No route for `/schemas` exists in any backend router
   - At runtime the schema `<select>` never populates; the Start button sends no schema ID
   - Fix: add `GET /schemas` to `pipeline.py` (or a new `schema.py` router):
     ```python
     @router.get("/schemas")
     async def list_schemas(session: AsyncSession = Depends(get_session)):
         schemas = (await session.exec(select(TargetSchema))).all()
         return [{"id": s.id, "name": s.name, "version": s.version} for s in schemas]
     ```
   - Note: test suite never hit this because `UploadPage.test.tsx` mocks `listTargetSchemas`

### High

2. **`review.py:edit_field` — no re-score after edit (plan spec Task 2.2)**
   - Plan: "update mapping, re-score via `score_mapping`, set `status='edited'`"
   - Actual: `status="edited"` is set, ReviewAction + AuditEvent written, but `score_mapping`
     never called — `confidence` and `flags` stay as the LLM-original values
   - If user corrects a type mismatch (changes `target_path`), the `type_mismatch` flag persists
   - Fix: after updating `fm.target_path`/`fm.transform`, call `score_mapping(...)` and update
     `fm.confidence` and `fm.flags`; requires the source field info (can look it up from the
     `FieldMapping.source_path` against the run's `source_xml` or use stored `source_type`)

3. **`graph/build.py:221-222` — bare `except Exception: pass` in `resume_run`**
   - After approve, `compiled.ainvoke(Command(resume=...))` is wrapped in bare
     `except Exception: pass` — any real failure in the resumed graph is silently swallowed
   - Same pattern as M1's `start_run` bug (flagged in M1 review, fixed to `NodeInterrupt`),
     but the fix wasn't applied to the new `resume_run` function
   - After approval the graph hits `END` directly so `NodeInterrupt` won't fire — the bare
     except serves no purpose and masks bugs
   - Fix: remove the try/except entirely, or at minimum `except NodeInterrupt: pass` with
     a comment explaining why

### Medium

4. **`graph/build.py:215-217` — `schema` loaded in `resume_run` but never used**
   - `schema = (await session.exec(select(TargetSchema)...)).first()` is assigned but not
     passed to `build_pipeline` or used anywhere
   - Dead code; misleads future readers into thinking mode is applied on resume
   - Fix: remove the `schema` load

5. **`approve_stage` / `reject_stage` — no guard against double-approval or wrong-state**
   - Approving a run that is already `completed` or `failed` calls `resume_run` again,
     potentially writing duplicate AuditEvents and leaving the run in an inconsistent state
   - Fix: check `run.status == "awaiting_review"` before proceeding; return 409 if not

6. **Frontend confidence threshold hardcoded at 0.7 vs backend setting of 0.8**
   - `frontend/src/components/FieldReviewTable.tsx:30` — flags rows when `confidence < 0.7`
   - `backend/app/config.py:17` — `confidence_threshold: float = 0.8`
   - Threshold is not exposed by the API, so frontend and backend disagree on what "low
     confidence" means
   - Fix for M2: either expose it via `GET /health` or a settings endpoint, or align the
     hardcoded value to `0.8`

7. **`FieldReviewTable.tsx:19` — `transform` setter discarded; transform field not editable**
   - `const [transform] = useState(mapping.transform ?? '')` — destructuring without setter
   - Transform is sent in `editField(...)` but can never change in the UI
   - Fix: `const [transform, setTransform] = useState(...)` and add a second input for transform,
     or drop transform from the edit call entirely

### Suggestions

- `resume_run:edits` param is accepted but `approve_stage`/`reject_stage` never pass it. The
  per-field edits at approval time are wired in `resume_run` but unreachable from the API. Fine
  for M2 (editing is a separate `PATCH /fields`), but add a `# edits: reserved for M3 batch edit`
  comment so it's not mistaken for an active path.

- `RunPage.tsx:18-19` — polling interval returns `POLL_INTERVAL` (2 s) for both `running` AND
  `awaiting_review`. While awaiting review the user is expected to interact — continuous 2 s polling
  during a human decision session is unnecessary noise. Consider polling only on `running`.

- `test_pipeline_api.py` — Task 2.3 said to extend it to assert `audit` array and
  `confidence`/`flags` on mappings in `GET /runs/{id}`. The test was not updated; it doesn't assert
  those fields exist. They're present in the code and tested indirectly via the review API test, but
  explicit coverage is missing.

---

## Validation Results

| Check | Status |
|-------|--------|
| Backend tests (pytest) | PASS — 44/44 |
| Frontend tests (vitest) | PASS — 9/9 |
| Frontend build (tsc + vite) | PASS |

---

## What's Good

- Confidence module is clean: two-level scoring (heuristic + LLM blend), named constants for
  weights, all four heuristics (type, name, required, enum) covered with good test cases
- `score_mapping` integrated directly in `map_node` (not scattered across `map.py` + `graph/build.py`)
- `resume_run` correctly handles reject (no `ainvoke`) vs approve (resume with `Command`)
- `review.py` endpoints use `session.flush()` before `resume_run` so ReviewAction is visible
  to the graph during resume — correct ordering
- `GET /runs/{id}` now returns `audit` array — Task 2.3 implemented
- All frontend pages use TanStack Query (`useQuery`, `useMutation`) as required by M2 conventions
- `FieldReviewTable` highlights low-confidence rows with `bg-red-50` and renders flag badges
- Frontend tests mock at `../api` module boundary — no network calls, clean isolation
- `AuditLog` component is simple, correct, and well-tested

---

## Recommendation

Fix issue #1 (`GET /schemas`) before any manual testing — the upload flow is dead without it.
Fix issue #2 (re-score on edit) and #3 (bare except in resume_run) before M3. Items #4–#7 are
low blast-radius and can be batched at M3 start alongside the `_engine` global fix (M1 High #3,
still open).
