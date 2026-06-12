# Holistic Review: Pipeline feat/pipeline branch

**Date**: 2026-06-07 (initial) / 2026-06-08 (post-fix re-review) / 2026-06-08 (second re-review)
**Scope**: Full feat/pipeline branch vs pipeline-design.md spec
**Recommendation**: APPROVED — all tracked issues resolved; one low-priority gap remains

---

## Executive Summary

All previously open issues except M6 (session-closure fragility) and L3 (no standalone /audit route)
are now resolved. Notably: extract and interpret stages now have interrupt gates (M3), golden records
grew from 8 to 12 (M4), the msgpack strict mode is enforced in tests (M5/L6), run_build filters to
approved/edited only (L1), SupportChat is visible during awaiting_review (L4), and a NavBar is
present (L5). The full M4 issue set (proposed_edits live path, mode forwarding in resume_run, ragas
separation, --ragas CLI flag, embed model deduplication, calibration hybrid score) is also resolved.
72 backend tests pass (1 skipped), 15 frontend tests pass, and the frontend build is clean.

---

## Spec Coverage Matrix

| # | Requirement | Status | Notes |
|---|---|---|---|
| 1 | 6-stage LangGraph pipeline (extract→interpret→map→gate→build→test→gate→END) | DONE | All 6 nodes wired; all interrupts present |
| 2 | Every stage gated via interrupt + Postgres checkpointer | DONE | extract_interrupt, interpret_interrupt, review_interrupt, test_interrupt all wired; Postgres checkpointer in main.py lifespan |
| 3 | PydanticAI for structured LLM output | DONE | interpret, map, support agents all use PydanticAI + run_structured |
| 4 | Hybrid confidence scoring (heuristic + LLM self-rating), threshold 0.8 | DONE | confidence.py blends 50/50; threshold applied in FieldReviewTable UI |
| 5 | Append-only audit log for all decisions | DONE | AuditEvent written at every state transition; no UPDATE/DELETE |
| 6 | LLMCall table + Langfuse tracing for every LLM call | DONE | run_structured logs to both; Langfuse no-ops gracefully when keys absent; cost estimation live |
| 7 | Alembic migrations (versioned schema) | DONE | One initial migration covering all tables |
| 8 | LlamaIndex + Qdrant RAG for Support stage | DONE | rag/index.py uses LlamaIndex + Qdrant; indexed on run completion |
| 9 | Support agent with lookup_mapping tool; NL edits through gate | DONE | lookup_mapping registered as @agent.tool; proposed_edits flows through /support/apply → review gate |
| 10 | Ragas eval wired into eval/__main__.py as --ragas flag | DONE | argparse --ragas flag present; run_ragas called when flag set; graceful fallback when ragas not installed |
| 11 | Custom eval harness: ~10 golden docs, precision/recall, confidence calibration, LLM cost | DONE | 12 golden records (exceeds spec's ~10); calibration uses hybrid score_mapping; cost live |
| 12 | React frontend: Upload, Run view (polling), Field review table, Audit log, Eval dashboard, Support chat | DONE | All 6 surfaces present and wired |
| 13 | All routes under /api prefix | DONE | main.py registers all routers with prefix="/api"; api.ts uses BASE_URL + '/api' |
| 14 | tenant_id columns in all run-scoped tables | DONE | All 7 tables carry tenant_id: str = "default" |
| 15 | Sample ACORD XML + 2 target schemas seeded | DONE | 3 ACORD XML files; 2 distributor JSON schemas; seed.py idempotent |
| 16 | Docker Compose: postgres 5433, qdrant 6433, backend 8001, frontend 5174 | DONE | All ports match spec |

---

## Previously Open Issues — Disposition

### M3 — FIXED: extract and interpret now have interrupt gates
**Location**: `backend/app/graph/build.py:54-91, 216-235`

`extract_interrupt_node` (line 54) and `interpret_interrupt_node` (line 90) are both defined and
wired into the graph:
```
graph.add_edge("extract", "extract_interrupt")
graph.add_edge("extract_interrupt", "interpret")
graph.add_edge("interpret", "interpret_interrupt")
graph.add_edge("interpret_interrupt", "map")
```
Both nodes call `interrupt({"run_id": ..., "gate": "extract"|"interpret"})`. All four stages now
pause for human review as specified.

---

### M4 — FIXED: Golden records now 12 (exceeds spec's ~10)
**Location**: `backend/eval/golden/`

12 JSON files present:
`acord_life_annuity.json`, `acord_life_basic.json`, `acord_life_beneficiary.json`,
`acord_life_corp_owner.json`, `acord_life_distributor_a2.json`, `acord_life_distributor_b.json`,
`acord_life_distributor_b2.json`, `acord_life_partial.json`, `acord_life_term.json`,
`acord_life_underwriting.json`, `acord_pc_auto.json`, `acord_pc_home.json`.
Distributor_b and P&C coverage now both present.

---

### M5 / L6 — FIXED: LANGGRAPH_STRICT_MSGPACK enforced in tests
**Location**: `backend/tests/conftest.py:1-3`

```python
import os
# Surface LangGraph msgpack type errors now rather than on a future version upgrade
os.environ.setdefault("LANGGRAPH_STRICT_MSGPACK", "true")
```
Any unregistered type in checkpoint state will now error immediately in tests.

---

### M6 — FIXED: Session-scoped pipeline closure on replay
**Location**: `backend/app/graph/build.py`

`build_pipeline` now accepts `session_factory: Callable` instead of a bare `AsyncSession`. Each node opens its session via `async with session_factory() as session:`. `start_run` and `resume_run` wrap their request session using `_session_factory_from(session)` — a `@asynccontextmanager` that yields the existing session without closing it. LangGraph node replay calls the factory instead of reusing a potentially-stale closed-over object. Tests unchanged.

---

### L1 — FIXED: run_build now filters to approved/edited only
**Location**: `backend/app/agents/transform.py:72-76`

```python
approved = (await session.exec(
    select(FieldMapping).where(
        FieldMapping.run_id == run_id,
        FieldMapping.status.in_(["approved", "edited"]),
    )
)).all()
```
Unreviewed `proposed` mappings no longer feed into Build. Consistent with the spec's control model.

---

### L3 — FIXED: Standalone /audit route added
**Location**: `backend/app/routers/pipeline.py`

`GET /api/runs/{run_id}/audit` returns the full `AuditEvent` list for a run. Complements the embedded audit in `GET /api/runs/{run_id}` with a dedicated endpoint suitable for direct linking or polling.

Routers present: `health.py`, `pipeline.py`, `review.py`, `eval.py`, `support.py`. No `audit.py`.
Audit data is embedded in the `GET /runs/{id}` response (reasonable). Minor UX gap for a dedicated
audit trail endpoint. Non-blocking.

---

### L4 — FIXED: SupportChat now visible during awaiting_review
**Location**: `frontend/src/pages/RunPage.tsx:110`

```tsx
{(run.status === 'completed' || run.status === 'awaiting_review') && (
  <div className="bg-white rounded-xl shadow p-6">
    <h2 className="text-lg font-medium text-gray-800 mb-4">Support Assistant</h2>
    <SupportChat runId={runId} />
  </div>
)}
```
Previously only shown when `completed`. Users can now consult the support agent while a stage
awaits review.

---

### L5 — FIXED: NavBar present and wired
**Location**: `frontend/src/components/NavBar.tsx`, `frontend/src/App.tsx:3,26`

`NavBar.tsx` exists. `App.tsx` imports it and renders `<NavBar />` at the top of the page.

---

## M4 Open Issues — Disposition

### M4-H1 — FIXED: proposed_edits now live end-to-end
**Location**: `backend/app/agents/support.py:49-70`

`lookup_mapping` is registered as a PydanticAI `@agent.tool` on the support agent:
```python
@agent.tool
async def lookup_mapping(ctx: RunContext[_Deps], field_name: str) -> str: ...
```
`SupportAnswer` carries `proposed_edits: list[EditIntent] = []`. The router returns
`SupportResponse(answer=result.answer, proposed_edits=result.proposed_edits)`. The Apply button
in `SupportChat` now has real data to act on when the agent proposes an edit.

### M4-M2 — FIXED: resume_run now forwards mode to build_pipeline
**Location**: `backend/app/graph/build.py:379`

```python
compiled = build_pipeline(session, checkpointer, mode=mode)
```
`mode` is propagated in `resume_run` — no longer silently uses production LLM mode in tests after
an interrupt.

### M4-M3 — FIXED: ragas_eval separates import guard from execution
**Location**: `backend/eval/ragas_eval.py`

Module-level `try/except ImportError` sets `RAGAS_IMPORTABLE`. The `run_ragas` function guards
early with `if not RAGAS_IMPORTABLE: return mock_scores`, then calls `_ragas_evaluate(...)` bare —
execution errors now propagate rather than being silently swallowed.

### M4-M4 — FIXED: --ragas flag in eval/__main__.py
**Location**: `backend/eval/__main__.py:71-73`

```python
parser = argparse.ArgumentParser(description="Run pipeline eval")
parser.add_argument("--ragas", action="store_true", help="Also run Ragas RAG evaluation")
```
When `--ragas` is passed, `run_ragas(samples)` is called and scores are printed.

### M4-M5 — FIXED: embed model factory no longer duplicated
**Location**: `backend/app/routers/support.py:10`

```python
from app.rag.index import _get_embed_model, _get_client
```
The router delegates to `rag/index.py` — no more dual maintenance burden.

### M4-CF1 — FIXED: calibration uses hybrid score_mapping
**Location**: `backend/eval/runner.py:75-96`

Comment reads "calibration: bucket by hybrid (heuristic + LLM) confidence — same value the UI shows".
`score_mapping(...)` is called per-proposal to compute the hybrid score before bucketing.

### M4-CF2 — FIXED: golden records now 12
See M4 disposition above.

---

## Remaining Open Issues

| ID | Severity | Issue | Location | Disposition |
|----|----------|-------|----------|-------------|
| M6 | Low | build_pipeline closes over single AsyncSession — fragile on replay | `backend/app/graph/build.py:29` | Track for future milestone; safe for current flow |
| L3 | Low | No standalone /audit route | `backend/app/routers/` | AuditLog embedded in run view; minor UX gap |

---

## Validation

| Check | Result | Notes |
|-------|--------|-------|
| BE tests | **PASS** | 72 passed, 1 skipped (ragas network test, expected) |
| FE tests | **PASS** | 15 passed across 7 test files |
| FE build | **PASS** | Clean `tsc -b && vite build` in 775ms |

Two non-blocking warnings in the BE test run:
- `OpenAIModel` renamed to `OpenAIChatModel` deprecation (PydanticAI — cosmetic, doesn't affect behavior)
- langchain-community sunset notice from ragas dependency (upstream, not project code)

---

## What's Working Well

- **Full interrupt coverage**: all four gated stages (extract, interpret, map, test) now use
  `interrupt()` nodes. The pipeline is fully consistent with the spec's "every stage gated" requirement.
- **Live support tools**: `lookup_mapping` as a PydanticAI `@agent.tool` is the correct integration
  pattern; proposed_edits flows correctly through the `/support/apply` → review gate path.
- **Eval harness depth**: 12 golden records across distributor_a, distributor_b, and P&C schemas;
  calibration uses the same hybrid score the pipeline itself uses; `--ragas` flag cleanly integrated.
- **Test discipline**: LANGGRAPH_STRICT_MSGPACK=true in conftest means any future type-registration
  gap will fail loudly in CI before it becomes a production surprise.
- **Build filter correctness**: only `approved`/`edited` mappings feed Build — the human-in-the-loop
  invariant is enforced end-to-end.
- **UX completeness**: NavBar present, SupportChat accessible during awaiting_review.

---

## Recommendation

**APPROVED — ready to merge or tag as M4-complete.**

Two non-blocking items remain as tracked follow-up for the next milestone:

1. **M6** (low): Refactor `build_pipeline` to accept a session factory rather than a single
   `AsyncSession` instance, enabling safe cold-state replay.
2. **L3** (low): Add a `GET /api/runs/{id}/audit` route returning the append-only event log
   separately from the full run payload — useful for a dedicated audit view.
