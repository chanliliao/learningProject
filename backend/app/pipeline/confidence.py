"""
Confidence scoring for proposed field mappings.

Combines a heuristic signal (type compatibility, name similarity, required-field
presence, enum membership) with the LLM's own self-reported confidence to produce a
single ``[0, 1]`` score.  The score is stored on ``FieldMapping.confidence`` and drives
the red-highlight threshold in the review UI.
"""

import re
import difflib
from pydantic import BaseModel
from app.config import get_settings

# Weight applied to the heuristic composite vs the LLM confidence value.
# They sum to 1.0, so the final score is always in [0, 1].
_HEURISTIC_WEIGHT = 0.5
_LLM_WEIGHT = 0.5

# Type-class sets used by ``_type_compatible`` to bucket source/target type strings.
_STR_TYPES = {"str", "string"}
_NUM_TYPES = {"number", "integer", "float", "int"}
_DATE_TYPES = {"date", "datetime"}


class ScoreResult(BaseModel):
    """Output of ``score_mapping``.

    Attributes:
        score: Composite confidence in ``[0, 1]``.  Higher is more confident.
        flags: List of quality warning strings, e.g. ``["type_mismatch", "enum_violation"]``.
            An empty list means no issues were detected.
    """

    score: float
    flags: list[str]


def _type_compatible(source_type: str, target_type: str, value: str) -> tuple[float, list[str]]:
    """Score how compatible a source value's type is with the target schema type.

    Args:
        source_type: Heuristic type from the extract stage (``"str"``, ``"number"``,
            ``"date"``).
        target_type: JSON Schema type from the target schema definition (e.g. ``"string"``,
            ``"integer"``, ``"date"``).
        value: The actual raw string value from the source document.  Used for
            numeric and date parsing to avoid false type-mismatch penalties.

    Returns:
        Tuple of ``(score, flags)`` where ``score`` is in ``[0, 1]`` and ``flags``
        may contain ``"type_mismatch"``.
    """
    flags: list[str] = []
    st = source_type.lower()
    tt = target_type.lower()

    if tt in _STR_TYPES:
        # Any value is a valid string — no penalty
        return 1.0, flags
    if tt in _NUM_TYPES:
        try:
            float(value)
            return 1.0, flags
        except (ValueError, TypeError):
            flags.append("type_mismatch")
            return 0.0, flags
    if tt in _DATE_TYPES:
        if re.match(r"\d{4}-\d{2}-\d{2}", value.strip()):
            return 1.0, flags
        try:
            float(value)
            # A number where a date is expected is a harder mismatch
            flags.append("type_mismatch")
            return 0.0, flags
        except (ValueError, TypeError):
            pass
        # Non-numeric, non-ISO string mapped to a date field — partial credit because
        # a transform might resolve it at run time
        return 0.5, flags
    # Unknown target type — give partial credit rather than penalising an edge case
    return 0.8, flags


def _name_similarity(source_path: str, target_path: str) -> float:
    """Score lexical similarity between the last segment of two dot-separated paths.

    First tries token-overlap (splitting on camelCase/snake_case/dots), then falls back
    to character-level sequence ratio.  A bonus of 0.2 is added when any tokens overlap
    so that partial matches score clearly above purely dissimilar names.

    Args:
        source_path: Dot-separated source field path.
        target_path: Dot-separated target field name.

    Returns:
        Similarity score in ``[0, 1]``.
    """
    def _tokens(s: str) -> set[str]:
        # Split on camelCase boundaries, underscores, dots, hyphens, and spaces
        s = re.sub(r"([A-Z])", r"_\1", s).lower()
        return set(re.split(r"[_.\-\s]+", s)) - {""}

    src = source_path.split(".")[-1]
    tgt = target_path.split(".")[-1]
    src_tokens = _tokens(src)
    tgt_tokens = _tokens(tgt)
    if src_tokens & tgt_tokens:
        overlap = len(src_tokens & tgt_tokens) / max(len(src_tokens | tgt_tokens), 1)
        return min(1.0, overlap + 0.2)
    # No common tokens — fall back to character-level similarity
    ratio = difflib.SequenceMatcher(None, src.lower(), tgt.lower()).ratio()
    return ratio


def score_mapping(
    *,
    source_path: str,
    source_type: str,
    target_path: str,
    target_type: str,
    target_required: bool,
    target_enum: list[str] | None,
    value: str,
    llm_confidence: float,
) -> ScoreResult:
    """Compute a composite confidence score for a proposed source→target field mapping.

    Combines four heuristic sub-scores (type compatibility weighted 2×, name similarity,
    required-field presence, enum membership) with the LLM's self-reported confidence.
    Each half contributes equally to the final score (``_HEURISTIC_WEIGHT = 0.5``).

    Args:
        source_path: Dot-separated path of the field in the source XML.
        source_type: Heuristic type label from the extract stage.
        target_path: Key name in the target JSON schema.
        target_type: JSON Schema ``type`` value for the target field.
        target_required: Whether the target field is listed in the schema's ``required``
            array.
        target_enum: List of allowed enum values for the target field, or ``None`` if the
            field has no enum constraint.
        value: Raw string value from the source document.
        llm_confidence: Self-reported confidence from the map agent, in ``[0, 1]``.

    Returns:
        ``ScoreResult`` with a composite score in ``[0, 1]`` and a list of warning flags.
    """
    flags: list[str] = []

    type_score, type_flags = _type_compatible(source_type, target_type, value)
    flags.extend(type_flags)

    name_score = _name_similarity(source_path, target_path)

    required_score = 1.0
    if target_required and not value.strip():
        flags.append("required_missing")
        required_score = 0.0

    enum_score = 1.0
    if target_enum is not None and value not in target_enum:
        flags.append("enum_violation")
        enum_score = 0.0

    # Type score is weighted 2× because a type mismatch is a harder blocker than a
    # name mismatch — a name can be remapped but a type error blocks execution.
    heuristic_mean = (type_score * 2 + name_score + required_score + enum_score) / 5

    score = _HEURISTIC_WEIGHT * heuristic_mean + _LLM_WEIGHT * llm_confidence
    score = max(0.0, min(1.0, score))

    return ScoreResult(score=score, flags=flags)
