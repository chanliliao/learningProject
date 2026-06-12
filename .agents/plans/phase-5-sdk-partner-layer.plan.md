# Plan: Phase 5 — SDK / Partner Integration Layer (TypeScript + Python)

## Summary

Expose the platform to third-party partners through a clean, versioned SDK so a distributor can integrate in ~15 lines without knowing carrier internals. Publish a stable OpenAPI contract, generate typed TypeScript and Python clients, add a headless workflow endpoint (start→poll→outputs without our review UI), partner API-key auth + tenancy, and a quickstart. This is the delivery layer over the clean CDM/projection model built in Phases 1–2.

## User Story

As a distributor's developer
I want a typed SDK that returns clean normalized data in a few lines
So that I integrate once and get every carrier without bespoke work

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | HIGH |
| Systems Affected | routers (new partner API + auth), OpenAPI, SDK packages, tenancy, docs |
| Jira Issue | N/A |

---

## Patterns to Follow

### Existing REST + FastAPI dependency style
```python
# SOURCE: backend/app/routers/pipeline.py:56-99  (create_run, Depends(get_session))
# SOURCE: backend/app/routers/pipeline.py:22-40  (get_checkpointer dependency)
```

### Existing hand-written TS client (SDK supersedes/wraps this)
```typescript
// SOURCE: frontend/src/api.ts:1-27  (get/post/patch helpers, BASE_URL)
```

### Outputs endpoint (the clean data partners consume)
```python
# SOURCE: backend/app/routers/pipeline.py  GET /runs/{id}/outputs  [Phase 2]
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `backend/app/routers/partner.py` | CREATE | Headless partner API: submit doc, get normalized outputs |
| `backend/app/pipeline/autoapprove.py` | CREATE | Confidence-threshold auto-approval policy (SOC 2) |
| `backend/app/models/run.py` | UPDATE | Add `PipelineRun.auto_approve: bool`; record policy version |
| `backend/app/auth.py` | CREATE | API-key dependency, maps key→tenant |
| `backend/app/models/api_key.py` | CREATE | `ApiKey` table (hashed key, tenant, quota) |
| `backend/app/middleware/ratelimit.py` | CREATE | Per-tenant rate limit + monthly quota + budget guard |
| `backend/app/pipeline/locking.py` | CREATE | Optimistic-lock helper + gate double-resume guard |
| `backend/app/security/output_policy.py` | CREATE | Mask/tokenize PII in partner outputs (moved from Phase 8) |
| `backend/app/main.py` | UPDATE | Register partner router; emit OpenAPI tags |
| `backend/alembic/versions/xxxx_api_key.py` | CREATE | Migration |
| `sdks/typescript/` | CREATE | Generated/typed TS SDK package |
| `sdks/python/` | CREATE | Generated/typed Python SDK package |
| `sdks/README.md` | CREATE | 15-line quickstart per language |
| `backend/tests/routers/test_partner_api.py` | CREATE | Auth + headless round-trip |

---

## Tasks

> Note: inserting the auto-approval policy made this list 8 tasks; later task headers (Register/OpenAPI, TS SDK, Python SDK, Quickstart) follow Task 3 in the order written — execute top-to-bottom regardless of the printed number.

### Task 1: ApiKey model + auth dependency + migration
- **File**: `backend/app/models/api_key.py`, `backend/app/auth.py`, migration
- **Action**: CREATE
- **Implement**: `ApiKey(id, tenant_id, key_hash, name, created_at, revoked)`. `auth.py`: `async def require_api_key(x_api_key: str = Header(...)) -> str` returns tenant_id; hash compare; 401 on miss. **No inline secrets** — keys hashed at rest (CLAUDE.md).
- **Mirror**: `backend/app/models/schema.py`, `backend/app/routers/pipeline.py:22-40`
- **Validate**: `cd backend && uv run alembic upgrade head`

### Task 2: Auto-approval policy (SOC 2)
- **File**: `backend/app/pipeline/autoapprove.py`, `backend/app/config.py`
- **Action**: CREATE / UPDATE
- **Implement**:
  - `def should_auto_approve(mappings, settings) -> tuple[bool, dict]`: returns `(approve, evidence)` where `approve` is True only if every mapping is `confidence >= settings.confidence_threshold` AND carries no flags. `evidence` = `{policy_version, threshold, min_confidence, escalated_field_ids}` — written to `AuditEvent` for the SOC 2 trail.
  - Add `auto_approve_policy_version: str = "v1"` to settings (versioned config requirement).
  - Headless runs call this at each gate: auto-approve when clean, else leave the gate `awaiting_review` and surface escalated fields. **Every decision logged with score+threshold+policy version** — this IS the SOC 2 control.
  - Single source of truth: the human review path (`resume_run`) and headless path both consult this helper.
- **Mirror**: `backend/app/pipeline/confidence.py` (ScoreResult), `backend/app/graph/build.py:612-628` (approval/audit)
- **Validate**: `cd backend && uv run pytest tests/pipeline/test_autoapprove.py`

### Task 3: Headless partner API
- **File**: `backend/app/routers/partner.py`, `backend/app/models/run.py`
- **Action**: CREATE / UPDATE
- **Implement**:
  - Add `PipelineRun.auto_approve: bool = False`.
  - `POST /v1/documents` (auth required): upload a doc → starts a run for the caller's tenant with `auto_approve=True`; gates resolve via `should_auto_approve`. Clean runs flow to completion; runs with escalations stop and return gate state. Returns `{run_id, status, escalations}`.
  - `GET /v1/documents/{run_id}` → status + normalized CDM record.
  - `GET /v1/documents/{run_id}/outputs` → per-distributor projections (the clean data).
  - All scoped to `tenant_id` from the API key (enforce row filtering).
- **Mirror**: `backend/app/routers/pipeline.py:56-147`
- **Validate**: `cd backend && uv run pytest tests/routers/test_partner_api.py`

### Task 3: Register + OpenAPI
- **File**: `backend/app/main.py`
- **Action**: UPDATE
- **Implement**: Include `partner.router` under `/v1`, tag `"partner"`. Ensure FastAPI auto-OpenAPI documents request/response models (define Pydantic response models, not bare dicts, for clean codegen). Export `openapi.json` via existing `/openapi.json`.
- **Mirror**: existing router registration in `backend/app/main.py`
- **Validate**: `cd backend && uv run pytest`

### Task 4: TypeScript SDK
- **File**: `sdks/typescript/`
- **Action**: CREATE
- **Implement**: Generate a typed client from `openapi.json` (e.g. `openapi-typescript` + a thin hand-written wrapper class `InfraClient` with `submitDocument`, `getOutputs`). Mirror the existing fetch-helper ergonomics. Quickstart ≤15 lines.
- **Mirror**: `frontend/src/api.ts:1-27`
- **Validate**: `cd sdks/typescript && npm install && npm run build`

### Task 5: Python SDK
- **File**: `sdks/python/`
- **Action**: CREATE
- **Implement**: Thin `httpx`-based client `InfraClient(api_key)` with `submit_document(path)`, `get_outputs(run_id)`. Typed via Pydantic models shared with backend response models. Packaged with its own `pyproject.toml`.
- **Mirror**: `backend/app/routers/partner.py` response models
- **Validate**: `cd sdks/python && uv run python -c "import infra_sdk"`

### Task 5b: Rate limiting, quota + budget guard
- **File**: `backend/app/middleware/ratelimit.py`, `backend/app/models/api_key.py`, `backend/pyproject.toml`
- **Action**: CREATE / UPDATE
- **Implement**:
  - Add `"slowapi>=0.1"`. Add `ApiKey.monthly_quota: int` and `ApiKey.budget_usd: float | None`.
  - Per-tenant **rate limit** (requests/min) keyed on `tenant_id` from the API key.
  - **Monthly quota**: count this tenant's runs in the current month; reject with `429` when exceeded.
  - **Budget guard** (the real money protection): sum the tenant's `LLMCall.estimated_cost` for the month; if over `budget_usd`, reject new runs with `429` + clear error. Reuses the cost you already track — enforce dollars, not just request count.
- **Mirror**: `backend/app/routers/pipeline.py:22-40` (dependency style), `backend/eval/runner.py:121-122` (cost sum)
- **Validate**: `cd backend && uv run pytest tests/routers/test_ratelimit.py`

### Task 5c: Optimistic locking + gate double-resume guard
- **File**: `backend/app/pipeline/locking.py`, `backend/app/models/mapping.py`, `backend/app/models/run.py`, `backend/app/graph/build.py`
- **Action**: CREATE / UPDATE
- **Implement**:
  - Add `version: int = 1` to `FieldMapping` and `PipelineRun`. Field edits (`review.py`) write with `WHERE id=? AND version=?`; zero rows updated → `409 Conflict`, client must reload. Prevents silent lost edits when two reviewers touch the same field.
  - **Gate double-resume guard** (correctness-critical with auto-approval): before `resume_run` resumes the graph, re-check the stage is not already `approved`/`rejected` for the current `attempt`. The human approve and the headless auto-approver can hit the same gate simultaneously; without this, two `Command(resume=…)` calls on one `thread_id` can desync the LangGraph checkpoint. Guard = a conditional DB update on stage status that only one caller wins.
- **Mirror**: `backend/app/graph/build.py:581-629` (resume/approval path), `backend/app/models/mapping.py:39-47`
- **Validate**: `cd backend && uv run pytest tests/pipeline/test_locking.py`

### Task 5d: PII output masking (moved from Phase 8 — ship with the SDK, no leak window)
- **File**: `backend/app/security/output_policy.py`, `backend/app/models/api_key.py`, `backend/app/routers/partner.py`, `backend/app/config.py`
- **Action**: CREATE / UPDATE
- **Implement**: Depends on Phase 0's PII detectors (`app/pipeline/pii.py`).
  - Add `ApiKey.pii_authorized: bool = False` and `pii_output_default: str = "mask"` setting.
  - `apply_output_policy(output, *, authorized) -> dict`: when not authorized (default), detect PII via Phase 0 detectors and tokenize (`***-**-6789`, year-only DOB); when authorized, pass through AND log a disclosure `AuditEvent`.
  - Run every partner response (`GET /v1/documents/{id}` + `/outputs`) through it using the API key's `pii_authorized` flag. The partner SDK never returns raw PII by default — closes the leak window the moment the SDK exists.
  - **Note**: this is output masking only. Encryption-at-rest stays in Phase 8.
- **Mirror**: `backend/app/pipeline/pii.py` (Phase 0), `backend/app/models/audit.py`
- **Validate**: `cd backend && uv run pytest tests/security/test_output_policy.py`

### Task 6: Quickstart + tests
- **File**: `sdks/README.md`, `backend/tests/routers/test_partner_api.py`
- **Action**: CREATE
- **Implement**: README with the ≤15-line snippet per language. Tests: 401 without key; 200 round-trip with key; tenant isolation (key A cannot read key B's run).
- **Mirror**: `backend/tests/agents/` style
- **Validate**: `cd backend && uv run pytest`

---

## Validation

```bash
cd backend && uv run alembic upgrade head && uv run pytest
cd sdks/typescript && npm run build
cd sdks/python && uv run python -c "import infra_sdk"
```

## Risks

| Risk | Mitigation |
|------|------------|
| Bare-dict responses break codegen | Define Pydantic response models on every partner endpoint. |
| Tenant data leak | API key → tenant enforced at query layer; explicit isolation test. |
| SDK drift from API | SDKs generated from `openapi.json`; regenerate in CI (Phase 7). |

## Acceptance Criteria

- [ ] Confidence-threshold auto-approval enforced via single `should_auto_approve` helper; every decision logs score+threshold+policy version (SOC 2 control)
- [ ] Below-threshold/flagged mappings escalate to human even in headless mode
- [ ] Versioned `/v1` partner API with API-key auth + tenant isolation
- [ ] OpenAPI contract published; TS + Python SDKs build
- [ ] ≤15-line quickstart works end-to-end in both languages
- [ ] Tenant isolation test passes
- [ ] Per-tenant rate limit + monthly quota + dollar-budget guard enforced (429 on exceed)
- [ ] Optimistic-lock conflict returns 409; no silent lost edits
- [ ] Gate double-resume guard: only one approver resumes a given (run, stage, attempt)
- [ ] Partner SDK masks PII by default; authorized tenants get plaintext + a logged disclosure (no leak window)
- [ ] `uv run pytest` green
