"""Safe Run and Trace record contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Self
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from .common import AuditOnlyModel, require_utc
from .tool_system import (
    GateDecisionValue,
    GateReasonCode,
    ToolCallStatus,
    ToolResultOutcome,
    ToolsetHash,
)

NonEmptyString = Annotated[str, Field(min_length=1)]
PositiveStateVersion = Annotated[int, Field(ge=1)]


class AgentRunStatus(StrEnum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    INCOMPLETE = "INCOMPLETE"


class StopReason(StrEnum):
    GOAL_COMPLETED = "GOAL_COMPLETED"
    NOT_FOUND_OR_NOT_ACCESSIBLE = "NOT_FOUND_OR_NOT_ACCESSIBLE"
    INPUT_INVALID = "INPUT_INVALID"
    GATE_REJECTED = "GATE_REJECTED"
    PROVIDER_PROTOCOL_ERROR = "PROVIDER_PROTOCOL_ERROR"
    ORDER_SERVICE_UNAVAILABLE = "ORDER_SERVICE_UNAVAILABLE"
    PRESENTATION_PLAN_REJECTED = "PRESENTATION_PLAN_REJECTED"
    RENDERER_INVARIANT_FAILED = "RENDERER_INVARIANT_FAILED"
    PROCESS_RESTART_DETECTED = "PROCESS_RESTART_DETECTED"


class AgentOutcome(StrEnum):
    COMPLETED = "COMPLETED"
    ASK_USER = "ASK_USER"
    BLOCKED = "BLOCKED"
    NEED_HUMAN = "NEED_HUMAN"
    NOT_FOUND_OR_NOT_ACCESSIBLE = "NOT_FOUND_OR_NOT_ACCESSIBLE"


class AgentRunRecord(AuditOnlyModel):
    run_id: UUID
    conversation_id: UUID | None = None
    status: AgentRunStatus
    provider_lane: NonEmptyString
    started_at: datetime
    completed_at: datetime | None = None
    stop_reason: StopReason | None = None
    incomplete_reason: NonEmptyString | None = None

    @field_validator("started_at", "completed_at")
    @classmethod
    def run_timestamps_are_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return require_utc(value, field_name="AgentRunRecord timestamp")

    @model_validator(mode="after")
    def run_lifecycle_is_consistent(self) -> Self:
        active = {AgentRunStatus.CREATED, AgentRunStatus.RUNNING}
        if self.status in active:
            if self.completed_at is not None or self.stop_reason is not None:
                raise ValueError("active Run cannot carry completion data")
        else:
            if self.completed_at is None:
                raise ValueError("terminal Run requires completed_at")
            if self.completed_at < self.started_at:
                raise ValueError("Run completed_at cannot precede started_at")
        if self.status is AgentRunStatus.COMPLETED and self.stop_reason is None:
            raise ValueError("completed Run requires an explicit stop_reason")
        if self.status is AgentRunStatus.INCOMPLETE:
            if self.stop_reason is not StopReason.PROCESS_RESTART_DETECTED:
                raise ValueError(
                    "thin-slice incomplete Run must record PROCESS_RESTART_DETECTED"
                )
        return self


class TraceEventType(StrEnum):
    MESSAGE_ACCEPTED = "MessageAccepted"
    RUN_STARTED = "RunStarted"
    REQUEST_UNDERSTANDING_STARTED = "RequestUnderstandingStarted"
    CONTEXT_MANIFEST_RECORDED = "ContextManifestRecorded"
    NEXT_MOVE_PROPOSED = "NextMoveProposed"
    TASK_DELTA_VALIDATED = "TaskDeltaValidated"
    TASK_DELTA_ACCEPTED = "TaskDeltaAccepted"
    INPUT_BINDING_RECORDED = "InputBindingRecorded"
    TASK_STATE_CHANGED = "TaskStateChanged"
    NEXT_MOVE_REVALIDATED = "NextMoveRevalidated"
    GATE_DECISION_RECORDED = "GateDecisionRecorded"
    TOOL_CALL_CREATED = "ToolCallCreated"
    TOOL_CALL_STARTED = "ToolCallStarted"
    TOOL_CALL_SUCCEEDED = "ToolCallSucceeded"
    TOOL_CALL_FAILED = "ToolCallFailed"
    TOOL_CALL_TIMED_OUT = "ToolCallTimedOut"
    TOOL_CALL_INTERRUPTED = "ToolCallInterrupted"
    TOOL_RESULT_NORMALIZED = "ToolResultNormalized"
    OBSERVATION_RECORDED = "ObservationRecorded"
    PRESENTATION_PLAN_PROPOSED = "PresentationPlanProposed"
    RESPONSE_RENDERED = "ResponseRendered"
    RUN_STOPPED = "RunStopped"
    EVAL_CASE_GRADED = "EvalCaseGraded"


_TERMINAL_TOOL_TRACE_STATUS: dict[TraceEventType, ToolCallStatus] = {
    TraceEventType.TOOL_CALL_SUCCEEDED: ToolCallStatus.SUCCEEDED,
    TraceEventType.TOOL_CALL_FAILED: ToolCallStatus.FAILED,
    TraceEventType.TOOL_CALL_TIMED_OUT: ToolCallStatus.TIMED_OUT,
    TraceEventType.TOOL_CALL_INTERRUPTED: ToolCallStatus.INTERRUPTED,
}


class TimingAndUsageSummary(AuditOnlyModel):
    duration_ms: Annotated[int, Field(ge=0)]
    input_tokens: Annotated[int, Field(ge=0)] | None = None
    output_tokens: Annotated[int, Field(ge=0)] | None = None


class TraceEvent(AuditOnlyModel):
    """Allowlisted cross-component projection; no arbitrary payload field exists."""

    trace_event_id: UUID
    event_type: TraceEventType
    occurred_at: datetime
    run_id: UUID
    case_id: NonEmptyString | None = None
    message_ref: UUID | None = None
    accepted_delta_ref: UUID | None = None
    task_id: UUID | None = None
    request_unit_id: UUID | None = None
    input_binding_ref: UUID | None = None
    model_call_id: UUID | None = None
    model_call_purpose: NonEmptyString | None = None
    context_manifest_id: UUID | None = None
    provider_name: NonEmptyString | None = None
    model_snapshot: NonEmptyString | None = None
    tool_registry_version: NonEmptyString | None = None
    model_visible_toolset_hash: ToolsetHash | None = None
    next_move_kind: NonEmptyString | None = None
    requested_tool_name: NonEmptyString | None = None
    proposed_base_task_state_version: PositiveStateVersion | None = None
    validated_task_state_version: PositiveStateVersion | None = None
    argument_binding_refs: tuple[UUID, ...] = ()
    gate_decision: GateDecisionValue | None = None
    gate_reason_code: GateReasonCode | None = None
    tool_call_id: UUID | None = None
    tool_call_terminal_status: ToolCallStatus | None = None
    safe_tool_outcome: ToolResultOutcome | None = None
    observation_ref: UUID | None = None
    presentation_plan_ref: UUID | None = None
    user_outcome: AgentOutcome | None = None
    stop_reason: StopReason | None = None
    timing_and_usage_summary: TimingAndUsageSummary | None = None

    @field_validator("occurred_at")
    @classmethod
    def occurred_at_is_utc(cls, value: datetime) -> datetime:
        return require_utc(value, field_name="occurred_at")

    @model_validator(mode="after")
    def stopped_event_has_outcome_and_reason(self) -> Self:
        if self.event_type is TraceEventType.RUN_STOPPED:
            if self.stop_reason is None or self.user_outcome is None:
                raise ValueError("RunStopped requires user_outcome and stop_reason")
        expected_tool_status = _TERMINAL_TOOL_TRACE_STATUS.get(self.event_type)
        if expected_tool_status is not None:
            if self.tool_call_id is None:
                raise ValueError("terminal ToolCall Trace requires tool_call_id")
            if self.tool_call_terminal_status is not expected_tool_status:
                raise ValueError(
                    "terminal ToolCall Trace event and status must match"
                )
        return self
