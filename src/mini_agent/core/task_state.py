"""Core-owned accepted binding, Task, and RequestUnit record semantics."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from .common import AuditOnlyModel, RuntimePrivateModel, require_utc
from .request_understanding import InputAuthority, TaskDeltaOperation

NonEmptyString = Annotated[str, Field(min_length=1)]
PositiveStateVersion = Annotated[int, Field(ge=1)]
OrderId = Annotated[str, Field(pattern=r"^O-[0-9]{4,20}$")]


class InputValidationStatus(StrEnum):
    ACCEPTED = "ACCEPTED"


class InputBinding(AuditOnlyModel):
    """Validated user input; it still does not prove a business fact."""

    binding_id: UUID
    name: Literal["order_id"]
    normalized_value: OrderId
    authority: Literal[InputAuthority.USER_CLAIM]
    source_refs: Annotated[tuple[UUID, ...], Field(min_length=1)]
    validation_status: Literal[InputValidationStatus.ACCEPTED]
    confirmed_by_user: Literal[True]
    created_at: datetime
    updated_at: datetime
    supersedes: UUID | None = None

    @field_validator("created_at", "updated_at")
    @classmethod
    def binding_timestamps_are_utc(cls, value: datetime) -> datetime:
        return require_utc(value, field_name="InputBinding timestamp")

    @model_validator(mode="after")
    def update_does_not_precede_creation(self) -> Self:
        if self.updated_at < self.created_at:
            raise ValueError("InputBinding updated_at cannot precede created_at")
        return self


class AcceptedTaskDelta(AuditOnlyModel):
    accepted_delta_id: UUID
    candidate_ref: UUID
    message_ref: UUID
    operation: Literal[TaskDeltaOperation.ADD_GOAL]
    goal_text: NonEmptyString
    input_binding_refs: Annotated[tuple[UUID, ...], Field(min_length=1)]
    accepted_at: datetime

    @field_validator("accepted_at")
    @classmethod
    def accepted_at_is_utc(cls, value: datetime) -> datetime:
        return require_utc(value, field_name="accepted_at")


class CandidateValidationDecision(StrEnum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"


class CandidateValidationRecord(AuditOnlyModel):
    candidate_ref: UUID
    decision: CandidateValidationDecision
    reason_code: NonEmptyString | None = None

    @model_validator(mode="after")
    def rejected_candidate_has_reason(self) -> Self:
        if (
            self.decision is CandidateValidationDecision.REJECT
            and self.reason_code is None
        ):
            raise ValueError("rejected candidate requires a stable reason")
        if (
            self.decision is CandidateValidationDecision.ACCEPT
            and self.reason_code is not None
        ):
            raise ValueError("accepted candidate cannot have a rejection reason")
        return self


class RequestUnderstandingRecord(AuditOnlyModel):
    run_id: UUID
    message_ref: UUID
    schema_version: NonEmptyString
    candidate_validation: tuple[CandidateValidationRecord, ...]
    accepted_delta_refs: tuple[UUID, ...]
    proposed_base_task_state_version: PositiveStateVersion | None = None
    validated_task_state_version: PositiveStateVersion | None = None
    next_move_candidate_ref: UUID | None = None


class TaskStatus(StrEnum):
    ACTIVE = "ACTIVE"
    WAITING_USER = "WAITING_USER"
    PENDING_ACTION = "PENDING_ACTION"
    ACTION_IN_PROGRESS = "ACTION_IN_PROGRESS"
    RECOVERING = "RECOVERING"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"


class RequestUnitRecord(AuditOnlyModel):
    request_unit_id: UUID
    task_id: UUID
    goal_text: NonEmptyString
    goal_source_refs: Annotated[tuple[UUID, ...], Field(min_length=1)]
    contextualization_ref: UUID | None = None
    constraint_refs: tuple[UUID, ...] = ()
    dependency_refs: tuple[UUID, ...] = ()
    input_binding_refs: Annotated[tuple[UUID, ...], Field(min_length=1)]
    open_questions: tuple[NonEmptyString, ...] = ()
    observation_refs: tuple[UUID, ...] = ()
    evidence_binding_refs: tuple[UUID, ...] = ()
    pending_action_ref: UUID | None = None
    result_refs: tuple[UUID, ...] = ()
    status: TaskStatus
    state_version: PositiveStateVersion
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at")
    @classmethod
    def request_unit_timestamps_are_utc(cls, value: datetime) -> datetime:
        return require_utc(value, field_name="RequestUnitRecord timestamp")

    @model_validator(mode="after")
    def request_unit_dates_are_ordered(self) -> Self:
        if self.updated_at < self.created_at:
            raise ValueError("RequestUnit updated_at cannot precede created_at")
        return self


class TaskRecord(RuntimePrivateModel):
    task_id: UUID
    owner_customer_id: NonEmptyString
    status: TaskStatus
    state_version: PositiveStateVersion
    created_at: datetime
    updated_at: datetime
    last_outcome_ref: UUID | None = None

    @field_validator("created_at", "updated_at")
    @classmethod
    def task_timestamps_are_utc(cls, value: datetime) -> datetime:
        return require_utc(value, field_name="TaskRecord timestamp")

    @model_validator(mode="after")
    def task_dates_are_ordered(self) -> Self:
        if self.updated_at < self.created_at:
            raise ValueError("Task updated_at cannot precede created_at")
        return self


class TaskStateTransition(AuditOnlyModel):
    task_id: UUID
    request_unit_id: UUID
    from_status: TaskStatus
    to_status: TaskStatus
    base_state_version: PositiveStateVersion
    result_state_version: PositiveStateVersion
    reason_ref: UUID
    changed_at: datetime

    @field_validator("changed_at")
    @classmethod
    def changed_at_is_utc(cls, value: datetime) -> datetime:
        return require_utc(value, field_name="changed_at")

    @model_validator(mode="after")
    def transition_increments_version_once(self) -> Self:
        if self.result_state_version != self.base_state_version + 1:
            raise ValueError("Task transition must increment state_version exactly once")
        if self.from_status is self.to_status:
            raise ValueError("Task transition must change status")
        return self
