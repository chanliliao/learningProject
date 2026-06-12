"""
Map agent: proposes source→target field mappings from extracted/interpreted fields.

The LLM receives the full list of extracted fields (plus optional interpretations)
and the target JSON schema, then returns a structured list of ``FieldMappingProposal``
objects.  Downstream, ``map_node`` in ``build.py`` validates the proposed transforms
against the known ``_TRANSFORMS`` registry before persisting.
"""

import json
from sqlmodel.ext.asyncio.session import AsyncSession
from app.agents.base import ExtractedField, InterpretedField, FieldMappingProposal, MappingProposals
from app.llm.client import build_agent, run_structured

_SYSTEM = (
    "You are a schema mapping expert. Given a list of extracted source fields and a target JSON "
    "schema, propose field mappings. For each source field, identify the best matching target field. "
    "Include a transform hint if data conversion is needed (e.g. type cast, rename). "
    "Only map fields that have a reasonable match. Return a MappingProposals object."
)


async def propose_mappings(
    fields: list[ExtractedField],
    target_schema: dict,
    *,
    run_id: int | None,
    session: AsyncSession | None,
    mode: str | None = None,
    interpreted: list[InterpretedField] | None = None,
) -> list[FieldMappingProposal]:
    """Ask the LLM to propose source→target field mappings for a pipeline run.

    Constructs a prompt containing the source fields (and optionally their semantic
    interpretations) alongside the JSON schema definition of the target system, then
    parses the structured LLM response.

    Note: The LLM may suggest transform strings that are not registered in
    ``_TRANSFORMS``.  ``map_node`` in ``build.py`` is responsible for discarding
    unrecognised values so they do not reach ``build_transform`` and cause a
    ``TransformError`` at build time.

    Args:
        fields: All leaf fields extracted from the source ACORD XML.
        target_schema: Full JSON Schema dict for the destination data format.
        run_id: Owning run ID, used only for ``LLMCall`` audit logging.  Pass ``None``
            to skip logging.
        session: Active async SQLModel session for persisting the ``LLMCall`` record.
            Pass ``None`` to skip logging.
        mode: LLM mode override.  ``"test"`` uses ``TestModel``; ``None`` reads
            ``Settings.llm_mode``.
        interpreted: Optional list of ``InterpretedField`` objects from the interpret
            stage.  When provided, their meaning and rules are appended to the prompt so
            the mapper has richer context for ambiguous fields.

    Returns:
        List of ``FieldMappingProposal`` objects — one per proposed mapping.  Not every
        source field will have a proposal if the LLM finds no reasonable match.
    """
    source_summary = "\n".join(
        f"  {f.path} ({f.inferred_type}): {f.value!r}" for f in fields
    )
    context_section = ""
    if interpreted:
        interp_lines = "\n".join(
            f"  {f.path}: {f.meaning or f.semantic_label or ''} {('Rules: ' + '; '.join(f.rules)) if f.rules else ''}".strip()
            for f in interpreted
        )
        context_section = f"\nField interpretations:\n{interp_lines}\n"
    user_msg = (
        f"Source fields extracted from ACORD XML:\n{source_summary}\n"
        f"{context_section}"
        f"\nTarget JSON schema:\n{json.dumps(target_schema, indent=2)}\n\n"
        "Propose field mappings."
    )
    agent = build_agent(MappingProposals, system=_SYSTEM, mode=mode)
    result = await run_structured(agent, user_msg, stage="map", run_id=run_id, session=session)
    return result.mappings
