import json
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app
from eval.runner import _REPORT_PATH, EvalReport, CalibrationRow

_FIXTURE = EvalReport(
    total_records=2,
    total_proposed=4,
    total_expected=4,
    tp=3, fp=1, fn=1,
    precision=0.75,
    recall=0.75,
    calibration=[
        CalibrationRow(confidence_bucket="high (>=0.8)", total=3, correct=2, precision=0.6667),
        CalibrationRow(confidence_bucket="mid (0.5-0.8)", total=1, correct=1, precision=1.0),
        CalibrationRow(confidence_bucket="low (<0.5)", total=0, correct=0, precision=0.0),
    ],
    total_cost=0.0,
)


def test_get_latest_eval_returns_report(tmp_path, monkeypatch):
    report_file = tmp_path / "latest_report.json"
    report_file.write_text(_FIXTURE.model_dump_json())
    monkeypatch.setattr("eval.runner._REPORT_PATH", report_file)

    client = TestClient(app)
    resp = client.get("/api/eval/latest")
    assert resp.status_code == 200
    body = resp.json()
    assert body["precision"] == pytest.approx(0.75)
    assert body["recall"] == pytest.approx(0.75)
    assert len(body["calibration"]) == 3
    assert "total_cost" in body


def test_get_latest_eval_404_when_no_report(tmp_path, monkeypatch):
    monkeypatch.setattr("eval.runner._REPORT_PATH", tmp_path / "nonexistent.json")

    client = TestClient(app)
    resp = client.get("/api/eval/latest")
    assert resp.status_code == 404
