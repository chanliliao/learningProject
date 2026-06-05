# learningProject

Learning project — React + FastAPI skeleton.

## Stack

- **Frontend:** Vite + React 19 + TypeScript
- **Backend:** FastAPI + Python 3.12 (managed by uv)

## Quick Start

**Backend:**
```bash
cd backend
uv sync
uv run fastapi dev app/main.py
# → http://localhost:8000
# → http://localhost:8000/docs
```

**Frontend:**
```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
# → http://localhost:5173
```

## Tests

```bash
# Backend
cd backend && uv run pytest

# Frontend
cd frontend && npm test
```
