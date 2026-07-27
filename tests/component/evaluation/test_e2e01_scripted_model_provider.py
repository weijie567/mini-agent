from __future__ import annotations

import asyncio
import os
import socket
from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest
from pydantic import BaseModel, ValidationError

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
from mini_agent.evaluation.artifacts import (
    LoadedE2E01Artifacts,
    ModelScriptArtifact,
    load_e2e01_artifacts,
)
from mini_agent.evaluation.scripted_provider import ScriptedModelProvider


REPO_ROOT = Path(__file__).resolve().parents[3]
MESSAGE_REF = UUID("00000000-0000-4000-8000-000000000101")
SCRIPT_EXECUTION_REF = UUID("abababab-abab-4bab-8bab-abababababab")


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


@dataclass(frozen=True, slots=True)
class _ReachableState:
    field_names: frozenset[str]
    string_values: frozenset[str]
    value_types: frozenset[type[object]]


def _reachable_state(
    value: object,
    *,
    visited: set[int] | None = None,
) -> _ReachableState:
    visited = visited if visited is not None else set()
    value_type = type(value)
    types: set[type[object]] = {value_type}
    if value is None:
        return _ReachableState(frozenset(), frozenset(), frozenset(types))
    if value_type is str:
        return _ReachableState(
            frozenset(),
            frozenset({value}),
            frozenset(types),
        )
    if value_type in {int, float, bool, bytes, UUID}:
        return _ReachableState(frozenset(), frozenset(), frozenset(types))
    value_id = id(value)
    if value_id in visited:
        return _ReachableState(frozenset(), frozenset(), frozenset())
    visited.add(value_id)
    names: set[str] = set()
    strings: set[str] = set()

    def merge(item: object) -> None:
        reachable = _reachable_state(item, visited=visited)
        names.update(reachable.field_names)
        strings.update(reachable.string_values)
        types.update(reachable.value_types)

    if isinstance(value, BaseModel):
        names.update(type(value).model_fields)
        for field_name in type(value).model_fields:
            merge(getattr(value, field_name))
        return _ReachableState(
            frozenset(names),
            frozenset(strings),
            frozenset(types),
        )
    if isinstance(value, Mapping):
        for key, item in value.items():
            if isinstance(key, str):
                names.add(key)
            else:
                merge(key)
            merge(item)
        return _ReachableState(
            frozenset(names),
            frozenset(strings),
            frozenset(types),
        )
    if isinstance(value, (tuple, list, set, frozenset)):
        for item in value:
            merge(item)
        return _ReachableState(
            frozenset(names),
            frozenset(strings),
            frozenset(types),
        )
    if is_dataclass(value):
        for item in fields(value):
            names.add(item.name)
            merge(getattr(value, item.name))
    seen_slots: set[str] = set()
    for owner in type(value).__mro__:
        raw_slots = owner.__dict__.get("__slots__", ())
        slots = (raw_slots,) if isinstance(raw_slots, str) else tuple(raw_slots)
        for field_name in slots:
            if (
                field_name in {"__dict__", "__weakref__"}
                or field_name in seen_slots
                or not hasattr(value, field_name)
            ):
                continue
            seen_slots.add(field_name)
            names.add(field_name.removeprefix("_"))
            merge(getattr(value, field_name))
    if hasattr(value, "__dict__"):
        for field_name, item in vars(value).items():
            names.add(field_name.removeprefix("_"))
            merge(item)
    return _ReachableState(
        frozenset(names),
        frozenset(strings),
        frozenset(types),
    )


def test_execution_only_provider_drops_script_oracle_and_unknown_step_keys() -> None:
    artifacts = load_e2e01_artifacts(REPO_ROOT, candidate_version="candidate")
    source = artifacts.script_by_ref("script:e2e01-01:success")
    first_step = dict(source.steps[0])
    first_step.update(
        {
            "grader_answer": {
                "expected_control_result": "PASS",
                "observable_equivalence": "SAME",
            },
            "setup_fixture_ref": "order:oracle-only",
        }
    )
    script = ModelScriptArtifact(
        model_script_ref=source.model_script_ref,
        case_refs=source.case_refs,
        steps=(first_step, *source.steps[1:]),
        expected_control_result=source.expected_control_result,
        runtime_fault=source.runtime_fault,
    )
    projected_artifacts = artifacts.model_copy(
        update={
            "scripts": tuple(
                script
                if item.model_script_ref == script.model_script_ref
                else item
                for item in artifacts.scripts
            )
        }
    )

    provider = ScriptedModelProvider(
        projected_artifacts,
        model_script_ref=script.model_script_ref,
    )
    reachable = _reachable_state(provider)

    assert not hasattr(provider, "model_script_ref")
    assert {
        "model_script_ref",
        "case_refs",
        "expected_control_result",
        "grader_answer",
        "observable_equivalence",
        "setup_fixture_ref",
        "fact_source",
    }.isdisjoint(reachable.field_names)
    assert {
        script.model_script_ref,
        *script.case_refs,
        "DETERMINISTIC_ORDER_SUMMARY_V1",
        "SAFE_ORDER_OBSERVATION",
        "order:oracle-only",
        "PASS",
        "SAME",
    }.isdisjoint(reachable.string_values)
    assert {
        ModelScriptArtifact,
        LoadedE2E01Artifacts,
        dict,
        list,
    }.isdisjoint(reachable.value_types)
    step_types = {
        value_type
        for value_type in reachable.value_types
        if value_type.__module__ == "mini_agent.evaluation.scripted_provider"
        and value_type.__name__.endswith("Step")
    }
    assert step_types
    assert all(
        is_dataclass(value_type)
        and value_type.__dataclass_params__.frozen
        and "__slots__" in value_type.__dict__
        for value_type in step_types
    )

    output = asyncio.run(provider.propose_next_move(_request()))
    assert output.task_delta_candidates[0].candidate_id != uuid5(
        NAMESPACE_URL,
        f"{script.model_script_ref}:{MESSAGE_REF}",
    )


def test_execution_only_provider_drops_fact_bearing_raw_payload() -> None:
    artifacts = load_e2e01_artifacts(REPO_ROOT, candidate_version="candidate")
    script = artifacts.script_by_ref(
        "script:fault-presentation:fact-bearing-envelope"
    )
    provider = ScriptedModelProvider(
        artifacts,
        model_script_ref=script.model_script_ref,
    )

    reachable = _reachable_state(provider)

    assert {
        "raw_function_arguments",
        "free_text",
        "validation_model",
        "raw_envelope_disposition",
    }.isdisjoint(reachable.field_names)
    assert {
        script.model_script_ref,
        *script.case_refs,
        "订单 O-1001 已发货",
        "FIXED_SAFE_PROCESSING_ERROR",
    }.isdisjoint(reachable.string_values)
    assert {
        ModelScriptArtifact,
        LoadedE2E01Artifacts,
        dict,
        list,
    }.isdisjoint(reachable.value_types)

    request_output = asyncio.run(provider.propose_next_move(_request()))
    assert request_output.next_move_candidate.arguments == {"order_id": "O-1001"}
    with pytest.raises(ProviderProtocolError):
        asyncio.run(provider.plan_presentation(_presentation_input()))
    provider.assert_exhausted()


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
        _provider("script:e2e01-04-b:nonexistent-order").propose_next_move(_request())
    )
    assert output.next_move_candidate.arguments == {"order_id": "O-9999"}
