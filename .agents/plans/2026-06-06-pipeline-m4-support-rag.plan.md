# Plan: Pipeline — Milestone 4 (Read & Interpret + Support RAG + Ragas)

> **For implementers:** Execute in order. TDD: failing test → run (fail) → implement → run (pass) →
> commit. Builds on M0–M3. Reference spec: `.agents/specs/2026-06-06-pipeline-design.md`.

## Summary

Complete the six-stage product. Add the **Read & Interpret** node (`interpret.py`): a PydanticAI step
between Extract and Map that describes each field's meaning + business rules, giving Map better
context. Add the **RAG layer** (`rag/index.py`): index a completed run's artifacts (interpreted
fields, mappings, audit notes) into **Qdrant** via **LlamaIndex** using OpenRouter embeddings. Add
the **Support** node/agent (`support.py`): a tool-calling chat over the indexed run that answers "why
was field X mapped to Y?" and proposes plain-English edits that re-enter the M2 review gate. Add
**Ragas** evaluation for the Support answers, and a **support chat UI**. Outcome: the full
InfrasAI-style 6-stage pipeline.

## User Story

As an integration engineer
I want to ask the system, in plain English, why a mapping was made and to request edits conversationally
So that I can understand and correct the pipeline without reading raw config — with answers grounded
in the run's own data.

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | HIGH |
| Milestone | M4 of (M0→M4) |
| Systems Affected | backend (interpret node, RAG, support, Ragas), frontend (chat) |
| Jira Issue | N/A |

---

## Prerequisites (from M0–M3)

- M0: Qdrant running + `qdrant_url` setting + `qdrant-client` dep.
- M1: graph, nodes, PydanticAI client (`build_agent`/`run_structured`), `InterpretedField` model.
- M2: review API + `resume_run` + console (chat edits reuse the field edit endpoint + audit).
- M3: completed runs with mappings + audit to index.

---

## Patterns to Follow

### PydanticAI node (existing) — `app/agents/map.py` (M1): `build_agent(OutModel, system) -> run_structured`.
### Backend test — `backend/tests/test_health.py:1-10`; pytest `pyproject.toml:17-20` (offline via TestModel).
### Frontend — `src/App.test.tsx:1-7`; `npm test`=`vitest run`.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `backend/app/agents/interpret.py` | CREATE | Read & Interpret node |
| `backend/app/graph/build.py` | UPDATE | Insert interpret between extract and map |
| `backend/pyproject.toml` | UPDATE | llama-index, llama-index-vector-stores-qdrant, ragas |
| `backend/app/rag/index.py` | CREATE | LlamaIndex + Qdrant indexing/query |
| `backend/app/agents/support.py` | CREATE | Support chat agent (RAG + tools) |
| `backend/app/routers/support.py` | CREATE | POST /runs/{id}/support |
| `backend/app/main.py` | UPDATE | Include support router |
| `backend/eval/ragas_eval.py` | CREATE | Ragas RAG eval |
| `frontend/src/components/SupportChat.tsx` | CREATE | Chat UI |
| `frontend/src/pages/RunPage.tsx` | UPDATE | Mount chat for completed runs |
| `frontend/src/api.ts` | UPDATE | askSupport() |
| tests | CREATE | per task |

---

## Story 1 — Read & Interpret node

### Task 1.1: Interpret node

- **File:** `backend/app/agents/interpret.py` (CREATE)
- [ ] **Step 1 — failing test** `backend/tests/agents/test_interpret.py`: given `ExtractedField`s,
  build the agent in `mode="test"` (PydanticAI `TestModel` returns schema-valid `InterpretedFields`);
  call `interpret_fields(fields, run_id=None, session=session, mode="test")`; assert it returns a
  non-empty `list[InterpretedField]` (each with `path`, `meaning`, `rules`) and logs one `LLMCall`.
- [ ] **Step 2 — run** → FAIL.
- [ ] **Step 3 — implement** `interpret.py`: define `InterpretedFields` wrapper output model; build a
  system prompt ("explain each insurance field's meaning + constraints using ACORD context"); embed
  the extracted fields; `run_structured`. Reuse `InterpretedField` from `agents/base.py`.
- [ ] **Step 4 — run** → PASS. **Step 5 — commit:** `feat: add read & interpret node`

### Task 1.2: Insert interpret into the graph

- **File:** `backend/app/graph/build.py` (UPDATE)
- [ ] **Step 1 — failing test** `backend/tests/graph/test_graph_interpret.py`: run pipeline; assert
  order `extract→interpret→map`, an `interpret` `StageResult` is persisted, and Map receives
  interpreted fields (state contains `interpreted`).
- [ ] **Step 2 — run** → FAIL.
- [ ] **Step 3 — implement** add `interpret_node` between extract and map; pass `interpreted` into
  Map's prompt. Keep interrupts unchanged (interpret auto-advances; review still at map + test).
- [ ] **Step 4 — run** → PASS. **Step 5 — commit:** `feat: wire interpret node into graph`

---

## Story 2 — RAG layer (LlamaIndex + Qdrant)

### Task 2.1: Dependencies

- **File:** `backend/pyproject.toml` (UPDATE)
- [ ] **Step 1 — add** `llama-index-core>=0.12`, `llama-index-vector-stores-qdrant>=0.4`,
  `llama-index-embeddings-openai>=0.3` (point at OpenRouter via base_url), `ragas>=0.2`; `uv sync`.
- [ ] **Step 2 — verify** imports: `from llama_index.core import VectorStoreIndex`,
  `from llama_index.vector_stores.qdrant import QdrantVectorStore`.
- [ ] **Step 3 — commit:** `chore: add llama-index, qdrant store, ragas deps`

### Task 2.2: Index + query a run

- **File:** `backend/app/rag/index.py` (CREATE)
- [ ] **Step 1 — failing test** `backend/tests/rag/test_index.py`: use an **in-memory/local Qdrant**
  (`QdrantClient(location=":memory:")`) and a stub embedding (LlamaIndex `MockEmbedding`) so no
  network; `index_run(run_id, docs, client=..., embed_model=...)` then
  `query_run(run_id, "policy number", client=..., embed_model=...)` returns nodes containing the
  indexed text. Collection name is per-run.
- [ ] **Step 2 — run** → FAIL.
- [ ] **Step 3 — implement** `index.py`: build `QdrantVectorStore` for a per-run collection, create a
  `VectorStoreIndex` from documents built out of the run's interpreted fields + mappings + audit
  notes; `query_run` returns a retriever's nodes. Real embeddings via OpenAI-compatible OpenRouter;
  tests inject `MockEmbedding` + in-memory client.
- [ ] **Step 4 — run** → PASS. **Step 5 — commit:** `feat: add LlamaIndex+Qdrant run indexing and query`

---

## Story 3 — Support agent + API

### Task 3.1: Support agent (RAG + tools)

- **File:** `backend/app/agents/support.py` (CREATE)
- [ ] **Step 1 — failing test** `backend/tests/agents/test_support.py`: with `mode="test"` and a
  stubbed `query_run` returning a known mapping note, call `answer_question(run_id, "why is faceAmount
  mapped?", session, retriever=stub, mode="test")`; assert a non-empty answer string and one
  `LLMCall` logged. Add a test that `propose_edit(...)` returns a structured edit intent (does NOT
  write directly — must go through review).
- [ ] **Step 2 — run** → FAIL.
- [ ] **Step 3 — implement** `support.py`: a PydanticAI agent whose context is the retrieved nodes
  (`query_run`), with two tools — `lookup_mapping(field)` (reads DB) and `propose_edit(field, change)`
  (returns an edit intent only). `answer_question` runs the agent and returns text + any proposed
  edits. Edits are applied only via the M2 `PATCH /runs/{id}/fields/{id}` path (audited).
- [ ] **Step 4 — run** → PASS. **Step 5 — commit:** `feat: add support agent with RAG and propose-edit tool`

### Task 3.2: Support API

- **Files:** `backend/app/routers/support.py` (CREATE), `main.py` (UPDATE)
- [ ] **Step 1 — failing test** `backend/tests/routers/test_support_api.py` (TestClient, in-memory
  DB + in-memory Qdrant + `mode="test"`): index a completed run, `POST /runs/{id}/support`
  `{question}` → 200 with `answer` and optional `proposed_edits`. Missing run → 404.
- [ ] **Step 2 — run** → FAIL.
- [ ] **Step 3 — implement** `routers/support.py`: `POST /runs/{run_id}/support` builds/loads the run
  retriever, calls `answer_question`, returns answer + proposed edits (the UI then calls the existing
  field-edit endpoint to apply, keeping the audit gate). Include router.
- [ ] **Step 4 — run** → PASS. **Step 5 — commit:** `feat: add support chat API`

### Task 3.3: Index on run completion

- **File:** `backend/app/graph/build.py` (UPDATE)
- [ ] **Step 1 — failing test** `backend/tests/graph/test_index_on_complete.py`: when a run reaches
  `completed`, `index_run` is invoked (assert the run's collection exists / a query returns nodes).
  Inject in-memory Qdrant + MockEmbedding.
- [ ] **Step 2 — run** → FAIL.
- [ ] **Step 3 — implement** call `index_run(...)` at the end of the final node (after final
  approval) so Support has data. Guard so test/offline mode uses injected client.
- [ ] **Step 4 — run** → PASS. **Step 5 — commit:** `feat: index run artifacts on completion`

---

## Story 4 — Ragas evaluation

### Task 4.1: Ragas RAG eval

- **File:** `backend/eval/ragas_eval.py` (CREATE)
- [ ] **Step 1 — failing test** `backend/tests/eval/test_ragas.py`: with a tiny Q&A set
  `{question, answer, contexts, ground_truth}` and Ragas configured with a stub/test LLM + embeddings
  (no network), `run_ragas(samples)` returns a report dict containing `faithfulness`,
  `answer_relevancy`, `context_precision` keys. (If Ragas cannot run fully offline, gate this test
  with `@pytest.mark.skipif` on missing keys and assert the report shape with a mocked metric
  runner.)
- [ ] **Step 2 — run** → FAIL.
- [ ] **Step 3 — implement** `ragas_eval.py`: assemble a Ragas `EvaluationDataset` from a small
  golden Q&A set over a completed run, run the metrics, return the scores. Wire into
  `eval/__main__.py` as an optional section (`--ragas`).
- [ ] **Step 4 — run** → PASS. **Step 5 — commit:** `feat: add Ragas RAG evaluation`

---

## Story 5 — Support chat UI

### Task 5.1: Support chat component

- **Files:** `frontend/src/components/SupportChat.tsx` (CREATE), `frontend/src/api.ts`,
  `frontend/src/pages/RunPage.tsx` (UPDATE)
- [ ] **Step 1 — failing test** `frontend/src/components/SupportChat.test.tsx`: mock `askSupport`
  returning an answer + a proposed edit; render; type a question, submit; assert the answer renders
  and an "Apply edit" action calls `editField`.
- [ ] **Step 2 — run** `npm test` → FAIL.
- [ ] **Step 3 — implement** `askSupport(runId, question)` in `api.ts`; `SupportChat` Tailwind chat
  (message list + input); render proposed edits with an Apply button that calls the M2 `editField`
  endpoint (audited). Mount `SupportChat` in `RunPage` only when run `status==="completed"`.
- [ ] **Step 4 — run** → PASS. **Step 5 — commit:** `feat: add support chat UI`

---

## Validation

```bash
cd backend && uv run pytest -v && uv run python -m eval --ragas
cd frontend && npm test && npm run build
# Manual: complete a run -> ask "why is X mapped to Y?" -> get grounded answer -> apply an edit
```

## Acceptance Criteria

- [ ] Graph runs all six stages: `extract→interpret→map→(gate)→build→test→(gate)→END`
- [ ] Completed runs are indexed into Qdrant via LlamaIndex
- [ ] `POST /runs/{id}/support` answers grounded in the run's data and can propose edits
- [ ] Proposed edits apply only through the audited M2 field-edit path (never silently)
- [ ] Ragas reports faithfulness / answer-relevancy / context-precision
- [ ] Support chat UI renders answers and applies edits
- [ ] All backend + frontend tests pass offline (TestModel, MockEmbedding, in-memory Qdrant)
- [ ] Follows existing patterns

---

## Project complete after M4

All four pipeline milestones (plus the M0 walking skeleton) delivered: a six-stage, human-gated,
auditable ACORD→distributor schema mapping pipeline with confidence scoring, a runnable validated
transform, eval (custom + Ragas), and a RAG support agent — built on the 2026 industry stack
(LangGraph, PydanticAI, LlamaIndex, Qdrant, Langfuse).
