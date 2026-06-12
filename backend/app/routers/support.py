"""
Support router: question-answering and edit-proposal endpoints for completed runs.

The support agent answers natural-language questions about a run's mapping decisions
using RAG retrieval from Qdrant.  It can also propose field remappings; those
proposals are queued as ``StageResult`` rows for human review before being applied.
"""

from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from app.db import get_session
from app.models.run import PipelineRun, StageResult
from app.models.audit import ReviewAction, AuditEvent
from app.agents.support import answer_question, EditIntent
from app.rag.index import _get_embed_model, _get_client
from app.routers.pipeline import get_llm_mode

router = APIRouter()


def get_qdrant_client() -> Any:
    """FastAPI dependency that returns the default Qdrant client.

    Returns:
        A ``QdrantClient`` instance connected to ``Settings.qdrant_url``.
    """
    return _get_client()


def get_embed_model() -> Any:
    """FastAPI dependency that returns the default embedding model.

    Returns:
        A LlamaIndex-compatible embedding model instance.
    """
    return _get_embed_model()


class SupportRequest(BaseModel):
    """Request body for the support question endpoint.

    Attributes:
        question: Free-text question from the user about the pipeline run.
    """

    question: str


class SupportResponse(BaseModel):
    """Response body from the support question endpoint.

    Attributes:
        answer: Plain-text answer from the support agent.
        proposed_edits: Zero or more ``EditIntent`` objects the agent recommends.
            The UI renders these as actionable "Apply" buttons.
    """

    answer: str
    proposed_edits: list[EditIntent] = []


@router.post("/runs/{run_id}/support", response_model=SupportResponse)
async def ask_support(
    run_id: int,
    body: SupportRequest,
    session: AsyncSession = Depends(get_session),
    qdrant_client: Any = Depends(get_qdrant_client),
    embed_model: Any = Depends(get_embed_model),
    mode: str | None = Depends(get_llm_mode),
):
    """Answer a question about a completed pipeline run using RAG + LLM.

    Retrieves relevant context from the run's Qdrant index and passes it to the
    support agent.  The agent may also look up live ``FieldMapping`` rows via the
    ``lookup_mapping`` tool and propose field remappings in ``proposed_edits``.

    Args:
        run_id: ID of the ``PipelineRun`` being queried.
        body: Request with the user's question.
        session: Injected async DB session for tool use inside the agent.
        qdrant_client: Injected Qdrant client for RAG retrieval.
        embed_model: Injected embedding model for RAG retrieval.
        mode: LLM mode override.

    Returns:
        ``SupportResponse`` with the answer and any proposed edits.

    Raises:
        HTTPException 404: If ``run_id`` does not exist.
    """
    run = (await session.exec(select(PipelineRun).where(PipelineRun.id == run_id))).first()
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    result = await answer_question(
        run_id=run_id,
        question=body.question,
        session=session,
        client=qdrant_client,
        embed_model=embed_model,
        mode=mode,
    )

    return SupportResponse(answer=result.answer, proposed_edits=result.proposed_edits)


@router.post("/runs/{run_id}/support/apply")
async def apply_proposed_edit(
    run_id: int,
    body: EditIntent,
    session: AsyncSession = Depends(get_session),
):
    """Queue a support-agent edit proposal for human review.

    Does NOT apply the edit immediately.  Instead, creates a ``StageResult``
    (stage="support_review", status="awaiting_review") containing the edit payload,
    and sets the run status to ``"awaiting_review"``.  The reviewer then calls
    ``POST /runs/{id}/stages/support_review/approve`` to apply it or ``/reject`` to
    discard it.

    Args:
        run_id: ID of the ``PipelineRun`` the edit applies to.
        body: The ``EditIntent`` from the support agent response.
        session: Injected async DB session.

    Returns:
        JSON with ``run_id`` and ``status="awaiting_review"``.

    Raises:
        HTTPException 404: If ``run_id`` does not exist.
    """
    run = (await session.exec(select(PipelineRun).where(PipelineRun.id == run_id))).first()
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    # Store the edit payload in a StageResult so the review endpoint can apply it
    session.add(StageResult(
        run_id=run_id,
        stage="support_review",
        status="awaiting_review",
        payload={
            "field_id": body.field_id,
            "new_target_path": body.new_target_path,
            "new_transform": body.new_transform,
            "reason": body.reason,
        },
    ))
    session.add(ReviewAction(
        run_id=run_id,
        field_mapping_id=body.field_id,
        reviewer="support_agent",
        decision="propose",
        note=f"-> {body.new_target_path}: {body.reason}",
    ))
    session.add(AuditEvent(
        run_id=run_id,
        actor="support_agent",
        action="edit_proposed",
        after={"field_id": body.field_id, "new_target_path": body.new_target_path, "reason": body.reason},
    ))

    run.status = "awaiting_review"
    session.add(run)
    await session.commit()
    return {"run_id": run_id, "status": "awaiting_review"}
