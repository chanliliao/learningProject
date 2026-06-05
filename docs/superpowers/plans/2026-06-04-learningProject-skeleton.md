# learningProject Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Scaffold a monorepo with a Vite + React + TypeScript frontend and a FastAPI + uv backend, wired to a new GitHub repo.

**Architecture:** Single repo with `frontend/` and `backend/` subdirectories. Frontend calls backend via `VITE_API_URL` env var. Backend exposes a `/health` endpoint to verify the server runs.

**Tech Stack:** React 18, Vite 5, TypeScript, Vitest, @testing-library/react, FastAPI, uv, Python 3.12, pytest, httpx, GitHub CLI (`gh`)

---

### Task 1: Initialize git repo + create GitHub repo

**Files:**
- Create: `.git/` (via `git init`)

- [ ] **Step 1: Init git in project root**

Run from `C:\Users\cliao\Desktop\Coding\Claude Projects\learningProject`:
```bash
git init
```
Expected output: `Initialized empty Git repository in .../learningProject/.git/`

- [ ] **Step 2: Create GitHub repo via gh CLI**

```bash
gh repo create learningProject --public --source=. --remote=origin
```
Expected output: `✓ Created repository cliao119/learningProject on GitHub`

> If `gh` not authenticated, run `gh auth login` first.

- [ ] **Step 3: Verify remote set**

```bash
git remote -v
```
Expected:
```
origin  https://github.com/cliao119/learningProject.git (fetch)
origin  https://github.com/cliao119/learningProject.git (push)
```

---

### Task 2: Create root .gitignore

**Files:**
- Create: `.gitignore`

- [ ] **Step 1: Write .gitignore**

Create `.gitignore` at project root with this content:

```gitignore
# Python
__pycache__/
*.py[cod]
*.pyo
.venv/
.env
dist/
*.egg-info/
.pytest_cache/
.mypy_cache/
.ruff_cache/

# Node
node_modules/
dist/
.env.local
.env.*.local

# OS
.DS_Store
Thumbs.db

# IDE
.vscode/
.idea/
*.swp
```

- [ ] **Step 2: Commit**

```bash
git add .gitignore
git commit -m "chore: add .gitignore"
```

---

### Task 3: Scaffold backend with uv

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/.python-version`
- Create: `backend/app/__init__.py`
- Create: `backend/app/routers/__init__.py`
- Create: `backend/tests/__init__.py`

- [ ] **Step 1: Init uv project**

```bash
cd backend
uv init --no-workspace
```
Expected: creates `pyproject.toml`, `.python-version`, `hello.py` (delete hello.py after)

- [ ] **Step 2: Delete hello.py scaffold file**

```bash
rm hello.py
```

- [ ] **Step 3: Add fastapi and dev deps**

```bash
uv add "fastapi[standard]"
uv add --dev pytest httpx pytest-asyncio
```

- [ ] **Step 4: Set Python version**

```bash
echo "3.12" > .python-version
```

- [ ] **Step 5: Create app package**

```bash
mkdir -p app/routers
touch app/__init__.py
touch app/routers/__init__.py
mkdir -p tests
touch tests/__init__.py
```

- [ ] **Step 6: Verify uv sync works**

```bash
uv sync
```
Expected: no errors, `.venv/` created.

- [ ] **Step 7: Commit**

```bash
cd ..
git add backend/
git commit -m "chore: scaffold backend with uv and fastapi"
```

---

### Task 4: Implement backend health endpoint (TDD)

**Files:**
- Create: `backend/tests/test_health.py`
- Create: `backend/app/main.py`

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_health.py`:

```python
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
cd backend
uv run pytest tests/test_health.py -v
```
Expected: `FAILED` — `ModuleNotFoundError: No module named 'app.main'`

- [ ] **Step 3: Implement health endpoint**

Create `backend/app/main.py`:

```python
from fastapi import FastAPI

app = FastAPI(title="learningProject API")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
```

- [ ] **Step 4: Run test to confirm it passes**

```bash
uv run pytest tests/test_health.py -v
```
Expected:
```
PASSED tests/test_health.py::test_health_returns_ok
1 passed in 0.XXs
```

- [ ] **Step 5: Verify dev server starts**

```bash
uv run fastapi dev app/main.py
```
Expected: `Uvicorn running on http://127.0.0.1:8000`
Stop with Ctrl+C.

- [ ] **Step 6: Commit**

```bash
cd ..
git add backend/app/main.py backend/tests/test_health.py
git commit -m "feat: add FastAPI app with /health endpoint"
```

---

### Task 5: Scaffold frontend with Vite

**Files:**
- Create: `frontend/` (all Vite scaffold files)
- Create: `frontend/.env.example`

- [ ] **Step 1: Scaffold Vite project**

From project root:
```bash
npm create vite@latest frontend -- --template react-ts
```
Expected: creates `frontend/` with React + TypeScript template.

- [ ] **Step 2: Install dependencies**

```bash
cd frontend
npm install
```

- [ ] **Step 3: Add test dependencies**

```bash
npm install --save-dev vitest @testing-library/react @testing-library/jest-dom @testing-library/user-event jsdom
```

- [ ] **Step 4: Create .env.example**

Create `frontend/.env.example`:
```
VITE_API_URL=http://localhost:8000
```

- [ ] **Step 5: Create .env.local for local dev**

```bash
cp .env.example .env.local
```

- [ ] **Step 6: Verify dev server starts**

```bash
npm run dev
```
Expected: `Local: http://localhost:5173/`
Stop with Ctrl+C.

- [ ] **Step 7: Commit**

```bash
cd ..
git add frontend/
git commit -m "chore: scaffold frontend with vite react-ts"
```

---

### Task 6: Wire vitest + write frontend render test (TDD)

**Files:**
- Modify: `frontend/vite.config.ts`
- Create: `frontend/src/App.test.tsx`

- [ ] **Step 1: Add vitest config to vite.config.ts**

Read current `frontend/vite.config.ts`, then replace with:

```typescript
/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.ts'],
  },
})
```

- [ ] **Step 2: Create test setup file**

Create `frontend/src/test-setup.ts`:

```typescript
import '@testing-library/jest-dom'
```

- [ ] **Step 3: Add test script to package.json**

In `frontend/package.json`, add to the `"scripts"` block:
```json
"test": "vitest run",
"test:watch": "vitest"
```

- [ ] **Step 4: Write failing render test**

Create `frontend/src/App.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import App from './App'

test('renders app without crashing', () => {
  render(<App />)
  expect(document.body).toBeTruthy()
})
```

- [ ] **Step 5: Run test to confirm it fails**

```bash
cd frontend
npm test
```
Expected: `FAIL` — missing setup file or import error.

- [ ] **Step 6: Fix tsconfig to include test files**

In `frontend/tsconfig.json`, ensure `"include"` contains `"src"`. If `compilerOptions` lacks `"types"`, add:
```json
"types": ["vitest/globals", "@testing-library/jest-dom"]
```

- [ ] **Step 7: Run test to confirm it passes**

```bash
npm test
```
Expected:
```
✓ src/App.test.tsx > renders app without crashing
Test Files  1 passed (1)
```

- [ ] **Step 8: Commit**

```bash
cd ..
git add frontend/vite.config.ts frontend/src/test-setup.ts frontend/src/App.test.tsx frontend/package.json frontend/tsconfig.json
git commit -m "test: add vitest and frontend render test"
```

---

### Task 7: Add components placeholder

**Files:**
- Create: `frontend/src/components/.gitkeep`

- [ ] **Step 1: Create .gitkeep**

```bash
touch frontend/src/components/.gitkeep
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/.gitkeep
git commit -m "chore: add components directory placeholder"
```

---

### Task 8: Write CLAUDE.md

**Files:**
- Create: `CLAUDE.md`

- [ ] **Step 1: Create CLAUDE.md at project root**

```markdown
# CLAUDE.md — learningProject

## Stack

| Layer | Tech |
|---|---|
| Frontend | React 18 + Vite 5 + TypeScript |
| Backend | FastAPI + Python 3.12 |
| Package manager (BE) | uv |
| Package manager (FE) | npm |
| Testing (BE) | pytest + httpx |
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
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add CLAUDE.md with stack and dev commands"
```

---

### Task 9: Write AGENTS.md

**Files:**
- Create: `AGENTS.md`

- [ ] **Step 1: Create AGENTS.md at project root**

```markdown
# AGENTS.md — learningProject

Rules and context for AI agents working in this repo.

## Stack

- **Frontend:** React 18 + Vite 5 + TypeScript — lives in `frontend/`
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
```

- [ ] **Step 2: Commit**

```bash
git add AGENTS.md
git commit -m "docs: add AGENTS.md with agent rules and directory map"
```

---

### Task 10: Write README + push to GitHub

**Files:**
- Create: `README.md`

- [ ] **Step 1: Create README.md**

```markdown
# learningProject

Learning project — React + FastAPI skeleton.

## Stack

- **Frontend:** Vite + React 18 + TypeScript
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
```

- [ ] **Step 2: Commit README**

```bash
git add README.md
git commit -m "docs: add README with quick start"
```

- [ ] **Step 3: Push all commits to GitHub**

```bash
git push -u origin main
```
Expected: all commits pushed, branch `main` tracked.

- [ ] **Step 4: Verify on GitHub**

```bash
gh repo view --web
```
Expected: opens `https://github.com/cliao119/learningProject` in browser with all files visible.
