from __future__ import annotations

import asyncio
import json
import sys
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import delete, event, func, select
from sqlalchemy.exc import OperationalError

from mini_agent.application.persistence import (
    P0PersistenceIntegrityCategory,
    P0PersistenceIntegrityError,
    P0RecordCode,
    encode_persistence_record,
)
from mini_agent.application.records import (
    ApplyRestartRecoveryCommand,
    ConditionalWriteResult,
    CreateRunCommand,
    CreateToolCallCommand,
    Cycle2ExactRunEvidenceClosure,
    InterruptToolCallForRecoveryCommand,
    MarkRunIncompleteForRecoveryCommand,
    MessageDirection,
    RecoveryWriteResult,
    TransitionRunCommand,
    TrustedOwnerScope,
)
from mini_agent.core.identity import CustomerContext
from mini_agent.core.tool_system import ToolCallStatus, ToolEffect
from mini_agent.core.trace import AgentRunStatus, StopReason
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
from mini_agent.infrastructure.cycle2_fixture_seed import (
    apply_cycle2_execution_setup_plan,
    resolve_cycle2_execution_setup_plan,
)
from mini_agent.infrastructure.cycle2_runtime import Cycle2DetachedExecutionSetup

_COMPONENT_APPLICATION_TESTS = (
    Path(__file__).parents[1] / "component" / "application"
)
sys.path.append(str(_COMPONENT_APPLICATION_TESTS))
from test_persistence_contract import _record_cases  # noqa: E402
from test_record_contracts import (  # noqa: E402
    _c2_retry_recovery_closure,
    _conversation,
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


def _assert_w12_recovery_message_closed_set(
    closure: Cycle2ExactRunEvidenceClosure,
) -> None:
    messages_by_id = {
        message.message_id: message for message in closure.message_records
    }
    assert len(messages_by_id) == len(closure.message_records)
    referenced_message_ids = {
        ref
        for unit in closure.request_unit_records
        for ref in unit.goal_source_refs
    }
    referenced_message_ids.update(
        ref
        for binding in closure.input_binding_records
        for ref in binding.source_refs
    )
    referenced_message_ids.update(
        record.source_message_ref
        for record in closure.candidate_selection_records
    )
    referenced_message_ids.update(
        ref
        for manifest in closure.context_manifest_records
        for ref in manifest.selected_message_refs
    )
    referenced_message_ids.update(
        trace.message_ref
        for trace in closure.trace_records
        if trace.message_ref is not None
    )
    assert set(messages_by_id) == referenced_message_ids
    assert all(
        message.conversation_id == closure.conversation_record.conversation_id
        and message.direction is MessageDirection.USER
        for message in closure.message_records
    )
    assert sum(
        message.content == "订单 O-1001 到哪了？"
        for message in closure.message_records
    ) == 1


class _RecoverySetupTarget:
    def __init__(self) -> None:
        self.setup: Cycle2DetachedExecutionSetup | None = None

    def attach_cycle2_execution_setup(
        self,
        setup: Cycle2DetachedExecutionSetup,
    ) -> None:
        self.setup = setup

    def detach_cycle2_execution_setup(
        self,
        setup: Cycle2DetachedExecutionSetup,
    ) -> None:
        if self.setup is setup:
            self.setup = None


def _w12_owner_scope() -> TrustedOwnerScope:
    return TrustedOwnerScope.from_customer_context(
        CustomerContext(
            subject_ref="subject-A",
            customer_id="customer-A",
            auth_scopes=frozenset({"orders:read"}),
            authenticated_at=datetime(2026, 7, 31, 11, 0, tzinfo=UTC),
            session_ref_hash="0" * 64,
        )
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


async def test_w12_recovery_setup_reads_exact_root_and_supporting_closure(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    factory = build_session_factory(engine)
    adapter = PostgresRecordAdapter(factory)
    plan = resolve_cycle2_execution_setup_plan(
        trusted_context_fixture_ref="session:alice",
        initial_state_fixture_refs=(
            "fx-retry-scheduled-obsolete-run-owner-a-v1",
        ),
        environment_fixture_refs=(
            "fx-search-unique-owner-a-with-foreign-decoy-v1",
            "fx-shipment-current-owner-a-v1",
        ),
        fault_ref=(
            "fault:get-shipment:restart-after-retry-finalize-state-invalidated-v1"
        ),
        authenticated_user_message="订单 O-1001 到哪了？",
    )
    target = _RecoverySetupTarget()
    try:
        setup = apply_cycle2_execution_setup_plan(
            factory,
            plan,
            attachment_target=target,
        )
        assert plan.runtime_state.recovery_subject_run_id is not None
        closure = await adapter.load_cycle2_exact_run_evidence_for_owner(
            owner_scope=_w12_owner_scope(),
            run_id=plan.runtime_state.recovery_subject_run_id,
        )
        assert closure is not None
        assert closure.run_record.run_id == plan.runtime_state.recovery_subject_run_id
        assert closure.run_record.status.value == "RUNNING"
        assert closure.terminal_result is None
        _assert_w12_recovery_message_closed_set(closure)
        root_message = next(
            message
            for message in closure.message_records
            if message.content == "订单 O-1001 到哪了？"
        )
        unreferenced = root_message.model_copy(
            update={
                "message_id": uuid4(),
                "content": "这是一条未被任何记录引用的额外消息。",
            }
        )
        for tampered_messages in (
            (),
            (*closure.message_records, unreferenced),
            (root_message, root_message),
            (
                *tuple(
                    message
                    for message in closure.message_records
                    if message.message_id != root_message.message_id
                ),
                root_message.model_copy(update={"conversation_id": uuid4()}),
            ),
            (
                *tuple(
                    message
                    for message in closure.message_records
                    if message.message_id != root_message.message_id
                ),
                root_message.model_copy(
                    update={"direction": MessageDirection.ASSISTANT}
                ),
            ),
        ):
            with pytest.raises(AssertionError):
                _assert_w12_recovery_message_closed_set(
                    closure.model_copy(
                        update={"message_records": tampered_messages}
                    )
                )
        assert len(closure.supporting_run_records) == 1
        root_tools = tuple(
            record
            for record in closure.tool_call_records
            if record.run_id == closure.run_record.run_id
        )
        supporting_tools = tuple(
            record
            for record in closure.tool_call_records
            if record.run_id != closure.run_record.run_id
        )
        assert len(root_tools) == 1
        assert root_tools[0].attempts[0].retry_decision.value == "RETRY_SCHEDULED"
        assert len(supporting_tools) == 1
        assert len(closure.gate_decision_records) == len(
            closure.tool_call_records
        )
        assert {
            record.gate_decision_id
            for record in closure.gate_decision_records
        } == {
            record.gate_decision_id
            for record in closure.tool_call_records
        }
        assert closure.candidate_selection_records == ()
        assert len(closure.auto_target_records) == 1
        auto_target = closure.auto_target_records[0]
        assert any(
            record.verified_target_ref == auto_target.verified_target_ref
            for record in closure.tool_call_records
        )
        assert all(
            edge.source_run_id != closure.run_record.run_id
            for edge in closure.observation_source_edges
        )
        serialized = closure.model_dump_json()
        assert "customer-B" not in serialized
        assert "O-9001" not in serialized

        missing_gate_id = root_tools[0].gate_decision_id
        with factory() as session:
            with session.begin():
                gate_rows = tuple(
                    session.scalars(
                        select(P0RecordModel).where(
                            P0RecordModel.record_code
                            == P0RecordCode.GATE_DECISION_RECORD.value,
                            P0RecordModel.scope_owner_customer_id
                            == closure.owner_scope.customer_id,
                        )
                    )
                )
                missing_gate_row = next(
                    row
                    for row in gate_rows
                    if row.logical_identity
                    == [["gate_decision_id", str(missing_gate_id)]]
                )
                session.execute(
                    delete(P0RecordReferenceModel).where(
                        P0RecordReferenceModel.target_record_code
                        == missing_gate_row.record_code,
                        P0RecordReferenceModel.target_logical_identity
                        == missing_gate_row.logical_identity,
                    )
                )
                session.execute(
                    delete(P0RecordModel).where(
                        P0RecordModel.record_id
                        == missing_gate_row.record_id
                    )
                )
        with pytest.raises(P0PersistenceIntegrityError) as caught:
            await adapter.load_cycle2_exact_run_evidence_for_owner(
                owner_scope=_w12_owner_scope(),
                run_id=plan.runtime_state.recovery_subject_run_id,
            )
        assert caught.value.category is (
            P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH
        )
        setup.detach()
        setup.dispose()
    finally:
        engine.dispose()


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


def _encoded_graph_and_new_tool_call():
    envelopes = []
    new_tool_call = None
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
            encode_persistence_record(
                case.code,
                record,
                external_references=case.external_references,
                logical_children=logical_children,
            )
        )
    assert new_tool_call is not None
    return tuple(envelopes), CreateToolCallCommand(created_record=new_tool_call)


def _assert_bounded_integrity_error(
    error: P0PersistenceIntegrityError,
    *,
    category: P0PersistenceIntegrityCategory,
    forbidden_values: tuple[str, ...],
) -> None:
    assert error.category is category
    assert error.__cause__ is None
    assert error.__context__ is None
    projection = f"{error!s} {error!r} {error.args!r}"
    assert all(value not in projection for value in forbidden_values)


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


async def test_recovery_bounds_malformed_normalized_reference(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    session_factory = build_session_factory(engine)
    records = PostgresRecordAdapter(session_factory)
    recovery = PostgresRestartRecoveryAdapter(session_factory)
    raw_secret = "Cookie=p0-session-reference-secret"
    try:
        with session_factory.begin() as session:
            records._persist_envelopes(
                session,
                _encoded_full_recovery_graph(effect=ToolEffect.READ),
            )

        with session_factory() as session:
            reference = session.scalar(
                select(P0RecordReferenceModel).where(
                    P0RecordReferenceModel.source_record_code
                    == P0RecordCode.AGENT_RUN_RECORD.value,
                    P0RecordReferenceModel.target_record_code
                    == P0RecordCode.CONVERSATION_RECORD.value,
                )
            )
            assert reference is not None
            reference.target_logical_identity = [
                ["conversation_id", {"raw_secret": raw_secret}]
            ]
            session.flush()
            with pytest.raises(P0PersistenceIntegrityError) as captured:
                recovery._load_closure_in_transaction(session)
            session.rollback()

        _assert_bounded_integrity_error(
            captured.value,
            category=P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH,
            forbidden_values=(
                raw_secret,
                "ValidationError",
                "target_logical_identity",
            ),
        )
    finally:
        engine.dispose()


async def test_recovery_first_rejects_late_tool_call_without_any_write(
    eval_postgres_namespace,
    monkeypatch,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    session_factory = build_session_factory(engine)
    records = PostgresRecordAdapter(session_factory)
    recovery = PostgresRestartRecoveryAdapter(session_factory)
    start_barrier = threading.Barrier(2)
    insert_waiting = threading.Event()
    recovery_committed = threading.Event()
    try:
        envelopes, create_command = _encoded_graph_and_new_tool_call()
        with session_factory.begin() as session:
            records._persist_envelopes(session, envelopes)
        closure = await recovery.load_next_restart_recovery_closure()
        assert closure is not None
        assert closure.tool_call_aggregates == ()
        recovery_command = _recovery_command(closure)

        original_row_for_identity = records._row_for_identity

        def wait_for_recovery_before_parent_lock(*args, **kwargs):
            if (
                kwargs.get("for_update")
                and kwargs.get("record_code")
                is P0RecordCode.AGENT_RUN_RECORD
            ):
                insert_waiting.set()
                assert recovery_committed.wait(timeout=5)
            return original_row_for_identity(*args, **kwargs)

        monkeypatch.setattr(
            records,
            "_row_for_identity",
            wait_for_recovery_before_parent_lock,
        )

        def insert_after_recovery():
            start_barrier.wait(timeout=5)
            try:
                return asyncio.run(records.insert_tool_call(create_command))
            except Exception as error:
                return error

        def apply_recovery_first():
            start_barrier.wait(timeout=5)
            assert insert_waiting.wait(timeout=5)
            try:
                return asyncio.run(
                    recovery.claim_and_apply_restart_recovery(
                        recovery_command
                    )
                )
            finally:
                recovery_committed.set()

        insert_result, recovery_result = await asyncio.wait_for(
            asyncio.gather(
                asyncio.to_thread(insert_after_recovery),
                asyncio.to_thread(apply_recovery_first),
            ),
            timeout=15,
        )

        assert recovery_result is RecoveryWriteResult.APPLIED
        assert type(insert_result) is P0PersistenceIntegrityError
        assert (
            insert_result.category
            is P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH
        )
        with session_factory() as session:
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(P0RecordModel)
                    .where(
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
                == 0
            )
    finally:
        recovery_committed.set()
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


async def test_legacy_restart_reader_does_not_decode_cycle2_active_run(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    session_factory = build_session_factory(engine)
    records = PostgresRecordAdapter(session_factory)
    recovery = PostgresRestartRecoveryAdapter(session_factory)
    cycle2 = _c2_retry_recovery_closure()
    conversation = _conversation(
        schema_version="conversation_record.p0.v1",
        conversation_id=cycle2.active_run_record.conversation_id,
        owner_customer_id=cycle2.owner_scope.customer_id,
        created_at=cycle2.active_run_record.started_at,
    )
    try:
        with session_factory.begin() as session:
            records._cycle2_insert(
                session,
                (
                    records._cycle2_encode(
                        P0RecordCode.CONVERSATION_RECORD,
                        conversation,
                    ),
                    records._cycle2_encode(
                        P0RecordCode.AGENT_RUN_RECORD,
                        cycle2.active_run_record,
                    ),
                ),
                owner_customer_id=cycle2.owner_scope.customer_id,
            )

        assert await recovery.load_next_restart_recovery_closure() is None
    finally:
        engine.dispose()
