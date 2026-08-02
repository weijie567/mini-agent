"""Core-owned accepted binding, Task, and RequestUnit record semantics."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Annotated, ClassVar, Literal, Self, cast
from uuid import UUID

from pydantic import (
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    TypeAdapter,
    field_validator,
    model_validator,
)

from .common import AuditOnlyModel, RuntimePrivateModel, require_utc
from .order_search import (
    ORDER_SEARCH_MAX_CANDIDATES,
    OrderId as StrictOrderIdV2,
    OrderCandidateSourceVersion,
    OrderSearchSnapshotSourceVersion,
    normalize_product_description,
)
from .request_understanding import (
    CYCLE2_ORDINAL_CLAIM_MAX,
    InputAuthority,
    TaskDeltaOperation,
)

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


InputBindingNameV2 = Literal[
    "order_id",
    "product_description",
    "candidate_ordinal",
    "shipment_not_received",
]
InputBindingNormalizedValueV2 = StrictStr | StrictInt | StrictBool
_STRICT_ORDER_ID_V2_ADAPTER = TypeAdapter(StrictOrderIdV2)


class InputBindingV2(AuditOnlyModel):
    """Inactive Cycle 2 accepted input; it remains only a user Claim."""

    binding_id: UUID
    name: InputBindingNameV2
    normalized_value: InputBindingNormalizedValueV2
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
        return require_utc(value, field_name="InputBindingV2 timestamp")

    @model_validator(mode="after")
    def accepted_name_value_pair_is_closed(self) -> Self:
        value = self.normalized_value
        if self.name == "order_id":
            _STRICT_ORDER_ID_V2_ADAPTER.validate_python(value)
        elif self.name == "product_description":
            if (
                type(value) is not str
                or normalize_product_description(value) != value
            ):
                raise ValueError(
                    "product_description must be the exact normalized value"
                )
        elif self.name == "candidate_ordinal":
            if (
                type(value) is not int
                or not 1 <= value <= CYCLE2_ORDINAL_CLAIM_MAX
            ):
                raise ValueError(
                    "candidate_ordinal must be a strict integer from 1 to 99"
                )
        elif type(value) is not bool:
            raise ValueError("shipment_not_received must be a strict boolean")
        return self

    @model_validator(mode="after")
    def update_does_not_precede_creation(self) -> Self:
        if self.updated_at < self.created_at:
            raise ValueError("InputBindingV2 updated_at cannot precede created_at")
        return self


def convert_input_binding_v1_to_v2(binding: InputBinding) -> InputBindingV2:
    """Copy one exact validated v1 order-id binding into the inactive v2 shape."""

    if type(binding) is not InputBinding:
        raise TypeError("conversion requires an exact InputBinding instance")
    validated = InputBinding.model_validate(binding.model_dump(), strict=True)
    return InputBindingV2(
        binding_id=validated.binding_id,
        name=validated.name,
        normalized_value=validated.normalized_value,
        authority=validated.authority,
        source_refs=validated.source_refs,
        validation_status=validated.validation_status,
        confirmed_by_user=validated.confirmed_by_user,
        created_at=validated.created_at,
        updated_at=validated.updated_at,
        supersedes=validated.supersedes,
    )


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


ORDER_CANDIDATE_SET_TTL = timedelta(minutes=15)
ORDER_CANDIDATE_SET_RECORD_SCHEMA_VERSION = "order_candidate_set_record.p0.v1"
ORDER_SEARCH_OBSERVATION_RECORD_SCHEMA_VERSION = (
    "order_search_observation_record.p0.v1"
)
ORDER_CANDIDATE_SELECTION_RECORD_SCHEMA_VERSION = (
    "order_candidate_selection_record.p0.v1"
)
ORDER_CANDIDATE_AUTO_TARGET_RECORD_SCHEMA_VERSION = (
    "order_candidate_auto_target_record.p0.v1"
)

StrictOpaqueRef = Annotated[
    StrictStr,
    Field(min_length=1, pattern=r"^\S+$"),
]
StrictPositiveStateVersionC2 = Annotated[StrictInt, Field(ge=1)]
OrderCandidateSetVersion = Annotated[
    StrictStr,
    Field(
        pattern=(
            r"^order-candidate-set\.p0\.v1:sha256:[0-9a-f]{64}$"
        )
    ),
]


class OrderCandidateSetOutcome(StrEnum):
    UNIQUE = "UNIQUE"
    MULTIPLE = "MULTIPLE"


class OrderCandidateSetEntry(AuditOnlyModel):
    """One ordinal-to-Observation-ref capability, never an order fact."""

    ordinal: Annotated[
        StrictInt,
        Field(ge=1, le=ORDER_SEARCH_MAX_CANDIDATES),
    ]
    observation_candidate_ref: UUID
    candidate_source_version: OrderCandidateSourceVersion


def _candidate_set_utc_timestamp(value: datetime, *, field_name: str) -> str:
    value = require_utc(value, field_name=field_name)
    return value.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def compute_order_candidate_set_version(
    *,
    candidate_set_id: UUID,
    private_owner_scope_ref: str,
    conversation_id: UUID,
    task_id: UUID,
    request_unit_id: UUID,
    outcome: OrderCandidateSetOutcome,
    base_task_state_version: int,
    result_task_state_version: int,
    selection_expected_task_state_version: int | None,
    query_binding_refs: Sequence[UUID],
    source_tool_call_id: UUID,
    search_observation_ref: UUID,
    search_observation_record_schema_version: str,
    search_observation_source_version: str,
    ordered_candidates: Sequence[OrderCandidateSetEntry],
    created_at: datetime,
    valid_until: datetime,
    supersedes_candidate_set_ref: UUID | None,
) -> OrderCandidateSetVersion:
    """Hash exactly the scoped CandidateSet canonical payload."""

    if type(private_owner_scope_ref) is not str or not private_owner_scope_ref:
        raise ValueError("private_owner_scope_ref must be a non-empty string")
    if not isinstance(outcome, OrderCandidateSetOutcome):
        raise TypeError("outcome must be an OrderCandidateSetOutcome")
    for name, value in (
        ("base_task_state_version", base_task_state_version),
        ("result_task_state_version", result_task_state_version),
    ):
        if type(value) is not int or value < 1:
            raise ValueError(f"{name} must be a strict positive integer")
    if selection_expected_task_state_version is not None and (
        type(selection_expected_task_state_version) is not int
        or selection_expected_task_state_version < 1
    ):
        raise ValueError(
            "selection_expected_task_state_version must be null or a strict "
            "positive integer"
        )
    if search_observation_record_schema_version != (
        ORDER_SEARCH_OBSERVATION_RECORD_SCHEMA_VERSION
    ):
        raise ValueError("unknown SearchOrdersObservation record schema version")

    query_refs = tuple(query_binding_refs)
    candidates = tuple(ordered_candidates)
    if not query_refs or len(query_refs) != len(set(query_refs)):
        raise ValueError("query_binding_refs must be non-empty and unique")
    if not candidates:
        raise ValueError("ordered_candidates must not be empty")

    payload: dict[str, object] = {
        "record_schema_version": ORDER_CANDIDATE_SET_RECORD_SCHEMA_VERSION,
        "candidate_set_id": str(candidate_set_id),
        "private_owner_scope_ref": private_owner_scope_ref,
        "conversation_id": str(conversation_id),
        "task_id": str(task_id),
        "request_unit_id": str(request_unit_id),
        "outcome": outcome.value,
        "base_task_state_version": base_task_state_version,
        "result_task_state_version": result_task_state_version,
        "selection_expected_task_state_version": (
            selection_expected_task_state_version
        ),
        "query_binding_refs": sorted(str(reference) for reference in query_refs),
        "source_tool_call_id": str(source_tool_call_id),
        "search_observation_ref": str(search_observation_ref),
        "search_observation_record_schema_version": (
            search_observation_record_schema_version
        ),
        "search_observation_source_version": search_observation_source_version,
        "ordered_candidates": [
            {
                "ordinal": candidate.ordinal,
                "observation_candidate_ref": str(
                    candidate.observation_candidate_ref
                ),
                "candidate_source_version": candidate.candidate_source_version,
            }
            for candidate in candidates
        ],
        "created_at": _candidate_set_utc_timestamp(
            created_at,
            field_name="created_at",
        ),
        "valid_until": _candidate_set_utc_timestamp(
            valid_until,
            field_name="valid_until",
        ),
        "supersedes_candidate_set_ref": (
            None
            if supersedes_candidate_set_ref is None
            else str(supersedes_candidate_set_ref)
        ),
    }
    canonical_bytes = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return cast(
        OrderCandidateSetVersion,
        (
            "order-candidate-set.p0.v1:sha256:"
            f"{hashlib.sha256(canonical_bytes).hexdigest()}"
        ),
    )


class OrderCandidateSetRecord(AuditOnlyModel):
    """Immutable ordinal-selection capability with no business facts."""

    record_schema_version: ClassVar[
        Literal["order_candidate_set_record.p0.v1"]
    ] = ORDER_CANDIDATE_SET_RECORD_SCHEMA_VERSION

    candidate_set_id: UUID
    private_owner_scope_ref: StrictOpaqueRef
    conversation_id: UUID
    task_id: UUID
    request_unit_id: UUID
    outcome: OrderCandidateSetOutcome
    base_task_state_version: StrictPositiveStateVersionC2
    result_task_state_version: StrictPositiveStateVersionC2
    selection_expected_task_state_version: StrictPositiveStateVersionC2 | None
    query_binding_refs: Annotated[tuple[UUID, ...], Field(min_length=1)]
    source_tool_call_id: UUID
    search_observation_ref: UUID
    search_observation_record_schema_version: Literal[
        "order_search_observation_record.p0.v1"
    ]
    search_observation_source_version: OrderSearchSnapshotSourceVersion
    ordered_candidates: Annotated[
        tuple[OrderCandidateSetEntry, ...],
        Field(min_length=1, max_length=ORDER_SEARCH_MAX_CANDIDATES),
    ]
    candidate_set_version: OrderCandidateSetVersion
    created_at: datetime
    valid_until: datetime
    supersedes_candidate_set_ref: UUID | None = None

    @field_validator("created_at", "valid_until")
    @classmethod
    def candidate_set_timestamps_are_utc(cls, value: datetime) -> datetime:
        return require_utc(value, field_name="OrderCandidateSetRecord timestamp")

    @field_validator("query_binding_refs")
    @classmethod
    def query_binding_refs_are_unique(
        cls,
        value: tuple[UUID, ...],
    ) -> tuple[UUID, ...]:
        if len(value) != len(set(value)):
            raise ValueError("query_binding_refs must be unique")
        return value

    @model_validator(mode="after")
    def candidate_set_is_closed_and_versioned(self) -> Self:
        if self.result_task_state_version <= self.base_task_state_version:
            raise ValueError("result_task_state_version must be greater than base")
        candidate_count = len(self.ordered_candidates)
        ordinals = tuple(candidate.ordinal for candidate in self.ordered_candidates)
        if ordinals != tuple(range(1, candidate_count + 1)):
            raise ValueError("candidate ordinals must be contiguous from one")
        candidate_refs = tuple(
            candidate.observation_candidate_ref
            for candidate in self.ordered_candidates
        )
        if len(candidate_refs) != len(set(candidate_refs)):
            raise ValueError("observation_candidate_ref values must be unique")
        if self.outcome is OrderCandidateSetOutcome.UNIQUE:
            if candidate_count != 1:
                raise ValueError("UNIQUE CandidateSet requires exactly one candidate")
            if self.selection_expected_task_state_version is not None:
                raise ValueError(
                    "UNIQUE CandidateSet cannot expect an ordinal selection"
                )
        else:
            if candidate_count < 2:
                raise ValueError("MULTIPLE CandidateSet requires two to five candidates")
            if (
                self.selection_expected_task_state_version
                != self.result_task_state_version
            ):
                raise ValueError(
                    "MULTIPLE selection expected version must equal result version"
                )
        if self.valid_until != self.created_at + ORDER_CANDIDATE_SET_TTL:
            raise ValueError("CandidateSet valid_until must equal created_at plus 15 minutes")
        if self.supersedes_candidate_set_ref == self.candidate_set_id:
            raise ValueError("CandidateSet cannot supersede itself")
        expected_version = compute_order_candidate_set_version(
            candidate_set_id=self.candidate_set_id,
            private_owner_scope_ref=self.private_owner_scope_ref,
            conversation_id=self.conversation_id,
            task_id=self.task_id,
            request_unit_id=self.request_unit_id,
            outcome=self.outcome,
            base_task_state_version=self.base_task_state_version,
            result_task_state_version=self.result_task_state_version,
            selection_expected_task_state_version=(
                self.selection_expected_task_state_version
            ),
            query_binding_refs=self.query_binding_refs,
            source_tool_call_id=self.source_tool_call_id,
            search_observation_ref=self.search_observation_ref,
            search_observation_record_schema_version=(
                self.search_observation_record_schema_version
            ),
            search_observation_source_version=(
                self.search_observation_source_version
            ),
            ordered_candidates=self.ordered_candidates,
            created_at=self.created_at,
            valid_until=self.valid_until,
            supersedes_candidate_set_ref=self.supersedes_candidate_set_ref,
        )
        if self.candidate_set_version != expected_version:
            raise ValueError("candidate_set_version does not match canonical payload")
        return self


class OrderCandidateAutoTargetRecord(AuditOnlyModel):
    """Append-only UNIQUE-search target capability; never model-visible."""

    record_schema_version: ClassVar[
        Literal["order_candidate_auto_target_record.p0.v1"]
    ] = ORDER_CANDIDATE_AUTO_TARGET_RECORD_SCHEMA_VERSION

    verified_target_ref: UUID
    private_owner_scope_ref: StrictOpaqueRef
    conversation_id: UUID
    task_id: UUID
    request_unit_id: UUID
    query_input_binding_ref: UUID
    candidate_set_ref: UUID
    candidate_set_version: OrderCandidateSetVersion
    source_tool_call_id: UUID
    search_observation_ref: UUID
    search_observation_record_schema_version: Literal[
        "order_search_observation_record.p0.v1"
    ]
    search_observation_source_version: OrderSearchSnapshotSourceVersion
    observation_candidate_ref: UUID
    candidate_source_version: OrderCandidateSourceVersion
    owner_scoped_order_target_ref: StrictOpaqueRef
    order_id: StrictOrderIdV2
    base_task_state_version: StrictPositiveStateVersionC2
    result_task_state_version: StrictPositiveStateVersionC2
    verified_at: datetime
    supersedes_verified_target_ref: UUID | None = None

    @field_validator("verified_at")
    @classmethod
    def verified_at_is_utc(cls, value: datetime) -> datetime:
        return require_utc(
            value,
            field_name="OrderCandidateAutoTargetRecord.verified_at",
        )

    @model_validator(mode="after")
    def auto_target_identity_and_version_are_closed(self) -> Self:
        if self.verified_target_ref.version != 4:
            raise ValueError("verified_target_ref must be a UUIDv4")
        graph_identities = {
            self.conversation_id,
            self.task_id,
            self.request_unit_id,
            self.query_input_binding_ref,
            self.candidate_set_ref,
            self.source_tool_call_id,
            self.search_observation_ref,
            self.observation_candidate_ref,
        }
        if self.verified_target_ref in graph_identities:
            raise ValueError(
                "verified_target_ref must be independent from graph identities"
            )
        if self.supersedes_verified_target_ref == self.verified_target_ref:
            raise ValueError("auto target cannot supersede itself")
        if (
            self.supersedes_verified_target_ref is not None
            and self.supersedes_verified_target_ref.version != 4
        ):
            raise ValueError("superseded auto target ref must be a UUIDv4")
        if self.result_task_state_version != self.base_task_state_version + 1:
            raise ValueError("auto target must advance Task version exactly once")
        return self


class OrderCandidateSelectionRequest(RuntimePrivateModel):
    """Accepted ordinal Candidate Input; it carries no CandidateSet authority."""

    source_message_ref: UUID
    ordinal_input_binding_ref: UUID
    ordinal: Annotated[
        StrictInt,
        Field(ge=1, le=CYCLE2_ORDINAL_CLAIM_MAX),
    ]


class OrderCandidateSelectionRecord(AuditOnlyModel):
    """Append-only record created only after the full selection closure passes."""

    record_schema_version: ClassVar[
        Literal["order_candidate_selection_record.p0.v1"]
    ] = ORDER_CANDIDATE_SELECTION_RECORD_SCHEMA_VERSION

    selection_id: UUID
    private_owner_scope_ref: StrictOpaqueRef
    conversation_id: UUID
    task_id: UUID
    request_unit_id: UUID
    source_message_ref: UUID
    ordinal_input_binding_ref: UUID
    candidate_set_ref: UUID
    candidate_set_version: OrderCandidateSetVersion
    search_observation_ref: UUID
    search_observation_record_schema_version: Literal[
        "order_search_observation_record.p0.v1"
    ]
    observation_candidate_ref: UUID
    candidate_source_version: OrderCandidateSourceVersion
    owner_scoped_order_target_ref: StrictOpaqueRef
    selected_target_ref: StrictOpaqueRef
    base_task_state_version: StrictPositiveStateVersionC2
    result_task_state_version: StrictPositiveStateVersionC2
    selected_at: datetime

    @field_validator("selected_at")
    @classmethod
    def selected_at_is_utc(cls, value: datetime) -> datetime:
        return require_utc(value, field_name="OrderCandidateSelectionRecord.selected_at")

    @model_validator(mode="after")
    def selection_advances_task_version(self) -> Self:
        if self.result_task_state_version <= self.base_task_state_version:
            raise ValueError("result_task_state_version must be greater than base")
        return self


def validate_candidate_set_supersession(
    *,
    current: OrderCandidateSetRecord,
    previous: OrderCandidateSetRecord,
) -> None:
    """Validate one append-only same-context CandidateSet supersession edge."""

    if current.supersedes_candidate_set_ref != previous.candidate_set_id:
        raise ValueError("CandidateSet supersession ref does not identify previous set")
    for field_name in (
        "private_owner_scope_ref",
        "conversation_id",
        "task_id",
        "request_unit_id",
    ):
        if getattr(current, field_name) != getattr(previous, field_name):
            raise ValueError(f"CandidateSet supersession {field_name} mismatch")
    if current.base_task_state_version < previous.result_task_state_version:
        raise ValueError("CandidateSet supersession cannot move Task version backwards")
    if current.created_at < previous.created_at:
        raise ValueError("CandidateSet supersession cannot move trusted time backwards")


def validate_current_candidate_selection(
    *,
    current_candidate_sets: Sequence[OrderCandidateSetRecord],
    request: OrderCandidateSelectionRequest,
    trusted_owner_scope_ref: str,
    conversation_id: UUID,
    task_id: UUID,
    request_unit_id: UUID,
    pending_candidate_set_ref: UUID | None,
    current_task_state_version: int,
    current_query_binding_refs: Sequence[UUID],
    trusted_now: datetime,
    superseded_candidate_set_refs: Sequence[UUID] = (),
    existing_selection_records: Sequence[OrderCandidateSelectionRecord] = (),
) -> OrderCandidateSetEntry:
    """Validate the loaded current-set capability; perform no read, CAS, or Tool call."""

    trusted_now = require_utc(trusted_now, field_name="trusted_now")
    if type(trusted_owner_scope_ref) is not str or not trusted_owner_scope_ref:
        raise ValueError("trusted_owner_scope_ref must be a non-empty string")
    if type(current_task_state_version) is not int or current_task_state_version < 1:
        raise ValueError("current_task_state_version must be a strict positive integer")
    current_query_refs = tuple(current_query_binding_refs)
    if not current_query_refs or len(current_query_refs) != len(set(current_query_refs)):
        raise ValueError("current_query_binding_refs must be non-empty and unique")
    sets = tuple(current_candidate_sets)
    if len(sets) != 1:
        raise ValueError("selection requires exactly one current CandidateSet")
    candidate_set = sets[0]
    if pending_candidate_set_ref is None:
        raise ValueError("selection requires a pending CandidateSet ref")
    if pending_candidate_set_ref != candidate_set.candidate_set_id:
        raise ValueError("pending CandidateSet ref mismatch")
    if candidate_set.candidate_set_id in set(superseded_candidate_set_refs):
        raise ValueError("current CandidateSet is superseded")
    if candidate_set.outcome is not OrderCandidateSetOutcome.MULTIPLE:
        raise ValueError("ordinal selection requires a MULTIPLE CandidateSet")
    for field_name, trusted_value in (
        ("private_owner_scope_ref", trusted_owner_scope_ref),
        ("conversation_id", conversation_id),
        ("task_id", task_id),
        ("request_unit_id", request_unit_id),
    ):
        if getattr(candidate_set, field_name) != trusted_value:
            raise ValueError(f"CandidateSet {field_name} mismatch")
    if trusted_now >= candidate_set.valid_until:
        raise ValueError("CandidateSet is expired")
    if (
        candidate_set.selection_expected_task_state_version
        != current_task_state_version
    ):
        raise ValueError("CandidateSet expected Task version mismatch")
    if set(candidate_set.query_binding_refs) != set(current_query_refs):
        raise ValueError("CandidateSet query binding closure mismatch")

    selected = next(
        (
            candidate
            for candidate in candidate_set.ordered_candidates
            if candidate.ordinal == request.ordinal
        ),
        None,
    )
    if selected is None:
        raise ValueError("candidate ordinal is outside the current CandidateSet")
    for record in existing_selection_records:
        if record.source_message_ref == request.source_message_ref:
            raise ValueError(
                "CANDIDATE_REFRESH_REQUIRED: source message selection is already "
                "consumed or contradictory"
            )
    return selected
