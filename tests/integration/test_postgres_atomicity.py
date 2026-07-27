from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import func, select

from mini_agent.application.persistence import (
    P0RecordCode,
    decode_persistence_record,
    encode_persistence_record,
)
from mini_agent.application.records import (
    ApplyTaskTransitionCommand,
    ConditionalWriteResult,
    CreateRunCommand,
    DispatchToolCallCommand,
    InsertOnlyWriteResult,
    ToolDispatchFenceWriteResult,
    TransitionRunCommand,
)
from mini_agent.core.task_state import TaskStateTransition, TaskStatus
from mini_agent.core.tool_system import (
    ToolAttemptRecord,
    ToolCallStatus,
    ToolEffect,
)
from mini_agent.core.trace import AgentRunStatus
from mini_agent.infrastructure.persistence.database import build_session_factory
from mini_agent.infrastructure.persistence.models import (
    P0RecordModel,
    P0RecordReferenceModel,
)
from mini_agent.infrastructure.persistence.postgres import PostgresRecordAdapter
from tests.component.application.test_persistence_contract import _record_cases
from tests.component.application.test_record_contracts import _initial_graph


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
