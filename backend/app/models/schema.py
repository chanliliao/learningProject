"""
SQLModel table definition for target schema records.

``TargetSchema`` stores the JSON Schema definitions that pipeline runs map source
ACORD XML fields into.  Schemas are seeded via ``app.seed`` and selected by the user
on the upload page.
"""

from datetime import datetime, UTC
from sqlalchemy import JSON, Column
from sqlmodel import SQLModel, Field


class TargetSchema(SQLModel, table=True):
    """A versioned JSON Schema definition used as the mapping target.

    Multiple schemas can coexist (e.g. different carrier formats or schema versions).
    The user picks one when starting a run.  The definition is stored verbatim and
    passed to the map agent and QA checks at run time.

    Attributes:
        id: Auto-assigned primary key.
        tenant_id: Tenant identifier.
        name: Human-readable schema name, e.g. ``"distributor_a"``.
        version: Schema version string, e.g. ``"1.0"``.
        definition: Full JSON Schema dict.  Must be a valid JSON Schema object.
        created_at: UTC timestamp when the schema was seeded or imported.
    """

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: str = "default"
    name: str
    version: str
    definition: dict = Field(sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))
