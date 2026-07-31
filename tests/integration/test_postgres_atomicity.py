from __future__ import annotations

import asyncio
import sys
import threading
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from mini_agent.application.persistence import (
    P0PersistenceIntegrityCategory,
    P0PersistenceIntegrityError,
    P0RecordCode,
    P0RecordReference,
    decode_persistence_record,
    encode_persistence_record,
)
from mini_agent.application.records import (
    ApplyRestartRecoveryCommand,
    ApplyTaskTransitionCommand,
    ConditionalWriteResult,
    CreateRunCommand,
    CreateToolCallCommand,
    DispatchToolCallCommand,
    FinalizeRunCommand,
    InsertOnlyWriteResult,
    MarkRunIncompleteForRecoveryCommand,
    RecoveryWriteResult,
    ToolDispatchFenceWriteResult,
    TransitionRunCommand,
)
from mini_agent.core.task_state import TaskStateTransition, TaskStatus
from mini_agent.core.tool_system import (
    ToolAttemptRecord,
    ToolCallStatus,
    ToolEffect,
)
from mini_agent.core.trace import (
    AgentOutcome,
    AgentRunStatus,
    StopReason,
    TraceEvent,
    TraceEventType,
)
from mini_agent.infrastructure.persistence.database import build_session_factory
from mini_agent.infrastructure.persistence.models import (
    P0RecordModel,
    P0RecordReferenceModel,
)
from mini_agent.infrastructure.persistence import postgres as postgres_persistence
from mini_agent.infrastructure.persistence.postgres import PostgresRecordAdapter
from mini_agent.infrastructure.persistence.recovery import (
    PostgresRestartRecoveryAdapter,
)

_COMPONENT_APPLICATION_TESTS = (
    Path(__file__).parents[1] / "component" / "application"
)
sys.path.append(str(_COMPONENT_APPLICATION_TESTS))
from test_record_contracts import (  # noqa: E402
    _completed_finalization,
    _conversation,
    _failed_finalization,
    _initial_v2_graph,
    _input_binding,
    _message,
    _owner_scope,
    _recovery_trace_events,
)

_INTEGRATION_TESTS = Path(__file__).parent
sys.path.append(str(_INTEGRATION_TESTS))
from test_postgres_record_adapters import (  # noqa: E402
    _encode_non_ru_record_case,
    _non_ru_record_cases,
)

pytestmark = pytest.mark.anyio


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


def _encoded_record_set_for_dispatch(*, effect: ToolEffect):
    envelopes = []
    created_tool_call = None
    for case in _non_ru_record_cases():
        record = case.record
        logical_children = case.logical_children
        if case.code is P0RecordCode.AGENT_RUN_RECORD:
            record = record.model_copy(update={"status": AgentRunStatus.RUNNING})
        elif case.code is P0RecordCode.RUN_TASK_LINK_RECORD:
            record = record.model_copy(update={"result_task_state_version": None})
        elif case.code is P0RecordCode.TOOL_CALL_RECORD:
            record = record.model_copy(
                update={
                    "effect": effect,
                    "attempt_count": 0,
                    "status": ToolCallStatus.CREATED,
                }
            )
            logical_children = ()
            created_tool_call = record
        envelopes.append(
            _encode_non_ru_record_case(
                case,
                record=record,
                logical_children=logical_children,
            )
        )
    assert created_tool_call is not None
    return tuple(envelopes), created_tool_call


def _encoded_graph_and_new_tool_call():
    envelopes = []
    new_tool_call = None
    for case in _non_ru_record_cases():
        record = case.record
        logical_children = case.logical_children
        if case.code is P0RecordCode.AGENT_RUN_RECORD:
            record = record.model_copy(update={"status": AgentRunStatus.RUNNING})
        elif case.code is P0RecordCode.RUN_TASK_LINK_RECORD:
            record = record.model_copy(update={"result_task_state_version": None})
        elif case.code is P0RecordCode.TOOL_CALL_RECORD:
            record = record.model_copy(
                update={
                    "status": ToolCallStatus.INTERRUPTED,
                    "finished_at": record.started_at + timedelta(milliseconds=1),
                    "interruption_reason": "PROCESS_RESTART_DETECTED",
                }
            )
            new_tool_call = case.record.model_copy(
                update={
                    "tool_call_id": uuid4(),
                    "attempt_count": 0,
                    "status": ToolCallStatus.CREATED,
                }
            )
        envelopes.append(
            _encode_non_ru_record_case(
                case,
                record=record,
                logical_children=logical_children,
            )
        )
    assert new_tool_call is not None
    return tuple(envelopes), CreateToolCallCommand(created_record=new_tool_call)


def _physical_finalization_command(
    *,
    with_task: bool,
    failed: bool = False,
) -> FinalizeRunCommand:
    if failed:
        command = _failed_finalization(with_task=with_task)
    else:
        command = _completed_finalization(
            stop_reason=(
                StopReason.GOAL_COMPLETED
                if with_task
                else StopReason.PROVIDER_PROTOCOL_ERROR
            ),
            outcome=(
                AgentOutcome.COMPLETED
                if with_task
                else AgentOutcome.BLOCKED
            ),
            with_task=with_task,
            task_status=TaskStatus.COMPLETED if with_task else None,
        )
    active_links = tuple(
        link.model_copy(
            update={"schema_version": "run_task_link_record.p0.v1"}
        )
        for link in command.expected_active_links
    )
    terminal_links = tuple(
        link.model_copy(
            update={"schema_version": "run_task_link_record.p0.v1"}
        )
        for link in command.terminal_links
    )
    return command.model_copy(
        update={
            "expected_active_links": active_links,
            "terminal_links": terminal_links,
        }
    )


def _finalization_prerequisite_envelopes(
    command: FinalizeRunCommand,
):
    conversation = _conversation(
        schema_version="conversation_record.p0.v1",
        conversation_id=command.expected_active_record.conversation_id,
        owner_customer_id="customer-A",
        created_at=command.expected_active_record.started_at,
    )
    envelopes = [
        encode_persistence_record(
            P0RecordCode.CONVERSATION_RECORD,
            conversation,
        ),
        encode_persistence_record(
            P0RecordCode.AGENT_RUN_RECORD,
            command.expected_active_record,
        ),
    ]
    if command.expected_active_links:
        expected_task = (
            command.task_transition.expected_task_record
            if command.task_transition is not None
            else command.result_task_records[0]
        )
        envelopes.append(
            encode_persistence_record(
                P0RecordCode.TASK_RECORD,
                expected_task,
            )
        )
        envelopes.append(
            encode_persistence_record(
                P0RecordCode.RUN_TASK_LINK_RECORD,
                command.expected_active_links[0],
            )
        )
        if command.task_transition is not None:
            expected_unit = (
                command.task_transition.expected_request_unit_record
            )
            source_message = _message(
                schema_version="message_record.p0.v1",
                message_id=expected_unit.goal_source_refs[0],
                conversation_id=conversation.conversation_id,
                received_at=conversation.created_at,
            )
            input_binding = _input_binding(
                binding_id=expected_unit.input_binding_refs[0],
                source_refs=(source_message.message_id,),
                created_at=conversation.created_at,
                updated_at=conversation.created_at,
            )
            envelopes.extend(
                (
                    encode_persistence_record(
                        P0RecordCode.MESSAGE_RECORD,
                        source_message,
                    ),
                    encode_persistence_record(
                        P0RecordCode.REQUEST_UNIT_RECORD,
                        expected_unit,
                    ),
                    encode_persistence_record(
                        P0RecordCode.INPUT_BINDING_RECORD,
                        input_binding,
                        external_references=(
                            P0RecordReference(
                                relation="request_unit_id",
                                target_record_code=(
                                    P0RecordCode.REQUEST_UNIT_RECORD
                                ),
                                target_logical_identity=(
                                    (
                                        "request_unit_id",
                                        str(
                                            expected_unit.request_unit_id
                                        ),
                                    ),
                                ),
                            ),
                        ),
                    ),
                )
            )
    return tuple(envelopes)


async def _seed_finalization_prerequisites(
    adapter: PostgresRecordAdapter,
    command: FinalizeRunCommand,
) -> None:
    with adapter.session_factory.begin() as session:
        inserted = adapter._persist_envelopes(
            session,
            _finalization_prerequisite_envelopes(command),
        )
        assert all(inserted)


def _physical_snapshot(session_factory):
    with session_factory() as session:
        record_columns = tuple(P0RecordModel.__table__.columns)
        reference_columns = tuple(P0RecordReferenceModel.__table__.columns)
        records = tuple(
            tuple(
                deepcopy(getattr(row, column.name))
                for column in record_columns
            )
            for row in session.scalars(
                select(P0RecordModel).order_by(P0RecordModel.record_id)
            )
        )
        references = tuple(
            tuple(
                deepcopy(getattr(row, column.name))
                for column in reference_columns
            )
            for row in session.scalars(
                select(P0RecordReferenceModel).order_by(
                    P0RecordReferenceModel.reference_id
                )
            )
        )
    return records, references


def _row_for_envelope(session, envelope):
    return session.scalar(
        select(P0RecordModel).where(
            P0RecordModel.record_code == envelope.record_code.value,
            P0RecordModel.logical_identity
            == [
                [
                    field_name,
                    str(value) if isinstance(value, UUID) else value,
                ]
                for field_name, value in envelope.logical_identity
            ],
        )
    )


def _terminal_envelopes(
    command: FinalizeRunCommand,
):
    assert command.task_transition is not None
    return {
        "task": encode_persistence_record(
            P0RecordCode.TASK_RECORD,
            command.task_transition.next_task_record,
            logical_children=(command.task_transition.task_state_transition,),
        ),
        "request_unit": encode_persistence_record(
            P0RecordCode.REQUEST_UNIT_RECORD,
            command.task_transition.next_request_unit_record,
        ),
        "run": encode_persistence_record(
            P0RecordCode.AGENT_RUN_RECORD,
            command.terminal_record,
        ),
        "link": encode_persistence_record(
            P0RecordCode.RUN_TASK_LINK_RECORD,
            command.terminal_links[0],
        ),
        "message": encode_persistence_record(
            P0RecordCode.MESSAGE_RECORD,
            command.assistant_message,
        ),
        "task_trace": encode_persistence_record(
            P0RecordCode.TRACE_EVENT_RECORD,
            command.terminal_trace_events[0],
        ),
        "run_trace": encode_persistence_record(
            P0RecordCode.TRACE_EVENT_RECORD,
            command.terminal_trace_events[1],
        ),
    }


def _assert_persisted_finalization(
    adapter: PostgresRecordAdapter,
    command: FinalizeRunCommand,
) -> None:
    with adapter.session_factory() as session:
        terminal_run_envelope = encode_persistence_record(
            P0RecordCode.AGENT_RUN_RECORD,
            command.terminal_record,
        )
        run_row = _row_for_envelope(session, terminal_run_envelope)
        assert run_row is not None
        assert (
            adapter._decode_row(session, run_row).source_record
            == command.terminal_record
        )

        for expected_link in command.terminal_links:
            envelope = encode_persistence_record(
                P0RecordCode.RUN_TASK_LINK_RECORD,
                expected_link,
            )
            row = _row_for_envelope(session, envelope)
            assert row is not None
            assert (
                adapter._decode_row(session, row).source_record
                == expected_link
            )

        if command.task_transition is not None:
            task_envelope = encode_persistence_record(
                P0RecordCode.TASK_RECORD,
                command.task_transition.next_task_record,
                logical_children=(
                    command.task_transition.task_state_transition,
                ),
            )
            task_row = _row_for_envelope(session, task_envelope)
            assert task_row is not None
            decoded_task = adapter._decode_row(session, task_row)
            assert (
                decoded_task.source_record
                == command.task_transition.next_task_record
            )
            assert decoded_task.logical_children == (
                command.task_transition.task_state_transition,
            )
            unit_envelope = encode_persistence_record(
                P0RecordCode.REQUEST_UNIT_RECORD,
                command.task_transition.next_request_unit_record,
            )
            unit_row = _row_for_envelope(session, unit_envelope)
            assert unit_row is not None
            assert (
                adapter._decode_row(session, unit_row).source_record
                == command.task_transition.next_request_unit_record
            )
        elif command.result_task_records:
            task_envelope = encode_persistence_record(
                P0RecordCode.TASK_RECORD,
                command.result_task_records[0],
            )
            task_row = _row_for_envelope(session, task_envelope)
            assert task_row is not None
            decoded_task = adapter._decode_row(session, task_row)
            assert decoded_task.source_record == command.result_task_records[0]
            assert decoded_task.logical_children == ()

        if command.assistant_message is not None:
            message_envelope = encode_persistence_record(
                P0RecordCode.MESSAGE_RECORD,
                command.assistant_message,
            )
            message_row = _row_for_envelope(session, message_envelope)
            assert message_row is not None
            assert (
                adapter._decode_row(session, message_row).source_record
                == command.assistant_message
            )

        expected_trace_by_id = {
            event.trace_event_id: event
            for event in command.terminal_trace_events
        }
        actual_trace_by_id = {}
        for row in session.scalars(
            select(P0RecordModel).where(
                P0RecordModel.record_code
                == P0RecordCode.TRACE_EVENT_RECORD.value,
                P0RecordModel.run_id == command.terminal_record.run_id,
            )
        ):
            event = adapter._decode_row(session, row).source_record
            actual_trace_by_id[event.trace_event_id] = event
        assert actual_trace_by_id == expected_trace_by_id


async def _seed_initial_graph_prerequisites(
    adapter: PostgresRecordAdapter,
):
    graph = _initial_v2_graph()
    created_run = graph.expected_active_run_record.model_copy(
        update={"status": AgentRunStatus.CREATED}
    )
    await adapter.save_conversation(graph.expected_conversation_record)
    for message in graph.expected_message_records:
        await adapter.append_message(message)
    assert (
        await adapter.insert_run(CreateRunCommand(created_record=created_run))
        is InsertOnlyWriteResult.INSERTED
    )
    assert (
        await adapter.start_run_if_created(
            TransitionRunCommand(
                expected_active_record=created_run,
                next_record=graph.expected_active_run_record,
            )
        )
        is ConditionalWriteResult.APPLIED
    )
    return graph


def _no_task_finalization_for_graph(graph) -> FinalizeRunCommand:
    template = _physical_finalization_command(with_task=False)
    assert template.terminal_record.completed_at is not None
    assert template.terminal_result is not None
    assert template.assistant_message is not None
    active_run = graph.expected_active_run_record
    completed_at = template.terminal_record.completed_at
    terminal_result = template.terminal_result.model_copy(
        update={"run_id": active_run.run_id}
    )
    return FinalizeRunCommand(
        expected_active_record=active_run,
        terminal_record=active_run.model_copy(
            update={
                "status": AgentRunStatus.COMPLETED,
                "completed_at": completed_at,
                "stop_reason": StopReason.PROVIDER_PROTOCOL_ERROR,
            }
        ),
        expected_active_links=(),
        terminal_links=(),
        result_task_records=(),
        task_transition=None,
        terminal_result=terminal_result,
        assistant_message=template.assistant_message.model_copy(
            update={
                "conversation_id": active_run.conversation_id,
                "content": terminal_result.message,
                "received_at": completed_at,
            }
        ),
        terminal_trace_events=tuple(
            event.model_copy(
                update={
                    "run_id": active_run.run_id,
                    "occurred_at": completed_at,
                }
            )
            for event in template.terminal_trace_events
        ),
    )


def _same_timestamp_terminal_trace_command() -> FinalizeRunCommand:
    command = _physical_finalization_command(with_task=True)
    transition = command.task_transition
    assert transition is not None
    assert command.terminal_record.completed_at is not None
    occurred_at = command.terminal_record.completed_at
    next_task = transition.next_task_record.model_copy(
        update={"updated_at": occurred_at}
    )
    next_unit = transition.next_request_unit_record.model_copy(
        update={"updated_at": occurred_at}
    )
    next_transition = ApplyTaskTransitionCommand(
        expected_task_record=transition.expected_task_record,
        next_task_record=next_task,
        expected_request_unit_record=(
            transition.expected_request_unit_record
        ),
        next_request_unit_record=next_unit,
        task_state_transition=transition.task_state_transition.model_copy(
            update={"changed_at": occurred_at}
        ),
    )
    task_changed, run_stopped = command.terminal_trace_events
    return command.model_copy(
        update={
            "result_task_records": (next_task,),
            "task_transition": next_transition,
            "terminal_trace_events": (
                task_changed.model_copy(update={"occurred_at": occurred_at}),
                run_stopped,
            ),
        }
    )


async def _seed_tool_call_support_for_finalization(
    adapter: PostgresRecordAdapter,
    command: FinalizeRunCommand,
) -> CreateToolCallCommand:
    transition = command.task_transition
    assert transition is not None
    record_by_code = {
        case.code: case.record
        for case in _non_ru_record_cases()
    }
    toolset_artifact = record_by_code[
        P0RecordCode.MODEL_VISIBLE_TOOLSET_ARTIFACT
    ]
    manifest_template = record_by_code[
        P0RecordCode.CONTEXT_MANIFEST_RECORD
    ]
    gate_template = record_by_code[P0RecordCode.GATE_DECISION_RECORD]
    tool_call_template = record_by_code[P0RecordCode.TOOL_CALL_RECORD]
    task_state_ref = manifest_template.task_state_ref_and_version
    assert task_state_ref is not None
    model_call_id = uuid4()
    context_manifest_id = uuid4()
    gate_decision_id = uuid4()
    binding_ref = (
        transition.expected_request_unit_record.input_binding_refs[0]
    )
    context_manifest = manifest_template.model_copy(
        update={
            "context_manifest_id": context_manifest_id,
            "run_id": command.expected_active_record.run_id,
            "model_call_id": model_call_id,
            "selected_message_refs": (
                transition.expected_request_unit_record.goal_source_refs[0],
            ),
            "task_state_ref_and_version": task_state_ref.model_copy(
                update={
                    "task_id": transition.expected_task_record.task_id,
                    "state_version": (
                        transition.expected_task_record.state_version
                    ),
                }
            ),
            "observation_refs_and_versions": (),
            "assembled_at": command.expected_active_record.started_at,
        }
    )
    gate_decision = gate_template.model_copy(
        update={
            "gate_decision_id": gate_decision_id,
            "model_call_id": model_call_id,
            "context_manifest_id": context_manifest_id,
            "argument_binding_refs": (binding_ref,),
            "proposed_base_task_state_version": (
                transition.expected_task_record.state_version
            ),
            "validated_task_state_version": (
                transition.expected_task_record.state_version
            ),
            "decided_at": command.expected_active_record.started_at,
        }
    )
    created_tool_call = tool_call_template.model_copy(
        update={
            "tool_call_id": uuid4(),
            "run_id": command.expected_active_record.run_id,
            "task_id": transition.expected_task_record.task_id,
            "request_unit_id": (
                transition.expected_request_unit_record.request_unit_id
            ),
            "model_call_id": model_call_id,
            "context_manifest_id": context_manifest_id,
            "gate_decision_id": gate_decision_id,
            "validated_task_state_version": (
                transition.expected_task_record.state_version
            ),
            "argument_binding_refs": (binding_ref,),
            "attempt_count": 0,
            "status": ToolCallStatus.CREATED,
            "started_at": command.expected_active_record.started_at,
            "finished_at": None,
            "failure_code": None,
            "timeout_phase": None,
            "interruption_reason": None,
            "result_ref": None,
        }
    )
    await adapter.put_toolset_artifact(toolset_artifact)
    await adapter.save_context_manifest(context_manifest)
    await adapter.save_gate_decision(gate_decision)
    return CreateToolCallCommand(created_record=created_tool_call)


def _dispatch_tool_call_command(
    created_record,
) -> DispatchToolCallCommand:
    running_record = created_record.model_copy(
        update={
            "attempt_count": 1,
            "status": ToolCallStatus.RUNNING,
        }
    )
    return DispatchToolCallCommand(
        expected_created_record=created_record,
        running_record=running_record,
        started_attempt=ToolAttemptRecord(
            tool_call_id=created_record.tool_call_id,
            attempt_no=1,
            started_at=created_record.started_at,
        ),
    )


def _empty_graph_recovery_command(closure) -> ApplyRestartRecoveryCommand:
    completed_at = closure.active_run_record.started_at + timedelta(seconds=1)
    run_transition = MarkRunIncompleteForRecoveryCommand(
        expected_active_record=closure.active_run_record,
        incomplete_record=closure.active_run_record.model_copy(
            update={
                "status": AgentRunStatus.INCOMPLETE,
                "completed_at": completed_at,
                "stop_reason": StopReason.PROCESS_RESTART_DETECTED,
            }
        ),
    )
    return ApplyRestartRecoveryCommand(
        expected_closure=closure,
        run_transition=run_transition,
        tool_call_transitions=(),
        task_transitions=(),
        terminal_run_task_links=(),
        recovery_trace_events=_recovery_trace_events(
            run_transition=run_transition,
            task_transitions=(),
            tool_call_transitions=(),
        ),
    )


def _linked_graph_recovery_command(closure) -> ApplyRestartRecoveryCommand:
    completed_at = closure.active_run_record.started_at + timedelta(seconds=1)
    run_transition = MarkRunIncompleteForRecoveryCommand(
        expected_active_record=closure.active_run_record,
        incomplete_record=closure.active_run_record.model_copy(
            update={
                "status": AgentRunStatus.INCOMPLETE,
                "completed_at": completed_at,
                "stop_reason": StopReason.PROCESS_RESTART_DETECTED,
            }
        ),
    )
    terminal_links = tuple(
        link.model_copy(
            update={
                "result_task_state_version": next(
                    aggregate.task_record.state_version
                    for aggregate in closure.task_aggregates
                    if aggregate.task_record.task_id == link.task_id
                )
            }
        )
        for link in closure.run_task_links
    )
    return ApplyRestartRecoveryCommand(
        expected_closure=closure,
        run_transition=run_transition,
        tool_call_transitions=(),
        task_transitions=(),
        terminal_run_task_links=terminal_links,
        recovery_trace_events=_recovery_trace_events(
            run_transition=run_transition,
            task_transitions=(),
            tool_call_transitions=(),
        ),
    )


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


async def test_owner_scoped_read_discards_database_failure_context(
    eval_postgres_namespace,
    monkeypatch,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    adapter = PostgresRecordAdapter(build_session_factory(engine))
    graph = _initial_v2_graph()
    forbidden_values = (
        "customer-A",
        "p0-session-alice",
        "SELECT private payload",
    )

    class ConnectionFailure(Exception):
        sqlstate = "08006"

    def fail_owner_scoped_read(*_args, **_kwargs):
        raise OperationalError(
            "SELECT private payload WHERE customer_id=:customer_id",
            {
                "customer_id": "customer-A",
                "cookie": "p0-session-alice",
            },
            ConnectionFailure("p0-session-alice"),
        )

    try:
        monkeypatch.setattr(
            adapter,
            "_owner_scoped_row",
            fail_owner_scoped_read,
        )
        with pytest.raises(Exception) as captured:
            await adapter.load_run_for_owner(
                owner_scope=graph.owner_scope,
                run_id=graph.expected_active_run_record.run_id,
            )

        _assert_bounded_persistence_system_error(
            captured.value,
            forbidden_values=forbidden_values,
        )
    finally:
        engine.dispose()


async def test_tool_call_insert_first_forces_recovery_conflict_without_orphan(
    eval_postgres_namespace,
    monkeypatch,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    session_factory = build_session_factory(engine)
    records = PostgresRecordAdapter(session_factory)
    recovery = PostgresRestartRecoveryAdapter(session_factory)
    start_barrier = threading.Barrier(2)
    tool_write_staged = threading.Event()
    recovery_started = threading.Event()
    try:
        envelopes, create_command = _encoded_graph_and_new_tool_call()
        with session_factory.begin() as session:
            records._persist_envelopes(session, envelopes)
        closure = await recovery.load_next_restart_recovery_closure()
        assert closure is not None
        assert closure.tool_call_aggregates == ()
        recovery_command = _linked_graph_recovery_command(closure)

        original_touch_recovery_anchor = records._touch_recovery_anchor

        def stage_tool_before_commit(session, run_row):
            original_touch_recovery_anchor(session, run_row)
            tool_write_staged.set()
            assert recovery_started.wait(timeout=5)

        monkeypatch.setattr(
            records,
            "_touch_recovery_anchor",
            stage_tool_before_commit,
        )

        def insert_first():
            start_barrier.wait(timeout=5)
            return asyncio.run(records.insert_tool_call(create_command))

        def recover_after_insert_is_staged():
            start_barrier.wait(timeout=5)
            assert tool_write_staged.wait(timeout=5)
            recovery_started.set()
            return asyncio.run(
                recovery.claim_and_apply_restart_recovery(recovery_command)
            )

        insert_result, recovery_result = await asyncio.wait_for(
            asyncio.gather(
                asyncio.to_thread(insert_first),
                asyncio.to_thread(recover_after_insert_is_staged),
            ),
            timeout=15,
        )

        assert insert_result is InsertOnlyWriteResult.INSERTED
        assert recovery_result is RecoveryWriteResult.CLOSURE_CONFLICT
        with session_factory() as session:
            run_row = session.scalar(
                select(P0RecordModel).where(
                    P0RecordModel.record_code
                    == P0RecordCode.AGENT_RUN_RECORD.value,
                    P0RecordModel.run_id
                    == create_command.created_record.run_id,
                )
            )
            tool_row = session.scalar(
                select(P0RecordModel).where(
                        P0RecordModel.record_code
                        == P0RecordCode.TOOL_CALL_RECORD.value,
                        P0RecordModel.logical_identity
                        == [
                            [
                                "tool_call_id",
                                str(
                                    create_command.created_record.tool_call_id
                                ),
                            ]
                        ],
                    )
                )
            assert run_row is not None
            assert tool_row is not None
            assert run_row.lifecycle_status == AgentRunStatus.RUNNING.value
            assert tool_row.lifecycle_status == ToolCallStatus.CREATED.value
    finally:
        recovery_started.set()
        engine.dispose()


async def test_task_transition_uses_exact_projection_cas_and_one_atomic_child(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    adapter = PostgresRecordAdapter(build_session_factory(engine))
    try:
        graph = await _seed_initial_graph_prerequisites(adapter)
        assert (
            await adapter.create_initial_task_graph_v2_if_current(graph)
            is ConditionalWriteResult.APPLIED
        )
        expected_task = graph.initial_task.initial_record
        expected_unit = graph.initial_request_unit.initial_record
        changed_at = expected_task.updated_at + timedelta(milliseconds=1)
        next_task = expected_task.model_copy(
            update={
                "status": TaskStatus.WAITING_USER,
                "state_version": 2,
                "updated_at": changed_at,
            }
        )
        next_unit = expected_unit.model_copy(
            update={
                "status": TaskStatus.WAITING_USER,
                "state_version": 2,
                "updated_at": changed_at,
            }
        )
        command = ApplyTaskTransitionCommand(
            expected_task_record=expected_task,
            next_task_record=next_task,
            expected_request_unit_record=expected_unit,
            next_request_unit_record=next_unit,
            task_state_transition=TaskStateTransition(
                task_id=expected_task.task_id,
                request_unit_id=expected_unit.request_unit_id,
                from_status=TaskStatus.ACTIVE,
                to_status=TaskStatus.WAITING_USER,
                base_state_version=1,
                result_state_version=2,
                reason_ref=graph.request_understanding.record.run_id,
                changed_at=changed_at,
            ),
        )

        assert (
            await adapter.apply_task_transition_if_current(command)
            is ConditionalWriteResult.APPLIED
        )
        assert (
            await adapter.apply_task_transition_if_current(command)
            is ConditionalWriteResult.PROJECTION_CONFLICT
        )

        with adapter.session_factory() as session:
            row = session.scalar(
                select(P0RecordModel).where(
                    P0RecordModel.record_code == P0RecordCode.TASK_RECORD.value,
                    P0RecordModel.task_id == expected_task.task_id,
                )
            )
            assert row is not None
            decoded = decode_persistence_record(
                row.envelope,
                expected_record_code=P0RecordCode.TASK_RECORD,
                correlation_ref=UUID(int=820),
            )
            assert decoded.source_record == next_task
            assert decoded.logical_children == (command.task_state_transition,)
    finally:
        engine.dispose()


async def test_read_dispatch_fence_is_durable_and_replay_conflicts(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    adapter = PostgresRecordAdapter(build_session_factory(engine))
    try:
        envelopes, created = _encoded_record_set_for_dispatch(effect=ToolEffect.READ)
        with adapter.session_factory.begin() as session:
            adapter._persist_envelopes(session, envelopes)
        running = created.model_copy(
            update={"status": ToolCallStatus.RUNNING, "attempt_count": 1}
        )
        attempt = ToolAttemptRecord(
            tool_call_id=created.tool_call_id,
            attempt_no=1,
            started_at=created.started_at,
        )
        command = DispatchToolCallCommand(
            expected_created_record=created,
            running_record=running,
            started_attempt=attempt,
        )

        assert (
            await adapter.start_tool_call_if_created(command)
            is ToolDispatchFenceWriteResult.APPLIED
        )
        assert (
            await adapter.start_tool_call_if_created(command)
            is ToolDispatchFenceWriteResult.STATUS_CONFLICT
        )

        with adapter.session_factory() as session:
            row = session.scalar(
                select(P0RecordModel).where(
                    P0RecordModel.record_code
                    == P0RecordCode.TOOL_CALL_RECORD.value,
                    P0RecordModel.run_id == running.run_id,
                )
            )
            assert row is not None
            assert row.lifecycle_status == ToolCallStatus.RUNNING.value
            assert row.attempt_count == 1
            decoded = decode_persistence_record(
                row.envelope,
                expected_record_code=P0RecordCode.TOOL_CALL_RECORD,
                correlation_ref=UUID(int=821),
            )
            assert decoded.source_record == running
            assert decoded.logical_children == (attempt,)
    finally:
        engine.dispose()


async def test_action_dispatch_requires_ledger_and_writes_nothing(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    adapter = PostgresRecordAdapter(build_session_factory(engine))
    try:
        envelopes, created = _encoded_record_set_for_dispatch(effect=ToolEffect.ACTION)
        with adapter.session_factory.begin() as session:
            adapter._persist_envelopes(session, envelopes)
        running = created.model_copy(
            update={"status": ToolCallStatus.RUNNING, "attempt_count": 1}
        )
        command = DispatchToolCallCommand(
            expected_created_record=created,
            running_record=running,
            started_attempt=ToolAttemptRecord(
                tool_call_id=created.tool_call_id,
                attempt_no=1,
                started_at=created.started_at,
            ),
        )
        with adapter.session_factory() as session:
            before_records = session.scalar(
                select(func.count()).select_from(P0RecordModel)
            )
            before_references = session.scalar(
                select(func.count()).select_from(P0RecordReferenceModel)
            )

        assert (
            await adapter.start_tool_call_if_created(command)
            is ToolDispatchFenceWriteResult.ACTION_LEDGER_REQUIRED
        )

        with adapter.session_factory() as session:
            assert (
                session.scalar(select(func.count()).select_from(P0RecordModel))
                == before_records
            )
            assert (
                session.scalar(
                    select(func.count()).select_from(P0RecordReferenceModel)
                )
                == before_references
            )
            row = session.scalar(
                select(P0RecordModel).where(
                    P0RecordModel.record_code
                    == P0RecordCode.TOOL_CALL_RECORD.value
                )
            )
            assert row is not None
            assert row.lifecycle_status == ToolCallStatus.CREATED.value
            assert row.attempt_count == 0
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("with_task", "failed"),
    (
        (True, False),
        (False, False),
        (True, True),
        (False, True),
    ),
)
async def test_finalize_run_persists_exact_complete_terminal_projection(
    eval_postgres_namespace,
    with_task: bool,
    failed: bool,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    adapter = PostgresRecordAdapter(build_session_factory(engine))
    try:
        command = _physical_finalization_command(
            with_task=with_task,
            failed=failed,
        )
        await _seed_finalization_prerequisites(adapter, command)

        assert (
            await adapter.finalize_run_if_active(command)
            is ConditionalWriteResult.APPLIED
        )
        _assert_persisted_finalization(adapter, command)
    finally:
        engine.dispose()


@pytest.mark.parametrize("same_timestamp", (True, False))
async def test_finalize_run_lists_same_timestamp_terminal_traces_semantically(
    eval_postgres_namespace,
    same_timestamp: bool,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    adapter = PostgresRecordAdapter(build_session_factory(engine))
    try:
        command = (
            _same_timestamp_terminal_trace_command()
            if same_timestamp
            else _physical_finalization_command(with_task=True)
        )
        await _seed_finalization_prerequisites(adapter, command)
        assert (
            await adapter.finalize_run_if_active(command)
            is ConditionalWriteResult.APPLIED
        )

        low_record_id = UUID(int=1)
        high_record_id = UUID(int=2)
        with adapter.session_factory.begin() as session:
            trace_rows = tuple(
                session.scalars(
                    select(P0RecordModel).where(
                        P0RecordModel.record_code
                        == P0RecordCode.TRACE_EVENT_RECORD.value,
                        P0RecordModel.run_id
                        == command.terminal_record.run_id,
                    )
                )
            )
            trace_row_by_type = {
                adapter._decode_row(session, row).source_record.event_type: row
                for row in trace_rows
            }
            task_changed_row = trace_row_by_type[
                TraceEventType.TASK_STATE_CHANGED
            ]
            run_stopped_row = trace_row_by_type[TraceEventType.RUN_STOPPED]
            task_changed_row.stored_at = (
                command.terminal_record.completed_at
            )
            run_stopped_row.stored_at = command.terminal_record.completed_at
            task_changed_row.record_id = high_record_id
            run_stopped_row.record_id = low_record_id

        with adapter.session_factory() as session:
            physical_order = tuple(
                adapter._decode_row(session, row).source_record.event_type
                for row in session.scalars(
                    select(P0RecordModel)
                    .where(
                        P0RecordModel.record_code
                        == P0RecordCode.TRACE_EVENT_RECORD.value,
                        P0RecordModel.run_id
                        == command.terminal_record.run_id,
                    )
                    .order_by(
                        P0RecordModel.stored_at,
                        P0RecordModel.record_id,
                    )
                )
            )
        assert physical_order == (
            TraceEventType.RUN_STOPPED,
            TraceEventType.TASK_STATE_CHANGED,
        )
        assert (
            await adapter.list_trace_events_for_owner(
                owner_scope=_owner_scope(),
                run_id=command.terminal_record.run_id,
            )
            == command.terminal_trace_events
        )
    finally:
        engine.dispose()


async def test_trace_listing_preserves_history_and_recovery_physical_order(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    adapter = PostgresRecordAdapter(build_session_factory(engine))
    try:
        command = _physical_finalization_command(with_task=True)
        await _seed_finalization_prerequisites(adapter, command)
        task_changed_template = command.terminal_trace_events[0]
        history_occurred_at = command.expected_active_record.started_at
        response_rendered = TraceEvent(
            trace_event_id=uuid4(),
            event_type=TraceEventType.RESPONSE_RENDERED,
            occurred_at=history_occurred_at,
            run_id=command.expected_active_record.run_id,
        )
        history_task_changed = task_changed_template.model_copy(
            update={
                "trace_event_id": uuid4(),
                "occurred_at": history_occurred_at,
            }
        )
        recovery_occurred_at = history_occurred_at + timedelta(seconds=1)
        recovery_run_stopped = TraceEvent(
            trace_event_id=uuid4(),
            event_type=TraceEventType.RUN_STOPPED,
            occurred_at=recovery_occurred_at,
            run_id=command.expected_active_record.run_id,
            user_outcome=AgentOutcome.BLOCKED,
            stop_reason=StopReason.PROCESS_RESTART_DETECTED,
        )
        recovery_task_changed = task_changed_template.model_copy(
            update={
                "trace_event_id": uuid4(),
                "occurred_at": recovery_occurred_at,
            }
        )
        expected_history = (
            response_rendered,
            history_task_changed,
            recovery_run_stopped,
            recovery_task_changed,
        )
        for event in expected_history:
            await adapter.append_trace_event(event)

        stored_at = command.expected_active_record.started_at
        with adapter.session_factory.begin() as session:
            trace_rows = tuple(
                session.scalars(
                    select(P0RecordModel).where(
                        P0RecordModel.record_code
                        == P0RecordCode.TRACE_EVENT_RECORD.value,
                        P0RecordModel.run_id
                        == command.expected_active_record.run_id,
                    )
                )
            )
            trace_row_by_id = {
                adapter._decode_row(
                    session,
                    row,
                ).source_record.trace_event_id: row
                for row in trace_rows
            }
            trace_row_by_id[response_rendered.trace_event_id].stored_at = (
                stored_at
            )
            trace_row_by_id[history_task_changed.trace_event_id].stored_at = (
                stored_at + timedelta(microseconds=1)
            )
            recovery_run_row = trace_row_by_id[
                recovery_run_stopped.trace_event_id
            ]
            recovery_task_row = trace_row_by_id[
                recovery_task_changed.trace_event_id
            ]
            recovery_run_row.stored_at = (
                stored_at + timedelta(microseconds=2)
            )
            recovery_task_row.stored_at = (
                stored_at + timedelta(microseconds=2)
            )
            recovery_run_row.record_id = UUID(int=3)
            recovery_task_row.record_id = UUID(int=4)

        physical_history = await adapter._list_for_owner(
            owner_scope=_owner_scope(),
            record_code=P0RecordCode.TRACE_EVENT_RECORD,
            filters=(
                P0RecordModel.run_id
                == command.expected_active_record.run_id,
            ),
            expected_type=TraceEvent,
        )
        assert physical_history == expected_history
        assert (
            await adapter.list_trace_events_for_owner(
                owner_scope=_owner_scope(),
                run_id=command.expected_active_record.run_id,
            )
            == expected_history
        )
    finally:
        engine.dispose()


async def test_finalize_run_rechecks_active_tool_calls_after_run_lock(
    eval_postgres_namespace,
    monkeypatch,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    session_factory = build_session_factory(engine)
    finalizer = PostgresRecordAdapter(session_factory)
    tool_call_writer = PostgresRecordAdapter(session_factory)
    prelock_closure_materialized = threading.Event()
    tool_call_committed = threading.Event()
    pause_guard = threading.Lock()
    paused = False
    try:
        command = _physical_finalization_command(with_task=True)
        await _seed_finalization_prerequisites(tool_call_writer, command)
        create_command = await _seed_tool_call_support_for_finalization(
            tool_call_writer,
            command,
        )
        original_lock_rows_stably = finalizer._lock_rows_stably

        def pause_before_first_lock(session, rows):
            nonlocal paused
            materialized = tuple(rows)
            with pause_guard:
                should_pause = not paused
                paused = True
            if should_pause:
                assert tuple(
                    row.record_code for row in materialized
                ) == (P0RecordCode.AGENT_RUN_RECORD.value,)
                prelock_closure_materialized.set()
                assert tool_call_committed.wait(timeout=5)
            return original_lock_rows_stably(session, materialized)

        monkeypatch.setattr(
            finalizer,
            "_lock_rows_stably",
            pause_before_first_lock,
        )

        def finalize_in_thread():
            return asyncio.run(finalizer.finalize_run_if_active(command))

        finalize_task = asyncio.create_task(
            asyncio.to_thread(finalize_in_thread)
        )
        assert await asyncio.to_thread(
            prelock_closure_materialized.wait,
            5,
        )
        try:
            insert_result = await tool_call_writer.insert_tool_call(
                create_command
            )
            after_insert = _physical_snapshot(session_factory)
        finally:
            tool_call_committed.set()
        finalize_result = await asyncio.wait_for(finalize_task, timeout=15)

        assert insert_result is InsertOnlyWriteResult.INSERTED
        assert finalize_result is ConditionalWriteResult.PROJECTION_CONFLICT
        assert _physical_snapshot(session_factory) == after_insert
        assert (
            await finalizer.load_run_for_owner(
                owner_scope=_owner_scope(),
                run_id=command.expected_active_record.run_id,
            )
            == command.expected_active_record
        )
        assert (
            await finalizer.load_tool_call_for_owner(
                owner_scope=_owner_scope(),
                tool_call_id=create_command.created_record.tool_call_id,
            )
            == create_command.created_record
        )
        assert (
            await finalizer.list_trace_events_for_owner(
                owner_scope=_owner_scope(),
                run_id=command.expected_active_record.run_id,
            )
            == ()
        )
        assert command.assistant_message is not None
        with session_factory() as session:
            assert (
                _row_for_envelope(
                    session,
                    encode_persistence_record(
                        P0RecordCode.MESSAGE_RECORD,
                        command.assistant_message,
                    ),
                )
                is None
            )
    finally:
        tool_call_committed.set()
        engine.dispose()


@pytest.mark.parametrize(
    "active_status",
    (ToolCallStatus.CREATED, ToolCallStatus.RUNNING),
)
async def test_finalize_run_rejects_existing_active_tool_call_without_writes(
    eval_postgres_namespace,
    active_status: ToolCallStatus,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    adapter = PostgresRecordAdapter(build_session_factory(engine))
    try:
        command = _physical_finalization_command(with_task=True)
        await _seed_finalization_prerequisites(adapter, command)
        create_command = await _seed_tool_call_support_for_finalization(
            adapter,
            command,
        )
        assert (
            await adapter.insert_tool_call(create_command)
            is InsertOnlyWriteResult.INSERTED
        )
        if active_status is ToolCallStatus.RUNNING:
            assert (
                await adapter.start_tool_call_if_created(
                    _dispatch_tool_call_command(
                        create_command.created_record
                    )
                )
                is ToolDispatchFenceWriteResult.APPLIED
            )

        before = _physical_snapshot(adapter.session_factory)
        assert (
            await adapter.finalize_run_if_active(command)
            is ConditionalWriteResult.PROJECTION_CONFLICT
        )
        assert _physical_snapshot(adapter.session_factory) == before
    finally:
        engine.dispose()


async def test_finalize_wins_before_tool_call_insert_leaves_no_orphan(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    adapter = PostgresRecordAdapter(build_session_factory(engine))
    try:
        command = _physical_finalization_command(with_task=True)
        await _seed_finalization_prerequisites(adapter, command)
        create_command = await _seed_tool_call_support_for_finalization(
            adapter,
            command,
        )
        assert (
            await adapter.finalize_run_if_active(command)
            is ConditionalWriteResult.APPLIED
        )
        before = _physical_snapshot(adapter.session_factory)

        with pytest.raises(P0PersistenceIntegrityError) as captured:
            await adapter.insert_tool_call(create_command)

        assert (
            captured.value.category
            is P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH
        )
        assert _physical_snapshot(adapter.session_factory) == before
        assert (
            await adapter.load_tool_call_for_owner(
                owner_scope=_owner_scope(),
                tool_call_id=create_command.created_record.tool_call_id,
            )
            is None
        )
    finally:
        engine.dispose()


async def test_terminal_tool_call_does_not_block_run_finalization(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    adapter = PostgresRecordAdapter(build_session_factory(engine))
    try:
        command = _physical_finalization_command(with_task=True)
        await _seed_finalization_prerequisites(adapter, command)
        create_command = await _seed_tool_call_support_for_finalization(
            adapter,
            command,
        )
        terminal_tool_call = create_command.created_record.model_copy(
            update={
                "status": ToolCallStatus.INTERRUPTED,
                "finished_at": (
                    create_command.created_record.started_at
                    + timedelta(microseconds=1)
                ),
                "interruption_reason": "PROCESS_RESTART_DETECTED",
            }
        )
        with adapter.session_factory.begin() as session:
            assert adapter._persist_envelopes(
                session,
                (
                    encode_persistence_record(
                        P0RecordCode.TOOL_CALL_RECORD,
                        terminal_tool_call,
                    ),
                ),
            ) == (True,)

        assert (
            await adapter.finalize_run_if_active(command)
            is ConditionalWriteResult.APPLIED
        )
        _assert_persisted_finalization(adapter, command)
        assert (
            await adapter.load_tool_call_for_owner(
                owner_scope=_owner_scope(),
                tool_call_id=terminal_tool_call.tool_call_id,
            )
            == terminal_tool_call
        )
    finally:
        engine.dispose()


_TERMINAL_RECORD_FAULTS = (
    ("task", None),
    ("request_unit", None),
    ("run", None),
    ("link", None),
    ("message", None),
    ("task_trace", None),
    ("run_trace", None),
)
_TERMINAL_REFERENCE_FAULTS = (
    ("task", 0),
    ("request_unit", 0),
    ("request_unit", 1),
    ("request_unit", 2),
    ("run", 0),
    ("link", 0),
    ("link", 1),
    ("message", 0),
    ("task_trace", 0),
    ("task_trace", 1),
    ("task_trace", 2),
    ("run_trace", 0),
)


@pytest.mark.parametrize(
    ("target_label", "reference_ordinal"),
    (*_TERMINAL_RECORD_FAULTS, *_TERMINAL_REFERENCE_FAULTS),
)
async def test_finalize_run_rolls_back_every_terminal_child_and_reference_fault(
    eval_postgres_namespace,
    monkeypatch,
    target_label: str,
    reference_ordinal: int | None,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    adapter = PostgresRecordAdapter(build_session_factory(engine))
    triggered = False
    try:
        command = _physical_finalization_command(with_task=True)
        await _seed_finalization_prerequisites(adapter, command)
        before = _physical_snapshot(adapter.session_factory)
        target = _terminal_envelopes(command)[target_label]
        target_key = (
            target.record_code,
            target.logical_identity,
        )

        if reference_ordinal is not None:
            original_reference_model = adapter._reference_model

            def fail_selected_reference(
                envelope,
                *,
                ordinal,
                reference,
            ):
                nonlocal triggered
                model = original_reference_model(
                    envelope,
                    ordinal=ordinal,
                    reference=reference,
                )
                if (
                    (envelope.record_code, envelope.logical_identity)
                    == target_key
                    and ordinal == reference_ordinal
                ):
                    triggered = True
                    raise RuntimeError(
                        f"injected {target_label} reference fault"
                    )
                return model

            monkeypatch.setattr(
                adapter,
                "_reference_model",
                fail_selected_reference,
            )
            with pytest.raises(
                RuntimeError,
                match=f"injected {target_label} reference fault",
            ):
                await adapter.finalize_run_if_active(command)
        elif target_label in {"task", "request_unit", "run", "link"}:
            original_replace = adapter._replace_row_envelope

            def fail_after_selected_replacement(
                session,
                row,
                *,
                expected_record,
                expected_children,
                next_envelope,
            ):
                nonlocal triggered
                result = original_replace(
                    session,
                    row,
                    expected_record=expected_record,
                    expected_children=expected_children,
                    next_envelope=next_envelope,
                )
                if (
                    (
                        next_envelope.record_code,
                        next_envelope.logical_identity,
                    )
                    == target_key
                ):
                    triggered = True
                    assert result
                    return False
                return result

            monkeypatch.setattr(
                adapter,
                "_replace_row_envelope",
                fail_after_selected_replacement,
            )
            assert (
                await adapter.finalize_run_if_active(command)
                is ConditionalWriteResult.PROJECTION_CONFLICT
            )
        else:
            original_persist = adapter._persist_envelopes

            def fail_after_selected_insert(session, envelopes):
                nonlocal triggered
                materialized = tuple(envelopes)
                results = list(original_persist(session, materialized))
                for index, envelope in enumerate(materialized):
                    if (
                        envelope.record_code,
                        envelope.logical_identity,
                    ) == target_key:
                        triggered = True
                        assert results[index]
                        results[index] = False
                return tuple(results)

            monkeypatch.setattr(
                adapter,
                "_persist_envelopes",
                fail_after_selected_insert,
            )
            assert (
                await adapter.finalize_run_if_active(command)
                is ConditionalWriteResult.PROJECTION_CONFLICT
            )

        assert triggered
        assert _physical_snapshot(adapter.session_factory) == before
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("stale_kind", "expected_result"),
    (
        ("missing_run", ConditionalWriteResult.NOT_APPLICABLE),
        ("run", ConditionalWriteResult.PROJECTION_CONFLICT),
        ("link", ConditionalWriteResult.PROJECTION_CONFLICT),
        ("task", ConditionalWriteResult.PROJECTION_CONFLICT),
        ("request_unit", ConditionalWriteResult.PROJECTION_CONFLICT),
        ("message_exists", ConditionalWriteResult.PROJECTION_CONFLICT),
        ("task_trace_exists", ConditionalWriteResult.PROJECTION_CONFLICT),
        ("run_trace_exists", ConditionalWriteResult.PROJECTION_CONFLICT),
    ),
)
async def test_finalize_run_non_applied_paths_write_nothing(
    eval_postgres_namespace,
    monkeypatch,
    stale_kind: str,
    expected_result: ConditionalWriteResult,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    adapter = PostgresRecordAdapter(build_session_factory(engine))
    replacement_attempted = False
    try:
        command = _physical_finalization_command(
            with_task=stale_kind != "missing_run"
        )
        if stale_kind == "missing_run":
            prerequisites = _finalization_prerequisite_envelopes(command)
            with adapter.session_factory.begin() as session:
                assert adapter._persist_envelopes(
                    session,
                    prerequisites[:1],
                ) == (True,)
        else:
            await _seed_finalization_prerequisites(adapter, command)

        if stale_kind in {"run", "link", "task", "request_unit"}:
            if stale_kind == "run":
                current_record = command.expected_active_record
                next_record = current_record.model_copy(
                    update={"provider_lane": "stale-provider-lane"}
                )
                code = P0RecordCode.AGENT_RUN_RECORD
                current_children = ()
                next_children = ()
            elif stale_kind == "link":
                current_record = command.expected_active_links[0]
                next_record = current_record.model_copy(
                    update={"base_task_state_version": None}
                )
                code = P0RecordCode.RUN_TASK_LINK_RECORD
                current_children = ()
                next_children = ()
            elif stale_kind == "task":
                assert command.task_transition is not None
                current_record = command.task_transition.expected_task_record
                next_record = current_record.model_copy(
                    update={
                        "status": TaskStatus.WAITING_USER,
                        "state_version": 2,
                        "updated_at": (
                            current_record.updated_at
                            + timedelta(milliseconds=1)
                        ),
                    }
                )
                code = P0RecordCode.TASK_RECORD
                current_children = ()
                next_children = ()
            else:
                assert command.task_transition is not None
                current_record = (
                    command.task_transition.expected_request_unit_record
                )
                next_record = current_record.model_copy(
                    update={
                        "status": TaskStatus.WAITING_USER,
                        "state_version": 2,
                        "updated_at": (
                            current_record.updated_at
                            + timedelta(milliseconds=1)
                        ),
                    }
                )
                code = P0RecordCode.REQUEST_UNIT_RECORD
                current_children = ()
                next_children = ()
            current_envelope = encode_persistence_record(
                code,
                current_record,
                logical_children=current_children,
            )
            next_envelope = encode_persistence_record(
                code,
                next_record,
                logical_children=next_children,
            )
            with adapter.session_factory.begin() as session:
                row = _row_for_envelope(session, current_envelope)
                assert row is not None
                assert adapter._replace_row_envelope(
                    session,
                    row,
                    expected_record=current_record,
                    expected_children=current_children,
                    next_envelope=next_envelope,
                )
        elif stale_kind.endswith("_exists"):
            terminal = _terminal_envelopes(command)
            key = stale_kind.removesuffix("_exists")
            with adapter.session_factory.begin() as session:
                assert adapter._persist_envelopes(
                    session,
                    (terminal[key],),
                ) == (True,)

            original_replace = adapter._replace_row_envelope

            def track_replacement(*args, **kwargs):
                nonlocal replacement_attempted
                replacement_attempted = True
                return original_replace(*args, **kwargs)

            monkeypatch.setattr(
                adapter,
                "_replace_row_envelope",
                track_replacement,
            )

        before = _physical_snapshot(adapter.session_factory)
        assert (
            await adapter.finalize_run_if_active(command)
            is expected_result
        )
        assert _physical_snapshot(adapter.session_factory) == before
        if stale_kind.endswith("_exists"):
            assert not replacement_attempted
    finally:
        engine.dispose()


async def test_finalize_run_concurrent_winner_and_loser_commit_one_aggregate(
    eval_postgres_namespace,
    monkeypatch,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    adapter = PostgresRecordAdapter(build_session_factory(engine))
    start_barrier = threading.Barrier(2)
    local_state = threading.local()
    try:
        command = _physical_finalization_command(with_task=True)
        await _seed_finalization_prerequisites(adapter, command)
        original_row_for_identity = adapter._row_for_identity

        def synchronize_first_lookup(*args, **kwargs):
            if not getattr(local_state, "first_lookup_seen", False):
                local_state.first_lookup_seen = True
                start_barrier.wait(timeout=5)
            return original_row_for_identity(*args, **kwargs)

        monkeypatch.setattr(
            adapter,
            "_row_for_identity",
            synchronize_first_lookup,
        )

        def finalize_in_thread():
            return asyncio.run(adapter.finalize_run_if_active(command))

        results = await asyncio.wait_for(
            asyncio.gather(
                asyncio.to_thread(finalize_in_thread),
                asyncio.to_thread(finalize_in_thread),
            ),
            timeout=15,
        )

        assert results.count(ConditionalWriteResult.APPLIED) == 1
        assert (
            results.count(ConditionalWriteResult.PROJECTION_CONFLICT) == 1
        )
        _assert_persisted_finalization(adapter, command)
    finally:
        engine.dispose()
