import pytest
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
import app.models  # noqa: F401
from eval.runner import evaluate

_GOLDEN = [
    {
        "source_xml": "<Policy><PolNumber>POL-001</PolNumber><FaceAmt>100000</FaceAmt></Policy>",
        "target_schema": {
            "type": "object",
            "required": ["policyNumber"],
            "properties": {
                "policyNumber": {"type": "string"},
                "faceAmount": {"type": "number"},
            },
        },
        "expected_mappings": [
            {"source_path": "Policy.PolNumber", "target_path": "policyNumber"},
            {"source_path": "Policy.FaceAmt", "target_path": "faceAmount"},
        ],
    }
]


@pytest.mark.asyncio
async def test_evaluate_returns_valid_report():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async with AsyncSession(engine) as session:
        report = await evaluate(_GOLDEN, session, mode="test")

    assert 0.0 <= report.precision <= 1.0
    assert 0.0 <= report.recall <= 1.0
    assert report.total_records == 1
    assert report.total_expected == 2
    assert len(report.calibration) == 3
    assert report.total_cost >= 0.0
