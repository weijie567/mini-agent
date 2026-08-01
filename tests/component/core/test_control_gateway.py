from collections.abc import Mapping
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel, ValidationError, create_model

from mini_agent.core.common import (
    FrozenJsonDict,
    RuntimePrivateModel,
    freeze_json_value,
)
from mini_agent.core.control_gateway import (
    Cycle2AcceptedBindingFacts,
    Cycle2GatewayBudgetFacts,
    Cycle2GatewayCandidate,
    Cycle2GatewayLoadedClosure,
    Cycle2GatewayProgressSnapshot,
    Cycle2TargetObservationFacts,
    Cycle2ToolProgressFact,
    Cycle2VerifiedOrderTargetFacts,
    build_cycle2_authorized_tool_command,
    evaluate_control_gateway,
    evaluate_cycle2_control_gateway,
)
from mini_agent.core.identity import CustomerContext
from mini_agent.core.memory import (
    ContextManifest,
    TaskStateRefAndVersion,
    TokenCounts,
    VersionedRecordRef,
)
from mini_agent.core.request_processing import (
    InitialRequestRoutableTaskGraphDecisionV2,
    InitialTaskIdentityAllocationV2,
    revalidate_next_move_v2,
    validate_and_reduce_initial_request_v2,
)
from mini_agent.core.request_understanding import (
    InputAuthority,
    InputCandidate,
    InputSourceKind,
    NextMove,
    NextMoveKind,
    QueryContextualizationCandidateV2,
    ReferenceSourceKindV2,
    RequestUnderstandingInput,
    RequestUnderstandingOutputV2,
    ResolvedReferenceCandidateV2,
    TaskDeltaCandidate,
    TaskDeltaOperation,
)
from mini_agent.core.task_state import TaskStatus
from mini_agent.core.tool_system import (
    AuthorizedToolCommandV2,
    Cycle2ToolName,
    ExecutionPolicy,
    GateDecisionV2,
    GateDecisionValue,
    GateReasonCode,
    RegistrySnapshot,
    ToolSpec,
    ToolEffect,
    ToolRegistration,
    build_cycle2_registry_snapshot,
    compute_model_visible_toolset_hash,
    get_order_tool_spec,
)

NOW = datetime(2030, 1, 1, tzinfo=UTC)


def _context(customer_id: str = "customer-A") -> CustomerContext:
    return CustomerContext(
        provenance="SERVER_AUTH_ADAPTER",
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
) -> InitialRequestRoutableTaskGraphDecisionV2:
    message_ref = uuid4()
    run_id = uuid4()
    candidate_id = uuid4()
    message = f"请查询订单 {bound_order_id}"
    tool_spec = get_order_tool_spec()
    request_input = RequestUnderstandingInput(
        schema_version="e2e01-thin-v1",
        run_id=run_id,
        message_ref=message_ref,
        original_query=message,
        provider_visible_tool_specs=(tool_spec,),
        model_visible_toolset_hash=compute_model_visible_toolset_hash(
            (tool_spec,)
        ),
    )
    output = RequestUnderstandingOutputV2(
        schema_version="e2e01-thin-v2",
        message_ref=message_ref,
        contextualization=QueryContextualizationCandidateV2(
            text=message,
            resolved_reference_candidates=(
                ResolvedReferenceCandidateV2(
                    name="order_id",
                    candidate_value=bound_order_id,
                    source_kind=ReferenceSourceKindV2.CURRENT_MESSAGE,
                    source_ref=message_ref,
                    source_quote=bound_order_id,
                    confidence=0.99,
                ),
            ),
            uncertainties=(),
            source_message_refs=(message_ref,),
        ),
        task_delta_candidates=(
            TaskDeltaCandidate(
                candidate_id=candidate_id,
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
    decision = validate_and_reduce_initial_request_v2(
        request_input=request_input,
        output=output,
        authoritative_messages={message_ref: message},
        customer_context=_context(),
        request_understanding_record_id=uuid4(),
        candidate_identity_allocations=(
            InitialTaskIdentityAllocationV2(
                candidate_ref=candidate_id,
                accepted_delta_id=uuid4(),
                task_id=uuid4(),
                request_unit_id=uuid4(),
                binding_id=uuid4(),
            ),
        ),
        next_move_candidate_ref=uuid4(),
        now=NOW,
    )
    assert type(decision) is InitialRequestRoutableTaskGraphDecisionV2
    return decision


def _manifest(
    *,
    snapshot: RegistrySnapshot,
    run_id: UUID,
    model_call_id: UUID,
    context_manifest_id: UUID,
    observation_refs_and_versions: tuple[VersionedRecordRef, ...] = (),
) -> ContextManifest:
    return ContextManifest(
        context_manifest_id=context_manifest_id,
        run_id=run_id,
        model_call_id=model_call_id,
        tool_registry_version=snapshot.tool_registry_version,
        model_visible_toolset_hash=snapshot.model_visible_toolset_hash,
        selected_message_refs=(uuid4(),),
        task_state_ref_and_version=None,
        observation_refs_and_versions=observation_refs_and_versions,
        evidence_refs_and_versions=(),
        action_record_refs=(),
        redaction_policy_version="redaction-v1",
        truncation_decisions=(),
        token_counts=TokenCounts(input_tokens=None, output_tokens=None),
        assembled_at=NOW,
    )


def _evaluate(
    decision: InitialRequestRoutableTaskGraphDecisionV2,
    *,
    snapshot: RegistrySnapshot | None = None,
    customer_context: CustomerContext | None = None,
    current_task: object | None = None,
    current_request_unit: object | None = None,
    tool_calls_used: int = 0,
    progress_valid: bool = True,
):
    actual_snapshot = snapshot or _snapshot()
    task_graph = decision.task_graph
    model_call_id = uuid4()
    context_manifest_id = uuid4()
    manifest = _manifest(
        snapshot=actual_snapshot,
        run_id=decision.closure.record.run_id,
        model_call_id=model_call_id,
        context_manifest_id=context_manifest_id,
    )
    move = revalidate_next_move_v2(
        decision=decision,
        current_task=task_graph.task,
        current_request_unit=task_graph.request_unit,
        current_input_binding=task_graph.input_binding,
    )
    gate = evaluate_control_gateway(
        revalidated_move=move,
        customer_context=customer_context or _context(),
        current_task=current_task or task_graph.task,
        current_request_unit=current_request_unit or task_graph.request_unit,
        current_input_binding=task_graph.input_binding,
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
    assert gate.argument_binding_refs == (
        decision.task_graph.input_binding.binding_id,
    )
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
    assert gate.argument_binding_refs == (
        decision.task_graph.input_binding.binding_id,
    )
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
    task_graph = decision.task_graph
    snapshot = _snapshot()
    model_call_id = uuid4()
    context_manifest_id = uuid4()
    manifest = _manifest(
        snapshot=snapshot,
        run_id=decision.closure.record.run_id,
        model_call_id=model_call_id,
        context_manifest_id=context_manifest_id,
    )
    move = revalidate_next_move_v2(
        decision=decision,
        current_task=task_graph.task,
        current_request_unit=task_graph.request_unit,
        current_input_binding=task_graph.input_binding,
    )
    task = task_graph.task
    request_unit = task_graph.request_unit
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
            run_id=decision.closure.record.run_id,
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
        current_input_binding=task_graph.input_binding,
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


def test_stale_state_version_one_against_current_v2_is_rejected() -> None:
    decision = _decision()
    current_task = decision.task_graph.task.model_copy(
        update={"state_version": 2, "status": TaskStatus.WAITING_USER}
    )
    current_request_unit = decision.task_graph.request_unit.model_copy(
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
    task_graph = decision.task_graph
    snapshot = _snapshot()
    model_call_id = uuid4()
    context_manifest_id = uuid4()
    manifest = _manifest(
        snapshot=snapshot,
        run_id=decision.closure.record.run_id,
        model_call_id=model_call_id,
        context_manifest_id=context_manifest_id,
    )
    move = revalidate_next_move_v2(
        decision=decision,
        current_task=task_graph.task,
        current_request_unit=task_graph.request_unit,
        current_input_binding=task_graph.input_binding,
    ).model_copy(
        update={"candidate_arguments": {"order_id": "O-2001"}}
    )

    gate = evaluate_control_gateway(
        revalidated_move=move,
        customer_context=_context(),
        current_task=task_graph.task,
        current_request_unit=task_graph.request_unit,
        current_input_binding=task_graph.input_binding,
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


def _cycle2_gateway_case(
    tool_name: Cycle2ToolName,
    *,
    binding_authority: InputAuthority = InputAuthority.USER_CLAIM,
    selected_get_order: bool = False,
) -> tuple[Cycle2GatewayCandidate, Cycle2GatewayLoadedClosure]:
    decision = _decision()
    task = decision.task_graph.task.model_copy(
        update={
            "last_outcome_ref": decision.task_graph.task.last_outcome_ref,
        }
    )
    request_unit = decision.task_graph.request_unit.model_copy(
        update={
            field_name: decision.task_graph.request_unit.__dict__[field_name]
            for field_name, field in type(
                decision.task_graph.request_unit
            ).model_fields.items()
            if not field.is_required()
        }
    )
    binding_id = uuid4()
    model_call_id = uuid4()
    context_manifest_id = uuid4()
    snapshot = build_cycle2_registry_snapshot()
    if selected_get_order and tool_name is not Cycle2ToolName.GET_ORDER:
        raise ValueError("selected_get_order is only valid for get_order")
    if tool_name is Cycle2ToolName.SEARCH_ORDERS:
        binding_name = "product_description"
        normalized_value = "跑鞋"
        arguments = {"product_description": normalized_value}
    elif selected_get_order:
        binding_name = "candidate_ordinal"
        normalized_value = 2
        arguments = {"order_id": "O-1001"}
    else:
        binding_name = "order_id"
        normalized_value = "O-1001"
        arguments = {"order_id": normalized_value}

    binding = Cycle2AcceptedBindingFacts(
        binding_id=binding_id,
        private_owner_scope_ref="owner-scope-A",
        owner_customer_id="customer-A",
        task_id=task.task_id,
        request_unit_id=request_unit.request_unit_id,
        task_state_version=task.state_version,
        name=binding_name,
        normalized_value=normalized_value,
        authority=InputAuthority.USER_CLAIM,
        validation_status="ACCEPTED",
        confirmed_by_user=True,
        source_refs=(uuid4(),),
        superseded_by=None,
    )
    if binding_authority is not InputAuthority.USER_CLAIM:
        binding = binding.model_copy(update={"authority": binding_authority})
    request_unit = request_unit.model_copy(
        update={"input_binding_refs": (binding_id,)}
    )

    target_ref = uuid4()
    verified_targets: tuple[Cycle2VerifiedOrderTargetFacts, ...] = ()
    target_observations: tuple[Cycle2TargetObservationFacts, ...] = ()
    manifest_observation_refs: tuple[VersionedRecordRef, ...] = ()
    candidate_refs = (binding_id,)
    candidate_target_ref = None
    if tool_name is Cycle2ToolName.GET_SHIPMENT or selected_get_order:
        source_observation_ref = uuid4()
        source_observation_version = "shipment-observation-v1"
        verified_targets = (
            Cycle2VerifiedOrderTargetFacts(
                verified_target_ref=target_ref,
                private_owner_scope_ref="owner-scope-A",
                owner_customer_id="customer-A",
                task_id=task.task_id,
                request_unit_id=request_unit.request_unit_id,
                task_state_version=task.state_version,
                order_id="O-1001",
                source_observation_ref=source_observation_ref,
                source_observation_version=source_observation_version,
                input_binding_refs=(binding_id,),
                superseded_by=None,
            ),
        )
        target_observations = (
            Cycle2TargetObservationFacts(
                observation_ref=source_observation_ref,
                observation_version=source_observation_version,
                private_owner_scope_ref="owner-scope-A",
                owner_customer_id="customer-A",
                task_id=task.task_id,
                request_unit_id=request_unit.request_unit_id,
                task_state_version=task.state_version,
                verified_target_ref=target_ref,
                input_binding_refs=(binding_id,),
                superseded_by=None,
            ),
        )
        request_unit = request_unit.model_copy(
            update={"observation_refs": (source_observation_ref,)}
        )
        manifest_observation_refs = (
            VersionedRecordRef(
                record_ref=source_observation_ref,
                version=source_observation_version,
            ),
        )
        candidate_refs = (binding_id,)
        candidate_target_ref = target_ref

    manifest = _manifest(
        snapshot=snapshot,
        run_id=decision.closure.record.run_id,
        model_call_id=model_call_id,
        context_manifest_id=context_manifest_id,
        observation_refs_and_versions=manifest_observation_refs,
    )
    candidate = Cycle2GatewayCandidate(
        run_id=decision.closure.record.run_id,
        task_id=task.task_id,
        request_unit_id=request_unit.request_unit_id,
        model_call_id=model_call_id,
        context_manifest_id=context_manifest_id,
        requested_provider_tool_name=tool_name.value,
        candidate_arguments=arguments,
        proposed_base_task_state_version=None,
        validated_task_state_version=task.state_version,
        argument_binding_refs=candidate_refs,
        verified_target_ref=candidate_target_ref,
    )
    loaded = Cycle2GatewayLoadedClosure(
        customer_context=_context(),
        private_owner_scope_ref="owner-scope-A",
        current_task=task,
        current_request_unit=request_unit,
        current_input_bindings=(binding,),
        current_verified_order_targets=verified_targets,
        current_target_observations=target_observations,
        registry_snapshot=snapshot,
        context_manifest=manifest,
        budget=Cycle2GatewayBudgetFacts(
            run_id=decision.closure.record.run_id,
            context_manifest_id=context_manifest_id,
            tool_registry_version=snapshot.tool_registry_version,
            model_visible_toolset_hash=snapshot.model_visible_toolset_hash,
            closure_complete=True,
            tool_calls_used=0,
            max_tool_calls=3,
            active_tool_calls=0,
            accepted_parallel_tool_calls=0,
            remaining_run_time_budget_ms=1500,
        ),
        progress_snapshot=Cycle2GatewayProgressSnapshot(
            run_id=decision.closure.record.run_id,
            context_manifest_id=context_manifest_id,
            tool_registry_version=snapshot.tool_registry_version,
            model_visible_toolset_hash=snapshot.model_visible_toolset_hash,
            task_state_version=task.state_version,
            history_complete=True,
            prior_tool_steps=(),
        ),
    )
    return candidate, loaded


def _evaluate_cycle2(
    candidate: Cycle2GatewayCandidate,
    loaded: Cycle2GatewayLoadedClosure,
):
    return evaluate_cycle2_control_gateway(
        candidate=candidate,
        loaded_closure=loaded,
        gate_decision_id=uuid4(),
        provider_tool_call_id="provider-cycle2-call",
        decided_at=NOW,
    )


def _foreign_shadow_model(model: BaseModel) -> BaseModel:
    shadow_type = create_model(
        f"Foreign{type(model).__name__}",
        __base__=RuntimePrivateModel,
        **{
            field_name: (field.annotation, ...)
            for field_name, field in type(model).model_fields.items()
        },
    )
    return shadow_type.model_validate(model.model_dump(), strict=True)


@pytest.mark.parametrize(
    ("tool_name", "selected_get_order"),
    [
        (Cycle2ToolName.SEARCH_ORDERS, False),
        (Cycle2ToolName.GET_ORDER, False),
        (Cycle2ToolName.GET_ORDER, True),
        (Cycle2ToolName.GET_SHIPMENT, False),
    ],
)
def test_cycle2_gateway_accepts_four_distinct_typed_binding_paths(
    tool_name: Cycle2ToolName,
    selected_get_order: bool,
) -> None:
    candidate, loaded = _cycle2_gateway_case(
        tool_name,
        selected_get_order=selected_get_order,
    )

    gate = _evaluate_cycle2(candidate, loaded)

    assert gate.decision is GateDecisionValue.ACCEPT
    assert gate.reason_code is None
    assert gate.resolved_canonical_tool_name == tool_name.value
    assert gate.argument_binding_refs == candidate.argument_binding_refs
    assert "tool_call_id" not in type(gate).model_fields
    assert "authorized_tool_command" not in type(gate).model_fields
    assert isinstance(gate, GateDecisionV2)
    assert gate.verified_target_ref == candidate.verified_target_ref
    if tool_name is Cycle2ToolName.GET_ORDER and not selected_get_order:
        assert loaded.current_verified_order_targets == ()
        assert loaded.current_input_bindings[0].authority is InputAuthority.USER_CLAIM
        assert candidate.verified_target_ref is None
    elif tool_name is Cycle2ToolName.GET_SHIPMENT or selected_get_order:
        assert candidate.verified_target_ref is not None
        assert candidate.verified_target_ref not in candidate.argument_binding_refs


@pytest.mark.parametrize(
    ("tool_name", "selected_get_order"),
    [
        (Cycle2ToolName.SEARCH_ORDERS, False),
        (Cycle2ToolName.GET_ORDER, False),
        (Cycle2ToolName.GET_ORDER, True),
        (Cycle2ToolName.GET_SHIPMENT, False),
    ],
)
def test_cycle2_accepted_gate_builds_exact_target_preserving_command(
    tool_name: Cycle2ToolName,
    selected_get_order: bool,
) -> None:
    candidate, loaded = _cycle2_gateway_case(
        tool_name,
        selected_get_order=selected_get_order,
    )
    gate = _evaluate_cycle2(candidate, loaded)

    command = build_cycle2_authorized_tool_command(
        gate_decision=gate,
        candidate=candidate,
        registry_snapshot_ref="cycle2-snapshot-ref",
        trusted_context_ref="cycle2-trusted-context-ref",
    )

    assert isinstance(command, AuthorizedToolCommandV2)
    assert command.gate_decision_id == gate.gate_decision_id
    assert command.canonical_tool_name == gate.resolved_canonical_tool_name
    assert gate.validated_arguments == candidate.candidate_arguments
    assert command.model_dump(mode="json")["validated_arguments"] == dict(
        gate.validated_arguments
    )
    assert command.argument_binding_refs == gate.argument_binding_refs
    assert command.validated_task_state_version == gate.validated_task_state_version
    assert command.verified_target_ref == gate.verified_target_ref
    if command.verified_target_ref is not None:
        assert command.verified_target_ref not in command.argument_binding_refs


def test_cycle2_rejected_or_mismatched_gate_cannot_form_command() -> None:
    candidate, loaded = _cycle2_gateway_case(
        Cycle2ToolName.GET_ORDER,
        selected_get_order=True,
    )
    rejected = _evaluate_cycle2(
        candidate.model_copy(update={"verified_target_ref": uuid4()}),
        loaded,
    )
    assert rejected.decision is GateDecisionValue.REJECT
    assert rejected.verified_target_ref is None
    assert rejected.validated_arguments is None

    with pytest.raises(ValueError, match="Gate and revalidated candidate do not match"):
        build_cycle2_authorized_tool_command(
            gate_decision=rejected,
            candidate=candidate,
            registry_snapshot_ref="cycle2-snapshot-ref",
            trusted_context_ref="cycle2-trusted-context-ref",
        )

    accepted = _evaluate_cycle2(candidate, loaded)
    with pytest.raises(ValueError, match="Gate and revalidated candidate do not match"):
        build_cycle2_authorized_tool_command(
            gate_decision=accepted,
            candidate=candidate.model_copy(update={"verified_target_ref": uuid4()}),
            registry_snapshot_ref="cycle2-snapshot-ref",
            trusted_context_ref="cycle2-trusted-context-ref",
        )


@pytest.mark.parametrize(
    ("tool_name", "selected_get_order", "drifted_arguments"),
    [
        (Cycle2ToolName.GET_ORDER, True, {"order_id": "O-9999"}),
        (
            Cycle2ToolName.SEARCH_ORDERS,
            False,
            {"product_description": "另一双鞋"},
        ),
    ],
)
def test_cycle2_command_rejects_post_gate_argument_drift(
    tool_name: Cycle2ToolName,
    selected_get_order: bool,
    drifted_arguments: dict[str, str],
) -> None:
    candidate, loaded = _cycle2_gateway_case(
        tool_name,
        selected_get_order=selected_get_order,
    )
    gate = _evaluate_cycle2(candidate, loaded)
    gated_arguments = gate.model_dump(mode="json")["validated_arguments"]
    drifted_candidate = candidate.model_copy(
        update={"candidate_arguments": drifted_arguments}
    )

    with pytest.raises(ValueError, match="Gate and revalidated candidate do not match"):
        build_cycle2_authorized_tool_command(
            gate_decision=gate,
            candidate=drifted_candidate,
            registry_snapshot_ref="cycle2-snapshot-ref",
            trusted_context_ref="cycle2-trusted-context-ref",
        )

    assert gate.model_dump(mode="json")["validated_arguments"] == gated_arguments


def test_cycle2_command_rejects_raw_constructed_gate_argument_replacement() -> None:
    candidate, loaded = _cycle2_gateway_case(
        Cycle2ToolName.GET_ORDER,
        selected_get_order=True,
    )
    gate = _evaluate_cycle2(candidate, loaded)
    raw_replacement = gate.model_copy(
        update={"validated_arguments": {"order_id": "O-9999"}}
    )
    drifted_candidate = candidate.model_copy(
        update={"candidate_arguments": {"order_id": "O-9999"}}
    )

    with pytest.raises(ValueError, match="exact typed inputs"):
        build_cycle2_authorized_tool_command(
            gate_decision=raw_replacement,
            candidate=drifted_candidate,
            registry_snapshot_ref="cycle2-snapshot-ref",
            trusted_context_ref="cycle2-trusted-context-ref",
        )


def test_cycle2_command_rejects_inert_gate_without_authorization_arguments() -> None:
    candidate, loaded = _cycle2_gateway_case(Cycle2ToolName.GET_ORDER)
    gate = _evaluate_cycle2(candidate, loaded)
    inert_gate = gate.model_copy(update={"validated_arguments": None})

    with pytest.raises(ValueError, match="Gate and revalidated candidate do not match"):
        build_cycle2_authorized_tool_command(
            gate_decision=inert_gate,
            candidate=candidate,
            registry_snapshot_ref="cycle2-snapshot-ref",
            trusted_context_ref="cycle2-trusted-context-ref",
        )

@pytest.mark.parametrize(
    "drift",
    ["missing-target", "target-in-bindings", "order-binding", "wrong-order"],
)
def test_cycle2_selected_get_order_never_falls_back_to_direct_path(
    drift: str,
) -> None:
    candidate, loaded = _cycle2_gateway_case(
        Cycle2ToolName.GET_ORDER,
        selected_get_order=True,
    )
    if drift == "missing-target":
        candidate = candidate.model_copy(update={"verified_target_ref": None})
    elif drift == "target-in-bindings":
        candidate = candidate.model_copy(
            update={
                "argument_binding_refs": (
                    candidate.argument_binding_refs[0],
                    candidate.verified_target_ref,
                )
            }
        )
    elif drift == "order-binding":
        binding = loaded.current_input_bindings[0].model_copy(
            update={"name": "order_id", "normalized_value": "O-1001"}
        )
        loaded = loaded.model_copy(update={"current_input_bindings": (binding,)})
    else:
        candidate = candidate.model_copy(
            update={"candidate_arguments": {"order_id": "O-9999"}}
        )

    gate = _evaluate_cycle2(candidate, loaded)

    assert gate.decision is GateDecisionValue.REJECT
    assert gate.verified_target_ref is None
    assert gate.reason_code in {
        GateReasonCode.ARGUMENT_BINDING_MISMATCH,
        GateReasonCode.SCHEMA_INVALID,
    }


def test_cycle2_gateway_accepts_search_length_after_normalization() -> None:
    candidate, loaded = _cycle2_gateway_case(Cycle2ToolName.SEARCH_ORDERS)
    normalized = "a" * 80
    candidate = candidate.model_copy(
        update={"candidate_arguments": {"product_description": normalized + " "}}
    )
    binding = loaded.current_input_bindings[0].model_copy(
        update={"normalized_value": normalized}
    )
    loaded = loaded.model_copy(update={"current_input_bindings": (binding,)})

    accepted = _evaluate_cycle2(candidate, loaded)

    assert accepted.decision is GateDecisionValue.ACCEPT
    assert accepted.schema_valid is True
    assert accepted.argument_binding_valid is True

    too_long = candidate.model_copy(
        update={"candidate_arguments": {"product_description": "a" * 81}}
    )
    rejected = _evaluate_cycle2(too_long, loaded)

    assert rejected.decision is GateDecisionValue.REJECT
    assert rejected.schema_valid is False


def test_cycle2_gateway_rejects_declared_nested_model_type_substitution() -> None:
    candidate, loaded = _cycle2_complete_gateway_model_graph()

    class CustomerContextSubclass(CustomerContext):
        pass

    subclass_context = CustomerContextSubclass.model_validate(
        loaded.customer_context.model_dump(),
        strict=True,
    )
    shadow_context = _foreign_shadow_model(loaded.customer_context)
    shadow_binding = _foreign_shadow_model(loaded.current_input_bindings[0])
    task_ref = loaded.context_manifest.task_state_ref_and_version
    assert task_ref is not None
    shadow_task_ref = _foreign_shadow_model(task_ref)
    variants = (
        (
            candidate,
            loaded.model_copy(update={"customer_context": shadow_context}),
        ),
        (
            candidate,
            loaded.model_copy(update={"customer_context": subclass_context}),
        ),
        (
            candidate,
            loaded.model_copy(update={"current_input_bindings": (shadow_binding,)}),
        ),
        (
            candidate,
            loaded.model_copy(
                update={
                    "context_manifest": loaded.context_manifest.model_copy(
                        update={"task_state_ref_and_version": shadow_task_ref}
                    )
                }
            ),
        ),
        (
            candidate.model_copy(
                update={
                    "candidate_arguments": {
                        "order_id": _foreign_shadow_model(
                            loaded.current_input_bindings[0]
                        )
                    }
                }
            ),
            loaded,
        ),
    )

    for malformed_candidate, malformed_loaded in variants:
        gate = _evaluate_cycle2(malformed_candidate, malformed_loaded)
        assert gate.decision is GateDecisionValue.REJECT
        assert gate.reason_code is GateReasonCode.SCHEMA_INVALID


def test_cycle2_gateway_rejects_raw_string_subclasses_before_reconstruction() -> None:
    class StrSubclass(str):
        pass

    candidate, loaded = _cycle2_complete_gateway_model_graph()
    variants = (
        loaded.model_copy(
            update={
                "private_owner_scope_ref": StrSubclass(
                    loaded.private_owner_scope_ref
                )
            }
        ),
        loaded.model_copy(
            update={
                "customer_context": loaded.customer_context.model_copy(
                    update={
                        "customer_id": StrSubclass(
                            loaded.customer_context.customer_id
                        )
                    }
                )
            }
        ),
        loaded.model_copy(
            update={
                "budget": loaded.budget.model_copy(
                    update={
                        "tool_registry_version": StrSubclass(
                            loaded.budget.tool_registry_version
                        )
                    }
                )
            }
        ),
    )

    for malformed_loaded in variants:
        gate = _evaluate_cycle2(candidate, malformed_loaded)
        assert gate.decision is GateDecisionValue.REJECT
        assert gate.reason_code is GateReasonCode.SCHEMA_INVALID


@pytest.mark.parametrize(
    "tool_name",
    [Cycle2ToolName.GET_ORDER, Cycle2ToolName.GET_SHIPMENT],
)
def test_cycle2_gateway_rejects_duplicate_request_unit_binding_refs(
    tool_name: Cycle2ToolName,
) -> None:
    candidate, loaded = _cycle2_gateway_case(tool_name)
    binding_ref = loaded.current_request_unit.input_binding_refs[0]
    loaded = loaded.model_copy(
        update={
            "current_request_unit": loaded.current_request_unit.model_copy(
                update={"input_binding_refs": (binding_ref, binding_ref)}
            )
        }
    )

    gate = _evaluate_cycle2(candidate, loaded)

    assert gate.decision is GateDecisionValue.REJECT
    assert gate.argument_binding_valid is False
    assert gate.reason_code is GateReasonCode.ARGUMENT_BINDING_MISMATCH


@pytest.mark.parametrize(
    "history_variant",
    [
        "budget-ahead",
        "history-ahead",
        "duplicate-step-identity",
        "identity-collision",
        "arguments-extra",
        "arguments-missing",
        "duplicate-binding-ref",
        "unique-extra-binding-ref",
        "current-semantic-padded",
        "duplicate-semantic-distinct-ids",
    ],
)
def test_cycle2_gateway_reconciles_complete_progress_history(
    history_variant: str,
) -> None:
    candidate, loaded = _cycle2_complete_gateway_model_graph()
    prior_step = loaded.progress_snapshot.prior_tool_steps[0]
    if history_variant == "budget-ahead":
        loaded = loaded.model_copy(
            update={
                "budget": loaded.budget.model_copy(update={"tool_calls_used": 2})
            }
        )
    elif history_variant == "history-ahead":
        loaded = loaded.model_copy(
            update={
                "budget": loaded.budget.model_copy(update={"tool_calls_used": 0})
            }
        )
    elif history_variant == "duplicate-step-identity":
        loaded = loaded.model_copy(
            update={
                "budget": loaded.budget.model_copy(update={"tool_calls_used": 2}),
                "progress_snapshot": loaded.progress_snapshot.model_copy(
                    update={"prior_tool_steps": (prior_step, prior_step)}
                ),
            }
        )
    elif history_variant == "identity-collision":
        collision = prior_step.model_copy(
            update={
                "canonical_tool_name": Cycle2ToolName.GET_SHIPMENT,
                "validated_arguments": {"order_id": "O-1001"},
                "argument_binding_refs": candidate.argument_binding_refs,
            }
        )
        loaded = loaded.model_copy(
            update={
                "budget": loaded.budget.model_copy(update={"tool_calls_used": 2}),
                "progress_snapshot": loaded.progress_snapshot.model_copy(
                    update={"prior_tool_steps": (prior_step, collision)}
                ),
            }
        )
    elif history_variant == "arguments-extra":
        malformed = prior_step.model_copy(
            update={
                "validated_arguments": {
                    "order_id": "O-1001",
                    "unexpected": "value",
                }
            }
        )
        loaded = loaded.model_copy(
            update={
                "progress_snapshot": loaded.progress_snapshot.model_copy(
                    update={"prior_tool_steps": (malformed,)}
                )
            }
        )
    elif history_variant == "arguments-missing":
        malformed = prior_step.model_copy(update={"validated_arguments": {}})
        loaded = loaded.model_copy(
            update={
                "progress_snapshot": loaded.progress_snapshot.model_copy(
                    update={"prior_tool_steps": (malformed,)}
                )
            }
        )
    elif history_variant == "duplicate-binding-ref":
        binding_ref = prior_step.argument_binding_refs[0]
        malformed = prior_step.model_copy(
            update={"argument_binding_refs": (binding_ref, binding_ref)}
        )
        loaded = loaded.model_copy(
            update={
                "progress_snapshot": loaded.progress_snapshot.model_copy(
                    update={"prior_tool_steps": (malformed,)}
                )
            }
        )
    elif history_variant == "unique-extra-binding-ref":
        malformed = prior_step.model_copy(
            update={
                "argument_binding_refs": (
                    *prior_step.argument_binding_refs,
                    uuid4(),
                )
            }
        )
        loaded = loaded.model_copy(
            update={
                "progress_snapshot": loaded.progress_snapshot.model_copy(
                    update={"prior_tool_steps": (malformed,)}
                )
            }
        )
    elif history_variant == "current-semantic-padded":
        malformed = prior_step.model_copy(
            update={
                "tool_call_id": uuid4(),
                "canonical_tool_name": Cycle2ToolName.GET_SHIPMENT,
                "validated_arguments": {"order_id": "O-1001"},
                "argument_binding_refs": (*candidate.argument_binding_refs, uuid4()),
            }
        )
        loaded = loaded.model_copy(
            update={
                "progress_snapshot": loaded.progress_snapshot.model_copy(
                    update={"prior_tool_steps": (malformed,)}
                )
            }
        )
    else:
        duplicate = prior_step.model_copy(update={"tool_call_id": uuid4()})
        loaded = loaded.model_copy(
            update={
                "budget": loaded.budget.model_copy(update={"tool_calls_used": 2}),
                "progress_snapshot": loaded.progress_snapshot.model_copy(
                    update={"prior_tool_steps": (prior_step, duplicate)}
                ),
            }
        )

    gate = _evaluate_cycle2(candidate, loaded)

    assert gate.decision is GateDecisionValue.REJECT
    assert gate.progress_valid is False
    assert gate.reason_code is (
        GateReasonCode.SCHEMA_INVALID
        if history_variant == "duplicate-binding-ref"
        else GateReasonCode.NO_PROGRESS
    )


def test_cycle2_gateway_accepts_legitimate_distinct_progress_semantics() -> None:
    candidate, loaded = _cycle2_complete_gateway_model_graph()
    prior_step = loaded.progress_snapshot.prior_tool_steps[0]
    assert prior_step.canonical_tool_name is Cycle2ToolName.GET_ORDER
    assert candidate.requested_provider_tool_name == Cycle2ToolName.GET_SHIPMENT.value

    gate = _evaluate_cycle2(candidate, loaded)

    assert gate.decision is GateDecisionValue.ACCEPT
    assert gate.progress_valid is True


def test_cycle2_direct_get_order_requires_current_user_claim_and_null_target() -> None:
    candidate, loaded = _cycle2_gateway_case(
        Cycle2ToolName.GET_ORDER,
        binding_authority=InputAuthority.MODEL_INFERENCE,
    )
    rejected = _evaluate_cycle2(candidate, loaded)
    assert rejected.decision is GateDecisionValue.REJECT
    assert rejected.reason_code is GateReasonCode.SCHEMA_INVALID
    assert rejected.verified_target_ref is None

    candidate, loaded = _cycle2_gateway_case(Cycle2ToolName.GET_ORDER)
    source_observation_ref = uuid4()
    source_observation_version = "shipment-observation-unrelated-v1"
    unrelated_target_ref = uuid4()
    unrelated_target = Cycle2VerifiedOrderTargetFacts(
        verified_target_ref=unrelated_target_ref,
        private_owner_scope_ref="owner-scope-A",
        owner_customer_id="customer-A",
        task_id=loaded.current_task.task_id,
        request_unit_id=loaded.current_request_unit.request_unit_id,
        task_state_version=loaded.current_task.state_version,
        order_id="O-9999",
        source_observation_ref=source_observation_ref,
        source_observation_version=source_observation_version,
        input_binding_refs=(loaded.current_input_bindings[0].binding_id,),
        superseded_by=None,
    )
    unrelated_observation = Cycle2TargetObservationFacts(
        observation_ref=source_observation_ref,
        observation_version=source_observation_version,
        private_owner_scope_ref="owner-scope-A",
        owner_customer_id="customer-A",
        task_id=loaded.current_task.task_id,
        request_unit_id=loaded.current_request_unit.request_unit_id,
        task_state_version=loaded.current_task.state_version,
        verified_target_ref=unrelated_target_ref,
        input_binding_refs=(loaded.current_input_bindings[0].binding_id,),
        superseded_by=None,
    )
    with_unrelated_target = loaded.model_copy(
        update={
            "current_verified_order_targets": (unrelated_target,),
            "current_target_observations": (unrelated_observation,),
            "current_request_unit": loaded.current_request_unit.model_copy(
                update={"observation_refs": (source_observation_ref,)}
            ),
            "context_manifest": loaded.context_manifest.model_copy(
                update={
                    "observation_refs_and_versions": (
                        VersionedRecordRef(
                            record_ref=source_observation_ref,
                            version=source_observation_version,
                        ),
                    )
                }
            ),
        }
    )
    accepted = _evaluate_cycle2(candidate, with_unrelated_target)
    assert accepted.decision is GateDecisionValue.ACCEPT
    assert candidate.verified_target_ref is None


@pytest.mark.parametrize(
    ("case", "expected_reason"),
    [
        ("snapshot", GateReasonCode.SNAPSHOT_MISMATCH),
        ("schema-extra", GateReasonCode.SCHEMA_INVALID),
        ("binding-value", GateReasonCode.ARGUMENT_BINDING_MISMATCH),
        ("binding-ref", GateReasonCode.SCHEMA_INVALID),
        ("owner", GateReasonCode.STATE_VERSION_MISMATCH),
        ("state", GateReasonCode.STATE_VERSION_MISMATCH),
        ("budget", GateReasonCode.BUDGET_EXCEEDED),
        ("progress", GateReasonCode.NO_PROGRESS),
        ("target", GateReasonCode.ARGUMENT_BINDING_MISMATCH),
    ],
)
def test_cycle2_gateway_compares_loaded_facts_and_fails_closed(
    case: str,
    expected_reason: GateReasonCode,
) -> None:
    candidate, loaded = _cycle2_gateway_case(Cycle2ToolName.GET_SHIPMENT)

    if case == "snapshot":
        loaded = loaded.model_copy(
            update={
                "context_manifest": loaded.context_manifest.model_copy(
                    update={"tool_registry_version": "drifted"}
                )
            }
        )
    elif case == "schema-extra":
        candidate = candidate.model_copy(
            update={"candidate_arguments": {"order_id": "O-1001", "ordinal": 2}}
        )
    elif case == "binding-value":
        candidate = candidate.model_copy(
            update={"candidate_arguments": {"order_id": "O-9999"}}
        )
    elif case == "binding-ref":
        candidate = candidate.model_copy(
            update={"argument_binding_refs": (uuid4(), candidate.verified_target_ref)}
        )
    elif case == "owner":
        loaded = loaded.model_copy(
            update={
                "current_task": loaded.current_task.model_copy(
                    update={"owner_customer_id": "customer-B"}
                )
            }
        )
    elif case == "state":
        loaded = loaded.model_copy(
            update={
                "current_task": loaded.current_task.model_copy(
                    update={"state_version": 2}
                )
            }
        )
    elif case == "budget":
        loaded = loaded.model_copy(
            update={
                "budget": loaded.budget.model_copy(update={"tool_calls_used": 3})
            }
        )
    elif case == "progress":
        loaded = loaded.model_copy(
            update={
                "progress_snapshot": loaded.progress_snapshot.model_copy(
                    update={
                        "prior_tool_steps": (
                            Cycle2ToolProgressFact(
                                tool_call_id=uuid4(),
                                run_id=candidate.run_id,
                                context_manifest_id=candidate.context_manifest_id,
                                tool_registry_version=(
                                    loaded.registry_snapshot.tool_registry_version
                                ),
                                model_visible_toolset_hash=(
                                    loaded.registry_snapshot.model_visible_toolset_hash
                                ),
                                canonical_tool_name=Cycle2ToolName.GET_SHIPMENT,
                                validated_arguments={"order_id": "O-1001"},
                                task_state_version=(
                                    candidate.validated_task_state_version
                                ),
                                argument_binding_refs=candidate.argument_binding_refs,
                                verified_target_ref=candidate.verified_target_ref,
                            ),
                        )
                    }
                ),
            }
        )
    elif case == "target":
        candidate = candidate.model_copy(update={"verified_target_ref": uuid4()})

    gate = _evaluate_cycle2(candidate, loaded)

    assert gate.decision is GateDecisionValue.REJECT
    assert gate.reason_code is expected_reason
    assert "tool_call_id" not in type(gate).model_fields


def test_cycle2_gateway_rejects_unknown_trusted_and_action_candidates() -> None:
    candidate, loaded = _cycle2_gateway_case(Cycle2ToolName.GET_ORDER)
    unknown = candidate.model_copy(update={"requested_provider_tool_name": "create_refund"})
    unknown_gate = _evaluate_cycle2(unknown, loaded)
    assert unknown_gate.decision is GateDecisionValue.REJECT
    assert unknown_gate.reason_code is GateReasonCode.TOOL_NOT_REGISTERED

    injected = candidate.model_copy(
        update={
            "candidate_arguments": {
                "order_id": "O-1001",
                "customer_id": "customer-B",
            }
        }
    )
    injected_gate = _evaluate_cycle2(injected, loaded)
    assert injected_gate.decision is GateDecisionValue.REJECT
    assert injected_gate.reason_code is GateReasonCode.TRUSTED_FIELD_INJECTION

    action_registration = loaded.registry_snapshot.canonical_registrations[1].model_copy(
        update={
            "effect": ToolEffect.ACTION,
            "unknown_result_recovery": "RESULT_UNKNOWN_RECONCILIATION",
        }
    )
    action_snapshot = RegistrySnapshot.build(
        tool_registry_version=loaded.registry_snapshot.tool_registry_version,
        registrations=(
            loaded.registry_snapshot.canonical_registrations[0],
            action_registration,
            loaded.registry_snapshot.canonical_registrations[2],
        ),
    )
    action_loaded = loaded.model_copy(
        update={
            "registry_snapshot": action_snapshot,
            "context_manifest": loaded.context_manifest.model_copy(
                update={
                    "tool_registry_version": action_snapshot.tool_registry_version,
                    "model_visible_toolset_hash": action_snapshot.model_visible_toolset_hash,
                }
            ),
        }
    )
    action_gate = _evaluate_cycle2(candidate, action_loaded)
    assert action_gate.decision is GateDecisionValue.REJECT
    assert action_gate.action_boundary_valid is False
    assert action_gate.reason_code is GateReasonCode.ACTION_REQUIRES_PROPOSAL


def test_cycle2_gateway_typed_surface_has_no_public_or_model_target_authority() -> None:
    candidate, _ = _cycle2_gateway_case(Cycle2ToolName.GET_SHIPMENT)

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Cycle2GatewayCandidate.model_validate(
            {
                **candidate.model_dump(),
                "public_summary": {"order_number": "O-9999"},
            }
        )
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Cycle2GatewayCandidate.model_validate(
            {
                **candidate.model_dump(),
                "model_selected_order_id": "O-9999",
            }
        )


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("not_received_claim", True),
        ("shipment_not_received", "true"),
        ("shipment_not_received", 1),
        ("candidate_ordinal", True),
        ("candidate_ordinal", "2"),
        ("candidate_ordinal", 0),
        ("candidate_ordinal", 6),
    ],
)
def test_cycle2_gateway_binding_vocabulary_is_strict_and_canonical(
    name: str,
    value: object,
) -> None:
    _candidate, loaded = _cycle2_gateway_case(Cycle2ToolName.GET_SHIPMENT)
    base = loaded.current_input_bindings[0]

    with pytest.raises(ValidationError):
        Cycle2AcceptedBindingFacts.model_validate(
            {
                **base.model_dump(),
                "name": name,
                "normalized_value": value,
            },
            strict=True,
        )


@pytest.mark.parametrize(
    ("extra_name", "extra_value"),
    [("shipment_not_received", True), ("product_description", "跑鞋")],
)
def test_cycle2_gateway_selects_candidate_binding_from_complete_multi_binding_closure(
    extra_name: str,
    extra_value: bool | str,
) -> None:
    candidate, loaded = _cycle2_gateway_case(Cycle2ToolName.GET_SHIPMENT)
    primary = loaded.current_input_bindings[0]
    extra = Cycle2AcceptedBindingFacts(
        binding_id=uuid4(),
        private_owner_scope_ref=loaded.private_owner_scope_ref,
        owner_customer_id=loaded.customer_context.customer_id,
        task_id=loaded.current_task.task_id,
        request_unit_id=loaded.current_request_unit.request_unit_id,
        task_state_version=loaded.current_task.state_version,
        name=extra_name,
        normalized_value=extra_value,
        authority=InputAuthority.USER_CLAIM,
        validation_status="ACCEPTED",
        confirmed_by_user=True,
        source_refs=(uuid4(),),
        superseded_by=None,
    )
    loaded = loaded.model_copy(
        update={
            "current_input_bindings": (extra, primary),
            "current_request_unit": loaded.current_request_unit.model_copy(
                update={"input_binding_refs": (extra.binding_id, primary.binding_id)}
            ),
        }
    )

    gate = _evaluate_cycle2(candidate, loaded)

    assert gate.decision is GateDecisionValue.ACCEPT
    assert gate.argument_binding_refs == candidate.argument_binding_refs
    command = build_cycle2_authorized_tool_command(
        gate_decision=gate,
        candidate=candidate,
        registry_snapshot_ref="cycle2-snapshot-ref",
        trusted_context_ref="cycle2-trusted-context-ref",
    )
    assert extra.binding_id not in command.argument_binding_refs
    assert extra.binding_id != command.verified_target_ref
    assert set(command.validated_arguments) == {"order_id"}


@pytest.mark.parametrize(
    "drift",
    ["missing", "wrong-version", "superseded", "wrong-owner", "omitted-manifest"],
)
def test_cycle2_shipment_target_requires_exact_current_observation_closure(
    drift: str,
) -> None:
    candidate, loaded = _cycle2_gateway_case(Cycle2ToolName.GET_SHIPMENT)
    observation = loaded.current_target_observations[0]
    if drift == "missing":
        loaded = loaded.model_copy(update={"current_target_observations": ()})
    elif drift == "wrong-version":
        loaded = loaded.model_copy(
            update={
                "current_target_observations": (
                    observation.model_copy(update={"observation_version": "v999"}),
                )
            }
        )
    elif drift == "superseded":
        loaded = loaded.model_copy(
            update={
                "current_target_observations": (
                    observation.model_copy(update={"superseded_by": uuid4()}),
                )
            }
        )
    elif drift == "wrong-owner":
        loaded = loaded.model_copy(
            update={
                "current_target_observations": (
                    observation.model_copy(update={"owner_customer_id": "customer-B"}),
                )
            }
        )
    else:
        loaded = loaded.model_copy(
            update={
                "context_manifest": loaded.context_manifest.model_copy(
                    update={"observation_refs_and_versions": ()}
                )
            }
        )

    gate = _evaluate_cycle2(candidate, loaded)

    assert gate.decision is GateDecisionValue.REJECT
    assert gate.argument_binding_valid is False


def test_cycle2_gateway_rejects_multiple_current_targets_for_same_binding() -> None:
    candidate, loaded = _cycle2_gateway_case(Cycle2ToolName.GET_SHIPMENT)
    target = loaded.current_verified_order_targets[0]
    observation = loaded.current_target_observations[0]
    second_observation_ref = uuid4()
    second_version = "shipment-observation-v2"
    second_target = target.model_copy(
        update={
            "verified_target_ref": uuid4(),
            "source_observation_ref": second_observation_ref,
            "source_observation_version": second_version,
        }
    )
    second_observation = observation.model_copy(
        update={
            "observation_ref": second_observation_ref,
            "observation_version": second_version,
            "verified_target_ref": second_target.verified_target_ref,
        }
    )
    loaded = loaded.model_copy(
        update={
            "current_verified_order_targets": (target, second_target),
            "current_target_observations": (observation, second_observation),
            "current_request_unit": loaded.current_request_unit.model_copy(
                update={
                    "observation_refs": (
                        observation.observation_ref,
                        second_observation_ref,
                    )
                }
            ),
            "context_manifest": loaded.context_manifest.model_copy(
                update={
                    "observation_refs_and_versions": (
                        *loaded.context_manifest.observation_refs_and_versions,
                        VersionedRecordRef(
                            record_ref=second_observation_ref,
                            version=second_version,
                        ),
                    )
                }
            ),
        }
    )

    gate = _evaluate_cycle2(candidate, loaded)

    assert gate.decision is GateDecisionValue.REJECT
    assert gate.reason_code is GateReasonCode.ARGUMENT_BINDING_MISMATCH
    assert gate.verified_target_ref is None


@pytest.mark.parametrize(
    "bypass",
    ["bool-state", "bool-budget", "foreign-budget-run", "foreign-progress-run"],
)
def test_cycle2_gateway_strictly_reconstructs_bypassed_or_foreign_facts(
    bypass: str,
) -> None:
    candidate, loaded = _cycle2_gateway_case(Cycle2ToolName.GET_ORDER)
    if bypass == "bool-state":
        candidate = candidate.model_copy(update={"validated_task_state_version": True})
    elif bypass == "bool-budget":
        loaded = loaded.model_copy(
            update={"budget": loaded.budget.model_copy(update={"tool_calls_used": False})}
        )
    elif bypass == "foreign-budget-run":
        loaded = loaded.model_copy(
            update={"budget": loaded.budget.model_copy(update={"run_id": uuid4()})}
        )
    else:
        loaded = loaded.model_copy(
            update={
                "progress_snapshot": loaded.progress_snapshot.model_copy(
                    update={"run_id": uuid4()}
                )
            }
        )

    gate = _evaluate_cycle2(candidate, loaded)

    assert gate.decision is GateDecisionValue.REJECT


@pytest.mark.parametrize(
    "bypass",
    [
        "task-state-bool",
        "task-state-float",
        "request-unit-state-bool",
        "request-unit-state-float",
        "manifest-state-bool",
        "manifest-state-float",
        "accepted-parallel-false",
        "accepted-parallel-float",
    ],
)
def test_cycle2_gateway_preflights_raw_nested_integer_types(
    bypass: str,
) -> None:
    candidate, loaded = _cycle2_gateway_case(Cycle2ToolName.GET_ORDER)
    if bypass.startswith("task-state"):
        loaded = loaded.model_copy(
            update={
                "current_task": loaded.current_task.model_copy(
                    update={
                        "state_version": (
                            True if bypass.endswith("bool") else 1.0
                        )
                    }
                )
            }
        )
    elif bypass.startswith("request-unit-state"):
        loaded = loaded.model_copy(
            update={
                "current_request_unit": loaded.current_request_unit.model_copy(
                    update={
                        "state_version": (
                            True if bypass.endswith("bool") else 1.0
                        )
                    }
                )
            }
        )
    elif bypass.startswith("manifest-state"):
        candidate = candidate.model_copy(
            update={"proposed_base_task_state_version": 1}
        )
        loaded = loaded.model_copy(
            update={
                "context_manifest": loaded.context_manifest.model_copy(
                    update={
                        "task_state_ref_and_version": (
                            TaskStateRefAndVersion.model_construct(
                                task_id=candidate.task_id,
                                state_version=(
                                    True if bypass.endswith("bool") else 1.0
                                ),
                            )
                        )
                    }
                )
            }
        )
    else:
        loaded = loaded.model_copy(
            update={
                "budget": loaded.budget.model_copy(
                    update={"accepted_parallel_tool_calls": False}
                    if bypass.endswith("false")
                    else {"accepted_parallel_tool_calls": 0.0}
                )
            }
        )

    gate = _evaluate_cycle2(candidate, loaded)

    assert gate.decision is GateDecisionValue.REJECT
    assert gate.state_version_valid is False


@pytest.mark.parametrize(
    ("policy_field", "malformed_value"),
    [
        ("max_attempts", True),
        ("max_attempts", 1.0),
        ("timeout_ms", True),
        ("timeout_ms", 500.0),
    ],
)
def test_cycle2_gateway_rejects_raw_malformed_private_registry_policy(
    policy_field: str,
    malformed_value: object,
) -> None:
    candidate, loaded = _cycle2_gateway_case(Cycle2ToolName.GET_ORDER)
    registrations = list(loaded.registry_snapshot.canonical_registrations)
    index = next(
        index
        for index, registration in enumerate(registrations)
        if registration.tool_spec.name == "get_order"
    )
    registration = registrations[index]
    registrations[index] = registration.model_copy(
        update={
            "execution_policy": registration.execution_policy.model_copy(
                update={policy_field: malformed_value}
            )
        }
    )
    malformed_snapshot = loaded.registry_snapshot.model_copy(
        update={"canonical_registrations": tuple(registrations)}
    )
    loaded = loaded.model_copy(update={"registry_snapshot": malformed_snapshot})

    gate = _evaluate_cycle2(candidate, loaded)

    assert gate.decision is GateDecisionValue.REJECT
    assert gate.registration_valid is False


@pytest.mark.parametrize(
    "variant",
    [
        "min-length-bool",
        "candidate-min-items-bool",
        "ordinal-minimum-bool",
        "effect-string",
        "raw-schema-dict",
        "raw-required-list",
    ],
)
def test_cycle2_gateway_rejects_complete_registration_raw_type_drift(
    variant: str,
) -> None:
    candidate, loaded = _cycle2_gateway_case(Cycle2ToolName.SEARCH_ORDERS)
    registrations = list(loaded.registry_snapshot.canonical_registrations)
    index = next(
        index
        for index, registration in enumerate(registrations)
        if registration.tool_spec.name == "search_orders"
    )
    registration = registrations[index]
    if variant == "effect-string":
        registrations[index] = registration.model_copy(update={"effect": "READ"})
    else:
        field_name = "input_schema" if variant in {
            "min-length-bool",
            "raw-schema-dict",
            "raw-required-list",
        } else "output_schema"
        schema = registration.tool_spec.model_dump()[field_name]
        if variant == "min-length-bool":
            schema["properties"]["product_description"]["minLength"] = True
            schema_value = freeze_json_value(schema)
        elif variant == "candidate-min-items-bool":
            schema["properties"]["candidates"]["minItems"] = True
            schema_value = freeze_json_value(schema)
        elif variant == "ordinal-minimum-bool":
            schema["properties"]["candidates"]["items"]["properties"][
                "ordinal"
            ]["minimum"] = True
            schema_value = freeze_json_value(schema)
        elif variant == "raw-schema-dict":
            schema_value = schema
        else:
            original = registration.tool_spec.input_schema
            schema_value = tuple.__new__(
                FrozenJsonDict,
                tuple(
                    (key, ["product_description"] if key == "required" else value)
                    for key, value in original.items()
                ),
            )
        registrations[index] = registration.model_copy(
            update={
                "tool_spec": registration.tool_spec.model_copy(
                    update={field_name: schema_value}
                )
            }
        )
    loaded = loaded.model_copy(
        update={
            "registry_snapshot": loaded.registry_snapshot.model_copy(
                update={"canonical_registrations": tuple(registrations)}
            )
        }
    )

    gate = _evaluate_cycle2(candidate, loaded)

    assert gate.decision is GateDecisionValue.REJECT
    assert gate.registration_valid is False


@pytest.mark.parametrize(
    "tool_name",
    [
        Cycle2ToolName.SEARCH_ORDERS,
        Cycle2ToolName.GET_ORDER,
        Cycle2ToolName.GET_SHIPMENT,
    ],
)
def test_cycle2_gateway_recursive_registry_preflight_accepts_exact_three_reads(
    tool_name: Cycle2ToolName,
) -> None:
    candidate, loaded = _cycle2_gateway_case(tool_name)

    gate = _evaluate_cycle2(candidate, loaded)

    assert gate.decision is GateDecisionValue.ACCEPT
    assert gate.registration_valid is True


def _cycle2_gateway_registry_model_envelope_variant(
    snapshot: RegistrySnapshot,
    layer: str,
    bypass: str,
) -> RegistrySnapshot:
    registrations = list(snapshot.canonical_registrations)
    registration = registrations[0]
    mappings = list(snapshot.provider_name_to_canonical_name)
    missing_fields = {
        "snapshot": "tool_registry_version",
        "registration": "risk",
        "tool-spec": "description",
        "execution-policy": "timeout_ms",
        "provider-binding": "canonical_tool_name",
    }

    def corrupt(model: object) -> object:
        if bypass == "model-copy-extra":
            malformed = model.model_copy(update={"unexpected_field": "unexpected"})
            assert "unexpected_field" in malformed.__dict__
            return malformed
        raw = dict(model.__dict__)
        if bypass == "model-construct-missing":
            raw.pop(missing_fields[layer])
            malformed = type(model).model_construct(**raw)
            assert missing_fields[layer] not in malformed.__dict__
            return malformed
        malformed = type(model).model_construct(**raw)
        object.__setattr__(
            malformed,
            "__pydantic_extra__",
            {"unexpected_field": "unexpected"},
        )
        assert malformed.__pydantic_extra__ == {
            "unexpected_field": "unexpected"
        }
        return malformed

    if layer == "snapshot":
        return corrupt(snapshot)
    if layer == "registration":
        registrations[0] = corrupt(registration)
    elif layer == "tool-spec":
        registrations[0] = registration.model_copy(
            update={"tool_spec": corrupt(registration.tool_spec)}
        )
    elif layer == "execution-policy":
        registrations[0] = registration.model_copy(
            update={"execution_policy": corrupt(registration.execution_policy)}
        )
    else:
        mappings[0] = corrupt(mappings[0])
        return snapshot.model_copy(
            update={"provider_name_to_canonical_name": tuple(mappings)}
        )
    return snapshot.model_copy(
        update={"canonical_registrations": tuple(registrations)}
    )


@pytest.mark.parametrize(
    "layer",
    [
        "snapshot",
        "registration",
        "tool-spec",
        "execution-policy",
        "provider-binding",
    ],
)
@pytest.mark.parametrize(
    "bypass",
    [
        "model-copy-extra",
        "model-construct-extra",
        "model-construct-missing",
    ],
)
def test_cycle2_gateway_rejects_open_registry_model_envelopes(
    layer: str,
    bypass: str,
) -> None:
    candidate, loaded = _cycle2_gateway_case(Cycle2ToolName.SEARCH_ORDERS)
    malformed_snapshot = _cycle2_gateway_registry_model_envelope_variant(
        loaded.registry_snapshot,
        layer,
        bypass,
    )
    loaded = loaded.model_copy(update={"registry_snapshot": malformed_snapshot})

    gate = _evaluate_cycle2(candidate, loaded)

    assert gate.decision is GateDecisionValue.REJECT
    assert gate.registration_valid is False


def _cycle2_complete_gateway_model_graph() -> tuple[
    Cycle2GatewayCandidate,
    Cycle2GatewayLoadedClosure,
]:
    candidate, loaded = _cycle2_gateway_case(Cycle2ToolName.GET_SHIPMENT)
    task_ref = TaskStateRefAndVersion(
        task_id=candidate.task_id,
        state_version=candidate.validated_task_state_version,
    )
    candidate = candidate.model_copy(
        update={
            "proposed_base_task_state_version": candidate.validated_task_state_version
        }
    )
    prior_step = Cycle2ToolProgressFact(
        tool_call_id=uuid4(),
        run_id=candidate.run_id,
        context_manifest_id=candidate.context_manifest_id,
        tool_registry_version=loaded.registry_snapshot.tool_registry_version,
        model_visible_toolset_hash=(
            loaded.registry_snapshot.model_visible_toolset_hash
        ),
        canonical_tool_name=Cycle2ToolName.GET_ORDER,
        validated_arguments={"order_id": "O-1001"},
        task_state_version=candidate.validated_task_state_version,
        argument_binding_refs=(loaded.current_input_bindings[0].binding_id,),
        verified_target_ref=None,
    )
    loaded = loaded.model_copy(
        update={
            "context_manifest": loaded.context_manifest.model_copy(
                update={"task_state_ref_and_version": task_ref}
            ),
            "progress_snapshot": loaded.progress_snapshot.model_copy(
                update={"prior_tool_steps": (prior_step,)}
            ),
            "budget": loaded.budget.model_copy(update={"tool_calls_used": 1}),
        }
    )
    assert _evaluate_cycle2(candidate, loaded).decision is GateDecisionValue.ACCEPT
    return candidate, loaded


def test_cycle2_progress_fact_requires_durable_tool_call_identity() -> None:
    _candidate, loaded = _cycle2_complete_gateway_model_graph()
    prior_step = loaded.progress_snapshot.prior_tool_steps[0]
    assert type(prior_step.tool_call_id) is UUID

    legacy_payload = prior_step.model_dump()
    legacy_payload.pop("tool_call_id")
    with pytest.raises(ValidationError):
        Cycle2ToolProgressFact.model_validate(legacy_payload, strict=True)

    missing_target_payload = prior_step.model_dump()
    missing_target_payload.pop("verified_target_ref")
    with pytest.raises(ValidationError):
        Cycle2ToolProgressFact.model_validate(
            missing_target_payload,
            strict=True,
        )


def test_cycle2_progress_identity_keeps_target_separate_and_distinguishable() -> None:
    candidate, loaded = _cycle2_gateway_case(Cycle2ToolName.GET_SHIPMENT)
    first = Cycle2ToolProgressFact(
        tool_call_id=uuid4(),
        run_id=candidate.run_id,
        context_manifest_id=candidate.context_manifest_id,
        tool_registry_version=loaded.registry_snapshot.tool_registry_version,
        model_visible_toolset_hash=loaded.registry_snapshot.model_visible_toolset_hash,
        canonical_tool_name=Cycle2ToolName.GET_SHIPMENT,
        validated_arguments={"order_id": "O-1001"},
        task_state_version=candidate.validated_task_state_version,
        argument_binding_refs=candidate.argument_binding_refs,
        verified_target_ref=candidate.verified_target_ref,
    )
    second = Cycle2ToolProgressFact.model_validate(
        {
            **first.model_dump(),
            "tool_call_id": uuid4(),
            "verified_target_ref": uuid4(),
        },
        strict=True,
    )

    assert first.verified_target_ref not in first.argument_binding_refs
    assert second.verified_target_ref not in second.argument_binding_refs
    assert first.verified_target_ref != second.verified_target_ref
    assert first != second


def _nested_gateway_models(value: object) -> tuple[BaseModel, ...]:
    found: list[BaseModel] = []
    seen: set[int] = set()

    def visit(current: object) -> None:
        current_id = id(current)
        if current_id in seen:
            return
        if isinstance(current, BaseModel):
            seen.add(current_id)
            found.append(current)
            for field_name in type(current).model_fields:
                if field_name in current.__dict__:
                    visit(current.__dict__[field_name])
            return
        if isinstance(current, Mapping):
            seen.add(current_id)
            for key, item in current.items():
                visit(key)
                visit(item)
            return
        if isinstance(current, tuple):
            seen.add(current_id)
            for item in current:
                visit(item)

    visit(value)
    return tuple(found)


def _replace_gateway_model(
    value: object,
    target: BaseModel,
    replacement: BaseModel,
) -> object:
    if value is target:
        return replacement
    if isinstance(value, BaseModel):
        updates: dict[str, object] = {}
        for field_name in type(value).model_fields:
            if field_name not in value.__dict__:
                continue
            original = value.__dict__[field_name]
            replaced = _replace_gateway_model(original, target, replacement)
            if replaced is not original:
                updates[field_name] = replaced
        return value.model_copy(update=updates) if updates else value
    if isinstance(value, tuple):
        replaced_items = tuple(
            _replace_gateway_model(item, target, replacement) for item in value
        )
        return replaced_items if any(
            replaced is not original
            for replaced, original in zip(replaced_items, value, strict=True)
        ) else value
    return value


def _assert_gateway_graph_corruption_rejected(
    *,
    candidate: Cycle2GatewayCandidate,
    loaded: Cycle2GatewayLoadedClosure,
    target: BaseModel,
    replacement: BaseModel,
    vector: str,
) -> None:
    malformed_candidate = _replace_gateway_model(candidate, target, replacement)
    malformed_loaded = _replace_gateway_model(loaded, target, replacement)
    gate = _evaluate_cycle2(malformed_candidate, malformed_loaded)
    label = f"{type(target).__name__}:{vector}"
    assert gate.decision is GateDecisionValue.REJECT, label
    assert gate.reason_code is GateReasonCode.SCHEMA_INVALID, label
    assert gate.registration_valid is False, label


def test_cycle2_gateway_raw_preflight_closes_complete_nested_model_graph() -> None:
    candidate, loaded = _cycle2_complete_gateway_model_graph()
    nodes = _nested_gateway_models(candidate) + _nested_gateway_models(loaded)
    discovered_types = {type(node).__name__ for node in nodes}
    assert {
        "Cycle2GatewayCandidate",
        "Cycle2GatewayLoadedClosure",
        "CustomerContext",
        "TaskRecord",
        "RequestUnitRecord",
        "Cycle2AcceptedBindingFacts",
        "Cycle2VerifiedOrderTargetFacts",
        "Cycle2TargetObservationFacts",
        "RegistrySnapshot",
        "ToolRegistration",
        "ToolSpec",
        "ExecutionPolicy",
        "ProviderToolNameBinding",
        "ContextManifest",
        "TaskStateRefAndVersion",
        "VersionedRecordRef",
        "TokenCounts",
        "Cycle2GatewayBudgetFacts",
        "Cycle2GatewayProgressSnapshot",
        "Cycle2ToolProgressFact",
    }.issubset(discovered_types)
    assert all(
        node.model_fields_set == set(type(node).model_fields) for node in nodes
    )

    missing_vectors: set[tuple[str, str, str]] = set()
    for node in nodes:
        raw_extra = node.model_copy(update={"unexpected_field": "unexpected"})
        _assert_gateway_graph_corruption_rejected(
            candidate=candidate,
            loaded=loaded,
            target=node,
            replacement=raw_extra,
            vector="raw-extra",
        )
        pydantic_extra = type(node).model_construct(**node.__dict__)
        object.__setattr__(
            pydantic_extra,
            "__pydantic_extra__",
            {"unexpected_field": "unexpected"},
        )
        _assert_gateway_graph_corruption_rejected(
            candidate=candidate,
            loaded=loaded,
            target=node,
            replacement=pydantic_extra,
            vector="pydantic-extra",
        )
        for field_name, field in type(node).model_fields.items():
            missing = type(node).model_construct(**node.__dict__)
            missing.__dict__.pop(field_name)
            field_kind = "required" if field.is_required() else "default"
            missing_vectors.add((type(node).__name__, field_name, field_kind))
            _assert_gateway_graph_corruption_rejected(
                candidate=candidate,
                loaded=loaded,
                target=node,
                replacement=missing,
                vector=f"missing-{field_kind}:{field_name}",
            )
            if not field.is_required():
                payload = node.model_dump()
                payload.pop(field_name)
                defaulted = type(node).model_validate(payload)
                assert field_name not in defaulted.model_fields_set
                _assert_gateway_graph_corruption_rejected(
                    candidate=candidate,
                    loaded=loaded,
                    target=node,
                    replacement=defaulted,
                    vector=f"validated-missing-default:{field_name}",
                )

    assert ("CustomerContext", "provenance", "default") in missing_vectors
    assert (
        "Cycle2AcceptedBindingFacts",
        "validation_status",
        "default",
    ) in missing_vectors
    assert (
        "Cycle2AcceptedBindingFacts",
        "superseded_by",
        "default",
    ) in missing_vectors


def test_cycle2_gateway_fails_closed_when_complete_progress_history_is_omitted() -> None:
    candidate, loaded = _cycle2_gateway_case(Cycle2ToolName.GET_ORDER)
    raw = dict(loaded.__dict__)
    raw.pop("progress_snapshot")
    incomplete = Cycle2GatewayLoadedClosure.model_construct(**raw)

    gate = _evaluate_cycle2(candidate, incomplete)

    assert gate.decision is GateDecisionValue.REJECT
    assert gate.progress_valid is False


def test_cycle2_gateway_fails_closed_on_model_construct_candidate_omission() -> None:
    candidate, loaded = _cycle2_gateway_case(Cycle2ToolName.GET_ORDER)
    raw = dict(candidate.__dict__)
    raw.pop("argument_binding_refs")
    incomplete = Cycle2GatewayCandidate.model_construct(**raw)

    gate = _evaluate_cycle2(incomplete, loaded)

    assert gate.decision is GateDecisionValue.REJECT
    assert gate.schema_valid is False
    assert gate.argument_binding_valid is False


def test_cycle2_get_order_preserves_phase1_trim_and_case_normalization() -> None:
    candidate, loaded = _cycle2_gateway_case(Cycle2ToolName.GET_ORDER)
    candidate = candidate.model_copy(
        update={"candidate_arguments": {"order_id": " o-1001 "}}
    )

    gate = _evaluate_cycle2(candidate, loaded)

    assert gate.decision is GateDecisionValue.ACCEPT
    assert gate.schema_valid is True
    assert gate.argument_binding_valid is True
