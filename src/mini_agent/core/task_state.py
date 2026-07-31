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


class CandidateValidationDecision(StrEnum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"


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
            raise ValueError(
                "Task transition must increment state_version exactly once"
            )
        if self.from_status is self.to_status:
            raise ValueError("Task transition must change status")
        return self


from pydantic import StrictInt, StrictStr

from .request_understanding import (
    Confidence,
    InputSourceKind,
    ReferenceSourceKindV2,
    UncertaintyV2,
)


StrictNonNegativeSpanV2 = Annotated[StrictInt, Field(ge=0)]
StrictPositiveStateVersionV2 = Annotated[StrictInt, Field(ge=1)]
SourceQuoteSha256V2 = Annotated[
    StrictStr,
    Field(pattern=r"^[0-9a-f]{64}$"),
]


class DurableResolvedReferenceCandidateV2(AuditOnlyModel):
    name: Literal["order_id"]
    candidate_value: NonEmptyString
    source_kind: ReferenceSourceKindV2
    source_ref: UUID
    source_span_start: StrictNonNegativeSpanV2
    source_span_end_exclusive: StrictNonNegativeSpanV2
    source_quote_sha256: SourceQuoteSha256V2
    confidence: Confidence

    @model_validator(mode="after")
    def source_span_is_non_empty(self) -> Self:
        if self.source_span_end_exclusive <= self.source_span_start:
            raise ValueError("source span end must be greater than start")
        return self


class DurableInputCandidateV2(AuditOnlyModel):
    name: Literal["order_id"]
    candidate_value: NonEmptyString
    semantic_role: Literal["TARGET_RESOURCE_IDENTIFIER"]
    authority: Literal[InputAuthority.USER_CLAIM]
    source_kind: Literal[InputSourceKind.CURRENT_MESSAGE]
    source_ref: UUID
    source_span_start: StrictNonNegativeSpanV2
    source_span_end_exclusive: StrictNonNegativeSpanV2
    source_quote_sha256: SourceQuoteSha256V2
    confidence: Confidence

    @model_validator(mode="after")
    def source_span_is_non_empty(self) -> Self:
        if self.source_span_end_exclusive <= self.source_span_start:
            raise ValueError("source span end must be greater than start")
        return self


class DurableQueryContextualizationCandidateV2(AuditOnlyModel):
    text: NonEmptyString
    resolved_reference_candidates: tuple[
        DurableResolvedReferenceCandidateV2,
        ...,
    ]
    uncertainties: tuple[UncertaintyV2, ...]
    source_message_refs: Annotated[
        tuple[UUID, ...],
        Field(min_length=1, max_length=8),
    ]

    @field_validator("source_message_refs")
    @classmethod
    def contextualization_source_refs_are_unique(
        cls,
        value: tuple[UUID, ...],
    ) -> tuple[UUID, ...]:
        if len(value) != len(set(value)):
            raise ValueError("source_message_refs must be unique")
        return value

    @model_validator(mode="after")
    def child_references_are_in_context_scope(self) -> Self:
        source_refs = set(self.source_message_refs)
        if any(
            candidate.source_ref not in source_refs
            for candidate in self.resolved_reference_candidates
        ):
            raise ValueError(
                "resolved reference source_ref must be in source_message_refs"
            )
        if any(
            reference not in source_refs
            for uncertainty in self.uncertainties
            for reference in uncertainty.source_message_refs
        ):
            raise ValueError(
                "uncertainty source refs must be in source_message_refs"
            )
        return self


class DurableTaskDeltaCandidateV2(AuditOnlyModel):
    candidate_id: UUID
    operation: Literal[TaskDeltaOperation.ADD_GOAL]
    goal_patch: NonEmptyString
    input_candidates: Annotated[
        tuple[DurableInputCandidateV2, ...],
        Field(min_length=1),
    ]
    confidence: Confidence

    @field_validator("input_candidates")
    @classmethod
    def candidate_names_are_unique(
        cls,
        value: tuple[DurableInputCandidateV2, ...],
    ) -> tuple[DurableInputCandidateV2, ...]:
        names = [candidate.name for candidate in value]
        if len(names) != len(set(names)):
            raise ValueError("input candidate names must be unique")
        return value


class CandidateRejectionReasonCode(StrEnum):
    OPERATION_NOT_SUPPORTED = "OPERATION_NOT_SUPPORTED"
    GOAL_PATCH_NOT_ACTIONABLE = "GOAL_PATCH_NOT_ACTIONABLE"
    REQUIRED_INPUT_MISSING = "REQUIRED_INPUT_MISSING"
    INPUT_VALUE_INVALID = "INPUT_VALUE_INVALID"
    REFERENCE_UNRESOLVED = "REFERENCE_UNRESOLVED"
    REFERENCE_AMBIGUOUS = "REFERENCE_AMBIGUOUS"
    NEXT_MOVE_INCONSISTENT = "NEXT_MOVE_INCONSISTENT"


class RequestUnderstandingAggregateFailureCodeV2(StrEnum):
    MODEL_INPUT_SCHEMA_INVALID = "MODEL_INPUT_SCHEMA_INVALID"
    MODEL_OUTPUT_SCHEMA_INVALID = "MODEL_OUTPUT_SCHEMA_INVALID"
    MODEL_SCHEMA_VERSION_INVALID = "MODEL_SCHEMA_VERSION_INVALID"
    TRUSTED_OR_PRIVATE_FIELD_PRESENT = "TRUSTED_OR_PRIVATE_FIELD_PRESENT"
    SOURCE_PROVENANCE_INVALID = "SOURCE_PROVENANCE_INVALID"


class RequestUnderstandingAtomicFailureCodeV2(StrEnum):
    TASK_STATE_CAS_CONFLICT = "TASK_STATE_CAS_CONFLICT"
    TASK_COMMIT_FAILED = "TASK_COMMIT_FAILED"
    DURABLE_CLOSURE_COMMIT_FAILED = "DURABLE_CLOSURE_COMMIT_FAILED"


class CandidateValidationRecordV2(AuditOnlyModel):
    candidate_ref: UUID
    decision: CandidateValidationDecision
    reason_code: CandidateRejectionReasonCode | None = None

    @model_validator(mode="after")
    def rejection_reason_matches_decision(self) -> Self:
        if (
            self.decision is CandidateValidationDecision.REJECT
            and self.reason_code is None
        ):
            raise ValueError("rejected candidate requires a reason")
        if (
            self.decision is CandidateValidationDecision.ACCEPT
            and self.reason_code is not None
        ):
            raise ValueError("accepted candidate cannot have a rejection reason")
        return self


class AcceptedTaskDeltaV2(AuditOnlyModel):
    accepted_delta_id: UUID
    candidate_ref: UUID
    message_ref: UUID
    operation: Literal[TaskDeltaOperation.ADD_GOAL]
    goal_text: NonEmptyString
    input_binding_refs: Annotated[tuple[UUID, ...], Field(min_length=1)]
    accepted_at: datetime
    task_id: UUID
    base_task_state_version: StrictPositiveStateVersionV2 | None
    result_task_state_version: StrictPositiveStateVersionV2

    @field_validator("accepted_at")
    @classmethod
    def accepted_at_is_utc(cls, value: datetime) -> datetime:
        return require_utc(value, field_name="accepted_at")


class RequestUnderstandingRecordV2(AuditOnlyModel):
    request_understanding_record_id: UUID
    run_id: UUID
    message_ref: UUID
    schema_version: Literal["request_understanding_record.p0.v2"]
    model_input_schema_version: Literal["e2e01-thin-v1"]
    model_output_schema_version: Literal["e2e01-thin-v2"]
    contextualization: DurableQueryContextualizationCandidateV2
    task_delta_candidates: tuple[DurableTaskDeltaCandidateV2, ...]
    candidate_validation: tuple[CandidateValidationRecordV2, ...]
    accepted_delta_refs: tuple[UUID, ...]
    proposed_base_task_state_version: StrictPositiveStateVersionV2 | None = None
    validated_task_state_version: StrictPositiveStateVersionV2 | None = None
    next_move_candidate_ref: UUID | None = None
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def created_at_is_utc(cls, value: datetime) -> datetime:
        return require_utc(value, field_name="created_at")

    @model_validator(mode="after")
    def record_graph_is_locally_closed(self) -> Self:
        candidate_ids = [
            candidate.candidate_id for candidate in self.task_delta_candidates
        ]
        validation_refs = [
            validation.candidate_ref
            for validation in self.candidate_validation
        ]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("candidate IDs must be unique")
        if len(validation_refs) != len(set(validation_refs)):
            raise ValueError("candidate validation refs must be unique")
        if set(validation_refs) != set(candidate_ids):
            raise ValueError(
                "candidate validation refs must exactly match candidates"
            )
        if len(self.accepted_delta_refs) != len(
            set(self.accepted_delta_refs)
        ):
            raise ValueError("accepted delta refs must be unique")
        accepted_count = sum(
            validation.decision is CandidateValidationDecision.ACCEPT
            for validation in self.candidate_validation
        )
        if len(self.accepted_delta_refs) != accepted_count:
            raise ValueError(
                "accepted delta refs must match accepted decisions"
            )
        if self.message_ref not in self.contextualization.source_message_refs:
            raise ValueError(
                "contextualization must include the current message"
            )
        if any(
            input_candidate.source_ref != self.message_ref
            for candidate in self.task_delta_candidates
            for input_candidate in candidate.input_candidates
        ):
            raise ValueError(
                "durable input candidates must bind to current message"
            )
        if self.next_move_candidate_ref is None and (
            self.proposed_base_task_state_version is not None
            or self.validated_task_state_version is not None
        ):
            raise ValueError(
                "next_move versions require next_move_candidate_ref"
            )
        return self
