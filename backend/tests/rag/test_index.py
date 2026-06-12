import pytest
from qdrant_client import QdrantClient
from llama_index.core.embeddings import MockEmbedding
from app.rag.index import index_run, query_run


@pytest.mark.asyncio
async def test_index_and_query_run():
    client = QdrantClient(location=":memory:")
    embed_model = MockEmbedding(embed_dim=8)

    docs = [
        "Policy.PolNumber maps to policyNumber. Policy number uniquely identifies the policy.",
        "Policy.FaceAmt maps to faceAmount. Face amount is the death benefit in dollars.",
        "Person.FirstName maps to insuredFirstName. First name of the insured person.",
    ]

    run_id = 42
    await index_run(run_id, docs, client=client, embed_model=embed_model)

    nodes = query_run(run_id, "policy number", client=client, embed_model=embed_model)
    assert len(nodes) > 0
    # At least one result should mention policy
    texts = " ".join(n.text for n in nodes).lower()
    assert "policy" in texts
