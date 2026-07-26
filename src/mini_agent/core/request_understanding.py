"""Model-visible Request Understanding and NextMove candidate contracts."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from enum import StrEnum
from typing import Annotated, Any, Literal, Self
from uuid import UUID

from pydantic import (
    Field,
    JsonValue,
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
from .tool_system import (
    ToolSpec,
    ToolsetHash,
    compute_model_visible_toolset_hash,
)

NonEmptyString = Annotated[str, Field(min_length=1)]
Confidence = Annotated[float, Field(ge=0.0, le=1.0)]
PositiveStateVersion = Annotated[int, Field(ge=1)]

THIN_SLICE_REQUEST_SCHEMA_VERSION = "e2e01-thin-v1"


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


class RequestUnderstandingOutput(ModelVisibleModel):
    schema_version: Literal["e2e01-thin-v1"] = THIN_SLICE_REQUEST_SCHEMA_VERSION
    message_ref: UUID
    task_delta_candidates: Annotated[
        tuple[TaskDeltaCandidate, ...],
        Field(min_length=1),
    ]
    next_move_candidate: NextMove

    @model_validator(mode="after")
    def candidates_bind_to_current_message(self) -> Self:
        candidate_ids = [
            candidate.candidate_id for candidate in self.task_delta_candidates
        ]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("TaskDeltaCandidate IDs must be unique")

        for delta in self.task_delta_candidates:
            for input_candidate in delta.input_candidates:
                if input_candidate.source_ref != self.message_ref:
                    raise ValueError(
                        "thin-slice InputCandidate must reference current message"
                    )
                if input_candidate.authority is not InputAuthority.USER_CLAIM:
                    raise ValueError(
                        "thin-slice InputCandidate must remain a USER_CLAIM"
                    )

        if self.next_move_candidate.base_task_state_version is not None:
            raise ValueError(
                "new-goal thin-slice candidate must use a null base Task version"
            )
        return self
