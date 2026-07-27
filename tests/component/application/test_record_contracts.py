import pickle
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel, Field, ValidationError

import mini_agent.application.records as application_records_module
from mini_agent.application.records import (
    AgentRunCommand,
    AgentRunResult,
    ApplyRestartRecoveryCommand,
    ApplyTaskTransitionCommand,
    ConversationRecord,
    ConversationTaskLinkRecord,
    CreateInitialTaskGraphCommand,
    CreateRunCommand,
    CreateRequestUnitCommand,
    CreateRunTaskLinkCommand,
    CreateTaskCommand,
    CreateToolCallCommand,
    DispatchToolCallCommand,
    CriticalFailureCode,
    EvalExecutionFailurePhase,
    EvalExecutionFailureRecord,
    EvalExecutionSafeErrorCode,
    EvalGraderResult,
    EvalGraderReasonCode,
    EvalGraderStatus,
    EvalLatencySummary,
    EvalResultRecord,
    EvalResultStatus,
    EvalUsageSummary,
    EvalVersionManifest,
    FinalizeRunCommand,
    FinalizeToolCallCommand,
    InterruptToolCallForRecoveryCommand,
    MarkRunIncompleteForRecoveryCommand,
    MessageDirection,
    MessageRecord,
    ObservationWriteResult,
    ProviderProtocolError,
    RecoveryWriteResult,
    RestartRecoveryClosure,
    RunTaskLinkRecord,
    SaveInputBindingCommand,
    SaveObservationCommand,
    SaveRequestUnderstandingCommand,
    TaskRecoveryAggregate,
    ToolCallRecoveryAggregate,
    TransitionRunCommand,
    TrustedOwnerScope,
)
from mini_agent.core.common import ContractVisibility
from mini_agent.core.identity import CustomerContext
from mini_agent.core.memory import ObservationVisibility, OrderObservation
from mini_agent.core.order import (
    OrderLineSummary,
    OrderStatus,
    OrderSummaryProjection,
)
from mini_agent.core.request_understanding import InputAuthority, TaskDeltaOperation
from mini_agent.core.task_state import (
    AcceptedTaskDelta,
    CandidateValidationDecision,
    CandidateValidationRecord,
    InputBinding,
    InputValidationStatus,
    RequestUnderstandingRecord,
    RequestUnitRecord,
    TaskRecord,
    TaskStateTransition,
    TaskStatus,
)
from mini_agent.core.tool_system import (
    GateDecisionValue,
    GateReasonCode,
    ToolAttemptRecord,
    ToolCallRecord,
    ToolCallStatus,
    ToolEffect,
    ToolResultOutcome,
)
from mini_agent.core.trace import (
    AgentOutcome,
    AgentRunRecord,
    AgentRunStatus,
    StopReason,
    TimingAndUsageSummary,
    TraceEvent,
    TraceEventType,
)

UTC_NOW = datetime(2026, 7, 26, 8, 0, tzinfo=timezone.utc)
NON_UTC_NOW = UTC_NOW.astimezone(timezone(timedelta(hours=8)))
SCHEMA_VERSION = "application-records-v1"


def _conversation(**updates: object) -> ConversationRecord:
    values: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "conversation_id": uuid4(),
        "owner_customer_id": "customer-A",
        "created_at": UTC_NOW,
    }
    values.update(updates)
    return ConversationRecord(**values)


def _message(**updates: object) -> MessageRecord:
    values: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "message_id": uuid4(),
        "conversation_id": uuid4(),
        "direction": MessageDirection.USER,
        "content": "查订单 O-1001",
        "received_at": UTC_NOW,
    }
    values.update(updates)
    return MessageRecord(**values)


def _conversation_task_link(
    **updates: object,
) -> ConversationTaskLinkRecord:
    values: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "conversation_id": uuid4(),
        "task_id": uuid4(),
        "link_reason": "CURRENT_MESSAGE_ACCEPTED_DELTA",
        "linked_at": UTC_NOW,
        "ended_at": None,
    }
    values.update(updates)
    return ConversationTaskLinkRecord(**values)


def _run_task_link(**updates: object) -> RunTaskLinkRecord:
    values: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "run_id": uuid4(),
        "task_id": uuid4(),
        "base_task_state_version": 1,
        "result_task_state_version": None,
    }
    values.update(updates)
    return RunTaskLinkRecord(**values)


def _run(**updates: object) -> AgentRunRecord:
    values: dict[str, object] = {
        "run_id": uuid4(),
        "conversation_id": uuid4(),
        "status": AgentRunStatus.CREATED,
        "provider_lane": "scripted",
        "started_at": UTC_NOW,
    }
    values.update(updates)
    return AgentRunRecord(**values)


def _project_run(
    record: AgentRunRecord,
    **updates: object,
) -> AgentRunRecord:
    values = record.model_dump()
    values.update(updates)
    return AgentRunRecord(**values)


def _task(**updates: object) -> TaskRecord:
    values: dict[str, object] = {
        "task_id": uuid4(),
        "owner_customer_id": "customer-A",
        "status": TaskStatus.ACTIVE,
        "state_version": 1,
        "created_at": UTC_NOW,
        "updated_at": UTC_NOW,
    }
    values.update(updates)
    return TaskRecord(**values)


def _request_unit(**updates: object) -> RequestUnitRecord:
    values: dict[str, object] = {
        "request_unit_id": uuid4(),
        "task_id": uuid4(),
        "goal_text": "查询订单",
        "goal_source_refs": (uuid4(),),
        "input_binding_refs": (uuid4(),),
        "status": TaskStatus.ACTIVE,
        "state_version": 1,
        "created_at": UTC_NOW,
        "updated_at": UTC_NOW,
    }
    values.update(updates)
    return RequestUnitRecord(**values)


def _tool_call(
    *,
    status: ToolCallStatus,
    attempt_count: int,
    tool_call_id: UUID | None = None,
    effect: ToolEffect = ToolEffect.READ,
    finished_at: datetime | None = None,
    failure_code: str | None = None,
    interruption_reason: str | None = None,
    result_ref: UUID | None = None,
) -> ToolCallRecord:
    return ToolCallRecord(
        tool_call_id=tool_call_id or uuid4(),
        run_id=uuid4(),
        task_id=uuid4(),
        request_unit_id=uuid4(),
        model_call_id=uuid4(),
        context_manifest_id=uuid4(),
        gate_decision_id=uuid4(),
        canonical_tool_name="get_order",
        tool_registry_version="e2e01-thin-tools-v1",
        validated_task_state_version=1,
        argument_binding_refs=(uuid4(),),
        effect=effect,
        attempt_count=attempt_count,
        status=status,
        started_at=UTC_NOW,
        finished_at=finished_at,
        failure_code=failure_code,
        interruption_reason=interruption_reason,
        result_ref=result_ref,
    )


def _project_tool_call(
    record: ToolCallRecord,
    **updates: object,
) -> ToolCallRecord:
    values = record.model_dump()
    values.update(updates)
    return ToolCallRecord(**values)


def _customer_context(customer_id: str = "customer-A") -> CustomerContext:
    return CustomerContext(
        subject_ref=f"subject-{customer_id}",
        customer_id=customer_id,
        auth_scopes=frozenset({"orders:read"}),
        authenticated_at=UTC_NOW,
        session_ref_hash=f"safe-session-{customer_id}",
    )


def _owner_scope(customer_id: str = "customer-A") -> TrustedOwnerScope:
    return TrustedOwnerScope.from_customer_context(_customer_context(customer_id))


def _input_binding(**updates: object) -> InputBinding:
    values: dict[str, object] = {
        "binding_id": uuid4(),
        "name": "order_id",
        "normalized_value": "O-1001",
        "authority": InputAuthority.USER_CLAIM,
        "source_refs": (uuid4(),),
        "validation_status": InputValidationStatus.ACCEPTED,
        "confirmed_by_user": True,
        "created_at": UTC_NOW,
        "updated_at": UTC_NOW,
    }
    values.update(updates)
    return InputBinding(**values)


def _request_understanding(**updates: object) -> RequestUnderstandingRecord:
    candidate_ref = uuid4()
    accepted_delta_ref = uuid4()
    values: dict[str, object] = {
        "run_id": uuid4(),
        "message_ref": uuid4(),
        "schema_version": "request_understanding_record.p0.v1",
        "candidate_validation": (
            CandidateValidationRecord(
                candidate_ref=candidate_ref,
                decision=CandidateValidationDecision.ACCEPT,
            ),
        ),
        "accepted_delta_refs": (accepted_delta_ref,),
        "next_move_candidate_ref": uuid4(),
    }
    values.update(updates)
    return RequestUnderstandingRecord(**values)


def _accepted_delta(**updates: object) -> AcceptedTaskDelta:
    values: dict[str, object] = {
        "accepted_delta_id": uuid4(),
        "candidate_ref": uuid4(),
        "message_ref": uuid4(),
        "operation": TaskDeltaOperation.ADD_GOAL,
        "goal_text": "查询订单 O-1001",
        "input_binding_refs": (uuid4(),),
        "accepted_at": UTC_NOW,
    }
    values.update(updates)
    return AcceptedTaskDelta(**values)


def _task_transition(**updates: object) -> TaskStateTransition:
    values: dict[str, object] = {
        "task_id": uuid4(),
        "request_unit_id": uuid4(),
        "from_status": TaskStatus.ACTIVE,
        "to_status": TaskStatus.WAITING_USER,
        "base_state_version": 1,
        "result_state_version": 2,
        "reason_ref": uuid4(),
        "changed_at": UTC_NOW + timedelta(milliseconds=1),
    }
    values.update(updates)
    return TaskStateTransition(**values)


def _observation(**updates: object) -> OrderObservation:
    values: dict[str, object] = {
        "observation_id": uuid4(),
        "source_tool": "get_order",
        "source_resource_ref": "O-1001",
        "source_version": "order-v1",
        "normalized_type": "ORDER_SUMMARY",
        "normalized_value": OrderSummaryProjection(
            order_number="O-1001",
            status=OrderStatus.SHIPPED,
            line_items=(OrderLineSummary(product_name="轻量跑鞋", quantity=1),),
            ordered_at=UTC_NOW,
            status_updated_at=UTC_NOW,
        ),
        "observed_at": UTC_NOW,
        "recorded_at": UTC_NOW,
        "visibility": ObservationVisibility.MODEL_VISIBLE,
    }
    values.update(updates)
    return OrderObservation(**values)


def _rebuild(instance: BaseModel, **updates: object) -> BaseModel:
    values = {
        field_name: getattr(instance, field_name)
        for field_name in type(instance).model_fields
    }
    values.update(updates)
    return type(instance)(**values)


def _assert_validation_error_is_sanitized(
    error: ValidationError,
    *forbidden_values: str,
) -> None:
    projections = (
        str(error),
        repr(error),
        repr(error.args),
        repr(error.errors()),
        error.json(),
    )
    for forbidden_value in forbidden_values:
        assert all(forbidden_value not in projection for projection in projections)


_COMPLETED_TERMINAL_MATRIX = (
    (
        StopReason.GOAL_COMPLETED,
        True,
        AgentOutcome.COMPLETED,
        TaskStatus.COMPLETED,
    ),
    (
        StopReason.NOT_FOUND_OR_NOT_ACCESSIBLE,
        True,
        AgentOutcome.NOT_FOUND_OR_NOT_ACCESSIBLE,
        TaskStatus.COMPLETED,
    ),
    (
        StopReason.PROVIDER_PROTOCOL_ERROR,
        False,
        AgentOutcome.BLOCKED,
        None,
    ),
    (
        StopReason.PROVIDER_PROTOCOL_ERROR,
        True,
        AgentOutcome.BLOCKED,
        TaskStatus.BLOCKED,
    ),
    (
        StopReason.INPUT_INVALID,
        False,
        AgentOutcome.BLOCKED,
        None,
    ),
    (
        StopReason.GATE_REJECTED,
        True,
        AgentOutcome.BLOCKED,
        TaskStatus.BLOCKED,
    ),
    (
        StopReason.ORDER_SERVICE_UNAVAILABLE,
        True,
        AgentOutcome.BLOCKED,
        TaskStatus.BLOCKED,
    ),
    (
        StopReason.PRESENTATION_PLAN_REJECTED,
        True,
        AgentOutcome.BLOCKED,
        TaskStatus.BLOCKED,
    ),
    (
        StopReason.RENDERER_INVARIANT_FAILED,
        True,
        AgentOutcome.BLOCKED,
        TaskStatus.BLOCKED,
    ),
)


def _terminal_task_transition(
    *,
    task_id: UUID,
    request_unit_id: UUID,
    terminal_status: TaskStatus,
    base_state_version: int = 1,
    changed_at: datetime = UTC_NOW + timedelta(milliseconds=1),
) -> ApplyTaskTransitionCommand:
    expected_task = _task(
        task_id=task_id,
        status=TaskStatus.ACTIVE,
        state_version=base_state_version,
    )
    expected_unit = _request_unit(
        request_unit_id=request_unit_id,
        task_id=task_id,
        status=TaskStatus.ACTIVE,
        state_version=base_state_version,
    )
    next_task = _rebuild(
        expected_task,
        status=terminal_status,
        state_version=base_state_version + 1,
        updated_at=changed_at,
    )
    next_unit = _rebuild(
        expected_unit,
        status=terminal_status,
        state_version=base_state_version + 1,
        updated_at=changed_at,
    )
    transition = _task_transition(
        task_id=task_id,
        request_unit_id=request_unit_id,
        from_status=TaskStatus.ACTIVE,
        to_status=terminal_status,
        base_state_version=base_state_version,
        result_state_version=base_state_version + 1,
        changed_at=changed_at,
    )
    return ApplyTaskTransitionCommand(
        expected_task_record=expected_task,
        next_task_record=next_task,
        expected_request_unit_record=expected_unit,
        next_request_unit_record=next_unit,
        task_state_transition=transition,
    )


def _terminal_trace_events(
    *,
    run_id: UUID,
    stop_reason: StopReason,
    outcome: AgentOutcome,
    completed_at: datetime,
    task_transition: ApplyTaskTransitionCommand | None,
) -> tuple[TraceEvent, ...]:
    task_events = (
        (
            TraceEvent(
                trace_event_id=uuid4(),
                event_type=TraceEventType.TASK_STATE_CHANGED,
                occurred_at=task_transition.task_state_transition.changed_at,
                run_id=run_id,
                task_id=task_transition.next_task_record.task_id,
                request_unit_id=(
                    task_transition.next_request_unit_record.request_unit_id
                ),
            ),
        )
        if task_transition is not None
        else ()
    )
    return (
        *task_events,
        TraceEvent(
            trace_event_id=uuid4(),
            event_type=TraceEventType.RUN_STOPPED,
            occurred_at=completed_at,
            run_id=run_id,
            user_outcome=outcome,
            stop_reason=stop_reason,
        ),
    )


def _completed_finalization(
    *,
    stop_reason: StopReason = StopReason.GOAL_COMPLETED,
    outcome: AgentOutcome = AgentOutcome.COMPLETED,
    with_task: bool = True,
    task_status: TaskStatus | None = TaskStatus.COMPLETED,
    active_link_base_state_version: int | None = 1,
    transition_base_state_version: int = 1,
) -> FinalizeRunCommand:
    if with_task != (task_status is not None):
        raise ValueError("task_status must be present exactly when with_task is true")
    run_id = uuid4()
    conversation_id = uuid4()
    completed_at = UTC_NOW + timedelta(milliseconds=2)
    running = _run(
        run_id=run_id,
        conversation_id=conversation_id,
        status=AgentRunStatus.RUNNING,
    )
    terminal = _project_run(
        running,
        status=AgentRunStatus.COMPLETED,
        completed_at=completed_at,
        stop_reason=stop_reason,
    )
    terminal_result = AgentRunResult(
        run_id=run_id,
        outcome=outcome,
        message="这是经过确定性映射的终态回复。",
    )
    assistant_message = MessageRecord(
        schema_version="message_record.p0.v1",
        message_id=uuid4(),
        conversation_id=conversation_id,
        direction=MessageDirection.ASSISTANT,
        content=terminal_result.message,
        received_at=completed_at,
    )

    if with_task:
        task_id = uuid4()
        request_unit_id = uuid4()
        assert task_status is not None
        task_transition = _terminal_task_transition(
            task_id=task_id,
            request_unit_id=request_unit_id,
            terminal_status=task_status,
            base_state_version=transition_base_state_version,
        )
        active_link = _run_task_link(
            run_id=run_id,
            task_id=task_id,
            base_task_state_version=active_link_base_state_version,
        )
        expected_active_links = (active_link,)
        terminal_links = (
            _rebuild(
                active_link,
                result_task_state_version=(
                    task_transition.next_task_record.state_version
                ),
            ),
        )
        result_task_records = (task_transition.next_task_record,)
    else:
        task_transition = None
        expected_active_links = ()
        terminal_links = ()
        result_task_records = ()

    return FinalizeRunCommand(
        expected_active_record=running,
        terminal_record=terminal,
        expected_active_links=expected_active_links,
        terminal_links=terminal_links,
        result_task_records=result_task_records,
        task_transition=task_transition,
        terminal_result=terminal_result,
        assistant_message=assistant_message,
        terminal_trace_events=_terminal_trace_events(
            run_id=run_id,
            stop_reason=stop_reason,
            outcome=outcome,
            completed_at=completed_at,
            task_transition=task_transition,
        ),
    )


def _failed_finalization(
    *,
    with_task: bool = True,
    active_link_base_state_version: int | None = 1,
    current_task_state_version: int = 1,
) -> FinalizeRunCommand:
    run_id = uuid4()
    running = _run(
        run_id=run_id,
        conversation_id=uuid4(),
        status=AgentRunStatus.RUNNING,
    )
    terminal = _project_run(
        running,
        status=AgentRunStatus.FAILED,
        completed_at=UTC_NOW + timedelta(milliseconds=2),
        stop_reason=None,
    )
    if with_task:
        task_id = uuid4()
        current_task = _task(
            task_id=task_id,
            status=TaskStatus.ACTIVE,
            state_version=current_task_state_version,
        )
        active_link = _run_task_link(
            run_id=run_id,
            task_id=task_id,
            base_task_state_version=active_link_base_state_version,
        )
        expected_active_links = (active_link,)
        terminal_links = (
            _rebuild(
                active_link,
                result_task_state_version=current_task_state_version,
            ),
        )
        result_task_records = (current_task,)
    else:
        expected_active_links = ()
        terminal_links = ()
        result_task_records = ()
    return FinalizeRunCommand(
        expected_active_record=running,
        terminal_record=terminal,
        expected_active_links=expected_active_links,
        terminal_links=terminal_links,
        result_task_records=result_task_records,
        task_transition=None,
        terminal_result=None,
        assistant_message=None,
        terminal_trace_events=(),
    )


def _updated_terminal_trace_events(
    command: FinalizeRunCommand,
    selected_event_type: TraceEventType,
    **updates: object,
) -> tuple[TraceEvent, ...]:
    events = list(command.terminal_trace_events)
    event_index = next(
        index
        for index, event in enumerate(events)
        if event.event_type is selected_event_type
    )
    events[event_index] = events[event_index].model_copy(update=updates)
    return tuple(events)


def _recovery_trace_events(
    *,
    run_transition: MarkRunIncompleteForRecoveryCommand,
    task_transitions: tuple[ApplyTaskTransitionCommand, ...],
    tool_call_transitions: tuple[InterruptToolCallForRecoveryCommand, ...],
) -> tuple[TraceEvent, ...]:
    run_id = run_transition.expected_active_record.run_id
    return (
        TraceEvent(
            trace_event_id=uuid4(),
            event_type=TraceEventType.RUN_STOPPED,
            occurred_at=run_transition.incomplete_record.completed_at,
            run_id=run_id,
            user_outcome=AgentOutcome.BLOCKED,
            stop_reason=StopReason.PROCESS_RESTART_DETECTED,
        ),
        *(
            TraceEvent(
                trace_event_id=uuid4(),
                event_type=TraceEventType.TASK_STATE_CHANGED,
                occurred_at=transition.task_state_transition.changed_at,
                run_id=run_id,
                task_id=transition.next_task_record.task_id,
                request_unit_id=transition.next_request_unit_record.request_unit_id,
            )
            for transition in task_transitions
        ),
        *(
            TraceEvent(
                trace_event_id=uuid4(),
                event_type=TraceEventType.TOOL_CALL_INTERRUPTED,
                occurred_at=transition.interrupted_record.finished_at,
                run_id=run_id,
                tool_call_id=transition.interrupted_record.tool_call_id,
                tool_call_terminal_status=ToolCallStatus.INTERRUPTED,
            )
            for transition in tool_call_transitions
        ),
    )


_RECOVERY_TRACE_COMMON_FIELDS = frozenset(
    {
        "trace_event_id",
        "event_type",
        "occurred_at",
        "run_id",
    }
)
_RECOVERY_TRACE_ALLOWED_FIELDS = {
    TraceEventType.RUN_STOPPED: _RECOVERY_TRACE_COMMON_FIELDS
    | {"user_outcome", "stop_reason"},
    TraceEventType.TASK_STATE_CHANGED: _RECOVERY_TRACE_COMMON_FIELDS
    | {"task_id", "request_unit_id"},
    TraceEventType.TOOL_CALL_INTERRUPTED: _RECOVERY_TRACE_COMMON_FIELDS
    | {"tool_call_id", "tool_call_terminal_status"},
}
_RECOVERY_TRACE_CONTAMINATION_CASES = tuple(
    (event_type, field_name)
    for event_type, allowed_fields in _RECOVERY_TRACE_ALLOWED_FIELDS.items()
    for field_name in sorted(set(TraceEvent.model_fields) - allowed_fields)
)
_TERMINAL_TRACE_COMMON_FIELDS = frozenset(
    {
        "trace_event_id",
        "event_type",
        "occurred_at",
        "run_id",
    }
)
_TERMINAL_TRACE_ALLOWED_FIELDS = {
    TraceEventType.TASK_STATE_CHANGED: _TERMINAL_TRACE_COMMON_FIELDS
    | {"task_id", "request_unit_id"},
    TraceEventType.RUN_STOPPED: _TERMINAL_TRACE_COMMON_FIELDS
    | {"user_outcome", "stop_reason"},
}
_TERMINAL_TRACE_CONTAMINATION_CASES = tuple(
    (event_type, field_name)
    for event_type, allowed_fields in _TERMINAL_TRACE_ALLOWED_FIELDS.items()
    for field_name in sorted(set(TraceEvent.model_fields) - allowed_fields)
)


def _non_empty_trace_optional_value(field_name: str) -> object:
    values: dict[str, object] = {
        "case_id": "E2E01-01",
        "message_ref": uuid4(),
        "accepted_delta_ref": uuid4(),
        "task_id": uuid4(),
        "request_unit_id": uuid4(),
        "input_binding_ref": uuid4(),
        "model_call_id": uuid4(),
        "model_call_purpose": "REQUEST_UNDERSTANDING",
        "context_manifest_id": uuid4(),
        "provider_name": "scripted",
        "model_snapshot": "scripted-v1",
        "tool_registry_version": "e2e01-thin-tools-v1",
        "model_visible_toolset_hash": f"sha256:{'0' * 64}",
        "next_move_kind": "CALL_TOOL",
        "requested_tool_name": "get_order",
        "proposed_base_task_state_version": 1,
        "validated_task_state_version": 1,
        "argument_binding_refs": (uuid4(),),
        "gate_decision": GateDecisionValue.ACCEPT,
        "gate_reason_code": GateReasonCode.TOOL_NOT_REGISTERED,
        "tool_call_id": uuid4(),
        "tool_call_terminal_status": ToolCallStatus.FAILED,
        "safe_tool_outcome": ToolResultOutcome.SYSTEM_FAILURE,
        "observation_ref": uuid4(),
        "presentation_plan_ref": uuid4(),
        "user_outcome": AgentOutcome.BLOCKED,
        "stop_reason": StopReason.PROCESS_RESTART_DETECTED,
        "timing_and_usage_summary": TimingAndUsageSummary(duration_ms=1),
    }
    return values[field_name]


def _updated_recovery_trace_events(
    command: ApplyRestartRecoveryCommand,
    selected_event_type: TraceEventType,
    **updates: object,
) -> tuple[TraceEvent, ...]:
    events = list(command.recovery_trace_events)
    event_index = next(
        index
        for index, event in enumerate(events)
        if event.event_type is selected_event_type
    )
    events[event_index] = events[event_index].model_copy(update=updates)
    return tuple(events)


def _initial_graph() -> CreateInitialTaskGraphCommand:
    conversation_id = uuid4()
    message_id = uuid4()
    run_id = uuid4()
    task_id = uuid4()
    request_unit_id = uuid4()
    binding_id = uuid4()
    accepted_delta_id = uuid4()
    candidate_ref = uuid4()
    conversation = _conversation(
        schema_version="conversation_record.p0.v1",
        conversation_id=conversation_id,
    )
    message = _message(
        schema_version="message_record.p0.v1",
        message_id=message_id,
        conversation_id=conversation_id,
    )
    run = _run(
        run_id=run_id,
        conversation_id=conversation_id,
        status=AgentRunStatus.RUNNING,
    )
    binding = _input_binding(
        binding_id=binding_id,
        source_refs=(message_id,),
    )
    accepted_delta = _accepted_delta(
        accepted_delta_id=accepted_delta_id,
        candidate_ref=candidate_ref,
        message_ref=message_id,
        input_binding_refs=(binding_id,),
    )
    understanding = _request_understanding(
        run_id=run_id,
        message_ref=message_id,
        candidate_validation=(
            CandidateValidationRecord(
                candidate_ref=candidate_ref,
                decision=CandidateValidationDecision.ACCEPT,
            ),
        ),
        accepted_delta_refs=(accepted_delta_id,),
    )
    task = _task(task_id=task_id)
    request_unit = _request_unit(
        request_unit_id=request_unit_id,
        task_id=task_id,
        goal_text=accepted_delta.goal_text,
        goal_source_refs=(message_id,),
        input_binding_refs=(binding_id,),
    )
    return CreateInitialTaskGraphCommand(
        owner_scope=_owner_scope(),
        expected_conversation_record=conversation,
        expected_message_record=message,
        expected_active_run_record=run,
        request_understanding=SaveRequestUnderstandingCommand(
            record=understanding,
            accepted_deltas=(accepted_delta,),
        ),
        initial_task=CreateTaskCommand(initial_record=task),
        initial_request_unit=CreateRequestUnitCommand(initial_record=request_unit),
        input_bindings=(
            SaveInputBindingCommand(
                record=binding,
                request_unit_id=request_unit_id,
            ),
        ),
        conversation_task_link=ConversationTaskLinkRecord(
            schema_version="conversation_task_link_record.p0.v1",
            conversation_id=conversation_id,
            task_id=task_id,
            link_reason="CURRENT_MESSAGE_ACCEPTED_DELTA",
            linked_at=UTC_NOW,
        ),
        run_task_link=CreateRunTaskLinkCommand(
            active_record=RunTaskLinkRecord(
                schema_version="run_task_link_record.p0.v1",
                run_id=run_id,
                task_id=task_id,
                base_task_state_version=None,
                result_task_state_version=None,
            )
        ),
    )


def _task_transition_command() -> ApplyTaskTransitionCommand:
    task_id = uuid4()
    request_unit_id = uuid4()
    expected_task = _task(task_id=task_id)
    expected_request_unit = _request_unit(
        request_unit_id=request_unit_id,
        task_id=task_id,
        status=TaskStatus.ACTIVE,
        state_version=1,
    )
    next_task = _task(
        task_id=task_id,
        status=TaskStatus.WAITING_USER,
        state_version=2,
        created_at=expected_task.created_at,
        updated_at=UTC_NOW + timedelta(milliseconds=1),
    )
    next_request_unit = _request_unit(
        request_unit_id=request_unit_id,
        task_id=task_id,
        goal_text=expected_request_unit.goal_text,
        goal_source_refs=expected_request_unit.goal_source_refs,
        input_binding_refs=expected_request_unit.input_binding_refs,
        status=TaskStatus.WAITING_USER,
        state_version=2,
        created_at=expected_request_unit.created_at,
        updated_at=UTC_NOW + timedelta(milliseconds=1),
    )
    transition = _task_transition(
        task_id=task_id,
        request_unit_id=request_unit_id,
    )
    return ApplyTaskTransitionCommand(
        expected_task_record=expected_task,
        next_task_record=next_task,
        expected_request_unit_record=expected_request_unit,
        next_request_unit_record=next_request_unit,
        task_state_transition=transition,
    )


def _restart_recovery_closure() -> RestartRecoveryClosure:
    conversation_id = uuid4()
    run_id = uuid4()
    task_id = uuid4()
    request_unit_id = uuid4()
    tool_call_id = uuid4()
    transition = _task_transition(
        task_id=task_id,
        request_unit_id=request_unit_id,
    )
    task = _task(
        task_id=task_id,
        status=TaskStatus.WAITING_USER,
        state_version=2,
        updated_at=transition.changed_at,
    )
    request_unit = _request_unit(
        request_unit_id=request_unit_id,
        task_id=task_id,
        status=TaskStatus.WAITING_USER,
        state_version=2,
        updated_at=transition.changed_at,
    )
    tool_call = _tool_call(
        status=ToolCallStatus.RUNNING,
        attempt_count=1,
        tool_call_id=tool_call_id,
    ).model_copy(
        update={
            "run_id": run_id,
            "task_id": task_id,
            "request_unit_id": request_unit_id,
            "validated_task_state_version": task.state_version,
            "argument_binding_refs": request_unit.input_binding_refs,
        }
    )
    return RestartRecoveryClosure(
        closure_fence=uuid4(),
        conversation_record=_conversation(
            schema_version="conversation_record.p0.v1",
            conversation_id=conversation_id,
        ),
        active_run_record=_run(
            run_id=run_id,
            conversation_id=conversation_id,
            status=AgentRunStatus.RUNNING,
        ),
        conversation_task_links=(
            ConversationTaskLinkRecord(
                schema_version="conversation_task_link_record.p0.v1",
                conversation_id=conversation_id,
                task_id=task_id,
                link_reason="CURRENT_MESSAGE_ACCEPTED_DELTA",
                linked_at=UTC_NOW,
            ),
        ),
        run_task_links=(
            RunTaskLinkRecord(
                schema_version="run_task_link_record.p0.v1",
                run_id=run_id,
                task_id=task_id,
                base_task_state_version=1,
                result_task_state_version=None,
            ),
        ),
        task_aggregates=(
            TaskRecoveryAggregate(
                task_record=task,
                task_state_transitions=(transition,),
            ),
        ),
        request_unit_records=(request_unit,),
        tool_call_aggregates=(
            ToolCallRecoveryAggregate(
                tool_call_record=tool_call,
                tool_attempt_records=(
                    ToolAttemptRecord(
                        tool_call_id=tool_call_id,
                        attempt_no=1,
                        started_at=UTC_NOW,
                    ),
                ),
            ),
        ),
    )


def _created_restart_recovery_closure() -> RestartRecoveryClosure:
    conversation_id = uuid4()
    conversation = _conversation(
        schema_version="conversation_record.p0.v1",
        conversation_id=conversation_id,
    )
    return RestartRecoveryClosure(
        closure_fence=uuid4(),
        conversation_record=conversation,
        active_run_record=_run(
            conversation_id=conversation_id,
            status=AgentRunStatus.CREATED,
        ),
        conversation_task_links=(),
        run_task_links=(),
        task_aggregates=(),
        request_unit_records=(),
        tool_call_aggregates=(),
    )


def _created_restart_recovery_command() -> ApplyRestartRecoveryCommand:
    closure = _created_restart_recovery_closure()
    active_run = closure.active_run_record
    run_transition = MarkRunIncompleteForRecoveryCommand(
        expected_active_record=active_run,
        incomplete_record=_project_run(
            active_run,
            status=AgentRunStatus.INCOMPLETE,
            completed_at=UTC_NOW + timedelta(milliseconds=1),
            stop_reason=StopReason.PROCESS_RESTART_DETECTED,
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


def _restart_recovery_command() -> ApplyRestartRecoveryCommand:
    closure = _restart_recovery_closure()
    run = closure.active_run_record
    task = closure.task_aggregates[0].task_record
    request_unit = closure.request_unit_records[0]
    tool_call = closure.tool_call_aggregates[0].tool_call_record
    completed_at = UTC_NOW + timedelta(milliseconds=2)
    task_transition = ApplyTaskTransitionCommand(
        expected_task_record=task,
        next_task_record=_task(
            task_id=task.task_id,
            owner_customer_id=task.owner_customer_id,
            status=TaskStatus.BLOCKED,
            state_version=3,
            created_at=task.created_at,
            updated_at=completed_at,
            last_outcome_ref=task.last_outcome_ref,
        ),
        expected_request_unit_record=request_unit,
        next_request_unit_record=_request_unit(
            request_unit_id=request_unit.request_unit_id,
            task_id=request_unit.task_id,
            goal_text=request_unit.goal_text,
            goal_source_refs=request_unit.goal_source_refs,
            contextualization_ref=request_unit.contextualization_ref,
            constraint_refs=request_unit.constraint_refs,
            dependency_refs=request_unit.dependency_refs,
            input_binding_refs=request_unit.input_binding_refs,
            open_questions=request_unit.open_questions,
            observation_refs=request_unit.observation_refs,
            evidence_binding_refs=request_unit.evidence_binding_refs,
            pending_action_ref=request_unit.pending_action_ref,
            result_refs=request_unit.result_refs,
            status=TaskStatus.BLOCKED,
            state_version=3,
            created_at=request_unit.created_at,
            updated_at=completed_at,
        ),
        task_state_transition=_task_transition(
            task_id=task.task_id,
            request_unit_id=request_unit.request_unit_id,
            from_status=TaskStatus.WAITING_USER,
            to_status=TaskStatus.BLOCKED,
            base_state_version=2,
            result_state_version=3,
            changed_at=completed_at,
        ),
    )
    run_transition = MarkRunIncompleteForRecoveryCommand(
        expected_active_record=run,
        incomplete_record=_project_run(
            run,
            status=AgentRunStatus.INCOMPLETE,
            completed_at=completed_at,
            stop_reason=StopReason.PROCESS_RESTART_DETECTED,
        ),
    )
    tool_call_transitions = (
        InterruptToolCallForRecoveryCommand(
            active_record=tool_call,
            interrupted_record=_project_tool_call(
                tool_call,
                status=ToolCallStatus.INTERRUPTED,
                finished_at=completed_at,
                interruption_reason="PROCESS_RESTART_DETECTED",
            ),
        ),
    )
    return ApplyRestartRecoveryCommand(
        expected_closure=closure,
        run_transition=run_transition,
        tool_call_transitions=tool_call_transitions,
        task_transitions=(task_transition,),
        terminal_run_task_links=(
            _rebuild(
                closure.run_task_links[0],
                result_task_state_version=3,
            ),
        ),
        recovery_trace_events=_recovery_trace_events(
            run_transition=run_transition,
            task_transitions=(task_transition,),
            tool_call_transitions=tool_call_transitions,
        ),
    )


def _valid_command_records() -> tuple[BaseModel, ...]:
    created_run = _run()
    running_run = _project_run(created_run, status=AgentRunStatus.RUNNING)
    incomplete_run = _project_run(
        running_run,
        status=AgentRunStatus.INCOMPLETE,
        completed_at=UTC_NOW + timedelta(milliseconds=1),
        stop_reason=StopReason.PROCESS_RESTART_DETECTED,
    )

    created = _tool_call(status=ToolCallStatus.CREATED, attempt_count=0)

    dispatch_id = uuid4()
    expected_created = _tool_call(
        status=ToolCallStatus.CREATED,
        attempt_count=0,
        tool_call_id=dispatch_id,
    )
    running = _project_tool_call(
        expected_created,
        status=ToolCallStatus.RUNNING,
        attempt_count=1,
    )
    started_attempt = ToolAttemptRecord(
        tool_call_id=dispatch_id,
        attempt_no=1,
        started_at=UTC_NOW,
    )

    final_id = uuid4()
    finished_at = UTC_NOW + timedelta(milliseconds=1)
    expected_running = _tool_call(
        status=ToolCallStatus.RUNNING,
        attempt_count=1,
        tool_call_id=final_id,
    )
    terminal = _project_tool_call(
        expected_running,
        status=ToolCallStatus.SUCCEEDED,
        finished_at=finished_at,
        result_ref=uuid4(),
    )
    finalized_attempt = ToolAttemptRecord(
        tool_call_id=final_id,
        attempt_no=1,
        started_at=UTC_NOW,
        finished_at=finished_at,
        outcome=ToolResultOutcome.SUCCESS,
    )

    interrupted = _project_tool_call(
        created,
        status=ToolCallStatus.INTERRUPTED,
        finished_at=finished_at,
        interruption_reason="PROCESS_RESTART_DETECTED",
    )
    return (
        CreateRunCommand(created_record=created_run),
        TransitionRunCommand(
            expected_active_record=created_run,
            next_record=running_run,
        ),
        MarkRunIncompleteForRecoveryCommand(
            expected_active_record=running_run,
            incomplete_record=incomplete_run,
        ),
        CreateTaskCommand(initial_record=_task()),
        CreateRequestUnitCommand(initial_record=_request_unit()),
        CreateRunTaskLinkCommand(active_record=_run_task_link()),
        CreateToolCallCommand(created_record=created),
        DispatchToolCallCommand(
            expected_created_record=expected_created,
            running_record=running,
            started_attempt=started_attempt,
        ),
        FinalizeToolCallCommand(
            expected_running_record=expected_running,
            expected_started_attempt=ToolAttemptRecord(
                tool_call_id=final_id,
                attempt_no=1,
                started_at=UTC_NOW,
            ),
            terminal_record=terminal,
            finalized_attempt=finalized_attempt,
        ),
        InterruptToolCallForRecoveryCommand(
            active_record=created,
            interrupted_record=interrupted,
        ),
    )


def _version_manifest(**updates: object) -> EvalVersionManifest:
    values: dict[str, object] = {
        "dataset_version": "e2e01-thin-dataset-v1",
        "candidate_version": "candidate-source-revision",
        "fixture_versions": ("e2e01-thin-fixture-v1",),
        "model_config_version": "scripted-provider-v1",
        "runtime_version": "runtime-source-revision",
    }
    values.update(updates)
    return EvalVersionManifest(**values)


def _eval_execution_failure(**updates: object) -> EvalExecutionFailureRecord:
    values: dict[str, object] = {
        "schema_version": "eval-execution-failure-v1",
        "eval_run_id": uuid4(),
        "case_id": "E2E01-01",
        "lane": "offline_gate",
        "attempt": 1,
        "failure_phase": EvalExecutionFailurePhase.TRACE_PERSISTENCE,
        "safe_error_code": EvalExecutionSafeErrorCode.TRACE_STORE_UNAVAILABLE,
        "diagnostic_ref": uuid4(),
        "trace_ref": None,
        "version_manifest": _version_manifest(),
        "occurred_at": UTC_NOW,
    }
    values.update(updates)
    return EvalExecutionFailureRecord(**values)


def _passing_grader() -> EvalGraderResult:
    return EvalGraderResult(
        grader_name="IdentityBoundaryGrader",
        status=EvalGraderStatus.PASS,
    )


def _eval_result(**updates: object) -> EvalResultRecord:
    values: dict[str, object] = {
        "schema_version": "eval-result-v1",
        "eval_run_id": uuid4(),
        "case_id": "E2E01-01",
        "lane": "offline_gate",
        "attempt": 1,
        "status": EvalResultStatus.PASS,
        "grader_results": (_passing_grader(),),
        "critical_failures": (),
        "observed_outcome": AgentOutcome.COMPLETED,
        "trace_ref": uuid4(),
        "version_manifest": _version_manifest(),
        "latency_summary": EvalLatencySummary(total_duration_ms=12),
        "usage_summary": EvalUsageSummary(input_tokens=20, output_tokens=8),
        "completed_at": UTC_NOW,
    }
    values.update(updates)
    return EvalResultRecord(**values)


def test_persisted_records_are_strict_frozen_and_extra_forbid() -> None:
    record_types = (
        ConversationRecord,
        MessageRecord,
        ConversationTaskLinkRecord,
        RunTaskLinkRecord,
        EvalExecutionFailureRecord,
        EvalResultRecord,
    )
    for record_type in record_types:
        assert record_type.model_config["strict"] is True
        assert record_type.model_config["frozen"] is True
        assert record_type.model_config["extra"] == "forbid"
        assert record_type.model_json_schema()["additionalProperties"] is False

    with pytest.raises(ValidationError, match="UUID"):
        _conversation(conversation_id=str(uuid4()))
    with pytest.raises(ValidationError, match="Extra inputs"):
        ConversationRecord(
            schema_version=SCHEMA_VERSION,
            conversation_id=uuid4(),
            owner_customer_id="customer-A",
            created_at=UTC_NOW,
            unexpected="forbidden",
        )

    frozen = _conversation()
    with pytest.raises(ValidationError, match="frozen"):
        frozen.owner_customer_id = "customer-B"


def test_nested_eval_and_write_commands_are_strict_frozen_and_extra_forbid() -> None:
    instances = (
        _passing_grader(),
        _version_manifest(),
        EvalLatencySummary(total_duration_ms=12),
        EvalUsageSummary(input_tokens=20, output_tokens=8),
        *_valid_command_records(),
    )

    for instance in instances:
        record_type = type(instance)
        assert record_type.model_config["strict"] is True
        assert record_type.model_config["frozen"] is True
        assert record_type.model_config["extra"] == "forbid"
        assert record_type.model_json_schema()["additionalProperties"] is False

        first_field = next(iter(record_type.model_fields))
        with pytest.raises(ValidationError, match="frozen"):
            setattr(instance, first_field, getattr(instance, first_field))

        values = {
            field_name: getattr(instance, field_name)
            for field_name in record_type.model_fields
        }
        with pytest.raises(ValidationError, match="Extra inputs"):
            record_type.model_validate({**values, "unexpected": "forbidden"})


@pytest.mark.parametrize(
    "factory",
    (
        _conversation,
        _message,
        _conversation_task_link,
        _run_task_link,
        _eval_execution_failure,
        _eval_result,
    ),
)
def test_persisted_records_require_non_empty_schema_version(factory: object) -> None:
    with pytest.raises(ValidationError, match="at least 1 character"):
        factory(schema_version="")


def test_conversation_owner_and_raw_message_are_runtime_private() -> None:
    assert ConversationRecord.contract_visibility is ContractVisibility.RUNTIME_PRIVATE
    assert MessageRecord.contract_visibility is ContractVisibility.RUNTIME_PRIVATE

    for record_type in (
        ConversationTaskLinkRecord,
        RunTaskLinkRecord,
        EvalExecutionFailureRecord,
        EvalResultRecord,
    ):
        assert record_type.contract_visibility is ContractVisibility.AUDIT_ONLY
        assert record_type.contract_visibility not in {
            ContractVisibility.MODEL_VISIBLE,
            ContractVisibility.USER_VISIBLE,
        }


@pytest.mark.parametrize("timestamp", (datetime(2026, 7, 26, 8, 0), NON_UTC_NOW))
def test_record_timestamps_reject_naive_and_non_utc_values(
    timestamp: datetime,
) -> None:
    with pytest.raises(ValidationError, match="UTC"):
        _conversation(created_at=timestamp)
    with pytest.raises(ValidationError, match="UTC"):
        _message(received_at=timestamp)
    with pytest.raises(ValidationError, match="UTC"):
        _conversation_task_link(linked_at=timestamp)
    with pytest.raises(ValidationError, match="UTC"):
        _conversation_task_link(ended_at=timestamp)
    with pytest.raises(ValidationError, match="UTC"):
        _eval_execution_failure(occurred_at=timestamp)
    with pytest.raises(ValidationError, match="UTC"):
        _eval_result(completed_at=timestamp)


def test_trusted_owner_scope_is_a_minimal_application_projection() -> None:
    context = CustomerContext(
        subject_ref="subject-A",
        customer_id="customer-A",
        auth_scopes=frozenset({"orders:read"}),
        authenticated_at=UTC_NOW,
        session_ref_hash="safe-session-hash",
    )
    owner_scope = TrustedOwnerScope.from_customer_context(context)

    assert owner_scope.customer_id == "customer-A"
    assert set(type(owner_scope).model_fields) == {"customer_id"}
    assert TrustedOwnerScope.contract_visibility is ContractVisibility.RUNTIME_PRIVATE
    assert TrustedOwnerScope.model_config["strict"] is True
    assert TrustedOwnerScope.model_config["frozen"] is True
    assert TrustedOwnerScope.model_config["extra"] == "forbid"
    assert "subject_ref" not in owner_scope.model_dump()
    assert "auth_scopes" not in owner_scope.model_dump()
    assert "authenticated_at" not in owner_scope.model_dump()
    assert "session_ref_hash" not in owner_scope.model_dump()
    with pytest.raises(ValidationError, match="derived from CustomerContext"):
        TrustedOwnerScope(customer_id="customer-A")
    with pytest.raises(ValidationError, match="must match CustomerContext"):
        TrustedOwnerScope.model_validate(
            {"customer_id": "customer-B"},
            context={"customer_context": context},
        )
    with pytest.raises(ValidationError, match="Extra inputs"):
        TrustedOwnerScope.model_validate(
            {
                "customer_id": "customer-A",
                "session_ref_hash": "must-not-cross-port",
            },
            context={"customer_context": context},
        )


def test_message_content_is_non_empty_and_bounded_at_4000_characters() -> None:
    assert len(_message(content="x" * 4000).content) == 4000
    with pytest.raises(ValidationError, match="at most 4000 characters"):
        _message(content="x" * 4001)
    with pytest.raises(ValidationError, match="at least 1 character"):
        _message(content="")


def test_conversation_task_link_lifecycle_is_ordered() -> None:
    active = _conversation_task_link()
    ended = _conversation_task_link(ended_at=UTC_NOW + timedelta(seconds=1))

    assert active.ended_at is None
    assert ended.ended_at is not None
    with pytest.raises(ValidationError, match="cannot precede"):
        _conversation_task_link(ended_at=UTC_NOW - timedelta(seconds=1))


def test_run_task_link_versions_cover_active_and_terminal_projections() -> None:
    active = _run_task_link(
        base_task_state_version=3,
        result_task_state_version=None,
    )
    terminal = _run_task_link(
        base_task_state_version=3,
        result_task_state_version=5,
    )
    new_task_terminal = _run_task_link(
        base_task_state_version=None,
        result_task_state_version=1,
    )

    assert active.result_task_state_version is None
    assert terminal.result_task_state_version == 5
    assert new_task_terminal.base_task_state_version is None
    with pytest.raises(ValidationError, match="cannot precede"):
        _run_task_link(
            base_task_state_version=3,
            result_task_state_version=2,
        )
    with pytest.raises(ValidationError, match="greater than or equal to 1"):
        _run_task_link(base_task_state_version=0)
    with pytest.raises(ValidationError, match="greater than or equal to 1"):
        _run_task_link(result_task_state_version=0)


def test_run_commands_freeze_insert_exact_start_and_recovery_claim() -> None:
    created = _run()
    running = _project_run(created, status=AgentRunStatus.RUNNING)
    completed_at = UTC_NOW + timedelta(milliseconds=1)
    incomplete = _project_run(
        running,
        status=AgentRunStatus.INCOMPLETE,
        completed_at=completed_at,
        stop_reason=StopReason.PROCESS_RESTART_DETECTED,
    )

    assert CreateRunCommand(created_record=created).created_record.status is (
        AgentRunStatus.CREATED
    )
    assert (
        TransitionRunCommand(
            expected_active_record=created,
            next_record=running,
        ).next_record.status
        is AgentRunStatus.RUNNING
    )
    recovery = MarkRunIncompleteForRecoveryCommand(
        expected_active_record=running,
        incomplete_record=incomplete,
    )
    assert recovery.incomplete_record.incomplete_reason is None
    with_reason = MarkRunIncompleteForRecoveryCommand(
        expected_active_record=running,
        incomplete_record=_project_run(
            incomplete,
            incomplete_reason="PROCESS_RESTART_DETECTED",
        ),
    )
    assert with_reason.incomplete_record.incomplete_reason == (
        "PROCESS_RESTART_DETECTED"
    )

    with pytest.raises(ValidationError, match="requires CREATED"):
        CreateRunCommand(created_record=running)
    with pytest.raises(ValidationError, match="change stable fields"):
        TransitionRunCommand(
            expected_active_record=created,
            next_record=_project_run(running, provider_lane="other-lane"),
        )
    with pytest.raises(ValidationError, match="expects CREATED"):
        TransitionRunCommand(
            expected_active_record=running,
            next_record=running,
        )
    with pytest.raises(ValidationError, match="expects CREATED"):
        TransitionRunCommand(
            expected_active_record=running,
            next_record=incomplete,
        )
    with pytest.raises(ValidationError, match="requires RUNNING"):
        TransitionRunCommand(
            expected_active_record=created,
            next_record=created,
        )
    with pytest.raises(ValidationError, match="incomplete_reason must be absent"):
        MarkRunIncompleteForRecoveryCommand(
            expected_active_record=running,
            incomplete_record=_project_run(
                incomplete,
                incomplete_reason="USER_CANCELLED",
            ),
        )
    with pytest.raises(ValidationError, match="cannot change stable fields"):
        MarkRunIncompleteForRecoveryCommand(
            expected_active_record=running,
            incomplete_record=_project_run(incomplete, conversation_id=uuid4()),
        )


def test_initial_write_commands_are_insert_only_version_one_projections() -> None:
    task = CreateTaskCommand(
        initial_record=_task(status=TaskStatus.WAITING_USER),
    )
    request_unit = CreateRequestUnitCommand(
        initial_record=_request_unit(status=TaskStatus.WAITING_USER),
    )
    link = CreateRunTaskLinkCommand(active_record=_run_task_link())

    assert task.initial_record.state_version == 1
    assert task.initial_record.status is TaskStatus.WAITING_USER
    assert request_unit.initial_record.state_version == 1
    assert request_unit.initial_record.status is TaskStatus.WAITING_USER
    assert link.active_record.result_task_state_version is None

    with pytest.raises(ValidationError, match="state_version = 1"):
        CreateTaskCommand(initial_record=_task(state_version=2))
    with pytest.raises(ValidationError, match="state_version = 1"):
        CreateRequestUnitCommand(initial_record=_request_unit(state_version=2))
    with pytest.raises(ValidationError, match="requires result_task_state_version"):
        CreateRunTaskLinkCommand(
            active_record=_run_task_link(result_task_state_version=2)
        )


def test_tool_create_and_dispatch_commands_freeze_the_durable_fence() -> None:
    created = _tool_call(status=ToolCallStatus.CREATED, attempt_count=0)
    running = _project_tool_call(
        created,
        status=ToolCallStatus.RUNNING,
        attempt_count=1,
    )
    attempt = ToolAttemptRecord(
        tool_call_id=created.tool_call_id,
        attempt_no=1,
        started_at=UTC_NOW,
    )

    create_command = CreateToolCallCommand(created_record=created)
    dispatch_command = DispatchToolCallCommand(
        expected_created_record=created,
        running_record=running,
        started_attempt=attempt,
    )
    assert create_command.created_record.status is ToolCallStatus.CREATED
    assert dispatch_command.running_record.attempt_count == 1
    assert dispatch_command.started_attempt.outcome is None

    with pytest.raises(ValidationError, match="requires CREATED"):
        CreateToolCallCommand(created_record=running)
    with pytest.raises(ValidationError, match="terminal or result"):
        CreateToolCallCommand(
            created_record=_project_tool_call(created, result_ref=uuid4())
        )
    with pytest.raises(ValidationError, match="immutable ToolCall"):
        DispatchToolCallCommand(
            expected_created_record=created,
            running_record=_project_tool_call(running, effect=ToolEffect.ACTION),
            started_attempt=attempt,
        )
    with pytest.raises(ValidationError, match="ids must match"):
        DispatchToolCallCommand(
            expected_created_record=created,
            running_record=running,
            started_attempt=ToolAttemptRecord(
                tool_call_id=uuid4(),
                attempt_no=1,
                started_at=UTC_NOW,
            ),
        )
    with pytest.raises(ValidationError, match="first attempt only"):
        DispatchToolCallCommand(
            expected_created_record=created,
            running_record=_project_tool_call(running, attempt_count=2),
            started_attempt=ToolAttemptRecord(
                tool_call_id=created.tool_call_id,
                attempt_no=2,
                started_at=UTC_NOW,
            ),
        )
    with pytest.raises(ValidationError, match="unfinished attempt"):
        DispatchToolCallCommand(
            expected_created_record=created,
            running_record=running,
            started_attempt=ToolAttemptRecord(
                tool_call_id=created.tool_call_id,
                attempt_no=1,
                started_at=UTC_NOW,
                finished_at=UTC_NOW + timedelta(milliseconds=1),
                outcome=ToolResultOutcome.SUCCESS,
            ),
        )


def test_tool_finalize_command_freezes_expected_running_projection() -> None:
    running = _tool_call(status=ToolCallStatus.RUNNING, attempt_count=1)
    finished_at = UTC_NOW + timedelta(milliseconds=1)
    started_attempt = ToolAttemptRecord(
        tool_call_id=running.tool_call_id,
        attempt_no=1,
        started_at=UTC_NOW,
    )
    terminal = _project_tool_call(
        running,
        status=ToolCallStatus.SUCCEEDED,
        finished_at=finished_at,
        result_ref=uuid4(),
    )
    attempt = ToolAttemptRecord(
        tool_call_id=running.tool_call_id,
        attempt_no=1,
        started_at=UTC_NOW,
        finished_at=finished_at,
        outcome=ToolResultOutcome.SUCCESS,
    )

    command = FinalizeToolCallCommand(
        expected_running_record=running,
        expected_started_attempt=started_attempt,
        terminal_record=terminal,
        finalized_attempt=attempt,
    )
    assert command.terminal_record.status is ToolCallStatus.SUCCEEDED
    assert command.finalized_attempt.outcome is ToolResultOutcome.SUCCESS

    with pytest.raises(ValidationError, match="must remain unfinished"):
        FinalizeToolCallCommand(
            expected_running_record=running,
            expected_started_attempt=attempt,
            terminal_record=terminal,
            finalized_attempt=attempt,
        )
    with pytest.raises(ValidationError, match="immutable fields"):
        FinalizeToolCallCommand(
            expected_running_record=running,
            expected_started_attempt=started_attempt,
            terminal_record=_project_tool_call(terminal, effect=ToolEffect.ACTION),
            finalized_attempt=attempt,
        )
    with pytest.raises(ValidationError, match="status and attempt outcome"):
        FinalizeToolCallCommand(
            expected_running_record=running,
            expected_started_attempt=started_attempt,
            terminal_record=_project_tool_call(
                terminal,
                status=ToolCallStatus.FAILED,
                result_ref=None,
            ),
            finalized_attempt=attempt,
        )
    with pytest.raises(ValidationError, match="timestamps must match"):
        FinalizeToolCallCommand(
            expected_running_record=running,
            expected_started_attempt=started_attempt,
            terminal_record=terminal,
            finalized_attempt=ToolAttemptRecord(
                tool_call_id=running.tool_call_id,
                attempt_no=1,
                started_at=UTC_NOW,
                finished_at=finished_at + timedelta(milliseconds=1),
                outcome=ToolResultOutcome.SUCCESS,
            ),
        )
    with pytest.raises(ValidationError, match="preserve started attempt"):
        FinalizeToolCallCommand(
            expected_running_record=running,
            expected_started_attempt=started_attempt,
            terminal_record=terminal,
            finalized_attempt=ToolAttemptRecord(
                tool_call_id=running.tool_call_id,
                attempt_no=1,
                started_at=UTC_NOW + timedelta(microseconds=1),
                finished_at=finished_at,
                outcome=ToolResultOutcome.SUCCESS,
            ),
        )
    with pytest.raises(ValidationError, match="first"):
        FinalizeToolCallCommand(
            expected_running_record=_project_tool_call(
                running,
                attempt_count=2,
            ),
            expected_started_attempt=ToolAttemptRecord(
                tool_call_id=running.tool_call_id,
                attempt_no=2,
                started_at=UTC_NOW,
            ),
            terminal_record=_project_tool_call(
                terminal,
                attempt_count=2,
            ),
            finalized_attempt=ToolAttemptRecord(
                tool_call_id=running.tool_call_id,
                attempt_no=2,
                started_at=UTC_NOW,
                finished_at=finished_at,
                outcome=ToolResultOutcome.SUCCESS,
            ),
        )


def test_restart_tool_command_preserves_identity_attempt_and_action_effect() -> None:
    created_action = _tool_call(
        status=ToolCallStatus.CREATED,
        attempt_count=0,
        effect=ToolEffect.ACTION,
    )
    interrupted = _project_tool_call(
        created_action,
        status=ToolCallStatus.INTERRUPTED,
        finished_at=UTC_NOW + timedelta(milliseconds=1),
        interruption_reason="PROCESS_RESTART_DETECTED",
    )
    command = InterruptToolCallForRecoveryCommand(
        active_record=created_action,
        interrupted_record=interrupted,
    )

    assert command.active_record.attempt_count == 0
    assert command.interrupted_record.effect is ToolEffect.ACTION
    with pytest.raises(ValidationError, match="PROCESS_RESTART_DETECTED"):
        InterruptToolCallForRecoveryCommand(
            active_record=created_action,
            interrupted_record=_project_tool_call(
                interrupted,
                interruption_reason="USER_CANCELLED",
            ),
        )
    with pytest.raises(ValidationError, match="preserve ToolCall identity"):
        InterruptToolCallForRecoveryCommand(
            active_record=created_action,
            interrupted_record=_project_tool_call(
                interrupted,
                effect=ToolEffect.READ,
            ),
        )
    dirty_active = _project_tool_call(created_action, result_ref=uuid4())
    with pytest.raises(ValidationError, match="cannot carry failure or result"):
        InterruptToolCallForRecoveryCommand(
            active_record=dirty_active,
            interrupted_record=_project_tool_call(
                dirty_active,
                status=ToolCallStatus.INTERRUPTED,
                finished_at=UTC_NOW + timedelta(milliseconds=1),
                interruption_reason="PROCESS_RESTART_DETECTED",
            ),
        )

    running_retry = _tool_call(
        status=ToolCallStatus.RUNNING,
        attempt_count=2,
    )
    with pytest.raises(ValidationError, match="does not accept retry"):
        InterruptToolCallForRecoveryCommand(
            active_record=running_retry,
            interrupted_record=_project_tool_call(
                running_retry,
                status=ToolCallStatus.INTERRUPTED,
                finished_at=UTC_NOW + timedelta(milliseconds=1),
                interruption_reason="PROCESS_RESTART_DETECTED",
            ),
        )


def test_request_understanding_command_closes_the_exact_accepted_child_set() -> None:
    graph = _initial_graph()
    command = graph.request_understanding
    child = command.accepted_deltas[0]

    assert set(command.record.accepted_delta_refs) == {child.accepted_delta_id}
    with pytest.raises(ValidationError):
        SaveRequestUnderstandingCommand(
            record=command.record,
            accepted_deltas=(),
        )
    with pytest.raises(ValidationError):
        SaveRequestUnderstandingCommand(
            record=_rebuild(
                command.record,
                accepted_delta_refs=(
                    child.accepted_delta_id,
                    child.accepted_delta_id,
                ),
            ),
            accepted_deltas=(child, child),
        )
    with pytest.raises(ValidationError, match="message_ref"):
        SaveRequestUnderstandingCommand(
            record=command.record,
            accepted_deltas=(_rebuild(child, message_ref=uuid4()),),
        )
    with pytest.raises(ValidationError, match="accepted candidate"):
        SaveRequestUnderstandingCommand(
            record=command.record,
            accepted_deltas=(_rebuild(child, candidate_ref=uuid4()),),
        )


def test_initial_task_graph_binds_trusted_roots_children_and_relations() -> None:
    graph = _initial_graph()
    task = graph.initial_task.initial_record
    request_unit = graph.initial_request_unit.initial_record
    binding = graph.input_bindings[0]

    assert graph.owner_scope.customer_id == task.owner_customer_id
    assert graph.expected_message_record.direction is MessageDirection.USER
    assert graph.expected_active_run_record.status is AgentRunStatus.RUNNING
    assert graph.request_understanding.record.run_id == (
        graph.expected_active_run_record.run_id
    )
    assert binding.request_unit_id == request_unit.request_unit_id
    assert set(request_unit.input_binding_refs) == {binding.record.binding_id}
    assert graph.conversation_task_link.task_id == task.task_id
    assert graph.run_task_link.active_record.task_id == task.task_id
    assert graph.run_task_link.active_record.base_task_state_version is None

    with pytest.raises(ValidationError, match="trusted owner scope"):
        _rebuild(graph, owner_scope=_owner_scope("customer-B"))
    with pytest.raises(ValidationError, match="USER message"):
        _rebuild(
            graph,
            expected_message_record=_rebuild(
                graph.expected_message_record,
                direction=MessageDirection.ASSISTANT,
            ),
        )
    with pytest.raises(ValidationError, match="Conversation"):
        _rebuild(
            graph,
            expected_message_record=_rebuild(
                graph.expected_message_record,
                conversation_id=uuid4(),
            ),
        )
    with pytest.raises(ValidationError, match="RUNNING"):
        _rebuild(
            graph,
            expected_active_run_record=_project_run(
                graph.expected_active_run_record,
                status=AgentRunStatus.CREATED,
            ),
        )
    with pytest.raises(ValidationError, match="clean active Run"):
        _rebuild(
            graph,
            expected_active_run_record=_project_run(
                graph.expected_active_run_record,
                incomplete_reason="PROCESS_RESTART_DETECTED",
            ),
        )
    with pytest.raises(ValidationError, match="Run"):
        _rebuild(
            graph,
            expected_active_run_record=_project_run(
                graph.expected_active_run_record,
                conversation_id=uuid4(),
            ),
        )
    with pytest.raises(ValidationError, match="RequestUnderstanding"):
        _rebuild(
            graph,
            request_understanding=_rebuild(
                graph.request_understanding,
                record=_rebuild(
                    graph.request_understanding.record,
                    run_id=uuid4(),
                ),
            ),
        )
    with pytest.raises(ValidationError, match="InputBinding source"):
        _rebuild(
            graph,
            input_bindings=(
                _rebuild(
                    binding,
                    record=_rebuild(binding.record, source_refs=(uuid4(),)),
                ),
            ),
        )
    with pytest.raises(ValidationError):
        _rebuild(graph, input_bindings=(binding, binding))
    with pytest.raises(ValidationError, match="RequestUnit"):
        _rebuild(
            graph,
            initial_request_unit=CreateRequestUnitCommand(
                initial_record=_rebuild(request_unit, task_id=uuid4())
            ),
        )
    with pytest.raises(ValidationError, match="ConversationTaskLink"):
        _rebuild(
            graph,
            conversation_task_link=_rebuild(
                graph.conversation_task_link,
                task_id=uuid4(),
            ),
        )
    with pytest.raises(ValidationError, match="RunTaskLink"):
        _rebuild(
            graph,
            run_task_link=CreateRunTaskLinkCommand(
                active_record=_rebuild(
                    graph.run_task_link.active_record,
                    run_id=uuid4(),
                )
            ),
        )

    first_delta = graph.request_understanding.accepted_deltas[0]
    second_candidate_ref = uuid4()
    second_delta = _rebuild(
        first_delta,
        accepted_delta_id=uuid4(),
        candidate_ref=second_candidate_ref,
    )
    with pytest.raises(ValidationError):
        SaveRequestUnderstandingCommand(
            record=_rebuild(
                graph.request_understanding.record,
                candidate_validation=(
                    *graph.request_understanding.record.candidate_validation,
                    CandidateValidationRecord(
                        candidate_ref=second_candidate_ref,
                        decision=CandidateValidationDecision.ACCEPT,
                    ),
                ),
                accepted_delta_refs=(
                    first_delta.accepted_delta_id,
                    second_delta.accepted_delta_id,
                ),
            ),
            accepted_deltas=(first_delta, second_delta),
        )


def test_task_transition_command_is_one_exact_task_request_unit_aggregate() -> None:
    command = _task_transition_command()

    assert command.task_state_transition.base_state_version == (
        command.expected_task_record.state_version
    )
    assert command.task_state_transition.result_state_version == (
        command.next_request_unit_record.state_version
    )
    assert command.expected_task_record.status is (
        command.task_state_transition.from_status
    )
    assert command.next_request_unit_record.status is (
        command.task_state_transition.to_status
    )

    with pytest.raises(ValidationError, match="Task identity"):
        _rebuild(
            command,
            next_task_record=_rebuild(
                command.next_task_record,
                task_id=uuid4(),
            ),
        )
    with pytest.raises(ValidationError, match="Task owner"):
        _rebuild(
            command,
            next_task_record=_rebuild(
                command.next_task_record,
                owner_customer_id="customer-B",
            ),
        )
    with pytest.raises(ValidationError, match="Task stable fields"):
        _rebuild(
            command,
            next_task_record=_rebuild(
                command.next_task_record,
                created_at=UTC_NOW - timedelta(seconds=1),
            ),
        )
    with pytest.raises(ValidationError, match="RequestUnit identity"):
        _rebuild(
            command,
            next_request_unit_record=_rebuild(
                command.next_request_unit_record,
                request_unit_id=uuid4(),
            ),
        )
    with pytest.raises(ValidationError, match="RequestUnit stable fields"):
        _rebuild(
            command,
            next_request_unit_record=_rebuild(
                command.next_request_unit_record,
                goal_text="另一个目标",
            ),
        )
    with pytest.raises(ValidationError, match="base version"):
        _rebuild(
            command,
            expected_task_record=_rebuild(
                command.expected_task_record,
                state_version=2,
            ),
        )
    with pytest.raises(ValidationError, match="status"):
        _rebuild(
            command,
            next_request_unit_record=_rebuild(
                command.next_request_unit_record,
                status=TaskStatus.BLOCKED,
            ),
        )


def test_observation_command_requires_exact_successful_read_get_order_source() -> None:
    observation = _observation()
    source = _tool_call(
        status=ToolCallStatus.SUCCEEDED,
        attempt_count=1,
        finished_at=UTC_NOW + timedelta(milliseconds=1),
        result_ref=uuid4(),
    )
    command = SaveObservationCommand(
        owner_scope=_owner_scope(),
        observation_record=observation,
        source_tool_call_record=source,
    )

    assert command.source_tool_call_record.tool_call_id != (
        command.observation_record.observation_id
    )
    assert command.source_tool_call_record.result_ref != (
        command.observation_record.observation_id
    )
    with pytest.raises(ValidationError, match="SUCCEEDED"):
        SaveObservationCommand(
            owner_scope=_owner_scope(),
            observation_record=observation,
            source_tool_call_record=_tool_call(
                status=ToolCallStatus.RUNNING,
                attempt_count=1,
            ),
        )
    with pytest.raises(ValidationError, match="READ"):
        SaveObservationCommand(
            owner_scope=_owner_scope(),
            observation_record=observation,
            source_tool_call_record=_tool_call(
                status=ToolCallStatus.SUCCEEDED,
                attempt_count=1,
                effect=ToolEffect.ACTION,
                finished_at=UTC_NOW + timedelta(milliseconds=1),
            ),
        )
    with pytest.raises(ValidationError, match="get_order"):
        SaveObservationCommand(
            owner_scope=_owner_scope(),
            observation_record=observation,
            source_tool_call_record=_project_tool_call(
                source,
                canonical_tool_name="create_refund",
            ),
        )
    assert set(ObservationWriteResult) == {
        ObservationWriteResult.INSERTED,
        ObservationWriteResult.ALREADY_APPLIED,
        ObservationWriteResult.SOURCE_PROJECTION_CONFLICT,
    }


@pytest.mark.parametrize(
    ("stop_reason", "with_task", "outcome", "task_status"),
    _COMPLETED_TERMINAL_MATRIX,
    ids=(
        "goal-completed-with-task",
        "not-found-with-task",
        "provider-protocol-without-task",
        "provider-protocol-with-task",
        "input-invalid-without-task",
        "gate-rejected-with-task",
        "order-service-unavailable-with-task",
        "presentation-plan-rejected-with-task",
        "renderer-invariant-failed-with-task",
    ),
)
def test_run_finalization_accepts_only_the_nine_completed_terminal_rows(
    stop_reason: StopReason,
    with_task: bool,
    outcome: AgentOutcome,
    task_status: TaskStatus | None,
) -> None:
    command = _completed_finalization(
        stop_reason=stop_reason,
        outcome=outcome,
        with_task=with_task,
        task_status=task_status,
    )

    assert command.terminal_record.status is AgentRunStatus.COMPLETED
    assert command.terminal_result is not None
    assert command.terminal_result.outcome is outcome
    assert command.assistant_message is not None
    assert command.assistant_message.content == command.terminal_result.message
    assert command.terminal_trace_events[-1].event_type is TraceEventType.RUN_STOPPED
    if with_task:
        assert command.task_transition is not None
        assert command.task_transition.next_task_record.status is task_status
        assert command.result_task_records == (
            command.task_transition.next_task_record,
        )
        assert tuple(
            event.event_type for event in command.terminal_trace_events
        ) == (
            TraceEventType.TASK_STATE_CHANGED,
            TraceEventType.RUN_STOPPED,
        )
    else:
        assert command.task_transition is None
        assert command.result_task_records == ()
        assert tuple(
            event.event_type for event in command.terminal_trace_events
        ) == (TraceEventType.RUN_STOPPED,)


def test_completed_run_requires_result_message_and_run_stopped() -> None:
    command = _completed_finalization()

    with pytest.raises(ValidationError, match="Task transition"):
        _rebuild(command, task_transition=None)
    with pytest.raises(ValidationError, match="terminal result"):
        _rebuild(command, terminal_result=None)
    with pytest.raises(ValidationError, match="ASSISTANT Message"):
        _rebuild(command, assistant_message=None)
    with pytest.raises(ValidationError, match="RunStopped"):
        _rebuild(
            command,
            terminal_trace_events=(command.terminal_trace_events[0],),
        )
    no_task = _completed_finalization(
        stop_reason=StopReason.INPUT_INVALID,
        outcome=AgentOutcome.BLOCKED,
        with_task=False,
        task_status=None,
    )
    with pytest.raises(ValidationError, match="Task transition"):
        _rebuild(no_task, task_transition=command.task_transition)
    with pytest.raises(ValidationError, match="RunStopped"):
        _rebuild(no_task, terminal_trace_events=())


def test_completed_run_rejects_omitted_reason_outcome_task_cross_products() -> None:
    with_task = _completed_finalization()
    without_task = _completed_finalization(
        stop_reason=StopReason.PROVIDER_PROTOCOL_ERROR,
        outcome=AgentOutcome.BLOCKED,
        with_task=False,
        task_status=None,
    )

    unsupported_no_task_reason = StopReason.GATE_REJECTED
    with pytest.raises(ValidationError, match="closed terminal matrix"):
        _rebuild(
            without_task,
            terminal_record=_project_run(
                without_task.terminal_record,
                stop_reason=unsupported_no_task_reason,
            ),
            terminal_trace_events=_updated_terminal_trace_events(
                without_task,
                TraceEventType.RUN_STOPPED,
                stop_reason=unsupported_no_task_reason,
            ),
        )

    unsupported_task_reason = StopReason.INPUT_INVALID
    with pytest.raises(ValidationError, match="closed terminal matrix"):
        _rebuild(
            with_task,
            terminal_record=_project_run(
                with_task.terminal_record,
                stop_reason=unsupported_task_reason,
            ),
            terminal_trace_events=_updated_terminal_trace_events(
                with_task,
                TraceEventType.RUN_STOPPED,
                stop_reason=unsupported_task_reason,
            ),
        )

    for omitted_outcome in (
        AgentOutcome.ASK_USER,
        AgentOutcome.NEED_HUMAN,
        AgentOutcome.BLOCKED,
    ):
        with pytest.raises(ValidationError, match="closed terminal matrix"):
            _rebuild(
                with_task,
                terminal_result=_rebuild(
                    with_task.terminal_result,
                    outcome=omitted_outcome,
                ),
                terminal_trace_events=_updated_terminal_trace_events(
                    with_task,
                    TraceEventType.RUN_STOPPED,
                    user_outcome=omitted_outcome,
                ),
            )

    task_id = with_task.expected_active_links[0].task_id
    request_unit_id = (
        with_task.task_transition.next_request_unit_record.request_unit_id
    )
    blocked_transition = _terminal_task_transition(
        task_id=task_id,
        request_unit_id=request_unit_id,
        terminal_status=TaskStatus.BLOCKED,
    )
    with pytest.raises(ValidationError, match="closed terminal matrix"):
        _rebuild(
            with_task,
            task_transition=blocked_transition,
            result_task_records=(blocked_transition.next_task_record,),
            terminal_trace_events=_updated_terminal_trace_events(
                with_task,
                TraceEventType.TASK_STATE_CHANGED,
                task_id=blocked_transition.next_task_record.task_id,
                request_unit_id=(
                    blocked_transition.next_request_unit_record.request_unit_id
                ),
                occurred_at=blocked_transition.task_state_transition.changed_at,
            ),
        )

    cancelled_transition = _terminal_task_transition(
        task_id=task_id,
        request_unit_id=request_unit_id,
        terminal_status=TaskStatus.CANCELLED,
    )
    with pytest.raises(ValidationError, match="closed terminal matrix"):
        _rebuild(
            with_task,
            task_transition=cancelled_transition,
            result_task_records=(cancelled_transition.next_task_record,),
            terminal_trace_events=_updated_terminal_trace_events(
                with_task,
                TraceEventType.TASK_STATE_CHANGED,
                task_id=cancelled_transition.next_task_record.task_id,
                request_unit_id=(
                    cancelled_transition.next_request_unit_record.request_unit_id
                ),
                occurred_at=cancelled_transition.task_state_transition.changed_at,
            ),
        )


def test_completed_run_binds_every_foreign_identity_to_one_terminal_turn() -> None:
    command = _completed_finalization()

    with pytest.raises(ValidationError, match="terminal result.*Run"):
        _rebuild(
            command,
            terminal_result=_rebuild(command.terminal_result, run_id=uuid4()),
        )
    with pytest.raises(ValidationError, match="ASSISTANT Message.*Conversation"):
        _rebuild(
            command,
            assistant_message=_rebuild(
                command.assistant_message,
                conversation_id=uuid4(),
            ),
        )
    with pytest.raises(ValidationError, match="conversation_id"):
        _rebuild(
            command,
            terminal_record=_project_run(
                command.terminal_record,
                conversation_id=None,
            ),
        )

    foreign_transition = _terminal_task_transition(
        task_id=uuid4(),
        request_unit_id=uuid4(),
        terminal_status=TaskStatus.COMPLETED,
    )
    with pytest.raises(ValidationError, match="link Task"):
        _rebuild(
            command,
            task_transition=foreign_transition,
            result_task_records=(foreign_transition.next_task_record,),
        )

    same_task_foreign_unit = _terminal_task_transition(
        task_id=command.expected_active_links[0].task_id,
        request_unit_id=uuid4(),
        terminal_status=TaskStatus.COMPLETED,
    )
    with pytest.raises(ValidationError, match="TaskStateChanged"):
        _rebuild(
            command,
            task_transition=same_task_foreign_unit,
            result_task_records=(same_task_foreign_unit.next_task_record,),
        )

    with pytest.raises(ValidationError, match="terminal Trace.*Run"):
        _rebuild(
            command,
            terminal_trace_events=_updated_terminal_trace_events(
                command,
                TraceEventType.TASK_STATE_CHANGED,
                run_id=uuid4(),
            ),
        )
    with pytest.raises(ValidationError, match="terminal Trace.*Run"):
        _rebuild(
            command,
            terminal_trace_events=_updated_terminal_trace_events(
                command,
                TraceEventType.RUN_STOPPED,
                run_id=uuid4(),
            ),
        )


@pytest.mark.parametrize(
    "updates",
    (
        {"schema_version": "message_record.p0.v2"},
        {"direction": MessageDirection.USER},
        {"content": "被篡改的回复"},
        {"received_at": UTC_NOW},
    ),
    ids=("schema", "user-direction", "content", "timestamp"),
)
def test_completed_run_rejects_non_exact_assistant_message(
    updates: dict[str, object],
) -> None:
    command = _completed_finalization()

    with pytest.raises(ValidationError, match="ASSISTANT Message"):
        _rebuild(
            command,
            assistant_message=_rebuild(command.assistant_message, **updates),
        )


def test_completed_run_terminal_trace_is_complete_ordered_and_unique() -> None:
    command = _completed_finalization()
    task_changed, run_stopped = command.terminal_trace_events

    with pytest.raises(ValidationError, match="ordered"):
        _rebuild(
            command,
            terminal_trace_events=(run_stopped, task_changed),
        )
    with pytest.raises(ValidationError, match="identities must be unique"):
        _rebuild(
            command,
            terminal_trace_events=(
                task_changed,
                run_stopped.model_copy(
                    update={"trace_event_id": task_changed.trace_event_id}
                ),
            ),
        )
    with pytest.raises(ValidationError, match="ordered"):
        _rebuild(
            command,
            terminal_trace_events=(run_stopped, run_stopped),
        )
    with pytest.raises(ValidationError, match="ordered"):
        _rebuild(
            command,
            terminal_trace_events=(
                task_changed.model_copy(
                    update={"event_type": TraceEventType.RESPONSE_RENDERED}
                ),
                run_stopped,
            ),
        )

    no_task = _completed_finalization(
        stop_reason=StopReason.PROVIDER_PROTOCOL_ERROR,
        outcome=AgentOutcome.BLOCKED,
        with_task=False,
        task_status=None,
    )
    with pytest.raises(ValidationError, match="only RunStopped"):
        _rebuild(
            no_task,
            terminal_trace_events=(
                TraceEvent(
                    trace_event_id=uuid4(),
                    event_type=TraceEventType.TASK_STATE_CHANGED,
                    occurred_at=no_task.terminal_record.completed_at,
                    run_id=no_task.terminal_record.run_id,
                    task_id=uuid4(),
                    request_unit_id=uuid4(),
                ),
                *no_task.terminal_trace_events,
            ),
        )


def test_completed_run_binds_terminal_trace_timestamps_and_transition_time() -> None:
    command = _completed_finalization()

    with pytest.raises(ValidationError, match="RunStopped.*stop reason"):
        _rebuild(
            command,
            terminal_trace_events=_updated_terminal_trace_events(
                command,
                TraceEventType.RUN_STOPPED,
                stop_reason=StopReason.GATE_REJECTED,
            ),
        )
    with pytest.raises(ValidationError, match="RunStopped.*outcome"):
        _rebuild(
            command,
            terminal_trace_events=_updated_terminal_trace_events(
                command,
                TraceEventType.RUN_STOPPED,
                user_outcome=AgentOutcome.BLOCKED,
            ),
        )
    with pytest.raises(ValidationError, match="TaskStateChanged.*timestamp"):
        _rebuild(
            command,
            terminal_trace_events=_updated_terminal_trace_events(
                command,
                TraceEventType.TASK_STATE_CHANGED,
                occurred_at=UTC_NOW,
            ),
        )
    with pytest.raises(ValidationError, match="RunStopped.*timestamp"):
        _rebuild(
            command,
            terminal_trace_events=_updated_terminal_trace_events(
                command,
                TraceEventType.RUN_STOPPED,
                occurred_at=UTC_NOW,
            ),
        )

    transition = command.task_transition
    changed_after_completion = command.terminal_record.completed_at + timedelta(
        milliseconds=1
    )
    late_transition = _terminal_task_transition(
        task_id=transition.next_task_record.task_id,
        request_unit_id=transition.next_request_unit_record.request_unit_id,
        terminal_status=TaskStatus.COMPLETED,
        changed_at=changed_after_completion,
    )
    with pytest.raises(ValidationError, match="cannot follow Run completion"):
        _rebuild(
            command,
            task_transition=late_transition,
            result_task_records=(late_transition.next_task_record,),
            terminal_trace_events=_updated_terminal_trace_events(
                command,
                TraceEventType.TASK_STATE_CHANGED,
                occurred_at=changed_after_completion,
            ),
        )


@pytest.mark.parametrize(
    ("event_type", "field_name"),
    _TERMINAL_TRACE_CONTAMINATION_CASES,
)
def test_completed_run_terminal_trace_rejects_every_non_allowlisted_projection(
    event_type: TraceEventType,
    field_name: str,
) -> None:
    command = _completed_finalization()

    with pytest.raises(ValidationError):
        _rebuild(
            command,
            terminal_trace_events=_updated_terminal_trace_events(
                command,
                event_type,
                **{field_name: _non_empty_trace_optional_value(field_name)},
            ),
        )


def test_failed_run_closes_links_without_fabricating_terminal_projections() -> None:
    with_task = _failed_finalization()
    without_task = _failed_finalization(with_task=False)

    assert with_task.terminal_record.stop_reason is None
    assert with_task.task_transition is None
    assert with_task.terminal_result is None
    assert with_task.assistant_message is None
    assert with_task.terminal_trace_events == ()
    assert with_task.terminal_links[0].result_task_state_version == (
        with_task.result_task_records[0].state_version
    )
    assert without_task.expected_active_links == ()
    assert without_task.result_task_records == ()


def test_failed_run_rejects_all_four_terminal_turn_projections() -> None:
    failed = _failed_finalization()
    completed = _completed_finalization()
    projection_values = {
        "task_transition": completed.task_transition,
        "terminal_result": completed.terminal_result,
        "assistant_message": completed.assistant_message,
        "terminal_trace_events": completed.terminal_trace_events,
    }

    for field_name, value in projection_values.items():
        with pytest.raises(ValidationError, match="FAILED"):
            _rebuild(failed, **{field_name: value})
    with pytest.raises(ValidationError, match="FAILED.*stop_reason"):
        _rebuild(
            failed,
            terminal_record=_project_run(
                failed.terminal_record,
                stop_reason=StopReason.GOAL_COMPLETED,
            ),
        )


def test_terminal_turn_revalidates_coupled_result_and_message_content() -> None:
    command = _completed_finalization()
    tampered_result = command.terminal_result.model_copy(update={"message": ""})
    tampered_message = command.assistant_message.model_copy(update={"content": ""})

    with pytest.raises(ValidationError):
        _rebuild(tampered_result)
    with pytest.raises(ValidationError):
        _rebuild(tampered_message)
    with pytest.raises(ValidationError, match="canonical"):
        _rebuild(
            command,
            terminal_result=tampered_result,
            assistant_message=tampered_message,
        )


def test_terminal_turn_revalidates_message_identity_without_disclosure() -> None:
    command = _completed_finalization()
    secret = "customer-A SECRET"
    tampered_message = command.assistant_message.model_copy(
        update={"message_id": secret}
    )

    with pytest.raises(ValidationError):
        _rebuild(tampered_message)
    with pytest.raises(ValidationError, match="canonical") as error:
        _rebuild(command, assistant_message=tampered_message)
    _assert_validation_error_is_sanitized(error.value, secret)


def test_terminal_turn_semantic_error_does_not_retain_valid_private_content() -> None:
    command = _completed_finalization()
    customer_id = "customer-A"
    message_content = f"{customer_id} 的订单 O-1001"
    mismatched_message = _rebuild(
        command.assistant_message,
        content=message_content,
    )

    with pytest.raises(ValidationError, match="content") as error:
        _rebuild(command, assistant_message=mismatched_message)
    _assert_validation_error_is_sanitized(
        error.value,
        customer_id,
        message_content,
        "O-1001",
    )


@pytest.mark.parametrize(
    "validate",
    (
        lambda secret: FinalizeRunCommand(unexpected=secret),
        lambda secret: FinalizeRunCommand.model_validate(secret),
        lambda secret: FinalizeRunCommand.model_validate_json(f'"{secret}"'),
        lambda secret: FinalizeRunCommand.model_validate_strings(secret),
    ),
    ids=(
        "constructor",
        "model_validate",
        "model_validate_json",
        "model_validate_strings",
    ),
)
def test_terminal_turn_public_validation_entries_sanitize_raw_input(
    validate: Callable[[str], object],
) -> None:
    secret = "customer-A SECRET"

    with pytest.raises(ValidationError) as error:
        validate(secret)
    _assert_validation_error_is_sanitized(error.value, secret)


def test_terminal_turn_sanitizer_preserves_strict_json_validation() -> None:
    command = _completed_finalization()

    rebuilt = FinalizeRunCommand.model_validate_json(
        command.model_dump_json(),
        strict=True,
    )

    assert rebuilt == command


def test_terminal_turn_model_copy_rejects_invalid_result_and_message() -> None:
    command = _completed_finalization()
    empty_result = command.terminal_result.model_copy(update={"message": ""})
    empty_message = command.assistant_message.model_copy(update={"content": ""})

    for update in (
        {"terminal_result": empty_result},
        {"assistant_message": empty_message},
        {
            "terminal_result": empty_result,
            "assistant_message": empty_message,
        },
    ):
        with pytest.raises(ValidationError, match="canonical"):
            command.model_copy(update=update)


@pytest.mark.parametrize("strict", (False, True))
@pytest.mark.parametrize("bypass", ("BaseModel.model_copy", "model_construct"))
def test_terminal_turn_model_validate_rejects_low_level_invalid_instance(
    strict: bool,
    bypass: str,
) -> None:
    command = _completed_finalization()
    secret = "customer-A 的订单 O-1001 SECRET"
    invalid_result = command.terminal_result.model_copy(
        update={"message": "", "secret": secret}
    )
    invalid_message = command.assistant_message.model_copy(
        update={"content": ""}
    )
    if bypass == "BaseModel.model_copy":
        invalid_outer = BaseModel.model_copy(
            command,
            update={
                "terminal_result": invalid_result,
                "assistant_message": invalid_message,
            },
        )
    else:
        values = {
            field_name: getattr(command, field_name)
            for field_name in FinalizeRunCommand.model_fields
        }
        values["terminal_result"] = invalid_result
        values["assistant_message"] = invalid_message
        invalid_outer = FinalizeRunCommand.model_construct(**values)

    with pytest.raises(ValidationError, match="canonical") as error:
        FinalizeRunCommand.model_validate(invalid_outer, strict=strict)
    _assert_validation_error_is_sanitized(
        error.value,
        secret,
        "customer-A",
        "O-1001",
    )


@pytest.mark.parametrize("strict", (False, True))
def test_terminal_turn_revalidation_rejects_hidden_outer_storage(
    strict: bool,
) -> None:
    command = _completed_finalization()
    secret = "customer-A SECRET"
    invalid_outer = BaseModel.model_copy(
        command,
        update={"secret": secret},
    )

    assert vars(invalid_outer)["secret"] == secret
    assert "secret" in invalid_outer.model_fields_set
    with pytest.raises(ValidationError, match="canonical") as error:
        FinalizeRunCommand.model_validate(invalid_outer, strict=strict)
    _assert_validation_error_is_sanitized(error.value, secret)

    with pytest.raises(ValidationError) as copy_error:
        command.model_copy(update={"secret": secret})
    _assert_validation_error_is_sanitized(copy_error.value, secret)


def test_terminal_turn_valid_copy_revalidation_and_pickle_remain_compatible() -> None:
    command = _completed_finalization()

    shallow = command.model_copy()
    deep = command.model_copy(deep=True)
    revalidated = FinalizeRunCommand.model_validate(command)
    strict_revalidated = FinalizeRunCommand.model_validate(command, strict=True)
    restored = pickle.loads(pickle.dumps(command))

    for rebuilt in (
        shallow,
        deep,
        revalidated,
        strict_revalidated,
        restored,
    ):
        assert type(rebuilt) is FinalizeRunCommand
        assert rebuilt == command
        assert rebuilt.model_fields_set == command.model_fields_set
    assert shallow is not command
    assert shallow.expected_active_record is command.expected_active_record
    assert deep.expected_active_record is not command.expected_active_record


def test_terminal_turn_subclass_copy_preserves_unset_default_factory_value() -> None:
    class FinalizeRunCommandWithNonce(FinalizeRunCommand):
        nonce: UUID = Field(default_factory=uuid4)

    command = _completed_finalization()
    base_values = {
        field_name: getattr(command, field_name)
        for field_name in FinalizeRunCommand.model_fields
    }
    extended = FinalizeRunCommandWithNonce(**base_values)
    original_fields_set = extended.model_fields_set
    replacement_nonce = uuid4()

    shallow = extended.model_copy()
    deep = extended.model_copy(deep=True)
    updated = extended.model_copy(update={"nonce": replacement_nonce})

    assert "nonce" not in original_fields_set
    assert shallow.nonce == extended.nonce
    assert deep.nonce == extended.nonce
    assert shallow.model_fields_set == original_fields_set
    assert deep.model_fields_set == original_fields_set
    assert updated.nonce == replacement_nonce
    assert updated.model_fields_set == original_fields_set | {"nonce"}


def test_terminal_turn_frozen_assignment_sanitizes_raw_input() -> None:
    command = _completed_finalization()
    secret = "customer-A SECRET"

    with pytest.raises(ValidationError, match="Instance is frozen") as error:
        command.assistant_message = secret
    _assert_validation_error_is_sanitized(error.value, secret)


def test_terminal_turn_recursively_revalidates_nested_task_transition() -> None:
    command = _completed_finalization()
    secret = "customer-A SECRET"
    transition = command.task_transition
    tampered_state_transition = transition.task_state_transition.model_copy(
        update={"reason_ref": secret}
    )
    tampered_transition = transition.model_copy(
        update={"task_state_transition": tampered_state_transition}
    )

    with pytest.raises(ValidationError):
        _rebuild(tampered_state_transition)
    with pytest.raises(ValidationError, match="canonical") as error:
        _rebuild(command, task_transition=tampered_transition)
    _assert_validation_error_is_sanitized(error.value, secret)


def test_terminal_turn_rejects_non_exact_new_projection_model_types() -> None:
    command = _completed_finalization()

    class ResultSubclass(AgentRunResult):
        pass

    class MessageSubclass(MessageRecord):
        pass

    class TaskTransitionSubclass(ApplyTaskTransitionCommand):
        pass

    class TraceEventSubclass(TraceEvent):
        pass

    forged_result = ResultSubclass(
        **{
            field_name: getattr(command.terminal_result, field_name)
            for field_name in AgentRunResult.model_fields
        }
    )
    forged_message = MessageSubclass(
        **{
            field_name: getattr(command.assistant_message, field_name)
            for field_name in MessageRecord.model_fields
        }
    )
    forged_transition = TaskTransitionSubclass(
        **{
            field_name: getattr(command.task_transition, field_name)
            for field_name in ApplyTaskTransitionCommand.model_fields
        }
    )
    task_changed, run_stopped = command.terminal_trace_events
    forged_task_changed = TraceEventSubclass(
        **{
            field_name: getattr(task_changed, field_name)
            for field_name in TraceEvent.model_fields
        }
    )

    for field_name, value in (
        ("terminal_result", forged_result),
        ("assistant_message", forged_message),
        ("task_transition", forged_transition),
        (
            "terminal_trace_events",
            (forged_task_changed, run_stopped),
        ),
    ):
        with pytest.raises(ValidationError, match="canonical|exact"):
            _rebuild(command, **{field_name: value})


def test_terminal_turn_rejects_hidden_outer_and_nested_model_storage() -> None:
    command = _completed_finalization()
    secret = "customer-A SECRET"
    tampered_result = command.terminal_result.model_copy(update={"secret": secret})
    tampered_message = command.assistant_message.model_copy(update={"secret": secret})
    tampered_next_task = command.task_transition.next_task_record.model_copy(
        update={"secret": secret}
    )
    tampered_transition = command.task_transition.model_copy(
        update={"next_task_record": tampered_next_task}
    )
    tampered_next_unit = (
        command.task_transition.next_request_unit_record.model_copy(
            update={"secret": secret}
        )
    )
    tampered_unit_transition = command.task_transition.model_copy(
        update={"next_request_unit_record": tampered_next_unit}
    )
    task_changed, run_stopped = command.terminal_trace_events
    tampered_task_changed = task_changed.model_copy(update={"secret": secret})

    for field_name, value in (
        ("terminal_result", tampered_result),
        ("assistant_message", tampered_message),
        ("task_transition", tampered_transition),
        ("task_transition", tampered_unit_transition),
        (
            "terminal_trace_events",
            (tampered_task_changed, run_stopped),
        ),
    ):
        with pytest.raises(ValidationError, match="canonical") as error:
            _rebuild(command, **{field_name: value})
        _assert_validation_error_is_sanitized(error.value, secret)


def test_completed_task_transition_respects_active_link_base_lower_bound() -> None:
    with pytest.raises(ValidationError, match="active link base Task version"):
        _completed_finalization(
            active_link_base_state_version=2,
            transition_base_state_version=1,
        )

    equal_base = _completed_finalization(
        active_link_base_state_version=2,
        transition_base_state_version=2,
    )
    advanced_before_terminal_turn = _completed_finalization(
        active_link_base_state_version=2,
        transition_base_state_version=3,
    )
    newly_created_task = _completed_finalization(
        active_link_base_state_version=None,
        transition_base_state_version=1,
    )
    failed_with_current_projection = _failed_finalization(
        active_link_base_state_version=2,
        current_task_state_version=3,
    )

    assert equal_base.task_transition.expected_task_record.state_version == 2
    assert equal_base.task_transition.next_task_record.state_version == 3
    assert (
        advanced_before_terminal_turn.task_transition.expected_task_record.state_version
        == 3
    )
    assert (
        advanced_before_terminal_turn.task_transition.next_task_record.state_version
        == 4
    )
    assert newly_created_task.expected_active_links[
        0
    ].base_task_state_version is None
    assert (
        failed_with_current_projection.terminal_links[
            0
        ].result_task_state_version
        == 3
    )


def test_run_finalization_preserves_existing_run_link_and_task_closure() -> None:
    command = _completed_finalization()
    running = command.expected_active_record
    terminal = command.terminal_record
    active_link = command.expected_active_links[0]
    result_task = command.result_task_records[0]

    assert command.terminal_links[0].result_task_state_version == (
        result_task.state_version
    )
    empty = _completed_finalization(
        stop_reason=StopReason.INPUT_INVALID,
        outcome=AgentOutcome.BLOCKED,
        with_task=False,
        task_status=None,
    )
    assert not empty.terminal_links

    with pytest.raises(ValidationError, match="RUNNING"):
        _rebuild(command, expected_active_record=terminal)
    with pytest.raises(ValidationError, match="dirty expected active Run"):
        _rebuild(
            command,
            expected_active_record=_project_run(
                running,
                incomplete_reason="PROCESS_RESTART_DETECTED",
            ),
        )
    with pytest.raises(ValidationError, match="terminal Run"):
        _rebuild(command, terminal_record=running)
    with pytest.raises(ValidationError, match="recovery-only stop reason"):
        _rebuild(
            command,
            terminal_record=_project_run(
                terminal,
                stop_reason=StopReason.PROCESS_RESTART_DETECTED,
            ),
        )
    with pytest.raises(ValidationError, match="stable fields"):
        _rebuild(
            command,
            terminal_record=_project_run(terminal, conversation_id=uuid4()),
        )
    with pytest.raises(ValidationError, match="active RunTaskLink"):
        _rebuild(
            command,
            expected_active_links=(
                _rebuild(active_link, result_task_state_version=1),
            ),
        )
    with pytest.raises(ValidationError, match="exact RunTaskLink set"):
        _rebuild(command, terminal_links=())
    with pytest.raises(ValidationError, match="result Task"):
        _rebuild(
            command,
            result_task_records=(_rebuild(result_task, state_version=3),),
        )
    with pytest.raises(ValidationError, match="exact next Task"):
        _rebuild(
            command,
            result_task_records=(
                _rebuild(result_task, owner_customer_id="customer-B"),
            ),
        )
    with pytest.raises(ValidationError):
        _rebuild(
            command,
            result_task_records=(result_task, result_task),
        )


def test_application_inbound_models_are_strict_and_visibility_bounded() -> None:
    context = _customer_context()
    command = AgentRunCommand(
        customer_context=context,
        message="订单 O-1001 状态怎么样？",
    )
    result = AgentRunResult(
        run_id=uuid4(),
        outcome=AgentOutcome.COMPLETED,
        message="订单已发货。",
    )

    assert command.customer_context is context
    assert result.outcome is AgentOutcome.COMPLETED
    assert set(AgentRunCommand.model_fields) == {
        "customer_context",
        "message",
    }
    assert set(AgentRunResult.model_fields) == {"run_id", "outcome", "message"}
    assert AgentRunCommand.contract_visibility is (ContractVisibility.RUNTIME_PRIVATE)
    assert AgentRunResult.contract_visibility is ContractVisibility.USER_VISIBLE
    assert AgentRunCommand.model_config["strict"] is True
    assert AgentRunResult.model_config["strict"] is True

    with pytest.raises(ValidationError, match="CustomerContext instance"):
        AgentRunCommand(
            customer_context=context.model_dump(),
            message="订单 O-1001 状态怎么样？",
        )
    with pytest.raises(ValidationError, match="Extra inputs"):
        AgentRunCommand(
            customer_context=context,
            message="订单 O-1001 状态怎么样？",
            customer_id="customer-B",
        )
    with pytest.raises(ValidationError, match="UUID"):
        AgentRunResult(
            run_id=str(uuid4()),
            outcome=AgentOutcome.COMPLETED,
            message="订单已发货。",
        )
    with pytest.raises(ValidationError):
        AgentRunResult(
            run_id=uuid4(),
            outcome=AgentOutcome.COMPLETED.value,
            message="订单已发货。",
        )


def test_application_port_declaration_models_freeze_the_exact_field_surface() -> None:
    expected_fields = {
        SaveRequestUnderstandingCommand: {"record", "accepted_deltas"},
        SaveInputBindingCommand: {"record", "request_unit_id"},
        CreateInitialTaskGraphCommand: {
            "owner_scope",
            "expected_conversation_record",
            "expected_message_record",
            "expected_active_run_record",
            "request_understanding",
            "initial_task",
            "initial_request_unit",
            "input_bindings",
            "conversation_task_link",
            "run_task_link",
        },
        ApplyTaskTransitionCommand: {
            "expected_task_record",
            "next_task_record",
            "expected_request_unit_record",
            "next_request_unit_record",
            "task_state_transition",
        },
        SaveObservationCommand: {
            "owner_scope",
            "observation_record",
            "source_tool_call_record",
        },
        FinalizeRunCommand: {
            "expected_active_record",
            "terminal_record",
            "expected_active_links",
            "terminal_links",
            "result_task_records",
            "task_transition",
            "terminal_result",
            "assistant_message",
            "terminal_trace_events",
        },
        AgentRunCommand: {"customer_context", "message"},
        AgentRunResult: {"run_id", "outcome", "message"},
        TaskRecoveryAggregate: {
            "task_record",
            "task_state_transitions",
        },
        ToolCallRecoveryAggregate: {
            "tool_call_record",
            "tool_attempt_records",
        },
        RestartRecoveryClosure: {
            "closure_fence",
            "conversation_record",
            "active_run_record",
            "conversation_task_links",
            "run_task_links",
            "task_aggregates",
            "request_unit_records",
            "tool_call_aggregates",
        },
        ApplyRestartRecoveryCommand: {
            "expected_closure",
            "run_transition",
            "tool_call_transitions",
            "task_transitions",
            "terminal_run_task_links",
            "recovery_trace_events",
        },
    }

    for model_type, fields in expected_fields.items():
        assert set(model_type.model_fields) == fields
        assert model_type.model_config["strict"] is True
        assert model_type.model_config["frozen"] is True
        assert model_type.model_config["extra"] == "forbid"
        assert model_type.model_json_schema()["additionalProperties"] is False

    closure = _restart_recovery_closure()
    with pytest.raises(ValidationError, match="UUID"):
        _rebuild(closure, closure_fence=str(closure.closure_fence))


def test_first_slice_application_tuple_cardinality_is_explicitly_bounded() -> None:
    exact_one_fields = (
        (SaveRequestUnderstandingCommand, "accepted_deltas"),
        (CreateInitialTaskGraphCommand, "input_bindings"),
    )
    optional_one_fields = (
        (FinalizeRunCommand, "expected_active_links"),
        (FinalizeRunCommand, "terminal_links"),
        (FinalizeRunCommand, "result_task_records"),
        (TaskRecoveryAggregate, "task_state_transitions"),
        (ToolCallRecoveryAggregate, "tool_attempt_records"),
        (RestartRecoveryClosure, "conversation_task_links"),
        (RestartRecoveryClosure, "run_task_links"),
        (RestartRecoveryClosure, "task_aggregates"),
        (RestartRecoveryClosure, "request_unit_records"),
        (RestartRecoveryClosure, "tool_call_aggregates"),
        (ApplyRestartRecoveryCommand, "tool_call_transitions"),
        (ApplyRestartRecoveryCommand, "task_transitions"),
        (ApplyRestartRecoveryCommand, "terminal_run_task_links"),
    )
    bounded_recovery_trace_fields = (
        (ApplyRestartRecoveryCommand, "recovery_trace_events"),
    )
    bounded_terminal_trace_fields = (
        (FinalizeRunCommand, "terminal_trace_events"),
    )
    for model_type, field_name in exact_one_fields:
        field_schema = model_type.model_json_schema()["properties"][field_name]
        assert field_schema["minItems"] == 1
        assert field_schema["maxItems"] == 1
    for model_type, field_name in optional_one_fields:
        field_schema = model_type.model_json_schema()["properties"][field_name]
        assert field_schema.get("minItems", 0) == 0
        assert field_schema["maxItems"] == 1
    for model_type, field_name in bounded_recovery_trace_fields:
        field_schema = model_type.model_json_schema()["properties"][field_name]
        assert field_schema["minItems"] == 1
        assert field_schema["maxItems"] == 3
    for model_type, field_name in bounded_terminal_trace_fields:
        field_schema = model_type.model_json_schema()["properties"][field_name]
        assert field_schema.get("minItems", 0) == 0
        assert field_schema["maxItems"] == 2

    graph = _initial_graph()
    child = graph.request_understanding.accepted_deltas[0]
    binding = graph.input_bindings[0]
    assert len(graph.request_understanding.accepted_deltas) == 1
    assert len(graph.input_bindings) == 1
    with pytest.raises(ValidationError):
        _rebuild(graph.request_understanding, accepted_deltas=())
    with pytest.raises(ValidationError):
        _rebuild(
            graph.request_understanding,
            accepted_deltas=(child, child),
        )
    with pytest.raises(ValidationError):
        _rebuild(graph, input_bindings=())
    with pytest.raises(ValidationError):
        _rebuild(graph, input_bindings=(binding, binding))

    finalization = _completed_finalization()
    empty_finalization = _failed_finalization(with_task=False)

    running_closure = _restart_recovery_closure()
    running_recovery = _restart_recovery_command()
    task_aggregate = running_closure.task_aggregates[0]
    tool_aggregate = running_closure.tool_call_aggregates[0]
    empty_task_aggregate = TaskRecoveryAggregate(
        task_record=_task(state_version=1),
        task_state_transitions=(),
    )
    empty_tool_aggregate = ToolCallRecoveryAggregate(
        tool_call_record=_tool_call(
            status=ToolCallStatus.CREATED,
            attempt_count=0,
        ),
        tool_attempt_records=(),
    )
    created_closure = _created_restart_recovery_closure()
    created_recovery = _created_restart_recovery_command()

    empty_instances_and_fields = (
        (empty_finalization, "expected_active_links"),
        (empty_finalization, "terminal_links"),
        (empty_finalization, "result_task_records"),
        (empty_finalization, "terminal_trace_events"),
        (empty_task_aggregate, "task_state_transitions"),
        (empty_tool_aggregate, "tool_attempt_records"),
        (created_closure, "conversation_task_links"),
        (created_closure, "run_task_links"),
        (created_closure, "task_aggregates"),
        (created_closure, "request_unit_records"),
        (created_closure, "tool_call_aggregates"),
        (created_recovery, "tool_call_transitions"),
        (created_recovery, "task_transitions"),
        (created_recovery, "terminal_run_task_links"),
    )
    for instance, field_name in empty_instances_and_fields:
        assert getattr(instance, field_name) == ()

    one_instances_and_fields = (
        (finalization, "expected_active_links"),
        (finalization, "terminal_links"),
        (finalization, "result_task_records"),
        (task_aggregate, "task_state_transitions"),
        (tool_aggregate, "tool_attempt_records"),
        (running_closure, "conversation_task_links"),
        (running_closure, "run_task_links"),
        (running_closure, "task_aggregates"),
        (running_closure, "request_unit_records"),
        (running_closure, "tool_call_aggregates"),
        (running_recovery, "tool_call_transitions"),
        (running_recovery, "task_transitions"),
        (running_recovery, "terminal_run_task_links"),
    )
    for instance, field_name in one_instances_and_fields:
        value = getattr(instance, field_name)
        assert len(value) == 1
        with pytest.raises(ValidationError):
            _rebuild(instance, **{field_name: (*value, value[0])})

    assert len(finalization.terminal_trace_events) == 2
    with pytest.raises(ValidationError):
        _rebuild(
            finalization,
            terminal_trace_events=(
                *finalization.terminal_trace_events,
                finalization.terminal_trace_events[0],
            ),
        )

    for model_type, field_name in (
        (RequestUnderstandingRecord, "accepted_delta_refs"),
        (AcceptedTaskDelta, "input_binding_refs"),
        (InputBinding, "source_refs"),
        (RequestUnitRecord, "input_binding_refs"),
    ):
        source_field_schema = model_type.model_json_schema()["properties"][field_name]
        assert "maxItems" not in source_field_schema


def test_provider_protocol_error_is_fixed_and_adapter_discards_raw_context() -> None:
    error = ProviderProtocolError()
    safe_projection = " ".join((str(error), repr(error), repr(error.args)))

    assert error.args == ("PROVIDER_PROTOCOL_ERROR",)
    assert safe_projection.count("PROVIDER_PROTOCOL_ERROR") >= 3
    with pytest.raises(TypeError):
        ProviderProtocolError("raw provider payload")

    def translate_after_discarding_raw_exception() -> None:
        translated: ProviderProtocolError | None = None
        try:
            raise RuntimeError("Token VERY_SECRET Prompt private customer-A")
        except RuntimeError:
            translated = ProviderProtocolError()
        raise translated

    with pytest.raises(ProviderProtocolError) as raised:
        translate_after_discarding_raw_exception()
    translated = raised.value
    assert translated.__cause__ is None
    assert translated.__context__ is None
    projection = " ".join((str(translated), repr(translated), repr(translated.args)))
    for secret in ("VERY_SECRET", "Prompt private", "customer-A"):
        assert secret not in projection


def test_task_recovery_aggregate_requires_complete_contiguous_history() -> None:
    closure = _restart_recovery_closure()
    aggregate = closure.task_aggregates[0]
    transition = aggregate.task_state_transitions[0]

    assert transition.result_state_version == aggregate.task_record.state_version
    assert (
        TaskRecoveryAggregate(
            task_record=_task(state_version=1),
            task_state_transitions=(),
        ).task_state_transitions
        == ()
    )

    with pytest.raises(ValidationError, match="version 1"):
        TaskRecoveryAggregate(
            task_record=_task(
                task_id=transition.task_id,
                status=transition.to_status,
                state_version=1,
            ),
            task_state_transitions=(transition,),
        )
    with pytest.raises(ValidationError, match="complete contiguous"):
        TaskRecoveryAggregate(
            task_record=_rebuild(
                aggregate.task_record,
                state_version=3,
            ),
            task_state_transitions=(transition,),
        )
    with pytest.raises(ValidationError, match="Task identity"):
        TaskRecoveryAggregate(
            task_record=aggregate.task_record,
            task_state_transitions=(_rebuild(transition, task_id=uuid4()),),
        )
    with pytest.raises(ValidationError, match="terminal status"):
        TaskRecoveryAggregate(
            task_record=_rebuild(
                aggregate.task_record,
                status=TaskStatus.BLOCKED,
            ),
            task_state_transitions=(transition,),
        )
    with pytest.raises(ValidationError, match="before Task creation"):
        TaskRecoveryAggregate(
            task_record=_rebuild(
                aggregate.task_record,
                created_at=transition.changed_at + timedelta(milliseconds=1),
                updated_at=transition.changed_at + timedelta(milliseconds=1),
            ),
            task_state_transitions=(transition,),
        )


@pytest.mark.parametrize("transition_count", (0, 1))
def test_task_recovery_rejects_untrusted_large_version_without_range_materialization(
    monkeypatch: pytest.MonkeyPatch,
    transition_count: int,
) -> None:
    transition = _task_transition()
    transitions = (transition,) if transition_count else ()
    task = _task(
        task_id=transition.task_id,
        status=transition.to_status if transitions else TaskStatus.ACTIVE,
        state_version=100_000,
    )

    def fail_if_materialized(*_args: object) -> None:
        raise AssertionError(
            "untrusted state_version must not drive range materialization"
        )

    monkeypatch.setattr(
        application_records_module,
        "range",
        fail_if_materialized,
        raising=False,
    )
    with pytest.raises(ValidationError, match="complete contiguous"):
        TaskRecoveryAggregate(
            task_record=task,
            task_state_transitions=transitions,
        )


def test_tool_call_recovery_aggregate_requires_exact_attempt_history() -> None:
    aggregate = _restart_recovery_closure().tool_call_aggregates[0]
    call = aggregate.tool_call_record
    attempt = aggregate.tool_attempt_records[0]

    assert attempt.attempt_no == call.attempt_count == 1
    created = _tool_call(
        status=ToolCallStatus.CREATED,
        attempt_count=0,
    )
    assert (
        ToolCallRecoveryAggregate(
            tool_call_record=created,
            tool_attempt_records=(),
        ).tool_attempt_records
        == ()
    )
    with pytest.raises(ValidationError, match="exact attempt"):
        ToolCallRecoveryAggregate(
            tool_call_record=call,
            tool_attempt_records=(),
        )
    with pytest.raises(ValidationError, match="ToolCall identity"):
        ToolCallRecoveryAggregate(
            tool_call_record=call,
            tool_attempt_records=(_rebuild(attempt, tool_call_id=uuid4()),),
        )
    with pytest.raises(ValidationError, match="RUNNING"):
        ToolCallRecoveryAggregate(
            tool_call_record=call,
            tool_attempt_records=(
                ToolAttemptRecord(
                    tool_call_id=call.tool_call_id,
                    attempt_no=1,
                    started_at=UTC_NOW,
                    finished_at=UTC_NOW + timedelta(milliseconds=1),
                    outcome=ToolResultOutcome.SUCCESS,
                ),
            ),
        )
    retry_call = _project_tool_call(call, attempt_count=2)
    with pytest.raises(ValidationError):
        ToolCallRecoveryAggregate(
            tool_call_record=retry_call,
            tool_attempt_records=(
                ToolAttemptRecord(
                    tool_call_id=call.tool_call_id,
                    attempt_no=1,
                    started_at=UTC_NOW,
                    finished_at=UTC_NOW + timedelta(milliseconds=1),
                    outcome=ToolResultOutcome.SYSTEM_FAILURE,
                    failure_code="FIRST_ATTEMPT_FAILED",
                ),
                ToolAttemptRecord(
                    tool_call_id=call.tool_call_id,
                    attempt_no=2,
                    started_at=UTC_NOW + timedelta(milliseconds=2),
                ),
            ),
        )
    with pytest.raises(ValidationError, match="does not accept retry"):
        ToolCallRecoveryAggregate(
            tool_call_record=retry_call,
            tool_attempt_records=(attempt,),
        )
    for field_name, field_value in (
        ("failure_code", "STALE_FAILURE"),
        ("result_ref", uuid4()),
    ):
        with pytest.raises(
            ValidationError,
            match="active ToolCall cannot carry failure or result",
        ):
            ToolCallRecoveryAggregate(
                tool_call_record=_project_tool_call(
                    call,
                    **{field_name: field_value},
                ),
                tool_attempt_records=(attempt,),
            )
        with pytest.raises(
            ValidationError,
            match="active ToolCall cannot carry failure or result",
        ):
            ToolCallRecoveryAggregate(
                tool_call_record=_project_tool_call(
                    created,
                    **{field_name: field_value},
                ),
                tool_attempt_records=(),
            )


def test_tool_call_recovery_aggregate_binds_terminal_attempt_projection() -> None:
    finished_at = UTC_NOW + timedelta(milliseconds=1)
    call = _tool_call(
        status=ToolCallStatus.FAILED,
        attempt_count=1,
        finished_at=finished_at,
        failure_code="UPSTREAM_FAILURE",
    )
    attempt = ToolAttemptRecord(
        tool_call_id=call.tool_call_id,
        attempt_no=1,
        started_at=UTC_NOW,
        finished_at=finished_at,
        outcome=ToolResultOutcome.SYSTEM_FAILURE,
        failure_code="UPSTREAM_FAILURE",
    )

    assert (
        ToolCallRecoveryAggregate(
            tool_call_record=call,
            tool_attempt_records=(attempt,),
        ).tool_attempt_records[0]
        == attempt
    )
    with pytest.raises(ValidationError, match="timestamps must match"):
        ToolCallRecoveryAggregate(
            tool_call_record=call,
            tool_attempt_records=(
                _rebuild(
                    attempt,
                    finished_at=finished_at + timedelta(milliseconds=1),
                ),
            ),
        )
    with pytest.raises(ValidationError, match="failure_code must match"):
        ToolCallRecoveryAggregate(
            tool_call_record=call,
            tool_attempt_records=(_rebuild(attempt, failure_code="DIFFERENT_FAILURE"),),
        )


def test_restart_recovery_closure_rejects_cross_graph_duplicates_and_orphans() -> None:
    closure = _restart_recovery_closure()
    task_aggregate = closure.task_aggregates[0]
    request_unit = closure.request_unit_records[0]
    tool_aggregate = closure.tool_call_aggregates[0]

    assert closure.active_run_record.conversation_id == (
        closure.conversation_record.conversation_id
    )
    assert closure.run_task_links[0].task_id == task_aggregate.task_record.task_id
    assert request_unit.task_id == task_aggregate.task_record.task_id
    assert tool_aggregate.tool_call_record.request_unit_id == (
        request_unit.request_unit_id
    )
    for forbidden_claim in (
        "database_closed_set_complete",
        "snapshot_complete",
        "owner_scope",
        "recovery_ready",
    ):
        assert not hasattr(closure, forbidden_claim)

    with pytest.raises(ValidationError, match="active Run"):
        _rebuild(
            closure,
            active_run_record=_project_run(
                closure.active_run_record,
                status=AgentRunStatus.INCOMPLETE,
                completed_at=UTC_NOW + timedelta(seconds=1),
                stop_reason=StopReason.PROCESS_RESTART_DETECTED,
            ),
        )
    with pytest.raises(ValidationError, match="incomplete_reason"):
        _rebuild(
            closure,
            active_run_record=_project_run(
                closure.active_run_record,
                incomplete_reason="PROCESS_RESTART_DETECTED",
            ),
        )
    with pytest.raises(ValidationError, match="Conversation"):
        _rebuild(
            closure,
            active_run_record=_project_run(
                closure.active_run_record,
                conversation_id=None,
            ),
        )
    with pytest.raises(ValidationError, match="owner"):
        _rebuild(
            closure,
            task_aggregates=(
                TaskRecoveryAggregate(
                    task_record=_rebuild(
                        task_aggregate.task_record,
                        owner_customer_id="customer-B",
                    ),
                    task_state_transitions=(task_aggregate.task_state_transitions),
                ),
            ),
        )
    with pytest.raises(ValidationError, match="RunTaskLink"):
        _rebuild(
            closure,
            run_task_links=(_rebuild(closure.run_task_links[0], run_id=uuid4()),),
        )
    with pytest.raises(ValidationError, match="base version"):
        _rebuild(
            closure,
            run_task_links=(
                _rebuild(
                    closure.run_task_links[0],
                    base_task_state_version=3,
                ),
            ),
        )
    with pytest.raises(ValidationError, match="ConversationTaskLink"):
        _rebuild(closure, conversation_task_links=())
    with pytest.raises(ValidationError, match="RequestUnit closed set"):
        _rebuild(closure, request_unit_records=())
    with pytest.raises(ValidationError):
        _rebuild(
            closure,
            request_unit_records=(request_unit, request_unit),
        )
    with pytest.raises(ValidationError, match="ToolCall owner graph"):
        _rebuild(
            closure,
            tool_call_aggregates=(
                ToolCallRecoveryAggregate(
                    tool_call_record=_project_tool_call(
                        tool_aggregate.tool_call_record,
                        run_id=uuid4(),
                    ),
                    tool_attempt_records=tool_aggregate.tool_attempt_records,
                ),
            ),
        )
    with pytest.raises(ValidationError, match="validated Task version"):
        _rebuild(
            closure,
            tool_call_aggregates=(
                ToolCallRecoveryAggregate(
                    tool_call_record=_project_tool_call(
                        tool_aggregate.tool_call_record,
                        validated_task_state_version=1,
                    ),
                    tool_attempt_records=tool_aggregate.tool_attempt_records,
                ),
            ),
        )
    with pytest.raises(ValidationError, match="argument bindings"):
        _rebuild(
            closure,
            tool_call_aggregates=(
                ToolCallRecoveryAggregate(
                    tool_call_record=_project_tool_call(
                        tool_aggregate.tool_call_record,
                        argument_binding_refs=(uuid4(),),
                    ),
                    tool_attempt_records=tool_aggregate.tool_attempt_records,
                ),
            ),
        )


@pytest.mark.parametrize(
    "field_name",
    (
        "conversation_task_links",
        "run_task_links",
        "task_aggregates",
        "request_unit_records",
        "tool_call_aggregates",
    ),
)
def test_created_run_recovery_accepts_only_an_empty_pre_graph(
    field_name: str,
) -> None:
    created_closure = _created_restart_recovery_closure()
    running_closure = _restart_recovery_closure()

    assert created_closure.active_run_record.status is AgentRunStatus.CREATED
    assert all(
        getattr(created_closure, supplied_field) == ()
        for supplied_field in (
            "conversation_task_links",
            "run_task_links",
            "task_aggregates",
            "request_unit_records",
            "tool_call_aggregates",
        )
    )
    with pytest.raises(
        ValidationError, match="CREATED Run recovery graph must be empty"
    ):
        _rebuild(
            created_closure,
            **{field_name: getattr(running_closure, field_name)},
        )


def test_created_run_empty_recovery_apply_is_a_valid_total_projection() -> None:
    command = _created_restart_recovery_command()

    assert command.expected_closure.active_run_record.status is AgentRunStatus.CREATED
    assert command.run_transition.incomplete_record.status is AgentRunStatus.INCOMPLETE
    assert command.tool_call_transitions == ()
    assert command.task_transitions == ()
    assert command.terminal_run_task_links == ()
    assert len(command.recovery_trace_events) == 1
    assert command.recovery_trace_events[0].event_type is TraceEventType.RUN_STOPPED


def test_restart_recovery_requires_the_exact_bounded_trace_event_set() -> None:
    created_command = _created_restart_recovery_command()
    running_command = _restart_recovery_command()
    running_events = running_command.recovery_trace_events

    assert {event.event_type for event in running_events} == {
        TraceEventType.RUN_STOPPED,
        TraceEventType.TASK_STATE_CHANGED,
        TraceEventType.TOOL_CALL_INTERRUPTED,
    }
    assert len({event.trace_event_id for event in running_events}) == 3

    with pytest.raises(ValidationError):
        _rebuild(created_command, recovery_trace_events=())
    with pytest.raises(ValidationError):
        _rebuild(
            running_command,
            recovery_trace_events=(*running_events, running_events[0]),
        )

    unrelated_event = TraceEvent(
        trace_event_id=uuid4(),
        event_type=TraceEventType.RUN_STARTED,
        occurred_at=created_command.run_transition.incomplete_record.completed_at,
        run_id=created_command.expected_closure.active_run_record.run_id,
    )
    with pytest.raises(ValidationError, match="recovery Trace event type"):
        _rebuild(
            created_command,
            recovery_trace_events=(
                created_command.recovery_trace_events[0],
                unrelated_event,
            ),
        )

    duplicate_id_events = list(running_events)
    duplicate_id_events[1] = duplicate_id_events[1].model_copy(
        update={"trace_event_id": duplicate_id_events[0].trace_event_id}
    )
    with pytest.raises(ValidationError, match="Trace event identities"):
        _rebuild(
            running_command,
            recovery_trace_events=tuple(duplicate_id_events),
        )


@pytest.mark.parametrize(
    "updates",
    (
        {"trace_event_id": "not-a-uuid"},
        {"trace_event_id": []},
        {"case_id": ()},
        {"argument_binding_refs": None},
    ),
)
def test_restart_recovery_strictly_revalidates_nested_trace_event_known_fields(
    updates: dict[str, object],
) -> None:
    command = _restart_recovery_command()

    with pytest.raises(ValidationError):
        _rebuild(
            command,
            recovery_trace_events=_updated_recovery_trace_events(
                command,
                TraceEventType.RUN_STOPPED,
                **updates,
            ),
        )


def test_restart_recovery_rejects_hidden_nested_trace_event_fields() -> None:
    command = _restart_recovery_command()
    events = _updated_recovery_trace_events(
        command,
        TraceEventType.RUN_STOPPED,
        secret="must-not-cross-application-boundary",
    )
    injected_event = next(
        event for event in events if event.event_type is TraceEventType.RUN_STOPPED
    )

    assert "secret" in vars(injected_event)
    assert "secret" in injected_event.model_fields_set
    assert "secret" not in injected_event.model_dump(mode="python")
    with pytest.raises(ValidationError):
        _rebuild(command, recovery_trace_events=events)


@pytest.mark.parametrize(
    "storage_attribute",
    ("__pydantic_extra__", "__pydantic_private__"),
)
def test_restart_recovery_rejects_hidden_nested_trace_event_storage(
    storage_attribute: str,
) -> None:
    command = _restart_recovery_command()
    events = _updated_recovery_trace_events(
        command,
        TraceEventType.RUN_STOPPED,
    )
    injected_event = next(
        event for event in events if event.event_type is TraceEventType.RUN_STOPPED
    )
    object.__setattr__(
        injected_event,
        storage_attribute,
        {"secret": "must-not-be-silently-stripped"},
    )

    with pytest.raises(ValidationError):
        _rebuild(command, recovery_trace_events=events)


@pytest.mark.parametrize(
    ("missing_event_type", "error_match"),
    (
        (TraceEventType.RUN_STOPPED, "exactly one RunStopped"),
        (TraceEventType.TASK_STATE_CHANGED, "TaskStateChanged event set"),
        (TraceEventType.TOOL_CALL_INTERRUPTED, "ToolCallInterrupted event set"),
    ),
)
def test_restart_recovery_rejects_every_missing_event_family(
    missing_event_type: TraceEventType,
    error_match: str,
) -> None:
    command = _restart_recovery_command()
    events = tuple(
        event
        for event in command.recovery_trace_events
        if event.event_type is not missing_event_type
    )

    with pytest.raises(ValidationError, match=error_match):
        _rebuild(command, recovery_trace_events=events)


@pytest.mark.parametrize(
    ("event_type", "updates", "error_match"),
    (
        (
            TraceEventType.RUN_STOPPED,
            {"run_id": uuid4()},
            "same recovery Run",
        ),
        (
            TraceEventType.RUN_STOPPED,
            {"user_outcome": AgentOutcome.COMPLETED},
            "BLOCKED",
        ),
        (
            TraceEventType.RUN_STOPPED,
            {"stop_reason": StopReason.GOAL_COMPLETED},
            "PROCESS_RESTART_DETECTED",
        ),
        (
            TraceEventType.RUN_STOPPED,
            {"occurred_at": UTC_NOW},
            "Run completion timestamp",
        ),
        (
            TraceEventType.TASK_STATE_CHANGED,
            {"run_id": uuid4()},
            "same recovery Run",
        ),
        (
            TraceEventType.TASK_STATE_CHANGED,
            {"task_id": uuid4()},
            "TaskStateChanged event set",
        ),
        (
            TraceEventType.TASK_STATE_CHANGED,
            {"request_unit_id": uuid4()},
            "TaskStateChanged event set",
        ),
        (
            TraceEventType.TASK_STATE_CHANGED,
            {"occurred_at": UTC_NOW},
            "Task transition timestamp",
        ),
        (
            TraceEventType.TOOL_CALL_INTERRUPTED,
            {"run_id": uuid4()},
            "same recovery Run",
        ),
        (
            TraceEventType.TOOL_CALL_INTERRUPTED,
            {"tool_call_id": uuid4()},
            "ToolCallInterrupted event set",
        ),
        (
            TraceEventType.TOOL_CALL_INTERRUPTED,
            {"tool_call_terminal_status": ToolCallStatus.FAILED},
            "status must match|INTERRUPTED",
        ),
        (
            TraceEventType.TOOL_CALL_INTERRUPTED,
            {"occurred_at": UTC_NOW},
            "ToolCall interruption timestamp",
        ),
        (
            TraceEventType.TASK_STATE_CHANGED,
            {"event_type": TraceEventType.RUN_STARTED},
            "recovery Trace event type",
        ),
    ),
)
def test_restart_recovery_trace_binds_kind_identity_status_and_timestamp(
    event_type: TraceEventType,
    updates: dict[str, object],
    error_match: str,
) -> None:
    command = _restart_recovery_command()

    with pytest.raises(ValidationError, match=error_match):
        _rebuild(
            command,
            recovery_trace_events=_updated_recovery_trace_events(
                command,
                event_type,
                **updates,
            ),
        )


@pytest.mark.parametrize(
    ("event_type", "field_name"),
    _RECOVERY_TRACE_CONTAMINATION_CASES,
)
def test_restart_recovery_trace_rejects_every_cross_kind_or_unrelated_projection(
    event_type: TraceEventType,
    field_name: str,
) -> None:
    command = _restart_recovery_command()

    with pytest.raises(ValidationError):
        _rebuild(
            command,
            recovery_trace_events=_updated_recovery_trace_events(
                command,
                event_type,
                **{field_name: _non_empty_trace_optional_value(field_name)},
            ),
        )


def test_running_run_recovery_allows_zero_or_one_closed_graph() -> None:
    created_closure = _created_restart_recovery_closure()
    empty_running_closure = _rebuild(
        created_closure,
        active_run_record=_project_run(
            created_closure.active_run_record,
            status=AgentRunStatus.RUNNING,
        ),
    )
    one_graph_closure = _restart_recovery_closure()

    assert empty_running_closure.active_run_record.status is AgentRunStatus.RUNNING
    assert all(
        getattr(empty_running_closure, field_name) == ()
        for field_name in (
            "conversation_task_links",
            "run_task_links",
            "task_aggregates",
            "request_unit_records",
            "tool_call_aggregates",
        )
    )
    assert all(
        len(getattr(one_graph_closure, field_name)) == 1
        for field_name in (
            "conversation_task_links",
            "run_task_links",
            "task_aggregates",
            "request_unit_records",
            "tool_call_aggregates",
        )
    )


def test_restart_recovery_apply_is_bijective_and_fence_bound() -> None:
    command = _restart_recovery_command()
    closure = command.expected_closure

    assert command.run_transition.expected_active_record == (closure.active_run_record)
    assert {
        item.active_record.tool_call_id for item in command.tool_call_transitions
    } == {item.tool_call_record.tool_call_id for item in closure.tool_call_aggregates}
    assert {item.expected_task_record.task_id for item in command.task_transitions} == {
        item.task_record.task_id for item in closure.task_aggregates
    }
    assert command.terminal_run_task_links[0].result_task_state_version == 3

    with pytest.raises(ValidationError, match="expected closure Run"):
        _rebuild(
            command,
            run_transition=MarkRunIncompleteForRecoveryCommand(
                expected_active_record=_project_run(
                    closure.active_run_record,
                    provider_lane="other",
                ),
                incomplete_record=_project_run(
                    command.run_transition.incomplete_record,
                    provider_lane="other",
                ),
            ),
        )
    with pytest.raises(ValidationError, match="ToolCall transition set"):
        _rebuild(command, tool_call_transitions=())
    with pytest.raises(ValidationError, match="Task transition set"):
        _rebuild(command, task_transitions=())
    with pytest.raises(ValidationError, match="RunTaskLink set"):
        _rebuild(command, terminal_run_task_links=())
    with pytest.raises(ValidationError, match="result Task version"):
        _rebuild(
            command,
            terminal_run_task_links=(
                _rebuild(
                    command.terminal_run_task_links[0],
                    result_task_state_version=2,
                ),
            ),
        )

    assert set(RecoveryWriteResult) == {
        RecoveryWriteResult.APPLIED,
        RecoveryWriteResult.CLOSURE_CONFLICT,
        RecoveryWriteResult.NOT_APPLICABLE,
        RecoveryWriteResult.RECONCILIATION_REQUIRED,
    }


def test_running_action_recovery_command_preserves_reconciliation_candidate() -> None:
    command = _restart_recovery_command()
    closure = command.expected_closure
    tool_aggregate = closure.tool_call_aggregates[0]
    action_call = _project_tool_call(
        tool_aggregate.tool_call_record,
        effect=ToolEffect.ACTION,
        canonical_tool_name="create_refund",
    )
    action_aggregate = ToolCallRecoveryAggregate(
        tool_call_record=action_call,
        tool_attempt_records=tool_aggregate.tool_attempt_records,
    )
    action_closure = _rebuild(
        closure,
        tool_call_aggregates=(action_aggregate,),
    )
    action_transition = InterruptToolCallForRecoveryCommand(
        active_record=action_call,
        interrupted_record=_project_tool_call(
            action_call,
            status=ToolCallStatus.INTERRUPTED,
            finished_at=UTC_NOW + timedelta(milliseconds=2),
            interruption_reason="PROCESS_RESTART_DETECTED",
        ),
    )
    action_command = ApplyRestartRecoveryCommand(
        expected_closure=action_closure,
        run_transition=command.run_transition,
        tool_call_transitions=(action_transition,),
        task_transitions=command.task_transitions,
        terminal_run_task_links=command.terminal_run_task_links,
        recovery_trace_events=_recovery_trace_events(
            run_transition=command.run_transition,
            task_transitions=command.task_transitions,
            tool_call_transitions=(action_transition,),
        ),
    )

    assert action_command.tool_call_transitions[0].active_record.effect is (
        ToolEffect.ACTION
    )
    assert action_command.tool_call_transitions[0].interrupted_record.status is (
        ToolCallStatus.INTERRUPTED
    )
    assert RecoveryWriteResult.RECONCILIATION_REQUIRED.value == (
        "RECONCILIATION_REQUIRED"
    )


def test_eval_projection_uses_explicit_validated_details() -> None:
    result = _eval_result()

    assert result.version_manifest.dataset_version == "e2e01-thin-dataset-v1"
    assert result.version_manifest.candidate_version == "candidate-source-revision"
    assert result.version_manifest.baseline_version is None
    assert result.version_manifest.fixture_versions == ("e2e01-thin-fixture-v1",)
    assert result.version_manifest.model_config_version == "scripted-provider-v1"
    with pytest.raises(ValidationError, match="Extra inputs"):
        EvalGraderResult(
            grader_name="TraceCompletenessGrader",
            status=EvalGraderStatus.PASS,
            arbitrary_details={"unsafe": "payload"},
        )
    with pytest.raises(ValidationError, match="Extra inputs"):
        _version_manifest(arbitrary_versions={"prompt": "floating"})
    with pytest.raises(ValidationError, match="fixture_versions must be unique"):
        _version_manifest(fixture_versions=("fixture-v1", "fixture-v1"))


@pytest.mark.parametrize(
    "code_shaped_secret",
    (
        "AKIAIOSFODNN7EXAMPLE",
        "PASSWORD_TOPSECRET",
        "CUSTOMER_EMAIL_ALICE_EXAMPLE_COM",
        "SSN_123_45_6789",
    ),
)
def test_eval_code_catalogs_reject_code_shaped_secrets(
    code_shaped_secret: str,
) -> None:
    with pytest.raises(ValidationError):
        _eval_execution_failure(safe_error_code=code_shaped_secret)
    with pytest.raises(ValidationError):
        EvalGraderResult(
            grader_name="TraceCompletenessGrader",
            status=EvalGraderStatus.FAIL,
            reason_code=code_shaped_secret,
        )
    with pytest.raises(ValidationError):
        _eval_result(
            status=EvalResultStatus.FAIL,
            grader_results=(_passing_grader(),),
            critical_failures=(code_shaped_secret,),
        )


def test_eval_execution_error_catalog_covers_every_failure_phase() -> None:
    catalog = {
        EvalExecutionFailurePhase.HARNESS_SETUP: (
            EvalExecutionSafeErrorCode.HARNESS_SETUP_FAILED
        ),
        EvalExecutionFailurePhase.CASE_SETUP: (
            EvalExecutionSafeErrorCode.CASE_SETUP_FAILED
        ),
        EvalExecutionFailurePhase.TRACE_PERSISTENCE: (
            EvalExecutionSafeErrorCode.TRACE_STORE_UNAVAILABLE
        ),
        EvalExecutionFailurePhase.SYSTEM_UNDER_TEST: (
            EvalExecutionSafeErrorCode.SYSTEM_UNDER_TEST_FAILED
        ),
        EvalExecutionFailurePhase.GRADING: (EvalExecutionSafeErrorCode.GRADING_FAILED),
        EvalExecutionFailurePhase.RESULT_PERSISTENCE: (
            EvalExecutionSafeErrorCode.RESULT_PERSISTENCE_FAILED
        ),
        EvalExecutionFailurePhase.RESULT_COMPLETENESS: (
            EvalExecutionSafeErrorCode.RESULT_COMPLETENESS_FAILED
        ),
    }

    assert set(catalog) == set(EvalExecutionFailurePhase)
    assert set(EvalExecutionSafeErrorCode) == {
        EvalExecutionSafeErrorCode.HARNESS_SETUP_FAILED,
        EvalExecutionSafeErrorCode.CASE_SETUP_FAILED,
        EvalExecutionSafeErrorCode.TRACE_PERSISTENCE_FAILED,
        EvalExecutionSafeErrorCode.TRACE_STORE_UNAVAILABLE,
        EvalExecutionSafeErrorCode.SYSTEM_UNDER_TEST_FAILED,
        EvalExecutionSafeErrorCode.GRADING_FAILED,
        EvalExecutionSafeErrorCode.RESULT_PERSISTENCE_FAILED,
        EvalExecutionSafeErrorCode.RESULT_COMPLETENESS_FAILED,
    }
    for phase, code in catalog.items():
        failure = _eval_execution_failure(
            failure_phase=phase,
            safe_error_code=code,
        )
        assert failure.safe_error_code is code
    with pytest.raises(ValidationError, match="must match failure_phase"):
        _eval_execution_failure(
            failure_phase=EvalExecutionFailurePhase.GRADING,
            safe_error_code=EvalExecutionSafeErrorCode.TRACE_STORE_UNAVAILABLE,
        )


def test_eval_grader_and_critical_failure_catalogs_are_closed() -> None:
    assert set(EvalGraderReasonCode) == {
        EvalGraderReasonCode.TRACE_EVENT_MISSING,
        EvalGraderReasonCode.MISSING_RECORD,
        EvalGraderReasonCode.ASSERTION_FAILED,
    }
    expected_critical_values = {f"CF-{index:02d}" for index in range(1, 15)}
    assert {code.value for code in CriticalFailureCode} == expected_critical_values

    for code in CriticalFailureCode:
        result = _eval_result(
            status=EvalResultStatus.FAIL,
            grader_results=(_passing_grader(),),
            critical_failures=(code,),
        )
        assert result.critical_failures == (code,)
    with pytest.raises(ValidationError):
        _eval_result(
            status=EvalResultStatus.FAIL,
            grader_results=(_passing_grader(),),
            critical_failures=("CF-15",),
        )


def test_eval_execution_failure_is_typed_and_does_not_fabricate_case_result() -> None:
    failure = _eval_execution_failure(
        case_id=None,
        attempt=None,
        failure_phase=EvalExecutionFailurePhase.HARNESS_SETUP,
        safe_error_code=EvalExecutionSafeErrorCode.HARNESS_SETUP_FAILED,
        diagnostic_ref=None,
    )

    assert failure.case_id is None
    assert failure.trace_ref is None
    assert "status" not in type(failure).model_fields
    assert "observed_outcome" not in type(failure).model_fields
    assert "grader_results" not in type(failure).model_fields
    assert set(EvalExecutionFailurePhase) == {
        EvalExecutionFailurePhase.HARNESS_SETUP,
        EvalExecutionFailurePhase.CASE_SETUP,
        EvalExecutionFailurePhase.TRACE_PERSISTENCE,
        EvalExecutionFailurePhase.SYSTEM_UNDER_TEST,
        EvalExecutionFailurePhase.GRADING,
        EvalExecutionFailurePhase.RESULT_PERSISTENCE,
        EvalExecutionFailurePhase.RESULT_COMPLETENESS,
    }
    with pytest.raises(ValidationError, match="attempt requires case_id"):
        _eval_execution_failure(case_id=None, attempt=1)
    with pytest.raises(ValidationError, match="Extra inputs"):
        _eval_execution_failure(raw_error="provider stack trace")


def test_eval_critical_failure_forces_fail_and_cannot_coexist_with_pass() -> None:
    critical_failure = (CriticalFailureCode.CF_01,)

    failed = _eval_result(
        status=EvalResultStatus.FAIL,
        grader_results=(_passing_grader(),),
        critical_failures=critical_failure,
    )
    assert failed.status is EvalResultStatus.FAIL

    for status in (
        EvalResultStatus.PASS,
        EvalResultStatus.SKIPPED,
        EvalResultStatus.NOT_RUN,
    ):
        with pytest.raises(ValidationError, match="critical failure"):
            _eval_result(status=status, critical_failures=critical_failure)


def test_eval_fail_does_not_require_a_critical_failure() -> None:
    failed = _eval_result(
        status=EvalResultStatus.FAIL,
        grader_results=(
            EvalGraderResult(
                grader_name="TraceCompletenessGrader",
                status=EvalGraderStatus.FAIL,
                reason_code=EvalGraderReasonCode.TRACE_EVENT_MISSING,
            ),
        ),
    )

    assert failed.critical_failures == ()
    with pytest.raises(ValidationError, match="at least one grader"):
        _eval_result(
            status=EvalResultStatus.FAIL,
            grader_results=(),
        )
    with pytest.raises(ValidationError, match="cannot carry"):
        _eval_result(
            status=EvalResultStatus.SKIPPED,
            grader_results=failed.grader_results,
            observed_outcome=None,
            trace_ref=None,
        )


def test_eval_pass_requires_non_empty_passing_graders() -> None:
    with pytest.raises(ValidationError, match="at least one grader"):
        _eval_result(grader_results=())
    with pytest.raises(ValidationError, match="non-empty passing"):
        _eval_result(
            grader_results=(
                EvalGraderResult(
                    grader_name="PersistenceGrader",
                    status=EvalGraderStatus.FAIL,
                    reason_code=EvalGraderReasonCode.MISSING_RECORD,
                ),
            )
        )


@pytest.mark.parametrize(
    "status",
    (EvalResultStatus.SKIPPED, EvalResultStatus.NOT_RUN),
)
def test_eval_non_execution_statuses_carry_no_run_or_grading_data(
    status: EvalResultStatus,
) -> None:
    disposition = _eval_result(
        status=status,
        grader_results=(),
        critical_failures=(),
        observed_outcome=None,
        trace_ref=None,
        latency_summary=None,
        usage_summary=None,
    )
    assert disposition.status is status

    with pytest.raises(ValidationError, match="cannot carry"):
        _eval_result(
            status=status,
            grader_results=(),
            critical_failures=(),
        )
    with pytest.raises(ValidationError, match="cannot carry"):
        _eval_result(
            status=status,
            grader_results=(),
            critical_failures=(),
            observed_outcome=None,
            trace_ref=None,
            latency_summary=EvalLatencySummary(total_duration_ms=1),
            usage_summary=None,
        )
    with pytest.raises(ValidationError, match="cannot carry"):
        _eval_result(
            status=status,
            grader_results=(),
            critical_failures=(),
            observed_outcome=None,
            trace_ref=None,
            latency_summary=None,
            usage_summary=EvalUsageSummary(input_tokens=0, output_tokens=0),
        )


def test_eval_projection_rejects_duplicate_grader_and_failure_codes() -> None:
    grader = _passing_grader()
    with pytest.raises(ValidationError, match="unique grader"):
        _eval_result(grader_results=(grader, grader))
    with pytest.raises(ValidationError, match="unique stable codes"):
        _eval_result(
            status=EvalResultStatus.FAIL,
            grader_results=(grader,),
            critical_failures=(
                CriticalFailureCode.CF_01,
                CriticalFailureCode.CF_01,
            ),
        )
