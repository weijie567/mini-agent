"""Build one exact atomic restart-recovery command without resuming work."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from mini_agent.application.ports import Cycle2RuntimeRecordPort, RestartRecoveryPort
from mini_agent.application.records import (
    AppendRecoveredToolAttemptV2Command,
    AppendToolAttemptV2Command,
    ApplyRestartRecoveryCommand,
    ApplyTaskTransitionCommand,
    Cycle2DispatchFenceWriteResult,
    Cycle2ReadDispatchGrant,
    Cycle2WriteResult,
    FinalizeBudgetExhaustedToolRecoveryV2Command,
    FinalizeCreatedToolRecoveryV2Command,
    FinalizeStateInvalidatedToolRecoveryV2Command,
    FinalizeSupersededRunV2Command,
    FinalizeUnfinishedToolRecoveryV2Command,
    InterruptToolCallForRecoveryCommand,
    MarkRunIncompleteForRecoveryCommand,
    RecoveryWriteResult,
    RestartRecoveryClosure,
    RunTaskLinkRecord,
    RunTaskLinkRecordV2,
    ToolRetryRecoveryDecisionRecordV2,
    ToolRetryRecoveryReadClosureV2,
    TrustedOwnerScope,
)
from mini_agent.core.common import RuntimePrivateModel
from mini_agent.core.task_state import (
    RequestUnitRecord,
    TaskRecord,
    TaskStateTransition,
    TaskStatus,
)
from mini_agent.core.tool_system import (
    ToolAttemptRecordV2,
    ToolCallRecord,
    ToolCallRecordV2,
    ToolCallStatus,
    ToolRecoveryDecision,
    ToolRecoveryDisposition,
    project_cycle2_budget_exhausted_recovery_terminal,
)
from mini_agent.core.trace import (
    AgentOutcome,
    AgentRunRecord,
    AgentRunStatus,
    AgentRunStatusV2,
    StopReason,
    StopReasonV2,
    TraceEvent,
    TraceEventV2,
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


Cycle2ToolRecoveryResult = tuple[
    ToolCallRecordV2,
    ToolAttemptRecordV2 | None,
    Cycle2ReadDispatchGrant | Cycle2WriteResult | None,
]


def _project_tool_call_v2(
    record: ToolCallRecordV2,
    **updates: object,
) -> ToolCallRecordV2:
    values = record.model_dump(mode="python")
    values.update(updates)
    return ToolCallRecordV2.model_validate(values, strict=True)


def _grant_exactly_authorizes_attempt(
    grant: object,
    *,
    tool_call_id: UUID,
    attempt: ToolAttemptRecordV2,
) -> bool:
    return (
        type(grant) is Cycle2ReadDispatchGrant
        and grant.write_result is Cycle2DispatchFenceWriteResult.APPLIED
        and grant.tool_call_id == tool_call_id
        and grant.attempt_no == attempt.attempt_no
        and grant.trusted_fenced_at is not None
        and grant.trusted_fenced_at >= attempt.started_at
        and grant.effective_timeout_ms is not None
    )


class Cycle2ToolRestartRecoveryService:
    """Apply exactly one reviewed v2 recovery command and never infer evidence."""

    def __init__(
        self,
        *,
        runtime_record_port: Cycle2RuntimeRecordPort,
        uuid_factory: Callable[[], UUID],
    ) -> None:
        self._runtime_record_port = runtime_record_port
        self._uuid_factory = uuid_factory

    async def recover_tool_call(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        tool_call_id: UUID,
        replacement_run_id: UUID | None = None,
    ) -> Cycle2ToolRecoveryResult:
        if (
            type(owner_scope) is not TrustedOwnerScope
            or type(tool_call_id) is not UUID
        ):
            raise TypeError("exact owner scope and ToolCall identity are required")
        if replacement_run_id is not None and type(replacement_run_id) is not UUID:
            raise TypeError("replacement_run_id must be an exact UUID or None")
        closure = await (
            self._runtime_record_port.load_tool_retry_recovery_closure_for_owner(
                owner_scope=owner_scope,
                tool_call_id=tool_call_id,
            )
        )
        if (
            type(closure) is not ToolRetryRecoveryReadClosureV2
            or closure.owner_scope != owner_scope
            or closure.tool_call_record.tool_call_id != tool_call_id
        ):
            raise ReadToolRecoveryError("recovery closure unavailable")
        decision = closure.derive_recovery_decision()
        source = closure.tool_call_record

        if decision.decision is ToolRecoveryDecision.INTERRUPT_WITHOUT_ATTEMPT:
            terminal = _project_tool_call_v2(
                source,
                status=ToolCallStatus.INTERRUPTED,
                finished_at=decision.decided_at,
                interruption_reason="PROCESS_RESTART_DETECTED",
            )
            result = await (
                self._runtime_record_port.finalize_created_tool_recovery_if_current(
                    FinalizeCreatedToolRecoveryV2Command(
                        loaded_closure=closure,
                        terminal_tool_call_record=terminal,
                    )
                )
            )
            return (
                terminal if result is Cycle2WriteResult.APPLIED else source,
                None,
                result,
            )

        if decision.decision in {
            ToolRecoveryDecision.INTERRUPT_UNFINISHED_ATTEMPT,
            ToolRecoveryDecision.APPEND_SECOND_ATTEMPT,
            ToolRecoveryDecision.TERMINATE_RETRY_PATH,
        }:
            child = ToolRetryRecoveryDecisionRecordV2(
                recovery_decision_id=self._uuid_factory(),
                tool_call_id=source.tool_call_id,
                last_attempt_no=decision.last_attempt_no,
                decision=decision.decision,
                stable_reason_code=decision.stable_reason_code,
                candidate_next_attempt_no=decision.candidate_next_attempt_no,
                decided_at=decision.decided_at,
            )
        else:
            return source, None, None

        if decision.decision is ToolRecoveryDecision.INTERRUPT_UNFINISHED_ATTEMPT:
            terminal = _project_tool_call_v2(
                source,
                status=ToolCallStatus.INTERRUPTED,
                finished_at=decision.decided_at,
                interruption_reason="PROCESS_RESTART_DETECTED",
                recovery_disposition=(
                    ToolRecoveryDisposition.UNFINISHED_ATTEMPT_INTERRUPTED
                ),
                recovery_decision_ref=child.recovery_decision_id,
            )
            reason_ref = self._uuid_factory()
            next_task = _project_task(
                closure.current_task_record,
                status=TaskStatus.BLOCKED,
                state_version=closure.current_task_record.state_version + 1,
                updated_at=decision.decided_at,
                last_outcome_ref=reason_ref,
            )
            next_unit = _project_request_unit(
                closure.current_request_unit_record,
                status=TaskStatus.BLOCKED,
                state_version=(
                    closure.current_request_unit_record.state_version + 1
                ),
                updated_at=decision.decided_at,
                result_refs=(
                    *closure.current_request_unit_record.result_refs,
                    reason_ref,
                ),
            )
            transition = ApplyTaskTransitionCommand(
                expected_task_record=closure.current_task_record,
                next_task_record=next_task,
                expected_request_unit_record=closure.current_request_unit_record,
                next_request_unit_record=next_unit,
                task_state_transition=TaskStateTransition(
                    task_id=closure.current_task_record.task_id,
                    request_unit_id=(
                        closure.current_request_unit_record.request_unit_id
                    ),
                    from_status=closure.current_task_record.status,
                    to_status=TaskStatus.BLOCKED,
                    base_state_version=(
                        closure.current_task_record.state_version
                    ),
                    result_state_version=next_task.state_version,
                    reason_ref=reason_ref,
                    changed_at=decision.decided_at,
                ),
            )
            incomplete_run = type(closure.active_run_record).model_validate(
                {
                    **closure.active_run_record.model_dump(mode="python"),
                    "status": AgentRunStatusV2.INCOMPLETE,
                    "completed_at": decision.decided_at,
                    "stop_reason": StopReasonV2.PROCESS_RESTART_DETECTED,
                    "incomplete_reason": "PROCESS_RESTART_DETECTED",
                },
                strict=True,
            )
            terminal_link = RunTaskLinkRecordV2.model_validate(
                {
                    **closure.active_run_task_link_record.model_dump(
                        mode="python"
                    ),
                    "result_task_state_version": next_task.state_version,
                },
                strict=True,
            )
            traces = (
                TraceEventV2(
                    trace_event_id=self._uuid_factory(),
                    event_type=TraceEventType.RUN_STOPPED,
                    occurred_at=decision.decided_at,
                    run_id=closure.active_run_record.run_id,
                    task_id=closure.current_task_record.task_id,
                    request_unit_id=(
                        closure.current_request_unit_record.request_unit_id
                    ),
                    user_outcome=AgentOutcome.BLOCKED,
                    stop_reason=StopReasonV2.PROCESS_RESTART_DETECTED,
                ),
                TraceEventV2(
                    trace_event_id=self._uuid_factory(),
                    event_type=TraceEventType.TASK_STATE_CHANGED,
                    occurred_at=decision.decided_at,
                    run_id=closure.active_run_record.run_id,
                    task_id=closure.current_task_record.task_id,
                    request_unit_id=(
                        closure.current_request_unit_record.request_unit_id
                    ),
                ),
                TraceEventV2(
                    trace_event_id=self._uuid_factory(),
                    event_type=TraceEventType.TOOL_CALL_INTERRUPTED,
                    occurred_at=decision.decided_at,
                    run_id=closure.active_run_record.run_id,
                    task_id=closure.current_task_record.task_id,
                    request_unit_id=(
                        closure.current_request_unit_record.request_unit_id
                    ),
                    tool_call_id=closure.tool_call_record.tool_call_id,
                    tool_call_terminal_status=ToolCallStatus.INTERRUPTED,
                ),
            )
            result = await (
                self._runtime_record_port.finalize_unfinished_tool_recovery_if_current(
                    FinalizeUnfinishedToolRecoveryV2Command(
                        loaded_closure=closure,
                        recovery_decision_record=child,
                        terminal_tool_call_record=terminal,
                        task_transition=transition,
                        terminal_run_record=incomplete_run,
                        terminal_run_task_link_record=terminal_link,
                        recovery_trace_records=traces,
                    )
                )
            )
            return (
                terminal if result is Cycle2WriteResult.APPLIED else source,
                None,
                result,
            )

        if decision.decision is ToolRecoveryDecision.APPEND_SECOND_ATTEMPT:
            attempt = ToolAttemptRecordV2(
                tool_call_id=source.tool_call_id,
                attempt_no=2,
                started_at=decision.decided_at,
            )
            next_record = _project_tool_call_v2(
                source,
                attempts=(*source.attempts, attempt),
                attempt_count=2,
            )
            append = AppendToolAttemptV2Command(
                owner_scope=closure.owner_scope,
                expected_record=source,
                next_running_record=next_record,
                started_attempt=attempt,
            )
            grant = await (
                self._runtime_record_port.append_recovered_tool_attempt_if_current(
                    AppendRecoveredToolAttemptV2Command(
                        loaded_closure=closure,
                        recovery_decision_record=child,
                        attempt_append_command=append,
                    )
                )
            )
            authorized = _grant_exactly_authorizes_attempt(
                grant,
                tool_call_id=source.tool_call_id,
                attempt=attempt,
            )
            return (
                next_record if authorized else source,
                attempt if authorized else None,
                grant,
            )

        if decision.stable_reason_code == "RUN_BUDGET_EXHAUSTED":
            terminal = project_cycle2_budget_exhausted_recovery_terminal(
                tool_call=source,
                recovery_decision=decision,
                recovery_decision_ref=child.recovery_decision_id,
            )
            result = await (
                self._runtime_record_port.finalize_budget_exhausted_tool_recovery_if_current(
                    FinalizeBudgetExhaustedToolRecoveryV2Command(
                        loaded_closure=closure,
                        recovery_decision_record=child,
                        terminal_tool_call_record=terminal,
                    )
                )
            )
            return (
                terminal if result is Cycle2WriteResult.APPLIED else source,
                None,
                result,
            )

        if (
            decision.stable_reason_code != "STATE_OR_BINDING_INVALIDATED"
            or replacement_run_id is None
        ):
            return source, None, None
        oa10_closure = await (
            self._runtime_record_port.load_superseded_run_closure_for_owner(
                owner_scope=owner_scope,
                obsolete_run_id=source.run_id,
                replacement_run_id=replacement_run_id,
                request_unit_id=source.request_unit_id,
            )
        )
        if oa10_closure is None:
            return source, None, None
        terminal_tool = _project_tool_call_v2(
            source,
            status=ToolCallStatus.INTERRUPTED,
            finished_at=decision.decided_at,
            interruption_reason="STATE_OR_BINDING_INVALIDATED",
            recovery_disposition=(
                ToolRecoveryDisposition.RETRY_SCHEDULED_STATE_INVALIDATED
            ),
            recovery_decision_ref=child.recovery_decision_id,
        )
        superseded_run = type(closure.active_run_record).model_validate(
            {
                **closure.active_run_record.model_dump(mode="python"),
                "status": AgentRunStatusV2.SUPERSEDED,
                "completed_at": decision.decided_at,
                "stop_reason": StopReasonV2.STATE_OR_BINDING_INVALIDATED,
            },
            strict=True,
        )
        oa10 = FinalizeSupersededRunV2Command(
            loaded_closure=oa10_closure,
            superseded_run_record=superseded_run,
            no_result_link_record=closure.active_run_task_link_record,
            run_stopped_trace_record=TraceEventV2(
                trace_event_id=self._uuid_factory(),
                event_type=TraceEventType.RUN_STOPPED,
                occurred_at=decision.decided_at,
                run_id=source.run_id,
                task_id=source.task_id,
                request_unit_id=source.request_unit_id,
                user_outcome=AgentOutcome.BLOCKED,
                stop_reason=StopReasonV2.STATE_OR_BINDING_INVALIDATED,
            ),
        )
        result = await (
            self._runtime_record_port.finalize_state_invalidated_tool_recovery_if_current(
                FinalizeStateInvalidatedToolRecoveryV2Command(
                    loaded_closure=closure,
                    recovery_decision_record=child,
                    terminal_tool_call_record=terminal_tool,
                    superseded_run_command=oa10,
                )
            )
        )
        return (
            terminal_tool if result is Cycle2WriteResult.APPLIED else source,
            None,
            result,
        )


class ReadToolRecoveryError(RuntimeError):
    """Bounded recovery failure without raw closure disclosure."""

    __slots__ = ()
