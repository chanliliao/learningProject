# Plan: Pipeline — Milestone 0 (Walking Skeleton: wire all tech end-to-end)

> **For implementers:** Execute in order. TDD where a test fits; for infra/manual steps, the
> "verify" step is the gate — do not proceed until it passes. Reference spec:
> `.agents/specs/2026-06-06-pipeline-design.md`.

## Summary

Before building any pipeline logic, prove the **entire technology stack connects end-to-end** with
the simplest possible code. Stand up Docker (Postgres + Qdrant), start the FastAPI backend, start the
Vite frontend, connect frontend → backend over a health API, and make the backend hit the LLM
(OpenRouter via PydanticAI) and return a simple response — surfaced in the browser. Each piece is
added and verified one at a time so that any failure (bad Docker image, wrong connection string,
CORS, missing key) surfaces immediately on a tiny surface, not buried under complex code. This is the
baseline every later milestone builds on.

**Definition of done:** `docker-compose up -d` runs; backend starts; frontend starts; the browser
shows green status for backend health, Postgres, Qdrant, and a live one-line LLM reply.

## User Story

As the developer
I want a minimal end-to-end slice where every technology is wired and verified
So that I can add pipeline features on a known-good foundation instead of debugging integration and
feature code at the same time.

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY (foundation) |
| Complexity | MEDIUM |
| Milestone | M0 of (M0→M4) |
| Systems Affected | docker, backend (FastAPI, Postgres, Qdrant, PydanticAI, Langfuse), frontend (Vite+React+Tailwind) |
| Jira Issue | N/A |

---

## Patterns to Follow

### Backend route + test
```python
# SOURCE: backend/app/main.py:1-8  /  backend/tests/test_health.py:1-10
from fastapi import FastAPI
app = FastAPI(title="learningProject API")

@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
```
```python
from fastapi.testclient import TestClient
from app.main import app
client = TestClient(app)
def test_health_returns_ok():
    assert client.get("/health").json() == {"status": "ok"}
```

### Frontend test
```tsx
# SOURCE: frontend/src/App.test.tsx:1-7
import { render, screen } from '@testing-library/react'
import App from './App'
test('renders app without crashing', () => {
  render(<App />)
  expect(screen.getByRole('heading', { name: /get started/i })).toBeInTheDocument()
})
```

---

## Principle for this milestone

**Smallest change, then verify, then commit.** Never stack two unverified integrations. If a verify
step fails, fix it before writing the next task's code. Each task ends in a working, committed state.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `docker-compose.yml` | CREATE | Postgres + Qdrant |
| `backend/pyproject.toml` | UPDATE | Minimal stack deps |
| `backend/.env.example` | CREATE | env keys |
| `backend/app/config.py` | CREATE | settings from env |
| `backend/app/db.py` | CREATE | engine + SELECT 1 ping |
| `backend/app/main.py` | UPDATE | CORS + health routers |
| `backend/app/routers/health.py` | CREATE | /health/db, /health/qdrant, /health/llm |
| `backend/app/llm/client.py` | CREATE | minimal PydanticAI call |
| `frontend/tailwind.config.js`, `postcss.config.js`, `src/index.css` | CREATE/UPDATE | Tailwind |
| `frontend/src/api.ts` | CREATE | backend client (VITE_API_URL) |
| `frontend/src/App.tsx` | UPDATE | status dashboard |
| `frontend/.env.local.example` | CREATE | VITE_API_URL |
| tests (be + fe) | CREATE | per task |

---

## Story A — Infrastructure up

### Task A.1: Docker Postgres + Qdrant

- **File:** `docker-compose.yml` (CREATE)
- [ ] **Step 1 — write:**

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_USER: pipeline
      POSTGRES_PASSWORD: pipeline
      POSTGRES_DB: pipeline
    ports: ["5432:5432"]
    volumes: ["pgdata:/var/lib/postgresql/data"]
  qdrant:
    image: qdrant/qdrant:latest
    ports: ["6333:6333", "6334:6334"]
    volumes: ["qdrantdata:/qdrant/storage"]
volumes:
  pgdata:
  qdrantdata:
```

- [ ] **Step 2 — verify (gate):** `docker-compose up -d`; `docker-compose ps` shows both running;
  `curl http://localhost:6333/healthz` returns ok; `docker exec` psql `SELECT 1` works (or
  `pg_isready`). If image pull or start fails, fix here before anything else.
- [ ] **Step 3 — commit:** `chore: add postgres + qdrant docker-compose`

---

## Story B — Backend baseline

### Task B.1: Minimal stack dependencies

- **File:** `backend/pyproject.toml` (UPDATE) — mirror `:7-15`
- [ ] **Step 1 — add** to `[project].dependencies`: `pydantic-settings>=2.5`,
  `psycopg[binary]>=3.2`, `sqlalchemy>=2.0`, `qdrant-client>=1.12`,
  `pydantic-ai-slim[openai]>=0.0.14`, `langfuse>=2.50`.
- [ ] **Step 2 — verify (gate):** `cd backend && uv sync` succeeds; in `uv run python -c` confirm
  `import psycopg, qdrant_client; from pydantic_ai import Agent; from langfuse import Langfuse`.
- [ ] **Step 3 — commit:** `chore: add minimal backend stack deps`

### Task B.2: Settings

- **Files:** `backend/app/config.py`, `backend/.env.example` (CREATE)
- [ ] **Step 1 — failing test** `backend/tests/test_config.py`: set env, assert `get_settings()`
  exposes `database_url`, `openrouter_api_key`, `qdrant_url`, `llm_mode in ("real","test")`.
- [ ] **Step 2 — run** → FAIL.
- [ ] **Step 3 — implement** `app/config.py` (this is the project's settings module, reused by all
  milestones):

```python
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://pipeline:pipeline@localhost:5432/pipeline"
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "openai/gpt-4o-mini"
    qdrant_url: str = "http://localhost:6333"
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"
    llm_mode: str = "real"   # "test" => offline
    confidence_threshold: float = 0.8

@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 4 — run** → PASS.
- [ ] **Step 5 — write** `backend/.env.example`:

```
OPENROUTER_API_KEY=
DATABASE_URL=postgresql+psycopg://pipeline:pipeline@localhost:5432/pipeline
QDRANT_URL=http://localhost:6333
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=https://cloud.langfuse.com
```

- [ ] **Step 6 — commit:** `feat: add settings module and env example`

### Task B.3: CORS + health wiring

- **File:** `backend/app/main.py` (UPDATE)
- [ ] **Step 1 — failing test** `backend/tests/test_cors.py`: `client.get("/health")` with an
  `Origin: http://localhost:5173` header returns `access-control-allow-origin`.
- [ ] **Step 2 — run** → FAIL.
- [ ] **Step 3 — implement:** add `CORSMiddleware` allowing `http://localhost:5173` (frontend dev
  origin). Keep existing `/health`.
- [ ] **Step 4 — run** → PASS. **Step 5 — commit:** `feat: enable CORS for frontend dev origin`

### Task B.4: Postgres health endpoint

- **Files:** `backend/app/db.py`, `backend/app/routers/health.py` (CREATE), `main.py` (UPDATE)
- [ ] **Step 1 — failing test** `backend/tests/routers/test_health_db.py`: override the DB ping
  dependency to return ok; `GET /health/db` → `{"status":"ok"}`. Add a test where the ping raises →
  `503`.
- [ ] **Step 2 — run** → FAIL.
- [ ] **Step 3 — implement** `app/db.py` with `get_engine()` and `ping_db()` running `SELECT 1`;
  `routers/health.py` `GET /health/db` returning ok or raising `HTTPException(503)`; include router
  in `main.py`.
- [ ] **Step 4 — verify (gate):** with `docker-compose up -d`, run `uv run fastapi dev app/main.py`
  and `curl localhost:8000/health/db` → ok. (Confirms real Postgres connection string works.)
- [ ] **Step 5 — run** tests → PASS. **Step 6 — commit:** `feat: add postgres health endpoint`

### Task B.5: Qdrant health endpoint

- **File:** `backend/app/routers/health.py` (UPDATE)
- [ ] **Step 1 — failing test** `backend/tests/routers/test_health_qdrant.py`: override the qdrant
  ping dependency; `GET /health/qdrant` → ok; failure → `503`.
- [ ] **Step 2 — run** → FAIL.
- [ ] **Step 3 — implement** a `ping_qdrant()` using `QdrantClient(url=settings.qdrant_url)` calling
  `get_collections()`; `GET /health/qdrant`.
- [ ] **Step 4 — verify (gate):** `curl localhost:8000/health/qdrant` → ok with Qdrant up.
- [ ] **Step 5 — run** tests → PASS. **Step 6 — commit:** `feat: add qdrant health endpoint`

### Task B.6: LLM health endpoint (PydanticAI → OpenRouter)

- **Files:** `backend/app/llm/client.py` (CREATE), `routers/health.py` (UPDATE)
- [ ] **Step 1 — failing test** `backend/tests/routers/test_health_llm.py`: with `llm_mode="test"`
  (PydanticAI `TestModel`), `GET /health/llm` → 200 with a non-empty `reply` string. No network.
- [ ] **Step 2 — run** → FAIL.
- [ ] **Step 3 — implement** `app/llm/client.py`:

```python
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider
from app.config import get_settings

def _model(mode: str | None = None):
    s = get_settings()
    if (mode or s.llm_mode) == "test":
        return TestModel()
    return OpenAIModel(s.openrouter_model,
        provider=OpenAIProvider(base_url=s.openrouter_base_url, api_key=s.openrouter_api_key))

def ping_llm(mode: str | None = None) -> str:
    agent = Agent(_model(mode), output_type=str, system_prompt="Reply with a short greeting.")
    return agent.run_sync("Say hello in five words or fewer.").output
```

  Then `GET /health/llm` returns `{"status":"ok","reply": ping_llm()}`; on exception → `503`.
- [ ] **Step 4 — verify (gate):** with a real `OPENROUTER_API_KEY` in `backend/.env`,
  `curl localhost:8000/health/llm` returns a real one-line model reply. (Confirms the whole LLM path:
  key, OpenRouter, PydanticAI.)
- [ ] **Step 5 — run** tests → PASS. **Step 6 — commit:** `feat: add llm health endpoint via PydanticAI/OpenRouter`

---

## Story C — Frontend baseline

### Task C.1: Tailwind setup

- **Files:** `frontend/tailwind.config.js`, `frontend/postcss.config.js`, `frontend/src/index.css`
  (CREATE/UPDATE), `frontend/package.json` (UPDATE)
- [ ] **Step 1 — install:** `cd frontend && npm install -D tailwindcss postcss autoprefixer && npx tailwindcss init -p`
- [ ] **Step 2 — configure** `content: ["./index.html","./src/**/*.{ts,tsx}"]`; add the three
  `@tailwind` directives to `src/index.css`; ensure `index.css` is imported in `main.tsx`.
- [ ] **Step 3 — verify (gate):** `npm run build` succeeds; `npm run dev` renders a Tailwind-styled
  element (e.g. a `className="text-2xl font-bold"` heading) correctly in the browser.
- [ ] **Step 4 — commit:** `feat: set up Tailwind CSS`

### Task C.2: Backend API client + status dashboard

- **Files:** `frontend/src/api.ts`, `frontend/src/App.tsx` (CREATE/UPDATE),
  `frontend/.env.local.example` (CREATE)
- [ ] **Step 1 — failing test** `frontend/src/App.test.tsx` (replace template test): mock `fetch` to
  return ok for `/health`, `/health/db`, `/health/qdrant`, and `{reply:"hi"}` for `/health/llm`;
  render `<App />`; assert it shows a "Backend", "Postgres", "Qdrant", and "LLM" status and the LLM
  reply text. Use `@testing-library` `findBy*` for the async results.
- [ ] **Step 2 — run** `npm test` → FAIL.
- [ ] **Step 3 — implement** `src/api.ts` reading `import.meta.env.VITE_API_URL` (default
  `http://localhost:8000`) with helpers `getHealth()`, `getDbHealth()`, `getQdrantHealth()`,
  `getLlmHealth()`. Rewrite `App.tsx` as a Tailwind status dashboard that calls all four on mount and
  renders a row per service (green/red) plus the LLM reply. Write `.env.local.example` with
  `VITE_API_URL=http://localhost:8000`.
- [ ] **Step 4 — run** `npm test` → PASS.
- [ ] **Step 5 — commit:** `feat: add backend status dashboard frontend`

---

## Story D — End-to-end verification

### Task D.1: Full-stack smoke + docs

- **File:** `README.md` (UPDATE) — add an "M0 smoke test" section
- [ ] **Step 1 — write** the exact run sequence:
  1. `docker-compose up -d`
  2. backend: copy `.env.example`→`.env`, set `OPENROUTER_API_KEY`, `uv sync`,
     `uv run fastapi dev app/main.py`
  3. frontend: copy `.env.local.example`→`.env.local`, `npm install`, `npm run dev`
  4. open `http://localhost:5173`
- [ ] **Step 2 — verify (gate, MANUAL END-TO-END):** browser shows green for Backend, Postgres,
  Qdrant, and a real one-line **LLM reply**. This is the milestone's whole point — confirm it live.
- [ ] **Step 3 — run** both suites: `cd backend && uv run pytest -v` and `cd frontend && npm test` →
  all pass.
- [ ] **Step 4 — commit:** `docs: add M0 full-stack smoke test instructions`

---

## Validation

```bash
docker-compose up -d
cd backend && uv sync && uv run pytest -v        # backend tests pass
uv run fastapi dev app/main.py                   # then curl the 4 health endpoints
cd frontend && npm install && npm test           # frontend tests pass
npm run dev                                       # browser dashboard all green + LLM reply
```

## Acceptance Criteria

- [ ] `docker-compose up -d` starts Postgres + Qdrant (verified, not assumed)
- [ ] Backend starts; `/health`, `/health/db`, `/health/qdrant`, `/health/llm` all return ok live
- [ ] `/health/llm` returns a real model reply with a valid OpenRouter key
- [ ] Frontend starts with Tailwind; dashboard calls backend via `VITE_API_URL`
- [ ] CORS allows the frontend dev origin
- [ ] Browser shows green status for all four + the live LLM reply (manual end-to-end gate)
- [ ] All backend + frontend tests pass offline (LLM via TestModel, fetch mocked)

---

## What M0 deliberately excludes (added in later milestones)

- No DB models, migrations, or pipeline logic (M1).
- No LangGraph graph, Extract/Map nodes, or structured mapping (M1).
- No confidence scoring, review gates, or full review console (M2).
- No Build/Test/eval (M3); no LlamaIndex indexing / Support RAG (M4).

M0 only proves the wiring. Everything after it extends a known-good baseline.
