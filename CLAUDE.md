# CLAUDE.md — learningProject

## Stack

| Layer | Tech |
|---|---|
| Frontend | React 19 + Vite 8 + TypeScript |
| Backend | FastAPI + Python 3.12 |
| Package manager (BE) | uv |
| Package manager (FE) | npm |
| Testing (BE) | pytest + httpx2 |
| Testing (FE) | vitest + @testing-library/react |

## Project Structure

```
learningProject/
├── frontend/      # Vite + React + TypeScript SPA
├── backend/       # FastAPI REST API
├── CLAUDE.md
└── AGENTS.md
```

## Dev Commands

| Task | Command |
|---|---|
| Start frontend | `cd frontend && npm run dev` |
| Start backend | `cd backend && uv run fastapi dev app/main.py` |
| Run FE tests | `cd frontend && npm test` |
| Run BE tests | `cd backend && uv run pytest` |
| Install FE deps | `cd frontend && npm install` |
| Install BE deps | `cd backend && uv sync` |

## Environment Variables

Frontend reads from `frontend/.env.local` (gitignored):
- `VITE_API_URL` — backend base URL (default: `http://localhost:8000`)

## Rules

- No inline secrets. Use `.env.local` for frontend, `.env` for backend.
- Read files before editing. Grep callers before modifying functions.
- Backend routes go in `backend/app/routers/`. Register in `backend/app/main.py`.
- Frontend components go in `frontend/src/components/`.
