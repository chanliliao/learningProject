# Implementation Report

**Plan**: `.agents/plans/2026-06-06-pipeline-m2-confidence-review.plan.md`
**Branch**: N/A (no git repo)
**Status**: COMPLETE

## Summary

Implemented hybrid confidence scoring, LangGraph resume-on-approval, a review API (field edit, stage approve/reject), and a React review console (upload → poll → field review → approve → audit log).

## Tasks Completed

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 1.1 | Confidence module | `backend/app/pipeline/confidence.py` | ✅ |
| 1.2 | Apply confidence in map node | `backend/app/graph/build.py` | ✅ |
| 2.1 | Resume helper | `backend/app/graph/build.py` | ✅ |
| 2.2 | Review API | `backend/app/routers/review.py`, `backend/app/main.py` | ✅ |
| 2.3 | Audit + confidence in run fetch | `backend/app/routers/pipeline.py` | ✅ |
| 3.1 | Router + run API client | `frontend/src/api.ts`, `frontend/src/main.tsx` | ✅ |
| 3.2 | Upload page | `frontend/src/pages/UploadPage.tsx` | ✅ |
| 3.3 | Run page | `frontend/src/pages/RunPage.tsx` | ✅ |
| 3.4 | Field review table | `frontend/src/components/FieldReviewTable.tsx` | ✅ |
| 3.5 | Audit log component | `frontend/src/components/AuditLog.tsx` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend tests | ✅ 44 passed |
| Frontend tests | ✅ 9 passed |
| Frontend build (`tsc -b && vite build`) | ✅ |

## Files Changed

| File | Action | Notes |
|------|--------|-------|
| `backend/app/pipeline/__init__.py` | CREATE | package init |
| `backend/app/pipeline/confidence.py` | CREATE | `score_mapping` — heuristic+LLM hybrid |
| `backend/app/graph/build.py` | UPDATE | confidence scoring in map_node; `resume_run` |
| `backend/app/routers/review.py` | CREATE | PATCH field, POST approve/reject stage |
| `backend/app/routers/pipeline.py` | UPDATE | audit in response; `await session.commit()` after start_run |
| `backend/app/main.py` | UPDATE | register review router |
| `backend/tests/pipeline/test_confidence.py` | CREATE | 6 tests |
| `backend/tests/agents/test_map_confidence.py` | CREATE | 1 test |
| `backend/tests/graph/test_resume.py` | CREATE | 2 tests |
| `backend/tests/routers/test_review_api.py` | CREATE | 4 tests |
| `backend/tests/routers/test_pipeline_api.py` | UPDATE | assert audit + confidence in response |
| `frontend/package.json` | UPDATE | added react-router-dom |
| `frontend/src/api.ts` | UPDATE | full run + review API |
| `frontend/src/main.tsx` | UPDATE | react-router-dom setup |
| `frontend/src/pages/UploadPage.tsx` | CREATE | upload form |
| `frontend/src/pages/RunPage.tsx` | CREATE | timeline + polling + approve/reject |
| `frontend/src/components/FieldReviewTable.tsx` | CREATE | inline edit + flag highlight |
| `frontend/src/components/AuditLog.tsx` | CREATE | read-only event list |
| `frontend/src/pages/UploadPage.test.tsx` | CREATE | 2 tests |
| `frontend/src/pages/RunPage.test.tsx` | CREATE | 2 tests |
| `frontend/src/components/FieldReviewTable.test.tsx` | CREATE | 3 tests |
| `frontend/src/components/AuditLog.test.tsx` | CREATE | 1 test |

## Deviations from Plan

- **Missing `listTargetSchemas` backend endpoint**: Plan calls `GET /schemas` in `api.ts`, but no `/schemas` route exists yet in the backend. The frontend call is wired; the backend route is left for M3 or whenever schemas are managed via API. The UploadPage gracefully handles empty schema list.
- **`resume_run` checkpointer parameter**: Plan says "load from checkpoint" but `MemorySaver` is in-memory only — the same instance must be passed. In production a persistent checkpointer (e.g., Redis) would solve this. Injected via dependency override in tests.
- **`pipeline.py` missing `await session.commit()`**: Found and fixed — `start_run` uses `flush()` but the handler never committed, rolling back all graph-written rows on session close.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/pipeline/test_confidence.py` | exact match high score, type mismatch flag, required missing, enum violation, enum valid, numeric coerce |
| `tests/agents/test_map_confidence.py` | map node sets confidence and type_mismatch flag |
| `tests/graph/test_resume.py` | approve→completed, reject→failed |
| `tests/routers/test_review_api.py` | edit field, approve, reject, 404 on missing run |
| `tests/routers/test_pipeline_api.py` | (updated) assert audit + confidence in GET response |
| `src/pages/UploadPage.test.tsx` | renders form, submits and navigates |
| `src/pages/RunPage.test.tsx` | timeline renders, approve calls API |
| `src/components/FieldReviewTable.test.tsx` | columns render, edit+save calls API, flagged row highlighted |
| `src/components/AuditLog.test.tsx` | rows with actor/action in order |
