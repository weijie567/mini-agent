from __future__ import annotations

import asyncio
import os
import socket
from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest
from pydantic import BaseModel

from mini_agent.application.ports import (
    Cycle2RequestUnderstandingProvider,
    ModelProviderV2,
)
from mini_agent.application.records import (
    Cycle2ControlPurpose,
    ProviderProtocolError,
    RequestUnderstandingCandidateInvalidError,
)
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
    Cycle2ControlCandidateKind,
    Cycle2InitialRequestUnderstandingOutputV2,
    Cycle2InputCandidate,
    RequestUnderstandingInput,
    RequestUnderstandingOutputV2,
)
from mini_agent.core.request_processing import (
    _canonical_cycle2_request_and_candidate,
)
from mini_agent.core.tool_system import ToolSpec, compute_model_visible_toolset_hash
import mini_agent.evaluation.artifacts as artifact_module
from mini_agent.evaluation.artifacts import (
    LoadedE2E01Artifacts,
    ModelScriptArtifact,
    load_e2e01_artifacts,
    load_e2e01_cycle2_artifacts,
)
import mini_agent.evaluation.scripted_provider as scripted_provider_module
from mini_agent.evaluation.scripted_provider import (
    Cycle2ScriptDirective,
    ScriptedModelProviderV2,
)


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
        schema_version="e2e01-thin-v1",
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


def _provider(script_ref: str) -> ScriptedModelProviderV2:
    artifacts = load_e2e01_artifacts(REPO_ROOT, candidate_version="candidate")
    provider = ScriptedModelProviderV2(
        artifacts.script_by_ref(script_ref),
        script_execution_ref=SCRIPT_EXECUTION_REF,
    )
    assert isinstance(provider, ModelProviderV2)
    return provider


def _cycle2_provider(case_id: str) -> ScriptedModelProviderV2:
    artifacts = load_e2e01_cycle2_artifacts(
        REPO_ROOT,
        candidate_version="candidate:cycle2",
    )
    return ScriptedModelProviderV2(
        artifacts.script_by_ref(f"script:{case_id}"),
        script_execution_ref=SCRIPT_EXECUTION_REF,
    )


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


def _implementation_traceback_state(
    error: BaseException,
) -> tuple[tuple[str, ...], _ReachableState]:
    frame_names: list[str] = []
    frame_locals: list[dict[str, object]] = []
    traceback = error.__traceback__
    while traceback is not None:
        frame = traceback.tb_frame
        if frame.f_globals.get("__name__") == (
            "mini_agent.evaluation.scripted_provider"
        ):
            frame_names.append(frame.f_code.co_name)
            frame_locals.append(dict(frame.f_locals))
        traceback = traceback.tb_next
    return tuple(frame_names), _reachable_state(tuple(frame_locals))


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
    provider = ScriptedModelProviderV2(
        script,
        script_execution_ref=SCRIPT_EXECUTION_REF,
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
    assert provider.script_execution_ref == SCRIPT_EXECUTION_REF
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
    assert output.task_delta_candidates[0].candidate_id == uuid5(
        NAMESPACE_URL,
        f"script-execution:{SCRIPT_EXECUTION_REF}:{MESSAGE_REF}",
    )
    assert output.task_delta_candidates[0].candidate_id != uuid5(
        NAMESPACE_URL,
        f"{script.model_script_ref}:{MESSAGE_REF}",
    )


def test_execution_only_provider_drops_fact_bearing_raw_payload() -> None:
    artifacts = load_e2e01_artifacts(REPO_ROOT, candidate_version="candidate")
    script = artifacts.script_by_ref(
        "script:fault-presentation:fact-bearing-envelope"
    )
    provider = ScriptedModelProviderV2(
        script,
        script_execution_ref=SCRIPT_EXECUTION_REF,
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

    assert type(output) is RequestUnderstandingOutputV2
    assert output.message_ref == MESSAGE_REF
    assert output.next_move_candidate.base_task_state_version is None
    assert output.next_move_candidate.requested_tool_name == "get_order"
    assert output.next_move_candidate.arguments == {"order_id": expected_order}
    if script_ref == "script:e2e01-01:success":
        plan = asyncio.run(provider.plan_presentation(_presentation_input()))
        assert type(plan) is PresentationPlan
    provider.assert_exhausted()


@pytest.mark.parametrize(
    ("script_ref", "expected_order", "expected_tool"),
    [
        ("script:e2e01-01:success", "O-1001", "get_order"),
        ("script:e2e01-04-a:foreign-order", "O-2001", "get_order"),
        ("script:fault-provider:unknown-tool-name", "O-1001", "get_any_order"),
    ],
)
def test_v2_scripts_return_canonical_contextualized_candidates(
    script_ref: str,
    expected_order: str,
    expected_tool: str,
) -> None:
    output = asyncio.run(
        _provider(script_ref).propose_next_move(
            _request("请查一下这个订单"),
        )
    )

    assert type(output) is RequestUnderstandingOutputV2
    assert output.schema_version == "e2e01-thin-v2"
    assert output.message_ref == MESSAGE_REF
    assert output.contextualization.text == "请查一下这个订单"
    assert output.contextualization.source_message_refs == (MESSAGE_REF,)
    assert output.contextualization.uncertainties == ()
    assert len(output.contextualization.resolved_reference_candidates) == 1
    resolved = output.contextualization.resolved_reference_candidates[0]
    assert resolved.candidate_value == expected_order
    assert resolved.source_ref == MESSAGE_REF
    assert resolved.source_quote == expected_order
    assert output.task_delta_candidates[0].candidate_id == uuid5(
        NAMESPACE_URL,
        f"script-execution:{SCRIPT_EXECUTION_REF}:{MESSAGE_REF}",
    )
    assert output.next_move_candidate.requested_tool_name == expected_tool
    assert output.next_move_candidate.arguments == {"order_id": expected_order}


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
    assert type(output) is RequestUnderstandingOutputV2
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
def test_v2_invalid_candidates_expose_fresh_bounded_candidate_errors(
    script_ref: str,
) -> None:
    errors = []
    for _ in range(2):
        with pytest.raises(
            RequestUnderstandingCandidateInvalidError
        ) as caught:
            asyncio.run(
                _provider(script_ref).propose_next_move(_request())
            )
        errors.append(caught.value)
        assert caught.value.args == (
            "REQUEST_UNDERSTANDING_CANDIDATE_INVALID",
        )
        assert caught.value.__cause__ is None
        assert caught.value.__context__ is None
        assert script_ref not in str(caught.value)
        frame_names, reachable = _implementation_traceback_state(caught.value)
        assert frame_names == ("propose_next_move",)
        assert "customer-B" not in reachable.string_values
        assert RequestUnderstandingInput not in reachable.value_types
        assert type(_provider(script_ref)) not in reachable.value_types
    assert errors[0] is not errors[1]


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
        "script:fault-provider:zero-target-functions",
        "script:fault-provider:multiple-target-functions",
    ],
)
def test_v2_request_framing_faults_remain_fresh_protocol_errors(
    script_ref: str,
) -> None:
    errors = []
    for _ in range(2):
        provider_type = type(_provider(script_ref))
        with pytest.raises(ProviderProtocolError) as caught:
            asyncio.run(_provider(script_ref).propose_next_move(_request()))
        errors.append(caught.value)
        assert not isinstance(
            caught.value,
            RequestUnderstandingCandidateInvalidError,
        )
        assert caught.value.args == ("PROVIDER_PROTOCOL_ERROR",)
        assert caught.value.__cause__ is None
        assert caught.value.__context__ is None
        frame_names, reachable = _implementation_traceback_state(caught.value)
        assert frame_names == ("propose_next_move",)
        assert RequestUnderstandingInput not in reachable.value_types
        assert provider_type not in reachable.value_types
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


@pytest.mark.parametrize(
    "script_ref",
    [
        "script:fault-presentation:zero-target-functions",
        "script:fault-presentation:multiple-target-functions",
        "script:fault-presentation:invalid-schema",
        "script:fault-presentation:fact-bearing-envelope",
    ],
)
def test_v2_presentation_faults_remain_protocol_errors(
    script_ref: str,
) -> None:
    errors = []
    for _ in range(2):
        provider = _provider(script_ref)
        provider_type = type(provider)
        asyncio.run(provider.propose_next_move(_request()))
        with pytest.raises(ProviderProtocolError) as caught:
            asyncio.run(provider.plan_presentation(_presentation_input()))
        errors.append(caught.value)
        assert caught.value.args == ("PROVIDER_PROTOCOL_ERROR",)
        assert caught.value.__cause__ is None
        assert caught.value.__context__ is None
        frame_names, reachable = _implementation_traceback_state(caught.value)
        assert frame_names == ("plan_presentation",)
        assert "O-1001 已发货" not in reachable.string_values
        assert PresentationInput not in reachable.value_types
        assert provider_type not in reachable.value_types
    assert errors[0] is not errors[1]


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
        _provider(
            "script:e2e01-04-b:nonexistent-order"
        ).propose_next_move(_request())
    )
    assert type(output) is RequestUnderstandingOutputV2
    assert output.next_move_candidate.arguments == {"order_id": "O-9999"}


def test_cycle2_provider_consumes_ordered_candidate_and_fault_directives() -> None:
    provider = _cycle2_provider("E2E01-06/transient-once-then-success")

    request = provider.take_cycle2_directive("REQUEST_UNDERSTANDING")
    fault = provider.take_cycle2_directive("FAULT_DIRECTIVE")
    control = provider.take_cycle2_directive("CONTROL_CANDIDATE")

    assert request == Cycle2ScriptDirective(
        purpose="REQUEST_UNDERSTANDING",
        behavior="PROPOSE_GET_SHIPMENT",
        candidate_arguments={"order_id": "O-1001"},
        fault_ref=None,
    )
    assert control == Cycle2ScriptDirective(
        purpose="CONTROL_CANDIDATE",
        behavior="PROPOSE_SHIPMENT_ASSESSMENT",
        candidate_arguments={},
        fault_ref=None,
    )
    assert fault == Cycle2ScriptDirective(
        purpose="FAULT_DIRECTIVE",
        behavior="INJECT_TOOL_FAULT",
        candidate_arguments={},
        fault_ref="fault:get-shipment:transient-once-v1",
    )
    provider.assert_exhausted()


def test_cycle2_provider_implements_active_port_and_initial_claim() -> None:
    provider = _cycle2_provider("E2E01-02/unique-own-with-foreign-decoy")
    assert isinstance(provider, Cycle2RequestUnderstandingProvider)

    output = asyncio.run(provider.propose_cycle2_initial(_request("最近买的鞋")))

    assert type(output) is Cycle2InitialRequestUnderstandingOutputV2
    assert output.message_ref == MESSAGE_REF
    assert output.task_delta_candidates[0].input_candidates == (
        Cycle2InputCandidate(
            name="product_description",
            candidate_value="鞋",
            source_ref=MESSAGE_REF,
            source_quote="鞋",
            confidence=0.99,
        ),
    )
    assert output.next_move_candidate.requested_tool_name == "search_orders"
    assert output.next_move_candidate.arguments == {"product_description": "鞋"}


@pytest.mark.parametrize(
    ("case_id", "expected_name", "expected_value"),
    (
        ("E2E01-03/current-second-selected", "candidate_ordinal", 2),
        ("T2-candidate-out-of-range-rejected", "candidate_ordinal", 6),
        ("E2E01-05/order-only-no-shipment", "order_id", "O-1001"),
        ("E2E01-06/stale-refresh-success", "order_id", "O-1001"),
    ),
)
def test_cycle2_provider_projects_exact_continuation_claims(
    case_id: str,
    expected_name: str,
    expected_value: object,
) -> None:
    provider = _cycle2_provider(case_id)

    candidate = asyncio.run(provider.propose_cycle2_continuation(_request()))

    assert type(candidate) is Cycle2InputCandidate
    assert candidate.name == expected_name
    assert candidate.candidate_value == expected_value
    assert candidate.source_ref == MESSAGE_REF


@pytest.mark.parametrize(
    ("case_id", "message", "ordinal"),
    (
        ("E2E01-03/current-second-selected", "第二个", 2),
        ("T2-candidate-out-of-range-rejected", "第六个", 6),
    ),
)
def test_cycle2_provider_ordinal_quote_passes_core_provenance_gate(
    case_id: str,
    message: str,
    ordinal: int,
) -> None:
    request = _request(message)
    candidate = asyncio.run(
        _cycle2_provider(case_id).propose_cycle2_continuation(request)
    )

    assert candidate == Cycle2InputCandidate(
        name="candidate_ordinal",
        candidate_value=ordinal,
        source_ref=MESSAGE_REF,
        source_quote=message,
        confidence=0.99,
    )
    canonical_request, canonical_candidate, authoritative_message = (
        _canonical_cycle2_request_and_candidate(
            request_input=request,
            candidate=candidate,
            authoritative_messages={MESSAGE_REF: message},
        )
    )
    assert canonical_request == request
    assert canonical_candidate == candidate
    assert authoritative_message == message


def test_cycle2_provider_projects_exact_zero_one_two_control_matrix() -> None:
    order_only = _cycle2_provider("E2E01-05/order-only-no-shipment")
    asyncio.run(order_only.propose_cycle2_continuation(_request()))
    summary = asyncio.run(
        order_only.propose_cycle2_control(
            _request(), Cycle2ControlPurpose.PROPOSE_POST_ORDER
        )
    )
    assert summary.kind is Cycle2ControlCandidateKind.FINISH
    order_only.assert_exhausted()

    logistics = _cycle2_provider(
        "E2E01-05/logistics-required-uses-shipment"
    )
    asyncio.run(logistics.propose_cycle2_continuation(_request()))
    shipment = asyncio.run(
        logistics.propose_cycle2_control(
            _request(), Cycle2ControlPurpose.PROPOSE_POST_ORDER
        )
    )
    assert shipment.kind is Cycle2ControlCandidateKind.CALL_TOOL
    assert shipment.requested_tool_name == "get_shipment"
    assessment = asyncio.run(
        logistics.propose_cycle2_control(
            _request(), Cycle2ControlPurpose.PROPOSE_SHIPMENT_ASSESSMENT
        )
    )
    assert assessment.kind is Cycle2ControlCandidateKind.FINISH
    logistics.assert_exhausted()

    no_result = _cycle2_provider(
        "T2-retry-finalize-before-second-fence-state-invalidated"
    )
    asyncio.run(no_result.propose_cycle2_continuation(_request()))
    no_result.take_cycle2_directive("FAULT_DIRECTIVE")
    no_result.assert_exhausted()


@pytest.mark.parametrize(
    ("case_id", "purpose"),
    (
        (
            "E2E01-02/unique-own-with-foreign-decoy",
            Cycle2ControlPurpose.PROPOSE_GET_ORDER,
        ),
        (
            "E2E01-03/multiple-minimum-summary",
            Cycle2ControlPurpose.PROPOSE_CANDIDATE_QUESTION,
        ),
        (
            "E2E01-06/stale-refresh-success",
            Cycle2ControlPurpose.PROPOSE_SHIPMENT_ASSESSMENT,
        ),
        (
            "E2E01-06/no-shipment-need-human",
            Cycle2ControlPurpose.PROPOSE_FIXED_RESPONSE,
        ),
    ),
)
def test_cycle2_provider_projects_matching_control_purposes(
    case_id: str,
    purpose: Cycle2ControlPurpose,
) -> None:
    provider = _cycle2_provider(case_id)
    first = provider.take_cycle2_directive("REQUEST_UNDERSTANDING")
    assert first.purpose == "REQUEST_UNDERSTANDING"

    candidate = asyncio.run(provider.propose_cycle2_control(_request(), purpose))

    if purpose is Cycle2ControlPurpose.PROPOSE_GET_ORDER:
        assert candidate.kind is Cycle2ControlCandidateKind.CALL_TOOL
        assert candidate.requested_tool_name == "get_order"
    else:
        assert candidate.kind is Cycle2ControlCandidateKind.FINISH
        assert candidate.requested_tool_name is None
    provider.assert_exhausted()


def test_cycle2_provider_active_control_mismatch_and_duplicate_fail_closed() -> None:
    provider = _cycle2_provider("E2E01-03/multiple-minimum-summary")
    asyncio.run(provider.propose_cycle2_initial(_request("最近买的鞋")))

    with pytest.raises(ProviderProtocolError):
        asyncio.run(
            provider.propose_cycle2_control(
                _request(), Cycle2ControlPurpose.PROPOSE_FIXED_RESPONSE
            )
        )
    with pytest.raises(ProviderProtocolError):
        asyncio.run(
            provider.propose_cycle2_control(
                _request(), Cycle2ControlPurpose.PROPOSE_CANDIDATE_QUESTION
            )
        )


def test_cycle2_provider_purpose_cursor_fails_closed() -> None:
    provider = _cycle2_provider("E2E01-03/current-second-selected")

    with pytest.raises(ProviderProtocolError):
        provider.take_cycle2_directive("CONTROL_CANDIDATE")


def test_cycle2_provider_reachable_state_excludes_oracles_and_business_truth() -> None:
    provider = _cycle2_provider(
        "T2-assessment-delivered-not-received-current-claim"
    )
    reachable = _reachable_state(provider)

    assert {
        "expected_control_result",
        "case_refs",
        "required_events",
        "forbidden_events",
        "state_assertions",
        "disclosure_assertions",
        "critical_failure_refs",
        "trace_events",
        "business_evidence",
        "grader_result",
        "customer_id",
        "owner_customer_id",
    }.isdisjoint(reachable.field_names)
    assert {
        "DELIVERED_NOT_RECEIVED",
        "COMPLETED",
        "GOAL_COMPLETED",
        "SHIPMENT_RENDERER_WHITELIST_EXACT",
    }.isdisjoint(reachable.string_values)


def test_cycle2_provider_rejects_unknown_directive_fields_and_behaviors() -> None:
    script = ModelScriptArtifact(
        model_script_ref="script:test:invalid-cycle2",
        case_refs=("test:invalid-cycle2",),
        steps=(
            {
                "purpose": "CONTROL_CANDIDATE",
                "behavior": "FABRICATE_EVIDENCE",
                "business_evidence": {"status": "DELIVERED"},
            },
        ),
        expected_control_result={"authority": "NONE"},
    )

    with pytest.raises(artifact_module.ArtifactContractError):
        ScriptedModelProviderV2(
            script,
            script_execution_ref=SCRIPT_EXECUTION_REF,
        )

    private_candidate = ModelScriptArtifact(
        model_script_ref="script:test:private-cycle2",
        case_refs=("test:private-cycle2",),
        steps=(
            {
                "purpose": "REQUEST_UNDERSTANDING",
                "behavior": "PROPOSE_GET_SHIPMENT",
                "candidate_arguments": {
                    "order_id": "O-1001",
                    "customer_id": "customer-A",
                },
            },
        ),
        expected_control_result={"authority": "NONE"},
    )
    with pytest.raises(artifact_module.ArtifactContractError):
        ScriptedModelProviderV2(
            private_candidate,
            script_execution_ref=SCRIPT_EXECUTION_REF,
        )
