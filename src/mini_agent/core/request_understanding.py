"""Model-visible Request Understanding and NextMove candidate contracts."""

from __future__ import annotations

import re
from collections.abc import Mapping
from copy import deepcopy
from enum import StrEnum
from typing import Annotated, Any, Literal, Self
from uuid import UUID

from pydantic import (
    Field,
    JsonValue,
    StrictBool,
    StrictInt,
    StrictStr,
    field_serializer,
    field_validator,
    model_validator,
)

from .common import (
    ModelVisibleModel,
    find_trusted_argument_field,
    freeze_json_value,
    thaw_json_value,
)
from .order_search import normalize_product_description
from .tool_system import (
    ToolSpec,
    ToolsetHash,
    compute_model_visible_toolset_hash,
)

NonEmptyString = Annotated[str, Field(min_length=1)]
Confidence = Annotated[float, Field(ge=0.0, le=1.0)]
PositiveStateVersion = Annotated[int, Field(ge=1)]

THIN_SLICE_REQUEST_SCHEMA_VERSION = "e2e01-thin-v1"
CYCLE2_ORDINAL_CLAIM_MAX = 99
_CYCLE2_ORDER_ID_PATTERN = re.compile(r"^O-[0-9]{4,20}$")


class ModelVisibleTaskSummary(ModelVisibleModel):
    task_alias: NonEmptyString
    request_unit_alias: NonEmptyString | None = None
    goal_summary: NonEmptyString
    status: NonEmptyString
    open_questions: tuple[NonEmptyString, ...] = ()


class ModelVisiblePendingActionSummary(ModelVisibleModel):
    action_alias: NonEmptyString
    summary: NonEmptyString


class RequestUnderstandingInput(ModelVisibleModel):
    """Minimal, safe input for the first Request Understanding model call."""

    schema_version: Literal["e2e01-thin-v1"] = THIN_SLICE_REQUEST_SCHEMA_VERSION
    run_id: UUID
    message_ref: UUID
    original_query: Annotated[str, Field(min_length=1, max_length=4000)]
    recent_message_refs: tuple[UUID, ...] = ()
    pending_question: NonEmptyString | None = None
    active_task_summaries: tuple[ModelVisibleTaskSummary, ...] = ()
    focused_task_summary: ModelVisibleTaskSummary | None = None
    pending_action_summaries: tuple[ModelVisiblePendingActionSummary, ...] = ()
    output_constraints: tuple[NonEmptyString, ...] = ()
    provider_visible_tool_specs: tuple[ToolSpec, ...]
    model_visible_toolset_hash: ToolsetHash

    @model_validator(mode="after")
    def toolset_hash_matches_projected_specs(self) -> Self:
        expected_hash = compute_model_visible_toolset_hash(
            self.provider_visible_tool_specs
        )
        if self.model_visible_toolset_hash != expected_hash:
            raise ValueError("model-visible ToolSpec hash mismatch")
        return self


class TaskDeltaOperation(StrEnum):
    ADD_GOAL = "ADD_GOAL"
    AMEND_GOAL = "AMEND_GOAL"
    SUPPLY_INPUT = "SUPPLY_INPUT"
    CANCEL_GOAL = "CANCEL_GOAL"
    CONFIRMATION_CANDIDATE = "CONFIRMATION_CANDIDATE"


class InputAuthority(StrEnum):
    USER_CLAIM = "USER_CLAIM"
    MODEL_INFERENCE = "MODEL_INFERENCE"


class InputSourceKind(StrEnum):
    CURRENT_MESSAGE = "CURRENT_MESSAGE"


class InputCandidate(ModelVisibleModel):
    name: Literal["order_id"]
    candidate_value: NonEmptyString
    semantic_role: Literal["TARGET_RESOURCE_IDENTIFIER"]
    authority: InputAuthority
    source_kind: InputSourceKind
    source_ref: UUID
    source_quote: NonEmptyString
    confidence: Confidence


class TaskDeltaCandidate(ModelVisibleModel):
    """A model proposal, never an authoritative Task state mutation."""

    candidate_id: UUID
    operation: Literal[TaskDeltaOperation.ADD_GOAL]
    goal_patch: NonEmptyString
    input_candidates: Annotated[tuple[InputCandidate, ...], Field(min_length=1)]
    confidence: Confidence

    @field_validator("input_candidates")
    @classmethod
    def candidate_names_are_unique(
        cls, value: tuple[InputCandidate, ...]
    ) -> tuple[InputCandidate, ...]:
        names = [candidate.name for candidate in value]
        if len(names) != len(set(names)):
            raise ValueError("input candidate names must be unique per Goal Delta")
        return value


class NextMoveKind(StrEnum):
    CALL_TOOL = "CALL_TOOL"
    ASK_USER = "ASK_USER"
    FINISH = "FINISH"
    ESCALATE = "ESCALATE"


class NextMove(ModelVisibleModel):
    """A single model proposal; it is not an executable command."""

    kind: NextMoveKind
    requested_tool_name: NonEmptyString | None = None
    arguments: Mapping[str, JsonValue] | None = None
    base_task_state_version: PositiveStateVersion | None = None

    @field_validator("arguments", mode="before")
    @classmethod
    def argument_input_is_native_json(cls, value: Any) -> Any:
        return thaw_json_value(value)

    @field_validator("arguments")
    @classmethod
    def arguments_exclude_trusted_fields(
        cls, value: Mapping[str, JsonValue] | None
    ) -> Mapping[str, JsonValue] | None:
        if value is None:
            return None
        copied = deepcopy(value)
        forbidden = find_trusted_argument_field(copied)
        if forbidden is not None:
            raise ValueError(
                f"model candidate cannot supply trusted field {forbidden!r}"
            )
        return freeze_json_value(copied)

    @field_serializer("arguments")
    def serialize_arguments(
        self, value: Mapping[str, JsonValue] | None
    ) -> dict[str, JsonValue] | None:
        if value is None:
            return None
        return thaw_json_value(value)

    @model_validator(mode="after")
    def candidate_shape_matches_kind(self) -> Self:
        if self.kind is NextMoveKind.CALL_TOOL:
            if self.requested_tool_name is None or self.arguments is None:
                raise ValueError("CALL_TOOL requires a tool name and arguments")
        elif self.requested_tool_name is not None or self.arguments is not None:
            raise ValueError(
                "non-CALL_TOOL candidates cannot carry tool name or arguments"
            )
        return self


BoundedSourceQuoteV2 = Annotated[
    StrictStr,
    Field(min_length=1, max_length=128),
]


class Cycle2InputCandidate(ModelVisibleModel):
    """Inactive model Claim with no owner, target, or Observation authority."""

    name: Literal[
        "order_id",
        "product_description",
        "candidate_ordinal",
        "shipment_not_received",
    ]
    candidate_value: StrictStr | StrictInt | StrictBool
    source_ref: UUID
    source_quote: BoundedSourceQuoteV2
    confidence: Confidence

    @model_validator(mode="after")
    def name_value_pair_is_exact(self) -> Self:
        value = self.candidate_value
        if self.name == "order_id":
            if (
                type(value) is not str
                or _CYCLE2_ORDER_ID_PATTERN.fullmatch(value) is None
            ):
                raise ValueError("order_id must match O-[0-9]{4,20}")
        elif self.name == "product_description":
            if type(value) is not str:
                raise ValueError("product_description must be a strict string")
            normalize_product_description(value)
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


class Cycle2ControlCandidateKind(StrEnum):
    CALL_TOOL = "CALL_TOOL"
    FINISH = "FINISH"


class Cycle2ControlCandidate(ModelVisibleModel):
    """Argument-free model choice; deterministic code owns target materialization."""

    kind: Cycle2ControlCandidateKind
    requested_tool_name: Literal["get_order", "get_shipment"] | None = None

    @model_validator(mode="after")
    def tool_name_matches_kind(self) -> Self:
        if self.kind is Cycle2ControlCandidateKind.CALL_TOOL:
            if self.requested_tool_name is None:
                raise ValueError("CALL_TOOL control candidate requires a tool name")
        elif self.requested_tool_name is not None:
            raise ValueError("FINISH control candidate cannot request a tool")
        return self


class Cycle2InitialTaskDeltaCandidateV2(ModelVisibleModel):
    """One first-turn Goal proposal containing only a product Claim."""

    candidate_id: UUID
    operation: Literal[TaskDeltaOperation.ADD_GOAL]
    goal_patch: NonEmptyString
    input_candidates: Annotated[
        tuple[Cycle2InputCandidate, ...],
        Field(min_length=1, max_length=1),
    ]
    confidence: Confidence

    @model_validator(mode="after")
    def exact_one_product_description_claim(self) -> Self:
        if self.input_candidates[0].name != "product_description":
            raise ValueError(
                "Cycle 2 initial Goal requires one product_description Claim"
            )
        return self


class Cycle2ContinuationTaskDeltaCandidateV2(ModelVisibleModel):
    """One scoped continuation proposal without trusted target authority."""

    candidate_id: UUID
    operation: TaskDeltaOperation
    target_task_alias: NonEmptyString
    target_request_unit_alias: NonEmptyString
    input_candidates: Annotated[
        tuple[Cycle2InputCandidate, ...],
        Field(min_length=1, max_length=2),
    ]
    confidence: Confidence


class ReferenceSourceKindV2(StrEnum):
    CURRENT_MESSAGE = "CURRENT_MESSAGE"
    RECENT_MESSAGE = "RECENT_MESSAGE"


class UncertaintyReasonCodeV2(StrEnum):
    MISSING_REFERENCE = "MISSING_REFERENCE"
    MULTIPLE_PLAUSIBLE_REFERENCES = "MULTIPLE_PLAUSIBLE_REFERENCES"


class ResolvedReferenceCandidateV2(ModelVisibleModel):
    name: Literal["order_id"]
    candidate_value: NonEmptyString
    source_kind: ReferenceSourceKindV2
    source_ref: UUID
    source_quote: BoundedSourceQuoteV2
    confidence: Confidence


class UncertaintyV2(ModelVisibleModel):
    name: Literal["order_id"]
    candidate_values: tuple[NonEmptyString, ...]
    reason_code: UncertaintyReasonCodeV2
    source_message_refs: Annotated[
        tuple[UUID, ...],
        Field(min_length=1, max_length=8),
    ]

    @field_validator("source_message_refs")
    @classmethod
    def source_message_refs_are_unique(
        cls,
        value: tuple[UUID, ...],
    ) -> tuple[UUID, ...]:
        if len(value) != len(set(value)):
            raise ValueError("source_message_refs must be unique")
        return value

    @model_validator(mode="after")
    def candidate_cardinality_matches_reason(self) -> Self:
        if self.reason_code is UncertaintyReasonCodeV2.MISSING_REFERENCE:
            if self.candidate_values:
                raise ValueError(
                    "MISSING_REFERENCE cannot carry candidate values"
                )
        elif not 2 <= len(self.candidate_values) <= 8:
            raise ValueError(
                "MULTIPLE_PLAUSIBLE_REFERENCES requires 2..8 candidate values"
            )
        if len(self.candidate_values) != len(set(self.candidate_values)):
            raise ValueError("uncertainty candidate values must be unique")
        return self


class QueryContextualizationCandidateV2(ModelVisibleModel):
    text: NonEmptyString
    resolved_reference_candidates: tuple[
        ResolvedReferenceCandidateV2,
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


class Cycle2ContinuationRequestUnderstandingOutputV2(ModelVisibleModel):
    """Closed Cycle 2 continuation envelope with no NextMove authority."""

    schema_version: Literal["e2e01-cycle2-continuation.p0.v2"]
    message_ref: UUID
    contextualization: QueryContextualizationCandidateV2
    task_delta_candidates: Annotated[
        tuple[Cycle2ContinuationTaskDeltaCandidateV2, ...],
        Field(min_length=1, max_length=1),
    ]


class Cycle2InitialRequestUnderstandingOutputV2(ModelVisibleModel):
    """Closed first-turn Cycle 2 proposal with no trusted business authority."""

    schema_version: Literal["e2e01-cycle2-initial.p0.v1"]
    message_ref: UUID
    contextualization: QueryContextualizationCandidateV2
    task_delta_candidates: Annotated[
        tuple[Cycle2InitialTaskDeltaCandidateV2, ...],
        Field(min_length=1, max_length=1),
    ]
    next_move_candidate: NextMove

    @model_validator(mode="after")
    def first_turn_graph_is_exact_and_claim_only(self) -> Self:
        if (
            self.contextualization.source_message_refs != (self.message_ref,)
            or self.contextualization.resolved_reference_candidates
            or self.contextualization.uncertainties
        ):
            raise ValueError(
                "Cycle 2 initial contextualization must use only current message"
            )
        delta = self.task_delta_candidates[0]
        candidate = delta.input_candidates[0]
        move = self.next_move_candidate
        arguments = move.arguments
        if candidate.source_ref != self.message_ref:
            raise ValueError(
                "Cycle 2 initial Claim must reference current message"
            )
        try:
            normalized_candidate = normalize_product_description(
                candidate.candidate_value
            )
            argument = (
                arguments.get("product_description")
                if arguments is not None
                else None
            )
            normalized_argument = normalize_product_description(argument)
        except (TypeError, ValueError):
            raise ValueError(
                "Cycle 2 initial next move requires normalized product_description"
            ) from None
        if (
            move.kind is not NextMoveKind.CALL_TOOL
            or move.requested_tool_name != "search_orders"
            or arguments is None
            or set(arguments) != {"product_description"}
            or type(argument) is not str
            or argument != normalized_argument
            or normalized_argument != normalized_candidate
            or move.base_task_state_version is not None
        ):
            raise ValueError(
                "Cycle 2 initial next move must exactly propose search_orders"
            )
        return self


class RequestUnderstandingOutputV2(ModelVisibleModel):
    schema_version: Literal["e2e01-thin-v2"]
    message_ref: UUID
    contextualization: QueryContextualizationCandidateV2
    task_delta_candidates: tuple[TaskDeltaCandidate, ...]
    next_move_candidate: NextMove

    @model_validator(mode="after")
    def v2_candidate_graph_is_locally_bound(self) -> Self:
        candidate_ids = [
            candidate.candidate_id for candidate in self.task_delta_candidates
        ]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("TaskDeltaCandidate IDs must be unique")
        if self.message_ref not in self.contextualization.source_message_refs:
            raise ValueError(
                "contextualization must include the current message"
            )
        for delta in self.task_delta_candidates:
            for input_candidate in delta.input_candidates:
                if len(input_candidate.source_quote) > 128:
                    raise ValueError(
                        "InputCandidate source_quote cannot exceed 128"
                    )
                if input_candidate.source_ref != self.message_ref:
                    raise ValueError(
                        "v2 InputCandidate must reference current message"
                    )
                if input_candidate.authority is not InputAuthority.USER_CLAIM:
                    raise ValueError(
                        "v2 InputCandidate must remain a USER_CLAIM"
                    )
                if (
                    input_candidate.source_kind
                    is not InputSourceKind.CURRENT_MESSAGE
                ):
                    raise ValueError(
                        "v2 InputCandidate must use current message source"
                    )
        if self.next_move_candidate.base_task_state_version is not None:
            raise ValueError(
                "new-goal v2 candidate must use a null base Task version"
            )
        return self
