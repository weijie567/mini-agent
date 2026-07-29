"""Pure deterministic validation and reduction for the first E2E-01 slice."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Annotated, Any, Literal, Self
from uuid import UUID

from pydantic import Field, JsonValue, field_serializer, field_validator

from .common import (
    RuntimePrivateModel,
    find_trusted_argument_field,
    freeze_json_value,
    thaw_json_value,
)
from .identity import CustomerContext
from .request_understanding import (
    InputAuthority,
    InputSourceKind,
    NextMove,
    NextMoveKind,
    RequestUnderstandingOutput,
    TaskDeltaOperation,
)
from .task_state import (
    AcceptedTaskDelta,
    CandidateValidationDecision,
    CandidateValidationRecord,
    InputBinding,
    InputValidationStatus,
    RequestUnderstandingRecord,
    RequestUnitRecord,
    TaskRecord,
    TaskStatus,
)

NonEmptyString = Annotated[str, Field(min_length=1)]
PositiveStateVersion = Annotated[int, Field(ge=1)]
OrderId = Annotated[str, Field(pattern=r"^O-[0-9]{4,20}$")]

_ORDER_ID_PATTERN = re.compile(r"^O-[0-9]{4,20}$")
_ORDER_ID_IN_TEXT_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])(?:O|o)-[0-9]{4,20}(?![A-Za-z0-9])"
)


class RequestProcessingError(ValueError):
    """A bounded validation failure that never contains caller-provided data."""

    __slots__ = ()


class InitialRequestDecision(RuntimePrivateModel):
    """Complete pure result for one accepted initial ADD_GOAL candidate."""

    request_understanding: RequestUnderstandingRecord
    accepted_delta: AcceptedTaskDelta
    input_binding: InputBinding
    task: TaskRecord
    request_unit: RequestUnitRecord
    next_move_candidate_ref: UUID
    next_move_candidate: NextMove


class RevalidatedNextMove(RuntimePrivateModel):
    """Candidate and current binding kept separate for the Control Gateway."""

    run_id: UUID
    task_id: UUID
    request_unit_id: UUID
    next_move_candidate_ref: UUID
    kind: Literal[NextMoveKind.CALL_TOOL]
    requested_provider_tool_name: NonEmptyString
    candidate_arguments: Mapping[str, JsonValue]
    normalized_candidate_order_id: OrderId | None
    binding_name: Literal["order_id"]
    binding_normalized_value: OrderId
    argument_binding_refs: Annotated[tuple[UUID, ...], Field(min_length=1)]
    proposed_base_task_state_version: PositiveStateVersion | None
    validated_task_state_version: PositiveStateVersion

    @field_validator("candidate_arguments", mode="before")
    @classmethod
    def candidate_argument_input_is_native_json(cls, value: Any) -> Any:
        return thaw_json_value(value)

    @field_validator("candidate_arguments")
    @classmethod
    def candidate_arguments_are_frozen(
        cls,
        value: Mapping[str, JsonValue],
    ) -> Mapping[str, JsonValue]:
        return freeze_json_value(value)

    @field_serializer("candidate_arguments")
    def serialize_candidate_arguments(
        self,
        value: Mapping[str, JsonValue],
    ) -> dict[str, JsonValue]:
        return thaw_json_value(value)


def _normalize_order_id(value: object) -> str:
    if type(value) is not str:
        raise RequestProcessingError("invalid order_id candidate")
    normalized = value.strip()
    if normalized[:2].casefold() == "o-":
        normalized = f"O-{normalized[2:]}"
    if _ORDER_ID_PATTERN.fullmatch(normalized) is None:
        raise RequestProcessingError("invalid order_id candidate")
    return normalized


def _candidate_order_id_or_none(arguments: Mapping[str, object]) -> str | None:
    if set(arguments) != {"order_id"}:
        return None
    try:
        return _normalize_order_id(arguments["order_id"])
    except RequestProcessingError:
        return None


def _source_quote_contains_exact_order_id(
    source_quote: str,
    normalized_order_id: str,
) -> bool:
    return any(
        _normalize_order_id(match.group()) == normalized_order_id
        for match in _ORDER_ID_IN_TEXT_PATTERN.finditer(source_quote)
    )


def validate_and_reduce_initial_request(
    *,
    output: RequestUnderstandingOutput,
    current_message_ref: UUID,
    current_message: str,
    customer_context: CustomerContext,
    run_id: UUID,
    accepted_delta_id: UUID,
    task_id: UUID,
    request_unit_id: UUID,
    binding_id: UUID,
    next_move_candidate_ref: UUID,
    now: Any,
) -> InitialRequestDecision:
    """Validate one current-message candidate and build an ACTIVE/v1 graph.

    All identities and time are supplied by the Application layer. This pure
    reducer neither performs I/O nor invents an owner or record identity.
    """

    if type(output) is not RequestUnderstandingOutput:
        raise RequestProcessingError("canonical output required")
    if type(customer_context) is not CustomerContext:
        raise RequestProcessingError("trusted CustomerContext required")
    if type(current_message) is not str or not current_message:
        raise RequestProcessingError("current message required")
    if output.message_ref != current_message_ref:
        raise RequestProcessingError("output must reference current message")
    if len(output.task_delta_candidates) != 1:
        raise RequestProcessingError("exactly one ADD_GOAL candidate required")

    delta = output.task_delta_candidates[0]
    if delta.operation is not TaskDeltaOperation.ADD_GOAL:
        raise RequestProcessingError("only ADD_GOAL is accepted")
    if len(delta.input_candidates) != 1:
        raise RequestProcessingError("exactly one order_id input required")

    candidate = delta.input_candidates[0]
    if candidate.name != "order_id":
        raise RequestProcessingError("order_id input required")
    if candidate.semantic_role != "TARGET_RESOURCE_IDENTIFIER":
        raise RequestProcessingError("invalid input semantic role")
    if candidate.source_kind is not InputSourceKind.CURRENT_MESSAGE:
        raise RequestProcessingError("invalid current-message source")
    if candidate.source_ref != current_message_ref:
        raise RequestProcessingError("input source must be current message")
    if candidate.authority is not InputAuthority.USER_CLAIM:
        raise RequestProcessingError("invalid input authority")
    if candidate.source_quote not in current_message:
        raise RequestProcessingError("source quote is not in current message")

    normalized_binding_value = _normalize_order_id(candidate.candidate_value)
    if not _source_quote_contains_exact_order_id(
        candidate.source_quote,
        normalized_binding_value,
    ):
        raise RequestProcessingError("source quote does not contain order_id")

    next_move = output.next_move_candidate
    if type(next_move) is not NextMove:
        raise RequestProcessingError("canonical next move required")
    if next_move.kind is not NextMoveKind.CALL_TOOL:
        raise RequestProcessingError("initial slice requires CALL_TOOL")
    if next_move.base_task_state_version is not None:
        raise RequestProcessingError("new goal requires null base Task version")
    if next_move.arguments is None:
        raise RequestProcessingError("CALL_TOOL arguments required")
    if find_trusted_argument_field(next_move.arguments) is not None:
        raise RequestProcessingError("trusted field in model arguments")

    input_binding = InputBinding(
        binding_id=binding_id,
        name="order_id",
        normalized_value=normalized_binding_value,
        authority=InputAuthority.USER_CLAIM,
        source_refs=(current_message_ref,),
        validation_status=InputValidationStatus.ACCEPTED,
        confirmed_by_user=True,
        created_at=now,
        updated_at=now,
    )
    accepted_delta = AcceptedTaskDelta(
        accepted_delta_id=accepted_delta_id,
        candidate_ref=delta.candidate_id,
        message_ref=current_message_ref,
        operation=TaskDeltaOperation.ADD_GOAL,
        goal_text=delta.goal_patch,
        input_binding_refs=(binding_id,),
        accepted_at=now,
    )
    task = TaskRecord(
        task_id=task_id,
        owner_customer_id=customer_context.customer_id,
        status=TaskStatus.ACTIVE,
        state_version=1,
        created_at=now,
        updated_at=now,
    )
    request_unit = RequestUnitRecord(
        request_unit_id=request_unit_id,
        task_id=task_id,
        goal_text=delta.goal_patch,
        goal_source_refs=(current_message_ref,),
        input_binding_refs=(binding_id,),
        status=TaskStatus.ACTIVE,
        state_version=1,
        created_at=now,
        updated_at=now,
    )
    understanding = RequestUnderstandingRecord(
        run_id=run_id,
        message_ref=current_message_ref,
        schema_version=output.schema_version,
        candidate_validation=(
            CandidateValidationRecord(
                candidate_ref=delta.candidate_id,
                decision=CandidateValidationDecision.ACCEPT,
            ),
        ),
        accepted_delta_refs=(accepted_delta_id,),
        proposed_base_task_state_version=next_move.base_task_state_version,
        validated_task_state_version=1,
        next_move_candidate_ref=next_move_candidate_ref,
    )
    return InitialRequestDecision(
        request_understanding=understanding,
        accepted_delta=accepted_delta,
        input_binding=input_binding,
        task=task,
        request_unit=request_unit,
        next_move_candidate_ref=next_move_candidate_ref,
        next_move_candidate=next_move,
    )


def revalidate_next_move(
    *,
    decision: InitialRequestDecision,
    current_task: TaskRecord,
    current_request_unit: RequestUnitRecord,
    current_input_binding: InputBinding,
) -> RevalidatedNextMove:
    """Bind a candidate to the exact current accepted graph without rewriting it."""

    if type(decision) is not InitialRequestDecision:
        raise RequestProcessingError("canonical initial decision required")
    if (
        type(current_task) is not TaskRecord
        or type(current_request_unit) is not RequestUnitRecord
        or type(current_input_binding) is not InputBinding
    ):
        raise RequestProcessingError("canonical current graph required")
    if current_task.owner_customer_id != decision.task.owner_customer_id:
        raise RequestProcessingError("current Task owner mismatch")
    if (
        current_task.task_id != decision.task.task_id
        or current_request_unit.task_id != current_task.task_id
        or current_request_unit.request_unit_id
        != decision.request_unit.request_unit_id
    ):
        raise RequestProcessingError("current Task graph mismatch")
    if (
        current_task.status is not TaskStatus.ACTIVE
        or current_request_unit.status is not TaskStatus.ACTIVE
        or current_task.state_version != current_request_unit.state_version
        or current_task.state_version != 1
    ):
        raise RequestProcessingError("current Task graph is not ACTIVE/v1")
    if (
        current_input_binding != decision.input_binding
        or current_input_binding.binding_id
        not in current_request_unit.input_binding_refs
        or current_request_unit.input_binding_refs
        != (current_input_binding.binding_id,)
    ):
        raise RequestProcessingError("current InputBinding graph mismatch")

    candidate = decision.next_move_candidate
    if (
        candidate.kind is not NextMoveKind.CALL_TOOL
        or candidate.requested_tool_name is None
        or candidate.arguments is None
    ):
        raise RequestProcessingError("revalidation requires CALL_TOOL candidate")
    if find_trusted_argument_field(candidate.arguments) is not None:
        raise RequestProcessingError("trusted field in model arguments")

    return RevalidatedNextMove(
        run_id=decision.request_understanding.run_id,
        task_id=current_task.task_id,
        request_unit_id=current_request_unit.request_unit_id,
        next_move_candidate_ref=decision.next_move_candidate_ref,
        kind=NextMoveKind.CALL_TOOL,
        requested_provider_tool_name=candidate.requested_tool_name,
        candidate_arguments=candidate.arguments,
        normalized_candidate_order_id=_candidate_order_id_or_none(
            candidate.arguments
        ),
        binding_name=current_input_binding.name,
        binding_normalized_value=current_input_binding.normalized_value,
        argument_binding_refs=(current_input_binding.binding_id,),
        proposed_base_task_state_version=candidate.base_task_state_version,
        validated_task_state_version=current_task.state_version,
    )


from datetime import datetime
from hashlib import sha256
from weakref import ref

from pydantic import (
    BaseModel,
    PrivateAttr,
    ValidationError,
    ValidationInfo,
    model_validator,
)
from pydantic_core import PydanticSerializationError

from .common import require_utc
from .request_understanding import (
    InputCandidate,
    QueryContextualizationCandidateV2,
    ReferenceSourceKindV2,
    RequestUnderstandingInput,
    RequestUnderstandingOutputV2,
    ResolvedReferenceCandidateV2,
    TaskDeltaCandidate,
    UncertaintyReasonCodeV2,
    UncertaintyV2,
)
from .task_state import (
    AcceptedTaskDeltaV2,
    CandidateRejectionReasonCode,
    CandidateValidationRecordV2,
    DurableInputCandidateV2,
    DurableQueryContextualizationCandidateV2,
    DurableResolvedReferenceCandidateV2,
    DurableTaskDeltaCandidateV2,
    RequestUnderstandingAggregateFailureCodeV2,
    RequestUnderstandingAtomicFailureCodeV2,
    RequestUnderstandingRecordV2,
)


class RequestUnderstandingV2Error(ValueError):
    """Bounded v2 validation failure containing only a stable reason code."""

    __slots__ = ("reason_code",)

    reason_code: (
        RequestUnderstandingAggregateFailureCodeV2
        | RequestUnderstandingAtomicFailureCodeV2
    )

    def __init__(
        self,
        reason_code: (
            RequestUnderstandingAggregateFailureCodeV2
            | RequestUnderstandingAtomicFailureCodeV2
        ),
    ) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code.value)


class RequestUnderstandingClosureV2(RuntimePrivateModel):
    record: RequestUnderstandingRecordV2
    accepted_task_deltas: tuple[AcceptedTaskDeltaV2, ...]

    @model_validator(mode="after")
    def accepted_children_are_exact_candidate_projections(self) -> Self:
        if (
            not _is_exact_canonical_model_v2(
                self.record,
                RequestUnderstandingRecordV2,
            )
            or any(
                not _is_exact_canonical_model_v2(
                    child,
                    AcceptedTaskDeltaV2,
                )
                for child in self.accepted_task_deltas
            )
        ):
            raise ValueError("v2 closure requires canonical records")
        candidate_by_id = {
            candidate.candidate_id: candidate
            for candidate in self.record.task_delta_candidates
        }
        decision_by_candidate = {
            decision.candidate_ref: decision
            for decision in self.record.candidate_validation
        }
        accepted_candidate_refs = {
            candidate_ref
            for candidate_ref, decision in decision_by_candidate.items()
            if decision.decision is CandidateValidationDecision.ACCEPT
        }
        child_candidate_refs = tuple(
            child.candidate_ref for child in self.accepted_task_deltas
        )
        child_ids = tuple(
            child.accepted_delta_id for child in self.accepted_task_deltas
        )
        if (
            len(child_candidate_refs) != len(set(child_candidate_refs))
            or len(child_ids) != len(set(child_ids))
            or set(child_candidate_refs) != accepted_candidate_refs
            or set(child_ids) != set(self.record.accepted_delta_refs)
        ):
            raise ValueError(
                "v2 closure children must match the exact accepted Candidate set"
            )
        for child in self.accepted_task_deltas:
            candidate = candidate_by_id.get(child.candidate_ref)
            if (
                candidate is None
                or child.message_ref != self.record.message_ref
                or child.operation is not candidate.operation
                or child.goal_text != candidate.goal_patch
            ):
                raise ValueError(
                    "v2 accepted child must preserve its Candidate projection"
                )
            if (
                len(child.input_binding_refs)
                != len(set(child.input_binding_refs))
            ):
                raise ValueError(
                    "v2 accepted child InputBinding refs must be unique"
                )
            if child.accepted_at != self.record.created_at:
                raise ValueError(
                    "v2 parent and children must share one trusted timestamp"
                )
        return self


def _fail_request_understanding_v2(
    reason_code: (
        RequestUnderstandingAggregateFailureCodeV2
        | RequestUnderstandingAtomicFailureCodeV2
    ),
) -> None:
    raise RequestUnderstandingV2Error(reason_code)


def _runtime_values_match_exactly_v2(left: Any, right: Any) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, BaseModel):
        try:
            declared_fields = set(type(left).model_fields)
            left_state_keys = set(left.__dict__)
            right_state_keys = set(right.__dict__)
            left_fields_set = left.__pydantic_fields_set__
            right_fields_set = right.__pydantic_fields_set__
        except (AttributeError, TypeError):
            return False
        if (
            type(left_fields_set) is not set
            or type(right_fields_set) is not set
            or any(type(key) is not str for key in left_state_keys)
            or any(type(key) is not str for key in right_state_keys)
            or any(type(field) is not str for field in left_fields_set)
            or any(type(field) is not str for field in right_fields_set)
            or left_state_keys != right_state_keys
            or left_fields_set != right_fields_set
            or not left_state_keys.issubset(declared_fields)
            or not left_fields_set.issubset(declared_fields)
            or not right_fields_set.issubset(declared_fields)
        ):
            return False
        left_extra = getattr(left, "__pydantic_extra__", None)
        right_extra = getattr(right, "__pydantic_extra__", None)
        left_private = getattr(left, "__pydantic_private__", None)
        right_private = getattr(right, "__pydantic_private__", None)
        if not _runtime_values_match_exactly_v2(left_extra, right_extra):
            return False
        if not _runtime_values_match_exactly_v2(left_private, right_private):
            return False
        return all(
            hasattr(left, field_name)
            and hasattr(right, field_name)
            and _runtime_values_match_exactly_v2(
                getattr(left, field_name),
                getattr(right, field_name),
            )
            for field_name in type(left).model_fields
        )
    if isinstance(left, Mapping):
        left_keys = tuple(left)
        right_keys = tuple(right)
        return len(left_keys) == len(right_keys) and all(
            _runtime_values_match_exactly_v2(left_key, right_key)
            and _runtime_values_match_exactly_v2(
                left[left_key],
                right[right_key],
            )
            for left_key, right_key in zip(
                left_keys,
                right_keys,
                strict=True,
            )
        )
    if isinstance(left, tuple):
        return len(left) == len(right) and all(
            _runtime_values_match_exactly_v2(left_item, right_item)
            for left_item, right_item in zip(left, right, strict=True)
        )
    return left == right


def _undeclared_model_state_keys_v2(
    value: Any,
    *,
    active_ids: set[int] | None = None,
) -> frozenset[str]:
    visited = active_ids if active_ids is not None else set()
    value_id = id(value)
    if value_id in visited:
        return frozenset()
    if isinstance(value, (BaseModel, tuple, list, Mapping)):
        visited.add(value_id)
    try:
        if isinstance(value, BaseModel):
            declared_fields = set(type(value).model_fields)
            actual_keys = set(value.__dict__)
            try:
                fields_set = set(value.model_fields_set)
            except (AttributeError, TypeError):
                fields_set = {"invalid_model_fields_set"}
            extra = getattr(value, "__pydantic_extra__", None)
            private = getattr(value, "__pydantic_private__", None)
            if isinstance(extra, Mapping):
                actual_keys.update(str(key) for key in extra)
            if isinstance(private, Mapping):
                actual_keys.update(str(key) for key in private)
            undeclared = actual_keys.difference(declared_fields)
            undeclared.update(
                str(key)
                for key in fields_set
                if key not in declared_fields
            )
            for field_name in declared_fields:
                if hasattr(value, field_name):
                    undeclared.update(
                        _undeclared_model_state_keys_v2(
                            getattr(value, field_name),
                            active_ids=visited,
                        )
                    )
            return frozenset(undeclared)
        if isinstance(value, Mapping):
            result: set[str] = set()
            for nested in value.values():
                result.update(
                    _undeclared_model_state_keys_v2(
                        nested,
                        active_ids=visited,
                    )
                )
            return frozenset(result)
        if isinstance(value, (tuple, list)):
            result = set()
            for nested in value:
                result.update(
                    _undeclared_model_state_keys_v2(
                        nested,
                        active_ids=visited,
                    )
                )
            return frozenset(result)
        return frozenset()
    finally:
        visited.discard(value_id)


def _has_trusted_or_private_undeclared_state_v2(value: Any) -> bool:
    for key in _undeclared_model_state_keys_v2(value):
        if key.startswith("_") or find_trusted_argument_field({key: None}):
            return True
    return False


def _canonical_request_input_v2(
    value: object,
) -> RequestUnderstandingInput:
    if type(value) is not RequestUnderstandingInput:
        _fail_request_understanding_v2(
            RequestUnderstandingAggregateFailureCodeV2.MODEL_INPUT_SCHEMA_INVALID
        )
    request_input = value
    if _has_trusted_or_private_undeclared_state_v2(request_input):
        _fail_request_understanding_v2(
            RequestUnderstandingAggregateFailureCodeV2.TRUSTED_OR_PRIVATE_FIELD_PRESENT
        )
    request_input_fields_set: set[str] | None = None
    try:
        request_input_fields_set = set(request_input.model_fields_set)
    except (AttributeError, TypeError):
        pass
    if request_input_fields_set is None:
        _fail_request_understanding_v2(
            RequestUnderstandingAggregateFailureCodeV2.MODEL_INPUT_SCHEMA_INVALID
        )
    if (
        "schema_version" not in request_input_fields_set
        or not hasattr(request_input, "schema_version")
    ):
        _fail_request_understanding_v2(
            RequestUnderstandingAggregateFailureCodeV2.MODEL_INPUT_SCHEMA_INVALID
        )
    if request_input.schema_version != "e2e01-thin-v1":
        _fail_request_understanding_v2(
            RequestUnderstandingAggregateFailureCodeV2.MODEL_SCHEMA_VERSION_INVALID
        )
    payload: dict[str, Any] | None
    try:
        payload = request_input.model_dump(
            mode="json",
            round_trip=True,
            exclude_unset=True,
            warnings="error",
        )
    except (TypeError, ValueError, PydanticSerializationError):
        payload = None
    if payload is None:
        _fail_request_understanding_v2(
            RequestUnderstandingAggregateFailureCodeV2.MODEL_INPUT_SCHEMA_INVALID
        )
    rebuilt: RequestUnderstandingInput | None
    try:
        rebuilt = RequestUnderstandingInput.model_validate(payload)
    except (TypeError, ValueError, ValidationError):
        rebuilt = None
    if rebuilt is None:
        _fail_request_understanding_v2(
            RequestUnderstandingAggregateFailureCodeV2.MODEL_INPUT_SCHEMA_INVALID
        )
    if not _runtime_values_match_exactly_v2(rebuilt, request_input):
        _fail_request_understanding_v2(
            RequestUnderstandingAggregateFailureCodeV2.MODEL_INPUT_SCHEMA_INVALID
        )
    return request_input


def _request_output_nested_types_are_exact_v2(
    output: RequestUnderstandingOutputV2,
) -> bool:
    try:
        contextualization = output.contextualization
        candidates = output.task_delta_candidates
        next_move = output.next_move_candidate
        if (
            type(output.message_ref) is not UUID
            or type(contextualization)
            is not QueryContextualizationCandidateV2
            or type(contextualization.resolved_reference_candidates)
            is not tuple
            or type(contextualization.uncertainties) is not tuple
            or type(contextualization.source_message_refs) is not tuple
            or any(
                type(source_ref) is not UUID
                for source_ref in contextualization.source_message_refs
            )
            or type(candidates) is not tuple
            or type(next_move) is not NextMove
            or type(next_move.kind) is not NextMoveKind
        ):
            return False
        for resolved in contextualization.resolved_reference_candidates:
            if (
                type(resolved) is not ResolvedReferenceCandidateV2
                or type(resolved.source_kind) is not ReferenceSourceKindV2
                or type(resolved.source_ref) is not UUID
                or type(resolved.source_quote) is not str
            ):
                return False
        for uncertainty in contextualization.uncertainties:
            if (
                type(uncertainty) is not UncertaintyV2
                or type(uncertainty.reason_code)
                is not UncertaintyReasonCodeV2
                or type(uncertainty.candidate_values) is not tuple
                or type(uncertainty.source_message_refs) is not tuple
                or any(
                    type(source_ref) is not UUID
                    for source_ref in uncertainty.source_message_refs
                )
            ):
                return False
        for candidate in candidates:
            if (
                type(candidate) is not TaskDeltaCandidate
                or type(candidate.candidate_id) is not UUID
                or type(candidate.operation) is not TaskDeltaOperation
                or type(candidate.input_candidates) is not tuple
            ):
                return False
            for input_candidate in candidate.input_candidates:
                if (
                    type(input_candidate) is not InputCandidate
                    or type(input_candidate.authority) is not InputAuthority
                    or type(input_candidate.source_kind) is not InputSourceKind
                    or type(input_candidate.source_ref) is not UUID
                    or type(input_candidate.source_quote) is not str
                ):
                    return False
    except (AttributeError, TypeError):
        return False
    return True


def _canonical_request_output_v2(
    value: object,
) -> RequestUnderstandingOutputV2:
    if type(value) is not RequestUnderstandingOutputV2:
        _fail_request_understanding_v2(
            RequestUnderstandingAggregateFailureCodeV2.MODEL_OUTPUT_SCHEMA_INVALID
        )
    output = value
    if _has_trusted_or_private_undeclared_state_v2(output):
        _fail_request_understanding_v2(
            RequestUnderstandingAggregateFailureCodeV2.TRUSTED_OR_PRIVATE_FIELD_PRESENT
        )
    if not hasattr(output, "schema_version"):
        _fail_request_understanding_v2(
            RequestUnderstandingAggregateFailureCodeV2.MODEL_OUTPUT_SCHEMA_INVALID
        )
    if output.schema_version != "e2e01-thin-v2":
        _fail_request_understanding_v2(
            RequestUnderstandingAggregateFailureCodeV2.MODEL_SCHEMA_VERSION_INVALID
        )
    if not _request_output_nested_types_are_exact_v2(output):
        _fail_request_understanding_v2(
            RequestUnderstandingAggregateFailureCodeV2.MODEL_OUTPUT_SCHEMA_INVALID
        )
    payload: dict[str, Any] | None
    try:
        payload = output.model_dump(
            mode="json",
            round_trip=True,
            exclude_unset=True,
            warnings="error",
        )
    except (TypeError, ValueError, PydanticSerializationError):
        payload = None
    if payload is None:
        _fail_request_understanding_v2(
            RequestUnderstandingAggregateFailureCodeV2.MODEL_OUTPUT_SCHEMA_INVALID
        )
    if find_trusted_argument_field(payload) is not None:
        _fail_request_understanding_v2(
            RequestUnderstandingAggregateFailureCodeV2.TRUSTED_OR_PRIVATE_FIELD_PRESENT
        )
    rebuilt: RequestUnderstandingOutputV2 | None
    try:
        rebuilt = RequestUnderstandingOutputV2.model_validate(payload)
    except (TypeError, ValueError, ValidationError):
        rebuilt = None
    if rebuilt is None:
        _fail_request_understanding_v2(
            RequestUnderstandingAggregateFailureCodeV2.MODEL_OUTPUT_SCHEMA_INVALID
        )
    if not _runtime_values_match_exactly_v2(rebuilt, output):
        _fail_request_understanding_v2(
            RequestUnderstandingAggregateFailureCodeV2.MODEL_OUTPUT_SCHEMA_INVALID
        )
    return output


def _canonical_candidate_validation_v2(
    values: object,
) -> tuple[CandidateValidationRecordV2, ...]:
    if type(values) is not tuple:
        _fail_request_understanding_v2(
            RequestUnderstandingAtomicFailureCodeV2.DURABLE_CLOSURE_COMMIT_FAILED
        )
    rebuilt_values: list[CandidateValidationRecordV2] = []
    for value in values:
        if type(value) is not CandidateValidationRecordV2:
            _fail_request_understanding_v2(
                RequestUnderstandingAtomicFailureCodeV2.DURABLE_CLOSURE_COMMIT_FAILED
            )
        if _has_trusted_or_private_undeclared_state_v2(value):
            _fail_request_understanding_v2(
                RequestUnderstandingAggregateFailureCodeV2.TRUSTED_OR_PRIVATE_FIELD_PRESENT
            )
        rebuilt: CandidateValidationRecordV2 | None = None
        try:
            rebuilt = CandidateValidationRecordV2.model_validate(
                value.model_dump(
                    mode="json",
                    round_trip=True,
                    exclude_unset=True,
                    warnings="error",
                )
            )
        except (
            TypeError,
            ValueError,
            ValidationError,
            PydanticSerializationError,
        ):
            pass
        if rebuilt is None:
            _fail_request_understanding_v2(
                RequestUnderstandingAtomicFailureCodeV2.DURABLE_CLOSURE_COMMIT_FAILED
            )
        if not _runtime_values_match_exactly_v2(rebuilt, value):
            _fail_request_understanding_v2(
                RequestUnderstandingAtomicFailureCodeV2.DURABLE_CLOSURE_COMMIT_FAILED
            )
        rebuilt_values.append(value)
    return tuple(rebuilt_values)


def _canonical_accepted_task_deltas_v2(
    values: object,
) -> tuple[AcceptedTaskDeltaV2, ...]:
    if type(values) is not tuple:
        _fail_request_understanding_v2(
            RequestUnderstandingAtomicFailureCodeV2.DURABLE_CLOSURE_COMMIT_FAILED
        )
    rebuilt_values: list[AcceptedTaskDeltaV2] = []
    for value in values:
        if type(value) is not AcceptedTaskDeltaV2:
            _fail_request_understanding_v2(
                RequestUnderstandingAtomicFailureCodeV2.DURABLE_CLOSURE_COMMIT_FAILED
            )
        if _has_trusted_or_private_undeclared_state_v2(value):
            _fail_request_understanding_v2(
                RequestUnderstandingAggregateFailureCodeV2.TRUSTED_OR_PRIVATE_FIELD_PRESENT
            )
        rebuilt: AcceptedTaskDeltaV2 | None = None
        try:
            rebuilt = AcceptedTaskDeltaV2.model_validate(
                value.model_dump(
                    mode="json",
                    round_trip=True,
                    exclude_unset=True,
                    warnings="error",
                )
            )
        except (
            TypeError,
            ValueError,
            ValidationError,
            PydanticSerializationError,
        ):
            pass
        if rebuilt is None:
            _fail_request_understanding_v2(
                RequestUnderstandingAtomicFailureCodeV2.DURABLE_CLOSURE_COMMIT_FAILED
            )
        if not _runtime_values_match_exactly_v2(rebuilt, value):
            _fail_request_understanding_v2(
                RequestUnderstandingAtomicFailureCodeV2.DURABLE_CLOSURE_COMMIT_FAILED
            )
        rebuilt_values.append(value)
    return tuple(rebuilt_values)


def _authoritative_message_v2(
    authoritative_messages: Mapping[UUID, str],
    source_ref: UUID,
) -> str:
    message: object | None = None
    try:
        message = authoritative_messages[source_ref]
    except (KeyError, TypeError):
        pass
    if type(message) is not str or not message:
        _fail_request_understanding_v2(
            RequestUnderstandingAggregateFailureCodeV2.SOURCE_PROVENANCE_INVALID
        )
    return message


def _exact_source_span_v2(
    *,
    authoritative_message: str,
    source_quote: str,
    candidate_value: str,
) -> tuple[int, int, str]:
    if type(source_quote) is not str or not source_quote:
        _fail_request_understanding_v2(
            RequestUnderstandingAggregateFailureCodeV2.SOURCE_PROVENANCE_INVALID
        )
    if source_quote == authoritative_message:
        _fail_request_understanding_v2(
            RequestUnderstandingAggregateFailureCodeV2.SOURCE_PROVENANCE_INVALID
        )
    occurrences: list[int] = []
    search_from = 0
    while True:
        position = authoritative_message.find(source_quote, search_from)
        if position < 0:
            break
        occurrences.append(position)
        if len(occurrences) > 1:
            break
        search_from = position + 1
    if len(occurrences) != 1:
        _fail_request_understanding_v2(
            RequestUnderstandingAggregateFailureCodeV2.SOURCE_PROVENANCE_INVALID
        )
    normalized_candidate: str | None = None
    try:
        normalized_candidate = _normalize_order_id(candidate_value)
    except RequestProcessingError:
        pass
    if normalized_candidate is None:
        if (
            type(candidate_value) is not str
            or not candidate_value
            or candidate_value not in source_quote
        ):
            _fail_request_understanding_v2(
                RequestUnderstandingAggregateFailureCodeV2.SOURCE_PROVENANCE_INVALID
            )
    else:
        if not _source_quote_contains_exact_order_id(
            source_quote,
            normalized_candidate,
        ):
            _fail_request_understanding_v2(
                RequestUnderstandingAggregateFailureCodeV2.SOURCE_PROVENANCE_INVALID
            )
    start = occurrences[0]
    end = start + len(source_quote)
    exact_slice = authoritative_message[start:end]
    return start, end, sha256(exact_slice.encode("utf-8")).hexdigest()


def _project_resolved_reference_v2(
    candidate: ResolvedReferenceCandidateV2,
    authoritative_messages: Mapping[UUID, str],
) -> DurableResolvedReferenceCandidateV2:
    message = _authoritative_message_v2(
        authoritative_messages,
        candidate.source_ref,
    )
    start, end, quote_hash = _exact_source_span_v2(
        authoritative_message=message,
        source_quote=candidate.source_quote,
        candidate_value=candidate.candidate_value,
    )
    projected: DurableResolvedReferenceCandidateV2 | None = None
    try:
        projected = DurableResolvedReferenceCandidateV2(
            name=candidate.name,
            candidate_value=candidate.candidate_value,
            source_kind=candidate.source_kind,
            source_ref=candidate.source_ref,
            source_span_start=start,
            source_span_end_exclusive=end,
            source_quote_sha256=quote_hash,
            confidence=candidate.confidence,
        )
    except (TypeError, ValueError, ValidationError):
        pass
    if projected is None:
        _fail_request_understanding_v2(
            RequestUnderstandingAggregateFailureCodeV2.MODEL_OUTPUT_SCHEMA_INVALID
        )
    return projected


def _project_input_candidate_v2(
    candidate: InputCandidate,
    authoritative_messages: Mapping[UUID, str],
) -> DurableInputCandidateV2:
    message = _authoritative_message_v2(
        authoritative_messages,
        candidate.source_ref,
    )
    start, end, quote_hash = _exact_source_span_v2(
        authoritative_message=message,
        source_quote=candidate.source_quote,
        candidate_value=candidate.candidate_value,
    )
    projected: DurableInputCandidateV2 | None = None
    try:
        projected = DurableInputCandidateV2(
            name=candidate.name,
            candidate_value=candidate.candidate_value,
            semantic_role=candidate.semantic_role,
            authority=candidate.authority,
            source_kind=candidate.source_kind,
            source_ref=candidate.source_ref,
            source_span_start=start,
            source_span_end_exclusive=end,
            source_quote_sha256=quote_hash,
            confidence=candidate.confidence,
        )
    except (TypeError, ValueError, ValidationError):
        pass
    if projected is None:
        _fail_request_understanding_v2(
            RequestUnderstandingAggregateFailureCodeV2.MODEL_OUTPUT_SCHEMA_INVALID
        )
    return projected


def _project_contextualization_v2(
    contextualization: QueryContextualizationCandidateV2,
    authoritative_messages: Mapping[UUID, str],
) -> DurableQueryContextualizationCandidateV2:
    for source_ref in contextualization.source_message_refs:
        _authoritative_message_v2(authoritative_messages, source_ref)
    projected_references = tuple(
        _project_resolved_reference_v2(
            candidate,
            authoritative_messages,
        )
        for candidate in contextualization.resolved_reference_candidates
    )
    projected: DurableQueryContextualizationCandidateV2 | None = None
    try:
        projected = DurableQueryContextualizationCandidateV2(
            text=contextualization.text,
            resolved_reference_candidates=projected_references,
            uncertainties=contextualization.uncertainties,
            source_message_refs=contextualization.source_message_refs,
        )
    except (TypeError, ValueError, ValidationError):
        pass
    if projected is None:
        _fail_request_understanding_v2(
            RequestUnderstandingAggregateFailureCodeV2.MODEL_OUTPUT_SCHEMA_INVALID
        )
    return projected


def _project_task_delta_v2(
    candidate: TaskDeltaCandidate,
    authoritative_messages: Mapping[UUID, str],
) -> DurableTaskDeltaCandidateV2:
    projected_inputs = tuple(
        _project_input_candidate_v2(
            input_candidate,
            authoritative_messages,
        )
        for input_candidate in candidate.input_candidates
    )
    projected: DurableTaskDeltaCandidateV2 | None = None
    try:
        projected = DurableTaskDeltaCandidateV2(
            candidate_id=candidate.candidate_id,
            operation=candidate.operation,
            goal_patch=candidate.goal_patch,
            input_candidates=projected_inputs,
            confidence=candidate.confidence,
        )
    except (TypeError, ValueError, ValidationError):
        pass
    if projected is None:
        _fail_request_understanding_v2(
            RequestUnderstandingAggregateFailureCodeV2.MODEL_OUTPUT_SCHEMA_INVALID
        )
    return projected


def _validate_input_visible_source_scope_v2(
    *,
    request_input: RequestUnderstandingInput,
    output: RequestUnderstandingOutputV2,
) -> None:
    current_ref = request_input.message_ref
    recent_refs = set(request_input.recent_message_refs)
    visible_refs = {current_ref, *recent_refs}
    if any(
        source_ref not in visible_refs
        for source_ref in output.contextualization.source_message_refs
    ):
        _fail_request_understanding_v2(
            RequestUnderstandingAggregateFailureCodeV2.SOURCE_PROVENANCE_INVALID
        )
    for resolved in output.contextualization.resolved_reference_candidates:
        if (
            resolved.source_kind is ReferenceSourceKindV2.CURRENT_MESSAGE
            and resolved.source_ref != current_ref
        ) or (
            resolved.source_kind is ReferenceSourceKindV2.RECENT_MESSAGE
            and (
                resolved.source_ref == current_ref
                or resolved.source_ref not in recent_refs
            )
        ):
            _fail_request_understanding_v2(
                RequestUnderstandingAggregateFailureCodeV2.SOURCE_PROVENANCE_INVALID
            )


def _validate_durable_closure_v2(
    *,
    output: RequestUnderstandingOutputV2,
    candidate_validation: tuple[CandidateValidationRecordV2, ...],
    accepted_task_deltas: tuple[AcceptedTaskDeltaV2, ...],
    now: datetime,
) -> None:
    emitted_ids = [
        candidate.candidate_id for candidate in output.task_delta_candidates
    ]
    validation_refs = [
        validation.candidate_ref for validation in candidate_validation
    ]
    if (
        len(validation_refs) != len(set(validation_refs))
        or set(validation_refs) != set(emitted_ids)
    ):
        _fail_request_understanding_v2(
            RequestUnderstandingAtomicFailureCodeV2.DURABLE_CLOSURE_COMMIT_FAILED
        )
    accepted_candidate_refs = {
        validation.candidate_ref
        for validation in candidate_validation
        if validation.decision is CandidateValidationDecision.ACCEPT
    }
    child_candidate_refs = [
        child.candidate_ref for child in accepted_task_deltas
    ]
    accepted_delta_ids = [
        child.accepted_delta_id for child in accepted_task_deltas
    ]
    child_pairs = [
        (child.accepted_delta_id, child.task_id)
        for child in accepted_task_deltas
    ]
    if (
        len(child_candidate_refs) != len(set(child_candidate_refs))
        or set(child_candidate_refs) != accepted_candidate_refs
        or len(accepted_delta_ids) != len(set(accepted_delta_ids))
        or len(child_pairs) != len(set(child_pairs))
    ):
        _fail_request_understanding_v2(
            RequestUnderstandingAtomicFailureCodeV2.DURABLE_CLOSURE_COMMIT_FAILED
        )
    emitted_by_id = {
        candidate.candidate_id: candidate
        for candidate in output.task_delta_candidates
    }
    child_by_candidate = {
        child.candidate_ref: child for child in accepted_task_deltas
    }
    for child in accepted_task_deltas:
        emitted = emitted_by_id.get(child.candidate_ref)
        if (
            emitted is None
            or child.message_ref != output.message_ref
            or child.accepted_at != now
            or child.operation is not emitted.operation
            or len(child.input_binding_refs)
            != len(set(child.input_binding_refs))
        ):
            _fail_request_understanding_v2(
                RequestUnderstandingAtomicFailureCodeV2.DURABLE_CLOSURE_COMMIT_FAILED
            )
    last_version_by_task: dict[UUID, int] = {}
    for candidate in output.task_delta_candidates:
        child = child_by_candidate.get(candidate.candidate_id)
        if child is None:
            continue
        previous_version = last_version_by_task.get(child.task_id)
        if previous_version is None:
            if child.base_task_state_version is not None:
                _fail_request_understanding_v2(
                    RequestUnderstandingAtomicFailureCodeV2.DURABLE_CLOSURE_COMMIT_FAILED
                )
        elif (
            child.base_task_state_version != previous_version
            or child.result_task_state_version != previous_version + 1
        ):
            _fail_request_understanding_v2(
                RequestUnderstandingAtomicFailureCodeV2.DURABLE_CLOSURE_COMMIT_FAILED
            )
        last_version_by_task[child.task_id] = child.result_task_state_version


def build_request_understanding_closure_v2(
    *,
    request_input: RequestUnderstandingInput,
    output: RequestUnderstandingOutputV2,
    authoritative_messages: Mapping[UUID, str],
    request_understanding_record_id: UUID,
    candidate_validation: tuple[CandidateValidationRecordV2, ...],
    accepted_task_deltas: tuple[AcceptedTaskDeltaV2, ...],
    proposed_base_task_state_version: PositiveStateVersion | None,
    validated_task_state_version: PositiveStateVersion | None,
    next_move_candidate_ref: UUID | None,
    now: datetime,
) -> RequestUnderstandingClosureV2:
    """Build one complete, quote-free v2 durable closure or fail bounded."""

    canonical_input = _canonical_request_input_v2(request_input)
    canonical_output = _canonical_request_output_v2(output)
    canonical_validation = _canonical_candidate_validation_v2(
        candidate_validation
    )
    canonical_children = _canonical_accepted_task_deltas_v2(
        accepted_task_deltas
    )
    if not isinstance(authoritative_messages, Mapping):
        _fail_request_understanding_v2(
            RequestUnderstandingAggregateFailureCodeV2.SOURCE_PROVENANCE_INVALID
        )
    if (
        type(request_understanding_record_id) is not UUID
        or (
            next_move_candidate_ref is not None
            and type(next_move_candidate_ref) is not UUID
        )
        or type(now) is not datetime
    ):
        _fail_request_understanding_v2(
            RequestUnderstandingAtomicFailureCodeV2.DURABLE_CLOSURE_COMMIT_FAILED
        )
    now_is_utc = True
    try:
        require_utc(now, field_name="now")
    except (TypeError, ValueError):
        now_is_utc = False
    if not now_is_utc:
        _fail_request_understanding_v2(
            RequestUnderstandingAtomicFailureCodeV2.DURABLE_CLOSURE_COMMIT_FAILED
        )
    if canonical_input.message_ref != canonical_output.message_ref:
        _fail_request_understanding_v2(
            RequestUnderstandingAggregateFailureCodeV2.SOURCE_PROVENANCE_INVALID
        )
    _validate_input_visible_source_scope_v2(
        request_input=canonical_input,
        output=canonical_output,
    )
    current_message = _authoritative_message_v2(
        authoritative_messages,
        canonical_input.message_ref,
    )
    if current_message != canonical_input.original_query:
        _fail_request_understanding_v2(
            RequestUnderstandingAggregateFailureCodeV2.SOURCE_PROVENANCE_INVALID
        )
    if (
        proposed_base_task_state_version
        != canonical_output.next_move_candidate.base_task_state_version
    ):
        _fail_request_understanding_v2(
            RequestUnderstandingAtomicFailureCodeV2.DURABLE_CLOSURE_COMMIT_FAILED
        )
    if next_move_candidate_ref is None and (
        proposed_base_task_state_version is not None
        or validated_task_state_version is not None
    ):
        _fail_request_understanding_v2(
            RequestUnderstandingAtomicFailureCodeV2.DURABLE_CLOSURE_COMMIT_FAILED
        )

    projected_contextualization = _project_contextualization_v2(
        canonical_output.contextualization,
        authoritative_messages,
    )
    projected_candidates = tuple(
        _project_task_delta_v2(
            candidate,
            authoritative_messages,
        )
        for candidate in canonical_output.task_delta_candidates
    )
    _validate_durable_closure_v2(
        output=canonical_output,
        candidate_validation=canonical_validation,
        accepted_task_deltas=canonical_children,
        now=now,
    )
    closure: RequestUnderstandingClosureV2 | None = None
    try:
        record = RequestUnderstandingRecordV2(
            request_understanding_record_id=request_understanding_record_id,
            run_id=canonical_input.run_id,
            message_ref=canonical_output.message_ref,
            schema_version="request_understanding_record.p0.v2",
            model_input_schema_version=canonical_input.schema_version,
            model_output_schema_version=canonical_output.schema_version,
            contextualization=projected_contextualization,
            task_delta_candidates=projected_candidates,
            candidate_validation=canonical_validation,
            accepted_delta_refs=tuple(
                child.accepted_delta_id for child in canonical_children
            ),
            proposed_base_task_state_version=proposed_base_task_state_version,
            validated_task_state_version=validated_task_state_version,
            next_move_candidate_ref=next_move_candidate_ref,
            created_at=now,
        )
        closure = RequestUnderstandingClosureV2(
            record=record,
            accepted_task_deltas=canonical_children,
        )
    except (TypeError, ValueError, ValidationError):
        pass
    if closure is None:
        _fail_request_understanding_v2(
            RequestUnderstandingAtomicFailureCodeV2.DURABLE_CLOSURE_COMMIT_FAILED
        )
    return closure


def _is_exact_canonical_model_v2(
    value: object,
    expected_type: type[BaseModel],
) -> bool:
    if type(value) is not expected_type:
        return False
    if expected_type is globals().get(
        "InitialRequestRoutableTaskGraphDecisionV2"
    ):
        verifier = globals().get(
            "_initial_routable_decision_seal_matches_v2"
        )
        return callable(verifier) and verifier(value)
    payload: dict[str, Any] | None
    try:
        payload = value.model_dump(
            mode="json",
            round_trip=True,
            exclude_unset=True,
            warnings="error",
        )
    except (AttributeError, TypeError, ValueError, PydanticSerializationError):
        payload = None
    if payload is None:
        return False
    try:
        rebuilt = expected_type.model_validate(payload)
    except (TypeError, ValueError, ValidationError):
        return False
    return _runtime_values_match_exactly_v2(rebuilt, value)


class InitialTaskIdentityAllocationV2(RuntimePrivateModel):
    """Trusted identities reserved for one emitted Candidate."""

    candidate_ref: UUID
    accepted_delta_id: UUID
    task_id: UUID
    request_unit_id: UUID
    binding_id: UUID

    @model_validator(mode="after")
    def generated_identities_are_distinct(self) -> Self:
        generated = (
            self.accepted_delta_id,
            self.task_id,
            self.request_unit_id,
            self.binding_id,
        )
        if len(generated) != len(set(generated)):
            raise ValueError("initial generated identities must be unique")
        if self.candidate_ref in generated:
            raise ValueError("candidate identity cannot be reused as a record identity")
        return self


class InitialAcceptedTaskGraphV2(RuntimePrivateModel):
    """One accepted v2 child and its exact clean initial Task graph."""

    accepted_delta: AcceptedTaskDeltaV2
    input_binding: InputBinding
    task: TaskRecord
    request_unit: RequestUnitRecord

    @model_validator(mode="after")
    def graph_is_exact_initial_projection(self) -> Self:
        if (
            not _is_exact_canonical_model_v2(
                self.accepted_delta,
                AcceptedTaskDeltaV2,
            )
            or not _is_exact_canonical_model_v2(
                self.input_binding,
                InputBinding,
            )
            or not _is_exact_canonical_model_v2(self.task, TaskRecord)
            or not _is_exact_canonical_model_v2(
                self.request_unit,
                RequestUnitRecord,
            )
        ):
            raise ValueError("initial Task graph requires canonical records")

        child = self.accepted_delta
        binding = self.input_binding
        task = self.task
        unit = self.request_unit
        identities = (
            child.accepted_delta_id,
            binding.binding_id,
            task.task_id,
            unit.request_unit_id,
        )
        if len(identities) != len(set(identities)):
            raise ValueError("initial Task graph identities must be unique")
        if (
            child.operation is not TaskDeltaOperation.ADD_GOAL
            or child.task_id != task.task_id
            or child.base_task_state_version is not None
            or child.result_task_state_version != 1
            or child.input_binding_refs != (binding.binding_id,)
        ):
            raise ValueError("accepted delta must define one initial Task effect")
        if (
            binding.name != "order_id"
            or binding.authority is not InputAuthority.USER_CLAIM
            or binding.validation_status is not InputValidationStatus.ACCEPTED
            or binding.confirmed_by_user is not True
            or binding.source_refs != (child.message_ref,)
            or binding.supersedes is not None
        ):
            raise ValueError("initial InputBinding must bind the accepted message")
        if (
            task.status is not TaskStatus.ACTIVE
            or task.state_version != 1
            or task.last_outcome_ref is not None
        ):
            raise ValueError("initial Task must be clean ACTIVE/v1")
        if (
            unit.task_id != task.task_id
            or unit.goal_text != child.goal_text
            or unit.goal_source_refs != (child.message_ref,)
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
            raise ValueError("initial RequestUnit must be a clean exact projection")
        timestamps = {
            child.accepted_at,
            binding.created_at,
            binding.updated_at,
            task.created_at,
            task.updated_at,
            unit.created_at,
            unit.updated_at,
        }
        if len(timestamps) != 1:
            raise ValueError("initial Task graph must use one trusted timestamp")
        return self


def _validate_initial_graph_candidate_projection_v2(
    *,
    record: RequestUnderstandingRecordV2,
    graph: InitialAcceptedTaskGraphV2,
) -> None:
    child = graph.accepted_delta
    matching_candidates = tuple(
        candidate
        for candidate in record.task_delta_candidates
        if candidate.candidate_id == child.candidate_ref
    )
    if len(matching_candidates) != 1:
        raise ValueError("initial graph must bind one accepted Candidate")
    candidate = matching_candidates[0]
    if (
        child.message_ref != record.message_ref
        or child.operation is not candidate.operation
        or child.goal_text != candidate.goal_patch
        or len(candidate.input_candidates) != 1
    ):
        raise ValueError(
            "initial graph must preserve its accepted Candidate projection"
        )
    candidate_input = candidate.input_candidates[0]
    try:
        normalized_candidate_value = _normalize_order_id(
            candidate_input.candidate_value
        )
    except RequestProcessingError:
        raise ValueError(
            "initial graph Candidate InputBinding projection is invalid"
        ) from None
    binding = graph.input_binding
    if (
        binding.name != candidate_input.name
        or binding.normalized_value != normalized_candidate_value
        or binding.authority is not candidate_input.authority
        or binding.source_refs != (candidate_input.source_ref,)
    ):
        raise ValueError(
            "initial graph Candidate InputBinding projection mismatch"
        )


def _validate_initial_graph_identity_closure_v2(
    *,
    record: RequestUnderstandingRecordV2,
    graphs: tuple[InitialAcceptedTaskGraphV2, ...],
) -> None:
    identities = [
        record.request_understanding_record_id,
        *(
            identity
            for graph in graphs
            for identity in (
                graph.accepted_delta.accepted_delta_id,
                graph.task.task_id,
                graph.request_unit.request_unit_id,
                graph.input_binding.binding_id,
            )
        ),
    ]
    if record.next_move_candidate_ref is not None:
        identities.append(record.next_move_candidate_ref)
    if len(identities) != len(set(identities)):
        raise ValueError(
            "initial decision record identities must be globally unique"
        )
    if any(
        graph.accepted_delta.base_task_state_version is not None
        or graph.accepted_delta.result_task_state_version != 1
        or graph.accepted_delta.task_id != graph.task.task_id
        or graph.task.state_version != 1
        or graph.request_unit.state_version != 1
        for graph in graphs
    ):
        raise ValueError(
            "each initial accepted Candidate requires one independent "
            "base-null/result-1 Task effect"
        )


class InitialRequestNoTaskDecisionV2(RuntimePrivateModel):
    """A valid zero/all-reject closure with no Task effect."""

    closure: RequestUnderstandingClosureV2

    @model_validator(mode="after")
    def closure_has_no_task_effect(self) -> Self:
        if not _is_exact_canonical_model_v2(
            self.closure,
            RequestUnderstandingClosureV2,
        ):
            raise ValueError("no-task decision requires a canonical closure")
        record = self.closure.record
        if (
            self.closure.accepted_task_deltas
            or record.accepted_delta_refs
            or any(
                decision.decision is CandidateValidationDecision.ACCEPT
                for decision in record.candidate_validation
            )
            or record.next_move_candidate_ref is not None
            or record.proposed_base_task_state_version is not None
            or record.validated_task_state_version is not None
        ):
            raise ValueError("no-task decision cannot carry a Task effect")
        return self


def _validate_initial_routable_decision_fields_v2(
    *,
    closure: RequestUnderstandingClosureV2,
    task_graph: InitialAcceptedTaskGraphV2,
    next_move_candidate_ref: UUID,
    next_move_candidate: NextMove,
) -> None:
    if (
        not _is_exact_canonical_model_v2(
            closure,
            RequestUnderstandingClosureV2,
        )
        or not _is_exact_canonical_model_v2(
            task_graph,
            InitialAcceptedTaskGraphV2,
        )
        or not _is_exact_canonical_model_v2(
            next_move_candidate,
            NextMove,
        )
        or type(next_move_candidate_ref) is not UUID
    ):
        raise ValueError("routable decision requires canonical records")
    record = closure.record
    if (
        len(record.task_delta_candidates) != 1
        or len(record.candidate_validation) != 1
        or record.candidate_validation[0].decision
        is not CandidateValidationDecision.ACCEPT
        or closure.accepted_task_deltas != (task_graph.accepted_delta,)
        or record.accepted_delta_refs
        != (task_graph.accepted_delta.accepted_delta_id,)
        or record.next_move_candidate_ref != next_move_candidate_ref
        or record.proposed_base_task_state_version
        != next_move_candidate.base_task_state_version
        or record.validated_task_state_version != 1
        or task_graph.accepted_delta.candidate_ref
        != record.task_delta_candidates[0].candidate_id
    ):
        raise ValueError("routable decision must close one accepted Candidate")
    _validate_initial_graph_candidate_projection_v2(
        record=record,
        graph=task_graph,
    )
    _validate_initial_graph_identity_closure_v2(
        record=record,
        graphs=(task_graph,),
    )


class InitialRequestRoutableTaskGraphDecisionV2(RuntimePrivateModel):
    """Exact-one emitted/accepted result retaining the shared NextMove."""

    _reducer_decision_seal: object = PrivateAttr()

    closure: RequestUnderstandingClosureV2
    task_graph: InitialAcceptedTaskGraphV2
    next_move_candidate_ref: UUID
    next_move_candidate: NextMove

    def __setattr__(self, name: str, value: Any) -> None:
        private_state = getattr(self, "__pydantic_private__", None)
        if (
            name == "_reducer_decision_seal"
            and isinstance(private_state, dict)
            and name in private_state
        ):
            raise TypeError("Reducer decision seal is immutable")
        if name == "_reducer_next_move_fingerprint":
            raise TypeError("Reducer decision seal is immutable")
        super().__setattr__(name, value)

    def __delattr__(self, name: str) -> None:
        if name in {
            "_reducer_decision_seal",
            "_reducer_next_move_fingerprint",
        }:
            raise TypeError("Reducer decision seal is immutable")
        super().__delattr__(name)

    @model_validator(mode="after")
    def result_is_exact_one_and_next_move_bound(
        self,
        info: ValidationInfo,
    ) -> Self:
        _validate_initial_routable_decision_fields_v2(
            closure=self.closure,
            task_graph=self.task_graph,
            next_move_candidate_ref=self.next_move_candidate_ref,
            next_move_candidate=self.next_move_candidate,
        )
        authorizer = globals().get(
            "_initial_routable_decision_construction_is_authorized_v2"
        )
        if not callable(authorizer) or not authorizer(self, info.context):
            raise ValueError(
                "routable decision must be constructed by Reducer"
            )
        return self


def _model_fields_set_manifest_v2(
    value: Any,
    *,
    active_ids: set[int] | None = None,
) -> tuple[tuple[str, tuple[str, ...]], ...] | None:
    if not isinstance(value, (BaseModel, tuple, Mapping)):
        return ()
    visited = active_ids if active_ids is not None else set()
    value_id = id(value)
    if value_id in visited:
        return None
    visited.add(value_id)
    try:
        if isinstance(value, BaseModel):
            fields_set = getattr(value, "__pydantic_fields_set__", None)
            declared_fields = tuple(type(value).model_fields)
            if (
                type(fields_set) is not set
                or any(type(field) is not str for field in fields_set)
                or not fields_set.issubset(declared_fields)
            ):
                return None
            manifest: list[tuple[str, tuple[str, ...]]] = [
                (
                    f"{type(value).__module__}.{type(value).__qualname__}",
                    tuple(sorted(fields_set)),
                )
            ]
            for field_name in declared_fields:
                if not hasattr(value, field_name):
                    return None
                child_manifest = _model_fields_set_manifest_v2(
                    getattr(value, field_name),
                    active_ids=visited,
                )
                if child_manifest is None:
                    return None
                manifest.extend(child_manifest)
            return tuple(manifest)
        manifest = []
        values = value if isinstance(value, tuple) else value.values()
        for child in values:
            child_manifest = _model_fields_set_manifest_v2(
                child,
                active_ids=visited,
            )
            if child_manifest is None:
                return None
            manifest.extend(child_manifest)
        return tuple(manifest)
    finally:
        visited.remove(value_id)


def _initial_routable_decision_fields_payload_v2(
    *,
    closure: RequestUnderstandingClosureV2,
    task_graph: InitialAcceptedTaskGraphV2,
    next_move_candidate_ref: UUID,
    next_move_candidate: NextMove,
) -> bytes | None:
    try:
        _validate_initial_routable_decision_fields_v2(
            closure=closure,
            task_graph=task_graph,
            next_move_candidate_ref=next_move_candidate_ref,
            next_move_candidate=next_move_candidate,
        )
        closure_json = closure.model_dump_json(
            round_trip=True, warnings="error"
        )
        task_graph_json = task_graph.model_dump_json(
            round_trip=True, warnings="error"
        )
        next_move_json = next_move_candidate.model_dump_json(
            round_trip=True, warnings="error"
        )
        fields_set_manifest = _model_fields_set_manifest_v2(
            (closure, task_graph, next_move_candidate)
        )
    except (
        AttributeError,
        TypeError,
        ValueError,
        ValidationError,
        PydanticSerializationError,
    ):
        return None
    if fields_set_manifest is None:
        return None
    return (
        b"mini-agent:initial-routable-task-graph-decision-v2:"
        + closure_json.encode("utf-8")
        + b"\x00"
        + task_graph_json.encode("utf-8")
        + b"\x00"
        + str(next_move_candidate_ref).encode("ascii")
        + b"\x00"
        + next_move_json.encode("utf-8")
        + b"\x00"
        + repr(fields_set_manifest).encode("utf-8")
    )


def _initial_routable_decision_payload_v2(
    value: object,
) -> bytes | None:
    if type(value) is not InitialRequestRoutableTaskGraphDecisionV2:
        return None
    declared_fields = set(type(value).model_fields)
    try:
        fields_set = value.__pydantic_fields_set__
        state_keys = set(value.__dict__)
        if (
            state_keys != declared_fields
            or type(fields_set) is not set
            or any(type(key) is not str for key in state_keys)
            or any(type(field) is not str for field in fields_set)
            or fields_set != declared_fields
            or value.__pydantic_extra__ is not None
        ):
            return None
    except (AttributeError, TypeError):
        return None
    return _initial_routable_decision_fields_payload_v2(
        closure=value.closure,
        task_graph=value.task_graph,
        next_move_candidate_ref=value.next_move_candidate_ref,
        next_move_candidate=value.next_move_candidate,
    )


class InitialRequestUnroutedTaskGraphsDecisionV2(RuntimePrivateModel):
    """Partial or multi-accepted closure with no shared NextMove."""

    closure: RequestUnderstandingClosureV2
    task_graphs: Annotated[
        tuple[InitialAcceptedTaskGraphV2, ...],
        Field(min_length=1),
    ]

    @model_validator(mode="after")
    def result_preserves_all_task_effects_without_next_move(self) -> Self:
        if not _is_exact_canonical_model_v2(
            self.closure,
            RequestUnderstandingClosureV2,
        ) or any(
            not _is_exact_canonical_model_v2(
                graph,
                InitialAcceptedTaskGraphV2,
            )
            for graph in self.task_graphs
        ):
            raise ValueError("unrouted decision requires canonical records")
        record = self.closure.record
        accepted_count = sum(
            decision.decision is CandidateValidationDecision.ACCEPT
            for decision in record.candidate_validation
        )
        if (
            accepted_count < 1
            or len(self.task_graphs) != accepted_count
            or self.closure.accepted_task_deltas
            != tuple(graph.accepted_delta for graph in self.task_graphs)
            or record.accepted_delta_refs
            != tuple(
                graph.accepted_delta.accepted_delta_id
                for graph in self.task_graphs
            )
            or record.next_move_candidate_ref is not None
            or record.proposed_base_task_state_version is not None
            or record.validated_task_state_version is not None
            or (
                len(record.task_delta_candidates) == 1
                and accepted_count == 1
            )
        ):
            raise ValueError("unrouted decision must close partial or multi effects")
        _validate_initial_graph_identity_closure_v2(
            record=record,
            graphs=self.task_graphs,
        )
        for graph in self.task_graphs:
            _validate_initial_graph_candidate_projection_v2(
                record=record,
                graph=graph,
            )
        return self


def _preflight_initial_request_projection_v2(
    *,
    request_input: RequestUnderstandingInput,
    output: RequestUnderstandingOutputV2,
    authoritative_messages: Mapping[UUID, str],
) -> tuple[RequestUnderstandingInput, RequestUnderstandingOutputV2]:
    canonical_input = _canonical_request_input_v2(request_input)
    canonical_output = _canonical_request_output_v2(output)
    if not isinstance(authoritative_messages, Mapping):
        _fail_request_understanding_v2(
            RequestUnderstandingAggregateFailureCodeV2.SOURCE_PROVENANCE_INVALID
        )
    if canonical_input.message_ref != canonical_output.message_ref:
        _fail_request_understanding_v2(
            RequestUnderstandingAggregateFailureCodeV2.SOURCE_PROVENANCE_INVALID
        )
    _validate_input_visible_source_scope_v2(
        request_input=canonical_input,
        output=canonical_output,
    )
    current_message = _authoritative_message_v2(
        authoritative_messages,
        canonical_input.message_ref,
    )
    if current_message != canonical_input.original_query:
        _fail_request_understanding_v2(
            RequestUnderstandingAggregateFailureCodeV2.SOURCE_PROVENANCE_INVALID
        )
    _project_contextualization_v2(
        canonical_output.contextualization,
        authoritative_messages,
    )
    tuple(
        _project_task_delta_v2(candidate, authoritative_messages)
        for candidate in canonical_output.task_delta_candidates
    )
    return canonical_input, canonical_output


def _canonical_initial_identity_allocations_v2(
    *,
    allocations: object,
    emitted_candidate_refs: tuple[UUID, ...],
    request_understanding_record_id: object,
    next_move_candidate_ref: object,
    customer_context: object,
    now: object,
) -> dict[UUID, InitialTaskIdentityAllocationV2]:
    trusted_values_valid = (
        type(request_understanding_record_id) is UUID
        and type(next_move_candidate_ref) is UUID
        and _is_exact_canonical_model_v2(customer_context, CustomerContext)
        and type(now) is datetime
    )
    if trusted_values_valid:
        now_is_utc = True
        try:
            require_utc(now, field_name="now")
        except (TypeError, ValueError):
            now_is_utc = False
        trusted_values_valid = now_is_utc
    if not trusted_values_valid or type(allocations) is not tuple:
        _fail_request_understanding_v2(
            RequestUnderstandingAtomicFailureCodeV2.DURABLE_CLOSURE_COMMIT_FAILED
        )

    canonical_allocations = tuple(allocations)
    if any(
        not _is_exact_canonical_model_v2(
            allocation,
            InitialTaskIdentityAllocationV2,
        )
        for allocation in canonical_allocations
    ):
        _fail_request_understanding_v2(
            RequestUnderstandingAtomicFailureCodeV2.DURABLE_CLOSURE_COMMIT_FAILED
        )
    allocation_refs = tuple(
        allocation.candidate_ref for allocation in canonical_allocations
    )
    if (
        len(allocation_refs) != len(set(allocation_refs))
        or set(allocation_refs) != set(emitted_candidate_refs)
    ):
        _fail_request_understanding_v2(
            RequestUnderstandingAtomicFailureCodeV2.DURABLE_CLOSURE_COMMIT_FAILED
        )
    generated_ids = (
        request_understanding_record_id,
        next_move_candidate_ref,
        *(
            generated_id
            for allocation in canonical_allocations
            for generated_id in (
                allocation.accepted_delta_id,
                allocation.task_id,
                allocation.request_unit_id,
                allocation.binding_id,
            )
        ),
    )
    if len(generated_ids) != len(set(generated_ids)):
        _fail_request_understanding_v2(
            RequestUnderstandingAtomicFailureCodeV2.DURABLE_CLOSURE_COMMIT_FAILED
        )
    return {
        allocation.candidate_ref: allocation
        for allocation in canonical_allocations
    }


def _candidate_rejection_reason_v2(
    *,
    candidate: TaskDeltaCandidate,
    output: RequestUnderstandingOutputV2,
) -> CandidateRejectionReasonCode | None:
    uncertainty_reasons = {
        uncertainty.reason_code
        for uncertainty in output.contextualization.uncertainties
        if uncertainty.name == "order_id"
    }
    if UncertaintyReasonCodeV2.MISSING_REFERENCE in uncertainty_reasons:
        return CandidateRejectionReasonCode.REFERENCE_UNRESOLVED
    if (
        UncertaintyReasonCodeV2.MULTIPLE_PLAUSIBLE_REFERENCES
        in uncertainty_reasons
    ):
        return CandidateRejectionReasonCode.REFERENCE_AMBIGUOUS
    if len(candidate.input_candidates) != 1:
        return CandidateRejectionReasonCode.REQUIRED_INPUT_MISSING
    input_candidate = candidate.input_candidates[0]
    if (
        input_candidate.name != "order_id"
        or input_candidate.semantic_role != "TARGET_RESOURCE_IDENTIFIER"
        or input_candidate.authority is not InputAuthority.USER_CLAIM
        or input_candidate.source_kind is not InputSourceKind.CURRENT_MESSAGE
        or input_candidate.source_ref != output.message_ref
    ):
        return CandidateRejectionReasonCode.REQUIRED_INPUT_MISSING
    try:
        _normalize_order_id(input_candidate.candidate_value)
    except RequestProcessingError:
        return CandidateRejectionReasonCode.INPUT_VALUE_INVALID
    return None


def _build_initial_task_graph_v2(
    *,
    candidate: TaskDeltaCandidate,
    allocation: InitialTaskIdentityAllocationV2,
    customer_context: CustomerContext,
    message_ref: UUID,
    normalized_order_id: str,
    now: datetime,
) -> InitialAcceptedTaskGraphV2:
    graph: InitialAcceptedTaskGraphV2 | None = None
    try:
        binding = InputBinding(
            binding_id=allocation.binding_id,
            name="order_id",
            normalized_value=normalized_order_id,
            authority=InputAuthority.USER_CLAIM,
            source_refs=(message_ref,),
            validation_status=InputValidationStatus.ACCEPTED,
            confirmed_by_user=True,
            created_at=now,
            updated_at=now,
        )
        accepted_delta = AcceptedTaskDeltaV2(
            accepted_delta_id=allocation.accepted_delta_id,
            candidate_ref=candidate.candidate_id,
            message_ref=message_ref,
            operation=TaskDeltaOperation.ADD_GOAL,
            goal_text=candidate.goal_patch,
            input_binding_refs=(allocation.binding_id,),
            accepted_at=now,
            task_id=allocation.task_id,
            base_task_state_version=None,
            result_task_state_version=1,
        )
        task = TaskRecord(
            task_id=allocation.task_id,
            owner_customer_id=customer_context.customer_id,
            status=TaskStatus.ACTIVE,
            state_version=1,
            created_at=now,
            updated_at=now,
        )
        request_unit = RequestUnitRecord(
            request_unit_id=allocation.request_unit_id,
            task_id=allocation.task_id,
            goal_text=candidate.goal_patch,
            goal_source_refs=(message_ref,),
            input_binding_refs=(allocation.binding_id,),
            status=TaskStatus.ACTIVE,
            state_version=1,
            created_at=now,
            updated_at=now,
        )
        graph = InitialAcceptedTaskGraphV2(
            accepted_delta=accepted_delta,
            input_binding=binding,
            task=task,
            request_unit=request_unit,
        )
    except (TypeError, ValueError, ValidationError):
        graph = None
    if graph is None:
        _fail_request_understanding_v2(
            RequestUnderstandingAtomicFailureCodeV2.DURABLE_CLOSURE_COMMIT_FAILED
        )
    return graph


def _validate_and_reduce_initial_request_v2_impl(
    *,
    request_input: RequestUnderstandingInput,
    output: RequestUnderstandingOutputV2,
    authoritative_messages: Mapping[UUID, str],
    customer_context: CustomerContext,
    request_understanding_record_id: UUID,
    candidate_identity_allocations: tuple[
        InitialTaskIdentityAllocationV2,
        ...,
    ],
    next_move_candidate_ref: UUID,
    now: datetime,
    _decision_construction_capability: object,
    _issue_decision_seal: Any,
) -> (
    InitialRequestNoTaskDecisionV2
    | InitialRequestRoutableTaskGraphDecisionV2
    | InitialRequestUnroutedTaskGraphsDecisionV2
):
    """Validate actual v2 Candidates and build one exact pure Core result."""

    canonical_input, canonical_output = _preflight_initial_request_projection_v2(
        request_input=request_input,
        output=output,
        authoritative_messages=authoritative_messages,
    )
    emitted_refs = tuple(
        candidate.candidate_id
        for candidate in canonical_output.task_delta_candidates
    )
    allocations_by_candidate = _canonical_initial_identity_allocations_v2(
        allocations=candidate_identity_allocations,
        emitted_candidate_refs=emitted_refs,
        request_understanding_record_id=request_understanding_record_id,
        next_move_candidate_ref=next_move_candidate_ref,
        customer_context=customer_context,
        now=now,
    )

    decisions: list[CandidateValidationRecordV2] = []
    graphs: list[InitialAcceptedTaskGraphV2] = []
    decision_construction_failed = False
    for candidate in canonical_output.task_delta_candidates:
        rejection_reason = _candidate_rejection_reason_v2(
            candidate=candidate,
            output=canonical_output,
        )
        try:
            decisions.append(
                CandidateValidationRecordV2(
                    candidate_ref=candidate.candidate_id,
                    decision=(
                        CandidateValidationDecision.REJECT
                        if rejection_reason is not None
                        else CandidateValidationDecision.ACCEPT
                    ),
                    reason_code=rejection_reason,
                )
            )
        except (TypeError, ValueError, ValidationError):
            decision_construction_failed = True
            break
        if rejection_reason is not None:
            continue
        input_candidate = candidate.input_candidates[0]
        try:
            normalized_order_id = _normalize_order_id(
                input_candidate.candidate_value
            )
        except RequestProcessingError:
            decision_construction_failed = True
            break
        graphs.append(
            _build_initial_task_graph_v2(
                candidate=candidate,
                allocation=allocations_by_candidate[candidate.candidate_id],
                customer_context=customer_context,
                message_ref=canonical_output.message_ref,
                normalized_order_id=normalized_order_id,
                now=now,
            )
        )
    if decision_construction_failed:
        _fail_request_understanding_v2(
            RequestUnderstandingAtomicFailureCodeV2.DURABLE_CLOSURE_COMMIT_FAILED
        )

    exact_one_routable = (
        len(canonical_output.task_delta_candidates) == 1 and len(graphs) == 1
    )
    closure = build_request_understanding_closure_v2(
        request_input=canonical_input,
        output=canonical_output,
        authoritative_messages=authoritative_messages,
        request_understanding_record_id=request_understanding_record_id,
        candidate_validation=tuple(decisions),
        accepted_task_deltas=tuple(
            graph.accepted_delta for graph in graphs
        ),
        proposed_base_task_state_version=(
            canonical_output.next_move_candidate.base_task_state_version
            if exact_one_routable
            else None
        ),
        validated_task_state_version=1 if exact_one_routable else None,
        next_move_candidate_ref=(
            next_move_candidate_ref if exact_one_routable else None
        ),
        now=now,
    )

    result: (
        InitialRequestNoTaskDecisionV2
        | InitialRequestRoutableTaskGraphDecisionV2
        | InitialRequestUnroutedTaskGraphsDecisionV2
        | None
    ) = None
    try:
        if not graphs:
            result = InitialRequestNoTaskDecisionV2(closure=closure)
        elif exact_one_routable:
            seal_payload = _initial_routable_decision_fields_payload_v2(
                closure=closure,
                task_graph=graphs[0],
                next_move_candidate_ref=next_move_candidate_ref,
                next_move_candidate=canonical_output.next_move_candidate,
            )
            if seal_payload is None or not callable(_issue_decision_seal):
                routable_result = None
            else:
                routable_result = (
                    InitialRequestRoutableTaskGraphDecisionV2.model_validate(
                        {
                            "closure": closure,
                            "task_graph": graphs[0],
                            "next_move_candidate_ref": (
                                next_move_candidate_ref
                            ),
                            "next_move_candidate": (
                                canonical_output.next_move_candidate
                            ),
                        },
                        context={
                            "initial_routable_decision_permit_v2": (
                                _decision_construction_capability
                            )
                        },
                    )
                )
            if routable_result is not None and seal_payload is not None:
                routable_result._reducer_decision_seal = (
                    _issue_decision_seal(
                        routable_result,
                        seal_payload,
                    )
                )
            result = routable_result
        else:
            result = InitialRequestUnroutedTaskGraphsDecisionV2(
                closure=closure,
                task_graphs=tuple(graphs),
            )
    except (TypeError, ValueError, ValidationError):
        result = None
    if result is None:
        _fail_request_understanding_v2(
            RequestUnderstandingAtomicFailureCodeV2.DURABLE_CLOSURE_COMMIT_FAILED
        )
    return result


def _build_initial_request_reducer_v2() -> tuple[Any, Any, Any, Any]:
    construction_capability = object()
    seal_registry: dict[int, tuple[Any, bytes, Any]] = {}
    pickle_ticket_registry: dict[int, tuple[object, bytes]] = {}

    class ReducerDecisionSeal:
        __slots__ = ("_digest", "__weakref__")

        def __new__(cls) -> Self:
            raise TypeError("Reducer decision seal cannot be constructed")

        def __setattr__(self, _name: str, _value: Any) -> None:
            raise TypeError("Reducer decision seal is immutable")

        def __delattr__(self, _name: str) -> None:
            raise TypeError("Reducer decision seal is immutable")

        def __copy__(self) -> Self:
            return self

        def __deepcopy__(self, _memo: dict[int, Any]) -> Self:
            return self

        def __eq__(self, other: object) -> bool:
            return (
                type(other) is ReducerDecisionSeal
                and self._digest == other._digest
            )

        __hash__ = None

        def __repr__(self) -> str:
            return "<ReducerDecisionSeal>"

    def issue_initial_routable_decision_seal(
        value: object,
        seal_payload: bytes,
    ) -> ReducerDecisionSeal:
        if (
            type(seal_payload) is not bytes
            or _initial_routable_decision_payload_v2(value)
            != seal_payload
        ):
            raise ValueError("Reducer decision seal payload mismatch")
        seal_digest = sha256(b"sealed:\x00" + seal_payload).digest()
        seal = object.__new__(ReducerDecisionSeal)
        object.__setattr__(seal, "_digest", seal_digest)
        seal_id = id(seal)

        def discard_seal(
            _dead_seal: Any,
            *,
            registered_seal_id: int = seal_id,
        ) -> None:
            seal_registry.pop(registered_seal_id, None)

        seal_registry[seal_id] = (
            ref(seal, discard_seal),
            seal_digest,
            ref(value, discard_seal),
        )
        return seal

    def initial_routable_decision_seal_matches(
        value: object,
    ) -> bool:
        if type(value) is not InitialRequestRoutableTaskGraphDecisionV2:
            return False
        private_state = getattr(value, "__pydantic_private__", None)
        if (
            type(private_state) is not dict
            or any(type(key) is not str for key in private_state)
            or set(private_state) != {"_reducer_decision_seal"}
        ):
            return False
        actual_seal = private_state["_reducer_decision_seal"]
        if type(actual_seal) is not ReducerDecisionSeal:
            return False
        seal_payload = _initial_routable_decision_payload_v2(value)
        if seal_payload is None:
            return False
        registered = seal_registry.get(id(actual_seal))
        if (
            registered is None
            or registered[0]() is not actual_seal
            or registered[2]() is not value
        ):
            return False
        expected_digest = sha256(
            b"sealed:\x00" + seal_payload
        ).digest()
        return (
            type(actual_seal._digest) is bytes
            and actual_seal._digest == registered[1]
            and actual_seal._digest == expected_digest
        )

    def initial_routable_decision_construction_is_authorized(
        value: object,
        context: object,
    ) -> bool:
        if type(context) is not dict or set(context) != {
            "initial_routable_decision_permit_v2"
        }:
            return False
        actual_permit = context["initial_routable_decision_permit_v2"]
        return (
            actual_permit is construction_capability
            and _initial_routable_decision_payload_v2(value) is not None
        )

    def copy_initial_routable_decision(
        self: InitialRequestRoutableTaskGraphDecisionV2,
    ) -> InitialRequestRoutableTaskGraphDecisionV2:
        if not initial_routable_decision_seal_matches(self):
            raise ValueError("canonical Reducer decision required")
        copied = BaseModel.__copy__(self)
        seal_payload = _initial_routable_decision_payload_v2(copied)
        if seal_payload is None:
            raise ValueError("canonical Reducer decision required")
        copied.__pydantic_private__["_reducer_decision_seal"] = (
            issue_initial_routable_decision_seal(copied, seal_payload)
        )
        return copied

    def deepcopy_initial_routable_decision(
        self: InitialRequestRoutableTaskGraphDecisionV2,
        memo: dict[int, Any] | None = None,
    ) -> InitialRequestRoutableTaskGraphDecisionV2:
        if not initial_routable_decision_seal_matches(self):
            raise ValueError("canonical Reducer decision required")
        copied = BaseModel.__deepcopy__(self, memo)
        seal_payload = _initial_routable_decision_payload_v2(copied)
        if seal_payload is None:
            raise ValueError("canonical Reducer decision required")
        copied.__pydantic_private__["_reducer_decision_seal"] = (
            issue_initial_routable_decision_seal(copied, seal_payload)
        )
        return copied

    def restore_pickled_initial_routable_decision(
        ticket_id: int,
        state: object,
    ) -> InitialRequestRoutableTaskGraphDecisionV2:
        expected_state_keys = {
            "__dict__",
            "__pydantic_extra__",
            "__pydantic_fields_set__",
            "__pydantic_private__",
        }
        if (
            type(ticket_id) is not int
            or type(state) is not dict
            or any(type(key) is not str for key in state)
            or set(state) != expected_state_keys
        ):
            raise ValueError("unknown Reducer decision pickle")
        registered_ticket = pickle_ticket_registry.get(ticket_id)
        if (
            registered_ticket is None
            or id(registered_ticket[0]) != ticket_id
            or type(registered_ticket[1]) is not bytes
        ):
            raise ValueError("unknown Reducer decision pickle")

        model_state = state["__dict__"]
        fields_set = state["__pydantic_fields_set__"]
        private_state = state["__pydantic_private__"]
        declared_fields = set(
            InitialRequestRoutableTaskGraphDecisionV2.model_fields
        )
        if (
            type(model_state) is not dict
            or any(type(key) is not str for key in model_state)
            or set(model_state) != declared_fields
            or state["__pydantic_extra__"] is not None
            or type(fields_set) is not set
            or any(type(field) is not str for field in fields_set)
            or fields_set != declared_fields
            or type(private_state) is not dict
            or private_state
        ):
            raise ValueError("invalid Reducer decision pickle")

        restored = InitialRequestRoutableTaskGraphDecisionV2.__new__(
            InitialRequestRoutableTaskGraphDecisionV2
        )
        BaseModel.__setstate__(
            restored,
            {
                "__dict__": dict(model_state),
                "__pydantic_extra__": None,
                "__pydantic_fields_set__": set(fields_set),
                "__pydantic_private__": {},
            },
        )
        seal_payload = _initial_routable_decision_payload_v2(restored)
        expected_digest = (
            sha256(b"sealed:\x00" + seal_payload).digest()
            if seal_payload is not None
            else None
        )
        if expected_digest != registered_ticket[1]:
            raise ValueError("invalid Reducer decision pickle")
        if pickle_ticket_registry.pop(ticket_id, None) is not registered_ticket:
            raise ValueError("unknown Reducer decision pickle")
        restored.__pydantic_private__["_reducer_decision_seal"] = (
            issue_initial_routable_decision_seal(restored, seal_payload)
        )
        return restored

    restore_pickled_initial_routable_decision.__name__ = (
        "_restore_pickled_initial_routable_decision_v2"
    )
    restore_pickled_initial_routable_decision.__qualname__ = (
        "_restore_pickled_initial_routable_decision_v2"
    )

    def reduce_pickled_initial_routable_decision(
        self: InitialRequestRoutableTaskGraphDecisionV2,
        protocol: int,
    ) -> tuple[Any, tuple[int, dict[str, Any]]]:
        if (
            type(protocol) is not int
            or not initial_routable_decision_seal_matches(self)
        ):
            raise ValueError("canonical Reducer decision required")
        seal_payload = _initial_routable_decision_payload_v2(self)
        if seal_payload is None:
            raise ValueError("canonical Reducer decision required")
        state = BaseModel.__getstate__(self)
        ticket = object()
        ticket_id = id(ticket)
        pickle_ticket_registry[ticket_id] = (
            ticket,
            sha256(b"sealed:\x00" + seal_payload).digest(),
        )
        return (
            restore_pickled_initial_routable_decision,
            (
                ticket_id,
                {
                    "__dict__": state["__dict__"],
                    "__pydantic_extra__": state["__pydantic_extra__"],
                    "__pydantic_fields_set__": (
                        state["__pydantic_fields_set__"]
                    ),
                    "__pydantic_private__": {},
                },
            ),
        )

    InitialRequestRoutableTaskGraphDecisionV2.__copy__ = (
        copy_initial_routable_decision
    )
    InitialRequestRoutableTaskGraphDecisionV2.__deepcopy__ = (
        deepcopy_initial_routable_decision
    )
    InitialRequestRoutableTaskGraphDecisionV2.__reduce_ex__ = (
        reduce_pickled_initial_routable_decision
    )

    def validate_and_reduce_initial_request_v2(
        *,
        request_input: RequestUnderstandingInput,
        output: RequestUnderstandingOutputV2,
        authoritative_messages: Mapping[UUID, str],
        customer_context: CustomerContext,
        request_understanding_record_id: UUID,
        candidate_identity_allocations: tuple[
            InitialTaskIdentityAllocationV2,
            ...,
        ],
        next_move_candidate_ref: UUID,
        now: datetime,
    ) -> (
        InitialRequestNoTaskDecisionV2
        | InitialRequestRoutableTaskGraphDecisionV2
        | InitialRequestUnroutedTaskGraphsDecisionV2
    ):
        """Validate actual v2 Candidates and build one exact Core result."""

        return _validate_and_reduce_initial_request_v2_impl(
            request_input=request_input,
            output=output,
            authoritative_messages=authoritative_messages,
            customer_context=customer_context,
            request_understanding_record_id=request_understanding_record_id,
            candidate_identity_allocations=candidate_identity_allocations,
            next_move_candidate_ref=next_move_candidate_ref,
            now=now,
            _decision_construction_capability=construction_capability,
            _issue_decision_seal=issue_initial_routable_decision_seal,
        )

    return (
        validate_and_reduce_initial_request_v2,
        initial_routable_decision_seal_matches,
        initial_routable_decision_construction_is_authorized,
        restore_pickled_initial_routable_decision,
    )


(
    validate_and_reduce_initial_request_v2,
    _initial_routable_decision_seal_matches_v2,
    _initial_routable_decision_construction_is_authorized_v2,
    _restore_pickled_initial_routable_decision_v2,
) = _build_initial_request_reducer_v2()
del _build_initial_request_reducer_v2


def revalidate_next_move_v2(
    *,
    decision: InitialRequestRoutableTaskGraphDecisionV2,
    current_task: TaskRecord,
    current_request_unit: RequestUnitRecord,
    current_input_binding: InputBinding,
) -> RevalidatedNextMove:
    """Revalidate one persisted exact-one v2 graph without rewriting arguments."""

    if not _is_exact_canonical_model_v2(
        decision,
        InitialRequestRoutableTaskGraphDecisionV2,
    ):
        raise RequestProcessingError("canonical v2 initial decision required")
    if (
        not _is_exact_canonical_model_v2(current_task, TaskRecord)
        or not _is_exact_canonical_model_v2(
            current_request_unit,
            RequestUnitRecord,
        )
        or not _is_exact_canonical_model_v2(
            current_input_binding,
            InputBinding,
        )
    ):
        raise RequestProcessingError("canonical current graph required")

    expected = decision.task_graph
    if current_task.owner_customer_id != expected.task.owner_customer_id:
        raise RequestProcessingError("current Task owner mismatch")
    if (
        current_task.task_id != expected.task.task_id
        or current_request_unit.task_id != current_task.task_id
        or current_request_unit.request_unit_id
        != expected.request_unit.request_unit_id
    ):
        raise RequestProcessingError("current Task graph mismatch")
    if (
        current_task.status is not TaskStatus.ACTIVE
        or current_request_unit.status is not TaskStatus.ACTIVE
        or current_task.state_version != 1
        or current_request_unit.state_version != 1
    ):
        raise RequestProcessingError("current Task graph is not ACTIVE/v1")
    if (
        not _runtime_values_match_exactly_v2(current_task, expected.task)
        or not _runtime_values_match_exactly_v2(
            current_request_unit,
            expected.request_unit,
        )
    ):
        raise RequestProcessingError("current Task graph mismatch")
    if (
        not _runtime_values_match_exactly_v2(
            current_input_binding,
            expected.input_binding,
        )
        or current_request_unit.input_binding_refs
        != (current_input_binding.binding_id,)
        or expected.accepted_delta.input_binding_refs
        != (current_input_binding.binding_id,)
    ):
        raise RequestProcessingError("current InputBinding graph mismatch")

    candidate = decision.next_move_candidate
    if (
        candidate.kind is not NextMoveKind.CALL_TOOL
        or candidate.requested_tool_name is None
        or candidate.arguments is None
    ):
        raise RequestProcessingError("revalidation requires CALL_TOOL candidate")
    if find_trusted_argument_field(candidate.arguments) is not None:
        raise RequestProcessingError("trusted field in model arguments")

    revalidated: RevalidatedNextMove | None = None
    try:
        revalidated = RevalidatedNextMove(
            run_id=decision.closure.record.run_id,
            task_id=current_task.task_id,
            request_unit_id=current_request_unit.request_unit_id,
            next_move_candidate_ref=decision.next_move_candidate_ref,
            kind=NextMoveKind.CALL_TOOL,
            requested_provider_tool_name=candidate.requested_tool_name,
            candidate_arguments=candidate.arguments,
            normalized_candidate_order_id=_candidate_order_id_or_none(
                candidate.arguments
            ),
            binding_name=current_input_binding.name,
            binding_normalized_value=current_input_binding.normalized_value,
            argument_binding_refs=(current_input_binding.binding_id,),
            proposed_base_task_state_version=(
                candidate.base_task_state_version
            ),
            validated_task_state_version=current_task.state_version,
        )
    except (TypeError, ValueError, ValidationError):
        revalidated = None
    if revalidated is None:
        raise RequestProcessingError("v2 NextMove revalidation failed")
    return revalidated
