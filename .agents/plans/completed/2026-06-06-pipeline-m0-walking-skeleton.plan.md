# Plan: Pipeline — Milestone 0 (Walking Skeleton: wire all tech end-to-end)

> **For implementers:** Execute in order. TDD where a test fits; for infra/manual steps, the
> "verify" step is the gate — do not proceed until it passes. Reference spec:
> `.agents/specs/2026-06-06-pipeline-design.md`.

## Summary

Before building any pipeline logic, prove the **entire technology stack connects end-to-end** with
the simplest possible code, using the project's real conventions: **async backend**, **TanStack
Query** frontend, and **full Docker Compose** (Postgres, Qdrant, backend, frontend). Stand up the
containers, start the async FastAPI backend, start the Vite/React/Tailwind frontend, connect
frontend → backend over a health API (TanStack Query), and make the backend hit the LLM (OpenRouter
via PydanticAI) and return a simple response — surfaced in the browser. Each piece is added and
verified one at a time so any failure (bad image, wrong port, connection string, CORS, missing key)
surfaces immediately on a tiny surface.

**Definition of done:** `docker-compose up -d` runs all four services; the browser at
`http://localhost:5174` shows green status for backend health, Postgres, Qdrant, and a live one-line
LLM reply.

## Ports (host) — avoid existing services on 5432/6333/3000/8000

| Service | Container | Host |
|---|---|---|
| Postgres | 5432 | **5433** |
| Qdrant HTTP / gRPC | 6333 / 6334 | **6433 / 6434** |
| Backend | 8000 | **8001** |
| Frontend (Vite) | 5173 | **5174** |

## User Story

As the developer
I want a minimal end-to-end slice where every technology is wired and verified on non-conflicting ports
So that I can add pipeline features on a known-good foundation.

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY (foundation) |
| Complexity | MEDIUM |
| Milestone | M0 of (M0→M4) |
| Systems Affected | docker, backend (async FastAPI, Postgres, Qdrant, PydanticAI, Langfuse), frontend (Vite+React+Tailwind+TanStack Query) |
| Jira Issue | N/A |

---

## Conventions (per spec — apply throughout)

- **Async backend:** `async def` handlers; async SQLAlchemy (`create_async_engine`, asyncpg driver);
  PydanticAI `await agent.run(...)`. FastAPI `TestClient` drives async endpoints in tests.
- **TanStack Query** for all frontend backend calls.
- **Full compose:** backend + frontend have Dockerfiles; local `uv`/`npm` dev still available.
- **Smallest change → verify (gate) → commit.** Never stack two unverified integrations.

---

## Patterns to Follow

### Backend route + test
```python
# SOURCE: backend/app/main.py:1-8 / backend/tests/test_health.py:1-10
@app.get("/health")
def health() -> dict: return {"status": "ok"}
```
```python
from fastapi.testclient import TestClient
from app.main import app
client = TestClient(app)
def test_health_returns_ok():
    assert client.get("/health").json() == {"status": "ok"}
```

### Frontend test — `frontend/src/App.test.tsx:1-7`; `npm test`=`vitest run` (`package.json:6-13`).

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `docker-compose.yml` | CREATE | db + qdrant + backend + frontend (alt ports) |
| `backend/Dockerfile` | CREATE | Backend image (uv) |
| `frontend/Dockerfile` | CREATE | Frontend dev image (vite) |
| `backend/pyproject.toml` | UPDATE | async + stack deps |
| `backend/.env.example` | CREATE | env keys (alt ports) |
| `backend/app/config.py` | CREATE | settings |
| `backend/app/db.py` | CREATE | async engine + ping |
| `backend/app/main.py` | UPDATE | CORS (5174) + health routers |
| `backend/app/routers/health.py` | CREATE | /health/db, /health/qdrant, /health/llm |
| `backend/app/llm/client.py` | CREATE | minimal async PydanticAI call |
| `frontend/tailwind.config.js`, `postcss.config.js`, `src/index.css` | CREATE/UPDATE | Tailwind |
| `frontend/src/api.ts` | CREATE | backend client (VITE_API_URL) |
| `frontend/src/queryClient.ts`, `src/main.tsx` | CREATE/UPDATE | TanStack Query provider |
| `frontend/src/App.tsx` | UPDATE | status dashboard (useQuery) |
| `frontend/vite.config.ts` | UPDATE | dev server port 5174 |
| `frontend/.env.local.example` | CREATE | VITE_API_URL=http://localhost:8001 |
| tests (be + fe) | CREATE | per task |

---

## Story A — Infrastructure (compose, infra services first)

### Task A.1: Compose with Postgres + Qdrant (alt ports)

- **File:** `docker-compose.yml` (CREATE)
- [ ] **Step 1 — write** (app services added later in Story E):

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_USER: pipeline
      POSTGRES_PASSWORD: pipeline
      POSTGRES_DB: pipeline
    ports: ["5433:5432"]
    volumes: ["pgdata:/var/lib/postgresql/data"]
  qdrant:
    image: qdrant/qdrant:latest
    ports: ["6433:6333", "6434:6334"]
    volumes: ["qdrantdata:/qdrant/storage"]
volumes:
  pgdata:
  qdrantdata:
```

- [ ] **Step 2 — verify (gate):** `docker-compose up -d`; `docker-compose ps` shows both up;
  `curl http://localhost:6433/healthz` ok; `pg_isready -h localhost -p 5433` ok.
- [ ] **Step 3 — commit:** `chore: add postgres + qdrant compose on alt ports`

---

## Story B — Backend baseline (async)

### Task B.1: Dependencies

- **File:** `backend/pyproject.toml` (UPDATE) — mirror `:7-15`
- [ ] **Step 1 — add** to `[project].dependencies`: `pydantic-settings>=2.5`,
  `sqlalchemy[asyncio]>=2.0`, `asyncpg>=0.30`, `psycopg[binary]>=3.2` (for Alembic later),
  `qdrant-client>=1.12`, `pydantic-ai-slim[openai]>=0.0.14`, `langfuse>=2.50`.
- [ ] **Step 2 — verify (gate):** `cd backend && uv sync`; confirm
  `import asyncpg, qdrant_client; from sqlalchemy.ext.asyncio import create_async_engine; from pydantic_ai import Agent`.
- [ ] **Step 3 — commit:** `chore: add async backend stack deps`

### Task B.2: Settings + env

- **Files:** `backend/app/config.py`, `backend/.env.example` (CREATE)
- [ ] **Step 1 — failing test** `backend/tests/test_config.py`: set env; assert `get_settings()`
  exposes `database_url`, `openrouter_api_key`, `qdrant_url`, `llm_mode in ("real","test")`,
  `embeddings_provider in ("openrouter","fastembed")`.
- [ ] **Step 2 — run** → FAIL.
- [ ] **Step 3 — implement** `app/config.py`:

```python
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+asyncpg://pipeline:pipeline@localhost:5433/pipeline"
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "openai/gpt-4o-mini"
    qdrant_url: str = "http://localhost:6433"
    embeddings_provider: str = "openrouter"   # or "fastembed"
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
DATABASE_URL=postgresql+asyncpg://pipeline:pipeline@localhost:5433/pipeline
QDRANT_URL=http://localhost:6433
EMBEDDINGS_PROVIDER=openrouter
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=https://cloud.langfuse.com
```

- [ ] **Step 6 — commit:** `feat: add settings module and env example`

### Task B.3: CORS + async health wiring

- **File:** `backend/app/main.py` (UPDATE)
- [ ] **Step 1 — failing test** `backend/tests/test_cors.py`: `client.get("/health")` with
  `Origin: http://localhost:5174` returns `access-control-allow-origin`.
- [ ] **Step 2 — run** → FAIL.
- [ ] **Step 3 — implement** add `CORSMiddleware` allowing `http://localhost:5174`. Keep `/health`.
- [ ] **Step 4 — run** → PASS. **Step 5 — commit:** `feat: enable CORS for frontend dev origin (5174)`

### Task B.4: Async Postgres health

- **Files:** `backend/app/db.py`, `backend/app/routers/health.py` (CREATE), `main.py` (UPDATE)
- [ ] **Step 1 — failing test** `backend/tests/routers/test_health_db.py`: override the db-ping
  dependency to return ok → `GET /health/db` `{"status":"ok"}`; override to raise → `503`.
- [ ] **Step 2 — run** → FAIL.
- [ ] **Step 3 — implement** `app/db.py`:

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text
from app.config import get_settings

_engine = None
def get_engine():
    global _engine
    if _engine is None:
        _engine = create_async_engine(get_settings().database_url)
    return _engine

async def ping_db() -> None:
    async with get_engine().connect() as conn:
        await conn.execute(text("SELECT 1"))
```

  `routers/health.py`: `@router.get("/health/db")` `async def` calling `ping_db()`, raising
  `HTTPException(503)` on error. Include router in `main.py`.
- [ ] **Step 4 — verify (gate):** with compose up, `uv run fastapi dev app/main.py --port 8001`,
  `curl localhost:8001/health/db` → ok (real Postgres on 5433).
- [ ] **Step 5 — run** tests → PASS. **Step 6 — commit:** `feat: add async postgres health endpoint`

### Task B.5: Qdrant health

- **File:** `backend/app/routers/health.py` (UPDATE)
- [ ] **Step 1 — failing test** `backend/tests/routers/test_health_qdrant.py`: override qdrant-ping
  dependency; ok → `GET /health/qdrant` ok; raise → 503.
- [ ] **Step 2 — run** → FAIL.
- [ ] **Step 3 — implement** `ping_qdrant()` using `QdrantClient(url=settings.qdrant_url)` →
  `get_collections()` (run in a threadpool via `await run_in_threadpool(...)` since the client is
  sync). `GET /health/qdrant`.
- [ ] **Step 4 — verify (gate):** `curl localhost:8001/health/qdrant` → ok (Qdrant on 6433).
- [ ] **Step 5 — run** tests → PASS. **Step 6 — commit:** `feat: add qdrant health endpoint`

### Task B.6: LLM health (async PydanticAI → OpenRouter)

- **Files:** `backend/app/llm/client.py` (CREATE), `routers/health.py` (UPDATE)
- [ ] **Step 1 — failing test** `backend/tests/routers/test_health_llm.py`: with `llm_mode="test"`
  (PydanticAI `TestModel`), `GET /health/llm` → 200 with a non-empty `reply`. No network.
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

async def ping_llm(mode: str | None = None) -> str:
    agent = Agent(_model(mode), output_type=str, system_prompt="Reply with a short greeting.")
    result = await agent.run("Say hello in five words or fewer.")
    return result.output
```

  `GET /health/llm` (`async def`) → `{"status":"ok","reply": await ping_llm()}`; 503 on error.
- [ ] **Step 4 — verify (gate):** with a real `OPENROUTER_API_KEY`, `curl localhost:8001/health/llm`
  returns a real one-line reply (whole LLM path proven).
- [ ] **Step 5 — run** tests → PASS. **Step 6 — commit:** `feat: add async llm health endpoint`

---

## Story C — Frontend baseline (Tailwind + TanStack Query)

### Task C.1: Vite port + Tailwind

- **Files:** `frontend/vite.config.ts`, `tailwind.config.js`, `postcss.config.js`, `src/index.css`
  (CREATE/UPDATE), `package.json` (UPDATE)
- [ ] **Step 1 — set** Vite dev port: in `vite.config.ts`, `server: { port: 5174, host: true }`.
- [ ] **Step 2 — install:** `npm install -D tailwindcss postcss autoprefixer && npx tailwindcss init -p`;
  set `content: ["./index.html","./src/**/*.{ts,tsx}"]`; add `@tailwind` directives to `index.css`;
  import `index.css` in `main.tsx`.
- [ ] **Step 3 — verify (gate):** `npm run build` ok; `npm run dev` serves on **5174** with a
  Tailwind-styled element.
- [ ] **Step 4 — commit:** `feat: set Vite port 5174 and Tailwind`

### Task C.2: TanStack Query provider + API client

- **Files:** `frontend/package.json`, `src/api.ts`, `src/queryClient.ts`, `src/main.tsx`,
  `.env.local.example` (CREATE/UPDATE)
- [ ] **Step 1 — install:** `npm install @tanstack/react-query`.
- [ ] **Step 2 — implement** `src/api.ts` reading `import.meta.env.VITE_API_URL` (default
  `http://localhost:8001`) with `getHealth/getDbHealth/getQdrantHealth/getLlmHealth`;
  `src/queryClient.ts` exports a `QueryClient`; wrap `<App/>` in `<QueryClientProvider>` in
  `main.tsx`. Write `.env.local.example` `VITE_API_URL=http://localhost:8001`.
- [ ] **Step 3 — commit:** `feat: add TanStack Query provider and API client`

### Task C.3: Status dashboard

- **File:** `frontend/src/App.tsx` (UPDATE), `frontend/src/App.test.tsx` (UPDATE)
- [ ] **Step 1 — failing test** `App.test.tsx`: render `<App/>` inside a `QueryClientProvider` with
  `fetch` mocked (ok for health/db/qdrant, `{reply:"hi"}` for llm); assert it shows Backend,
  Postgres, Qdrant, LLM statuses and the reply (use `findBy*`).
- [ ] **Step 2 — run** `npm test` → FAIL.
- [ ] **Step 3 — implement** `App.tsx` as a Tailwind dashboard using `useQuery` per health check;
  render a green/red row per service + the LLM reply.
- [ ] **Step 4 — run** → PASS. **Step 5 — commit:** `feat: add backend status dashboard (useQuery)`

---

## Story D — Containerize the app

### Task D.1: Backend + frontend Dockerfiles

- **Files:** `backend/Dockerfile`, `frontend/Dockerfile` (CREATE)
- [ ] **Step 1 — backend Dockerfile** (uv base, copy, `uv sync`, run
  `uv run fastapi run app/main.py --host 0.0.0.0 --port 8000`).
- [ ] **Step 2 — frontend Dockerfile** (node base, `npm ci`, dev: `npm run dev -- --host --port 5173`;
  or build + `vite preview`). Dev image is fine for M0.
- [ ] **Step 3 — verify (gate):** `docker build` succeeds for both.
- [ ] **Step 4 — commit:** `chore: add backend and frontend Dockerfiles`

### Task D.2: Add app services to compose

- **File:** `docker-compose.yml` (UPDATE)
- [ ] **Step 1 — add** services:

```yaml
  backend:
    build: ./backend
    env_file: ./backend/.env
    environment:
      DATABASE_URL: postgresql+asyncpg://pipeline:pipeline@db:5432/pipeline
      QDRANT_URL: http://qdrant:6333
    ports: ["8001:8000"]
    depends_on: [db, qdrant]
  frontend:
    build: ./frontend
    environment:
      VITE_API_URL: http://localhost:8001
    ports: ["5174:5173"]
    depends_on: [backend]
```

  (Note: in-container the backend reaches db/qdrant by service name on container ports; host maps
  to 8001/5174.)
- [ ] **Step 2 — verify (gate):** `docker-compose up -d --build`; all four healthy;
  `curl localhost:8001/health/db` and `/health/qdrant` ok from the containerized backend.
- [ ] **Step 3 — commit:** `chore: add backend and frontend to docker-compose`

---

## Story E — End-to-end verification

### Task E.1: Full-stack smoke + docs

- **File:** `README.md` (UPDATE) — add "M0 smoke test"
- [ ] **Step 1 — write** the run sequence (document both paths):
  - **Compose:** copy `backend/.env.example`→`backend/.env`, set `OPENROUTER_API_KEY`;
    `docker-compose up -d --build`; open `http://localhost:5174`.
  - **Local dev:** `docker-compose up -d db qdrant`; backend `uv run fastapi dev app/main.py --port 8001`;
    frontend `npm run dev -- --port 5174`.
- [ ] **Step 2 — verify (gate, MANUAL END-TO-END):** browser at `localhost:5174` shows green for
  Backend, Postgres, Qdrant, and a real one-line **LLM reply**.
- [ ] **Step 3 — run** both suites: `cd backend && uv run pytest -v`; `cd frontend && npm test` → pass.
- [ ] **Step 4 — commit:** `docs: add M0 full-stack smoke test instructions`

---

## Validation

```bash
docker-compose up -d --build                      # db(5433) qdrant(6433) backend(8001) frontend(5174)
cd backend && uv run pytest -v
cd frontend && npm test && npm run build
# browser http://localhost:5174 => all green + live LLM reply
```

## Acceptance Criteria

- [ ] `docker-compose up -d --build` starts all four services on the alt ports (no 5432/6333/3000/8000)
- [ ] Backend (async) serves `/health`, `/health/db`, `/health/qdrant`, `/health/llm` live
- [ ] `/health/llm` returns a real model reply with a valid OpenRouter key
- [ ] Frontend (Vite:5174, Tailwind, TanStack Query) dashboard calls backend via `VITE_API_URL=:8001`
- [ ] CORS allows `http://localhost:5174`
- [ ] Browser shows green for all four + live LLM reply (manual end-to-end gate)
- [ ] All backend + frontend tests pass offline (TestModel, fetch mocked)

---

## What M0 deliberately excludes (later milestones)

- No DB models, migrations, or pipeline logic (M1); no LangGraph nodes (M1).
- No confidence/review/console (M2); no Build/Test/eval (M3); no LlamaIndex/Support RAG (M4).

M0 only proves the wiring. Everything after extends a known-good baseline.
