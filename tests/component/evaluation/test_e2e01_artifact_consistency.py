from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_PATH = REPO_ROOT / "evals/fixtures/e2e01-thin-slice.v1.json"
CASES_PATH = REPO_ROOT / "evals/cases/e2e01-thin-slice.v1.json"
SCRIPTS_PATH = REPO_ROOT / "evals/model_scripts/e2e01-thin-slice.v1.json"
LANES_PATH = REPO_ROOT / "evals/lanes/e2e01-thin-slice.v1.json"
MANIFEST_PATH = REPO_ROOT / "evals/manifests/e2e01-thin-slice.v1.json"

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


def _all_string_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [
            nested
            for item in value
            for nested in _all_string_values(item)
        ]
    if isinstance(value, dict):
        return [
            nested
            for item in value.values()
            for nested in _all_string_values(item)
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

    sessions = {
        session["session_id"]: session
        for session in fixture["sessions"]
    }
    assert set(sessions) == {"p0-session-alice", "p0-session-bob"}
    assert sessions["p0-session-alice"]["trusted_customer_id"] == "customer-A"
    assert sessions["p0-session-bob"]["trusted_customer_id"] == "customer-B"
    assert {
        session["trust_boundary"]
        for session in sessions.values()
    } == {"SERVER_SIDE_FIXTURE_ONLY"}

    orders = {
        order["safe_projection"]["order_number"]: order
        for order in fixture["orders"]
    }
    assert set(orders) == {"O-1001", "O-2001"}
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


def test_every_case_maps_requirements_and_stays_contract_defined() -> None:
    fixture = _load_json(FIXTURE_PATH)
    dataset = _load_json(CASES_PATH)
    manifest = _load_json(MANIFEST_PATH)

    cases = dataset["cases"]
    case_ids = [case["case_id"] for case in cases]
    assert set(case_ids) == EXPECTED_CASE_IDS
    assert len(case_ids) == len(set(case_ids))

    shared_expectation_ids = {
        expectation["expectation_id"]
        for expectation in dataset["shared_expectations"]
    }
    assert len(shared_expectation_ids) == len(dataset["shared_expectations"])
    assert all(
        expectation["requirement_ref"].startswith("docs/")
        for expectation in dataset["shared_expectations"]
    )

    fixture_refs = _ref_ids(fixture)
    for case in cases:
        assert case["lifecycle_status"] == "CONTRACT_DEFINED"
        assert len(case["requirement_refs"]) >= 3
        assert all(
            requirement_ref.startswith("docs/")
            and "::" in requirement_ref
            for requirement_ref in case["requirement_refs"]
        )
        assert set(case["scope_levels"]) == {
            "COMPONENT",
            "TRAJECTORY",
            "E2E",
        }
        assert case["quality_dimensions"]
        assert case["input"]["messages"]
        assert (
            case["input"]["trusted_context_fixture_ref"]
            in fixture_refs
        )
        assert set(case["input"]["environment_fixture_refs"]) <= fixture_refs
        assert case["input"]["model_script_refs"]
        assert case["expectations"]["required_events"]
        assert case["expectations"]["forbidden_events"]
        assert case["expectations"]["state_assertions"]
        assert case["expectations"]["disclosure_assertions"]
        assert case["expectations"]["critical_failure_refs"]
        assert (
            set(case["shared_expectation_refs"])
            == shared_expectation_ids
        )
        assert set(case["grading"]["graders"]) <= ALLOWED_GRADERS
        assert case["grading"]["graders"]
        assert case["version_manifest"] == {
            "dataset_version": manifest["versions"]["dataset_version"],
            "fixture_versions": [
                manifest["versions"]["fixture_version"]
            ],
            "model_config_version": (
                "scripted-model-provider-config-v1"
                if (
                    "SEC-" in case["case_id"]
                    or "FAULT-" in case["case_id"]
                )
                else "BOUND_BY_LANE"
            ),
            "prompt_version": manifest["versions"]["prompt_version"],
            "tool_registry_version": manifest["versions"][
                "tool_registry_version"
            ],
            "runtime_version": manifest["versions"]["runtime_version"],
        }

    assert {
        case["lifecycle_status"]
        for case in cases
    } == {"CONTRACT_DEFINED"}
    assert manifest["case_lifecycle_status"] == "CONTRACT_DEFINED"
    assert manifest["eval_result_artifacts_created"] is False
    assert manifest["baseline_result_artifacts_created"] is False


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
        "model_script_catalog_version": scripts[
            "model_script_catalog_version"
        ],
        "path": "evals/model_scripts/e2e01-thin-slice.v1.json",
    }
    assert lanes["dataset_ref"] == {
        "artifact_id": dataset["artifact_id"],
        "dataset_version": dataset["dataset_version"],
        "path": "evals/cases/e2e01-thin-slice.v1.json",
    }
    assert lanes["fixture_ref"] == dataset["fixture_ref"]

    offline_lane = next(
        lane
        for lane in lanes["lanes"]
        if lane["lane"] == "offline_gate"
    )
    assert offline_lane["model_script_catalog_ref"] == (
        dataset["model_script_catalog_ref"]
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
    assert {
        artifact_ref["path"]
        for artifact_ref in artifact_refs
    } == expected_paths

    for artifact_ref in artifact_refs:
        relative_path = Path(artifact_ref["path"])
        assert not relative_path.is_absolute()
        assert ".." not in relative_path.parts

        artifact_path = REPO_ROOT / relative_path
        artifact = _load_json(artifact_path)
        actual_sha256 = hashlib.sha256(artifact_path.read_bytes()).hexdigest()

        assert artifact["artifact_id"] == artifact_ref["artifact_id"]
        assert (
            artifact[artifact_ref["version_field"]]
            == artifact_ref["version"]
        )
        assert actual_sha256 == artifact_ref["sha256"]

    assert set(manifest["default_offline_artifact_refs"]) == {
        artifact_ref["artifact_id"]
        for artifact_ref in artifact_refs
    }


def test_default_offline_lane_requires_no_credentials_or_network() -> None:
    lanes = _load_json(LANES_PATH)
    lane_by_name = {
        lane["lane"]: lane
        for lane in lanes["lanes"]
    }

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
    assert qwen_lane["network_access"] == (
        "REQUIRED_WHEN_EXPLICITLY_ENABLED"
    )
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
    assert {
        session["trusted_customer_id"]
        for session in fixture["sessions"]
    } == {"customer-A", "customer-B"}
    assert {
        session["label"]
        for session in fixture["sessions"]
    } == {"Alice", "Bob"}

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
                pattern.search(string_value)
                for pattern in SECRET_VALUE_PATTERNS
            )
            assert not string_value.startswith(("http://", "https://"))
