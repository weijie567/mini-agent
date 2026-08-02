from __future__ import annotations

import hashlib
import json
import re
import shutil
from inspect import getsource, signature
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from pydantic import ValidationError

from mini_agent.application.ports import ModelProviderV2
from mini_agent.application.records import ConditionalWriteResult
from mini_agent.core.presentation import PresentationPlan
from mini_agent.core.request_understanding import (
    NextMove,
    RequestUnderstandingOutputV2,
)
from mini_agent.core.tool_system import (
    CYCLE2_TOOL_REGISTRY_VERSION,
    build_cycle2_registry_snapshot,
)
import mini_agent.evaluation.graders as graders_module
import mini_agent.evaluation.harness as harness_module
import mini_agent.evaluation.artifacts as artifacts_module
import mini_agent.evaluation.scripted_provider as scripted_provider_module
import mini_agent.infrastructure.model.qwen_responses as qwen_responses_module


REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_PATH = REPO_ROOT / "evals/fixtures/e2e01-thin-slice.v1.json"
CASES_PATH = REPO_ROOT / "evals/cases/e2e01-thin-slice.v1.json"
SCRIPTS_PATH = REPO_ROOT / "evals/model_scripts/e2e01-thin-slice.v1.json"
LANES_PATH = REPO_ROOT / "evals/lanes/e2e01-thin-slice.v1.json"
MANIFEST_PATH = REPO_ROOT / "evals/manifests/e2e01-thin-slice.v1.json"
SPEC_PATH = REPO_ROOT / "docs/implementation/e2e01-thin-slice-implementation-spec.md"
CYCLE2_FIXTURE_PATH = REPO_ROOT / "evals/fixtures/e2e01-cycle2.v1.json"
CYCLE2_CASES_PATH = REPO_ROOT / "evals/cases/e2e01-cycle2.v1.json"
CYCLE2_SCRIPTS_PATH = REPO_ROOT / "evals/model_scripts/e2e01-cycle2.v1.json"
CYCLE2_LANES_PATH = REPO_ROOT / "evals/lanes/e2e01-cycle2.v1.json"
CYCLE2_MANIFEST_PATH = REPO_ROOT / "evals/manifests/e2e01-cycle2.v1.json"

CYCLE2_ARTIFACT_PATHS = (
    CYCLE2_FIXTURE_PATH,
    CYCLE2_CASES_PATH,
    CYCLE2_SCRIPTS_PATH,
    CYCLE2_LANES_PATH,
    CYCLE2_MANIFEST_PATH,
)

CYCLE2_LONGITUDINAL_CASE_IDS = {
    "E2E01-02/unique-own-with-foreign-decoy",
    "E2E01-02/no-match-safe-not-found",
    "E2E01-03/multiple-minimum-summary",
    "E2E01-03/current-second-selected",
    "E2E01-03/expired-second-rejected",
    "E2E01-03/cross-task-second-rejected",
    "E2E01-05/order-only-no-shipment",
    "E2E01-05/logistics-required-uses-shipment",
    "E2E01-06/stale-refresh-success",
    "E2E01-06/transient-once-then-success",
    "E2E01-06/transient-exhausted-blocked",
    "E2E01-06/deterministic-source-integrity-no-retry",
    "E2E01-06/insufficient-promise-need-human",
    "E2E01-06/no-shipment-need-human",
}

CYCLE2_TRAJECTORY_CASE_IDS = {
    "T2-candidate-owner-mismatch-rejected",
    "T2-candidate-superseded-rejected",
    "T2-candidate-out-of-range-rejected",
    "T2-candidate-zero-or-multiple-current-rejected",
    "T2-assessment-delayed-boundary",
    "T2-assessment-delivered-not-received-current-claim",
    "T2-assessment-claim-corrected",
    "T2-timeout-after-dispatch-then-success",
    "T2-retry-finalize-before-second-fence-recovery",
    "T2-retry-finalize-before-second-fence-state-invalidated",
    "T2-retry-unfinished-attempt-restart-blocked",
    "T2-refresh-returns-already-stale-blocked",
    "T2-two-active-packages-integrity-blocked",
}

ARTIFACT_PATHS = (
    FIXTURE_PATH,
    CASES_PATH,
    SCRIPTS_PATH,
    LANES_PATH,
    MANIFEST_PATH,
)

EXPECTED_CASE_IDS = {
    "E2E01-01",
    "E2E01-04-A",
    "E2E01-04-B",
    "E2E01-01+SEC-ARGUMENT-BINDING",
    "E2E01-01+FAULT-PROVIDER-PROTOCOL",
    "E2E01-01+FAULT-PRESENTATION-PROTOCOL",
}

ALLOWED_ORDER_STATUSES = {
    "CREATED",
    "PAID",
    "FULFILLING",
    "SHIPPED",
    "DELIVERED",
    "CANCELLED",
}

TRACE_EVENT_VOCABULARY = {
    "MessageAccepted",
    "RunStarted",
    "RequestUnderstandingStarted",
    "ContextManifestRecorded",
    "NextMoveProposed",
    "TaskDeltaValidated",
    "TaskDeltaAccepted",
    "InputBindingRecorded",
    "TaskStateChanged",
    "NextMoveRevalidated",
    "GateDecisionRecorded",
    "ToolCallCreated",
    "ToolCallStarted",
    "ToolCallSucceeded",
    "ToolCallFailed",
    "ToolCallInterrupted",
    "ToolResultNormalized",
    "ObservationRecorded",
    "PresentationPlanProposed",
    "ResponseRendered",
    "RunStopped",
    "EvalCaseGraded",
}

TASK_GATE_TRACE_EVENTS = {
    "MessageAccepted",
    "RunStarted",
    "RequestUnderstandingStarted",
    "ContextManifestRecorded",
    "NextMoveProposed",
    "TaskDeltaValidated",
    "TaskDeltaAccepted",
    "InputBindingRecorded",
    "TaskStateChanged",
    "NextMoveRevalidated",
    "GateDecisionRecorded",
    "ResponseRendered",
    "RunStopped",
    "EvalCaseGraded",
}

MANDATORY_REQUIRED_EVENTS_BY_CASE = {
    "E2E01-01": TASK_GATE_TRACE_EVENTS
    | {
        "ToolCallCreated",
        "ToolCallStarted",
        "ToolCallSucceeded",
        "ToolResultNormalized",
        "ObservationRecorded",
        "PresentationPlanProposed",
    },
    "E2E01-04-A": TASK_GATE_TRACE_EVENTS
    | {
        "ToolCallCreated",
        "ToolCallStarted",
        "ToolCallFailed",
        "ToolResultNormalized",
    },
    "E2E01-04-B": TASK_GATE_TRACE_EVENTS
    | {
        "ToolCallCreated",
        "ToolCallStarted",
        "ToolCallFailed",
        "ToolResultNormalized",
    },
    "E2E01-01+SEC-ARGUMENT-BINDING": TASK_GATE_TRACE_EVENTS,
    "E2E01-01+FAULT-PROVIDER-PROTOCOL": {
        "MessageAccepted",
        "RunStarted",
        "RequestUnderstandingStarted",
        "ContextManifestRecorded",
        "ResponseRendered",
        "RunStopped",
        "EvalCaseGraded",
    },
    "E2E01-01+FAULT-PRESENTATION-PROTOCOL": (
        TASK_GATE_TRACE_EVENTS
        | {
            "ToolCallCreated",
            "ToolCallStarted",
            "ToolCallSucceeded",
            "ToolResultNormalized",
            "ObservationRecorded",
        }
    ),
}

MANDATORY_FORBIDDEN_EVENTS_BY_CASE = {
    "E2E01-01": {
        "ToolCallFailed",
        "ToolCallInterrupted",
    },
    "E2E01-04-A": {
        "ToolCallSucceeded",
        "ToolCallInterrupted",
        "ObservationRecorded",
        "PresentationPlanProposed",
    },
    "E2E01-04-B": {
        "ToolCallSucceeded",
        "ToolCallInterrupted",
        "ObservationRecorded",
        "PresentationPlanProposed",
    },
    "E2E01-01+SEC-ARGUMENT-BINDING": {
        "ToolCallCreated",
        "ToolCallStarted",
        "ToolCallSucceeded",
        "ToolCallFailed",
        "ToolCallInterrupted",
        "ToolResultNormalized",
        "ObservationRecorded",
        "PresentationPlanProposed",
    },
    "E2E01-01+FAULT-PROVIDER-PROTOCOL": {
        "ToolCallCreated",
        "ToolCallStarted",
        "ToolCallSucceeded",
        "ToolCallFailed",
        "ToolCallInterrupted",
        "ToolResultNormalized",
        "ObservationRecorded",
        "PresentationPlanProposed",
    },
    "E2E01-01+FAULT-PRESENTATION-PROTOCOL": {
        "ToolCallFailed",
        "ToolCallInterrupted",
    },
}

EXPECTED_EVENT_COUNTS_BY_CASE = {
    "E2E01-01": {
        "ContextManifestRecorded": 2,
        "TaskStateChanged": 2,
        "ToolCallCreated": 1,
        "ObservationRecorded": 1,
        "PresentationPlanProposed": 1,
    },
    "E2E01-04-A": {
        "ContextManifestRecorded": 1,
        "TaskStateChanged": 2,
        "ToolCallCreated": 1,
        "ObservationRecorded": 0,
        "PresentationPlanProposed": 0,
    },
    "E2E01-04-B": {
        "ContextManifestRecorded": 1,
        "TaskStateChanged": 2,
        "ToolCallCreated": 1,
        "ObservationRecorded": 0,
        "PresentationPlanProposed": 0,
    },
    "E2E01-01+SEC-ARGUMENT-BINDING": {
        "ContextManifestRecorded": 1,
        "TaskStateChanged": 2,
        "GateDecisionRecorded": 1,
        "ToolCallCreated": 0,
        "ObservationRecorded": 0,
        "PresentationPlanProposed": 0,
    },
    "E2E01-01+FAULT-PROVIDER-PROTOCOL": {
        "ContextManifestRecorded": 1,
        "ToolCallCreated": 0,
        "ObservationRecorded": 0,
        "PresentationPlanProposed": 0,
    },
    "E2E01-01+FAULT-PRESENTATION-PROTOCOL": {
        "ContextManifestRecorded": 2,
        "TaskStateChanged": 2,
        "ToolCallCreated": 1,
        "ObservationRecorded": 1,
    },
}

EXPECTED_VERSIONS = {
    "fixture_version": "e2e01-thin-fixture-v1",
    "dataset_version": "e2e01-thin-dataset-v1",
    "prompt_version": "e2e01-thin-prompt-v1",
    "tool_registry_version": "e2e01-thin-tools-v1",
    "renderer_version": "order-summary-renderer-v1",
    "redaction_policy_version": "e2e01-thin-redaction-v1",
    "model_script_catalog_version": "e2e01-thin-model-scripts-v1",
    "lane_manifest_version": "e2e01-thin-lanes-v1",
    "runtime_version": "BOUND_AT_EVAL_RUN_FROM_SOURCE_REVISION_OR_BUILD_ID",
}

ALLOWED_GRADERS = {
    "SchemaGrader",
    "IdentityBoundaryGrader",
    "RequestUnderstandingGrader",
    "InputBindingGrader",
    "TaskStateGrader",
    "ToolCallGrader",
    "ObservationGrader",
    "DisclosureGrader",
    "RendererFactGrader",
    "ErrorMappingGrader",
    "TraceCompletenessGrader",
    "PersistenceGrader",
    "ToolsetReplayGrader",
}

SECRET_VALUE_PATTERNS = (
    re.compile(r"^sk-[A-Za-z0-9_-]{8,}$"),
    re.compile(r"^gh[opsu]_[A-Za-z0-9]{8,}$"),
    re.compile(r"^Bearer\s+\S+$", re.IGNORECASE),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as artifact_file:
        loaded = json.load(artifact_file)
    assert isinstance(loaded, dict), f"{path} must contain one JSON object"
    return loaded


def _copy_cycle2_artifacts(destination: Path) -> Path:
    for source in CYCLE2_ARTIFACT_PATHS:
        relative = source.relative_to(REPO_ROOT)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    return destination


def _write_cycle2_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _reauthenticate_cycle2_artifact(
    root: Path,
    relative: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path = root / CYCLE2_MANIFEST_PATH.relative_to(REPO_ROOT)
    manifest = _load_json(manifest_path)
    entry = next(item for item in manifest["artifacts"] if item["path"] == relative)
    entry["sha256"] = hashlib.sha256((root / relative).read_bytes()).hexdigest()
    _write_cycle2_json(manifest_path, manifest)
    monkeypatch.setattr(
        artifacts_module,
        "CYCLE2_EXPECTED_MANIFEST_SHA256",
        hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
    )


def _all_string_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [nested for item in value for nested in _all_string_values(item)]
    if isinstance(value, dict):
        return [
            nested for item in value.values() for nested in _all_string_values(item)
        ]
    return []


def _ref_ids(fixture: dict[str, Any]) -> set[str]:
    return {
        *(session["fixture_ref"] for session in fixture["sessions"]),
        *(order["fixture_ref"] for order in fixture["orders"]),
        *(
            sentinel["fixture_ref"]
            for sentinel in fixture["nonexistent_order_sentinels"]
        ),
    }


def test_all_declared_artifacts_are_valid_json_objects() -> None:
    artifact_ids = []

    for path in ARTIFACT_PATHS:
        artifact = _load_json(path)
        assert artifact["artifact_type"]
        assert artifact["artifact_id"]
        assert artifact["schema_version"]
        artifact_ids.append(artifact["artifact_id"])

    assert len(artifact_ids) == len(set(artifact_ids))


def test_fixture_is_the_single_synthetic_source_for_all_consumers() -> None:
    fixture = _load_json(FIXTURE_PATH)
    manifest = _load_json(MANIFEST_PATH)

    assert fixture["artifact_id"] == "e2e01-thin-fixture"
    assert fixture["fixture_version"] == "e2e01-thin-fixture-v1"
    assert fixture["classification"] == "SYNTHETIC_DETERMINISTIC"
    assert set(fixture["consumers"]) == {
        "DATABASE_SEED",
        "HTTP_E2E",
        "OFFLINE_GATE",
        "QWEN_BASELINE",
    }
    assert fixture["versions"] == {
        key: manifest["versions"][key]
        for key in (
            "fixture_version",
            "dataset_version",
            "prompt_version",
            "tool_registry_version",
            "renderer_version",
            "redaction_policy_version",
            "runtime_version",
        )
    }

    sessions = {session["session_id"]: session for session in fixture["sessions"]}
    assert set(sessions) == {"p0-session-alice", "p0-session-bob"}
    assert sessions["p0-session-alice"]["trusted_customer_id"] == "customer-A"
    assert sessions["p0-session-bob"]["trusted_customer_id"] == "customer-B"
    assert {session["trust_boundary"] for session in sessions.values()} == {
        "SERVER_SIDE_FIXTURE_ONLY"
    }

    orders = {
        order["safe_projection"]["order_number"]: order for order in fixture["orders"]
    }
    assert set(orders) == {"O-1001", "O-2001"}
    assert {
        order["safe_projection"]["status"] for order in fixture["orders"]
    } <= ALLOWED_ORDER_STATUSES
    assert orders["O-1001"] == {
        "fixture_ref": "order:O-1001",
        "owner_customer_id": "customer-A",
        "safe_projection": {
            "order_number": "O-1001",
            "status": "SHIPPED",
            "line_items": [
                {
                    "product_name": "轻量跑鞋",
                    "quantity": 1,
                }
            ],
            "ordered_at": "2026-07-20T02:15:00Z",
            "status_updated_at": "2026-07-24T09:30:00Z",
        },
    }
    assert orders["O-2001"]["owner_customer_id"] == "customer-B"
    assert orders["O-2001"]["safe_projection"]["status"] == "FULFILLING"
    assert orders["O-2001"]["safe_projection"]["line_items"] == [
        {
            "product_name": "合成隔离测试商品",
            "quantity": 2,
        }
    ]

    sentinels = fixture["nonexistent_order_sentinels"]
    assert sentinels == [
        {
            "fixture_ref": "order-sentinel:O-9999",
            "order_number": "O-9999",
            "seed_behavior": "MUST_NOT_INSERT",
        }
    ]
    assert "O-9999" not in orders


def test_every_case_maps_requirements_and_is_in_the_regression_gate() -> None:
    fixture = _load_json(FIXTURE_PATH)
    dataset = _load_json(CASES_PATH)
    manifest = _load_json(MANIFEST_PATH)

    cases = dataset["cases"]
    case_ids = [case["case_id"] for case in cases]
    assert set(case_ids) == EXPECTED_CASE_IDS
    assert len(case_ids) == len(set(case_ids))

    shared_expectation_ids = {
        expectation["expectation_id"] for expectation in dataset["shared_expectations"]
    }
    assert len(shared_expectation_ids) == len(dataset["shared_expectations"])
    assert all(
        expectation["requirement_ref"].startswith("docs/")
        for expectation in dataset["shared_expectations"]
    )

    fixture_refs = _ref_ids(fixture)
    for case in cases:
        assert case["lifecycle_status"] == "REGRESSION_GATE"
        assert len(case["requirement_refs"]) >= 3
        assert all(
            requirement_ref.startswith("docs/") and "::" in requirement_ref
            for requirement_ref in case["requirement_refs"]
        )
        assert set(case["scope_levels"]) == {
            "COMPONENT",
            "TRAJECTORY",
            "E2E",
        }
        assert case["quality_dimensions"]
        assert case["input"]["messages"]
        assert case["input"]["trusted_context_fixture_ref"] in fixture_refs
        assert set(case["input"]["environment_fixture_refs"]) <= fixture_refs
        assert case["input"]["model_script_refs"]
        required_events = set(case["expectations"]["required_events"])
        forbidden_events = set(case["expectations"]["forbidden_events"])
        assert MANDATORY_REQUIRED_EVENTS_BY_CASE[case["case_id"]] <= required_events
        assert MANDATORY_FORBIDDEN_EVENTS_BY_CASE[case["case_id"]] <= forbidden_events
        assert required_events.isdisjoint(forbidden_events)
        assert required_events | forbidden_events <= TRACE_EVENT_VOCABULARY

        event_count_assertions = case["expectations"]["event_count_assertions"]
        event_counts = {
            assertion["event"]: assertion["count"]
            for assertion in event_count_assertions
        }
        assert len(event_counts) == len(event_count_assertions)
        assert all(
            assertion["operator"] == "EQUALS" for assertion in event_count_assertions
        )
        assert (
            EXPECTED_EVENT_COUNTS_BY_CASE[case["case_id"]].items()
            <= event_counts.items()
        )
        assert case["expectations"]["state_assertions"]
        assert case["expectations"]["disclosure_assertions"]
        assert case["expectations"]["critical_failure_refs"]
        assert set(case["shared_expectation_refs"]) == shared_expectation_ids
        assert set(case["grading"]["graders"]) <= ALLOWED_GRADERS
        assert case["grading"]["graders"]
        assert case["version_manifest"] == {
            "dataset_version": manifest["versions"]["dataset_version"],
            "fixture_versions": [manifest["versions"]["fixture_version"]],
            "model_config_version": (
                "scripted-model-provider-config-v1"
                if ("SEC-" in case["case_id"] or "FAULT-" in case["case_id"])
                else "BOUND_BY_LANE"
            ),
            "prompt_version": manifest["versions"]["prompt_version"],
            "tool_registry_version": manifest["versions"]["tool_registry_version"],
            "runtime_version": manifest["versions"]["runtime_version"],
        }

    assert {case["lifecycle_status"] for case in cases} == {"REGRESSION_GATE"}
    assert manifest["case_lifecycle_status"] == "REGRESSION_GATE"
    assert manifest["eval_result_artifacts_created"] is False
    assert manifest["baseline_result_artifacts_created"] is False


def test_parameterized_cases_define_complete_trace_variant_coverage() -> None:
    dataset = _load_json(CASES_PATH)
    cases = {case["case_id"]: case for case in dataset["cases"]}

    assert {
        case_id
        for case_id, case in cases.items()
        if "trace_expectation_variants" in case["expectations"]
    } == {
        "E2E01-01+FAULT-PROVIDER-PROTOCOL",
        "E2E01-01+FAULT-PRESENTATION-PROTOCOL",
    }

    for case in cases.values():
        variants = case["expectations"].get("trace_expectation_variants")
        if variants is None:
            continue

        case_required = set(case["expectations"]["required_events"])
        covered_script_refs: list[str] = []
        variant_names = []
        for variant in variants:
            variant_names.append(variant["variant"])
            covered_script_refs.extend(variant["model_script_refs"])

            required_events = set(variant["required_events"])
            forbidden_events = set(variant["forbidden_events"])
            assert case_required <= required_events
            assert required_events.isdisjoint(forbidden_events)
            assert required_events | forbidden_events <= TRACE_EVENT_VOCABULARY

            event_count_assertions = variant["event_count_assertions"]
            assert len(event_count_assertions) == len(
                {assertion["event"] for assertion in event_count_assertions}
            )
            assert all(
                assertion["operator"] == "EQUALS" and assertion["count"] >= 0
                for assertion in event_count_assertions
            )

        assert len(variant_names) == len(set(variant_names))
        assert len(covered_script_refs) == len(set(covered_script_refs))
        assert set(covered_script_refs) == set(case["input"]["model_script_refs"])

    provider_case = cases["E2E01-01+FAULT-PROVIDER-PROTOCOL"]
    provider_variants = {
        variant["variant"]: variant
        for variant in provider_case["expectations"]["trace_expectation_variants"]
    }
    gateway_variant = provider_variants["CONTROL_GATEWAY_REJECTED"]
    assert TASK_GATE_TRACE_EVENTS <= set(gateway_variant["required_events"])
    assert {
        "ToolCallCreated",
        "ObservationRecorded",
        "PresentationPlanProposed",
    } <= set(gateway_variant["forbidden_events"])

    presentation_case = cases["E2E01-01+FAULT-PRESENTATION-PROTOCOL"]
    presentation_variants = {
        variant["variant"]: variant
        for variant in presentation_case["expectations"]["trace_expectation_variants"]
    }
    assert set(presentation_variants) == {"PRESENTATION_PROTOCOL_REJECTED"}
    assert (
        "PresentationPlanProposed"
        in presentation_variants["PRESENTATION_PROTOCOL_REJECTED"]["forbidden_events"]
    )


def test_frozen_dtos_reject_noncanonical_stale_and_fact_bearing_returns() -> None:
    message_ref = "00000000-0000-4000-8000-000000000101"

    with pytest.raises(
        ValidationError,
        match="new-goal v2 candidate must use a null base Task version",
    ):
        RequestUnderstandingOutputV2.model_validate(
            {
                "schema_version": "e2e01-thin-v2",
                "message_ref": message_ref,
                "contextualization": {
                    "text": "查询订单 O-1001",
                    "resolved_reference_candidates": [
                        {
                            "name": "order_id",
                            "candidate_value": "O-1001",
                            "source_kind": "CURRENT_MESSAGE",
                            "source_ref": message_ref,
                            "source_quote": "O-1001",
                            "confidence": 1.0,
                        }
                    ],
                    "uncertainties": [],
                    "source_message_refs": [message_ref],
                },
                "task_delta_candidates": [
                    {
                        "candidate_id": ("00000000-0000-4000-8000-000000000102"),
                        "operation": "ADD_GOAL",
                        "goal_patch": "查询订单 O-1001",
                        "input_candidates": [
                            {
                                "name": "order_id",
                                "candidate_value": "O-1001",
                                "semantic_role": ("TARGET_RESOURCE_IDENTIFIER"),
                                "authority": "USER_CLAIM",
                                "source_kind": "CURRENT_MESSAGE",
                                "source_ref": message_ref,
                                "source_quote": "O-1001",
                                "confidence": 1.0,
                            }
                        ],
                        "confidence": 1.0,
                    }
                ],
                "next_move_candidate": {
                    "kind": "CALL_TOOL",
                    "requested_tool_name": "get_order",
                    "arguments": {"order_id": "O-1001"},
                    "base_task_state_version": 1,
                },
            }
        )

    with pytest.raises(ValidationError, match="free_text"):
        PresentationPlan.model_validate(
            {
                "schema_version": "presentation-plan-v1",
                "template_id": "ORDER_STATUS_SUMMARY_V1",
                "tone": "NEUTRAL",
                "opening_variant": "DIRECT",
                "field_order": [
                    "ORDER_NUMBER",
                    "STATUS",
                    "ITEMS",
                    "ORDERED_AT",
                    "STATUS_UPDATED_AT",
                ],
                "closing_variant": "NONE",
                "free_text": "订单 O-1001 已发货",
            }
        )


def test_stale_state_race_is_canonical_and_script_scoped() -> None:
    dataset = _load_json(CASES_PATH)
    scripts = _load_json(SCRIPTS_PATH)
    script_by_ref = {
        scenario["model_script_ref"]: scenario for scenario in scripts["scenarios"]
    }
    stale_ref = "script:fault-runtime:state-advanced-before-gate"
    unknown_ref = "script:fault-provider:unknown-tool-name"

    assert "script:fault-provider:stale-task-state-version" not in script_by_ref
    stale_scenario = script_by_ref[stale_ref]
    assert stale_scenario["steps"] == [
        {
            "purpose": "REQUEST_UNDERSTANDING",
            "behavior": "VALID_ORDER_LOOKUP",
            "message_order_number": "O-1001",
            "next_move_order_number": "O-1001",
            "base_task_state_version": None,
        }
    ]

    runtime_fault = stale_scenario["runtime_fault"]
    assert runtime_fault == {
        "behavior": "ADVANCE_TASK_STATE_AFTER_REVALIDATION_BEFORE_GATE",
        "boundary": "AFTER_REVALIDATION_BEFORE_GATE",
        "transition_command": "ApplyTaskTransitionCommand",
        "transition_port": ("RuntimeRecordPort.apply_task_transition_if_current"),
        "atomic_scope": "TASK_REQUEST_UNIT_AND_TASK_STATE_TRANSITION",
        "from_status": "ACTIVE",
        "to_status": "WAITING_USER",
        "base_task_state_version": 1,
        "result_task_state_version": 2,
        "base_request_unit_state_version": 1,
        "result_request_unit_state_version": 2,
        "validated_task_state_version": 1,
        "current_task_state_version": 2,
        "reason_ref": "00000000-0000-4000-8000-000000000401",
        "conditional_write_required_result": "APPLIED",
        "non_applied_disposition": "EVAL_EXECUTION_FAILURE",
    }
    UUID(runtime_fault["reason_ref"])

    stale_result = stale_scenario["expected_control_result"]
    assert stale_result["stop_reason"] == "GATE_REJECTED"
    assert stale_result["gate_decision"] == "REJECT"
    assert stale_result["task_terminal_status"] == "BLOCKED"
    assert stale_result["request_unit_terminal_status"] == "BLOCKED"
    assert stale_result["validated_task_state_version"] == 1
    assert stale_result["current_task_state_version"] == 2
    assert stale_result["terminal_task_state_version"] == 3
    assert stale_result["terminal_request_unit_state_version"] == 3
    assert stale_result["task_state_version_delta"] == 2
    assert stale_result["request_unit_state_version_delta"] == 2
    assert stale_result["tool_calls"] == 0
    assert stale_result["order_reads"] == 0
    assert stale_result["observation_records"] == 0
    assert stale_result["gate_reason_expectation"] == {
        "mode": "EXACT_CANONICAL",
        "must_be_nonempty": True,
        "must_be_deterministic": True,
        "must_match_injected_fault": True,
        "canonical_reason_code": "STATE_VERSION_MISMATCH",
        "canonical_reason_status": "CONFIRMED",
        "injected_fault_behavior": (
            "ADVANCE_TASK_STATE_AFTER_REVALIDATION_BEFORE_GATE"
        ),
    }

    provider_case = next(
        case
        for case in dataset["cases"]
        if case["case_id"] == "E2E01-01+FAULT-PROVIDER-PROTOCOL"
    )
    assert stale_ref in provider_case["input"]["model_script_refs"]
    assert (
        "script:fault-provider:stale-task-state-version"
        not in provider_case["input"]["model_script_refs"]
    )

    state_assertions = provider_case["expectations"]["state_assertions"]
    obsolete_global_assertion = "".join(
        ("GATEWAY_FAULTS_INCREMENT_", "STATE_VERSION_BY_1")
    )
    assert obsolete_global_assertion not in state_assertions
    assertion_scopes = {
        scope["state_assertion_id"]: scope
        for scope in provider_case["expectations"]["state_assertion_scopes"]
    }
    assert assertion_scopes == {
        (
            "UNKNOWN_TOOL_GATEWAY_REJECTION_INCREMENTS_TASK_AND_"
            "REQUEST_UNIT_STATE_VERSION_BY_1"
        ): {
            "state_assertion_id": (
                "UNKNOWN_TOOL_GATEWAY_REJECTION_INCREMENTS_TASK_AND_"
                "REQUEST_UNIT_STATE_VERSION_BY_1"
            ),
            "model_script_ref": unknown_ref,
            "trace_variant": "CONTROL_GATEWAY_REJECTED",
            "task_state_version_delta": 1,
            "request_unit_state_version_delta": 1,
        },
        (
            "STALE_STATE_GATEWAY_REJECTION_INCREMENTS_TASK_AND_"
            "REQUEST_UNIT_STATE_VERSION_BY_2"
        ): {
            "state_assertion_id": (
                "STALE_STATE_GATEWAY_REJECTION_INCREMENTS_TASK_AND_"
                "REQUEST_UNIT_STATE_VERSION_BY_2"
            ),
            "model_script_ref": stale_ref,
            "trace_variant": "CONTROL_GATEWAY_STALE_STATE_REJECTED",
            "task_state_version_delta": 2,
            "request_unit_state_version_delta": 2,
        },
    }
    assert set(assertion_scopes) <= set(state_assertions)

    variants = {
        variant["variant"]: variant
        for variant in provider_case["expectations"]["trace_expectation_variants"]
    }
    assert variants["CONTROL_GATEWAY_REJECTED"]["model_script_refs"] == [unknown_ref]
    assert variants["CONTROL_GATEWAY_STALE_STATE_REJECTED"]["model_script_refs"] == [
        stale_ref
    ]
    assert {
        assertion["event"]: assertion["count"]
        for assertion in variants["CONTROL_GATEWAY_REJECTED"]["event_count_assertions"]
    } == {
        "TaskStateChanged": 2,
        "GateDecisionRecorded": 1,
    }
    assert {
        assertion["event"]: assertion["count"]
        for assertion in variants["CONTROL_GATEWAY_STALE_STATE_REJECTED"][
            "event_count_assertions"
        ]
    } == {
        "TaskStateChanged": 3,
        "GateDecisionRecorded": 1,
    }


def test_stale_runtime_fault_uses_canonical_conditional_write_results() -> None:
    canonical_results = {result.value for result in ConditionalWriteResult}
    assert canonical_results == {
        "APPLIED",
        "PROJECTION_CONFLICT",
        "NOT_APPLICABLE",
    }
    non_applied_results = canonical_results - {ConditionalWriteResult.APPLIED.value}

    spec_paragraph = next(
        paragraph
        for paragraph in SPEC_PATH.read_text(encoding="utf-8").split("\n\n")
        if paragraph.startswith("注入转换必须通过一个 canonical")
    )
    for result in non_applied_results:
        assert f"`{result}`" in spec_paragraph
    assert "`CONFLICT`" not in spec_paragraph
    assert "其他非 `APPLIED` 结果必须记录为 Eval execution failure" in spec_paragraph

    scripts = _load_json(SCRIPTS_PATH)
    stale_scenario = next(
        scenario
        for scenario in scripts["scenarios"]
        if scenario["model_script_ref"]
        == "script:fault-runtime:state-advanced-before-gate"
    )
    runtime_fault = stale_scenario["runtime_fault"]
    assert runtime_fault["conditional_write_required_result"] == (
        ConditionalWriteResult.APPLIED.value
    )
    assert {
        result: runtime_fault["non_applied_disposition"]
        for result in non_applied_results
    } == {
        "PROJECTION_CONFLICT": "EVAL_EXECUTION_FAILURE",
        "NOT_APPLICABLE": "EVAL_EXECUTION_FAILURE",
    }


def test_fact_bearing_presentation_is_a_raw_protocol_violation() -> None:
    dataset = _load_json(CASES_PATH)
    scripts = _load_json(SCRIPTS_PATH)
    script_by_ref = {
        scenario["model_script_ref"]: scenario for scenario in scripts["scenarios"]
    }
    fact_bearing_ref = "script:fault-presentation:fact-bearing-envelope"

    assert "script:fault-presentation:fact-bearing-plan" not in script_by_ref
    scenario = script_by_ref[fact_bearing_ref]
    presentation_step = next(
        step for step in scenario["steps"] if step["purpose"] == "PRESENTATION"
    )
    assert presentation_step == {
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

    presentation_case = next(
        case
        for case in dataset["cases"]
        if case["case_id"] == "E2E01-01+FAULT-PRESENTATION-PROTOCOL"
    )
    assert fact_bearing_ref in presentation_case["input"]["model_script_refs"]
    variants = {
        variant["variant"]: variant
        for variant in presentation_case["expectations"]["trace_expectation_variants"]
    }
    assert "PRESENTATION_PLAN_GATE_REJECTED" not in variants
    protocol_variant = variants["PRESENTATION_PROTOCOL_REJECTED"]
    assert fact_bearing_ref in protocol_variant["model_script_refs"]
    assert {
        assertion["event"]: assertion["count"]
        for assertion in protocol_variant["event_count_assertions"]
    } == {"PresentationPlanProposed": 0}
    assert "PresentationPlanProposed" in protocol_variant["forbidden_events"]


def test_trusted_field_override_fails_before_next_move_and_task_creation() -> None:
    with pytest.raises(
        ValidationError,
        match="trusted field 'customer_id'",
    ):
        NextMove.model_validate(
            {
                "kind": "CALL_TOOL",
                "requested_tool_name": "get_order",
                "arguments": {
                    "order_id": "O-1001",
                    "customer_id": "customer-B",
                },
                "base_task_state_version": None,
            }
        )

    scripts = _load_json(SCRIPTS_PATH)
    trusted_field_script = next(
        scenario
        for scenario in scripts["scenarios"]
        if scenario["model_script_ref"]
        == "script:fault-provider:trusted-field-override"
    )
    expected_result = trusted_field_script["expected_control_result"]
    assert expected_result == {
        "run_status": "COMPLETED",
        "stop_reason": "INPUT_INVALID",
        "task_creation": "FORBIDDEN",
        "user_outcome": "BLOCKED",
        "response_policy": "FIXED_SAFE_PROCESSING_ERROR",
        "model_calls": 1,
        "tool_calls": 0,
        "order_reads": 0,
        "observation_records": 0,
        "presentation_model_calls": 0,
    }
    assert set(expected_result).isdisjoint(
        {
            "gate_decision",
            "task_terminal_status",
            "request_unit_terminal_status",
            "task_state_version_delta",
            "request_unit_state_version_delta",
            "gate_reason_code",
            "gate_reason_expectation",
        }
    )

    dataset = _load_json(CASES_PATH)
    provider_case = next(
        case
        for case in dataset["cases"]
        if case["case_id"] == "E2E01-01+FAULT-PROVIDER-PROTOCOL"
    )
    variants = {
        variant["variant"]: variant
        for variant in provider_case["expectations"]["trace_expectation_variants"]
    }
    script_ref = trusted_field_script["model_script_ref"]
    input_validation_variant = variants["INPUT_VALIDATION_REJECTED"]
    gateway_variant = variants["CONTROL_GATEWAY_REJECTED"]

    assert script_ref in input_validation_variant["model_script_refs"]
    assert script_ref not in gateway_variant["model_script_refs"]
    assert set(input_validation_variant["required_events"]) == {
        "MessageAccepted",
        "RunStarted",
        "RequestUnderstandingStarted",
        "ContextManifestRecorded",
        "ResponseRendered",
        "RunStopped",
        "EvalCaseGraded",
    }
    assert {
        "NextMoveProposed",
        "TaskDeltaValidated",
        "TaskDeltaAccepted",
        "InputBindingRecorded",
        "TaskStateChanged",
        "NextMoveRevalidated",
        "GateDecisionRecorded",
    } <= set(input_validation_variant["forbidden_events"])
    assert input_validation_variant["event_count_assertions"] == [
        {
            "event": "TaskStateChanged",
            "operator": "EQUALS",
            "count": 0,
        },
        {
            "event": "GateDecisionRecorded",
            "operator": "EQUALS",
            "count": 0,
        },
    ]


def test_eval_case_graded_is_required_without_inventing_event_count() -> None:
    dataset = _load_json(CASES_PATH)

    for case in dataset["cases"]:
        expectations = case["expectations"]
        assert "EvalCaseGraded" in expectations["required_events"]
        assert "EvalCaseGraded" not in {
            assertion["event"] for assertion in expectations["event_count_assertions"]
        }

        for variant in expectations.get(
            "trace_expectation_variants",
            [],
        ):
            assert "EvalCaseGraded" in variant["required_events"]
            assert "EvalCaseGraded" not in {
                assertion["event"] for assertion in variant["event_count_assertions"]
            }


def test_case_fixture_script_lane_and_manifest_refs_resolve() -> None:
    fixture = _load_json(FIXTURE_PATH)
    dataset = _load_json(CASES_PATH)
    scripts = _load_json(SCRIPTS_PATH)
    lanes = _load_json(LANES_PATH)
    manifest = _load_json(MANIFEST_PATH)

    expected_manifest_ref = {
        "artifact_id": manifest["artifact_id"],
        "path": "evals/manifests/e2e01-thin-slice.v1.json",
    }
    for artifact in (fixture, dataset, scripts, lanes):
        assert artifact["version_manifest_ref"] == expected_manifest_ref

    assert dataset["fixture_ref"] == {
        "artifact_id": fixture["artifact_id"],
        "fixture_version": fixture["fixture_version"],
        "path": "evals/fixtures/e2e01-thin-slice.v1.json",
    }
    assert dataset["model_script_catalog_ref"] == {
        "artifact_id": scripts["artifact_id"],
        "model_script_catalog_version": scripts["model_script_catalog_version"],
        "path": "evals/model_scripts/e2e01-thin-slice.v1.json",
    }
    assert lanes["dataset_ref"] == {
        "artifact_id": dataset["artifact_id"],
        "dataset_version": dataset["dataset_version"],
        "path": "evals/cases/e2e01-thin-slice.v1.json",
    }
    assert lanes["fixture_ref"] == dataset["fixture_ref"]

    offline_lane = next(
        lane for lane in lanes["lanes"] if lane["lane"] == "offline_gate"
    )
    assert (
        offline_lane["model_script_catalog_ref"]
        == (dataset["model_script_catalog_ref"])
    )
    assert set(offline_lane["case_refs"]) == EXPECTED_CASE_IDS


def test_manifest_versions_and_sha256_hashes_match_artifact_bytes() -> None:
    manifest = _load_json(MANIFEST_PATH)
    artifact_refs = manifest["artifacts"]

    assert manifest["hash_algorithm"] == "SHA-256"
    assert manifest["versions"] == EXPECTED_VERSIONS
    assert len(artifact_refs) == len(
        {artifact_ref["artifact_id"] for artifact_ref in artifact_refs}
    )
    assert len(artifact_refs) == len(
        {artifact_ref["path"] for artifact_ref in artifact_refs}
    )

    expected_paths = {
        "evals/fixtures/e2e01-thin-slice.v1.json",
        "evals/cases/e2e01-thin-slice.v1.json",
        "evals/model_scripts/e2e01-thin-slice.v1.json",
        "evals/lanes/e2e01-thin-slice.v1.json",
    }
    assert {artifact_ref["path"] for artifact_ref in artifact_refs} == expected_paths

    for artifact_ref in artifact_refs:
        relative_path = Path(artifact_ref["path"])
        assert not relative_path.is_absolute()
        assert ".." not in relative_path.parts

        artifact_path = REPO_ROOT / relative_path
        artifact = _load_json(artifact_path)
        actual_sha256 = hashlib.sha256(artifact_path.read_bytes()).hexdigest()

        assert artifact["artifact_id"] == artifact_ref["artifact_id"]
        assert artifact[artifact_ref["version_field"]] == artifact_ref["version"]
        assert actual_sha256 == artifact_ref["sha256"]

    assert set(manifest["default_offline_artifact_refs"]) == {
        artifact_ref["artifact_id"] for artifact_ref in artifact_refs
    }


def test_default_offline_lane_requires_no_credentials_or_network() -> None:
    lanes = _load_json(LANES_PATH)
    lane_by_name = {lane["lane"]: lane for lane in lanes["lanes"]}

    assert set(lane_by_name) == {"offline_gate", "qwen_baseline"}
    assert lanes["default_lane"] == "offline_gate"

    offline_lane = lane_by_name["offline_gate"]
    assert offline_lane["provider_adapter"] == "ScriptedModelProvider"
    assert offline_lane["deterministic"] is True
    assert offline_lane["release_gate"] is True
    assert offline_lane["network_access"] == "FORBIDDEN"
    assert offline_lane["credential_policy"] == {
        "required_env": [],
        "when_missing": "NOT_APPLICABLE",
    }

    qwen_lane = lane_by_name["qwen_baseline"]
    assert qwen_lane["provider_adapter"] == "QwenResponsesAdapter"
    assert qwen_lane["model_snapshot"] == "qwen3.7-plus-2026-05-26"
    assert qwen_lane["deterministic"] is False
    assert qwen_lane["release_gate"] is False
    assert qwen_lane["network_access"] == ("REQUIRED_WHEN_EXPLICITLY_ENABLED")
    assert qwen_lane["credential_policy"] == {
        "required_env": [
            "DASHSCOPE_API_KEY",
            "DASHSCOPE_BASE_URL",
        ],
        "when_missing": "NOT_RUN",
    }
    assert all(
        "SEC-" not in case_ref and "FAULT-" not in case_ref
        for case_ref in qwen_lane["case_refs"]
    )


def test_artifacts_contain_only_declared_synthetic_data_and_no_secrets() -> None:
    fixture = _load_json(FIXTURE_PATH)
    scripts = _load_json(SCRIPTS_PATH)

    assert fixture["classification"] == "SYNTHETIC_DETERMINISTIC"
    assert {session["trusted_customer_id"] for session in fixture["sessions"]} == {
        "customer-A",
        "customer-B",
    }
    assert {session["label"] for session in fixture["sessions"]} == {"Alice", "Bob"}

    fixture_keys = {
        key.casefold()
        for order in fixture["orders"]
        for key in order["safe_projection"]
    }
    assert fixture_keys.isdisjoint(
        {
            "address",
            "email",
            "phone",
            "payment",
            "payment_method",
            "risk_profile",
        }
    )
    assert scripts["network_access"] == "FORBIDDEN"
    assert scripts["credential_inputs"] == []

    for path in ARTIFACT_PATHS:
        artifact = _load_json(path)
        for string_value in _all_string_values(artifact):
            assert not any(
                pattern.search(string_value) for pattern in SECRET_VALUE_PATTERNS
            )
            assert not string_value.startswith(("http://", "https://"))


def test_eval_provider_contract_is_v2_only_without_artifact_activation() -> None:
    serialized_artifacts = "\n".join(
        path.read_text(encoding="utf-8") for path in ARTIFACT_PATHS
    )
    assert "ORDER_SERVICE_UNAVAILABLE" not in serialized_artifacts
    assert "FIXED_ORDER_SERVICE_UNAVAILABLE" not in serialized_artifacts

    scripted_v2 = getattr(
        scripted_provider_module,
        "ScriptedModelProviderV2",
    )
    qwen_v2 = getattr(
        qwen_responses_module,
        "QwenResponsesAdapterV2",
    )
    assert not hasattr(scripted_provider_module, "ScriptedModelProvider")
    assert not hasattr(qwen_responses_module, "QwenResponsesAdapter")
    for provider_type in (scripted_v2, qwen_v2):
        assert provider_type.__bases__ == (object,)
        assert issubclass(provider_type, ModelProviderV2)
        method_signature = signature(provider_type.propose_next_move)
        assert tuple(method_signature.parameters) == ("self", "request")
        presentation_signature = signature(provider_type.plan_presentation)
        assert tuple(presentation_signature.parameters) == ("self", "request")

    assert {
        "request_understanding_output",
        "request_understanding_records",
        "accepted_task_deltas",
        "observation_persistence_envelopes",
    }.isdisjoint(graders_module.EvalEvidence.model_fields)
    assert {
        "request_understanding_records_v2",
        "accepted_task_deltas_v2",
        "task_state_transitions",
    } <= set(graders_module.EvalEvidence.model_fields)
    harness_source = getsource(harness_module)
    assert "ScriptedModelProviderV2" in harness_source
    assert "ScriptedModelProvider," not in harness_source
    mapper_signature = signature(
        getattr(
            harness_module,
            "map_exact_run_http_result_to_sut_result",
        )
    )
    assert tuple(mapper_signature.parameters) == (
        "execution_ref",
        "http_status",
        "agent_result",
        "closure",
    )
    assert all(
        parameter.kind.name == "KEYWORD_ONLY"
        for parameter in mapper_signature.parameters.values()
    )


def test_cycle2_bundle_has_exact_27_executable_case_identities() -> None:
    dataset = _load_json(CYCLE2_CASES_PATH)
    cases = dataset["cases"]
    case_ids = [case["case_id"] for case in cases]

    assert len(case_ids) == 27
    assert len(case_ids) == len(set(case_ids))
    assert set(case_ids[:14]) == CYCLE2_LONGITUDINAL_CASE_IDS
    assert set(case_ids[14:]) == CYCLE2_TRAJECTORY_CASE_IDS
    assert {case["lifecycle_status"] for case in cases} == {"EXECUTABLE"}
    assert all(case["title"] == case["case_id"] for case in cases)
    assert all(case["requirement_refs"][0] == "EVAL-CASE" for case in cases)
    assert all(
        case["input"]["trusted_context_fixture_ref"] == "session:alice"
        and case["input"]["model_script_refs"]
        == [f"script:{case['case_id']}"]
        for case in cases
    )


def test_cycle2_bundle_uses_the_real_runtime_tool_registry_version() -> None:
    dataset = _load_json(CYCLE2_CASES_PATH)
    manifest = _load_json(CYCLE2_MANIFEST_PATH)

    assert {
        case["version_manifest"]["tool_registry_version"]
        for case in dataset["cases"]
    } == {CYCLE2_TOOL_REGISTRY_VERSION}
    assert manifest["versions"]["tool_registry_version"] == (
        CYCLE2_TOOL_REGISTRY_VERSION
    )
    assert build_cycle2_registry_snapshot().tool_registry_version == (
        CYCLE2_TOOL_REGISTRY_VERSION
    )


def test_cycle2_bundle_has_exact_pair_lane_and_bidirectional_closure() -> None:
    dataset = _load_json(CYCLE2_CASES_PATH)
    fixture = _load_json(CYCLE2_FIXTURE_PATH)
    scripts = _load_json(CYCLE2_SCRIPTS_PATH)
    lanes = _load_json(CYCLE2_LANES_PATH)
    manifest = _load_json(CYCLE2_MANIFEST_PATH)
    cases = dataset["cases"]
    case_ids = [case["case_id"] for case in cases]

    pair_cases = [case for case in cases if "pair_identity" in case]
    assert [case["case_id"] for case in pair_cases] == [
        "E2E01-05/order-only-no-shipment",
        "E2E01-05/logistics-required-uses-shipment",
    ]
    shared_pair_fields = {
        key: pair_cases[0]["pair_identity"][key]
        for key in (
            "pair_id",
            "pair_fixture_ref",
            "pair_manifest_schema",
            "registry_snapshot_digest",
            "model_visible_toolset_hash",
            "provider_mapping_digest",
            "owner_order_initial_state_digest",
        )
    }
    assert shared_pair_fields["pair_id"] == "PAIR-E2E01-05-V1"
    assert shared_pair_fields["pair_fixture_ref"] == (
        "fx-dynamic-tool-pair-owner-a-v1"
    )
    assert all(
        {
            key: case["pair_identity"][key]
            for key in shared_pair_fields
        }
        == shared_pair_fields
        for case in pair_cases
    )
    assert {case["pair_identity"]["input_goal"] for case in pair_cases} == {
        "ORDER_ONLY",
        "LOGISTICS_REQUIRED",
    }
    pair_manifest = fixture["pair_manifests"]
    assert pair_manifest == [
        {
            **shared_pair_fields,
            "allowed_input_goals": ["ORDER_ONLY", "LOGISTICS_REQUIRED"],
        }
    ]

    assert scripts["network_access"] == "FORBIDDEN"
    assert scripts["credential_inputs"] == []
    assert [script["case_refs"] for script in scripts["scenarios"]] == [
        [case_id] for case_id in case_ids
    ]
    offline_lane = lanes["lanes"]
    assert offline_lane["lane"] == "offline_gate"
    assert offline_lane["provider_adapter"] == "ScriptedModelProvider"
    assert offline_lane["network_access"] == "FORBIDDEN"
    assert offline_lane["release_gate"] is True
    assert offline_lane["case_refs"] == case_ids
    assert manifest["case_lifecycle_status"] == "EXECUTABLE"
    assert manifest["eval_result_artifacts_created"] is False
    assert manifest["baseline_result_artifacts_created"] is False


def test_cycle2_manifest_authenticates_exact_companion_bytes() -> None:
    manifest = _load_json(CYCLE2_MANIFEST_PATH)
    entries = manifest["artifacts"]
    assert [entry["path"] for entry in entries] == [
        "evals/fixtures/e2e01-cycle2.v1.json",
        "evals/cases/e2e01-cycle2.v1.json",
        "evals/model_scripts/e2e01-cycle2.v1.json",
        "evals/lanes/e2e01-cycle2.v1.json",
    ]
    assert manifest["default_offline_artifact_refs"] == [
        entry["artifact_id"] for entry in entries
    ]
    for entry in entries:
        path = REPO_ROOT / entry["path"]
        document = _load_json(path)
        assert document["artifact_id"] == entry["artifact_id"]
        assert document[entry["version_field"]] == entry["version"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]


def test_cycle2_loader_authenticates_the_atomic_executable_bundle() -> None:
    bundle = artifacts_module.load_e2e01_cycle2_artifacts(
        REPO_ROOT,
        candidate_version="candidate:cycle2",
        runtime_version="runtime:cycle2",
    )
    assert bundle.candidate_version == "candidate:cycle2"
    assert bundle.runtime_version == "runtime:cycle2"
    assert len(bundle.cases) == 27
    assert {case.lifecycle_status for case in bundle.cases} == {"EXECUTABLE"}
    assert bundle.lane_by_name("offline_gate").case_refs == tuple(
        case.case_id for case in bundle.cases
    )
    assert not hasattr(harness_module, "load_e2e01_cycle2_artifacts")


def test_cycle2_predicates_use_closed_names_arity_and_symbols() -> None:
    dataset = _load_json(CYCLE2_CASES_PATH)
    signatures = {
        "REQ_BINDING": 3,
        "REQ_TOOL": 5,
        "REQ_ATTEMPT": 6,
        "REQ_UNFINISHED_ATTEMPT": 2,
        "REQ_OBSERVATION": 4,
        "REQ_CANDIDATE_SET": 4,
        "REQ_SELECTION": 4,
        "REQ_ASSESSMENT": 3,
        "REQ_PAIR": 5,
        "REQ_RECOVERY": 5,
        "REQ_STOP": 2,
        "REQ_RUN_NO_RESULT_CLOSURE": 4,
    }
    symbols = {
        "$QUERY_BINDING_REF",
        "$ORDINAL_BINDING_REF",
        "$ORDER_BINDING_REF",
        "$CLAIM_BINDING_REF",
        "$TASK_VERSION_AT_GATE",
        "$SEARCH_BASE_TASK_VERSION",
        "$SEARCH_RESULT_TASK_VERSION",
        "$SELECTION_EXPECTED_TASK_VERSION",
        "$SELECTION_RESULT_TASK_VERSION",
        "$SEARCH_OBSERVATION_REF",
        "$SEARCH_SOURCE_VERSION",
        "$CANDIDATE_REF_ORDINAL_2",
        "$STALE_SHIPMENT_OBSERVATION_REF",
        "$STALE_SHIPMENT_SOURCE_VERSION",
        "$SHIPMENT_OBSERVATION_REF",
        "$SHIPMENT_SOURCE_VERSION",
        "$REGISTRY_SNAPSHOT_DIGEST",
        "$MODEL_VISIBLE_TOOLSET_HASH",
        "$PROVIDER_MAPPING_DIGEST",
        "$OWNER_ORDER_INITIAL_STATE_DIGEST",
    }
    for case in dataset["cases"]:
        expectations = case["expectations"]
        for predicate in expectations["required_events"]:
            match = re.fullmatch(r"([A-Z_]+)\(([^()]*)\)", predicate)
            assert match is not None
            name, operands = match.groups()
            assert name in signatures
            values = operands.split(",")
            assert len(values) == signatures[name]
            assert all(value == value.strip() and value for value in values)
            assert {value for value in values if value.startswith("$")} <= symbols
        assert all(
            re.fullmatch(r"FORBID_[A-Z0-9_]+", predicate)
            for predicate in expectations["forbidden_events"]
        )


def test_cycle2_bundle_has_no_action_or_result_artifact_content() -> None:
    serialized = "\n".join(
        path.read_text(encoding="utf-8") for path in CYCLE2_ARTIFACT_PATHS
    )
    for forbidden in (
        "REGRESSION_GATE",
        "create_refund",
        "ActionLedger",
        "ACTION_LEDGER",
        "idempotency_key",
        "confirmation_token",
        "\"artifact_type\": \"EVAL_RESULT\"",
        "grader_result",
        "trace_events",
        "business_evidence",
    ):
        assert forbidden not in serialized


def test_cycle2_loader_fails_closed_on_missing_or_digest_drift(
    tmp_path: Path,
) -> None:
    root = _copy_cycle2_artifacts(tmp_path / "missing")
    (root / "evals/fixtures/e2e01-cycle2.v1.json").unlink()
    with pytest.raises(artifacts_module.ArtifactIntegrityError):
        artifacts_module.load_e2e01_cycle2_artifacts(
            root,
            candidate_version="candidate:cycle2",
        )

    root = _copy_cycle2_artifacts(tmp_path / "drift")
    (root / "evals/cases/e2e01-cycle2.v1.json").write_bytes(b"{not-json")
    with pytest.raises(
        artifacts_module.ArtifactIntegrityError,
        match="exact-byte digest",
    ):
        artifacts_module.load_e2e01_cycle2_artifacts(
            root,
            candidate_version="candidate:cycle2",
        )


def test_cycle2_loader_fails_closed_on_extra_manifest_entry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _copy_cycle2_artifacts(tmp_path)
    manifest_path = root / "evals/manifests/e2e01-cycle2.v1.json"
    manifest = _load_json(manifest_path)
    manifest["artifacts"].append(dict(manifest["artifacts"][0]))
    _write_cycle2_json(manifest_path, manifest)
    monkeypatch.setattr(
        artifacts_module,
        "CYCLE2_EXPECTED_MANIFEST_SHA256",
        hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
    )

    with pytest.raises(
        artifacts_module.ArtifactContractError,
        match="manifest artifact set",
    ):
        artifacts_module.load_e2e01_cycle2_artifacts(
            root,
            candidate_version="candidate:cycle2",
        )


def test_cycle2_loader_fails_closed_on_wrong_lane(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _copy_cycle2_artifacts(tmp_path)
    relative = "evals/lanes/e2e01-cycle2.v1.json"
    lane_path = root / relative
    lane = _load_json(lane_path)
    lane["lanes"]["network_access"] = "OPTIONAL"
    _write_cycle2_json(lane_path, lane)
    _reauthenticate_cycle2_artifact(root, relative, monkeypatch)

    with pytest.raises(
        artifacts_module.ArtifactContractError,
        match="offline lane",
    ):
        artifacts_module.load_e2e01_cycle2_artifacts(
            root,
            candidate_version="candidate:cycle2",
        )


def test_cycle2_loader_fails_closed_on_predicate_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _copy_cycle2_artifacts(tmp_path)
    relative = "evals/cases/e2e01-cycle2.v1.json"
    cases_path = root / relative
    dataset = _load_json(cases_path)
    dataset["cases"][0]["expectations"]["required_events"][1] = (
        "REQ_TOOL(search_orders,1)"
    )
    _write_cycle2_json(cases_path, dataset)
    _reauthenticate_cycle2_artifact(root, relative, monkeypatch)

    with pytest.raises(
        artifacts_module.ArtifactContractError,
        match="predicate operands",
    ):
        artifacts_module.load_e2e01_cycle2_artifacts(
            root,
            candidate_version="candidate:cycle2",
        )
