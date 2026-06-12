import argparse
import asyncio
import json
from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
import app.models  # noqa: F401
from eval.runner import evaluate, save_report

_GOLDEN_DIR = Path(__file__).parent / "golden"


def _load_golden() -> list[dict]:
    records = []
    for p in sorted(_GOLDEN_DIR.glob("*.json")):
        records.append(json.loads(p.read_text()))
    return records


async def _main(args: argparse.Namespace) -> None:
    from app.db import get_engine
    engine = get_engine()

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    golden = _load_golden()
    print(f"Loaded {len(golden)} golden records")

    async with AsyncSession(engine) as session:
        report = await evaluate(golden, session, mode="test")
        save_report(report)

    print(f"\n=== Eval Report ===")
    print(f"Records:   {report.total_records}")
    print(f"Precision: {report.precision:.2%}")
    print(f"Recall:    {report.recall:.2%}")
    print(f"TP/FP/FN:  {report.tp}/{report.fp}/{report.fn}")
    print(f"\nCalibration:")
    for row in report.calibration:
        print(f"  {row.confidence_bucket:20s}  n={row.total:3d}  correct={row.correct:3d}  precision={row.precision:.2%}")
    print(f"\nTotal LLM cost: ${report.total_cost:.6f}")
    print(f"\nReport saved to eval/latest_report.json")

    if args.ragas:
        from eval.ragas_eval import run_ragas, RAGAS_IMPORTABLE
        print(f"\n=== Ragas RAG Eval ===")
        if not RAGAS_IMPORTABLE:
            print("ragas not installed — showing mock scores")
        samples = [
            {
                "question": g.get("question", "What is this field?"),
                "answer": g.get("answer", ""),
                "contexts": g.get("contexts", []),
                "ground_truth": g.get("ground_truth", ""),
                "_score": g.get("_score", 1.0),
            }
            for g in golden
            if "question" in g or "_score" in g
        ]
        if not samples:
            print("No RAG samples in golden records (need question/answer/contexts/ground_truth fields).")
        else:
            scores = run_ragas(samples)
            for k, v in scores.items():
                print(f"  {k}: {v:.3f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run pipeline eval")
    parser.add_argument("--ragas", action="store_true", help="Also run Ragas RAG evaluation")
    args = parser.parse_args()
    asyncio.run(_main(args))
