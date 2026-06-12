"""
SQLModel table definition for field-level mapping records.

One ``FieldMapping`` row is created per proposed source→target pair during the map
stage.  The reviewer can edit individual mappings before approving.  ``run_build``
reads only rows with ``status in ("approved", "edited")`` to build the transform spec.
"""

from sqlalchemy import JSON, Column
from sqlmodel import SQLModel, Field


class FieldMapping(SQLModel, table=True):
    """A single proposed or approved source→target field mapping for a pipeline run.

    Attributes:
        id: Auto-assigned primary key.  Used by the review UI to target specific rows
            for inline edits.
        run_id: Foreign key to the owning ``PipelineRun``.
        tenant_id: Tenant identifier.
        source_path: Dot-separated path of the field in the source ACORD XML, e.g.
            ``"TXLife.Policy.PolNumber"``.
        target_path: Key in the target JSON schema output, e.g. ``"policy_id"``.
        transform: Optional transform name from ``_TRANSFORMS`` (e.g. ``"to_number"``).
            ``None`` means verbatim copy.  ``map_node`` normalises any LLM-generated
            string not in ``_TRANSFORMS`` to ``None`` before saving.
        confidence: Composite confidence score in ``[0, 1]`` from ``score_mapping``.
            ``None`` before scoring has been applied.
        flags: List of quality warning strings from ``score_mapping``, e.g.
            ``["type_mismatch", "required_missing"]``.  Displayed as red badges in the
            review UI.
        status: Lifecycle status.
            ``"proposed"`` — created by the map node, not yet reviewed.
            ``"approved"`` — reviewer approved (or map gate was approved wholesale).
            ``"edited"``   — reviewer changed ``target_path`` or ``transform``.
            ``"rejected"`` — reviewer explicitly rejected (reserved for future use).
    """

    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="pipelinerun.id")
    tenant_id: str = "default"
    source_path: str
    target_path: str
    transform: str | None = None
    confidence: float | None = None
    flags: list = Field(default_factory=list, sa_column=Column(JSON))
    status: str = "proposed"
