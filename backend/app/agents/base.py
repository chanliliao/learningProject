"""
Shared Pydantic models used as structured outputs by all pipeline agents.

These dataclasses cross the boundary between the LLM layer (pydantic-ai) and the
rest of the application.  Every agent in this package returns one of these types.
"""

from pydantic import BaseModel


class ExtractedField(BaseModel):
    """A single leaf field pulled from a raw ACORD XML document.

    Attributes:
        path: Dot-separated XPath-style location, e.g. ``"TXLife.Party.FullName"``.
        value: The text content of the XML element, stripped of leading/trailing whitespace.
        inferred_type: Heuristic type label — one of ``"str"``, ``"number"``, or ``"date"``.
    """

    path: str
    value: str
    inferred_type: str  # "str" | "number" | "date"


class InterpretedField(BaseModel):
    """An ``ExtractedField`` enriched with insurance-domain semantics by the interpret agent.

    Attributes:
        path: Same dot-separated path as the source ``ExtractedField``.
        value: Same raw text value as the source ``ExtractedField``.
        inferred_type: Same type label as the source ``ExtractedField``.
        semantic_label: Short human-readable label, e.g. ``"Policy Number"``.
        meaning: Full sentence describing what the field represents in ACORD Life context.
        rules: Zero or more business-rule strings, e.g. ``["Must be non-empty", "ISO 8601 date"]``.
    """

    path: str
    value: str
    inferred_type: str
    semantic_label: str | None = None
    meaning: str | None = None
    rules: list[str] = []


class FieldMappingProposal(BaseModel):
    """A single source→target mapping proposed by the map agent.

    Attributes:
        source_path: Dot-separated path from the source ACORD XML.
        target_path: Field key in the target JSON schema.
        transform: Optional transform hint from the LLM (e.g. ``"to_date_iso"``).
            If the value is not in ``_TRANSFORMS``, ``map_node`` normalises it to ``None``
            before persisting to avoid ``TransformError`` at build time.
        llm_confidence: Self-reported confidence from the LLM, in ``[0, 1]``.  ``None`` when
            the model did not return a confidence value.
    """

    source_path: str
    target_path: str
    transform: str | None = None
    llm_confidence: float | None = None


class MappingProposals(BaseModel):
    """Wrapper returned by the map agent containing all proposed mappings.

    Attributes:
        mappings: Ordered list of ``FieldMappingProposal`` objects, one per proposed mapping.
    """

    mappings: list[FieldMappingProposal]


class ExtractError(Exception):
    """Raised by the extract agent when the XML document cannot be parsed or is empty."""
