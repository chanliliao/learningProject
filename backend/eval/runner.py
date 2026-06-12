import json
from pathlib import Path
from pydantic import BaseModel
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from app.agents.extract import extract
from app.agents.map import propose_mappings
from app.models.audit import LLMCall
from app.pipeline.confidence import score_mapping

_REPORT_PATH = Path(__file__).parent / "latest_report.json"


class CalibrationRow(BaseModel):
    confidence_bucket: str
    total: int
    correct: int
    precision: float


class EvalReport(BaseModel):
    total_records: int
    total_proposed: int
    total_expected: int
    tp: int
    fp: int
    fn: int
    precision: float
    recall: float
    calibration: list[CalibrationRow]
    total_cost: float


def _tp_fp_fn(proposed: list[str], expected: list[str]) -> tuple[int, int, int]:
    p_set = set(proposed)
    e_set = set(expected)
    tp = len(p_set & e_set)
    fp = len(p_set - e_set)
    fn = len(e_set - p_set)
    return tp, fp, fn


async def evaluate(
    golden_records: list[dict],
    session: AsyncSession,
    *,
    mode: str = "test",
) -> EvalReport:
    total_tp = total_fp = total_fn = 0
    total_proposed = total_expected = 0

    # for calibration: bucket proposals by confidence range
    high_bucket: list[tuple[bool, float]] = []   # confidence >= 0.8
    mid_bucket: list[tuple[bool, float]] = []    # 0.5 <= confidence < 0.8
    low_bucket: list[tuple[bool, float]] = []    # confidence < 0.5

    for record in golden_records:
        source_xml = record["source_xml"]
        target_schema = record["target_schema"]
        expected = [m["target_path"] for m in record.get("expected_mappings", [])]

        fields = extract(source_xml)
        proposals = await propose_mappings(
            fields, target_schema, run_id=None, session=session, mode=mode
        )
        proposed_targets = [p.target_path for p in proposals]

        tp, fp, fn = _tp_fp_fn(proposed_targets, expected)
        total_tp += tp
        total_fp += fp
        total_fn += fn
        total_proposed += len(proposed_targets)
        total_expected += len(expected)

        # calibration: bucket by hybrid (heuristic + LLM) confidence — same value the UI shows
        extracted_by_path = {f.path: f for f in fields}
        schema_props = target_schema.get("properties", {})
        schema_required = set(target_schema.get("required", []))
        expected_set = set(expected)
        for p in proposals:
            correct = p.target_path in expected_set
            src_field = extracted_by_path.get(p.source_path)
            tgt_prop = schema_props.get(p.target_path, {})
            scored = score_mapping(
                source_path=p.source_path,
                source_type=src_field.inferred_type if src_field else "str",
                target_path=p.target_path,
                target_type=tgt_prop.get("type", "string"),
                target_required=p.target_path in schema_required,
                target_enum=tgt_prop.get("enum"),
                value=src_field.value if src_field else "",
                llm_confidence=p.llm_confidence if p.llm_confidence is not None else 0.5,
            )
            conf = scored.score
            if conf >= 0.8:
                high_bucket.append((correct, conf))
            elif conf >= 0.5:
                mid_bucket.append((correct, conf))
            else:
                low_bucket.append((correct, conf))

    precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0.0
    recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0.0

    def _bucket_row(name: str, items: list[tuple[bool, float]]) -> CalibrationRow:
        n = len(items)
        correct = sum(1 for ok, _ in items if ok)
        return CalibrationRow(
            confidence_bucket=name,
            total=n,
            correct=correct,
            precision=correct / n if n > 0 else 0.0,
        )

    calibration = [
        _bucket_row("high (>=0.8)", high_bucket),
        _bucket_row("mid (0.5-0.8)", mid_bucket),
        _bucket_row("low (<0.5)", low_bucket),
    ]

    total_cost_result = await session.exec(select(LLMCall.estimated_cost))
    total_cost = sum(r for r in total_cost_result.all() if r is not None)

    return EvalReport(
        total_records=len(golden_records),
        total_proposed=total_proposed,
        total_expected=total_expected,
        tp=total_tp,
        fp=total_fp,
        fn=total_fn,
        precision=round(precision, 4),
        recall=round(recall, 4),
        calibration=calibration,
        total_cost=round(total_cost, 6),
    )


def save_report(report: EvalReport) -> None:
    _REPORT_PATH.write_text(report.model_dump_json(indent=2))


def load_latest_report() -> EvalReport | None:
    if not _REPORT_PATH.exists():
        return None
    data = json.loads(_REPORT_PATH.read_text())
    return EvalReport(**data)
