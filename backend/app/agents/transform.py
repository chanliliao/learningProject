"""
Transform layer: validates, compiles, and applies field-level data transforms.

``_TRANSFORMS`` is the single source of truth for all supported transform names.
Any other string — including values suggested by the LLM — is invalid and will
raise ``TransformError``.  ``map_node`` in ``build.py`` normalises unknown values to
``None`` at ingestion time so they never reach this module with bad data.
"""

from pydantic import BaseModel
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from app.models.mapping import FieldMapping
from app.models.run import StageResult
from app.models.audit import AuditEvent


class TransformError(Exception):
    """Raised when a transform name is unrecognised or a transform application fails."""


class TransformMapping(BaseModel):
    """A single field-level mapping record used inside a ``TransformSpec``.

    Attributes:
        source_path: Dot-separated path in the source document, e.g. ``"TXLife.Policy.Amount"``.
        target_path: Key in the output dict.  Dotted paths (e.g. ``"coverage.amount"``)
            are written as nested dicts by ``apply_transform``.
        transform: Name of the transform function to apply.  Must be a key in
            ``_TRANSFORMS``, or ``None`` for a verbatim copy.
    """

    source_path: str
    target_path: str
    transform: str | None = None


class TransformSpec(BaseModel):
    """Compiled transform specification for one pipeline run.

    Produced by ``build_transform`` from approved ``FieldMapping`` rows and consumed
    by ``apply_transform`` and ``run_qa_checks``.

    Attributes:
        mappings: All source→target mappings for the run, in arbitrary order.
    """

    mappings: list[TransformMapping]


# Registry of all supported transform functions.
# Keys are the string names stored in ``FieldMapping.transform``.
# Values are pure functions that accept a single string value and return
# the transformed value (any type).  Errors during application raise ``TransformError``.
_TRANSFORMS: dict[str, object] = {
    "to_number": lambda v: float(v) if "." in str(v) else int(v),
    "to_date_iso": lambda v: str(v).strip(),
    "uppercase": lambda v: str(v).upper(),
    "lowercase": lambda v: str(v).lower(),
    "trim": lambda v: str(v).strip(),
}


def build_transform(mappings: list[dict]) -> TransformSpec:
    """Validate a list of mapping dicts and return a compiled ``TransformSpec``.

    Validates every transform name against ``_TRANSFORMS`` before building the spec
    so callers get a clear error at compile time rather than at apply time.

    Args:
        mappings: Raw mapping dicts, each with keys ``"source_path"``, ``"target_path"``,
            and optionally ``"transform"`` (``None`` or a key from ``_TRANSFORMS``).

    Returns:
        A ``TransformSpec`` containing validated ``TransformMapping`` objects.

    Raises:
        TransformError: If any mapping's ``transform`` value is not ``None`` and is not
            a key in ``_TRANSFORMS``.
    """
    items = []
    for m in mappings:
        t = m.get("transform")
        if t is not None and t not in _TRANSFORMS:
            raise TransformError(f"Unknown transform: {t!r}")
        items.append(TransformMapping(
            source_path=m["source_path"],
            target_path=m["target_path"],
            transform=t,
        ))
    return TransformSpec(mappings=items)


def apply_transform(spec: TransformSpec, source: dict) -> dict:
    """Apply a compiled ``TransformSpec`` to a single source record.

    For each mapping in ``spec``:
    - If the source path is absent, the field is silently skipped (no output key).
    - If ``transform`` is ``None``, the raw value is copied verbatim.
    - If ``transform`` is set, the corresponding function from ``_TRANSFORMS`` is called.
    - Dotted target paths are expanded into nested dicts (e.g. ``"a.b"`` → ``{"a": {"b": …}}``).

    Args:
        spec: Compiled transform specification produced by ``build_transform``.
        source: Flat dict of source field values keyed by dot-separated path.

    Returns:
        Output dict with transformed values, potentially nested via dotted target paths.

    Raises:
        TransformError: If a transform function is not found in ``_TRANSFORMS`` (should
            not happen if ``build_transform`` was used to create ``spec``) or if the
            transform function raises ``ValueError`` or ``TypeError`` on the input value.
    """
    out: dict = {}
    for m in spec.mappings:
        if m.source_path not in source:
            continue
        raw = source[m.source_path]
        if m.transform is None:
            value = raw
        else:
            fn = _TRANSFORMS.get(m.transform)
            if fn is None:
                raise TransformError(f"Unknown transform: {m.transform!r}")
            try:
                value = fn(raw)
            except (ValueError, TypeError) as e:
                raise TransformError(f"Transform {m.transform!r} failed on {raw!r}: {e}") from e
        # Expand dotted target paths into nested dicts so "a.b.c" → {"a": {"b": {"c": value}}}
        parts = m.target_path.split(".")
        node = out
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value
    return out


async def run_build(run_id: int, session: AsyncSession) -> TransformSpec:
    """Compile and persist the transform spec for a completed map-review stage.

    Reads all ``FieldMapping`` rows for the run that have been approved (status
    ``"approved"`` or ``"edited"``), validates their transform names, stores the
    compiled spec in a ``StageResult``, and logs an ``AuditEvent``.

    Only approved/edited mappings are included — ``"proposed"`` mappings that were
    never reviewed are intentionally excluded to prevent unreviewed LLM output from
    reaching production.

    Args:
        run_id: ID of the ``PipelineRun`` being built.
        session: Active async SQLModel session.  Caller is responsible for committing.

    Returns:
        The compiled ``TransformSpec`` that was persisted to the ``StageResult``.

    Raises:
        TransformError: If any approved mapping contains an unrecognised transform name.
            This should not occur in normal flow because ``map_node`` already validates
            transforms before saving, but is possible if the DB was manually edited.
    """
    approved = (await session.exec(
        select(FieldMapping).where(
            FieldMapping.run_id == run_id,
            FieldMapping.status.in_(["approved", "edited"]),
        )
    )).all()

    mappings_data = [
        {"source_path": fm.source_path, "target_path": fm.target_path, "transform": fm.transform}
        for fm in approved
    ]
    spec = build_transform(mappings_data)

    session.add(StageResult(
        run_id=run_id,
        stage="build",
        status="approved",
        payload={"mapping_count": len(mappings_data), "spec": spec.model_dump()},
    ))
    session.add(AuditEvent(
        run_id=run_id,
        actor="system",
        action="build_completed",
        after={"mapping_count": len(mappings_data)},
    ))
    await session.flush()
    return spec
