# Code Review: Pipeline M4 Read & Interpret + Support RAG + Ragas

**Scope**: feat/pipeline branch — M4 (vs M4 plan at
`.agents/plans/completed/2026-06-06-pipeline-m4-support-rag.plan.md`)
**Recommendation**: NEEDS WORK — `proposed_edits` is dead end-to-end; Apply button in SupportChat
has no backend data to trigger

---

## Summary

M4 delivers the interpret node (`interpret.py`), RAG layer (`rag/index.py` via LlamaIndex + Qdrant),
support agent (`support.py`), `POST /runs/{id}/support`, Ragas eval (`ragas_eval.py`), and the
SupportChat UI. All 72 backend tests pass (1 skipped — ragas network test, expected), 15 frontend
tests pass, and the frontend build is clean. Three M3 issues were fixed in this milestone (stage
hardcoding in RunPage, test_node silent fallback, polling during awaiting_review). One high issue
blocks the proposed-edit flow: `answer_question` has no PydanticAI tools registered, so
`proposed_edits` is always `[]` and the Apply button is permanently a no-op.

---

## M3 Issues — Disposition

| M3 Issue | Status |
|----------|--------|
| RunPage hardcodes `stage='map'` (High) | FIXED — `pendingStage` derived from `stage_results` |
| `test_node` silent empty-spec fallback (Medium) | FIXED — `raise RuntimeError` if `build_stage` is None |
| Polling during `awaiting_review` (Medium) | FIXED — polls only when `status === 'running'` |
| Calibration uses raw `llm_confidence` (Medium) | NOT FIXED — `runner.py:78` unchanged |
| Only 2 golden records vs plan's ~10 (Medium) | NOT FIXED — still 2 records |

---

## Issues Found

### Critical

None.

### High

1. **`support.py:48-61` / `routers/support.py:76` — `proposed_edits` always empty**
   - `answer_question` calls `build_agent(SupportAnswer, system=_SYSTEM, mode=mode)` where
     `SupportAnswer` has only one field: `answer: str`
   - No PydanticAI tools are registered on the agent — `lookup_mapping` and `propose_edit` from the
     plan spec are not wired in
   - `propose_edit(...)` exists as a standalone function but is never called by the agent
   - `routers/support.py:76` returns `SupportResponse(answer=answer)` — `proposed_edits` defaults
     to `[]` and stays empty on every request
   - Frontend `SupportChat` renders an Apply button only when `proposed_edits.length > 0`, which
     never happens — the Apply path from the spec (proposed edits re-enter M2 field-edit endpoint) is
     dead end-to-end
   - Plan spec: "two tools — `lookup_mapping(field)` (reads DB) and `propose_edit(field, change)`
     (returns an edit intent only)"
   - Fix: register `lookup_mapping` and `propose_edit` as PydanticAI tools on the support agent;
     change `SupportAnswer` to include a `proposed_edits: list[EditIntent]` field; propagate through
     the router response

### Medium

2. **`build.py:344` — `resume_run` calls `build_pipeline` without `mode` parameter**
   - `compiled = build_pipeline(session, checkpointer)` — `mode` not forwarded
   - `resume_run` accepts `mode: str | None = None` but never uses it
   - No current breakage: nodes after interrupts (`build_node`, `test_node`) don't call LLMs, so
     TestModel is never needed during resume
   - Fragile: any future LLM step after an interrupt would silently use production LLM mode even in
     tests
   - Fix: pass `mode=mode` to `build_pipeline` in `resume_run:344`

3. **`ragas_eval.py:13-27` — broad `except Exception` swallows execution errors**
   - The entire try block covers both the import and the evaluation execution
   - If ragas is installed but `evaluate(dataset, metrics=...)` raises (schema change, metric error,
     network timeout), the exception is silently swallowed and mock scores (average of `_score`
     fields) are returned — indistinguishable from a real score of 0.85
   - Fix: separate the import guard (`if not RAGAS_IMPORTABLE: return fallback`) from the execution;
     only catch `ImportError` for the fallback, let execution errors propagate

4. **`eval/__main__.py` — missing `--ragas` flag**
   - Plan: "Wire into `eval/__main__.py` as an optional section (`--ragas`)"
   - Current `__main__.py` runs the custom precision/recall eval only; no argparse, no Ragas section
   - Fix: add `argparse` with `--ragas` flag; when present, run `ragas_eval.run_ragas(...)` on a
     small Q&A set from the run and print the scores

5. **`routers/support.py:13-34` — embed model + Qdrant client factory duplicated from `rag/index.py`**
   - `_get_embed_model` and `_get_client` in `rag/index.py` are identical to `get_embed_model` and
     `get_qdrant_client` in `routers/support.py`
   - Changes to the OpenRouter → FastEmbed fallback logic must be made in two places
   - Fix: import `_get_embed_model` / `_get_client` from `rag/index.py` into the router, or expose
     them as public functions

6. **M3 carry-forward: `runner.py:78` — calibration uses raw `llm_confidence`, not hybrid score**
   - See M3 review issue #2 — unchanged

---

### Suggestions

- **`test_support_api.py:83-92` — manually indexes the run instead of testing auto-index path**:
  the test calls `index_run` directly with a hardcoded doc string after `stages/test/approve`, rather
  than relying on `_index_completed_run` being invoked inside `resume_run`. This doesn't exercise the
  integration path. `test_index_on_complete.py` does test auto-indexing separately, so this is a
  gap in the router test only.

- **`SupportChat.test.tsx` — no error state test for `ask` mutation**: test covers happy path and
  proposed-edit Apply; missing a case where `askSupport` rejects (network/500 error) and the UI
  surfaces it (or at minimum doesn't crash).

- **`test_ragas_evaluate_shape` always SKIPPED in this env**: the skip condition is
  `not RAGAS_IMPORTABLE` — ragas install fails at import time here (DeprecationWarning trace from
  langchain-community). Consider marking with `@pytest.mark.network` or adding a `conftest.py` skip
  condition so CI can gate this explicitly.

---

## Validation Results

| Check | Status |
|-------|--------|
| Backend tests (pytest) | PASS — 72/72 (1 skipped — ragas network, expected) |
| Frontend tests (vitest) | PASS — 15/15 |
| Frontend build (tsc + vite) | PASS |

---

## What's Good

- All three M3 HIGH/MEDIUM issues fixed: RunPage `pendingStage` dynamic, test_node raises instead of
  silently using empty spec, polling gated to `status === 'running'` only
- `interpret_node` correctly inserted between extract and map; `StageResult(stage="interpret")`
  persisted; `map_node` receives `interpreted` fields via state
- `_index_completed_run` called inside `resume_run` after `graph_state.next` is empty — indexing
  is triggered automatically on completion, injectable (qdrant_client, embed_model params)
- `index_run` / `query_run` use per-run Qdrant collections (`run_{id}`) — no cross-run leakage
- Test isolation is clean: `MockEmbedding(embed_dim=8)` + `QdrantClient(location=":memory:")` across
  `test_index.py`, `test_support.py`, `test_index_on_complete.py`, `test_support_api.py`
- `_get_embed_model` in `rag/index.py` correctly falls back to FastEmbed when OpenRouter fails —
  offline/CI safe
- `SupportChat.tsx` uses `useMutation` (correct per plan convention), not raw fetch+useState;
  renders proposed edits with Apply button wired to `editField` (correct audit path when data comes)
- `RunPage.tsx` mounts `<SupportChat>` only when `run.status === 'completed'` — correct gating
- `propose_edit` function returns the right shape and is tested (`test_propose_edit_returns_edit_intent`)
- ragas fallback path (`ragas_eval.py`) correctly returns mock scores when ragas is unavailable so CI
  doesn't fail on missing deps

---

## Recommendation

Fix issue #1 (tools + proposed_edits) before declaring M4 complete — it's the core feature of the
support agent. Issues #2–#5 and the two M3 carry-forwards can be batched. Issue #1 requires:
1. Register `lookup_mapping` / `propose_edit` as PydanticAI tools on the support agent
2. Update `SupportAnswer` to include `proposed_edits: list[EditIntent]`
3. Propagate `proposed_edits` through the router response
4. Add/update `test_support.py` to assert non-empty `proposed_edits` when agent triggers the tool
