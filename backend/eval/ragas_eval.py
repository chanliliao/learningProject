"""Ragas RAG evaluation for Support agent answers."""
from __future__ import annotations

try:
    from ragas import evaluate as _ragas_evaluate
    from ragas.metrics import faithfulness, answer_relevancy, context_precision
    from datasets import Dataset
    RAGAS_IMPORTABLE = True
except ImportError:
    RAGAS_IMPORTABLE = False


def run_ragas(samples: list[dict]) -> dict:
    """
    Evaluate RAG samples using Ragas metrics.

    Each sample dict must have: question, answer, contexts (list[str]), ground_truth.
    Returns dict with faithfulness, answer_relevancy, context_precision scores.
    Falls back to mock scores when ragas is unavailable.
    """
    if not RAGAS_IMPORTABLE:
        scores = [s.get("_score", 1.0) for s in samples]
        avg = sum(scores) / len(scores) if scores else 0.0
        return {
            "faithfulness": avg,
            "answer_relevancy": avg,
            "context_precision": avg,
        }

    dataset = Dataset.from_list(samples)
    result = _ragas_evaluate(dataset, metrics=[faithfulness, answer_relevancy, context_precision])
    return {
        "faithfulness": float(result["faithfulness"]),
        "answer_relevancy": float(result["answer_relevancy"]),
        "context_precision": float(result["context_precision"]),
    }
