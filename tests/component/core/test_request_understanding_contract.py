from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from mini_agent.core.request_understanding import (
    Cycle2InitialRequestUnderstandingOutputV2,
    Cycle2InitialTaskDeltaCandidateV2,
    Cycle2InputCandidate,
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
    UncertaintyReasonCodeV2,
    UncertaintyV2,
)
from mini_agent.core.tool_system import (
    compute_model_visible_toolset_hash,
    get_order_tool_spec,
)


def _candidate(*, message_ref: UUID, order_id: str = "O-4242") -> InputCandidate:
    return InputCandidate(
        name="order_id",
        candidate_value=order_id,
        semantic_role="TARGET_RESOURCE_IDENTIFIER",
        authority=InputAuthority.USER_CLAIM,
        source_kind=InputSourceKind.CURRENT_MESSAGE,
        source_ref=message_ref,
        source_quote=f"订单 {order_id}",
        confidence=0.99,
    )


def test_request_input_binds_model_to_the_exact_toolset_projection() -> None:
    tool_spec = get_order_tool_spec()
    expected_hash = compute_model_visible_toolset_hash((tool_spec,))
    request = RequestUnderstandingInput(
        run_id=uuid4(),
        message_ref=uuid4(),
        original_query="查询订单状态",
        provider_visible_tool_specs=(tool_spec,),
        model_visible_toolset_hash=expected_hash,
    )
    assert request.model_visible_toolset_hash == expected_hash

    with pytest.raises(ValidationError, match="ToolSpec hash mismatch"):
        RequestUnderstandingInput(
            run_id=uuid4(),
            message_ref=uuid4(),
            original_query="查询订单状态",
            provider_visible_tool_specs=(tool_spec,),
            model_visible_toolset_hash=f"sha256:{'0' * 64}",
        )


@pytest.mark.parametrize(
    "arguments",
    [
        {"customer_id": "attacker-selected"},
        {"nested": {"auth_scopes": ["orders:read"]}},
        {"idempotency_key": "model-selected"},
        {"run_id": str(uuid4())},
    ],
)
def test_next_move_rejects_runtime_private_argument_sources(
    arguments: dict[str, object],
) -> None:
    with pytest.raises(ValidationError, match="trusted field"):
        NextMove(
            kind=NextMoveKind.CALL_TOOL,
            requested_tool_name="get_order",
            arguments=arguments,
            base_task_state_version=None,
        )


def test_task_delta_rejects_identity_and_direct_state_fields() -> None:
    message_ref = uuid4()
    base_payload = {
        "candidate_id": uuid4(),
        "operation": "ADD_GOAL",
        "goal_patch": "查询订单状态",
        "input_candidates": (_candidate(message_ref=message_ref),),
        "confidence": 0.9,
    }

    with pytest.raises(ValidationError, match="extra"):
        TaskDeltaCandidate.model_validate(
            {**base_payload, "customer_id": "attacker-selected"}
        )

    with pytest.raises(ValidationError, match="extra"):
        TaskDeltaCandidate.model_validate({**base_payload, "status": "COMPLETED"})


def test_next_move_rejects_fake_zero_version() -> None:
    with pytest.raises(ValidationError, match="greater than or equal to 1"):
        NextMove(
            kind="CALL_TOOL",
            requested_tool_name="get_order",
            arguments={"order_id": "O-4242"},
            base_task_state_version=0,
        )


def _resolved_v2(
    *,
    source_ref: UUID,
    source_quote: str = "订单 O-4242",
    source_kind: ReferenceSourceKindV2 = ReferenceSourceKindV2.CURRENT_MESSAGE,
) -> ResolvedReferenceCandidateV2:
    return ResolvedReferenceCandidateV2(
        name="order_id",
        candidate_value="O-4242",
        source_kind=source_kind,
        source_ref=source_ref,
        source_quote=source_quote,
        confidence=0.98,
    )


def _contextualization_v2(
    *,
    message_ref: UUID,
    resolved: tuple[ResolvedReferenceCandidateV2, ...] | None = None,
    source_message_refs: tuple[UUID, ...] | None = None,
) -> QueryContextualizationCandidateV2:
    return QueryContextualizationCandidateV2(
        text="查询订单 O-4242 的当前状态",
        resolved_reference_candidates=resolved
        if resolved is not None
        else (_resolved_v2(source_ref=message_ref),),
        uncertainties=(),
        source_message_refs=source_message_refs or (message_ref,),
    )


def _output_v2(
    *,
    message_ref: UUID | None = None,
    candidates: tuple[TaskDeltaCandidate, ...] | None = None,
    next_move: NextMove | None = None,
) -> RequestUnderstandingOutputV2:
    actual_message_ref = message_ref or uuid4()
    actual_candidates = candidates
    if actual_candidates is None:
        actual_candidates = (
            TaskDeltaCandidate(
                candidate_id=uuid4(),
                operation=TaskDeltaOperation.ADD_GOAL,
                goal_patch="查询当前消息中订单的状态",
                input_candidates=(
                    _candidate(message_ref=actual_message_ref),
                ),
                confidence=0.98,
            ),
        )
    return RequestUnderstandingOutputV2(
        schema_version="e2e01-thin-v2",
        message_ref=actual_message_ref,
        contextualization=_contextualization_v2(
            message_ref=actual_message_ref
        ),
        task_delta_candidates=actual_candidates,
        next_move_candidate=next_move
        or NextMove(
            kind=NextMoveKind.CALL_TOOL,
            requested_tool_name="get_order",
            arguments={"order_id": "O-4242"},
            base_task_state_version=None,
        ),
    )


def test_v2_model_facing_types_have_exact_direct_binding_fields() -> None:
    assert tuple(ResolvedReferenceCandidateV2.model_fields) == (
        "name",
        "candidate_value",
        "source_kind",
        "source_ref",
        "source_quote",
        "confidence",
    )
    assert tuple(UncertaintyV2.model_fields) == (
        "name",
        "candidate_values",
        "reason_code",
        "source_message_refs",
    )
    assert tuple(QueryContextualizationCandidateV2.model_fields) == (
        "text",
        "resolved_reference_candidates",
        "uncertainties",
        "source_message_refs",
    )
    assert tuple(RequestUnderstandingOutputV2.model_fields) == (
        "schema_version",
        "message_ref",
        "contextualization",
        "task_delta_candidates",
        "next_move_candidate",
    )
    assert RequestUnderstandingOutputV2.model_fields[
        "schema_version"
    ].is_required()

    output = _output_v2()
    assert output.schema_version == "e2e01-thin-v2"
    assert output.task_delta_candidates
    assert output.next_move_candidate.base_task_state_version is None
    assert "status" not in TaskDeltaCandidate.model_fields
    assert "state_version" not in TaskDeltaCandidate.model_fields
    assert "tool_call_id" not in NextMove.model_fields

    payload = output.model_dump()
    payload.pop("schema_version")
    with pytest.raises(ValidationError, match="schema_version"):
        RequestUnderstandingOutputV2.model_validate(payload)

    with pytest.raises(ValidationError, match="literal"):
        RequestUnderstandingOutputV2.model_validate(
            {**output.model_dump(), "schema_version": "e2e01-thin-v1"}
        )

    with pytest.raises(ValidationError, match="extra"):
        RequestUnderstandingOutputV2.model_validate(
            {**output.model_dump(), "customer_id": "attacker-selected"}
        )

    with pytest.raises(ValidationError, match="frozen"):
        output.schema_version = "e2e01-thin-v2"
    with pytest.raises(ValidationError, match="frozen"):
        output.next_move_candidate.kind = NextMoveKind.FINISH


def test_v2_model_parameter_mismatch_remains_for_gateway_rejection() -> None:
    message_ref = uuid4()
    output = _output_v2(
        message_ref=message_ref,
        candidates=(
            TaskDeltaCandidate(
                candidate_id=uuid4(),
                operation=TaskDeltaOperation.ADD_GOAL,
                goal_patch="查询当前消息中订单的状态",
                input_candidates=(
                    _candidate(message_ref=message_ref, order_id="O-4242"),
                ),
                confidence=0.98,
            ),
        ),
        next_move=NextMove(
            kind=NextMoveKind.CALL_TOOL,
            requested_tool_name="get_order",
            arguments={"order_id": "O-4343"},
            base_task_state_version=None,
        ),
    )

    assert (
        output.task_delta_candidates[0].input_candidates[0].candidate_value
        != output.next_move_candidate.arguments["order_id"]
    )


@pytest.mark.parametrize("source_quote", ["", "界" * 129, b"order O-4242"])
def test_v2_resolved_reference_quote_is_required_bounded_strict_text(
    source_quote: object,
) -> None:
    with pytest.raises(ValidationError):
        ResolvedReferenceCandidateV2(
            name="order_id",
            candidate_value="O-4242",
            source_kind=ReferenceSourceKindV2.CURRENT_MESSAGE,
            source_ref=uuid4(),
            source_quote=source_quote,  # type: ignore[arg-type]
            confidence=0.9,
        )


def test_v2_reference_and_contextualization_preserve_exact_source_scope() -> None:
    current_ref = uuid4()
    recent_ref = uuid4()
    recent = _resolved_v2(
        source_ref=recent_ref,
        source_kind=ReferenceSourceKindV2.RECENT_MESSAGE,
    )
    contextualization = _contextualization_v2(
        message_ref=current_ref,
        resolved=(recent,),
        source_message_refs=(current_ref, recent_ref),
    )

    assert contextualization.source_message_refs == (current_ref, recent_ref)
    assert (
        contextualization.resolved_reference_candidates[0].source_kind
        is ReferenceSourceKindV2.RECENT_MESSAGE
    )

    with pytest.raises(ValidationError, match="source_message_refs"):
        _contextualization_v2(
            message_ref=current_ref,
            resolved=(recent,),
            source_message_refs=(current_ref,),
        )

    with pytest.raises(ValidationError, match="unique"):
        _contextualization_v2(
            message_ref=current_ref,
            source_message_refs=(current_ref, current_ref),
        )

    other_ref = uuid4()
    with pytest.raises(ValidationError, match="current message"):
        RequestUnderstandingOutputV2(
            schema_version="e2e01-thin-v2",
            message_ref=other_ref,
            contextualization=contextualization,
            task_delta_candidates=(),
            next_move_candidate=NextMove(kind=NextMoveKind.ASK_USER),
        )


@pytest.mark.parametrize(
    ("reason", "candidate_values", "valid"),
    [
        (UncertaintyReasonCodeV2.MISSING_REFERENCE, (), True),
        (UncertaintyReasonCodeV2.MISSING_REFERENCE, ("O-4242",), False),
        (
            UncertaintyReasonCodeV2.MULTIPLE_PLAUSIBLE_REFERENCES,
            ("O-4242", "O-4343"),
            True,
        ),
        (
            UncertaintyReasonCodeV2.MULTIPLE_PLAUSIBLE_REFERENCES,
            ("O-4242",),
            False,
        ),
        (
            UncertaintyReasonCodeV2.MULTIPLE_PLAUSIBLE_REFERENCES,
            ("O-4242", "O-4242"),
            False,
        ),
    ],
)
def test_v2_uncertainty_reason_controls_candidate_cardinality(
    reason: UncertaintyReasonCodeV2,
    candidate_values: tuple[str, ...],
    valid: bool,
) -> None:
    values = {
        "name": "order_id",
        "candidate_values": candidate_values,
        "reason_code": reason,
        "source_message_refs": (uuid4(),),
    }
    if valid:
        uncertainty = UncertaintyV2.model_validate(values)
        assert uncertainty.candidate_values == candidate_values
    else:
        with pytest.raises(ValidationError):
            UncertaintyV2.model_validate(values)


def test_v2_output_allows_zero_candidates_but_rejects_duplicate_ids() -> None:
    message_ref = uuid4()
    empty = _output_v2(
        message_ref=message_ref,
        candidates=(),
        next_move=NextMove(kind=NextMoveKind.ASK_USER),
    )
    assert empty.task_delta_candidates == ()

    candidate = TaskDeltaCandidate(
        candidate_id=uuid4(),
        operation=TaskDeltaOperation.ADD_GOAL,
        goal_patch="查询订单状态",
        input_candidates=(_candidate(message_ref=message_ref),),
        confidence=0.9,
    )
    with pytest.raises(ValidationError, match="unique"):
        _output_v2(
            message_ref=message_ref,
            candidates=(candidate, candidate),
        )


def test_v2_output_rejects_long_input_quote_and_non_null_base_version() -> None:
    message_ref = uuid4()
    long_quote = InputCandidate(
        name="order_id",
        candidate_value="O-4242",
        semantic_role="TARGET_RESOURCE_IDENTIFIER",
        authority=InputAuthority.USER_CLAIM,
        source_kind=InputSourceKind.CURRENT_MESSAGE,
        source_ref=message_ref,
        source_quote="界" * 129,
        confidence=0.9,
    )
    candidate = TaskDeltaCandidate(
        candidate_id=uuid4(),
        operation=TaskDeltaOperation.ADD_GOAL,
        goal_patch="查询订单状态",
        input_candidates=(long_quote,),
        confidence=0.9,
    )
    with pytest.raises(ValidationError, match="128"):
        _output_v2(message_ref=message_ref, candidates=(candidate,))

    positive_base = NextMove(
        kind=NextMoveKind.CALL_TOOL,
        requested_tool_name="get_order",
        arguments={"order_id": "O-4242"},
        base_task_state_version=1,
    )
    with pytest.raises(ValidationError, match="null base"):
        _output_v2(message_ref=message_ref, next_move=positive_base)


@pytest.mark.parametrize(
    ("name", "candidate_value"),
    [
        ("product_description", "轻量 跑鞋"),
        ("candidate_ordinal", 2),
        ("shipment_not_received", True),
        ("shipment_not_received", False),
    ],
)
def test_cycle2_input_candidate_has_exact_claim_only_surface(
    name: str,
    candidate_value: object,
) -> None:
    message_ref = uuid4()
    candidate = Cycle2InputCandidate(
        name=name,
        candidate_value=candidate_value,
        source_ref=message_ref,
        source_quote="当前用户消息中的原文",
        confidence=0.98,
    )

    assert tuple(Cycle2InputCandidate.model_fields) == (
        "name",
        "candidate_value",
        "source_ref",
        "source_quote",
        "confidence",
    )
    assert candidate.source_ref == message_ref
    assert {
        "customer_id",
        "private_owner_scope_ref",
        "owner_scoped_order_ref",
        "selected_target_ref",
        "verified_target_ref",
        "candidate_set_ref",
        "candidate_set_version",
        "observation_ref",
        "authority",
    }.isdisjoint(type(candidate).model_fields)


@pytest.mark.parametrize(
    ("name", "candidate_value"),
    [
        ("product_description", 2),
        ("product_description", True),
        ("candidate_ordinal", True),
        ("candidate_ordinal", "2"),
        ("candidate_ordinal", 0),
        ("candidate_ordinal", 6),
        ("shipment_not_received", 1),
        ("shipment_not_received", "true"),
    ],
)
def test_cycle2_input_candidate_rejects_name_value_coercion(
    name: str,
    candidate_value: object,
) -> None:
    with pytest.raises(ValidationError):
        Cycle2InputCandidate(
            name=name,
            candidate_value=candidate_value,
            source_ref=uuid4(),
            source_quote="当前用户消息中的原文",
            confidence=0.98,
        )


@pytest.mark.parametrize(
    "forbidden_field",
    [
        "private_owner_scope_ref",
        "owner_scoped_order_ref",
        "selected_target_ref",
        "verified_target_ref",
        "candidate_set_ref",
        "candidate_set_version",
        "search_observation_ref",
        "observation_candidate_ref",
        "argument_binding_refs",
        "authority",
    ],
)
def test_cycle2_model_candidates_cannot_supply_private_authority(
    forbidden_field: str,
) -> None:
    with pytest.raises(ValidationError):
        Cycle2InputCandidate.model_validate(
            {
                "name": "candidate_ordinal",
                "candidate_value": 2,
                "source_ref": uuid4(),
                "source_quote": "第二个",
                "confidence": 0.98,
                forbidden_field: "attacker-selected",
            }
        )


def _cycle2_initial_delta(
    *,
    message_ref: UUID,
    name: str = "product_description",
    value: object = "轻量 跑鞋",
) -> Cycle2InitialTaskDeltaCandidateV2:
    return Cycle2InitialTaskDeltaCandidateV2(
        candidate_id=uuid4(),
        operation=TaskDeltaOperation.ADD_GOAL,
        goal_patch="查找最近购买的轻量跑鞋订单",
        input_candidates=(
            Cycle2InputCandidate(
                name=name,
                candidate_value=value,
                source_ref=message_ref,
                source_quote="最近买的轻量 跑鞋",
                confidence=0.98,
            ),
        ),
        confidence=0.97,
    )


def _cycle2_initial_output(
    *,
    message_ref: UUID,
    deltas: tuple[Cycle2InitialTaskDeltaCandidateV2, ...] | None = None,
    next_move: NextMove | None = None,
) -> Cycle2InitialRequestUnderstandingOutputV2:
    return Cycle2InitialRequestUnderstandingOutputV2(
        schema_version="e2e01-cycle2-initial.p0.v1",
        message_ref=message_ref,
        contextualization=QueryContextualizationCandidateV2(
            text="查找最近购买的轻量跑鞋订单",
            resolved_reference_candidates=(),
            uncertainties=(),
            source_message_refs=(message_ref,),
        ),
        task_delta_candidates=(
            deltas
            if deltas is not None
            else (_cycle2_initial_delta(message_ref=message_ref),)
        ),
        next_move_candidate=(
            next_move
            if next_move is not None
            else NextMove(
                kind=NextMoveKind.CALL_TOOL,
                requested_tool_name="search_orders",
                arguments={"product_description": "轻量 跑鞋"},
                base_task_state_version=None,
            )
        ),
    )


def test_cycle2_initial_output_is_distinct_closed_claim_only_surface() -> None:
    message_ref = uuid4()
    output = _cycle2_initial_output(message_ref=message_ref)

    assert type(output) is Cycle2InitialRequestUnderstandingOutputV2
    assert type(output.task_delta_candidates[0]) is Cycle2InitialTaskDeltaCandidateV2
    assert output.task_delta_candidates[0].input_candidates[0].name == (
        "product_description"
    )
    assert set(Cycle2InitialRequestUnderstandingOutputV2.model_fields) == {
        "schema_version",
        "message_ref",
        "contextualization",
        "task_delta_candidates",
        "next_move_candidate",
    }
    assert {
        "customer_id",
        "owner_customer_id",
        "verified_target_ref",
        "observation_ref",
        "order_id",
    }.isdisjoint(type(output).model_fields)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("order_id", "O-4242"),
        ("candidate_ordinal", 2),
        ("shipment_not_received", True),
    ],
)
def test_cycle2_initial_delta_rejects_continuation_only_candidates(
    name: str,
    value: object,
) -> None:
    with pytest.raises(ValidationError):
        _cycle2_initial_delta(
            message_ref=uuid4(),
            name=name,
            value=value,
        )


def test_cycle2_initial_output_rejects_zero_multiple_and_wrong_source() -> None:
    message_ref = uuid4()
    delta = _cycle2_initial_delta(message_ref=message_ref)
    for deltas in ((), (delta, delta.model_copy(update={"candidate_id": uuid4()}))):
        with pytest.raises(ValidationError):
            _cycle2_initial_output(message_ref=message_ref, deltas=deltas)

    with pytest.raises(ValidationError, match="current message"):
        _cycle2_initial_output(
            message_ref=message_ref,
            deltas=(_cycle2_initial_delta(message_ref=uuid4()),),
        )


@pytest.mark.parametrize(
    "next_move",
    [
        NextMove(
            kind=NextMoveKind.CALL_TOOL,
            requested_tool_name="get_order",
            arguments={"product_description": "轻量 跑鞋"},
        ),
        NextMove(
            kind=NextMoveKind.CALL_TOOL,
            requested_tool_name="search_orders",
            arguments={"product_description": " 轻量  跑鞋 "},
        ),
        NextMove(
            kind=NextMoveKind.CALL_TOOL,
            requested_tool_name="search_orders",
            arguments={"product_description": "其他商品"},
        ),
        NextMove(kind=NextMoveKind.ASK_USER),
    ],
)
def test_cycle2_initial_output_rejects_unbounded_next_move(
    next_move: NextMove,
) -> None:
    with pytest.raises(ValidationError, match="search_orders|normalized"):
        _cycle2_initial_output(
            message_ref=uuid4(),
            next_move=next_move,
        )


def test_cycle2_initial_types_reject_model_supplied_authority() -> None:
    message_ref = uuid4()
    payload = _cycle2_initial_output(message_ref=message_ref).model_dump()
    payload["customer_id"] = "attacker"
    with pytest.raises(ValidationError, match="extra"):
        Cycle2InitialRequestUnderstandingOutputV2.model_validate(payload)
