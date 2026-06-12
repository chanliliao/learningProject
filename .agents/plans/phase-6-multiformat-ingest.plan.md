# Plan: Phase 6 — Multi-Format Document Ingestion

## Summary

Broaden inputs to match InfrasAI's breadth: ACORD XML (have), text-based PDF, scanned PDF (OCR), and Excel/CSV. Add a format-router that detects the input type and dispatches to the right extractor, all normalizing into the existing `list[ExtractedField]` shape so the rest of the pipeline is unchanged. PDF/scanned ingestion uses **OpenRouter vision/PDF** (vision LLM + `mistral-ocr` fallback) — reusing the existing `OPENROUTER_API_KEY`, no new OCR engine or secret. Includes one sample document per format per LOB.

## User Story

As a carrier onboarding engineer
I want to submit requirements as PDF, scanned forms, or spreadsheets — not just XML
So that the platform ingests real-world document formats without manual conversion

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | HIGH |
| Systems Affected | extract layer, llm/client (vision), format router, upload router, deps, samples |
| Jira Issue | N/A |

---

## Patterns to Follow

### Current extractor contract (all formats must produce this)
```python
# SOURCE: backend/app/agents/extract.py:62-88
def extract(xml_str: str) -> list[ExtractedField]:
    # returns list[ExtractedField(path, value, inferred_type)]
```

### ExtractedField shape
```python
# SOURCE: backend/app/agents/base.py:11-22
class ExtractedField(BaseModel):
    path: str; value: str; inferred_type: str
```

### LLM client (extend for vision)
```python
# SOURCE: backend/app/llm/client.py  (_model, build_agent, run_structured)
# OpenRouter base_url already configured: config.py:42
```

### Upload entry point
```python
# SOURCE: backend/app/routers/pipeline.py:86-96  (file.read → start_run)
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `backend/pyproject.toml` | UPDATE | Add `pdfplumber`, `openpyxl` |
| `backend/app/agents/extract_pdf.py` | CREATE | Text-PDF extractor (pdfplumber) |
| `backend/app/agents/extract_vision.py` | CREATE | Scanned-PDF via OpenRouter vision/mistral-ocr |
| `backend/app/agents/extract_tabular.py` | CREATE | Excel/CSV extractor (openpyxl) |
| `backend/app/agents/ingest.py` | CREATE | Format router: detect type → dispatch → `ExtractedField[]` |
| `backend/app/llm/client.py` | UPDATE | Add `run_vision()` for image/PDF input |
| `backend/app/routers/pipeline.py` | UPDATE | Route upload through `ingest()` not raw `extract()` |
| `backend/app/graph/build.py` | UPDATE | Store source bytes + format; extract/test use `ingest` |
| `backend/app/schemas/samples/` | CREATE | One sample per format per LOB |
| `backend/tests/agents/test_ingest.py` | CREATE | Each format → ExtractedField[] |

---

## Tasks

### Task 1: Deps
- **File**: `backend/pyproject.toml`
- **Action**: UPDATE — add `"pdfplumber>=0.11"`, `"openpyxl>=3.1"`.
- **Validate**: `cd backend && uv sync`

### Task 2: Text-PDF extractor
- **File**: `backend/app/agents/extract_pdf.py`
- **Action**: CREATE
- **Implement**: `def extract_pdf(data: bytes) -> list[ExtractedField]`. Use `pdfplumber` to pull text + tables; build dotted paths from page/section/label (e.g. `page1.Policy.PolicyNumber`). Reuse `_infer_type` from `extract.py`. Raise `ExtractError` on empty.
- **Mirror**: `backend/app/agents/extract.py:62-88`
- **Validate**: `cd backend && uv run pytest tests/agents/test_ingest.py -k pdf`

### Task 3: Vision/OCR extractor (OpenRouter)
- **File**: `backend/app/agents/extract_vision.py`, `backend/app/llm/client.py`
- **Action**: CREATE / UPDATE
- **Implement**:
  - `client.py`: `async def run_vision(file_bytes, mime, prompt, *, run_id, session, mode) -> dict` — sends the document to a vision-capable OpenRouter model (PDF native + `mistral-ocr` fallback per OpenRouter PDF docs). Logs `LLMCall` like `run_structured`. In `mode="test"`, return a deterministic stub (no API).
  - `extract_vision.py`: `async def extract_vision(data, mime) -> list[ExtractedField]` — prompt the vision model to return structured `{path, value}` pairs; coerce to `ExtractedField` with `_infer_type`.
- **Mirror**: `backend/app/llm/client.py` (`run_structured` logging), `backend/app/agents/extract.py` (output shape)
- **Validate**: `cd backend && uv run pytest tests/agents/test_ingest.py -k vision`

### Task 4: Tabular extractor
- **File**: `backend/app/agents/extract_tabular.py`
- **Action**: CREATE
- **Implement**: `def extract_tabular(data: bytes, filename: str) -> list[ExtractedField]`. Excel via `openpyxl`, CSV via stdlib `csv`. Path = `sheet.row{N}.{column}` or `row{N}.{column}`. Type-infer each cell.
- **Mirror**: `backend/app/agents/extract.py:19-36` (`_infer_type`)
- **Validate**: `cd backend && uv run pytest tests/agents/test_ingest.py -k tabular`

### Task 5: Format router
- **File**: `backend/app/agents/ingest.py`
- **Action**: CREATE
- **Implement**: `async def ingest(data: bytes, filename: str, *, mode=None, run_id=None, session=None) -> list[ExtractedField]`. Detect by extension + magic bytes: `.xml`→`extract`; `.pdf`→ try `extract_pdf`, if near-empty text fall back to `extract_vision`; `.xlsx/.csv`→`extract_tabular`. Single entry point; returns the uniform contract.
- **Mirror**: `backend/app/agents/extract.py:62-88`
- **Validate**: `cd backend && uv run pytest tests/agents/test_ingest.py`

### Task 5b: LOB detection for non-XML
- **File**: `backend/app/agents/classify.py` (from Phase 1), `backend/app/routers/pipeline.py`
- **Action**: UPDATE
- **Implement**: Phase 1's `classify_lob` takes `ExtractedField[]`, so it already works for PDF/Excel once `ingest` produces fields — no XML namespace needed. Confirm the upload flow runs `ingest` → `classify_lob` when the user didn't pick an LOB. The user-override dropdown (Phase 1 Task 8) still wins for any format.
- **Mirror**: `backend/app/agents/classify.py` (Phase 1)
- **Validate**: `cd backend && uv run pytest tests/agents/test_ingest.py -k lob`

### Task 6: Wire into pipeline
- **File**: `backend/app/routers/pipeline.py`, `backend/app/graph/build.py`
- **Action**: UPDATE
- **Implement**: Store raw bytes + filename on `PipelineRun` (add `source_bytes`/`source_format`; XML stays in `source_xml` for back-compat). `extract_node` and `test_node` call `ingest(...)` instead of `extract(...)`. Keep XML path unchanged when format is XML.
- **Mirror**: `backend/app/graph/build.py:105-141` (extract_node), `:327-358` (test_node)
- **Validate**: `cd backend && uv run pytest`

### Task 7: Samples + tests
- **File**: `backend/app/schemas/samples/`, `backend/tests/agents/test_ingest.py`
- **Action**: CREATE
- **Implement**: One sample per format per LOB where meaningful (e.g. `life.pdf`, `life.xlsx`, `pc.pdf`, `annuity.pdf`, `group_health.xlsx`, plus a scanned-style PDF for the vision path). Tests assert each yields `ExtractedField[]` with sane paths/types (vision test in `mode="test"`).
- **Mirror**: `backend/tests/agents/test_extract.py`
- **Validate**: `cd backend && uv run pytest`

---

## Validation

```bash
cd backend && uv sync && uv run pytest
```

## Risks

| Risk | Mitigation |
|------|------------|
| PDF layout variety | pdfplumber + vision fallback for anything text-extraction misses. |
| Vision cost on every PDF | Try cheap text extraction first; vision only when text is empty/garbled. |
| Binary in `source_xml` | Add dedicated `source_bytes`/`source_format`; don't overload the XML column. |
| Tests need real PDFs | Generate tiny fixtures programmatically or commit small samples; vision path stubbed in test mode. |

## Acceptance Criteria

- [ ] XML, text-PDF, scanned-PDF (OCR), Excel/CSV all ingest to `ExtractedField[]`
- [ ] OCR uses OpenRouter (`OPENROUTER_API_KEY`) — no new secret/engine
- [ ] One sample per format per LOB flows through extract
- [ ] Format router auto-detects + dispatches correctly
- [ ] `uv run pytest` green
