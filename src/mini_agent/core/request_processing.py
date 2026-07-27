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
    normalized_quote = candidate.source_quote.strip()
    if normalized_quote[:2].casefold() == "o-":
        normalized_quote = f"O-{normalized_quote[2:]}"
    if normalized_binding_value not in normalized_quote.upper():
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
