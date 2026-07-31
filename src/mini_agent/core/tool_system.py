"""Core-owned ToolSpec, immutable snapshot, Gate, and ToolCall contracts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence, Set as AbstractSet
from copy import deepcopy
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    Field,
    JsonValue,
    TypeAdapter,
    ValidationError,
    field_serializer,
    field_validator,
    model_validator,
)
from pydantic_core import PydanticSerializationError

from .common import (
    AuditOnlyModel,
    ModelVisibleModel,
    RuntimePrivateModel,
    find_trusted_argument_field,
    freeze_json_value,
    require_utc,
    thaw_json_value,
)
from .shipment import GetShipmentInsufficiencyCode

NonEmptyString = Annotated[str, Field(min_length=1)]
ToolName = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$")]
ToolsetHash = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
SafeReasonCode = Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]{1,127}$")]

MODEL_VISIBLE_TOOLSET_ARTIFACT_SCHEMA_VERSION = "model-visible-toolset.p0.v1"
CYCLE2_TOOL_REGISTRY_VERSION = "e2e01-cycle2-tools.p0.v1"


class ToolEffect(StrEnum):
    READ = "READ"
    RETRIEVAL = "RETRIEVAL"
    ACTION = "ACTION"


class Cycle2ToolName(StrEnum):
    """The exact inactive E2E-01 Cycle 2 Read Tool set."""

    SEARCH_ORDERS = "search_orders"
    GET_ORDER = "get_order"
    GET_SHIPMENT = "get_shipment"


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
    def serialize_schema(self, value: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
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
        allow_nan=False,
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
        expected = compute_model_visible_toolset_hash(self.provider_visible_tool_specs)
        if self.model_visible_toolset_hash != expected:
            raise ValueError(
                "model_visible_toolset_hash does not match ToolSpec payload"
            )
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
            registration.provider_visible_name for registration in frozen_registrations
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
                output_schema=thaw_json_value(registration.tool_spec.output_schema),
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
            registration.tool_spec.name for registration in self.canonical_registrations
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
                raise ValueError(
                    "accepted GateDecision requires a validated state version"
                )
            if not self.argument_binding_refs:
                raise ValueError("accepted GateDecision requires argument bindings")
            if self.reason_code is not None:
                raise ValueError(
                    "accepted GateDecision cannot carry a rejection reason"
                )
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
    def argument_bindings_are_present(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
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
        requires_attempt = {
            ToolCallStatus.RUNNING,
            ToolCallStatus.SUCCEEDED,
            ToolCallStatus.FAILED,
            ToolCallStatus.TIMED_OUT,
        }
        if self.status is ToolCallStatus.CREATED and self.attempt_count != 0:
            raise ValueError("created ToolCall requires attempt_count = 0")
        if self.status in requires_attempt and self.attempt_count < 1:
            raise ValueError("dispatched ToolCall requires attempt_count >= 1")
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
            raise ValueError("only interrupted ToolCall can carry interruption_reason")
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
    outcome: ToolResultOutcome | None = None
    failure_code: NonEmptyString | None = None

    @field_validator("started_at", "finished_at")
    @classmethod
    def attempt_timestamps_are_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return require_utc(value, field_name="ToolAttemptRecord timestamp")

    @model_validator(mode="after")
    def lifecycle_is_consistent(self) -> Self:
        if self.finished_at is None:
            if self.outcome is not None:
                raise ValueError("active ToolAttempt cannot carry outcome")
            if self.failure_code is not None:
                raise ValueError("active ToolAttempt cannot carry failure_code")
            return self
        if self.outcome is None:
            raise ValueError("finalized ToolAttempt requires outcome")
        if self.finished_at is not None and self.finished_at < self.started_at:
            raise ValueError("ToolAttempt finished_at cannot precede started_at")
        if (
            self.outcome is ToolResultOutcome.SUCCESS
            and self.failure_code is not None
        ):
            raise ValueError("successful ToolAttempt cannot carry failure_code")
        return self


class ToolRetryDecision(StrEnum):
    """Exact inactive Cycle 2 attempt-finalization decision vocabulary."""

    NOT_APPLICABLE = "NOT_APPLICABLE"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"
    NOT_RETRYABLE = "NOT_RETRYABLE"
    MAX_ATTEMPTS_REACHED = "MAX_ATTEMPTS_REACHED"
    RUN_BUDGET_EXHAUSTED = "RUN_BUDGET_EXHAUSTED"
    STATE_OR_BINDING_INVALIDATED = "STATE_OR_BINDING_INVALIDATED"


class ToolAttemptRecordV2(AuditOnlyModel):
    """Inactive v2 attempt contract; no codec or dispatcher consumes it yet."""

    tool_call_id: UUID
    attempt_no: Annotated[int, Field(strict=True, ge=1, le=2)]
    started_at: datetime
    finished_at: datetime | None = None
    outcome: ToolResultOutcome | None = None
    failure_code: SafeReasonCode | None = None
    timeout_phase: ToolTimeoutPhase | None = None
    retry_decision: ToolRetryDecision | None = None

    @field_validator("started_at", "finished_at")
    @classmethod
    def attempt_timestamps_are_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return require_utc(value, field_name="ToolAttemptRecordV2 timestamp")

    @model_validator(mode="after")
    def lifecycle_is_closed(self) -> Self:
        completion = (
            self.finished_at,
            self.outcome,
            self.retry_decision,
        )
        if all(value is None for value in completion):
            if self.failure_code is not None or self.timeout_phase is not None:
                raise ValueError(
                    "unfinished v2 attempt has identity/start only"
                )
            return self
        if any(value is None for value in completion):
            raise ValueError(
                "v2 attempt must finalize finished_at/outcome/retry_decision atomically"
            )
        if self.finished_at < self.started_at:
            raise ValueError("v2 attempt finished_at cannot precede started_at")
        if self.outcome is ToolResultOutcome.RESULT_UNKNOWN:
            raise ValueError("Cycle 2 Read attempt cannot use RESULT_UNKNOWN")

        if self.outcome is ToolResultOutcome.SUCCESS:
            if self.failure_code is not None or self.timeout_phase is not None:
                raise ValueError("successful v2 attempt cannot carry failure metadata")
            if self.retry_decision is not ToolRetryDecision.NOT_APPLICABLE:
                raise ValueError("successful v2 attempt requires NOT_APPLICABLE")
        elif self.outcome is ToolResultOutcome.TIMEOUT:
            if self.failure_code != "TOOL_CALL_TIMEOUT":
                raise ValueError("TIMEOUT iff failure_code is TOOL_CALL_TIMEOUT")
            if self.timeout_phase is None:
                raise ValueError("TIMEOUT requires timeout_phase")
            if self.retry_decision not in {
                ToolRetryDecision.RETRY_SCHEDULED,
                ToolRetryDecision.MAX_ATTEMPTS_REACHED,
                ToolRetryDecision.RUN_BUDGET_EXHAUSTED,
                ToolRetryDecision.STATE_OR_BINDING_INVALIDATED,
            }:
                raise ValueError("TIMEOUT retry_decision is outside the closed matrix")
        else:
            if self.failure_code is None:
                raise ValueError("non-success v2 attempt requires failure_code")
            if self.failure_code == "TOOL_CALL_TIMEOUT":
                raise ValueError("TIMEOUT iff failure_code is TOOL_CALL_TIMEOUT")
            if self.timeout_phase is not None:
                raise ValueError("only TIMEOUT may carry timeout_phase")
            if self.outcome is ToolResultOutcome.BUSINESS_FAILURE:
                if self.retry_decision is not ToolRetryDecision.NOT_RETRYABLE:
                    raise ValueError("business failure must be NOT_RETRYABLE")
            elif self.outcome is ToolResultOutcome.SYSTEM_FAILURE:
                if self.retry_decision not in {
                    ToolRetryDecision.RETRY_SCHEDULED,
                    ToolRetryDecision.NOT_RETRYABLE,
                    ToolRetryDecision.MAX_ATTEMPTS_REACHED,
                    ToolRetryDecision.RUN_BUDGET_EXHAUSTED,
                    ToolRetryDecision.STATE_OR_BINDING_INVALIDATED,
                }:
                    raise ValueError(
                        "system failure retry_decision is outside the closed matrix"
                    )
            elif self.outcome is ToolResultOutcome.INTERRUPTED:
                if self.retry_decision not in {
                    ToolRetryDecision.NOT_RETRYABLE,
                    ToolRetryDecision.RUN_BUDGET_EXHAUSTED,
                    ToolRetryDecision.STATE_OR_BINDING_INVALIDATED,
                }:
                    raise ValueError(
                        "interrupted retry_decision is outside the closed matrix"
                    )
            else:
                raise ValueError("unknown v2 attempt outcome")
        return self


class Cycle2ToolDispatchFacts(RuntimePrivateModel):
    """Immutable parent dispatch identity used by retry/recovery closure checks."""

    tool_call_id: UUID
    run_id: UUID
    private_owner_scope_ref: NonEmptyString
    task_id: UUID
    request_unit_id: UUID
    validated_task_state_version: Annotated[int, Field(strict=True, ge=1)]
    argument_binding_refs: Annotated[tuple[UUID, ...], Field(min_length=1)]
    verified_target_ref: UUID | None = None

    @field_validator("argument_binding_refs")
    @classmethod
    def binding_refs_are_unique(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        if len(value) != len(set(value)):
            raise ValueError("dispatch binding refs must be unique")
        return value


class Cycle2RetryRevalidation(RuntimePrivateModel):
    """Parent -> expected -> current closure used by pure retry decisions."""

    parent_dispatch_facts: Cycle2ToolDispatchFacts
    expected_dispatch_facts: Cycle2ToolDispatchFacts
    current_dispatch_facts: Cycle2ToolDispatchFacts
    remaining_run_time_budget_ms: Annotated[int, Field(strict=True, ge=0)]

    def current_closure_matches(self) -> bool:
        return (
            self.parent_dispatch_facts == self.expected_dispatch_facts
            and self.expected_dispatch_facts == self.current_dispatch_facts
        )


_CYCLE2_MAX_ATTEMPTS: dict[Cycle2ToolName, int] = {
    Cycle2ToolName.SEARCH_ORDERS: 2,
    Cycle2ToolName.GET_ORDER: 1,
    Cycle2ToolName.GET_SHIPMENT: 2,
}
_CYCLE2_RETRYABLE_FAILURE_CODES: dict[Cycle2ToolName, frozenset[str]] = {
    Cycle2ToolName.SEARCH_ORDERS: frozenset(
        {"ORDER_SEARCH_TRANSIENT", "TOOL_CALL_TIMEOUT"}
    ),
    Cycle2ToolName.GET_ORDER: frozenset(),
    Cycle2ToolName.GET_SHIPMENT: frozenset(
        {"SHIPMENT_SERVICE_TRANSIENT", "TOOL_CALL_TIMEOUT"}
    ),
}
_CYCLE2_BUSINESS_FAILURE_CODES: dict[Cycle2ToolName, frozenset[str]] = {
    Cycle2ToolName.SEARCH_ORDERS: frozenset({"NO_MATCH"}),
    Cycle2ToolName.GET_ORDER: frozenset({"NOT_FOUND_OR_NOT_ACCESSIBLE"}),
    Cycle2ToolName.GET_SHIPMENT: frozenset(
        {
            "NO_SHIPMENT",
            "NOT_FOUND_OR_NOT_ACCESSIBLE",
            *(code.value for code in GetShipmentInsufficiencyCode),
        }
    ),
}
_CYCLE2_SYSTEM_FAILURE_CODES: dict[Cycle2ToolName, frozenset[str]] = {
    Cycle2ToolName.SEARCH_ORDERS: frozenset(
        {
            "ORDER_SEARCH_TRANSIENT",
            "ORDER_SEARCH_UNAVAILABLE",
            "ORDER_SEARCH_SOURCE_INTEGRITY",
        }
    ),
    Cycle2ToolName.GET_ORDER: frozenset({"ORDER_SERVICE_UNAVAILABLE"}),
    Cycle2ToolName.GET_SHIPMENT: frozenset(
        {
            "SHIPMENT_SERVICE_TRANSIENT",
            "SHIPMENT_SERVICE_UNAVAILABLE",
            "SHIPMENT_RELATION_CARDINALITY_VIOLATION",
            "SHIPMENT_SOURCE_INTEGRITY",
            "SHIPMENT_SOURCE_VERSION_INVALID",
        }
    ),
}
_CYCLE2_INTERRUPTION_CODES = frozenset(
    {
        "USER_MESSAGE_SUPERSEDED",
        "RUN_BUDGET_EXHAUSTED",
        "PROVIDER_STREAM_TERMINATED",
        "HANDLER_EXECUTION_CANCELLED",
        "PROCESS_RESTART_DETECTED",
        "STATE_OR_BINDING_INVALIDATED",
    }
)


def effective_cycle2_tool_timeout_ms(remaining_run_time_budget_ms: int) -> int:
    """Return ``min(500, remaining)`` for a dispatchable positive budget."""

    if type(remaining_run_time_budget_ms) is not int:
        raise TypeError("remaining_run_time_budget_ms must be a strict integer")
    if remaining_run_time_budget_ms <= 0:
        raise ValueError("remaining_run_time_budget_ms must be positive")
    return min(500, remaining_run_time_budget_ms)


def _validate_cycle2_failure_shape(
    *,
    canonical_tool_name: Cycle2ToolName,
    outcome: ToolResultOutcome,
    failure_code: str | None,
) -> None:
    if outcome is ToolResultOutcome.SUCCESS:
        if failure_code is not None:
            raise ValueError("SUCCESS cannot carry failure_code")
    elif outcome is ToolResultOutcome.TIMEOUT:
        if failure_code != "TOOL_CALL_TIMEOUT":
            raise ValueError("TIMEOUT requires TOOL_CALL_TIMEOUT")
    elif outcome is ToolResultOutcome.BUSINESS_FAILURE:
        if failure_code not in _CYCLE2_BUSINESS_FAILURE_CODES[canonical_tool_name]:
            raise ValueError("unknown business failure code for Cycle 2 tool")
    elif outcome is ToolResultOutcome.SYSTEM_FAILURE:
        if failure_code not in _CYCLE2_SYSTEM_FAILURE_CODES[canonical_tool_name]:
            raise ValueError("unknown system failure code for Cycle 2 tool")
    elif outcome is ToolResultOutcome.INTERRUPTED:
        if failure_code not in _CYCLE2_INTERRUPTION_CODES:
            raise ValueError("unknown interruption code for Cycle 2 tool")
    else:
        raise ValueError("Cycle 2 Read retry does not accept RESULT_UNKNOWN")


def decide_cycle2_tool_retry(
    *,
    canonical_tool_name: Cycle2ToolName,
    attempt_no: int,
    outcome: ToolResultOutcome,
    failure_code: str | None,
    revalidation: Cycle2RetryRevalidation,
) -> ToolRetryDecision:
    """Apply the exact policy and loaded-fact comparisons without persistence IO."""

    if not isinstance(canonical_tool_name, Cycle2ToolName):
        raise TypeError("canonical_tool_name must be a Cycle2ToolName")
    revalidation = Cycle2RetryRevalidation.model_validate(revalidation.model_dump())
    if type(attempt_no) is not int or attempt_no < 1:
        raise ValueError("attempt_no must be a strict positive integer")
    max_attempts = _CYCLE2_MAX_ATTEMPTS[canonical_tool_name]
    if attempt_no > max_attempts:
        raise ValueError("attempt_no exceeds the exact Tool policy")
    if not isinstance(outcome, ToolResultOutcome):
        raise TypeError("outcome must be a ToolResultOutcome")
    _validate_cycle2_failure_shape(
        canonical_tool_name=canonical_tool_name,
        outcome=outcome,
        failure_code=failure_code,
    )
    if outcome is ToolResultOutcome.SUCCESS:
        return ToolRetryDecision.NOT_APPLICABLE
    if outcome is ToolResultOutcome.BUSINESS_FAILURE:
        return ToolRetryDecision.NOT_RETRYABLE
    if outcome is ToolResultOutcome.INTERRUPTED:
        if failure_code == "RUN_BUDGET_EXHAUSTED":
            return ToolRetryDecision.RUN_BUDGET_EXHAUSTED
        if failure_code == "STATE_OR_BINDING_INVALIDATED":
            return ToolRetryDecision.STATE_OR_BINDING_INVALIDATED
        return ToolRetryDecision.NOT_RETRYABLE

    retryable_codes = _CYCLE2_RETRYABLE_FAILURE_CODES[canonical_tool_name]
    if outcome is ToolResultOutcome.TIMEOUT and attempt_no >= max_attempts:
        return ToolRetryDecision.MAX_ATTEMPTS_REACHED
    if failure_code not in retryable_codes:
        return ToolRetryDecision.NOT_RETRYABLE
    if attempt_no >= max_attempts:
        return ToolRetryDecision.MAX_ATTEMPTS_REACHED
    if revalidation.remaining_run_time_budget_ms <= 0:
        return ToolRetryDecision.RUN_BUDGET_EXHAUSTED
    if not revalidation.current_closure_matches():
        return ToolRetryDecision.STATE_OR_BINDING_INVALIDATED
    return ToolRetryDecision.RETRY_SCHEDULED


def _validate_cycle2_attempt_for_tool(
    attempt: ToolAttemptRecordV2,
    *,
    canonical_tool_name: Cycle2ToolName,
) -> None:
    if attempt.outcome is None:
        return
    _validate_cycle2_failure_shape(
        canonical_tool_name=canonical_tool_name,
        outcome=attempt.outcome,
        failure_code=attempt.failure_code,
    )
    retryable = (
        attempt.failure_code
        in _CYCLE2_RETRYABLE_FAILURE_CODES[canonical_tool_name]
    )
    max_attempts = _CYCLE2_MAX_ATTEMPTS[canonical_tool_name]
    if attempt.retry_decision is ToolRetryDecision.RETRY_SCHEDULED:
        if not retryable or attempt.attempt_no >= max_attempts:
            raise ValueError("deterministic failure cannot schedule retry")
    elif attempt.retry_decision is ToolRetryDecision.MAX_ATTEMPTS_REACHED:
        timeout_at_tool_max = (
            attempt.outcome is ToolResultOutcome.TIMEOUT
            and attempt.attempt_no >= max_attempts
        )
        if not timeout_at_tool_max and (
            not retryable or attempt.attempt_no < max_attempts
        ):
            raise ValueError("MAX_ATTEMPTS_REACHED contradicts Tool policy")
    elif attempt.retry_decision in {
        ToolRetryDecision.RUN_BUDGET_EXHAUSTED,
        ToolRetryDecision.STATE_OR_BINDING_INVALIDATED,
    }:
        if attempt.outcome is not ToolResultOutcome.INTERRUPTED and not retryable:
            raise ValueError("retry termination decision requires retryable failure")
    elif (
        attempt.retry_decision is ToolRetryDecision.NOT_RETRYABLE
        and retryable
        and attempt.outcome is not ToolResultOutcome.INTERRUPTED
    ):
        raise ValueError("retryable failure cannot be marked NOT_RETRYABLE")


class Cycle2ToolTerminalProjection(RuntimePrivateModel):
    """Pure final-attempt projection; it does not mutate a durable ToolCall."""

    status: ToolCallStatus
    finished_at: datetime
    failure_code: SafeReasonCode | None = None
    timeout_phase: ToolTimeoutPhase | None = None
    interruption_reason: SafeReasonCode | None = None

    @field_validator("finished_at")
    @classmethod
    def finished_at_is_utc(cls, value: datetime) -> datetime:
        return require_utc(value, field_name="Cycle2 terminal finished_at")


def project_cycle2_tool_terminal(
    attempt: ToolAttemptRecordV2,
    *,
    canonical_tool_name: Cycle2ToolName,
) -> Cycle2ToolTerminalProjection:
    """Project only a finalized, non-retrying attempt to parent terminal fields."""

    validated = ToolAttemptRecordV2.model_validate(attempt.model_dump())
    _validate_cycle2_attempt_for_tool(
        validated,
        canonical_tool_name=canonical_tool_name,
    )
    if validated.outcome is None or validated.finished_at is None:
        raise ValueError("terminal projection requires a finalized attempt")
    if validated.retry_decision is ToolRetryDecision.RETRY_SCHEDULED:
        raise ValueError("RETRY_SCHEDULED attempt is not terminal")
    if validated.outcome is ToolResultOutcome.SUCCESS:
        return Cycle2ToolTerminalProjection(
            status=ToolCallStatus.SUCCEEDED,
            finished_at=validated.finished_at,
        )
    if validated.outcome in {
        ToolResultOutcome.BUSINESS_FAILURE,
        ToolResultOutcome.SYSTEM_FAILURE,
    }:
        return Cycle2ToolTerminalProjection(
            status=ToolCallStatus.FAILED,
            finished_at=validated.finished_at,
            failure_code=validated.failure_code,
        )
    if validated.outcome is ToolResultOutcome.TIMEOUT:
        return Cycle2ToolTerminalProjection(
            status=ToolCallStatus.TIMED_OUT,
            finished_at=validated.finished_at,
            failure_code="TOOL_CALL_TIMEOUT",
            timeout_phase=validated.timeout_phase,
        )
    if validated.outcome is ToolResultOutcome.INTERRUPTED:
        return Cycle2ToolTerminalProjection(
            status=ToolCallStatus.INTERRUPTED,
            finished_at=validated.finished_at,
            interruption_reason=validated.failure_code,
        )
    raise ValueError("unknown terminal attempt outcome")


class ToolRecoveryDisposition(StrEnum):
    """The only recovery-only parent terminal exceptions for Cycle 2 Reads."""

    UNFINISHED_ATTEMPT_INTERRUPTED = "UNFINISHED_ATTEMPT_INTERRUPTED"
    RETRY_SCHEDULED_STATE_INVALIDATED = "RETRY_SCHEDULED_STATE_INVALIDATED"


class ToolCallRecordV2(AuditOnlyModel):
    """Inactive Cycle 2 parent aggregate with append-only attempt evidence."""

    tool_call_id: UUID
    run_id: UUID
    task_id: UUID
    request_unit_id: UUID
    model_call_id: UUID
    context_manifest_id: UUID
    gate_decision_id: UUID
    provider_tool_call_id: NonEmptyString | None = None
    canonical_tool_name: Cycle2ToolName
    tool_registry_version: Literal["e2e01-cycle2-tools.p0.v1"]
    private_owner_scope_ref: NonEmptyString
    validated_task_state_version: Annotated[int, Field(strict=True, ge=1)]
    argument_binding_refs: Annotated[tuple[UUID, ...], Field(min_length=1)]
    verified_target_ref: UUID | None = None
    effect: Literal[ToolEffect.READ]
    attempt_count: Annotated[int, Field(strict=True, ge=0, le=2)]
    attempts: Annotated[tuple[ToolAttemptRecordV2, ...], Field(max_length=2)]
    status: ToolCallStatus
    started_at: datetime
    finished_at: datetime | None = None
    failure_code: SafeReasonCode | None = None
    timeout_phase: ToolTimeoutPhase | None = None
    interruption_reason: SafeReasonCode | None = None
    result_ref: UUID | None = None
    recovery_disposition: ToolRecoveryDisposition | None = None
    recovery_decision_ref: UUID | None = None

    @field_validator("started_at", "finished_at")
    @classmethod
    def timestamps_are_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return require_utc(value, field_name="ToolCallRecordV2 timestamp")

    @field_validator("argument_binding_refs")
    @classmethod
    def binding_refs_are_unique(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        if len(value) != len(set(value)):
            raise ValueError("ToolCallRecordV2 binding refs must be unique")
        return value

    def dispatch_facts(self) -> Cycle2ToolDispatchFacts:
        """Return the immutable parent fields that every retry must revalidate."""

        return Cycle2ToolDispatchFacts(
            tool_call_id=self.tool_call_id,
            run_id=self.run_id,
            private_owner_scope_ref=self.private_owner_scope_ref,
            task_id=self.task_id,
            request_unit_id=self.request_unit_id,
            validated_task_state_version=self.validated_task_state_version,
            argument_binding_refs=self.argument_binding_refs,
            verified_target_ref=self.verified_target_ref,
        )

    @model_validator(mode="after")
    def aggregate_is_closed(self) -> Self:
        if self.attempt_count != len(self.attempts):
            raise ValueError("attempt_count must equal durable attempt count")
        if any(attempt.tool_call_id != self.tool_call_id for attempt in self.attempts):
            raise ValueError("attempt child tool_call_id mismatch")
        attempt_numbers = tuple(attempt.attempt_no for attempt in self.attempts)
        if attempt_numbers != tuple(range(1, len(self.attempts) + 1)):
            raise ValueError("attempt numbers must be continuous from one")
        for attempt in self.attempts:
            _validate_cycle2_attempt_for_tool(
                attempt,
                canonical_tool_name=self.canonical_tool_name,
            )
            if attempt.started_at < self.started_at:
                raise ValueError("attempt cannot start before ToolCall")
        for previous, current in zip(self.attempts, self.attempts[1:]):
            if (
                previous.finished_at is None
                or previous.retry_decision is not ToolRetryDecision.RETRY_SCHEDULED
            ):
                raise ValueError("next attempt requires finalized RETRY_SCHEDULED fence")
            if current.started_at < previous.finished_at:
                raise ValueError("next attempt cannot start before prior finalize")
        if (
            self.attempts
            and self.attempts[-1].attempt_no == 2
            and self.attempts[-1].retry_decision is ToolRetryDecision.RETRY_SCHEDULED
        ):
            raise ValueError("second attempt cannot schedule a third attempt")

        terminal_statuses = {
            ToolCallStatus.SUCCEEDED,
            ToolCallStatus.FAILED,
            ToolCallStatus.TIMED_OUT,
            ToolCallStatus.INTERRUPTED,
        }
        if self.status is ToolCallStatus.CREATED:
            if self.attempts or self.finished_at is not None:
                raise ValueError("CREATED v2 ToolCall has no attempt or finish")
        elif self.status is ToolCallStatus.RUNNING:
            if not self.attempts or self.finished_at is not None:
                raise ValueError("RUNNING v2 ToolCall requires attempts and no finish")
            last = self.attempts[-1]
            if (
                last.finished_at is not None
                and last.retry_decision is not ToolRetryDecision.RETRY_SCHEDULED
            ):
                raise ValueError("RUNNING finalized attempt must schedule retry")
        elif self.status in terminal_statuses:
            pre_dispatch_interruption = (
                self.status is ToolCallStatus.INTERRUPTED
                and not self.attempts
                and self.attempt_count == 0
            )
            if self.finished_at is None:
                raise ValueError("terminal v2 ToolCall requires parent finish timestamp")
            if pre_dispatch_interruption:
                if (
                    self.interruption_reason not in _CYCLE2_INTERRUPTION_CODES
                    or self.failure_code is not None
                    or self.timeout_phase is not None
                    or self.recovery_disposition is not None
                    or self.recovery_decision_ref is not None
                ):
                    raise ValueError(
                        "pre-dispatch interruption requires only a stable reason"
                    )
            else:
                if not self.attempts:
                    raise ValueError("terminal v2 ToolCall requires finalized attempt")
                last = self.attempts[-1]
                unfinished_recovery = (
                    last.finished_at is None
                    and self.status is ToolCallStatus.INTERRUPTED
                    and self.interruption_reason == "PROCESS_RESTART_DETECTED"
                    and self.recovery_disposition
                    is ToolRecoveryDisposition.UNFINISHED_ATTEMPT_INTERRUPTED
                    and self.recovery_decision_ref is not None
                    and self.failure_code is None
                    and self.timeout_phase is None
                    and self.finished_at >= last.started_at
                )
                scheduled_invalidation_recovery = (
                    last.finished_at is not None
                    and last.retry_decision is ToolRetryDecision.RETRY_SCHEDULED
                    and self.status is ToolCallStatus.INTERRUPTED
                    and self.interruption_reason == "STATE_OR_BINDING_INVALIDATED"
                    and self.recovery_disposition
                    is ToolRecoveryDisposition.RETRY_SCHEDULED_STATE_INVALIDATED
                    and self.recovery_decision_ref is not None
                    and self.failure_code is None
                    and self.timeout_phase is None
                    and self.finished_at >= last.finished_at
                )
                if last.finished_at is None or (
                    last.retry_decision is ToolRetryDecision.RETRY_SCHEDULED
                ):
                    if not (
                        unfinished_recovery or scheduled_invalidation_recovery
                    ):
                        raise ValueError(
                            "recovery disposition/ref does not match the approved "
                            "terminal exception"
                        )
                else:
                    if (
                        self.recovery_disposition is not None
                        or self.recovery_decision_ref is not None
                    ):
                        raise ValueError(
                            "ordinary terminal projection cannot carry recovery metadata"
                        )
                    projection = project_cycle2_tool_terminal(
                        last,
                        canonical_tool_name=self.canonical_tool_name,
                    )
                    if (
                        self.status is not projection.status
                        or self.finished_at != projection.finished_at
                        or self.failure_code != projection.failure_code
                        or self.timeout_phase is not projection.timeout_phase
                        or self.interruption_reason != projection.interruption_reason
                    ):
                        raise ValueError(
                            "ToolCall terminal fields must exactly project last attempt"
                        )
            if self.status is ToolCallStatus.SUCCEEDED:
                if self.result_ref is None:
                    raise ValueError("SUCCEEDED v2 ToolCall requires result_ref")
            elif self.result_ref is not None:
                raise ValueError("non-success v2 ToolCall cannot carry result_ref")
        else:
            raise ValueError("unknown ToolCall status")

        if self.status not in terminal_statuses:
            if any(
                value is not None
                for value in (
                    self.failure_code,
                    self.timeout_phase,
                    self.interruption_reason,
                    self.result_ref,
                    self.recovery_disposition,
                    self.recovery_decision_ref,
                )
            ):
                raise ValueError("non-terminal v2 ToolCall cannot carry terminal metadata")
        if self.finished_at is not None and self.finished_at < self.started_at:
            raise ValueError("ToolCallRecordV2 finished_at cannot precede started_at")
        return self


class ToolRecoveryDecision(StrEnum):
    INTERRUPT_WITHOUT_ATTEMPT = "INTERRUPT_WITHOUT_ATTEMPT"
    INTERRUPT_UNFINISHED_ATTEMPT = "INTERRUPT_UNFINISHED_ATTEMPT"
    APPEND_SECOND_ATTEMPT = "APPEND_SECOND_ATTEMPT"
    TERMINATE_RETRY_PATH = "TERMINATE_RETRY_PATH"
    NO_ACTION_TERMINAL = "NO_ACTION_TERMINAL"
    FAIL_CLOSED = "FAIL_CLOSED"


class ToolRetryRecoveryDecision(RuntimePrivateModel):
    """Pure recovery result; ``durable_cas_claimed`` is intentionally false."""

    tool_call_id: UUID | None
    last_attempt_no: Annotated[int, Field(strict=True, ge=0)]
    decision: ToolRecoveryDecision
    stable_reason_code: SafeReasonCode
    candidate_next_attempt_no: Literal[2] | None = None
    durable_cas_claimed: Literal[False] = False
    decided_at: datetime

    @field_validator("decided_at")
    @classmethod
    def decided_at_is_utc(cls, value: datetime) -> datetime:
        return require_utc(value, field_name="recovery decided_at")

    @model_validator(mode="after")
    def executable_shape_is_closed(self) -> Self:
        if (
            self.decision is not ToolRecoveryDecision.FAIL_CLOSED
            and self.tool_call_id is None
        ):
            raise ValueError("executable recovery evidence requires ToolCall identity")
        if self.decision is ToolRecoveryDecision.APPEND_SECOND_ATTEMPT:
            if self.candidate_next_attempt_no != 2 or self.last_attempt_no != 1:
                raise ValueError("second-attempt decision requires attempt 1 only")
        elif self.candidate_next_attempt_no is not None:
            raise ValueError("non-append recovery cannot grant attempt authority")
        return self


def _recovery_decision(
    *,
    tool_call_id: UUID | None,
    last_attempt_no: int,
    decision: ToolRecoveryDecision,
    stable_reason_code: str,
    decided_at: datetime,
    candidate_next_attempt_no: Literal[2] | None = None,
) -> ToolRetryRecoveryDecision:
    return ToolRetryRecoveryDecision(
        tool_call_id=tool_call_id,
        last_attempt_no=last_attempt_no,
        decision=decision,
        stable_reason_code=stable_reason_code,
        candidate_next_attempt_no=candidate_next_attempt_no,
        decided_at=decided_at,
    )


def _safe_malformed_recovery_identity(
    tool_call: object,
) -> tuple[UUID | None, int]:
    """Extract only an exact UUID from an actual ToolCall contract instance."""

    if type(tool_call) is not ToolCallRecordV2:
        return None, 0
    try:
        raw_tool_call_id = getattr(tool_call, "tool_call_id")
    except AttributeError:
        return None, 0
    tool_call_id = raw_tool_call_id if type(raw_tool_call_id) is UUID else None
    try:
        attempts = getattr(tool_call, "attempts")
    except AttributeError:
        return tool_call_id, 0
    last_attempt_no = len(attempts) if type(attempts) is tuple else 0
    return tool_call_id, last_attempt_no


def decide_cycle2_tool_recovery(
    *,
    tool_call: object,
    revalidation: object,
    decided_at: datetime,
) -> ToolRetryRecoveryDecision:
    """Evaluate restart evidence without claiming CAS, dispatch, or persistence."""

    decided_at = require_utc(decided_at, field_name="decided_at")
    safe_tool_call_id, last_attempt_no = _safe_malformed_recovery_identity(
        tool_call
    )
    if safe_tool_call_id is None:
        return _recovery_decision(
            tool_call_id=None,
            last_attempt_no=last_attempt_no,
            decision=ToolRecoveryDecision.FAIL_CLOSED,
            stable_reason_code="RECOVERY_EVIDENCE_INVALID",
            decided_at=decided_at,
        )
    if (
        type(revalidation) is not Cycle2RetryRevalidation
        or not cycle2_pydantic_model_graph_is_raw_closed(
            tool_call,
            revalidation,
        )
    ):
        return _recovery_decision(
            tool_call_id=safe_tool_call_id,
            last_attempt_no=last_attempt_no,
            decision=ToolRecoveryDecision.FAIL_CLOSED,
            stable_reason_code="RECOVERY_EVIDENCE_INVALID",
            decided_at=decided_at,
        )
    try:
        validated = ToolCallRecordV2.model_validate(
            tool_call.model_dump(),
            strict=True,
        )
        validated_revalidation = Cycle2RetryRevalidation.model_validate(
            revalidation.model_dump(),
            strict=True,
        )
    except (
        ValidationError,
        PydanticSerializationError,
        AttributeError,
        ValueError,
        TypeError,
    ):
        return _recovery_decision(
            tool_call_id=safe_tool_call_id,
            last_attempt_no=last_attempt_no,
            decision=ToolRecoveryDecision.FAIL_CLOSED,
            stable_reason_code="RECOVERY_EVIDENCE_INVALID",
            decided_at=decided_at,
        )

    actual_dispatch_facts = validated.dispatch_facts()
    if (
        actual_dispatch_facts != validated_revalidation.parent_dispatch_facts
        or validated_revalidation.parent_dispatch_facts
        != validated_revalidation.expected_dispatch_facts
    ):
        return _recovery_decision(
            tool_call_id=validated.tool_call_id,
            last_attempt_no=validated.attempt_count,
            decision=ToolRecoveryDecision.FAIL_CLOSED,
            stable_reason_code="RECOVERY_EVIDENCE_CONTRADICTORY",
            decided_at=decided_at,
        )

    if validated.status in {
        ToolCallStatus.SUCCEEDED,
        ToolCallStatus.FAILED,
        ToolCallStatus.TIMED_OUT,
        ToolCallStatus.INTERRUPTED,
    }:
        return _recovery_decision(
            tool_call_id=validated.tool_call_id,
            last_attempt_no=validated.attempt_count,
            decision=ToolRecoveryDecision.NO_ACTION_TERMINAL,
            stable_reason_code="TOOL_CALL_ALREADY_TERMINAL",
            decided_at=decided_at,
        )
    if validated.status is ToolCallStatus.CREATED:
        return _recovery_decision(
            tool_call_id=validated.tool_call_id,
            last_attempt_no=0,
            decision=ToolRecoveryDecision.INTERRUPT_WITHOUT_ATTEMPT,
            stable_reason_code="CREATED_WITHOUT_DISPATCH_FENCE",
            decided_at=decided_at,
        )

    last = validated.attempts[-1]
    if last.finished_at is None:
        return _recovery_decision(
            tool_call_id=validated.tool_call_id,
            last_attempt_no=last.attempt_no,
            decision=ToolRecoveryDecision.INTERRUPT_UNFINISHED_ATTEMPT,
            stable_reason_code="UNFINISHED_ATTEMPT_OUTCOME_UNKNOWN",
            decided_at=decided_at,
        )
    if (
        last.attempt_no == 1
        and last.retry_decision is ToolRetryDecision.RETRY_SCHEDULED
        and validated.attempt_count == 1
    ):
        current_retry = decide_cycle2_tool_retry(
            canonical_tool_name=validated.canonical_tool_name,
            attempt_no=last.attempt_no,
            outcome=last.outcome,
            failure_code=last.failure_code,
            revalidation=validated_revalidation,
        )
        if current_retry is ToolRetryDecision.RETRY_SCHEDULED:
            return _recovery_decision(
                tool_call_id=validated.tool_call_id,
                last_attempt_no=1,
                decision=ToolRecoveryDecision.APPEND_SECOND_ATTEMPT,
                stable_reason_code="RETRY_REVALIDATED_CAS_REQUIRED",
                candidate_next_attempt_no=2,
                decided_at=decided_at,
            )
        if current_retry in {
            ToolRetryDecision.RUN_BUDGET_EXHAUSTED,
            ToolRetryDecision.STATE_OR_BINDING_INVALIDATED,
        }:
            return _recovery_decision(
                tool_call_id=validated.tool_call_id,
                last_attempt_no=1,
                decision=ToolRecoveryDecision.TERMINATE_RETRY_PATH,
                stable_reason_code=current_retry.value,
                decided_at=decided_at,
            )
    return _recovery_decision(
        tool_call_id=validated.tool_call_id,
        last_attempt_no=validated.attempt_count,
        decision=ToolRecoveryDecision.FAIL_CLOSED,
        stable_reason_code="RECOVERY_EVIDENCE_CONTRADICTORY",
        decided_at=decided_at,
    )


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
    def payload_is_recursively_frozen(cls, value: JsonValue | None) -> JsonValue | None:
        if value is None:
            return None
        return freeze_json_value(deepcopy(value))

    @field_serializer("payload")
    def serialize_payload(self, value: JsonValue | None) -> JsonValue | None:
        return thaw_json_value(value)

    @field_validator("observed_at", "completed_at")
    @classmethod
    def result_timestamps_are_utc(cls, value: datetime | None) -> datetime | None:
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


def search_orders_tool_spec() -> ToolSpec:
    """Return the closed Cycle 2 order-search model-visible projection."""

    status_values = [
        "CREATED",
        "PAID",
        "FULFILLING",
        "SHIPPED",
        "DELIVERED",
        "CANCELLED",
    ]
    return ToolSpec(
        name="search_orders",
        description=(
            "在当前已登录用户范围内按商品描述搜索近期订单，并返回最小候选摘要。"
        ),
        input_schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "product_description": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 80,
                }
            },
            "required": ["product_description"],
        },
        output_schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "outcome": {"enum": ["UNIQUE", "MULTIPLE"]},
                "candidates": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 5,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "ordinal": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 5,
                            },
                            "order_number": {
                                "type": "string",
                                "pattern": r"^O-[0-9]{4,20}$",
                            },
                            "ordered_on_utc": {
                                "type": "string",
                                "format": "date",
                            },
                            "status": {"enum": status_values},
                            "matching_items": {
                                "type": "array",
                                "minItems": 1,
                                "maxItems": 3,
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
                        },
                        "required": [
                            "ordinal",
                            "order_number",
                            "ordered_on_utc",
                            "status",
                            "matching_items",
                        ],
                    },
                },
                "truncated": {"type": "boolean"},
            },
            "required": ["outcome", "candidates", "truncated"],
        },
    )


def get_shipment_tool_spec() -> ToolSpec:
    """Return the closed Cycle 2 Shipment model-visible success projection."""

    return ToolSpec(
        name="get_shipment",
        description="查询当前已验证订单关联的配送状态，并返回最小物流摘要。",
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
                "shipment_status": {
                    "enum": [
                        "LABEL_CREATED",
                        "IN_TRANSIT",
                        "OUT_FOR_DELIVERY",
                        "DELIVERED",
                    ]
                },
                "latest_event_code": {
                    "enum": [
                        "LABEL_CREATED",
                        "PICKED_UP",
                        "IN_TRANSIT",
                        "ARRIVED_AT_FACILITY",
                        "OUT_FOR_DELIVERY",
                        "DELIVERED",
                    ]
                },
                "latest_event_at_utc": {
                    "type": "string",
                    "format": "date-time",
                },
                "promised_delivery_at_utc": {
                    "type": ["string", "null"],
                    "format": "date-time",
                },
                "delivered_at_utc": {
                    "type": ["string", "null"],
                    "format": "date-time",
                },
            },
            "required": [
                "shipment_status",
                "latest_event_code",
                "latest_event_at_utc",
            ],
        },
    )


class Cycle2ToolProfile(RuntimePrivateModel):
    """One exact scoped profile used only by the inactive Cycle 2 factory."""

    canonical_tool_name: Cycle2ToolName
    provider_visible_name: Cycle2ToolName
    tool_spec: ToolSpec
    effect: Literal[ToolEffect.READ] = ToolEffect.READ
    risk: Literal["LOW"] = "LOW"
    idempotency: Literal["READ_ONLY"] = "READ_ONLY"
    handler_ref: NonEmptyString
    execution_policy: ExecutionPolicy

    @model_validator(mode="after")
    def names_and_spec_are_exact(self) -> Self:
        if self.canonical_tool_name is not self.provider_visible_name:
            raise ValueError("Cycle 2 canonical/provider names must be exact")
        expected_specs = {
            Cycle2ToolName.SEARCH_ORDERS: search_orders_tool_spec(),
            Cycle2ToolName.GET_ORDER: get_order_tool_spec(),
            Cycle2ToolName.GET_SHIPMENT: get_shipment_tool_spec(),
        }
        expected_handlers = {
            Cycle2ToolName.SEARCH_ORDERS: "orders.search_orders",
            Cycle2ToolName.GET_ORDER: "orders.get_order",
            Cycle2ToolName.GET_SHIPMENT: "shipments.get_shipment",
        }
        expected_retryable = {
            name: tuple(sorted(codes))
            for name, codes in _CYCLE2_RETRYABLE_FAILURE_CODES.items()
        }
        if self.tool_spec != expected_specs[self.canonical_tool_name]:
            raise ValueError("Cycle 2 profile ToolSpec must match the exact contract")
        if self.handler_ref != expected_handlers[self.canonical_tool_name]:
            raise ValueError("Cycle 2 profile handler identity mismatch")
        policy = self.execution_policy
        if (
            policy.timeout_ms != 500
            or policy.max_attempts
            != _CYCLE2_MAX_ATTEMPTS[self.canonical_tool_name]
            or tuple(sorted(policy.retryable_failure_codes))
            != expected_retryable[self.canonical_tool_name]
            or policy.interrupt_behavior != "MARK_INTERRUPTED"
        ):
            raise ValueError("Cycle 2 profile execution policy mismatch")
        return self


def cycle2_tool_profiles() -> tuple[Cycle2ToolProfile, ...]:
    """Return the exact ordered three-Read registration profiles."""

    return (
        Cycle2ToolProfile(
            canonical_tool_name=Cycle2ToolName.SEARCH_ORDERS,
            provider_visible_name=Cycle2ToolName.SEARCH_ORDERS,
            tool_spec=search_orders_tool_spec(),
            handler_ref="orders.search_orders",
            execution_policy=ExecutionPolicy(
                timeout_ms=500,
                max_attempts=2,
                retryable_failure_codes=(
                    "ORDER_SEARCH_TRANSIENT",
                    "TOOL_CALL_TIMEOUT",
                ),
                interrupt_behavior="MARK_INTERRUPTED",
            ),
        ),
        Cycle2ToolProfile(
            canonical_tool_name=Cycle2ToolName.GET_ORDER,
            provider_visible_name=Cycle2ToolName.GET_ORDER,
            tool_spec=get_order_tool_spec(),
            handler_ref="orders.get_order",
            execution_policy=ExecutionPolicy(
                timeout_ms=500,
                max_attempts=1,
                retryable_failure_codes=(),
                interrupt_behavior="MARK_INTERRUPTED",
            ),
        ),
        Cycle2ToolProfile(
            canonical_tool_name=Cycle2ToolName.GET_SHIPMENT,
            provider_visible_name=Cycle2ToolName.GET_SHIPMENT,
            tool_spec=get_shipment_tool_spec(),
            handler_ref="shipments.get_shipment",
            execution_policy=ExecutionPolicy(
                timeout_ms=500,
                max_attempts=2,
                retryable_failure_codes=(
                    "SHIPMENT_SERVICE_TRANSIENT",
                    "TOOL_CALL_TIMEOUT",
                ),
                interrupt_behavior="MARK_INTERRUPTED",
            ),
        ),
    )


def _cycle2_registrations() -> tuple[ToolRegistration, ...]:
    return tuple(
        ToolRegistration(
            tool_spec=profile.tool_spec,
            provider_visible_name=profile.provider_visible_name.value,
            effect=profile.effect,
            risk=profile.risk,
            idempotency=profile.idempotency,
            unknown_result_recovery=None,
            handler_ref=profile.handler_ref,
            execution_policy=profile.execution_policy,
        )
        for profile in cycle2_tool_profiles()
    )


def build_cycle2_registry_snapshot() -> RegistrySnapshot:
    """Build the exact inactive three-Read snapshot without changing generic build."""

    return RegistrySnapshot.build(
        tool_registry_version=CYCLE2_TOOL_REGISTRY_VERSION,
        registrations=_cycle2_registrations(),
    )


def validate_cycle2_registry_snapshot(
    snapshot: RegistrySnapshot,
) -> RegistrySnapshot:
    """Fail closed unless every scoped visible/private registration field is exact."""

    expected = build_cycle2_registry_snapshot()
    expected_registrations = {
        registration.tool_spec.name: registration
        for registration in expected.canonical_registrations
    }
    try:
        if type(snapshot) is not RegistrySnapshot:
            raise TypeError("Cycle 2 snapshot must be the exact contract type")
        if type(snapshot.canonical_registrations) is not tuple:
            raise TypeError("Cycle 2 registrations must be a tuple")
        actual_registrations = {
            registration.tool_spec.name: registration
            for registration in snapshot.canonical_registrations
        }
        private_policies_exact = cycle2_registry_private_policies_are_raw_exact(
            snapshot
        )
        raw_snapshot_exact = _cycle2_raw_value_is_exact(snapshot, expected)
    except (AttributeError, TypeError, ValueError):
        raise ValueError(
            "snapshot does not match the exact Cycle 2 registry"
        ) from None
    if not raw_snapshot_exact:
        raise ValueError("snapshot does not match the exact Cycle 2 registry")
    if (
        snapshot.tool_registry_version != expected.tool_registry_version
        or len(actual_registrations) != len(snapshot.canonical_registrations)
        or not private_policies_exact
        or actual_registrations != expected_registrations
        or snapshot.provider_visible_toolset != expected.provider_visible_toolset
        or snapshot.provider_name_to_canonical_name
        != expected.provider_name_to_canonical_name
        or snapshot.model_visible_toolset_hash
        != expected.model_visible_toolset_hash
    ):
        raise ValueError("snapshot does not match the exact Cycle 2 registry")
    return snapshot


def _cycle2_raw_value_is_exact(actual: object, expected: object) -> bool:
    """Recursively compare raw contract values without Python type coercion."""

    if type(actual) is not type(expected):
        return False
    if isinstance(expected, BaseModel):
        if not _cycle2_model_envelope_is_raw_closed(actual, expected):
            return False
        field_names = tuple(type(expected).model_fields)
        return all(
            _cycle2_raw_value_is_exact(
                actual.__dict__[field_name],
                expected.__dict__[field_name],
            )
            for field_name in field_names
        )
    if isinstance(expected, Mapping):
        actual_items = tuple(actual.items())
        expected_items = tuple(expected.items())
        if len(actual_items) != len(expected_items):
            return False
        unmatched_actual = list(actual_items)
        for expected_key, expected_value in expected_items:
            matching_indexes = tuple(
                index
                for index, (actual_key, _actual_value) in enumerate(
                    unmatched_actual
                )
                if _cycle2_raw_value_is_exact(actual_key, expected_key)
            )
            if len(matching_indexes) != 1:
                return False
            actual_key, actual_value = unmatched_actual.pop(matching_indexes[0])
            if not _cycle2_raw_value_is_exact(actual_key, expected_key):
                return False
            if not _cycle2_raw_value_is_exact(actual_value, expected_value):
                return False
        return not unmatched_actual
    if isinstance(expected, Sequence) and not isinstance(
        expected,
        (str, bytes, bytearray),
    ):
        return len(actual) == len(expected) and all(
            _cycle2_raw_value_is_exact(actual_item, expected_item)
            for actual_item, expected_item in zip(actual, expected, strict=True)
        )
    return actual == expected


def _pydantic_model_envelope_is_raw_closed(value: object) -> bool:
    """Validate only declared payload storage, leaving Pydantic slots untouched."""

    if not isinstance(value, BaseModel) or type(value.__dict__) is not dict:
        return False
    if frozenset(value.__dict__) != frozenset(type(value).model_fields):
        return False
    extra = value.__pydantic_extra__
    return extra is None or (type(extra) is dict and not extra)


def cycle2_pydantic_model_graph_is_raw_closed(*roots: object) -> bool:
    """Recursively close every BaseModel envelope in a trusted Cycle 2 graph."""

    seen: set[int] = set()

    def visit(value: object) -> bool:
        if isinstance(value, BaseModel):
            if not _pydantic_model_envelope_is_raw_closed(value):
                return False
            if (
                type(value.__pydantic_fields_set__) is not set
                or value.__pydantic_fields_set__
                != set(type(value).model_fields)
            ):
                return False
            for field_name, field in type(value).model_fields.items():
                raw_field_value = value.__dict__[field_name]
                if isinstance(raw_field_value, (BaseModel, Mapping)):
                    continue
                TypeAdapter(field.annotation).validate_python(
                    raw_field_value,
                    strict=True,
                )
            value_id = id(value)
            if value_id in seen:
                return True
            seen.add(value_id)
            return all(
                visit(value.__dict__[field_name])
                for field_name in type(value).model_fields
            )
        if isinstance(value, Mapping):
            value_id = id(value)
            if value_id in seen:
                return True
            seen.add(value_id)
            return all(
                visit(key) and visit(item) for key, item in value.items()
            )
        if isinstance(value, Sequence) and not isinstance(
            value,
            (str, bytes, bytearray),
        ):
            value_id = id(value)
            if value_id in seen:
                return True
            seen.add(value_id)
            return all(visit(item) for item in value)
        if isinstance(value, AbstractSet):
            value_id = id(value)
            if value_id in seen:
                return True
            seen.add(value_id)
            return all(visit(item) for item in value)
        return True

    try:
        return all(visit(root) for root in roots)
    except (AttributeError, TypeError, ValueError, RecursionError):
        return False


def _cycle2_model_envelope_is_raw_closed(
    actual: object,
    expected: object,
) -> bool:
    """Require exactly declared payload fields and no Pydantic extras."""

    return (
        type(actual) is type(expected)
        and _pydantic_model_envelope_is_raw_closed(actual)
        and _pydantic_model_envelope_is_raw_closed(expected)
    )


def _cycle2_registration_private_policy_is_exact(
    actual: object,
    expected: ToolRegistration | None,
) -> bool:
    """Compare raw private policy fields without bool/int/float equality coercion."""

    if type(actual) is not ToolRegistration or expected is None:
        return False
    policy = actual.execution_policy
    expected_policy = expected.execution_policy
    return (
        type(policy) is ExecutionPolicy
        and type(policy.timeout_ms) is int
        and policy.timeout_ms == expected_policy.timeout_ms
        and type(policy.max_attempts) is int
        and policy.max_attempts == expected_policy.max_attempts
        and type(policy.retryable_failure_codes) is tuple
        and all(type(code) is str for code in policy.retryable_failure_codes)
        and policy.retryable_failure_codes
        == expected_policy.retryable_failure_codes
        and type(policy.interrupt_behavior) is str
        and policy.interrupt_behavior == expected_policy.interrupt_behavior
    )


def cycle2_registry_private_policies_are_raw_exact(
    snapshot: object,
) -> bool:
    """Check raw private execution policies without validating other Gates."""

    if type(snapshot) is not RegistrySnapshot:
        return False
    expected = build_cycle2_registry_snapshot()
    expected_registrations = {
        registration.tool_spec.name: registration
        for registration in expected.canonical_registrations
    }
    try:
        if type(snapshot.canonical_registrations) is not tuple:
            return False
        return (
            len(snapshot.canonical_registrations) == len(expected_registrations)
            and all(
                _cycle2_registration_private_policy_is_exact(
                    registration,
                    expected_registrations.get(registration.tool_spec.name),
                )
                for registration in snapshot.canonical_registrations
            )
        )
    except (AttributeError, TypeError, ValueError):
        return False


def cycle2_registry_precoercion_contract_is_raw_exact(
    snapshot: object,
) -> bool:
    """Check the complete raw registry shape while preserving typed Action gating."""

    if type(snapshot) is not RegistrySnapshot:
        return False
    expected = build_cycle2_registry_snapshot()
    expected_registrations = {
        registration.tool_spec.name: registration
        for registration in expected.canonical_registrations
    }
    try:
        if (
            not _cycle2_model_envelope_is_raw_closed(snapshot, expected)
            or type(snapshot.canonical_registrations) is not tuple
            or len(snapshot.canonical_registrations) != len(expected_registrations)
            or not _cycle2_raw_value_is_exact(
                snapshot.tool_registry_version,
                expected.tool_registry_version,
            )
            or not _cycle2_raw_value_is_exact(
                snapshot.provider_visible_toolset,
                expected.provider_visible_toolset,
            )
            or not _cycle2_raw_value_is_exact(
                snapshot.provider_name_to_canonical_name,
                expected.provider_name_to_canonical_name,
            )
            or not _cycle2_raw_value_is_exact(
                snapshot.model_visible_toolset_hash,
                expected.model_visible_toolset_hash,
            )
        ):
            return False
        for registration in snapshot.canonical_registrations:
            if type(registration) is not ToolRegistration:
                return False
            expected_registration = expected_registrations.get(
                registration.tool_spec.name
            )
            if expected_registration is None:
                return False
            if not (
                _cycle2_model_envelope_is_raw_closed(
                    registration,
                    expected_registration,
                )
                and _cycle2_raw_value_is_exact(
                    registration.tool_spec,
                    expected_registration.tool_spec,
                )
                and _cycle2_raw_value_is_exact(
                    registration.provider_visible_name,
                    expected_registration.provider_visible_name,
                )
                and type(registration.effect) is ToolEffect
                and _cycle2_raw_value_is_exact(
                    registration.risk,
                    expected_registration.risk,
                )
                and _cycle2_raw_value_is_exact(
                    registration.idempotency,
                    expected_registration.idempotency,
                )
                and (
                    registration.unknown_result_recovery is None
                    or type(registration.unknown_result_recovery) is str
                )
                and _cycle2_raw_value_is_exact(
                    registration.handler_ref,
                    expected_registration.handler_ref,
                )
                and _cycle2_raw_value_is_exact(
                    registration.execution_policy,
                    expected_registration.execution_policy,
                )
            ):
                return False
    except (AttributeError, TypeError, ValueError):
        return False
    return True
