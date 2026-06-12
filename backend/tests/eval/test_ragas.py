import pytest

try:
    import ragas  # noqa: F401
    RAGAS_IMPORTABLE = True
except Exception:
    RAGAS_IMPORTABLE = False


@pytest.mark.skipif(RAGAS_IMPORTABLE, reason="Only run mock test when ragas is unavailable")
def test_ragas_fallback_returns_correct_shape():
    """When ragas is unavailable the fallback path returns correct report shape."""
    from eval.ragas_eval import run_ragas

    samples = [
        {
            "question": "Why is faceAmount mapped to faceAmount?",
            "answer": "FaceAmt is the death benefit in the ACORD standard.",
            "contexts": ["FaceAmt maps to faceAmount. Death benefit."],
            "ground_truth": "FaceAmt is the death benefit.",
            "_score": 0.9,
        },
        {
            "question": "Why is PolNumber mapped to policyNumber?",
            "answer": "PolNumber uniquely identifies the policy.",
            "contexts": ["PolNumber maps to policyNumber. Policy identifier."],
            "ground_truth": "PolNumber is the policy identifier.",
            "_score": 0.8,
        },
    ]

    report = run_ragas(samples)

    assert "faithfulness" in report
    assert "answer_relevancy" in report
    assert "context_precision" in report
    assert all(isinstance(v, float) for v in report.values())
    assert all(0.0 <= v <= 1.0 for v in report.values())


@pytest.mark.skipif(not RAGAS_IMPORTABLE, reason="Requires ragas to be importable")
def test_ragas_evaluate_shape():
    """When ragas is available, verify report shape with real metrics."""
    from eval.ragas_eval import run_ragas

    samples = [
        {
            "question": "Why is faceAmount mapped?",
            "answer": "FaceAmt is the death benefit.",
            "contexts": ["FaceAmt maps to faceAmount. Death benefit value."],
            "ground_truth": "FaceAmt is the death benefit.",
        },
    ]

    report = run_ragas(samples)

    assert "faithfulness" in report
    assert "answer_relevancy" in report
    assert "context_precision" in report
