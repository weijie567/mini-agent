from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from mini_agent.core.request_understanding import (
    InputAuthority,
    InputCandidate,
    InputSourceKind,
    NextMove,
    NextMoveKind,
    RequestUnderstandingInput,
    RequestUnderstandingOutput,
    TaskDeltaCandidate,
    TaskDeltaOperation,
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


def _output(
    *,
    bound_order_id: str = "O-4242",
    proposed_order_id: str = "O-4242",
) -> RequestUnderstandingOutput:
    message_ref = uuid4()
    return RequestUnderstandingOutput(
        message_ref=message_ref,
        task_delta_candidates=(
            TaskDeltaCandidate(
                candidate_id=uuid4(),
                operation=TaskDeltaOperation.ADD_GOAL,
                goal_patch="查询当前消息中订单的状态",
                input_candidates=(
                    _candidate(
                        message_ref=message_ref,
                        order_id=bound_order_id,
                    ),
                ),
                confidence=0.98,
            ),
        ),
        next_move_candidate=NextMove(
            kind=NextMoveKind.CALL_TOOL,
            requested_tool_name="get_order",
            arguments={"order_id": proposed_order_id},
            base_task_state_version=None,
        ),
    )


def test_new_goal_output_keeps_candidate_and_state_write_separate() -> None:
    output = _output()

    assert output.next_move_candidate.base_task_state_version is None
    assert "status" not in TaskDeltaCandidate.model_fields
    assert "state_version" not in TaskDeltaCandidate.model_fields
    assert "tool_call_id" not in NextMove.model_fields

    with pytest.raises(ValidationError, match="frozen"):
        output.next_move_candidate.kind = NextMoveKind.FINISH


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


def test_model_parameter_mismatch_remains_a_candidate_for_gateway_rejection() -> None:
    output = _output(
        bound_order_id="O-4242",
        proposed_order_id="O-4343",
    )

    assert (
        output.task_delta_candidates[0].input_candidates[0].candidate_value
        != output.next_move_candidate.arguments["order_id"]
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


def test_output_rejects_non_current_source_and_fake_zero_version() -> None:
    current_message_ref = uuid4()
    other_message_ref = uuid4()

    with pytest.raises(ValidationError, match="current message"):
        RequestUnderstandingOutput(
            message_ref=current_message_ref,
            task_delta_candidates=(
                TaskDeltaCandidate(
                    candidate_id=uuid4(),
                    operation="ADD_GOAL",
                    goal_patch="查询订单状态",
                    input_candidates=(_candidate(message_ref=other_message_ref),),
                    confidence=0.9,
                ),
            ),
            next_move_candidate=NextMove(
                kind="CALL_TOOL",
                requested_tool_name="get_order",
                arguments={"order_id": "O-4242"},
            ),
        )

    with pytest.raises(ValidationError, match="greater than or equal to 1"):
        NextMove(
            kind="CALL_TOOL",
            requested_tool_name="get_order",
            arguments={"order_id": "O-4242"},
            base_task_state_version=0,
        )
