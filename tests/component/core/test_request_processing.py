from datetime import UTC, datetime, timedelta
from hashlib import sha256
import warnings
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from mini_agent.core.identity import CustomerContext
from mini_agent.core.request_processing import (
    InitialAcceptedTaskGraphV2,
    InitialRequestDecision,
    InitialRequestNoTaskDecisionV2,
    InitialRequestRoutableTaskGraphDecisionV2,
    InitialRequestUnroutedTaskGraphsDecisionV2,
    InitialTaskIdentityAllocationV2,
    RequestProcessingError,
    RequestUnderstandingClosureV2,
    RequestUnderstandingV2Error,
    RevalidatedNextMove,
    build_request_understanding_closure_v2,
    revalidate_next_move,
    revalidate_next_move_v2,
    validate_and_reduce_initial_request,
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
    RequestUnderstandingOutput,
    RequestUnderstandingOutputV2,
    ResolvedReferenceCandidateV2,
    TaskDeltaCandidate,
    TaskDeltaOperation,
    UncertaintyReasonCodeV2,
    UncertaintyV2,
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
    recent_message_refs: tuple[UUID, ...] = (),
    explicit_schema_version: bool = True,
) -> RequestUnderstandingInput:
    tool_spec = get_order_tool_spec()
    values: dict[str, object] = {
        "run_id": run_id or uuid4(),
        "message_ref": message_ref,
        "original_query": message,
        "recent_message_refs": recent_message_refs,
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
    goal_text: str = "查询订单状态",
) -> AcceptedTaskDeltaV2:
    return AcceptedTaskDeltaV2(
        accepted_delta_id=accepted_delta_id or uuid4(),
        candidate_ref=candidate_ref,
        message_ref=message_ref,
        operation=TaskDeltaOperation.ADD_GOAL,
        goal_text=goal_text,
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
        goal_text="查询 O-4242 的状态",
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
        goal_text="查询 O-4242 的状态",
    )
    second_child = _accepted_delta_v2(
        candidate_ref=second_id,
        message_ref=message_ref,
        task_id=task_id,
        base_version=1,
        result_version=2,
        goal_text="查询 O-4343 的状态",
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
        goal_text="查询 O-4242 的状态",
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
        _fields_set=set(RequestUnderstandingInput.model_fields),
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


def test_v2_builder_bounds_constructed_objects_with_missing_schema_fields() -> None:
    message_ref = uuid4()
    message = "查询订单 O-4242"
    canonical_input = _request_input_v2(
        message_ref=message_ref,
        message=message,
    )
    output = _output_v2(message_ref=message_ref, candidates=())
    input_values = canonical_input.model_dump()
    input_values.pop("schema_version")
    missing_input_schema = RequestUnderstandingInput.model_construct(
        **input_values,
        _fields_set=set(RequestUnderstandingInput.model_fields),
    )
    missing_output_schema = RequestUnderstandingOutputV2.model_construct(
        message_ref=output.message_ref,
        contextualization=output.contextualization,
        task_delta_candidates=output.task_delta_candidates,
        next_move_candidate=output.next_move_candidate,
        _fields_set=set(RequestUnderstandingOutputV2.model_fields),
    )

    with pytest.raises(RequestUnderstandingV2Error) as caught:
        _build_v2(
            request_input=missing_input_schema,
            output=output,
            authoritative_messages={message_ref: message},
            candidate_validation=(),
            accepted_task_deltas=(),
        )
    assert (
        caught.value.reason_code
        is RequestUnderstandingAggregateFailureCodeV2.MODEL_INPUT_SCHEMA_INVALID
    )

    with pytest.raises(RequestUnderstandingV2Error) as caught:
        _build_v2(
            request_input=canonical_input,
            output=missing_output_schema,
            authoritative_messages={message_ref: message},
            candidate_validation=(),
            accepted_task_deltas=(),
        )
    assert (
        caught.value.reason_code
        is RequestUnderstandingAggregateFailureCodeV2.MODEL_OUTPUT_SCHEMA_INVALID
    )


def test_v2_builder_rejects_noncanonical_nested_types_without_diagnostics(
    capsys: pytest.CaptureFixture[str],
) -> None:
    message_ref = uuid4()
    message = "查询订单 O-4242"
    raw_quote = "RAW-QUOTE-MARKER O-4242"
    request_input = _request_input_v2(
        message_ref=message_ref,
        message=message,
    )
    constructed_resolved = ResolvedReferenceCandidateV2.model_construct(
        name="order_id",
        candidate_value="O-4242",
        source_kind="CURRENT_MESSAGE",
        source_ref=message_ref,
        source_quote=raw_quote,
        confidence=0.9,
    )
    contextualization = QueryContextualizationCandidateV2(
        text="查询订单状态",
        resolved_reference_candidates=(constructed_resolved,),
        uncertainties=(),
        source_message_refs=(message_ref,),
    )
    output = RequestUnderstandingOutputV2(
        schema_version="e2e01-thin-v2",
        message_ref=message_ref,
        contextualization=contextualization,
        task_delta_candidates=(),
        next_move_candidate=NextMove(kind=NextMoveKind.ASK_USER),
    )

    with warnings.catch_warnings(record=True) as caught_warnings:
        warnings.simplefilter("always")
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
        is RequestUnderstandingAggregateFailureCodeV2.MODEL_OUTPUT_SCHEMA_INVALID
    )
    assert caught.value.__context__ is None
    assert caught_warnings == []
    captured = capsys.readouterr()
    assert raw_quote not in captured.out
    assert raw_quote not in captured.err
    assert raw_quote not in str(caught.value)
    assert raw_quote not in repr(caught.value)


@pytest.mark.parametrize(
    "case",
    [
        "unseen_recent",
        "current_kind_on_recent_ref",
        "recent_kind_on_current_ref",
    ],
)
def test_v2_builder_binds_reference_kind_to_actual_input_visible_scope(
    case: str,
) -> None:
    current_ref = uuid4()
    recent_ref = uuid4()
    current_message = "请查订单 O-4242"
    recent_message = "此前提到订单 O-4242"
    source_ref = recent_ref
    source_kind = ReferenceSourceKindV2.RECENT_MESSAGE
    recent_message_refs: tuple[UUID, ...] = ()
    source_quote = "订单 O-4242"
    context_refs = (current_ref, recent_ref)

    if case == "current_kind_on_recent_ref":
        source_kind = ReferenceSourceKindV2.CURRENT_MESSAGE
        recent_message_refs = (recent_ref,)
    elif case == "recent_kind_on_current_ref":
        source_ref = current_ref
        recent_message_refs = (recent_ref,)
        context_refs = (current_ref,)

    request_input = _request_input_v2(
        message_ref=current_ref,
        message=current_message,
        recent_message_refs=recent_message_refs,
    )
    output = RequestUnderstandingOutputV2(
        schema_version="e2e01-thin-v2",
        message_ref=current_ref,
        contextualization=QueryContextualizationCandidateV2(
            text="查询订单状态",
            resolved_reference_candidates=(
                ResolvedReferenceCandidateV2(
                    name="order_id",
                    candidate_value="O-4242",
                    source_kind=source_kind,
                    source_ref=source_ref,
                    source_quote=source_quote,
                    confidence=0.9,
                ),
            ),
            uncertainties=(),
            source_message_refs=context_refs,
        ),
        task_delta_candidates=(),
        next_move_candidate=NextMove(kind=NextMoveKind.ASK_USER),
    )

    with pytest.raises(RequestUnderstandingV2Error) as caught:
        _build_v2(
            request_input=request_input,
            output=output,
            authoritative_messages={
                current_ref: current_message,
                recent_ref: recent_message,
            },
            candidate_validation=(),
            accepted_task_deltas=(),
        )
    assert (
        caught.value.reason_code
        is RequestUnderstandingAggregateFailureCodeV2.SOURCE_PROVENANCE_INVALID
    )


def test_v2_builder_projects_an_authorized_recent_message_reference() -> None:
    current_ref = uuid4()
    recent_ref = uuid4()
    current_message = "请查询刚才提到的订单"
    recent_message = "此前提到订单 O-4242"
    source_quote = "订单 O-4242"
    request_input = _request_input_v2(
        message_ref=current_ref,
        message=current_message,
        recent_message_refs=(recent_ref,),
    )
    output = RequestUnderstandingOutputV2(
        schema_version="e2e01-thin-v2",
        message_ref=current_ref,
        contextualization=QueryContextualizationCandidateV2(
            text="查询订单 O-4242 的状态",
            resolved_reference_candidates=(
                ResolvedReferenceCandidateV2(
                    name="order_id",
                    candidate_value="O-4242",
                    source_kind=ReferenceSourceKindV2.RECENT_MESSAGE,
                    source_ref=recent_ref,
                    source_quote=source_quote,
                    confidence=0.9,
                ),
            ),
            uncertainties=(),
            source_message_refs=(current_ref, recent_ref),
        ),
        task_delta_candidates=(),
        next_move_candidate=NextMove(kind=NextMoveKind.ASK_USER),
    )

    closure = _build_v2(
        request_input=request_input,
        output=output,
        authoritative_messages={
            current_ref: current_message,
            recent_ref: recent_message,
        },
        candidate_validation=(),
        accepted_task_deltas=(),
    )

    durable = closure.record.contextualization.resolved_reference_candidates[0]
    assert durable.source_kind is ReferenceSourceKindV2.RECENT_MESSAGE
    assert durable.source_ref == recent_ref
    assert durable.source_span_start == recent_message.index(source_quote)
    assert durable.source_quote_sha256 == sha256(
        source_quote.encode("utf-8")
    ).hexdigest()


@pytest.mark.parametrize(
    "injection_site",
    [
        "input",
        "output",
        "nested",
        "decision",
        "child",
    ],
)
def test_v2_builder_rejects_trusted_fields_in_actual_model_instance_state(
    injection_site: str,
) -> None:
    message_ref = uuid4()
    message = "查询订单 O-4242"
    request_input = _request_input_v2(
        message_ref=message_ref,
        message=message,
    )
    output = _output_v2(message_ref=message_ref, candidates=())
    candidate_validation: tuple[CandidateValidationRecordV2, ...] = ()
    accepted_task_deltas: tuple[AcceptedTaskDeltaV2, ...] = ()

    if injection_site == "input":
        request_input = request_input.model_copy(
            update={"customer_id": "attacker-selected"}
        )
    elif injection_site == "output":
        output = output.model_copy(
            update={"owner_customer_id": "attacker-selected"}
        )
    elif injection_site == "nested":
        contextualization = output.contextualization.model_copy(
            update={"auth_scopes": ("orders:read",)}
        )
        output = output.model_copy(
            update={"contextualization": contextualization}
        )
    elif injection_site == "decision":
        candidate_validation = (
            _validation_v2(uuid4(), accept=False).model_copy(
                update={"run_id": uuid4()}
            ),
        )
    elif injection_site == "child":
        accepted_task_deltas = (
            _accepted_delta_v2(
                candidate_ref=uuid4(),
                message_ref=message_ref,
            ).model_copy(update={"customer_id": "attacker-selected"}),
        )

    with pytest.raises(RequestUnderstandingV2Error) as caught:
        _build_v2(
            request_input=request_input,
            output=output,
            authoritative_messages={message_ref: message},
            candidate_validation=candidate_validation,
            accepted_task_deltas=accepted_task_deltas,
        )

    assert (
        caught.value.reason_code
        is RequestUnderstandingAggregateFailureCodeV2.TRUSTED_OR_PRIVATE_FIELD_PRESENT
    )
    assert "attacker-selected" not in str(caught.value)
    assert "attacker-selected" not in repr(caught.value)


@pytest.mark.parametrize(
    ("injection_site", "expected_reason"),
    [
        (
            "input",
            RequestUnderstandingAggregateFailureCodeV2.MODEL_INPUT_SCHEMA_INVALID,
        ),
        (
            "output",
            RequestUnderstandingAggregateFailureCodeV2.MODEL_OUTPUT_SCHEMA_INVALID,
        ),
        (
            "nested",
            RequestUnderstandingAggregateFailureCodeV2.MODEL_OUTPUT_SCHEMA_INVALID,
        ),
        (
            "decision",
            RequestUnderstandingAtomicFailureCodeV2.DURABLE_CLOSURE_COMMIT_FAILED,
        ),
        (
            "child",
            RequestUnderstandingAtomicFailureCodeV2.DURABLE_CLOSURE_COMMIT_FAILED,
        ),
    ],
)
def test_v2_builder_rejects_any_undeclared_model_instance_state(
    injection_site: str,
    expected_reason: (
        RequestUnderstandingAggregateFailureCodeV2
        | RequestUnderstandingAtomicFailureCodeV2
    ),
) -> None:
    message_ref = uuid4()
    message = "查询订单 O-4242"
    request_input = _request_input_v2(
        message_ref=message_ref,
        message=message,
    )
    output = _output_v2(message_ref=message_ref, candidates=())
    candidate_validation: tuple[CandidateValidationRecordV2, ...] = ()
    accepted_task_deltas: tuple[AcceptedTaskDeltaV2, ...] = ()

    if injection_site == "input":
        request_input = request_input.model_copy(
            update={"unexpected_field": "unexpected-value"}
        )
    elif injection_site == "output":
        output = output.model_copy(
            update={"unexpected_field": "unexpected-value"}
        )
    elif injection_site == "nested":
        contextualization = output.contextualization.model_copy(
            update={"unexpected_field": "unexpected-value"}
        )
        output = output.model_copy(
            update={"contextualization": contextualization}
        )
    elif injection_site == "decision":
        candidate_validation = (
            _validation_v2(uuid4(), accept=False).model_copy(
                update={"unexpected_field": "unexpected-value"}
            ),
        )
    elif injection_site == "child":
        accepted_task_deltas = (
            _accepted_delta_v2(
                candidate_ref=uuid4(),
                message_ref=message_ref,
            ).model_copy(
                update={"unexpected_field": "unexpected-value"}
            ),
        )

    with pytest.raises(RequestUnderstandingV2Error) as caught:
        _build_v2(
            request_input=request_input,
            output=output,
            authoritative_messages={message_ref: message},
            candidate_validation=candidate_validation,
            accepted_task_deltas=accepted_task_deltas,
        )

    assert caught.value.reason_code is expected_reason


def _identity_allocation_v2(
    candidate_ref: UUID,
) -> InitialTaskIdentityAllocationV2:
    return InitialTaskIdentityAllocationV2(
        candidate_ref=candidate_ref,
        accepted_delta_id=uuid4(),
        task_id=uuid4(),
        request_unit_id=uuid4(),
        binding_id=uuid4(),
    )


def _initial_output_v2(
    *,
    message_ref: UUID,
    candidates: tuple[TaskDeltaCandidate, ...],
    uncertainties: tuple[UncertaintyV2, ...] = (),
    next_move: NextMove | None = None,
) -> RequestUnderstandingOutputV2:
    return RequestUnderstandingOutputV2(
        schema_version="e2e01-thin-v2",
        message_ref=message_ref,
        contextualization=QueryContextualizationCandidateV2(
            text="确定性处理当前订单查询",
            resolved_reference_candidates=(),
            uncertainties=uncertainties,
            source_message_refs=(message_ref,),
        ),
        task_delta_candidates=candidates,
        next_move_candidate=next_move
        or NextMove(
            kind=NextMoveKind.CALL_TOOL,
            requested_tool_name="get_order",
            arguments={"order_id": "O-4242"},
            base_task_state_version=None,
        ),
    )


def _reduce_initial_v2(
    *,
    message: str,
    output: RequestUnderstandingOutputV2,
    allocations: tuple[InitialTaskIdentityAllocationV2, ...] | None = None,
    request_understanding_record_id: UUID | None = None,
    next_move_candidate_ref: UUID | None = None,
    now: datetime = NOW,
) -> (
    InitialRequestNoTaskDecisionV2
    | InitialRequestRoutableTaskGraphDecisionV2
    | InitialRequestUnroutedTaskGraphsDecisionV2
):
    return validate_and_reduce_initial_request_v2(
        request_input=_request_input_v2(
            message_ref=output.message_ref,
            message=message,
        ),
        output=output,
        authoritative_messages={output.message_ref: message},
        customer_context=_customer_context(),
        request_understanding_record_id=(
            request_understanding_record_id or uuid4()
        ),
        candidate_identity_allocations=(
            allocations
            if allocations is not None
            else tuple(
                _identity_allocation_v2(candidate.candidate_id)
                for candidate in output.task_delta_candidates
            )
        ),
        next_move_candidate_ref=next_move_candidate_ref or uuid4(),
        now=now,
    )


def test_v2_initial_decision_adds_only_the_declared_exact_core_surface() -> None:
    assert set(InitialTaskIdentityAllocationV2.model_fields) == {
        "candidate_ref",
        "accepted_delta_id",
        "task_id",
        "request_unit_id",
        "binding_id",
    }
    assert set(InitialAcceptedTaskGraphV2.model_fields) == {
        "accepted_delta",
        "input_binding",
        "task",
        "request_unit",
    }
    assert set(InitialRequestNoTaskDecisionV2.model_fields) == {"closure"}
    assert set(InitialRequestRoutableTaskGraphDecisionV2.model_fields) == {
        "closure",
        "task_graph",
        "next_move_candidate_ref",
        "next_move_candidate",
    }
    assert set(InitialRequestUnroutedTaskGraphsDecisionV2.model_fields) == {
        "closure",
        "task_graphs",
    }


def test_v2_initial_decision_closes_zero_and_all_reject_without_task() -> None:
    message_ref = uuid4()
    zero = _reduce_initial_v2(
        message="请帮我看看订单",
        output=_initial_output_v2(
            message_ref=message_ref,
            candidates=(),
        ),
    )

    assert type(zero) is InitialRequestNoTaskDecisionV2
    assert zero.closure.record.candidate_validation == ()
    assert zero.closure.record.accepted_delta_refs == ()
    assert zero.closure.accepted_task_deltas == ()
    assert zero.closure.record.next_move_candidate_ref is None
    assert zero.closure.record.proposed_base_task_state_version is None
    assert zero.closure.record.validated_task_state_version is None

    invalid_id = uuid4()
    rejected = _reduce_initial_v2(
        message="请查询订单 not-an-order",
        output=_initial_output_v2(
            message_ref=message_ref,
            candidates=(
                _task_delta_v2(
                    candidate_id=invalid_id,
                    message_ref=message_ref,
                    order_id="not-an-order",
                    source_quote="订单 not-an-order",
                ),
            ),
        ),
    )

    assert type(rejected) is InitialRequestNoTaskDecisionV2
    assert rejected.closure.record.candidate_validation == (
        CandidateValidationRecordV2(
            candidate_ref=invalid_id,
            decision=CandidateValidationDecision.REJECT,
            reason_code=CandidateRejectionReasonCode.INPUT_VALUE_INVALID,
        ),
    )
    assert rejected.closure.accepted_task_deltas == ()


def test_v2_initial_decision_builds_exact_one_routable_initial_graph() -> None:
    message_ref = uuid4()
    candidate_id = uuid4()
    next_move_ref = uuid4()
    output = _initial_output_v2(
        message_ref=message_ref,
        candidates=(
            _task_delta_v2(
                candidate_id=candidate_id,
                message_ref=message_ref,
                order_id="o-4242",
                source_quote="订单 o-4242",
            ),
        ),
        next_move=NextMove(
            kind=NextMoveKind.CALL_TOOL,
            requested_tool_name="unknown_provider_tool",
            arguments={"order_id": "O-9999"},
            base_task_state_version=None,
        ),
    )

    result = _reduce_initial_v2(
        message="请查询订单 o-4242",
        output=output,
        next_move_candidate_ref=next_move_ref,
    )

    assert type(result) is InitialRequestRoutableTaskGraphDecisionV2
    graph = result.task_graph
    record = result.closure.record
    assert record.candidate_validation == (
        CandidateValidationRecordV2(
            candidate_ref=candidate_id,
            decision=CandidateValidationDecision.ACCEPT,
        ),
    )
    assert result.closure.accepted_task_deltas == (graph.accepted_delta,)
    assert record.accepted_delta_refs == (
        graph.accepted_delta.accepted_delta_id,
    )
    assert graph.accepted_delta.task_id == graph.task.task_id
    assert graph.accepted_delta.base_task_state_version is None
    assert graph.accepted_delta.result_task_state_version == 1
    assert graph.accepted_delta.input_binding_refs == (
        graph.input_binding.binding_id,
    )
    assert graph.request_unit.task_id == graph.task.task_id
    assert graph.request_unit.input_binding_refs == (
        graph.input_binding.binding_id,
    )
    assert graph.input_binding.normalized_value == "O-4242"
    assert graph.task.owner_customer_id == "customer-A"
    assert graph.task.status is TaskStatus.ACTIVE
    assert graph.task.state_version == 1
    assert graph.task.last_outcome_ref is None
    assert graph.request_unit.contextualization_ref is None
    assert graph.request_unit.constraint_refs == ()
    assert graph.request_unit.dependency_refs == ()
    assert graph.request_unit.open_questions == ()
    assert graph.request_unit.observation_refs == ()
    assert graph.request_unit.evidence_binding_refs == ()
    assert graph.request_unit.pending_action_ref is None
    assert graph.request_unit.result_refs == ()
    assert graph.input_binding.supersedes is None
    assert {
        record.created_at,
        graph.accepted_delta.accepted_at,
        graph.input_binding.created_at,
        graph.input_binding.updated_at,
        graph.task.created_at,
        graph.task.updated_at,
        graph.request_unit.created_at,
        graph.request_unit.updated_at,
    } == {NOW}
    assert result.next_move_candidate_ref == next_move_ref
    assert result.next_move_candidate == output.next_move_candidate
    assert record.next_move_candidate_ref == next_move_ref
    assert record.proposed_base_task_state_version is None
    assert record.validated_task_state_version == 1


def test_v2_initial_decision_preserves_partial_effect_but_discards_next_move() -> None:
    message_ref = uuid4()
    accepted_id = uuid4()
    rejected_id = uuid4()
    result = _reduce_initial_v2(
        message="比较订单 O-4242 与订单 invalid-order",
        output=_initial_output_v2(
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
                    order_id="invalid-order",
                    source_quote="订单 invalid-order",
                ),
            ),
        ),
    )

    assert type(result) is InitialRequestUnroutedTaskGraphsDecisionV2
    assert tuple(
        decision.decision
        for decision in result.closure.record.candidate_validation
    ) == (
        CandidateValidationDecision.ACCEPT,
        CandidateValidationDecision.REJECT,
    )
    assert result.closure.record.candidate_validation[1].reason_code is (
        CandidateRejectionReasonCode.INPUT_VALUE_INVALID
    )
    assert len(result.task_graphs) == 1
    assert (
        result.task_graphs[0].accepted_delta.candidate_ref == accepted_id
    )
    assert result.closure.record.next_move_candidate_ref is None
    assert result.closure.record.proposed_base_task_state_version is None
    assert result.closure.record.validated_task_state_version is None
    assert "next_move_candidate" not in type(result).model_fields


def test_v2_initial_decision_accepts_each_independent_multi_candidate() -> None:
    message_ref = uuid4()
    first_id = uuid4()
    second_id = uuid4()
    result = _reduce_initial_v2(
        message="比较订单 O-4242 与订单 O-4343",
        output=_initial_output_v2(
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
        ),
    )

    assert type(result) is InitialRequestUnroutedTaskGraphsDecisionV2
    assert tuple(
        decision.decision
        for decision in result.closure.record.candidate_validation
    ) == (
        CandidateValidationDecision.ACCEPT,
        CandidateValidationDecision.ACCEPT,
    )
    assert tuple(
        graph.accepted_delta.candidate_ref for graph in result.task_graphs
    ) == (first_id, second_id)
    assert len({graph.task.task_id for graph in result.task_graphs}) == 2
    assert all(
        graph.accepted_delta.base_task_state_version is None
        and graph.accepted_delta.result_task_state_version == 1
        for graph in result.task_graphs
    )
    assert result.closure.accepted_task_deltas == tuple(
        graph.accepted_delta for graph in result.task_graphs
    )
    assert result.closure.record.next_move_candidate_ref is None


@pytest.mark.parametrize(
    ("reason", "candidate_values", "expected"),
    [
        (
            UncertaintyReasonCodeV2.MISSING_REFERENCE,
            (),
            CandidateRejectionReasonCode.REFERENCE_UNRESOLVED,
        ),
        (
            UncertaintyReasonCodeV2.MULTIPLE_PLAUSIBLE_REFERENCES,
            ("O-4242", "O-4343"),
            CandidateRejectionReasonCode.REFERENCE_AMBIGUOUS,
        ),
    ],
)
def test_v2_initial_decision_maps_reference_uncertainty_to_stable_reject(
    reason: UncertaintyReasonCodeV2,
    candidate_values: tuple[str, ...],
    expected: CandidateRejectionReasonCode,
) -> None:
    message_ref = uuid4()
    candidate_id = uuid4()
    result = _reduce_initial_v2(
        message="请查询订单 O-4242",
        output=_initial_output_v2(
            message_ref=message_ref,
            candidates=(
                _task_delta_v2(
                    candidate_id=candidate_id,
                    message_ref=message_ref,
                    order_id="O-4242",
                    source_quote="订单 O-4242",
                ),
            ),
            uncertainties=(
                UncertaintyV2(
                    name="order_id",
                    candidate_values=candidate_values,
                    reason_code=reason,
                    source_message_refs=(message_ref,),
                ),
            ),
        ),
    )

    assert type(result) is InitialRequestNoTaskDecisionV2
    assert result.closure.record.candidate_validation[0].reason_code is expected


def test_v2_initial_decision_does_not_downgrade_bypassed_input_shape() -> None:
    message_ref = uuid4()
    candidate_id = uuid4()
    malformed_shape = _task_delta_v2(
        candidate_id=candidate_id,
        message_ref=message_ref,
        order_id="O-4242",
        source_quote="订单 O-4242",
    ).model_copy(
        update={
            "input_candidates": (
                _task_delta_v2(
                    candidate_id=uuid4(),
                    message_ref=message_ref,
                    order_id="O-4242",
                    source_quote="订单 O-4242",
                ).input_candidates[0].model_copy(
                    update={"semantic_role": "OTHER_ROLE"}
                ),
            )
        }
    )

    with pytest.raises(RequestUnderstandingV2Error) as caught:
        _reduce_initial_v2(
            message="请查询订单 O-4242",
            output=_initial_output_v2(
                message_ref=message_ref,
                candidates=(malformed_shape,),
            ),
        )

    assert caught.value.reason_code is (
        RequestUnderstandingAggregateFailureCodeV2.MODEL_OUTPUT_SCHEMA_INVALID
    )


def test_v2_initial_decision_identity_allocation_failure_is_atomic() -> None:
    message_ref = uuid4()
    first_id = uuid4()
    second_id = uuid4()
    output = _initial_output_v2(
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
    first = _identity_allocation_v2(first_id)
    colliding = _identity_allocation_v2(second_id).model_copy(
        update={"task_id": first.task_id}
    )

    for allocations in ((first,), (first, colliding)):
        with pytest.raises(RequestUnderstandingV2Error) as caught:
            _reduce_initial_v2(
                message="比较订单 O-4242 与订单 O-4343",
                output=output,
                allocations=allocations,
            )
        assert caught.value.reason_code is (
            RequestUnderstandingAtomicFailureCodeV2.DURABLE_CLOSURE_COMMIT_FAILED
        )
        assert caught.value.__cause__ is None
        assert caught.value.__context__ is None


def test_v2_initial_decision_noncanonical_base_remains_aggregate_invalid() -> None:
    message_ref = uuid4()
    output = _initial_output_v2(
        message_ref=message_ref,
        candidates=(),
    )
    invalid_next_move = output.next_move_candidate.model_copy(
        update={"base_task_state_version": 1}
    )
    bypassed = RequestUnderstandingOutputV2.model_construct(
        **{
            **output.model_dump(),
            "next_move_candidate": invalid_next_move,
        }
    )

    with pytest.raises(RequestUnderstandingV2Error) as caught:
        _reduce_initial_v2(
            message="请帮我看看订单",
            output=bypassed,
        )

    assert caught.value.reason_code is (
        RequestUnderstandingAggregateFailureCodeV2.MODEL_OUTPUT_SCHEMA_INVALID
    )


def test_v2_next_move_revalidation_preserves_unknown_tool_and_substitution() -> None:
    message_ref = uuid4()
    candidate_id = uuid4()
    result = _reduce_initial_v2(
        message="请查询订单 O-4242",
        output=_initial_output_v2(
            message_ref=message_ref,
            candidates=(
                _task_delta_v2(
                    candidate_id=candidate_id,
                    message_ref=message_ref,
                    order_id="O-4242",
                    source_quote="订单 O-4242",
                ),
            ),
            next_move=NextMove(
                kind=NextMoveKind.CALL_TOOL,
                requested_tool_name="unknown_provider_tool",
                arguments={"order_id": "O-9999"},
                base_task_state_version=None,
            ),
        ),
    )
    assert type(result) is InitialRequestRoutableTaskGraphDecisionV2

    move = revalidate_next_move_v2(
        decision=result,
        current_task=result.task_graph.task,
        current_request_unit=result.task_graph.request_unit,
        current_input_binding=result.task_graph.input_binding,
    )

    assert move.requested_provider_tool_name == "unknown_provider_tool"
    assert move.candidate_arguments["order_id"] == "O-9999"
    assert move.normalized_candidate_order_id == "O-9999"
    assert move.binding_normalized_value == "O-4242"
    assert move.argument_binding_refs == (
        result.task_graph.input_binding.binding_id,
    )
    assert move.proposed_base_task_state_version is None
    assert move.validated_task_state_version == 1


def test_v2_next_move_revalidation_rejects_stale_owner_or_non_call_tool() -> None:
    message_ref = uuid4()
    candidate_id = uuid4()
    result = _reduce_initial_v2(
        message="请查询订单 O-4242",
        output=_initial_output_v2(
            message_ref=message_ref,
            candidates=(
                _task_delta_v2(
                    candidate_id=candidate_id,
                    message_ref=message_ref,
                    order_id="O-4242",
                    source_quote="订单 O-4242",
                ),
            ),
        ),
    )
    assert type(result) is InitialRequestRoutableTaskGraphDecisionV2

    with pytest.raises(RequestProcessingError, match="owner"):
        revalidate_next_move_v2(
            decision=result,
            current_task=result.task_graph.task.model_copy(
                update={"owner_customer_id": "customer-B"}
            ),
            current_request_unit=result.task_graph.request_unit,
            current_input_binding=result.task_graph.input_binding,
        )
    with pytest.raises(RequestProcessingError, match="ACTIVE/v1"):
        revalidate_next_move_v2(
            decision=result,
            current_task=result.task_graph.task.model_copy(
                update={"state_version": 2}
            ),
            current_request_unit=result.task_graph.request_unit,
            current_input_binding=result.task_graph.input_binding,
        )

    ask_user = _reduce_initial_v2(
        message="请查询订单 O-4242",
        output=_initial_output_v2(
            message_ref=message_ref,
            candidates=(
                _task_delta_v2(
                    candidate_id=uuid4(),
                    message_ref=message_ref,
                    order_id="O-4242",
                    source_quote="订单 O-4242",
                ),
            ),
            next_move=NextMove(kind=NextMoveKind.ASK_USER),
        ),
    )
    assert type(ask_user) is InitialRequestRoutableTaskGraphDecisionV2
    with pytest.raises(RequestProcessingError, match="CALL_TOOL"):
        revalidate_next_move_v2(
            decision=ask_user,
            current_task=ask_user.task_graph.task,
            current_request_unit=ask_user.task_graph.request_unit,
            current_input_binding=ask_user.task_graph.input_binding,
        )


def test_v2_initial_task_graph_model_rejects_non_initial_state() -> None:
    message_ref = uuid4()
    candidate_id = uuid4()
    result = _reduce_initial_v2(
        message="请查询订单 O-4242",
        output=_initial_output_v2(
            message_ref=message_ref,
            candidates=(
                _task_delta_v2(
                    candidate_id=candidate_id,
                    message_ref=message_ref,
                    order_id="O-4242",
                    source_quote="订单 O-4242",
                ),
            ),
        ),
    )
    assert type(result) is InitialRequestRoutableTaskGraphDecisionV2

    with pytest.raises(ValidationError, match="initial"):
        InitialAcceptedTaskGraphV2(
            accepted_delta=result.task_graph.accepted_delta,
            input_binding=result.task_graph.input_binding.model_copy(
                update={"supersedes": uuid4()}
            ),
            task=result.task_graph.task,
            request_unit=result.task_graph.request_unit,
        )


def test_v2_routable_decision_rejects_joint_binding_and_next_move_substitution() -> None:
    message_ref = uuid4()
    candidate_id = uuid4()
    result = _reduce_initial_v2(
        message="请查询订单 O-4242",
        output=_initial_output_v2(
            message_ref=message_ref,
            candidates=(
                _task_delta_v2(
                    candidate_id=candidate_id,
                    message_ref=message_ref,
                    order_id="O-4242",
                    source_quote="订单 O-4242",
                ),
            ),
        ),
    )
    assert type(result) is InitialRequestRoutableTaskGraphDecisionV2
    binding_values = result.task_graph.input_binding.model_dump(mode="python")
    binding_values["normalized_value"] = "O-9999"
    tampered_binding = type(result.task_graph.input_binding)(**binding_values)
    tampered_graph = InitialAcceptedTaskGraphV2(
        accepted_delta=result.task_graph.accepted_delta,
        input_binding=tampered_binding,
        task=result.task_graph.task,
        request_unit=result.task_graph.request_unit,
    )
    tampered_next_move = NextMove(
        kind=NextMoveKind.CALL_TOOL,
        requested_tool_name="get_order",
        arguments={"order_id": "O-9999"},
        base_task_state_version=None,
    )

    with pytest.raises(ValidationError, match="Candidate InputBinding"):
        InitialRequestRoutableTaskGraphDecisionV2(
            closure=result.closure,
            task_graph=tampered_graph,
            next_move_candidate_ref=result.next_move_candidate_ref,
            next_move_candidate=tampered_next_move,
        )

    bypassed = result.model_copy(
        update={
            "task_graph": tampered_graph,
            "next_move_candidate": tampered_next_move,
        }
    )
    with pytest.raises(RequestProcessingError, match="canonical"):
        revalidate_next_move_v2(
            decision=bypassed,
            current_task=tampered_graph.task,
            current_request_unit=tampered_graph.request_unit,
            current_input_binding=tampered_binding,
        )


def test_v2_unrouted_closure_rejects_child_bound_to_rejected_candidate() -> None:
    message_ref = uuid4()
    accepted_id = uuid4()
    rejected_id = uuid4()
    result = _reduce_initial_v2(
        message="比较订单 O-4242 与订单 invalid-order",
        output=_initial_output_v2(
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
                    order_id="invalid-order",
                    source_quote="订单 invalid-order",
                ),
            ),
        ),
    )
    assert type(result) is InitialRequestUnroutedTaskGraphsDecisionV2
    original_child = result.closure.accepted_task_deltas[0]
    child_values = original_child.model_dump(mode="python")
    child_values["candidate_ref"] = rejected_id
    tampered_child = AcceptedTaskDeltaV2(**child_values)

    with pytest.raises(ValidationError, match="accepted Candidate set"):
        RequestUnderstandingClosureV2(
            record=result.closure.record,
            accepted_task_deltas=(tampered_child,),
        )


def test_v2_decision_closure_rejects_parent_child_clock_drift() -> None:
    message_ref = uuid4()
    candidate_id = uuid4()
    result = _reduce_initial_v2(
        message="请查询订单 O-4242",
        output=_initial_output_v2(
            message_ref=message_ref,
            candidates=(
                _task_delta_v2(
                    candidate_id=candidate_id,
                    message_ref=message_ref,
                    order_id="O-4242",
                    source_quote="订单 O-4242",
                ),
            ),
        ),
    )
    assert type(result) is InitialRequestRoutableTaskGraphDecisionV2
    record_values = result.closure.record.model_dump(mode="python")
    record_values["created_at"] = (
        result.closure.record.created_at + timedelta(seconds=1)
    )
    drifted_record = type(result.closure.record)(**record_values)

    with pytest.raises(ValidationError, match="trusted timestamp"):
        RequestUnderstandingClosureV2(
            record=drifted_record,
            accepted_task_deltas=result.closure.accepted_task_deltas,
        )
