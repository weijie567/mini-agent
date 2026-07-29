from __future__ import annotations

import asyncio
import json
import sys
import threading
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic_core import to_jsonable_python
from sqlalchemy import event, select, update
from sqlalchemy.exc import SQLAlchemyError

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
    RecoveryWriteResult,
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
from mini_agent.infrastructure.persistence.recovery import (
    PostgresRestartRecoveryAdapter,
)

_COMPONENT_APPLICATION_TESTS = (
    Path(__file__).parents[1] / "component" / "application"
)
sys.path.append(str(_COMPONENT_APPLICATION_TESTS))
from test_record_contracts import (  # noqa: E402
    _initial_graph,
    _initial_v2_graph,
)

_INTEGRATION_TESTS = Path(__file__).parent
sys.path.append(str(_INTEGRATION_TESTS))
from test_postgres_atomicity import (  # noqa: E402
    _empty_graph_recovery_command,
    _no_task_finalization_for_graph,
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


def _assert_bounded_persistence_system_error(
    error: Exception,
    *,
    forbidden_values: tuple[str, ...],
) -> None:
    safe_error_type = getattr(
        postgres_persistence,
        "P0PersistenceSystemError",
        None,
    )
    assert safe_error_type is not None
    with pytest.raises(TypeError):
        safe_error_type("unsafe diagnostic")
    assert type(error) is safe_error_type
    assert error.args == ("PERSISTENCE_SYSTEM_FAILURE",)
    assert error.__cause__ is None
    assert error.__context__ is None
    projection = f"{error!s} {error!r} {error.args!r}"
    assert all(value not in projection for value in forbidden_values)


def _task_graph_family_counts(
    adapter: PostgresRecordAdapter,
) -> dict[P0RecordCode, int]:
    family = (
        P0RecordCode.REQUEST_UNDERSTANDING_RECORD,
        P0RecordCode.TASK_RECORD,
        P0RecordCode.REQUEST_UNIT_RECORD,
        P0RecordCode.INPUT_BINDING_RECORD,
        P0RecordCode.CONVERSATION_TASK_LINK_RECORD,
        P0RecordCode.RUN_TASK_LINK_RECORD,
    )
    with adapter.session_factory() as session:
        rows = tuple(
            session.scalars(
                select(P0RecordModel).where(
                    P0RecordModel.record_code.in_(
                        tuple(code.value for code in family)
                    )
                )
            )
        )
    return {
        code: sum(row.record_code == code.value for row in rows)
        for code in family
    }


async def _assert_initial_graph_closure(
    adapter: PostgresRecordAdapter,
    command: CreateInitialTaskGraphV2Command,
) -> None:
    loaded = await adapter.load_exact_run_evidence_for_owner(
        owner_scope=command.owner_scope,
        run_id=command.expected_active_run_record.run_id,
    )
    assert loaded is not None
    assert loaded.request_understanding_record == command.request_understanding.record
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
    assert loaded.run_task_links == (command.run_task_link.active_record,)


@pytest.mark.parametrize("drift", ("stale_root", "foreign_scope"))
async def test_stale_and_foreign_trusted_roots_are_zero_write(
    eval_postgres_namespace,
    drift: str,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    adapter = PostgresRecordAdapter(build_session_factory(engine))
    graph = _initial_v2_graph()
    try:
        await _seed_v2_roots(adapter, graph)
        baseline = _database_snapshot(adapter)
        if drift == "stale_root":
            stale_conversation = graph.expected_conversation_record.model_copy(
                update={
                    "created_at": (
                        graph.expected_conversation_record.created_at
                        + timedelta(microseconds=1)
                    )
                }
            )
            command = graph.model_copy(
                update={
                    "expected_conversation_record": stale_conversation,
                }
            )
            expected = ConditionalWriteResult.PROJECTION_CONFLICT
        else:
            command = graph.model_copy(
                update={
                    "owner_scope": graph.owner_scope.model_copy(
                        update={"customer_id": "customer-B"}
                    ),
                }
            )
            expected = ConditionalWriteResult.NOT_APPLICABLE

        assert (
            await adapter.create_initial_task_graph_v2_if_current(command)
            is expected
        )
        assert _database_snapshot(adapter) == baseline
    finally:
        engine.dispose()


async def test_partial_target_set_is_a_zero_write_conflict(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    adapter = PostgresRecordAdapter(build_session_factory(engine))
    command = _initial_v2_graph()
    try:
        await _seed_v2_roots(adapter, command)
        task_envelope = adapter._ru_v2_write_encode(
            P0RecordCode.TASK_RECORD,
            command.initial_task.initial_record,
        )
        with adapter.session_factory.begin() as session:
            inserted = adapter._ru_v2_write_insert_targets(
                session,
                (task_envelope,),
                owner_customer_id=command.owner_scope.customer_id,
            )
            assert len(inserted) == 1
        baseline = _database_snapshot(adapter)

        assert (
            await adapter.create_initial_task_graph_v2_if_current(command)
            is ConditionalWriteResult.PROJECTION_CONFLICT
        )
        assert _database_snapshot(adapter) == baseline
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("corruption", "returns_conflict"),
    (
        ("wrong_physical_version", True),
        ("physical_run_projection", False),
        ("payload_record_code", False),
        ("normalized_reference", False),
    ),
)
async def test_replay_rejects_corrupt_target_without_mutation(
    eval_postgres_namespace,
    corruption: str,
    returns_conflict: bool,
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
        with adapter.session_factory.begin() as session:
            ru_row = session.scalar(
                select(P0RecordModel).where(
                    P0RecordModel.record_code
                    == P0RecordCode.REQUEST_UNDERSTANDING_RECORD.value
                )
            )
            assert ru_row is not None
            if corruption == "wrong_physical_version":
                ru_row.record_schema_version = (
                    "request_understanding_record.p0.v1"
                )
            elif corruption == "physical_run_projection":
                ru_row.run_id = uuid4()
            elif corruption == "payload_record_code":
                envelope = dict(ru_row.envelope)
                envelope["record_code"] = P0RecordCode.TASK_RECORD.value
                ru_row.envelope = envelope
            else:
                reference = session.scalar(
                    select(P0RecordReferenceModel)
                    .where(
                        P0RecordReferenceModel.source_record_code
                        == P0RecordCode.REQUEST_UNDERSTANDING_RECORD.value
                    )
                    .order_by(P0RecordReferenceModel.ordinal)
                    .limit(1)
                )
                assert reference is not None
                reference.ordinal += 1000
        baseline = _database_snapshot(adapter)

        if returns_conflict:
            assert (
                await adapter.create_initial_task_graph_v2_if_current(command)
                is ConditionalWriteResult.PROJECTION_CONFLICT
            )
        else:
            with pytest.raises(P0PersistenceIntegrityError) as raised:
                await adapter.create_initial_task_graph_v2_if_current(command)
            assert raised.value.__cause__ is None
            assert raised.value.__context__ is None
        assert _database_snapshot(adapter) == baseline
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "fault_site",
    (
        "versioned_encode",
        "versioned_decode",
        "physical_projection",
        "post_insert_validation",
        "owner_closure",
        "recovery_anchor",
    ),
)
async def test_private_v2_fault_matrix_rolls_back_to_exact_baseline(
    eval_postgres_namespace,
    monkeypatch,
    fault_site: str,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    adapter = PostgresRecordAdapter(build_session_factory(engine))
    command = _initial_v2_graph()
    marker = f"injected_{fault_site}_failure"

    def fail(*_args, **_kwargs):
        raise RuntimeError(marker)

    try:
        await _seed_v2_roots(adapter, command)
        baseline = _database_snapshot(adapter)
        if fault_site == "versioned_encode":
            monkeypatch.setattr(
                postgres_persistence,
                "encode_persistence_record_versioned",
                fail,
            )
        elif fault_site == "versioned_decode":
            monkeypatch.setattr(
                postgres_persistence,
                "decode_persistence_record_versioned",
                fail,
            )
        elif fault_site == "physical_projection":
            monkeypatch.setattr(
                PostgresRecordAdapter,
                "_ru_v2_write_projection_values",
                classmethod(fail),
            )
        elif fault_site == "post_insert_validation":
            original_validate_row = (
                PostgresRecordAdapter._ru_v2_write_validate_row
            )

            def fail_target_row(
                _cls,
                session,
                row,
                **kwargs,
            ):
                if (
                    row.record_code
                    == P0RecordCode.REQUEST_UNDERSTANDING_RECORD.value
                ):
                    fail()
                return original_validate_row(
                    session,
                    row,
                    **kwargs,
                )

            monkeypatch.setattr(
                PostgresRecordAdapter,
                "_ru_v2_write_validate_row",
                classmethod(fail_target_row),
            )
        elif fault_site == "owner_closure":
            monkeypatch.setattr(
                PostgresRecordAdapter,
                "_ru_v2_write_validate_closed_rows",
                classmethod(fail),
            )
        else:
            monkeypatch.setattr(
                PostgresRecordAdapter,
                "_touch_recovery_anchor",
                staticmethod(fail),
            )

        with pytest.raises(RuntimeError, match=marker):
            await adapter.create_initial_task_graph_v2_if_current(command)
        assert _database_snapshot(adapter) == baseline
    finally:
        engine.dispose()


async def test_record_insert_database_failure_is_bounded_and_zero_write(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    adapter = PostgresRecordAdapter(build_session_factory(engine))
    command = _initial_v2_graph()
    secret = "INJECTED_RECORD_INSERT_DATABASE_SECRET"

    def fail_record_insert(
        _connection,
        _cursor,
        statement,
        _parameters,
        _context,
        _executemany,
    ) -> None:
        if "insert into p0_records" in statement.lower():
            raise SQLAlchemyError(secret)

    try:
        await _seed_v2_roots(adapter, command)
        baseline = _database_snapshot(adapter)
        event.listen(engine, "before_cursor_execute", fail_record_insert)
        with pytest.raises(Exception) as captured:
            await adapter.create_initial_task_graph_v2_if_current(command)
        _assert_bounded_persistence_system_error(
            captured.value,
            forbidden_values=(
                secret,
                command.owner_scope.customer_id,
                command.expected_message_records[0].content,
            ),
        )
        assert _database_snapshot(adapter) == baseline
    finally:
        if event.contains(engine, "before_cursor_execute", fail_record_insert):
            event.remove(engine, "before_cursor_execute", fail_record_insert)
        engine.dispose()


async def test_initial_writer_locks_exact_run_before_other_trusted_roots(
    eval_postgres_namespace,
    monkeypatch,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    adapter = PostgresRecordAdapter(build_session_factory(engine))
    command = _initial_v2_graph()
    validated_codes: list[P0RecordCode] = []
    original_validate_row = PostgresRecordAdapter._ru_v2_write_validate_row

    def record_validation_order(
        _cls,
        session,
        row,
        *,
        expected_code,
        owner_customer_id,
    ):
        validated_codes.append(expected_code)
        return original_validate_row(
            session,
            row,
            expected_code=expected_code,
            owner_customer_id=owner_customer_id,
        )

    try:
        await _seed_v2_roots(adapter, command)
        monkeypatch.setattr(
            PostgresRecordAdapter,
            "_ru_v2_write_validate_row",
            classmethod(record_validation_order),
        )
        assert (
            await adapter.create_initial_task_graph_v2_if_current(command)
            is ConditionalWriteResult.APPLIED
        )
        expected_root_order = tuple(
            sorted(
                (
                    P0RecordCode.AGENT_RUN_RECORD,
                    P0RecordCode.CONVERSATION_RECORD,
                    *(
                        P0RecordCode.MESSAGE_RECORD
                        for _message in command.expected_message_records
                    ),
                ),
                key=lambda code: code.value,
            )
        )
        assert tuple(validated_codes[: len(expected_root_order)]) == (
            expected_root_order
        )
        assert validated_codes[0] is P0RecordCode.AGENT_RUN_RECORD
    finally:
        engine.dispose()


async def test_no_task_and_initial_writers_commit_one_nonhybrid_closure(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    adapter = PostgresRecordAdapter(build_session_factory(engine))
    initial = _initial_v2_graph()
    no_task = _no_task_from_graph(initial)
    barrier = threading.Barrier(2)

    def write_no_task():
        barrier.wait(timeout=5)
        return asyncio.run(
            adapter.save_request_understanding_v2_no_task_if_current(no_task)
        )

    def write_initial():
        barrier.wait(timeout=5)
        return asyncio.run(
            adapter.create_initial_task_graph_v2_if_current(initial)
        )

    try:
        await _seed_v2_roots(adapter, initial)
        no_task_result, initial_result = await asyncio.wait_for(
            asyncio.gather(
                asyncio.to_thread(write_no_task),
                asyncio.to_thread(write_initial),
            ),
            timeout=15,
        )
        assert (
            no_task_result is ConditionalWriteResult.APPLIED
        ) is not (
            initial_result is ConditionalWriteResult.APPLIED
        )
        assert {
            no_task_result,
            initial_result,
        } == {
            ConditionalWriteResult.APPLIED,
            ConditionalWriteResult.PROJECTION_CONFLICT,
        }
        loaded = await adapter.load_exact_run_evidence_for_owner(
            owner_scope=initial.owner_scope,
            run_id=initial.expected_active_run_record.run_id,
        )
        assert loaded is not None
        if no_task_result is ConditionalWriteResult.APPLIED:
            assert loaded.request_understanding_record == (
                no_task.request_understanding_record
            )
            assert loaded.accepted_task_deltas == ()
            assert all(
                count == 0
                for code, count in _task_graph_family_counts(adapter).items()
                if code is not P0RecordCode.REQUEST_UNDERSTANDING_RECORD
            )
        else:
            await _assert_initial_graph_closure(adapter, initial)
    finally:
        engine.dispose()


@pytest.mark.parametrize("winner", ("legacy", "v2"))
async def test_legacy_and_v2_writers_serialize_both_lock_orders(
    eval_postgres_namespace,
    monkeypatch,
    winner: str,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    session_factory = build_session_factory(engine)
    legacy_adapter = PostgresRecordAdapter(session_factory)
    v2_adapter = PostgresRecordAdapter(session_factory)
    v2 = _initial_v2_graph()
    legacy = _legacy_graph_for(v2)
    winner_locked = threading.Event()
    loser_attempted = threading.Event()
    held = False

    try:
        await _seed_v2_roots(v2_adapter, v2)
        if winner == "legacy":
            original_legacy_validate = (
                legacy_adapter._validate_physical_projection
            )

            def hold_legacy_after_run_lock(session, row, **kwargs):
                nonlocal held
                if (
                    not held
                    and row.record_code
                    == P0RecordCode.AGENT_RUN_RECORD.value
                ):
                    held = True
                    winner_locked.set()
                    assert loser_attempted.wait(timeout=5)
                return original_legacy_validate(session, row, **kwargs)

            original_v2_lock_roots = (
                PostgresRecordAdapter._ru_v2_write_lock_roots
            )

            def announce_v2_attempt(_cls, *args, **kwargs):
                loser_attempted.set()
                return original_v2_lock_roots(*args, **kwargs)

            monkeypatch.setattr(
                legacy_adapter,
                "_validate_physical_projection",
                hold_legacy_after_run_lock,
            )
            monkeypatch.setattr(
                PostgresRecordAdapter,
                "_ru_v2_write_lock_roots",
                classmethod(announce_v2_attempt),
            )
        else:
            original_v2_validate = (
                PostgresRecordAdapter._ru_v2_write_validate_row
            )

            def hold_v2_after_run_lock(
                _cls,
                session,
                row,
                *,
                expected_code,
                owner_customer_id,
            ):
                nonlocal held
                if (
                    not held
                    and expected_code is P0RecordCode.AGENT_RUN_RECORD
                ):
                    held = True
                    winner_locked.set()
                    assert loser_attempted.wait(timeout=5)
                return original_v2_validate(
                    session,
                    row,
                    expected_code=expected_code,
                    owner_customer_id=owner_customer_id,
                )

            original_legacy_row = legacy_adapter._row_for_identity

            def announce_legacy_attempt(*args, **kwargs):
                if (
                    kwargs.get("record_code")
                    is P0RecordCode.AGENT_RUN_RECORD
                ):
                    loser_attempted.set()
                return original_legacy_row(*args, **kwargs)

            monkeypatch.setattr(
                PostgresRecordAdapter,
                "_ru_v2_write_validate_row",
                classmethod(hold_v2_after_run_lock),
            )
            monkeypatch.setattr(
                legacy_adapter,
                "_row_for_identity",
                announce_legacy_attempt,
            )

        def apply_legacy():
            return asyncio.run(
                legacy_adapter.create_initial_task_graph_if_current(legacy)
            )

        def apply_v2():
            return asyncio.run(
                v2_adapter.create_initial_task_graph_v2_if_current(v2)
            )

        winner_call = apply_legacy if winner == "legacy" else apply_v2
        loser_call = apply_v2 if winner == "legacy" else apply_legacy
        winner_task = asyncio.create_task(asyncio.to_thread(winner_call))
        assert await asyncio.to_thread(winner_locked.wait, 5)
        loser_task = asyncio.create_task(asyncio.to_thread(loser_call))
        winner_result, loser_result = await asyncio.wait_for(
            asyncio.gather(winner_task, loser_task),
            timeout=15,
        )

        assert winner_result is ConditionalWriteResult.APPLIED
        assert loser_result is ConditionalWriteResult.PROJECTION_CONFLICT
        counts = _task_graph_family_counts(v2_adapter)
        assert all(count == 1 for count in counts.values())
        with session_factory() as session:
            ru_row = session.scalar(
                select(P0RecordModel).where(
                    P0RecordModel.record_code
                    == P0RecordCode.REQUEST_UNDERSTANDING_RECORD.value
                )
            )
            assert ru_row is not None
            assert ru_row.record_schema_version == (
                "request_understanding_record.p0.v1"
                if winner == "legacy"
                else "request_understanding_record.p0.v2"
            )
    finally:
        loser_attempted.set()
        engine.dispose()


async def test_recovery_and_v2_initial_writer_converge_without_orphans(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    session_factory = build_session_factory(engine)
    writer = PostgresRecordAdapter(session_factory)
    recovery = PostgresRestartRecoveryAdapter(session_factory)
    command = _initial_v2_graph()
    barrier = threading.Barrier(2)
    try:
        await _seed_v2_roots(writer, command)
        closure = await recovery.load_next_restart_recovery_closure()
        assert closure is not None
        assert closure.run_task_links == ()
        recovery_command = _empty_graph_recovery_command(closure)

        def write_v2():
            barrier.wait(timeout=5)
            return asyncio.run(
                writer.create_initial_task_graph_v2_if_current(command)
            )

        def apply_recovery():
            barrier.wait(timeout=5)
            return asyncio.run(
                recovery.claim_and_apply_restart_recovery(recovery_command)
            )

        writer_result, recovery_result = await asyncio.wait_for(
            asyncio.gather(
                asyncio.to_thread(write_v2),
                asyncio.to_thread(apply_recovery),
            ),
            timeout=15,
        )
        assert (
            writer_result is ConditionalWriteResult.APPLIED
        ) is not (recovery_result is RecoveryWriteResult.APPLIED)
        if writer_result is ConditionalWriteResult.APPLIED:
            assert recovery_result in {
                RecoveryWriteResult.CLOSURE_CONFLICT,
                RecoveryWriteResult.NOT_APPLICABLE,
            }
            await _assert_initial_graph_closure(writer, command)
        else:
            assert recovery_result is RecoveryWriteResult.APPLIED
            assert writer_result in {
                ConditionalWriteResult.PROJECTION_CONFLICT,
                ConditionalWriteResult.NOT_APPLICABLE,
            }
            assert all(
                count == 0
                for count in _task_graph_family_counts(writer).values()
            )
    finally:
        engine.dispose()


async def test_finalization_and_v2_initial_writer_converge_without_orphans(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    session_factory = build_session_factory(engine)
    writer = PostgresRecordAdapter(session_factory)
    finalizer = PostgresRecordAdapter(session_factory)
    command = _initial_v2_graph()
    barrier = threading.Barrier(2)
    try:
        await _seed_v2_roots(writer, command)
        finalization = _no_task_finalization_for_graph(command)

        def write_v2():
            barrier.wait(timeout=5)
            return asyncio.run(
                writer.create_initial_task_graph_v2_if_current(command)
            )

        def finalize():
            barrier.wait(timeout=5)
            return asyncio.run(finalizer.finalize_run_if_active(finalization))

        writer_result, finalization_result = await asyncio.wait_for(
            asyncio.gather(
                asyncio.to_thread(write_v2),
                asyncio.to_thread(finalize),
            ),
            timeout=15,
        )
        assert (
            writer_result is ConditionalWriteResult.APPLIED
        ) is not (
            finalization_result is ConditionalWriteResult.APPLIED
        )
        if writer_result is ConditionalWriteResult.APPLIED:
            assert (
                finalization_result
                is ConditionalWriteResult.PROJECTION_CONFLICT
            )
            await _assert_initial_graph_closure(writer, command)
        else:
            assert (
                finalization_result is ConditionalWriteResult.APPLIED
            )
            assert writer_result in {
                ConditionalWriteResult.PROJECTION_CONFLICT,
                ConditionalWriteResult.NOT_APPLICABLE,
            }
            assert all(
                count == 0
                for count in _task_graph_family_counts(writer).values()
            )
    finally:
        engine.dispose()
