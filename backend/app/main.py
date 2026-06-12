import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import SQLModel
import app.models  # noqa: F401 — register all tables
from app.config import get_settings
from app.db import get_engine
from app.routers import health as health_router
from app.routers import pipeline as pipeline_router
from app.routers import review as review_router
from app.routers import eval as eval_router
from app.routers import support as support_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI):
    try:
        async with get_engine().begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
    except Exception as e:
        logger.warning("DB create_all failed (run alembic upgrade head): %s", e)

    # Wire LangGraph checkpointer: Postgres when available, MemorySaver as fallback
    from langgraph.checkpoint.memory import MemorySaver
    s = get_settings()
    checkpointer = None

    if "postgresql" in s.database_url:
        try:
            pg_url = s.database_url.replace("+asyncpg", "").replace("+psycopg", "")
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
            async with AsyncPostgresSaver.from_conn_string(pg_url) as cp:
                await cp.setup()
                application.state.checkpointer = cp
                logger.info("LangGraph checkpointer: AsyncPostgresSaver")
                yield
                return
        except Exception as e:
            logger.warning("Postgres checkpointer unavailable (%s); using MemorySaver", e)

    application.state.checkpointer = MemorySaver()
    logger.info("LangGraph checkpointer: MemorySaver")
    yield


app = FastAPI(title="learningProject API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router.router, prefix="/api")
app.include_router(pipeline_router.router, prefix="/api")
app.include_router(review_router.router, prefix="/api")
app.include_router(eval_router.router, prefix="/api")
app.include_router(support_router.router, prefix="/api")
