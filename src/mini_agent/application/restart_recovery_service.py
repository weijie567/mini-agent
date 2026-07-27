"""Build one exact atomic restart-recovery command without resuming work."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from mini_agent.application.ports import RestartRecoveryPort
from mini_agent.application.records import (
    ApplyRestartRecoveryCommand,
    ApplyTaskTransitionCommand,
    InterruptToolCallForRecoveryCommand,
    MarkRunIncompleteForRecoveryCommand,
    RecoveryWriteResult,
    RestartRecoveryClosure,
    RunTaskLinkRecord,
)
from mini_agent.core.common import RuntimePrivateModel
from mini_agent.core.task_state import (
    RequestUnitRecord,
    TaskRecord,
    TaskStateTransition,
    TaskStatus,
)
from mini_agent.core.tool_system import ToolCallRecord, ToolCallStatus
from mini_agent.core.trace import (
    AgentOutcome,
    AgentRunRecord,
    AgentRunStatus,
    StopReason,
    TraceEvent,
    TraceEventType,
)

_ACTIVE_TASK_STATUSES = frozenset(
    {
        TaskStatus.ACTIVE,
        TaskStatus.WAITING_USER,
        TaskStatus.PENDING_ACTION,
        TaskStatus.ACTION_IN_PROGRESS,
        TaskStatus.RECOVERING,
    }
)


class RestartRecoveryResult(RuntimePrivateModel):
    """One bounded startup recovery result for the composition root."""

    ready: bool
    closure_found: bool
    write_result: RecoveryWriteResult | None = None


def _project_run(
    record: AgentRunRecord,
    **updates: object,
) -> AgentRunRecord:
    values = {
        field_name: getattr(record, field_name)
        for field_name in AgentRunRecord.model_fields
    }
    values.update(updates)
    return AgentRunRecord(**values)


def _project_task(
    record: TaskRecord,
    **updates: object,
) -> TaskRecord:
    values = {
        field_name: getattr(record, field_name)
        for field_name in TaskRecord.model_fields
    }
    values.update(updates)
    return TaskRecord(**values)


def _project_request_unit(
    record: RequestUnitRecord,
    **updates: object,
) -> RequestUnitRecord:
    values = {
        field_name: getattr(record, field_name)
        for field_name in RequestUnitRecord.model_fields
    }
    values.update(updates)
    return RequestUnitRecord(**values)


def _project_tool_call(
    record: ToolCallRecord,
    **updates: object,
) -> ToolCallRecord:
    values = {
        field_name: getattr(record, field_name)
        for field_name in ToolCallRecord.model_fields
    }
    values.update(updates)
    return ToolCallRecord(**values)


class RestartRecoveryService:
    """Recover at most one closure through the single atomic recovery Port."""

    def __init__(
        self,
        *,
        restart_recovery_port: RestartRecoveryPort,
        clock: Callable[[], datetime],
        uuid_factory: Callable[[], UUID],
    ) -> None:
        self._restart_recovery_port = restart_recovery_port
        self._clock = clock
        self._uuid_factory = uuid_factory

    async def recover_pending(self) -> RestartRecoveryResult:
        closure = (
            await self._restart_recovery_port.load_next_restart_recovery_closure()
        )
        if closure is None:
            return RestartRecoveryResult(
                ready=True,
                closure_found=False,
            )

        recovered_at = self._clock()
        incomplete_run = _project_run(
            closure.active_run_record,
            status=AgentRunStatus.INCOMPLETE,
            completed_at=recovered_at,
            stop_reason=StopReason.PROCESS_RESTART_DETECTED,
            incomplete_reason="PROCESS_RESTART_DETECTED",
        )
        run_transition = MarkRunIncompleteForRecoveryCommand(
            expected_active_record=closure.active_run_record,
            incomplete_record=incomplete_run,
        )

        tool_transitions: list[InterruptToolCallForRecoveryCommand] = []
        for aggregate in closure.tool_call_aggregates:
            active_tool = aggregate.tool_call_record
            interrupted = _project_tool_call(
                active_tool,
                status=ToolCallStatus.INTERRUPTED,
                finished_at=recovered_at,
                interruption_reason="PROCESS_RESTART_DETECTED",
            )
            tool_transitions.append(
                InterruptToolCallForRecoveryCommand(
                    active_record=active_tool,
                    interrupted_record=interrupted,
                )
            )

        unit_by_task = {
            unit.task_id: unit for unit in closure.request_unit_records
        }
        task_transitions: list[ApplyTaskTransitionCommand] = []
        for aggregate in closure.task_aggregates:
            task = aggregate.task_record
            if task.status not in _ACTIVE_TASK_STATUSES:
                continue
            request_unit = unit_by_task[task.task_id]
            reason_ref = self._uuid_factory()
            next_task = _project_task(
                task,
                status=TaskStatus.BLOCKED,
                state_version=task.state_version + 1,
                updated_at=recovered_at,
                last_outcome_ref=reason_ref,
            )
            next_unit = _project_request_unit(
                request_unit,
                status=TaskStatus.BLOCKED,
                state_version=request_unit.state_version + 1,
                updated_at=recovered_at,
                result_refs=(*request_unit.result_refs, reason_ref),
            )
            task_transitions.append(
                ApplyTaskTransitionCommand(
                    expected_task_record=task,
                    next_task_record=next_task,
                    expected_request_unit_record=request_unit,
                    next_request_unit_record=next_unit,
                    task_state_transition=TaskStateTransition(
                        task_id=task.task_id,
                        request_unit_id=request_unit.request_unit_id,
                        from_status=task.status,
                        to_status=TaskStatus.BLOCKED,
                        base_state_version=task.state_version,
                        result_state_version=task.state_version + 1,
                        reason_ref=reason_ref,
                        changed_at=recovered_at,
                    ),
                )
            )

        transition_by_task = {
            transition.next_task_record.task_id: transition
            for transition in task_transitions
        }
        task_by_id = {
            aggregate.task_record.task_id: aggregate.task_record
            for aggregate in closure.task_aggregates
        }
        terminal_links = tuple(
            RunTaskLinkRecord(
                schema_version=link.schema_version,
                run_id=link.run_id,
                task_id=link.task_id,
                base_task_state_version=link.base_task_state_version,
                result_task_state_version=(
                    transition_by_task[link.task_id].next_task_record.state_version
                    if link.task_id in transition_by_task
                    else task_by_id[link.task_id].state_version
                ),
            )
            for link in closure.run_task_links
        )

        trace_events = (
            TraceEvent(
                trace_event_id=self._uuid_factory(),
                event_type=TraceEventType.RUN_STOPPED,
                occurred_at=recovered_at,
                run_id=closure.active_run_record.run_id,
                user_outcome=AgentOutcome.BLOCKED,
                stop_reason=StopReason.PROCESS_RESTART_DETECTED,
            ),
            *(
                TraceEvent(
                    trace_event_id=self._uuid_factory(),
                    event_type=TraceEventType.TASK_STATE_CHANGED,
                    occurred_at=transition.task_state_transition.changed_at,
                    run_id=closure.active_run_record.run_id,
                    task_id=transition.next_task_record.task_id,
                    request_unit_id=(
                        transition.next_request_unit_record.request_unit_id
                    ),
                )
                for transition in task_transitions
            ),
            *(
                TraceEvent(
                    trace_event_id=self._uuid_factory(),
                    event_type=TraceEventType.TOOL_CALL_INTERRUPTED,
                    occurred_at=transition.interrupted_record.finished_at,
                    run_id=closure.active_run_record.run_id,
                    tool_call_id=transition.interrupted_record.tool_call_id,
                    tool_call_terminal_status=ToolCallStatus.INTERRUPTED,
                )
                for transition in tool_transitions
            ),
        )
        command = ApplyRestartRecoveryCommand(
            expected_closure=closure,
            run_transition=run_transition,
            tool_call_transitions=tuple(tool_transitions),
            task_transitions=tuple(task_transitions),
            terminal_run_task_links=terminal_links,
            recovery_trace_events=trace_events,
        )
        write_result = (
            await self._restart_recovery_port.claim_and_apply_restart_recovery(
                command
            )
        )
        return RestartRecoveryResult(
            ready=write_result is RecoveryWriteResult.APPLIED,
            closure_found=True,
            write_result=write_result,
        )
