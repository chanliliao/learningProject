# Plan: Phase 8 — PII Encryption at Rest + Key Rotation

> **Scope change**: partner-output masking moved to **Phase 5** (ships with the SDK, no leak window). This phase now covers **encryption at rest + key rotation only**.

## Summary

Protect PII **at rest** — encrypt sensitive columns (`source_xml`/`source_bytes`) so a DB dump doesn't leak SSN/DOB — with built-in key rotation via `MultiFernet`. Phase 0 keeps PII out of LLM prompts; Phase 5 masks it in partner outputs; this phase closes the storage gap. Together they make the platform's data handling genuinely SOC 2-ready rather than audit-trail-only.

## User Story

As a security/compliance owner
I want PII encrypted in the database and masked in partner responses by default
So that neither a DB breach nor an unauthorized partner exposes SSN/DOB

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY (security) |
| Complexity | MEDIUM |
| Systems Affected | models (encrypted types), partner router, output policy, config, migration |
| Jira Issue | N/A |

---

## Patterns to Follow

### PII detection (reuse Phase 0)
```python
# SOURCE: backend/app/pipeline/pii.py  [Phase 0]  (_SSN_RE, _PII_FIELD_HINTS, mask_fields)
```

### Settings + secret loading (.env only — CLAUDE.md)
```python
# SOURCE: backend/app/config.py:38-51  (SettingsConfigDict env_file, fields)
```

### Partner outputs endpoint (where masking is applied)
```python
# SOURCE: backend/app/routers/partner.py  GET /v1/documents/{id}/outputs  [Phase 5]
```

### JSON column model fields (target for encryption wrapping)
```python
# SOURCE: backend/app/models/run.py:42  source_xml: str
# SOURCE: backend/app/models/mapping.py:42-44  source_path/value-bearing rows
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `backend/pyproject.toml` | UPDATE | Add `cryptography` (Fernet) |
| `backend/app/security/crypto.py` | CREATE | MultiFernet encrypt/decrypt; supports key rotation |
| `backend/app/security/rotate.py` | CREATE | Re-encrypt rows under newest key; CLI command |
| `backend/app/security/types.py` | CREATE | SQLAlchemy `EncryptedStr` TypeDecorator |
| `backend/app/models/run.py` | UPDATE | Wrap `source_xml`/`source_bytes` in `EncryptedStr` |
| `backend/app/config.py` | UPDATE | `pii_encryption_keys` (env, comma-separated) |
| `backend/alembic/versions/xxxx_encrypt_pii.py` | CREATE | Migration (fresh-DB; no backfill per greenfield) |
| `backend/tests/security/test_pii_at_rest.py` | CREATE | Round-trip + ciphertext-at-rest + rotation tests |

---

## Tasks

### Task 1: Crypto helper with rotation support + dep
- **File**: `backend/pyproject.toml`, `backend/app/security/crypto.py`, `backend/app/config.py`
- **Action**: UPDATE / CREATE
- **Implement**: Add `cryptography>=43`. `crypto.py`: use **`MultiFernet`** (not single `Fernet`) so rotation is built in — `encrypt` uses the newest key (`keys[0]`); `decrypt` tries each key in order, so rows written under an old key still decrypt. Keys come from `settings.pii_encryption_keys` (comma-separated, env only — **no inline secret**, CLAUDE.md), newest first. Fail fast if empty in production. Add `pii_encryption_keys: str = ""` to settings. (Note: `pii_output_default` + output masking live in Phase 5, not here.)
- **Mirror**: `backend/app/config.py:38-51`
- **Validate**: `cd backend && uv run pytest tests/security/test_pii_at_rest.py -k crypto`

### Task 1b: Key rotation command
- **File**: `backend/app/security/rotate.py`
- **Action**: CREATE
- **Implement**: `rotate_pii_keys(session)` — iterate encrypted rows, `decrypt` (tries all keys) then `encrypt` (newest key), write back. Runnable as `uv run python -m app.security.rotate`. Rotation flow documented: (1) prepend new key to `pii_encryption_keys`, (2) deploy, (3) run this command, (4) once all rows re-encrypted, drop the old key from the env list. Idempotent — safe to re-run.
- **Mirror**: `backend/app/seed.py` (script style), `backend/eval/__main__.py` (module-run pattern)
- **Validate**: `cd backend && uv run pytest tests/security/test_pii_at_rest.py -k rotate

### Task 2: Encrypted column type
- **File**: `backend/app/security/types.py`
- **Action**: CREATE
- **Implement**: SQLAlchemy `TypeDecorator(String)` `EncryptedStr` — `process_bind_param` encrypts, `process_result_value` decrypts. Transparent to app code; ciphertext at rest.
- **Mirror**: `backend/app/models/run.py:42` (column it wraps)
- **Validate**: `cd backend && uv run pytest tests/security/test_pii_at_rest.py -k roundtrip`

### Task 3: Encrypt source columns + migration
- **File**: `backend/app/models/run.py`, migration
- **Action**: UPDATE / CREATE
- **Implement**: Change `source_xml` (and `source_bytes` from Phase 6) to `EncryptedStr`. **Greenfield**: assume a fresh DB — the migration just alters the column type; no read-encrypt-writeback backfill step needed. Verify pipeline still reads source for re-extraction (decryption is transparent).
- **Mirror**: existing `backend/alembic/versions/c0c37cb17507_initial_schema.py`
- **Validate**: `cd backend && uv run alembic upgrade head && uv run pytest`

### Task 4: Tests
- **File**: `backend/tests/security/test_pii_at_rest.py`
- **Action**: CREATE
- **Implement**:
  - `test_crypto_roundtrip`: encrypt→decrypt identity.
  - `test_source_stored_ciphertext`: raw DB value for `source_xml` is not plaintext.
  - `test_decrypt_with_rotated_key`: row encrypted under key B still decrypts after a new key A is prepended.
  - `test_rotate_reencrypts`: after `rotate_pii_keys`, rows decrypt under the newest key alone.
  - `test_missing_keys_fails_fast`: production w/o `pii_encryption_keys` raises at startup.
- **Mirror**: `backend/tests/agents/test_pii.py` (Phase 0)
- **Validate**: `cd backend && uv run pytest`

---

## Validation

```bash
cd backend && uv sync && uv run alembic upgrade head && uv run pytest
```

## Risks

| Risk | Mitigation |
|------|------------|
| Key management | Keys in `.env`/secret store only; never committed. Fail-fast if absent. **Rotation built in via `MultiFernet`** (Task 1b) — not deferred. KMS-backed keys are the production upgrade path. |
| Encrypted columns unsearchable | Acceptable — source docs aren't queried by content. Keep non-PII metadata (filename, LOB) plaintext for filtering. |
| Migration on existing data | Greenfield: fresh-DB assumption, no backfill (per roadmap convention). |

## Acceptance Criteria

- [ ] `source_xml`/`source_bytes` stored as ciphertext at rest
- [ ] Encryption keys loaded from env only; fail-fast when missing
- [ ] Key rotation works: rows under an old key still decrypt; `rotate` command re-encrypts under newest
- [ ] All PII security tests pass
- [ ] `uv run pytest` green
