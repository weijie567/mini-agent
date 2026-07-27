"""Pure fail-closed Control Gateway decisions for the first E2E-01 slice."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime
from uuid import UUID

from .common import find_trusted_argument_field
from .identity import CustomerContext
from .memory import ContextManifest
from .request_processing import RevalidatedNextMove
from .task_state import InputBinding, RequestUnitRecord, TaskRecord, TaskStatus
from .tool_system import (
    GateDecision,
    GateDecisionValue,
    GateReasonCode,
    RegistrySnapshot,
    ToolEffect,
    ToolRegistration,
    ToolSpec,
    get_order_tool_spec,
)

_ORDER_ID_PATTERN = re.compile(r"^O-[0-9]{4,20}$")


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
