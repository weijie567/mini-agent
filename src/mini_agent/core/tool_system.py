"""Core-owned ToolSpec, immutable snapshot, Gate, and ToolCall contracts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal, Self, Sequence
from uuid import UUID

from pydantic import (
    Field,
    JsonValue,
    field_serializer,
    field_validator,
    model_validator,
)

from .common import (
    AuditOnlyModel,
    ModelVisibleModel,
    RuntimePrivateModel,
    find_trusted_argument_field,
    freeze_json_value,
    require_utc,
    thaw_json_value,
)

NonEmptyString = Annotated[str, Field(min_length=1)]
ToolName = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$")]
ToolsetHash = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
SafeReasonCode = Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]{1,127}$")]

MODEL_VISIBLE_TOOLSET_ARTIFACT_SCHEMA_VERSION = "model-visible-toolset.p0.v1"


class ToolEffect(StrEnum):
    READ = "READ"
    RETRIEVAL = "RETRIEVAL"
    ACTION = "ACTION"


class ToolSpec(ModelVisibleModel):
    """The complete safe Tool definition that a model may see."""

    name: ToolName
    description: NonEmptyString
    input_schema: Mapping[str, JsonValue]
    output_schema: Mapping[str, JsonValue]

    @field_validator("input_schema", "output_schema", mode="before")
    @classmethod
    def schema_input_is_native_json(cls, value: Any) -> Any:
        return thaw_json_value(value)

    @field_validator("input_schema", "output_schema")
    @classmethod
    def schema_is_closed_json_object(
        cls, value: Mapping[str, JsonValue]
    ) -> Mapping[str, JsonValue]:
        copied = deepcopy(value)
        if copied.get("type") != "object":
            raise ValueError("tool schemas must declare type=object")
        if copied.get("additionalProperties") is not False:
            raise ValueError("tool schemas must set additionalProperties=false")
        return freeze_json_value(copied)

    @field_validator("input_schema", "output_schema")
    @classmethod
    def model_schema_excludes_trusted_fields(
        cls, value: Mapping[str, JsonValue]
    ) -> Mapping[str, JsonValue]:
        forbidden = find_trusted_argument_field(value)
        if forbidden is not None:
            raise ValueError(
                f"model-visible ToolSpec cannot declare trusted field {forbidden!r}"
            )
        return value

    @field_serializer("input_schema", "output_schema")
    def serialize_schema(
        self, value: Mapping[str, JsonValue]
    ) -> dict[str, JsonValue]:
        return thaw_json_value(value)


class ExecutionPolicy(RuntimePrivateModel):
    timeout_ms: Annotated[int, Field(gt=0)]
    max_attempts: Annotated[int, Field(ge=1)]
    retryable_failure_codes: tuple[NonEmptyString, ...] = ()
    interrupt_behavior: NonEmptyString


class ToolRegistration(RuntimePrivateModel):
    """Runtime-private registration; only ``tool_spec`` is model-projectable."""

    tool_spec: ToolSpec
    provider_visible_name: ToolName
    effect: ToolEffect
    risk: NonEmptyString
    idempotency: NonEmptyString
    unknown_result_recovery: NonEmptyString | None = None
    handler_ref: NonEmptyString
    execution_policy: ExecutionPolicy

    @model_validator(mode="after")
    def action_has_explicit_recovery(self) -> Self:
        if self.effect is ToolEffect.ACTION and self.unknown_result_recovery is None:
            raise ValueError("ACTION registration requires unknown-result recovery")
        if self.effect is ToolEffect.ACTION and self.execution_policy.max_attempts != 1:
            raise ValueError("ACTION registration cannot use generic automatic retry")
        return self


class ProviderToolNameBinding(AuditOnlyModel):
    provider_visible_name: ToolName
    canonical_tool_name: ToolName


def compute_model_visible_toolset_hash(tools: Sequence[ToolSpec]) -> str:
    """Hash the sorted, final provider-visible ToolSpec projection."""

    sorted_tools = sorted(tools, key=lambda tool: tool.name)
    names = [tool.name for tool in sorted_tools]
    if not names:
        raise ValueError("model-visible toolset cannot be empty")
    if len(names) != len(set(names)):
        raise ValueError("provider-visible tool names must be unique")

    payload = {
        "artifact_schema_version": MODEL_VISIBLE_TOOLSET_ARTIFACT_SCHEMA_VERSION,
        "tools": [tool.model_dump(mode="json") for tool in sorted_tools],
    }
    canonical_json = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical_json).hexdigest()}"


class ModelVisibleToolsetArtifact(AuditOnlyModel):
    artifact_schema_version: Literal["model-visible-toolset.p0.v1"] = (
        MODEL_VISIBLE_TOOLSET_ARTIFACT_SCHEMA_VERSION
    )
    model_visible_toolset_hash: ToolsetHash
    provider_visible_tool_specs: tuple[ToolSpec, ...]

    @model_validator(mode="after")
    def hash_matches_projection(self) -> Self:
        expected = compute_model_visible_toolset_hash(
            self.provider_visible_tool_specs
        )
        if self.model_visible_toolset_hash != expected:
            raise ValueError("model_visible_toolset_hash does not match ToolSpec payload")
        return self


class RegistrySnapshot(RuntimePrivateModel):
    """Frozen registration view shared by model projection and Gate validation."""

    tool_registry_version: NonEmptyString
    canonical_registrations: tuple[ToolRegistration, ...]
    provider_visible_toolset: tuple[ToolSpec, ...]
    provider_name_to_canonical_name: tuple[ProviderToolNameBinding, ...]
    model_visible_toolset_hash: ToolsetHash

    @classmethod
    def build(
        cls,
        *,
        tool_registry_version: str,
        registrations: Sequence[ToolRegistration],
    ) -> Self:
        frozen_registrations = tuple(registrations)
        if not frozen_registrations:
            raise ValueError("registry snapshot cannot be empty")

        canonical_names = [
            registration.tool_spec.name for registration in frozen_registrations
        ]
        provider_names = [
            registration.provider_visible_name
            for registration in frozen_registrations
        ]
        if len(canonical_names) != len(set(canonical_names)):
            raise ValueError("canonical tool names must be unique")
        if len(provider_names) != len(set(provider_names)):
            raise ValueError("provider-visible tool names must be unique")

        provider_visible_toolset = tuple(
            ToolSpec(
                name=registration.provider_visible_name,
                description=registration.tool_spec.description,
                input_schema=thaw_json_value(registration.tool_spec.input_schema),
                output_schema=thaw_json_value(
                    registration.tool_spec.output_schema
                ),
            )
            for registration in sorted(
                frozen_registrations,
                key=lambda item: item.provider_visible_name,
            )
        )
        bindings = tuple(
            ProviderToolNameBinding(
                provider_visible_name=registration.provider_visible_name,
                canonical_tool_name=registration.tool_spec.name,
            )
            for registration in sorted(
                frozen_registrations,
                key=lambda item: item.provider_visible_name,
            )
        )
        return cls(
            tool_registry_version=tool_registry_version,
            canonical_registrations=frozen_registrations,
            provider_visible_toolset=provider_visible_toolset,
            provider_name_to_canonical_name=bindings,
            model_visible_toolset_hash=compute_model_visible_toolset_hash(
                provider_visible_toolset
            ),
        )

    @model_validator(mode="after")
    def snapshot_is_self_consistent(self) -> Self:
        expected_hash = compute_model_visible_toolset_hash(
            self.provider_visible_toolset
        )
        if self.model_visible_toolset_hash != expected_hash:
            raise ValueError("registry snapshot ToolSpec hash mismatch")

        canonical_names = [
            registration.tool_spec.name
            for registration in self.canonical_registrations
        ]
        provider_names = [
            registration.provider_visible_name
            for registration in self.canonical_registrations
        ]
        if len(canonical_names) != len(set(canonical_names)):
            raise ValueError("canonical tool names must be unique")
        if len(provider_names) != len(set(provider_names)):
            raise ValueError("provider-visible tool names must be unique")

        expected_bindings = {
            registration.provider_visible_name: registration.tool_spec.name
            for registration in self.canonical_registrations
        }
        actual_bindings = {
            binding.provider_visible_name: binding.canonical_tool_name
            for binding in self.provider_name_to_canonical_name
        }
        if actual_bindings != expected_bindings:
            raise ValueError("provider name mapping does not match registrations")
        if {tool.name for tool in self.provider_visible_toolset} != set(
            expected_bindings
        ):
            raise ValueError("provider-visible ToolSpec set does not match mapping")
        return self

    def artifact(self) -> ModelVisibleToolsetArtifact:
        return ModelVisibleToolsetArtifact(
            model_visible_toolset_hash=self.model_visible_toolset_hash,
            provider_visible_tool_specs=self.provider_visible_toolset,
        )


class GateDecisionValue(StrEnum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"


class GateReasonCode(StrEnum):
    ACTION_REQUIRES_PROPOSAL = "ACTION_REQUIRES_PROPOSAL"
    ARGUMENT_BINDING_MISMATCH = "ARGUMENT_BINDING_MISMATCH"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    NO_PROGRESS = "NO_PROGRESS"
    SCHEMA_INVALID = "SCHEMA_INVALID"
    SNAPSHOT_MISMATCH = "SNAPSHOT_MISMATCH"
    STATE_VERSION_MISMATCH = "STATE_VERSION_MISMATCH"
    TOOL_NOT_REGISTERED = "TOOL_NOT_REGISTERED"
    TRUSTED_FIELD_INJECTION = "TRUSTED_FIELD_INJECTION"


_GATE_REASON_TO_FAILED_CHECK: dict[GateReasonCode, str] = {
    GateReasonCode.ACTION_REQUIRES_PROPOSAL: "action_boundary_valid",
    GateReasonCode.ARGUMENT_BINDING_MISMATCH: "argument_binding_valid",
    GateReasonCode.BUDGET_EXCEEDED: "budget_valid",
    GateReasonCode.NO_PROGRESS: "progress_valid",
    GateReasonCode.SCHEMA_INVALID: "schema_valid",
    GateReasonCode.SNAPSHOT_MISMATCH: "snapshot_match",
    GateReasonCode.STATE_VERSION_MISMATCH: "state_version_valid",
    GateReasonCode.TOOL_NOT_REGISTERED: "registration_valid",
    GateReasonCode.TRUSTED_FIELD_INJECTION: "trusted_field_valid",
}


class GateDecision(AuditOnlyModel):
    gate_decision_id: UUID
    model_call_id: UUID
    context_manifest_id: UUID
    provider_tool_call_id: NonEmptyString | None = None
    requested_provider_tool_name: NonEmptyString
    resolved_canonical_tool_name: ToolName | None = None
    snapshot_match: bool
    registration_valid: bool
    schema_valid: bool
    trusted_field_valid: bool
    argument_binding_valid: bool
    argument_binding_refs: tuple[UUID, ...] = ()
    budget_valid: bool
    progress_valid: bool
    proposed_base_task_state_version: Annotated[int, Field(ge=1)] | None = None
    validated_task_state_version: Annotated[int, Field(ge=1)] | None = None
    state_version_valid: bool
    action_boundary_valid: bool
    decision: GateDecisionValue
    reason_code: GateReasonCode | None = None
    decided_at: datetime

    @field_validator("decided_at")
    @classmethod
    def decided_at_is_utc(cls, value: datetime) -> datetime:
        return require_utc(value, field_name="decided_at")

    @model_validator(mode="after")
    def decision_matches_checks(self) -> Self:
        checks = (
            self.snapshot_match,
            self.registration_valid,
            self.schema_valid,
            self.trusted_field_valid,
            self.argument_binding_valid,
            self.budget_valid,
            self.progress_valid,
            self.state_version_valid,
            self.action_boundary_valid,
        )
        if self.decision is GateDecisionValue.ACCEPT:
            if not all(checks):
                raise ValueError("accepted GateDecision requires every Gate to pass")
            if self.resolved_canonical_tool_name is None:
                raise ValueError("accepted GateDecision requires a canonical tool")
            if self.validated_task_state_version is None:
                raise ValueError("accepted GateDecision requires a validated state version")
            if not self.argument_binding_refs:
                raise ValueError("accepted GateDecision requires argument bindings")
            if self.reason_code is not None:
                raise ValueError("accepted GateDecision cannot carry a rejection reason")
        else:
            if self.reason_code is None:
                raise ValueError("rejected GateDecision requires a stable reason code")
            if all(checks):
                raise ValueError(
                    "rejected GateDecision requires at least one failed Gate check"
                )
            failed_check = _GATE_REASON_TO_FAILED_CHECK[self.reason_code]
            if getattr(self, failed_check):
                raise ValueError(
                    "GateDecision reason_code must match its failed Gate check"
                )
            if (
                self.reason_code is GateReasonCode.ARGUMENT_BINDING_MISMATCH
                and not self.argument_binding_refs
            ):
                raise ValueError(
                    "ARGUMENT_BINDING_MISMATCH requires argument_binding_refs"
                )
        return self


class AuthorizedToolCommand(RuntimePrivateModel):
    gate_decision_id: UUID
    canonical_tool_name: ToolName
    validated_arguments: Mapping[str, JsonValue]
    argument_binding_refs: Annotated[tuple[UUID, ...], Field(min_length=1)]
    validated_task_state_version: Annotated[int, Field(ge=1)]
    registry_snapshot_ref: NonEmptyString
    trusted_context_ref: NonEmptyString

    @field_validator("validated_arguments", mode="before")
    @classmethod
    def validated_argument_input_is_native_json(cls, value: Any) -> Any:
        return thaw_json_value(value)

    @field_validator("validated_arguments")
    @classmethod
    def validated_arguments_exclude_trusted_fields(
        cls, value: Mapping[str, JsonValue]
    ) -> Mapping[str, JsonValue]:
        copied = deepcopy(value)
        forbidden = find_trusted_argument_field(copied)
        if forbidden is not None:
            raise ValueError(
                f"validated business arguments cannot include {forbidden!r}"
            )
        return freeze_json_value(copied)

    @field_serializer("validated_arguments")
    def serialize_validated_arguments(
        self, value: Mapping[str, JsonValue]
    ) -> dict[str, JsonValue]:
        return thaw_json_value(value)

    @field_validator("argument_binding_refs")
    @classmethod
    def argument_bindings_are_present(
        cls, value: tuple[UUID, ...]
    ) -> tuple[UUID, ...]:
        if not value:
            raise ValueError("AuthorizedToolCommand requires argument bindings")
        return value


class ToolCallStatus(StrEnum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    INTERRUPTED = "INTERRUPTED"


class ToolTimeoutPhase(StrEnum):
    BEFORE_DISPATCH = "BEFORE_DISPATCH"
    AFTER_DISPATCH = "AFTER_DISPATCH"
    UNKNOWN = "UNKNOWN"


class ToolCallRecord(AuditOnlyModel):
    tool_call_id: UUID
    run_id: UUID
    task_id: UUID
    request_unit_id: UUID
    model_call_id: UUID
    context_manifest_id: UUID
    gate_decision_id: UUID
    provider_tool_call_id: NonEmptyString | None = None
    canonical_tool_name: ToolName
    tool_registry_version: NonEmptyString
    validated_task_state_version: Annotated[int, Field(ge=1)]
    argument_binding_refs: Annotated[tuple[UUID, ...], Field(min_length=1)]
    effect: ToolEffect
    attempt_count: Annotated[int, Field(ge=0)]
    status: ToolCallStatus
    started_at: datetime
    finished_at: datetime | None = None
    failure_code: NonEmptyString | None = None
    timeout_phase: ToolTimeoutPhase | None = None
    interruption_reason: SafeReasonCode | None = None
    result_ref: UUID | None = None

    @field_validator("started_at", "finished_at")
    @classmethod
    def timestamps_are_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return require_utc(value, field_name="ToolCallRecord timestamp")

    @model_validator(mode="after")
    def lifecycle_is_consistent(self) -> Self:
        terminal = {
            ToolCallStatus.SUCCEEDED,
            ToolCallStatus.FAILED,
            ToolCallStatus.TIMED_OUT,
            ToolCallStatus.INTERRUPTED,
        }
        if (
            self.status is not ToolCallStatus.CREATED
            and self.attempt_count < 1
        ):
            raise ValueError("initiated ToolCall requires attempt_count >= 1")
        if self.status in terminal and self.finished_at is None:
            raise ValueError("terminal ToolCall requires finished_at")
        if self.status not in terminal and self.finished_at is not None:
            raise ValueError("non-terminal ToolCall cannot have finished_at")
        if self.finished_at is not None and self.finished_at < self.started_at:
            raise ValueError("ToolCall finished_at cannot precede started_at")
        if self.status is ToolCallStatus.SUCCEEDED and self.failure_code is not None:
            raise ValueError("succeeded ToolCall cannot carry failure_code")
        if self.status is ToolCallStatus.TIMED_OUT:
            if self.timeout_phase is None:
                raise ValueError("timed-out ToolCall requires a safe timeout_phase")
        elif self.timeout_phase is not None:
            raise ValueError("only timed-out ToolCall can carry timeout_phase")
        if self.status is ToolCallStatus.INTERRUPTED:
            if self.interruption_reason is None:
                raise ValueError(
                    "interrupted ToolCall requires a safe interruption_reason"
                )
        elif self.interruption_reason is not None:
            raise ValueError(
                "only interrupted ToolCall can carry interruption_reason"
            )
        return self


class ToolResultOutcome(StrEnum):
    SUCCESS = "SUCCESS"
    BUSINESS_FAILURE = "BUSINESS_FAILURE"
    SYSTEM_FAILURE = "SYSTEM_FAILURE"
    TIMEOUT = "TIMEOUT"
    INTERRUPTED = "INTERRUPTED"
    RESULT_UNKNOWN = "RESULT_UNKNOWN"


class ToolAttemptRecord(AuditOnlyModel):
    tool_call_id: UUID
    attempt_no: Annotated[int, Field(ge=1)]
    started_at: datetime
    finished_at: datetime | None = None
    outcome: ToolResultOutcome
    failure_code: NonEmptyString | None = None

    @field_validator("started_at", "finished_at")
    @classmethod
    def attempt_timestamps_are_utc(
        cls, value: datetime | None
    ) -> datetime | None:
        if value is None:
            return None
        return require_utc(value, field_name="ToolAttemptRecord timestamp")

    @model_validator(mode="after")
    def attempt_dates_are_ordered(self) -> Self:
        if self.finished_at is not None and self.finished_at < self.started_at:
            raise ValueError("ToolAttempt finished_at cannot precede started_at")
        return self


class ToolResult(RuntimePrivateModel):
    tool_call_id: UUID
    canonical_tool_name: ToolName
    outcome: ToolResultOutcome
    payload: JsonValue | None = None
    error_code: NonEmptyString | None = None
    retryable: bool
    raw_result_ref: NonEmptyString | None = None
    observed_at: datetime | None = None
    completed_at: datetime

    @field_validator("payload", mode="before")
    @classmethod
    def payload_input_is_native_json(cls, value: Any) -> Any:
        return thaw_json_value(value)

    @field_validator("payload")
    @classmethod
    def payload_is_recursively_frozen(
        cls, value: JsonValue | None
    ) -> JsonValue | None:
        if value is None:
            return None
        return freeze_json_value(deepcopy(value))

    @field_serializer("payload")
    def serialize_payload(self, value: JsonValue | None) -> JsonValue | None:
        return thaw_json_value(value)

    @field_validator("observed_at", "completed_at")
    @classmethod
    def result_timestamps_are_utc(
        cls, value: datetime | None
    ) -> datetime | None:
        if value is None:
            return None
        return require_utc(value, field_name="ToolResult timestamp")


def get_order_tool_spec() -> ToolSpec:
    """Return the scoped E2E01 ``get_order`` agent-visible contract."""

    return ToolSpec(
        name="get_order",
        description="查询当前已登录用户可访问的单个订单，并返回最小订单摘要。",
        input_schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "order_id": {
                    "type": "string",
                    "pattern": r"^O-[0-9]{4,20}$",
                }
            },
            "required": ["order_id"],
        },
        output_schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "outcome": {
                    "enum": [
                        "FOUND",
                        "NOT_FOUND_OR_NOT_ACCESSIBLE",
                        "SYSTEM_FAILURE",
                    ]
                },
                "order_summary": {
                    "type": ["object", "null"],
                    "additionalProperties": False,
                    "properties": {
                        "order_number": {"type": "string"},
                        "status": {
                            "enum": [
                                "CREATED",
                                "PAID",
                                "FULFILLING",
                                "SHIPPED",
                                "DELIVERED",
                                "CANCELLED",
                            ]
                        },
                        "line_items": {
                            "type": "array",
                            "minItems": 1,
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "product_name": {
                                        "type": "string",
                                        "minLength": 1,
                                    },
                                    "quantity": {
                                        "type": "integer",
                                        "minimum": 1,
                                    },
                                },
                                "required": ["product_name", "quantity"],
                            },
                        },
                        "ordered_at": {"type": "string", "format": "date-time"},
                        "status_updated_at": {
                            "type": "string",
                            "format": "date-time",
                        },
                    },
                    "required": [
                        "order_number",
                        "status",
                        "line_items",
                        "ordered_at",
                        "status_updated_at",
                    ],
                },
                "failure_code": {"type": ["string", "null"]},
            },
            "required": ["outcome"],
        },
    )
