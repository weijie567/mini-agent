"""Pure fail-closed Control Gateway decisions for the first E2E-01 slice."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime
from typing import Annotated, Any, Literal, Self
from uuid import UUID

from pydantic import (
    Field,
    JsonValue,
    ValidationError,
    field_serializer,
    field_validator,
    model_validator,
)
from pydantic_core import PydanticSerializationError

from .common import (
    RuntimePrivateModel,
    find_trusted_argument_field,
    freeze_json_value,
    require_utc,
    thaw_json_value,
)
from .identity import CustomerContext
from .memory import ContextManifest
from .order_search import normalize_product_description
from .request_processing import RevalidatedNextMove
from .request_understanding import InputAuthority
from .task_state import InputBinding, RequestUnitRecord, TaskRecord, TaskStatus
from .tool_system import (
    Cycle2ToolName,
    GateDecision,
    GateDecisionValue,
    GateReasonCode,
    RegistrySnapshot,
    ToolEffect,
    ToolRegistration,
    ToolSpec,
    ToolsetHash,
    build_cycle2_registry_snapshot,
    cycle2_registry_private_policies_are_raw_exact,
    get_order_tool_spec,
    validate_cycle2_registry_snapshot,
)

_ORDER_ID_PATTERN = re.compile(r"^O-[0-9]{4,20}$")


class Cycle2AcceptedBindingFacts(RuntimePrivateModel):
    """One current accepted binding loaded from the controlled record graph."""

    binding_id: UUID
    private_owner_scope_ref: Annotated[str, Field(min_length=1)]
    owner_customer_id: Annotated[str, Field(min_length=1)]
    task_id: UUID
    request_unit_id: UUID
    task_state_version: Annotated[int, Field(strict=True, ge=1)]
    name: Literal["product_description", "order_id", "not_received_claim"]
    normalized_value: Annotated[str, Field(strict=True, min_length=1)]
    authority: InputAuthority
    validation_status: Literal["ACCEPTED"] = "ACCEPTED"
    source_refs: Annotated[tuple[UUID, ...], Field(min_length=1)]
    superseded_by: UUID | None = None

    @field_validator("source_refs")
    @classmethod
    def source_refs_are_unique(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        if len(value) != len(set(value)):
            raise ValueError("Cycle 2 binding source refs must be unique")
        return value

    @model_validator(mode="after")
    def normalized_value_is_canonical(self) -> Self:
        if self.name == "product_description":
            if normalize_product_description(self.normalized_value) != (
                self.normalized_value
            ):
                raise ValueError("search binding must store its exact normalized value")
        elif self.name == "order_id" and _ORDER_ID_PATTERN.fullmatch(
            self.normalized_value
        ) is None:
            raise ValueError("order_id binding must be an exact normalized Order ID")
        return self


class Cycle2VerifiedOrderTargetFacts(RuntimePrivateModel):
    """Deterministic current target evidence; never constructed from model text."""

    verified_target_ref: UUID
    private_owner_scope_ref: Annotated[str, Field(min_length=1)]
    owner_customer_id: Annotated[str, Field(min_length=1)]
    task_id: UUID
    request_unit_id: UUID
    task_state_version: Annotated[int, Field(strict=True, ge=1)]
    order_id: Annotated[str, Field(strict=True, pattern=r"^O-[0-9]{4,20}$")]
    source_observation_ref: UUID
    source_observation_version: Annotated[str, Field(strict=True, min_length=1)]
    input_binding_refs: Annotated[tuple[UUID, ...], Field(min_length=1)]
    superseded_by: UUID | None = None

    @field_validator("input_binding_refs")
    @classmethod
    def binding_refs_are_unique(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        if len(value) != len(set(value)):
            raise ValueError("verified target binding refs must be unique")
        return value


class Cycle2TargetObservationFacts(RuntimePrivateModel):
    """Current typed Observation provenance for one verified Order target."""

    observation_ref: UUID
    observation_version: Annotated[str, Field(strict=True, min_length=1)]
    private_owner_scope_ref: Annotated[str, Field(min_length=1)]
    owner_customer_id: Annotated[str, Field(min_length=1)]
    task_id: UUID
    request_unit_id: UUID
    task_state_version: Annotated[int, Field(strict=True, ge=1)]
    verified_target_ref: UUID
    input_binding_refs: Annotated[tuple[UUID, ...], Field(min_length=1)]
    superseded_by: UUID | None = None

    @field_validator("input_binding_refs")
    @classmethod
    def binding_refs_are_unique(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        if len(value) != len(set(value)):
            raise ValueError("target Observation binding refs must be unique")
        return value


class Cycle2GatewayBudgetFacts(RuntimePrivateModel):
    run_id: UUID
    context_manifest_id: UUID
    tool_registry_version: Literal["e2e01-cycle2-tools.p0.v1"]
    model_visible_toolset_hash: ToolsetHash
    closure_complete: Literal[True]
    tool_calls_used: Annotated[int, Field(strict=True, ge=0)]
    max_tool_calls: Literal[3]
    active_tool_calls: Annotated[int, Field(strict=True, ge=0)]
    accepted_parallel_tool_calls: Literal[0]
    remaining_run_time_budget_ms: Annotated[int, Field(strict=True, ge=0)]


class Cycle2ToolProgressFact(RuntimePrivateModel):
    """A prior validated step used for deterministic no-progress comparison."""

    run_id: UUID
    context_manifest_id: UUID
    tool_registry_version: Literal["e2e01-cycle2-tools.p0.v1"]
    model_visible_toolset_hash: ToolsetHash
    canonical_tool_name: Cycle2ToolName
    validated_arguments: Mapping[str, JsonValue]
    task_state_version: Annotated[int, Field(strict=True, ge=1)]
    argument_binding_refs: Annotated[tuple[UUID, ...], Field(min_length=1)]

    @field_validator("validated_arguments", mode="before")
    @classmethod
    def arguments_are_native_json(cls, value: Any) -> Any:
        return thaw_json_value(value)

    @field_validator("validated_arguments")
    @classmethod
    def arguments_are_frozen(
        cls, value: Mapping[str, JsonValue]
    ) -> Mapping[str, JsonValue]:
        return freeze_json_value(value)

    @field_serializer("validated_arguments")
    def serialize_arguments(
        self, value: Mapping[str, JsonValue]
    ) -> dict[str, JsonValue]:
        return thaw_json_value(value)


class Cycle2GatewayProgressSnapshot(RuntimePrivateModel):
    """Complete run-bound history used by deterministic no-progress checks."""

    run_id: UUID
    context_manifest_id: UUID
    tool_registry_version: Literal["e2e01-cycle2-tools.p0.v1"]
    model_visible_toolset_hash: ToolsetHash
    task_state_version: Annotated[int, Field(strict=True, ge=1)]
    history_complete: Literal[True]
    prior_tool_steps: tuple[Cycle2ToolProgressFact, ...]


class Cycle2GatewayCandidate(RuntimePrivateModel):
    """Runtime-revalidated candidate; it contains no public-summary authority."""

    run_id: UUID
    task_id: UUID
    request_unit_id: UUID
    model_call_id: UUID
    context_manifest_id: UUID
    requested_provider_tool_name: Annotated[str, Field(min_length=1)]
    candidate_arguments: Mapping[str, JsonValue]
    proposed_base_task_state_version: Annotated[int, Field(strict=True, ge=1)] | None
    validated_task_state_version: Annotated[int, Field(strict=True, ge=1)]
    argument_binding_refs: Annotated[tuple[UUID, ...], Field(min_length=1)]
    verified_target_ref: UUID | None = None

    @field_validator("candidate_arguments", mode="before")
    @classmethod
    def arguments_are_native_json(cls, value: Any) -> Any:
        return thaw_json_value(value)

    @field_validator("candidate_arguments")
    @classmethod
    def arguments_are_frozen(
        cls, value: Mapping[str, JsonValue]
    ) -> Mapping[str, JsonValue]:
        return freeze_json_value(value)

    @field_serializer("candidate_arguments")
    def serialize_arguments(
        self, value: Mapping[str, JsonValue]
    ) -> dict[str, JsonValue]:
        return thaw_json_value(value)

    @field_validator("argument_binding_refs")
    @classmethod
    def binding_refs_are_unique(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        if len(value) != len(set(value)):
            raise ValueError("Cycle 2 candidate binding refs must be unique")
        return value


class Cycle2GatewayLoadedClosure(RuntimePrivateModel):
    """Typed already-loaded facts; this value performs no IO or authorization."""

    customer_context: CustomerContext
    private_owner_scope_ref: Annotated[str, Field(min_length=1)]
    current_task: TaskRecord
    current_request_unit: RequestUnitRecord
    current_input_bindings: Annotated[
        tuple[Cycle2AcceptedBindingFacts, ...], Field(min_length=1)
    ]
    current_verified_order_targets: tuple[Cycle2VerifiedOrderTargetFacts, ...]
    current_target_observations: tuple[Cycle2TargetObservationFacts, ...]
    registry_snapshot: RegistrySnapshot
    context_manifest: ContextManifest
    budget: Cycle2GatewayBudgetFacts
    progress_snapshot: Cycle2GatewayProgressSnapshot

    @model_validator(mode="after")
    def loaded_fact_identities_are_unique(self) -> Self:
        binding_ids = tuple(binding.binding_id for binding in self.current_input_bindings)
        target_ids = tuple(
            target.verified_target_ref
            for target in self.current_verified_order_targets
        )
        observation_ids = tuple(
            observation.observation_ref
            for observation in self.current_target_observations
        )
        observation_target_ids = tuple(
            observation.verified_target_ref
            for observation in self.current_target_observations
        )
        if len(binding_ids) != len(set(binding_ids)):
            raise ValueError("loaded Cycle 2 bindings must be unique")
        if len(target_ids) != len(set(target_ids)):
            raise ValueError("loaded Cycle 2 verified targets must be unique")
        if len(observation_ids) != len(set(observation_ids)):
            raise ValueError("loaded Cycle 2 target Observations must be unique")
        if len(observation_target_ids) != len(set(observation_target_ids)):
            raise ValueError("loaded Cycle 2 target Observation owners must be unique")
        return self


def _resolve_registration(
    snapshot: RegistrySnapshot,
    requested_provider_name: str,
) -> tuple[str | None, ToolRegistration | None]:
    bindings = tuple(
        binding
        for binding in snapshot.provider_name_to_canonical_name
        if binding.provider_visible_name == requested_provider_name
    )
    if len(bindings) != 1:
        return None, None
    canonical_name = bindings[0].canonical_tool_name
    registrations = tuple(
        registration
        for registration in snapshot.canonical_registrations
        if registration.tool_spec.name == canonical_name
    )
    if len(registrations) != 1:
        return canonical_name, None
    return canonical_name, registrations[0]


def _registration_matches_visible_spec(
    *,
    registration: ToolRegistration | None,
    provider_visible_spec: ToolSpec | None,
) -> bool:
    if registration is None or provider_visible_spec is None:
        return False
    return provider_visible_spec == ToolSpec(
        name=registration.provider_visible_name,
        description=registration.tool_spec.description,
        input_schema=registration.tool_spec.input_schema,
        output_schema=registration.tool_spec.output_schema,
    )


def _closed_get_order_schema_is_valid(
    *,
    arguments: Mapping[str, object],
    normalized_candidate_order_id: str | None,
    registration: ToolRegistration | None,
    provider_visible_spec: ToolSpec | None,
) -> bool:
    if registration is None or registration.tool_spec != get_order_tool_spec():
        return False
    if not _registration_matches_visible_spec(
        registration=registration,
        provider_visible_spec=provider_visible_spec,
    ):
        return False
    if set(arguments) != {"order_id"}:
        return False
    raw_order_id = arguments.get("order_id")
    if type(raw_order_id) is not str:
        return False
    normalized_raw_order_id = raw_order_id.strip()
    if normalized_raw_order_id[:2].casefold() == "o-":
        normalized_raw_order_id = f"O-{normalized_raw_order_id[2:]}"
    return (
        _ORDER_ID_PATTERN.fullmatch(normalized_raw_order_id) is not None
        and normalized_raw_order_id == normalized_candidate_order_id
    )


def _resolve_provider_visible_spec(
    snapshot: RegistrySnapshot,
    requested_provider_name: str,
) -> ToolSpec | None:
    matching_specs = tuple(
        spec
        for spec in snapshot.provider_visible_toolset
        if spec.name == requested_provider_name
    )
    if len(matching_specs) != 1:
        return None
    return matching_specs[0]


def resolve_validated_get_order_registration(
    *,
    registry_snapshot: RegistrySnapshot,
    requested_provider_name: str,
) -> ToolRegistration | None:
    """Return only the registration whose actual visible projection was gated."""

    resolved_name, registration = _resolve_registration(
        registry_snapshot,
        requested_provider_name,
    )
    visible_spec = _resolve_provider_visible_spec(
        registry_snapshot,
        requested_provider_name,
    )
    if (
        resolved_name != "get_order"
        or requested_provider_name != "get_order"
        or registration is None
        or registration.provider_visible_name != requested_provider_name
        or registration.tool_spec != get_order_tool_spec()
        or not _registration_matches_visible_spec(
            registration=registration,
            provider_visible_spec=visible_spec,
        )
    ):
        return None
    return registration


def evaluate_control_gateway(
    *,
    revalidated_move: RevalidatedNextMove,
    customer_context: CustomerContext,
    current_task: TaskRecord,
    current_request_unit: RequestUnitRecord,
    current_input_binding: InputBinding,
    registry_snapshot: RegistrySnapshot,
    context_manifest: ContextManifest,
    gate_decision_id: UUID,
    model_call_id: UUID,
    provider_tool_call_id: str | None,
    decided_at: datetime,
    tool_calls_used: int,
    max_tool_calls: int,
    progress_valid: bool,
) -> GateDecision:
    """Revalidate every deterministic boundary and return an audit decision."""

    snapshot_match = (
        context_manifest.tool_registry_version
        == registry_snapshot.tool_registry_version
        and context_manifest.model_visible_toolset_hash
        == registry_snapshot.model_visible_toolset_hash
    )
    resolved_name, registration = _resolve_registration(
        registry_snapshot,
        revalidated_move.requested_provider_tool_name,
    )
    provider_visible_spec = _resolve_provider_visible_spec(
        registry_snapshot,
        revalidated_move.requested_provider_tool_name,
    )
    registration_valid = (
        resolved_name == "get_order"
        and revalidated_move.requested_provider_tool_name == "get_order"
        and registration is not None
        and registration.provider_visible_name == "get_order"
        and provider_visible_spec is not None
    )
    trusted_field_valid = (
        find_trusted_argument_field(revalidated_move.candidate_arguments) is None
    )
    schema_valid = _closed_get_order_schema_is_valid(
        arguments=revalidated_move.candidate_arguments,
        normalized_candidate_order_id=(
            revalidated_move.normalized_candidate_order_id
        ),
        registration=registration,
        provider_visible_spec=provider_visible_spec,
    )

    graph_binding_valid = (
        current_input_binding.name == "order_id"
        and current_input_binding.binding_id
        in current_request_unit.input_binding_refs
        and current_request_unit.input_binding_refs
        == (current_input_binding.binding_id,)
        and revalidated_move.argument_binding_refs
        == (current_input_binding.binding_id,)
        and revalidated_move.binding_name == current_input_binding.name
        and revalidated_move.binding_normalized_value
        == current_input_binding.normalized_value
    )
    argument_binding_valid = (
        graph_binding_valid
        and revalidated_move.normalized_candidate_order_id
        == current_input_binding.normalized_value
    )
    budget_valid = (
        type(tool_calls_used) is int
        and type(max_tool_calls) is int
        and max_tool_calls == 1
        and 0 <= tool_calls_used < max_tool_calls
    )
    state_version_valid = (
        type(customer_context) is CustomerContext
        and current_task.owner_customer_id == customer_context.customer_id
        and current_task.task_id == revalidated_move.task_id
        and current_request_unit.task_id == current_task.task_id
        and current_request_unit.request_unit_id
        == revalidated_move.request_unit_id
        and current_task.status is TaskStatus.ACTIVE
        and current_request_unit.status is TaskStatus.ACTIVE
        and current_task.state_version == current_request_unit.state_version
        and current_task.state_version
        == revalidated_move.validated_task_state_version
        and revalidated_move.proposed_base_task_state_version is None
        and context_manifest.task_state_ref_and_version is None
        and context_manifest.run_id == revalidated_move.run_id
        and context_manifest.model_call_id == model_call_id
    )
    action_boundary_valid = (
        registration is not None and registration.effect is ToolEffect.READ
    )

    checks = (
        snapshot_match,
        registration_valid,
        schema_valid,
        trusted_field_valid,
        argument_binding_valid,
        budget_valid,
        progress_valid,
        state_version_valid,
        action_boundary_valid,
    )
    reason_code: GateReasonCode | None = None
    if not argument_binding_valid:
        reason_code = GateReasonCode.ARGUMENT_BINDING_MISMATCH
    elif not snapshot_match:
        reason_code = GateReasonCode.SNAPSHOT_MISMATCH
    elif not registration_valid:
        reason_code = GateReasonCode.TOOL_NOT_REGISTERED
    elif not trusted_field_valid:
        reason_code = GateReasonCode.TRUSTED_FIELD_INJECTION
    elif not schema_valid:
        reason_code = GateReasonCode.SCHEMA_INVALID
    elif not budget_valid:
        reason_code = GateReasonCode.BUDGET_EXCEEDED
    elif not progress_valid:
        reason_code = GateReasonCode.NO_PROGRESS
    elif not state_version_valid:
        reason_code = GateReasonCode.STATE_VERSION_MISMATCH
    elif not action_boundary_valid:
        reason_code = GateReasonCode.ACTION_REQUIRES_PROPOSAL

    accepted = all(checks)
    return GateDecision(
        gate_decision_id=gate_decision_id,
        model_call_id=model_call_id,
        context_manifest_id=context_manifest.context_manifest_id,
        provider_tool_call_id=provider_tool_call_id,
        requested_provider_tool_name=(
            revalidated_move.requested_provider_tool_name
        ),
        resolved_canonical_tool_name=resolved_name,
        snapshot_match=snapshot_match,
        registration_valid=registration_valid,
        schema_valid=schema_valid,
        trusted_field_valid=trusted_field_valid,
        argument_binding_valid=argument_binding_valid,
        argument_binding_refs=revalidated_move.argument_binding_refs,
        budget_valid=budget_valid,
        progress_valid=progress_valid,
        proposed_base_task_state_version=(
            revalidated_move.proposed_base_task_state_version
        ),
        validated_task_state_version=(
            revalidated_move.validated_task_state_version
        ),
        state_version_valid=state_version_valid,
        action_boundary_valid=action_boundary_valid,
        decision=(
            GateDecisionValue.ACCEPT
            if accepted
            else GateDecisionValue.REJECT
        ),
        reason_code=reason_code,
        decided_at=decided_at,
    )


def _cycle2_schema_valid(
    *,
    tool_name: Cycle2ToolName | None,
    arguments: Mapping[str, JsonValue],
) -> bool:
    if tool_name is None:
        return False
    if tool_name is Cycle2ToolName.SEARCH_ORDERS:
        if set(arguments) != {"product_description"}:
            return False
        value = arguments.get("product_description")
        if type(value) is not str or not 1 <= len(value) <= 80:
            return False
        try:
            normalize_product_description(value)
        except (TypeError, ValueError):
            return False
        return True
    if set(arguments) != {"order_id"}:
        return False
    order_id = arguments.get("order_id")
    if type(order_id) is not str:
        return False
    if tool_name is Cycle2ToolName.GET_ORDER:
        normalized = order_id.strip()
        if normalized[:2].casefold() == "o-":
            normalized = f"O-{normalized[2:]}"
        return _ORDER_ID_PATTERN.fullmatch(normalized) is not None
    return _ORDER_ID_PATTERN.fullmatch(order_id) is not None


def _cycle2_normalized_argument(
    *,
    tool_name: Cycle2ToolName,
    arguments: Mapping[str, JsonValue],
) -> tuple[str, str] | None:
    if tool_name is Cycle2ToolName.SEARCH_ORDERS:
        value = arguments.get("product_description")
        if type(value) is not str:
            return None
        try:
            return "product_description", normalize_product_description(value)
        except (TypeError, ValueError):
            return None
    value = arguments.get("order_id")
    if type(value) is not str:
        return None
    normalized_value = value
    if tool_name is Cycle2ToolName.GET_ORDER:
        normalized_value = value.strip()
        if normalized_value[:2].casefold() == "o-":
            normalized_value = f"O-{normalized_value[2:]}"
    if _ORDER_ID_PATTERN.fullmatch(normalized_value) is None:
        return None
    return "order_id", normalized_value


def _cycle2_loaded_graph_complete(loaded: Cycle2GatewayLoadedClosure) -> bool:
    """Verify the complete current binding/target/Observation record closure."""

    task = loaded.current_task
    request_unit = loaded.current_request_unit
    owner_customer_id = loaded.customer_context.customer_id
    binding_ids = tuple(binding.binding_id for binding in loaded.current_input_bindings)
    if set(binding_ids) != set(request_unit.input_binding_refs):
        return False
    for binding in loaded.current_input_bindings:
        if not (
            binding.superseded_by is None
            and binding.private_owner_scope_ref == loaded.private_owner_scope_ref
            and binding.owner_customer_id == owner_customer_id
            and binding.task_id == task.task_id
            and binding.request_unit_id == request_unit.request_unit_id
            and binding.task_state_version == task.state_version
        ):
            return False

    targets_by_ref = {
        target.verified_target_ref: target
        for target in loaded.current_verified_order_targets
    }
    observations_by_target = {
        observation.verified_target_ref: observation
        for observation in loaded.current_target_observations
    }
    if set(targets_by_ref) != set(observations_by_target):
        return False
    if set(request_unit.observation_refs) != {
        observation.observation_ref
        for observation in loaded.current_target_observations
    }:
        return False
    manifest_observations = {
        (record.record_ref, record.version)
        for record in loaded.context_manifest.observation_refs_and_versions
    }
    closure_observations = {
        (observation.observation_ref, observation.observation_version)
        for observation in loaded.current_target_observations
    }
    if (
        len(manifest_observations)
        != len(loaded.context_manifest.observation_refs_and_versions)
        or len(closure_observations) != len(loaded.current_target_observations)
        or len(set(request_unit.observation_refs))
        != len(request_unit.observation_refs)
        or manifest_observations != closure_observations
    ):
        return False
    binding_id_set = set(binding_ids)
    for target_ref, target in targets_by_ref.items():
        observation = observations_by_target[target_ref]
        if not (
            target.superseded_by is None
            and observation.superseded_by is None
            and target.private_owner_scope_ref == loaded.private_owner_scope_ref
            and observation.private_owner_scope_ref == loaded.private_owner_scope_ref
            and target.owner_customer_id == owner_customer_id
            and observation.owner_customer_id == owner_customer_id
            and target.task_id == task.task_id == observation.task_id
            and target.request_unit_id
            == request_unit.request_unit_id
            == observation.request_unit_id
            and target.task_state_version
            == task.state_version
            == observation.task_state_version
            and target.source_observation_ref == observation.observation_ref
            and target.source_observation_version == observation.observation_version
            and target.input_binding_refs == observation.input_binding_refs
            and set(target.input_binding_refs).issubset(binding_id_set)
        ):
            return False
    return True


def _cycle2_argument_binding_valid(
    *,
    candidate: Cycle2GatewayCandidate,
    loaded: Cycle2GatewayLoadedClosure,
    tool_name: Cycle2ToolName | None,
) -> bool:
    if tool_name is None or not _cycle2_loaded_graph_complete(loaded):
        return False
    normalized = _cycle2_normalized_argument(
        tool_name=tool_name,
        arguments=candidate.candidate_arguments,
    )
    if normalized is None:
        return False
    expected_name, normalized_value = normalized
    matching_bindings = tuple(
        binding
        for binding in loaded.current_input_bindings
        if binding.binding_id in candidate.argument_binding_refs
        and binding.name == expected_name
        and binding.normalized_value == normalized_value
    )
    if len(matching_bindings) != 1:
        return False
    binding = matching_bindings[0]
    common_binding_closed = (
        binding.name == expected_name
        and binding.normalized_value == normalized_value
        and binding.superseded_by is None
        and binding.private_owner_scope_ref == loaded.private_owner_scope_ref
        and binding.owner_customer_id == loaded.customer_context.customer_id
        and binding.task_id == candidate.task_id
        and binding.request_unit_id == candidate.request_unit_id
        and binding.task_state_version == candidate.validated_task_state_version
        and binding.binding_id in loaded.current_request_unit.input_binding_refs
    )
    if not common_binding_closed:
        return False

    if tool_name is Cycle2ToolName.SEARCH_ORDERS:
        return (
            binding.authority
            in {InputAuthority.USER_CLAIM, InputAuthority.MODEL_INFERENCE}
            and candidate.verified_target_ref is None
            and candidate.argument_binding_refs == (binding.binding_id,)
        )
    if tool_name is Cycle2ToolName.GET_ORDER:
        return (
            binding.authority is InputAuthority.USER_CLAIM
            and candidate.verified_target_ref is None
            and candidate.argument_binding_refs == (binding.binding_id,)
        )

    matching_targets = tuple(
        target
        for target in loaded.current_verified_order_targets
        if target.verified_target_ref == candidate.verified_target_ref
    )
    if len(matching_targets) != 1:
        return False
    target = matching_targets[0]
    matching_observations = tuple(
        observation
        for observation in loaded.current_target_observations
        if observation.observation_ref == target.source_observation_ref
        and observation.verified_target_ref == target.verified_target_ref
    )
    if len(matching_observations) != 1:
        return False
    observation = matching_observations[0]
    manifest_ref_matches = sum(
        manifest_ref.record_ref == target.source_observation_ref
        and manifest_ref.version == target.source_observation_version
        for manifest_ref in loaded.context_manifest.observation_refs_and_versions
    ) == 1
    return (
        target.superseded_by is None
        and target.private_owner_scope_ref == loaded.private_owner_scope_ref
        and target.owner_customer_id == loaded.customer_context.customer_id
        and target.task_id == candidate.task_id
        and target.request_unit_id == candidate.request_unit_id
        and target.task_state_version == candidate.validated_task_state_version
        and target.order_id == normalized_value
        and binding.binding_id in target.input_binding_refs
        and target.source_observation_ref
        in loaded.current_request_unit.observation_refs
        and observation.observation_version == target.source_observation_version
        and manifest_ref_matches
        and candidate.verified_target_ref == target.verified_target_ref
        and candidate.argument_binding_refs
        == (binding.binding_id, target.verified_target_ref)
    )


def _cycle2_state_version_valid(
    *,
    candidate: Cycle2GatewayCandidate,
    loaded: Cycle2GatewayLoadedClosure,
) -> bool:
    task = loaded.current_task
    request_unit = loaded.current_request_unit
    manifest = loaded.context_manifest
    if manifest.task_state_ref_and_version is None:
        proposed_version_valid = candidate.proposed_base_task_state_version is None
    else:
        proposed_version_valid = (
            manifest.task_state_ref_and_version.task_id == candidate.task_id
            and manifest.task_state_ref_and_version.state_version
            == candidate.proposed_base_task_state_version
        )
    return (
        type(loaded.customer_context) is CustomerContext
        and task.owner_customer_id == loaded.customer_context.customer_id
        and task.task_id == candidate.task_id
        and request_unit.task_id == task.task_id
        and request_unit.request_unit_id == candidate.request_unit_id
        and task.status is TaskStatus.ACTIVE
        and request_unit.status is TaskStatus.ACTIVE
        and task.state_version == request_unit.state_version
        and task.state_version == candidate.validated_task_state_version
        and proposed_version_valid
        and manifest.context_manifest_id == candidate.context_manifest_id
        and manifest.run_id == candidate.run_id
        and manifest.model_call_id == candidate.model_call_id
    )


def _cycle2_budget_valid(
    *,
    candidate: Cycle2GatewayCandidate,
    loaded: Cycle2GatewayLoadedClosure,
) -> bool:
    budget = loaded.budget
    snapshot = loaded.registry_snapshot
    return (
        budget.closure_complete is True
        and budget.run_id == candidate.run_id
        and budget.context_manifest_id == candidate.context_manifest_id
        and budget.tool_registry_version == snapshot.tool_registry_version
        and budget.model_visible_toolset_hash == snapshot.model_visible_toolset_hash
        and budget.max_tool_calls == 3
        and 0 <= budget.tool_calls_used < budget.max_tool_calls
        and budget.active_tool_calls == 0
        and budget.accepted_parallel_tool_calls == 0
        and budget.remaining_run_time_budget_ms > 0
    )


def _cycle2_progress_valid(
    *,
    candidate: Cycle2GatewayCandidate,
    tool_name: Cycle2ToolName | None,
    loaded: Cycle2GatewayLoadedClosure,
) -> bool:
    if tool_name is None:
        return False
    progress = loaded.progress_snapshot
    snapshot = loaded.registry_snapshot
    if not (
        progress.history_complete is True
        and progress.run_id == candidate.run_id
        and progress.context_manifest_id == candidate.context_manifest_id
        and progress.tool_registry_version == snapshot.tool_registry_version
        and progress.model_visible_toolset_hash
        == snapshot.model_visible_toolset_hash
        and progress.task_state_version == candidate.validated_task_state_version
        and all(
            step.run_id == progress.run_id
            and step.context_manifest_id == progress.context_manifest_id
            and step.tool_registry_version == progress.tool_registry_version
            and step.model_visible_toolset_hash
            == progress.model_visible_toolset_hash
            and step.task_state_version == progress.task_state_version
            for step in progress.prior_tool_steps
        )
    ):
        return False
    normalized = _cycle2_normalized_argument(
        tool_name=tool_name,
        arguments=candidate.candidate_arguments,
    )
    if normalized is None:
        return False
    argument_name, argument_value = normalized
    validated_arguments = {argument_name: argument_value}
    return not any(
        step.canonical_tool_name is tool_name
        and step.validated_arguments == validated_arguments
        and step.task_state_version == candidate.validated_task_state_version
        and step.argument_binding_refs == candidate.argument_binding_refs
        for step in progress.prior_tool_steps
    )


def _cycle2_malformed_rejection(
    *,
    candidate: object,
    gate_decision_id: UUID,
    provider_tool_call_id: str | None,
    decided_at: datetime,
) -> GateDecision:
    """Return auditable non-executable evidence for bypassed malformed input."""

    model_call_id = getattr(candidate, "model_call_id", None)
    if not isinstance(model_call_id, UUID):
        model_call_id = UUID(int=0)
    context_manifest_id = getattr(candidate, "context_manifest_id", None)
    if not isinstance(context_manifest_id, UUID):
        context_manifest_id = UUID(int=0)
    requested_name = getattr(candidate, "requested_provider_tool_name", None)
    if type(requested_name) is not str or not requested_name:
        requested_name = "invalid_cycle2_candidate"
    raw_refs = getattr(candidate, "argument_binding_refs", ())
    if not isinstance(raw_refs, tuple):
        raw_refs = ()
    binding_refs = tuple(ref for ref in raw_refs if isinstance(ref, UUID))
    if len(binding_refs) != len(set(binding_refs)):
        binding_refs = ()
    proposed_version = getattr(candidate, "proposed_base_task_state_version", None)
    if type(proposed_version) is not int or proposed_version < 1:
        proposed_version = None
    validated_version = getattr(candidate, "validated_task_state_version", None)
    if type(validated_version) is not int or validated_version < 1:
        validated_version = None
    return GateDecision(
        gate_decision_id=gate_decision_id,
        model_call_id=model_call_id,
        context_manifest_id=context_manifest_id,
        provider_tool_call_id=provider_tool_call_id,
        requested_provider_tool_name=requested_name,
        resolved_canonical_tool_name=None,
        snapshot_match=False,
        registration_valid=False,
        schema_valid=False,
        trusted_field_valid=False,
        argument_binding_valid=False,
        argument_binding_refs=binding_refs,
        budget_valid=False,
        progress_valid=False,
        proposed_base_task_state_version=proposed_version,
        validated_task_state_version=validated_version,
        state_version_valid=False,
        action_boundary_valid=False,
        decision=GateDecisionValue.REJECT,
        reason_code=GateReasonCode.SCHEMA_INVALID,
        decided_at=decided_at,
    )


def _cycle2_raw_exact_type_preflight(
    candidate: object,
    loaded: object,
) -> bool:
    """Reject raw bypass values before any nested Pydantic coercion can occur."""

    if (
        type(candidate) is not Cycle2GatewayCandidate
        or type(loaded) is not Cycle2GatewayLoadedClosure
    ):
        return False
    try:
        proposed_version = candidate.proposed_base_task_state_version
        manifest_task_ref = loaded.context_manifest.task_state_ref_and_version
        budget = loaded.budget
        progress = loaded.progress_snapshot
        token_counts = loaded.context_manifest.token_counts
        integer_values = (
            candidate.validated_task_state_version,
            loaded.current_task.state_version,
            loaded.current_request_unit.state_version,
            budget.tool_calls_used,
            budget.max_tool_calls,
            budget.active_tool_calls,
            budget.accepted_parallel_tool_calls,
            budget.remaining_run_time_budget_ms,
            progress.task_state_version,
            *(binding.task_state_version for binding in loaded.current_input_bindings),
            *(
                target.task_state_version
                for target in loaded.current_verified_order_targets
            ),
            *(
                observation.task_state_version
                for observation in loaded.current_target_observations
            ),
            *(step.task_state_version for step in progress.prior_tool_steps),
        )
        if any(type(value) is not int for value in integer_values):
            return False
        if proposed_version is not None and type(proposed_version) is not int:
            return False
        if (
            manifest_task_ref is not None
            and type(manifest_task_ref.state_version) is not int
        ):
            return False
        if (
            budget.max_tool_calls != 3
            or budget.accepted_parallel_tool_calls != 0
            or type(budget.closure_complete) is not bool
            or budget.closure_complete is not True
            or type(progress.history_complete) is not bool
            or progress.history_complete is not True
        ):
            return False
        if any(
            count is not None and type(count) is not int
            for count in (token_counts.input_tokens, token_counts.output_tokens)
        ):
            return False
        if not cycle2_registry_private_policies_are_raw_exact(
            loaded.registry_snapshot
        ):
            return False
    except (AttributeError, TypeError, ValueError):
        return False
    return True


def evaluate_cycle2_control_gateway(
    *,
    candidate: Cycle2GatewayCandidate,
    loaded_closure: Cycle2GatewayLoadedClosure,
    gate_decision_id: UUID,
    provider_tool_call_id: str | None,
    decided_at: datetime,
) -> GateDecision:
    """Return only a pure decision over the typed Cycle 2 loaded closure.

    This inactive helper neither creates a ToolCall nor dispatches, persists, or
    claims a durable authorization/fence.
    """

    decided_at = require_utc(decided_at, field_name="decided_at")
    try:
        if not _cycle2_raw_exact_type_preflight(candidate, loaded_closure):
            raise ValueError("Cycle 2 raw exact-type preflight failed")
        candidate = Cycle2GatewayCandidate.model_validate(
            candidate.model_dump(),
            strict=True,
        )
        loaded_closure = Cycle2GatewayLoadedClosure.model_validate(
            loaded_closure.model_dump(),
            strict=True,
        )
    except (
        ValidationError,
        PydanticSerializationError,
        ValueError,
        TypeError,
        AttributeError,
    ):
        return _cycle2_malformed_rejection(
            candidate=candidate,
            gate_decision_id=gate_decision_id,
            provider_tool_call_id=provider_tool_call_id,
            decided_at=decided_at,
        )
    snapshot = loaded_closure.registry_snapshot
    manifest = loaded_closure.context_manifest
    snapshot_match = (
        manifest.tool_registry_version == snapshot.tool_registry_version
        and manifest.model_visible_toolset_hash == snapshot.model_visible_toolset_hash
    )
    resolved_name, registration = _resolve_registration(
        snapshot,
        candidate.requested_provider_tool_name,
    )
    try:
        tool_name = (
            Cycle2ToolName(resolved_name) if resolved_name is not None else None
        )
    except ValueError:
        tool_name = None
    provider_visible_spec = _resolve_provider_visible_spec(
        snapshot,
        candidate.requested_provider_tool_name,
    )

    expected_snapshot = build_cycle2_registry_snapshot()
    expected_registration = None
    expected_visible_spec = None
    if tool_name is not None:
        expected_registration = next(
            (
                item
                for item in expected_snapshot.canonical_registrations
                if item.tool_spec.name == tool_name.value
            ),
            None,
        )
        expected_visible_spec = next(
            (
                item
                for item in expected_snapshot.provider_visible_toolset
                if item.name == tool_name.value
            ),
            None,
        )
    try:
        validate_cycle2_registry_snapshot(snapshot)
    except ValueError:
        registry_exact = False
    else:
        registry_exact = True
    registration_valid = (
        tool_name is not None
        and candidate.requested_provider_tool_name == tool_name.value
        and resolved_name == tool_name.value
        and registration == expected_registration
        and provider_visible_spec == expected_visible_spec
        and registry_exact
    )
    trusted_field_valid = (
        find_trusted_argument_field(candidate.candidate_arguments) is None
    )
    schema_valid = _cycle2_schema_valid(
        tool_name=tool_name,
        arguments=candidate.candidate_arguments,
    )
    argument_binding_valid = _cycle2_argument_binding_valid(
        candidate=candidate,
        loaded=loaded_closure,
        tool_name=tool_name,
    )
    budget_valid = _cycle2_budget_valid(
        candidate=candidate,
        loaded=loaded_closure,
    )
    progress_valid = _cycle2_progress_valid(
        candidate=candidate,
        tool_name=tool_name,
        loaded=loaded_closure,
    )
    state_version_valid = _cycle2_state_version_valid(
        candidate=candidate,
        loaded=loaded_closure,
    )
    action_boundary_valid = (
        registration is not None and registration.effect is ToolEffect.READ
    )

    checks = (
        snapshot_match,
        registration_valid,
        schema_valid,
        trusted_field_valid,
        argument_binding_valid,
        budget_valid,
        progress_valid,
        state_version_valid,
        action_boundary_valid,
    )
    reason_code: GateReasonCode | None = None
    if not action_boundary_valid and registration is not None:
        reason_code = GateReasonCode.ACTION_REQUIRES_PROPOSAL
    elif not snapshot_match:
        reason_code = GateReasonCode.SNAPSHOT_MISMATCH
    elif not registration_valid:
        reason_code = GateReasonCode.TOOL_NOT_REGISTERED
    elif not trusted_field_valid:
        reason_code = GateReasonCode.TRUSTED_FIELD_INJECTION
    elif not schema_valid:
        reason_code = GateReasonCode.SCHEMA_INVALID
    elif not state_version_valid:
        reason_code = GateReasonCode.STATE_VERSION_MISMATCH
    elif not argument_binding_valid:
        reason_code = GateReasonCode.ARGUMENT_BINDING_MISMATCH
    elif not budget_valid:
        reason_code = GateReasonCode.BUDGET_EXCEEDED
    elif not progress_valid:
        reason_code = GateReasonCode.NO_PROGRESS

    accepted = all(checks)
    return GateDecision(
        gate_decision_id=gate_decision_id,
        model_call_id=candidate.model_call_id,
        context_manifest_id=candidate.context_manifest_id,
        provider_tool_call_id=provider_tool_call_id,
        requested_provider_tool_name=candidate.requested_provider_tool_name,
        resolved_canonical_tool_name=resolved_name,
        snapshot_match=snapshot_match,
        registration_valid=registration_valid,
        schema_valid=schema_valid,
        trusted_field_valid=trusted_field_valid,
        argument_binding_valid=argument_binding_valid,
        argument_binding_refs=candidate.argument_binding_refs,
        budget_valid=budget_valid,
        progress_valid=progress_valid,
        proposed_base_task_state_version=(
            candidate.proposed_base_task_state_version
        ),
        validated_task_state_version=candidate.validated_task_state_version,
        state_version_valid=state_version_valid,
        action_boundary_valid=action_boundary_valid,
        decision=(
            GateDecisionValue.ACCEPT if accepted else GateDecisionValue.REJECT
        ),
        reason_code=reason_code,
        decided_at=decided_at,
    )
