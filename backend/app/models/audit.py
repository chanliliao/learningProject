"""
SQLModel table definitions for audit, review, and LLM call records.

These tables provide a full audit trail for every pipeline run:
- ``AuditEvent`` — system and reviewer actions on a run.
- ``ReviewAction`` — reviewer decisions (approve/reject/edit) on stages or mappings.
- ``LLMCall`` — one row per LLM invocation with token counts and cost estimates.
"""

from datetime import datetime, UTC
from sqlalchemy import JSON, Column
from sqlmodel import SQLModel, Field


class AuditEvent(SQLModel, table=True):
    """A single auditable event in a pipeline run's lifecycle.

    Emitted by both system nodes (e.g. ``action="extract_completed"``) and reviewer
    actions (e.g. ``action="field_edited"``).  The ``before``/``after`` JSON fields
    capture the relevant state change for diffing.

    Attributes:
        id: Auto-assigned primary key.
        run_id: Foreign key to the owning ``PipelineRun``.
        tenant_id: Tenant identifier.
        actor: Who triggered the event — ``"system"`` for pipeline nodes,
            ``"reviewer"`` for human actions, ``"support_agent"`` for AI-proposed edits.
        action: Short action label, e.g. ``"extract_completed"``, ``"field_edited"``,
            ``"map_approved"``.
        before: Optional JSON snapshot of the relevant state before the action.
        after: Optional JSON snapshot of the relevant state after the action.
        created_at: UTC timestamp.
    """

    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="pipelinerun.id")
    tenant_id: str = "default"
    actor: str
    action: str
    before: dict | None = Field(default=None, sa_column=Column(JSON))
    after: dict | None = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))


class ReviewAction(SQLModel, table=True):
    """A reviewer's explicit decision on a stage or individual field mapping.

    One row per approve/reject/edit action taken in the review UI or via the API.
    Provides a separate log from ``AuditEvent`` that is scoped to reviewer decisions
    only, making it easy to filter the review history.

    Attributes:
        id: Auto-assigned primary key.
        run_id: Foreign key to the owning ``PipelineRun``.
        tenant_id: Tenant identifier.
        stage: Pipeline stage the decision applies to (e.g. ``"map"``).  ``None`` for
            field-level actions that are not stage-scoped.
        field_mapping_id: Foreign key to the ``FieldMapping`` row, if this action
            targets a specific mapping rather than an entire stage.
        reviewer: Identifier of the reviewer — ``"user"`` for human reviewers,
            ``"support_agent"`` for AI-proposed edits.
        decision: ``"approve"``, ``"reject"``, ``"edit"``, or ``"propose"``.
        note: Optional free-text note from the reviewer.
        created_at: UTC timestamp.
    """

    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="pipelinerun.id")
    tenant_id: str = "default"
    stage: str | None = None
    field_mapping_id: int | None = Field(default=None, foreign_key="fieldmapping.id")
    reviewer: str
    decision: str
    note: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))


class LLMCall(SQLModel, table=True):
    """Record of a single LLM API call made during a pipeline run.

    One row per call to ``run_structured``.  Stores the full prompt and response for
    debugging, plus token counts and estimated cost for analytics.

    Attributes:
        id: Auto-assigned primary key.
        run_id: Foreign key to the owning ``PipelineRun``.  ``None`` for calls not
            associated with a specific run (e.g. health-check pings).
        tenant_id: Tenant identifier.
        stage: Pipeline stage label (e.g. ``"interpret"``, ``"map"``, ``"support"``).
        model: Model identifier string as returned by pydantic-ai.
        prompt: Full user-turn prompt string sent to the model.
        response: Full response string from the model.
        prompt_tokens: Number of input tokens consumed.
        completion_tokens: Number of output tokens generated.
        latency_ms: Wall-clock call duration in milliseconds.
        estimated_cost: Approximate USD cost based on ``_COST_PER_1K`` lookup.
        langfuse_trace_id: Langfuse trace ID for cross-referencing in the Langfuse
            dashboard.  ``None`` if Langfuse is not configured.
        created_at: UTC timestamp.
    """

    id: int | None = Field(default=None, primary_key=True)
    run_id: int | None = Field(default=None, foreign_key="pipelinerun.id")
    tenant_id: str = "default"
    stage: str
    model: str
    prompt: str
    response: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0
    estimated_cost: float = 0.0
    langfuse_trace_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))
