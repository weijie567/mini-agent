from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from mini_agent.core.tool_system import (
    MODEL_VISIBLE_TOOLSET_ARTIFACT_SCHEMA_VERSION,
    AuthorizedToolCommand,
    ExecutionPolicy,
    GateDecision,
    GateDecisionValue,
    GateReasonCode,
    ModelVisibleToolsetArtifact,
    RegistrySnapshot,
    ToolAttemptRecord,
    ToolCallRecord,
    ToolCallStatus,
    ToolEffect,
    ToolRegistration,
    ToolResult,
    ToolResultOutcome,
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


def _tool_call_values() -> dict[str, object]:
    return {
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


def test_toolset_json_blocks_mutation_aliases_and_preserves_hash() -> None:
    tool_spec = _spec("first_read")
    snapshot = RegistrySnapshot.build(
        tool_registry_version="runtime-tools-v1",
        registrations=(
            ToolRegistration(
                tool_spec=tool_spec,
                provider_visible_name="first_read",
                effect=ToolEffect.READ,
                risk="LOW",
                idempotency="READ_ONLY",
                handler_ref="handlers.first",
                execution_policy=ExecutionPolicy(
                    timeout_ms=500,
                    max_attempts=1,
                    interrupt_behavior="MARK_INTERRUPTED",
                ),
            ),
        ),
    )
    original_hash = snapshot.model_visible_toolset_hash
    injected_property = {"customer_id": {"type": "string"}}

    with pytest.raises(TypeError, match="immutable"):
        tool_spec.input_schema |= {
            "properties": injected_property,
        }

    snapshot_schema = snapshot.provider_visible_toolset[0].input_schema
    snapshot_properties = snapshot_schema["properties"]
    snapshot_required = snapshot_schema["required"]

    with pytest.raises(TypeError, match="immutable"):
        snapshot_properties |= injected_property
    with pytest.raises(TypeError, match="immutable"):
        snapshot_properties.update(injected_property)
    with pytest.raises(TypeError, match="immutable"):
        snapshot_properties.setdefault("customer_id", {"type": "string"})
    with pytest.raises(TypeError, match="immutable"):
        snapshot_properties.__init__(injected_property)
    dict_mutation_aliases = (
        lambda: snapshot_properties.__setitem__(
            "customer_id", {"type": "string"}
        ),
        lambda: snapshot_properties.__delitem__("resource_ref"),
        snapshot_properties.clear,
        lambda: snapshot_properties.pop("resource_ref"),
        snapshot_properties.popitem,
    )
    for mutate in dict_mutation_aliases:
        with pytest.raises(TypeError, match="immutable"):
            mutate()

    with pytest.raises(TypeError, match="immutable"):
        snapshot_required.append("customer_id")
    with pytest.raises(TypeError, match="immutable"):
        snapshot_required += ["customer_id"]
    list_mutation_aliases = (
        lambda: snapshot_required.__setitem__(0, "customer_id"),
        lambda: snapshot_required.__delitem__(0),
        snapshot_required.clear,
        lambda: snapshot_required.extend(["customer_id"]),
        lambda: snapshot_required.insert(0, "customer_id"),
        snapshot_required.pop,
        lambda: snapshot_required.remove("resource_ref"),
        snapshot_required.reverse,
        snapshot_required.sort,
        lambda: snapshot_required.__imul__(2),
        lambda: snapshot_required.__init__(["customer_id"]),
    )
    for mutate in list_mutation_aliases:
        with pytest.raises(TypeError, match="immutable"):
            mutate()

    assert "customer_id" not in str(tool_spec.model_dump())
    assert "customer_id" not in str(snapshot.model_dump())
    assert compute_model_visible_toolset_hash(
        snapshot.provider_visible_toolset
    ) == original_hash


def test_toolset_artifact_rejects_noncanonical_schema_version() -> None:
    snapshot = RegistrySnapshot.build(
        tool_registry_version="runtime-tools-v1",
        registrations=(_registration("first_read"),),
    )
    artifact = snapshot.artifact()

    assert (
        artifact.artifact_schema_version
        == MODEL_VISIBLE_TOOLSET_ARTIFACT_SCHEMA_VERSION
    )
    with pytest.raises(ValidationError, match="model-visible-toolset.p0.v1"):
        ModelVisibleToolsetArtifact.model_validate(
            {
                **artifact.model_dump(),
                "artifact_schema_version": "model-visible-toolset.p0.v2",
            }
        )


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


def test_gate_rejection_requires_a_failed_check_matching_the_reason() -> None:
    base: dict[str, object] = {
        "gate_decision_id": uuid4(),
        "model_call_id": uuid4(),
        "context_manifest_id": uuid4(),
        "requested_provider_tool_name": "get_order",
        "resolved_canonical_tool_name": "get_order",
        "snapshot_match": True,
        "registration_valid": True,
        "schema_valid": True,
        "trusted_field_valid": True,
        "argument_binding_valid": True,
        "argument_binding_refs": (uuid4(),),
        "budget_valid": True,
        "progress_valid": True,
        "validated_task_state_version": 1,
        "state_version_valid": True,
        "action_boundary_valid": True,
        "decision": GateDecisionValue.REJECT,
        "decided_at": NOW,
    }

    with pytest.raises(ValidationError, match="at least one failed"):
        GateDecision(
            **base,
            reason_code=GateReasonCode.ARGUMENT_BINDING_MISMATCH,
        )

    with pytest.raises(ValidationError, match="reason_code must match"):
        GateDecision(
            **{
                **base,
                "argument_binding_valid": False,
            },
            reason_code=GateReasonCode.SCHEMA_INVALID,
        )


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


def test_tool_result_payload_is_recursively_immutable_after_validation() -> None:
    source_payload = {
        "order_summary": {
            "line_items": [{"product_name": "示例商品", "quantity": 1}],
        }
    }
    result = ToolResult(
        tool_call_id=uuid4(),
        canonical_tool_name="get_order",
        outcome=ToolResultOutcome.SUCCESS,
        payload=source_payload,
        retryable=False,
        observed_at=NOW,
        completed_at=NOW,
    )
    expected_payload = result.model_dump(mode="json")["payload"]

    source_payload["customer_id"] = "late-source-mutation"
    payload = result.payload
    order_summary = payload["order_summary"]
    line_items = order_summary["line_items"]

    with pytest.raises(TypeError, match="immutable"):
        payload |= {"customer_id": "late-injection"}
    with pytest.raises(TypeError, match="immutable"):
        order_summary.update({"customer_id": "late-injection"})
    with pytest.raises(TypeError, match="immutable"):
        line_items.append({"customer_id": "late-injection"})

    assert "customer_id" not in str(result.model_dump())
    assert result.model_dump(mode="json")["payload"] == expected_payload


def test_toolcall_terminal_state_requires_finish_time() -> None:
    base = _tool_call_values()

    with pytest.raises(ValidationError, match="finished_at"):
        ToolCallRecord(**base, status=ToolCallStatus.SUCCEEDED)

    record = ToolCallRecord(
        **base,
        status=ToolCallStatus.SUCCEEDED,
        finished_at=NOW,
        result_ref=uuid4(),
    )
    assert record.status is ToolCallStatus.SUCCEEDED


def test_toolcall_requires_binding_chain_and_status_specific_safe_codes() -> None:
    base = _tool_call_values()

    with pytest.raises(ValidationError, match="at least 1"):
        ToolCallRecord(
            **{
                **base,
                "argument_binding_refs": (),
            },
            status=ToolCallStatus.RUNNING,
        )

    with pytest.raises(ValidationError, match="timeout_phase"):
        ToolCallRecord(
            **base,
            status=ToolCallStatus.TIMED_OUT,
            finished_at=NOW,
        )

    timed_out = ToolCallRecord(
        **base,
        status=ToolCallStatus.TIMED_OUT,
        finished_at=NOW,
        timeout_phase="POST_DISPATCH",
    )
    assert timed_out.timeout_phase == "POST_DISPATCH"

    with pytest.raises(ValidationError, match="interruption_reason"):
        ToolCallRecord(
            **base,
            status=ToolCallStatus.INTERRUPTED,
            finished_at=NOW,
        )

    with pytest.raises(ValidationError, match="String should match pattern"):
        ToolCallRecord(
            **base,
            status=ToolCallStatus.INTERRUPTED,
            finished_at=NOW,
            interruption_reason="unsafe free text",
        )

    interrupted = ToolCallRecord(
        **base,
        status=ToolCallStatus.INTERRUPTED,
        finished_at=NOW,
        interruption_reason="PROCESS_RESTART_DETECTED",
    )
    assert interrupted.interruption_reason == "PROCESS_RESTART_DETECTED"


def test_tool_attempt_record_has_append_only_attempt_identity_and_utc_order() -> None:
    attempt = ToolAttemptRecord(
        tool_call_id=uuid4(),
        attempt_no=1,
        started_at=NOW,
        finished_at=NOW,
        outcome=ToolResultOutcome.SUCCESS,
    )
    assert attempt.attempt_no == 1

    with pytest.raises(ValidationError, match="cannot precede"):
        ToolAttemptRecord(
            tool_call_id=uuid4(),
            attempt_no=1,
            started_at=NOW,
            finished_at=datetime(2029, 1, 1, tzinfo=UTC),
            outcome=ToolResultOutcome.SYSTEM_FAILURE,
            failure_code="UPSTREAM_FAILURE",
        )
