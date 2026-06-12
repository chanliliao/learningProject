# Code Review: Pipeline M0 Walking Skeleton

**Scope**: feat/pipeline branch — M0 walking skeleton (all commits vs master)
**Recommendation**: APPROVE with minor notes

## Summary

M0 delivers a functional walking skeleton: async FastAPI backend with three health endpoints (DB/Qdrant/LLM), React 19 dashboard with TanStack Query, Docker Compose for full stack. All 9 backend tests and 1 frontend test pass. TypeScript clean. Code is tight and idiomatic.

## Issues Found

### Critical
None

### High Priority

1. **`db.py` uses module-level mutable global** (`_engine = None` with `global` mutation)
   - Pattern leaks state across tests if engine is not cleared between runs
   - Safer: use dependency injection via FastAPI `Depends` or a lifespan-managed singleton
   - Current test mocks `ping_db` directly so tests pass, but the global survives across test sessions

2. **`QdrantClient` constructed on every request** in `ping_qdrant()`
   - No connection pooling — new TCP handshake each `/health/qdrant` call
   - Low risk now (health check), but will bite when moved to real routes in M1+

### Medium Priority

3. **CORS `allow_origins` hardcoded to single origin** (`http://localhost:5174`)
   - Should come from `settings.cors_origins: list[str]` so staging/prod can override without code change

4. **Frontend `Dockerfile` runs dev server in production** (`npm run dev`)
   - `vite dev` is not for production; should `npm run build` then serve with nginx/`vite preview`
   - No impact for local dev, but misleading and fragile for any real deploy

5. **`frontend/src/queryClient.ts` exports bare `QueryClient` with no config**
   - No `staleTime`, `gcTime`, or retry settings — defaults to 3 retries and instant re-fetch
   - `App.test.tsx` correctly sets `retry: false` for tests; production client should at minimum set `retry: 1`

6. **`test_config.py` doesn't call `get_settings.cache_clear()` after the test**
   - `lru_cache` persists across test module — can pollute other tests that rely on default settings if run order changes

### Suggestions

- `backend/app/llm/__init__.py` — empty init is fine but `client.py` exports only `ping_llm`; as LLM usage grows, consider a thin `LLMClient` class so callers don't reach into internals
- `docker-compose.yml` — `qdrant/qdrant:latest` is unpinned; pin to a specific version for reproducibility
- `frontend/.env.local.example` — good practice to have; confirm it's gitignored (`.env.local` is, `.env.local.example` should be committed)

## Validation Results

| Check | Status |
|-------|--------|
| Backend tests (pytest) | PASS — 9/9 |
| Frontend tests (vitest) | PASS — 1/1 |
| TypeScript (`tsc --noEmit`) | PASS |

## What's Good

- Clean separation: routers, config, db, llm all in distinct modules
- `monkeypatch` strategy in backend tests is correct — patches at the module that imports, not the source module
- `lru_cache` on `get_settings()` is idiomatic pydantic-settings pattern
- `run_in_threadpool` for sync Qdrant client is the right FastAPI pattern
- `llm_mode = "test"` escape hatch in `_model()` is clean
- TanStack Query `queryKey` naming is consistent
- Frontend test wraps with `QueryClientProvider` and stubs `fetch` properly

## Recommendation

M0 goal achieved — skeleton walks. Fix the Dockerfile prod issue (#4) before M4 deploy work. The `_engine` global (#1) and per-request Qdrant client (#2) should be addressed in M1 when real routes start hitting those services.
