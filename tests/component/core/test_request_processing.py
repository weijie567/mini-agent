import ast
import gc
import pickle
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
import warnings
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

import mini_agent.core.request_processing as request_processing_module
import mini_agent.core.request_understanding as request_understanding_module
import mini_agent.core.task_state as task_state_module
from mini_agent.core.identity import CustomerContext
from mini_agent.core.request_processing import (
    InitialAcceptedTaskGraphV2,
    InitialRequestNoTaskDecisionV2,
    InitialRequestRoutableTaskGraphDecisionV2,
    InitialRequestUnroutedTaskGraphsDecisionV2,
    InitialTaskIdentityAllocationV2,
    RequestProcessingError,
    RequestUnderstandingClosureV2,
    RequestUnderstandingV2Error,
    RevalidatedNextMove,
    build_request_understanding_closure_v2,
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


def test_v2_routable_decision_rejects_next_move_only_substitution() -> None:
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
            next_move=NextMove(kind=NextMoveKind.ASK_USER),
        ),
    )
    assert type(result) is InitialRequestRoutableTaskGraphDecisionV2
    replacement = NextMove(
        kind=NextMoveKind.CALL_TOOL,
        requested_tool_name="get_order",
        arguments={"order_id": "O-4242"},
        base_task_state_version=None,
    )
    substituted = result.model_copy(
        update={"next_move_candidate": replacement}
    )

    with pytest.raises(RequestProcessingError, match="canonical"):
        revalidate_next_move_v2(
            decision=substituted,
            current_task=result.task_graph.task,
            current_request_unit=result.task_graph.request_unit,
            current_input_binding=result.task_graph.input_binding,
        )

    with pytest.raises(ValidationError, match="Reducer"):
        InitialRequestRoutableTaskGraphDecisionV2(
            closure=result.closure,
            task_graph=result.task_graph,
            next_move_candidate_ref=result.next_move_candidate_ref,
            next_move_candidate=replacement,
        )

    payload = result.model_dump(mode="python")
    payload["next_move_candidate"] = replacement
    with pytest.raises(ValidationError, match="Reducer"):
        InitialRequestRoutableTaskGraphDecisionV2.model_validate(payload)

    with pytest.raises(TypeError, match="immutable"):
        substituted._reducer_next_move_fingerprint = "forged"

    nested_poisoned = result.model_copy(deep=True)
    nested_poisoned.next_move_candidate.__dict__.update(
        replacement.__dict__
    )
    with pytest.raises(RequestProcessingError, match="canonical"):
        revalidate_next_move_v2(
            decision=nested_poisoned,
            current_task=result.task_graph.task,
            current_request_unit=result.task_graph.request_unit,
            current_input_binding=result.task_graph.input_binding,
        )

    for copied in (
        result.model_copy(deep=True),
        pickle.loads(pickle.dumps(result)),
    ):
        with pytest.raises(RequestProcessingError, match="CALL_TOOL"):
            revalidate_next_move_v2(
                decision=copied,
                current_task=result.task_graph.task,
                current_request_unit=result.task_graph.request_unit,
                current_input_binding=result.task_graph.input_binding,
            )


def test_v2_routable_decision_rejects_self_issued_provenance_seals() -> None:
    message_ref = uuid4()
    result = _reduce_initial_v2(
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
    assert type(result) is InitialRequestRoutableTaskGraphDecisionV2
    replacement = NextMove(
        kind=NextMoveKind.CALL_TOOL,
        requested_tool_name="get_order",
        arguments={"order_id": "O-4242"},
        base_task_state_version=None,
    )
    replacement_fingerprint = sha256(
        replacement.model_dump_json(
            round_trip=True,
            warnings="error",
        ).encode("utf-8")
    ).hexdigest()

    substituted = result.model_copy(
        update={"next_move_candidate": replacement}
    )
    substituted.__pydantic_private__[
        "_reducer_next_move_fingerprint"
    ] = replacement_fingerprint
    with pytest.raises(RequestProcessingError, match="canonical"):
        revalidate_next_move_v2(
            decision=substituted,
            current_task=result.task_graph.task,
            current_request_unit=result.task_graph.request_unit,
            current_input_binding=result.task_graph.input_binding,
        )

    constructed = InitialRequestRoutableTaskGraphDecisionV2.model_construct(
        closure=result.closure,
        task_graph=result.task_graph,
        next_move_candidate_ref=result.next_move_candidate_ref,
        next_move_candidate=replacement,
    )
    constructed.__pydantic_private__[
        "_reducer_next_move_fingerprint"
    ] = replacement_fingerprint
    with pytest.raises(RequestProcessingError, match="canonical"):
        revalidate_next_move_v2(
            decision=constructed,
            current_task=result.task_graph.task,
            current_request_unit=result.task_graph.request_unit,
            current_input_binding=result.task_graph.input_binding,
        )

    payload = result.model_dump(mode="python")
    payload["next_move_candidate"] = replacement
    context_key = getattr(
        request_processing_module,
        "_INITIAL_ROUTABLE_DECISION_CONTEXT_KEY",
        "retired-internal-context-key",
    )
    context_token = getattr(
        request_processing_module,
        "_INITIAL_ROUTABLE_DECISION_TOKEN",
        object(),
    )
    with pytest.raises(ValidationError, match="Reducer"):
        InitialRequestRoutableTaskGraphDecisionV2.model_validate(
            payload,
            context={context_key: context_token},
        )
    assert not hasattr(
        request_processing_module,
        "_INITIAL_ROUTABLE_DECISION_CONTEXT_KEY",
    )
    assert not hasattr(
        request_processing_module,
        "_INITIAL_ROUTABLE_DECISION_TOKEN",
    )
    assert not hasattr(request_processing_module, "token_bytes")


@pytest.mark.parametrize(
    ("target_name", "field_name", "operation"),
    (
        ("task", "owner_customer_id", "discard"),
        ("task", "last_outcome_ref", "add"),
        ("request_unit", "task_id", "discard"),
        ("input_binding", "authority", "discard"),
        ("next_move", "kind", "discard"),
    ),
)
def test_v2_routable_decision_rejects_nested_fields_set_mutation(
    target_name: str,
    field_name: str,
    operation: str,
) -> None:
    message_ref = uuid4()
    result = _reduce_initial_v2(
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
        ),
    )
    assert type(result) is InitialRequestRoutableTaskGraphDecisionV2
    poisoned = result.model_copy(deep=True)
    targets = {
        "task": poisoned.task_graph.task,
        "request_unit": poisoned.task_graph.request_unit,
        "input_binding": poisoned.task_graph.input_binding,
        "next_move": poisoned.next_move_candidate,
    }
    target = targets[target_name]
    if operation == "add":
        target.__pydantic_fields_set__.add(field_name)
    else:
        target.__pydantic_fields_set__.discard(field_name)

    with pytest.raises(RequestProcessingError, match="canonical"):
        revalidate_next_move_v2(
            decision=poisoned,
            current_task=poisoned.task_graph.task,
            current_request_unit=poisoned.task_graph.request_unit,
            current_input_binding=poisoned.task_graph.input_binding,
        )


def test_v2_routable_decision_rejects_nested_scalar_subclasses() -> None:
    class DatetimeSubclass(datetime):
        pass

    class UUIDSubclass(UUID):
        pass

    message_ref = uuid4()
    result = _reduce_initial_v2(
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
        ),
    )
    assert type(result) is InitialRequestRoutableTaskGraphDecisionV2

    poisoned_clock = result.model_copy(deep=True)
    poisoned_now = DatetimeSubclass.fromtimestamp(
        poisoned_clock.task_graph.task.created_at.timestamp(),
        tz=UTC,
    )
    poisoned_clock.task_graph.task.__dict__["created_at"] = poisoned_now
    poisoned_clock.task_graph.task.__dict__["updated_at"] = poisoned_now

    poisoned_binding = result.model_copy(deep=True)
    poisoned_binding.task_graph.input_binding.__dict__["binding_id"] = (
        UUIDSubclass(str(poisoned_binding.task_graph.input_binding.binding_id))
    )

    for poisoned in (poisoned_clock, poisoned_binding):
        with pytest.raises(RequestProcessingError, match="canonical"):
            revalidate_next_move_v2(
                decision=poisoned,
                current_task=poisoned.task_graph.task,
                current_request_unit=poisoned.task_graph.request_unit,
                current_input_binding=poisoned.task_graph.input_binding,
            )


def test_v2_routable_decision_rejects_fields_set_and_json_leaf_subclasses() -> None:
    class StrSubclass(str):
        pass

    class DictSubclass(dict):
        pass

    message_ref = uuid4()
    result = _reduce_initial_v2(
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
        ),
    )
    assert type(result) is InitialRequestRoutableTaskGraphDecisionV2

    poisoned_fields_set = result.model_copy(deep=True)
    object.__setattr__(
        poisoned_fields_set,
        "__pydantic_fields_set__",
        tuple(poisoned_fields_set.model_fields_set),
    )

    poisoned_json_leaf = result.model_copy(deep=True)
    original_arguments = poisoned_json_leaf.next_move_candidate.arguments
    poisoned_arguments = tuple.__new__(
        type(original_arguments),
        (
            (
                "order_id",
                StrSubclass(original_arguments["order_id"]),
            ),
        ),
    )
    poisoned_json_leaf.next_move_candidate.__dict__["arguments"] = (
        poisoned_arguments
    )

    poisoned_mapping_key = result.model_copy(deep=True)
    mapping_arguments = poisoned_mapping_key.next_move_candidate.arguments
    poisoned_mapping_key.next_move_candidate.__dict__["arguments"] = (
        tuple.__new__(
            type(mapping_arguments),
            (
                (
                    StrSubclass("order_id"),
                    mapping_arguments["order_id"],
                ),
            ),
        )
    )

    poisoned_nested_fields_member = result.model_copy(deep=True)
    object.__setattr__(
        poisoned_nested_fields_member.next_move_candidate,
        "__pydantic_fields_set__",
        {
            StrSubclass(field_name)
            for field_name in (
                poisoned_nested_fields_member.next_move_candidate.model_fields_set
            )
        },
    )

    poisoned_top_fields_member = result.model_copy(deep=True)
    object.__setattr__(
        poisoned_top_fields_member,
        "__pydantic_fields_set__",
        {
            StrSubclass(field_name)
            for field_name in poisoned_top_fields_member.model_fields_set
        },
    )

    poisoned_private_key = result.model_copy(deep=True)
    decision_seal = poisoned_private_key.__pydantic_private__.pop(
        "_reducer_decision_seal"
    )
    poisoned_private_key.__pydantic_private__[
        StrSubclass("_reducer_decision_seal")
    ] = decision_seal

    poisoned_top_state = result.model_copy(deep=True)
    object.__setattr__(
        poisoned_top_state,
        "__dict__",
        DictSubclass(poisoned_top_state.__dict__),
    )

    poisoned_nested_state = result.model_copy(deep=True)
    object.__setattr__(
        poisoned_nested_state.task_graph.task,
        "__dict__",
        DictSubclass(poisoned_nested_state.task_graph.task.__dict__),
    )

    for poisoned in (
        poisoned_fields_set,
        poisoned_json_leaf,
        poisoned_mapping_key,
        poisoned_nested_fields_member,
        poisoned_top_fields_member,
        poisoned_private_key,
        poisoned_top_state,
        poisoned_nested_state,
    ):
        with pytest.raises(RequestProcessingError, match="canonical"):
            revalidate_next_move_v2(
                decision=poisoned,
                current_task=poisoned.task_graph.task,
                current_request_unit=poisoned.task_graph.request_unit,
                current_input_binding=poisoned.task_graph.input_binding,
            )


def test_v2_routable_decision_rejects_reused_witness_on_direct_clone() -> None:
    message_ref = uuid4()
    result = _reduce_initial_v2(
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
        ),
    )
    assert type(result) is InitialRequestRoutableTaskGraphDecisionV2
    clone = InitialRequestRoutableTaskGraphDecisionV2.model_construct(
        **result.__dict__
    )
    clone.__pydantic_private__["_reducer_decision_seal"] = (
        result.__pydantic_private__["_reducer_decision_seal"]
    )

    with pytest.raises(RequestProcessingError, match="canonical"):
        revalidate_next_move_v2(
            decision=clone,
            current_task=clone.task_graph.task,
            current_request_unit=clone.task_graph.request_unit,
            current_input_binding=clone.task_graph.input_binding,
        )


def test_v2_routable_decision_pickle_survives_source_collection() -> None:
    message_ref = uuid4()
    result = _reduce_initial_v2(
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
        ),
    )
    assert type(result) is InitialRequestRoutableTaskGraphDecisionV2
    blob = pickle.dumps(result)
    del result
    gc.collect()

    restored = pickle.loads(blob)
    move = revalidate_next_move_v2(
        decision=restored,
        current_task=restored.task_graph.task,
        current_request_unit=restored.task_graph.request_unit,
        current_input_binding=restored.task_graph.input_binding,
    )
    assert move.requested_provider_tool_name == "get_order"


def test_v2_routable_decision_pickle_ticket_stays_consumed() -> None:
    message_ref = uuid4()
    result = _reduce_initial_v2(
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
        ),
    )
    assert type(result) is InitialRequestRoutableTaskGraphDecisionV2
    consumed_blob = pickle.dumps(result)
    current = pickle.loads(consumed_blob)

    for _ in range(32):
        successor_blob = pickle.dumps(current)
        with pytest.raises(ValueError, match="unknown Reducer decision pickle"):
            pickle.loads(consumed_blob)
        current = pickle.loads(successor_blob)


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


def test_v2_builder_discards_semantic_projection_validation_context() -> None:
    marker = "LEAK-MARKER-WRONG-GOAL"
    message_ref = uuid4()
    candidate_id = uuid4()
    message = "请查询订单 O-4242"
    request_input = _request_input_v2(
        message_ref=message_ref,
        message=message,
    )
    output = _output_v2(
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
    child = _accepted_delta_v2(
        candidate_ref=candidate_id,
        message_ref=message_ref,
        goal_text=marker,
    )

    with pytest.raises(RequestUnderstandingV2Error) as caught:
        _build_v2(
            request_input=request_input,
            output=output,
            authoritative_messages={message_ref: message},
            candidate_validation=(_validation_v2(candidate_id, accept=True),),
            accepted_task_deltas=(child,),
            validated_task_state_version=1,
            next_move_candidate_ref=uuid4(),
        )

    assert caught.value.reason_code is (
        RequestUnderstandingAtomicFailureCodeV2.DURABLE_CLOSURE_COMMIT_FAILED
    )
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert marker not in str(caught.value)
    assert marker not in repr(caught.value)
    assert marker not in repr(caught.value.args)


def test_v2_builder_discards_canonical_validation_diagnostics() -> None:
    marker = "LEAK-MARKER-DECISION"
    message_ref = uuid4()
    message = "请查询订单 O-4242"
    poisoned_decision = _validation_v2(uuid4(), accept=False).model_copy(
        update={"decision": marker}
    )

    with warnings.catch_warnings(record=True) as caught_warnings:
        warnings.simplefilter("always")
        with pytest.raises(RequestUnderstandingV2Error) as caught:
            _build_v2(
                request_input=_request_input_v2(
                    message_ref=message_ref,
                    message=message,
                ),
                output=_output_v2(
                    message_ref=message_ref,
                    candidates=(),
                ),
                authoritative_messages={message_ref: message},
                candidate_validation=(poisoned_decision,),
                accepted_task_deltas=(),
            )

    assert caught.value.reason_code is (
        RequestUnderstandingAtomicFailureCodeV2.DURABLE_CLOSURE_COMMIT_FAILED
    )
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert caught_warnings == []
    assert marker not in str(caught.value)
    assert marker not in repr(caught.value)
    assert marker not in repr(caught.value.args)


def test_v2_builder_discards_authoritative_lookup_context() -> None:
    message_ref = uuid4()
    message = "请查询订单 O-4242"

    with pytest.raises(RequestUnderstandingV2Error) as caught:
        _build_v2(
            request_input=_request_input_v2(
                message_ref=message_ref,
                message=message,
            ),
            output=_output_v2(
                message_ref=message_ref,
                candidates=(),
            ),
            authoritative_messages={},
            candidate_validation=(),
            accepted_task_deltas=(),
        )

    assert caught.value.reason_code is (
        RequestUnderstandingAggregateFailureCodeV2.SOURCE_PROVENANCE_INVALID
    )
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert str(message_ref) not in str(caught.value)
    assert str(message_ref) not in repr(caught.value)
    assert str(message_ref) not in repr(caught.value.args)


def test_v2_builder_discards_source_normalization_context() -> None:
    marker = "LEAK-MARKER-CANDIDATE"
    message_ref = uuid4()
    message = "请查询订单 O-4242"

    with pytest.raises(RequestUnderstandingV2Error) as caught:
        _build_v2(
            request_input=_request_input_v2(
                message_ref=message_ref,
                message=message,
            ),
            output=_output_v2(
                message_ref=message_ref,
                candidates=(
                    _task_delta_v2(
                        candidate_id=uuid4(),
                        message_ref=message_ref,
                        order_id=marker,
                        source_quote="订单 O-4242",
                    ),
                ),
            ),
            authoritative_messages={message_ref: message},
            candidate_validation=(),
            accepted_task_deltas=(),
        )

    assert caught.value.reason_code is (
        RequestUnderstandingAggregateFailureCodeV2.SOURCE_PROVENANCE_INVALID
    )
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert marker not in str(caught.value)
    assert marker not in repr(caught.value)
    assert marker not in repr(caught.value.args)


def test_v2_unrouted_decision_rejects_cross_graph_identity_and_version_fork() -> None:
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
    first_graph, second_graph = result.task_graphs
    child_values = second_graph.accepted_delta.model_dump(mode="python")
    child_values["task_id"] = first_graph.task.task_id
    forked_child = AcceptedTaskDeltaV2(**child_values)
    task_values = second_graph.task.model_dump(mode="python")
    task_values["task_id"] = first_graph.task.task_id
    forked_task = type(second_graph.task)(**task_values)
    unit_values = second_graph.request_unit.model_dump(mode="python")
    unit_values["task_id"] = first_graph.task.task_id
    forked_unit = type(second_graph.request_unit)(**unit_values)
    forked_graph = InitialAcceptedTaskGraphV2(
        accepted_delta=forked_child,
        input_binding=second_graph.input_binding,
        task=forked_task,
        request_unit=forked_unit,
    )
    forked_closure = RequestUnderstandingClosureV2(
        record=result.closure.record,
        accepted_task_deltas=(
            first_graph.accepted_delta,
            forked_child,
        ),
    )

    with pytest.raises(ValidationError, match="globally unique"):
        InitialRequestUnroutedTaskGraphsDecisionV2(
            closure=forked_closure,
            task_graphs=(first_graph, forked_graph),
        )


_LEGACY_REQUEST_UNDERSTANDING_CORE_TARGETS = frozenset(
    {
        "RequestUnderstandingOutput",
        "AcceptedTaskDelta",
        "CandidateValidationRecord",
        "RequestUnderstandingRecord",
        "InitialRequestDecision",
        "validate_and_reduce_initial_request",
        "revalidate_next_move",
    }
)


def _folded_static_string(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _folded_static_string(node.left)
        right = _folded_static_string(node.right)
        if left is not None and right is not None:
            return left + right
    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        for value in node.values:
            if not isinstance(value, ast.Constant) or not isinstance(
                value.value,
                str,
            ):
                return None
            parts.append(value.value)
        return "".join(parts)
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "join"
        and len(node.args) == 1
        and not node.keywords
    ):
        separator = _folded_static_string(node.func.value)
        values_node = node.args[0]
        if separator is None or not isinstance(
            values_node,
            (ast.List, ast.Tuple),
        ):
            return None
        values = [_folded_static_string(item) for item in values_node.elts]
        if all(value is not None for value in values):
            return separator.join(value for value in values if value is not None)
    if isinstance(node, ast.Subscript):
        value = _folded_static_string(node.value)
        if value is None:
            return None
        if isinstance(node.slice, ast.Constant) and isinstance(
            node.slice.value,
            int,
        ):
            return value[node.slice.value]
        if isinstance(node.slice, ast.Slice):
            bounds: list[int | None] = []
            for bound in (
                node.slice.lower,
                node.slice.upper,
                node.slice.step,
            ):
                if bound is None:
                    bounds.append(None)
                elif isinstance(bound, ast.Constant) and isinstance(
                    bound.value,
                    int,
                ):
                    bounds.append(bound.value)
                else:
                    return None
            return value[slice(*bounds)]
    return None


def _dotted_ast_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _dotted_ast_name(node.value)
        if prefix is not None:
            return f"{prefix}.{node.attr}"
    return None


def _legacy_core_source_hits(
    source: str,
    *,
    filename: str,
    ignore_target_catalog: bool = False,
) -> tuple[str, ...]:
    tree = ast.parse(source, filename=filename)
    ignored_literal_nodes: set[int] = set()
    catalog_assignments = [
        node
        for node in tree.body
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id
            == "_LEGACY_REQUEST_UNDERSTANDING_CORE_TARGETS"
        )
    ]

    def static_string_set(node: ast.AST) -> frozenset[str] | None:
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "frozenset"
            and len(node.args) == 1
            and not node.keywords
        ):
            node = node.args[0]
        if not isinstance(node, (ast.Set, ast.List, ast.Tuple)):
            return None
        values = [_folded_static_string(item) for item in node.elts]
        if any(value is None for value in values):
            return None
        return frozenset(value for value in values if value is not None)

    catalog_is_exact = (
        len(catalog_assignments) == 1
        and static_string_set(catalog_assignments[0].value)
        == _LEGACY_REQUEST_UNDERSTANDING_CORE_TARGETS
    )
    if ignore_target_catalog and catalog_is_exact:
        for node in catalog_assignments:
            ignored_literal_nodes.update(
                id(descendant) for descendant in ast.walk(node.value)
            )

    parents = {
        child: parent
        for parent in ast.walk(tree)
        for child in ast.iter_child_nodes(parent)
    }

    def lexical_scope(node: ast.AST) -> ast.AST:
        current = node
        while current in parents:
            current = parents[current]
            if isinstance(
                current,
                (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda),
            ):
                return current
        return tree

    def parameter_names(scope: ast.AST) -> set[str]:
        if not isinstance(
            scope,
            (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda),
        ):
            return set()
        return {
            argument.arg
            for argument in (
                *scope.args.posonlyargs,
                *scope.args.args,
                *scope.args.kwonlyargs,
            )
        } | {
            argument.arg
            for argument in (scope.args.vararg, scope.args.kwarg)
            if argument is not None
        }

    relevant_modules = {
        "mini_agent.core.request_processing",
        "mini_agent.core.request_understanding",
        "mini_agent.core.task_state",
    }
    relevant_module_tails = {
        module_name.rsplit(".", maxsplit=1)[-1]
        for module_name in relevant_modules
    }
    imported_module_aliases: set[str] = set()
    importlib_aliases: set[str] = set()
    builtins_aliases: set[str] = set()
    pytest_aliases: set[str] = set()
    builtin_callable_names = {
        "__import__",
        "delattr",
        "getattr",
        "globals",
        "hasattr",
        "locals",
        "setattr",
        "vars",
    }
    imported_callable_aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if (
                    alias.name in relevant_modules
                    and lexical_scope(node) is tree
                ):
                    imported_module_aliases.add(
                        alias.asname or alias.name.split(".")[0]
                    )
                if alias.name == "importlib":
                    importlib_aliases.add(alias.asname or alias.name)
                if alias.name == "builtins":
                    builtins_aliases.add(alias.asname or alias.name)
                if alias.name == "pytest":
                    pytest_aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom):
            if (
                node.module == "mini_agent.core"
                and lexical_scope(node) is tree
            ):
                for alias in node.names:
                    if alias.name in relevant_module_tails:
                        imported_module_aliases.add(alias.asname or alias.name)
            if node.module == "builtins":
                for alias in node.names:
                    if alias.name in builtin_callable_names:
                        imported_callable_aliases[
                            alias.asname or alias.name
                        ] = alias.name
            if node.module == "importlib":
                for alias in node.names:
                    if alias.name == "import_module":
                        imported_callable_aliases[
                            alias.asname or alias.name
                        ] = "import_module"
            if node.module == "pytest":
                for alias in node.names:
                    if alias.name in {"importorskip", "skip", "xfail"}:
                        imported_callable_aliases[
                            alias.asname or alias.name
                        ] = alias.name

    def assignment_target_values(
        node: ast.AST,
    ) -> tuple[tuple[ast.Name, ...], ast.AST | None]:
        if isinstance(node, ast.Assign):
            return (
                tuple(
                    target
                    for target in node.targets
                    if isinstance(target, ast.Name)
                ),
                node.value,
            )
        if isinstance(node, ast.AnnAssign):
            return (
                (node.target,) if isinstance(node.target, ast.Name) else (),
                node.value,
            )
        if isinstance(node, ast.NamedExpr):
            return (
                (node.target,) if isinstance(node.target, ast.Name) else (),
                node.value,
            )
        return (), None

    assignments_by_name: dict[str, list[tuple[ast.AST, ast.AST]]] = {}
    for node in ast.walk(tree):
        targets, value = assignment_target_values(node)
        if value is None:
            continue
        for target in targets:
            assignments_by_name.setdefault(target.id, []).append((node, value))

    def position(node: ast.AST) -> tuple[int, int]:
        return (
            getattr(node, "lineno", -1),
            getattr(node, "col_offset", -1),
        )

    def latest_assignment(
        name: str,
        *,
        before: ast.AST,
    ) -> tuple[ast.AST, ast.AST] | bool | None:
        use_scope = lexical_scope(before)
        local_bindings = [
            item
            for item in assignments_by_name.get(name, ())
            if lexical_scope(item[0]) is use_scope
        ]
        if use_scope is not tree and (
            local_bindings or name in parameter_names(use_scope)
        ):
            dominating = [
                item
                for item in local_bindings
                if position(item[0]) < position(before)
            ]
            return max(
                dominating,
                key=lambda item: position(item[0]),
                default=False,
            )
        module_candidates = [
            item
            for item in assignments_by_name.get(name, ())
            if lexical_scope(item[0]) is tree
            and position(item[0]) < position(before)
        ]
        return max(
            module_candidates,
            key=lambda item: position(item[0]),
            default=None,
        )

    def name_refers_to_module(
        name: str,
        *,
        before: ast.AST,
        seen: frozenset[str] = frozenset(),
    ) -> bool:
        if name in seen:
            return False
        assignment = latest_assignment(name, before=before)
        if assignment is False:
            return False
        if assignment is not None:
            assignment_node, value = assignment
            if isinstance(value, ast.Name):
                return name_refers_to_module(
                    value.id,
                    before=assignment_node,
                    seen=seen | {name},
                )
            return _dotted_ast_name(value) in relevant_modules
        return name in imported_module_aliases

    def normalized_callable_name(
        name: str,
        *,
        before: ast.AST,
        seen: frozenset[str] = frozenset(),
    ) -> str | None:
        if name in seen:
            return None
        assignment = latest_assignment(name, before=before)
        if assignment is False:
            return None
        if assignment is not None:
            assignment_node, value = assignment
            if isinstance(value, ast.Name):
                return normalized_callable_name(
                    value.id,
                    before=assignment_node,
                    seen=seen | {name},
                )
            if (
                isinstance(value, ast.Attribute)
                and isinstance(value.value, ast.Name)
                and value.value.id in builtins_aliases
                and value.attr in builtin_callable_names
            ):
                return value.attr
            if (
                isinstance(value, ast.Attribute)
                and isinstance(value.value, ast.Name)
                and value.value.id in importlib_aliases
                and value.attr == "import_module"
            ):
                return "import_module"
            return None
        if name in imported_callable_aliases:
            return imported_callable_aliases[name]
        if name in builtin_callable_names:
            return name
        return None

    def normalized_call_name(node: ast.Call) -> str | None:
        if isinstance(node.func, ast.Name):
            return normalized_callable_name(node.func.id, before=node)
        if (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in builtins_aliases
            and node.func.attr in builtin_callable_names
        ):
            return node.func.attr
        if (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in pytest_aliases
            and node.func.attr in {"importorskip", "skip", "xfail"}
        ):
            return node.func.attr
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "import_module"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in importlib_aliases
        ):
            return "import_module"
        if isinstance(node.func, ast.Attribute):
            return node.func.attr
        return None

    def name_refers_to_namespace(
        name: str,
        *,
        before: ast.AST,
        seen: frozenset[str] = frozenset(),
    ) -> bool:
        if name in seen:
            return False
        assignment = latest_assignment(name, before=before)
        if assignment is None or assignment is False:
            return False
        assignment_node, value = assignment
        if isinstance(value, ast.Name):
            return name_refers_to_namespace(
                value.id,
                before=assignment_node,
                seen=seen | {name},
            )
        return (
            isinstance(value, ast.Call)
            and normalized_call_name(value) in {"globals", "locals", "vars"}
            and not value.args
            and not value.keywords
        )

    def is_relevant_module(node: ast.AST, *, at: ast.AST | None = None) -> bool:
        dotted_name = _dotted_ast_name(node)
        return (
            isinstance(node, ast.Name)
            and name_refers_to_module(node.id, before=at or node)
        ) or dotted_name in relevant_modules

    def enclosing_function(node: ast.AST) -> ast.FunctionDef | None:
        current = parents.get(node)
        while current is not None:
            if isinstance(current, ast.FunctionDef):
                return current
            current = parents.get(current)
        return None

    required_runtime_modules = {
        "request_processing_module",
        "request_understanding_module",
        "task_state_module",
    }

    def runtime_absence_loop_is_exact(node: ast.For) -> bool:
        if (
            not isinstance(node.target, ast.Name)
            or node.target.id != "legacy_name"
            or not isinstance(node.iter, ast.Name)
            or node.iter.id != "_LEGACY_REQUEST_UNDERSTANDING_CORE_TARGETS"
            or node.orelse
            or len(node.body) != 3
        ):
            return False
        checked_modules: set[str] = set()
        for statement in node.body:
            if (
                not isinstance(statement, ast.Assert)
                or not isinstance(statement.test, ast.UnaryOp)
                or not isinstance(statement.test.op, ast.Not)
                or not isinstance(statement.test.operand, ast.Call)
            ):
                return False
            call = statement.test.operand
            if (
                normalized_call_name(call) != "hasattr"
                or len(call.args) != 2
                or not isinstance(call.args[0], ast.Name)
                or call.args[0].id not in required_runtime_modules
                or not isinstance(call.args[1], ast.Name)
                or call.args[1].id != "legacy_name"
            ):
                return False
            checked_modules.add(call.args[0].id)
        return checked_modules == required_runtime_modules

    def enclosing_runtime_loop(node: ast.AST) -> ast.For | None:
        current = parents.get(node)
        while current is not None:
            if isinstance(current, ast.For):
                return current
            if isinstance(current, ast.FunctionDef):
                return None
            current = parents.get(current)
        return None

    def runtime_absence_function_is_exact(function: ast.FunctionDef) -> bool:
        runtime_loops = [
            node
            for node in function.body
            if isinstance(node, ast.For)
            and isinstance(node.target, ast.Name)
            and node.target.id == "legacy_name"
        ]
        legacy_name_stores = [
            node
            for node in ast.walk(function)
            if isinstance(node, ast.Name)
            and node.id == "legacy_name"
            and isinstance(node.ctx, ast.Store)
        ]
        runtime_loop_index = (
            function.body.index(runtime_loops[0])
            if len(runtime_loops) == 1
            else -1
        )
        prefix_is_straight_line = (
            runtime_loop_index >= 0
            and all(
                isinstance(statement, (ast.Assign, ast.AnnAssign, ast.Assert))
                for statement in function.body[:runtime_loop_index]
            )
        )
        has_early_termination = any(
            isinstance(
                node,
                (ast.Raise, ast.Return, ast.Yield, ast.YieldFrom),
            )
            for node in ast.walk(function)
        )
        has_skip_call = any(
            isinstance(node, ast.Call)
            and (
                normalized_call_name(node)
                in {"importorskip", "skip", "xfail"}
                or (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr in {"importorskip", "skip", "xfail"}
                )
            )
            for node in ast.walk(function)
        )
        critical_runtime_bindings = required_runtime_modules | {
            "_LEGACY_REQUEST_UNDERSTANDING_CORE_TARGETS",
            "hasattr",
        }
        local_critical_stores = [
            node
            for node in ast.walk(function)
            if isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Store)
            and node.id in critical_runtime_bindings
        ]
        module_critical_rebindings = [
            node
            for name in required_runtime_modules | {"hasattr"}
            for node, _value in assignments_by_name.get(name, ())
            if lexical_scope(node) is tree
        ]
        has_parameters = bool(
            function.args.posonlyargs
            or function.args.args
            or function.args.kwonlyargs
            or function.args.vararg
            or function.args.kwarg
        )
        return (
            catalog_is_exact
            and not function.decorator_list
            and not has_parameters
            and len(runtime_loops) == 1
            and runtime_absence_loop_is_exact(runtime_loops[0])
            and legacy_name_stores == [runtime_loops[0].target]
            and prefix_is_straight_line
            and not has_early_termination
            and not has_skip_call
            and not local_critical_stores
            and not module_critical_rebindings
            and required_runtime_modules.issubset(imported_module_aliases)
        )

    def is_exact_runtime_absence_call(node: ast.Call) -> bool:
        if (
            normalized_call_name(node) != "hasattr"
            or len(node.args) != 2
            or not is_relevant_module(node.args[0])
            or not isinstance(node.args[1], ast.Name)
            or node.args[1].id != "legacy_name"
        ):
            return False
        function = enclosing_function(node)
        loop = enclosing_runtime_loop(node)
        return (
            function is not None
            and function.name
            == "test_request_understanding_core_has_no_legacy_v1_executable_surface"
            and runtime_absence_function_is_exact(function)
            and loop is not None
            and runtime_absence_loop_is_exact(loop)
        )

    def is_namespace_mapping(node: ast.AST) -> bool:
        return (
            isinstance(node, ast.Call)
            and normalized_call_name(node) in {"globals", "locals", "vars"}
            and not node.args
            and not node.keywords
        ) or (
            isinstance(node, ast.Name)
            and name_refers_to_namespace(node.id, before=node)
        )

    hits: list[str] = []
    dynamic_export_names = {"__getattr__", "__getattribute__"}
    for node in ast.walk(tree):
        folded = _folded_static_string(node)
        if (
            id(node) not in ignored_literal_nodes
            and folded in _LEGACY_REQUEST_UNDERSTANDING_CORE_TARGETS
        ):
            hits.append(f"{node.lineno}:folded:{folded}")
        if isinstance(node, ast.ImportFrom):
            if node.module in relevant_modules and any(
                alias.name == "*" for alias in node.names
            ):
                hits.append(f"{node.lineno}:star-import:{node.module}")
            for alias in node.names:
                if alias.name in _LEGACY_REQUEST_UNDERSTANDING_CORE_TARGETS:
                    hits.append(f"{node.lineno}:import:{alias.name}")
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets, _ = assignment_target_values(node)
            if any(target.id == "pytestmark" for target in targets):
                hits.append(f"{node.lineno}:runtime-oracle-skip-marker")
        elif (
            isinstance(node, ast.AugAssign)
            and is_namespace_mapping(node.target)
        ):
            hits.append(f"{node.lineno}:dynamic-namespace-augassign")
        elif isinstance(
            node,
            (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef),
        ):
            if node.name in _LEGACY_REQUEST_UNDERSTANDING_CORE_TARGETS:
                hits.append(f"{node.lineno}:definition:{node.name}")
            if (
                isinstance(node, ast.FunctionDef)
                and node.name
                == "test_request_understanding_core_has_no_legacy_v1_executable_surface"
                and not runtime_absence_function_is_exact(node)
            ):
                hits.append(
                    f"{node.lineno}:invalid-runtime-absence-oracle-shape"
                )
            if (
                node.name in dynamic_export_names
                and isinstance(parents.get(node), ast.Module)
            ):
                hits.append(f"{node.lineno}:dynamic-export:{node.name}")
        elif isinstance(node, ast.Name):
            if node.id in _LEGACY_REQUEST_UNDERSTANDING_CORE_TARGETS:
                hits.append(f"{node.lineno}:name:{node.id}")
        elif isinstance(node, ast.Attribute):
            if node.attr in _LEGACY_REQUEST_UNDERSTANDING_CORE_TARGETS:
                hits.append(f"{node.lineno}:attribute:{node.attr}")
            if node.attr in dynamic_export_names and is_relevant_module(
                node.value
            ):
                hits.append(
                    f"{node.lineno}:dynamic-export-attribute:{node.attr}"
                )
            if node.attr == "__dict__" and is_relevant_module(node.value):
                hits.append(f"{node.lineno}:dynamic-module-dict")
        elif isinstance(node, ast.Call):
            call_name = normalized_call_name(node)
            if (
                call_name in {"getattr", "hasattr", "setattr", "delattr"}
                and len(node.args) >= 2
                and is_relevant_module(node.args[0])
            ):
                reflected_name = _folded_static_string(node.args[1])
                if (
                    reflected_name is None
                    and not is_exact_runtime_absence_call(node)
                ):
                    hits.append(
                        f"{node.lineno}:dynamic-module-reflection:{call_name}"
                    )
            if (
                call_name == "vars"
                and node.args
                and is_relevant_module(node.args[0])
            ):
                hits.append(f"{node.lineno}:dynamic-module-vars")
            if call_name in {"__import__", "import_module"}:
                hits.append(f"{node.lineno}:dynamic-import:{call_name}")
            if (
                call_name in {"get", "setdefault"}
                and isinstance(node.func, ast.Attribute)
                and is_namespace_mapping(node.func.value)
                and node.args
                and (
                    call_name == "setdefault"
                    or _folded_static_string(node.args[0]) is None
                )
            ):
                hits.append(
                    f"{node.lineno}:dynamic-namespace:{call_name}"
                )
            if (
                call_name
                in {
                    "__setitem__",
                    "clear",
                    "pop",
                    "popitem",
                    "update",
                }
                and isinstance(node.func, ast.Attribute)
                and is_namespace_mapping(node.func.value)
            ):
                hits.append(
                    f"{node.lineno}:dynamic-namespace-mutation:{call_name}"
                )
            if (
                call_name
                in {
                    "__setitem__",
                    "clear",
                    "pop",
                    "popitem",
                    "setdefault",
                    "update",
                }
                and isinstance(node.func, ast.Attribute)
                and _dotted_ast_name(node.func.value)
                in {"dict", "builtins.dict"}
                and node.args
                and is_namespace_mapping(node.args[0])
            ):
                hits.append(
                    f"{node.lineno}:unbound-namespace-mutation:{call_name}"
                )
        elif (
            isinstance(node, ast.Subscript)
            and is_namespace_mapping(node.value)
            and (
                _folded_static_string(node.slice) is None
                or isinstance(node.ctx, (ast.Store, ast.Del))
            )
        ):
            hits.append(f"{node.lineno}:dynamic-namespace-subscript")
    return tuple(sorted(set(hits)))


def _legacy_core_hits(path: Path) -> tuple[str, ...]:
    return _legacy_core_source_hits(
        path.read_text(),
        filename=str(path),
        ignore_target_catalog=path == Path(__file__),
    )


def test_request_understanding_core_has_no_legacy_v1_executable_surface() -> None:
    core_test_dir = Path(__file__).parent
    owned_paths = (
        Path(request_understanding_module.__file__),
        Path(task_state_module.__file__),
        Path(request_processing_module.__file__),
        core_test_dir / "test_control_gateway.py",
        core_test_dir / "test_identity_contract.py",
        core_test_dir / "test_request_understanding_contract.py",
        core_test_dir / "test_task_state_contract.py",
        Path(__file__),
    )
    hits = {
        str(path): path_hits
        for path in owned_paths
        if (path_hits := _legacy_core_hits(path))
    }

    assert not hits
    for legacy_name in _LEGACY_REQUEST_UNDERSTANDING_CORE_TARGETS:
        assert not hasattr(request_understanding_module, legacy_name)
        assert not hasattr(task_state_module, legacy_name)
        assert not hasattr(request_processing_module, legacy_name)

    assert hasattr(request_understanding_module, "RequestUnderstandingInput")
    assert hasattr(request_understanding_module, "RequestUnderstandingOutputV2")
    assert hasattr(task_state_module, "AcceptedTaskDeltaV2")
    assert hasattr(task_state_module, "CandidateValidationRecordV2")
    assert hasattr(task_state_module, "RequestUnderstandingRecordV2")
    assert hasattr(
        request_processing_module,
        "validate_and_reduce_initial_request_v2",
    )
    assert hasattr(request_processing_module, "revalidate_next_move_v2")


def test_request_understanding_core_absence_oracle_rejects_dynamic_bypasses() -> None:
    module_import = (
        "import mini_agent.core.request_processing as core_module\n"
    )
    legacy_target = min(_LEGACY_REQUEST_UNDERSTANDING_CORE_TARGETS)
    mutations = (
        module_import + "getattr(core_module, input())",
        module_import + "hasattr(core_module, input())",
        module_import + "setattr(core_module, input(), None)",
        module_import + "vars(core_module).get(input())",
        module_import + "core_module.__dict__.get(input())",
        module_import + "alias = core_module\ngetattr(alias, input())",
        module_import
        + "alias: object = core_module\ngetattr(alias, input())",
        module_import
        + "reflect = getattr\nreflect(core_module, input())",
        module_import
        + "reflect: object = getattr\nreflect(core_module, input())",
        (
            "from builtins import getattr as reflect\n"
            + module_import
            + "reflect(core_module, input())"
        ),
        (
            "import builtins\n"
            + module_import
            + "reflect = builtins.getattr\nreflect(core_module, input())"
        ),
        "import importlib\nimportlib.import_module(input())",
        (
            "import importlib\n"
            "loader = importlib.import_module\n"
            "loader(input())"
        ),
        "from importlib import import_module\nimport_module(input())",
        "__import__(input())",
        "vars()[input()] = object()",
        "globals().get(input())",
        "globals().setdefault(input(), object())",
        "globals().update({input(): object()})",
        "namespace = locals()\nnamespace[input()] = object()",
        "namespace: dict = globals()\nnamespace[input()] = object()",
        "namespace = globals()\nnamespace |= {input(): object()}",
        (
            "namespace = globals()\n"
            "dict.update(namespace, {input(): object()})"
        ),
        (
            "def __getattr__(name):\n"
            "    return globals().get(name + 'V2')\n"
        ),
        (
            module_import
            + "def test_request_understanding_core_has_no_legacy_v1_executable_surface():\n"
            "    legacy_name = input()\n"
            "    assert not hasattr(core_module, legacy_name)\n"
        ),
        (
            module_import
            + "def test_request_understanding_core_has_no_legacy_v1_executable_surface():\n"
            "    for legacy_name in ():\n"
            "        assert not hasattr(core_module, legacy_name)\n"
        ),
        (
            module_import
            + "def unrelated():\n"
            "    core_module = object()\n"
            "def consumer():\n"
            "    return getattr(core_module, input())\n"
        ),
        (
            module_import
            + "reflect = getattr\n"
            "def unrelated():\n"
            "    reflect = lambda value, name: None\n"
            "def consumer():\n"
            "    return reflect(core_module, input())\n"
        ),
        (
            "namespace = globals()\n"
            "def unrelated():\n"
            "    namespace = {}\n"
            "def consumer():\n"
            "    namespace[input()] = object()\n"
        ),
        module_import + f'getattr(core_module, "{legacy_target}")',
    )
    for mutation in mutations:
        assert _legacy_core_source_hits(
            mutation,
            filename="mutation.py",
        ), mutation

    catalog_source = (
        "_LEGACY_REQUEST_UNDERSTANDING_CORE_TARGETS = frozenset("
        f"{tuple(sorted(_LEGACY_REQUEST_UNDERSTANDING_CORE_TARGETS))!r}"
        ")\n"
    )
    runtime_imports = (
        "import mini_agent.core.request_processing as request_processing_module\n"
        "import mini_agent.core.request_understanding as "
        "request_understanding_module\n"
        "import mini_agent.core.task_state as task_state_module\n"
    )
    runtime_loop = (
        "    for legacy_name in "
        "_LEGACY_REQUEST_UNDERSTANDING_CORE_TARGETS:\n"
        "        assert not hasattr(request_understanding_module, legacy_name)\n"
        "        assert not hasattr(task_state_module, legacy_name)\n"
        "        assert not hasattr(request_processing_module, legacy_name)\n"
    )
    runtime_downgrades = (
        (
            catalog_source
            + runtime_imports
            + "def test_request_understanding_core_has_no_legacy_v1_executable_surface():\n"
            "    return\n"
            + runtime_loop
        ),
        (
            catalog_source
            + runtime_imports
            + "def test_request_understanding_core_has_no_legacy_v1_executable_surface():\n"
            '    pytest.skip("disabled")\n'
            + runtime_loop
        ),
        (
            catalog_source
            + runtime_imports
            + "@pytest.mark.skip\n"
            "def test_request_understanding_core_has_no_legacy_v1_executable_surface():\n"
            + runtime_loop
        ),
        (
            catalog_source
            + runtime_imports
            + "def test_request_understanding_core_has_no_legacy_v1_executable_surface():\n"
            "    _LEGACY_REQUEST_UNDERSTANDING_CORE_TARGETS = ()\n"
            + runtime_loop
        ),
        (
            catalog_source
            + runtime_imports
            + "def test_request_understanding_core_has_no_legacy_v1_executable_surface():\n"
            "    request_processing_module = object()\n"
            + runtime_loop
        ),
        (
            catalog_source
            + runtime_imports
            + "request_processing_module = object()\n"
            "def test_request_understanding_core_has_no_legacy_v1_executable_surface():\n"
            + runtime_loop
        ),
        (
            catalog_source
            + runtime_imports
            + "def test_request_understanding_core_has_no_legacy_v1_executable_surface("
            "request_processing_module=object()):\n"
            + runtime_loop
        ),
        (
            catalog_source
            + runtime_imports
            + "from pytest import skip\n"
            "def test_request_understanding_core_has_no_legacy_v1_executable_surface():\n"
            '    skipped = skip("disabled")\n'
            + runtime_loop
        ),
        (
            catalog_source
            + runtime_imports
            + "import pytest\n"
            "def test_request_understanding_core_has_no_legacy_v1_executable_surface():\n"
            '    skipped = pytest.importorskip("missing")\n'
            + runtime_loop
        ),
    )
    for runtime_downgrade in runtime_downgrades:
        assert _legacy_core_source_hits(
            runtime_downgrade,
            filename="runtime_downgrade.py",
            ignore_target_catalog=True,
        ), runtime_downgrade

    safe_sources = (
        module_import
        + f'getattr(core_module, "{legacy_target}V2", None)',
        'label = "historical request-understanding v1 absence"',
        (
            module_import
            + "alias = core_module\n"
            "alias = object()\n"
            "getattr(alias, input())"
        ),
        (
            module_import
            + "reflect = getattr\n"
            "reflect = lambda value, name: None\n"
            "reflect(core_module, input())"
        ),
        (
            "namespace = globals()\n"
            "namespace = {}\n"
            "namespace[input()] = object()"
        ),
        (
            module_import
            + "def consumer(core_module):\n"
            "    return getattr(core_module, input())"
        ),
    )
    for safe_source in safe_sources:
        assert not _legacy_core_source_hits(
            safe_source,
            filename="safe_source.py",
        ), safe_source
