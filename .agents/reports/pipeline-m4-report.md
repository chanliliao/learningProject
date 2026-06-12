# Implementation Report

**Plan**: `.agents/plans/2026-06-06-pipeline-m4-support-rag.plan.md`
**Branch**: `feat/pipeline`
**Status**: COMPLETE

## Summary

Completed the six-stage pipeline with Read & Interpret node, LlamaIndex+Qdrant RAG layer, Support chat agent + API, Ragas evaluation, and support chat UI.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1.1 | Interpret node | `backend/app/agents/interpret.py` | ✅ |
| 1.2 | Insert interpret into graph | `backend/app/graph/build.py` | ✅ |
| 2.1 | Add llama-index, ragas deps | `backend/pyproject.toml` | ✅ |
| 2.2 | Index + query a run | `backend/app/rag/index.py` | ✅ |
| 3.1 | Support agent (RAG + tools) | `backend/app/agents/support.py` | ✅ |
| 3.2 | Support API | `backend/app/routers/support.py`, `main.py` | ✅ |
| 3.3 | Index on run completion | `backend/app/graph/build.py` | ✅ |
| 4.1 | Ragas RAG eval | `backend/eval/ragas_eval.py` | ✅ |
| 5.1 | Support chat UI | `frontend/src/components/SupportChat.tsx`, `api.ts`, `RunPage.tsx` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend tests | ✅ 72 passed, 1 skipped |
| Frontend tests | ✅ 15 passed |

## Files Changed

| File | Action |
|------|--------|
| `backend/app/agents/base.py` | UPDATE — added `meaning`, `rules` to `InterpretedField` |
| `backend/app/agents/interpret.py` | CREATE |
| `backend/app/agents/map.py` | UPDATE — accept `interpreted` context param |
| `backend/app/agents/support.py` | CREATE |
| `backend/app/graph/build.py` | UPDATE — interpret node, `_index_completed_run`, `resume_run` qdrant params |
| `backend/app/rag/__init__.py` | CREATE |
| `backend/app/rag/index.py` | CREATE |
| `backend/app/routers/support.py` | CREATE |
| `backend/app/main.py` | UPDATE — include support router |
| `backend/eval/ragas_eval.py` | CREATE |
| `backend/pyproject.toml` | UPDATE — llama-index, ragas deps |
| `frontend/src/api.ts` | UPDATE — `askSupport`, `EditIntent`, `SupportResponse` types |
| `frontend/src/components/SupportChat.tsx` | CREATE |
| `frontend/src/pages/RunPage.tsx` | UPDATE — mount SupportChat when completed |

## Deviations from Plan

1. **`query_run` is sync** — LlamaIndex's `aretrieve` requires an async Qdrant client; the in-memory `QdrantClient` is sync-only. Used sync `retriever.retrieve()` instead of `aretrieve()`.
2. **Ragas pinned to `<0.3`** — ragas 0.4.x has broken `langchain_community` import. Pinned to `0.2.x`. Test gated with `skipif` and uses fallback mock path.
3. **`propose_edit` is a pure function** — Plan said to make it a PydanticAI tool; implemented as a standalone helper returning an edit intent dict (avoids coupling to DB). API consumers call the existing M2 field-edit endpoint to apply.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/agents/test_interpret.py` | interpret_fields returns InterpretedField list + logs LLMCall |
| `tests/graph/test_graph_interpret.py` | graph has interpret stage between extract and map |
| `tests/rag/test_index.py` | index_run + query_run with in-memory Qdrant + MockEmbedding |
| `tests/agents/test_support.py` | answer_question returns string + logs; propose_edit returns intent |
| `tests/routers/test_support_api.py` | POST /runs/{id}/support 200 with answer; 404 for missing run |
| `tests/graph/test_index_on_complete.py` | completed run gets indexed into Qdrant |
| `tests/eval/test_ragas.py` | fallback report shape when ragas unavailable |
| `frontend/src/components/SupportChat.test.tsx` | submit question renders answer; Apply button calls editField |
