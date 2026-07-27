from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Callable
from uuid import UUID

import httpx
import pytest

from mini_agent.application.ports import ModelProvider
from mini_agent.application.records import ProviderProtocolError
from mini_agent.core.order import (
    OrderLineSummary,
    OrderStatus,
    OrderSummaryProjection,
)
from mini_agent.core.presentation import (
    ClosingVariant,
    OpeningVariant,
    PresentationField,
    PresentationInput,
    PresentationPlan,
    PresentationPurpose,
    PresentationTone,
)
from mini_agent.core.request_understanding import (
    InputAuthority,
    InputSourceKind,
    NextMove,
    NextMoveKind,
    RequestUnderstandingInput,
    RequestUnderstandingOutput,
    TaskDeltaCandidate,
    TaskDeltaOperation,
    InputCandidate,
)
from mini_agent.core.tool_system import ToolSpec, compute_model_visible_toolset_hash
from mini_agent.infrastructure.model.qwen_responses import (
    QWEN_MODEL_SNAPSHOT,
    QwenResponsesAdapter,
)


MESSAGE_REF = UUID("00000000-0000-4000-8000-000000000101")


def _tool_spec() -> ToolSpec:
    return ToolSpec(
        name="get_order",
        description="查询订单。",
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


def _request() -> RequestUnderstandingInput:
    tool = _tool_spec()
    return RequestUnderstandingInput(
        run_id=UUID("00000000-0000-4000-8000-000000000102"),
        message_ref=MESSAGE_REF,
        original_query="查订单 O-1001",
        provider_visible_tool_specs=(tool,),
        model_visible_toolset_hash=compute_model_visible_toolset_hash((tool,)),
    )


def _request_output() -> RequestUnderstandingOutput:
    return RequestUnderstandingOutput(
        message_ref=MESSAGE_REF,
        task_delta_candidates=(
            TaskDeltaCandidate(
                candidate_id=UUID("00000000-0000-4000-8000-000000000103"),
                operation=TaskDeltaOperation.ADD_GOAL,
                goal_patch="查询订单状态",
                input_candidates=(
                    InputCandidate(
                        name="order_id",
                        candidate_value="O-1001",
                        semantic_role="TARGET_RESOURCE_IDENTIFIER",
                        authority=InputAuthority.USER_CLAIM,
                        source_kind=InputSourceKind.CURRENT_MESSAGE,
                        source_ref=MESSAGE_REF,
                        source_quote="O-1001",
                        confidence=1.0,
                    ),
                ),
                confidence=1.0,
            ),
        ),
        next_move_candidate=NextMove(
            kind=NextMoveKind.CALL_TOOL,
            requested_tool_name="get_order",
            arguments={"order_id": "O-1001"},
            base_task_state_version=None,
        ),
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


def _presentation_plan() -> PresentationPlan:
    return PresentationPlan(
        template_id="ORDER_STATUS_SUMMARY_V1",
        tone=PresentationTone.WARM,
        opening_variant=OpeningVariant.ACKNOWLEDGE,
        field_order=tuple(PresentationField),
        closing_variant=ClosingVariant.OFFER_FOLLOW_UP,
    )


def _response(name: str, arguments: object) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "raw-provider-id-must-not-escape",
            "output": [
                {
                    "type": "function_call",
                    "name": name,
                    "arguments": (
                        arguments
                        if isinstance(arguments, str)
                        else json.dumps(arguments)
                    ),
                }
            ],
        },
    )


def _run_with_handler(
    handler: Callable[[httpx.Request], httpx.Response],
    operation: Callable[[QwenResponsesAdapter], object],
) -> object:
    async def run() -> object:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = QwenResponsesAdapter(
                base_url="https://qwen.invalid/compatible-mode/v1/",
                api_key="synthetic-secret",
                client=client,
            )
            assert isinstance(adapter, ModelProvider)
            return await operation(adapter)  # type: ignore[misc]

    return asyncio.run(run())


def test_request_understanding_uses_exact_closed_one_function_request() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _response(
            "submit_next_move",
            _request_output().model_dump(mode="json"),
        )

    output = _run_with_handler(
        handler,
        lambda adapter: adapter.propose_next_move(_request()),
    )

    assert type(output) is RequestUnderstandingOutput
    request = seen.pop()
    body = json.loads(request.content)
    assert request.url == "https://qwen.invalid/compatible-mode/v1/responses"
    assert set(body) == {"model", "input", "tools", "tool_choice", "store", "stream"}
    assert body["model"] == QWEN_MODEL_SNAPSHOT == "qwen3.7-plus-2026-05-26"
    assert body["input"] == _request().model_dump(mode="json")
    assert body["store"] is False
    assert body["stream"] is False
    assert len(body["tools"]) == 1
    assert body["tools"][0]["type"] == "function"
    assert body["tools"][0]["name"] == "submit_next_move"
    assert body["tool_choice"] == {
        "type": "function",
        "name": "submit_next_move",
    }
    assert request.headers["authorization"] == "Bearer synthetic-secret"
    assert "x-dashscope-session-cache" not in request.headers
    assert "previous_response_id" not in body
    assert "conversation" not in body
    assert {tool.get("type") for tool in body["tools"]}.isdisjoint(
        {"web_search", "web_extractor", "code_interpreter", "file_search", "MCP"}
    )
    serialized = json.dumps(body)
    assert "customer_id" not in serialized
    assert "synthetic-secret" not in serialized


def test_presentation_uses_only_presentation_function_and_canonical_output() -> None:
    seen: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return _response(
            "submit_presentation_plan",
            _presentation_plan().model_dump(mode="json"),
        )

    output = _run_with_handler(
        handler,
        lambda adapter: adapter.plan_presentation(_presentation_input()),
    )
    assert type(output) is PresentationPlan
    assert seen[0]["tools"][0]["name"] == "submit_presentation_plan"  # type: ignore[index]
    assert seen[0]["tool_choice"] == {
        "type": "function",
        "name": "submit_presentation_plan",
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"output": []},
        {
            "output": [
                {
                    "type": "function_call",
                    "name": "submit_next_move",
                    "arguments": "{}",
                },
                {
                    "type": "function_call",
                    "name": "submit_next_move",
                    "arguments": "{}",
                },
            ]
        },
        {
            "output": [
                {
                    "type": "function_call",
                    "name": "wrong_function",
                    "arguments": "{}",
                }
            ]
        },
        {
            "output": [
                {
                    "type": "function_call",
                    "name": "submit_next_move",
                    "arguments": "{raw-secret:not-json",
                }
            ]
        },
        {
            "output": [
                {
                    "type": "function_call",
                    "name": "submit_next_move",
                    "arguments": "{}",
                }
            ]
        },
    ],
)
def test_protocol_violations_are_fresh_bounded_errors(
    payload: dict[str, object],
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    with pytest.raises(ProviderProtocolError) as caught:
        _run_with_handler(
            handler,
            lambda adapter: adapter.propose_next_move(_request()),
        )
    assert caught.value.args == ("PROVIDER_PROTOCOL_ERROR",)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert "raw-secret" not in str(caught.value)
    assert "wrong_function" not in str(caught.value)


@pytest.mark.parametrize("mode", ["transport", "http"])
def test_raw_transport_and_http_errors_are_discarded(mode: str) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        if mode == "transport":
            raise RuntimeError("raw-secret-transport")
        return httpx.Response(500, text="raw-secret-http")

    with pytest.raises(ProviderProtocolError) as caught:
        _run_with_handler(
            handler,
            lambda adapter: adapter.propose_next_move(_request()),
        )
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert "raw-secret" not in str(caught.value)


def test_adapter_uses_injected_configuration_without_environment_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        os,
        "getenv",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("environment lookup forbidden")
        ),
    )

    output = _run_with_handler(
        lambda _request: _response(
            "submit_next_move",
            _request_output().model_dump(mode="json"),
        ),
        lambda adapter: adapter.propose_next_move(_request()),
    )
    assert type(output) is RequestUnderstandingOutput
