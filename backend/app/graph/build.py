"""
LangGraph pipeline orchestration: builds and runs the 6-stage document mapping pipeline.

Pipeline stages (in order):
    extract → extract_interrupt → interpret → interpret_interrupt →
    map → review_interrupt → build → test → test_interrupt → END

Each ``*_interrupt`` node calls LangGraph's ``interrupt()`` to pause execution and
wait for a human reviewer to approve or reject via the review API.  Only after all
four gates (extract, interpret, map, test) are approved does the run reach ``END``
and get indexed into Qdrant.

Each substantive node (extract, interpret, map, build, test) opens its own session via
``session_factory`` so that LangGraph can replay individual nodes across multiple Python
invocations without inheriting a stale session from a previous run.  The factory wraps
the caller's existing session via ``_session_factory_from`` so tests and the router
layer do not need to change.

Entry points:
    ``start_run`` — start a new pipeline run from the initial state.
    ``resume_run`` — resume a paused run after a reviewer decision.
"""

import uuid
from contextlib import asynccontextmanager
from typing import Any, Callable, TypedDict
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt, Command
from langgraph.errors import NodeInterrupt
from langgraph.checkpoint.memory import MemorySaver
from app.models.run import PipelineRun, StageResult
from app.models.mapping import FieldMapping
from app.models.audit import AuditEvent
from app.models.schema import TargetSchema
from app.agents.extract import extract
from app.agents.interpret import interpret_fields
from app.agents.map import propose_mappings
from app.agents.transform import run_build, TransformSpec, _TRANSFORMS
from app.agents.qa import run_qa_checks
from app.agents.base import ExtractedField, InterpretedField, FieldMappingProposal
from app.pipeline.confidence import score_mapping


def _session_factory_from(session: AsyncSession) -> Callable:
    """Wrap an existing ``AsyncSession`` in an async context-manager factory.

    Each graph node expects a zero-argument callable that returns an async context
    manager yielding an ``AsyncSession``.  When ``start_run`` and ``resume_run`` already
    hold a session (e.g. from a FastAPI dependency), this function wraps it so the
    node closures can use the same session without opening a new one.

    Args:
        session: An already-open async SQLModel session.

    Returns:
        Async context-manager factory ``() -> AsyncContextManager[AsyncSession]``.
    """
    @asynccontextmanager
    async def _factory():
        yield session
    return _factory


class PipelineState(TypedDict):
    """Mutable state passed between LangGraph nodes throughout a pipeline run.

    Attributes:
        run_id: Primary key of the owning ``PipelineRun`` row.
        source_xml: Full XML document string uploaded by the user.
        target_schema: Parsed JSON Schema definition of the target data format.
        extracted: Leaf fields produced by the extract node.
        interpreted: Semantically enriched fields produced by the interpret node.
        mappings: Field-mapping proposals produced by the map node.
    """

    run_id: int
    source_xml: str
    target_schema: dict
    extracted: list[ExtractedField]
    interpreted: list[InterpretedField]
    mappings: list[FieldMappingProposal]


def build_pipeline(session_factory: Callable, checkpointer: Any, mode: str | None = None):
    """Construct and compile the LangGraph pipeline for a single run's lifetime.

    Each call returns a freshly compiled graph.  Nodes open and close their own
    sessions via ``session_factory`` so LangGraph replay (across multiple Python
    invocations) never shares a stale session.

    Args:
        session_factory: Zero-argument async context-manager factory that yields an
            ``AsyncSession``.  Use ``_session_factory_from`` to wrap an existing session,
            or pass a proper factory for production use.
        checkpointer: LangGraph checkpointer for persisting interrupt state.
            Use ``MemorySaver`` in tests, ``AsyncPostgresSaver`` in production.
        mode: LLM mode override — ``"test"`` swaps in ``TestModel`` for all agent
            calls, ``None`` reads from ``Settings.llm_mode``.

    Returns:
        A compiled LangGraph ``Runnable`` ready to call with ``ainvoke``.
    """
    async def extract_node(state: PipelineState) -> dict:
        """Parse the XML document and record extracted fields.

        Runs the deterministic extract agent (no LLM), persists a ``StageResult``
        (status="awaiting_review"), and sets the run status to ``"awaiting_review"``.

        Args:
            state: Pipeline state containing ``run_id`` and ``source_xml``.

        Returns:
            Dict with ``"extracted"`` key containing the list of ``ExtractedField``
            objects to merge into graph state.
        """
        run_id = state["run_id"]
        async with session_factory() as session:
            try:
                fields = extract(state["source_xml"])
                run = (await session.exec(select(PipelineRun).where(PipelineRun.id == run_id))).first()
                if run:
                    run.status = "awaiting_review"
                    session.add(run)
                session.add(StageResult(run_id=run_id, stage="extract", status="awaiting_review", payload={"count": len(fields)}))
                session.add(AuditEvent(
                    run_id=run_id, actor="system", action="extract_completed",
                    after={"field_count": len(fields)},
                ))
                await session.flush()
                return {"extracted": fields}
            except Exception as e:
                run = (await session.exec(select(PipelineRun).where(PipelineRun.id == run_id))).first()
                if run:
                    run.status = "failed"
                    session.add(run)
                session.add(AuditEvent(run_id=run_id, actor="system", action="extract_failed", after={"error": str(e)}))
                await session.flush()
                raise

    async def extract_interrupt_node(state: PipelineState) -> dict:
        """Human-in-the-loop gate after extraction.

        Calls ``interrupt()`` so LangGraph saves the checkpoint and raises
        ``NodeInterrupt``.  Execution resumes when ``resume_run`` is called with
        ``stage="extract"`` and ``decision="approve"``.

        Args:
            state: Current pipeline state.

        Returns:
            Empty dict — no state change.
        """
        interrupt({"run_id": state["run_id"], "status": "awaiting_review", "gate": "extract"})
        return {}

    async def interpret_node(state: PipelineState) -> dict:
        """Enrich extracted fields with ACORD domain semantics via LLM.

        Calls the interpret agent, persists a ``StageResult`` (status="awaiting_review"),
        and updates the run status.

        Args:
            state: Pipeline state with ``extracted`` populated.

        Returns:
            Dict with ``"interpreted"`` key to merge into graph state.
        """
        run_id = state["run_id"]
        async with session_factory() as session:
            try:
                interpreted = await interpret_fields(
                    state["extracted"],
                    run_id=run_id,
                    session=session,
                    mode=mode,
                )
                run = (await session.exec(select(PipelineRun).where(PipelineRun.id == run_id))).first()
                if run:
                    run.status = "awaiting_review"
                    session.add(run)
                session.add(StageResult(
                    run_id=run_id, stage="interpret", status="awaiting_review",
                    payload={"count": len(interpreted)},
                ))
                session.add(AuditEvent(
                    run_id=run_id, actor="system", action="interpret_completed",
                    after={"field_count": len(interpreted)},
                ))
                await session.flush()
                return {"interpreted": interpreted}
            except Exception as e:
                run = (await session.exec(select(PipelineRun).where(PipelineRun.id == run_id))).first()
                if run:
                    run.status = "failed"
                    session.add(run)
                session.add(AuditEvent(run_id=run_id, actor="system", action="interpret_failed", after={"error": str(e)}))
                await session.flush()
                raise

    async def interpret_interrupt_node(state: PipelineState) -> dict:
        """Human-in-the-loop gate after interpretation.

        Args:
            state: Current pipeline state.

        Returns:
            Empty dict — no state change.
        """
        interrupt({"run_id": state["run_id"], "status": "awaiting_review", "gate": "interpret"})
        return {}

    async def map_node(state: PipelineState) -> dict:
        """Propose source→target field mappings via LLM, score, and persist them.

        Validates LLM-suggested transform strings against ``_TRANSFORMS`` before
        saving — any unrecognised value is normalised to ``None`` so that
        ``build_transform`` never receives invalid names.

        Args:
            state: Pipeline state with ``extracted``, ``interpreted``, and
                ``target_schema`` populated.

        Returns:
            Dict with ``"mappings"`` key to merge into graph state.
        """
        run_id = state["run_id"]
        async with session_factory() as session:
            try:
                proposals = await propose_mappings(
                    state["extracted"],
                    state["target_schema"],
                    run_id=run_id,
                    session=session,
                    mode=mode,
                    interpreted=state.get("interpreted"),
                )
                extracted_by_path = {f.path: f for f in state["extracted"]}
                schema_props = state["target_schema"].get("properties", {})
                schema_required = set(state["target_schema"].get("required", []))
                for p in proposals:
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
                    # Discard any transform string the LLM invented that is not in the
                    # registry — normalise to None at ingestion time so build_transform
                    # never receives an unrecognised name.
                    valid_transform = p.transform if p.transform in _TRANSFORMS else None
                    session.add(FieldMapping(
                        run_id=run_id,
                        source_path=p.source_path,
                        target_path=p.target_path,
                        transform=valid_transform,
                        confidence=scored.score,
                        flags=scored.flags,
                        status="proposed",
                    ))
                stage = StageResult(run_id=run_id, stage="map", status="awaiting_review", payload={"count": len(proposals)})
                session.add(stage)
                run = (await session.exec(select(PipelineRun).where(PipelineRun.id == run_id))).first()
                if run:
                    run.status = "awaiting_review"
                    session.add(run)
                session.add(AuditEvent(
                    run_id=run_id, actor="system", action="map_proposed",
                    after={"mapping_count": len(proposals), "status": "awaiting_review"},
                ))
                await session.flush()
                return {"mappings": proposals}
            except Exception as e:
                run = (await session.exec(select(PipelineRun).where(PipelineRun.id == run_id))).first()
                if run:
                    run.status = "failed"
                    session.add(run)
                session.add(AuditEvent(run_id=run_id, actor="system", action="map_failed", after={"error": str(e)}))
                await session.flush()
                raise

    async def review_interrupt_node(state: PipelineState) -> dict:
        """Human-in-the-loop gate after mapping proposals.

        Args:
            state: Current pipeline state.

        Returns:
            Empty dict — no state change.
        """
        interrupt({"run_id": state["run_id"], "status": "awaiting_review", "gate": "map"})
        return {}

    async def build_node(state: PipelineState) -> dict:
        """Compile approved field mappings into a ``TransformSpec``.

        Delegates to ``run_build`` which reads all approved/edited ``FieldMapping``
        rows, validates transform names, and persists the spec to a ``StageResult``.

        Args:
            state: Pipeline state with ``run_id`` populated.

        Returns:
            Empty dict — the compiled spec is stored in the ``StageResult`` payload.
        """
        run_id = state["run_id"]
        async with session_factory() as session:
            try:
                await run_build(run_id, session)
                return {}
            except Exception as e:
                run = (await session.exec(select(PipelineRun).where(PipelineRun.id == run_id))).first()
                if run:
                    run.status = "failed"
                    session.add(run)
                session.add(AuditEvent(run_id=run_id, actor="system", action="build_failed", after={"error": str(e)}))
                await session.flush()
                raise

    async def test_node(state: PipelineState) -> dict:
        """Run QA checks against the compiled transform spec.

        Loads the spec from the build ``StageResult`` payload, re-extracts the source
        XML as the live sample, and runs ``run_qa_checks``.  Persists pass/fail counts
        to a new ``StageResult`` (stage="test").

        Args:
            state: Pipeline state with ``run_id``, ``source_xml``, and
                ``target_schema`` populated.

        Returns:
            Empty dict — results stored in the ``StageResult`` payload.

        Raises:
            RuntimeError: If the build stage result is absent, indicating the pipeline
                ran out of order.
        """
        run_id = state["run_id"]
        async with session_factory() as session:
            try:
                fields = extract(state["source_xml"])
                source_dict = {f.path: f.value for f in fields}
                build_stage = (await session.exec(
                    select(StageResult).where(StageResult.run_id == run_id, StageResult.stage == "build")
                )).first()
                if build_stage is None:
                    raise RuntimeError(f"build stage not found for run_id={run_id}")
                spec_data = build_stage.payload.get("spec", {})
                spec = TransformSpec(**spec_data) if spec_data else TransformSpec(mappings=[])

                report = run_qa_checks(spec, state["target_schema"], [source_dict])

                run = (await session.exec(select(PipelineRun).where(PipelineRun.id == run_id))).first()
                if run:
                    run.status = "awaiting_review"
                    session.add(run)
                session.add(StageResult(
                    run_id=run_id,
                    stage="test",
                    status="awaiting_review",
                    payload={"total": report.total, "passed": report.passed},
                ))
                session.add(AuditEvent(
                    run_id=run_id, actor="system", action="test_completed",
                    after={"total": report.total, "passed": report.passed},
                ))
                await session.flush()
                return {}
            except Exception as e:
                run = (await session.exec(select(PipelineRun).where(PipelineRun.id == run_id))).first()
                if run:
                    run.status = "failed"
                    session.add(run)
                session.add(AuditEvent(run_id=run_id, actor="system", action="test_failed", after={"error": str(e)}))
                await session.flush()
                raise

    async def test_interrupt_node(state: PipelineState) -> dict:
        """Human-in-the-loop gate after QA testing.

        This is the final gate.  Once approved, the graph reaches ``END`` and
        ``resume_run`` marks the run ``"completed"`` and indexes it into Qdrant.

        Args:
            state: Current pipeline state.

        Returns:
            Empty dict — no state change.
        """
        interrupt({"run_id": state["run_id"], "status": "awaiting_review", "gate": "test"})
        return {}

    graph = StateGraph(PipelineState)
    graph.add_node("extract", extract_node)
    graph.add_node("extract_interrupt", extract_interrupt_node)
    graph.add_node("interpret", interpret_node)
    graph.add_node("interpret_interrupt", interpret_interrupt_node)
    graph.add_node("map", map_node)
    graph.add_node("review_interrupt", review_interrupt_node)
    graph.add_node("build", build_node)
    graph.add_node("test", test_node)
    graph.add_node("test_interrupt", test_interrupt_node)
    graph.add_edge(START, "extract")
    graph.add_edge("extract", "extract_interrupt")
    graph.add_edge("extract_interrupt", "interpret")
    graph.add_edge("interpret", "interpret_interrupt")
    graph.add_edge("interpret_interrupt", "map")
    graph.add_edge("map", "review_interrupt")
    graph.add_edge("review_interrupt", "build")
    graph.add_edge("build", "test")
    graph.add_edge("test", "test_interrupt")
    graph.add_edge("test_interrupt", END)
    return graph.compile(checkpointer=checkpointer)


async def _index_completed_run(
    run_id: int,
    session: AsyncSession,
    *,
    qdrant_client: Any = None,
    embed_model: Any = None,
    mode: str | None = None,
) -> None:
    """Index the completed run's mappings into Qdrant for RAG retrieval.

    Called automatically by ``resume_run`` when the graph reaches ``END``.  Builds
    one text document per ``FieldMapping`` row and passes them to ``index_run``.  In
    ``"test"`` mode, a ``MockEmbedding`` is injected automatically so tests do not
    require a real embedding API.

    Args:
        run_id: ID of the completed ``PipelineRun``.
        session: Active async SQLModel session for loading ``FieldMapping`` rows.
        qdrant_client: Override Qdrant client.  ``None`` uses ``_get_client()``.
        embed_model: Override embedding model.  ``None`` uses ``_get_embed_model()``.
        mode: LLM mode override — ``"test"`` injects ``MockEmbedding``.
    """
    from app.rag.index import index_run

    if embed_model is None and mode == "test":
        from llama_index.core.embeddings import MockEmbedding
        embed_model = MockEmbedding(embed_dim=8)

    mappings = (await session.exec(select(FieldMapping).where(FieldMapping.run_id == run_id))).all()
    docs = [
        f"{m.source_path} maps to {m.target_path}. "
        f"Confidence: {m.confidence:.2f}. "
        f"{'Transform: ' + m.transform + '. ' if m.transform else ''}"
        f"Status: {m.status}."
        for m in mappings
    ]
    if not docs:
        docs = [f"Run {run_id} completed with no mappings."]
    await index_run(run_id, docs, client=qdrant_client, embed_model=embed_model)


async def start_run(
    run_id: int,
    session: AsyncSession,
    *,
    checkpointer: Any = None,
    mode: str | None = None,
) -> None:
    """Start the pipeline for an existing ``PipelineRun`` record.

    Loads the run and its target schema, assigns a LangGraph thread ID, then invokes
    the compiled graph.  The graph runs until it hits the first interrupt
    (``extract_interrupt``) and then returns — the run is left in
    ``status="awaiting_review"``.

    The ``NodeInterrupt`` raised at the first gate is caught here because it is the
    expected happy-path exit: the graph saved its checkpoint and is waiting for a
    ``resume_run`` call.

    Args:
        run_id: Primary key of an existing ``PipelineRun`` with ``source_xml`` and a
            valid ``target_schema_id`` set.
        session: Active async SQLModel session.  Caller is responsible for committing
            after this function returns.
        checkpointer: LangGraph checkpointer.  Defaults to an in-memory
            ``MemorySaver``.  Production wires in ``AsyncPostgresSaver`` via the
            FastAPI lifespan.
        mode: LLM mode override.

    Raises:
        ValueError: If ``run_id`` does not exist, or if its ``target_schema_id``
            references a non-existent schema.
    """
    if checkpointer is None:
        checkpointer = MemorySaver()

    run = (await session.exec(select(PipelineRun).where(PipelineRun.id == run_id))).first()
    if run is None:
        raise ValueError(f"PipelineRun {run_id} not found")

    schema = (await session.exec(
        select(TargetSchema).where(TargetSchema.id == run.target_schema_id)
    )).first()
    if schema is None:
        raise ValueError(f"TargetSchema {run.target_schema_id} not found")

    thread_id = str(uuid.uuid4())
    run.thread_id = thread_id
    session.add(run)
    await session.flush()

    compiled = build_pipeline(_session_factory_from(session), checkpointer, mode=mode)
    config = {"configurable": {"thread_id": thread_id}}
    initial_state: PipelineState = {
        "run_id": run_id,
        "source_xml": run.source_xml,
        "target_schema": schema.definition,
        "extracted": [],
        "interpreted": [],
        "mappings": [],
    }
    try:
        await compiled.ainvoke(initial_state, config=config)
    except NodeInterrupt:
        pass  # Graph paused at extract_interrupt — expected happy-path exit


async def resume_run(
    run_id: int,
    decision: str,
    session: AsyncSession,
    *,
    checkpointer: Any = None,
    edits: list[dict] | None = None,
    stage: str = "map",
    qdrant_client: Any = None,
    embed_model: Any = None,
    mode: str | None = None,
) -> None:
    """Resume a paused pipeline run after a reviewer decision.

    Applies any field edits, records the review decision, then resumes the LangGraph
    graph via ``Command(resume=...)``.  If the graph reaches ``END``, the run is marked
    ``"completed"`` and indexed into Qdrant.

    Rejection short-circuits the graph: the stage is marked ``"rejected"``, the run
    is marked ``"failed"``, and no further processing occurs.

    When approving the map stage (``stage="map"``), all ``FieldMapping`` rows still in
    ``"proposed"`` status are promoted to ``"approved"`` before resuming so that
    ``run_build`` includes them.

    Args:
        run_id: ID of the ``PipelineRun`` to resume.
        decision: ``"approve"`` to continue execution, ``"reject"`` to halt.
        session: Active async SQLModel session.  Caller is responsible for committing.
        checkpointer: LangGraph checkpointer holding the saved interrupt state.  Must
            be the same instance used by ``start_run`` — the checkpoint is keyed by
            ``thread_id``.
        edits: Optional field edits to apply before resuming.  Each dict must contain
            an ``"id"`` key (``FieldMapping`` primary key) plus any field keys to
            overwrite.
        stage: Pipeline gate being reviewed: ``"extract"``, ``"interpret"``, ``"map"``,
            or ``"test"``.  Defaults to ``"map"`` for backwards compatibility.
        qdrant_client: Override Qdrant client for indexing on completion.
        embed_model: Override embedding model for indexing on completion.
        mode: LLM mode override.

    Raises:
        ValueError: If ``run_id`` does not correspond to an existing ``PipelineRun``.
    """
    if checkpointer is None:
        checkpointer = MemorySaver()

    run = (await session.exec(select(PipelineRun).where(PipelineRun.id == run_id))).first()
    if run is None:
        raise ValueError(f"PipelineRun {run_id} not found")

    current_stage = (await session.exec(
        select(StageResult).where(StageResult.run_id == run_id, StageResult.stage == stage)
    )).first()

    if edits:
        for edit in edits:
            fm = (await session.exec(
                select(FieldMapping).where(FieldMapping.id == edit["id"])
            )).first()
            if fm:
                for k, v in edit.items():
                    if k != "id":
                        setattr(fm, k, v)
                session.add(fm)

    if decision == "reject":
        if current_stage:
            current_stage.status = "rejected"
            session.add(current_stage)
        run.status = "failed"
        session.add(run)
        session.add(AuditEvent(
            run_id=run_id, actor="reviewer", action=f"{stage}_rejected",
            after={"decision": "reject"},
        ))
        await session.flush()
        return

    if current_stage:
        current_stage.status = "approved"
        session.add(current_stage)
    session.add(AuditEvent(
        run_id=run_id, actor="reviewer", action=f"{stage}_approved",
        after={"decision": "approve"},
    ))
    if stage == "map":
        # Promote all still-proposed mappings to approved so run_build includes them.
        # Mappings already edited by the reviewer have status="edited" and are picked
        # up by run_build regardless — this only sweeps up unmodified proposals.
        proposed = (await session.exec(
            select(FieldMapping).where(
                FieldMapping.run_id == run_id,
                FieldMapping.status == "proposed",
            )
        )).all()
        for fm in proposed:
            fm.status = "approved"
            session.add(fm)
    await session.flush()

    compiled = build_pipeline(_session_factory_from(session), checkpointer, mode=mode)
    config = {"configurable": {"thread_id": run.thread_id}}
    try:
        await compiled.ainvoke(Command(resume={"decision": decision}), config=config)
    except NodeInterrupt:
        pass  # Some LangGraph versions re-raise NodeInterrupt on the next gate; others save checkpoint silently

    # If no further nodes are pending, the graph reached END — mark complete and index
    graph_state = await compiled.aget_state(config)
    if not graph_state.next:
        run.status = "completed"
        session.add(run)
        await session.flush()
        await _index_completed_run(run_id, session, qdrant_client=qdrant_client, embed_model=embed_model, mode=mode)
