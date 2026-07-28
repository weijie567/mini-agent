from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from mini_agent.core.identity import CustomerContext
from mini_agent.core.request_processing import (
    InitialRequestDecision,
    RequestProcessingError,
    RequestUnderstandingClosureV2,
    RequestUnderstandingV2Error,
    RevalidatedNextMove,
    build_request_understanding_closure_v2,
    revalidate_next_move,
    validate_and_reduce_initial_request,
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
    RequestUnderstandingOutput,
    RequestUnderstandingOutputV2,
    ResolvedReferenceCandidateV2,
    TaskDeltaCandidate,
    TaskDeltaOperation,
)
from mini_agent.core.task_state import (
    AcceptedTaskDeltaV2,
    CandidateRejectionReasonCode,
    CandidateValidationDecision,
    CandidateValidationRecordV2,
    InputValidationStatus,
    RequestUnderstandingAggregateFailureCodeV2,
    RequestUnderstandingAtomicFailureCodeV2,
    TaskStatus,
)
from mini_agent.core.tool_system import (
    compute_model_visible_toolset_hash,
    get_order_tool_spec,
)

NOW = datetime(2030, 1, 1, tzinfo=UTC)


def _customer_context(customer_id: str = "customer-A") -> CustomerContext:
    return CustomerContext(
        subject_ref="subject-A",
        customer_id=customer_id,
        auth_scopes=frozenset({"orders:read"}),
        authenticated_at=NOW,
        session_ref_hash="sha256:session-A",
    )


def _output(
    *,
    message_ref: UUID,
    candidate_order_id: str = "o-1001",
    proposed_order_id: object = " O-1001 ",
    source_ref: UUID | None = None,
    source_quote: str | None = None,
    requested_tool_name: str = "get_order",
) -> RequestUnderstandingOutput:
    return RequestUnderstandingOutput(
        message_ref=message_ref,
        task_delta_candidates=(
            TaskDeltaCandidate(
                candidate_id=uuid4(),
                operation=TaskDeltaOperation.ADD_GOAL,
                goal_patch="查询当前消息中的订单状态",
                input_candidates=(
                    InputCandidate(
                        name="order_id",
                        candidate_value=candidate_order_id,
                        semantic_role="TARGET_RESOURCE_IDENTIFIER",
                        authority=InputAuthority.USER_CLAIM,
                        source_kind=InputSourceKind.CURRENT_MESSAGE,
                        source_ref=source_ref or message_ref,
                        source_quote=source_quote or f"订单 {candidate_order_id}",
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


def _decision(
    *,
    output: RequestUnderstandingOutput | None = None,
    message_ref: UUID | None = None,
    message: str = "请查询订单 o-1001 的状态",
) -> InitialRequestDecision:
    actual_message_ref = message_ref or uuid4()
    return validate_and_reduce_initial_request(
        output=output or _output(message_ref=actual_message_ref),
        current_message_ref=actual_message_ref,
        current_message=message,
        customer_context=_customer_context(),
        run_id=uuid4(),
        accepted_delta_id=uuid4(),
        task_id=uuid4(),
        request_unit_id=uuid4(),
        binding_id=uuid4(),
        next_move_candidate_ref=uuid4(),
        now=NOW,
    )


def test_valid_current_message_add_goal_builds_one_active_v1_graph() -> None:
    decision = _decision()

    assert decision.input_binding.normalized_value == "O-1001"
    assert decision.input_binding.authority is InputAuthority.USER_CLAIM
    assert (
        decision.input_binding.validation_status
        is InputValidationStatus.ACCEPTED
    )
    assert decision.input_binding.confirmed_by_user is True
    assert decision.task.owner_customer_id == "customer-A"
    assert decision.task.status is TaskStatus.ACTIVE
    assert decision.task.state_version == 1
    assert decision.request_unit.status is TaskStatus.ACTIVE
    assert decision.request_unit.state_version == 1
    assert decision.request_unit.input_binding_refs == (
        decision.input_binding.binding_id,
    )
    assert decision.request_understanding.validated_task_state_version == 1


def test_revalidation_keeps_provider_candidate_distinct_from_binding() -> None:
    message_ref = uuid4()
    decision = _decision(
        output=_output(
            message_ref=message_ref,
            candidate_order_id="O-1001",
            proposed_order_id="O-2001",
        ),
        message_ref=message_ref,
        message="查询订单 O-1001",
    )

    move = revalidate_next_move(
        decision=decision,
        current_task=decision.task,
        current_request_unit=decision.request_unit,
        current_input_binding=decision.input_binding,
    )

    assert move.normalized_candidate_order_id == "O-2001"
    assert move.binding_normalized_value == "O-1001"
    assert move.candidate_arguments["order_id"] == "O-2001"
    assert move.argument_binding_refs == (decision.input_binding.binding_id,)
    assert move.validated_task_state_version == 1
    assert "order_number" not in RevalidatedNextMove.model_fields
    assert "order_number" not in InitialRequestDecision.model_fields


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (
            lambda output, current_ref: output.model_copy(
                update={"message_ref": uuid4()}
            ),
            "current message",
        ),
        (
            lambda output, current_ref: output.model_copy(
                update={
                    "task_delta_candidates": (
                        output.task_delta_candidates[0].model_copy(
                            update={
                                "input_candidates": (
                                    output.task_delta_candidates[
                                        0
                                    ].input_candidates[0].model_copy(
                                        update={
                                            "source_kind": "RECENT_MESSAGE",
                                        }
                                    ),
                                )
                            }
                        ),
                    )
                }
            ),
            "source",
        ),
        (
            lambda output, current_ref: output.model_copy(
                update={
                    "task_delta_candidates": (
                        output.task_delta_candidates[0].model_copy(
                            update={
                                "input_candidates": (
                                    output.task_delta_candidates[
                                        0
                                    ].input_candidates[0].model_copy(
                                        update={
                                            "authority": "MODEL_INFERENCE",
                                        }
                                    ),
                                )
                            }
                        ),
                    )
                }
            ),
            "authority",
        ),
        (
            lambda output, current_ref: output.model_copy(
                update={
                    "next_move_candidate": output.next_move_candidate.model_copy(
                        update={"base_task_state_version": 1}
                    )
                }
            ),
            "base Task version",
        ),
        (
            lambda output, current_ref: output.model_copy(
                update={
                    "next_move_candidate": output.next_move_candidate.model_copy(
                        update={
                            "arguments": {
                                "order_id": "O-1001",
                                "customer_id": "attacker-selected",
                            }
                        }
                    )
                }
            ),
            "trusted field",
        ),
    ],
)
def test_fail_closed_validation_rejects_bypassed_invalid_candidates(
    mutator: object,
    message: str,
) -> None:
    message_ref = uuid4()
    canonical = _output(message_ref=message_ref)
    bypassed = mutator(canonical, message_ref)  # type: ignore[operator]

    with pytest.raises(RequestProcessingError, match=message):
        _decision(output=bypassed, message_ref=message_ref)


def test_source_quote_must_be_an_exact_current_message_provenance() -> None:
    message_ref = uuid4()
    output = _output(
        message_ref=message_ref,
        source_quote="订单 O-1001",
        candidate_order_id="O-1001",
    )

    with pytest.raises(RequestProcessingError, match="source quote"):
        _decision(
            output=output,
            message_ref=message_ref,
            message="请查询我的订单状态",
        )


def test_source_quote_cannot_match_order_id_as_a_longer_id_prefix() -> None:
    message_ref = uuid4()
    output = _output(
        message_ref=message_ref,
        source_quote="订单 O-10010",
        candidate_order_id="O-1001",
    )

    with pytest.raises(RequestProcessingError, match="source quote"):
        _decision(
            output=output,
            message_ref=message_ref,
            message="请查询订单 O-10010 的状态",
        )


def test_input_contract_rejects_trusted_fields_without_runtime_bypass() -> None:
    with pytest.raises(ValidationError, match="trusted field"):
        NextMove(
            kind=NextMoveKind.CALL_TOOL,
            requested_tool_name="get_order",
            arguments={
                "order_id": "O-1001",
                "customer_id": "attacker-selected",
            },
        )


def test_request_processing_accepts_only_exact_frozen_contract_instances() -> None:
    message_ref = uuid4()
    output = _output(message_ref=message_ref)

    with pytest.raises(RequestProcessingError, match="canonical output"):
        validate_and_reduce_initial_request(
            output=output.model_dump(),  # type: ignore[arg-type]
            current_message_ref=message_ref,
            current_message="请查询订单 o-1001 的状态",
            customer_context=_customer_context(),
            run_id=uuid4(),
            accepted_delta_id=uuid4(),
            task_id=uuid4(),
            request_unit_id=uuid4(),
            binding_id=uuid4(),
            next_move_candidate_ref=uuid4(),
            now=NOW,
        )


def test_revalidation_rejects_owner_or_graph_substitution() -> None:
    decision = _decision()
    foreign_task = decision.task.model_copy(
        update={"owner_customer_id": "customer-B"}
    )
    unrelated_unit = decision.request_unit.model_copy(
        update={"task_id": uuid4()}
    )

    with pytest.raises(RequestProcessingError, match="owner"):
        revalidate_next_move(
            decision=decision,
            current_task=foreign_task,
            current_request_unit=decision.request_unit,
            current_input_binding=decision.input_binding,
        )

    with pytest.raises(RequestProcessingError, match="graph"):
        revalidate_next_move(
            decision=decision,
            current_task=decision.task,
            current_request_unit=unrelated_unit,
            current_input_binding=decision.input_binding,
        )


def _request_input_v2(
    *,
    message_ref: UUID,
    message: str,
    run_id: UUID | None = None,
    explicit_schema_version: bool = True,
) -> RequestUnderstandingInput:
    tool_spec = get_order_tool_spec()
    values: dict[str, object] = {
        "run_id": run_id or uuid4(),
        "message_ref": message_ref,
        "original_query": message,
        "provider_visible_tool_specs": (tool_spec,),
        "model_visible_toolset_hash": compute_model_visible_toolset_hash(
            (tool_spec,)
        ),
    }
    if explicit_schema_version:
        values["schema_version"] = "e2e01-thin-v1"
    return RequestUnderstandingInput.model_validate(values)


def _task_delta_v2(
    *,
    candidate_id: UUID,
    message_ref: UUID,
    order_id: str,
    source_quote: str,
) -> TaskDeltaCandidate:
    return TaskDeltaCandidate(
        candidate_id=candidate_id,
        operation=TaskDeltaOperation.ADD_GOAL,
        goal_patch=f"查询 {order_id} 的状态",
        input_candidates=(
            InputCandidate(
                name="order_id",
                candidate_value=order_id,
                semantic_role="TARGET_RESOURCE_IDENTIFIER",
                authority=InputAuthority.USER_CLAIM,
                source_kind=InputSourceKind.CURRENT_MESSAGE,
                source_ref=message_ref,
                source_quote=source_quote,
                confidence=0.98,
            ),
        ),
        confidence=0.97,
    )


def _output_v2(
    *,
    message_ref: UUID,
    candidates: tuple[TaskDeltaCandidate, ...],
    resolved_quote: str | None = None,
) -> RequestUnderstandingOutputV2:
    resolved = ()
    if resolved_quote is not None:
        resolved = (
            ResolvedReferenceCandidateV2(
                name="order_id",
                candidate_value="O-4242",
                source_kind=ReferenceSourceKindV2.CURRENT_MESSAGE,
                source_ref=message_ref,
                source_quote=resolved_quote,
                confidence=0.99,
            ),
        )
    return RequestUnderstandingOutputV2(
        schema_version="e2e01-thin-v2",
        message_ref=message_ref,
        contextualization=QueryContextualizationCandidateV2(
            text="查询用户所指订单的状态",
            resolved_reference_candidates=resolved,
            uncertainties=(),
            source_message_refs=(message_ref,),
        ),
        task_delta_candidates=candidates,
        next_move_candidate=NextMove(kind=NextMoveKind.ASK_USER),
    )


def _validation_v2(
    candidate_ref: UUID,
    *,
    accept: bool,
) -> CandidateValidationRecordV2:
    return CandidateValidationRecordV2(
        candidate_ref=candidate_ref,
        decision=(
            CandidateValidationDecision.ACCEPT
            if accept
            else CandidateValidationDecision.REJECT
        ),
        reason_code=(
            None
            if accept
            else CandidateRejectionReasonCode.INPUT_VALUE_INVALID
        ),
    )


def _accepted_delta_v2(
    *,
    candidate_ref: UUID,
    message_ref: UUID,
    accepted_delta_id: UUID | None = None,
    task_id: UUID | None = None,
    base_version: int | None = None,
    result_version: int = 1,
    accepted_at: datetime = NOW,
) -> AcceptedTaskDeltaV2:
    return AcceptedTaskDeltaV2(
        accepted_delta_id=accepted_delta_id or uuid4(),
        candidate_ref=candidate_ref,
        message_ref=message_ref,
        operation=TaskDeltaOperation.ADD_GOAL,
        goal_text="查询订单状态",
        input_binding_refs=(uuid4(),),
        accepted_at=accepted_at,
        task_id=task_id or uuid4(),
        base_task_state_version=base_version,
        result_task_state_version=result_version,
    )


def _build_v2(
    *,
    request_input: RequestUnderstandingInput,
    output: RequestUnderstandingOutputV2,
    authoritative_messages: object,
    candidate_validation: tuple[CandidateValidationRecordV2, ...],
    accepted_task_deltas: tuple[AcceptedTaskDeltaV2, ...],
    proposed_base_task_state_version: int | None = None,
    validated_task_state_version: int | None = None,
    next_move_candidate_ref: UUID | None = None,
    now: datetime = NOW,
) -> RequestUnderstandingClosureV2:
    return build_request_understanding_closure_v2(
        request_input=request_input,
        output=output,
        authoritative_messages=authoritative_messages,  # type: ignore[arg-type]
        request_understanding_record_id=uuid4(),
        candidate_validation=candidate_validation,
        accepted_task_deltas=accepted_task_deltas,
        proposed_base_task_state_version=proposed_base_task_state_version,
        validated_task_state_version=validated_task_state_version,
        next_move_candidate_ref=next_move_candidate_ref,
        now=now,
    )


def test_v2_builder_projects_unicode_quotes_to_safe_exact_provenance() -> None:
    message_ref = uuid4()
    run_id = uuid4()
    message = "前缀🙂订单 O-4242 后缀"
    resolved_quote = "🙂订单 O-4242"
    input_quote = "订单 O-4242"
    candidate_id = uuid4()
    request_input = _request_input_v2(
        message_ref=message_ref,
        message=message,
        run_id=run_id,
    )
    output = _output_v2(
        message_ref=message_ref,
        candidates=(
            _task_delta_v2(
                candidate_id=candidate_id,
                message_ref=message_ref,
                order_id="O-4242",
                source_quote=input_quote,
            ),
        ),
        resolved_quote=resolved_quote,
    )
    child = _accepted_delta_v2(
        candidate_ref=candidate_id,
        message_ref=message_ref,
    )

    closure = _build_v2(
        request_input=request_input,
        output=output,
        authoritative_messages={message_ref: message},
        candidate_validation=(_validation_v2(candidate_id, accept=True),),
        accepted_task_deltas=(child,),
        validated_task_state_version=child.result_task_state_version,
        next_move_candidate_ref=uuid4(),
    )

    durable_resolved = (
        closure.record.contextualization.resolved_reference_candidates[0]
    )
    durable_input = (
        closure.record.task_delta_candidates[0].input_candidates[0]
    )
    assert durable_resolved.source_span_start == message.index(resolved_quote)
    assert durable_resolved.source_span_end_exclusive == (
        message.index(resolved_quote) + len(resolved_quote)
    )
    assert durable_resolved.source_quote_sha256 == sha256(
        resolved_quote.encode("utf-8")
    ).hexdigest()
    assert durable_input.source_span_start == message.index(input_quote)
    assert durable_input.source_span_end_exclusive == (
        message.index(input_quote) + len(input_quote)
    )
    assert durable_input.source_quote_sha256 == sha256(
        input_quote.encode("utf-8")
    ).hexdigest()
    assert closure.record.run_id == run_id
    assert closure.record.model_input_schema_version == request_input.schema_version
    assert closure.record.model_output_schema_version == output.schema_version
    assert closure.record.created_at == NOW
    assert closure.accepted_task_deltas[0].accepted_at == NOW
    serialized = closure.model_dump_json()
    assert resolved_quote not in serialized
    assert input_quote not in serialized
    assert '"source_quote":' not in serialized


@pytest.mark.parametrize(
    ("message", "source_quote"),
    [
        ("请查 O-4242", "不存在 O-4242"),
        ("订单 O-4242，再看订单 O-4242", "订单 O-4242"),
        ("订单 O-4242", "订单 O-4242"),
        ("请查订单 O-4242", " 订单 O-4242 "),
        ("请查 订单 o-4242", "订单 O-4242"),
        ("请查 Ｏ-4242", "O-4242"),
    ],
)
def test_v2_builder_rejects_non_exact_unique_bounded_provenance(
    message: str,
    source_quote: str,
) -> None:
    message_ref = uuid4()
    candidate_id = uuid4()
    request_input = _request_input_v2(
        message_ref=message_ref,
        message=message,
    )
    output = _output_v2(
        message_ref=message_ref,
        candidates=(),
        resolved_quote=source_quote,
    )

    with pytest.raises(RequestUnderstandingV2Error) as caught:
        _build_v2(
            request_input=request_input,
            output=output,
            authoritative_messages={message_ref: message},
            candidate_validation=(),
            accepted_task_deltas=(),
        )

    assert (
        caught.value.reason_code
        is RequestUnderstandingAggregateFailureCodeV2.SOURCE_PROVENANCE_INVALID
    )
    assert source_quote not in str(caught.value)
    assert source_quote not in repr(caught.value)


def test_v2_builder_supports_zero_candidate_and_all_reject_closures() -> None:
    message_ref = uuid4()
    message = "请查询订单 O-4242"
    request_input = _request_input_v2(
        message_ref=message_ref,
        message=message,
    )
    empty_output = _output_v2(message_ref=message_ref, candidates=())

    empty = _build_v2(
        request_input=request_input,
        output=empty_output,
        authoritative_messages={message_ref: message},
        candidate_validation=(),
        accepted_task_deltas=(),
    )
    assert empty.record.task_delta_candidates == ()
    assert empty.record.candidate_validation == ()
    assert empty.record.accepted_delta_refs == ()

    candidate_id = uuid4()
    rejected_output = _output_v2(
        message_ref=message_ref,
        candidates=(
            _task_delta_v2(
                candidate_id=candidate_id,
                message_ref=message_ref,
                order_id="O-4242",
                source_quote="订单 O-4242",
            ),
        ),
    )
    rejected = _build_v2(
        request_input=request_input,
        output=rejected_output,
        authoritative_messages={message_ref: message},
        candidate_validation=(_validation_v2(candidate_id, accept=False),),
        accepted_task_deltas=(),
    )
    assert rejected.record.accepted_delta_refs == ()


def test_v2_builder_preserves_child_order_but_chains_by_emitted_candidates() -> None:
    message_ref = uuid4()
    message = "比较订单 O-4242 与订单 O-4343"
    first_id = uuid4()
    second_id = uuid4()
    request_input = _request_input_v2(
        message_ref=message_ref,
        message=message,
    )
    output = _output_v2(
        message_ref=message_ref,
        candidates=(
            _task_delta_v2(
                candidate_id=first_id,
                message_ref=message_ref,
                order_id="O-4242",
                source_quote="订单 O-4242",
            ),
            _task_delta_v2(
                candidate_id=second_id,
                message_ref=message_ref,
                order_id="O-4343",
                source_quote="订单 O-4343",
            ),
        ),
    )
    task_id = uuid4()
    first_child = _accepted_delta_v2(
        candidate_ref=first_id,
        message_ref=message_ref,
        task_id=task_id,
        base_version=None,
        result_version=1,
    )
    second_child = _accepted_delta_v2(
        candidate_ref=second_id,
        message_ref=message_ref,
        task_id=task_id,
        base_version=1,
        result_version=2,
    )

    closure = _build_v2(
        request_input=request_input,
        output=output,
        authoritative_messages={message_ref: message},
        candidate_validation=(
            _validation_v2(first_id, accept=True),
            _validation_v2(second_id, accept=True),
        ),
        accepted_task_deltas=(second_child, first_child),
        validated_task_state_version=2,
        next_move_candidate_ref=uuid4(),
    )

    assert closure.record.accepted_delta_refs == (
        second_child.accepted_delta_id,
        first_child.accepted_delta_id,
    )
    assert closure.accepted_task_deltas == (second_child, first_child)


def test_v2_builder_supports_partial_acceptance() -> None:
    message_ref = uuid4()
    message = "比较订单 O-4242 与订单 O-4343"
    accepted_id = uuid4()
    rejected_id = uuid4()
    request_input = _request_input_v2(
        message_ref=message_ref,
        message=message,
    )
    output = _output_v2(
        message_ref=message_ref,
        candidates=(
            _task_delta_v2(
                candidate_id=accepted_id,
                message_ref=message_ref,
                order_id="O-4242",
                source_quote="订单 O-4242",
            ),
            _task_delta_v2(
                candidate_id=rejected_id,
                message_ref=message_ref,
                order_id="O-4343",
                source_quote="订单 O-4343",
            ),
        ),
    )
    child = _accepted_delta_v2(
        candidate_ref=accepted_id,
        message_ref=message_ref,
    )

    closure = _build_v2(
        request_input=request_input,
        output=output,
        authoritative_messages={message_ref: message},
        candidate_validation=(
            _validation_v2(accepted_id, accept=True),
            _validation_v2(rejected_id, accept=False),
        ),
        accepted_task_deltas=(child,),
        validated_task_state_version=1,
        next_move_candidate_ref=uuid4(),
    )
    assert closure.record.accepted_delta_refs == (child.accepted_delta_id,)


@pytest.mark.parametrize(
    "case",
    [
        "missing_decision",
        "extra_decision",
        "duplicate_decision",
        "missing_child",
        "extra_child",
        "duplicate_child",
        "wrong_message",
        "wrong_time",
        "duplicate_accepted_id",
        "duplicate_pair",
    ],
)
def test_v2_builder_rejects_non_closed_decision_and_child_graphs(
    case: str,
) -> None:
    message_ref = uuid4()
    message = "比较订单 O-4242 与订单 O-4343"
    first_id = uuid4()
    second_id = uuid4()
    request_input = _request_input_v2(
        message_ref=message_ref,
        message=message,
    )
    output = _output_v2(
        message_ref=message_ref,
        candidates=(
            _task_delta_v2(
                candidate_id=first_id,
                message_ref=message_ref,
                order_id="O-4242",
                source_quote="订单 O-4242",
            ),
            _task_delta_v2(
                candidate_id=second_id,
                message_ref=message_ref,
                order_id="O-4343",
                source_quote="订单 O-4343",
            ),
        ),
    )
    first_validation = _validation_v2(first_id, accept=True)
    second_validation = _validation_v2(second_id, accept=True)
    first_child = _accepted_delta_v2(
        candidate_ref=first_id,
        message_ref=message_ref,
    )
    second_child = _accepted_delta_v2(
        candidate_ref=second_id,
        message_ref=message_ref,
    )
    validations = (first_validation, second_validation)
    children = (first_child, second_child)

    if case == "missing_decision":
        validations = (first_validation,)
    elif case == "extra_decision":
        validations += (_validation_v2(uuid4(), accept=False),)
    elif case == "duplicate_decision":
        validations = (first_validation, first_validation)
    elif case == "missing_child":
        children = (first_child,)
    elif case == "extra_child":
        children += (
            _accepted_delta_v2(
                candidate_ref=uuid4(),
                message_ref=message_ref,
            ),
        )
    elif case == "duplicate_child":
        children = (first_child, first_child)
    elif case == "wrong_message":
        children = (
            first_child,
            second_child.model_copy(update={"message_ref": uuid4()}),
        )
    elif case == "wrong_time":
        children = (
            first_child,
            second_child.model_copy(
                update={"accepted_at": datetime(2031, 1, 1, tzinfo=UTC)}
            ),
        )
    elif case == "duplicate_accepted_id":
        children = (
            first_child,
            second_child.model_copy(
                update={"accepted_delta_id": first_child.accepted_delta_id}
            ),
        )
    elif case == "duplicate_pair":
        children = (
            first_child,
            second_child.model_copy(
                update={
                    "accepted_delta_id": first_child.accepted_delta_id,
                    "task_id": first_child.task_id,
                }
            ),
        )

    with pytest.raises(RequestUnderstandingV2Error) as caught:
        _build_v2(
            request_input=request_input,
            output=output,
            authoritative_messages={message_ref: message},
            candidate_validation=validations,
            accepted_task_deltas=children,
            validated_task_state_version=1,
            next_move_candidate_ref=uuid4(),
        )
    assert (
        caught.value.reason_code
        is RequestUnderstandingAtomicFailureCodeV2.DURABLE_CLOSURE_COMMIT_FAILED
    )


@pytest.mark.parametrize(
    ("first_base", "first_result", "second_base", "second_result"),
    [
        (None, 1, None, 2),
        (None, 1, 1, 3),
        (None, 2, 2, 1),
        (None, 2, 1, 2),
    ],
)
def test_v2_builder_rejects_fork_gap_rollback_or_stale_task_chains(
    first_base: int | None,
    first_result: int,
    second_base: int | None,
    second_result: int,
) -> None:
    message_ref = uuid4()
    message = "比较订单 O-4242 与订单 O-4343"
    first_id = uuid4()
    second_id = uuid4()
    request_input = _request_input_v2(
        message_ref=message_ref,
        message=message,
    )
    output = _output_v2(
        message_ref=message_ref,
        candidates=(
            _task_delta_v2(
                candidate_id=first_id,
                message_ref=message_ref,
                order_id="O-4242",
                source_quote="订单 O-4242",
            ),
            _task_delta_v2(
                candidate_id=second_id,
                message_ref=message_ref,
                order_id="O-4343",
                source_quote="订单 O-4343",
            ),
        ),
    )
    task_id = uuid4()
    children = (
        _accepted_delta_v2(
            candidate_ref=first_id,
            message_ref=message_ref,
            task_id=task_id,
            base_version=first_base,
            result_version=first_result,
        ),
        _accepted_delta_v2(
            candidate_ref=second_id,
            message_ref=message_ref,
            task_id=task_id,
            base_version=second_base,
            result_version=second_result,
        ),
    )

    with pytest.raises(RequestUnderstandingV2Error) as caught:
        _build_v2(
            request_input=request_input,
            output=output,
            authoritative_messages={message_ref: message},
            candidate_validation=(
                _validation_v2(first_id, accept=True),
                _validation_v2(second_id, accept=True),
            ),
            accepted_task_deltas=children,
            validated_task_state_version=second_result,
            next_move_candidate_ref=uuid4(),
        )
    assert (
        caught.value.reason_code
        is RequestUnderstandingAtomicFailureCodeV2.DURABLE_CLOSURE_COMMIT_FAILED
    )


def test_v2_builder_requires_explicit_exact_canonical_input_instance() -> None:
    message_ref = uuid4()
    message = "查询订单 O-4242"
    canonical = _request_input_v2(
        message_ref=message_ref,
        message=message,
    )
    output = _output_v2(message_ref=message_ref, candidates=())

    class DerivedRequestUnderstandingInput(RequestUnderstandingInput):
        pass

    derived = DerivedRequestUnderstandingInput.model_validate(
        canonical.model_dump()
    )
    cases: tuple[object, ...] = (
        _request_input_v2(
            message_ref=message_ref,
            message=message,
            explicit_schema_version=False,
        ),
        canonical.model_dump(),
        derived,
    )
    for invalid_input in cases:
        with pytest.raises(RequestUnderstandingV2Error) as caught:
            _build_v2(
                request_input=invalid_input,  # type: ignore[arg-type]
                output=output,
                authoritative_messages={message_ref: message},
                candidate_validation=(),
                accepted_task_deltas=(),
            )
        assert (
            caught.value.reason_code
            is RequestUnderstandingAggregateFailureCodeV2.MODEL_INPUT_SCHEMA_INVALID
        )

    bypassed = RequestUnderstandingInput.model_construct(
        **{
            **canonical.model_dump(),
            "schema_version": "e2e01-thin-v9",
        },
        _fields_set=set(canonical.model_fields),
    )
    with pytest.raises(RequestUnderstandingV2Error) as caught:
        _build_v2(
            request_input=bypassed,
            output=output,
            authoritative_messages={message_ref: message},
            candidate_validation=(),
            accepted_task_deltas=(),
        )
    assert (
        caught.value.reason_code
        is RequestUnderstandingAggregateFailureCodeV2.MODEL_SCHEMA_VERSION_INVALID
    )


def test_v2_builder_revalidates_constructed_output_and_message_binding() -> None:
    message_ref = uuid4()
    message = "查询订单 O-4242"
    request_input = _request_input_v2(
        message_ref=message_ref,
        message=message,
    )
    output = _output_v2(message_ref=message_ref, candidates=())

    wrong_schema = RequestUnderstandingOutputV2.model_construct(
        **{**output.model_dump(), "schema_version": "e2e01-thin-v1"}
    )
    with pytest.raises(RequestUnderstandingV2Error) as caught:
        _build_v2(
            request_input=request_input,
            output=wrong_schema,
            authoritative_messages={message_ref: message},
            candidate_validation=(),
            accepted_task_deltas=(),
        )
    assert (
        caught.value.reason_code
        is RequestUnderstandingAggregateFailureCodeV2.MODEL_SCHEMA_VERSION_INVALID
    )

    invalid_next_move = output.next_move_candidate.model_copy(
        update={"base_task_state_version": 1}
    )
    non_null_base = RequestUnderstandingOutputV2.model_construct(
        **{
            **output.model_dump(),
            "next_move_candidate": invalid_next_move,
        }
    )
    with pytest.raises(RequestUnderstandingV2Error) as caught:
        _build_v2(
            request_input=request_input,
            output=non_null_base,
            authoritative_messages={message_ref: message},
            candidate_validation=(),
            accepted_task_deltas=(),
        )
    assert (
        caught.value.reason_code
        is RequestUnderstandingAggregateFailureCodeV2.MODEL_OUTPUT_SCHEMA_INVALID
    )

    mismatched_output = _output_v2(message_ref=uuid4(), candidates=())
    for bound_output, authoritative in (
        (mismatched_output, {message_ref: message}),
        (output, {message_ref: "不同的 authoritative 原文"}),
    ):
        with pytest.raises(RequestUnderstandingV2Error) as caught:
            _build_v2(
                request_input=request_input,
                output=bound_output,
                authoritative_messages=authoritative,
                candidate_validation=(),
                accepted_task_deltas=(),
            )
        assert (
            caught.value.reason_code
            is RequestUnderstandingAggregateFailureCodeV2.SOURCE_PROVENANCE_INVALID
        )


def test_v2_builder_requires_next_move_versions_to_close_without_ref() -> None:
    message_ref = uuid4()
    message = "查询订单 O-4242"
    request_input = _request_input_v2(
        message_ref=message_ref,
        message=message,
    )
    output = _output_v2(message_ref=message_ref, candidates=())

    with pytest.raises(RequestUnderstandingV2Error) as caught:
        _build_v2(
            request_input=request_input,
            output=output,
            authoritative_messages={message_ref: message},
            candidate_validation=(),
            accepted_task_deltas=(),
            proposed_base_task_state_version=1,
            next_move_candidate_ref=None,
        )
    assert (
        caught.value.reason_code
        is RequestUnderstandingAtomicFailureCodeV2.DURABLE_CLOSURE_COMMIT_FAILED
    )
