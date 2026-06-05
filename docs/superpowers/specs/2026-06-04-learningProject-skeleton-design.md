# learningProject Skeleton Design

**Date:** 2026-06-04  
**Status:** Approved

---

## Overview

Monorepo skeleton for a React (Vite + TypeScript) frontend and Python (FastAPI + uv) backend. Purpose is learning — no business domain yet. Structure is ready to grow into any application.

---

## Repository Structure

```
learningProject/
├── frontend/                  # Vite + React + TypeScript
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   └── components/
│   ├── index.html
│   ├── package.json
│   ├── tsconfig.json
│   └── vite.config.ts
├── backend/                   # FastAPI + uv
│   ├── app/
│   │   ├── main.py
│   │   └── routers/
│   ├── pyproject.toml
│   └── .python-version
├── .gitignore
├── CLAUDE.md
├── AGENTS.md
└── README.md
```

---

## Frontend

- **Framework:** Vite + React 18 + TypeScript
- **Dev server:** `npm run dev` → localhost:5173
- **API base URL:** read from `VITE_API_URL` env var (`.env.local` for local dev)
- `components/` directory empty — ready for feature work

---

## Backend

- **Framework:** FastAPI
- **Runtime:** Python 3.12, managed by uv
- **Dev server:** `uv run fastapi dev app/main.py` → localhost:8000
- **Routes:**
  - `GET /health` → `{"status": "ok"}` — confirms server is running
- `routers/` directory empty — ready for feature routes

---

## Dev Commands

| Task | Command |
|---|---|
| Start frontend | `cd frontend && npm run dev` |
| Start backend | `cd backend && uv run fastapi dev app/main.py` |
| Install FE deps | `cd frontend && npm install` |
| Install BE deps | `cd backend && uv sync` |

---

## CLAUDE.md Contents

- Stack summary (React + Vite + TS frontend, FastAPI + uv backend)
- Project structure overview
- Dev commands
- Key conventions (env vars, no inline secrets)

## AGENTS.md Contents

- Agent rules: read before edit, grep callers before modifying functions
- Stack context for agents
- Directory map
- No inline secrets rule

---

## GitHub

- New public repo: `learningProject`
- Remote: `origin` → `https://github.com/cliao119/learningProject`
- Initial commit includes all scaffold files
