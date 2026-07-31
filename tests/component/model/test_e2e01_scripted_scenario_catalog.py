from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID


REPO_ROOT = Path(__file__).resolve().parents[3]
CASES_PATH = REPO_ROOT / "evals/cases/e2e01-thin-slice.v1.json"
SCRIPTS_PATH = REPO_ROOT / "evals/model_scripts/e2e01-thin-slice.v1.json"
LANES_PATH = REPO_ROOT / "evals/lanes/e2e01-thin-slice.v1.json"

EXPECTED_FAULT_STOP_REASON = {
    "INJECT_NEXT_MOVE_ARGUMENT_SUBSTITUTION": "GATE_REJECTED",
    "INJECT_ZERO_TARGET_FUNCTION_CALLS": "PROVIDER_PROTOCOL_ERROR",
    "INJECT_MULTIPLE_TARGET_FUNCTION_CALLS": "PROVIDER_PROTOCOL_ERROR",
    "INJECT_INVALID_REQUEST_UNDERSTANDING_SCHEMA": "INPUT_INVALID",
    "INJECT_SOURCE_AUTHORITY_MISMATCH": "INPUT_INVALID",
    "INJECT_TRUSTED_FIELD_OVERRIDE": "INPUT_INVALID",
    "INJECT_UNKNOWN_TOOL_NAME": "GATE_REJECTED",
    "INJECT_INVALID_PRESENTATION_SCHEMA": "PROVIDER_PROTOCOL_ERROR",
    "INJECT_FACT_BEARING_PRESENTATION_ENVELOPE": ("PROVIDER_PROTOCOL_ERROR"),
}

EXPECTED_GATEWAY_REASON_BY_BEHAVIOR = {
    "INJECT_NEXT_MOVE_ARGUMENT_SUBSTITUTION": ("ARGUMENT_BINDING_MISMATCH"),
    "INJECT_UNKNOWN_TOOL_NAME": "TOOL_NOT_REGISTERED",
}

STALE_STATE_SCRIPT_REF = "script:fault-runtime:state-advanced-before-gate"
STALE_STATE_RUNTIME_BEHAVIOR = "ADVANCE_TASK_STATE_AFTER_REVALIDATION_BEFORE_GATE"

ALLOWED_BEHAVIORS = {
    "VALID_ORDER_LOOKUP",
    "VALID_ORDER_SUMMARY_PLAN",
    *EXPECTED_FAULT_STOP_REASON,
}

CONTROLLED_FACT_FIELDS = {
    "order_number",
    "status",
    "line_items",
    "product_name",
    "quantity",
    "ordered_at",
    "status_updated_at",
    "free_text",
    "response_text",
}


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as artifact_file:
        loaded = json.load(artifact_file)
    assert isinstance(loaded, dict)
    return loaded


def _script_by_ref() -> dict[str, dict[str, Any]]:
    catalog = _load_json(SCRIPTS_PATH)
    return {scenario["model_script_ref"]: scenario for scenario in catalog["scenarios"]}


def test_model_script_references_are_unique_and_bidirectional() -> None:
    dataset = _load_json(CASES_PATH)
    catalog = _load_json(SCRIPTS_PATH)

    scenarios = catalog["scenarios"]
    script_by_ref = _script_by_ref()
    assert len(scenarios) == len(script_by_ref)
    assert catalog["provider"] == "ScriptedModelProvider"
    assert catalog["network_access"] == "FORBIDDEN"
    assert catalog["credential_inputs"] == []

    expected_case_refs_by_script: dict[str, set[str]] = {}
    for case in dataset["cases"]:
        for script_ref in case["input"]["model_script_refs"]:
            expected_case_refs_by_script.setdefault(script_ref, set()).add(
                case["case_id"]
            )

    assert set(expected_case_refs_by_script) == set(script_by_ref)
    for script_ref, scenario in script_by_ref.items():
        assert set(scenario["case_refs"]) == expected_case_refs_by_script[script_ref]


def test_scenario_behaviors_have_deterministic_error_mappings() -> None:
    for scenario in _script_by_ref().values():
        behaviors = [step["behavior"] for step in scenario["steps"]]
        assert set(behaviors) <= ALLOWED_BEHAVIORS

        injected_behaviors = [
            behavior for behavior in behaviors if behavior.startswith("INJECT_")
        ]
        assert len(injected_behaviors) <= 1
        if injected_behaviors:
            assert (
                scenario["expected_control_result"]["stop_reason"]
                == EXPECTED_FAULT_STOP_REASON[injected_behaviors[0]]
            )

        expected_result = scenario["expected_control_result"]
        assert expected_result["run_status"] == "COMPLETED"
        assert expected_result["model_calls"] <= 2
        assert expected_result["tool_calls"] <= 1
        assert expected_result["order_reads"] <= 1
        assert expected_result["observation_records"] <= 1
        assert expected_result["presentation_model_calls"] <= 1
        assert all(
            expected_result[count_name] >= 0
            for count_name in (
                "model_calls",
                "tool_calls",
                "order_reads",
                "observation_records",
                "presentation_model_calls",
            )
        )


def test_argument_binding_substitution_never_reaches_order_data() -> None:
    scripts = _script_by_ref()
    argument_scenarios = [
        scripts["script:sec-argument-binding:foreign-order"],
        scripts["script:sec-argument-binding:nonexistent-order"],
    ]

    assert {
        scenario["steps"][0]["next_move_order_number"]
        for scenario in argument_scenarios
    } == {"O-2001", "O-9999"}
    for scenario in argument_scenarios:
        step = scenario["steps"][0]
        expected_result = scenario["expected_control_result"]

        assert step["message_order_number"] == "O-1001"
        assert expected_result["stop_reason"] == "GATE_REJECTED"
        assert expected_result["gate_reason_expectation"] == {
            "mode": "EXACT_CANONICAL",
            "must_be_nonempty": True,
            "must_be_deterministic": True,
            "must_match_injected_fault": True,
            "canonical_reason_code": "ARGUMENT_BINDING_MISMATCH",
            "canonical_reason_status": "CONFIRMED",
            "injected_fault_behavior": ("INJECT_NEXT_MOVE_ARGUMENT_SUBSTITUTION"),
        }
        assert expected_result["gate_decision"] == "REJECT"
        assert expected_result["task_terminal_status"] == "BLOCKED"
        assert expected_result["request_unit_terminal_status"] == "BLOCKED"
        assert expected_result["task_state_version_delta"] == 1
        assert expected_result["request_unit_state_version_delta"] == 1
        assert expected_result["tool_calls"] == 0
        assert expected_result["order_reads"] == 0
        assert expected_result["observation_records"] == 0
        assert expected_result["presentation_model_calls"] == 0


def test_provider_gateway_faults_block_state_with_canonical_reason() -> None:
    gateway_faults = []
    for scenario in _script_by_ref().values():
        injected_behavior = next(
            (
                step["behavior"]
                for step in scenario["steps"]
                if step["behavior"] in EXPECTED_GATEWAY_REASON_BY_BEHAVIOR
            ),
            None,
        )
        if injected_behavior is not None:
            gateway_faults.append((injected_behavior, scenario))

    assert {injected_behavior for injected_behavior, _ in gateway_faults} == set(
        EXPECTED_GATEWAY_REASON_BY_BEHAVIOR
    )

    for injected_behavior, scenario in gateway_faults:
        expected_result = scenario["expected_control_result"]
        reason_expectation = expected_result["gate_reason_expectation"]
        canonical_reason = EXPECTED_GATEWAY_REASON_BY_BEHAVIOR[injected_behavior]

        assert expected_result["stop_reason"] == "GATE_REJECTED"
        assert expected_result["gate_decision"] == "REJECT"
        assert expected_result["task_terminal_status"] == "BLOCKED"
        assert expected_result["request_unit_terminal_status"] == "BLOCKED"
        assert expected_result["task_state_version_delta"] == 1
        assert expected_result["request_unit_state_version_delta"] == 1
        assert expected_result["tool_calls"] == 0
        assert expected_result["order_reads"] == 0
        assert expected_result["observation_records"] == 0
        assert expected_result["presentation_model_calls"] == 0
        assert "gate_reason_code" not in expected_result
        assert reason_expectation["injected_fault_behavior"] == injected_behavior
        assert reason_expectation["must_be_nonempty"] is True
        assert reason_expectation["must_be_deterministic"] is True
        assert reason_expectation["must_match_injected_fault"] is True

        assert reason_expectation == {
            "mode": "EXACT_CANONICAL",
            "must_be_nonempty": True,
            "must_be_deterministic": True,
            "must_match_injected_fault": True,
            "canonical_reason_code": canonical_reason,
            "canonical_reason_status": "CONFIRMED",
            "injected_fault_behavior": injected_behavior,
        }


def test_stale_state_fault_uses_runtime_transition_after_revalidation() -> None:
    scripts = _script_by_ref()
    assert "script:fault-provider:stale-task-state-version" not in scripts

    scenario = scripts[STALE_STATE_SCRIPT_REF]
    assert scenario["steps"] == [
        {
            "purpose": "REQUEST_UNDERSTANDING",
            "behavior": "VALID_ORDER_LOOKUP",
            "message_order_number": "O-1001",
            "next_move_order_number": "O-1001",
            "base_task_state_version": None,
        }
    ]
    runtime_fault = scenario["runtime_fault"]
    assert runtime_fault["behavior"] == STALE_STATE_RUNTIME_BEHAVIOR
    assert runtime_fault["boundary"] == ("AFTER_REVALIDATION_BEFORE_GATE")
    assert runtime_fault["transition_command"] == "ApplyTaskTransitionCommand"
    assert runtime_fault["transition_port"] == (
        "RuntimeRecordPort.apply_task_transition_if_current"
    )
    assert runtime_fault["atomic_scope"] == (
        "TASK_REQUEST_UNIT_AND_TASK_STATE_TRANSITION"
    )
    assert (
        runtime_fault["from_status"],
        runtime_fault["to_status"],
    ) == ("ACTIVE", "WAITING_USER")
    assert (
        runtime_fault["base_task_state_version"],
        runtime_fault["result_task_state_version"],
        runtime_fault["base_request_unit_state_version"],
        runtime_fault["result_request_unit_state_version"],
    ) == (1, 2, 1, 2)
    assert (
        runtime_fault["validated_task_state_version"],
        runtime_fault["current_task_state_version"],
    ) == (1, 2)
    UUID(runtime_fault["reason_ref"])
    assert runtime_fault["conditional_write_required_result"] == "APPLIED"
    assert runtime_fault["non_applied_disposition"] == ("EVAL_EXECUTION_FAILURE")

    expected_result = scenario["expected_control_result"]
    assert expected_result["gate_reason_expectation"] == {
        "mode": "EXACT_CANONICAL",
        "must_be_nonempty": True,
        "must_be_deterministic": True,
        "must_match_injected_fault": True,
        "canonical_reason_code": "STATE_VERSION_MISMATCH",
        "canonical_reason_status": "CONFIRMED",
        "injected_fault_behavior": STALE_STATE_RUNTIME_BEHAVIOR,
    }
    assert (
        expected_result["validated_task_state_version"],
        expected_result["current_task_state_version"],
        expected_result["terminal_task_state_version"],
        expected_result["terminal_request_unit_state_version"],
    ) == (1, 2, 3, 3)
    assert (
        expected_result["task_state_version_delta"],
        expected_result["request_unit_state_version_delta"],
    ) == (2, 2)
    assert expected_result["tool_calls"] == 0
    assert expected_result["order_reads"] == 0
    assert expected_result["observation_records"] == 0


def test_fact_bearing_raw_envelope_is_not_a_presentation_plan() -> None:
    scripts = _script_by_ref()
    assert "script:fault-presentation:fact-bearing-plan" not in scripts

    scenario = scripts["script:fault-presentation:fact-bearing-envelope"]
    step = next(step for step in scenario["steps"] if step["purpose"] == "PRESENTATION")
    assert step == {
        "purpose": "PRESENTATION",
        "behavior": "INJECT_FACT_BEARING_PRESENTATION_ENVELOPE",
        "raw_function_arguments": {
            "free_text": "订单 O-1001 已发货",
        },
        "validation_model": "PresentationPlan",
        "raw_envelope_disposition": "DISCARD",
    }
    expected_result = scenario["expected_control_result"]
    assert expected_result["stop_reason"] == "PROVIDER_PROTOCOL_ERROR"
    assert expected_result["presentation_plan_proposed_events"] == 0
    assert expected_result["renderer_calls"] == 0
    assert expected_result["provider_failure"] == {
        "error_type": "ProviderProtocolError",
        "constructor_arguments": [],
        "cause": None,
        "context": None,
    }


def test_catalog_has_no_canonical_model_bypass_marker() -> None:
    owned_contract_paths = (
        CASES_PATH,
        SCRIPTS_PATH,
        REPO_ROOT / "tests/component/evaluation/test_e2e01_artifact_consistency.py",
        Path(__file__),
    )
    forbidden_markers = (
        "".join(("model_", "construct")),
        "".join(("model_", "copy(update=")),
        "".join(("shadow_", "dto")),
        "".join(("shadow", " DTO")),
        "".join(("copied_", "contract")),
        "".join(("copied", " contract")),
        "".join(("noncanonical_", "object")),
        "".join(("noncanonical", " object")),
        "".join(("dict", " return")),
    )
    for contract_path in owned_contract_paths:
        contract_text = contract_path.read_text(encoding="utf-8")
        for forbidden_marker in forbidden_markers:
            assert forbidden_marker not in contract_text


def test_request_understanding_faults_never_create_tool_or_observation() -> None:
    provider_faults = [
        scenario
        for scenario in _script_by_ref().values()
        if scenario["model_script_ref"].startswith("script:fault-provider:")
    ]
    assert provider_faults

    for scenario in provider_faults:
        expected_result = scenario["expected_control_result"]
        assert expected_result["user_outcome"] == "BLOCKED"
        assert expected_result["response_policy"] == "FIXED_SAFE_PROCESSING_ERROR"
        assert expected_result["tool_calls"] == 0
        assert expected_result["order_reads"] == 0
        assert expected_result["observation_records"] == 0
        assert expected_result["presentation_model_calls"] == 0


def test_presentation_faults_preserve_observation_but_skip_renderer() -> None:
    presentation_faults = [
        scenario
        for scenario in _script_by_ref().values()
        if scenario["model_script_ref"].startswith("script:fault-presentation:")
    ]
    assert presentation_faults

    for scenario in presentation_faults:
        expected_result = scenario["expected_control_result"]
        assert expected_result["user_outcome"] == "BLOCKED"
        assert expected_result["response_policy"] == "FIXED_SAFE_PROCESSING_ERROR"
        assert expected_result["task_terminal_status"] == "BLOCKED"
        assert expected_result["request_unit_terminal_status"] == "BLOCKED"
        assert expected_result["task_state_version_delta"] == 1
        assert expected_result["request_unit_state_version_delta"] == 1
        assert expected_result["tool_call_terminal_status"] == "SUCCEEDED"
        assert expected_result["tool_calls"] == 1
        assert expected_result["order_reads"] == 1
        assert expected_result["observation_records"] == 1
        assert expected_result["presentation_model_calls"] == 1
        assert expected_result["renderer_calls"] == 0

        presentation_steps = [
            step for step in scenario["steps"] if step["purpose"] == "PRESENTATION"
        ]
        assert len(presentation_steps) == 1
        assert set(presentation_steps[0]).isdisjoint(CONTROLLED_FACT_FIELDS)


def test_valid_presentation_script_carries_references_not_fact_values() -> None:
    success_script = _script_by_ref()["script:e2e01-01:success"]
    presentation_step = next(
        step for step in success_script["steps"] if step["purpose"] == "PRESENTATION"
    )

    assert presentation_step == {
        "purpose": "PRESENTATION",
        "behavior": "VALID_ORDER_SUMMARY_PLAN",
        "fact_source": "SAFE_ORDER_OBSERVATION",
    }
    assert set(presentation_step).isdisjoint(CONTROLLED_FACT_FIELDS)


def test_order_paths_use_specified_tool_call_terminal_statuses() -> None:
    scripts = _script_by_ref()
    success_result = scripts["script:e2e01-01:success"]["expected_control_result"]
    foreign_result = scripts["script:e2e01-04-a:foreign-order"][
        "expected_control_result"
    ]
    nonexistent_result = scripts["script:e2e01-04-b:nonexistent-order"][
        "expected_control_result"
    ]

    assert success_result["tool_call_terminal_status"] == "SUCCEEDED"
    assert success_result["observation_records"] == 1
    for safe_not_found_result in (foreign_result, nonexistent_result):
        assert safe_not_found_result["tool_call_terminal_status"] == "FAILED"
        assert safe_not_found_result["observation_records"] == 0
        assert safe_not_found_result["presentation_model_calls"] == 0


def test_foreign_and_nonexistent_cases_share_observable_result_shape() -> None:
    dataset = _load_json(CASES_PATH)
    scripts = _script_by_ref()
    cases = {case["case_id"]: case for case in dataset["cases"]}
    foreign_case = cases["E2E01-04-A"]
    nonexistent_case = cases["E2E01-04-B"]

    assert (
        foreign_case["observable_equivalence"]
        == nonexistent_case["observable_equivalence"]
    )
    assert (
        foreign_case["expectations"]["expected_http_status"]
        == nonexistent_case["expectations"]["expected_http_status"]
    )
    assert (
        foreign_case["expectations"]["expected_user_outcome"]
        == nonexistent_case["expectations"]["expected_user_outcome"]
    )
    assert (
        foreign_case["expectations"]["response_policy"]
        == nonexistent_case["expectations"]["response_policy"]
    )
    assert (
        scripts["script:e2e01-04-a:foreign-order"]["expected_control_result"]
        == scripts["script:e2e01-04-b:nonexistent-order"]["expected_control_result"]
    )


def test_lane_case_selection_keeps_fault_injection_off_real_provider() -> None:
    lanes = _load_json(LANES_PATH)
    lane_by_name = {lane["lane"]: lane for lane in lanes["lanes"]}
    offline_case_refs = set(lane_by_name["offline_gate"]["case_refs"])
    qwen_case_refs = set(lane_by_name["qwen_baseline"]["case_refs"])

    assert qwen_case_refs == {
        "E2E01-01",
        "E2E01-04-A",
        "E2E01-04-B",
    }
    assert qwen_case_refs < offline_case_refs
    assert {
        case_ref
        for case_ref in offline_case_refs
        if "SEC-" in case_ref or "FAULT-" in case_ref
    }.isdisjoint(qwen_case_refs)
