from __future__ import annotations

import json
import sys
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.exc import OperationalError

from mini_agent.application.persistence import (
    P0PersistenceIntegrityError,
    P0RecordCode,
    encode_persistence_record,
)
from mini_agent.application.records import (
    ApplyRestartRecoveryCommand,
    ConditionalWriteResult,
    CreateRunCommand,
    InterruptToolCallForRecoveryCommand,
    MarkRunIncompleteForRecoveryCommand,
    RecoveryWriteResult,
    TransitionRunCommand,
)
from mini_agent.core.tool_system import ToolCallStatus, ToolEffect
from mini_agent.core.trace import AgentRunStatus, StopReason
from mini_agent.infrastructure.persistence import postgres as postgres_persistence
from mini_agent.infrastructure.persistence.database import build_session_factory
from mini_agent.infrastructure.persistence.models import P0RecordModel
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
    _created_restart_recovery_closure,
    _recovery_trace_events,
)

pytestmark = pytest.mark.anyio


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


def _recovery_command(closure):
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
    tool_transitions = tuple(
        InterruptToolCallForRecoveryCommand(
            active_record=aggregate.tool_call_record,
            interrupted_record=aggregate.tool_call_record.model_copy(
                update={
                    "status": ToolCallStatus.INTERRUPTED,
                    "finished_at": completed_at,
                    "interruption_reason": "PROCESS_RESTART_DETECTED",
                }
            ),
        )
        for aggregate in closure.tool_call_aggregates
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
        tool_call_transitions=tool_transitions,
        task_transitions=(),
        terminal_run_task_links=terminal_links,
        recovery_trace_events=_recovery_trace_events(
            run_transition=run_transition,
            task_transitions=(),
            tool_call_transitions=tool_transitions,
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


async def _seed_created_recovery_candidate(
    record_adapter: PostgresRecordAdapter,
):
    fixture = _created_restart_recovery_closure()
    await record_adapter.save_conversation(fixture.conversation_record)
    await record_adapter.insert_run(
        CreateRunCommand(created_record=fixture.active_run_record)
    )
    return fixture


def _encoded_full_recovery_graph(*, effect: ToolEffect):
    envelopes = []
    for case in _record_cases():
        record = case.record
        if case.code is P0RecordCode.AGENT_RUN_RECORD:
            record = record.model_copy(update={"status": AgentRunStatus.RUNNING})
        elif case.code is P0RecordCode.RUN_TASK_LINK_RECORD:
            record = record.model_copy(update={"result_task_state_version": None})
        elif case.code is P0RecordCode.TOOL_CALL_RECORD:
            record = record.model_copy(update={"effect": effect})
        envelopes.append(
            encode_persistence_record(
                case.code,
                record,
                external_references=case.external_references,
                logical_children=case.logical_children,
            )
        )
    return tuple(envelopes)


async def test_recovery_loader_uses_repeatable_snapshot_and_limit_two_queries(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    session_factory = build_session_factory(engine)
    records = PostgresRecordAdapter(session_factory)
    recovery = PostgresRestartRecoveryAdapter(session_factory)
    statements: list[str] = []

    def capture_statement(
        _conn,
        _cursor,
        statement,
        _parameters,
        _context,
        _executemany,
    ):
        statements.append(" ".join(statement.upper().split()))

    event.listen(engine, "before_cursor_execute", capture_statement)
    try:
        fixture = await _seed_created_recovery_candidate(records)
        loaded = await recovery.load_next_restart_recovery_closure()

        assert loaded is not None
        assert loaded.active_run_record == fixture.active_run_record
        assert any("REPEATABLE READ" in statement for statement in statements)
        bounded_selects = [
            statement
            for statement in statements
            if statement.startswith("SELECT") and "LIMIT" in statement
        ]
        assert len(bounded_selects) >= 5
        assert all("LIMIT" in statement for statement in bounded_selects)
    finally:
        event.remove(engine, "before_cursor_execute", capture_statement)
        engine.dispose()


async def test_recovery_loader_rejects_logical_child_overflow_before_decode(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    session_factory = build_session_factory(engine)
    records = PostgresRecordAdapter(session_factory)
    recovery = PostgresRestartRecoveryAdapter(session_factory)
    try:
        with session_factory.begin() as session:
            records._persist_envelopes(
                session,
                _encoded_full_recovery_graph(effect=ToolEffect.READ),
            )
            row = session.scalar(
                select(P0RecordModel).where(
                    P0RecordModel.record_code == P0RecordCode.TASK_RECORD.value
                )
            )
            assert row is not None
            corrupted = json.loads(json.dumps(row.envelope))
            children = corrupted["payload"]["logical_children"]
            children.append(children[0])
            row.envelope = corrupted

        with pytest.raises(P0PersistenceIntegrityError):
            await recovery.load_next_restart_recovery_closure()
    finally:
        engine.dispose()


async def test_recovery_apply_rereads_bounded_closure_and_fence_after_locks(
    eval_postgres_namespace,
    monkeypatch,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    session_factory = build_session_factory(engine)
    records = PostgresRecordAdapter(session_factory)
    recovery = PostgresRestartRecoveryAdapter(session_factory)
    locks_completed = False
    post_lock_bounded_families: list[str] = []
    post_lock_fence_count = 0
    try:
        await _seed_created_recovery_candidate(records)
        closure = await recovery.load_next_restart_recovery_closure()
        assert closure is not None

        original_lock_rows = recovery._lock_rows_stably
        original_bounded_rows = recovery._bounded_rows
        original_closure_fence = recovery._closure_fence

        def track_locks(session, rows):
            nonlocal locks_completed
            locked = original_lock_rows(session, rows)
            locks_completed = True
            return locked

        def track_bounded_rows(session, statement, *, family):
            if locks_completed:
                post_lock_bounded_families.append(family)
            return original_bounded_rows(
                session,
                statement,
                family=family,
            )

        def track_closure_fence(session, rows):
            nonlocal post_lock_fence_count
            if locks_completed:
                post_lock_fence_count += 1
            return original_closure_fence(session, rows)

        monkeypatch.setattr(recovery, "_lock_rows_stably", track_locks)
        monkeypatch.setattr(recovery, "_bounded_rows", track_bounded_rows)
        monkeypatch.setattr(recovery, "_closure_fence", track_closure_fence)

        assert (
            await recovery.claim_and_apply_restart_recovery(
                _recovery_command(closure)
            )
            is RecoveryWriteResult.APPLIED
        )
        assert post_lock_bounded_families == [
            "conversation",
            "conversation_task_link",
            "run_task_link",
            "tool_call",
        ]
        assert post_lock_fence_count == 2
    finally:
        engine.dispose()


async def test_applied_recovery_commits_run_and_exact_trace_together(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    session_factory = build_session_factory(engine)
    records = PostgresRecordAdapter(session_factory)
    recovery = PostgresRestartRecoveryAdapter(session_factory)
    try:
        await _seed_created_recovery_candidate(records)
        closure = await recovery.load_next_restart_recovery_closure()
        assert closure is not None
        command = _recovery_command(closure)

        assert (
            await recovery.claim_and_apply_restart_recovery(command)
            is RecoveryWriteResult.APPLIED
        )

        with session_factory() as session:
            run = session.scalar(
                select(P0RecordModel).where(
                    P0RecordModel.record_code
                    == P0RecordCode.AGENT_RUN_RECORD.value
                )
            )
            assert run is not None
            assert run.lifecycle_status == AgentRunStatus.INCOMPLETE.value
            traces = tuple(
                session.scalars(
                    select(P0RecordModel).where(
                        P0RecordModel.record_code
                        == P0RecordCode.TRACE_EVENT_RECORD.value
                    )
                )
            )
            assert len(traces) == len(command.recovery_trace_events) == 1
    finally:
        engine.dispose()


async def test_recovery_trace_failure_rolls_back_state_and_trace(
    eval_postgres_namespace,
    monkeypatch,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    session_factory = build_session_factory(engine)
    records = PostgresRecordAdapter(session_factory)
    recovery = PostgresRestartRecoveryAdapter(session_factory)
    try:
        fixture = await _seed_created_recovery_candidate(records)
        closure = await recovery.load_next_restart_recovery_closure()
        assert closure is not None

        def fail_trace(*_args, **_kwargs):
            raise RuntimeError("injected recovery trace failure")

        monkeypatch.setattr(recovery, "_persist_recovery_trace", fail_trace)
        with pytest.raises(RuntimeError, match="injected recovery trace failure"):
            await recovery.claim_and_apply_restart_recovery(
                _recovery_command(closure)
            )

        with session_factory() as session:
            run = session.scalar(
                select(P0RecordModel).where(
                    P0RecordModel.record_code
                    == P0RecordCode.AGENT_RUN_RECORD.value
                )
            )
            assert run is not None
            assert run.lifecycle_status == AgentRunStatus.CREATED.value
            assert run.envelope["payload"]["data"]["run_id"] == str(
                fixture.active_run_record.run_id
            )
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(P0RecordModel)
                    .where(
                        P0RecordModel.record_code
                        == P0RecordCode.TRACE_EVENT_RECORD.value
                    )
                )
                == 0
            )
    finally:
        engine.dispose()


async def test_closure_drift_and_serialization_failure_are_zero_write_conflicts(
    eval_postgres_namespace,
    monkeypatch,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    session_factory = build_session_factory(engine)
    records = PostgresRecordAdapter(session_factory)
    recovery = PostgresRestartRecoveryAdapter(session_factory)
    try:
        await _seed_created_recovery_candidate(records)
        closure = await recovery.load_next_restart_recovery_closure()
        assert closure is not None
        assert (
            await records.start_run_if_created(
                TransitionRunCommand(
                    expected_active_record=closure.active_run_record,
                    next_record=closure.active_run_record.model_copy(
                        update={"status": AgentRunStatus.RUNNING}
                    ),
                )
            )
            is ConditionalWriteResult.APPLIED
        )
        assert (
            await recovery.claim_and_apply_restart_recovery(
                _recovery_command(closure)
            )
            is RecoveryWriteResult.CLOSURE_CONFLICT
        )

        latest_closure = await recovery.load_next_restart_recovery_closure()
        assert latest_closure is not None
        for conflict_code in ("40001", "40P01"):
            class ConcurrencyFailure(Exception):
                pgcode = conflict_code

            def fail_concurrency(*_args, **_kwargs):
                raise OperationalError(
                    "secret customer-A Cookie p0-session-alice",
                    {},
                    ConcurrencyFailure(),
                )

            monkeypatch.setattr(
                recovery,
                "_apply_recovery_in_transaction",
                fail_concurrency,
            )
            assert (
                await recovery.claim_and_apply_restart_recovery(
                    _recovery_command(latest_closure)
                )
                is RecoveryWriteResult.CLOSURE_CONFLICT
            )
        with session_factory() as session:
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(P0RecordModel)
                    .where(
                        P0RecordModel.record_code
                        == P0RecordCode.TRACE_EVENT_RECORD.value
                    )
                )
                == 0
            )
    finally:
        engine.dispose()


async def test_recovery_discards_nonconcurrency_database_failure_context(
    eval_postgres_namespace,
    monkeypatch,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    session_factory = build_session_factory(engine)
    records = PostgresRecordAdapter(session_factory)
    recovery = PostgresRestartRecoveryAdapter(session_factory)
    forbidden_values = (
        "customer-A",
        "p0-session-alice",
        "SELECT recovery private payload",
    )

    class ConnectionFailure(Exception):
        sqlstate = "08006"

    def fail_database_operation(*_args, **_kwargs):
        raise OperationalError(
            "SELECT recovery private payload",
            {
                "customer_id": "customer-A",
                "cookie": "p0-session-alice",
            },
            ConnectionFailure("p0-session-alice"),
        )

    try:
        await _seed_created_recovery_candidate(records)
        closure = await recovery.load_next_restart_recovery_closure()
        assert closure is not None
        command = _recovery_command(closure)

        for target_name, operation in (
            (
                "_load_closure_in_transaction",
                recovery.load_next_restart_recovery_closure,
            ),
            (
                "_apply_recovery_in_transaction",
                lambda: recovery.claim_and_apply_restart_recovery(command),
            ),
        ):
            with monkeypatch.context() as context:
                context.setattr(
                    recovery,
                    target_name,
                    fail_database_operation,
                )
                with pytest.raises(Exception) as captured:
                    await operation()
            _assert_bounded_persistence_system_error(
                captured.value,
                forbidden_values=forbidden_values,
            )
    finally:
        engine.dispose()


async def test_running_action_requires_reconciliation_and_writes_nothing(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    session_factory = build_session_factory(engine)
    records = PostgresRecordAdapter(session_factory)
    recovery = PostgresRestartRecoveryAdapter(session_factory)
    try:
        with session_factory.begin() as session:
            records._persist_envelopes(
                session,
                _encoded_full_recovery_graph(effect=ToolEffect.ACTION),
            )
        closure = await recovery.load_next_restart_recovery_closure()
        assert closure is not None
        assert (
            closure.tool_call_aggregates[0].tool_call_record.effect
            is ToolEffect.ACTION
        )
        with session_factory() as session:
            before = session.scalar(
                select(func.count()).select_from(P0RecordModel)
            )

        assert (
            await recovery.claim_and_apply_restart_recovery(
                _recovery_command(closure)
            )
            is RecoveryWriteResult.RECONCILIATION_REQUIRED
        )

        with session_factory() as session:
            assert session.scalar(
                select(func.count()).select_from(P0RecordModel)
            ) == before
            run = session.scalar(
                select(P0RecordModel).where(
                    P0RecordModel.record_code
                    == P0RecordCode.AGENT_RUN_RECORD.value
                )
            )
            tool_call = session.scalar(
                select(P0RecordModel).where(
                    P0RecordModel.record_code
                    == P0RecordCode.TOOL_CALL_RECORD.value
                )
            )
            assert run is not None
            assert tool_call is not None
            assert run.lifecycle_status == AgentRunStatus.RUNNING.value
            assert tool_call.lifecycle_status == ToolCallStatus.RUNNING.value
    finally:
        engine.dispose()
