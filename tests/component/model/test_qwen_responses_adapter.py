from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Callable, Mapping
from dataclasses import fields, is_dataclass
from uuid import UUID

import httpx
import pytest
from pydantic import BaseModel

from mini_agent.application.ports import ModelProviderV2
from mini_agent.application.records import (
    ProviderProtocolError,
    RequestUnderstandingCandidateInvalidError,
)
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
    QueryContextualizationCandidateV2,
    ReferenceSourceKindV2,
    ResolvedReferenceCandidateV2,
    RequestUnderstandingInput,
    RequestUnderstandingOutputV2,
    TaskDeltaCandidate,
    TaskDeltaOperation,
    InputCandidate,
)
from mini_agent.core.tool_system import ToolSpec, compute_model_visible_toolset_hash
import mini_agent.infrastructure.model.qwen_responses as qwen_responses_module
from mini_agent.infrastructure.model.qwen_responses import (
    QWEN_MODEL_SNAPSHOT,
    QwenResponsesAdapterV2,
)


MESSAGE_REF = UUID("00000000-0000-4000-8000-000000000101")


def _reachable_traceback_state(
    error: BaseException,
) -> tuple[tuple[str, ...], frozenset[str], frozenset[type[object]]]:
    visited: set[int] = set()
    strings: set[str] = set()
    value_types: set[type[object]] = set()

    def visit(value: object) -> None:
        value_type = type(value)
        value_types.add(value_type)
        if value_type is str:
            strings.add(value)
            return
        if value is None or value_type in {bool, int, float, bytes, UUID}:
            return
        value_id = id(value)
        if value_id in visited:
            return
        visited.add(value_id)
        if isinstance(value, BaseModel):
            for field_name in type(value).model_fields:
                visit(getattr(value, field_name))
            return
        if isinstance(value, Mapping):
            for key, item in value.items():
                visit(key)
                visit(item)
            return
        if isinstance(value, (tuple, list, set, frozenset)):
            for item in value:
                visit(item)
            return
        if is_dataclass(value):
            for item in fields(value):
                visit(getattr(value, item.name))
        for owner in value_type.__mro__:
            raw_slots = owner.__dict__.get("__slots__", ())
            slots = (raw_slots,) if isinstance(raw_slots, str) else tuple(raw_slots)
            for field_name in slots:
                if (
                    field_name not in {"__dict__", "__weakref__"}
                    and hasattr(value, field_name)
                ):
                    visit(getattr(value, field_name))
        if hasattr(value, "__dict__"):
            visit(vars(value))

    frame_names: list[str] = []
    pending_errors = [error]
    visited_errors: set[int] = set()
    while pending_errors:
        current_error = pending_errors.pop()
        if id(current_error) in visited_errors:
            continue
        visited_errors.add(id(current_error))
        visit(current_error.args)
        traceback = current_error.__traceback__
        while traceback is not None:
            frame = traceback.tb_frame
            if frame.f_globals.get("__name__") == (
                "mini_agent.infrastructure.model.qwen_responses"
            ):
                frame_names.append(frame.f_code.co_name)
                visit(dict(frame.f_locals))
            traceback = traceback.tb_next
        for chained_error in (
            current_error.__cause__,
            current_error.__context__,
        ):
            if chained_error is not None:
                pending_errors.append(chained_error)
    return tuple(frame_names), frozenset(strings), frozenset(value_types)


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


def _request_output_v2() -> RequestUnderstandingOutputV2:
    return RequestUnderstandingOutputV2(
        schema_version="e2e01-thin-v2",
        message_ref=MESSAGE_REF,
        contextualization=QueryContextualizationCandidateV2(
            text=_request().original_query,
            resolved_reference_candidates=(
                ResolvedReferenceCandidateV2(
                    name="order_id",
                    candidate_value="O-1001",
                    source_kind=ReferenceSourceKindV2.CURRENT_MESSAGE,
                    source_ref=MESSAGE_REF,
                    source_quote="O-1001",
                    confidence=1.0,
                ),
            ),
            uncertainties=(),
            source_message_refs=(MESSAGE_REF,),
        ),
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
    operation: Callable[[ModelProviderV2], object],
) -> object:
    async def run() -> object:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = QwenResponsesAdapterV2(
                base_url="https://qwen.invalid/compatible-mode/v1/",
                api_key="synthetic-secret",
                client=client,
            )
            assert isinstance(adapter, ModelProviderV2)
            return await operation(adapter)  # type: ignore[misc]

    return asyncio.run(run())


@pytest.mark.parametrize(
    "base_url",
    [
        " https://qwen.invalid/compatible-mode/v1 ",
        "http://qwen.invalid/compatible-mode/v1",
        "https:///compatible-mode/v1",
        "relative/compatible-mode/v1",
        "https://qwen.invalid:bad/compatible-mode/v1",
    ],
)
def test_adapter_rejects_invalid_url_without_reachable_inputs_or_transport(
    base_url: str,
) -> None:
    seen: list[httpx.Request] = []
    errors: list[ValueError] = []

    async def run() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: seen.append(request) or httpx.Response(200)
            )
        ) as client:
            for _ in range(2):
                with pytest.raises(ValueError) as caught:
                    QwenResponsesAdapterV2(
                        base_url=base_url,
                        api_key="synthetic-secret",
                        client=client,
                    )
                errors.append(caught.value)

    asyncio.run(run())
    assert seen == []
    for error in errors:
        assert type(error) is ValueError
        assert error.args in {
            ("base_url must be a concrete injected value",),
            ("base_url must be a valid HTTPS URL",),
        }
        assert error.__cause__ is None
        assert error.__context__ is None
        frame_names, strings, value_types = _reachable_traceback_state(error)
        assert frame_names == ("__init__",)
        assert {base_url, "synthetic-secret"}.isdisjoint(strings)
        assert QwenResponsesAdapterV2 not in value_types
        assert httpx.AsyncClient not in value_types
        assert httpx.URL not in value_types
    assert errors[0] is not errors[1]


@pytest.mark.parametrize("invalid_input", ["api_key", "client"])
def test_adapter_rejects_invalid_injected_dependency_without_reachable_inputs(
    invalid_input: str,
) -> None:
    seen: list[httpx.Request] = []
    base_url = "https://qwen.invalid/compatible-mode/v1"
    api_key = " synthetic-secret " if invalid_input == "api_key" else (
        "synthetic-secret"
    )
    client: object = (
        object()
        if invalid_input == "client"
        else httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: seen.append(request) or httpx.Response(200)
            )
        )
    )
    errors: list[ValueError | TypeError] = []
    try:
        for _ in range(2):
            with pytest.raises((ValueError, TypeError)) as caught:
                QwenResponsesAdapterV2(
                    base_url=base_url,
                    api_key=api_key,
                    client=client,  # type: ignore[arg-type]
                )
            errors.append(caught.value)
    finally:
        if isinstance(client, httpx.AsyncClient):
            asyncio.run(client.aclose())

    assert seen == []
    expected_type = ValueError if invalid_input == "api_key" else TypeError
    for error in errors:
        assert type(error) is expected_type
        assert error.args == (
            (
                "api_key must be a concrete injected value"
                if invalid_input == "api_key"
                else "client must be an injected httpx.AsyncClient"
            ),
        )
        assert error.__cause__ is None
        assert error.__context__ is None
        frame_names, strings, value_types = _reachable_traceback_state(error)
        assert frame_names == ("__init__",)
        assert {base_url, api_key}.isdisjoint(strings)
        assert QwenResponsesAdapterV2 not in value_types
        assert type(client) not in value_types
        assert httpx.AsyncClient not in value_types
        assert httpx.URL not in value_types
    assert errors[0] is not errors[1]


def test_v2_request_understanding_uses_exact_closed_one_function_request() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _response(
            "submit_next_move",
            _request_output_v2().model_dump(mode="json"),
        )

    output = _run_with_handler(
        handler,
        lambda adapter: adapter.propose_next_move(_request()),
    )

    assert type(output) is RequestUnderstandingOutputV2
    request = seen.pop()
    body = json.loads(request.content)
    assert set(body) == {"model", "input", "tools", "tool_choice", "store", "stream"}
    assert body["model"] == QWEN_MODEL_SNAPSHOT
    assert body["input"] == _request().model_dump(mode="json")
    assert body["tools"][0]["name"] == "submit_next_move"
    assert body["tools"][0]["parameters"]["properties"]["schema_version"][  # type: ignore[index]
        "const"
    ] == "e2e01-thin-v2"
    assert body["tool_choice"] == {
        "type": "function",
        "name": "submit_next_move",
    }
    assert body["store"] is False
    assert body["stream"] is False
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


def test_v2_presentation_path_preserves_validation_taxonomy() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return _response(
            "submit_presentation_plan",
            {"template_id": "RAW_INVALID_PRESENTATION_SECRET"},
        )

    errors = []
    for _ in range(2):
        with pytest.raises(ProviderProtocolError) as caught:
            _run_with_handler(
                handler,
                lambda adapter: adapter.plan_presentation(_presentation_input()),
            )
        errors.append(caught.value)
        assert caught.value.args == ("PROVIDER_PROTOCOL_ERROR",)
        assert caught.value.__cause__ is None
        assert caught.value.__context__ is None
        assert "RAW_INVALID_PRESENTATION_SECRET" not in str(caught.value)
        frame_names, strings, value_types = _reachable_traceback_state(
            caught.value
        )
        assert frame_names == ("plan_presentation",)
        assert {
            "RAW_INVALID_PRESENTATION_SECRET",
            "synthetic-secret",
        }.isdisjoint(strings)
        assert PresentationInput not in value_types
        assert getattr(
            qwen_responses_module,
            "QwenResponsesAdapterV2",
        ) not in value_types
    assert errors[0] is not errors[1]


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
                    "arguments": "[]",
                }
            ]
        },
    ],
)
def test_v2_framing_violations_remain_fresh_protocol_errors(
    payload: dict[str, object],
) -> None:
    errors = []
    for _ in range(2):
        with pytest.raises(ProviderProtocolError) as caught:
            _run_with_handler(
                lambda _request: httpx.Response(200, json=payload),
                lambda adapter: adapter.propose_next_move(_request()),
            )
        errors.append(caught.value)
        assert caught.value.args == ("PROVIDER_PROTOCOL_ERROR",)
        assert caught.value.__cause__ is None
        assert caught.value.__context__ is None
        assert "raw-secret" not in str(caught.value)
        frame_names, strings, value_types = _reachable_traceback_state(
            caught.value
        )
        assert frame_names == ("propose_next_move",)
        assert {"raw-secret", "synthetic-secret"}.isdisjoint(strings)
        assert RequestUnderstandingInput not in value_types
        assert getattr(
            qwen_responses_module,
            "QwenResponsesAdapterV2",
        ) not in value_types
    assert errors[0] is not errors[1]


@pytest.mark.parametrize(
    "mutation",
    ["schema", "authority", "trusted"],
)
def test_v2_correctly_framed_invalid_candidates_are_candidate_errors(
    mutation: str,
) -> None:
    arguments = _request_output_v2().model_dump(mode="json")
    if mutation == "schema":
        arguments["schema_version"] = "raw-invalid-schema-secret"
    elif mutation == "authority":
        arguments["task_delta_candidates"][0]["input_candidates"][0][  # type: ignore[index]
            "authority"
        ] = "MODEL_INFERENCE"
    else:
        arguments["next_move_candidate"]["arguments"][  # type: ignore[index]
            "customer_id"
        ] = "raw-customer-secret"

    errors = []
    for _ in range(2):
        with pytest.raises(
            RequestUnderstandingCandidateInvalidError
        ) as caught:
            _run_with_handler(
                lambda _request: _response("submit_next_move", arguments),
                lambda adapter: adapter.propose_next_move(_request()),
            )
        errors.append(caught.value)
        assert caught.value.args == (
            "REQUEST_UNDERSTANDING_CANDIDATE_INVALID",
        )
        assert caught.value.__cause__ is None
        assert caught.value.__context__ is None
        assert "raw-" not in str(caught.value)
        frame_names, strings, value_types = _reachable_traceback_state(
            caught.value
        )
        assert frame_names == ("propose_next_move",)
        assert {
            "raw-invalid-schema-secret",
            "raw-customer-secret",
            "synthetic-secret",
        }.isdisjoint(strings)
        assert RequestUnderstandingInput not in value_types
        assert getattr(
            qwen_responses_module,
            "QwenResponsesAdapterV2",
        ) not in value_types
    assert errors[0] is not errors[1]


@pytest.mark.parametrize("mode", ["transport", "http", "json"])
def test_v2_transport_http_and_json_errors_remain_protocol_errors(
    mode: str,
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        if mode == "transport":
            raise RuntimeError("raw-secret-transport")
        if mode == "http":
            return httpx.Response(500, text="raw-secret-http")
        return httpx.Response(200, text="{raw-secret-json")

    errors = []
    for _ in range(2):
        with pytest.raises(ProviderProtocolError) as caught:
            _run_with_handler(
                handler,
                lambda adapter: adapter.propose_next_move(_request()),
            )
        errors.append(caught.value)
        assert caught.value.__cause__ is None
        assert caught.value.__context__ is None
        assert "raw-secret" not in str(caught.value)
        frame_names, strings, value_types = _reachable_traceback_state(
            caught.value
        )
        assert frame_names == ("propose_next_move",)
        assert {
            "raw-secret-transport",
            "raw-secret-http",
            "raw-secret-json",
            "synthetic-secret",
        }.isdisjoint(strings)
        assert RequestUnderstandingInput not in value_types
        assert getattr(
            qwen_responses_module,
            "QwenResponsesAdapterV2",
        ) not in value_types
    assert errors[0] is not errors[1]


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
            _request_output_v2().model_dump(mode="json"),
        ),
        lambda adapter: adapter.propose_next_move(_request()),
    )
    assert type(output) is RequestUnderstandingOutputV2
