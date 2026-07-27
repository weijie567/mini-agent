from __future__ import annotations

import asyncio
import os
import socket
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from mini_agent.application.ports import ModelProvider
from mini_agent.application.records import ProviderProtocolError
from mini_agent.core.order import (
    OrderLineSummary,
    OrderStatus,
    OrderSummaryProjection,
)
from mini_agent.core.presentation import (
    PresentationInput,
    PresentationPlan,
    PresentationPurpose,
)
from mini_agent.core.request_understanding import (
    RequestUnderstandingInput,
    RequestUnderstandingOutput,
)
from mini_agent.core.tool_system import ToolSpec, compute_model_visible_toolset_hash
from mini_agent.evaluation.artifacts import load_e2e01_artifacts
from mini_agent.evaluation.scripted_provider import ScriptedModelProvider


REPO_ROOT = Path(__file__).resolve().parents[3]
MESSAGE_REF = UUID("00000000-0000-4000-8000-000000000101")


def _tool_spec() -> ToolSpec:
    return ToolSpec(
        name="get_order",
        description="查询当前用户订单。",
        input_schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {"order_id": {"type": "string"}},
            "required": ["order_id"],
        },
        output_schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {"outcome": {"type": "string"}},
            "required": ["outcome"],
        },
    )


def _request(query: str = "查订单 O-1001") -> RequestUnderstandingInput:
    tool = _tool_spec()
    return RequestUnderstandingInput(
        run_id=UUID("00000000-0000-4000-8000-000000000102"),
        message_ref=MESSAGE_REF,
        original_query=query,
        provider_visible_tool_specs=(tool,),
        model_visible_toolset_hash=compute_model_visible_toolset_hash((tool,)),
    )


def _presentation_input() -> PresentationInput:
    return PresentationInput(
        purpose=PresentationPurpose.ORDER_STATUS_SUMMARY,
        order_summary=OrderSummaryProjection(
            order_number="O-1001",
            status=OrderStatus.SHIPPED,
            line_items=(OrderLineSummary(product_name="轻量跑鞋", quantity=1),),
            ordered_at="2026-07-20T02:15:00Z",
            status_updated_at="2026-07-24T09:30:00Z",
        ),
    )


def _provider(script_ref: str) -> ScriptedModelProvider:
    artifacts = load_e2e01_artifacts(REPO_ROOT, candidate_version="candidate")
    provider = ScriptedModelProvider(artifacts, model_script_ref=script_ref)
    assert isinstance(provider, ModelProvider)
    return provider


@pytest.mark.parametrize(
    ("script_ref", "expected_order"),
    [
        ("script:e2e01-01:success", "O-1001"),
        ("script:e2e01-04-a:foreign-order", "O-2001"),
        ("script:e2e01-04-b:nonexistent-order", "O-9999"),
    ],
)
def test_explicit_scripts_return_canonical_request_understanding(
    script_ref: str,
    expected_order: str,
) -> None:
    provider = _provider(script_ref)
    output = asyncio.run(provider.propose_next_move(_request("unrelated wording")))

    assert type(output) is RequestUnderstandingOutput
    assert output.message_ref == MESSAGE_REF
    assert output.next_move_candidate.base_task_state_version is None
    assert output.next_move_candidate.requested_tool_name == "get_order"
    assert output.next_move_candidate.arguments == {"order_id": expected_order}
    if script_ref == "script:e2e01-01:success":
        plan = asyncio.run(provider.plan_presentation(_presentation_input()))
        assert type(plan) is PresentationPlan
    provider.assert_exhausted()


def test_script_cursor_is_strict_and_does_not_keyword_route() -> None:
    provider = _provider("script:e2e01-01:success")
    with pytest.raises(ProviderProtocolError) as caught:
        asyncio.run(provider.plan_presentation(_presentation_input()))
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


@pytest.mark.parametrize(
    ("script_ref", "expected_order"),
    [
        ("script:sec-argument-binding:foreign-order", "O-2001"),
        ("script:sec-argument-binding:nonexistent-order", "O-9999"),
        ("script:fault-provider:unknown-tool-name", "O-1001"),
    ],
)
def test_gateway_fault_candidates_remain_canonical(
    script_ref: str,
    expected_order: str,
) -> None:
    output = asyncio.run(_provider(script_ref).propose_next_move(_request()))
    assert type(output) is RequestUnderstandingOutput
    assert output.next_move_candidate.arguments == {"order_id": expected_order}
    if script_ref.endswith("unknown-tool-name"):
        assert output.next_move_candidate.requested_tool_name == "get_any_order"


@pytest.mark.parametrize(
    "script_ref",
    [
        "script:fault-provider:invalid-request-understanding-schema",
        "script:fault-provider:source-authority-mismatch",
        "script:fault-provider:trusted-field-override",
    ],
)
def test_invalid_request_candidates_fail_canonical_validation(
    script_ref: str,
) -> None:
    with pytest.raises(ValidationError):
        asyncio.run(_provider(script_ref).propose_next_move(_request()))


@pytest.mark.parametrize(
    "script_ref",
    [
        "script:fault-provider:zero-target-functions",
        "script:fault-provider:multiple-target-functions",
    ],
)
def test_request_protocol_faults_expose_fresh_parameterless_errors(
    script_ref: str,
) -> None:
    errors = []
    for _ in range(2):
        with pytest.raises(ProviderProtocolError) as caught:
            asyncio.run(_provider(script_ref).propose_next_move(_request()))
        errors.append(caught.value)
        assert caught.value.args == ("PROVIDER_PROTOCOL_ERROR",)
        assert caught.value.__cause__ is None
        assert caught.value.__context__ is None
        assert script_ref not in str(caught.value)
    assert errors[0] is not errors[1]


@pytest.mark.parametrize(
    "script_ref",
    [
        "script:fault-presentation:zero-target-functions",
        "script:fault-presentation:multiple-target-functions",
        "script:fault-presentation:invalid-schema",
        "script:fault-presentation:fact-bearing-envelope",
    ],
)
def test_presentation_protocol_faults_discard_raw_envelopes(
    script_ref: str,
) -> None:
    provider = _provider(script_ref)
    asyncio.run(provider.propose_next_move(_request()))
    with pytest.raises(ProviderProtocolError) as caught:
        asyncio.run(provider.plan_presentation(_presentation_input()))
    assert caught.value.args == ("PROVIDER_PROTOCOL_ERROR",)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert "O-1001 已发货" not in str(caught.value)


def test_stale_state_directive_is_separate_closed_and_one_shot() -> None:
    provider = _provider("script:fault-runtime:state-advanced-before-gate")
    output = asyncio.run(provider.propose_next_move(_request()))
    assert output.next_move_candidate.base_task_state_version is None

    directive = provider.take_runtime_fault_directive()
    assert directive is not None
    assert directive.behavior == "ADVANCE_TASK_STATE_AFTER_REVALIDATION_BEFORE_GATE"
    assert directive.boundary == "AFTER_REVALIDATION_BEFORE_GATE"
    assert provider.take_runtime_fault_directive() is None
    provider.assert_exhausted()


def test_scripted_provider_reads_no_credentials_and_opens_no_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_getenv(*_args: object, **_kwargs: object) -> str:
        raise AssertionError("credential lookup is forbidden")

    def forbidden_connect(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr(os, "getenv", forbidden_getenv)
    monkeypatch.setattr(socket.socket, "connect", forbidden_connect)
    output = asyncio.run(
        _provider("script:e2e01-04-b:nonexistent-order").propose_next_move(
            _request()
        )
    )
    assert output.next_move_candidate.arguments == {"order_id": "O-9999"}
