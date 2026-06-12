# Plan: Phase 4 — Natural-Language Rule Editing (Support Copilot)

## Summary

Let business users author and modify mapping/transform rules in plain English, preview the impact before applying, and redeploy in minutes. Extends the existing support agent (`support.py`) from single-field `EditIntent` proposals to full rule authoring: English → validated DSL rule (Phase 3), an impact-preview that re-runs affected mappings against the run's sample WITHOUT committing, and an approve→redeploy loop that re-projects outputs (Phase 2). Includes rule versioning + rollback.

## User Story

As a business analyst (non-engineer)
I want to change a mapping rule in English and see what it affects before applying
So that I can maintain the system without filing an IT ticket

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | support agent, routers/support, DSL, projection, rule-version model, frontend SupportChat |
| Jira Issue | N/A |

---

## Patterns to Follow

### Support agent edit proposal (extend from single-field to rule)
```python
# SOURCE: backend/app/agents/support.py  (answer_question → EditIntent[])
# EditIntent: run_id, field_id, new_target_path, new_transform, reason
```

### Apply-edit endpoint (queues for review, doesn't auto-apply)
```python
# SOURCE: backend/app/routers/support.py  (apply_proposed_edit → StageResult stage="support_review")
```

### DSL validate/eval (reuse for preview)
```python
# SOURCE: backend/app/pipeline/dsl.py  (validate_rule, eval_rule)  [Phase 3]
```

### Frontend mutation + proposed-edit UI
```typescript
// SOURCE: frontend/src/components/SupportChat.tsx:46-63  (ask/apply mutations)
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `backend/app/models/rule_version.py` | CREATE | `RuleVersion` table for history/rollback |
| `backend/app/agents/support.py` | UPDATE | NL → DSL rule authoring intent |
| `backend/app/pipeline/preview.py` | CREATE | Dry-run a rule change, return before/after diff |
| `backend/app/routers/support.py` | UPDATE | `/support/preview`, `/support/redeploy`, `/support/rollback` |
| `backend/alembic/versions/xxxx_rule_version.py` | CREATE | Migration |
| `frontend/src/components/SupportChat.tsx` | UPDATE | Preview/diff panel + redeploy button |
| `frontend/src/api.ts` | UPDATE | New endpoints + types |
| `backend/tests/agents/test_nl_rule.py` | CREATE | NL→rule, preview diff, redeploy, rollback |

---

## Tasks

### Task 1: RuleVersion model + migration
- **File**: `backend/app/models/rule_version.py`
- **Action**: CREATE
- **Implement**: `RuleVersion(id, tenant_id, run_id, field_id, version_num, rule: dict | None, transform: str | None, author, reason, created_at)`. Every rule change writes a new version; rollback restores a prior one.
- **Mirror**: `backend/app/models/mapping.py`, `backend/app/models/audit.py`
- **Validate**: `cd backend && uv run alembic upgrade head`

### Task 2: NL → DSL authoring in support agent
- **File**: `backend/app/agents/support.py`
- **Action**: UPDATE
- **Implement**: Add a `propose_rule` output path: given an English instruction ("if face amount over 250k, flag for underwriting"), the agent emits a DSL rule (`{engine, expr, inputs}` from Phase 3) plus target field + reason. Validate via `validate_rule`; if invalid, ask the model to repair once. Return as an extended `EditIntent` carrying `rule`.
- **Mirror**: existing `support.py` `propose_edit`, `backend/app/pipeline/dsl.py:validate_rule`
- **Validate**: `cd backend && uv run pytest tests/agents/test_nl_rule.py`

### Task 3: Impact preview (dry-run)
- **File**: `backend/app/pipeline/preview.py`
- **Action**: CREATE
- **Implement**: `async def preview_rule_change(run_id, field_id, new_rule, session) -> dict`: load the run's source sample, compute current output value for the field, apply the proposed rule via `eval_rule`, return `{before, after, affected_distributors}` (which Phase 2 projections change). **No DB writes** — pure dry-run.
- **Mirror**: `backend/app/agents/transform.py:94-136`, `backend/app/pipeline/projection.py` [Phase 2]
- **Validate**: `cd backend && uv run pytest tests/agents/test_nl_rule.py`

### Task 4: Preview / redeploy / rollback endpoints
- **File**: `backend/app/routers/support.py`
- **Action**: UPDATE
- **Implement**:
  - `POST /runs/{id}/support/preview` → `preview_rule_change` result (no commit).
  - `POST /runs/{id}/support/redeploy` → write new `RuleVersion`, update `FieldMapping.rule`, re-run build + projection (Phase 2 fan-out), return new outputs.
  - `POST /runs/{id}/support/rollback` → restore a prior `RuleVersion`, re-run build + projection.
  - Each logs an `AuditEvent` (actor `"support_agent"` / `"reviewer"`).
- **Mirror**: `backend/app/routers/support.py` (existing apply), `backend/app/routers/review.py` (resume pattern)
- **Validate**: `cd backend && uv run pytest`

### Task 5: Frontend preview + redeploy UI
- **File**: `frontend/src/components/SupportChat.tsx`, `frontend/src/api.ts`
- **Action**: UPDATE
- **Implement**: When the agent proposes a rule, show a **diff panel** (before → after, affected distributors) with "Preview", "Apply & Redeploy", "Cancel". Add `previewRule`, `redeployRule`, `rollbackRule` to `api.ts` with types.
- **Mirror**: `frontend/src/components/SupportChat.tsx:46-104`, `frontend/src/api.ts:106-110`
- **Validate**: `cd frontend && npm run build && npm test`

### Task 6: Tests
- **File**: `backend/tests/agents/test_nl_rule.py`
- **Action**: CREATE
- **Implement** (mode `"test"`): `test_nl_to_rule_valid`, `test_preview_returns_before_after`, `test_preview_no_db_write`, `test_redeploy_updates_outputs`, `test_rollback_restores_prior`.
- **Mirror**: `backend/tests/agents/test_support.py`
- **Validate**: `cd backend && uv run pytest`

---

## Validation

```bash
cd backend && uv run alembic upgrade head && uv run pytest
cd frontend && npm run build && npm test
```

## Risks

| Risk | Mitigation |
|------|------------|
| LLM emits invalid DSL | `validate_rule` + one repair attempt; reject if still invalid. |
| Redeploy applies bad rule | Preview is mandatory in UI before redeploy; every change versioned for instant rollback. |
| Preview side effects | `preview_rule_change` does zero DB writes (asserted in test). |

## Acceptance Criteria

- [ ] English instruction produces a validated DSL rule
- [ ] Preview shows before/after + affected distributors with no DB write
- [ ] Redeploy updates mappings + re-projects outputs; rollback restores prior version
- [ ] All changes versioned in `RuleVersion` and audited
- [ ] Backend + frontend tests green
