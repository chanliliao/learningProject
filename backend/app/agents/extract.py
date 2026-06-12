"""
XML extraction agent: walks a raw ACORD XML document and returns typed leaf fields.

No LLM is involved here — extraction is deterministic regex-based heuristics so it is
always run synchronously (no ``async``).
"""

import re
from lxml import etree
from app.agents.base import ExtractedField, ExtractError

# ISO 8601 date pattern: YYYY-MM-DD
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Integer or decimal number with no leading/trailing whitespace
_NUM_RE = re.compile(r"^\d+(\.\d+)?$")


def _infer_type(value: str) -> str:
    """Heuristically determine the data type of a field value.

    Checks in priority order: date → number → string.  The input is trimmed before
    matching so surrounding whitespace does not affect the result.

    Args:
        value: Raw string text content from an XML element.

    Returns:
        One of ``"date"``, ``"number"``, or ``"str"``.
    """
    v = value.strip()
    if _DATE_RE.match(v):
        return "date"
    if _NUM_RE.match(v):
        return "number"
    return "str"


def _walk(element: etree._Element, parent_path: str, fields: list[ExtractedField]) -> None:
    """Recursively visit every element in the XML tree, collecting leaf-node values.

    A *leaf* is an element whose text content is non-empty AND that has no child
    elements.  Intermediate container elements (e.g. ``<Party>``) are not collected.

    Args:
        element: The current XML element being visited.
        parent_path: Dot-separated path of the element's ancestors (empty string at root).
        fields: Accumulator list; leaf fields are appended here in document order.
    """
    tag = etree.QName(element.tag).localname          # strip namespace URI if present
    path = f"{parent_path}.{tag}" if parent_path else tag

    text = (element.text or "").strip()
    # Only collect if there is text AND this element has no children (true leaf)
    if text and not list(element):
        fields.append(ExtractedField(path=path, value=text, inferred_type=_infer_type(text)))

    for child in element:
        _walk(child, path, fields)


def extract(xml_str: str) -> list[ExtractedField]:
    """Parse an ACORD XML string and return all typed leaf fields.

    The function is synchronous and deterministic — no LLM calls are made.  It raises
    ``ExtractError`` instead of returning an empty list so callers can treat a blank or
    malformed document as a hard failure.

    Args:
        xml_str: Full XML document as a string or bytes.  Must be valid, non-empty XML.

    Returns:
        List of ``ExtractedField`` objects in document order, one per leaf element.

    Raises:
        ExtractError: If the input is empty, unparseable, or contains no leaf fields.
    """
    if not xml_str or not xml_str.strip():
        raise ExtractError("Empty document")
    try:
        root = etree.fromstring(xml_str.encode() if isinstance(xml_str, str) else xml_str)
    except etree.XMLSyntaxError as e:
        raise ExtractError(f"XML parse error: {e}") from e
    fields: list[ExtractedField] = []
    _walk(root, "", fields)
    if not fields:
        raise ExtractError("Document contains no extractable leaf fields")
    return fields
