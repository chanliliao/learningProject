"""
Review router: field-edit, stage-approve, and stage-reject endpoints.

These endpoints are called from the review UI (``RunPage``) and the support chat
after a reviewer examines the pipeline output at each gate.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from app.db import get_session
from app.models.run import PipelineRun, StageResult
from app.models.mapping import FieldMapping
from app.models.schema import TargetSchema
from app.models.audit import ReviewAction, AuditEvent
from app.graph.build import resume_run
from app.pipeline.confidence import score_mapping
from app.agents.extract import extract
from app.routers.pipeline import get_checkpointer

router = APIRouter()


class FieldEditRequest(BaseModel):
    """Request body for the field-edit endpoint.

    Attributes:
        target_path: New target schema field name.  ``None`` leaves the current value.
        transform: New transform name.  ``None`` leaves the current value.
    """

    target_path: str | None = None
    transform: str | None = None


@router.patch("/runs/{run_id}/fields/{field_id}")
async def edit_field(
    run_id: int,
    field_id: int,
    body: FieldEditRequest,
    session: AsyncSession = Depends(get_session),
):
    """Edit a single field mapping while a run is awaiting map-stage review.

    Updates the ``target_path`` and/or ``transform`` on the specified ``FieldMapping``
    row, sets its status to ``"edited"``, and recalculates the confidence score and
    flags using the new target path.

    Args:
        run_id: ID of the owning ``PipelineRun``.
        field_id: Primary key of the ``FieldMapping`` to edit.
        body: New field values.  Only non-``None`` fields are applied.
        session: Injected async DB session.

    Returns:
        Updated ``FieldMapping`` as a dict.

    Raises:
        HTTPException 404: If the run or field mapping does not exist.
    """
    run = (await session.exec(select(PipelineRun).where(PipelineRun.id == run_id))).first()
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    fm = (await session.exec(select(FieldMapping).where(FieldMapping.id == field_id, FieldMapping.run_id == run_id))).first()
    if fm is None:
        raise HTTPException(status_code=404, detail="Field mapping not found")

    before = {"target_path": fm.target_path, "transform": fm.transform}
    if body.target_path is not None:
        fm.target_path = body.target_path
    if body.transform is not None:
        fm.transform = body.transform
    fm.status = "edited"

    # Re-score the mapping against the (potentially new) target path
    schema = (await session.exec(select(TargetSchema).where(TargetSchema.id == run.target_schema_id))).first()
    if schema:
        fields = extract(run.source_xml)
        extracted_by_path = {f.path: f for f in fields}
        src_field = extracted_by_path.get(fm.source_path)
        schema_props = schema.definition.get("properties", {})
        schema_required = set(schema.definition.get("required", []))
        tgt_prop = schema_props.get(fm.target_path, {})
        scored = score_mapping(
            source_path=fm.source_path,
            source_type=src_field.inferred_type if src_field else "string",
            target_path=fm.target_path,
            target_type=tgt_prop.get("type", "string"),
            target_required=fm.target_path in schema_required,
            target_enum=tgt_prop.get("enum"),
            value=src_field.value if src_field else "",
            llm_confidence=0.5,  # Use neutral confidence for reviewer-driven edits
        )
        fm.confidence = scored.score
        fm.flags = scored.flags

    session.add(fm)
    session.add(ReviewAction(
        run_id=run_id,
        field_mapping_id=field_id,
        reviewer="user",
        decision="edit",
    ))
    session.add(AuditEvent(
        run_id=run_id,
        actor="reviewer",
        action="field_edited",
        before=before,
        after={"target_path": fm.target_path, "transform": fm.transform},
    ))
    await session.commit()
    await session.refresh(fm)
    return fm.model_dump()


@router.post("/runs/{run_id}/stages/{stage}/approve")
async def approve_stage(
    run_id: int,
    stage: str,
    session: AsyncSession = Depends(get_session),
    checkpointer=Depends(get_checkpointer),
):
    """Approve a pipeline gate, resuming the graph to the next stage.

    For standard pipeline stages (``"extract"``, ``"interpret"``, ``"map"``,
    ``"test"``), delegates to ``resume_run`` which marks the stage approved and
    continues LangGraph execution.

    The ``"support_review"`` stage is handled separately: it applies any queued
    support-agent edit proposals and marks the run ``"completed"`` without resuming
    the graph (the graph already reached ``END`` before the support question was asked).

    Args:
        run_id: ID of the ``PipelineRun`` to approve.
        stage: Stage name to approve.
        session: Injected async DB session.
        checkpointer: Injected LangGraph checkpointer.

    Returns:
        JSON with ``run_id`` and the run's updated ``status``.

    Raises:
        HTTPException 404: If the run does not exist.
        HTTPException 409: If the run is not currently ``"awaiting_review"``, or if
            the specified stage has already been processed.
    """
    run = (await session.exec(select(PipelineRun).where(PipelineRun.id == run_id))).first()
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status != "awaiting_review":
        raise HTTPException(status_code=409, detail=f"Run is not awaiting review (current status: {run.status})")

    # Support-review stage: apply pending proposed edits directly, no LangGraph resume needed
    if stage == "support_review":
        pending = (await session.exec(
            select(StageResult).where(
                StageResult.run_id == run_id,
                StageResult.stage == "support_review",
                StageResult.status == "awaiting_review",
            )
        )).all()
        if not pending:
            raise HTTPException(status_code=409, detail="No pending support review edits found")

        for sr in pending:
            payload = sr.payload or {}
            field_id = payload.get("field_id")
            new_target_path = payload.get("new_target_path")
            new_transform = payload.get("new_transform")
            if field_id and new_target_path:
                fm = (await session.exec(
                    select(FieldMapping).where(FieldMapping.id == field_id)
                )).first()
                if fm:
                    before = {"target_path": fm.target_path, "transform": fm.transform}
                    fm.target_path = new_target_path
                    if new_transform is not None:
                        fm.transform = new_transform
                    fm.status = "edited"
                    session.add(fm)
                    session.add(AuditEvent(
                        run_id=run_id, actor="reviewer", action="support_edit_applied",
                        before=before,
                        after={"target_path": fm.target_path, "transform": fm.transform},
                    ))
            sr.status = "approved"
            session.add(sr)

        session.add(ReviewAction(run_id=run_id, stage=stage, reviewer="user", decision="approve"))
        session.add(AuditEvent(run_id=run_id, actor="reviewer", action="support_review_approved", after={"decision": "approve"}))
        run.status = "completed"
        session.add(run)
        await session.commit()
        await session.refresh(run)
        return {"run_id": run_id, "status": run.status}

    stage_result = (await session.exec(
        select(StageResult).where(StageResult.run_id == run_id, StageResult.stage == stage)
    )).first()
    if stage_result and stage_result.status not in ("awaiting_review", "pending"):
        raise HTTPException(status_code=409, detail=f"Stage '{stage}' already processed (status: {stage_result.status})")

    session.add(ReviewAction(run_id=run_id, stage=stage, reviewer="user", decision="approve"))
    await session.flush()

    await resume_run(run_id, decision="approve", session=session, checkpointer=checkpointer, stage=stage)
    await session.commit()
    await session.refresh(run)
    return {"run_id": run_id, "status": run.status}


@router.post("/runs/{run_id}/stages/{stage}/reject")
async def reject_stage(
    run_id: int,
    stage: str,
    session: AsyncSession = Depends(get_session),
    checkpointer=Depends(get_checkpointer),
):
    """Reject a pipeline gate, halting the run.

    Marks the stage ``"rejected"``, the run ``"failed"``, and does NOT resume the
    LangGraph graph.  For ``"support_review"``, rejects any pending edit proposals
    and returns the run to ``"completed"`` status (the graph already finished).

    Args:
        run_id: ID of the ``PipelineRun`` to reject.
        stage: Stage name to reject.
        session: Injected async DB session.
        checkpointer: Injected LangGraph checkpointer.

    Returns:
        JSON with ``run_id`` and the run's updated ``status``.

    Raises:
        HTTPException 404: If the run does not exist.
        HTTPException 409: If the run is not currently ``"awaiting_review"``, or if
            the stage has already been processed.
    """
    run = (await session.exec(select(PipelineRun).where(PipelineRun.id == run_id))).first()
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status != "awaiting_review":
        raise HTTPException(status_code=409, detail=f"Run is not awaiting review (current status: {run.status})")

    # Support-review stage: reject pending proposed edits, run returns to completed
    if stage == "support_review":
        pending = (await session.exec(
            select(StageResult).where(
                StageResult.run_id == run_id,
                StageResult.stage == "support_review",
                StageResult.status == "awaiting_review",
            )
        )).all()
        for sr in pending:
            sr.status = "rejected"
            session.add(sr)
        session.add(ReviewAction(run_id=run_id, stage=stage, reviewer="user", decision="reject"))
        session.add(AuditEvent(run_id=run_id, actor="reviewer", action="support_review_rejected", after={"decision": "reject"}))
        run.status = "completed"
        session.add(run)
        await session.commit()
        await session.refresh(run)
        return {"run_id": run_id, "status": run.status}

    stage_result = (await session.exec(
        select(StageResult).where(StageResult.run_id == run_id, StageResult.stage == stage)
    )).first()
    if stage_result and stage_result.status not in ("awaiting_review", "pending"):
        raise HTTPException(status_code=409, detail=f"Stage '{stage}' already processed (status: {stage_result.status})")

    session.add(ReviewAction(run_id=run_id, stage=stage, reviewer="user", decision="reject"))
    await session.flush()

    await resume_run(run_id, decision="reject", session=session, checkpointer=checkpointer, stage=stage)
    await session.commit()
    await session.refresh(run)
    return {"run_id": run_id, "status": run.status}
