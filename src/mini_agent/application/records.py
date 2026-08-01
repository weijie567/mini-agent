"""Application-owned records shared by Runtime, Infrastructure, and Eval."""

from __future__ import annotations

import weakref
from collections import Counter
from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from typing import Any, Annotated, Literal, Self, TypeVar
from uuid import UUID, uuid4

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
from mini_agent.core.control_gateway import (
    Cycle2GatewayCandidate,
    build_cycle2_authorized_tool_command,
)
from mini_agent.core.identity import CustomerContext
from mini_agent.core.memory import (
    ContextManifest,
    OrderObservation,
    SearchOrdersObservation,
    ShipmentObservation,
    validate_candidate_selection_closure,
    validate_search_candidate_set_observation_closure,
    validate_shipment_observation_supersession,
)
from mini_agent.core.request_processing import _normalize_order_id
from mini_agent.core.request_understanding import InputAuthority, UncertaintyV2
from mini_agent.core.shipment import (
    GetShipmentOutcome,
    GetShipmentResult,
    ShipmentAssessment,
    assess_shipment,
    shipment_snapshot_is_fresh_at_acceptance,
)
from mini_agent.core.task_state import (
    AcceptedTaskDeltaV2,
    CandidateValidationDecision,
    CandidateValidationRecordV2,
    DurableInputCandidateV2,
    DurableQueryContextualizationCandidateV2,
    DurableResolvedReferenceCandidateV2,
    DurableTaskDeltaCandidateV2,
    InputBinding,
    InputBindingV2,
    InputValidationStatus,
    OrderCandidateSelectionRecord,
    OrderCandidateSelectionRequest,
    OrderCandidateSetOutcome,
    OrderCandidateSetRecord,
    RequestUnderstandingRecordV2,
    RequestUnitRecord,
    TaskRecord,
    TaskStateTransition,
    TaskStatus,
)
from mini_agent.core.tool_system import (
    AuthorizedToolCommandV2,
    Cycle2RetryRevalidation,
    Cycle2ToolDispatchFacts,
    GateDecision,
    GateDecisionV2,
    GateDecisionValue,
    ModelVisibleToolsetArtifact,
    SafeReasonCode,
    ToolAttemptRecord,
    ToolAttemptRecordV2,
    ToolCallRecord,
    ToolCallRecordV2,
    ToolCallStatus,
    ToolRecoveryDecision,
    ToolRecoveryDisposition,
    ToolRetryRecoveryDecision,
    ToolRetryDecision,
    ToolEffect,
    ToolResultOutcome,
    decide_cycle2_tool_recovery,
    project_cycle2_budget_exhausted_recovery_terminal,
)
from mini_agent.core.trace import (
    AgentOutcome,
    AgentRunRecord,
    AgentRunRecordV2,
    AgentRunStatus,
    AgentRunStatusV2,
    StopReason,
    StopReasonV2,
    TimingAndUsageSummary,
    TraceEvent,
    TraceEventV2,
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


_OWNER_SCOPE_FACTORY_TOKEN = object()
_TRUSTED_OWNER_SCOPE_INSTANCES: dict[
    int,
    tuple[weakref.ReferenceType["TrustedOwnerScope"], str],
] = {}


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
        if (
            validation_context.get("owner_scope_factory_token")
            is not _OWNER_SCOPE_FACTORY_TOKEN
            or type(customer_context) is not CustomerContext
        ):
            raise ValueError("TrustedOwnerScope must be derived from CustomerContext")
        if not isinstance(value, Mapping):
            raise ValueError("TrustedOwnerScope requires a mapping projection")
        if value.get("customer_id") != customer_context.customer_id:
            raise ValueError("TrustedOwnerScope customer_id must match CustomerContext")
        return value

    @classmethod
    def from_customer_context(cls, context: CustomerContext) -> Self:
        canonical_context = _strict_rebuild_exact_write_contract_model(
            context,
            CustomerContext,
            error_message="CustomerContext must be recursively canonical",
        )
        return cls.model_validate(
            {"customer_id": canonical_context.customer_id},
            context={
                "customer_context": canonical_context,
                "owner_scope_factory_token": _OWNER_SCOPE_FACTORY_TOKEN,
            },
        )

    def model_post_init(self, context: Any, /) -> None:
        validation_context = context or {}
        customer_context = validation_context.get("customer_context")
        if (
            validation_context.get("owner_scope_factory_token")
            is _OWNER_SCOPE_FACTORY_TOKEN
            and type(customer_context) is CustomerContext
            and customer_context.customer_id == self.customer_id
        ):
            instance_id = id(self)

            def discard_if_same(
                expired: weakref.ReferenceType[TrustedOwnerScope],
                *,
                registered_id: int = instance_id,
            ) -> None:
                registered = _TRUSTED_OWNER_SCOPE_INSTANCES.get(registered_id)
                if registered is not None and registered[0] is expired:
                    _TRUSTED_OWNER_SCOPE_INSTANCES.pop(registered_id, None)

            _TRUSTED_OWNER_SCOPE_INSTANCES[instance_id] = (
                weakref.ref(self, discard_if_same),
                customer_context.customer_id,
            )

    def require_trusted_derivation(self) -> None:
        """Reject objects that bypassed the trusted CustomerContext factory."""

        registered = _TRUSTED_OWNER_SCOPE_INSTANCES.get(id(self))
        if (
            registered is None
            or registered[0]() is not self
            or self.customer_id != registered[1]
        ):
            raise ValueError("TrustedOwnerScope lacks CustomerContext derivation")


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
    required_field_names = frozenset(
        field_name
        for field_name, field in expected_type.model_fields.items()
        if field.is_required()
    )
    try:
        state = value.__dict__
        fields_set = value.__pydantic_fields_set__
        extra = value.__pydantic_extra__
        private = value.__pydantic_private__
    except (AttributeError, TypeError):
        raise ValueError(error_message) from None
    if (
        type(state) is not dict
        or any(type(field_name) is not str for field_name in state)
        or frozenset(state) != field_names
        or type(fields_set) is not set
        or any(type(field_name) is not str for field_name in fields_set)
        or not required_field_names.issubset(fields_set)
        or not fields_set.issubset(field_names)
        or extra is not None
        or private is not None
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
        {
            field_name: projection[field_name]
            for field_name in value.__pydantic_fields_set__
        },
        error_message=error_message,
    )


def _write_contract_values_match_exactly(
    left: object,
    right: object,
) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, BaseModel):
        try:
            declared_fields = set(type(left).model_fields)
            left_state = left.__dict__
            right_state = right.__dict__
            left_state_keys = set(left_state)
            right_state_keys = set(right_state)
            left_fields_set = left.__pydantic_fields_set__
            right_fields_set = right.__pydantic_fields_set__
        except (AttributeError, TypeError):
            return False
        if (
            type(left_state) is not dict
            or type(right_state) is not dict
            or any(type(field_name) is not str for field_name in left_state)
            or any(type(field_name) is not str for field_name in right_state)
            or left_state_keys != declared_fields
            or right_state_keys != declared_fields
            or type(left_fields_set) is not set
            or type(right_fields_set) is not set
            or any(
                type(field_name) is not str
                for field_name in left_fields_set
            )
            or any(
                type(field_name) is not str
                for field_name in right_fields_set
            )
            or left_fields_set != right_fields_set
            or not left_fields_set.issubset(declared_fields)
            or not right_fields_set.issubset(declared_fields)
        ):
            return False
        try:
            left_extra = left.__pydantic_extra__
            right_extra = right.__pydantic_extra__
            left_private = left.__pydantic_private__
            right_private = right.__pydantic_private__
        except (AttributeError, TypeError):
            return False
        if not _write_contract_values_match_exactly(left_extra, right_extra):
            return False
        if not _write_contract_values_match_exactly(left_private, right_private):
            return False
        return all(
            field_name in left.__dict__
            and field_name in right.__dict__
            and _write_contract_values_match_exactly(
                left.__dict__[field_name],
                right.__dict__[field_name],
            )
            for field_name in type(left).model_fields
        )
    if isinstance(left, tuple):
        return len(left) == len(right) and all(
            _write_contract_values_match_exactly(left_item, right_item)
            for left_item, right_item in zip(left, right, strict=True)
        )
    if isinstance(left, Mapping):
        left_items = tuple(left.items())
        right_items = tuple(right.items())
        return len(left_items) == len(right_items) and all(
            _write_contract_values_match_exactly(left_key, right_key)
            and _write_contract_values_match_exactly(left_value, right_value)
            for (left_key, left_value), (right_key, right_value) in zip(
                left_items,
                right_items,
                strict=True,
            )
        )
    if isinstance(left, StrEnum):
        return left == right
    if isinstance(left, datetime):
        return type(left) is datetime and left == right
    if isinstance(left, UUID):
        return type(left) is UUID and left == right
    if isinstance(left, str):
        return type(left) is str and left == right
    if isinstance(left, bool):
        return type(left) is bool and left == right
    if isinstance(left, int):
        return type(left) is int and left == right
    if isinstance(left, float):
        return type(left) is float and left == right
    if isinstance(left, bytes):
        return type(left) is bytes and left == right
    return left == right


def _require_exact_write_contract_projection(
    original: object,
    rebuilt: _ModelT,
    *,
    error_message: str,
) -> _ModelT:
    if not _write_contract_values_match_exactly(original, rebuilt):
        raise ValueError(error_message)
    return rebuilt


def _strict_rebuild_exact_write_contract_model(
    value: object,
    expected_type: type[_ModelT],
    *,
    error_message: str,
) -> _ModelT:
    rebuilt = _strict_rebuild_exact_model(
        value,
        expected_type,
        error_message=error_message,
    )
    return _require_exact_write_contract_projection(
        value,
        rebuilt,
        error_message=error_message,
    )


def _strict_tuple_projection(
    value: object,
    *,
    error_message: str,
) -> tuple[object, ...]:
    if type(value) is not tuple:
        raise ValueError(error_message)
    return value


def _strict_rebuild_durable_contextualization_v2(
    value: object,
) -> DurableQueryContextualizationCandidateV2:
    error_message = "RU-v2 contextualization must be recursively canonical"
    projection = _canonical_model_field_projection(
        value,
        DurableQueryContextualizationCandidateV2,
        error_message=error_message,
    )
    resolved = _strict_tuple_projection(
        projection["resolved_reference_candidates"],
        error_message=error_message,
    )
    uncertainties = _strict_tuple_projection(
        projection["uncertainties"],
        error_message=error_message,
    )
    _strict_tuple_projection(
        projection["source_message_refs"],
        error_message=error_message,
    )
    projection["resolved_reference_candidates"] = tuple(
        _strict_rebuild_exact_write_contract_model(
            item,
            DurableResolvedReferenceCandidateV2,
            error_message=error_message,
        )
        for item in resolved
    )
    projection["uncertainties"] = tuple(
        _strict_rebuild_exact_write_contract_model(
            item,
            UncertaintyV2,
            error_message=error_message,
        )
        for item in uncertainties
    )
    rebuilt = _strict_validate_canonical_projection(
        DurableQueryContextualizationCandidateV2,
        projection,
        error_message=error_message,
    )
    return _require_exact_write_contract_projection(
        value,
        rebuilt,
        error_message=error_message,
    )


def _strict_rebuild_durable_candidate_v2(
    value: object,
) -> DurableTaskDeltaCandidateV2:
    error_message = "RU-v2 Candidate must be recursively canonical"
    projection = _canonical_model_field_projection(
        value,
        DurableTaskDeltaCandidateV2,
        error_message=error_message,
    )
    input_candidates = _strict_tuple_projection(
        projection["input_candidates"],
        error_message=error_message,
    )
    projection["input_candidates"] = tuple(
        _strict_rebuild_exact_write_contract_model(
            item,
            DurableInputCandidateV2,
            error_message=error_message,
        )
        for item in input_candidates
    )
    rebuilt = _strict_validate_canonical_projection(
        DurableTaskDeltaCandidateV2,
        projection,
        error_message=error_message,
    )
    return _require_exact_write_contract_projection(
        value,
        rebuilt,
        error_message=error_message,
    )


def _strict_rebuild_request_understanding_record_v2(
    value: object,
) -> RequestUnderstandingRecordV2:
    error_message = "RU-v2 record must be recursively canonical"
    projection = _canonical_model_field_projection(
        value,
        RequestUnderstandingRecordV2,
        error_message=error_message,
    )
    candidates = _strict_tuple_projection(
        projection["task_delta_candidates"],
        error_message=error_message,
    )
    validation = _strict_tuple_projection(
        projection["candidate_validation"],
        error_message=error_message,
    )
    _strict_tuple_projection(
        projection["accepted_delta_refs"],
        error_message=error_message,
    )
    projection["contextualization"] = (
        _strict_rebuild_durable_contextualization_v2(
            projection["contextualization"]
        )
    )
    projection["task_delta_candidates"] = tuple(
        _strict_rebuild_durable_candidate_v2(candidate)
        for candidate in candidates
    )
    projection["candidate_validation"] = tuple(
        _strict_rebuild_exact_write_contract_model(
            decision,
            CandidateValidationRecordV2,
            error_message=error_message,
        )
        for decision in validation
    )
    rebuilt = _strict_validate_canonical_projection(
        RequestUnderstandingRecordV2,
        {
            field_name: projection[field_name]
            for field_name in value.__pydantic_fields_set__
        },
        error_message=error_message,
    )
    return _require_exact_write_contract_projection(
        value,
        rebuilt,
        error_message=error_message,
    )


def _require_exact_trusted_owner_scope(value: object) -> TrustedOwnerScope:
    error_message = "TrustedOwnerScope must be an exact trusted projection"
    if type(value) is not TrustedOwnerScope:
        raise ValueError(error_message)
    try:
        state = value.__dict__
        fields_set = value.__pydantic_fields_set__
        extra = value.__pydantic_extra__
        private = value.__pydantic_private__
    except (AttributeError, TypeError):
        raise ValueError(error_message) from None
    if (
        type(state) is not dict
        or set(state) != {"customer_id"}
        or type(state.get("customer_id")) is not str
        or type(fields_set) is not set
        or fields_set != {"customer_id"}
        or extra is not None
        or private is not None
    ):
        raise ValueError(error_message)
    try:
        value.require_trusted_derivation()
    except ValueError:
        raise ValueError(error_message) from None
    return value


def _referenced_message_ids_v2(
    record: RequestUnderstandingRecordV2,
) -> frozenset[UUID]:
    references = {
        record.message_ref,
        *record.contextualization.source_message_refs,
    }
    references.update(
        candidate.source_ref
        for candidate in record.contextualization.resolved_reference_candidates
    )
    references.update(
        source_ref
        for uncertainty in record.contextualization.uncertainties
        for source_ref in uncertainty.source_message_refs
    )
    references.update(
        candidate_input.source_ref
        for candidate in record.task_delta_candidates
        for candidate_input in candidate.input_candidates
    )
    return frozenset(references)


def _validate_v2_owner_roots_and_messages(
    *,
    owner_scope: object,
    conversation: object,
    messages: object,
    run: object,
    record: RequestUnderstandingRecordV2,
) -> MessageRecord:
    owner = _require_exact_trusted_owner_scope(owner_scope)
    canonical_conversation = _strict_rebuild_exact_write_contract_model(
        conversation,
        ConversationRecord,
        error_message="RU-v2 Conversation must be canonical",
    )
    message_values = _strict_tuple_projection(
        messages,
        error_message="RU-v2 Message closure must be canonical",
    )
    canonical_messages = tuple(
        _strict_rebuild_exact_write_contract_model(
            message,
            MessageRecord,
            error_message="RU-v2 Message closure must be canonical",
        )
        for message in message_values
    )
    canonical_run = _strict_rebuild_exact_write_contract_model(
        run,
        AgentRunRecord,
        error_message="RU-v2 Run must be canonical",
    )
    message_ids = tuple(message.message_id for message in canonical_messages)
    if len(message_ids) != len(set(message_ids)):
        raise ValueError("RU-v2 expected Message identities must be unique")
    if canonical_conversation.owner_customer_id != owner.customer_id:
        raise ValueError("RU-v2 Conversation must match trusted owner scope")
    if any(
        message.conversation_id != canonical_conversation.conversation_id
        for message in canonical_messages
    ):
        raise ValueError("RU-v2 Messages must belong to the exact Conversation")
    if set(message_ids) != set(_referenced_message_ids_v2(record)):
        raise ValueError("RU-v2 requires the exact referenced Message set")
    current_messages = tuple(
        message
        for message in canonical_messages
        if message.message_id == record.message_ref
    )
    if (
        len(current_messages) != 1
        or current_messages[0].direction is not MessageDirection.USER
    ):
        raise ValueError("RU-v2 current Message must be exactly one USER Message")
    if (
        canonical_run.status is not AgentRunStatus.RUNNING
        or canonical_run.incomplete_reason is not None
    ):
        raise ValueError("RU-v2 requires a clean RUNNING Run")
    if canonical_run.conversation_id != canonical_conversation.conversation_id:
        raise ValueError("RU-v2 Run must belong to the exact Conversation")
    if record.run_id != canonical_run.run_id:
        raise ValueError("RU-v2 record must bind the exact Run")
    current_message = current_messages[0]
    if (
        record.created_at < current_message.received_at
        or record.created_at < canonical_run.started_at
    ):
        raise ValueError(
            "RU-v2 creation timestamp cannot precede current Message or Run"
        )
    return current_message


class SaveRequestUnderstandingV2AcceptedCommand(_StrictRuntimePrivateRecord):
    """One exact RU-v2 parent/accepted-child logical aggregate."""

    record: RequestUnderstandingRecordV2
    accepted_delta: AcceptedTaskDeltaV2

    @model_validator(mode="after")
    def accepted_child_is_exact_one_candidate_projection(self) -> Self:
        record = _strict_rebuild_request_understanding_record_v2(self.record)
        child = _strict_rebuild_exact_write_contract_model(
            self.accepted_delta,
            AcceptedTaskDeltaV2,
            error_message="RU-v2 accepted child must be canonical",
        )
        if (
            len(record.task_delta_candidates) != 1
            or len(record.candidate_validation) != 1
        ):
            raise ValueError(
                "RU-v2 accepted command requires exactly one emitted Candidate"
            )
        candidate = record.task_delta_candidates[0]
        decision = record.candidate_validation[0]
        if (
            decision.candidate_ref != candidate.candidate_id
            or decision.decision is not CandidateValidationDecision.ACCEPT
            or record.accepted_delta_refs != (child.accepted_delta_id,)
            or child.candidate_ref != candidate.candidate_id
            or child.message_ref != record.message_ref
            or child.operation is not candidate.operation
            or child.goal_text != candidate.goal_patch
        ):
            raise ValueError(
                "RU-v2 accepted child must preserve its candidate projection"
            )
        if (
            len(child.input_binding_refs) != 1
            or len(set(child.input_binding_refs)) != 1
            or child.base_task_state_version is not None
            or child.result_task_state_version != 1
            or record.proposed_base_task_state_version is not None
            or record.validated_task_state_version != 1
            or record.next_move_candidate_ref is None
        ):
            raise ValueError(
                "RU-v2 accepted command requires one initial Task effect"
            )
        if record.created_at != child.accepted_at:
            raise ValueError(
                "RU-v2 parent and accepted child must share one timestamp"
            )
        return self


def _strict_rebuild_v2_accepted_command(
    value: object,
) -> SaveRequestUnderstandingV2AcceptedCommand:
    error_message = "RU-v2 accepted command must be recursively canonical"
    projection = _canonical_model_field_projection(
        value,
        SaveRequestUnderstandingV2AcceptedCommand,
        error_message=error_message,
    )
    projection["record"] = _strict_rebuild_request_understanding_record_v2(
        projection["record"]
    )
    projection["accepted_delta"] = _strict_rebuild_exact_write_contract_model(
        projection["accepted_delta"],
        AcceptedTaskDeltaV2,
        error_message=error_message,
    )
    rebuilt = _strict_validate_canonical_projection(
        SaveRequestUnderstandingV2AcceptedCommand,
        projection,
        error_message=error_message,
    )
    return _require_exact_write_contract_projection(
        value,
        rebuilt,
        error_message=error_message,
    )


class SaveRequestUnderstandingV2NoTaskCommand(_StrictRuntimePrivateRecord):
    """Conditional RU-v2 parent write with no accepted Task effect."""

    owner_scope: TrustedOwnerScope
    expected_conversation_record: ConversationRecord
    expected_message_records: Annotated[
        tuple[MessageRecord, ...],
        Field(min_length=1, max_length=8),
    ]
    expected_active_run_record: AgentRunRecord
    request_understanding_record: RequestUnderstandingRecordV2

    @model_validator(mode="after")
    def graph_is_exact_owner_bound_no_task_closure(self) -> Self:
        record = _strict_rebuild_request_understanding_record_v2(
            self.request_understanding_record
        )
        _validate_v2_owner_roots_and_messages(
            owner_scope=self.owner_scope,
            conversation=self.expected_conversation_record,
            messages=self.expected_message_records,
            run=self.expected_active_run_record,
            record=record,
        )
        if (
            record.accepted_delta_refs
            or any(
                decision.decision is CandidateValidationDecision.ACCEPT
                for decision in record.candidate_validation
            )
            or record.proposed_base_task_state_version is not None
            or record.validated_task_state_version is not None
            or record.next_move_candidate_ref is not None
        ):
            raise ValueError("RU-v2 no-task command must carry no Task effect")
        return self


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


def _strict_rebuild_create_task_command(
    value: object,
) -> CreateTaskCommand:
    error_message = "initial Task command must be recursively canonical"
    projection = _canonical_model_field_projection(
        value,
        CreateTaskCommand,
        error_message=error_message,
    )
    projection["initial_record"] = _strict_rebuild_exact_write_contract_model(
        projection["initial_record"],
        TaskRecord,
        error_message=error_message,
    )
    rebuilt = _strict_validate_canonical_projection(
        CreateTaskCommand,
        projection,
        error_message=error_message,
    )
    return _require_exact_write_contract_projection(
        value,
        rebuilt,
        error_message=error_message,
    )


def _strict_rebuild_create_request_unit_command(
    value: object,
) -> CreateRequestUnitCommand:
    error_message = "initial RequestUnit command must be recursively canonical"
    projection = _canonical_model_field_projection(
        value,
        CreateRequestUnitCommand,
        error_message=error_message,
    )
    projection["initial_record"] = _strict_rebuild_exact_write_contract_model(
        projection["initial_record"],
        RequestUnitRecord,
        error_message=error_message,
    )
    rebuilt = _strict_validate_canonical_projection(
        CreateRequestUnitCommand,
        projection,
        error_message=error_message,
    )
    return _require_exact_write_contract_projection(
        value,
        rebuilt,
        error_message=error_message,
    )


def _strict_rebuild_save_input_binding_command(
    value: object,
) -> SaveInputBindingCommand:
    error_message = "initial InputBinding command must be recursively canonical"
    projection = _canonical_model_field_projection(
        value,
        SaveInputBindingCommand,
        error_message=error_message,
    )
    projection["record"] = _strict_rebuild_exact_write_contract_model(
        projection["record"],
        InputBinding,
        error_message=error_message,
    )
    rebuilt = _strict_validate_canonical_projection(
        SaveInputBindingCommand,
        projection,
        error_message=error_message,
    )
    return _require_exact_write_contract_projection(
        value,
        rebuilt,
        error_message=error_message,
    )


def _strict_rebuild_create_run_task_link_command(
    value: object,
) -> CreateRunTaskLinkCommand:
    error_message = "initial RunTaskLink command must be recursively canonical"
    projection = _canonical_model_field_projection(
        value,
        CreateRunTaskLinkCommand,
        error_message=error_message,
    )
    projection["active_record"] = _strict_rebuild_exact_write_contract_model(
        projection["active_record"],
        RunTaskLinkRecord,
        error_message=error_message,
    )
    rebuilt = _strict_validate_canonical_projection(
        CreateRunTaskLinkCommand,
        projection,
        error_message=error_message,
    )
    return _require_exact_write_contract_projection(
        value,
        rebuilt,
        error_message=error_message,
    )


class CreateInitialTaskGraphV2Command(_StrictRuntimePrivateRecord):
    """One conditional RU-v2 exact-one initial graph write."""

    owner_scope: TrustedOwnerScope
    expected_conversation_record: ConversationRecord
    expected_message_records: Annotated[
        tuple[MessageRecord, ...],
        Field(min_length=1, max_length=8),
    ]
    expected_active_run_record: AgentRunRecord
    request_understanding: SaveRequestUnderstandingV2AcceptedCommand
    initial_task: CreateTaskCommand
    initial_request_unit: CreateRequestUnitCommand
    input_binding: SaveInputBindingCommand
    conversation_task_link: ConversationTaskLinkRecord
    run_task_link: CreateRunTaskLinkCommand

    @model_validator(mode="after")
    def graph_is_exact_clean_initial_projection(self) -> Self:
        understanding = _strict_rebuild_v2_accepted_command(
            self.request_understanding
        )
        record = understanding.record
        child = understanding.accepted_delta
        _validate_v2_owner_roots_and_messages(
            owner_scope=self.owner_scope,
            conversation=self.expected_conversation_record,
            messages=self.expected_message_records,
            run=self.expected_active_run_record,
            record=record,
        )
        task_command = _strict_rebuild_create_task_command(self.initial_task)
        unit_command = _strict_rebuild_create_request_unit_command(
            self.initial_request_unit
        )
        binding_command = _strict_rebuild_save_input_binding_command(
            self.input_binding
        )
        conversation_link = _strict_rebuild_exact_write_contract_model(
            self.conversation_task_link,
            ConversationTaskLinkRecord,
            error_message="initial ConversationTaskLink must be canonical",
        )
        run_link_command = _strict_rebuild_create_run_task_link_command(
            self.run_task_link
        )
        task = task_command.initial_record
        unit = unit_command.initial_record
        binding = binding_command.record
        run_link = run_link_command.active_record
        conversation = self.expected_conversation_record
        run = self.expected_active_run_record
        candidate = record.task_delta_candidates[0]
        candidate_input = candidate.input_candidates[0]

        try:
            normalized_candidate_value = _normalize_order_id(
                candidate_input.candidate_value
            )
        except ValueError:
            raise ValueError(
                "RU-v2 accepted candidate InputBinding is invalid"
            ) from None
        if (
            binding.name != candidate_input.name
            or binding.normalized_value != normalized_candidate_value
            or binding.authority is not candidate_input.authority
            or binding.source_refs != (candidate_input.source_ref,)
        ):
            raise ValueError(
                "RU-v2 accepted candidate InputBinding projection mismatch"
            )
        if task.owner_customer_id != self.owner_scope.customer_id:
            raise ValueError("initial Task must match the trusted owner scope")
        if (
            task.status is not TaskStatus.ACTIVE
            or task.state_version != 1
            or task.last_outcome_ref is not None
        ):
            raise ValueError("RU-v2 requires a clean initial Task")
        if (
            unit.task_id != task.task_id
            or unit.goal_text != child.goal_text
            or unit.goal_source_refs != (record.message_ref,)
            or unit.input_binding_refs != (binding.binding_id,)
            or unit.status is not TaskStatus.ACTIVE
            or unit.state_version != 1
            or unit.contextualization_ref is not None
            or unit.constraint_refs
            or unit.dependency_refs
            or unit.open_questions
            or unit.observation_refs
            or unit.evidence_binding_refs
            or unit.pending_action_ref is not None
            or unit.result_refs
        ):
            raise ValueError("RU-v2 requires a clean initial RequestUnit")
        if (
            binding_command.request_unit_id != unit.request_unit_id
            or binding.validation_status is not InputValidationStatus.ACCEPTED
            or binding.confirmed_by_user is not True
            or binding.supersedes is not None
        ):
            raise ValueError("RU-v2 requires a clean initial InputBinding")
        if (
            child.task_id != task.task_id
            or child.input_binding_refs != (binding.binding_id,)
            or child.base_task_state_version is not None
            or child.result_task_state_version != task.state_version
            or child.result_task_state_version != unit.state_version
        ):
            raise ValueError("RU-v2 accepted child must bind the initial Task effect")
        generated_ids = (
            record.request_understanding_record_id,
            record.next_move_candidate_ref,
            child.accepted_delta_id,
            task.task_id,
            unit.request_unit_id,
            binding.binding_id,
        )
        if len(generated_ids) != len(set(generated_ids)):
            raise ValueError("RU-v2 initial graph identities must be unique")
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
            or run_link.result_task_state_version is not None
        ):
            raise ValueError("RunTaskLink must bind the Run to its new Task")
        timestamps = {
            record.created_at,
            child.accepted_at,
            task.created_at,
            task.updated_at,
            unit.created_at,
            unit.updated_at,
            binding.created_at,
            binding.updated_at,
            conversation_link.linked_at,
        }
        if len(timestamps) != 1:
            raise ValueError("RU-v2 initial graph must use one trusted timestamp")
        initial_at = next(iter(timestamps))
        current_message = next(
            message
            for message in self.expected_message_records
            if message.message_id == record.message_ref
        )
        if (
            initial_at < current_message.received_at
            or initial_at < run.started_at
        ):
            raise ValueError(
                "RU-v2 initial timestamp cannot precede current Message or Run"
            )
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


RUN_TASK_LINK_RECORD_V2_SCHEMA_VERSION = "run_task_link_record.p0.v2"


def _require_exact_cycle2_model(
    value: object,
    expected_type: type[BaseModel],
    *,
    field_name: str,
) -> BaseModel:
    """Reject sidecars/bypasses and return a freshly validated canonical instance."""

    if type(value) is not expected_type:
        raise ValueError(f"{field_name} must be an exact {expected_type.__name__}")
    if expected_type is TrustedOwnerScope:
        return _require_exact_trusted_owner_scope(value)
    error_message = f"{field_name} must be recursively canonical"
    try:
        if expected_type.__module__ == __name__:
            projection = _canonical_model_field_projection(
                value,
                expected_type,
                error_message=error_message,
            )
            rebuilt = expected_type.model_validate(projection, strict=True)
        else:
            rebuilt = _strict_rebuild_exact_write_contract_model(
                value,
                expected_type,
                error_message=error_message,
            )
    except (ValidationError, ValueError) as error:
        raise ValueError(error_message) from error
    return rebuilt


def _require_exact_cycle2_inputs(
    value: object,
    *,
    model_fields: Mapping[str, type[BaseModel]],
    optional_model_fields: Mapping[str, type[BaseModel]] | None = None,
    tuple_model_fields: Mapping[str, type[BaseModel]] | None = None,
) -> object:
    if not isinstance(value, Mapping):
        raise ValueError("Cycle 2 Application contract requires a mapping")
    canonical = dict(value)
    for field_name, expected_type in model_fields.items():
        canonical[field_name] = _require_exact_cycle2_model(
            value.get(field_name),
            expected_type,
            field_name=field_name,
        )
    for field_name, expected_type in (optional_model_fields or {}).items():
        item = value.get(field_name)
        if item is not None:
            canonical[field_name] = _require_exact_cycle2_model(
                item,
                expected_type,
                field_name=field_name,
            )
    for field_name, expected_type in (tuple_model_fields or {}).items():
        items = value.get(field_name, ())
        if type(items) is not tuple:
            raise ValueError(f"{field_name} must be an exact tuple")
        canonical[field_name] = tuple(
            _require_exact_cycle2_model(
                item,
                expected_type,
                field_name=field_name,
            )
            for item in items
        )
    return canonical


def _owner_matches_private_scope(
    owner_scope: TrustedOwnerScope,
    private_owner_scope_ref: str,
) -> bool:
    return owner_scope.customer_id == private_owner_scope_ref


def _task_and_request_unit_form_current_pair(
    *,
    owner_scope: TrustedOwnerScope,
    task_record: TaskRecord,
    request_unit_record: RequestUnitRecord,
) -> None:
    if task_record.owner_customer_id != owner_scope.customer_id:
        raise ValueError("Task owner does not match trusted owner scope")
    if request_unit_record.task_id != task_record.task_id:
        raise ValueError("RequestUnit does not belong to Task")
    if request_unit_record.state_version != task_record.state_version:
        raise ValueError("Task and RequestUnit current versions must match")
    if request_unit_record.status is not task_record.status:
        raise ValueError("Task and RequestUnit current statuses must match")


def _task_pair_advances_once(
    *,
    expected_task_record: TaskRecord,
    next_task_record: TaskRecord,
    expected_request_unit_record: RequestUnitRecord,
    next_request_unit_record: RequestUnitRecord,
    result_state_version: int,
    changed_at: datetime,
    allowed_request_unit_delta_fields: frozenset[str],
) -> None:
    task_delta_fields = frozenset({"status", "state_version", "updated_at"})
    if any(
        getattr(next_task_record, field_name)
        != getattr(expected_task_record, field_name)
        for field_name in TaskRecord.model_fields
        if field_name not in task_delta_fields
    ):
        raise ValueError("Task transition changed a non-authorized field")
    unit_delta_fields = frozenset(
        {"status", "state_version", "updated_at"}
    ) | allowed_request_unit_delta_fields
    if any(
        getattr(next_request_unit_record, field_name)
        != getattr(expected_request_unit_record, field_name)
        for field_name in RequestUnitRecord.model_fields
        if field_name not in unit_delta_fields
    ):
        raise ValueError("RequestUnit transition changed a non-authorized field")
    if result_state_version != expected_task_record.state_version + 1:
        raise ValueError("Cycle 2 Task effect must increment version exactly once")
    if (
        next_task_record.state_version != result_state_version
        or next_request_unit_record.state_version != result_state_version
        or expected_request_unit_record.state_version
        != expected_task_record.state_version
    ):
        raise ValueError("Task and RequestUnit versions must close atomically")
    if (
        next_task_record.status is not next_request_unit_record.status
        or next_task_record.updated_at != changed_at
        or next_request_unit_record.updated_at != changed_at
    ):
        raise ValueError("Task and RequestUnit effect must share status and timestamp")
    if (
        changed_at < expected_task_record.updated_at
        or changed_at < expected_request_unit_record.updated_at
    ):
        raise ValueError("Task effect timestamp cannot move backwards")


class RunTaskLinkRecordV2(_StrictAuditOnlyRecord):
    """Inactive exact-v2 Run/Task link; ``None`` can close SUPERSEDED only."""

    record_schema_version: Literal["run_task_link_record.p0.v2"] = (
        RUN_TASK_LINK_RECORD_V2_SCHEMA_VERSION
    )
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
            raise ValueError("v2 RunTaskLink result version cannot precede base")
        return self


class Cycle2WriteResult(StrEnum):
    """Closed result for inactive aggregate writes; non-APPLIED means zero writes."""

    APPLIED = "APPLIED"
    ALREADY_APPLIED = "ALREADY_APPLIED"
    PROJECTION_CONFLICT = "PROJECTION_CONFLICT"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class Cycle2DispatchFenceWriteResult(StrEnum):
    """Only APPLIED grants one dispatch after an exact attempt append fence."""

    APPLIED = "APPLIED"
    ALREADY_APPLIED = "ALREADY_APPLIED"
    PROJECTION_CONFLICT = "PROJECTION_CONFLICT"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class Cycle2ReadDispatchGrant(_StrictRuntimePrivateRecord):
    """One awaited READ-fence result; never a persistent or replayable record."""

    write_result: Cycle2DispatchFenceWriteResult
    tool_call_id: UUID | None = None
    attempt_no: Annotated[int, Field(strict=True, ge=1, le=2)] | None = None
    trusted_fenced_at: datetime | None = None
    effective_timeout_ms: (
        Annotated[int, Field(strict=True, ge=1, le=500)] | None
    ) = None

    @field_validator("trusted_fenced_at")
    @classmethod
    def trusted_fenced_at_is_utc(
        cls,
        value: datetime | None,
    ) -> datetime | None:
        if value is None:
            return None
        return require_utc(value, field_name="dispatch grant trusted_fenced_at")

    @model_validator(mode="after")
    def applied_matrix_is_closed(self) -> Self:
        grant_fields = (
            self.tool_call_id,
            self.attempt_no,
            self.trusted_fenced_at,
            self.effective_timeout_ms,
        )
        if self.write_result is Cycle2DispatchFenceWriteResult.APPLIED:
            if any(value is None for value in grant_fields):
                raise ValueError("APPLIED dispatch grant requires every grant field")
        elif any(value is not None for value in grant_fields):
            raise ValueError("non-APPLIED dispatch grant requires null grant fields")
        return self


def _require_complete_current_input_bindings_v2(
    *,
    request_unit: RequestUnitRecord,
    bindings: tuple[InputBindingV2, ...],
    trusted_now: datetime,
) -> None:
    binding_ids = tuple(binding.binding_id for binding in bindings)
    if (
        len(binding_ids) != len(set(binding_ids))
        or binding_ids != request_unit.input_binding_refs
    ):
        raise ValueError(
            "current InputBindingV2 records must exactly match RequestUnit refs"
        )
    if any(
        len(binding.source_refs) != len(set(binding.source_refs))
        or binding.created_at > trusted_now
        or binding.updated_at > trusted_now
        for binding in bindings
    ):
        raise ValueError("current InputBindingV2 record is not canonical and current")


def _is_canonical_uuid_text(value: object) -> bool:
    if type(value) is not str:
        return False
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError):
        return False
    return str(parsed) == value


class ContinuationInputBindingReadClosure(_StrictRuntimePrivateRecord):
    """Owner-reader snapshot for one existing-Task USER continuation."""

    owner_scope: TrustedOwnerScope
    trusted_conversation_record: ConversationRecord
    current_conversation_task_link_record: ConversationTaskLinkRecord
    saved_user_message_record: MessageRecord
    current_task_record: TaskRecord
    current_request_unit_record: RequestUnitRecord
    current_input_binding_records: Annotated[
        tuple[InputBindingV2, ...],
        Field(min_length=1),
    ]
    trusted_now: datetime

    @model_validator(mode="before")
    @classmethod
    def nested_records_are_exact(cls, value: object) -> object:
        return _require_exact_cycle2_inputs(
            value,
            model_fields={
                "owner_scope": TrustedOwnerScope,
                "trusted_conversation_record": ConversationRecord,
                "current_conversation_task_link_record": (
                    ConversationTaskLinkRecord
                ),
                "saved_user_message_record": MessageRecord,
                "current_task_record": TaskRecord,
                "current_request_unit_record": RequestUnitRecord,
            },
            tuple_model_fields={
                "current_input_binding_records": InputBindingV2,
            },
        )

    @field_validator("trusted_now")
    @classmethod
    def trusted_now_is_utc(cls, value: datetime) -> datetime:
        return require_utc(value, field_name="trusted_now")

    @model_validator(mode="after")
    def continuation_graph_is_exact_and_current(self) -> Self:
        conversation = self.trusted_conversation_record
        link = self.current_conversation_task_link_record
        message = self.saved_user_message_record
        task = self.current_task_record
        unit = self.current_request_unit_record
        _task_and_request_unit_form_current_pair(
            owner_scope=self.owner_scope,
            task_record=task,
            request_unit_record=unit,
        )
        if (
            conversation.owner_customer_id != self.owner_scope.customer_id
            or link.conversation_id != conversation.conversation_id
            or link.task_id != task.task_id
            or link.ended_at is not None
            or message.conversation_id != conversation.conversation_id
            or message.direction is not MessageDirection.USER
            or message.received_at < conversation.created_at
            or message.received_at > self.trusted_now
            or task.updated_at > self.trusted_now
            or unit.updated_at > self.trusted_now
        ):
            raise ValueError("continuation owner/Conversation/Message closure mismatch")
        _require_complete_current_input_bindings_v2(
            request_unit=unit,
            bindings=self.current_input_binding_records,
            trusted_now=self.trusted_now,
        )
        names = tuple(binding.name for binding in self.current_input_binding_records)
        if len(names) != len(set(names)):
            raise ValueError("continuation requires unique current binding names")
        return self


class ApplyContinuationInputBindingV2Command(_StrictRuntimePrivateRecord):
    """CAS one non-ordinal binding and Task/RequestUnit version advance."""

    loaded_closure: ContinuationInputBindingReadClosure
    new_input_binding_record: InputBindingV2
    next_task_record: TaskRecord
    next_request_unit_record: RequestUnitRecord

    @model_validator(mode="before")
    @classmethod
    def nested_records_are_exact(cls, value: object) -> object:
        return _require_exact_cycle2_inputs(
            value,
            model_fields={
                "loaded_closure": ContinuationInputBindingReadClosure,
                "new_input_binding_record": InputBindingV2,
                "next_task_record": TaskRecord,
                "next_request_unit_record": RequestUnitRecord,
            },
        )

    @model_validator(mode="after")
    def continuation_effect_is_exact(self) -> Self:
        closure = self.loaded_closure
        current_task = closure.current_task_record
        current_unit = closure.current_request_unit_record
        binding = self.new_input_binding_record
        if binding.name == "candidate_ordinal":
            raise ValueError("candidate_ordinal requires the selection CAS")
        if binding.binding_id in current_unit.input_binding_refs:
            raise ValueError("continuation binding identity must be new")
        if binding.source_refs != (closure.saved_user_message_record.message_id,):
            raise ValueError("continuation binding must cite the exact USER Message")
        if (
            binding.created_at != closure.trusted_now
            or binding.updated_at != closure.trusted_now
        ):
            raise ValueError("continuation binding must use trusted transaction time")

        same_name = tuple(
            current
            for current in closure.current_input_binding_records
            if current.name == binding.name
        )
        if len(same_name) > 1:
            raise ValueError("continuation binding name is not uniquely current")
        expected_supersedes = same_name[0].binding_id if same_name else None
        if binding.supersedes != expected_supersedes:
            raise ValueError("continuation supersedes must identify one current binding")
        expected_refs = (
            tuple(
                binding.binding_id if ref == expected_supersedes else ref
                for ref in current_unit.input_binding_refs
            )
            if expected_supersedes is not None
            else (*current_unit.input_binding_refs, binding.binding_id)
        )
        if self.next_request_unit_record.input_binding_refs != expected_refs:
            raise ValueError("continuation must replace only its same-name binding ref")

        _task_pair_advances_once(
            expected_task_record=current_task,
            next_task_record=self.next_task_record,
            expected_request_unit_record=current_unit,
            next_request_unit_record=self.next_request_unit_record,
            result_state_version=current_task.state_version + 1,
            changed_at=closure.trusted_now,
            allowed_request_unit_delta_fields=frozenset({"input_binding_refs"}),
        )
        if (
            self.next_task_record.status is not current_task.status
            or self.next_request_unit_record.status is not current_unit.status
        ):
            raise ValueError("ordinary continuation cannot change Task status")
        return self


class AcceptedOrderSearchQueryBindingReadClosure(_StrictRuntimePrivateRecord):
    """Exact owner-reader projection of one still-current search query Claim."""

    binding_ref: UUID
    binding_name: Literal["product_description"] = "product_description"
    normalized_query: NonEmptyString
    authority: Literal[InputAuthority.USER_CLAIM] = InputAuthority.USER_CLAIM
    validation_status: Literal[InputValidationStatus.ACCEPTED] = (
        InputValidationStatus.ACCEPTED
    )
    private_owner_scope_ref: NonEmptyString
    conversation_id: UUID
    task_id: UUID
    request_unit_id: UUID
    accepted_task_state_version: PositiveStateVersion
    current_task_state_version: PositiveStateVersion
    source_message_record: MessageRecord
    accepted_at: datetime
    superseded_by_binding_ref: Literal[None] = None

    @model_validator(mode="before")
    @classmethod
    def nested_record_is_exact(cls, value: object) -> object:
        return _require_exact_cycle2_inputs(
            value,
            model_fields={"source_message_record": MessageRecord},
        )

    @field_validator("accepted_at")
    @classmethod
    def accepted_at_is_utc(cls, value: datetime) -> datetime:
        return require_utc(value, field_name="accepted_at")

    @model_validator(mode="after")
    def source_is_one_saved_user_message(self) -> Self:
        message = self.source_message_record
        if (
            message.direction is not MessageDirection.USER
            or message.conversation_id != self.conversation_id
            or self.accepted_at < message.received_at
            or self.current_task_state_version
            < self.accepted_task_state_version
        ):
            raise ValueError("search query binding requires exact current USER Claim")
        return self


class OrderSearchCurrentReadClosure(_StrictRuntimePrivateRecord):
    """Exact typed records returned by the owner-scoped search pre-read."""

    owner_scope: TrustedOwnerScope
    trusted_conversation_record: ConversationRecord
    source_run_record: AgentRunRecordV2
    current_query_binding: AcceptedOrderSearchQueryBindingReadClosure
    current_task_record: TaskRecord
    current_request_unit_record: RequestUnitRecord
    current_candidate_source_tool_call_record: ToolCallRecordV2 | None = None
    current_search_observation_record: SearchOrdersObservation | None = None
    current_candidate_set_record: OrderCandidateSetRecord | None = None
    trusted_read_at: datetime

    @model_validator(mode="before")
    @classmethod
    def nested_records_are_exact(cls, value: object) -> object:
        return _require_exact_cycle2_inputs(
            value,
            model_fields={
                "owner_scope": TrustedOwnerScope,
                "trusted_conversation_record": ConversationRecord,
                "source_run_record": AgentRunRecordV2,
                "current_query_binding": (
                    AcceptedOrderSearchQueryBindingReadClosure
                ),
                "current_task_record": TaskRecord,
                "current_request_unit_record": RequestUnitRecord,
            },
            optional_model_fields={
                "current_candidate_source_tool_call_record": ToolCallRecordV2,
                "current_search_observation_record": SearchOrdersObservation,
                "current_candidate_set_record": OrderCandidateSetRecord,
            },
        )

    @field_validator("trusted_read_at")
    @classmethod
    def read_at_is_utc(cls, value: datetime) -> datetime:
        return require_utc(value, field_name="search trusted_read_at")

    @model_validator(mode="after")
    def current_graph_is_exact(self) -> Self:
        task = self.current_task_record
        unit = self.current_request_unit_record
        query = self.current_query_binding
        conversation = self.trusted_conversation_record
        run = self.source_run_record
        _task_and_request_unit_form_current_pair(
            owner_scope=self.owner_scope,
            task_record=task,
            request_unit_record=unit,
        )
        if (
            unit.input_binding_refs != (query.binding_ref,)
            or query.private_owner_scope_ref != self.owner_scope.customer_id
            or query.conversation_id != conversation.conversation_id
            or query.task_id != task.task_id
            or query.request_unit_id != unit.request_unit_id
            or query.current_task_state_version != task.state_version
            or run.conversation_id != conversation.conversation_id
            or run.status is not AgentRunStatusV2.RUNNING
            or conversation.owner_customer_id != self.owner_scope.customer_id
            or max(
                task.updated_at,
                unit.updated_at,
                run.started_at,
                query.accepted_at,
            )
            > self.trusted_read_at
        ):
            raise ValueError("search owner-scoped current read closure mismatch")
        previous_source = self.current_candidate_source_tool_call_record
        previous_observation = self.current_search_observation_record
        previous_candidate_set = self.current_candidate_set_record
        previous_graph = (
            previous_source,
            previous_observation,
            previous_candidate_set,
        )
        if all(record is None for record in previous_graph):
            return self
        if (
            previous_source is None
            or previous_observation is None
            or previous_candidate_set is None
        ):
            raise ValueError("search current CandidateSet graph must be complete")
        if (
            previous_source.status is not ToolCallStatus.SUCCEEDED
            or previous_source.effect is not ToolEffect.READ
            or previous_source.canonical_tool_name.value != "search_orders"
            or previous_source.finished_at is None
            or previous_source.result_ref is None
            or previous_source.private_owner_scope_ref
            != self.owner_scope.customer_id
            or not _owner_matches_private_scope(
                self.owner_scope,
                previous_observation.private_owner_scope,
            )
            or previous_source.task_id != task.task_id
            or previous_source.request_unit_id != unit.request_unit_id
            or previous_source.validated_task_state_version
            != previous_candidate_set.base_task_state_version
            or previous_source.argument_binding_refs != (query.binding_ref,)
            or previous_observation.source_tool_call_id
            != previous_source.tool_call_id
            or previous_candidate_set.source_tool_call_id
            != previous_source.tool_call_id
            or previous_candidate_set.private_owner_scope_ref
            != self.owner_scope.customer_id
            or previous_candidate_set.conversation_id
            != conversation.conversation_id
            or previous_candidate_set.task_id != task.task_id
            or previous_candidate_set.request_unit_id != unit.request_unit_id
            or previous_candidate_set.query_binding_refs != (query.binding_ref,)
            or previous_candidate_set.result_task_state_version
            != task.state_version
            or query.accepted_task_state_version
            > previous_candidate_set.base_task_state_version
            or not (
                query.accepted_at
                <= previous_source.started_at
                <= previous_source.finished_at
                <= previous_observation.recorded_at
                <= self.trusted_read_at
            )
        ):
            raise ValueError("search current CandidateSet aggregate mismatch")
        validate_search_candidate_set_observation_closure(
            candidate_set=previous_candidate_set,
            observation=previous_observation,
        )
        if previous_candidate_set.outcome is OrderCandidateSetOutcome.UNIQUE:
            if task.status is not TaskStatus.ACTIVE or unit.open_questions:
                raise ValueError("current UNIQUE CandidateSet Task effect mismatch")
        elif (
            task.status is not TaskStatus.WAITING_USER
            or len(unit.open_questions) != 1
        ):
            raise ValueError("current MULTIPLE CandidateSet Task effect mismatch")
        return self

    def require_same_persisted_graph(
        self,
        current: OrderSearchCurrentReadClosure,
    ) -> None:
        """Fail when an atomic Port re-read differs from the loaded closure."""

        rebuilt = _require_exact_cycle2_model(
            current,
            OrderSearchCurrentReadClosure,
            field_name="current search read closure",
        )
        graph_fields = tuple(
            field_name
            for field_name in OrderSearchCurrentReadClosure.model_fields
            if field_name != "trusted_read_at"
        )
        if any(
            getattr(rebuilt, field_name) != getattr(self, field_name)
            for field_name in graph_fields
        ):
            raise ValueError("search persisted read fence mismatch")


def _require_disjoint_search_candidate_refs(
    *,
    previous: SearchOrdersObservation,
    current: SearchOrdersObservation,
) -> None:
    """Reject reuse of any Runtime-private candidate authority reference."""

    previous_candidate_refs = {
        candidate.observation_candidate_ref
        for candidate in previous.normalized_value.ordered_candidates
    }
    current_candidate_refs = {
        candidate.observation_candidate_ref
        for candidate in current.normalized_value.ordered_candidates
    }
    if previous_candidate_refs & current_candidate_refs:
        raise ValueError(
            "CandidateSet supersession requires disjoint candidate refs"
        )


class ApplyOrderSearchOutcomeV2Command(_StrictRuntimePrivateRecord):
    """Atomic Search Observation, CandidateSet and Task/RequestUnit effect."""

    owner_scope: TrustedOwnerScope
    loaded_read_closure: OrderSearchCurrentReadClosure
    trusted_conversation_record: ConversationRecord
    source_run_record: AgentRunRecordV2
    current_query_binding: AcceptedOrderSearchQueryBindingReadClosure
    expected_task_record: TaskRecord
    next_task_record: TaskRecord
    expected_request_unit_record: RequestUnitRecord
    next_request_unit_record: RequestUnitRecord
    source_tool_call_record: ToolCallRecordV2
    search_observation_record: SearchOrdersObservation
    candidate_set_record: OrderCandidateSetRecord
    previous_candidate_set_record: OrderCandidateSetRecord | None = None
    current_query_binding_refs: Annotated[
        tuple[UUID, ...],
        Field(min_length=1, max_length=1),
    ]
    pending_candidate_set_ref: UUID | None = None
    resolved_owner_scoped_order_target_ref: NonEmptyString | None = None

    @model_validator(mode="before")
    @classmethod
    def nested_records_are_exact(cls, value: object) -> object:
        return _require_exact_cycle2_inputs(
            value,
            model_fields={
                "owner_scope": TrustedOwnerScope,
                "loaded_read_closure": OrderSearchCurrentReadClosure,
                "trusted_conversation_record": ConversationRecord,
                "source_run_record": AgentRunRecordV2,
                "current_query_binding": (
                    AcceptedOrderSearchQueryBindingReadClosure
                ),
                "expected_task_record": TaskRecord,
                "next_task_record": TaskRecord,
                "expected_request_unit_record": RequestUnitRecord,
                "next_request_unit_record": RequestUnitRecord,
                "source_tool_call_record": ToolCallRecordV2,
                "search_observation_record": SearchOrdersObservation,
                "candidate_set_record": OrderCandidateSetRecord,
            },
            optional_model_fields={
                "previous_candidate_set_record": OrderCandidateSetRecord,
            },
        )

    @field_validator("current_query_binding_refs")
    @classmethod
    def query_refs_are_unique(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        if len(value) != len(set(value)):
            raise ValueError("current_query_binding_refs must be unique")
        return value

    @model_validator(mode="after")
    def aggregate_is_closed(self) -> Self:
        owner = self.owner_scope
        expected_task = self.expected_task_record
        expected_unit = self.expected_request_unit_record
        next_task = self.next_task_record
        next_unit = self.next_request_unit_record
        source = self.source_tool_call_record
        observation = self.search_observation_record
        candidate_set = self.candidate_set_record
        conversation = self.trusted_conversation_record
        run = self.source_run_record
        query_binding = self.current_query_binding
        loaded = self.loaded_read_closure

        if (
            loaded.owner_scope != owner
            or loaded.trusted_conversation_record != conversation
            or loaded.source_run_record != run
            or loaded.current_query_binding != query_binding
            or loaded.current_task_record != expected_task
            or loaded.current_request_unit_record != expected_unit
            or loaded.current_candidate_set_record
            != self.previous_candidate_set_record
        ):
            raise ValueError("search command/read closure mismatch")

        _task_and_request_unit_form_current_pair(
            owner_scope=owner,
            task_record=expected_task,
            request_unit_record=expected_unit,
        )
        if (
            expected_task.status is not TaskStatus.ACTIVE
            or expected_unit.open_questions
        ):
            raise ValueError("order search requires ACTIVE Task with no open question")
        if (
            conversation.owner_customer_id != owner.customer_id
            or candidate_set.conversation_id != conversation.conversation_id
            or run.conversation_id != conversation.conversation_id
            or run.status is not AgentRunStatusV2.RUNNING
            or run.started_at > observation.recorded_at
            or conversation.created_at > run.started_at
        ):
            raise ValueError("search outcome Conversation/Run closure mismatch")
        if (
            expected_unit.input_binding_refs != self.current_query_binding_refs
            or self.current_query_binding_refs != (query_binding.binding_ref,)
            or query_binding.private_owner_scope_ref != owner.customer_id
            or query_binding.conversation_id != conversation.conversation_id
            or query_binding.task_id != expected_task.task_id
            or query_binding.request_unit_id != expected_unit.request_unit_id
            or query_binding.current_task_state_version
            != expected_task.state_version
            or query_binding.accepted_at > observation.recorded_at
        ):
            raise ValueError("search current query InputBinding closure mismatch")
        if (
            source.status is not ToolCallStatus.SUCCEEDED
            or source.effect is not ToolEffect.READ
            or source.canonical_tool_name.value != "search_orders"
        ):
            raise ValueError("search outcome requires successful search_orders Read")
        if (
            not _owner_matches_private_scope(owner, source.private_owner_scope_ref)
            or not _owner_matches_private_scope(owner, observation.private_owner_scope)
            or not _owner_matches_private_scope(
                owner,
                candidate_set.private_owner_scope_ref,
            )
        ):
            raise ValueError("search outcome owner scope mismatch")
        if (
            source.task_id != expected_task.task_id
            or source.request_unit_id != expected_unit.request_unit_id
            or source.run_id != run.run_id
            or source.validated_task_state_version != expected_task.state_version
            or not (
                run.started_at
                <= query_binding.accepted_at
                <= loaded.trusted_read_at
                <= source.started_at
            )
            or source.finished_at is None
            or source.finished_at > observation.recorded_at
            or observation.source_tool_call_id != source.tool_call_id
            or candidate_set.source_tool_call_id != source.tool_call_id
            or candidate_set.task_id != expected_task.task_id
            or candidate_set.request_unit_id != expected_unit.request_unit_id
        ):
            raise ValueError("search outcome source graph mismatch")
        if candidate_set.base_task_state_version != expected_task.state_version:
            raise ValueError("CandidateSet base version must equal current Task version")
        if (
            len(source.argument_binding_refs) != 1
            or len(candidate_set.query_binding_refs) != 1
            or len(self.current_query_binding_refs) != 1
            or not (
                source.argument_binding_refs
                == candidate_set.query_binding_refs
                == self.current_query_binding_refs
                == (query_binding.binding_ref,)
            )
        ):
            raise ValueError("search ToolCall/query binding closure mismatch")
        validate_search_candidate_set_observation_closure(
            candidate_set=candidate_set,
            observation=observation,
        )
        _task_pair_advances_once(
            expected_task_record=expected_task,
            next_task_record=next_task,
            expected_request_unit_record=expected_unit,
            next_request_unit_record=next_unit,
            result_state_version=candidate_set.result_task_state_version,
            changed_at=observation.recorded_at,
            allowed_request_unit_delta_fields=frozenset(
                {"open_questions", "observation_refs"}
            ),
        )
        if next_unit.observation_refs != (
            *expected_unit.observation_refs,
            observation.observation_id,
        ):
            raise ValueError(
                "search outcome must append exactly its Search Observation ref"
            )

        previous = self.previous_candidate_set_record
        if candidate_set.supersedes_candidate_set_ref is None:
            if previous is not None:
                raise ValueError("unexpected previous CandidateSet without supersession")
        else:
            if previous is None:
                raise ValueError("CandidateSet supersession requires previous record")
            previous_source = loaded.current_candidate_source_tool_call_record
            previous_observation = loaded.current_search_observation_record
            if previous_source is None or previous_observation is None:
                raise ValueError("CandidateSet supersession requires current graph")
            if (
                previous_source.tool_call_id == source.tool_call_id
                or previous_observation.observation_id
                == candidate_set.search_observation_ref
            ):
                raise ValueError(
                    "CandidateSet supersession requires distinct Search outcomes"
                )
            _require_disjoint_search_candidate_refs(
                previous=previous_observation,
                current=observation,
            )
            from mini_agent.core.task_state import validate_candidate_set_supersession

            validate_candidate_set_supersession(
                current=candidate_set,
                previous=previous,
            )

        if candidate_set.outcome is OrderCandidateSetOutcome.MULTIPLE:
            if (
                self.pending_candidate_set_ref != candidate_set.candidate_set_id
                or self.resolved_owner_scoped_order_target_ref is not None
                or next_task.status is not TaskStatus.WAITING_USER
                or len(next_unit.open_questions) != 1
            ):
                raise ValueError(
                    "MULTIPLE search must atomically install pending clarification"
                )
        else:
            if (
                self.pending_candidate_set_ref is not None
                or next_task.status is not TaskStatus.ACTIVE
                or next_unit.open_questions
            ):
                raise ValueError("UNIQUE search cannot install pending clarification")
            if self.resolved_owner_scoped_order_target_ref is None:
                raise ValueError("UNIQUE search requires exact owner-scoped target")
            bindings = observation.candidate_target_bindings
            if (
                len(bindings) != 1
                or bindings[0].owner_scoped_order_ref
                != self.resolved_owner_scoped_order_target_ref
            ):
                raise ValueError("UNIQUE resolved target must match Observation mapping")
        return self


class AcceptedOrdinalBindingReadClosure(_StrictRuntimePrivateRecord):
    """Exact owner-reader projection of an already committed ordinal Claim."""

    binding_ref: UUID
    binding_name: Literal["candidate_ordinal"] = "candidate_ordinal"
    normalized_ordinal: Annotated[int, Field(ge=1)]
    authority: Literal[InputAuthority.USER_CLAIM] = InputAuthority.USER_CLAIM
    validation_status: Literal[InputValidationStatus.ACCEPTED] = (
        InputValidationStatus.ACCEPTED
    )
    private_owner_scope_ref: NonEmptyString
    conversation_id: UUID
    task_id: UUID
    request_unit_id: UUID
    task_state_version: PositiveStateVersion
    source_message_record: MessageRecord
    accepted_at: datetime
    superseded_by_binding_ref: Literal[None] = None

    @model_validator(mode="before")
    @classmethod
    def nested_record_is_exact(cls, value: object) -> object:
        return _require_exact_cycle2_inputs(
            value,
            model_fields={"source_message_record": MessageRecord},
        )

    @field_validator("accepted_at")
    @classmethod
    def accepted_at_is_utc(cls, value: datetime) -> datetime:
        return require_utc(value, field_name="accepted_at")

    @model_validator(mode="after")
    def source_is_one_saved_user_message(self) -> Self:
        message = self.source_message_record
        if (
            message.direction is not MessageDirection.USER
            or message.conversation_id != self.conversation_id
            or self.accepted_at < message.received_at
        ):
            raise ValueError("ordinal binding requires one exact saved USER Message")
        return self


class OrderCandidateSelectionReadClosure(_StrictRuntimePrivateRecord):
    """One owner-scoped exact current CandidateSet/Observation read closure."""

    owner_scope: TrustedOwnerScope
    trusted_conversation_record: ConversationRecord
    current_run_record: AgentRunRecordV2
    current_run_task_link_record: RunTaskLinkRecordV2
    current_task_record: TaskRecord
    current_request_unit_record: RequestUnitRecord
    current_candidate_set_record: OrderCandidateSetRecord
    search_observation_record: SearchOrdersObservation
    selection_request: OrderCandidateSelectionRequest
    saved_selection_message_record: MessageRecord
    current_query_binding: AcceptedOrderSearchQueryBindingReadClosure
    pending_candidate_set_ref: UUID
    current_query_binding_refs: Annotated[tuple[UUID, ...], Field(min_length=1)]
    resolved_owner_scoped_order_target_ref: NonEmptyString
    superseded_candidate_set_refs: tuple[UUID, ...] = ()
    existing_selection_records: tuple[OrderCandidateSelectionRecord, ...] = ()
    trusted_now: datetime

    @model_validator(mode="before")
    @classmethod
    def nested_records_are_exact(cls, value: object) -> object:
        return _require_exact_cycle2_inputs(
            value,
            model_fields={
                "owner_scope": TrustedOwnerScope,
                "trusted_conversation_record": ConversationRecord,
                "current_run_record": AgentRunRecordV2,
                "current_run_task_link_record": RunTaskLinkRecordV2,
                "current_task_record": TaskRecord,
                "current_request_unit_record": RequestUnitRecord,
                "current_candidate_set_record": OrderCandidateSetRecord,
                "search_observation_record": SearchOrdersObservation,
                "selection_request": OrderCandidateSelectionRequest,
                "saved_selection_message_record": MessageRecord,
                "current_query_binding": (
                    AcceptedOrderSearchQueryBindingReadClosure
                ),
            },
            tuple_model_fields={
                "existing_selection_records": OrderCandidateSelectionRecord,
            },
        )

    @field_validator("trusted_now")
    @classmethod
    def trusted_now_is_utc(cls, value: datetime) -> datetime:
        return require_utc(value, field_name="trusted_now")

    @model_validator(mode="after")
    def current_selection_graph_is_exact(self) -> Self:
        task = self.current_task_record
        unit = self.current_request_unit_record
        candidate_set = self.current_candidate_set_record
        conversation = self.trusted_conversation_record
        run = self.current_run_record
        run_link = self.current_run_task_link_record
        message = self.saved_selection_message_record
        query_binding = self.current_query_binding
        _task_and_request_unit_form_current_pair(
            owner_scope=self.owner_scope,
            task_record=task,
            request_unit_record=unit,
        )
        if task.status is not TaskStatus.WAITING_USER:
            raise ValueError("ordinal selection requires WAITING_USER Task")
        if (
            conversation.owner_customer_id != self.owner_scope.customer_id
            or candidate_set.conversation_id != conversation.conversation_id
            or run.conversation_id != conversation.conversation_id
            or run.status is not AgentRunStatusV2.RUNNING
            or run_link.run_id != run.run_id
            or run_link.task_id != task.task_id
            or run_link.base_task_state_version != task.state_version
            or run_link.result_task_state_version is not None
            or run.started_at > self.trusted_now
            or conversation.created_at > run.started_at
        ):
            raise ValueError("ordinal selection Conversation/Run closure mismatch")
        request = self.selection_request
        if (
            message.message_id != request.source_message_ref
            or message.direction is not MessageDirection.USER
            or message.conversation_id != conversation.conversation_id
            or message.received_at < candidate_set.created_at
            or message.received_at > run.started_at
            or message.received_at > self.trusted_now
            or request.ordinal_input_binding_ref in unit.input_binding_refs
            or request.ordinal_input_binding_ref in self.current_query_binding_refs
        ):
            raise ValueError("selection Message or pre-CAS ordinal ref mismatch")
        if (
            len(self.current_query_binding_refs) != 1
            or self.current_query_binding_refs
            != candidate_set.query_binding_refs
            or self.current_query_binding_refs != (query_binding.binding_ref,)
            or not set(self.current_query_binding_refs).issubset(
                unit.input_binding_refs
            )
            or query_binding.private_owner_scope_ref
            != self.owner_scope.customer_id
            or query_binding.conversation_id != conversation.conversation_id
            or query_binding.task_id != task.task_id
            or query_binding.request_unit_id != unit.request_unit_id
            or query_binding.accepted_task_state_version
            > candidate_set.base_task_state_version
            or query_binding.current_task_state_version != task.state_version
            or query_binding.accepted_at > candidate_set.created_at
            or query_binding.accepted_at > self.trusted_now
        ):
            raise ValueError("current query InputBinding closure mismatch")
        if len(self.superseded_candidate_set_refs) != len(
            set(self.superseded_candidate_set_refs)
        ):
            raise ValueError("superseded CandidateSet refs must be unique")
        for existing in self.existing_selection_records:
            matching_entries = tuple(
                entry
                for entry in candidate_set.ordered_candidates
                if entry.observation_candidate_ref
                == existing.observation_candidate_ref
                and entry.candidate_source_version
                == existing.candidate_source_version
            )
            matching_targets = tuple(
                target
                for target in self.search_observation_record.candidate_target_bindings
                if target.observation_candidate_ref
                == existing.observation_candidate_ref
                and target.candidate_source_version
                == existing.candidate_source_version
            )
            if (
                existing.private_owner_scope_ref != self.owner_scope.customer_id
                or existing.conversation_id != conversation.conversation_id
                or existing.task_id != task.task_id
                or existing.request_unit_id != unit.request_unit_id
                or existing.candidate_set_ref != candidate_set.candidate_set_id
                or existing.candidate_set_version != candidate_set.candidate_set_version
                or existing.search_observation_ref
                != self.search_observation_record.observation_id
                or existing.search_observation_record_schema_version
                != self.search_observation_record.record_schema_version
                or existing.base_task_state_version != task.state_version
                or existing.result_task_state_version != task.state_version + 1
                or existing.source_message_ref
                != message.message_id
                or existing.ordinal_input_binding_ref
                != request.ordinal_input_binding_ref
                or existing.selected_at < candidate_set.created_at
                or existing.selected_at >= candidate_set.valid_until
                or existing.selected_at > self.trusted_now
                or len(matching_entries) != 1
                or len(matching_targets) != 1
                or matching_targets[0].owner_scoped_order_ref
                != existing.owner_scoped_order_target_ref
                or not _is_canonical_uuid_text(existing.selected_target_ref)
                or existing.selected_target_ref
                == existing.owner_scoped_order_target_ref
            ):
                raise ValueError("existing selection record graph mismatch")
        validate_candidate_selection_closure(
            current_candidate_sets=(candidate_set,),
            observation=self.search_observation_record,
            request=self.selection_request,
            trusted_owner_scope_ref=self.owner_scope.customer_id,
            conversation_id=conversation.conversation_id,
            task_id=task.task_id,
            request_unit_id=unit.request_unit_id,
            pending_candidate_set_ref=self.pending_candidate_set_ref,
            current_task_state_version=task.state_version,
            current_query_binding_refs=self.current_query_binding_refs,
            trusted_now=self.trusted_now,
            resolved_owner_scoped_order_target_ref=(
                self.resolved_owner_scoped_order_target_ref
            ),
            superseded_candidate_set_refs=self.superseded_candidate_set_refs,
            existing_selection_records=self.existing_selection_records,
        )
        if self.existing_selection_records:
            raise ValueError("current CandidateSet capability is already consumed")
        return self

    @property
    def conversation_id(self) -> UUID:
        return self.trusted_conversation_record.conversation_id


class IssuedSelectedTargetRef(_StrictRuntimePrivateRecord):
    """One Application-issued UUID capability for one selection command."""

    selected_target_ref: UUID

    @model_validator(mode="before")
    @classmethod
    def target_is_issued_in_process(
        cls,
        value: object,
        info: ValidationInfo,
    ) -> object:
        if not _issued_selected_target_context_is_live(info.context):
            raise ValueError(
                "IssuedSelectedTargetRef must be created by fresh()"
            )
        return value

    @field_validator("selected_target_ref")
    @classmethod
    def target_is_uuid4(cls, value: UUID) -> UUID:
        if value.version != 4:
            raise ValueError("issued selected target must be UUIDv4")
        return value

    @classmethod
    def fresh(cls) -> Self:
        """Generate a fresh target internally; callers cannot supply entropy."""

        return _issue_selected_target_ref()


class ApplyOrderCandidateSelectionV2Command(_StrictRuntimePrivateRecord):
    """CAS one exact ordinal selection and its Task/RequestUnit effect."""

    loaded_closure: OrderCandidateSelectionReadClosure
    ordinal_input_binding_record: InputBindingV2
    issued_selected_target: IssuedSelectedTargetRef
    next_task_record: TaskRecord
    next_request_unit_record: RequestUnitRecord
    selection_record: OrderCandidateSelectionRecord
    closed_pending_candidate_set_ref: UUID

    def require_live_target_issuance(self) -> None:
        """Reject a command not returned by the live Application factory."""

        _require_live_order_candidate_selection_v2_command(self)

    @property
    def selected_target_ref(self) -> UUID:
        return self.issued_selected_target.selected_target_ref

    @model_validator(mode="before")
    @classmethod
    def nested_records_are_exact(
        cls,
        value: object,
        info: ValidationInfo,
    ) -> object:
        if not _order_selection_command_context_is_live(info.context):
            raise ValueError(
                "selection command must be created by the Application factory"
            )
        if not isinstance(value, Mapping):
            raise ValueError("selection command requires a mapping")
        issued_target = value.get("issued_selected_target")
        if type(issued_target) is not IssuedSelectedTargetRef:
            raise ValueError(
                "issued_selected_target must be an exact live issuance"
            )
        canonical = dict(value)
        for field_name, expected_type in {
            "loaded_closure": OrderCandidateSelectionReadClosure,
            "ordinal_input_binding_record": InputBindingV2,
            "next_task_record": TaskRecord,
            "next_request_unit_record": RequestUnitRecord,
            "selection_record": OrderCandidateSelectionRecord,
        }.items():
            canonical[field_name] = _require_exact_cycle2_model(
                value.get(field_name),
                expected_type,
                field_name=field_name,
            )
        canonical["issued_selected_target"] = issued_target
        return canonical

    @model_validator(mode="after")
    def selection_effect_is_exact(self, info: ValidationInfo) -> Self:
        closure = self.loaded_closure
        current_task = closure.current_task_record
        current_unit = closure.current_request_unit_record
        candidate_set = closure.current_candidate_set_record
        observation = closure.search_observation_record
        request = closure.selection_request
        ordinal_binding = self.ordinal_input_binding_record
        selection = self.selection_record

        decision = validate_candidate_selection_closure(
            current_candidate_sets=(candidate_set,),
            observation=observation,
            request=request,
            trusted_owner_scope_ref=closure.owner_scope.customer_id,
            conversation_id=closure.conversation_id,
            task_id=current_task.task_id,
            request_unit_id=current_unit.request_unit_id,
            pending_candidate_set_ref=closure.pending_candidate_set_ref,
            current_task_state_version=current_task.state_version,
            current_query_binding_refs=closure.current_query_binding_refs,
            trusted_now=closure.trusted_now,
            resolved_owner_scoped_order_target_ref=(
                closure.resolved_owner_scoped_order_target_ref
            ),
            superseded_candidate_set_refs=closure.superseded_candidate_set_refs,
            existing_selection_records=closure.existing_selection_records,
        )
        exact_values = {
            "private_owner_scope_ref": closure.owner_scope.customer_id,
            "conversation_id": closure.conversation_id,
            "task_id": current_task.task_id,
            "request_unit_id": current_unit.request_unit_id,
            "source_message_ref": request.source_message_ref,
            "ordinal_input_binding_ref": request.ordinal_input_binding_ref,
            "candidate_set_ref": candidate_set.candidate_set_id,
            "candidate_set_version": candidate_set.candidate_set_version,
            "search_observation_ref": observation.observation_id,
            "search_observation_record_schema_version": (
                observation.record_schema_version
            ),
            "observation_candidate_ref": decision.observation_candidate_ref,
            "candidate_source_version": decision.candidate_source_version,
            "owner_scoped_order_target_ref": (
                closure.resolved_owner_scoped_order_target_ref
            ),
            "selected_target_ref": str(self.selected_target_ref),
            "base_task_state_version": current_task.state_version,
        }
        if any(
            getattr(selection, field_name) != expected_value
            for field_name, expected_value in exact_values.items()
        ):
            raise ValueError("SelectionRecord does not match exact loaded closure")
        if self.closed_pending_candidate_set_ref != candidate_set.candidate_set_id:
            raise ValueError("selection must close the exact pending CandidateSet")
        if selection.selected_at != closure.trusted_now:
            raise ValueError("selection timestamp must equal trusted transaction time")
        if (
            self.selected_target_ref.version != 4
            or not _is_canonical_uuid_text(selection.selected_target_ref)
            or selection.selected_target_ref
            == closure.resolved_owner_scoped_order_target_ref
            or self.selected_target_ref
            in {
                request.ordinal_input_binding_ref,
                request.source_message_ref,
                candidate_set.candidate_set_id,
                observation.observation_id,
                decision.observation_candidate_ref,
                selection.selection_id,
                current_task.task_id,
                current_unit.request_unit_id,
            }
        ):
            raise ValueError(
                "selected target must be a fresh independent canonical UUID"
            )
        if (
            ordinal_binding.binding_id != request.ordinal_input_binding_ref
            or ordinal_binding.name != "candidate_ordinal"
            or type(ordinal_binding.normalized_value) is not int
            or ordinal_binding.normalized_value != request.ordinal
            or ordinal_binding.source_refs
            != (closure.saved_selection_message_record.message_id,)
            or ordinal_binding.created_at != closure.trusted_now
            or ordinal_binding.updated_at != closure.trusted_now
            or ordinal_binding.supersedes is not None
            or ordinal_binding.binding_id in current_unit.input_binding_refs
        ):
            raise ValueError(
                "selection must create one exact new ordinal InputBindingV2"
            )
        expected_next_refs = (
            *current_unit.input_binding_refs,
            ordinal_binding.binding_id,
        )
        if self.next_request_unit_record.input_binding_refs != expected_next_refs:
            raise ValueError("selection must append exactly the ordinal binding ref")
        _task_pair_advances_once(
            expected_task_record=current_task,
            next_task_record=self.next_task_record,
            expected_request_unit_record=current_unit,
            next_request_unit_record=self.next_request_unit_record,
            result_state_version=selection.result_task_state_version,
            changed_at=selection.selected_at,
            allowed_request_unit_delta_fields=frozenset(
                {"input_binding_refs", "open_questions"}
            ),
        )
        if self.next_task_record.status is not TaskStatus.ACTIVE:
            raise ValueError("successful selection must reactivate Task")
        if (
            len(current_unit.open_questions) != 1
            or self.next_request_unit_record.open_questions
        ):
            raise ValueError("successful selection must close pending question")
        if not _order_selection_command_context_is_live(info.context, self):
            raise ValueError(
                "selection command must retain its Application factory context"
            )
        _bind_issued_selected_target_to_command(
            self.issued_selected_target,
            self,
        )
        return self


def _build_order_selection_target_issuer() -> tuple[Any, ...]:
    """Keep UUID issuance, factory tokens, and provenance state in closure."""

    generate_uuid4 = uuid4
    issue_factory_token = object()
    command_factory_token = object()
    active_command_contexts: dict[int, object] = {}
    active_command_candidates: dict[
        int,
        tuple[
            weakref.ReferenceType[ApplyOrderCandidateSelectionV2Command],
            int,
        ],
    ] = {}
    issue_registry: dict[
        int,
        tuple[
            weakref.ReferenceType[IssuedSelectedTargetRef],
            UUID,
            weakref.ReferenceType[ApplyOrderCandidateSelectionV2Command]
            | None,
            str | None,
        ],
    ] = {}

    def issue_context_is_live(context: object) -> bool:
        return (
            type(context) is dict
            and context.get("issued_selected_target_factory_context")
            is issue_factory_token
        )

    def command_context_is_live(
        context: object,
        candidate: object | None = None,
    ) -> bool:
        context_is_live = (
            type(context) is dict
            and active_command_contexts.get(id(context)) is context
            and context.get("order_selection_command_factory_context")
            is command_factory_token
        )
        if not context_is_live:
            return False
        if candidate is None:
            return True
        if type(candidate) is not ApplyOrderCandidateSelectionV2Command:
            return False
        active_command_candidates[id(candidate)] = (
            weakref.ref(candidate),
            id(context),
        )
        return True

    def issue_selected_target_ref() -> IssuedSelectedTargetRef:
        issued_target = IssuedSelectedTargetRef.model_validate(
            {"selected_target_ref": generate_uuid4()},
            strict=True,
            context={
                "issued_selected_target_factory_context": issue_factory_token
            },
        )
        issued_id = id(issued_target)

        def discard_if_same(
            expired: weakref.ReferenceType[IssuedSelectedTargetRef],
            *,
            registered_id: int = issued_id,
        ) -> None:
            registered = issue_registry.get(registered_id)
            if registered is not None and registered[0] is expired:
                issue_registry.pop(registered_id, None)

        issue_registry[issued_id] = (
            weakref.ref(issued_target, discard_if_same),
            issued_target.selected_target_ref,
            None,
            None,
        )
        return issued_target

    def bind_issued_target_to_command(
        issued_target: IssuedSelectedTargetRef,
        command: ApplyOrderCandidateSelectionV2Command,
    ) -> None:
        registered = issue_registry.get(id(issued_target))
        candidate = active_command_candidates.pop(id(command), None)
        if (
            candidate is None
            or candidate[0]() is not command
            or active_command_contexts.get(candidate[1]) is None
            or type(issued_target) is not IssuedSelectedTargetRef
            or type(command) is not ApplyOrderCandidateSelectionV2Command
            or registered is None
            or registered[0]() is not issued_target
            or registered[1] != issued_target.selected_target_ref
            or registered[2] is not None
            or registered[3] is not None
        ):
            raise ValueError(
                "selected target requires one fresh Application issuance"
            )
        issue_registry[id(issued_target)] = (
            registered[0],
            registered[1],
            weakref.ref(command),
            command.model_dump_json(),
        )

    def require_live_command(
        command: ApplyOrderCandidateSelectionV2Command,
    ) -> None:
        if type(command) is not ApplyOrderCandidateSelectionV2Command:
            raise ValueError(
                "selection command lacks fresh Application target issuance"
            )
        issued_target = command.issued_selected_target
        registered = issue_registry.get(id(issued_target))
        if (
            type(issued_target) is not IssuedSelectedTargetRef
            or registered is None
            or registered[0]() is not issued_target
            or registered[1] != issued_target.selected_target_ref
            or registered[2] is None
            or registered[2]() is not command
            or registered[3] != command.model_dump_json()
        ):
            raise ValueError(
                "selection command lacks fresh Application target issuance"
            )

    def build_command(
        *,
        loaded_closure: OrderCandidateSelectionReadClosure,
        ordinal_input_binding_record: InputBindingV2,
        issued_selected_target: IssuedSelectedTargetRef,
        next_task_record: TaskRecord,
        next_request_unit_record: RequestUnitRecord,
        selection_record: OrderCandidateSelectionRecord,
        closed_pending_candidate_set_ref: UUID,
    ) -> ApplyOrderCandidateSelectionV2Command:
        """Bind one fresh Application target to one exact selection command."""

        context = {
            "order_selection_command_factory_context": command_factory_token
        }
        context_id = id(context)
        active_command_contexts[context_id] = context
        try:
            return ApplyOrderCandidateSelectionV2Command.model_validate(
                {
                    "loaded_closure": loaded_closure,
                    "ordinal_input_binding_record": (
                        ordinal_input_binding_record
                    ),
                    "issued_selected_target": issued_selected_target,
                    "next_task_record": next_task_record,
                    "next_request_unit_record": next_request_unit_record,
                    "selection_record": selection_record,
                    "closed_pending_candidate_set_ref": (
                        closed_pending_candidate_set_ref
                    ),
                },
                strict=True,
                context=context,
            )
        finally:
            if active_command_contexts.get(context_id) is context:
                active_command_contexts.pop(context_id, None)

    return (
        issue_selected_target_ref,
        issue_context_is_live,
        command_context_is_live,
        bind_issued_target_to_command,
        require_live_command,
        build_command,
    )


(
    _issue_selected_target_ref,
    _issued_selected_target_context_is_live,
    _order_selection_command_context_is_live,
    _bind_issued_selected_target_to_command,
    _require_live_order_candidate_selection_v2_command,
    build_order_candidate_selection_v2_command,
) = _build_order_selection_target_issuer()
del _build_order_selection_target_issuer


class InitialToolCallV2ReadClosure(_StrictRuntimePrivateRecord):
    """Exact current owner/Task/RequestUnit/InputBinding snapshot for insert."""

    owner_scope: TrustedOwnerScope
    current_task_record: TaskRecord
    current_request_unit_record: RequestUnitRecord
    current_input_binding_records: Annotated[
        tuple[InputBindingV2, ...],
        Field(min_length=1),
    ]
    trusted_read_at: datetime

    @model_validator(mode="before")
    @classmethod
    def nested_records_are_exact(cls, value: object) -> object:
        return _require_exact_cycle2_inputs(
            value,
            model_fields={
                "owner_scope": TrustedOwnerScope,
                "current_task_record": TaskRecord,
                "current_request_unit_record": RequestUnitRecord,
            },
            tuple_model_fields={
                "current_input_binding_records": InputBindingV2,
            },
        )

    @field_validator("trusted_read_at")
    @classmethod
    def trusted_read_at_is_utc(cls, value: datetime) -> datetime:
        return require_utc(value, field_name="trusted_read_at")

    @model_validator(mode="after")
    def current_graph_is_exact(self) -> Self:
        _task_and_request_unit_form_current_pair(
            owner_scope=self.owner_scope,
            task_record=self.current_task_record,
            request_unit_record=self.current_request_unit_record,
        )
        if (
            self.current_task_record.updated_at > self.trusted_read_at
            or self.current_request_unit_record.updated_at > self.trusted_read_at
        ):
            raise ValueError("initial ToolCall read cannot precede current state")
        _require_complete_current_input_bindings_v2(
            request_unit=self.current_request_unit_record,
            bindings=self.current_input_binding_records,
            trusted_now=self.trusted_read_at,
        )
        return self


class CreateToolCallV2Command(_StrictRuntimePrivateRecord):
    """Conditionally insert one clean CREATED v2 ToolCall authorization graph."""

    loaded_closure: InitialToolCallV2ReadClosure
    gateway_candidate: Cycle2GatewayCandidate
    gate_decision: GateDecisionV2
    authorized_tool_command: AuthorizedToolCommandV2
    created_record: ToolCallRecordV2

    @model_validator(mode="before")
    @classmethod
    def nested_records_are_exact_and_gate_is_live(
        cls,
        value: object,
    ) -> object:
        if not isinstance(value, Mapping):
            raise ValueError("initial ToolCall v2 contract requires a mapping")
        gate = value.get("gate_decision")
        if type(gate) is not GateDecisionV2:
            raise ValueError("gate_decision must be an exact live GateDecisionV2")
        canonical = dict(value)
        for field_name, expected_type in {
            "loaded_closure": InitialToolCallV2ReadClosure,
            "gateway_candidate": Cycle2GatewayCandidate,
            "authorized_tool_command": AuthorizedToolCommandV2,
            "created_record": ToolCallRecordV2,
        }.items():
            canonical[field_name] = _require_exact_cycle2_model(
                value.get(field_name),
                expected_type,
                field_name=field_name,
            )
        canonical["gate_decision"] = gate
        return canonical

    @model_validator(mode="after")
    def initial_tool_call_graph_is_exact(self) -> Self:
        closure = self.loaded_closure
        task = closure.current_task_record
        unit = closure.current_request_unit_record
        candidate = self.gateway_candidate
        gate = self.gate_decision
        authorized = self.authorized_tool_command
        created = self.created_record
        try:
            reproved = build_cycle2_authorized_tool_command(
                gate_decision=gate,
                candidate=candidate,
                registry_snapshot_ref=authorized.registry_snapshot_ref,
                trusted_context_ref=authorized.trusted_context_ref,
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "initial ToolCall requires live public Gateway authorization"
            ) from exc
        if (
            type(reproved) is not AuthorizedToolCommandV2
            or reproved.model_dump() != authorized.model_dump()
        ):
            raise ValueError("authorized Tool command does not match sealed Gate")

        binding_ids = tuple(
            binding.binding_id for binding in closure.current_input_binding_records
        )
        if (
            len(authorized.argument_binding_refs)
            != len(set(authorized.argument_binding_refs))
            or not set(authorized.argument_binding_refs).issubset(binding_ids)
            or authorized.verified_target_ref in authorized.argument_binding_refs
        ):
            raise ValueError("Tool authorization refs do not resolve in current bindings")
        exact_fields = {
            "run_id": candidate.run_id,
            "task_id": task.task_id,
            "request_unit_id": unit.request_unit_id,
            "model_call_id": gate.model_call_id,
            "context_manifest_id": gate.context_manifest_id,
            "gate_decision_id": gate.gate_decision_id,
            "provider_tool_call_id": gate.provider_tool_call_id,
            "canonical_tool_name": authorized.canonical_tool_name,
            "private_owner_scope_ref": closure.owner_scope.customer_id,
            "validated_task_state_version": task.state_version,
            "argument_binding_refs": authorized.argument_binding_refs,
            "verified_target_ref": authorized.verified_target_ref,
        }
        if any(
            getattr(created, field_name) != expected
            for field_name, expected in exact_fields.items()
        ):
            raise ValueError("ToolCallRecordV2 does not close the authorization graph")
        if (
            candidate.task_id != task.task_id
            or candidate.request_unit_id != unit.request_unit_id
            or candidate.validated_task_state_version != task.state_version
            or gate.validated_task_state_version != task.state_version
            or candidate.argument_binding_refs != authorized.argument_binding_refs
            or candidate.verified_target_ref != authorized.verified_target_ref
            or authorized.registry_snapshot_ref
            != created.tool_registry_version
        ):
            raise ValueError("Gateway candidate is stale or belongs to another state")
        if (
            created.status is not ToolCallStatus.CREATED
            or created.effect is not ToolEffect.READ
            or created.attempt_count != 0
            or created.attempts
            or created.started_at != closure.trusted_read_at
            or gate.decided_at > created.started_at
            or any(
                value is not None
                for value in (
                    created.finished_at,
                    created.failure_code,
                    created.timeout_phase,
                    created.interruption_reason,
                    created.result_ref,
                    created.recovery_disposition,
                    created.recovery_decision_ref,
                )
            )
        ):
            raise ValueError("initial ToolCallV2 must be a clean CREATED projection")
        return self


_CYCLE2_TOOL_STABLE_FIELDS = (
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
    "private_owner_scope_ref",
    "validated_task_state_version",
    "argument_binding_refs",
    "verified_target_ref",
    "effect",
    "started_at",
)


def _cycle2_tool_stable_fields_match(
    current: ToolCallRecordV2,
    next_record: ToolCallRecordV2,
) -> bool:
    return all(
        getattr(current, field_name) == getattr(next_record, field_name)
        for field_name in _CYCLE2_TOOL_STABLE_FIELDS
    )


class AppendToolAttemptV2Command(_StrictRuntimePrivateRecord):
    """CAS-append one unfinished contiguous attempt before dispatch."""

    owner_scope: TrustedOwnerScope
    expected_record: ToolCallRecordV2
    next_running_record: ToolCallRecordV2
    started_attempt: ToolAttemptRecordV2

    @model_validator(mode="before")
    @classmethod
    def nested_records_are_exact(cls, value: object) -> object:
        return _require_exact_cycle2_inputs(
            value,
            model_fields={
                "owner_scope": TrustedOwnerScope,
                "expected_record": ToolCallRecordV2,
                "next_running_record": ToolCallRecordV2,
                "started_attempt": ToolAttemptRecordV2,
            },
        )

    @model_validator(mode="after")
    def attempt_append_is_exact(self) -> Self:
        expected = self.expected_record
        next_record = self.next_running_record
        attempt = self.started_attempt
        if not _owner_matches_private_scope(
            self.owner_scope,
            expected.private_owner_scope_ref,
        ) or not _owner_matches_private_scope(
            self.owner_scope,
            next_record.private_owner_scope_ref,
        ):
            raise ValueError("attempt append owner scope mismatch")
        if expected.status not in {ToolCallStatus.CREATED, ToolCallStatus.RUNNING}:
            raise ValueError("attempt append requires active ToolCall")
        if next_record.status is not ToolCallStatus.RUNNING:
            raise ValueError("attempt append must produce RUNNING ToolCall")
        if not _cycle2_tool_stable_fields_match(expected, next_record):
            raise ValueError("attempt append cannot change parent stable fields")
        if attempt.tool_call_id != expected.tool_call_id:
            raise ValueError("attempt child ToolCall identity mismatch")
        if (
            attempt.finished_at is not None
            or attempt.outcome is not None
            or attempt.failure_code is not None
            or attempt.timeout_phase is not None
            or attempt.retry_decision is not None
        ):
            raise ValueError("dispatch fence requires an unfinished attempt")
        if attempt.attempt_no != expected.attempt_count + 1:
            raise ValueError("attempt append must be next contiguous attempt")
        if next_record.attempts != (*expected.attempts, attempt):
            raise ValueError("attempt append must preserve all prior attempt evidence")
        if next_record.attempt_count != expected.attempt_count + 1:
            raise ValueError("attempt count must advance exactly once")
        if expected.attempt_count == 0:
            if expected.status is not ToolCallStatus.CREATED:
                raise ValueError("first attempt fence requires CREATED ToolCall")
        else:
            last = expected.attempts[-1]
            if (
                expected.status is not ToolCallStatus.RUNNING
                or last.finished_at is None
                or last.retry_decision is not ToolRetryDecision.RETRY_SCHEDULED
            ):
                raise ValueError("retry fence requires finalized RETRY_SCHEDULED")
        return self


class FinalizeToolAttemptV2Command(_StrictRuntimePrivateRecord):
    """CAS-finalize the exact unfinished child and matching parent projection."""

    owner_scope: TrustedOwnerScope
    expected_running_record: ToolCallRecordV2
    finalized_attempt: ToolAttemptRecordV2
    next_record: ToolCallRecordV2

    @model_validator(mode="before")
    @classmethod
    def nested_records_are_exact(cls, value: object) -> object:
        return _require_exact_cycle2_inputs(
            value,
            model_fields={
                "owner_scope": TrustedOwnerScope,
                "expected_running_record": ToolCallRecordV2,
                "finalized_attempt": ToolAttemptRecordV2,
                "next_record": ToolCallRecordV2,
            },
        )

    @model_validator(mode="after")
    def attempt_finalization_is_exact(self) -> Self:
        expected = self.expected_running_record
        finalized = self.finalized_attempt
        next_record = self.next_record
        if expected.status is not ToolCallStatus.RUNNING or not expected.attempts:
            raise ValueError("attempt finalization requires RUNNING ToolCall")
        if not _owner_matches_private_scope(
            self.owner_scope,
            expected.private_owner_scope_ref,
        ) or not _owner_matches_private_scope(
            self.owner_scope,
            next_record.private_owner_scope_ref,
        ):
            raise ValueError("attempt finalization owner scope mismatch")
        if not _cycle2_tool_stable_fields_match(expected, next_record):
            raise ValueError("attempt finalization cannot change stable parent fields")
        started = expected.attempts[-1]
        if started.finished_at is not None:
            raise ValueError("expected last attempt must remain unfinished")
        if (
            finalized.tool_call_id != started.tool_call_id
            or finalized.attempt_no != started.attempt_no
            or finalized.started_at != started.started_at
            or finalized.finished_at is None
            or finalized.outcome is None
            or finalized.retry_decision is None
        ):
            raise ValueError("finalized attempt must close exact started attempt")
        if next_record.attempts != (*expected.attempts[:-1], finalized):
            raise ValueError("finalization must replace only the unfinished attempt")
        if next_record.attempt_count != expected.attempt_count:
            raise ValueError("finalization cannot change attempt count")
        if finalized.retry_decision is ToolRetryDecision.RETRY_SCHEDULED:
            if next_record.status is not ToolCallStatus.RUNNING:
                raise ValueError("scheduled retry keeps ToolCall RUNNING")
        elif next_record.status is ToolCallStatus.RUNNING:
            raise ValueError("non-retry finalization requires terminal parent")
        return self


class Cycle2RunBudgetPolicyEvidence(_StrictRuntimePrivateRecord):
    """Versioned trusted configuration used to derive recovery Run budget."""

    policy_version: NonEmptyString
    run_time_budget_ms: Annotated[int, Field(strict=True, ge=1)]


class ToolRetryRecoveryDecisionRecordV2(_StrictAuditOnlyRecord):
    """Minimal audit-only logical child of one Cycle 2 ToolCall."""

    recovery_decision_id: UUID
    tool_call_id: UUID
    last_attempt_no: Annotated[int, Field(strict=True, ge=1, le=2)]
    decision: ToolRecoveryDecision
    stable_reason_code: SafeReasonCode
    candidate_next_attempt_no: Literal[2] | None = None
    decided_at: datetime

    @field_validator("decided_at")
    @classmethod
    def decided_at_is_utc(cls, value: datetime) -> datetime:
        return require_utc(value, field_name="recovery decision decided_at")

    @model_validator(mode="after")
    def decision_shape_is_closed(self) -> Self:
        exact_shapes = {
            ToolRecoveryDecision.APPEND_SECOND_ATTEMPT: (
                "RETRY_REVALIDATED_CAS_REQUIRED",
                2,
            ),
            ToolRecoveryDecision.INTERRUPT_UNFINISHED_ATTEMPT: (
                "UNFINISHED_ATTEMPT_OUTCOME_UNKNOWN",
                None,
            ),
            ToolRecoveryDecision.TERMINATE_RETRY_PATH: (None, None),
        }
        if self.decision not in exact_shapes:
            raise ValueError("decision child does not contain an approved recovery")
        expected_reason, expected_next = exact_shapes[self.decision]
        if self.decision is ToolRecoveryDecision.TERMINATE_RETRY_PATH:
            if self.stable_reason_code not in {
                "RUN_BUDGET_EXHAUSTED",
                "STATE_OR_BINDING_INVALIDATED",
            }:
                raise ValueError("terminal decision child has an unknown reason")
        elif self.stable_reason_code != expected_reason:
            raise ValueError("decision child reason contradicts Core decision")
        if self.candidate_next_attempt_no != expected_next:
            raise ValueError("decision child next attempt contradicts Core decision")
        if (
            self.decision
            in {
                ToolRecoveryDecision.APPEND_SECOND_ATTEMPT,
                ToolRecoveryDecision.TERMINATE_RETRY_PATH,
            }
            and self.last_attempt_no != 1
        ):
            raise ValueError("retry recovery decision must bind attempt 1")
        return self


class ToolRetryRecoveryReadClosureV2(_StrictRuntimePrivateRecord):
    """Exact owner/current graph with trusted time and versioned budget policy."""

    owner_scope: TrustedOwnerScope
    active_run_record: AgentRunRecordV2
    active_run_task_link_record: RunTaskLinkRecordV2
    current_task_record: TaskRecord
    current_request_unit_record: RequestUnitRecord
    current_input_binding_records: Annotated[
        tuple[InputBindingV2, ...],
        Field(min_length=1),
    ]
    tool_call_record: ToolCallRecordV2
    recovery_decision_records: Annotated[
        tuple[ToolRetryRecoveryDecisionRecordV2, ...],
        Field(max_length=1),
    ]
    trusted_read_at: datetime
    run_budget_policy: Cycle2RunBudgetPolicyEvidence

    @model_validator(mode="before")
    @classmethod
    def nested_records_are_exact(cls, value: object) -> object:
        return _require_exact_cycle2_inputs(
            value,
            model_fields={
                "owner_scope": TrustedOwnerScope,
                "active_run_record": AgentRunRecordV2,
                "active_run_task_link_record": RunTaskLinkRecordV2,
                "current_task_record": TaskRecord,
                "current_request_unit_record": RequestUnitRecord,
                "tool_call_record": ToolCallRecordV2,
                "run_budget_policy": Cycle2RunBudgetPolicyEvidence,
            },
            tuple_model_fields={
                "current_input_binding_records": InputBindingV2,
                "recovery_decision_records": ToolRetryRecoveryDecisionRecordV2,
            },
        )

    @field_validator("trusted_read_at")
    @classmethod
    def trusted_read_at_is_utc(cls, value: datetime) -> datetime:
        return require_utc(value, field_name="recovery trusted_read_at")

    @model_validator(mode="after")
    def recovery_graph_is_exact(self) -> Self:
        run = self.active_run_record
        link = self.active_run_task_link_record
        task = self.current_task_record
        unit = self.current_request_unit_record
        tool_call = self.tool_call_record
        _task_and_request_unit_form_current_pair(
            owner_scope=self.owner_scope,
            task_record=task,
            request_unit_record=unit,
        )
        _require_complete_current_input_bindings_v2(
            request_unit=unit,
            bindings=self.current_input_binding_records,
            trusted_now=self.trusted_read_at,
        )
        if run.status is not AgentRunStatusV2.RUNNING:
            raise ValueError("recovery requires the exact active RUNNING Run")
        if (
            link.run_id != run.run_id
            or link.task_id != task.task_id
            or link.base_task_state_version
            != tool_call.validated_task_state_version
            or link.result_task_state_version is not None
        ):
            raise ValueError("recovery RunTaskLink does not match active Tool state")
        if (
            not _owner_matches_private_scope(
                self.owner_scope,
                tool_call.private_owner_scope_ref,
            )
            or tool_call.run_id != run.run_id
            or tool_call.task_id != task.task_id
            or tool_call.request_unit_id != unit.request_unit_id
            or tool_call.started_at < run.started_at
        ):
            raise ValueError("recovery ToolCall owner or identity mismatch")
        created_recovery = (
            tool_call.status is ToolCallStatus.CREATED
            and tool_call.attempt_count == 0
            and not tool_call.attempts
        )
        running_recovery = (
            tool_call.status is ToolCallStatus.RUNNING
            and tool_call.attempt_count in {1, 2}
            and len(tool_call.attempts) == tool_call.attempt_count
            and (
                tool_call.attempts[-1].finished_at is None
                or (
                    tool_call.attempt_count == 1
                    and tool_call.attempts[-1].retry_decision
                    is ToolRetryDecision.RETRY_SCHEDULED
                )
            )
        )
        if not (created_recovery or running_recovery):
            raise ValueError(
                "recovery requires CREATED without attempt, an unfinished last "
                "attempt, or scheduled attempt 1"
            )
        if self.recovery_decision_records:
            raise ValueError("recovery decision child already exists")
        attempt_evidence_times = ()
        if tool_call.attempts:
            last_attempt = tool_call.attempts[-1]
            attempt_evidence_times = (
                last_attempt.started_at,
                *(
                    ()
                    if last_attempt.finished_at is None
                    else (last_attempt.finished_at,)
                ),
            )
        evidence_floor = max(
            run.started_at,
            task.updated_at,
            unit.updated_at,
            tool_call.started_at,
            *(binding.updated_at for binding in self.current_input_binding_records),
            *attempt_evidence_times,
        )
        if self.trusted_read_at < evidence_floor:
            raise ValueError("trusted recovery time precedes current evidence")
        return self

    def remaining_run_time_budget_ms(self) -> int:
        elapsed = self.trusted_read_at - self.active_run_record.started_at
        elapsed_microseconds = (
            (elapsed.days * 86_400 + elapsed.seconds) * 1_000_000
            + elapsed.microseconds
        )
        elapsed_milliseconds = (elapsed_microseconds + 999) // 1_000
        return max(
            0,
            self.run_budget_policy.run_time_budget_ms - elapsed_milliseconds,
        )

    def derive_recovery_decision(self) -> ToolRetryRecoveryDecision:
        exact_tool_call = ToolCallRecordV2.model_validate(
            self.tool_call_record.model_dump(mode="python"),
            strict=True,
        )
        parent = exact_tool_call.dispatch_facts()
        current_binding_ids = {
            binding.binding_id for binding in self.current_input_binding_records
        }
        current_argument_refs = tuple(
            ref
            for ref in parent.argument_binding_refs
            if ref in current_binding_ids
        )
        if not current_argument_refs:
            current_argument_refs = self.current_request_unit_record.input_binding_refs
        current = Cycle2ToolDispatchFacts(
            tool_call_id=parent.tool_call_id,
            run_id=self.active_run_record.run_id,
            private_owner_scope_ref=self.owner_scope.customer_id,
            task_id=self.current_task_record.task_id,
            request_unit_id=self.current_request_unit_record.request_unit_id,
            validated_task_state_version=self.current_task_record.state_version,
            argument_binding_refs=current_argument_refs,
            verified_target_ref=parent.verified_target_ref,
        )
        revalidation = Cycle2RetryRevalidation(
            parent_dispatch_facts=parent,
            expected_dispatch_facts=parent,
            current_dispatch_facts=current,
            remaining_run_time_budget_ms=self.remaining_run_time_budget_ms(),
        )
        return decide_cycle2_tool_recovery(
            tool_call=exact_tool_call,
            revalidation=revalidation,
            decided_at=self.trusted_read_at,
        )


def _recovery_decision_record_matches_loaded_closure(
    *,
    closure: ToolRetryRecoveryReadClosureV2,
    record: ToolRetryRecoveryDecisionRecordV2,
) -> bool:
    expected = closure.derive_recovery_decision()
    return (
        record.tool_call_id == expected.tool_call_id
        and record.last_attempt_no == expected.last_attempt_no
        and record.decision is expected.decision
        and record.stable_reason_code == expected.stable_reason_code
        and record.candidate_next_attempt_no == expected.candidate_next_attempt_no
        and record.decided_at == expected.decided_at
    )


def _recovery_parent_stable_and_attempts_unchanged(
    expected: ToolCallRecordV2,
    terminal: ToolCallRecordV2,
) -> bool:
    return (
        _cycle2_tool_stable_fields_match(expected, terminal)
        and terminal.attempt_count == expected.attempt_count
        and terminal.attempts == expected.attempts
    )


class AppendInitialToolAttemptV2Command(_StrictRuntimePrivateRecord):
    """Bind an exact CREATED closure to the pure attempt-1 append projection."""

    loaded_closure: ToolRetryRecoveryReadClosureV2
    attempt_append_command: AppendToolAttemptV2Command

    @model_validator(mode="before")
    @classmethod
    def nested_records_are_exact(cls, value: object) -> object:
        return _require_exact_cycle2_inputs(
            value,
            model_fields={
                "loaded_closure": ToolRetryRecoveryReadClosureV2,
                "attempt_append_command": AppendToolAttemptV2Command,
            },
        )

    @model_validator(mode="after")
    def initial_append_is_exact(self) -> Self:
        closure = self.loaded_closure
        source = closure.tool_call_record
        append = self.attempt_append_command
        if (
            source.status is not ToolCallStatus.CREATED
            or source.attempt_count != 0
            or source.attempts
        ):
            raise ValueError("initial append requires CREATED attempt-0 closure")
        if (
            append.owner_scope != closure.owner_scope
            or append.expected_record != source
            or append.started_attempt.attempt_no != 1
            or append.started_attempt.started_at < closure.trusted_read_at
        ):
            raise ValueError("initial append does not match trusted closure")
        return self


class AppendRecoveredToolAttemptV2Command(_StrictRuntimePrivateRecord):
    """Atomically append one decision child and the recovered attempt 2 fence."""

    loaded_closure: ToolRetryRecoveryReadClosureV2
    recovery_decision_record: ToolRetryRecoveryDecisionRecordV2
    attempt_append_command: AppendToolAttemptV2Command

    @model_validator(mode="before")
    @classmethod
    def nested_records_are_exact(cls, value: object) -> object:
        return _require_exact_cycle2_inputs(
            value,
            model_fields={
                "loaded_closure": ToolRetryRecoveryReadClosureV2,
                "recovery_decision_record": ToolRetryRecoveryDecisionRecordV2,
                "attempt_append_command": AppendToolAttemptV2Command,
            },
        )

    @model_validator(mode="after")
    def recovered_append_is_exact(self) -> Self:
        closure = self.loaded_closure
        decision = self.recovery_decision_record
        append = self.attempt_append_command
        if (
            not _recovery_decision_record_matches_loaded_closure(
                closure=closure,
                record=decision,
            )
            or decision.decision is not ToolRecoveryDecision.APPEND_SECOND_ATTEMPT
        ):
            raise ValueError("recovered append decision does not match trusted closure")
        if (
            append.owner_scope != closure.owner_scope
            or append.expected_record != closure.tool_call_record
            or append.started_attempt.attempt_no != 2
            or append.started_attempt.started_at < decision.decided_at
        ):
            raise ValueError("recovered append fence does not match trusted decision")
        return self


class FinalizeCreatedToolRecoveryV2Command(_StrictRuntimePrivateRecord):
    """Atomically interrupt a CREATED ToolCall without child or dispatch."""

    loaded_closure: ToolRetryRecoveryReadClosureV2
    terminal_tool_call_record: ToolCallRecordV2

    @model_validator(mode="before")
    @classmethod
    def nested_records_are_exact(cls, value: object) -> object:
        return _require_exact_cycle2_inputs(
            value,
            model_fields={
                "loaded_closure": ToolRetryRecoveryReadClosureV2,
                "terminal_tool_call_record": ToolCallRecordV2,
            },
        )

    @model_validator(mode="after")
    def created_terminal_is_exact(self) -> Self:
        closure = self.loaded_closure
        source = closure.tool_call_record
        terminal = self.terminal_tool_call_record
        decision = closure.derive_recovery_decision()
        if (
            source.status is not ToolCallStatus.CREATED
            or source.attempt_count != 0
            or source.attempts
            or decision.decision
            is not ToolRecoveryDecision.INTERRUPT_WITHOUT_ATTEMPT
            or decision.stable_reason_code != "CREATED_WITHOUT_DISPATCH_FENCE"
        ):
            raise ValueError("created recovery does not match trusted Core decision")
        if (
            not _recovery_parent_stable_and_attempts_unchanged(source, terminal)
            or terminal.status is not ToolCallStatus.INTERRUPTED
            or terminal.finished_at != decision.decided_at
            or terminal.interruption_reason != "PROCESS_RESTART_DETECTED"
            or terminal.failure_code is not None
            or terminal.timeout_phase is not None
            or terminal.result_ref is not None
            or terminal.recovery_disposition is not None
            or terminal.recovery_decision_ref is not None
        ):
            raise ValueError("created recovery terminal must remain parent-only")
        return self


class FinalizeUnfinishedToolRecoveryV2Command(_StrictRuntimePrivateRecord):
    """Atomically append a decision child and terminate only the parent."""

    loaded_closure: ToolRetryRecoveryReadClosureV2
    recovery_decision_record: ToolRetryRecoveryDecisionRecordV2
    terminal_tool_call_record: ToolCallRecordV2

    @model_validator(mode="before")
    @classmethod
    def nested_records_are_exact(cls, value: object) -> object:
        return _require_exact_cycle2_inputs(
            value,
            model_fields={
                "loaded_closure": ToolRetryRecoveryReadClosureV2,
                "recovery_decision_record": ToolRetryRecoveryDecisionRecordV2,
                "terminal_tool_call_record": ToolCallRecordV2,
            },
        )

    @model_validator(mode="after")
    def unfinished_terminal_is_exact(self) -> Self:
        closure = self.loaded_closure
        decision = self.recovery_decision_record
        terminal = self.terminal_tool_call_record
        if (
            not _recovery_decision_record_matches_loaded_closure(
                closure=closure,
                record=decision,
            )
            or decision.decision
            is not ToolRecoveryDecision.INTERRUPT_UNFINISHED_ATTEMPT
        ):
            raise ValueError("unfinished recovery decision does not match closure")
        if (
            not _recovery_parent_stable_and_attempts_unchanged(
                closure.tool_call_record,
                terminal,
            )
            or terminal.status is not ToolCallStatus.INTERRUPTED
            or terminal.finished_at != decision.decided_at
            or terminal.interruption_reason != "PROCESS_RESTART_DETECTED"
            or terminal.recovery_disposition
            is not ToolRecoveryDisposition.UNFINISHED_ATTEMPT_INTERRUPTED
            or terminal.recovery_decision_ref != decision.recovery_decision_id
            or terminal.result_ref is not None
        ):
            raise ValueError("unfinished recovery terminal projection is not exact")
        return self


class FinalizeBudgetExhaustedToolRecoveryV2Command(_StrictRuntimePrivateRecord):
    """Atomically append RUN_BUDGET_EXHAUSTED and its exact parent terminal."""

    loaded_closure: ToolRetryRecoveryReadClosureV2
    recovery_decision_record: ToolRetryRecoveryDecisionRecordV2
    terminal_tool_call_record: ToolCallRecordV2

    @model_validator(mode="before")
    @classmethod
    def nested_records_are_exact(cls, value: object) -> object:
        return _require_exact_cycle2_inputs(
            value,
            model_fields={
                "loaded_closure": ToolRetryRecoveryReadClosureV2,
                "recovery_decision_record": ToolRetryRecoveryDecisionRecordV2,
                "terminal_tool_call_record": ToolCallRecordV2,
            },
        )

    @model_validator(mode="after")
    def budget_terminal_is_exact(self) -> Self:
        closure = self.loaded_closure
        decision = self.recovery_decision_record
        if (
            not _recovery_decision_record_matches_loaded_closure(
                closure=closure,
                record=decision,
            )
            or decision.decision is not ToolRecoveryDecision.TERMINATE_RETRY_PATH
            or decision.stable_reason_code != "RUN_BUDGET_EXHAUSTED"
        ):
            raise ValueError("budget recovery decision does not match trusted closure")
        expected = project_cycle2_budget_exhausted_recovery_terminal(
            tool_call=closure.tool_call_record,
            recovery_decision=closure.derive_recovery_decision(),
            recovery_decision_ref=decision.recovery_decision_id,
        )
        if self.terminal_tool_call_record != expected:
            raise ValueError("budget recovery terminal projection is not exact")
        return self


class FinalizeStateInvalidatedToolRecoveryV2Command(_StrictRuntimePrivateRecord):
    """Atomically close ToolCall and compose the exact OA-10 no-result command."""

    loaded_closure: ToolRetryRecoveryReadClosureV2
    recovery_decision_record: ToolRetryRecoveryDecisionRecordV2
    terminal_tool_call_record: ToolCallRecordV2
    superseded_run_command: FinalizeSupersededRunV2Command

    @model_validator(mode="before")
    @classmethod
    def nested_records_are_exact(cls, value: object) -> object:
        return _require_exact_cycle2_inputs(
            value,
            model_fields={
                "loaded_closure": ToolRetryRecoveryReadClosureV2,
                "recovery_decision_record": ToolRetryRecoveryDecisionRecordV2,
                "terminal_tool_call_record": ToolCallRecordV2,
                "superseded_run_command": FinalizeSupersededRunV2Command,
            },
        )

    @model_validator(mode="after")
    def state_invalidation_is_exact(self) -> Self:
        closure = self.loaded_closure
        decision = self.recovery_decision_record
        terminal = self.terminal_tool_call_record
        oa10 = self.superseded_run_command
        if (
            not _recovery_decision_record_matches_loaded_closure(
                closure=closure,
                record=decision,
            )
            or decision.decision is not ToolRecoveryDecision.TERMINATE_RETRY_PATH
            or decision.stable_reason_code != "STATE_OR_BINDING_INVALIDATED"
        ):
            raise ValueError("state invalidation decision does not match closure")
        if (
            not _recovery_parent_stable_and_attempts_unchanged(
                closure.tool_call_record,
                terminal,
            )
            or terminal.status is not ToolCallStatus.INTERRUPTED
            or terminal.finished_at != decision.decided_at
            or terminal.interruption_reason != "STATE_OR_BINDING_INVALIDATED"
            or terminal.recovery_disposition
            is not ToolRecoveryDisposition.RETRY_SCHEDULED_STATE_INVALIDATED
            or terminal.recovery_decision_ref != decision.recovery_decision_id
            or terminal.result_ref is not None
        ):
            raise ValueError("state invalidation ToolCall terminal is not exact")
        oa10_closure = oa10.loaded_closure
        if (
            oa10_closure.owner_scope != closure.owner_scope
            or oa10_closure.expected_active_run_record
            != closure.active_run_record
            or oa10_closure.expected_active_link_record
            != closure.active_run_task_link_record
            or oa10_closure.current_task_record != closure.current_task_record
            or oa10_closure.current_request_unit_record
            != closure.current_request_unit_record
            or oa10.superseded_run_record.completed_at != decision.decided_at
        ):
            raise ValueError("state invalidation must compose the exact OA-10 closure")
        return self


class SaveShipmentObservationV2Command(_StrictRuntimePrivateRecord):
    """Insert one fresh Shipment Observation after exact successful ToolCall."""

    owner_scope: TrustedOwnerScope
    current_task_record: TaskRecord
    current_request_unit_record: RequestUnitRecord
    source_tool_call_record: ToolCallRecordV2
    source_result_ref: UUID
    source_result: GetShipmentResult
    observation_record: ShipmentObservation
    trusted_acceptance_now: datetime
    previous_observation_record: ShipmentObservation | None = None

    @model_validator(mode="before")
    @classmethod
    def nested_records_are_exact(cls, value: object) -> object:
        return _require_exact_cycle2_inputs(
            value,
            model_fields={
                "owner_scope": TrustedOwnerScope,
                "current_task_record": TaskRecord,
                "current_request_unit_record": RequestUnitRecord,
                "source_tool_call_record": ToolCallRecordV2,
                "source_result": GetShipmentResult,
                "observation_record": ShipmentObservation,
            },
            optional_model_fields={
                "previous_observation_record": ShipmentObservation,
            },
        )

    @field_validator("trusted_acceptance_now")
    @classmethod
    def acceptance_time_is_utc(cls, value: datetime) -> datetime:
        return require_utc(value, field_name="trusted_acceptance_now")

    @model_validator(mode="after")
    def source_graph_is_exact(self) -> Self:
        owner = self.owner_scope
        task = self.current_task_record
        unit = self.current_request_unit_record
        source = self.source_tool_call_record
        result = self.source_result
        observation = self.observation_record
        _task_and_request_unit_form_current_pair(
            owner_scope=owner,
            task_record=task,
            request_unit_record=unit,
        )
        if (
            source.status is not ToolCallStatus.SUCCEEDED
            or source.effect is not ToolEffect.READ
            or source.canonical_tool_name.value != "get_shipment"
        ):
            raise ValueError("Shipment Observation requires successful get_shipment")
        if (
            not _owner_matches_private_scope(owner, source.private_owner_scope_ref)
            or not _owner_matches_private_scope(owner, observation.private_owner_scope)
        ):
            raise ValueError("Shipment Observation owner scope mismatch")
        if (
            source.task_id != task.task_id
            or source.request_unit_id != unit.request_unit_id
            or source.validated_task_state_version != task.state_version
            or source.finished_at is None
            or source.finished_at > observation.recorded_at
            or source.result_ref != self.source_result_ref
            or result.outcome is not GetShipmentOutcome.FOUND
            or observation.source_tool_call_id != source.tool_call_id
            or observation.task_id != source.task_id
            or observation.request_unit_id != source.request_unit_id
            or observation.verified_order_target_ref
            != (
                None
                if source.verified_target_ref is None
                else str(source.verified_target_ref)
            )
        ):
            raise ValueError("Shipment Observation source graph mismatch")
        if (
            result.shipment_summary != observation.normalized_value
            or result.source_resource_ref != observation.source_resource_ref
            or result.source_version != observation.source_version
            or result.observed_at != observation.observed_at
            or (
                observation.raw_result_ref is not None
                and observation.raw_result_ref != str(self.source_result_ref)
            )
        ):
            raise ValueError("Shipment Observation/result projection mismatch")
        if (
            self.trusted_acceptance_now != observation.recorded_at
            or not shipment_snapshot_is_fresh_at_acceptance(
                result,
                trusted_acceptance_now=self.trusted_acceptance_now,
            )
        ):
            raise ValueError("Shipment Observation must be fresh at acceptance")
        previous = self.previous_observation_record
        if observation.supersedes is None:
            if previous is not None:
                raise ValueError("unexpected previous Shipment Observation")
        else:
            if previous is None:
                raise ValueError("Shipment supersession requires previous Observation")
            validate_shipment_observation_supersession(
                current=observation,
                previous=previous,
            )
        return self


class ShipmentNotReceivedClaimReadClosure(_StrictRuntimePrivateRecord):
    """Exact owner-reader projection of one current not-received user Claim."""

    binding_ref: UUID
    binding_name: Literal["shipment_not_received"] = "shipment_not_received"
    normalized_value: Literal[True] = True
    authority: Literal[InputAuthority.USER_CLAIM] = InputAuthority.USER_CLAIM
    validation_status: Literal[InputValidationStatus.ACCEPTED] = (
        InputValidationStatus.ACCEPTED
    )
    private_owner_scope_ref: NonEmptyString
    conversation_id: UUID
    task_id: UUID
    request_unit_id: UUID
    task_state_version: PositiveStateVersion
    verified_order_target_ref: NonEmptyString
    source_message_record: MessageRecord
    accepted_at: datetime
    superseded_by_binding_ref: Literal[None] = None

    @model_validator(mode="before")
    @classmethod
    def nested_record_is_exact(cls, value: object) -> object:
        return _require_exact_cycle2_inputs(
            value,
            model_fields={"source_message_record": MessageRecord},
        )

    @field_validator("accepted_at")
    @classmethod
    def accepted_at_is_utc(cls, value: datetime) -> datetime:
        return require_utc(value, field_name="accepted_at")

    @model_validator(mode="after")
    def source_is_one_saved_user_message(self) -> Self:
        message = self.source_message_record
        if (
            message.direction is not MessageDirection.USER
            or message.conversation_id != self.conversation_id
            or self.accepted_at < message.received_at
        ):
            raise ValueError("Shipment Claim requires one exact saved USER Message")
        return self


class ShipmentAssessmentReadClosure(_StrictRuntimePrivateRecord):
    """Typed graph loaded by the owner reader for deterministic Assessment."""

    owner_scope: TrustedOwnerScope
    trusted_conversation_record: ConversationRecord
    current_task_record: TaskRecord
    current_request_unit_record: RequestUnitRecord
    current_observation_record: ShipmentObservation
    current_observation_ref: UUID
    superseded_observation_records: tuple[ShipmentObservation, ...] = ()
    verified_order_target_ref: NonEmptyString
    trusted_assessed_at: datetime
    current_input_binding_records: tuple[InputBinding, ...] = ()
    current_query_bindings: tuple[AcceptedOrderSearchQueryBindingReadClosure, ...] = ()
    current_ordinal_bindings: tuple[AcceptedOrdinalBindingReadClosure, ...] = ()
    current_claim_bindings: Annotated[
        tuple[ShipmentNotReceivedClaimReadClosure, ...],
        Field(max_length=1),
    ] = ()
    current_assessment_records: Annotated[
        tuple[ShipmentAssessment, ...],
        Field(max_length=1),
    ] = ()

    @model_validator(mode="before")
    @classmethod
    def nested_records_are_exact(cls, value: object) -> object:
        return _require_exact_cycle2_inputs(
            value,
            model_fields={
                "owner_scope": TrustedOwnerScope,
                "trusted_conversation_record": ConversationRecord,
                "current_task_record": TaskRecord,
                "current_request_unit_record": RequestUnitRecord,
                "current_observation_record": ShipmentObservation,
            },
            tuple_model_fields={
                "superseded_observation_records": ShipmentObservation,
                "current_input_binding_records": InputBinding,
                "current_query_bindings": (
                    AcceptedOrderSearchQueryBindingReadClosure
                ),
                "current_ordinal_bindings": AcceptedOrdinalBindingReadClosure,
                "current_claim_bindings": ShipmentNotReceivedClaimReadClosure,
                "current_assessment_records": ShipmentAssessment,
            },
        )

    @field_validator("trusted_assessed_at")
    @classmethod
    def assessed_at_is_utc(cls, value: datetime) -> datetime:
        return require_utc(value, field_name="trusted_assessed_at")

    @model_validator(mode="after")
    def assessment_inputs_are_exact(self) -> Self:
        task = self.current_task_record
        unit = self.current_request_unit_record
        observation = self.current_observation_record
        conversation = self.trusted_conversation_record
        _task_and_request_unit_form_current_pair(
            owner_scope=self.owner_scope,
            task_record=task,
            request_unit_record=unit,
        )
        if (
            conversation.owner_customer_id != self.owner_scope.customer_id
            or self.current_observation_ref != observation.observation_id
            or observation.observation_id not in unit.observation_refs
            or not _owner_matches_private_scope(
                self.owner_scope,
                observation.private_owner_scope,
            )
            or observation.task_id != task.task_id
            or observation.request_unit_id != unit.request_unit_id
            or observation.verified_order_target_ref
            != self.verified_order_target_ref
        ):
            raise ValueError("Shipment Assessment Observation binding mismatch")
        if not (
            observation.observed_at
            <= self.trusted_assessed_at
            < observation.valid_until
        ):
            raise ValueError("Shipment Assessment requires a fresh Observation")

        shipment_records = (
            observation,
            *self.superseded_observation_records,
        )
        shipment_by_ref = {
            record.observation_id: record for record in shipment_records
        }
        if (
            len(shipment_by_ref) != len(shipment_records)
            or not set(shipment_by_ref).issubset(unit.observation_refs)
            or any(
                not _owner_matches_private_scope(
                    self.owner_scope,
                    record.private_owner_scope,
                )
                or record.task_id != task.task_id
                or record.request_unit_id != unit.request_unit_id
                or record.verified_order_target_ref
                != self.verified_order_target_ref
                for record in shipment_records
            )
        ):
            raise ValueError("complete Shipment Observation graph mismatch")
        traversed_superseded_refs: set[UUID] = set()
        cursor = observation
        while cursor.supersedes is not None:
            next_ref = cursor.supersedes
            if (
                next_ref in traversed_superseded_refs
                or next_ref not in shipment_by_ref
            ):
                raise ValueError(
                    "Shipment Observation current/supersession graph mismatch"
                )
            traversed_superseded_refs.add(next_ref)
            next_record = shipment_by_ref[next_ref]
            validate_shipment_observation_supersession(
                current=cursor,
                previous=next_record,
            )
            cursor = next_record
        if traversed_superseded_refs != {
            record.observation_id
            for record in self.superseded_observation_records
        }:
            raise ValueError("Shipment Observation current/supersession graph mismatch")

        binding_refs = tuple(
            binding.binding_id for binding in self.current_input_binding_records
        ) + tuple(
            binding.binding_ref for binding in self.current_query_bindings
        ) + tuple(
            binding.binding_ref for binding in self.current_ordinal_bindings
        ) + tuple(binding.binding_ref for binding in self.current_claim_bindings)
        if (
            len(binding_refs) != len(set(binding_refs))
            or len(binding_refs) != len(unit.input_binding_refs)
            or set(binding_refs) != set(unit.input_binding_refs)
        ):
            raise ValueError("complete current InputBinding partition mismatch")
        for query in self.current_query_bindings:
            if (
                query.private_owner_scope_ref != self.owner_scope.customer_id
                or query.conversation_id != conversation.conversation_id
                or query.task_id != task.task_id
                or query.request_unit_id != unit.request_unit_id
                or query.current_task_state_version != task.state_version
                or query.accepted_at > self.trusted_assessed_at
            ):
                raise ValueError("current query binding closure mismatch")
        for ordinal in self.current_ordinal_bindings:
            if (
                ordinal.private_owner_scope_ref != self.owner_scope.customer_id
                or ordinal.conversation_id != conversation.conversation_id
                or ordinal.task_id != task.task_id
                or ordinal.request_unit_id != unit.request_unit_id
                or ordinal.task_state_version != task.state_version
                or ordinal.accepted_at > self.trusted_assessed_at
            ):
                raise ValueError("current ordinal binding closure mismatch")
        for claim in self.current_claim_bindings:
            if (
                claim.private_owner_scope_ref != self.owner_scope.customer_id
                or claim.conversation_id != conversation.conversation_id
                or claim.task_id != task.task_id
                or claim.request_unit_id != unit.request_unit_id
                or claim.task_state_version != task.state_version
                or claim.verified_order_target_ref
                != self.verified_order_target_ref
                or claim.accepted_at > self.trusted_assessed_at
            ):
                raise ValueError("current Claim binding closure mismatch")
        previous = self.current_assessment_record
        if previous is not None and (
            previous.private_owner_scope_ref != self.owner_scope.customer_id
            or previous.task_id != task.task_id
            or previous.request_unit_id != unit.request_unit_id
            or previous.task_state_version > task.state_version
            or previous.verified_order_target_ref != self.verified_order_target_ref
            or previous.shipment_observation_ref not in shipment_by_ref
            or shipment_by_ref[
                previous.shipment_observation_ref
            ].source_version != previous.shipment_observation_source_version
            or previous.assessed_at > self.trusted_assessed_at
        ):
            raise ValueError("current Shipment Assessment context mismatch")
        return self

    def require_same_persisted_graph(
        self,
        current: ShipmentAssessmentReadClosure,
    ) -> None:
        """Fail when the Port's in-transaction re-read differs in any field."""

        rebuilt = _require_exact_cycle2_model(
            current,
            ShipmentAssessmentReadClosure,
            field_name="current Shipment Assessment read closure",
        )
        if rebuilt != self:
            raise ValueError("Shipment Assessment persisted read fence mismatch")

    @property
    def current_claim_binding_ref(self) -> UUID | None:
        if not self.current_claim_bindings:
            return None
        return self.current_claim_bindings[0].binding_ref

    @property
    def current_assessment_record(self) -> ShipmentAssessment | None:
        if not self.current_assessment_records:
            return None
        return self.current_assessment_records[0]


class SaveShipmentAssessmentV2Command(_StrictRuntimePrivateRecord):
    """Persist one exact deterministic derivation after durable Observation."""

    loaded_closure: ShipmentAssessmentReadClosure
    assessment_record: ShipmentAssessment

    @model_validator(mode="before")
    @classmethod
    def nested_records_are_exact(cls, value: object) -> object:
        return _require_exact_cycle2_inputs(
            value,
            model_fields={
                "loaded_closure": ShipmentAssessmentReadClosure,
                "assessment_record": ShipmentAssessment,
            },
        )

    @model_validator(mode="after")
    def assessment_is_exact_derivation(self) -> Self:
        closure = self.loaded_closure
        observation = closure.current_observation_record
        assessment = self.assessment_record
        expected = assess_shipment(
            assessment_id=assessment.assessment_id,
            private_owner_scope_ref=closure.owner_scope.customer_id,
            task_id=closure.current_task_record.task_id,
            request_unit_id=closure.current_request_unit_record.request_unit_id,
            task_state_version=closure.current_task_record.state_version,
            verified_order_target_ref=closure.verified_order_target_ref,
            shipment_observation_ref=observation.observation_id,
            shipment_observation_source_version=observation.source_version,
            shipment_summary=observation.normalized_value,
            observation_observed_at=observation.observed_at,
            observation_valid_until=observation.valid_until,
            assessed_at=closure.trusted_assessed_at,
            claim_binding_ref=closure.current_claim_binding_ref,
            supersedes_assessment_ref=(
                None
                if closure.current_assessment_record is None
                else closure.current_assessment_record.assessment_id
            ),
        )
        if assessment != expected:
            raise ValueError("ShipmentAssessment must equal deterministic derivation")
        return self


class SupersededRunInvalidationKind(StrEnum):
    TASK_VERSION_ADVANCED = "TASK_VERSION_ADVANCED"
    BINDING_INVALIDATED = "BINDING_INVALIDATED"


class SupersededRunReadClosure(_StrictRuntimePrivateRecord):
    """Exact owner-scoped no-result fence proving an active Run is obsolete."""

    owner_scope: TrustedOwnerScope
    trusted_conversation_record: ConversationRecord
    expected_active_run_record: AgentRunRecordV2
    expected_active_link_record: RunTaskLinkRecordV2
    current_authoritative_run_record: AgentRunRecordV2
    current_authoritative_link_record: RunTaskLinkRecordV2
    current_task_record: TaskRecord
    current_request_unit_record: RequestUnitRecord
    obsolete_task_record: TaskRecord | None = None
    obsolete_request_unit_record: RequestUnitRecord | None = None
    trusted_current_evidence_at: datetime
    invalidation_kind: SupersededRunInvalidationKind
    obsolete_binding_refs: tuple[UUID, ...] = ()
    invalidated_binding_refs: tuple[UUID, ...] = ()

    @model_validator(mode="before")
    @classmethod
    def nested_records_are_exact(cls, value: object) -> object:
        return _require_exact_cycle2_inputs(
            value,
            model_fields={
                "owner_scope": TrustedOwnerScope,
                "trusted_conversation_record": ConversationRecord,
                "expected_active_run_record": AgentRunRecordV2,
                "expected_active_link_record": RunTaskLinkRecordV2,
                "current_authoritative_run_record": AgentRunRecordV2,
                "current_authoritative_link_record": RunTaskLinkRecordV2,
                "current_task_record": TaskRecord,
                "current_request_unit_record": RequestUnitRecord,
            },
            optional_model_fields={
                "obsolete_task_record": TaskRecord,
                "obsolete_request_unit_record": RequestUnitRecord,
            },
        )

    @field_validator("trusted_current_evidence_at")
    @classmethod
    def evidence_time_is_utc(cls, value: datetime) -> datetime:
        return require_utc(value, field_name="trusted_current_evidence_at")

    @model_validator(mode="after")
    def obsolete_fence_is_closed(self) -> Self:
        run = self.expected_active_run_record
        link = self.expected_active_link_record
        current_run = self.current_authoritative_run_record
        current_link = self.current_authoritative_link_record
        current_task = self.current_task_record
        current_unit = self.current_request_unit_record
        obsolete_task = self.obsolete_task_record
        obsolete_unit = self.obsolete_request_unit_record
        conversation = self.trusted_conversation_record
        if run.status not in {AgentRunStatusV2.CREATED, AgentRunStatusV2.RUNNING}:
            raise ValueError("obsolete fence requires active v2 Run")
        if (
            link.run_id != run.run_id
            or link.result_task_state_version is not None
        ):
            raise ValueError("obsolete fence requires active no-result RunTaskLink")
        _task_and_request_unit_form_current_pair(
            owner_scope=self.owner_scope,
            task_record=current_task,
            request_unit_record=current_unit,
        )
        if link.task_id != current_task.task_id:
            raise ValueError("obsolete fence current Task does not match RunTaskLink")
        if link.base_task_state_version is None:
            if obsolete_task is not None or obsolete_unit is not None:
                raise ValueError("initial Run cannot carry invented obsolete snapshots")
        else:
            if obsolete_task is None or obsolete_unit is None:
                raise ValueError("versioned obsolete Run requires exact old Task graph")
            _task_and_request_unit_form_current_pair(
                owner_scope=self.owner_scope,
                task_record=obsolete_task,
                request_unit_record=obsolete_unit,
            )
            if (
                obsolete_task.task_id != link.task_id
                or obsolete_task.state_version != link.base_task_state_version
                or obsolete_unit.request_unit_id != current_unit.request_unit_id
                or current_task.state_version <= obsolete_task.state_version
                or current_task.updated_at < obsolete_task.updated_at
                or current_unit.updated_at < obsolete_unit.updated_at
            ):
                raise ValueError("obsolete Task snapshot/version graph mismatch")
        if (
            current_run.run_id == run.run_id
            or current_run.status
            not in {
                AgentRunStatusV2.CREATED,
                AgentRunStatusV2.RUNNING,
                AgentRunStatusV2.COMPLETED,
            }
            or current_run.started_at < run.started_at
        ):
            raise ValueError("obsolete fence requires a newer authoritative Run")
        if current_link.run_id != current_run.run_id or (
            current_link.task_id != current_task.task_id
        ):
            raise ValueError(
                "authoritative RunTaskLink must match current Run and Task"
            )
        if current_run.status in {
            AgentRunStatusV2.CREATED,
            AgentRunStatusV2.RUNNING,
        }:
            if (
                current_link.base_task_state_version != current_task.state_version
                or current_link.result_task_state_version is not None
            ):
                raise ValueError(
                    "active authoritative RunTaskLink must match current Task version"
                )
        elif (
            current_link.result_task_state_version != current_task.state_version
            or current_link.base_task_state_version is None
            or current_link.base_task_state_version
            > current_link.result_task_state_version
        ):
            raise ValueError(
                "completed authoritative RunTaskLink must close current Task version"
            )
        if (
            conversation.owner_customer_id != self.owner_scope.customer_id
            or run.conversation_id is None
            or run.conversation_id != conversation.conversation_id
            or current_run.conversation_id != conversation.conversation_id
        ):
            raise ValueError("obsolete and authoritative Runs must share Conversation")
        evidence_floor = max(
            current_task.updated_at,
            current_unit.updated_at,
            current_run.started_at,
            conversation.created_at,
            *(
                ()
                if current_run.completed_at is None
                else (current_run.completed_at,)
            ),
        )
        if self.trusted_current_evidence_at < evidence_floor:
            raise ValueError("obsolete fence evidence time precedes current graph")
        if len(self.obsolete_binding_refs) != len(set(self.obsolete_binding_refs)):
            raise ValueError("obsolete binding refs must be unique")
        if len(self.invalidated_binding_refs) != len(
            set(self.invalidated_binding_refs)
        ):
            raise ValueError("invalidated binding refs must be unique")
        if self.invalidation_kind is SupersededRunInvalidationKind.TASK_VERSION_ADVANCED:
            if self.obsolete_binding_refs or self.invalidated_binding_refs:
                raise ValueError(
                    "Task-version invalidation cannot carry binding evidence"
                )
        else:
            if obsolete_unit is None:
                raise ValueError(
                    "binding invalidation requires versioned obsolete RequestUnit"
                )
            removed_binding_refs = tuple(
                binding_ref
                for binding_ref in obsolete_unit.input_binding_refs
                if binding_ref not in set(current_unit.input_binding_refs)
            )
            if (
                not self.obsolete_binding_refs
                or self.invalidated_binding_refs != self.obsolete_binding_refs
                or self.obsolete_binding_refs != removed_binding_refs
            ):
                raise ValueError("binding invalidation requires exact binding refs")
            if set(self.invalidated_binding_refs).intersection(
                current_unit.input_binding_refs
            ):
                raise ValueError(
                    "invalidated binding refs cannot remain current"
                )
        return self


class FinalizeSupersededRunV2Command(_StrictRuntimePrivateRecord):
    """OA-10 no-result closure; contains no Task/RequestUnit/outbound write DTO."""

    loaded_closure: SupersededRunReadClosure
    superseded_run_record: AgentRunRecordV2
    no_result_link_record: RunTaskLinkRecordV2
    run_stopped_trace_record: TraceEventV2

    @model_validator(mode="before")
    @classmethod
    def nested_records_are_exact(cls, value: object) -> object:
        return _require_exact_cycle2_inputs(
            value,
            model_fields={
                "loaded_closure": SupersededRunReadClosure,
                "superseded_run_record": AgentRunRecordV2,
                "no_result_link_record": RunTaskLinkRecordV2,
                "run_stopped_trace_record": TraceEventV2,
            },
        )

    @model_validator(mode="after")
    def no_result_closure_is_exact(self) -> Self:
        closure = self.loaded_closure
        active = closure.expected_active_run_record
        active_link = closure.expected_active_link_record
        terminal = self.superseded_run_record
        terminal_link = self.no_result_link_record
        trace = self.run_stopped_trace_record
        if (
            terminal.status is not AgentRunStatusV2.SUPERSEDED
            or terminal.stop_reason
            is not StopReasonV2.STATE_OR_BINDING_INVALIDATED
            or terminal.incomplete_reason is not None
        ):
            raise ValueError("OA-10 requires exact SUPERSEDED terminal Run")
        if terminal.completed_at < closure.trusted_current_evidence_at:
            raise ValueError("OA-10 terminal time precedes current invalidation evidence")
        if any(
            getattr(active, field_name) != getattr(terminal, field_name)
            for field_name in (
                "run_id",
                "conversation_id",
                "provider_lane",
                "started_at",
            )
        ):
            raise ValueError("SUPERSEDED Run cannot change stable fields")
        if terminal_link != active_link or terminal_link.result_task_state_version is not None:
            raise ValueError("OA-10 link must remain exact no-result closure")
        if (
            trace.event_type is not TraceEventType.RUN_STOPPED
            or trace.run_id != terminal.run_id
            or trace.task_id != terminal_link.task_id
            or trace.request_unit_id
            != closure.current_request_unit_record.request_unit_id
            or trace.occurred_at != terminal.completed_at
            or trace.user_outcome is not AgentOutcome.BLOCKED
            or trace.stop_reason is not StopReasonV2.STATE_OR_BINDING_INVALIDATED
        ):
            raise ValueError("OA-10 requires exact audit-only RunStopped trace")
        allowed_trace_fields = {
            "trace_event_id",
            "event_type",
            "occurred_at",
            "run_id",
            "task_id",
            "request_unit_id",
            "user_outcome",
            "stop_reason",
        }
        if any(
            getattr(trace, field_name) != field.default
            for field_name, field in TraceEventV2.model_fields.items()
            if field_name not in allowed_trace_fields
        ):
            raise ValueError("OA-10 audit Trace cannot carry outbound or mutation refs")
        return self


FinalizeStateInvalidatedToolRecoveryV2Command.model_rebuild()


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


_EXACT_RUN_EVIDENCE_BINDING_VALIDATION_MESSAGE = (
    "accepted child bindings must preserve validated input values"
)


def _is_exact_run_evidence_binding_validation_error(
    error: ValidationError,
) -> bool:
    line_errors = error.errors(
        include_url=False,
        include_context=True,
        include_input=False,
    )
    if len(line_errors) != 1:
        return False
    context = line_errors[0].get("ctx")
    if not isinstance(context, Mapping):
        return False
    source_error = context.get("error")
    return (
        type(source_error) is ValueError
        and source_error.args
        == (_EXACT_RUN_EVIDENCE_BINDING_VALIDATION_MESSAGE,)
    )


def _new_exact_run_evidence_binding_validation_error() -> ValidationError:
    return ValidationError.from_exception_data(
        "ExactRunEvidenceClosure",
        [
            {
                "type": "value_error",
                "loc": ("accepted_task_deltas",),
                "input": None,
                "ctx": {
                    "error": ValueError(
                        _EXACT_RUN_EVIDENCE_BINDING_VALIDATION_MESSAGE
                    )
                },
            }
        ],
        input_type="python",
        hide_input=True,
    )


class _ExactRunEvidenceClosureMeta(type(_StrictRuntimePrivateRecord)):
    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        try:
            return super().__call__(*args, **kwargs)
        except ValidationError as error:
            if not _is_exact_run_evidence_binding_validation_error(error):
                raise
            sanitized_error = (
                _new_exact_run_evidence_binding_validation_error()
            )
        raise sanitized_error from None


class ExactRunEvidenceClosure(
    _StrictRuntimePrivateRecord,
    metaclass=_ExactRunEvidenceClosureMeta,
):
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
                try:
                    normalized_expected_inputs = {
                        name: _normalize_order_id(
                            candidate_input.candidate_value
                        )
                        for name, candidate_input in expected_inputs.items()
                    }
                except ValueError:
                    raise ValueError(
                        _EXACT_RUN_EVIDENCE_BINDING_VALIDATION_MESSAGE
                    ) from None
                if any(
                    binding.normalized_value
                    != normalized_expected_inputs[name]
                    or binding.authority is not expected_inputs[name].authority
                    or binding.source_refs
                    != (expected_inputs[name].source_ref,)
                    for name, binding in actual_bindings.items()
                ):
                    raise ValueError(
                        _EXACT_RUN_EVIDENCE_BINDING_VALIDATION_MESSAGE
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
        normalized_tool_result_events_by_call: dict[UUID, TraceEvent] = {}
        for event in self.trace_events:
            if event.run_id != run.run_id or event.case_id is not None:
                raise ValueError(
                    "TraceEvent must bind the root Run without Eval case identity"
                )
            if (
                event.event_type is not TraceEventType.GATE_DECISION_RECORDED
                and (
                    event.gate_decision is not None
                    or event.gate_reason_code is not None
                )
            ):
                raise ValueError(
                    "Gate fields require GateDecisionRecorded"
                )
            if (
                event.event_type is not TraceEventType.RUN_STOPPED
                and (
                    event.user_outcome is not None
                    or event.stop_reason is not None
                )
            ):
                raise ValueError(
                    "terminal fields require RunStopped"
                )
            if event.event_type is TraceEventType.TOOL_RESULT_NORMALIZED:
                if (
                    event.safe_tool_outcome is None
                    or event.tool_call_id is None
                ):
                    raise ValueError(
                        "ToolResultNormalized requires safe_tool_outcome "
                        "and tool_call_id"
                    )
                if event.tool_call_id in normalized_tool_result_events_by_call:
                    raise ValueError(
                        "ToolResultNormalized must be unique per ToolCall"
                    )
                normalized_tool_result_events_by_call[event.tool_call_id] = event
            elif event.safe_tool_outcome is not None:
                raise ValueError(
                    "safe_tool_outcome requires ToolResultNormalized"
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

        gate_trace_events_by_projection: dict[
            tuple[object, ...],
            list[TraceEvent],
        ] = {}
        for event in self.trace_events:
            if event.event_type is not TraceEventType.GATE_DECISION_RECORDED:
                continue
            projection = (
                event.model_call_id,
                event.context_manifest_id,
                event.requested_tool_name,
                event.validated_task_state_version,
                event.argument_binding_refs,
                event.gate_decision,
                event.gate_reason_code,
            )
            gate_trace_events_by_projection.setdefault(projection, []).append(
                event
            )

        gate_owner_records_by_projection: dict[
            tuple[object, ...],
            list[GateDecision],
        ] = {}
        for gate in self.gate_decisions:
            projection = (
                gate.model_call_id,
                gate.context_manifest_id,
                gate.requested_provider_tool_name,
                gate.validated_task_state_version,
                gate.argument_binding_refs,
                gate.decision,
                gate.reason_code,
            )
            gate_owner_records_by_projection.setdefault(projection, []).append(
                gate
            )

        gate_trace_projection_counts = Counter(
            {
                projection: len(events)
                for projection, events in gate_trace_events_by_projection.items()
            }
        )
        gate_owner_projection_counts = Counter(
            {
                projection: len(gates)
                for projection, gates in gate_owner_records_by_projection.items()
            }
        )
        if not gate_trace_projection_counts <= gate_owner_projection_counts:
            raise ValueError(
                "GateDecisionRecorded must match an owner GateDecision projection"
            )

        for projection, events in gate_trace_events_by_projection.items():
            owners = gate_owner_records_by_projection[projection]
            for event in events:
                if event.task_id is None or event.request_unit_id is None:
                    raise ValueError(
                        "GateDecisionRecorded requires a root Task/RequestUnit pair"
                    )
                manifest = manifest_by_id[event.context_manifest_id]
                if (
                    manifest.task_state_ref_and_version is not None
                    and event.task_id
                    != manifest.task_state_ref_and_version.task_id
                ):
                    raise ValueError(
                        "GateDecisionRecorded Task must match ContextManifest"
                    )

            gate_binding_refs = set(owners[0].argument_binding_refs)
            cross_unit_binding_count = sum(
                not gate_binding_refs.issubset(
                    unit_by_id[event.request_unit_id].input_binding_refs
                )
                for event in events
            )
            binding_invalid_owner_count = sum(
                not owner.argument_binding_valid for owner in owners
            )
            if cross_unit_binding_count > binding_invalid_owner_count:
                raise ValueError(
                    "GateDecisionRecorded bindings must belong to its RequestUnit"
                )

        for call_id, normalized in normalized_tool_result_events_by_call.items():
            call = call_by_id[call_id]
            allowed_outcomes = _TERMINAL_TOOL_OUTCOMES.get(call.status)
            if allowed_outcomes is None:
                raise ValueError(
                    "ToolResultNormalized requires a terminal ToolCall"
                )
            if (
                normalized.occurred_at != call.finished_at
                or normalized.safe_tool_outcome not in allowed_outcomes
            ):
                raise ValueError(
                    "ToolResultNormalized must match terminal ToolCall "
                    "status and timestamp"
                )
            attempts = attempts_by_call[call_id]
            if call.status is ToolCallStatus.INTERRUPTED:
                if call.attempt_count == 0:
                    if attempts:
                        raise ValueError(
                            "ToolResultNormalized must match the final ToolAttempt"
                        )
                elif (
                    not attempts
                    or attempts[-1].outcome
                    not in {None, ToolResultOutcome.INTERRUPTED}
                ):
                    raise ValueError(
                        "ToolResultNormalized must match the final ToolAttempt"
                    )
            elif (
                not attempts
                or attempts[-1].outcome
                is not normalized.safe_tool_outcome
            ):
                raise ValueError(
                    "ToolResultNormalized must match the final ToolAttempt"
                )

        active_run_statuses = {
            AgentRunStatus.CREATED,
            AgentRunStatus.RUNNING,
        }
        if run.status in active_run_statuses:
            if run_stopped_events:
                raise ValueError("active Run cannot have RunStopped Trace")
        elif run.status is AgentRunStatus.FAILED:
            if run.stop_reason is not None:
                raise ValueError("FAILED Run must not carry stop_reason")
            if run_stopped_events:
                raise ValueError("FAILED Run cannot have RunStopped Trace")
        else:
            if len(run_stopped_events) != 1:
                raise ValueError(
                    "terminal RunStopped Trace must exist exactly once"
                )
            run_stopped = run_stopped_events[0]
            allowed_run_stopped_fields = _TERMINAL_TRACE_ALLOWED_FIELDS[
                TraceEventType.RUN_STOPPED
            ]
            if any(
                getattr(run_stopped, field_name) != field_info.default
                for field_name, field_info in TraceEvent.model_fields.items()
                if field_name not in allowed_run_stopped_fields
            ):
                raise ValueError(
                    "RunStopped Trace only allows its exact per-kind projection"
                )
            if (
                run_stopped.stop_reason is not run.stop_reason
                or run_stopped.occurred_at != run.completed_at
            ):
                raise ValueError(
                    "terminal RunStopped Trace must match the Run projection"
                )
            if run.status is AgentRunStatus.COMPLETED:
                task_statuses = {task.status for task in self.task_records}
                task_status = (
                    next(iter(task_statuses))
                    if len(task_statuses) == 1
                    else None
                )
                completed_row = (
                    run.stop_reason,
                    bool(self.task_records),
                    run_stopped.user_outcome,
                    task_status,
                )
                if (
                    len(task_statuses) > 1
                    or completed_row not in _COMPLETED_FINALIZATION_ROWS
                ):
                    raise ValueError(
                        "RunStopped projection is outside the closed "
                        "completed Run matrix"
                    )
            elif (
                run.stop_reason
                is not StopReason.PROCESS_RESTART_DETECTED
                or run_stopped.user_outcome is not AgentOutcome.BLOCKED
            ):
                raise ValueError(
                    "INCOMPLETE RunStopped requires "
                    "PROCESS_RESTART_DETECTED and BLOCKED"
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
