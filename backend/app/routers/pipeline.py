"""
Pipeline router: document upload and run status endpoints.

Provides the endpoints that start a new mapping run (``POST /runs``), list available
target schemas (``GET /schemas``), fetch run state (``GET /runs/{id}``), and retrieve
the audit log (``GET /runs/{id}/audit``).
"""

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from app.db import get_session
from app.models.run import PipelineRun, StageResult
from app.models.mapping import FieldMapping
from app.models.schema import TargetSchema
from app.models.audit import AuditEvent
from app.graph.build import start_run

router = APIRouter()


def get_checkpointer(request: Request):
    """FastAPI dependency that returns the application-level LangGraph checkpointer.

    The checkpointer is set on ``app.state.checkpointer`` during the FastAPI lifespan
    (``AsyncPostgresSaver`` when Postgres is available, ``MemorySaver`` as fallback).
    When no checkpointer is found on app state (e.g. in tests that bypass lifespan),
    a fresh ``MemorySaver`` is returned.

    Args:
        request: FastAPI request object used to access ``app.state``.

    Returns:
        The active LangGraph checkpointer instance.
    """
    cp = getattr(request.app.state, "checkpointer", None)
    if cp is None:
        from langgraph.checkpoint.memory import MemorySaver
        return MemorySaver()
    return cp


def get_llm_mode() -> str | None:
    """FastAPI dependency that returns the LLM mode override for a request.

    Currently always returns ``None``, which causes ``_model()`` to read the mode
    from ``Settings.llm_mode``.  Override this dependency in tests to force test mode
    without modifying the global settings.

    Returns:
        ``None`` (reads from ``Settings.llm_mode``).
    """
    return None


@router.post("/runs", status_code=201)
async def create_run(
    file: UploadFile,
    target_schema_id: int = Form(...),
    session: AsyncSession = Depends(get_session),
    checkpointer=Depends(get_checkpointer),
    mode: str | None = Depends(get_llm_mode),
):
    """Start a new pipeline run by uploading an ACORD XML document.

    Creates a ``PipelineRun`` record, then calls ``start_run`` synchronously (sharing
    the same DB session).  The pipeline runs until the first interrupt gate and returns
    with the run in ``status="awaiting_review"``.

    Args:
        file: Uploaded XML file.
        target_schema_id: ID of the ``TargetSchema`` to map the document into.
        session: Injected async DB session.
        checkpointer: Injected LangGraph checkpointer.
        mode: LLM mode override (``None`` reads from settings).

    Returns:
        JSON with ``run_id`` and the run's current ``status``.

    Raises:
        HTTPException 404: If ``target_schema_id`` does not exist.
    """
    schema = (await session.exec(select(TargetSchema).where(TargetSchema.id == target_schema_id))).first()
    if schema is None:
        raise HTTPException(status_code=404, detail=f"TargetSchema {target_schema_id} not found")
    xml_bytes = await file.read()
    xml_str = xml_bytes.decode("utf-8", errors="replace")
    run = PipelineRun(
        source_filename=file.filename or "upload.xml",
        source_xml=xml_str,
        target_schema_id=target_schema_id,
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    await start_run(run.id, session, checkpointer=checkpointer, mode=mode)
    await session.commit()
    await session.refresh(run)
    return {"run_id": run.id, "status": run.status}


@router.get("/schemas")
async def list_schemas(session: AsyncSession = Depends(get_session)):
    """List all available target schemas.

    Used by the upload page to populate the schema selector dropdown.

    Args:
        session: Injected async DB session.

    Returns:
        List of dicts with ``id``, ``name``, and ``version`` for each schema.
    """
    schemas = (await session.exec(select(TargetSchema))).all()
    return [{"id": s.id, "name": s.name, "version": s.version} for s in schemas]


@router.get("/runs/{run_id}")
async def get_run(run_id: int, session: AsyncSession = Depends(get_session)):
    """Fetch the full state of a pipeline run.

    Returns the run record, all stage results, all field mappings, and the full audit
    log in a single response.  The review UI polls this endpoint while the run is
    ``"running"`` and after each gate approval.

    Args:
        run_id: ID of the ``PipelineRun`` to fetch.
        session: Injected async DB session.

    Returns:
        JSON with keys ``run``, ``stage_results``, ``mappings``, and ``audit``.

    Raises:
        HTTPException 404: If ``run_id`` does not exist.
    """
    run = (await session.exec(select(PipelineRun).where(PipelineRun.id == run_id))).first()
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    stages = (await session.exec(select(StageResult).where(StageResult.run_id == run_id))).all()
    mappings = (await session.exec(select(FieldMapping).where(FieldMapping.run_id == run_id))).all()
    audit = (await session.exec(select(AuditEvent).where(AuditEvent.run_id == run_id))).all()
    return {
        "run": run.model_dump(),
        "stage_results": [s.model_dump() for s in stages],
        "mappings": [m.model_dump() for m in mappings],
        "audit": [a.model_dump() for a in audit],
    }


@router.get("/runs/{run_id}/audit")
async def get_run_audit(run_id: int, session: AsyncSession = Depends(get_session)):
    """Fetch only the audit log for a pipeline run.

    Lighter alternative to ``GET /runs/{id}`` when only the audit trail is needed.

    Args:
        run_id: ID of the ``PipelineRun`` to query.
        session: Injected async DB session.

    Returns:
        List of audit event dicts ordered by creation time (ascending).

    Raises:
        HTTPException 404: If ``run_id`` does not exist.
    """
    run = (await session.exec(select(PipelineRun).where(PipelineRun.id == run_id))).first()
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    audit = (await session.exec(select(AuditEvent).where(AuditEvent.run_id == run_id))).all()
    return [a.model_dump() for a in audit]
