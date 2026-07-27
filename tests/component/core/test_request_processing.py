from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from mini_agent.core.identity import CustomerContext
from mini_agent.core.request_processing import (
    InitialRequestDecision,
    RequestProcessingError,
    RevalidatedNextMove,
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
from mini_agent.core.task_state import InputValidationStatus, TaskStatus

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
    source_quote: str = "订单 o-1001",
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
                        source_quote=source_quote,
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

