from __future__ import annotations

import asyncio
import json
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic_core import to_jsonable_python
from sqlalchemy import event, select

from mini_agent.application import persistence as application_persistence
from mini_agent.application.persistence import (
    P0PersistenceIntegrityCategory,
    P0PersistenceIntegrityError,
    P0RecordCode,
    encode_persistence_record_versioned,
)
from mini_agent.application.records import (
    ConditionalWriteResult,
    CreateInitialTaskGraphV2Command,
    CreateRunCommand,
    InsertOnlyWriteResult,
    SaveRequestUnderstandingV2NoTaskCommand,
    TransitionRunCommand,
)
from mini_agent.core.task_state import (
    CandidateRejectionReasonCode,
    CandidateValidationDecision,
    CandidateValidationRecordV2,
)
from mini_agent.core.trace import AgentRunStatus
from mini_agent.infrastructure.persistence import postgres as postgres_persistence
from mini_agent.infrastructure.persistence.database import build_session_factory
from mini_agent.infrastructure.persistence.models import (
    P0RecordModel,
    P0RecordReferenceModel,
)
from mini_agent.infrastructure.persistence.postgres import PostgresRecordAdapter

_COMPONENT_APPLICATION_TESTS = (
    Path(__file__).parents[1] / "component" / "application"
)
sys.path.append(str(_COMPONENT_APPLICATION_TESTS))
from test_record_contracts import (  # noqa: E402
    _initial_graph,
    _initial_v2_graph,
)

pytestmark = pytest.mark.anyio


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


def _no_task_from_graph(
    graph: CreateInitialTaskGraphV2Command,
) -> SaveRequestUnderstandingV2NoTaskCommand:
    record = graph.request_understanding.record
    candidate = record.task_delta_candidates[0]
    no_task_record = record.model_copy(
        update={
            "candidate_validation": (
                CandidateValidationRecordV2(
                    candidate_ref=candidate.candidate_id,
                    decision=CandidateValidationDecision.REJECT,
                    reason_code=(
                        CandidateRejectionReasonCode.INPUT_VALUE_INVALID
                    ),
                ),
            ),
            "accepted_delta_refs": (),
            "proposed_base_task_state_version": None,
            "validated_task_state_version": None,
            "next_move_candidate_ref": None,
        }
    )
    return SaveRequestUnderstandingV2NoTaskCommand(
        owner_scope=graph.owner_scope,
        expected_conversation_record=graph.expected_conversation_record,
        expected_message_records=graph.expected_message_records,
        expected_active_run_record=graph.expected_active_run_record,
        request_understanding_record=no_task_record,
    )


def _second_v2_graph(
    graph: CreateInitialTaskGraphV2Command,
) -> CreateInitialTaskGraphV2Command:
    accepted_delta_id = uuid4()
    binding_id = uuid4()
    task_id = uuid4()
    request_unit_id = uuid4()
    record = graph.request_understanding.record.model_copy(
        update={
            "request_understanding_record_id": uuid4(),
            "accepted_delta_refs": (accepted_delta_id,),
            "next_move_candidate_ref": uuid4(),
        }
    )
    accepted = graph.request_understanding.accepted_delta.model_copy(
        update={
            "accepted_delta_id": accepted_delta_id,
            "input_binding_refs": (binding_id,),
            "task_id": task_id,
        }
    )
    binding = graph.input_binding.record.model_copy(
        update={"binding_id": binding_id}
    )
    task = graph.initial_task.initial_record.model_copy(
        update={"task_id": task_id}
    )
    unit = graph.initial_request_unit.initial_record.model_copy(
        update={
            "request_unit_id": request_unit_id,
            "task_id": task_id,
            "input_binding_refs": (binding_id,),
        }
    )
    return CreateInitialTaskGraphV2Command(
        owner_scope=graph.owner_scope,
        expected_conversation_record=graph.expected_conversation_record,
        expected_message_records=graph.expected_message_records,
        expected_active_run_record=graph.expected_active_run_record,
        request_understanding=type(graph.request_understanding)(
            record=record,
            accepted_delta=accepted,
        ),
        initial_task=type(graph.initial_task)(initial_record=task),
        initial_request_unit=type(graph.initial_request_unit)(
            initial_record=unit
        ),
        input_binding=type(graph.input_binding)(
            record=binding,
            request_unit_id=request_unit_id,
        ),
        conversation_task_link=graph.conversation_task_link.model_copy(
            update={"task_id": task_id}
        ),
        run_task_link=type(graph.run_task_link)(
            active_record=graph.run_task_link.active_record.model_copy(
                update={"task_id": task_id}
            )
        ),
    )


def _legacy_graph_for(
    graph: CreateInitialTaskGraphV2Command,
):
    template = _initial_graph()
    current_message = next(
        message
        for message in graph.expected_message_records
        if message.message_id == graph.request_understanding.record.message_ref
    )
    binding_template = template.input_bindings[0]
    binding = binding_template.record.model_copy(
        update={"source_refs": (current_message.message_id,)}
    )
    accepted_template = template.request_understanding.accepted_deltas[0]
    accepted = accepted_template.model_copy(
        update={
            "message_ref": current_message.message_id,
            "input_binding_refs": (binding.binding_id,),
        }
    )
    understanding = template.request_understanding.record.model_copy(
        update={
            "run_id": graph.expected_active_run_record.run_id,
            "message_ref": current_message.message_id,
            "accepted_delta_refs": (accepted.accepted_delta_id,),
        }
    )
    task = template.initial_task.initial_record
    unit = template.initial_request_unit.initial_record.model_copy(
        update={
            "task_id": task.task_id,
            "goal_text": accepted.goal_text,
            "goal_source_refs": (current_message.message_id,),
            "input_binding_refs": (binding.binding_id,),
        }
    )
    return type(template)(
        owner_scope=graph.owner_scope,
        expected_conversation_record=graph.expected_conversation_record,
        expected_message_record=current_message,
        expected_active_run_record=graph.expected_active_run_record,
        request_understanding=type(template.request_understanding)(
            record=understanding,
            accepted_deltas=(accepted,),
        ),
        initial_task=type(template.initial_task)(initial_record=task),
        initial_request_unit=type(template.initial_request_unit)(
            initial_record=unit
        ),
        input_bindings=(
            type(binding_template)(
                record=binding,
                request_unit_id=unit.request_unit_id,
            ),
        ),
        conversation_task_link=template.conversation_task_link.model_copy(
            update={
                "conversation_id": (
                    graph.expected_conversation_record.conversation_id
                ),
                "task_id": task.task_id,
            }
        ),
        run_task_link=type(template.run_task_link)(
            active_record=template.run_task_link.active_record.model_copy(
                update={
                    "run_id": graph.expected_active_run_record.run_id,
                    "task_id": task.task_id,
                }
            )
        ),
    )


async def _seed_v2_roots(
    adapter: PostgresRecordAdapter,
    graph: CreateInitialTaskGraphV2Command,
) -> None:
    await adapter.save_conversation(graph.expected_conversation_record)
    for message in graph.expected_message_records:
        await adapter.append_message(message)
    active_run = graph.expected_active_run_record
    created_run = active_run.model_copy(update={"status": AgentRunStatus.CREATED})
    assert (
        await adapter.insert_run(CreateRunCommand(created_record=created_run))
        is InsertOnlyWriteResult.INSERTED
    )
    assert (
        await adapter.start_run_if_created(
            TransitionRunCommand(
                expected_active_record=created_run,
                next_record=active_run,
            )
        )
        is ConditionalWriteResult.APPLIED
    )


def _database_snapshot(
    adapter: PostgresRecordAdapter,
) -> tuple[tuple[object, ...], tuple[object, ...]]:
    with adapter.session_factory() as session:
        rows = tuple(
            (
                str(row.record_id),
                row.record_code,
                row.record_schema_version,
                json.dumps(
                    row.logical_identity,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                row.scope_owner_customer_id,
                str(row.run_id) if row.run_id is not None else None,
                json.dumps(
                    row.envelope,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                row.stored_at,
            )
            for row in session.scalars(
                select(P0RecordModel).order_by(P0RecordModel.record_id)
            )
        )
        references = tuple(
            (
                str(reference.reference_id),
                reference.source_record_code,
                json.dumps(
                    reference.source_logical_identity,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                reference.ordinal,
                reference.relation,
                reference.target_record_code,
                json.dumps(
                    reference.target_logical_identity,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ),
            )
            for reference in session.scalars(
                select(P0RecordReferenceModel).order_by(
                    P0RecordReferenceModel.reference_id
                )
            )
        )
    return rows, references


async def test_no_task_writer_roundtrips_exact_v2_and_replays_without_mutation(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    adapter = PostgresRecordAdapter(build_session_factory(engine))
    graph = _initial_v2_graph()
    command = _no_task_from_graph(graph)
    try:
        await _seed_v2_roots(adapter, graph)
        assert (
            await adapter.save_request_understanding_v2_no_task_if_current(
                command
            )
            is ConditionalWriteResult.APPLIED
        )
        loaded = await adapter.load_exact_run_evidence_for_owner(
            owner_scope=command.owner_scope,
            run_id=command.expected_active_run_record.run_id,
        )
        assert loaded is not None
        assert (
            loaded.request_understanding_record
            == command.request_understanding_record
        )
        assert loaded.accepted_task_deltas == ()
        assert loaded.task_records == ()
        assert loaded.request_unit_records == ()
        assert loaded.input_binding_records == ()
        assert loaded.conversation_task_links == ()
        assert loaded.run_task_links == ()

        first_snapshot = _database_snapshot(adapter)
        assert (
            await adapter.save_request_understanding_v2_no_task_if_current(
                command
            )
            is ConditionalWriteResult.APPLIED
        )
        assert _database_snapshot(adapter) == first_snapshot
    finally:
        engine.dispose()


async def test_initial_graph_writer_roundtrips_exact_v2_and_replays_without_mutation(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    adapter = PostgresRecordAdapter(build_session_factory(engine))
    command = _initial_v2_graph()
    try:
        await _seed_v2_roots(adapter, command)
        assert (
            await adapter.create_initial_task_graph_v2_if_current(command)
            is ConditionalWriteResult.APPLIED
        )
        loaded = await adapter.load_exact_run_evidence_for_owner(
            owner_scope=command.owner_scope,
            run_id=command.expected_active_run_record.run_id,
        )
        assert loaded is not None
        assert (
            loaded.request_understanding_record
            == command.request_understanding.record
        )
        assert loaded.accepted_task_deltas == (
            command.request_understanding.accepted_delta,
        )
        assert loaded.task_records == (command.initial_task.initial_record,)
        assert loaded.request_unit_records == (
            command.initial_request_unit.initial_record,
        )
        assert loaded.input_binding_records == (command.input_binding.record,)
        assert loaded.conversation_task_links == (
            command.conversation_task_link,
        )
        assert loaded.run_task_links == (
            command.run_task_link.active_record,
        )

        first_snapshot = _database_snapshot(adapter)
        assert (
            await adapter.create_initial_task_graph_v2_if_current(command)
            is ConditionalWriteResult.APPLIED
        )
        assert _database_snapshot(adapter) == first_snapshot
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("method_name", "command_factory"),
    (
        (
            "save_request_understanding_v2_no_task_if_current",
            lambda graph: _no_task_from_graph(graph),
        ),
        (
            "create_initial_task_graph_v2_if_current",
            lambda graph: graph,
        ),
    ),
)
async def test_v2_writers_do_not_call_legacy_codec_or_persistence_chain(
    eval_postgres_namespace,
    monkeypatch,
    method_name: str,
    command_factory: Callable[[CreateInitialTaskGraphV2Command], object],
) -> None:
    engine = eval_postgres_namespace.build_engine()
    adapter = PostgresRecordAdapter(build_session_factory(engine))
    graph = _initial_v2_graph()

    def forbidden(*_args, **_kwargs):
        raise AssertionError("legacy persistence path used by RU-v2 writer")

    try:
        await _seed_v2_roots(adapter, graph)
        monkeypatch.setattr(
            application_persistence,
            "encode_persistence_record",
            forbidden,
        )
        monkeypatch.setattr(
            application_persistence,
            "decode_persistence_record",
            forbidden,
        )
        monkeypatch.setattr(
            postgres_persistence,
            "encode_persistence_record",
            forbidden,
        )
        monkeypatch.setattr(
            postgres_persistence,
            "decode_persistence_record",
            forbidden,
        )
        for helper_name in (
            "_persist_envelopes",
            "_decode_envelope",
            "_decode_row",
            "_validate_physical_projection",
            "_derive_owner_from_graph",
        ):
            monkeypatch.setattr(adapter, helper_name, forbidden)

        result = await getattr(adapter, method_name)(command_factory(graph))
        assert result is ConditionalWriteResult.APPLIED
    finally:
        engine.dispose()


async def test_absent_trusted_run_returns_not_applicable_before_collision_probe(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    adapter = PostgresRecordAdapter(build_session_factory(engine))
    command = _no_task_from_graph(_initial_v2_graph())
    statements: list[tuple[str, str]] = []

    def capture(
        _connection,
        _cursor,
        statement,
        parameters,
        _context,
        _executemany,
    ) -> None:
        statements.append((statement, repr(parameters)))

    event.listen(engine, "before_cursor_execute", capture)
    try:
        assert (
            await adapter.save_request_understanding_v2_no_task_if_current(
                command
            )
            is ConditionalWriteResult.NOT_APPLICABLE
        )
    finally:
        event.remove(engine, "before_cursor_execute", capture)
        engine.dispose()
    assert not any(
        P0RecordCode.REQUEST_UNDERSTANDING_RECORD.value in parameters
        for _statement, parameters in statements
    )


async def test_wrong_owner_same_run_collision_never_selects_foreign_envelope(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    adapter = PostgresRecordAdapter(build_session_factory(engine))
    graph = _initial_v2_graph()
    command = _no_task_from_graph(graph)
    foreign_record = command.request_understanding_record.model_copy(
        update={"request_understanding_record_id": uuid4()}
    )
    foreign_envelope = encode_persistence_record_versioned(
        P0RecordCode.REQUEST_UNDERSTANDING_RECORD,
        "request_understanding_record.p0.v2",
        foreign_record,
    )
    foreign_secret = "FOREIGN_ENVELOPE_MUST_NOT_MATERIALIZE"
    raw_envelope = foreign_envelope.model_dump(mode="json")
    raw_envelope["foreign_secret"] = foreign_secret
    statements: list[tuple[str, str]] = []

    def capture(
        _connection,
        _cursor,
        statement,
        parameters,
        _context,
        _executemany,
    ) -> None:
        statements.append((statement, repr(parameters)))

    try:
        await _seed_v2_roots(adapter, graph)
        with adapter.session_factory.begin() as session:
            session.add(
                P0RecordModel(
                    record_id=uuid4(),
                    record_code=P0RecordCode.REQUEST_UNDERSTANDING_RECORD.value,
                    record_schema_version=(
                        "request_understanding_record.p0.v2"
                    ),
                    logical_identity=to_jsonable_python(
                        foreign_envelope.logical_identity
                    ),
                    direct_owner_customer_id=None,
                    scope_owner_customer_id="customer-B",
                    conversation_id=None,
                    run_id=graph.expected_active_run_record.run_id,
                    task_id=None,
                    request_unit_id=None,
                    lifecycle_status=None,
                    state_version=None,
                    attempt_count=None,
                    recovery_sort_at=None,
                    envelope=raw_envelope,
                )
            )
        baseline = _database_snapshot(adapter)
        event.listen(engine, "before_cursor_execute", capture)
        with pytest.raises(P0PersistenceIntegrityError) as raised:
            await adapter.save_request_understanding_v2_no_task_if_current(
                command
            )
        assert (
            raised.value.category
            is P0PersistenceIntegrityCategory.OWNER_PROJECTION_MISMATCH
        )
        error_projection = (
            f"{raised.value!s} {raised.value!r} {raised.value.args!r}"
        )
        assert foreign_secret not in error_projection
        assert _database_snapshot(adapter) == baseline
    finally:
        if event.contains(engine, "before_cursor_execute", capture):
            event.remove(engine, "before_cursor_execute", capture)
        engine.dispose()

    collision_selects = tuple(
        statement
        for statement, parameters in statements
        if P0RecordCode.REQUEST_UNDERSTANDING_RECORD.value in parameters
    )
    assert collision_selects
    for statement in collision_selects:
        selected_columns = statement.lower().split(" from ", maxsplit=1)[0]
        assert "envelope" not in selected_columns


async def test_mid_reference_failure_rolls_back_every_v2_row_and_reference(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    adapter = PostgresRecordAdapter(build_session_factory(engine))
    command = _initial_v2_graph()

    def fail_reference_insert(
        _connection,
        _cursor,
        statement,
        _parameters,
        _context,
        _executemany,
    ) -> None:
        if "insert into p0_record_references" in statement.lower():
            raise RuntimeError("injected RU-v2 reference failure")

    try:
        await _seed_v2_roots(adapter, command)
        baseline = _database_snapshot(adapter)
        event.listen(engine, "before_cursor_execute", fail_reference_insert)
        with pytest.raises(
            RuntimeError,
            match="injected RU-v2 reference failure",
        ):
            await adapter.create_initial_task_graph_v2_if_current(command)
        assert _database_snapshot(adapter) == baseline
    finally:
        if event.contains(
            engine,
            "before_cursor_execute",
            fail_reference_insert,
        ):
            event.remove(
                engine,
                "before_cursor_execute",
                fail_reference_insert,
            )
        engine.dispose()


@pytest.mark.parametrize("winner_index", (0, 1))
async def test_distinct_v2_graphs_allow_only_one_complete_closure(
    eval_postgres_namespace,
    winner_index: int,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    adapter = PostgresRecordAdapter(build_session_factory(engine))
    first = _initial_v2_graph()
    second = _second_v2_graph(first)
    commands = (first, second)
    try:
        await _seed_v2_roots(adapter, first)
        assert (
            await adapter.create_initial_task_graph_v2_if_current(
                commands[winner_index]
            )
            is ConditionalWriteResult.APPLIED
        )
        winner_snapshot = _database_snapshot(adapter)
        assert (
            await adapter.create_initial_task_graph_v2_if_current(
                commands[1 - winner_index]
            )
            is ConditionalWriteResult.PROJECTION_CONFLICT
        )
        assert _database_snapshot(adapter) == winner_snapshot
    finally:
        engine.dispose()


@pytest.mark.parametrize("first_writer", ("legacy", "v2"))
async def test_legacy_and_v2_writers_recheck_same_run_in_both_orders(
    eval_postgres_namespace,
    first_writer: str,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    adapter = PostgresRecordAdapter(build_session_factory(engine))
    v2 = _initial_v2_graph()
    legacy = _legacy_graph_for(v2)
    try:
        await _seed_v2_roots(adapter, v2)
        if first_writer == "legacy":
            first_result = await adapter.create_initial_task_graph_if_current(
                legacy
            )
            first_snapshot = _database_snapshot(adapter)
            second_result = (
                await adapter.create_initial_task_graph_v2_if_current(v2)
            )
        else:
            first_result = (
                await adapter.create_initial_task_graph_v2_if_current(v2)
            )
            first_snapshot = _database_snapshot(adapter)
            second_result = await adapter.create_initial_task_graph_if_current(
                legacy
            )
        assert first_result is ConditionalWriteResult.APPLIED
        assert second_result is ConditionalWriteResult.PROJECTION_CONFLICT
        assert _database_snapshot(adapter) == first_snapshot
    finally:
        engine.dispose()


async def test_concurrent_v2_writers_commit_at_most_one_complete_graph(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    adapter = PostgresRecordAdapter(build_session_factory(engine))
    first = _initial_v2_graph()
    second = _second_v2_graph(first)
    barrier = threading.Barrier(2)

    def write(command: CreateInitialTaskGraphV2Command):
        barrier.wait(timeout=5)
        return asyncio.run(
            adapter.create_initial_task_graph_v2_if_current(command)
        )

    try:
        await _seed_v2_roots(adapter, first)
        results = await asyncio.wait_for(
            asyncio.gather(
                asyncio.to_thread(write, first),
                asyncio.to_thread(write, second),
            ),
            timeout=15,
        )
        assert sorted(result.value for result in results) == [
            ConditionalWriteResult.APPLIED.value,
            ConditionalWriteResult.PROJECTION_CONFLICT.value,
        ]
        loaded = await adapter.load_exact_run_evidence_for_owner(
            owner_scope=first.owner_scope,
            run_id=first.expected_active_run_record.run_id,
        )
        assert loaded is not None
        assert len(loaded.accepted_task_deltas) == 1
        assert len(loaded.task_records) == 1
        assert len(loaded.request_unit_records) == 1
        assert len(loaded.input_binding_records) == 1
        assert len(loaded.conversation_task_links) == 1
        assert len(loaded.run_task_links) == 1
    finally:
        engine.dispose()
