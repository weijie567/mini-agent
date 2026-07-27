from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from mini_agent.core.control_gateway import evaluate_control_gateway
from mini_agent.core.identity import CustomerContext
from mini_agent.core.memory import ContextManifest, TokenCounts
from mini_agent.core.request_processing import (
    InitialRequestDecision,
    revalidate_next_move,
    validate_and_reduce_initial_request,
)
from mini_agent.core.request_understanding import (
    InputAuthority,
    InputCandidate,
    InputSourceKind,
    NextMove,
    NextMoveKind,
    RequestUnderstandingOutput,
    TaskDeltaCandidate,
    TaskDeltaOperation,
)
from mini_agent.core.task_state import TaskStatus
from mini_agent.core.tool_system import (
    ExecutionPolicy,
    GateDecisionValue,
    GateReasonCode,
    RegistrySnapshot,
    ToolSpec,
    ToolEffect,
    ToolRegistration,
    compute_model_visible_toolset_hash,
    get_order_tool_spec,
)

NOW = datetime(2030, 1, 1, tzinfo=UTC)


def _context(customer_id: str = "customer-A") -> CustomerContext:
    return CustomerContext(
        subject_ref="subject-A",
        customer_id=customer_id,
        auth_scopes=frozenset({"orders:read"}),
        authenticated_at=NOW,
        session_ref_hash="sha256:session-A",
    )


def _snapshot(
    *,
    effect: ToolEffect = ToolEffect.READ,
    provider_name: str = "get_order",
    version: str = "runtime-tools-v1",
) -> RegistrySnapshot:
    return RegistrySnapshot.build(
        tool_registry_version=version,
        registrations=(
            ToolRegistration(
                tool_spec=get_order_tool_spec(),
                provider_visible_name=provider_name,
                effect=effect,
                risk="LOW",
                idempotency="READ_ONLY",
                unknown_result_recovery=(
                    "RECONCILE_ACTION" if effect is ToolEffect.ACTION else None
                ),
                handler_ref="orders.get_order",
                execution_policy=ExecutionPolicy(
                    timeout_ms=500,
                    max_attempts=1,
                    interrupt_behavior="MARK_INTERRUPTED",
                ),
            ),
        ),
    )


def _snapshot_with_provider_schema_drift() -> RegistrySnapshot:
    snapshot = _snapshot()
    canonical_spec = get_order_tool_spec()
    drifted_visible_spec = ToolSpec(
        name="get_order",
        description=canonical_spec.description,
        input_schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "order_ref": {
                    "type": "string",
                    "pattern": r"^O-[0-9]{4,20}$",
                }
            },
            "required": ["order_ref"],
        },
        output_schema=canonical_spec.output_schema,
    )
    return RegistrySnapshot(
        tool_registry_version=snapshot.tool_registry_version,
        canonical_registrations=snapshot.canonical_registrations,
        provider_visible_toolset=(drifted_visible_spec,),
        provider_name_to_canonical_name=(
            snapshot.provider_name_to_canonical_name
        ),
        model_visible_toolset_hash=compute_model_visible_toolset_hash(
            (drifted_visible_spec,)
        ),
    )


def _decision(
    *,
    bound_order_id: str = "O-1001",
    proposed_order_id: object = "O-1001",
    requested_tool_name: str = "get_order",
) -> InitialRequestDecision:
    message_ref = uuid4()
    output = RequestUnderstandingOutput(
        message_ref=message_ref,
        task_delta_candidates=(
            TaskDeltaCandidate(
                candidate_id=uuid4(),
                operation=TaskDeltaOperation.ADD_GOAL,
                goal_patch="查询当前消息中的订单状态",
                input_candidates=(
                    InputCandidate(
                        name="order_id",
                        candidate_value=bound_order_id,
                        semantic_role="TARGET_RESOURCE_IDENTIFIER",
                        authority=InputAuthority.USER_CLAIM,
                        source_kind=InputSourceKind.CURRENT_MESSAGE,
                        source_ref=message_ref,
                        source_quote=f"订单 {bound_order_id}",
                        confidence=0.99,
                    ),
                ),
                confidence=0.98,
            ),
        ),
        next_move_candidate=NextMove(
            kind=NextMoveKind.CALL_TOOL,
            requested_tool_name=requested_tool_name,
            arguments={"order_id": proposed_order_id},
            base_task_state_version=None,
        ),
    )
    return validate_and_reduce_initial_request(
        output=output,
        current_message_ref=message_ref,
        current_message=f"请查询订单 {bound_order_id}",
        customer_context=_context(),
        run_id=uuid4(),
        accepted_delta_id=uuid4(),
        task_id=uuid4(),
        request_unit_id=uuid4(),
        binding_id=uuid4(),
        next_move_candidate_ref=uuid4(),
        now=NOW,
    )


def _manifest(
    *,
    snapshot: RegistrySnapshot,
    run_id: UUID,
    model_call_id: UUID,
    context_manifest_id: UUID,
) -> ContextManifest:
    return ContextManifest(
        context_manifest_id=context_manifest_id,
        run_id=run_id,
        model_call_id=model_call_id,
        tool_registry_version=snapshot.tool_registry_version,
        model_visible_toolset_hash=snapshot.model_visible_toolset_hash,
        selected_message_refs=(uuid4(),),
        redaction_policy_version="redaction-v1",
        token_counts=TokenCounts(input_tokens=None, output_tokens=None),
        assembled_at=NOW,
    )


def _evaluate(
    decision: InitialRequestDecision,
    *,
    snapshot: RegistrySnapshot | None = None,
    customer_context: CustomerContext | None = None,
    current_task: object | None = None,
    current_request_unit: object | None = None,
    tool_calls_used: int = 0,
    progress_valid: bool = True,
):
    actual_snapshot = snapshot or _snapshot()
    model_call_id = uuid4()
    context_manifest_id = uuid4()
    manifest = _manifest(
        snapshot=actual_snapshot,
        run_id=decision.request_understanding.run_id,
        model_call_id=model_call_id,
        context_manifest_id=context_manifest_id,
    )
    move = revalidate_next_move(
        decision=decision,
        current_task=decision.task,
        current_request_unit=decision.request_unit,
        current_input_binding=decision.input_binding,
    )
    gate = evaluate_control_gateway(
        revalidated_move=move,
        customer_context=customer_context or _context(),
        current_task=current_task or decision.task,
        current_request_unit=current_request_unit or decision.request_unit,
        current_input_binding=decision.input_binding,
        registry_snapshot=actual_snapshot,
        context_manifest=manifest,
        gate_decision_id=uuid4(),
        model_call_id=model_call_id,
        provider_tool_call_id="provider-call-1",
        decided_at=NOW,
        tool_calls_used=tool_calls_used,
        max_tool_calls=1,
        progress_valid=progress_valid,
    )
    return gate


def test_exact_bound_get_order_candidate_is_approved() -> None:
    decision = _decision()

    gate = _evaluate(decision)

    assert gate.decision is GateDecisionValue.ACCEPT
    assert gate.reason_code is None
    assert gate.resolved_canonical_tool_name == "get_order"
    assert gate.argument_binding_refs == (decision.input_binding.binding_id,)
    assert gate.validated_task_state_version == 1
    assert "tool_call_id" not in type(gate).model_fields
    assert "order_number" not in type(gate).model_fields


def test_provider_visible_schema_must_match_registration_projection() -> None:
    decision = _decision()
    snapshot = _snapshot_with_provider_schema_drift()

    gate = _evaluate(decision, snapshot=snapshot)

    assert (
        snapshot.provider_visible_toolset[0].input_schema["required"]
        == ("order_ref",)
    )
    assert gate.decision is GateDecisionValue.REJECT
    assert gate.reason_code is GateReasonCode.SCHEMA_INVALID
    assert gate.schema_valid is False
    assert "tool_call_id" not in type(gate).model_fields


@pytest.mark.parametrize("replacement", ["O-2001", "O-9999"])
def test_provider_argument_replacement_is_rejected_before_toolcall(
    replacement: str,
) -> None:
    decision = _decision(proposed_order_id=replacement)

    gate = _evaluate(decision)

    assert gate.decision is GateDecisionValue.REJECT
    assert gate.reason_code is GateReasonCode.ARGUMENT_BINDING_MISMATCH
    assert gate.argument_binding_valid is False
    assert gate.argument_binding_refs == (decision.input_binding.binding_id,)
    assert "tool_call_id" not in type(gate).model_fields


def test_unknown_tool_is_rejected_without_authorized_execution_identity() -> None:
    decision = _decision(requested_tool_name="delete_order")

    gate = _evaluate(decision)

    assert gate.decision is GateDecisionValue.REJECT
    assert gate.reason_code is GateReasonCode.TOOL_NOT_REGISTERED
    assert gate.registration_valid is False
    assert gate.resolved_canonical_tool_name is None
    assert "tool_call_id" not in type(gate).model_fields


@pytest.mark.parametrize(
    ("case", "expected_reason"),
    [
        ("snapshot-version", GateReasonCode.SNAPSHOT_MISMATCH),
        ("schema-extra", GateReasonCode.SCHEMA_INVALID),
        ("action-effect", GateReasonCode.ACTION_REQUIRES_PROPOSAL),
        ("budget", GateReasonCode.BUDGET_EXCEEDED),
        ("progress", GateReasonCode.NO_PROGRESS),
        ("inactive", GateReasonCode.STATE_VERSION_MISMATCH),
        ("owner", GateReasonCode.STATE_VERSION_MISMATCH),
        ("binding-ref", GateReasonCode.ARGUMENT_BINDING_MISMATCH),
    ],
)
def test_gateway_revalidates_every_fail_closed_boundary(
    case: str,
    expected_reason: GateReasonCode,
) -> None:
    decision = _decision()
    snapshot = _snapshot()
    model_call_id = uuid4()
    context_manifest_id = uuid4()
    manifest = _manifest(
        snapshot=snapshot,
        run_id=decision.request_understanding.run_id,
        model_call_id=model_call_id,
        context_manifest_id=context_manifest_id,
    )
    move = revalidate_next_move(
        decision=decision,
        current_task=decision.task,
        current_request_unit=decision.request_unit,
        current_input_binding=decision.input_binding,
    )
    task = decision.task
    request_unit = decision.request_unit
    tool_calls_used = 0
    progress_valid = True

    if case == "snapshot-version":
        manifest = manifest.model_copy(
            update={"tool_registry_version": "different-runtime-tools-v1"}
        )
    elif case == "schema-extra":
        move = move.model_copy(
            update={
                "candidate_arguments": {
                    "order_id": "O-1001",
                    "unexpected": "value",
                }
            }
        )
    elif case == "action-effect":
        snapshot = _snapshot(effect=ToolEffect.ACTION)
        manifest = _manifest(
            snapshot=snapshot,
            run_id=decision.request_understanding.run_id,
            model_call_id=model_call_id,
            context_manifest_id=context_manifest_id,
        )
    elif case == "budget":
        tool_calls_used = 1
    elif case == "progress":
        progress_valid = False
    elif case == "inactive":
        task = task.model_copy(update={"status": TaskStatus.BLOCKED})
        request_unit = request_unit.model_copy(update={"status": TaskStatus.BLOCKED})
    elif case == "owner":
        task = task.model_copy(update={"owner_customer_id": "customer-B"})
    elif case == "binding-ref":
        request_unit = request_unit.model_copy(
            update={"input_binding_refs": (uuid4(),)}
        )

    gate = evaluate_control_gateway(
        revalidated_move=move,
        customer_context=_context(),
        current_task=task,
        current_request_unit=request_unit,
        current_input_binding=decision.input_binding,
        registry_snapshot=snapshot,
        context_manifest=manifest,
        gate_decision_id=uuid4(),
        model_call_id=model_call_id,
        provider_tool_call_id=None,
        decided_at=NOW,
        tool_calls_used=tool_calls_used,
        max_tool_calls=1,
        progress_valid=progress_valid,
    )

    assert gate.decision is GateDecisionValue.REJECT
    assert gate.reason_code is expected_reason
    assert "tool_call_id" not in type(gate).model_fields


def test_stale_revalidated_v1_against_current_v2_is_rejected() -> None:
    decision = _decision()
    current_task = decision.task.model_copy(
        update={"state_version": 2, "status": TaskStatus.WAITING_USER}
    )
    current_request_unit = decision.request_unit.model_copy(
        update={"state_version": 2, "status": TaskStatus.WAITING_USER}
    )

    gate = _evaluate(
        decision,
        current_task=current_task,
        current_request_unit=current_request_unit,
    )

    assert gate.decision is GateDecisionValue.REJECT
    assert gate.reason_code is GateReasonCode.STATE_VERSION_MISMATCH
    assert gate.validated_task_state_version == 1
    assert gate.state_version_valid is False


def test_bypassed_raw_and_normalized_candidate_drift_fails_closed() -> None:
    decision = _decision()
    snapshot = _snapshot()
    model_call_id = uuid4()
    context_manifest_id = uuid4()
    manifest = _manifest(
        snapshot=snapshot,
        run_id=decision.request_understanding.run_id,
        model_call_id=model_call_id,
        context_manifest_id=context_manifest_id,
    )
    move = revalidate_next_move(
        decision=decision,
        current_task=decision.task,
        current_request_unit=decision.request_unit,
        current_input_binding=decision.input_binding,
    ).model_copy(
        update={"candidate_arguments": {"order_id": "O-2001"}}
    )

    gate = evaluate_control_gateway(
        revalidated_move=move,
        customer_context=_context(),
        current_task=decision.task,
        current_request_unit=decision.request_unit,
        current_input_binding=decision.input_binding,
        registry_snapshot=snapshot,
        context_manifest=manifest,
        gate_decision_id=uuid4(),
        model_call_id=model_call_id,
        provider_tool_call_id=None,
        decided_at=NOW,
        tool_calls_used=0,
        max_tool_calls=1,
        progress_valid=True,
    )

    assert gate.decision is GateDecisionValue.REJECT
    assert gate.reason_code is GateReasonCode.SCHEMA_INVALID
    assert gate.schema_valid is False
    assert "tool_call_id" not in type(gate).model_fields


def test_gateway_modules_are_pure_core_without_outer_layer_imports() -> None:
    import mini_agent.core.control_gateway as control_gateway
    import mini_agent.core.request_processing as request_processing

    source = (
        request_processing.__loader__.get_source(request_processing.__name__)
        + control_gateway.__loader__.get_source(control_gateway.__name__)
    )

    assert "mini_agent.application" not in source
    assert "mini_agent.infrastructure" not in source
    assert "mini_agent.evaluation" not in source
