"""
Interpret agent: enriches raw extracted fields with ACORD insurance-domain semantics.

Calls the LLM once per run to annotate every extracted field with a human-readable
meaning and a list of applicable business rules.  The output feeds into the map agent
so the mapper has richer context when choosing target schema fields.
"""

from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession
from app.agents.base import ExtractedField, InterpretedField
from app.llm.client import build_agent, run_structured


class InterpretedFields(BaseModel):
    """LLM output wrapper containing the full set of interpreted fields.

    Attributes:
        fields: One ``InterpretedField`` per input ``ExtractedField``.  The LLM is
            instructed to preserve the original ``path``, ``value``, and ``inferred_type``
            and add ``meaning`` and ``rules``.
    """

    fields: list[InterpretedField]


_SYSTEM = (
    "You are an insurance domain expert. Given a list of fields extracted from an ACORD XML document, "
    "describe each field's semantic meaning and any applicable business rules or constraints. "
    "Use your knowledge of ACORD Life standards. "
    "Return an InterpretedFields object where each field has its original path, value, and inferred_type "
    "plus a human-readable meaning and a list of relevant business rules."
)


async def interpret_fields(
    fields: list[ExtractedField],
    *,
    run_id: int | None,
    session: AsyncSession | None,
    mode: str | None = None,
) -> list[InterpretedField]:
    """Annotate extracted fields with insurance-domain meaning and business rules.

    Sends a single LLM prompt containing all fields in the run and parses the
    structured response.  The LLM call is logged to ``LLMCall`` when ``session``
    is provided.

    Args:
        fields: Extracted leaf fields from the source ACORD XML document.
        run_id: ID of the owning ``PipelineRun``, used only for LLM call logging.
            Pass ``None`` when logging is not needed (e.g. unit tests).
        session: Active async SQLModel session for persisting the ``LLMCall`` audit
            record.  Pass ``None`` to skip logging.
        mode: LLM mode override — ``"test"`` swaps in ``TestModel`` (no real API call),
            ``None`` reads from ``Settings.llm_mode``.

    Returns:
        List of ``InterpretedField`` objects in the same order as the input ``fields``.
    """
    source_summary = "\n".join(
        f"  {f.path} ({f.inferred_type}): {f.value!r}" for f in fields
    )
    user_msg = (
        f"Extracted ACORD fields:\n{source_summary}\n\n"
        "Describe the meaning and business rules for each field."
    )
    agent = build_agent(InterpretedFields, system=_SYSTEM, mode=mode)
    result = await run_structured(agent, user_msg, stage="interpret", run_id=run_id, session=session)
    return result.fields
