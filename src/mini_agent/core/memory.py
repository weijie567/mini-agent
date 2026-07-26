"""Observation and Context Manifest contracts; neither is free-form Memory."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from .common import AuditOnlyModel, require_utc
from .order import OrderSummaryProjection
from .tool_system import ToolsetHash

NonEmptyString = Annotated[str, Field(min_length=1)]
PositiveStateVersion = Annotated[int, Field(ge=1)]


class ObservationVisibility(StrEnum):
    MODEL_VISIBLE = "MODEL_VISIBLE"
    AUDIT_ONLY = "AUDIT_ONLY"
    USER_VISIBLE = "USER_VISIBLE"


class OrderObservation(AuditOnlyModel):
    """A safe Observation created only after scoped ownership validation."""

    observation_id: UUID
    source_tool: Literal["get_order"]
    source_resource_ref: NonEmptyString
    source_version: NonEmptyString | None = None
    normalized_type: Literal["ORDER_SUMMARY"]
    normalized_value: OrderSummaryProjection
    observed_at: datetime
    recorded_at: datetime
    valid_until: datetime | None = None
    supersedes: UUID | None = None
    raw_result_ref: NonEmptyString | None = None
    visibility: ObservationVisibility

    @field_validator("observed_at", "recorded_at", "valid_until")
    @classmethod
    def observation_timestamps_are_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return require_utc(value, field_name="OrderObservation timestamp")

    @model_validator(mode="after")
    def observation_dates_are_ordered(self) -> Self:
        if self.recorded_at < self.observed_at:
            raise ValueError("recorded_at cannot precede observed_at")
        if self.valid_until is not None and self.valid_until < self.observed_at:
            raise ValueError("valid_until cannot precede observed_at")
        return self


class TaskStateRefAndVersion(AuditOnlyModel):
    task_id: UUID
    state_version: PositiveStateVersion


class VersionedRecordRef(AuditOnlyModel):
    record_ref: UUID
    version: NonEmptyString


class TruncationDecision(AuditOnlyModel):
    source_ref: UUID
    reason_code: NonEmptyString


class TokenCounts(AuditOnlyModel):
    input_tokens: Annotated[int, Field(ge=0)]
    output_tokens: Annotated[int, Field(ge=0)] = 0


class ContextManifest(AuditOnlyModel):
    """References actually projected to one model call, without private payloads."""

    context_manifest_id: UUID
    run_id: UUID
    model_call_id: UUID
    tool_registry_version: NonEmptyString
    model_visible_toolset_hash: ToolsetHash
    selected_message_refs: tuple[UUID, ...]
    task_state_ref_and_version: TaskStateRefAndVersion | None = None
    observation_refs_and_versions: tuple[VersionedRecordRef, ...] = ()
    evidence_refs_and_versions: tuple[VersionedRecordRef, ...] = ()
    action_record_refs: tuple[UUID, ...] = ()
    redaction_policy_version: NonEmptyString
    truncation_decisions: tuple[TruncationDecision, ...] = ()
    token_counts: TokenCounts
    assembled_at: datetime

    @field_validator("assembled_at")
    @classmethod
    def assembled_at_is_utc(cls, value: datetime) -> datetime:
        return require_utc(value, field_name="assembled_at")
