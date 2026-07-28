"""Application-owned records shared by Runtime, Infrastructure, and Eval."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from typing import Any, Annotated, Self, TypeVar
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)

from mini_agent.core.common import (
    AuditOnlyModel,
    RuntimePrivateModel,
    UserVisibleModel,
    require_utc,
)
from mini_agent.core.identity import CustomerContext
from mini_agent.core.memory import ContextManifest, OrderObservation
from mini_agent.core.task_state import (
    AcceptedTaskDelta,
    AcceptedTaskDeltaV2,
    CandidateValidationDecision,
    InputBinding,
    RequestUnderstandingRecord,
    RequestUnderstandingRecordV2,
    RequestUnitRecord,
    TaskRecord,
    TaskStateTransition,
    TaskStatus,
)
from mini_agent.core.tool_system import (
    GateDecision,
    GateDecisionValue,
    ModelVisibleToolsetArtifact,
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

NonEmptyString = Annotated[str, Field(min_length=1)]
MessageContent = Annotated[str, Field(min_length=1, max_length=4000)]
PositiveStateVersion = Annotated[int, Field(ge=1)]
NonNegativeCount = Annotated[int, Field(ge=0)]
PositiveAttempt = Annotated[int, Field(ge=1)]


class _StrictRuntimePrivateRecord(RuntimePrivateModel):
    model_config = ConfigDict(strict=True)


class _StrictAuditOnlyRecord(AuditOnlyModel):
    model_config = ConfigDict(strict=True)


class _StrictUserVisibleRecord(UserVisibleModel):
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
            raise ValueError("TrustedOwnerScope must be derived from CustomerContext")
        if not isinstance(value, Mapping):
            raise ValueError("TrustedOwnerScope requires a mapping projection")
        if value.get("customer_id") != customer_context.customer_id:
            raise ValueError("TrustedOwnerScope customer_id must match CustomerContext")
        return value

    @classmethod
    def from_customer_context(cls, context: CustomerContext) -> Self:
        return cls.model_validate(
            {"customer_id": context.customer_id},
            context={"customer_context": context},
        )


class AgentRunCommand(_StrictRuntimePrivateRecord):
    """Trusted Application input; transport DTOs must terminate before this model."""

    customer_context: CustomerContext
    message: MessageContent

    @field_validator("customer_context", mode="before")
    @classmethod
    def context_is_an_existing_trusted_model(
        cls,
        value: object,
    ) -> CustomerContext:
        if type(value) is not CustomerContext:
            raise ValueError("customer_context must be a CustomerContext instance")
        return value


class AgentRunResult(_StrictUserVisibleRecord):
    """Approved user-visible result with no trusted identity or internal record."""

    run_id: UUID
    outcome: AgentOutcome
    message: MessageContent


class ProviderProtocolError(Exception):
    """Bounded Provider contract violation with no caller-controlled diagnostic."""

    __slots__ = ()

    def __init__(self) -> None:
        super().__init__("PROVIDER_PROTOCOL_ERROR")


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
            raise ValueError("RunTaskLink result version cannot precede base version")
        return self


class SaveRequestUnderstandingCommand(_StrictRuntimePrivateRecord):
    """Persist one RequestUnderstanding with its exact accepted logical children."""

    record: RequestUnderstandingRecord
    accepted_deltas: Annotated[
        tuple[AcceptedTaskDelta, ...],
        Field(min_length=1, max_length=1),
    ]

    @model_validator(mode="after")
    def accepted_children_are_exact_and_parent_bound(self) -> Self:
        accepted_refs = self.record.accepted_delta_refs
        child_ids = tuple(child.accepted_delta_id for child in self.accepted_deltas)
        if len(accepted_refs) != len(set(accepted_refs)) or len(child_ids) != len(
            set(child_ids)
        ):
            raise ValueError(
                "RequestUnderstanding requires unique accepted child identities"
            )
        if set(accepted_refs) != set(child_ids):
            raise ValueError(
                "RequestUnderstanding requires the exact accepted child set"
            )
        for child in self.accepted_deltas:
            if child.message_ref != self.record.message_ref:
                raise ValueError(
                    "accepted child message_ref must match RequestUnderstanding"
                )
            matching_candidates = tuple(
                candidate
                for candidate in self.record.candidate_validation
                if candidate.candidate_ref == child.candidate_ref
            )
            if (
                len(matching_candidates) != 1
                or matching_candidates[0].decision
                is not CandidateValidationDecision.ACCEPT
            ):
                raise ValueError(
                    "accepted child must bind exactly one accepted candidate"
                )
            if len(child.input_binding_refs) != len(set(child.input_binding_refs)):
                raise ValueError(
                    "accepted child requires unique InputBinding references"
                )
        return self


class SaveInputBindingCommand(_StrictRuntimePrivateRecord):
    """Persist an InputBinding with its external-required RequestUnit identity."""

    record: InputBinding
    request_unit_id: UUID

    @model_validator(mode="after")
    def source_references_are_unique(self) -> Self:
        if len(self.record.source_refs) != len(set(self.record.source_refs)):
            raise ValueError("InputBinding source references must be unique")
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
    """Conditional normal start from an exact CREATED Run projection."""

    expected_active_record: AgentRunRecord
    next_record: AgentRunRecord

    @model_validator(mode="after")
    def records_form_exact_start_transition(self) -> Self:
        expected = self.expected_active_record
        next_record = self.next_record
        if expected.status is not AgentRunStatus.CREATED:
            raise ValueError("Run start expects CREATED status")
        if expected.incomplete_reason is not None:
            raise ValueError("active Run cannot carry incomplete_reason")
        if next_record.status is not AgentRunStatus.RUNNING:
            raise ValueError("Run start requires RUNNING status")
        if next_record.incomplete_reason is not None:
            raise ValueError("Run start cannot carry incomplete_reason")
        if any(
            getattr(expected, field_name) != getattr(next_record, field_name)
            for field_name in _RUN_STABLE_FIELDS
        ):
            raise ValueError("Run start cannot change stable fields")
        return self


_ModelT = TypeVar("_ModelT", bound=BaseModel)


def _canonical_model_field_projection(
    value: object,
    expected_type: type[_ModelT],
    *,
    error_message: str,
) -> dict[str, object]:
    if type(value) is not expected_type:
        raise ValueError(error_message)
    field_names = frozenset(expected_type.model_fields)
    if (
        frozenset(vars(value)) != field_names
        or not value.model_fields_set.issubset(field_names)
        or value.__pydantic_extra__ is not None
        or value.__pydantic_private__ is not None
    ):
        raise ValueError(error_message)
    return {
        field_name: getattr(value, field_name)
        for field_name in expected_type.model_fields
    }


def _strict_validate_canonical_projection(
    expected_type: type[_ModelT],
    projection: Mapping[str, object],
    *,
    error_message: str,
) -> _ModelT:
    try:
        return expected_type.model_validate(projection, strict=True)
    except ValidationError:
        raise ValueError(error_message) from None


def _strict_rebuild_exact_model(
    value: object,
    expected_type: type[_ModelT],
    *,
    error_message: str,
) -> _ModelT:
    projection = _canonical_model_field_projection(
        value,
        expected_type,
        error_message=error_message,
    )
    return _strict_validate_canonical_projection(
        expected_type,
        projection,
        error_message=error_message,
    )


def _strict_rebuild_terminal_trace_event(value: object) -> TraceEvent:
    error_message = "terminal TraceEvent must be canonical"
    projection = _canonical_model_field_projection(
        value,
        TraceEvent,
        error_message=error_message,
    )
    timing_summary = projection["timing_and_usage_summary"]
    if timing_summary is not None:
        projection["timing_and_usage_summary"] = _strict_rebuild_exact_model(
            timing_summary,
            TimingAndUsageSummary,
            error_message=error_message,
        )
    return _strict_validate_canonical_projection(
        TraceEvent,
        projection,
        error_message=error_message,
    )


_COMPLETED_FINALIZATION_ROWS = frozenset(
    {
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
    }
)
_TRACE_EVENT_FIELD_NAMES = frozenset(TraceEvent.model_fields)
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
_FINALIZE_VALIDATION_FALLBACK = "FinalizeRunCommand validation failed"
_FINALIZE_SAFE_ERROR_TYPE_MESSAGES = {
    "frozen_instance": "Instance is frozen",
}
_FINALIZE_SAFE_VALIDATION_MESSAGES = frozenset(
    {
        "terminal result must be canonical",
        "ASSISTANT Message must be canonical",
        "Task transition must be recursively canonical",
        "terminal TraceEvent must be canonical",
        "FinalizeRunCommand must be canonical",
        "Run finalization expects RUNNING status",
        "Run finalization rejects a dirty expected active Run",
        "Run finalization requires a terminal Run",
        "normal Run finalization cannot use recovery-only stop reason",
        "normal terminal Run cannot carry incomplete_reason",
        "COMPLETED Run requires conversation_id",
        "FAILED Run cannot carry stop_reason",
        "Run finalization cannot change stable fields",
        "active RunTaskLink must belong to the Run",
        "active RunTaskLink must have no result Task version",
        "RunTaskLink identities must be unique",
        "terminal RunTaskLink must belong to the Run",
        "terminal RunTaskLink requires a result Task version",
        "Run finalization requires the exact RunTaskLink set",
        "terminal RunTaskLink must preserve its active projection",
        "result Task identities must be unique",
        "Run finalization requires one exact result Task per link Task identity",
        "RunTaskLink result Task version must match result Task",
        (
            "FAILED Run requires empty Task transition, terminal result, "
            "ASSISTANT Message and terminal Trace projections"
        ),
        "COMPLETED Run with a link requires its Task transition",
        "COMPLETED Run without a link cannot carry a Task transition",
        "COMPLETED Run requires a terminal result",
        "terminal result requires an exact AgentRunResult",
        "COMPLETED Run requires an ASSISTANT Message",
        "ASSISTANT Message requires an exact MessageRecord",
        "Run without a Task cannot carry result Tasks",
        "Run without a Task terminal Trace may contain only RunStopped",
        "Task transition expected and next Task must equal the link Task",
        "Task transition cannot precede active link base Task version",
        "terminal Task and RequestUnit require the same status/version",
        "result Task projection must equal the exact next Task",
        "Task transition cannot follow Run completion",
        (
            "Task terminal Trace must be ordered exactly as "
            "TaskStateChanged, RunStopped"
        ),
        "COMPLETED Run projection is outside the closed terminal matrix",
        "terminal result must bind the terminal Run",
        "ASSISTANT Message requires schema_version message_record.p0.v1",
        "ASSISTANT Message requires ASSISTANT direction",
        "ASSISTANT Message must bind the terminal Conversation",
        "ASSISTANT Message content must equal terminal result",
        "ASSISTANT Message timestamp must equal Run completion",
        "terminal Trace event identities must be unique",
        "every terminal Trace event must bind the terminal Run",
        (
            "TaskStateChanged terminal Trace only allows its exact per-kind "
            "projection"
        ),
        (
            "RunStopped terminal Trace only allows its exact per-kind projection"
        ),
        "TaskStateChanged must bind the terminal Task/RequestUnit",
        "TaskStateChanged timestamp must equal Task transition",
        "RunStopped stop reason must equal terminal Run",
        "RunStopped outcome must equal terminal result",
        "RunStopped timestamp must equal Run completion",
    }
)


def _bounded_finalize_validation_message(
    line_error: Mapping[str, object],
) -> str:
    error_type = line_error.get("type")
    if type(error_type) is str:
        safe_error_type_message = _FINALIZE_SAFE_ERROR_TYPE_MESSAGES.get(
            error_type
        )
        if safe_error_type_message is not None:
            return safe_error_type_message
    context = line_error.get("ctx")
    if not isinstance(context, Mapping):
        return _FINALIZE_VALIDATION_FALLBACK
    source_error = context.get("error")
    if type(source_error) is not ValueError or len(source_error.args) != 1:
        return _FINALIZE_VALIDATION_FALLBACK
    candidate = source_error.args[0]
    if (
        type(candidate) is str
        and candidate in _FINALIZE_SAFE_VALIDATION_MESSAGES
    ):
        return candidate
    return _FINALIZE_VALIDATION_FALLBACK


def _new_finalize_validation_error(safe_message: str) -> ValidationError:
    if (
        safe_message != _FINALIZE_VALIDATION_FALLBACK
        and safe_message not in _FINALIZE_SAFE_ERROR_TYPE_MESSAGES.values()
        and safe_message not in _FINALIZE_SAFE_VALIDATION_MESSAGES
    ):
        safe_message = _FINALIZE_VALIDATION_FALLBACK
    return ValidationError.from_exception_data(
        "FinalizeRunCommand",
        [
            {
                "type": "value_error",
                "loc": ("finalize_run_command",),
                "input": None,
                "ctx": {"error": ValueError(safe_message)},
            }
        ],
        input_type="python",
        hide_input=True,
    )


def _sanitize_finalize_validation_error(
    error: ValidationError,
) -> ValidationError:
    source_line_errors = error.errors(
        include_url=False,
        include_context=True,
        include_input=False,
    )
    safe_message = (
        _bounded_finalize_validation_message(source_line_errors[0])
        if source_line_errors
        else _FINALIZE_VALIDATION_FALLBACK
    )
    return _new_finalize_validation_error(safe_message)


class _FinalizeRunCommandMeta(type(_StrictRuntimePrivateRecord)):
    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        try:
            return super().__call__(*args, **kwargs)
        except ValidationError as error:
            sanitized_error = _sanitize_finalize_validation_error(error)
        raise sanitized_error from None


class FinalizeRunCommand(
    _StrictRuntimePrivateRecord,
    metaclass=_FinalizeRunCommandMeta,
):
    """One validated aggregate for a normal terminal turn."""

    model_config = ConfigDict(
        hide_input_in_errors=True,
        revalidate_instances="always",
    )

    expected_active_record: AgentRunRecord
    terminal_record: AgentRunRecord
    expected_active_links: Annotated[
        tuple[RunTaskLinkRecord, ...],
        Field(max_length=1),
    ]
    terminal_links: Annotated[
        tuple[RunTaskLinkRecord, ...],
        Field(max_length=1),
    ]
    result_task_records: Annotated[
        tuple[TaskRecord, ...],
        Field(max_length=1),
    ]
    task_transition: ApplyTaskTransitionCommand | None = None
    terminal_result: AgentRunResult | None = None
    assistant_message: MessageRecord | None = None
    terminal_trace_events: Annotated[
        tuple[TraceEvent, ...],
        Field(max_length=2),
    ] = ()

    def __setattr__(self, name: str, value: Any) -> None:
        try:
            super().__setattr__(name, value)
        except ValidationError as error:
            sanitized_error = _sanitize_finalize_validation_error(error)
        else:
            return
        raise sanitized_error from None

    def __delattr__(self, name: str) -> None:
        try:
            super().__delattr__(name)
        except ValidationError as error:
            sanitized_error = _sanitize_finalize_validation_error(error)
        else:
            return
        raise sanitized_error from None

    def model_copy(
        self,
        *,
        update: Mapping[str, Any] | None = None,
        deep: bool = False,
    ) -> Self:
        copied_source = self.__deepcopy__() if deep else self.__copy__()
        try:
            complete_projection = _canonical_model_field_projection(
                copied_source,
                type(self),
                error_message="FinalizeRunCommand must be canonical",
            )
        except ValueError:
            sanitized_error = _new_finalize_validation_error(
                "FinalizeRunCommand must be canonical"
            )
        else:
            restored_fields_set = set(copied_source.model_fields_set)
            updated_field_names: set[str] = set()
            if update:
                updated_field_names.update(update)
                if not updated_field_names.issubset(complete_projection):
                    raise _new_finalize_validation_error(
                        "FinalizeRunCommand must be canonical"
                    ) from None
                complete_projection.update(update)
                restored_fields_set.update(updated_field_names)
            rebuilt = type(self).model_validate(complete_projection)
            for field_name in updated_field_names:
                object.__setattr__(
                    copied_source,
                    field_name,
                    getattr(rebuilt, field_name),
                )
            object.__setattr__(
                copied_source,
                "__pydantic_fields_set__",
                restored_fields_set,
            )
            return copied_source
        raise sanitized_error from None

    @classmethod
    def model_validate(
        cls,
        obj: Any,
        **kwargs: Any,
    ) -> Self:
        if isinstance(obj, cls):
            try:
                obj = _canonical_model_field_projection(
                    obj,
                    cls,
                    error_message="FinalizeRunCommand must be canonical",
                )
            except ValueError:
                sanitized_error = _new_finalize_validation_error(
                    "FinalizeRunCommand must be canonical"
                )
            else:
                sanitized_error = None
            if sanitized_error is not None:
                raise sanitized_error from None
        try:
            return super().model_validate(obj, **kwargs)
        except ValidationError as error:
            sanitized_error = _sanitize_finalize_validation_error(error)
        raise sanitized_error from None

    @classmethod
    def model_validate_json(
        cls,
        json_data: str | bytes | bytearray,
        **kwargs: Any,
    ) -> Self:
        try:
            return super().model_validate_json(json_data, **kwargs)
        except ValidationError as error:
            sanitized_error = _sanitize_finalize_validation_error(error)
        raise sanitized_error from None

    @classmethod
    def model_validate_strings(
        cls,
        obj: Any,
        **kwargs: Any,
    ) -> Self:
        try:
            return super().model_validate_strings(obj, **kwargs)
        except ValidationError as error:
            sanitized_error = _sanitize_finalize_validation_error(error)
        raise sanitized_error from None

    @field_validator("task_transition")
    @classmethod
    def task_transition_is_recursively_canonical(
        cls,
        value: ApplyTaskTransitionCommand | None,
    ) -> ApplyTaskTransitionCommand | None:
        if value is None:
            return None
        return _strict_rebuild_task_transition(value)

    @field_validator("terminal_result")
    @classmethod
    def terminal_result_is_canonical(
        cls,
        value: AgentRunResult | None,
    ) -> AgentRunResult | None:
        if value is None:
            return None
        return _strict_rebuild_exact_model(
            value,
            AgentRunResult,
            error_message="terminal result must be canonical",
        )

    @field_validator("assistant_message")
    @classmethod
    def assistant_message_is_canonical(
        cls,
        value: MessageRecord | None,
    ) -> MessageRecord | None:
        if value is None:
            return None
        return _strict_rebuild_exact_model(
            value,
            MessageRecord,
            error_message="ASSISTANT Message must be canonical",
        )

    @field_validator("terminal_trace_events")
    @classmethod
    def terminal_trace_events_are_canonical(
        cls,
        events: tuple[TraceEvent, ...],
    ) -> tuple[TraceEvent, ...]:
        return tuple(_strict_rebuild_terminal_trace_event(event) for event in events)

    @model_validator(mode="after")
    def terminal_projection_is_exact_and_graph_closed(self) -> Self:
        expected = self.expected_active_record
        terminal = self.terminal_record
        if expected.status is not AgentRunStatus.RUNNING:
            raise ValueError("Run finalization expects RUNNING status")
        if expected.incomplete_reason is not None:
            raise ValueError("Run finalization rejects a dirty expected active Run")
        if terminal.status not in {
            AgentRunStatus.COMPLETED,
            AgentRunStatus.FAILED,
        }:
            raise ValueError("Run finalization requires a terminal Run")
        if terminal.stop_reason is StopReason.PROCESS_RESTART_DETECTED:
            raise ValueError(
                "normal Run finalization cannot use recovery-only stop reason"
            )
        if terminal.incomplete_reason is not None:
            raise ValueError("normal terminal Run cannot carry incomplete_reason")
        if (
            terminal.status is AgentRunStatus.COMPLETED
            and terminal.conversation_id is None
        ):
            raise ValueError("COMPLETED Run requires conversation_id")
        if (
            terminal.status is AgentRunStatus.FAILED
            and terminal.stop_reason is not None
        ):
            raise ValueError("FAILED Run cannot carry stop_reason")
        if any(
            getattr(expected, field_name) != getattr(terminal, field_name)
            for field_name in _RUN_STABLE_FIELDS
        ):
            raise ValueError("Run finalization cannot change stable fields")

        expected_by_task: dict[UUID, RunTaskLinkRecord] = {}
        for link in self.expected_active_links:
            if link.run_id != expected.run_id:
                raise ValueError("active RunTaskLink must belong to the Run")
            if link.result_task_state_version is not None:
                raise ValueError("active RunTaskLink must have no result Task version")
            if link.task_id in expected_by_task:
                raise ValueError("RunTaskLink identities must be unique")
            expected_by_task[link.task_id] = link

        terminal_by_task: dict[UUID, RunTaskLinkRecord] = {}
        for link in self.terminal_links:
            if link.run_id != expected.run_id:
                raise ValueError("terminal RunTaskLink must belong to the Run")
            if link.result_task_state_version is None:
                raise ValueError("terminal RunTaskLink requires a result Task version")
            if link.task_id in terminal_by_task:
                raise ValueError("RunTaskLink identities must be unique")
            terminal_by_task[link.task_id] = link
        if set(expected_by_task) != set(terminal_by_task):
            raise ValueError("Run finalization requires the exact RunTaskLink set")
        for task_id, expected_link in expected_by_task.items():
            terminal_link = terminal_by_task[task_id]
            if (
                terminal_link.schema_version != expected_link.schema_version
                or terminal_link.base_task_state_version
                != expected_link.base_task_state_version
            ):
                raise ValueError(
                    "terminal RunTaskLink must preserve its active projection"
                )

        task_by_id: dict[UUID, TaskRecord] = {}
        for task_record in self.result_task_records:
            if task_record.task_id in task_by_id:
                raise ValueError("result Task identities must be unique")
            task_by_id[task_record.task_id] = task_record
        if set(task_by_id) != set(terminal_by_task):
            raise ValueError(
                "Run finalization requires one exact result Task per link Task "
                "identity"
            )
        for task_id, terminal_link in terminal_by_task.items():
            if (
                terminal_link.result_task_state_version
                != task_by_id[task_id].state_version
            ):
                raise ValueError(
                    "RunTaskLink result Task version must match result Task"
                )

        if terminal.status is AgentRunStatus.FAILED:
            if (
                self.task_transition is not None
                or self.terminal_result is not None
                or self.assistant_message is not None
                or self.terminal_trace_events
            ):
                raise ValueError(
                    "FAILED Run requires empty Task transition, terminal result, "
                    "ASSISTANT Message and terminal Trace projections"
                )
            return self

        has_task = bool(expected_by_task)
        transition = self.task_transition
        if has_task and transition is None:
            raise ValueError("COMPLETED Run with a link requires its Task transition")
        if not has_task and transition is not None:
            raise ValueError(
                "COMPLETED Run without a link cannot carry a Task transition"
            )

        result = self.terminal_result
        if result is None:
            raise ValueError("COMPLETED Run requires a terminal result")
        if type(result) is not AgentRunResult:
            raise ValueError("terminal result requires an exact AgentRunResult")
        message = self.assistant_message
        if message is None:
            raise ValueError("COMPLETED Run requires an ASSISTANT Message")
        if type(message) is not MessageRecord:
            raise ValueError("ASSISTANT Message requires an exact MessageRecord")

        task_status: TaskStatus | None = None
        event_types = tuple(event.event_type for event in self.terminal_trace_events)
        if transition is None:
            if self.result_task_records:
                raise ValueError("Run without a Task cannot carry result Tasks")
            if event_types != (TraceEventType.RUN_STOPPED,):
                raise ValueError(
                    "Run without a Task terminal Trace may contain only RunStopped"
                )
        else:
            link_task_id = next(iter(expected_by_task))
            if (
                transition.expected_task_record.task_id != link_task_id
                or transition.next_task_record.task_id != link_task_id
            ):
                raise ValueError(
                    "Task transition expected and next Task must equal the link Task"
                )
            active_link_base_version = expected_by_task[
                link_task_id
            ].base_task_state_version
            if (
                active_link_base_version is not None
                and transition.expected_task_record.state_version
                < active_link_base_version
            ):
                raise ValueError(
                    "Task transition cannot precede active link base Task version"
                )
            next_task = transition.next_task_record
            next_unit = transition.next_request_unit_record
            if (
                next_task.status is not next_unit.status
                or next_task.state_version != next_unit.state_version
            ):
                raise ValueError(
                    "terminal Task and RequestUnit require the same status/version"
                )
            if self.result_task_records != (next_task,):
                raise ValueError(
                    "result Task projection must equal the exact next Task"
                )
            if transition.task_state_transition.changed_at > terminal.completed_at:
                raise ValueError("Task transition cannot follow Run completion")
            task_status = next_task.status
            if event_types != (
                TraceEventType.TASK_STATE_CHANGED,
                TraceEventType.RUN_STOPPED,
            ):
                raise ValueError(
                    "Task terminal Trace must be ordered exactly as "
                    "TaskStateChanged, RunStopped"
                )

        matrix_row = (
            terminal.stop_reason,
            has_task,
            result.outcome,
            task_status,
        )
        if matrix_row not in _COMPLETED_FINALIZATION_ROWS:
            raise ValueError(
                "COMPLETED Run projection is outside the closed terminal matrix"
            )
        if result.run_id != terminal.run_id:
            raise ValueError("terminal result must bind the terminal Run")
        if message.schema_version != "message_record.p0.v1":
            raise ValueError(
                "ASSISTANT Message requires schema_version message_record.p0.v1"
            )
        if message.direction is not MessageDirection.ASSISTANT:
            raise ValueError("ASSISTANT Message requires ASSISTANT direction")
        if message.conversation_id != terminal.conversation_id:
            raise ValueError("ASSISTANT Message must bind the terminal Conversation")
        if message.content != result.message:
            raise ValueError("ASSISTANT Message content must equal terminal result")
        if message.received_at != terminal.completed_at:
            raise ValueError(
                "ASSISTANT Message timestamp must equal Run completion"
            )

        event_ids = tuple(
            event.trace_event_id for event in self.terminal_trace_events
        )
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("terminal Trace event identities must be unique")
        for event in self.terminal_trace_events:
            if event.run_id != terminal.run_id:
                raise ValueError(
                    "every terminal Trace event must bind the terminal Run"
                )
            allowed_fields = _TERMINAL_TRACE_ALLOWED_FIELDS[event.event_type]
            for field_name, field_info in TraceEvent.model_fields.items():
                if field_name in allowed_fields:
                    continue
                if getattr(event, field_name) != field_info.default:
                    raise ValueError(
                        f"{event.event_type.value} terminal Trace only allows "
                        "its exact per-kind projection"
                    )

        if transition is not None:
            task_changed = self.terminal_trace_events[0]
            if (
                task_changed.task_id != transition.next_task_record.task_id
                or task_changed.request_unit_id
                != transition.next_request_unit_record.request_unit_id
            ):
                raise ValueError(
                    "TaskStateChanged must bind the terminal Task/RequestUnit"
                )
            if (
                task_changed.occurred_at
                != transition.task_state_transition.changed_at
            ):
                raise ValueError(
                    "TaskStateChanged timestamp must equal Task transition"
                )

        run_stopped = self.terminal_trace_events[-1]
        if run_stopped.stop_reason is not terminal.stop_reason:
            raise ValueError("RunStopped stop reason must equal terminal Run")
        if run_stopped.user_outcome is not result.outcome:
            raise ValueError("RunStopped outcome must equal terminal result")
        if run_stopped.occurred_at != terminal.completed_at:
            raise ValueError("RunStopped timestamp must equal Run completion")
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


class CreateInitialTaskGraphCommand(_StrictRuntimePrivateRecord):
    """One conditional write for the accepted initial goal and all projections."""

    owner_scope: TrustedOwnerScope
    expected_conversation_record: ConversationRecord
    expected_message_record: MessageRecord
    expected_active_run_record: AgentRunRecord
    request_understanding: SaveRequestUnderstandingCommand
    initial_task: CreateTaskCommand
    initial_request_unit: CreateRequestUnitCommand
    input_bindings: Annotated[
        tuple[SaveInputBindingCommand, ...],
        Field(min_length=1, max_length=1),
    ]
    conversation_task_link: ConversationTaskLinkRecord
    run_task_link: CreateRunTaskLinkCommand

    @model_validator(mode="after")
    def graph_is_owner_consistent_and_bijective(self) -> Self:
        conversation = self.expected_conversation_record
        message = self.expected_message_record
        run = self.expected_active_run_record
        understanding = self.request_understanding
        task = self.initial_task.initial_record
        request_unit = self.initial_request_unit.initial_record
        conversation_link = self.conversation_task_link
        run_link = self.run_task_link.active_record

        if conversation.owner_customer_id != self.owner_scope.customer_id:
            raise ValueError("Conversation must match the trusted owner scope")
        if task.owner_customer_id != self.owner_scope.customer_id:
            raise ValueError("initial Task must match the trusted owner scope")
        if (
            message.direction is not MessageDirection.USER
            or message.conversation_id != conversation.conversation_id
        ):
            raise ValueError(
                "initial graph requires the exact USER message in Conversation"
            )
        if run.status is not AgentRunStatus.RUNNING:
            raise ValueError("initial graph requires a RUNNING Run")
        if run.incomplete_reason is not None:
            raise ValueError("initial graph requires a clean active Run")
        if run.conversation_id != conversation.conversation_id:
            raise ValueError("active Run must belong to the Conversation")
        if (
            understanding.record.run_id != run.run_id
            or understanding.record.message_ref != message.message_id
        ):
            raise ValueError("RequestUnderstanding must bind the exact Run and Message")
        if request_unit.task_id != task.task_id:
            raise ValueError("initial RequestUnit must belong to initial Task")
        if (
            request_unit.state_version != task.state_version
            or request_unit.status is not task.status
        ):
            raise ValueError(
                "initial Task and RequestUnit must share version and status"
            )
        if (
            len(request_unit.goal_source_refs) != 1
            or request_unit.goal_source_refs[0] != message.message_id
        ):
            raise ValueError(
                "initial RequestUnit goal source must be the exact USER message"
            )

        binding_by_id: dict[UUID, SaveInputBindingCommand] = {}
        for binding in self.input_bindings:
            binding_id = binding.record.binding_id
            if binding_id in binding_by_id:
                raise ValueError("InputBinding identities must be unique")
            if binding.request_unit_id != request_unit.request_unit_id:
                raise ValueError("InputBinding must bind the initial RequestUnit")
            if binding.record.source_refs != (message.message_id,):
                raise ValueError("InputBinding source must be the exact USER message")
            binding_by_id[binding_id] = binding
        request_unit_binding_ids = tuple(request_unit.input_binding_refs)
        if len(request_unit_binding_ids) != len(set(request_unit_binding_ids)) or set(
            request_unit_binding_ids
        ) != set(binding_by_id):
            raise ValueError("initial graph requires exact InputBinding identities")

        accepted_binding_ids = {
            binding_id
            for delta in understanding.accepted_deltas
            for binding_id in delta.input_binding_refs
        }
        if accepted_binding_ids != set(binding_by_id):
            raise ValueError(
                "accepted deltas and RequestUnit require the same InputBindings"
            )
        if (
            len(understanding.accepted_deltas) != 1
            or understanding.accepted_deltas[0].goal_text != request_unit.goal_text
        ):
            raise ValueError(
                "initial RequestUnit must map bijectively to one accepted goal"
            )

        if (
            conversation_link.conversation_id != conversation.conversation_id
            or conversation_link.task_id != task.task_id
            or conversation_link.ended_at is not None
        ):
            raise ValueError(
                "ConversationTaskLink must be the active initial Task link"
            )
        if (
            run_link.run_id != run.run_id
            or run_link.task_id != task.task_id
            or run_link.base_task_state_version is not None
        ):
            raise ValueError("RunTaskLink must bind the Run to its newly created Task")
        return self


_TASK_STABLE_FIELDS = (
    "task_id",
    "owner_customer_id",
    "created_at",
)

_REQUEST_UNIT_STABLE_FIELDS = (
    "request_unit_id",
    "task_id",
    "goal_text",
    "goal_source_refs",
    "contextualization_ref",
    "constraint_refs",
    "dependency_refs",
    "input_binding_refs",
    "created_at",
)


class ApplyTaskTransitionCommand(_StrictRuntimePrivateRecord):
    """Atomically advance one Task, RequestUnit and TaskStateTransition."""

    expected_task_record: TaskRecord
    next_task_record: TaskRecord
    expected_request_unit_record: RequestUnitRecord
    next_request_unit_record: RequestUnitRecord
    task_state_transition: TaskStateTransition

    @model_validator(mode="after")
    def projections_form_one_exact_transition(self) -> Self:
        expected_task = self.expected_task_record
        next_task = self.next_task_record
        expected_unit = self.expected_request_unit_record
        next_unit = self.next_request_unit_record
        transition = self.task_state_transition

        if expected_task.task_id != next_task.task_id:
            raise ValueError("Task identity cannot change")
        if expected_task.owner_customer_id != next_task.owner_customer_id:
            raise ValueError("Task owner cannot change")
        if any(
            getattr(expected_task, field_name) != getattr(next_task, field_name)
            for field_name in _TASK_STABLE_FIELDS
        ):
            raise ValueError("Task stable fields cannot change")
        if expected_unit.request_unit_id != next_unit.request_unit_id:
            raise ValueError("RequestUnit identity cannot change")
        if any(
            getattr(expected_unit, field_name) != getattr(next_unit, field_name)
            for field_name in _REQUEST_UNIT_STABLE_FIELDS
        ):
            raise ValueError("RequestUnit stable fields cannot change")
        if (
            expected_unit.task_id != expected_task.task_id
            or next_unit.task_id != next_task.task_id
            or transition.task_id != expected_task.task_id
            or transition.request_unit_id != expected_unit.request_unit_id
        ):
            raise ValueError("Task transition must bind one exact Task and RequestUnit")
        if (
            expected_task.state_version != transition.base_state_version
            or expected_unit.state_version != transition.base_state_version
        ):
            raise ValueError(
                "Task and RequestUnit must match the transition base version"
            )
        if (
            next_task.state_version != transition.result_state_version
            or next_unit.state_version != transition.result_state_version
        ):
            raise ValueError(
                "Task and RequestUnit must match the transition result version"
            )
        if (
            expected_task.status is not transition.from_status
            or expected_unit.status is not transition.from_status
            or next_task.status is not transition.to_status
            or next_unit.status is not transition.to_status
        ):
            raise ValueError("Task and RequestUnit status must match the transition")
        if (
            next_task.updated_at < expected_task.updated_at
            or next_unit.updated_at < expected_unit.updated_at
            or next_task.updated_at != transition.changed_at
            or next_unit.updated_at != transition.changed_at
        ):
            raise ValueError(
                "next projections must use the transition change timestamp"
            )
        return self


def _strict_rebuild_task_transition(
    value: object,
) -> ApplyTaskTransitionCommand:
    error_message = "Task transition must be recursively canonical"
    projection = _canonical_model_field_projection(
        value,
        ApplyTaskTransitionCommand,
        error_message=error_message,
    )
    nested_types: dict[str, type[BaseModel]] = {
        "expected_task_record": TaskRecord,
        "next_task_record": TaskRecord,
        "expected_request_unit_record": RequestUnitRecord,
        "next_request_unit_record": RequestUnitRecord,
        "task_state_transition": TaskStateTransition,
    }
    for field_name, expected_type in nested_types.items():
        projection[field_name] = _strict_rebuild_exact_model(
            projection[field_name],
            expected_type,
            error_message=error_message,
        )
    return _strict_validate_canonical_projection(
        ApplyTaskTransitionCommand,
        projection,
        error_message=error_message,
    )


FinalizeRunCommand.model_rebuild()


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
            raise ValueError("dispatch fence cannot change immutable ToolCall fields")
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
            raise ValueError("expected started attempt must match RUNNING ToolCall")
        if (
            expected_attempt.finished_at is not None
            or expected_attempt.outcome is not None
            or expected_attempt.failure_code is not None
        ):
            raise ValueError("expected started attempt must remain unfinished")
        if any(
            getattr(expected, field_name) != getattr(record, field_name)
            for field_name in _TOOL_IMMUTABLE_FIELDS
        ):
            raise ValueError("ToolCall finalization cannot change immutable fields")
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
            raise ValueError("ToolCall terminal status and attempt outcome must agree")
        if record.finished_at != attempt.finished_at:
            raise ValueError("ToolCall and attempt finalization timestamps must match")
        if record.failure_code != attempt.failure_code:
            raise ValueError("ToolCall and attempt failure_code projections must match")
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
            raise ValueError("restart interruption requires PROCESS_RESTART_DETECTED")
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


class SaveObservationCommand(_StrictRuntimePrivateRecord):
    """Persist a safe Observation against one exact successful Read ToolCall."""

    owner_scope: TrustedOwnerScope
    observation_record: OrderObservation
    source_tool_call_record: ToolCallRecord

    @model_validator(mode="after")
    def source_is_exact_successful_get_order_read(self) -> Self:
        source = self.source_tool_call_record
        if source.status is not ToolCallStatus.SUCCEEDED:
            raise ValueError("Observation source ToolCall must be SUCCEEDED")
        if source.effect is not ToolEffect.READ:
            raise ValueError("Observation source ToolCall must be READ")
        if (
            source.canonical_tool_name != "get_order"
            or self.observation_record.source_tool != "get_order"
        ):
            raise ValueError("Observation source must be canonical get_order")
        return self


class TaskRecoveryAggregate(_StrictRuntimePrivateRecord):
    """Strictly decoded Task plus the complete history visible in this closure."""

    task_record: TaskRecord
    task_state_transitions: Annotated[
        tuple[TaskStateTransition, ...],
        Field(max_length=1),
    ]

    @model_validator(mode="after")
    def transition_history_is_complete_contiguous_and_unique(self) -> Self:
        task = self.task_record
        transitions = self.task_state_transitions
        if task.state_version == 1:
            if transitions:
                raise ValueError("Task version 1 has no transition history")
            return self

        if task.state_version != len(transitions) + 1:
            raise ValueError(
                "Task recovery requires a complete contiguous transition history"
            )
        if any(
            transition.result_state_version != expected_result_version
            for expected_result_version, transition in enumerate(
                transitions,
                start=2,
            )
        ):
            raise ValueError(
                "Task recovery requires a complete contiguous transition history"
            )
        if transitions[0].changed_at < task.created_at:
            raise ValueError("Task transition cannot occur before Task creation")
        identities = tuple(
            (
                transition.task_id,
                transition.request_unit_id,
                transition.result_state_version,
            )
            for transition in transitions
        )
        if len(identities) != len(set(identities)):
            raise ValueError("Task transition identities must be unique")
        if any(transition.task_id != task.task_id for transition in transitions):
            raise ValueError("Task transition history must preserve Task identity")
        if any(
            current.to_status is not following.from_status
            for current, following in zip(transitions, transitions[1:])
        ):
            raise ValueError(
                "Task recovery requires a complete contiguous status chain"
            )
        if transitions[-1].to_status is not task.status:
            raise ValueError(
                "Task transition terminal status must match Task projection"
            )
        if any(
            current.changed_at > following.changed_at
            for current, following in zip(transitions, transitions[1:])
        ):
            raise ValueError("Task transition timestamps must be ordered")
        if transitions[-1].changed_at > task.updated_at:
            raise ValueError("Task projection cannot precede its terminal transition")
        return self


class ToolCallRecoveryAggregate(_StrictRuntimePrivateRecord):
    """Strictly decoded ToolCall plus its exact existing attempt children."""

    tool_call_record: ToolCallRecord
    tool_attempt_records: Annotated[
        tuple[ToolAttemptRecord, ...],
        Field(max_length=1),
    ]

    @model_validator(mode="after")
    def attempt_history_is_exact_and_lifecycle_consistent(self) -> Self:
        call = self.tool_call_record
        attempts = self.tool_attempt_records
        if call.attempt_count > 1:
            raise ValueError("P0 ToolCall recovery does not accept retry attempts")
        if call.status in {ToolCallStatus.CREATED, ToolCallStatus.RUNNING} and (
            call.failure_code is not None or call.result_ref is not None
        ):
            raise ValueError(
                "active ToolCall cannot carry failure or result projection"
            )
        actual_numbers = tuple(attempt.attempt_no for attempt in attempts)
        expected_numbers = tuple(range(1, call.attempt_count + 1))
        if actual_numbers != expected_numbers:
            raise ValueError("ToolCall recovery requires the exact attempt sequence")
        if any(attempt.tool_call_id != call.tool_call_id for attempt in attempts):
            raise ValueError("ToolAttempt history must preserve ToolCall identity")
        if call.status is ToolCallStatus.CREATED:
            return self
        if call.status is ToolCallStatus.RUNNING:
            if (
                not attempts
                or attempts[-1].finished_at is not None
                or attempts[-1].outcome is not None
                or any(
                    attempt.finished_at is None or attempt.outcome is None
                    for attempt in attempts[:-1]
                )
            ):
                raise ValueError(
                    "RUNNING ToolCall requires one active terminal attempt"
                )
            return self

        if call.status is ToolCallStatus.INTERRUPTED:
            if attempts and any(
                attempt.finished_at is None or attempt.outcome is None
                for attempt in attempts[:-1]
            ):
                raise ValueError("INTERRUPTED ToolCall has inconsistent prior attempts")
            if (
                attempts
                and attempts[-1].finished_at is not None
                and attempts[-1].outcome is not ToolResultOutcome.INTERRUPTED
            ):
                raise ValueError(
                    "INTERRUPTED ToolCall finalized attempt must be INTERRUPTED"
                )
            if (
                attempts
                and attempts[-1].finished_at is not None
                and call.finished_at != attempts[-1].finished_at
            ):
                raise ValueError("ToolCall and finalized attempt timestamps must match")
            return self

        if any(
            attempt.finished_at is None or attempt.outcome is None
            for attempt in attempts
        ):
            raise ValueError("terminal ToolCall requires finalized attempts")
        terminal_outcomes = {
            ToolCallStatus.SUCCEEDED: frozenset({ToolResultOutcome.SUCCESS}),
            ToolCallStatus.FAILED: frozenset(
                {
                    ToolResultOutcome.BUSINESS_FAILURE,
                    ToolResultOutcome.SYSTEM_FAILURE,
                }
            ),
            ToolCallStatus.TIMED_OUT: frozenset({ToolResultOutcome.TIMEOUT}),
        }
        if attempts[-1].outcome not in terminal_outcomes.get(
            call.status,
            frozenset(),
        ):
            raise ValueError(
                "ToolCall terminal status and final attempt outcome must agree"
            )
        if call.finished_at != attempts[-1].finished_at:
            raise ValueError("ToolCall and final attempt timestamps must match")
        if call.failure_code != attempts[-1].failure_code:
            raise ValueError("ToolCall and final attempt failure_code must match")
        return self


_RECOVERY_ACTIVE_TASK_STATUSES = frozenset(
    {
        TaskStatus.ACTIVE,
        TaskStatus.WAITING_USER,
        TaskStatus.PENDING_ACTION,
        TaskStatus.ACTION_IN_PROGRESS,
        TaskStatus.RECOVERING,
    }
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


class RestartRecoveryClosure(_StrictRuntimePrivateRecord):
    """Internally consistent decoded recovery graph guarded by an opaque fence.

    This model validates only the records supplied to it. It does not prove that
    a database returned a complete closed set; Infrastructure must establish that
    under one transactionally consistent snapshot or an equivalent exact fence.
    """

    closure_fence: UUID
    conversation_record: ConversationRecord
    active_run_record: AgentRunRecord
    conversation_task_links: Annotated[
        tuple[ConversationTaskLinkRecord, ...],
        Field(max_length=1),
    ]
    run_task_links: Annotated[
        tuple[RunTaskLinkRecord, ...],
        Field(max_length=1),
    ]
    task_aggregates: Annotated[
        tuple[TaskRecoveryAggregate, ...],
        Field(max_length=1),
    ]
    request_unit_records: Annotated[
        tuple[RequestUnitRecord, ...],
        Field(max_length=1),
    ]
    tool_call_aggregates: Annotated[
        tuple[ToolCallRecoveryAggregate, ...],
        Field(max_length=1),
    ]

    @model_validator(mode="after")
    def supplied_graph_is_internally_owner_consistent(self) -> Self:
        conversation = self.conversation_record
        run = self.active_run_record
        if run.status not in {
            AgentRunStatus.CREATED,
            AgentRunStatus.RUNNING,
        }:
            raise ValueError("recovery closure requires an active Run")
        if run.incomplete_reason is not None:
            raise ValueError("active recovery Run cannot carry incomplete_reason")
        if (
            run.conversation_id is None
            or run.conversation_id != conversation.conversation_id
        ):
            raise ValueError("active Run must identify the recovery Conversation")
        if run.status is AgentRunStatus.CREATED and any(
            (
                self.conversation_task_links,
                self.run_task_links,
                self.task_aggregates,
                self.request_unit_records,
                self.tool_call_aggregates,
            )
        ):
            raise ValueError("CREATED Run recovery graph must be empty")

        task_by_id: dict[UUID, TaskRecoveryAggregate] = {}
        for aggregate in self.task_aggregates:
            task_id = aggregate.task_record.task_id
            if task_id in task_by_id:
                raise ValueError("Task recovery identities must be unique")
            if (
                aggregate.task_record.owner_customer_id
                != conversation.owner_customer_id
            ):
                raise ValueError("recovery Task owner must match Conversation owner")
            task_by_id[task_id] = aggregate

        run_link_by_task: dict[UUID, RunTaskLinkRecord] = {}
        for link in self.run_task_links:
            if link.run_id != run.run_id:
                raise ValueError("RunTaskLink must belong to the active Run")
            if link.result_task_state_version is not None:
                raise ValueError("recovery RunTaskLink must remain active")
            if link.task_id in run_link_by_task:
                raise ValueError("RunTaskLink identities must be unique")
            run_link_by_task[link.task_id] = link
        if set(run_link_by_task) != set(task_by_id):
            raise ValueError("RunTaskLink set must match the recovery Task set")
        if any(
            link.base_task_state_version is not None
            and link.base_task_state_version
            > task_by_id[task_id].task_record.state_version
            for task_id, link in run_link_by_task.items()
        ):
            raise ValueError(
                "RunTaskLink base version cannot exceed its current Task version"
            )

        conversation_link_tasks: set[UUID] = set()
        for link in self.conversation_task_links:
            if (
                link.conversation_id != conversation.conversation_id
                or link.ended_at is not None
            ):
                raise ValueError(
                    "ConversationTaskLink must be active in the Conversation"
                )
            if link.task_id in conversation_link_tasks:
                raise ValueError("ConversationTaskLink Task identities must be unique")
            conversation_link_tasks.add(link.task_id)
        if conversation_link_tasks != set(task_by_id):
            raise ValueError(
                "ConversationTaskLink set must match the recovery Task set"
            )

        unit_by_id: dict[UUID, RequestUnitRecord] = {}
        unit_by_task: dict[UUID, RequestUnitRecord] = {}
        for unit in self.request_unit_records:
            if unit.request_unit_id in unit_by_id:
                raise ValueError("RequestUnit identities must be unique")
            if unit.task_id not in task_by_id:
                raise ValueError("RequestUnit cannot be orphaned from a Task")
            if unit.task_id in unit_by_task:
                raise ValueError("recovery requires one exact RequestUnit per Task")
            task = task_by_id[unit.task_id].task_record
            if (
                unit.status is not task.status
                or unit.state_version != task.state_version
            ):
                raise ValueError(
                    "RequestUnit current status/version must match its Task"
                )
            unit_by_id[unit.request_unit_id] = unit
            unit_by_task[unit.task_id] = unit
        if set(unit_by_task) != set(task_by_id):
            raise ValueError("RequestUnit closed set must match the recovery Task set")
        for aggregate in self.task_aggregates:
            for transition in aggregate.task_state_transitions:
                unit = unit_by_id.get(transition.request_unit_id)
                if unit is None or unit.task_id != aggregate.task_record.task_id:
                    raise ValueError(
                        "Task transition RequestUnit must exist in its Task graph"
                    )

        tool_ids: set[UUID] = set()
        for aggregate in self.tool_call_aggregates:
            tool_call = aggregate.tool_call_record
            if tool_call.tool_call_id in tool_ids:
                raise ValueError("ToolCall identities must be unique")
            tool_ids.add(tool_call.tool_call_id)
            unit = unit_by_id.get(tool_call.request_unit_id)
            task = task_by_id.get(tool_call.task_id)
            if (
                tool_call.status not in {ToolCallStatus.CREATED, ToolCallStatus.RUNNING}
                or tool_call.run_id != run.run_id
                or task is None
                or unit is None
                or unit.task_id != tool_call.task_id
            ):
                raise ValueError(
                    "active ToolCall owner graph must match Run/Task/RequestUnit"
                )
            if tool_call.validated_task_state_version != task.task_record.state_version:
                raise ValueError(
                    "active ToolCall validated Task version must match its Task"
                )
            if not set(tool_call.argument_binding_refs).issubset(
                unit.input_binding_refs
            ):
                raise ValueError(
                    "active ToolCall argument bindings must belong to its RequestUnit"
                )
        return self


class ApplyRestartRecoveryCommand(_StrictRuntimePrivateRecord):
    """One fenced atomic apply for every Runtime/Core recovery projection."""

    expected_closure: RestartRecoveryClosure
    run_transition: MarkRunIncompleteForRecoveryCommand
    tool_call_transitions: Annotated[
        tuple[InterruptToolCallForRecoveryCommand, ...],
        Field(max_length=1),
    ]
    task_transitions: Annotated[
        tuple[ApplyTaskTransitionCommand, ...],
        Field(max_length=1),
    ]
    terminal_run_task_links: Annotated[
        tuple[RunTaskLinkRecord, ...],
        Field(max_length=1),
    ]
    recovery_trace_events: Annotated[
        tuple[TraceEvent, ...],
        Field(min_length=1, max_length=3),
    ]

    @field_validator("recovery_trace_events")
    @classmethod
    def recovery_trace_events_are_canonical(
        cls,
        events: tuple[TraceEvent, ...],
    ) -> tuple[TraceEvent, ...]:
        canonical_events: list[TraceEvent] = []
        for event in events:
            if type(event) is not TraceEvent:
                raise ValueError("recovery Trace requires exact TraceEvent records")
            event_field_names = frozenset(vars(event))
            has_only_known_fields = event.model_fields_set.issubset(
                _TRACE_EVENT_FIELD_NAMES
            )
            has_no_hidden_storage = (
                event.__pydantic_extra__ is None and event.__pydantic_private__ is None
            )
            if (
                event_field_names != _TRACE_EVENT_FIELD_NAMES
                or not has_only_known_fields
                or not has_no_hidden_storage
            ):
                raise ValueError(
                    "recovery TraceEvent records must contain only canonical fields"
                )
            canonical_events.append(
                TraceEvent.model_validate(
                    dict(vars(event)),
                    strict=True,
                )
            )
        return tuple(canonical_events)

    @model_validator(mode="after")
    def next_projections_are_bijective_with_expected_closure(self) -> Self:
        closure = self.expected_closure
        if self.run_transition.expected_active_record != closure.active_run_record:
            raise ValueError("Run transition must use the expected closure Run")

        expected_tool_by_id = {
            aggregate.tool_call_record.tool_call_id: aggregate.tool_call_record
            for aggregate in closure.tool_call_aggregates
        }
        actual_tool_by_id: dict[UUID, InterruptToolCallForRecoveryCommand] = {}
        for transition in self.tool_call_transitions:
            tool_call_id = transition.active_record.tool_call_id
            if tool_call_id in actual_tool_by_id:
                raise ValueError("ToolCall transition identities must be unique")
            if expected_tool_by_id.get(tool_call_id) != transition.active_record:
                raise ValueError(
                    "ToolCall transition must use its exact closure projection"
                )
            actual_tool_by_id[tool_call_id] = transition
        if set(actual_tool_by_id) != set(expected_tool_by_id):
            raise ValueError("recovery requires the exact ToolCall transition set")

        task_by_id = {
            aggregate.task_record.task_id: aggregate.task_record
            for aggregate in closure.task_aggregates
        }
        unit_by_task = {unit.task_id: unit for unit in closure.request_unit_records}
        recoverable_task_ids = {
            task_id
            for task_id, task in task_by_id.items()
            if task.status in _RECOVERY_ACTIVE_TASK_STATUSES
        }
        transition_by_task: dict[UUID, ApplyTaskTransitionCommand] = {}
        for transition in self.task_transitions:
            task_id = transition.expected_task_record.task_id
            if task_id in transition_by_task:
                raise ValueError("Task transition identities must be unique")
            if (
                task_by_id.get(task_id) != transition.expected_task_record
                or unit_by_task.get(task_id) != transition.expected_request_unit_record
            ):
                raise ValueError("Task transition must use exact closure projections")
            if (
                transition.next_task_record.status is not TaskStatus.BLOCKED
                or transition.next_request_unit_record.status is not TaskStatus.BLOCKED
            ):
                raise ValueError("restart recovery Task transition must end BLOCKED")
            transition_by_task[task_id] = transition
        if set(transition_by_task) != recoverable_task_ids:
            raise ValueError("recovery requires the exact Task transition set")

        expected_link_by_task = {link.task_id: link for link in closure.run_task_links}
        terminal_link_by_task: dict[UUID, RunTaskLinkRecord] = {}
        for link in self.terminal_run_task_links:
            if link.task_id in terminal_link_by_task:
                raise ValueError("terminal RunTaskLink identities must be unique")
            expected_link = expected_link_by_task.get(link.task_id)
            if (
                expected_link is None
                or link.run_id != expected_link.run_id
                or link.schema_version != expected_link.schema_version
                or link.base_task_state_version != expected_link.base_task_state_version
                or link.result_task_state_version is None
            ):
                raise ValueError(
                    "terminal RunTaskLink must preserve its closure projection"
                )
            expected_result_version = (
                transition_by_task[link.task_id].next_task_record.state_version
                if link.task_id in transition_by_task
                else task_by_id[link.task_id].state_version
            )
            if link.result_task_state_version != expected_result_version:
                raise ValueError(
                    "RunTaskLink result Task version must match recovery result"
                )
            terminal_link_by_task[link.task_id] = link
        if set(terminal_link_by_task) != set(expected_link_by_task):
            raise ValueError("recovery requires the exact terminal RunTaskLink set")
        return self

    @model_validator(mode="after")
    def recovery_trace_is_exact_bounded_and_projection_safe(self) -> Self:
        events = self.recovery_trace_events
        event_ids = tuple(event.trace_event_id for event in events)
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("recovery Trace event identities must be unique")

        run_id = self.expected_closure.active_run_record.run_id
        for event in events:
            allowed_fields = _RECOVERY_TRACE_ALLOWED_FIELDS.get(event.event_type)
            if allowed_fields is None:
                raise ValueError("unsupported recovery Trace event type")
            if event.run_id != run_id:
                raise ValueError(
                    "every recovery Trace event must use the same recovery Run"
                )
            for field_name in TraceEvent.model_fields:
                if field_name in allowed_fields:
                    continue
                value = getattr(event, field_name)
                if value is not None and value != ():
                    raise ValueError(
                        f"{event.event_type.value} recovery Trace only allows "
                        "its exact per-kind projection"
                    )

        run_stopped_events = tuple(
            event for event in events if event.event_type is TraceEventType.RUN_STOPPED
        )
        if len(run_stopped_events) != 1:
            raise ValueError("recovery Trace requires exactly one RunStopped event")
        run_stopped = run_stopped_events[0]
        if run_stopped.user_outcome is not AgentOutcome.BLOCKED:
            raise ValueError("recovery RunStopped requires BLOCKED user outcome")
        if run_stopped.stop_reason is not StopReason.PROCESS_RESTART_DETECTED:
            raise ValueError("recovery RunStopped requires PROCESS_RESTART_DETECTED")
        if (
            run_stopped.occurred_at
            != self.run_transition.incomplete_record.completed_at
        ):
            raise ValueError(
                "recovery RunStopped must use the Run completion timestamp"
            )

        expected_task_events = {
            (
                transition.next_task_record.task_id,
                transition.next_request_unit_record.request_unit_id,
            ): transition.task_state_transition.changed_at
            for transition in self.task_transitions
        }
        actual_task_events: dict[tuple[UUID | None, UUID | None], datetime] = {}
        for event in events:
            if event.event_type is not TraceEventType.TASK_STATE_CHANGED:
                continue
            identity = (event.task_id, event.request_unit_id)
            if identity in actual_task_events:
                raise ValueError(
                    "recovery TaskStateChanged event identities must be unique"
                )
            actual_task_events[identity] = event.occurred_at
        if set(actual_task_events) != set(expected_task_events):
            raise ValueError("recovery requires the exact TaskStateChanged event set")
        if any(
            actual_task_events[identity] != changed_at
            for identity, changed_at in expected_task_events.items()
        ):
            raise ValueError(
                "recovery TaskStateChanged must use the Task transition timestamp"
            )

        expected_tool_events = {
            transition.interrupted_record.tool_call_id: (
                transition.interrupted_record.finished_at
            )
            for transition in self.tool_call_transitions
        }
        actual_tool_events: dict[UUID | None, datetime] = {}
        for event in events:
            if event.event_type is not TraceEventType.TOOL_CALL_INTERRUPTED:
                continue
            if event.tool_call_terminal_status is not ToolCallStatus.INTERRUPTED:
                raise ValueError(
                    "recovery ToolCallInterrupted requires INTERRUPTED status"
                )
            if event.tool_call_id in actual_tool_events:
                raise ValueError(
                    "recovery ToolCallInterrupted event identities must be unique"
                )
            actual_tool_events[event.tool_call_id] = event.occurred_at
        if set(actual_tool_events) != set(expected_tool_events):
            raise ValueError(
                "recovery requires the exact ToolCallInterrupted event set"
            )
        if any(
            actual_tool_events[identity] != finished_at
            for identity, finished_at in expected_tool_events.items()
        ):
            raise ValueError(
                "recovery ToolCallInterrupted must use the ToolCall interruption "
                "timestamp"
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


class ObservationWriteResult(StrEnum):
    """Conditional Observation insert/replay result."""

    INSERTED = "INSERTED"
    ALREADY_APPLIED = "ALREADY_APPLIED"
    SOURCE_PROJECTION_CONFLICT = "SOURCE_PROJECTION_CONFLICT"


class VersionedWriteResult(StrEnum):
    """Explicit compare-and-set result; never collapse conflict to ``False``."""

    APPLIED = "APPLIED"
    VERSION_CONFLICT = "VERSION_CONFLICT"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class RecoveryWriteResult(StrEnum):
    """Exact fenced startup-recovery mutation result."""

    APPLIED = "APPLIED"
    CLOSURE_CONFLICT = "CLOSURE_CONFLICT"
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
    def fixture_versions_are_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
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
    EvalExecutionSafeErrorCode.GRADING_FAILED: (EvalExecutionFailurePhase.GRADING),
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
            raise ValueError("Eval safe_error_code must match failure_phase")
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
            result.status is EvalGraderStatus.FAIL for result in self.grader_results
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
            raise ValueError("SKIPPED/NOT_RUN cannot carry execution or grading data")
        return self


class RequestUnderstandingCandidateInvalidError(Exception):
    """Bounded invalid-candidate signal with no caller-controlled diagnostic."""

    __slots__ = ()

    def __init__(self) -> None:
        super().__init__("REQUEST_UNDERSTANDING_CANDIDATE_INVALID")


_EXACT_EVIDENCE_TUPLE_TYPES: dict[str, type[BaseModel]] = {
    "message_records": MessageRecord,
    "accepted_task_deltas": AcceptedTaskDeltaV2,
    "input_binding_records": InputBinding,
    "task_records": TaskRecord,
    "task_state_transitions": TaskStateTransition,
    "request_unit_records": RequestUnitRecord,
    "conversation_task_links": ConversationTaskLinkRecord,
    "run_task_links": RunTaskLinkRecord,
    "gate_decisions": GateDecision,
    "tool_calls": ToolCallRecord,
    "tool_attempts": ToolAttemptRecord,
    "observation_records": OrderObservation,
    "context_manifests": ContextManifest,
    "model_visible_toolset_artifacts": ModelVisibleToolsetArtifact,
    "trace_events": TraceEvent,
}

_EXACT_EVIDENCE_TOOL_LIFECYCLE_STATUS: dict[
    TraceEventType,
    ToolCallStatus,
] = {
    TraceEventType.TOOL_CALL_CREATED: ToolCallStatus.CREATED,
    TraceEventType.TOOL_CALL_STARTED: ToolCallStatus.RUNNING,
    TraceEventType.TOOL_CALL_SUCCEEDED: ToolCallStatus.SUCCEEDED,
    TraceEventType.TOOL_CALL_FAILED: ToolCallStatus.FAILED,
    TraceEventType.TOOL_CALL_TIMED_OUT: ToolCallStatus.TIMED_OUT,
    TraceEventType.TOOL_CALL_INTERRUPTED: ToolCallStatus.INTERRUPTED,
}


def _exact_evidence_unique(
    identities: tuple[object, ...],
    *,
    family_name: str,
) -> None:
    if len(identities) != len(set(identities)):
        raise ValueError(f"{family_name} identities must be unique")


def _exact_evidence_require_unique_refs(
    references: tuple[UUID, ...],
    *,
    field_name: str,
) -> None:
    if len(references) != len(set(references)):
        raise ValueError(f"{field_name} references must be unique")


def _exact_evidence_expand_supersedes(
    initial_refs: set[UUID],
    records_by_id: Mapping[UUID, InputBinding] | Mapping[UUID, OrderObservation],
    *,
    family_name: str,
) -> set[UUID]:
    reachable: set[UUID] = set()
    for initial_ref in initial_refs:
        path: set[UUID] = set()
        current_ref: UUID | None = initial_ref
        while current_ref is not None and current_ref not in reachable:
            if current_ref in path:
                raise ValueError(f"{family_name} supersedes graph must be acyclic")
            current = records_by_id.get(current_ref)
            if current is None:
                raise ValueError(
                    f"{family_name} reference must resolve in closure"
                )
            path.add(current_ref)
            current_ref = current.supersedes
        reachable.update(path)
    return reachable


class ExactRunEvidenceClosure(_StrictRuntimePrivateRecord):
    """Internally closed logical records for exactly one owner-scoped Run.

    This DTO validates only the supplied graph. Infrastructure remains
    responsible for proving exact physical rows, versions, provenance, metadata,
    and database closed-set completeness in one consistent snapshot or fence.
    """

    conversation_record: ConversationRecord
    run_record: AgentRunRecord
    message_records: tuple[MessageRecord, ...]
    request_understanding_record: RequestUnderstandingRecordV2 | None
    accepted_task_deltas: tuple[AcceptedTaskDeltaV2, ...]
    input_binding_records: tuple[InputBinding, ...]
    task_records: tuple[TaskRecord, ...]
    task_state_transitions: tuple[TaskStateTransition, ...]
    request_unit_records: tuple[RequestUnitRecord, ...]
    conversation_task_links: tuple[ConversationTaskLinkRecord, ...]
    run_task_links: tuple[RunTaskLinkRecord, ...]
    gate_decisions: tuple[GateDecision, ...]
    tool_calls: tuple[ToolCallRecord, ...]
    tool_attempts: tuple[ToolAttemptRecord, ...]
    observation_records: tuple[OrderObservation, ...]
    context_manifests: tuple[ContextManifest, ...]
    model_visible_toolset_artifacts: tuple[ModelVisibleToolsetArtifact, ...]
    trace_events: tuple[TraceEvent, ...]

    @field_validator("conversation_record", "run_record", mode="before")
    @classmethod
    def root_records_are_exact(
        cls,
        value: object,
        info: ValidationInfo,
    ) -> BaseModel:
        expected_type = (
            ConversationRecord
            if info.field_name == "conversation_record"
            else AgentRunRecord
        )
        return _strict_rebuild_exact_model(
            value,
            expected_type,
            error_message=f"{info.field_name} must be a canonical exact record",
        )

    @field_validator("request_understanding_record", mode="before")
    @classmethod
    def request_understanding_record_is_exact_or_absent(
        cls,
        value: object,
    ) -> RequestUnderstandingRecordV2 | None:
        if value is None:
            return None
        return _strict_rebuild_exact_model(
            value,
            RequestUnderstandingRecordV2,
            error_message=(
                "request_understanding_record must be a canonical exact v2 record"
            ),
        )

    @field_validator(*_EXACT_EVIDENCE_TUPLE_TYPES, mode="before")
    @classmethod
    def record_families_are_exact_tuples(
        cls,
        value: object,
        info: ValidationInfo,
    ) -> tuple[BaseModel, ...]:
        if type(value) is not tuple:
            raise ValueError(f"{info.field_name} must be an exact tuple")
        expected_type = _EXACT_EVIDENCE_TUPLE_TYPES[info.field_name]
        return tuple(
            _strict_rebuild_exact_model(
                record,
                expected_type,
                error_message=(
                    f"{info.field_name} must contain canonical exact records"
                ),
            )
            for record in value
        )

    @model_validator(mode="after")
    def supplied_graph_is_exact_and_root_closed(self) -> Self:
        conversation = self.conversation_record
        run = self.run_record
        if (
            run.conversation_id is None
            or run.conversation_id != conversation.conversation_id
        ):
            raise ValueError("Run must identify the exact closure Conversation")

        _exact_evidence_unique(
            tuple(message.message_id for message in self.message_records),
            family_name="Message",
        )
        _exact_evidence_unique(
            tuple(
                child.accepted_delta_id for child in self.accepted_task_deltas
            ),
            family_name="AcceptedTaskDelta",
        )
        _exact_evidence_unique(
            tuple(binding.binding_id for binding in self.input_binding_records),
            family_name="InputBinding",
        )
        _exact_evidence_unique(
            tuple(task.task_id for task in self.task_records),
            family_name="Task",
        )
        _exact_evidence_unique(
            tuple(
                (
                    transition.task_id,
                    transition.request_unit_id,
                    transition.result_state_version,
                )
                for transition in self.task_state_transitions
            ),
            family_name="TaskStateTransition",
        )
        _exact_evidence_unique(
            tuple(unit.request_unit_id for unit in self.request_unit_records),
            family_name="RequestUnit",
        )
        _exact_evidence_unique(
            tuple(
                (link.conversation_id, link.task_id, link.linked_at)
                for link in self.conversation_task_links
            ),
            family_name="ConversationTaskLink",
        )
        _exact_evidence_unique(
            tuple(link.task_id for link in self.run_task_links),
            family_name="RunTaskLink",
        )
        _exact_evidence_unique(
            tuple(gate.gate_decision_id for gate in self.gate_decisions),
            family_name="GateDecision",
        )
        _exact_evidence_unique(
            tuple(call.tool_call_id for call in self.tool_calls),
            family_name="ToolCall",
        )
        _exact_evidence_unique(
            tuple(
                (attempt.tool_call_id, attempt.attempt_no)
                for attempt in self.tool_attempts
            ),
            family_name="ToolAttempt",
        )
        _exact_evidence_unique(
            tuple(
                observation.observation_id
                for observation in self.observation_records
            ),
            family_name="Observation",
        )
        _exact_evidence_unique(
            tuple(
                manifest.context_manifest_id
                for manifest in self.context_manifests
            ),
            family_name="ContextManifest",
        )
        _exact_evidence_unique(
            tuple(
                artifact.model_visible_toolset_hash
                for artifact in self.model_visible_toolset_artifacts
            ),
            family_name="ModelVisibleToolsetArtifact",
        )
        _exact_evidence_unique(
            tuple(event.trace_event_id for event in self.trace_events),
            family_name="TraceEvent",
        )

        message_by_id = {
            message.message_id: message for message in self.message_records
        }
        binding_by_id = {
            binding.binding_id: binding for binding in self.input_binding_records
        }
        task_by_id = {task.task_id: task for task in self.task_records}
        unit_by_id = {
            unit.request_unit_id: unit for unit in self.request_unit_records
        }
        gate_by_id = {
            gate.gate_decision_id: gate for gate in self.gate_decisions
        }
        call_by_id = {call.tool_call_id: call for call in self.tool_calls}
        observation_by_id = {
            observation.observation_id: observation
            for observation in self.observation_records
        }
        manifest_by_id = {
            manifest.context_manifest_id: manifest
            for manifest in self.context_manifests
        }
        artifact_by_hash = {
            artifact.model_visible_toolset_hash: artifact
            for artifact in self.model_visible_toolset_artifacts
        }
        accepted_by_id = {
            child.accepted_delta_id: child
            for child in self.accepted_task_deltas
        }

        if any(
            message.conversation_id != conversation.conversation_id
            for message in self.message_records
        ):
            raise ValueError("every Message must belong to the root Conversation")

        referenced_message_ids: set[UUID] = set()
        referenced_binding_ids: set[UUID] = set()
        referenced_observation_ids: set[UUID] = set()
        referenced_artifact_hashes: set[str] = set()
        ordered_children_by_task: dict[
            UUID,
            list[AcceptedTaskDeltaV2],
        ] = {}

        request_understanding = self.request_understanding_record
        if request_understanding is None:
            if self.accepted_task_deltas:
                raise ValueError(
                    "accepted children require a RequestUnderstanding record"
                )
            accepted_task_ids: set[UUID] = set()
        else:
            if (
                request_understanding.run_id != run.run_id
                or request_understanding.message_ref not in message_by_id
            ):
                raise ValueError(
                    "RequestUnderstanding must bind the root Run and a closure Message"
                )
            referenced_message_ids.add(request_understanding.message_ref)
            referenced_message_ids.update(
                request_understanding.contextualization.source_message_refs
            )
            referenced_message_ids.update(
                candidate.source_ref
                for candidate in (
                    request_understanding.contextualization
                    .resolved_reference_candidates
                )
            )
            referenced_message_ids.update(
                candidate_input.source_ref
                for candidate in request_understanding.task_delta_candidates
                for candidate_input in candidate.input_candidates
            )

            if set(request_understanding.accepted_delta_refs) != set(
                accepted_by_id
            ):
                raise ValueError(
                    "RequestUnderstanding must name the exact accepted child set"
                )
            candidate_by_id = {
                candidate.candidate_id: candidate
                for candidate in request_understanding.task_delta_candidates
            }
            decision_by_candidate = {
                decision.candidate_ref: decision
                for decision in request_understanding.candidate_validation
            }
            child_by_candidate: dict[UUID, AcceptedTaskDeltaV2] = {}
            for child in self.accepted_task_deltas:
                if child.candidate_ref in child_by_candidate:
                    raise ValueError(
                        "an accepted candidate must have exactly one child"
                    )
                candidate = candidate_by_id.get(child.candidate_ref)
                decision = decision_by_candidate.get(child.candidate_ref)
                if (
                    candidate is None
                    or decision is None
                    or decision.decision
                    is not CandidateValidationDecision.ACCEPT
                ):
                    raise ValueError(
                        "accepted child must bind one accepted candidate"
                    )
                if (
                    child.message_ref != request_understanding.message_ref
                    or child.operation is not candidate.operation
                    or child.goal_text != candidate.goal_patch
                    or child.accepted_at != request_understanding.created_at
                ):
                    raise ValueError(
                        "accepted child must preserve its parent candidate projection"
                    )
                _exact_evidence_require_unique_refs(
                    child.input_binding_refs,
                    field_name="AcceptedTaskDelta.input_binding_refs",
                )
                child_bindings = tuple(
                    binding_by_id.get(binding_ref)
                    for binding_ref in child.input_binding_refs
                )
                if any(binding is None for binding in child_bindings):
                    raise ValueError(
                        "accepted child InputBinding refs must resolve in closure"
                    )
                expected_inputs = {
                    candidate_input.name: candidate_input
                    for candidate_input in candidate.input_candidates
                }
                actual_bindings = {
                    binding.name: binding
                    for binding in child_bindings
                    if binding is not None
                }
                if set(actual_bindings) != set(expected_inputs):
                    raise ValueError(
                        "accepted child bindings must match candidate inputs"
                    )
                if any(
                    binding.normalized_value
                    != expected_inputs[name].candidate_value
                    or binding.authority is not expected_inputs[name].authority
                    or expected_inputs[name].source_ref not in binding.source_refs
                    for name, binding in actual_bindings.items()
                ):
                    raise ValueError(
                        "accepted child bindings must preserve validated input values"
                    )
                if child.task_id not in task_by_id:
                    raise ValueError("accepted child Task must resolve in closure")
                referenced_message_ids.add(child.message_ref)
                referenced_binding_ids.update(child.input_binding_refs)
                child_by_candidate[child.candidate_ref] = child

            accepted_candidate_ids = {
                candidate_id
                for candidate_id, decision in decision_by_candidate.items()
                if decision.decision is CandidateValidationDecision.ACCEPT
            }
            if set(child_by_candidate) != accepted_candidate_ids:
                raise ValueError(
                    "accepted decisions must have the exact accepted child set"
                )

            prior_result_by_task: dict[UUID, int] = {}
            for candidate in request_understanding.task_delta_candidates:
                child = child_by_candidate.get(candidate.candidate_id)
                if child is None:
                    continue
                prior_result = prior_result_by_task.get(child.task_id)
                if prior_result is None:
                    if child.base_task_state_version is None:
                        expected_result = 1
                    else:
                        expected_result = child.base_task_state_version + 1
                else:
                    if child.base_task_state_version != prior_result:
                        raise ValueError(
                            "accepted Task delta chain must be contiguous"
                        )
                    expected_result = prior_result + 1
                if child.result_task_state_version != expected_result:
                    raise ValueError(
                        "accepted Task delta result version must advance once"
                    )
                if (
                    child.result_task_state_version
                    > task_by_id[child.task_id].state_version
                ):
                    raise ValueError(
                        "accepted Task delta must fit the current Task history"
                    )
                prior_result_by_task[child.task_id] = (
                    child.result_task_state_version
                )
                ordered_children_by_task.setdefault(child.task_id, []).append(
                    child
                )
            accepted_task_ids = {
                child.task_id for child in self.accepted_task_deltas
            }

        if accepted_task_ids != set(task_by_id):
            raise ValueError(
                "accepted child Task refs must match the exact closure Task set"
            )

        for task in self.task_records:
            if task.owner_customer_id != conversation.owner_customer_id:
                raise ValueError("Task owner must match the root Conversation owner")

        run_link_by_task: dict[UUID, RunTaskLinkRecord] = {}
        for link in self.run_task_links:
            if link.run_id != run.run_id or link.task_id not in task_by_id:
                raise ValueError("RunTaskLink must bind the root Run and closure Task")
            task = task_by_id[link.task_id]
            if (
                link.base_task_state_version is not None
                and link.base_task_state_version > task.state_version
            ):
                raise ValueError("RunTaskLink base version exceeds its Task")
            if (
                link.result_task_state_version is not None
                and link.result_task_state_version != task.state_version
            ):
                raise ValueError(
                    "RunTaskLink result version must match its Task projection"
                )
            if run.status in {AgentRunStatus.CREATED, AgentRunStatus.RUNNING}:
                if link.result_task_state_version is not None:
                    raise ValueError(
                        "active RunTaskLink cannot carry a result Task version"
                    )
            elif link.result_task_state_version is None:
                raise ValueError(
                    "terminal RunTaskLink requires the exact Task result version"
                )
            task_children = ordered_children_by_task[link.task_id]
            if (
                task_children[0].base_task_state_version
                != link.base_task_state_version
            ):
                raise ValueError(
                    "accepted Task delta first base must match RunTaskLink base"
                )
            run_link_by_task[link.task_id] = link
        if set(run_link_by_task) != set(task_by_id):
            raise ValueError("RunTaskLink set must match the exact Task set")

        conversation_link_tasks: set[UUID] = set()
        for link in self.conversation_task_links:
            if (
                link.conversation_id != conversation.conversation_id
                or link.task_id not in task_by_id
            ):
                raise ValueError(
                    "ConversationTaskLink must bind the root Conversation and Task"
                )
            conversation_link_tasks.add(link.task_id)
        if conversation_link_tasks != set(task_by_id):
            raise ValueError(
                "ConversationTaskLink set must match the exact Task set"
            )

        unit_by_task: dict[UUID, RequestUnitRecord] = {}
        for unit in self.request_unit_records:
            if unit.task_id not in task_by_id or unit.task_id in unit_by_task:
                raise ValueError("closure requires one exact RequestUnit per Task")
            task = task_by_id[unit.task_id]
            if (
                unit.status is not task.status
                or unit.state_version != task.state_version
            ):
                raise ValueError(
                    "RequestUnit status/version must match its Task projection"
                )
            for field_name, references in (
                ("goal_source_refs", unit.goal_source_refs),
                ("input_binding_refs", unit.input_binding_refs),
                ("observation_refs", unit.observation_refs),
            ):
                _exact_evidence_require_unique_refs(
                    references,
                    field_name=f"RequestUnit.{field_name}",
                )
            if unit.evidence_binding_refs or unit.pending_action_ref is not None:
                raise ValueError(
                    "P0 exact Run closure cannot contain Evidence or Action refs"
                )
            referenced_message_ids.update(unit.goal_source_refs)
            referenced_binding_ids.update(unit.input_binding_refs)
            referenced_observation_ids.update(unit.observation_refs)
            unit_by_task[unit.task_id] = unit
        if set(unit_by_task) != set(task_by_id):
            raise ValueError("RequestUnit set must match the exact Task set")
        for task_id, task_children in ordered_children_by_task.items():
            unit = unit_by_task[task_id]
            latest_child = task_children[-1]
            if (
                latest_child.goal_text != unit.goal_text
                or set(latest_child.input_binding_refs)
                != set(unit.input_binding_refs)
                or latest_child.message_ref not in unit.goal_source_refs
            ):
                raise ValueError(
                    "latest accepted child and RequestUnit causality must match exactly"
                )

        transitions_by_task: dict[UUID, list[TaskStateTransition]] = {
            task_id: [] for task_id in task_by_id
        }
        for transition in self.task_state_transitions:
            task = task_by_id.get(transition.task_id)
            unit = unit_by_id.get(transition.request_unit_id)
            if (
                task is None
                or unit is None
                or unit.task_id != transition.task_id
            ):
                raise ValueError(
                    "Task transition must bind its closure Task and RequestUnit"
                )
            transitions_by_task[transition.task_id].append(transition)
        for task_id, task in task_by_id.items():
            transitions = transitions_by_task[task_id]
            if task.state_version != len(transitions) + 1:
                raise ValueError(
                    "Task transition history must be complete and contiguous"
                )
            if any(
                transition.result_state_version != expected_result_version
                for expected_result_version, transition in enumerate(
                    transitions,
                    start=2,
                )
            ):
                raise ValueError(
                    "Task transition history must be complete and contiguous"
                )
            if not transitions:
                if task.status is not TaskStatus.ACTIVE:
                    raise ValueError(
                        "Task without transitions must retain initial ACTIVE status"
                    )
                continue
            if transitions[0].from_status is not TaskStatus.ACTIVE:
                raise ValueError("Task history must start from ACTIVE")
            if transitions[0].changed_at < task.created_at:
                raise ValueError("Task transition cannot precede Task creation")
            if any(
                current.to_status is not following.from_status
                or current.changed_at > following.changed_at
                for current, following in zip(transitions, transitions[1:])
            ):
                raise ValueError(
                    "Task transition status and timestamp chain must be contiguous"
                )
            if (
                transitions[-1].to_status is not task.status
                or transitions[-1].changed_at != task.updated_at
            ):
                raise ValueError(
                    "Task terminal transition must match its current projection"
                )
            effective_time_by_version = {
                1: task.created_at,
                **{
                    transition.result_state_version: transition.changed_at
                    for transition in transitions
                },
            }
            for child in ordered_children_by_task[task_id]:
                base_version = child.base_task_state_version
                if base_version is None:
                    if task.created_at != child.accepted_at:
                        raise ValueError(
                            "new accepted Task delta must match Task creation time"
                        )
                    continue
                base_effective_at = effective_time_by_version.get(base_version)
                result_effective_at = effective_time_by_version.get(
                    child.result_task_state_version
                )
                if (
                    base_effective_at is None
                    or result_effective_at is None
                    or base_effective_at > child.accepted_at
                    or result_effective_at < child.accepted_at
                ):
                    raise ValueError(
                        "accepted Task delta must fit the current Task history"
                    )

        for binding in self.input_binding_records:
            _exact_evidence_require_unique_refs(
                binding.source_refs,
                field_name="InputBinding.source_refs",
            )
            referenced_message_ids.update(binding.source_refs)

        for manifest in self.context_manifests:
            if manifest.run_id != run.run_id:
                raise ValueError("ContextManifest must belong to the root Run")
            _exact_evidence_require_unique_refs(
                manifest.selected_message_refs,
                field_name="ContextManifest.selected_message_refs",
            )
            referenced_message_ids.update(manifest.selected_message_refs)
            if manifest.task_state_ref_and_version is not None:
                task_state_ref = manifest.task_state_ref_and_version
                task = task_by_id.get(task_state_ref.task_id)
                if task is None:
                    raise ValueError(
                        "ContextManifest Task ref must resolve in closure"
                    )
                if task_state_ref.state_version == 1:
                    effective_at = task.created_at
                else:
                    matching_transition = next(
                        (
                            transition
                            for transition in transitions_by_task[task.task_id]
                            if transition.result_state_version
                            == task_state_ref.state_version
                        ),
                        None,
                    )
                    effective_at = (
                        matching_transition.changed_at
                        if matching_transition is not None
                        else None
                    )
                following_transition = next(
                    (
                        transition
                        for transition in transitions_by_task[task.task_id]
                        if transition.result_state_version
                        == task_state_ref.state_version + 1
                    ),
                    None,
                )
                if (
                    effective_at is None
                    or manifest.assembled_at < effective_at
                    or (
                        following_transition is not None
                        and following_transition.changed_at
                        <= manifest.assembled_at
                    )
                ):
                    raise ValueError(
                        "ContextManifest Task version must match history at assembly"
                    )
            observation_refs = tuple(
                item.record_ref
                for item in manifest.observation_refs_and_versions
            )
            _exact_evidence_require_unique_refs(
                observation_refs,
                field_name="ContextManifest.observation_refs_and_versions",
            )
            for versioned_ref in manifest.observation_refs_and_versions:
                observation = observation_by_id.get(versioned_ref.record_ref)
                if (
                    observation is None
                    or observation.source_version != versioned_ref.version
                ):
                    raise ValueError(
                        "ContextManifest Observation version must match exactly"
                    )
            referenced_observation_ids.update(observation_refs)
            if manifest.evidence_refs_and_versions or manifest.action_record_refs:
                raise ValueError(
                    "P0 exact Run closure cannot contain Evidence or Action refs"
                )
            referenced_artifact_hashes.add(
                manifest.model_visible_toolset_hash
            )

        for gate in self.gate_decisions:
            manifest = manifest_by_id.get(gate.context_manifest_id)
            if manifest is None:
                raise ValueError("GateDecision manifest must resolve in closure")
            _exact_evidence_require_unique_refs(
                gate.argument_binding_refs,
                field_name="GateDecision.argument_binding_refs",
            )
            if gate.model_call_id != manifest.model_call_id:
                raise ValueError(
                    "GateDecision model call must match its ContextManifest"
                )
            referenced_binding_ids.update(gate.argument_binding_refs)

        attempts_by_call: dict[UUID, list[ToolAttemptRecord]] = {
            call_id: [] for call_id in call_by_id
        }
        used_gate_ids: set[UUID] = set()
        for call in self.tool_calls:
            task = task_by_id.get(call.task_id)
            unit = unit_by_id.get(call.request_unit_id)
            manifest = manifest_by_id.get(call.context_manifest_id)
            gate = gate_by_id.get(call.gate_decision_id)
            if (
                call.run_id != run.run_id
                or task is None
                or unit is None
                or unit.task_id != call.task_id
                or manifest is None
                or gate is None
            ):
                raise ValueError(
                    "ToolCall owner graph must close to the exact Run"
                )
            if call.gate_decision_id in used_gate_ids:
                raise ValueError("a GateDecision cannot dispatch multiple ToolCalls")
            used_gate_ids.add(call.gate_decision_id)
            _exact_evidence_require_unique_refs(
                call.argument_binding_refs,
                field_name="ToolCall.argument_binding_refs",
            )
            if not set(call.argument_binding_refs).issubset(
                unit.input_binding_refs
            ):
                raise ValueError(
                    "ToolCall argument bindings must belong to its RequestUnit"
                )
            if (
                gate.decision is not GateDecisionValue.ACCEPT
                or gate.resolved_canonical_tool_name != call.canonical_tool_name
                or gate.model_call_id != call.model_call_id
                or manifest.model_call_id != call.model_call_id
                or gate.context_manifest_id != call.context_manifest_id
                or set(gate.argument_binding_refs)
                != set(call.argument_binding_refs)
                or gate.validated_task_state_version
                != call.validated_task_state_version
                or manifest.tool_registry_version != call.tool_registry_version
                or call.validated_task_state_version > task.state_version
            ):
                raise ValueError(
                    "ToolCall must preserve its accepted Gate and Manifest projection"
                )
            referenced_binding_ids.update(call.argument_binding_refs)

        for attempt in self.tool_attempts:
            if attempt.tool_call_id not in attempts_by_call:
                raise ValueError("ToolAttempt parent ToolCall must resolve in closure")
            attempts_by_call[attempt.tool_call_id].append(attempt)
        terminal_outcomes: dict[
            ToolCallStatus,
            frozenset[ToolResultOutcome],
        ] = {
            ToolCallStatus.SUCCEEDED: frozenset({ToolResultOutcome.SUCCESS}),
            ToolCallStatus.FAILED: frozenset(
                {
                    ToolResultOutcome.BUSINESS_FAILURE,
                    ToolResultOutcome.SYSTEM_FAILURE,
                }
            ),
            ToolCallStatus.TIMED_OUT: frozenset({ToolResultOutcome.TIMEOUT}),
        }
        for call_id, call in call_by_id.items():
            attempts = attempts_by_call[call_id]
            if call.attempt_count != len(attempts):
                raise ValueError(
                    "ToolCall requires the exact contiguous attempt history"
                )
            if any(
                attempt.attempt_no != expected_attempt_no
                for expected_attempt_no, attempt in enumerate(
                    attempts,
                    start=1,
                )
            ):
                raise ValueError(
                    "ToolCall requires the exact contiguous attempt history"
                )
            if any(
                attempt.started_at < call.started_at
                for attempt in attempts
            ) or any(
                current.finished_at is None
                or current.finished_at > following.started_at
                for current, following in zip(attempts, attempts[1:])
            ):
                raise ValueError("ToolAttempt timestamps must be ordered")
            if call.status is ToolCallStatus.CREATED:
                continue
            if call.status is ToolCallStatus.RUNNING:
                if (
                    not attempts
                    or attempts[-1].finished_at is not None
                    or attempts[-1].outcome is not None
                    or any(
                        attempt.finished_at is None or attempt.outcome is None
                        for attempt in attempts[:-1]
                    )
                ):
                    raise ValueError(
                        "RUNNING ToolCall requires one active final attempt"
                    )
                continue
            if call.status is ToolCallStatus.INTERRUPTED:
                if any(
                    attempt.finished_at is None or attempt.outcome is None
                    for attempt in attempts[:-1]
                ):
                    raise ValueError(
                        "INTERRUPTED ToolCall has inconsistent prior attempts"
                    )
                if attempts and attempts[-1].finished_at is not None:
                    if (
                        attempts[-1].outcome
                        is not ToolResultOutcome.INTERRUPTED
                        or call.finished_at != attempts[-1].finished_at
                    ):
                        raise ValueError(
                            "INTERRUPTED ToolCall final attempt must agree"
                        )
                continue
            if (
                not attempts
                or any(
                    attempt.finished_at is None or attempt.outcome is None
                    for attempt in attempts
                )
                or attempts[-1].outcome
                not in terminal_outcomes.get(call.status, frozenset())
                or call.finished_at != attempts[-1].finished_at
                or call.failure_code != attempts[-1].failure_code
            ):
                raise ValueError(
                    "terminal ToolCall and final attempt must agree"
                )

        for observation in self.observation_records:
            if (
                observation.supersedes is not None
                and observation.supersedes not in observation_by_id
            ):
                raise ValueError(
                    "Observation supersedes must resolve in closure"
                )

        observation_source_edge_counts: dict[UUID, int] = {}
        run_stopped_events: list[TraceEvent] = []
        tool_lifecycle_events_by_call: dict[
            UUID,
            list[tuple[ToolCallStatus, TraceEvent]],
        ] = {call_id: [] for call_id in call_by_id}
        for event in self.trace_events:
            if event.run_id != run.run_id or event.case_id is not None:
                raise ValueError(
                    "TraceEvent must bind the root Run without Eval case identity"
                )
            if event.event_type is TraceEventType.RUN_STOPPED:
                run_stopped_events.append(event)
            if event.message_ref is not None:
                referenced_message_ids.add(event.message_ref)
            if event.accepted_delta_ref is not None:
                accepted_child = accepted_by_id.get(event.accepted_delta_ref)
                if accepted_child is None:
                    raise ValueError(
                        "Trace accepted child ref must resolve in closure"
                    )
                accepted_unit = (
                    unit_by_id.get(event.request_unit_id)
                    if event.request_unit_id is not None
                    else None
                )
                if (
                    (
                        event.message_ref is not None
                        and event.message_ref != accepted_child.message_ref
                    )
                    or (
                        event.task_id is not None
                        and event.task_id != accepted_child.task_id
                    )
                    or (
                        event.request_unit_id is not None
                        and (
                            accepted_unit is None
                            or accepted_unit.task_id != accepted_child.task_id
                        )
                    )
                ):
                    raise ValueError(
                        "Trace accepted child correlations must match"
                    )
            if event.task_id is not None and event.task_id not in task_by_id:
                raise ValueError("Trace Task ref must resolve in closure")
            if (
                event.request_unit_id is not None
                and event.request_unit_id not in unit_by_id
            ):
                raise ValueError("Trace RequestUnit ref must resolve in closure")
            if (
                event.task_id is not None
                and event.request_unit_id is not None
                and unit_by_id[event.request_unit_id].task_id != event.task_id
            ):
                raise ValueError("Trace Task and RequestUnit refs must agree")
            if event.input_binding_ref is not None:
                referenced_binding_ids.add(event.input_binding_ref)
            _exact_evidence_require_unique_refs(
                event.argument_binding_refs,
                field_name="TraceEvent.argument_binding_refs",
            )
            referenced_binding_ids.update(event.argument_binding_refs)
            event_manifest: ContextManifest | None = None
            if event.context_manifest_id is not None:
                event_manifest = manifest_by_id.get(event.context_manifest_id)
                if event_manifest is None:
                    raise ValueError(
                        "Trace ContextManifest ref must resolve in closure"
                    )
                if (
                    (
                        event.model_call_id is not None
                        and event.model_call_id != event_manifest.model_call_id
                    )
                    or (
                        event.model_visible_toolset_hash is not None
                        and event.model_visible_toolset_hash
                        != event_manifest.model_visible_toolset_hash
                    )
                    or (
                        event.tool_registry_version is not None
                        and event.tool_registry_version
                        != event_manifest.tool_registry_version
                    )
                ):
                    raise ValueError(
                        "Trace Manifest correlations must match"
                    )
            if event.model_visible_toolset_hash is not None:
                referenced_artifact_hashes.add(
                    event.model_visible_toolset_hash
                )
            if event.tool_call_id is not None:
                call = call_by_id.get(event.tool_call_id)
                if call is None:
                    raise ValueError("Trace ToolCall ref must resolve in closure")
                lifecycle_status = _EXACT_EVIDENCE_TOOL_LIFECYCLE_STATUS.get(
                    event.event_type
                )
                if lifecycle_status is not None:
                    tool_lifecycle_events_by_call[event.tool_call_id].append(
                        (lifecycle_status, event)
                    )
                if event.task_id is not None and event.task_id != call.task_id:
                    raise ValueError("Trace Task must match its ToolCall")
                if (
                    event.request_unit_id is not None
                    and event.request_unit_id != call.request_unit_id
                ):
                    raise ValueError("Trace RequestUnit must match its ToolCall")
                if (
                    event.context_manifest_id is not None
                    and event.context_manifest_id != call.context_manifest_id
                ):
                    raise ValueError("Trace Manifest must match its ToolCall")
                call_manifest = manifest_by_id[call.context_manifest_id]
                if (
                    (
                        event.model_call_id is not None
                        and event.model_call_id != call.model_call_id
                    )
                    or (
                        event.model_visible_toolset_hash is not None
                        and event.model_visible_toolset_hash
                        != call_manifest.model_visible_toolset_hash
                    )
                    or (
                        event.tool_registry_version is not None
                        and event.tool_registry_version
                        != call.tool_registry_version
                    )
                    or (
                        event.argument_binding_refs
                        and set(event.argument_binding_refs)
                        != set(call.argument_binding_refs)
                    )
                ):
                    raise ValueError(
                        "Trace ToolCall correlations must match"
                    )
            if event.observation_ref is not None:
                referenced_observation_ids.add(event.observation_ref)
                observation = observation_by_id.get(event.observation_ref)
                if observation is None:
                    raise ValueError(
                        "Trace Observation ref must resolve in closure"
                    )
                if event.event_type is not TraceEventType.OBSERVATION_RECORDED:
                    continue
                call = (
                    call_by_id.get(event.tool_call_id)
                    if event.tool_call_id is not None
                    else None
                )
                if (
                    call is None
                    or call.status is not ToolCallStatus.SUCCEEDED
                    or call.effect is not ToolEffect.READ
                    or observation.source_tool != call.canonical_tool_name
                    or event.task_id != call.task_id
                    or event.request_unit_id != call.request_unit_id
                    or event.occurred_at != observation.recorded_at
                ):
                    raise ValueError(
                        "Observation source must close to a root Run ToolCall"
                    )
                observation_source_edge_counts[event.observation_ref] = (
                    observation_source_edge_counts.get(
                        event.observation_ref,
                        0,
                    )
                    + 1
                )

        active_run_statuses = {
            AgentRunStatus.CREATED,
            AgentRunStatus.RUNNING,
        }
        if run.status in active_run_statuses:
            if run_stopped_events:
                raise ValueError("active Run cannot have RunStopped Trace")
        elif len(run_stopped_events) != 1:
            raise ValueError(
                "terminal RunStopped Trace must exist exactly once"
            )
        else:
            run_stopped = run_stopped_events[0]
            if (
                run_stopped.stop_reason is not run.stop_reason
                or run_stopped.occurred_at != run.completed_at
            ):
                raise ValueError(
                    "terminal RunStopped Trace must match the Run projection"
                )

        terminal_tool_statuses = {
            ToolCallStatus.SUCCEEDED,
            ToolCallStatus.FAILED,
            ToolCallStatus.TIMED_OUT,
            ToolCallStatus.INTERRUPTED,
        }
        tool_lifecycle_phase = {
            ToolCallStatus.CREATED: 0,
            ToolCallStatus.RUNNING: 1,
            ToolCallStatus.SUCCEEDED: 2,
            ToolCallStatus.FAILED: 2,
            ToolCallStatus.TIMED_OUT: 2,
            ToolCallStatus.INTERRUPTED: 2,
        }
        for call_id, call in call_by_id.items():
            lifecycle_events = tool_lifecycle_events_by_call[call_id]
            if not lifecycle_events:
                raise ValueError(
                    "ToolCall lifecycle must include its current projection"
                )
            ordered_lifecycle = sorted(
                lifecycle_events,
                key=lambda item: (
                    item[1].occurred_at,
                    tool_lifecycle_phase[item[0]],
                    item[1].trace_event_id.hex,
                ),
            )
            ordered_statuses = tuple(
                status for status, _event in ordered_lifecycle
            )
            if (
                len(ordered_statuses) != len(set(ordered_statuses))
                or any(
                    tool_lifecycle_phase[current]
                    >= tool_lifecycle_phase[following]
                    for current, following in zip(
                        ordered_statuses,
                        ordered_statuses[1:],
                    )
                )
                or any(
                    event.occurred_at < call.started_at
                    for _status, event in ordered_lifecycle
                )
            ):
                raise ValueError(
                    "ToolCall lifecycle timestamps and status order must agree"
                )
            terminal_lifecycle = tuple(
                (status, event)
                for status, event in ordered_lifecycle
                if status in terminal_tool_statuses
            )
            latest_status, latest_event = ordered_lifecycle[-1]
            if call.status in terminal_tool_statuses:
                if (
                    len(terminal_lifecycle) != 1
                    or latest_status is not call.status
                    or latest_event.occurred_at != call.finished_at
                    or any(
                        event.occurred_at > call.finished_at
                        for _status, event in ordered_lifecycle
                    )
                ):
                    raise ValueError(
                        "ToolCall lifecycle must match its terminal projection"
                    )
            elif (
                terminal_lifecycle
                or latest_status is not call.status
            ):
                raise ValueError(
                    "ToolCall lifecycle must match its active projection"
                )

        if set(observation_source_edge_counts) != set(observation_by_id) or any(
            count != 1 for count in observation_source_edge_counts.values()
        ):
            raise ValueError(
                "each Observation source edge must exist exactly once for root Run"
            )

        referenced_binding_ids = _exact_evidence_expand_supersedes(
            referenced_binding_ids,
            binding_by_id,
            family_name="InputBinding",
        )
        referenced_observation_ids = _exact_evidence_expand_supersedes(
            referenced_observation_ids,
            observation_by_id,
            family_name="Observation",
        )
        if referenced_message_ids != set(message_by_id):
            raise ValueError("Message family must be the exact referenced set")
        if referenced_binding_ids != set(binding_by_id):
            raise ValueError("InputBinding family must be the exact referenced set")
        if referenced_observation_ids != set(observation_by_id):
            raise ValueError("Observation family must be the exact referenced set")
        if referenced_artifact_hashes != set(artifact_by_hash):
            raise ValueError(
                "ModelVisibleToolsetArtifact family must be the exact referenced set"
            )
        return self
