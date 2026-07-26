"""Application-owned records shared by Runtime, Infrastructure, and Eval."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Self
from uuid import UUID

from pydantic import (
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

from mini_agent.core.common import AuditOnlyModel, RuntimePrivateModel, require_utc
from mini_agent.core.identity import CustomerContext
from mini_agent.core.task_state import RequestUnitRecord, TaskRecord
from mini_agent.core.tool_system import (
    ToolAttemptRecord,
    ToolCallRecord,
    ToolCallStatus,
    ToolResultOutcome,
)
from mini_agent.core.trace import (
    AgentOutcome,
    AgentRunRecord,
    AgentRunStatus,
    StopReason,
)

NonEmptyString = Annotated[str, Field(min_length=1)]
MessageContent = Annotated[str, Field(min_length=1, max_length=4000)]
PositiveStateVersion = Annotated[int, Field(ge=1)]
NonNegativeCount = Annotated[int, Field(ge=0)]
PositiveAttempt = Annotated[int, Field(ge=1)]


class _StrictRuntimePrivateRecord(RuntimePrivateModel):
    model_config = ConfigDict(strict=True)


class _StrictAuditOnlyRecord(AuditOnlyModel):
    model_config = ConfigDict(strict=True)


class TrustedOwnerScope(_StrictRuntimePrivateRecord):
    """Minimum persistence scope derived by Application from trusted auth."""

    customer_id: NonEmptyString

    @model_validator(mode="before")
    @classmethod
    def scope_is_derived_from_matching_context(
        cls,
        value: object,
        info: ValidationInfo,
    ) -> object:
        validation_context = info.context or {}
        customer_context = validation_context.get("customer_context")
        if not isinstance(customer_context, CustomerContext):
            raise ValueError(
                "TrustedOwnerScope must be derived from CustomerContext"
            )
        if not isinstance(value, Mapping):
            raise ValueError("TrustedOwnerScope requires a mapping projection")
        if value.get("customer_id") != customer_context.customer_id:
            raise ValueError(
                "TrustedOwnerScope customer_id must match CustomerContext"
            )
        return value

    @classmethod
    def from_customer_context(cls, context: CustomerContext) -> Self:
        return cls.model_validate(
            {"customer_id": context.customer_id},
            context={"customer_context": context},
        )


class ConversationRecord(_StrictRuntimePrivateRecord):
    """Application-owned Conversation identity and trusted owner scope."""

    schema_version: NonEmptyString
    conversation_id: UUID
    owner_customer_id: NonEmptyString
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def created_at_is_utc(cls, value: datetime) -> datetime:
        return require_utc(value, field_name="created_at")


class MessageDirection(StrEnum):
    USER = "USER"
    ASSISTANT = "ASSISTANT"


class MessageRecord(_StrictRuntimePrivateRecord):
    """Controlled raw Conversation message; never a normal Trace payload."""

    schema_version: NonEmptyString
    message_id: UUID
    conversation_id: UUID
    direction: MessageDirection
    content: MessageContent
    received_at: datetime

    @field_validator("received_at")
    @classmethod
    def received_at_is_utc(cls, value: datetime) -> datetime:
        return require_utc(value, field_name="received_at")


class ConversationTaskLinkRecord(_StrictAuditOnlyRecord):
    """M:N Conversation-to-Task link; ``ended_at=None`` means active."""

    schema_version: NonEmptyString
    conversation_id: UUID
    task_id: UUID
    link_reason: NonEmptyString
    linked_at: datetime
    ended_at: datetime | None = None

    @field_validator("linked_at", "ended_at")
    @classmethod
    def link_timestamps_are_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return require_utc(value, field_name="ConversationTaskLinkRecord timestamp")

    @model_validator(mode="after")
    def link_dates_are_ordered(self) -> Self:
        if self.ended_at is not None and self.ended_at < self.linked_at:
            raise ValueError("ConversationTaskLink ended_at cannot precede linked_at")
        return self


class RunTaskLinkRecord(_StrictAuditOnlyRecord):
    """Run-to-Task version projection; no result version means Run is active."""

    schema_version: NonEmptyString
    run_id: UUID
    task_id: UUID
    base_task_state_version: PositiveStateVersion | None = None
    result_task_state_version: PositiveStateVersion | None = None

    @model_validator(mode="after")
    def result_version_does_not_regress(self) -> Self:
        if (
            self.base_task_state_version is not None
            and self.result_task_state_version is not None
            and self.result_task_state_version < self.base_task_state_version
        ):
            raise ValueError(
                "RunTaskLink result version cannot precede base version"
            )
        return self


_RUN_STABLE_FIELDS = (
    "run_id",
    "conversation_id",
    "provider_lane",
    "started_at",
)


class CreateRunCommand(_StrictRuntimePrivateRecord):
    """Insert-only clean CREATED Run projection."""

    created_record: AgentRunRecord

    @model_validator(mode="after")
    def record_is_clean_created_projection(self) -> Self:
        record = self.created_record
        if record.status is not AgentRunStatus.CREATED:
            raise ValueError("initial Run requires CREATED status")
        if (
            record.completed_at is not None
            or record.stop_reason is not None
            or record.incomplete_reason is not None
        ):
            raise ValueError("initial Run cannot carry completion projection")
        return self


class TransitionRunCommand(_StrictRuntimePrivateRecord):
    """Conditional normal transition from an exact active Run projection."""

    expected_active_record: AgentRunRecord
    next_record: AgentRunRecord

    @model_validator(mode="after")
    def records_form_normal_forward_transition(self) -> Self:
        expected = self.expected_active_record
        next_record = self.next_record
        if expected.status not in {AgentRunStatus.CREATED, AgentRunStatus.RUNNING}:
            raise ValueError("normal Run transition expects an active projection")
        if expected.incomplete_reason is not None:
            raise ValueError("active Run cannot carry incomplete_reason")
        allowed_next = {
            AgentRunStatus.RUNNING,
            AgentRunStatus.COMPLETED,
            AgentRunStatus.FAILED,
        }
        if next_record.status not in allowed_next:
            raise ValueError(
                "normal Run transition cannot create CREATED or INCOMPLETE"
            )
        if (
            expected.status is AgentRunStatus.RUNNING
            and next_record.status is AgentRunStatus.RUNNING
        ):
            raise ValueError("normal Run transition must move status forward")
        if next_record.incomplete_reason is not None:
            raise ValueError("normal Run transition cannot carry incomplete_reason")
        if next_record.stop_reason is StopReason.PROCESS_RESTART_DETECTED:
            raise ValueError(
                "normal Run transition cannot use recovery-only stop reason"
            )
        if any(
            getattr(expected, field_name) != getattr(next_record, field_name)
            for field_name in _RUN_STABLE_FIELDS
        ):
            raise ValueError("normal Run transition cannot change stable fields")
        return self


class MarkRunIncompleteForRecoveryCommand(_StrictRuntimePrivateRecord):
    """Conditional recovery claim from an exact active Run projection."""

    expected_active_record: AgentRunRecord
    incomplete_record: AgentRunRecord

    @model_validator(mode="after")
    def records_form_restart_projection(self) -> Self:
        expected = self.expected_active_record
        incomplete = self.incomplete_record
        if expected.status not in {AgentRunStatus.CREATED, AgentRunStatus.RUNNING}:
            raise ValueError("Run recovery expects an active projection")
        if expected.incomplete_reason is not None:
            raise ValueError("active Run cannot carry incomplete_reason")
        if incomplete.status is not AgentRunStatus.INCOMPLETE:
            raise ValueError("Run recovery requires INCOMPLETE status")
        if incomplete.stop_reason is not StopReason.PROCESS_RESTART_DETECTED:
            raise ValueError(
                "Run recovery requires PROCESS_RESTART_DETECTED stop reason"
            )
        if incomplete.incomplete_reason not in {
            None,
            "PROCESS_RESTART_DETECTED",
        }:
            raise ValueError(
                "Run recovery incomplete_reason must be absent or "
                "PROCESS_RESTART_DETECTED"
            )
        if any(
            getattr(expected, field_name) != getattr(incomplete, field_name)
            for field_name in _RUN_STABLE_FIELDS
        ):
            raise ValueError("Run recovery cannot change stable fields")
        return self


class CreateTaskCommand(_StrictRuntimePrivateRecord):
    """Insert-only Task command; Reducer owns status, this freezes version 1."""

    initial_record: TaskRecord

    @model_validator(mode="after")
    def record_is_initial(self) -> Self:
        if self.initial_record.state_version != 1:
            raise ValueError("initial Task requires state_version = 1")
        return self


class CreateRequestUnitCommand(_StrictRuntimePrivateRecord):
    """Insert-only RequestUnit command; Reducer owns status, this freezes version 1."""

    initial_record: RequestUnitRecord

    @model_validator(mode="after")
    def record_is_initial(self) -> Self:
        if self.initial_record.state_version != 1:
            raise ValueError("initial RequestUnit requires state_version = 1")
        return self


class CreateRunTaskLinkCommand(_StrictRuntimePrivateRecord):
    """Insert-only active Run-to-Task link command."""

    active_record: RunTaskLinkRecord

    @model_validator(mode="after")
    def record_is_active(self) -> Self:
        if self.active_record.result_task_state_version is not None:
            raise ValueError(
                "initial RunTaskLink requires result_task_state_version = null"
            )
        return self


class CreateToolCallCommand(_StrictRuntimePrivateRecord):
    """Insert-only pre-dispatch ToolCall command."""

    created_record: ToolCallRecord

    @model_validator(mode="after")
    def record_is_created_and_clean(self) -> Self:
        record = self.created_record
        if record.status is not ToolCallStatus.CREATED:
            raise ValueError("initial ToolCall requires CREATED status")
        if record.attempt_count != 0:
            raise ValueError("initial ToolCall requires attempt_count = 0")
        if (
            record.finished_at is not None
            or record.failure_code is not None
            or record.timeout_phase is not None
            or record.interruption_reason is not None
            or record.result_ref is not None
        ):
            raise ValueError(
                "initial ToolCall cannot carry terminal or result projection"
            )
        return self


_TOOL_IMMUTABLE_FIELDS = (
    "tool_call_id",
    "run_id",
    "task_id",
    "request_unit_id",
    "model_call_id",
    "context_manifest_id",
    "gate_decision_id",
    "provider_tool_call_id",
    "canonical_tool_name",
    "tool_registry_version",
    "validated_task_state_version",
    "argument_binding_refs",
    "effect",
    "started_at",
)


class DispatchToolCallCommand(_StrictRuntimePrivateRecord):
    """Atomic P0 dispatch fence: RUNNING plus the first started attempt."""

    expected_created_record: ToolCallRecord
    running_record: ToolCallRecord
    started_attempt: ToolAttemptRecord

    @model_validator(mode="after")
    def records_form_first_dispatch_fence(self) -> Self:
        expected = self.expected_created_record
        record = self.running_record
        attempt = self.started_attempt
        if expected.status is not ToolCallStatus.CREATED:
            raise ValueError("dispatch fence expects a CREATED ToolCall")
        if expected.attempt_count != 0:
            raise ValueError("expected CREATED ToolCall requires attempt_count = 0")
        if record.status is not ToolCallStatus.RUNNING:
            raise ValueError("dispatch fence requires RUNNING ToolCall")
        if record.attempt_count != 1 or attempt.attempt_no != 1:
            raise ValueError("P0 dispatch fence requires first attempt only")
        if any(
            getattr(expected, field_name) != getattr(record, field_name)
            for field_name in _TOOL_IMMUTABLE_FIELDS
        ):
            raise ValueError(
                "dispatch fence cannot change immutable ToolCall fields"
            )
        if record.tool_call_id != attempt.tool_call_id:
            raise ValueError("dispatch fence ToolCall and attempt ids must match")
        if (
            expected.finished_at is not None
            or expected.failure_code is not None
            or expected.timeout_phase is not None
            or expected.interruption_reason is not None
            or expected.result_ref is not None
        ):
            raise ValueError(
                "expected CREATED ToolCall cannot carry terminal projection"
            )
        if (
            attempt.finished_at is not None
            or attempt.outcome is not None
            or attempt.failure_code is not None
        ):
            raise ValueError("dispatch fence requires an unfinished attempt")
        if record.failure_code is not None or record.result_ref is not None:
            raise ValueError(
                "RUNNING dispatch fence cannot carry failure or result projection"
            )
        return self


_TERMINAL_TOOL_OUTCOMES: dict[ToolCallStatus, frozenset[ToolResultOutcome]] = {
    ToolCallStatus.SUCCEEDED: frozenset({ToolResultOutcome.SUCCESS}),
    ToolCallStatus.FAILED: frozenset(
        {
            ToolResultOutcome.BUSINESS_FAILURE,
            ToolResultOutcome.SYSTEM_FAILURE,
        }
    ),
    ToolCallStatus.TIMED_OUT: frozenset({ToolResultOutcome.TIMEOUT}),
    ToolCallStatus.INTERRUPTED: frozenset({ToolResultOutcome.INTERRUPTED}),
}


class FinalizeToolCallCommand(_StrictRuntimePrivateRecord):
    """Atomic P0 finalization of a terminal ToolCall and its first attempt."""

    expected_running_record: ToolCallRecord
    expected_started_attempt: ToolAttemptRecord
    terminal_record: ToolCallRecord
    finalized_attempt: ToolAttemptRecord

    @model_validator(mode="after")
    def records_form_consistent_finalization(self) -> Self:
        expected = self.expected_running_record
        expected_attempt = self.expected_started_attempt
        record = self.terminal_record
        attempt = self.finalized_attempt
        if expected.status is not ToolCallStatus.RUNNING:
            raise ValueError("ToolCall finalization expects RUNNING status")
        if expected.attempt_count != 1:
            raise ValueError("P0 finalization expects the first running attempt")
        valid_outcomes = _TERMINAL_TOOL_OUTCOMES.get(record.status)
        if valid_outcomes is None:
            raise ValueError("ToolCall finalization requires terminal status")
        if record.attempt_count != 1 or attempt.attempt_no != 1:
            raise ValueError("P0 ToolCall finalization requires first attempt only")
        if (
            expected_attempt.tool_call_id != expected.tool_call_id
            or expected_attempt.attempt_no != expected.attempt_count
        ):
            raise ValueError(
                "expected started attempt must match RUNNING ToolCall"
            )
        if (
            expected_attempt.finished_at is not None
            or expected_attempt.outcome is not None
            or expected_attempt.failure_code is not None
        ):
            raise ValueError(
                "expected started attempt must remain unfinished"
            )
        if any(
            getattr(expected, field_name) != getattr(record, field_name)
            for field_name in _TOOL_IMMUTABLE_FIELDS
        ):
            raise ValueError(
                "ToolCall finalization cannot change immutable fields"
            )
        if record.tool_call_id != attempt.tool_call_id:
            raise ValueError("finalized ToolCall and attempt ids must match")
        if (
            attempt.tool_call_id != expected_attempt.tool_call_id
            or attempt.attempt_no != expected_attempt.attempt_no
            or attempt.started_at != expected_attempt.started_at
        ):
            raise ValueError(
                "finalized attempt must preserve started attempt identity and time"
            )
        if (
            expected.finished_at is not None
            or expected.failure_code is not None
            or expected.timeout_phase is not None
            or expected.interruption_reason is not None
            or expected.result_ref is not None
        ):
            raise ValueError(
                "expected RUNNING ToolCall cannot carry terminal projection"
            )
        if attempt.finished_at is None or attempt.outcome is None:
            raise ValueError("ToolCall finalization requires a finalized attempt")
        if attempt.outcome not in valid_outcomes:
            raise ValueError(
                "ToolCall terminal status and attempt outcome must agree"
            )
        if record.finished_at != attempt.finished_at:
            raise ValueError(
                "ToolCall and attempt finalization timestamps must match"
            )
        if record.failure_code != attempt.failure_code:
            raise ValueError(
                "ToolCall and attempt failure_code projections must match"
            )
        return self


_RECOVERY_STABLE_TOOL_FIELDS = _TOOL_IMMUTABLE_FIELDS + (
    "attempt_count",
    "failure_code",
    "timeout_phase",
    "result_ref",
)


class InterruptToolCallForRecoveryCommand(_StrictRuntimePrivateRecord):
    """Conditional restart projection without inventing dispatch or outcome."""

    active_record: ToolCallRecord
    interrupted_record: ToolCallRecord

    @model_validator(mode="after")
    def records_preserve_recovery_facts(self) -> Self:
        active = self.active_record
        interrupted = self.interrupted_record
        if active.status not in {ToolCallStatus.CREATED, ToolCallStatus.RUNNING}:
            raise ValueError("restart interruption requires an active ToolCall")
        if interrupted.status is not ToolCallStatus.INTERRUPTED:
            raise ValueError("restart projection requires INTERRUPTED status")
        if interrupted.interruption_reason != "PROCESS_RESTART_DETECTED":
            raise ValueError(
                "restart interruption requires PROCESS_RESTART_DETECTED"
            )
        if active.attempt_count not in {0, 1}:
            raise ValueError("P0 restart recovery does not accept retry attempts")
        if active.failure_code is not None or active.result_ref is not None:
            raise ValueError(
                "active ToolCall cannot carry failure or result projection"
            )
        if any(
            getattr(active, field_name) != getattr(interrupted, field_name)
            for field_name in _RECOVERY_STABLE_TOOL_FIELDS
        ):
            raise ValueError(
                "restart interruption must preserve ToolCall identity and facts"
            )
        return self


class EvalResultStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIPPED = "SKIPPED"
    NOT_RUN = "NOT_RUN"


class InsertOnlyWriteResult(StrEnum):
    """Explicit insert result; existing identities are never overwritten."""

    INSERTED = "INSERTED"
    ALREADY_EXISTS = "ALREADY_EXISTS"


class ConditionalWriteResult(StrEnum):
    """Explicit exact-projection conditional-write result."""

    APPLIED = "APPLIED"
    PROJECTION_CONFLICT = "PROJECTION_CONFLICT"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class VersionedWriteResult(StrEnum):
    """Explicit compare-and-set result; never collapse conflict to ``False``."""

    APPLIED = "APPLIED"
    VERSION_CONFLICT = "VERSION_CONFLICT"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class RecoveryWriteResult(StrEnum):
    """Conditional startup-recovery mutation result."""

    APPLIED = "APPLIED"
    STATUS_CONFLICT = "STATUS_CONFLICT"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


class ToolDispatchFenceWriteResult(StrEnum):
    """Conditional durable fence result before any external dispatch."""

    APPLIED = "APPLIED"
    STATUS_CONFLICT = "STATUS_CONFLICT"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    ACTION_LEDGER_REQUIRED = "ACTION_LEDGER_REQUIRED"


class EvalGraderStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"


class EvalExecutionSafeErrorCode(StrEnum):
    HARNESS_SETUP_FAILED = "HARNESS_SETUP_FAILED"
    CASE_SETUP_FAILED = "CASE_SETUP_FAILED"
    TRACE_PERSISTENCE_FAILED = "TRACE_PERSISTENCE_FAILED"
    TRACE_STORE_UNAVAILABLE = "TRACE_STORE_UNAVAILABLE"
    SYSTEM_UNDER_TEST_FAILED = "SYSTEM_UNDER_TEST_FAILED"
    GRADING_FAILED = "GRADING_FAILED"
    RESULT_PERSISTENCE_FAILED = "RESULT_PERSISTENCE_FAILED"
    RESULT_COMPLETENESS_FAILED = "RESULT_COMPLETENESS_FAILED"


class EvalGraderReasonCode(StrEnum):
    TRACE_EVENT_MISSING = "TRACE_EVENT_MISSING"
    MISSING_RECORD = "MISSING_RECORD"
    ASSERTION_FAILED = "ASSERTION_FAILED"


class CriticalFailureCode(StrEnum):
    CF_01 = "CF-01"
    CF_02 = "CF-02"
    CF_03 = "CF-03"
    CF_04 = "CF-04"
    CF_05 = "CF-05"
    CF_06 = "CF-06"
    CF_07 = "CF-07"
    CF_08 = "CF-08"
    CF_09 = "CF-09"
    CF_10 = "CF-10"
    CF_11 = "CF-11"
    CF_12 = "CF-12"
    CF_13 = "CF-13"
    CF_14 = "CF-14"


class EvalGraderResult(_StrictAuditOnlyRecord):
    """Minimal explicit grader projection; owner-specific details stay elsewhere."""

    grader_name: NonEmptyString
    status: EvalGraderStatus
    reason_code: EvalGraderReasonCode | None = None

    @model_validator(mode="after")
    def grader_status_has_consistent_reason(self) -> Self:
        if self.status is EvalGraderStatus.PASS and self.reason_code is not None:
            raise ValueError("passing grader result cannot carry a failure reason")
        if self.status is EvalGraderStatus.FAIL and self.reason_code is None:
            raise ValueError("failing grader result requires a stable reason code")
        return self


class EvalVersionManifest(_StrictAuditOnlyRecord):
    """Explicit replay versions without an arbitrary metadata dictionary."""

    dataset_version: NonEmptyString
    candidate_version: NonEmptyString
    baseline_version: NonEmptyString | None = None
    fixture_versions: tuple[NonEmptyString, ...] = ()
    model_config_version: NonEmptyString | None = None
    prompt_version: NonEmptyString | None = None
    tool_registry_version: NonEmptyString | None = None
    corpus_version: NonEmptyString | None = None
    runtime_version: NonEmptyString | None = None

    @field_validator("fixture_versions")
    @classmethod
    def fixture_versions_are_unique(
        cls, value: tuple[str, ...]
    ) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("fixture_versions must be unique")
        return value


class EvalLatencySummary(_StrictAuditOnlyRecord):
    total_duration_ms: NonNegativeCount


class EvalUsageSummary(_StrictAuditOnlyRecord):
    input_tokens: NonNegativeCount
    output_tokens: NonNegativeCount


class EvalExecutionFailurePhase(StrEnum):
    HARNESS_SETUP = "HARNESS_SETUP"
    CASE_SETUP = "CASE_SETUP"
    TRACE_PERSISTENCE = "TRACE_PERSISTENCE"
    SYSTEM_UNDER_TEST = "SYSTEM_UNDER_TEST"
    GRADING = "GRADING"
    RESULT_PERSISTENCE = "RESULT_PERSISTENCE"
    RESULT_COMPLETENESS = "RESULT_COMPLETENESS"


_EVAL_ERROR_PHASES = {
    EvalExecutionSafeErrorCode.HARNESS_SETUP_FAILED: (
        EvalExecutionFailurePhase.HARNESS_SETUP
    ),
    EvalExecutionSafeErrorCode.CASE_SETUP_FAILED: (
        EvalExecutionFailurePhase.CASE_SETUP
    ),
    EvalExecutionSafeErrorCode.TRACE_PERSISTENCE_FAILED: (
        EvalExecutionFailurePhase.TRACE_PERSISTENCE
    ),
    EvalExecutionSafeErrorCode.TRACE_STORE_UNAVAILABLE: (
        EvalExecutionFailurePhase.TRACE_PERSISTENCE
    ),
    EvalExecutionSafeErrorCode.SYSTEM_UNDER_TEST_FAILED: (
        EvalExecutionFailurePhase.SYSTEM_UNDER_TEST
    ),
    EvalExecutionSafeErrorCode.GRADING_FAILED: (
        EvalExecutionFailurePhase.GRADING
    ),
    EvalExecutionSafeErrorCode.RESULT_PERSISTENCE_FAILED: (
        EvalExecutionFailurePhase.RESULT_PERSISTENCE
    ),
    EvalExecutionSafeErrorCode.RESULT_COMPLETENESS_FAILED: (
        EvalExecutionFailurePhase.RESULT_COMPLETENESS
    ),
}


class EvalExecutionFailureRecord(_StrictAuditOnlyRecord):
    """Infrastructure failure before a complete Case result can exist."""

    schema_version: NonEmptyString
    eval_run_id: UUID
    case_id: NonEmptyString | None = None
    lane: NonEmptyString
    attempt: PositiveAttempt | None = None
    failure_phase: EvalExecutionFailurePhase
    safe_error_code: EvalExecutionSafeErrorCode
    diagnostic_ref: UUID | None = None
    trace_ref: UUID | None = None
    version_manifest: EvalVersionManifest
    occurred_at: datetime

    @field_validator("occurred_at")
    @classmethod
    def occurred_at_is_utc(cls, value: datetime) -> datetime:
        return require_utc(value, field_name="occurred_at")

    @model_validator(mode="after")
    def attempt_requires_a_case(self) -> Self:
        if self.attempt is not None and self.case_id is None:
            raise ValueError("Eval failure attempt requires case_id")
        if _EVAL_ERROR_PHASES[self.safe_error_code] is not self.failure_phase:
            raise ValueError(
                "Eval safe_error_code must match failure_phase"
            )
        return self


class EvalResultRecord(_StrictAuditOnlyRecord):
    """Stable per-attempt Eval result projection."""

    schema_version: NonEmptyString
    eval_run_id: UUID
    case_id: NonEmptyString
    lane: NonEmptyString
    attempt: PositiveAttempt
    status: EvalResultStatus
    grader_results: tuple[EvalGraderResult, ...] = ()
    critical_failures: tuple[CriticalFailureCode, ...] = ()
    observed_outcome: AgentOutcome | None = None
    trace_ref: UUID | None = None
    version_manifest: EvalVersionManifest
    latency_summary: EvalLatencySummary | None = None
    usage_summary: EvalUsageSummary | None = None
    completed_at: datetime

    @field_validator("completed_at")
    @classmethod
    def completed_at_is_utc(cls, value: datetime) -> datetime:
        return require_utc(value, field_name="completed_at")

    @model_validator(mode="after")
    def result_lifecycle_is_consistent(self) -> Self:
        grader_names = tuple(result.grader_name for result in self.grader_results)
        if len(grader_names) != len(set(grader_names)):
            raise ValueError("grader_results must contain unique grader names")
        if len(self.critical_failures) != len(set(self.critical_failures)):
            raise ValueError("critical_failures must contain unique stable codes")

        any_grader_failed = any(
            result.status is EvalGraderStatus.FAIL
            for result in self.grader_results
        )
        if self.critical_failures and self.status is not EvalResultStatus.FAIL:
            raise ValueError("critical failure requires overall FAIL status")
        if self.status in {EvalResultStatus.PASS, EvalResultStatus.FAIL}:
            if (
                self.observed_outcome is None
                or self.trace_ref is None
                or not self.grader_results
            ):
                raise ValueError(
                    "PASS/FAIL requires outcome, Trace, and at least one grader"
                )
        if self.status is EvalResultStatus.PASS:
            if any_grader_failed:
                raise ValueError("PASS requires non-empty passing grader results")
        elif self.status is EvalResultStatus.FAIL:
            if not self.critical_failures and not any_grader_failed:
                raise ValueError("FAIL requires a failing grader or critical failure")
        elif (
            self.observed_outcome is not None
            or self.trace_ref is not None
            or self.grader_results
            or self.critical_failures
            or self.latency_summary is not None
            or self.usage_summary is not None
        ):
            raise ValueError(
                "SKIPPED/NOT_RUN cannot carry execution or grading data"
            )
        return self
