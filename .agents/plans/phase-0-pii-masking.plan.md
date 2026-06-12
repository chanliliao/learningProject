# Plan: Phase 0 — PII Masking Before LLM

## Summary

Mask personally identifiable information (SSN, DOB, full names, addresses, policy IDs where required) before any field value is placed into an LLM prompt in `interpret_fields` and `propose_mappings`. Masking is reversible within a single run via a per-run token map so transforms still operate on real values at build/test time, but raw PII never crosses the LLM boundary or appears in `LLMCall.prompt`. This is a security/correctness fix, not a feature, and gates all later phases.

## User Story

As a compliance-conscious engineer
I want PII redacted before it reaches the LLM or the audit log
So that we never send SSN/DOB to a third-party model or persist it in plaintext traces

## Metadata

| Field | Value |
|-------|-------|
| Type | BUG_FIX / SECURITY |
| Complexity | LOW–MEDIUM |
| Systems Affected | agents (interpret, map), llm/client, new pipeline/pii module, config |
| Jira Issue | N/A |

---

## Patterns to Follow

### Agent prompt construction (where PII currently leaks)
```python
# SOURCE: backend/app/agents/interpret.py:61-63
source_summary = "\n".join(
    f"  {f.path} ({f.inferred_type}): {f.value!r}" for f in fields
)
# SOURCE: backend/app/agents/map.py:60-62  (same leak)
```

### Module-level regex constants (mirror for detectors)
```python
# SOURCE: backend/app/agents/extract.py:13-16
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_NUM_RE = re.compile(r"^\d+(\.\d+)?$")
```

### Settings field pattern
```python
# SOURCE: backend/app/config.py:49-51
llm_mode: str = "real"
confidence_threshold: float = 0.8
```

### Test style
```python
# SOURCE: backend/tests/agents/test_transform_apply.py:5-13
def test_apply_maps_and_coerces():
    ...
    assert out == {...}
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `backend/app/pipeline/pii.py` | CREATE | Detect + mask/unmask PII; per-run token map |
| `backend/app/agents/interpret.py` | UPDATE | Mask field values before prompt build |
| `backend/app/agents/map.py` | UPDATE | Mask field values before prompt build |
| `backend/app/config.py` | UPDATE | Add `pii_masking_enabled: bool = True` |
| `backend/tests/agents/test_pii.py` | CREATE | Unit tests for detectors + round-trip |
| `backend/tests/agents/test_interpret.py` | UPDATE | Assert no raw SSN/DOB in built prompt |

---

## Tasks

### Task 1: Create the PII module
- **File**: `backend/app/pipeline/pii.py`
- **Action**: CREATE
- **Implement**:
  - Module docstring + Google-style docstrings (match repo convention).
  - Module-level compiled regexes: `_SSN_RE` (`\d{3}-\d{2}-\d{4}`), `_DATE_RE` (reuse ISO), plus a `_PII_FIELD_HINTS` set of path-substrings (`{"ssn", "birthdate", "dob", "surname", "lastname", "firstname", "givenname", "addr", "postalcode"}`).
  - `class PiiMap(BaseModel)` holding `tokens: dict[str, str]` (token → original value).
  - `def mask_fields(fields: list[ExtractedField]) -> tuple[list[ExtractedField], PiiMap]`: returns copies with PII values replaced by stable tokens like `「PII_SSN_1」`; type/path preserved so the LLM still maps correctly.
  - `def unmask(text: str, pii_map: PiiMap) -> str`: reverse substitution (for displaying answers if ever needed).
  - Detection rule: a field is PII if its value matches a regex OR its `path` lowercased contains any `_PII_FIELD_HINTS` substring.
- **Mirror**: `backend/app/agents/extract.py:13-16` (regex consts), `backend/app/agents/base.py:11-22` (Pydantic model)
- **Validate**: `cd backend && uv run pytest tests/agents/test_pii.py`

### Task 2: Add config flag
- **File**: `backend/app/config.py`
- **Action**: UPDATE
- **Implement**: Add `pii_masking_enabled: bool = True` with an Attributes docstring line.
- **Mirror**: `backend/app/config.py:49-51`
- **Validate**: `cd backend && uv run pytest`

### Task 3: Mask in interpret agent
- **File**: `backend/app/agents/interpret.py`
- **Action**: UPDATE
- **Implement**: Before line 61, if `get_settings().pii_masking_enabled`, call `masked, _ = mask_fields(fields)` and build `source_summary` from `masked`. The interpret output describes meaning/rules — masked tokens are fine; do not unmask (interpretations are not value-dependent).
- **Mirror**: `backend/app/agents/interpret.py:61-69`
- **Validate**: `cd backend && uv run pytest tests/agents/test_interpret.py`

### Task 4: Mask in map agent
- **File**: `backend/app/agents/map.py`
- **Action**: UPDATE
- **Implement**: Mask `fields` (and the interpreted context lines) before building `source_summary`/`context_section`. Mapping decisions are path-based, not value-based, so masking values does not degrade mapping quality. Target schema is not PII — leave it.
- **Mirror**: `backend/app/agents/map.py:60-75`
- **Validate**: `cd backend && uv run pytest tests/agents/test_map.py`

### Task 5: Tests
- **File**: `backend/tests/agents/test_pii.py`
- **Action**: CREATE
- **Implement**:
  - `test_masks_ssn_value`: field value `"123-45-6789"` → token, not raw.
  - `test_masks_by_path_hint`: path `...Person.LastName` value `"Doe"` → masked even though value isn't regex-matchable.
  - `test_roundtrip_unmask`: `unmask(masked_text, map) == original_text`.
  - `test_non_pii_untouched`: `FaceAmt` value `"500000.00"` stays raw.
- **File**: `backend/tests/agents/test_interpret.py`
- **Action**: UPDATE — add assertion that built prompt contains no `123-45-6789` when masking on (use `mode="test"`).
- **Mirror**: `backend/tests/agents/test_transform_apply.py`
- **Validate**: `cd backend && uv run pytest`

---

## Validation

```bash
cd backend && uv run pytest
```

## Risks

| Risk | Mitigation |
|------|------------|
| Masking changes mapping quality | Mapping is path-driven; values masked but types/paths intact. Add a test mapping run in test mode to confirm same target paths. |
| Token collisions | Tokens are counter-suffixed per run (`PII_SSN_1`, `PII_SSN_2`). |
| Over-masking real mappable values | Hint set is conservative; regex + path-hint only. Tune via `test_non_pii_untouched`. |

## Acceptance Criteria

- [ ] No raw SSN/DOB/surname value appears in any LLM prompt when `pii_masking_enabled=True`
- [ ] `LLMCall.prompt` rows contain only masked tokens for PII fields
- [ ] Transforms at build/test still use real values (masking is prompt-only, not stored on `ExtractedField` in DB state)
- [ ] `uv run pytest` green
