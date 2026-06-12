# learningProject

Learning project — React + FastAPI pipeline skeleton.

## Stack

- **Frontend:** Vite + React 19 + TypeScript + Tailwind + TanStack Query
- **Backend:** FastAPI + Python 3.12 (async, managed by uv)
- **Infra:** Postgres 16, Qdrant, Docker Compose

## Ports

| Service | Host port |
|---|---|
| Postgres | 5433 |
| Qdrant | 6433 / 6434 |
| Backend | 8001 |
| Frontend | 5174 |

## M0 Smoke Test

### Option A — Full Docker Compose

```bash
cp backend/.env.example backend/.env
# Set OPENROUTER_API_KEY in backend/.env
docker compose up -d --build
# Open http://localhost:5174 — all rows green + LLM reply
```

### Option B — Local dev (infra only in Docker)

```bash
docker compose up -d db qdrant

# Backend
cd backend
cp ../.env.example .env  # or create backend/.env with your key
uv sync
uv run fastapi dev app/main.py --port 8001

# Frontend (new terminal)
cd frontend
cp .env.local.example .env.local
npm install
npm run dev
# Open http://localhost:5174
```

## Tests

```bash
# Backend
cd backend && uv run pytest -v

# Frontend
cd frontend && npm test && npm run build
```

## Development

```bash
# Backend routes → backend/app/routers/
# Register router in backend/app/main.py

# Frontend components → frontend/src/components/
# API calls → frontend/src/api.ts (reads VITE_API_URL)
```
