from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from mini_agent.core.tool_system import (
    AuthorizedToolCommand,
    ExecutionPolicy,
    GateDecision,
    GateDecisionValue,
    GateReasonCode,
    RegistrySnapshot,
    ToolCallRecord,
    ToolCallStatus,
    ToolEffect,
    ToolRegistration,
    ToolSpec,
    compute_model_visible_toolset_hash,
    get_order_tool_spec,
)

NOW = datetime(2030, 1, 1, tzinfo=UTC)


def _spec(name: str, description: str = "Safe synthetic read contract.") -> ToolSpec:
    return ToolSpec(
        name=name,
        description=description,
        input_schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "resource_ref": {"type": "string"},
            },
            "required": ["resource_ref"],
        },
        output_schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {"outcome": {"type": "string"}},
            "required": ["outcome"],
        },
    )


def _registration(
    name: str,
    *,
    provider_name: str | None = None,
    handler_ref: str = "handlers.synthetic",
) -> ToolRegistration:
    return ToolRegistration(
        tool_spec=_spec(name),
        provider_visible_name=provider_name or name,
        effect=ToolEffect.READ,
        risk="LOW",
        idempotency="READ_ONLY",
        handler_ref=handler_ref,
        execution_policy=ExecutionPolicy(
            timeout_ms=500,
            max_attempts=1,
            interrupt_behavior="MARK_INTERRUPTED",
        ),
    )


def test_get_order_toolspec_has_only_model_visible_business_argument() -> None:
    tool_spec = get_order_tool_spec()
    properties = tool_spec.input_schema["properties"]

    assert set(properties) == {"order_id"}
    assert "customer_id" not in str(tool_spec.model_dump())
    assert tool_spec.input_schema["additionalProperties"] is False


def test_model_visible_hash_is_order_independent_and_content_sensitive() -> None:
    first = _spec("first_read")
    second = _spec("second_read")

    assert compute_model_visible_toolset_hash((first, second)) == (
        compute_model_visible_toolset_hash((second, first))
    )
    assert compute_model_visible_toolset_hash((first,)) != (
        compute_model_visible_toolset_hash(
            (_spec("first_read", description="Changed model-visible contract."),)
        )
    )


def test_registry_snapshot_excludes_private_registration_changes_from_hash() -> None:
    first = RegistrySnapshot.build(
        tool_registry_version="runtime-tools-v1",
        registrations=(
            _registration("first_read", handler_ref="handlers.first"),
        ),
    )
    second = RegistrySnapshot.build(
        tool_registry_version="runtime-tools-v2",
        registrations=(
            _registration("first_read", handler_ref="handlers.replaced"),
        ),
    )

    assert first.model_visible_toolset_hash == second.model_visible_toolset_hash
    assert first.artifact().model_visible_toolset_hash == (
        first.model_visible_toolset_hash
    )

    with pytest.raises(ValidationError, match="frozen"):
        first.tool_registry_version = "mutated"

    with pytest.raises(TypeError, match="immutable"):
        first.provider_visible_toolset[0].input_schema["properties"][
            "injected"
        ] = {"type": "string"}


def test_registry_rejects_duplicate_provider_mapping() -> None:
    with pytest.raises(ValueError, match="provider-visible"):
        RegistrySnapshot.build(
            tool_registry_version="runtime-tools-v1",
            registrations=(
                _registration("first_read", provider_name="same_name"),
                _registration("second_read", provider_name="same_name"),
            ),
        )


def test_model_visible_toolspec_rejects_trusted_identity_parameter() -> None:
    with pytest.raises(ValidationError, match="trusted field"):
        ToolSpec(
            name="unsafe_read",
            description="Unsafe.",
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {"customer_id": {"type": "string"}},
                "required": ["customer_id"],
            },
            output_schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {},
            },
        )


def test_argument_binding_mismatch_is_a_gate_rejection_not_a_toolcall() -> None:
    rejected = GateDecision(
        gate_decision_id=uuid4(),
        model_call_id=uuid4(),
        context_manifest_id=uuid4(),
        requested_provider_tool_name="get_order",
        resolved_canonical_tool_name="get_order",
        snapshot_match=True,
        registration_valid=True,
        schema_valid=True,
        trusted_field_valid=True,
        argument_binding_valid=False,
        argument_binding_refs=(uuid4(),),
        budget_valid=True,
        progress_valid=True,
        proposed_base_task_state_version=None,
        validated_task_state_version=1,
        state_version_valid=True,
        action_boundary_valid=True,
        decision=GateDecisionValue.REJECT,
        reason_code=GateReasonCode.ARGUMENT_BINDING_MISMATCH,
        decided_at=NOW,
    )

    assert rejected.decision is GateDecisionValue.REJECT
    assert "tool_call_id" not in GateDecision.model_fields


def test_authorized_command_cannot_move_identity_into_business_arguments() -> None:
    with pytest.raises(ValidationError, match="cannot include"):
        AuthorizedToolCommand(
            gate_decision_id=uuid4(),
            canonical_tool_name="get_order",
            validated_arguments={
                "order_id": "O-4242",
                "customer_id": "attacker-selected",
            },
            argument_binding_refs=(uuid4(),),
            validated_task_state_version=1,
            registry_snapshot_ref="snapshot-safe-ref",
            trusted_context_ref="private-context-safe-ref",
        )


def test_toolcall_terminal_state_requires_finish_time() -> None:
    base = {
        "tool_call_id": uuid4(),
        "run_id": uuid4(),
        "task_id": uuid4(),
        "request_unit_id": uuid4(),
        "model_call_id": uuid4(),
        "context_manifest_id": uuid4(),
        "gate_decision_id": uuid4(),
        "canonical_tool_name": "get_order",
        "tool_registry_version": "runtime-tools-v1",
        "validated_task_state_version": 1,
        "argument_binding_refs": (uuid4(),),
        "effect": ToolEffect.READ,
        "attempt_count": 1,
        "started_at": NOW,
    }

    with pytest.raises(ValidationError, match="finished_at"):
        ToolCallRecord(**base, status=ToolCallStatus.SUCCEEDED)

    record = ToolCallRecord(
        **base,
        status=ToolCallStatus.SUCCEEDED,
        finished_at=NOW,
        result_ref=uuid4(),
    )
    assert record.status is ToolCallStatus.SUCCEEDED
