from __future__ import annotations

import json
from pathlib import Path
from typing import Any


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
    "INJECT_STALE_TASK_STATE_VERSION": "GATE_REJECTED",
    "INJECT_TRUSTED_FIELD_OVERRIDE": "GATE_REJECTED",
    "INJECT_UNKNOWN_TOOL_NAME": "GATE_REJECTED",
    "INJECT_INVALID_PRESENTATION_SCHEMA": "PROVIDER_PROTOCOL_ERROR",
    "INJECT_FACT_BEARING_PRESENTATION_PLAN": (
        "PRESENTATION_PLAN_REJECTED"
    ),
}

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
    return {
        scenario["model_script_ref"]: scenario
        for scenario in catalog["scenarios"]
    }


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
        assert set(scenario["case_refs"]) == expected_case_refs_by_script[
            script_ref
        ]


def test_scenario_behaviors_have_deterministic_error_mappings() -> None:
    for scenario in _script_by_ref().values():
        behaviors = [step["behavior"] for step in scenario["steps"]]
        assert set(behaviors) <= ALLOWED_BEHAVIORS

        injected_behaviors = [
            behavior
            for behavior in behaviors
            if behavior.startswith("INJECT_")
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
        assert (
            expected_result["gate_reason_code"]
            == "ARGUMENT_BINDING_MISMATCH"
        )
        assert expected_result["tool_calls"] == 0
        assert expected_result["order_reads"] == 0
        assert expected_result["observation_records"] == 0
        assert expected_result["presentation_model_calls"] == 0


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
        assert (
            expected_result["response_policy"]
            == "FIXED_SAFE_PROCESSING_ERROR"
        )
        assert expected_result["tool_calls"] == 0
        assert expected_result["order_reads"] == 0
        assert expected_result["observation_records"] == 0
        assert expected_result["presentation_model_calls"] == 0


def test_presentation_faults_preserve_observation_but_skip_renderer() -> None:
    presentation_faults = [
        scenario
        for scenario in _script_by_ref().values()
        if scenario["model_script_ref"].startswith(
            "script:fault-presentation:"
        )
    ]
    assert presentation_faults

    for scenario in presentation_faults:
        expected_result = scenario["expected_control_result"]
        assert expected_result["user_outcome"] == "BLOCKED"
        assert (
            expected_result["response_policy"]
            == "FIXED_SAFE_PROCESSING_ERROR"
        )
        assert expected_result["tool_calls"] == 1
        assert expected_result["order_reads"] == 1
        assert expected_result["observation_records"] == 1
        assert expected_result["presentation_model_calls"] == 1
        assert expected_result["renderer_calls"] == 0

        presentation_steps = [
            step
            for step in scenario["steps"]
            if step["purpose"] == "PRESENTATION"
        ]
        assert len(presentation_steps) == 1
        assert set(presentation_steps[0]).isdisjoint(
            CONTROLLED_FACT_FIELDS
        )


def test_valid_presentation_script_carries_references_not_fact_values() -> None:
    success_script = _script_by_ref()["script:e2e01-01:success"]
    presentation_step = next(
        step
        for step in success_script["steps"]
        if step["purpose"] == "PRESENTATION"
    )

    assert presentation_step == {
        "purpose": "PRESENTATION",
        "behavior": "VALID_ORDER_SUMMARY_PLAN",
        "fact_source": "SAFE_ORDER_OBSERVATION",
    }
    assert set(presentation_step).isdisjoint(CONTROLLED_FACT_FIELDS)


def test_foreign_and_nonexistent_cases_share_observable_result_shape() -> None:
    dataset = _load_json(CASES_PATH)
    scripts = _script_by_ref()
    cases = {
        case["case_id"]: case
        for case in dataset["cases"]
    }
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
        scripts[
            "script:e2e01-04-a:foreign-order"
        ]["expected_control_result"]
        == scripts[
            "script:e2e01-04-b:nonexistent-order"
        ]["expected_control_result"]
    )


def test_lane_case_selection_keeps_fault_injection_off_real_provider() -> None:
    lanes = _load_json(LANES_PATH)
    lane_by_name = {
        lane["lane"]: lane
        for lane in lanes["lanes"]
    }
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
