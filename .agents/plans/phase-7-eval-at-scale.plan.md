# Plan: Phase 7 — Eval at Scale (Regression, Drift, CI)

## Summary

Harden quality measurement so prompt/schema/rule changes can't silently break existing mappings. Grows the existing 14-fixture golden harness into per-LOB suites, adds a regression gate (compare current run vs. a stored baseline and fail on precision/recall drop), schema-drift detection (alert when a carrier doc introduces unseen fields or a CDM field changes), and CI wiring so eval runs on every change. This is the continuous-hardening phase; finalized last but informs all prior work.

> **Two metric tracks** (keep both): mapping quality uses the custom precision/recall + confidence-calibration in `eval/runner.py`; **support-agent (RAG) quality uses ragas** (`eval/ragas_eval.py` — faithfulness, answer_relevancy, context_precision). Per-LOB suites below should carry BOTH: mapping fixtures *and* support-Q&A samples scored by ragas, so the regression gate covers the support agent too.

## User Story

As a platform maintainer
I want eval to fail CI when a change degrades mapping quality or a schema drifts
So that we ship prompt/rule changes safely at scale

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT (quality infra) |
| Complexity | MEDIUM |
| Systems Affected | eval runner, golden fixtures, drift detector, CI config |
| Jira Issue | N/A |

---

## Patterns to Follow

### Existing eval runner + report shape
```python
# SOURCE: backend/eval/runner.py  (load_latest_report, precision/recall/calibration)
# SOURCE: backend/eval/__main__.py  (uv run python -m eval)
```

### Golden fixture format
```json
// SOURCE: backend/eval/golden/acord_life_basic.json
// { "source_xml": "...", "target_schema": {...}, "expected_mappings": [{source_path, target_path}, ...] }
```

### Eval report types (frontend already consumes)
```typescript
// SOURCE: frontend/src/api.ts:73-91  (EvalReport, CalibrationRow)
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `backend/eval/golden/` | UPDATE | Add per-LOB fixtures for all 4 LOBs + formats |
| `backend/eval/baseline.py` | CREATE | Store/load a baseline report for regression compare |
| `backend/eval/regression.py` | CREATE | Compare current vs baseline; threshold gate |
| `backend/eval/drift.py` | CREATE | Detect unseen source fields / CDM field changes |
| `backend/eval/runner.py` | UPDATE | Per-LOB breakdown; emit machine-readable exit code |
| `.github/workflows/eval.yml` | CREATE | CI: run eval + regression on PR |
| `backend/app/observability/metrics.py` | CREATE | Live Prometheus metrics for production runs |
| `backend/app/routers/admin.py` | CREATE | `/admin/metrics` summary endpoint |
| `frontend/src/pages/MetricsPage.tsx` | CREATE | Live ops dashboard (auto-approval/escalation/cost) |
| `backend/tests/eval/test_regression.py` | CREATE | Regression + drift unit tests |

---

## Tasks

### Task 1: Expand golden fixtures per LOB
- **File**: `backend/eval/golden/`
- **Action**: UPDATE
- **Implement**: Add fixtures so each LOB (Life, P&C, Annuity, Group/Health) has several examples covering the canonical schema, including edge cases (missing required, unknown field — mirror `acord_messy_sample.xml`). Tag each fixture with its `lob`.
- **Mirror**: `backend/eval/golden/acord_life_basic.json`, `backend/eval/golden/acord_life_partial.json`
- **Validate**: `cd backend && uv run python -m eval`

### Task 2: Baseline store
- **File**: `backend/eval/baseline.py`
- **Action**: CREATE
- **Implement**: `save_baseline(report) -> path` and `load_baseline() -> report | None`. Baseline is a committed JSON snapshot of accepted metrics (per-LOB precision/recall). `update-baseline` CLI flag to bless a new baseline intentionally.
- **Mirror**: `backend/eval/runner.py` (load_latest_report)
- **Validate**: `cd backend && uv run pytest tests/eval/test_regression.py`

### Task 3: Regression gate
- **File**: `backend/eval/regression.py`
- **Action**: CREATE
- **Implement**: `compare(current, baseline, tol=0.02) -> RegressionResult`. Fail if any LOB precision/recall drops more than `tol` below baseline. Return structured diffs (which LOB, which metric, delta). Non-zero exit on regression for CI.
- **Mirror**: `backend/app/pipeline/confidence.py` (ScoreResult dataclass style)
- **Validate**: `cd backend && uv run pytest tests/eval/test_regression.py`

### Task 4: Drift detection
- **File**: `backend/eval/drift.py`
- **Action**: CREATE
- **Implement**: `detect_drift(samples, cdm_schema) -> DriftReport`. For each sample, extract fields; flag source paths never seen in fixtures (new carrier field) and CDM required fields no sample covers. Surfaces schema evolution before it breaks mappings.
- **Mirror**: `backend/app/agents/extract.py` (field walk), `backend/app/pipeline/confidence.py`
- **Validate**: `cd backend && uv run pytest tests/eval/test_regression.py -k drift`

### Task 5: Runner per-LOB + exit codes
- **File**: `backend/eval/runner.py`
- **Action**: UPDATE
- **Implement**: Group metrics by `lob`; write `eval_report.json` including per-LOB breakdown; integrate `compare()` so `python -m eval --check` exits non-zero on regression.
- **Mirror**: `backend/eval/runner.py` (existing aggregation)
- **Validate**: `cd backend && uv run python -m eval --check`

### Task 6: CI workflow
- **File**: `.github/workflows/eval.yml`
- **Action**: CREATE
- **Implement**: On PR: set `LLM_MODE=test` (deterministic, no key), `uv sync`, `uv run python -m eval --check`, `uv run pytest`. Fail the build on regression. Also regenerate SDKs (Phase 5) and fail if `openapi.json` drifted.
- **Mirror**: repo conventions (CLAUDE.md test commands)
- **Validate**: workflow runs on a test PR.

### Task 6b: Live observability metrics
- **File**: `backend/app/observability/metrics.py`, `backend/app/routers/admin.py`, `backend/pyproject.toml`
- **Action**: CREATE / UPDATE
- **Implement**: Offline eval (above) measures fixtures; this measures **live traffic** — needed because auto-approval (Phase 5) runs unattended.
  - Add `"prometheus-client>=0.21"`. Emit at gate decisions + stage completions:
    - Counters: `runs_total`, `auto_approved_total`, `escalated_total{lob,tenant}`, `stage_failed_total{stage}`, `projection_failed_total{distributor}`.
    - Histograms: `mapping_confidence`, `run_duration_seconds`, `run_cost_usd`.
  - `GET /admin/metrics` (Prometheus format) + a JSON summary endpoint for the UI: auto-approval rate, escalation rate per LOB/tenant, confidence distribution, cost/run, stage failure rates.
  - Hook emission into the `should_auto_approve` path (Phase 5) and node completions (`build.py`).
- **Mirror**: `backend/app/routers/pipeline.py` (router style), `backend/eval/runner.py` (cost aggregation)
- **Validate**: `cd backend && uv run pytest tests/observability/test_metrics.py`

### Task 6c: Live ops dashboard (frontend)
- **File**: `frontend/src/pages/MetricsPage.tsx`, `frontend/src/api.ts`, `frontend/src/components/NavBar.tsx`
- **Action**: CREATE / UPDATE
- **Implement**: New `/metrics` route reusing the eval-dashboard card/table pattern. Show live: auto-approval rate, escalation rate per LOB, confidence histogram, cost/run trend, stage failure rates. Add nav link.
- **Mirror**: `frontend/src/pages/EvalPage.tsx:99-138` (MetricCard + table layout), `frontend/src/components/NavBar.tsx`
- **Validate**: `cd frontend && npm run build && npm test`

### Task 7: Tests
- **File**: `backend/tests/eval/test_regression.py`
- **Action**: CREATE
- **Implement**: `test_no_regression_passes`, `test_precision_drop_fails`, `test_drift_flags_new_field`, `test_drift_flags_uncovered_required`.
- **Mirror**: `backend/tests/agents/test_map_confidence.py`
- **Validate**: `cd backend && uv run pytest`

---

## Validation

```bash
cd backend && uv run python -m eval --check && uv run pytest
```

## Risks

| Risk | Mitigation |
|------|------------|
| Flaky LLM eval in CI | Run eval in `LLM_MODE=test` (TestModel) for determinism; real-model eval is a separate manual job. |
| Baseline staleness blocks good changes | Explicit `--update-baseline` to bless intended metric changes. |
| Drift false positives | Drift is advisory (warn) except for uncovered required CDM fields (fail). |

## Acceptance Criteria

- [ ] Per-LOB golden suites for all 4 LOBs incl. edge cases
- [ ] Regression gate fails on >2% precision/recall drop vs baseline
- [ ] Drift detector flags new source fields + uncovered required CDM fields
- [ ] CI runs eval + pytest on every PR and blocks on regression
- [ ] Live metrics expose auto-approval rate, escalation rate per LOB/tenant, confidence distribution, cost/run, stage failures
- [ ] `/metrics` dashboard renders live ops data
- [ ] `uv run python -m eval --check` and `uv run pytest` green
