from __future__ import annotations

import asyncio
import sys
import threading
from datetime import timedelta
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import func, select

from mini_agent.application.persistence import (
    P0RecordCode,
    decode_persistence_record,
    encode_persistence_record,
)
from mini_agent.application.records import (
    ApplyRestartRecoveryCommand,
    ApplyTaskTransitionCommand,
    ConditionalWriteResult,
    CreateRunCommand,
    DispatchToolCallCommand,
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
from mini_agent.core.trace import AgentRunStatus, StopReason
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
from test_persistence_contract import _record_cases  # noqa: E402
from test_record_contracts import (  # noqa: E402
    _initial_graph,
    _recovery_trace_events,
)

pytestmark = pytest.mark.anyio


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


def _encoded_record_set_for_dispatch(*, effect: ToolEffect):
    envelopes = []
    created_tool_call = None
    for case in _record_cases():
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
            encode_persistence_record(
                case.code,
                record,
                external_references=case.external_references,
                logical_children=logical_children,
            )
        )
    assert created_tool_call is not None
    return tuple(envelopes), created_tool_call


async def _seed_initial_graph_prerequisites(
    adapter: PostgresRecordAdapter,
):
    graph = _initial_graph()
    created_run = graph.expected_active_run_record.model_copy(
        update={"status": AgentRunStatus.CREATED}
    )
    await adapter.save_conversation(graph.expected_conversation_record)
    await adapter.append_message(graph.expected_message_record)
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


async def test_initial_graph_rolls_back_every_row_and_reference_on_mid_write_failure(
    eval_postgres_namespace,
    monkeypatch,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    adapter = PostgresRecordAdapter(build_session_factory(engine))
    try:
        graph = await _seed_initial_graph_prerequisites(adapter)
        with adapter.session_factory() as session:
            baseline_records = session.scalar(
                select(func.count()).select_from(P0RecordModel)
            )
            baseline_references = session.scalar(
                select(func.count()).select_from(P0RecordReferenceModel)
            )

        original = adapter._persist_one_envelope
        calls = 0

        def fail_after_two_writes(session, envelope):
            nonlocal calls
            calls += 1
            result = original(session, envelope)
            if calls == 2:
                raise RuntimeError("injected aggregate failure")
            return result

        monkeypatch.setattr(adapter, "_persist_one_envelope", fail_after_two_writes)
        with pytest.raises(RuntimeError, match="injected aggregate failure"):
            await adapter.create_initial_task_graph_if_current(graph)

        with adapter.session_factory() as session:
            assert (
                session.scalar(select(func.count()).select_from(P0RecordModel))
                == baseline_records
            )
            assert (
                session.scalar(
                    select(func.count()).select_from(P0RecordReferenceModel)
                )
                == baseline_references
            )
    finally:
        engine.dispose()


async def test_initial_graph_and_recovery_use_one_stable_real_transaction_lock_order(
    eval_postgres_namespace,
    monkeypatch,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    session_factory = build_session_factory(engine)
    records = PostgresRecordAdapter(session_factory)
    recovery = PostgresRestartRecoveryAdapter(session_factory)
    initial_conversation_locked = threading.Event()
    recovery_run_selected = threading.Event()
    start_barrier = threading.Barrier(2)
    first_initial_lock: list[P0RecordCode] = []
    try:
        graph = await _seed_initial_graph_prerequisites(records)
        closure = await recovery.load_next_restart_recovery_closure()
        assert closure is not None
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
        recovery_command = ApplyRestartRecoveryCommand(
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

        original_row_for_identity = records._row_for_identity

        def synchronized_initial_row_lock(*args, **kwargs):
            row = original_row_for_identity(*args, **kwargs)
            if kwargs.get("for_update"):
                code = kwargs["record_code"]
                if not first_initial_lock:
                    first_initial_lock.append(code)
                if code is P0RecordCode.CONVERSATION_RECORD:
                    initial_conversation_locked.set()
                    if first_initial_lock[0] is P0RecordCode.CONVERSATION_RECORD:
                        assert recovery_run_selected.wait(timeout=5)
            return row

        original_validate = recovery._validate_physical_projection
        first_recovery_validation = True

        def synchronize_after_recovery_run_selection(*args, **kwargs):
            nonlocal first_recovery_validation
            if first_recovery_validation:
                first_recovery_validation = False
                recovery_run_selected.set()
                assert initial_conversation_locked.wait(timeout=5)
            return original_validate(*args, **kwargs)

        monkeypatch.setattr(
            records,
            "_row_for_identity",
            synchronized_initial_row_lock,
        )
        monkeypatch.setattr(
            recovery,
            "_validate_physical_projection",
            synchronize_after_recovery_run_selection,
        )

        def apply_initial_graph():
            start_barrier.wait(timeout=5)
            return asyncio.run(
                records.create_initial_task_graph_if_current(graph)
            )

        def apply_recovery():
            start_barrier.wait(timeout=5)
            return asyncio.run(
                recovery.claim_and_apply_restart_recovery(recovery_command)
            )

        initial_result, recovery_result = await asyncio.wait_for(
            asyncio.gather(
                asyncio.to_thread(apply_initial_graph),
                asyncio.to_thread(apply_recovery),
            ),
            timeout=15,
        )

        assert initial_result in {
            ConditionalWriteResult.APPLIED,
            ConditionalWriteResult.PROJECTION_CONFLICT,
            ConditionalWriteResult.NOT_APPLICABLE,
        }
        assert recovery_result in {
            RecoveryWriteResult.APPLIED,
            RecoveryWriteResult.CLOSURE_CONFLICT,
            RecoveryWriteResult.NOT_APPLICABLE,
        }
        assert first_initial_lock[0] is P0RecordCode.AGENT_RUN_RECORD
    finally:
        engine.dispose()


async def test_task_transition_uses_exact_projection_cas_and_one_atomic_child(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    adapter = PostgresRecordAdapter(build_session_factory(engine))
    try:
        graph = await _seed_initial_graph_prerequisites(adapter)
        assert (
            await adapter.create_initial_task_graph_if_current(graph)
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
