from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError
from pydantic_core import PydanticSerializationError

from mini_agent.core.common import (
    FrozenJsonDict,
    FrozenJsonList,
    freeze_json_value,
)
from mini_agent.core.request_understanding import NextMove, NextMoveKind
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
    ToolTimeoutPhase,
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
        registrations=(_registration("first_read", handler_ref="handlers.first"),),
    )
    second = RegistrySnapshot.build(
        tool_registry_version="runtime-tools-v2",
        registrations=(_registration("first_read", handler_ref="handlers.replaced"),),
    )

    assert first.model_visible_toolset_hash == second.model_visible_toolset_hash
    assert first.artifact().model_visible_toolset_hash == (
        first.model_visible_toolset_hash
    )

    with pytest.raises(ValidationError, match="frozen"):
        first.tool_registry_version = "mutated"

    with pytest.raises(TypeError):
        first.provider_visible_toolset[0].input_schema["properties"]["injected"] = {
            "type": "string"
        }


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
    snapshot_schema = snapshot.provider_visible_toolset[0].input_schema
    snapshot_properties = snapshot_schema["properties"]
    snapshot_required = snapshot_schema["required"]

    assert isinstance(tool_spec.input_schema, Mapping)
    assert not isinstance(tool_spec.input_schema, dict)
    assert "properties" in snapshot_schema
    assert isinstance(snapshot_properties, Mapping)
    assert not isinstance(snapshot_properties, dict)
    assert isinstance(snapshot_required, Sequence)
    assert not isinstance(snapshot_required, list)

    with pytest.raises(TypeError):
        dict.__setitem__(
            tool_spec.input_schema,
            "customer_id",
            {"type": "string"},
        )
    with pytest.raises(TypeError):
        dict.__setitem__(
            snapshot_properties,
            "customer_id",
            {"type": "string"},
        )
    with pytest.raises(TypeError):
        dict.__ior__(
            snapshot_properties,
            {"customer_id": {"type": "string"}},
        )
    with pytest.raises(TypeError):
        list.append(snapshot_required, "customer_id")

    assert "customer_id" not in str(tool_spec.model_dump())
    assert "customer_id" not in str(snapshot.model_dump())
    assert (
        compute_model_visible_toolset_hash(snapshot.provider_visible_toolset)
        == original_hash
    )


def test_direct_frozen_dict_constructor_copies_aliases_before_dtos() -> None:
    mutable_properties = {"resource_ref": {"type": "string"}}
    mutable_required = ["resource_ref"]
    frozen_schema = FrozenJsonDict(
        {
            "type": "object",
            "additionalProperties": False,
            "properties": mutable_properties,
            "required": mutable_required,
        }
    )
    tool_spec = ToolSpec(
        name="direct_frozen_read",
        description="Safe direct Frozen input.",
        input_schema=frozen_schema,
        output_schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {},
        },
    )
    original_hash = compute_model_visible_toolset_hash((tool_spec,))

    mutable_metadata = {"labels": ["safe"]}
    frozen_arguments = FrozenJsonDict(
        {
            "order_id": "O-4242",
            "metadata": mutable_metadata,
        }
    )
    command = AuthorizedToolCommand(
        gate_decision_id=uuid4(),
        canonical_tool_name="get_order",
        validated_arguments=frozen_arguments,
        argument_binding_refs=(uuid4(),),
        validated_task_state_version=1,
        registry_snapshot_ref="snapshot-safe-ref",
        trusted_context_ref="private-context-safe-ref",
    )

    mutable_properties["customer_id"] = {"type": "string"}
    mutable_required.append("customer_id")
    mutable_metadata["customer_id"] = "late-injection"

    assert "customer_id" not in frozen_schema["properties"]
    assert "customer_id" not in frozen_schema["required"]
    assert "customer_id" not in frozen_arguments["metadata"]
    assert "customer_id" not in str(tool_spec.model_dump(mode="json"))
    assert "customer_id" not in str(command.model_dump(mode="json"))
    assert compute_model_visible_toolset_hash((tool_spec,)) == original_hash


def test_direct_frozen_list_constructor_copies_aliases_before_tool_result() -> None:
    mutable_object = {"outcome": "SUCCESS"}
    mutable_array = ["safe"]
    frozen_payload = FrozenJsonList((mutable_object, mutable_array))
    result = ToolResult(
        tool_call_id=uuid4(),
        canonical_tool_name="get_order",
        outcome=ToolResultOutcome.SUCCESS,
        payload=frozen_payload,
        retryable=False,
        observed_at=NOW,
        completed_at=NOW,
    )

    mutable_object["customer_id"] = "late-injection"
    mutable_array.append("customer_id")

    assert "customer_id" not in frozen_payload[0]
    assert "customer_id" not in frozen_payload[1]
    assert result.model_dump(mode="json")["payload"] == [
        {"outcome": "SUCCESS"},
        ["safe"],
    ]


def test_freeze_json_value_rebuilds_untrusted_frozen_instances() -> None:
    mutable_object: dict[str, object] = {"safe": True}
    mutable_array = ["safe"]
    forged_dict = tuple.__new__(
        FrozenJsonDict,
        (("nested", mutable_object),),
    )
    forged_list = tuple.__new__(FrozenJsonList, (mutable_array,))

    rebuilt_dict = freeze_json_value(forged_dict)
    rebuilt_list = freeze_json_value(forged_list)
    mutable_object["customer_id"] = "late-injection"
    mutable_array.append("customer_id")

    assert rebuilt_dict is not forged_dict
    assert rebuilt_list is not forged_list
    assert "customer_id" not in rebuilt_dict["nested"]
    assert "customer_id" not in rebuilt_list[0]


def test_frozen_json_constructors_reject_cyclic_containers() -> None:
    cyclic_object: dict[str, object] = {}
    cyclic_object["self"] = cyclic_object
    cyclic_array: list[object] = []
    cyclic_array.append(cyclic_array)

    with pytest.raises(ValueError, match="cyclic JSON container"):
        FrozenJsonDict(cyclic_object)
    with pytest.raises(ValueError, match="cyclic JSON container"):
        FrozenJsonList(cyclic_array)


@pytest.mark.parametrize(
    "non_finite",
    [
        pytest.param(float("nan"), id="nan"),
        pytest.param(float("inf"), id="positive-infinity"),
        pytest.param(float("-inf"), id="negative-infinity"),
    ],
)
def test_frozen_json_constructors_reject_non_finite_numbers(
    non_finite: float,
) -> None:
    with pytest.raises(ValueError, match="finite"):
        FrozenJsonDict({"nested": [non_finite]})
    with pytest.raises(ValueError, match="finite"):
        FrozenJsonList(({"nested": non_finite},))


@pytest.mark.parametrize(
    "non_finite",
    [
        pytest.param(float("nan"), id="nan"),
        pytest.param(float("inf"), id="positive-infinity"),
        pytest.param(float("-inf"), id="negative-infinity"),
    ],
)
def test_json_contract_boundaries_reject_non_finite_numbers(
    non_finite: float,
) -> None:
    unsafe_schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "measurement": {
                "type": "number",
                "example": non_finite,
            }
        },
    }
    with pytest.raises(ValidationError, match="finite"):
        ToolSpec(
            name="unsafe_number_read",
            description="Unsafe non-finite schema.",
            input_schema=unsafe_schema,
            output_schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {},
            },
        )
    with pytest.raises(ValidationError, match="finite"):
        NextMove(
            kind=NextMoveKind.CALL_TOOL,
            requested_tool_name="get_order",
            arguments={"nested": [non_finite]},
        )
    with pytest.raises(ValidationError, match="finite"):
        AuthorizedToolCommand(
            gate_decision_id=uuid4(),
            canonical_tool_name="get_order",
            validated_arguments={
                "order_id": "O-4242",
                "metadata": {"measurement": non_finite},
            },
            argument_binding_refs=(uuid4(),),
            validated_task_state_version=1,
            registry_snapshot_ref="snapshot-safe-ref",
            trusted_context_ref="private-context-safe-ref",
        )
    with pytest.raises(ValidationError, match="finite"):
        ToolResult(
            tool_call_id=uuid4(),
            canonical_tool_name="get_order",
            outcome=ToolResultOutcome.SUCCESS,
            payload={"nested": [non_finite]},
            retryable=False,
            observed_at=NOW,
            completed_at=NOW,
        )


@pytest.mark.parametrize(
    "non_finite",
    [
        pytest.param(float("nan"), id="nan"),
        pytest.param(float("inf"), id="positive-infinity"),
        pytest.param(float("-inf"), id="negative-infinity"),
    ],
)
def test_toolset_hash_and_artifact_serialization_fail_closed_for_bypass(
    non_finite: float,
) -> None:
    bypassed_spec = ToolSpec.model_construct(
        name="bypassed_number_read",
        description="Bypassed unsafe schema.",
        input_schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "measurement": {
                    "type": "number",
                    "example": non_finite,
                }
            },
        },
        output_schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {},
        },
    )

    with pytest.raises((ValueError, PydanticSerializationError)):
        compute_model_visible_toolset_hash((bypassed_spec,))

    bypassed_artifact = ModelVisibleToolsetArtifact.model_construct(
        model_visible_toolset_hash=f"sha256:{'0' * 64}",
        provider_visible_tool_specs=(bypassed_spec,),
    )
    with pytest.raises(PydanticSerializationError, match="finite"):
        bypassed_artifact.model_dump_json()


@pytest.mark.parametrize(
    "non_finite",
    [
        pytest.param(float("nan"), id="nan"),
        pytest.param(float("inf"), id="positive-infinity"),
        pytest.param(float("-inf"), id="negative-infinity"),
    ],
)
def test_tool_result_serialization_fails_closed_for_bypass(
    non_finite: float,
) -> None:
    bypassed_result = ToolResult.model_construct(
        tool_call_id=uuid4(),
        canonical_tool_name="get_order",
        outcome=ToolResultOutcome.SUCCESS,
        payload={"nested": [non_finite]},
        retryable=False,
        observed_at=NOW,
        completed_at=NOW,
    )

    with pytest.raises(PydanticSerializationError, match="finite"):
        bypassed_result.model_dump_json()


def test_finite_numbers_round_trip_through_artifact_and_tool_result() -> None:
    tool_spec = ToolSpec(
        name="finite_number_read",
        description="Finite number schema.",
        input_schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "measurement": {
                    "type": "number",
                    "example": 1.25,
                }
            },
        },
        output_schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {},
        },
    )
    toolset_hash = compute_model_visible_toolset_hash((tool_spec,))
    artifact = ModelVisibleToolsetArtifact(
        model_visible_toolset_hash=toolset_hash,
        provider_visible_tool_specs=(tool_spec,),
    )
    restored_artifact = ModelVisibleToolsetArtifact.model_validate_json(
        artifact.model_dump_json()
    )

    assert FrozenJsonDict({"measurement": 1.25})["measurement"] == 1.25
    assert FrozenJsonList((-1.5, 0.0, 2.5)) == [-1.5, 0.0, 2.5]
    assert restored_artifact.model_visible_toolset_hash == toolset_hash
    assert (
        compute_model_visible_toolset_hash(
            restored_artifact.provider_visible_tool_specs
        )
        == toolset_hash
    )

    result = ToolResult(
        tool_call_id=uuid4(),
        canonical_tool_name="get_order",
        outcome=ToolResultOutcome.SUCCESS,
        payload={"measurements": [-1.5, 0.0, 2.5]},
        retryable=False,
        observed_at=NOW,
        completed_at=NOW,
    )
    restored_result = ToolResult.model_validate_json(result.model_dump_json())

    assert restored_result.model_dump(mode="json")["payload"] == {
        "measurements": [-1.5, 0.0, 2.5]
    }


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

    with pytest.raises(
        ValidationError,
        match="ARGUMENT_BINDING_MISMATCH requires argument_binding_refs",
    ):
        GateDecision.model_validate(
            {
                **rejected.model_dump(),
                "argument_binding_refs": (),
            }
        )


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

    assert isinstance(payload, Mapping)
    assert not isinstance(payload, dict)
    assert isinstance(order_summary, Mapping)
    assert not isinstance(order_summary, dict)
    assert isinstance(line_items, Sequence)
    assert not isinstance(line_items, list)

    with pytest.raises(TypeError):
        dict.__setitem__(payload, "customer_id", "late-injection")
    with pytest.raises(TypeError):
        dict.__ior__(order_summary, {"customer_id": "late-injection"})
    with pytest.raises(TypeError):
        list.append(line_items, {"customer_id": "late-injection"})

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
        timeout_phase=ToolTimeoutPhase.AFTER_DISPATCH,
    )
    assert timed_out.timeout_phase is ToolTimeoutPhase.AFTER_DISPATCH

    with pytest.raises(ValidationError, match="Input should be"):
        ToolCallRecord(
            **base,
            status=ToolCallStatus.TIMED_OUT,
            finished_at=NOW,
            timeout_phase="UPSTREAM_WAIT",
        )

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


@pytest.mark.parametrize(
    ("status", "lifecycle_values"),
    [
        (ToolCallStatus.RUNNING, {}),
        (ToolCallStatus.SUCCEEDED, {"finished_at": NOW}),
        (
            ToolCallStatus.FAILED,
            {"finished_at": NOW, "failure_code": "UPSTREAM_FAILURE"},
        ),
        (
            ToolCallStatus.TIMED_OUT,
            {
                "finished_at": NOW,
                "timeout_phase": ToolTimeoutPhase.UNKNOWN,
            },
        ),
        (
            ToolCallStatus.INTERRUPTED,
            {
                "finished_at": NOW,
                "interruption_reason": "PROCESS_RESTART_DETECTED",
            },
        ),
    ],
)
def test_initiated_toolcall_requires_at_least_one_attempt(
    status: ToolCallStatus,
    lifecycle_values: dict[str, object],
) -> None:
    with pytest.raises(ValidationError, match="attempt_count >= 1"):
        ToolCallRecord(
            **{
                **_tool_call_values(),
                "attempt_count": 0,
                **lifecycle_values,
            },
            status=status,
        )

    created = ToolCallRecord(
        **{
            **_tool_call_values(),
            "attempt_count": 0,
        },
        status=ToolCallStatus.CREATED,
    )
    assert created.attempt_count == 0


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
