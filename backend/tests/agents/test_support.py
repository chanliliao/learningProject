import pytest
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from llama_index.core.schema import NodeWithScore, TextNode
import app.models  # noqa: F401
from app.models.audit import LLMCall
from app.agents.support import answer_question, propose_edit, SupportAnswer


def _stub_retriever(nodes: list[NodeWithScore]):
    def retriever(run_id, question, **kwargs):
        return nodes
    return retriever


@pytest.mark.asyncio
async def test_answer_question_returns_answer_and_logs():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    stub_nodes = [
        NodeWithScore(node=TextNode(text="FaceAmt maps to faceAmount. Death benefit value."), score=0.9),
    ]

    async with AsyncSession(engine) as s:
        result = await answer_question(
            run_id=1,
            question="why is faceAmount mapped?",
            session=s,
            retriever=_stub_retriever(stub_nodes),
            mode="test",
        )
        await s.commit()

        assert isinstance(result, SupportAnswer)
        assert isinstance(result.answer, str)
        assert len(result.answer) > 0
        assert isinstance(result.proposed_edits, list)

        rows = (await s.exec(select(LLMCall))).all()
        assert len(rows) == 1


def test_propose_edit_returns_edit_intent():
    intent = propose_edit(
        run_id=1,
        field_id=10,
        new_target_path="coverageAmount",
        reason="Better semantic match",
    )
    assert intent["run_id"] == 1
    assert intent["field_id"] == 10
    assert intent["new_target_path"] == "coverageAmount"
    assert "reason" in intent
