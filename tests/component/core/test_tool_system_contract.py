from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
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
    CYCLE2_TOOL_REGISTRY_VERSION,
    Cycle2RetryRevalidation,
    Cycle2ToolName,
    Cycle2ToolTerminalProjection,
    ExecutionPolicy,
    GateDecision,
    GateDecisionValue,
    GateReasonCode,
    ModelVisibleToolsetArtifact,
    RegistrySnapshot,
    ToolAttemptRecord,
    ToolAttemptRecordV2,
    ToolCallRecord,
    ToolCallRecordV2,
    ToolCallStatus,
    ToolEffect,
    ToolRegistration,
    ToolRecoveryDecision,
    ToolResult,
    ToolResultOutcome,
    ToolRetryDecision,
    ToolRetryRecoveryDecision,
    ToolSpec,
    ToolTimeoutPhase,
    build_cycle2_registry_snapshot,
    cycle2_tool_profiles,
    compute_model_visible_toolset_hash,
    decide_cycle2_tool_recovery,
    decide_cycle2_tool_retry,
    effective_cycle2_tool_timeout_ms,
    get_shipment_tool_spec,
    get_order_tool_spec,
    project_cycle2_tool_terminal,
    search_orders_tool_spec,
    validate_cycle2_registry_snapshot,
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
    ("status", "attempt_count", "lifecycle_values"),
    [
        pytest.param(
            ToolCallStatus.CREATED,
            0,
            {},
            id="created-before-dispatch",
        ),
        pytest.param(
            ToolCallStatus.RUNNING,
            1,
            {},
            id="running-first-attempt",
        ),
        pytest.param(
            ToolCallStatus.SUCCEEDED,
            1,
            {"finished_at": NOW, "result_ref": uuid4()},
            id="succeeded-first-attempt",
        ),
        pytest.param(
            ToolCallStatus.FAILED,
            1,
            {"finished_at": NOW, "failure_code": "UPSTREAM_FAILURE"},
            id="failed-first-attempt",
        ),
        pytest.param(
            ToolCallStatus.TIMED_OUT,
            1,
            {
                "finished_at": NOW,
                "timeout_phase": ToolTimeoutPhase.AFTER_DISPATCH,
            },
            id="timed-out-first-attempt",
        ),
        pytest.param(
            ToolCallStatus.INTERRUPTED,
            0,
            {
                "finished_at": NOW,
                "interruption_reason": "PROCESS_RESTART_DETECTED",
            },
            id="interrupted-before-dispatch",
        ),
        pytest.param(
            ToolCallStatus.INTERRUPTED,
            1,
            {
                "finished_at": NOW,
                "interruption_reason": "PROCESS_RESTART_DETECTED",
            },
            id="interrupted-first-attempt",
        ),
        pytest.param(
            ToolCallStatus.INTERRUPTED,
            2,
            {
                "finished_at": NOW,
                "interruption_reason": "PROCESS_RESTART_DETECTED",
            },
            id="interrupted-after-retry",
        ),
    ],
)
def test_toolcall_accepts_valid_status_lifecycle(
    status: ToolCallStatus,
    attempt_count: int,
    lifecycle_values: dict[str, object],
) -> None:
    record = ToolCallRecord(
        **{
            **_tool_call_values(),
            "attempt_count": attempt_count,
            **lifecycle_values,
        },
        status=status,
    )

    assert record.status is status
    assert record.attempt_count == attempt_count


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
    ],
)
def test_dispatched_toolcall_requires_at_least_one_attempt(
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


def test_created_toolcall_requires_zero_attempts() -> None:
    with pytest.raises(ValidationError, match="attempt_count = 0"):
        ToolCallRecord(
            **_tool_call_values(),
            status=ToolCallStatus.CREATED,
        )


def test_active_tool_attempt_has_only_started_identity() -> None:
    attempt = ToolAttemptRecord(
        tool_call_id=uuid4(),
        attempt_no=1,
        started_at=NOW,
    )

    assert attempt.finished_at is None
    assert attempt.outcome is None
    assert attempt.failure_code is None


@pytest.mark.parametrize(
    ("lifecycle_values", "message"),
    [
        ({"outcome": ToolResultOutcome.SYSTEM_FAILURE}, "cannot carry outcome"),
        ({"failure_code": "UPSTREAM_FAILURE"}, "cannot carry failure_code"),
        ({"finished_at": NOW}, "requires outcome"),
    ],
)
def test_tool_attempt_rejects_partial_lifecycle_state(
    lifecycle_values: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        ToolAttemptRecord(
            tool_call_id=uuid4(),
            attempt_no=1,
            started_at=NOW,
            **lifecycle_values,
        )


def test_successful_tool_attempt_rejects_failure_code() -> None:
    with pytest.raises(ValidationError, match="cannot carry failure_code"):
        ToolAttemptRecord(
            tool_call_id=uuid4(),
            attempt_no=1,
            started_at=NOW,
            finished_at=NOW,
            outcome=ToolResultOutcome.SUCCESS,
            failure_code="UPSTREAM_FAILURE",
        )


def test_tool_attempt_record_has_append_only_attempt_identity_and_utc_order() -> None:
    tool_call_id = uuid4()
    first_attempt = ToolAttemptRecord(
        tool_call_id=tool_call_id,
        attempt_no=1,
        started_at=NOW,
        finished_at=NOW,
        outcome=ToolResultOutcome.SUCCESS,
    )
    retry_attempt = ToolAttemptRecord(
        tool_call_id=tool_call_id,
        attempt_no=2,
        started_at=NOW,
        finished_at=NOW,
        outcome=ToolResultOutcome.SYSTEM_FAILURE,
        failure_code="UPSTREAM_FAILURE",
    )

    assert (first_attempt.attempt_no, retry_attempt.attempt_no) == (1, 2)

    with pytest.raises(ValidationError, match="greater than or equal to 1"):
        ToolAttemptRecord(
            tool_call_id=tool_call_id,
            attempt_no=0,
            started_at=NOW,
        )

    with pytest.raises(ValidationError, match="cannot precede"):
        ToolAttemptRecord(
            tool_call_id=tool_call_id,
            attempt_no=1,
            started_at=NOW,
            finished_at=datetime(2029, 1, 1, tzinfo=UTC),
            outcome=ToolResultOutcome.SYSTEM_FAILURE,
            failure_code="UPSTREAM_FAILURE",
        )


def _assert_all_nested_object_schemas_are_closed(value: object) -> None:
    if isinstance(value, Mapping):
        if value.get("type") == "object":
            assert value.get("additionalProperties") is False
        for child in value.values():
            _assert_all_nested_object_schemas_are_closed(child)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for child in value:
            _assert_all_nested_object_schemas_are_closed(child)


def test_cycle2_search_orders_toolspec_is_exact_closed_minimum_disclosure() -> None:
    spec = search_orders_tool_spec()

    assert spec.name == "search_orders"
    assert spec.input_schema["required"] == ("product_description",)
    assert set(spec.input_schema["properties"]) == {"product_description"}
    description = spec.input_schema["properties"]["product_description"]
    assert description == {"type": "string", "minLength": 1, "maxLength": 80}

    output = spec.output_schema
    assert set(output["properties"]) == {"outcome", "candidates", "truncated"}
    assert output["required"] == ("outcome", "candidates", "truncated")
    candidate = output["properties"]["candidates"]["items"]
    assert set(candidate["properties"]) == {
        "ordinal",
        "order_number",
        "ordered_on_utc",
        "status",
        "matching_items",
    }
    matching_item = candidate["properties"]["matching_items"]["items"]
    assert set(matching_item["properties"]) == {"product_name", "quantity"}
    _assert_all_nested_object_schemas_are_closed(spec.model_dump(mode="json"))

    forbidden = {
        "customer_id",
        "owner_scoped_order_ref",
        "source_version",
        "failure_code",
        "ordered_at",
        "line_ordinal",
        "product_category",
        "search_aliases",
        "price",
        "address",
        "tracking_number",
        "query_window",
        "limit",
        "ranking",
    }
    serialized = str(spec.model_dump(mode="json"))
    assert all(field not in serialized for field in forbidden)


def test_cycle2_get_shipment_toolspec_is_exact_closed_minimum_disclosure() -> None:
    spec = get_shipment_tool_spec()

    assert spec.name == "get_shipment"
    assert spec.input_schema["required"] == ("order_id",)
    assert set(spec.input_schema["properties"]) == {"order_id"}
    assert set(spec.output_schema["properties"]) == {
        "shipment_status",
        "latest_event_code",
        "latest_event_at_utc",
        "promised_delivery_at_utc",
        "delivered_at_utc",
    }
    assert spec.output_schema["required"] == (
        "shipment_status",
        "latest_event_code",
        "latest_event_at_utc",
    )
    _assert_all_nested_object_schemas_are_closed(spec.model_dump(mode="json"))

    forbidden = {
        "customer_id",
        "package_id",
        "tracking_number",
        "address",
        "recipient",
        "phone",
        "raw_trajectory",
        "outcome",
        "failure_code",
        "insufficiency_code",
        "source_resource_ref",
        "source_version",
        "observed_at",
        "freshness",
        "retry",
    }
    serialized = str(spec.model_dump(mode="json"))
    assert all(field not in serialized for field in forbidden)


def test_cycle2_registry_is_exact_three_read_tools_with_exact_policies() -> None:
    snapshot = build_cycle2_registry_snapshot()
    profiles = cycle2_tool_profiles()

    assert snapshot.tool_registry_version == CYCLE2_TOOL_REGISTRY_VERSION
    assert tuple(profile.canonical_tool_name for profile in profiles) == (
        Cycle2ToolName.SEARCH_ORDERS,
        Cycle2ToolName.GET_ORDER,
        Cycle2ToolName.GET_SHIPMENT,
    )
    assert {registration.tool_spec.name for registration in snapshot.canonical_registrations} == {
        "search_orders",
        "get_order",
        "get_shipment",
    }
    assert {registration.provider_visible_name for registration in snapshot.canonical_registrations} == {
        "search_orders",
        "get_order",
        "get_shipment",
    }
    assert {registration.effect for registration in snapshot.canonical_registrations} == {
        ToolEffect.READ
    }
    policies = {
        registration.tool_spec.name: registration.execution_policy
        for registration in snapshot.canonical_registrations
    }
    assert policies["get_order"].model_dump() == {
        "timeout_ms": 500,
        "max_attempts": 1,
        "retryable_failure_codes": (),
        "interrupt_behavior": "MARK_INTERRUPTED",
    }
    assert policies["search_orders"].retryable_failure_codes == (
        "ORDER_SEARCH_TRANSIENT",
        "TOOL_CALL_TIMEOUT",
    )
    assert policies["get_shipment"].retryable_failure_codes == (
        "SHIPMENT_SERVICE_TRANSIENT",
        "TOOL_CALL_TIMEOUT",
    )
    assert policies["search_orders"].max_attempts == 2
    assert policies["get_shipment"].max_attempts == 2
    assert validate_cycle2_registry_snapshot(snapshot) is snapshot
    assert all(
        registration.unknown_result_recovery is None
        for registration in snapshot.canonical_registrations
    )
    assert "create_refund" not in str(snapshot.model_dump(mode="json"))
    assert "PROPOSE_ACTION" not in str(snapshot.model_dump(mode="json"))
    assert "ActionPolicy" not in str(snapshot.model_dump(mode="json"))


def test_cycle2_validator_is_scoped_without_tightening_generic_registry_build() -> None:
    generic_snapshot = RegistrySnapshot.build(
        tool_registry_version="generic-test-registry",
        registrations=(_registration("unrelated_safe_read"),),
    )
    assert generic_snapshot.canonical_registrations[0].tool_spec.name == (
        "unrelated_safe_read"
    )

    unexpected = RegistrySnapshot.build(
        tool_registry_version=CYCLE2_TOOL_REGISTRY_VERSION,
        registrations=tuple(build_cycle2_registry_snapshot().canonical_registrations)
        + (_registration("unexpected_read"),),
    )
    with pytest.raises(ValueError, match="exact Cycle 2 registry"):
        validate_cycle2_registry_snapshot(unexpected)


def _retry_revalidation(
    *,
    remaining_run_time_budget_ms: int = 500,
    current_owner_scope_ref: str = "owner-A",
    current_task_state_version: int = 3,
    current_binding_refs: tuple = (),
    current_verified_target_ref=None,
) -> Cycle2RetryRevalidation:
    binding_refs = current_binding_refs or (uuid4(),)
    verified_target_ref = current_verified_target_ref or uuid4()
    task_id = uuid4()
    request_unit_id = uuid4()
    return Cycle2RetryRevalidation(
        expected_owner_scope_ref="owner-A",
        current_owner_scope_ref=current_owner_scope_ref,
        expected_task_id=task_id,
        current_task_id=task_id,
        expected_request_unit_id=request_unit_id,
        current_request_unit_id=request_unit_id,
        expected_task_state_version=3,
        current_task_state_version=current_task_state_version,
        expected_argument_binding_refs=binding_refs,
        current_argument_binding_refs=binding_refs,
        expected_verified_target_ref=verified_target_ref,
        current_verified_target_ref=verified_target_ref,
        remaining_run_time_budget_ms=remaining_run_time_budget_ms,
    )


def _attempt_v2(
    *,
    tool_call_id=None,
    attempt_no: int = 1,
    outcome: ToolResultOutcome | None = None,
    failure_code: str | None = None,
    timeout_phase: ToolTimeoutPhase | None = None,
    retry_decision: ToolRetryDecision | None = None,
) -> ToolAttemptRecordV2:
    values: dict[str, object] = {
        "tool_call_id": tool_call_id or uuid4(),
        "attempt_no": attempt_no,
        "started_at": NOW + timedelta(milliseconds=attempt_no - 1),
    }
    if outcome is not None:
        values.update(
            finished_at=NOW + timedelta(milliseconds=attempt_no),
            outcome=outcome,
            failure_code=failure_code,
            timeout_phase=timeout_phase,
            retry_decision=retry_decision,
        )
    return ToolAttemptRecordV2(**values)


def _tool_call_v2_values(
    *,
    tool_call_id=None,
    canonical_tool_name: Cycle2ToolName = Cycle2ToolName.SEARCH_ORDERS,
) -> dict[str, object]:
    return {
        "tool_call_id": tool_call_id or uuid4(),
        "run_id": uuid4(),
        "task_id": uuid4(),
        "request_unit_id": uuid4(),
        "model_call_id": uuid4(),
        "context_manifest_id": uuid4(),
        "gate_decision_id": uuid4(),
        "canonical_tool_name": canonical_tool_name,
        "tool_registry_version": CYCLE2_TOOL_REGISTRY_VERSION,
        "validated_task_state_version": 3,
        "argument_binding_refs": (uuid4(),),
        "effect": ToolEffect.READ,
        "started_at": NOW,
    }


def test_cycle2_effective_timeout_is_bounded_by_policy_and_run_budget() -> None:
    assert effective_cycle2_tool_timeout_ms(800) == 500
    assert effective_cycle2_tool_timeout_ms(499) == 499
    with pytest.raises(ValueError, match="positive"):
        effective_cycle2_tool_timeout_ms(0)
    with pytest.raises(TypeError, match="strict integer"):
        effective_cycle2_tool_timeout_ms(True)


def test_cycle2_attempt_finalize_is_atomic_and_timeout_iff_is_closed() -> None:
    started = _attempt_v2()
    assert started.model_dump(exclude_none=True).keys() == {
        "tool_call_id",
        "attempt_no",
        "started_at",
    }

    with pytest.raises(ValidationError, match="finalize.*atomically"):
        ToolAttemptRecordV2(
            tool_call_id=uuid4(),
            attempt_no=1,
            started_at=NOW,
            finished_at=NOW,
            outcome=ToolResultOutcome.TIMEOUT,
        )
    with pytest.raises(ValidationError, match="TIMEOUT iff"):
        _attempt_v2(
            outcome=ToolResultOutcome.SYSTEM_FAILURE,
            failure_code="TOOL_CALL_TIMEOUT",
            retry_decision=ToolRetryDecision.NOT_RETRYABLE,
        )
    with pytest.raises(ValidationError, match="timeout_phase"):
        _attempt_v2(
            outcome=ToolResultOutcome.TIMEOUT,
            failure_code="TOOL_CALL_TIMEOUT",
            retry_decision=ToolRetryDecision.RETRY_SCHEDULED,
        )
    with pytest.raises(ValidationError, match="only TIMEOUT"):
        _attempt_v2(
            outcome=ToolResultOutcome.SYSTEM_FAILURE,
            failure_code="ORDER_SEARCH_TRANSIENT",
            timeout_phase=ToolTimeoutPhase.AFTER_DISPATCH,
            retry_decision=ToolRetryDecision.RETRY_SCHEDULED,
        )


@pytest.mark.parametrize(
    ("tool_name", "attempt_no", "outcome", "failure_code", "change", "expected"),
    [
        (
            Cycle2ToolName.SEARCH_ORDERS,
            1,
            ToolResultOutcome.SYSTEM_FAILURE,
            "ORDER_SEARCH_TRANSIENT",
            {},
            ToolRetryDecision.RETRY_SCHEDULED,
        ),
        (
            Cycle2ToolName.GET_SHIPMENT,
            1,
            ToolResultOutcome.TIMEOUT,
            "TOOL_CALL_TIMEOUT",
            {},
            ToolRetryDecision.RETRY_SCHEDULED,
        ),
        (
            Cycle2ToolName.SEARCH_ORDERS,
            2,
            ToolResultOutcome.SYSTEM_FAILURE,
            "ORDER_SEARCH_TRANSIENT",
            {},
            ToolRetryDecision.MAX_ATTEMPTS_REACHED,
        ),
        (
            Cycle2ToolName.GET_ORDER,
            1,
            ToolResultOutcome.TIMEOUT,
            "TOOL_CALL_TIMEOUT",
            {},
            ToolRetryDecision.MAX_ATTEMPTS_REACHED,
        ),
        (
            Cycle2ToolName.GET_SHIPMENT,
            1,
            ToolResultOutcome.SYSTEM_FAILURE,
            "SHIPMENT_SOURCE_INTEGRITY",
            {},
            ToolRetryDecision.NOT_RETRYABLE,
        ),
        (
            Cycle2ToolName.SEARCH_ORDERS,
            1,
            ToolResultOutcome.SYSTEM_FAILURE,
            "ORDER_SEARCH_TRANSIENT",
            {"remaining_run_time_budget_ms": 0},
            ToolRetryDecision.RUN_BUDGET_EXHAUSTED,
        ),
        (
            Cycle2ToolName.SEARCH_ORDERS,
            1,
            ToolResultOutcome.SYSTEM_FAILURE,
            "ORDER_SEARCH_TRANSIENT",
            {"current_owner_scope_ref": "owner-B"},
            ToolRetryDecision.STATE_OR_BINDING_INVALIDATED,
        ),
    ],
)
def test_cycle2_retry_decision_uses_exact_policy_and_loaded_revalidation(
    tool_name: Cycle2ToolName,
    attempt_no: int,
    outcome: ToolResultOutcome,
    failure_code: str,
    change: dict[str, object],
    expected: ToolRetryDecision,
) -> None:
    decision = decide_cycle2_tool_retry(
        canonical_tool_name=tool_name,
        attempt_no=attempt_no,
        outcome=outcome,
        failure_code=failure_code,
        revalidation=_retry_revalidation(**change),
    )
    assert decision is expected


def test_cycle2_toolcall_preserves_first_failure_after_second_attempt_success() -> None:
    tool_call_id = uuid4()
    first = _attempt_v2(
        tool_call_id=tool_call_id,
        outcome=ToolResultOutcome.TIMEOUT,
        failure_code="TOOL_CALL_TIMEOUT",
        timeout_phase=ToolTimeoutPhase.AFTER_DISPATCH,
        retry_decision=ToolRetryDecision.RETRY_SCHEDULED,
    )
    second = _attempt_v2(
        tool_call_id=tool_call_id,
        attempt_no=2,
        outcome=ToolResultOutcome.SUCCESS,
        retry_decision=ToolRetryDecision.NOT_APPLICABLE,
    )
    record = ToolCallRecordV2(
        **_tool_call_v2_values(tool_call_id=tool_call_id),
        attempt_count=2,
        attempts=(first, second),
        status=ToolCallStatus.SUCCEEDED,
        finished_at=second.finished_at,
        result_ref=uuid4(),
    )

    assert record.attempts[0].timeout_phase is ToolTimeoutPhase.AFTER_DISPATCH
    assert record.attempts[0].retry_decision is ToolRetryDecision.RETRY_SCHEDULED
    assert record.attempts[1].outcome is ToolResultOutcome.SUCCESS
    assert record.failure_code is None
    assert record.timeout_phase is None


def test_cycle2_toolcall_rejects_third_attempt_and_deterministic_retry() -> None:
    with pytest.raises(ValidationError, match="less than or equal to 2"):
        ToolAttemptRecordV2(
            tool_call_id=uuid4(),
            attempt_no=3,
            started_at=NOW,
        )

    tool_call_id = uuid4()
    deterministic_retry = _attempt_v2(
        tool_call_id=tool_call_id,
        outcome=ToolResultOutcome.SYSTEM_FAILURE,
        failure_code="ORDER_SEARCH_SOURCE_INTEGRITY",
        retry_decision=ToolRetryDecision.RETRY_SCHEDULED,
    )
    with pytest.raises(ValidationError, match="deterministic failure"):
        ToolCallRecordV2(
            **_tool_call_v2_values(tool_call_id=tool_call_id),
            attempt_count=1,
            attempts=(deterministic_retry,),
            status=ToolCallStatus.RUNNING,
        )


@pytest.mark.parametrize(
    ("outcome", "failure_code", "timeout_phase", "decision", "status"),
    [
        (
            ToolResultOutcome.SUCCESS,
            None,
            None,
            ToolRetryDecision.NOT_APPLICABLE,
            ToolCallStatus.SUCCEEDED,
        ),
        (
            ToolResultOutcome.SYSTEM_FAILURE,
            "ORDER_SEARCH_UNAVAILABLE",
            None,
            ToolRetryDecision.NOT_RETRYABLE,
            ToolCallStatus.FAILED,
        ),
        (
            ToolResultOutcome.TIMEOUT,
            "TOOL_CALL_TIMEOUT",
            ToolTimeoutPhase.UNKNOWN,
            ToolRetryDecision.MAX_ATTEMPTS_REACHED,
            ToolCallStatus.TIMED_OUT,
        ),
        (
            ToolResultOutcome.INTERRUPTED,
            "RUN_BUDGET_EXHAUSTED",
            None,
            ToolRetryDecision.RUN_BUDGET_EXHAUSTED,
            ToolCallStatus.INTERRUPTED,
        ),
    ],
)
def test_cycle2_terminal_projection_is_exact(
    outcome: ToolResultOutcome,
    failure_code: str | None,
    timeout_phase: ToolTimeoutPhase | None,
    decision: ToolRetryDecision,
    status: ToolCallStatus,
) -> None:
    attempt = _attempt_v2(
        outcome=outcome,
        failure_code=failure_code,
        timeout_phase=timeout_phase,
        retry_decision=decision,
    )
    projection = project_cycle2_tool_terminal(attempt)

    assert isinstance(projection, Cycle2ToolTerminalProjection)
    assert projection.status is status
    if status is ToolCallStatus.FAILED:
        assert projection.failure_code == failure_code
    if status is ToolCallStatus.TIMED_OUT:
        assert projection.timeout_phase is timeout_phase
    if status is ToolCallStatus.INTERRUPTED:
        assert projection.interruption_reason == failure_code


def test_cycle2_recovery_truth_table_grants_only_unfenced_second_attempt() -> None:
    created = ToolCallRecordV2(
        **_tool_call_v2_values(),
        attempt_count=0,
        attempts=(),
        status=ToolCallStatus.CREATED,
    )
    assert decide_cycle2_tool_recovery(
        tool_call=created,
        revalidation=_retry_revalidation(),
        decided_at=NOW,
    ).decision is ToolRecoveryDecision.INTERRUPT_WITHOUT_ATTEMPT

    tool_call_id = uuid4()
    unfinished = _attempt_v2(tool_call_id=tool_call_id)
    running_unfinished = ToolCallRecordV2(
        **_tool_call_v2_values(tool_call_id=tool_call_id),
        attempt_count=1,
        attempts=(unfinished,),
        status=ToolCallStatus.RUNNING,
    )
    assert decide_cycle2_tool_recovery(
        tool_call=running_unfinished,
        revalidation=_retry_revalidation(),
        decided_at=NOW,
    ).decision is ToolRecoveryDecision.INTERRUPT_UNFINISHED_ATTEMPT

    finalized = _attempt_v2(
        tool_call_id=tool_call_id,
        outcome=ToolResultOutcome.SYSTEM_FAILURE,
        failure_code="ORDER_SEARCH_TRANSIENT",
        retry_decision=ToolRetryDecision.RETRY_SCHEDULED,
    )
    before_second_fence = ToolCallRecordV2(
        **_tool_call_v2_values(tool_call_id=tool_call_id),
        attempt_count=1,
        attempts=(finalized,),
        status=ToolCallStatus.RUNNING,
    )
    append = decide_cycle2_tool_recovery(
        tool_call=before_second_fence,
        revalidation=_retry_revalidation(),
        decided_at=NOW,
    )
    assert isinstance(append, ToolRetryRecoveryDecision)
    assert append.decision is ToolRecoveryDecision.APPEND_SECOND_ATTEMPT
    assert append.candidate_next_attempt_no == 2
    assert append.durable_cas_claimed is False

    second_fence = _attempt_v2(tool_call_id=tool_call_id, attempt_no=2)
    after_second_fence = ToolCallRecordV2(
        **_tool_call_v2_values(tool_call_id=tool_call_id),
        attempt_count=2,
        attempts=(finalized, second_fence),
        status=ToolCallStatus.RUNNING,
    )
    decision = decide_cycle2_tool_recovery(
        tool_call=after_second_fence,
        revalidation=_retry_revalidation(),
        decided_at=NOW,
    )
    assert decision.decision is ToolRecoveryDecision.INTERRUPT_UNFINISHED_ATTEMPT
    assert decision.candidate_next_attempt_no is None


def test_cycle2_recovery_unknown_or_contradictory_shape_fails_closed() -> None:
    contradictory = ToolCallRecordV2.model_construct(
        **_tool_call_v2_values(),
        attempt_count=0,
        attempts=(),
        status=ToolCallStatus.SUCCEEDED,
        finished_at=None,
    )
    decision = decide_cycle2_tool_recovery(
        tool_call=contradictory,
        revalidation=_retry_revalidation(),
        decided_at=NOW,
    )

    assert decision.decision is ToolRecoveryDecision.FAIL_CLOSED
    assert decision.candidate_next_attempt_no is None
    assert decision.durable_cas_claimed is False


def test_cycle2_recovery_revalidation_failure_terminates_without_append() -> None:
    tool_call_id = uuid4()
    finalized = _attempt_v2(
        tool_call_id=tool_call_id,
        outcome=ToolResultOutcome.SYSTEM_FAILURE,
        failure_code="ORDER_SEARCH_TRANSIENT",
        retry_decision=ToolRetryDecision.RETRY_SCHEDULED,
    )
    before_second_fence = ToolCallRecordV2(
        **_tool_call_v2_values(tool_call_id=tool_call_id),
        attempt_count=1,
        attempts=(finalized,),
        status=ToolCallStatus.RUNNING,
    )

    decision = decide_cycle2_tool_recovery(
        tool_call=before_second_fence,
        revalidation=_retry_revalidation(current_owner_scope_ref="owner-B"),
        decided_at=NOW,
    )

    assert decision.decision is ToolRecoveryDecision.TERMINATE_RETRY_PATH
    assert decision.stable_reason_code == "STATE_OR_BINDING_INVALIDATED"
    assert decision.candidate_next_attempt_no is None
    assert decision.durable_cas_claimed is False


def test_cycle2_recovery_already_terminal_has_no_executable_authority() -> None:
    tool_call_id = uuid4()
    failure = _attempt_v2(
        tool_call_id=tool_call_id,
        outcome=ToolResultOutcome.SYSTEM_FAILURE,
        failure_code="ORDER_SEARCH_UNAVAILABLE",
        retry_decision=ToolRetryDecision.NOT_RETRYABLE,
    )
    terminal = ToolCallRecordV2(
        **_tool_call_v2_values(tool_call_id=tool_call_id),
        attempt_count=1,
        attempts=(failure,),
        status=ToolCallStatus.FAILED,
        finished_at=failure.finished_at,
        failure_code="ORDER_SEARCH_UNAVAILABLE",
    )

    decision = decide_cycle2_tool_recovery(
        tool_call=terminal,
        revalidation=_retry_revalidation(),
        decided_at=NOW,
    )

    assert decision.decision is ToolRecoveryDecision.NO_ACTION_TERMINAL
    assert decision.candidate_next_attempt_no is None


def test_cycle2_v2_allows_interrupted_created_call_without_fake_attempt() -> None:
    record = ToolCallRecordV2(
        **_tool_call_v2_values(),
        attempt_count=0,
        attempts=(),
        status=ToolCallStatus.INTERRUPTED,
        finished_at=NOW,
        interruption_reason="PROCESS_RESTART_DETECTED",
    )

    assert record.attempts == ()
    assert record.attempt_count == 0
    assert record.interruption_reason == "PROCESS_RESTART_DETECTED"
