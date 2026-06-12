from fastapi import APIRouter, HTTPException
from eval.runner import load_latest_report

router = APIRouter()


@router.get("/eval/latest")
async def get_latest_eval():
    report = load_latest_report()
    if report is None:
        raise HTTPException(status_code=404, detail="No eval report found. Run: uv run python -m eval")
    return report.model_dump()
