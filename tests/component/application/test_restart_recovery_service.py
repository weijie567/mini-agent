import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from mini_agent.application.records import (
    ConversationRecord,
    ConversationTaskLinkRecord,
    RecoveryWriteResult,
    RestartRecoveryClosure,
    RunTaskLinkRecord,
    TaskRecoveryAggregate,
    ToolCallRecoveryAggregate,
)
from mini_agent.application.restart_recovery_service import (
    RestartRecoveryService,
)
from mini_agent.core.request_understanding import InputAuthority
from mini_agent.core.task_state import (
    RequestUnitRecord,
    TaskRecord,
    TaskStatus,
)
from mini_agent.core.tool_system import (
    ToolAttemptRecord,
    ToolCallRecord,
    ToolCallStatus,
    ToolEffect,
)
from mini_agent.core.trace import (
    AgentOutcome,
    AgentRunRecord,
    AgentRunStatus,
    StopReason,
    TraceEventType,
)

NOW = datetime(2030, 1, 1, tzinfo=UTC)


class UuidSequence:
    def __init__(self) -> None:
        self.values = [uuid4() for _ in range(32)]
        self.index = 0

    def __call__(self) -> UUID:
        value = self.values[self.index]
        self.index += 1
        return value


class RecoveryPortSpy:
    def __init__(
        self,
        closure: RestartRecoveryClosure | None,
        write_result: RecoveryWriteResult,
    ) -> None:
        self.closure = closure
        self.write_result = write_result
        self.load_calls = 0
        self.apply_commands: list[object] = []

    async def load_next_restart_recovery_closure(
        self,
    ) -> RestartRecoveryClosure | None:
        self.load_calls += 1
        return self.closure

    async def claim_and_apply_restart_recovery(
        self,
        command: object,
    ) -> RecoveryWriteResult:
        self.apply_commands.append(command)
        return self.write_result


def _conversation() -> ConversationRecord:
    return ConversationRecord(
        schema_version="conversation_record.p0.v1",
        conversation_id=uuid4(),
        owner_customer_id="customer-A",
        created_at=NOW,
    )


def _run(
    *,
    conversation_id: UUID,
    status: AgentRunStatus,
) -> AgentRunRecord:
    return AgentRunRecord(
        run_id=uuid4(),
        conversation_id=conversation_id,
        status=status,
        provider_lane="scripted",
        started_at=NOW,
    )


def _created_closure() -> RestartRecoveryClosure:
    conversation = _conversation()
    return RestartRecoveryClosure(
        closure_fence=uuid4(),
        conversation_record=conversation,
        active_run_record=_run(
            conversation_id=conversation.conversation_id,
            status=AgentRunStatus.CREATED,
        ),
        conversation_task_links=(),
        run_task_links=(),
        task_aggregates=(),
        request_unit_records=(),
        tool_call_aggregates=(),
    )


def _running_closure(
    *,
    include_tool: bool,
    effect: ToolEffect = ToolEffect.READ,
) -> RestartRecoveryClosure:
    conversation = _conversation()
    run = _run(
        conversation_id=conversation.conversation_id,
        status=AgentRunStatus.RUNNING,
    )
    task = TaskRecord(
        task_id=uuid4(),
        owner_customer_id=conversation.owner_customer_id,
        status=TaskStatus.ACTIVE,
        state_version=1,
        created_at=NOW,
        updated_at=NOW,
    )
    binding_ref = uuid4()
    request_unit = RequestUnitRecord(
        request_unit_id=uuid4(),
        task_id=task.task_id,
        goal_text="查询订单",
        goal_source_refs=(uuid4(),),
        input_binding_refs=(binding_ref,),
        status=TaskStatus.ACTIVE,
        state_version=1,
        created_at=NOW,
        updated_at=NOW,
    )
    tool_aggregates: tuple[ToolCallRecoveryAggregate, ...] = ()
    if include_tool:
        tool_call = ToolCallRecord(
            tool_call_id=uuid4(),
            run_id=run.run_id,
            task_id=task.task_id,
            request_unit_id=request_unit.request_unit_id,
            model_call_id=uuid4(),
            context_manifest_id=uuid4(),
            gate_decision_id=uuid4(),
            canonical_tool_name=(
                "get_order" if effect is ToolEffect.READ else "create_refund"
            ),
            tool_registry_version="runtime-tools-v1",
            validated_task_state_version=1,
            argument_binding_refs=(binding_ref,),
            effect=effect,
            attempt_count=1,
            status=ToolCallStatus.RUNNING,
            started_at=NOW,
        )
        tool_aggregates = (
            ToolCallRecoveryAggregate(
                tool_call_record=tool_call,
                tool_attempt_records=(
                    ToolAttemptRecord(
                        tool_call_id=tool_call.tool_call_id,
                        attempt_no=1,
                        started_at=NOW,
                    ),
                ),
            ),
        )
    return RestartRecoveryClosure(
        closure_fence=uuid4(),
        conversation_record=conversation,
        active_run_record=run,
        conversation_task_links=(
            ConversationTaskLinkRecord(
                schema_version="conversation_task_link_record.p0.v1",
                conversation_id=conversation.conversation_id,
                task_id=task.task_id,
                link_reason="CURRENT_MESSAGE_ACCEPTED_DELTA",
                linked_at=NOW,
            ),
        ),
        run_task_links=(
            RunTaskLinkRecord(
                schema_version="run_task_link_record.p0.v1",
                run_id=run.run_id,
                task_id=task.task_id,
                base_task_state_version=None,
            ),
        ),
        task_aggregates=(
            TaskRecoveryAggregate(
                task_record=task,
                task_state_transitions=(),
            ),
        ),
        request_unit_records=(request_unit,),
        tool_call_aggregates=tool_aggregates,
    )


def _recover(
    closure: RestartRecoveryClosure | None,
    write_result: RecoveryWriteResult = RecoveryWriteResult.APPLIED,
):
    port = RecoveryPortSpy(closure, write_result)
    service = RestartRecoveryService(
        restart_recovery_port=port,
        clock=lambda: NOW,
        uuid_factory=UuidSequence(),
    )
    result = asyncio.run(service.recover_pending())
    return result, port


def test_no_pending_closure_is_ready_without_apply_or_loop() -> None:
    result, port = _recover(None)

    assert result.ready is True
    assert result.closure_found is False
    assert result.write_result is None
    assert port.load_calls == 1
    assert port.apply_commands == []


def test_created_only_recovery_has_exact_single_run_stopped_event() -> None:
    closure = _created_closure()

    result, port = _recover(closure)

    assert result.ready is True
    assert result.write_result is RecoveryWriteResult.APPLIED
    assert port.load_calls == 1
    assert len(port.apply_commands) == 1
    command = port.apply_commands[0]
    assert command.expected_closure is closure
    assert command.task_transitions == ()
    assert command.tool_call_transitions == ()
    assert command.terminal_run_task_links == ()
    assert len(command.recovery_trace_events) == 1
    event = command.recovery_trace_events[0]
    assert event.event_type is TraceEventType.RUN_STOPPED
    assert event.user_outcome is AgentOutcome.BLOCKED
    assert event.stop_reason is StopReason.PROCESS_RESTART_DETECTED


def test_active_task_and_read_tool_have_exact_three_event_bijection() -> None:
    closure = _running_closure(include_tool=True)

    result, port = _recover(closure)

    assert result.ready is True
    command = port.apply_commands[0]
    assert len(command.task_transitions) == 1
    assert command.task_transitions[0].next_task_record.status is (
        TaskStatus.BLOCKED
    )
    assert command.task_transitions[0].next_task_record.state_version == 2
    assert len(command.tool_call_transitions) == 1
    assert command.tool_call_transitions[0].interrupted_record.status is (
        ToolCallStatus.INTERRUPTED
    )
    assert command.tool_call_transitions[0].interrupted_record.attempt_count == 1
    assert len(command.terminal_run_task_links) == 1
    assert (
        command.terminal_run_task_links[0].result_task_state_version == 2
    )
    assert tuple(event.event_type for event in command.recovery_trace_events) == (
        TraceEventType.RUN_STOPPED,
        TraceEventType.TASK_STATE_CHANGED,
        TraceEventType.TOOL_CALL_INTERRUPTED,
    )


def test_running_action_returns_reconciliation_without_replay_or_state_claim() -> None:
    closure = _running_closure(
        include_tool=True,
        effect=ToolEffect.ACTION,
    )

    result, port = _recover(
        closure,
        RecoveryWriteResult.RECONCILIATION_REQUIRED,
    )

    assert result.ready is False
    assert result.write_result is RecoveryWriteResult.RECONCILIATION_REQUIRED
    assert len(port.apply_commands) == 1
    command = port.apply_commands[0]
    assert command.tool_call_transitions[0].active_record.effect is (
        ToolEffect.ACTION
    )
    assert not hasattr(port, "append_trace_event")
    assert not hasattr(port, "resume")
    assert not hasattr(port, "execute_tool")


@pytest.mark.parametrize(
    "write_result",
    [
        RecoveryWriteResult.CLOSURE_CONFLICT,
        RecoveryWriteResult.NOT_APPLICABLE,
        RecoveryWriteResult.RECONCILIATION_REQUIRED,
    ],
)
def test_every_non_applied_result_is_returned_non_ready_without_retry(
    write_result: RecoveryWriteResult,
) -> None:
    result, port = _recover(
        _running_closure(include_tool=False),
        write_result,
    )

    assert result.ready is False
    assert result.write_result is write_result
    assert port.load_calls == 1
    assert len(port.apply_commands) == 1


def test_recovery_service_surface_cannot_resume_replay_or_append_trace() -> None:
    public_methods = {
        name
        for name in dir(RestartRecoveryService)
        if not name.startswith("_")
    }

    assert public_methods == {"recover_pending"}
    assert all(
        forbidden not in public_methods
        for forbidden in (
            "resume",
            "replay",
            "execute",
            "append_trace_event",
        )
    )
