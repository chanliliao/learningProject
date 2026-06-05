# AGENTS.md — learningProject

Rules and context for AI agents working in this repo.

## Stack

- **Frontend:** React 19 + Vite 8 + TypeScript — lives in `frontend/`
- **Backend:** FastAPI + Python 3.12 + uv — lives in `backend/`

## Hard Rules

1. Read every file before editing it.
2. Grep all callers before modifying a function signature.
3. No inline secrets — API keys go in `.env.local` (FE) or `.env` (BE), never in source.
4. No shell execution from user input — never pass user-supplied data to `subprocess`.

## Directory Map

| Path | Purpose |
|---|---|
| `frontend/src/components/` | React components |
| `frontend/src/` | App entry, pages, hooks |
| `backend/app/main.py` | FastAPI app instance + route registration |
| `backend/app/routers/` | Route modules (one file per domain) |
| `backend/tests/` | pytest tests |
| `frontend/src/*.test.tsx` | Vitest tests |

## Adding a New API Route

1. Create `backend/app/routers/<name>.py` with an `APIRouter`.
2. Import and register it in `backend/app/main.py` via `app.include_router(...)`.
3. Write test in `backend/tests/test_<name>.py` first.

## Adding a New Frontend Component

1. Create `frontend/src/components/<Name>.tsx`.
2. Write test in `frontend/src/components/<Name>.test.tsx` first.

## Commit Style

Use conventional commits: `feat:`, `fix:`, `chore:`, `docs:`, `test:`.
