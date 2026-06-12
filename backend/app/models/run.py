"""
SQLModel table definitions for pipeline run state.

``PipelineRun`` is the top-level record created when a user uploads a document.
``StageResult`` tracks the outcome of each pipeline stage (extract, interpret, map,
build, test) and is the source of truth for gate status in the review UI.
"""

from datetime import datetime, UTC
from sqlalchemy import JSON, Column
from sqlmodel import SQLModel, Field


class PipelineRun(SQLModel, table=True):
    """Top-level record representing one document-mapping pipeline execution.

    Attributes:
        id: Auto-assigned primary key.
        tenant_id: Tenant identifier for future multi-tenancy support.  Defaults to
            ``"default"`` until the multi-tenant migration is applied.
        status: Current run status.  Lifecycle:
            ``"running"`` → ``"awaiting_review"`` (at each gate) → ``"completed"``
            or ``"failed"``.
        source_filename: Original filename of the uploaded XML document.
        source_xml: Full XML document content stored verbatim.  Re-extracted by the
            test node for QA checks.
        target_schema_id: Foreign key to the ``TargetSchema`` used for this run.
        thread_id: LangGraph thread ID assigned at run start.  Required by
            ``resume_run`` to locate the saved checkpoint.  ``None`` before
            ``start_run`` is called.
        prompt_version: Version tag for the prompts used in this run, stored for
            reproducibility and regression analysis.
        target_schema_version: Version of the target schema at run time.
        created_at: UTC timestamp when the run record was created.
    """

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: str = "default"
    status: str = "running"
    source_filename: str
    source_xml: str
    target_schema_id: int = Field(foreign_key="targetschema.id")
    thread_id: str | None = None
    prompt_version: str = "v1"
    target_schema_version: str = "1.0"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))


class StageResult(SQLModel, table=True):
    """Per-stage outcome record for a single pipeline run.

    One row is created per gate by the corresponding graph node.  The review API
    reads these rows to determine which gate is currently awaiting review and
    transitions their status on approval/rejection.

    Attributes:
        id: Auto-assigned primary key.
        run_id: Foreign key to the owning ``PipelineRun``.
        tenant_id: Tenant identifier.
        stage: Stage name: one of ``"extract"``, ``"interpret"``, ``"map"``,
            ``"build"``, or ``"test"``.
        status: Stage status.  Lifecycle: ``"pending"`` → ``"awaiting_review"`` →
            ``"approved"`` or ``"rejected"``.
        payload: Arbitrary JSON data stored by the node (e.g. field counts, the
            compiled ``TransformSpec`` for the build stage, QA pass/fail counts).
        created_at: UTC timestamp when the stage result was created.
    """

    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="pipelinerun.id")
    tenant_id: str = "default"
    stage: str
    status: str = "pending"
    payload: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))
