"""Pure deterministic validation and reduction for the first E2E-01 slice."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Annotated, Any, Literal
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

from pydantic import BaseModel, ValidationError
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
            left_fields_set = set(left.model_fields_set)
            right_fields_set = set(right.model_fields_set)
        except (AttributeError, TypeError):
            return False
        if (
            left_state_keys != right_state_keys
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
    if isinstance(left, tuple):
        return len(left) == len(right) and all(
            _runtime_values_match_exactly_v2(left_item, right_item)
            for left_item, right_item in zip(left, right, strict=True)
        )
    if isinstance(left, Mapping):
        return (
            tuple(left) == tuple(right)
            and all(
                _runtime_values_match_exactly_v2(left[key], right[key])
                for key in left
            )
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
    try:
        request_input_fields_set = set(request_input.model_fields_set)
    except (AttributeError, TypeError):
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
            mode="python",
            round_trip=True,
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
            mode="python",
            round_trip=True,
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
        try:
            rebuilt = CandidateValidationRecordV2.model_validate(
                value.model_dump(mode="python", round_trip=True)
            )
        except (TypeError, ValueError, ValidationError):
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
        try:
            rebuilt = AcceptedTaskDeltaV2.model_validate(
                value.model_dump(mode="python", round_trip=True)
            )
        except (TypeError, ValueError, ValidationError):
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
    try:
        message = authoritative_messages[source_ref]
    except (KeyError, TypeError):
        _fail_request_understanding_v2(
            RequestUnderstandingAggregateFailureCodeV2.SOURCE_PROVENANCE_INVALID
        )
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
    try:
        normalized_candidate = _normalize_order_id(candidate_value)
    except RequestProcessingError:
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
    try:
        return DurableResolvedReferenceCandidateV2(
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
        _fail_request_understanding_v2(
            RequestUnderstandingAggregateFailureCodeV2.MODEL_OUTPUT_SCHEMA_INVALID
        )


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
    try:
        return DurableInputCandidateV2(
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
        _fail_request_understanding_v2(
            RequestUnderstandingAggregateFailureCodeV2.MODEL_OUTPUT_SCHEMA_INVALID
        )


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
    try:
        return DurableQueryContextualizationCandidateV2(
            text=contextualization.text,
            resolved_reference_candidates=projected_references,
            uncertainties=contextualization.uncertainties,
            source_message_refs=contextualization.source_message_refs,
        )
    except (TypeError, ValueError, ValidationError):
        _fail_request_understanding_v2(
            RequestUnderstandingAggregateFailureCodeV2.MODEL_OUTPUT_SCHEMA_INVALID
        )


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
    try:
        return DurableTaskDeltaCandidateV2(
            candidate_id=candidate.candidate_id,
            operation=candidate.operation,
            goal_patch=candidate.goal_patch,
            input_candidates=projected_inputs,
            confidence=candidate.confidence,
        )
    except (TypeError, ValueError, ValidationError):
        _fail_request_understanding_v2(
            RequestUnderstandingAggregateFailureCodeV2.MODEL_OUTPUT_SCHEMA_INVALID
        )


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
    try:
        require_utc(now, field_name="now")
    except (TypeError, ValueError):
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
        return RequestUnderstandingClosureV2(
            record=record,
            accepted_task_deltas=canonical_children,
        )
    except (TypeError, ValueError, ValidationError):
        _fail_request_understanding_v2(
            RequestUnderstandingAtomicFailureCodeV2.DURABLE_CLOSURE_COMMIT_FAILED
        )
