"""Versioned E2E01 Eval artifact loading boundary."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Any

from pydantic import AfterValidator, JsonValue, PlainSerializer

from mini_agent.core.common import (
    FrozenJsonDict,
    freeze_json_value,
    thaw_json_value,
)
from mini_agent.core.common import AuditOnlyModel


MANIFEST_RELATIVE_PATH = "evals/manifests/e2e01-thin-slice.v1.json"
EXPECTED_MANIFEST_SHA256 = (
    "cf7683133145cf5c2c161b396be852ce4c226e3bc9d3154fd2b1dc8149166cb9"
)
CYCLE2_MANIFEST_RELATIVE_PATH = "evals/manifests/e2e01-cycle2.v1.json"
CYCLE2_EXPECTED_MANIFEST_SHA256 = (
    "00600b24a8403280f527c0ad8140e1a3543738dad46c648d1965ca4bda22914c"
)
_RUNTIME_VERSION_PLACEHOLDER = "BOUND_AT_EVAL_RUN_FROM_SOURCE_REVISION_OR_BUILD_ID"
_MANIFEST_ARTIFACT_ID = "e2e01-thin-version-manifest"
_EXPECTED_ARTIFACTS: Mapping[str, tuple[str, str, str]] = {
    "e2e01-thin-fixture": (
        "evals/fixtures/e2e01-thin-slice.v1.json",
        "fixture_version",
        "e2e01-thin-fixture-v1",
    ),
    "e2e01-thin-cases": (
        "evals/cases/e2e01-thin-slice.v1.json",
        "dataset_version",
        "e2e01-thin-dataset-v1",
    ),
    "e2e01-thin-model-scripts": (
        "evals/model_scripts/e2e01-thin-slice.v1.json",
        "model_script_catalog_version",
        "e2e01-thin-model-scripts-v1",
    ),
    "e2e01-thin-lanes": (
        "evals/lanes/e2e01-thin-slice.v1.json",
        "lane_manifest_version",
        "e2e01-thin-lanes-v1",
    ),
}
_EXPECTED_ARTIFACT_ORDER = tuple(_EXPECTED_ARTIFACTS)
_MANIFEST_KEYS = frozenset(
    {
        "artifact_type",
        "artifact_id",
        "schema_version",
        "manifest_version",
        "created_from_base_sha",
        "versions",
        "runtime_version_binding",
        "hash_algorithm",
        "artifacts",
        "default_offline_artifact_refs",
        "case_lifecycle_status",
        "eval_result_artifacts_created",
        "baseline_result_artifacts_created",
    }
)
_FIXTURE_KEYS = frozenset(
    {
        "artifact_type",
        "artifact_id",
        "schema_version",
        "fixture_version",
        "classification",
        "version_manifest_ref",
        "consumers",
        "sessions",
        "orders",
        "nonexistent_order_sentinels",
        "versions",
    }
)
_CASE_CATALOG_KEYS = frozenset(
    {
        "artifact_type",
        "artifact_id",
        "schema_version",
        "dataset_version",
        "fixture_ref",
        "model_script_catalog_ref",
        "version_manifest_ref",
        "shared_expectations",
        "cases",
    }
)
_CASE_KEYS = frozenset(
    {
        "case_id",
        "title",
        "lifecycle_status",
        "requirement_refs",
        "scope_levels",
        "quality_dimensions",
        "dataset_category",
        "input",
        "shared_expectation_refs",
        "expectations",
        "grading",
        "version_manifest",
    }
)
_SCRIPT_CATALOG_KEYS = frozenset(
    {
        "artifact_type",
        "artifact_id",
        "schema_version",
        "model_script_catalog_version",
        "provider",
        "network_access",
        "credential_inputs",
        "version_manifest_ref",
        "scenarios",
    }
)
_SCRIPT_KEYS = frozenset(
    {
        "model_script_ref",
        "case_refs",
        "steps",
        "expected_control_result",
    }
)
_LANE_CATALOG_KEYS = frozenset(
    {
        "artifact_type",
        "artifact_id",
        "schema_version",
        "lane_manifest_version",
        "default_lane",
        "dataset_ref",
        "fixture_ref",
        "version_manifest_ref",
        "lanes",
    }
)
_LANE_KEYS = frozenset(
    {
        "lane",
        "provider_adapter",
        "model_config_version",
        "deterministic",
        "release_gate",
        "network_access",
        "credential_policy",
        "case_refs",
        "result_policy",
    }
)
_SHA256_HEX_LENGTH = 64


class EvalArtifactError(ValueError):
    """Bounded failure while authenticating or validating Eval artifacts."""


class ArtifactIntegrityError(EvalArtifactError):
    """An artifact failed exact-byte or path integrity validation."""


class ArtifactContractError(EvalArtifactError):
    """An authenticated artifact failed its closed semantic contract."""


def _freeze_mapping(value: Mapping[str, Any]) -> FrozenJsonDict:
    frozen = freeze_json_value(value)
    if not isinstance(frozen, FrozenJsonDict):
        raise TypeError("artifact JSON object must remain a mapping")
    return frozen


ArtifactJsonObject = Annotated[
    Mapping[str, JsonValue],
    AfterValidator(_freeze_mapping),
    PlainSerializer(
        thaw_json_value,
        return_type=dict[str, JsonValue],
        when_used="json",
    ),
]


class EvalCaseArtifact(AuditOnlyModel):
    case_id: str
    lifecycle_status: str
    requirement_refs: tuple[str, ...]
    input: ArtifactJsonObject
    expectations: ArtifactJsonObject
    grading: ArtifactJsonObject
    version_manifest: ArtifactJsonObject
    observable_equivalence: ArtifactJsonObject | None = None


class ModelScriptArtifact(AuditOnlyModel):
    model_script_ref: str
    case_refs: tuple[str, ...]
    steps: tuple[ArtifactJsonObject, ...]
    expected_control_result: ArtifactJsonObject
    runtime_fault: ArtifactJsonObject | None = None


class EvalLaneArtifact(AuditOnlyModel):
    lane: str
    provider_adapter: str
    model_config_version: str
    deterministic: bool
    release_gate: bool
    network_access: str
    credential_policy: ArtifactJsonObject
    case_refs: tuple[str, ...]
    result_policy: ArtifactJsonObject
    model_snapshot: str | None = None


class LoadedE2E01Artifacts(AuditOnlyModel):
    candidate_version: str
    runtime_version: str | None
    manifest: ArtifactJsonObject
    fixture: ArtifactJsonObject
    cases: tuple[EvalCaseArtifact, ...]
    scripts: tuple[ModelScriptArtifact, ...]
    lanes: tuple[EvalLaneArtifact, ...]

    def case_by_id(self, case_id: str) -> EvalCaseArtifact:
        matches = tuple(case for case in self.cases if case.case_id == case_id)
        if len(matches) != 1:
            raise ArtifactContractError("unknown or duplicate Eval Case identity")
        return matches[0]

    def script_by_ref(self, model_script_ref: str) -> ModelScriptArtifact:
        matches = tuple(
            script
            for script in self.scripts
            if script.model_script_ref == model_script_ref
        )
        if len(matches) != 1:
            raise ArtifactContractError("unknown or duplicate model script reference")
        return matches[0]

    def lane_by_name(self, lane: str) -> EvalLaneArtifact:
        matches = tuple(item for item in self.lanes if item.lane == lane)
        if len(matches) != 1:
            raise ArtifactContractError("unknown or duplicate Eval lane")
        return matches[0]


def _expect_mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ArtifactContractError("artifact object shape is invalid")
    return value


def _expect_list(value: object) -> list[Any]:
    if not isinstance(value, list):
        raise ArtifactContractError("artifact list shape is invalid")
    return value


def _expect_exact_keys(
    value: Mapping[str, Any],
    required: frozenset[str],
    *,
    optional: frozenset[str] = frozenset(),
) -> None:
    keys = frozenset(value)
    if not required <= keys or not keys <= required | optional:
        raise ArtifactContractError("artifact fields do not match the closed schema")


def _expect_nonempty_strings(value: object) -> tuple[str, ...]:
    items = _expect_list(value)
    if not all(
        isinstance(item, str) and item and item == item.strip() for item in items
    ):
        raise ArtifactContractError("artifact string references are invalid")
    result = tuple(items)
    if len(result) != len(set(result)):
        raise ArtifactContractError("artifact references must be unique")
    return result


def _safe_json_loads(raw: bytes) -> dict[str, Any]:
    try:
        loaded = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ArtifactContractError("authenticated artifact JSON is invalid") from None
    return _expect_mapping(loaded)


def _resolve_closed_file(repository_root: Path, relative_path: str) -> Path:
    relative = Path(relative_path)
    if (
        relative.is_absolute()
        or not relative.parts
        or ".." in relative.parts
        or "." in relative.parts
    ):
        raise ArtifactIntegrityError("artifact path is outside the closed path set")
    candidate = repository_root.joinpath(relative)
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError):
        raise ArtifactIntegrityError("artifact path cannot be resolved") from None
    if not resolved.is_relative_to(repository_root):
        raise ArtifactIntegrityError("artifact path escapes repository root")
    if candidate.is_symlink() or not resolved.is_file():
        raise ArtifactIntegrityError("artifact path is not a regular fixed file")
    return resolved


def _validate_caller_versions(
    candidate_version: object,
    runtime_version: object,
) -> tuple[str, str | None]:
    if (
        not isinstance(candidate_version, str)
        or not candidate_version
        or candidate_version != candidate_version.strip()
    ):
        raise ArtifactContractError("candidate_version must be a concrete value")
    if runtime_version is None:
        return candidate_version, None
    if (
        not isinstance(runtime_version, str)
        or not runtime_version
        or runtime_version != runtime_version.strip()
        or runtime_version == _RUNTIME_VERSION_PLACEHOLDER
    ):
        raise ArtifactContractError("runtime_version must be a concrete value")
    return candidate_version, runtime_version


def _validate_manifest(manifest: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    _expect_exact_keys(manifest, _MANIFEST_KEYS)
    if (
        manifest.get("artifact_type") != "EVAL_VERSION_MANIFEST"
        or manifest.get("artifact_id") != _MANIFEST_ARTIFACT_ID
        or manifest.get("schema_version") != "e2e01-thin-version-manifest-schema-v1"
        or manifest.get("manifest_version") != "e2e01-thin-version-manifest-v1"
        or manifest.get("created_from_base_sha")
        != "6c6d041cf20db6ff268c8bca129cc19b521cb568"
        or manifest.get("hash_algorithm") != "SHA-256"
        or manifest.get("case_lifecycle_status") != "REGRESSION_GATE"
        or manifest.get("eval_result_artifacts_created") is not False
        or manifest.get("baseline_result_artifacts_created") is not False
    ):
        raise ArtifactContractError("version manifest closed values are invalid")
    versions = _expect_mapping(manifest.get("versions"))
    expected_versions = {
        "fixture_version": "e2e01-thin-fixture-v1",
        "dataset_version": "e2e01-thin-dataset-v1",
        "prompt_version": "e2e01-thin-prompt-v1",
        "tool_registry_version": "e2e01-thin-tools-v1",
        "renderer_version": "order-summary-renderer-v1",
        "redaction_policy_version": "e2e01-thin-redaction-v1",
        "model_script_catalog_version": "e2e01-thin-model-scripts-v1",
        "lane_manifest_version": "e2e01-thin-lanes-v1",
        "runtime_version": _RUNTIME_VERSION_PLACEHOLDER,
    }
    if versions != expected_versions:
        raise ArtifactContractError("version manifest version set is invalid")
    runtime_binding = _expect_mapping(manifest.get("runtime_version_binding"))
    if runtime_binding != {
        "required_at_eval_run": True,
        "source": "SOURCE_REVISION_OR_BUILD_ID",
        "artifact_placeholder": _RUNTIME_VERSION_PLACEHOLDER,
    }:
        raise ArtifactContractError("runtime version binding is invalid")

    raw_entries = _expect_list(manifest.get("artifacts"))
    entries = tuple(_expect_mapping(entry) for entry in raw_entries)
    artifact_ids = tuple(entry.get("artifact_id") for entry in entries)
    if artifact_ids != _EXPECTED_ARTIFACT_ORDER:
        raise ArtifactContractError("manifest artifact identity set is invalid")
    if len(artifact_ids) != len(set(artifact_ids)):
        raise ArtifactContractError("manifest artifact identities are duplicated")
    if (
        _expect_nonempty_strings(manifest.get("default_offline_artifact_refs"))
        != artifact_ids
    ):
        raise ArtifactContractError("default artifact references are invalid")

    for entry in entries:
        _expect_exact_keys(
            entry,
            frozenset(
                {
                    "artifact_id",
                    "path",
                    "version_field",
                    "version",
                    "sha256",
                }
            ),
        )
        artifact_id = entry["artifact_id"]
        expected_path, expected_field, expected_version = _EXPECTED_ARTIFACTS[
            artifact_id
        ]
        digest = entry["sha256"]
        if (
            entry["path"] != expected_path
            or entry["version_field"] != expected_field
            or entry["version"] != expected_version
            or not isinstance(digest, str)
            or len(digest) != _SHA256_HEX_LENGTH
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise ArtifactContractError("manifest artifact entry is invalid")
    return entries


def _validate_fixture(document: dict[str, Any]) -> None:
    _expect_exact_keys(document, _FIXTURE_KEYS)
    if (
        document.get("artifact_type") != "E2E_FIXTURE"
        or document.get("artifact_id") != "e2e01-thin-fixture"
        or document.get("schema_version") != "e2e01-thin-fixture-schema-v1"
        or document.get("fixture_version") != "e2e01-thin-fixture-v1"
        or document.get("classification") != "SYNTHETIC_DETERMINISTIC"
    ):
        raise ArtifactContractError("fixture artifact closed values are invalid")
    _validate_manifest_ref(document.get("version_manifest_ref"))
    sessions = tuple(
        _expect_mapping(item) for item in _expect_list(document.get("sessions"))
    )
    orders = tuple(
        _expect_mapping(item) for item in _expect_list(document.get("orders"))
    )
    sentinels = tuple(
        _expect_mapping(item)
        for item in _expect_list(document.get("nonexistent_order_sentinels"))
    )
    all_refs = tuple(
        item.get("fixture_ref") for item in (*sessions, *orders, *sentinels)
    )
    if not all(isinstance(ref, str) and ref for ref in all_refs) or len(
        all_refs
    ) != len(set(all_refs)):
        raise ArtifactContractError("fixture references are invalid")


def _validate_manifest_ref(value: object) -> None:
    if _expect_mapping(value) != {
        "artifact_id": _MANIFEST_ARTIFACT_ID,
        "path": MANIFEST_RELATIVE_PATH,
    }:
        raise ArtifactContractError("version manifest reference is invalid")


def _validate_cases(
    document: dict[str, Any],
) -> tuple[EvalCaseArtifact, ...]:
    _expect_exact_keys(document, _CASE_CATALOG_KEYS)
    if (
        document.get("artifact_type") != "EVAL_CASE_DATASET"
        or document.get("artifact_id") != "e2e01-thin-cases"
        or document.get("schema_version") != "e2e01-thin-case-schema-v1"
        or document.get("dataset_version") != "e2e01-thin-dataset-v1"
    ):
        raise ArtifactContractError("case artifact closed values are invalid")
    if _expect_mapping(document.get("fixture_ref")) != {
        "artifact_id": "e2e01-thin-fixture",
        "fixture_version": "e2e01-thin-fixture-v1",
        "path": _EXPECTED_ARTIFACTS["e2e01-thin-fixture"][0],
    }:
        raise ArtifactContractError("case fixture reference is invalid")
    if _expect_mapping(document.get("model_script_catalog_ref")) != {
        "artifact_id": "e2e01-thin-model-scripts",
        "model_script_catalog_version": "e2e01-thin-model-scripts-v1",
        "path": _EXPECTED_ARTIFACTS["e2e01-thin-model-scripts"][0],
    }:
        raise ArtifactContractError("case script catalog reference is invalid")
    _validate_manifest_ref(document.get("version_manifest_ref"))

    views: list[EvalCaseArtifact] = []
    for raw_case in _expect_list(document.get("cases")):
        case = _expect_mapping(raw_case)
        _expect_exact_keys(
            case,
            _CASE_KEYS,
            optional=frozenset({"observable_equivalence"}),
        )
        if case.get("lifecycle_status") != "REGRESSION_GATE":
            raise ArtifactContractError("case lifecycle is not REGRESSION_GATE")
        input_projection = _expect_mapping(case.get("input"))
        grading = _expect_mapping(case.get("grading"))
        _expect_nonempty_strings(grading.get("graders"))
        views.append(
            EvalCaseArtifact(
                case_id=case.get("case_id"),
                lifecycle_status=case.get("lifecycle_status"),
                requirement_refs=tuple(case.get("requirement_refs", ())),
                input=input_projection,
                expectations=_expect_mapping(case.get("expectations")),
                grading=grading,
                version_manifest=_expect_mapping(case.get("version_manifest")),
                observable_equivalence=case.get("observable_equivalence"),
            )
        )
    _require_unique(tuple(view.case_id for view in views), "Eval Case")
    return tuple(views)


def _validate_scripts(
    document: dict[str, Any],
) -> tuple[ModelScriptArtifact, ...]:
    _expect_exact_keys(document, _SCRIPT_CATALOG_KEYS)
    if (
        document.get("artifact_type") != "SCRIPTED_SCENARIO_CATALOG"
        or document.get("artifact_id") != "e2e01-thin-model-scripts"
        or document.get("schema_version") != "e2e01-thin-model-script-schema-v1"
        or document.get("model_script_catalog_version") != "e2e01-thin-model-scripts-v1"
        or document.get("provider") != "ScriptedModelProvider"
        or document.get("network_access") != "FORBIDDEN"
        or document.get("credential_inputs") != []
    ):
        raise ArtifactContractError("model script closed values are invalid")
    _validate_manifest_ref(document.get("version_manifest_ref"))

    views: list[ModelScriptArtifact] = []
    for raw_script in _expect_list(document.get("scenarios")):
        script = _expect_mapping(raw_script)
        _expect_exact_keys(
            script,
            _SCRIPT_KEYS,
            optional=frozenset({"runtime_fault"}),
        )
        steps = tuple(
            _expect_mapping(step) for step in _expect_list(script.get("steps"))
        )
        if not steps:
            raise ArtifactContractError("model script cannot be empty")
        for step in steps:
            if not frozenset({"purpose", "behavior"}) <= frozenset(step):
                raise ArtifactContractError("model script step is invalid")
        views.append(
            ModelScriptArtifact(
                model_script_ref=script.get("model_script_ref"),
                case_refs=_expect_nonempty_strings(script.get("case_refs")),
                steps=steps,
                expected_control_result=_expect_mapping(
                    script.get("expected_control_result")
                ),
                runtime_fault=script.get("runtime_fault"),
            )
        )
    _require_unique(
        tuple(view.model_script_ref for view in views),
        "model script",
    )
    return tuple(views)


def _validate_lanes(
    document: dict[str, Any],
) -> tuple[EvalLaneArtifact, ...]:
    _expect_exact_keys(document, _LANE_CATALOG_KEYS)
    if (
        document.get("artifact_type") != "EVAL_LANE_MANIFEST"
        or document.get("artifact_id") != "e2e01-thin-lanes"
        or document.get("schema_version") != "e2e01-thin-lane-schema-v1"
        or document.get("lane_manifest_version") != "e2e01-thin-lanes-v1"
        or document.get("default_lane") != "offline_gate"
    ):
        raise ArtifactContractError("lane artifact closed values are invalid")
    _validate_manifest_ref(document.get("version_manifest_ref"))
    if _expect_mapping(document.get("dataset_ref")) != {
        "artifact_id": "e2e01-thin-cases",
        "dataset_version": "e2e01-thin-dataset-v1",
        "path": _EXPECTED_ARTIFACTS["e2e01-thin-cases"][0],
    }:
        raise ArtifactContractError("lane dataset reference is invalid")
    if _expect_mapping(document.get("fixture_ref")) != {
        "artifact_id": "e2e01-thin-fixture",
        "fixture_version": "e2e01-thin-fixture-v1",
        "path": _EXPECTED_ARTIFACTS["e2e01-thin-fixture"][0],
    }:
        raise ArtifactContractError("lane fixture reference is invalid")

    views: list[EvalLaneArtifact] = []
    for raw_lane in _expect_list(document.get("lanes")):
        lane = _expect_mapping(raw_lane)
        lane_name = lane.get("lane")
        optional = (
            frozenset({"model_script_catalog_ref"})
            if lane_name == "offline_gate"
            else frozenset({"model_snapshot"})
        )
        _expect_exact_keys(lane, _LANE_KEYS, optional=optional)
        if lane_name == "offline_gate":
            if _expect_mapping(lane.get("model_script_catalog_ref")) != {
                "artifact_id": "e2e01-thin-model-scripts",
                "model_script_catalog_version": "e2e01-thin-model-scripts-v1",
                "path": _EXPECTED_ARTIFACTS["e2e01-thin-model-scripts"][0],
            }:
                raise ArtifactContractError("offline script reference is invalid")
        elif lane_name != "qwen_baseline":
            raise ArtifactContractError("unknown Eval lane")
        views.append(
            EvalLaneArtifact(
                lane=lane_name,
                provider_adapter=lane.get("provider_adapter"),
                model_config_version=lane.get("model_config_version"),
                model_snapshot=lane.get("model_snapshot"),
                deterministic=lane.get("deterministic"),
                release_gate=lane.get("release_gate"),
                network_access=lane.get("network_access"),
                credential_policy=_expect_mapping(lane.get("credential_policy")),
                case_refs=_expect_nonempty_strings(lane.get("case_refs")),
                result_policy=_expect_mapping(lane.get("result_policy")),
            )
        )
    _require_unique(tuple(view.lane for view in views), "Eval lane")
    if tuple(view.lane for view in views) != ("offline_gate", "qwen_baseline"):
        raise ArtifactContractError("Eval lane set is incomplete")
    return tuple(views)


def _require_unique(values: tuple[str, ...], subject: str) -> None:
    if (
        not values
        or not all(isinstance(value, str) and value for value in values)
        or len(values) != len(set(values))
    ):
        raise ArtifactContractError(f"{subject} identities are invalid")


def _validate_reference_closure(
    fixture: dict[str, Any],
    cases: tuple[EvalCaseArtifact, ...],
    scripts: tuple[ModelScriptArtifact, ...],
    lanes: tuple[EvalLaneArtifact, ...],
) -> None:
    fixture_refs = {
        item["fixture_ref"]
        for collection_name in (
            "sessions",
            "orders",
            "nonexistent_order_sentinels",
        )
        for item in _expect_list(fixture[collection_name])
    }
    case_ids = {case.case_id for case in cases}
    script_refs = {script.model_script_ref for script in scripts}

    expected_case_refs_by_script: dict[str, set[str]] = {}
    for case in cases:
        if case.version_manifest.get("dataset_version") != ("e2e01-thin-dataset-v1"):
            raise ArtifactContractError("case dataset version is invalid")
        case_fixture_refs = {
            case.input.get("trusted_context_fixture_ref"),
            *tuple(case.input.get("initial_state_fixture_refs", ())),
            *tuple(case.input.get("environment_fixture_refs", ())),
        }
        if not case_fixture_refs <= fixture_refs:
            raise ArtifactContractError("case fixture reference is dangling")
        model_script_refs = tuple(case.input.get("model_script_refs", ()))
        if (
            not model_script_refs
            or not set(model_script_refs) <= script_refs
            or len(model_script_refs) != len(set(model_script_refs))
        ):
            raise ArtifactContractError("case model script reference is invalid")
        for script_ref in model_script_refs:
            expected_case_refs_by_script.setdefault(script_ref, set()).add(case.case_id)
    if set(expected_case_refs_by_script) != script_refs:
        raise ArtifactContractError("model script closure is incomplete")
    for script in scripts:
        if (
            set(script.case_refs)
            != expected_case_refs_by_script[script.model_script_ref]
        ):
            raise ArtifactContractError("model script Case closure is invalid")
    for lane in lanes:
        if not set(lane.case_refs) <= case_ids:
            raise ArtifactContractError("lane Case reference is dangling")
    if set(lanes[0].case_refs) != case_ids:
        raise ArtifactContractError("offline lane Case closure is incomplete")


def load_e2e01_artifacts(
    repository_root: str | Path,
    *,
    candidate_version: str,
    runtime_version: str | None = None,
) -> LoadedE2E01Artifacts:
    """Authenticate and load the fixed five-artifact E2E01 bundle."""

    candidate_version, runtime_version = _validate_caller_versions(
        candidate_version,
        runtime_version,
    )
    try:
        root = Path(repository_root).resolve(strict=True)
    except (OSError, RuntimeError, TypeError):
        raise ArtifactIntegrityError("repository root cannot be resolved") from None
    if not root.is_dir():
        raise ArtifactIntegrityError("repository root is not a directory")

    manifest_path = _resolve_closed_file(root, MANIFEST_RELATIVE_PATH)
    try:
        manifest_raw = manifest_path.read_bytes()
    except OSError:
        raise ArtifactIntegrityError("version manifest cannot be read") from None
    if hashlib.sha256(manifest_raw).hexdigest() != EXPECTED_MANIFEST_SHA256:
        raise ArtifactIntegrityError(
            "version manifest exact-byte digest does not match"
        )
    manifest = _safe_json_loads(manifest_raw)
    entries = _validate_manifest(manifest)

    authenticated_raw: dict[str, bytes] = {}
    for entry in entries:
        artifact_id = entry["artifact_id"]
        artifact_path = _resolve_closed_file(root, entry["path"])
        try:
            raw = artifact_path.read_bytes()
        except OSError:
            raise ArtifactIntegrityError("referenced artifact cannot be read") from None
        if hashlib.sha256(raw).hexdigest() != entry["sha256"]:
            raise ArtifactIntegrityError(
                "referenced artifact exact-byte digest does not match"
            )
        authenticated_raw[artifact_id] = raw

    parsed = {
        artifact_id: _safe_json_loads(raw)
        for artifact_id, raw in authenticated_raw.items()
    }
    for entry in entries:
        document = parsed[entry["artifact_id"]]
        if (
            document.get("artifact_id") != entry["artifact_id"]
            or document.get(entry["version_field"]) != entry["version"]
        ):
            raise ArtifactContractError(
                "artifact identity or version does not match manifest"
            )

    fixture = parsed["e2e01-thin-fixture"]
    _validate_fixture(fixture)
    cases = _validate_cases(parsed["e2e01-thin-cases"])
    scripts = _validate_scripts(parsed["e2e01-thin-model-scripts"])
    lanes = _validate_lanes(parsed["e2e01-thin-lanes"])
    _validate_reference_closure(fixture, cases, scripts, lanes)
    return LoadedE2E01Artifacts(
        candidate_version=candidate_version,
        runtime_version=runtime_version,
        manifest=manifest,
        fixture=fixture,
        cases=cases,
        scripts=scripts,
        lanes=lanes,
    )


_CYCLE2_MANIFEST_ARTIFACT_ID = "e2e01-cycle2-version-manifest"
_CYCLE2_EXPECTED_ARTIFACTS: Mapping[str, tuple[str, str, str]] = {
    "e2e01-cycle2-fixture": (
        "evals/fixtures/e2e01-cycle2.v1.json",
        "fixture_version",
        "e2e01-cycle2-fixture-v1",
    ),
    "e2e01-cycle2-cases": (
        "evals/cases/e2e01-cycle2.v1.json",
        "dataset_version",
        "e2e01-cycle2-dataset-v1",
    ),
    "e2e01-cycle2-model-scripts": (
        "evals/model_scripts/e2e01-cycle2.v1.json",
        "model_script_catalog_version",
        "e2e01-cycle2-model-scripts-v1",
    ),
    "e2e01-cycle2-lanes": (
        "evals/lanes/e2e01-cycle2.v1.json",
        "lane_manifest_version",
        "e2e01-cycle2-lanes-v1",
    ),
}
_CYCLE2_CASE_IDS = (
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
)
_CYCLE2_CASE_CONTRACT_SHA256: Mapping[str, str] = {
    "E2E01-02/unique-own-with-foreign-decoy": "ee4ba2acd7741587079aefd1d49fd15782532f55f5c93445a74088d79bc6fb2a",
    "E2E01-02/no-match-safe-not-found": "f88a0a8eadec996066db2fb147a5bb2514f1e7cd2b3fa50d8486d75b3387ccb8",
    "E2E01-03/multiple-minimum-summary": "6ae92783328f9ab634f23d713dfb2cd3567ca0823595346ddd0a82ee630c68fe",
    "E2E01-03/current-second-selected": "f0dc2d1baf2da2957dda31ced226fe658caa0b89ffeb06c71a143b1b21ee3e03",
    "E2E01-03/expired-second-rejected": "131b8ef42e2a07ffc79f4d5c965229cbbd67297d878d8142b083f85f336bc633",
    "E2E01-03/cross-task-second-rejected": "fbea2b11152d02fc7e266641ebaeac11c592c0edf65476bc5c76d77d94090e11",
    "E2E01-05/order-only-no-shipment": "a960200b4694424c52bd25aca25ab0bb37fde1f72a8307e10fa94ae7d9094b86",
    "E2E01-05/logistics-required-uses-shipment": "7aab06b77728321fa0ed9323e4e11329c45a2b3fe3084a8ed51fde99cece8ec4",
    "E2E01-06/stale-refresh-success": "d39cb6ff820093fcda128115557fffdd15bd906f587c05baf2cd1c4378846de2",
    "E2E01-06/transient-once-then-success": "d31f0b0c126d0ca8ef82b0e15cd188dc9b53d85298fa376d7b4f32a876462dd1",
    "E2E01-06/transient-exhausted-blocked": "6dfb18831720536fcc1881954c79a0fd63cad232b1af1ee6443d1eac7e326d37",
    "E2E01-06/deterministic-source-integrity-no-retry": "738ae3fdd847efc31e1120c65f340480d4e5222bc18d1877adf195a92c449e0c",
    "E2E01-06/insufficient-promise-need-human": "27027eb16d9474a19f3ff5dcc4a64b462a357029e3661252d22d8c00b4771674",
    "E2E01-06/no-shipment-need-human": "fadee09b297b66a224d53c9f3e54fa21dfdad278e897239f32d4bad3df081d98",
    "T2-candidate-owner-mismatch-rejected": "80887c5aa462b32d63d7686b0af992822ecd5fc73a2119890841aeb54691b84e",
    "T2-candidate-superseded-rejected": "871a4c511fdf5a9060a95893e26dbce2904dbabce5c020e35ca21585b2857848",
    "T2-candidate-out-of-range-rejected": "f53e8378307be20476eff022cdfdd3899e46f4f9c0c0fe459a502cb7ba88830a",
    "T2-candidate-zero-or-multiple-current-rejected": "34230b8e9acf1285766f990249cb25f0b5c1254419bf1d78298b2ca17b833bb2",
    "T2-assessment-delayed-boundary": "4eee58f51bfc5e0fbf0ad77c9f326d12158b6209276b41f5767e74c0f9142935",
    "T2-assessment-delivered-not-received-current-claim": "c416655d151c89545297162bc976eb6049976be1f47e96a97a0bd5783d4c438b",
    "T2-assessment-claim-corrected": "46560a94765e3d742f5be777cdd449747537141996c5f40300a9b31e87f87157",
    "T2-timeout-after-dispatch-then-success": "4d97d65c12d415a08d7d376d4b88dbc43e3b5c66d3cd54f35ceefab99c79374c",
    "T2-retry-finalize-before-second-fence-recovery": "58e736b45396059eeadf4d70b9045471daff5bea3c438c1b3fdf14e47f87a801",
    "T2-retry-finalize-before-second-fence-state-invalidated": "350bd904ed5a289503266983853d6db0edb61449d27167e96d3cb5a8a3cd6ec8",
    "T2-retry-unfinished-attempt-restart-blocked": "81fec623a8488e19e82df1d77e013ddd131fe6b7d333ca0bf0ceed9a122c0593",
    "T2-refresh-returns-already-stale-blocked": "fd5865f64defe194bbfacc3203b44fca9faae8cf23528bc02ec76dfe0fdfd315",
    "T2-two-active-packages-integrity-blocked": "90c1bde8a72d7dda8e61c5a12bdf79f28dd16f79775bb99544f203ebd41bfa35",
}
_CYCLE2_SHARED_EXPECTATIONS = (
    "TRUSTED_IDENTITY_NOT_USER_CONTROLLED",
    "PROVENANCE_CHAIN_RESTORABLE",
    "TRACE_AND_CONTEXT_EXCLUDE_PRIVATE_DATA",
    "RUN_STOP_REASON_EXPLICIT",
    "MODEL_VISIBLE_TOOLSET_HASH_REPLAYABLE",
    "EVAL_RESULT_VERSION_MANIFEST_COMPLETE",
    "NO_MODEL_GENERATED_FACT_OR_RESULT",
    "CANDIDATE_TARGET_MAPPING_OWNER_SCOPED",
    "TIMEOUT_ATTEMPT_SHAPE_EXACT",
)
_CYCLE2_GRADERS = (
    "SchemaGrader",
    "IdentityBoundaryGrader",
    "RequestUnderstandingGrader",
    "InputBindingGrader",
    "TaskStateGrader",
    "ToolCallGrader",
    "CandidateSetGrader",
    "ObservationGrader",
    "ShipmentAssessmentGrader",
    "RetryRecoveryGrader",
    "DisclosureGrader",
    "RendererFactGrader",
    "TraceCompletenessGrader",
    "PersistenceGrader",
    "ToolsetReplayGrader",
)
_CYCLE2_CASE_VERSION_MANIFEST = {
    "dataset_version": "e2e01-cycle2-dataset-v1",
    "fixture_versions": ["e2e01-cycle2-fixture-v1"],
    "model_config_version": "scripted-model-provider-config-v1",
    "prompt_version": "e2e01-cycle2-prompt-v1",
    "tool_registry_version": "e2e01-cycle2-tools-v1",
    "corpus_version": None,
    "runtime_version": _RUNTIME_VERSION_PLACEHOLDER,
}
_CYCLE2_PREDICATE_ARITY = {
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
_CYCLE2_SYMBOLS = frozenset(
    {
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
)
_CYCLE2_FORBIDDEN_PREDICATES = frozenset(
    {
        "FORBID_FOREIGN_PRIVATE_DATA_ANYWHERE",
        "FORBID_UNBOUND_OR_STALE_TOOLCALL",
        "FORBID_SEARCH_OBSERVATION",
        "FORBID_CANDIDATE_SET",
        "FORBID_SELECTION",
        "FORBID_ORDER_TOOLCALL",
        "FORBID_SHIPMENT_TOOLCALL",
        "FORBID_SHIPMENT_OBSERVATION",
        "FORBID_ASSESSMENT",
        "FORBID_STALE_FACT_IN_CONTEXT_OR_REPLY",
        "FORBID_MODEL_GENERATED_FACT_OR_RESULT",
        "FORBID_MODEL_PRESENTATION_AFTER_FIXED_RESULT",
        "FORBID_RETRY_AFTER_DETERMINISTIC_FAILURE",
        "FORBID_ATTEMPT_OVER_BUDGET",
        "FORBID_SECOND_TOOLCALL_IDENTITY_FOR_SAME_SEMANTICS",
        "FORBID_LOSS_OF_PRIOR_ATTEMPT_EVIDENCE",
        "FORBID_ASSESSMENT_BOUND_TO_OLD_OBSERVATION",
        "FORBID_NEW_PRIVATE_OBSERVATION",
        "FORBID_CROSS_TASK_REF_LOAD",
        "FORBID_PARTIAL_PRIVATE_PROJECTION",
        "FORBID_INVENTED_PACKAGE_OR_TICKET",
        "FORBID_SEARCH_TOOLCALL_IN_SELECTION_TURN",
        "FORBID_ATTEMPT_AFTER_STATE_OR_BINDING_INVALIDATED",
        "FORBID_AGENT_RUN_RESULT",
        "FORBID_ASSISTANT_MESSAGE",
        "FORBID_RESPONSE_RENDERED",
        "FORBID_TASK_OR_REQUEST_UNIT_MUTATION",
    }
)
_CYCLE2_FIXTURE_REFS = (
    "session:alice",
    "fx-search-unique-owner-a-with-foreign-decoy-v1",
    "fx-search-no-match-owner-a-v1",
    "fx-search-multiple-owner-a-v1",
    "fx-current-candidate-set-owner-a-v1",
    "fx-order-targets-owner-a-v1",
    "fx-expired-candidate-set-owner-a-v1",
    "fx-candidate-set-other-task-owner-a-v1",
    "fx-verified-order-target-o1001-owner-a-v1",
    "fx-dynamic-tool-pair-owner-a-v1",
    "fx-stale-shipment-observation-owner-a-v1",
    "fx-shipment-refresh-stalled-owner-a-v1",
    "fx-shipment-current-owner-a-v1",
    "fx-shipment-missing-promise-owner-a-v1",
    "fx-order-zero-active-package-owner-a-v1",
    "fx-candidate-owner-mismatch-owner-a-v1",
    "fx-superseded-candidate-set-owner-a-v1",
    "fx-zero-or-multiple-current-candidate-set-owner-a-v1",
    "fx-shipment-delayed-boundary-owner-a-v1",
    "fx-shipment-delivered-owner-a-v1",
    "fx-corrected-not-received-claim-owner-a-v1",
    "fx-retry-scheduled-obsolete-run-owner-a-v1",
    "fx-shipment-refresh-born-stale-owner-a-v1",
    "fx-two-active-packages-owner-a-v1",
)
_CYCLE2_PAIR_COMMON = {
    "pair_id": "PAIR-E2E01-05-V1",
    "pair_fixture_ref": "fx-dynamic-tool-pair-owner-a-v1",
    "pair_manifest_schema": "dynamic-tool-selection-pair.p0.v1",
    "registry_snapshot_digest": (
        "242ecc99f4886e490d45ed90ba22ba4532178b7f15473d632fef464d58d0cb7e"
    ),
    "model_visible_toolset_hash": (
        "035f5af9b8a6c4f99e06e12ed7ce236e3b1caaa00452d8778da96516ebd3272f"
    ),
    "provider_mapping_digest": (
        "79f33f3a4cf2c38e182cac13b24fd13d25d5f4a7d94890322df757051fa928dd"
    ),
    "owner_order_initial_state_digest": (
        "617044627393c3e10a1def6f294bd62375b0204b999284cb85a0a0e1df0dcfae"
    ),
}


def _cycle2_validate_manifest_ref(value: object) -> None:
    if _expect_mapping(value) != {
        "artifact_id": _CYCLE2_MANIFEST_ARTIFACT_ID,
        "path": CYCLE2_MANIFEST_RELATIVE_PATH,
    }:
        raise ArtifactContractError("Cycle 2 version manifest reference is invalid")


def _cycle2_validate_manifest(
    manifest: dict[str, Any],
) -> tuple[dict[str, Any], ...]:
    _expect_exact_keys(manifest, _MANIFEST_KEYS)
    if (
        manifest.get("artifact_type") != "EVAL_VERSION_MANIFEST"
        or manifest.get("artifact_id") != _CYCLE2_MANIFEST_ARTIFACT_ID
        or manifest.get("schema_version")
        != "e2e01-cycle2-version-manifest-schema-v1"
        or manifest.get("manifest_version")
        != "e2e01-cycle2-version-manifest-v1"
        or manifest.get("created_from_base_sha")
        != "5f2fa6d28575bcdcaf8a4c650469acc7dd19b7de"
        or manifest.get("hash_algorithm") != "SHA-256"
        or manifest.get("case_lifecycle_status") != "CONTRACT_DEFINED"
        or manifest.get("eval_result_artifacts_created") is not False
        or manifest.get("baseline_result_artifacts_created") is not False
    ):
        raise ArtifactContractError("Cycle 2 version manifest closed values are invalid")
    if _expect_mapping(manifest.get("versions")) != {
        "fixture_version": "e2e01-cycle2-fixture-v1",
        "dataset_version": "e2e01-cycle2-dataset-v1",
        "model_config_version": "scripted-model-provider-config-v1",
        "prompt_version": "e2e01-cycle2-prompt-v1",
        "tool_registry_version": "e2e01-cycle2-tools-v1",
        "corpus_version": None,
        "model_script_catalog_version": "e2e01-cycle2-model-scripts-v1",
        "lane_manifest_version": "e2e01-cycle2-lanes-v1",
        "runtime_version": _RUNTIME_VERSION_PLACEHOLDER,
    }:
        raise ArtifactContractError("Cycle 2 version set is invalid")
    if _expect_mapping(manifest.get("runtime_version_binding")) != {
        "required_at_eval_run": True,
        "source": "SOURCE_REVISION_OR_BUILD_ID",
        "artifact_placeholder": _RUNTIME_VERSION_PLACEHOLDER,
    }:
        raise ArtifactContractError("Cycle 2 runtime version binding is invalid")

    entries = tuple(
        _expect_mapping(item) for item in _expect_list(manifest.get("artifacts"))
    )
    expected_order = tuple(_CYCLE2_EXPECTED_ARTIFACTS)
    if tuple(entry.get("artifact_id") for entry in entries) != expected_order:
        raise ArtifactContractError("Cycle 2 manifest artifact set is invalid")
    if _expect_nonempty_strings(
        manifest.get("default_offline_artifact_refs")
    ) != expected_order:
        raise ArtifactContractError("Cycle 2 default artifact set is invalid")
    for entry in entries:
        _expect_exact_keys(
            entry,
            frozenset({"artifact_id", "path", "version_field", "version", "sha256"}),
        )
        artifact_id = entry["artifact_id"]
        expected_path, expected_field, expected_version = (
            _CYCLE2_EXPECTED_ARTIFACTS[artifact_id]
        )
        digest = entry.get("sha256")
        if (
            entry.get("path") != expected_path
            or entry.get("version_field") != expected_field
            or entry.get("version") != expected_version
            or not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        ):
            raise ArtifactContractError("Cycle 2 manifest artifact entry is invalid")
    return entries


def _cycle2_validate_fixture(document: dict[str, Any]) -> set[str]:
    _expect_exact_keys(
        document,
        frozenset(
            {
                "artifact_type",
                "artifact_id",
                "schema_version",
                "fixture_version",
                "classification",
                "version_manifest_ref",
                "consumers",
                "fixtures",
                "pair_manifests",
            }
        ),
    )
    if (
        document.get("artifact_type") != "E2E_FIXTURE_CATALOG"
        or document.get("artifact_id") != "e2e01-cycle2-fixture"
        or document.get("schema_version") != "e2e01-cycle2-fixture-schema-v1"
        or document.get("fixture_version") != "e2e01-cycle2-fixture-v1"
        or document.get("classification") != "SYNTHETIC_DETERMINISTIC"
        or document.get("consumers") != ["OFFLINE_GATE"]
    ):
        raise ArtifactContractError("Cycle 2 fixture closed values are invalid")
    _cycle2_validate_manifest_ref(document.get("version_manifest_ref"))
    fixtures = tuple(
        _expect_mapping(item) for item in _expect_list(document.get("fixtures"))
    )
    for fixture in fixtures:
        _expect_exact_keys(
            fixture,
            frozenset({"fixture_ref", "fixture_kind", "owner_scope"}),
        )
        if fixture.get("owner_scope") != "customer-A":
            raise ArtifactContractError("Cycle 2 fixture owner scope is invalid")
    fixture_refs = tuple(fixture.get("fixture_ref") for fixture in fixtures)
    if fixture_refs != _CYCLE2_FIXTURE_REFS:
        raise ArtifactContractError("Cycle 2 fixture identity set is invalid")

    pair_manifests = _expect_list(document.get("pair_manifests"))
    if len(pair_manifests) != 1:
        raise ArtifactContractError("Cycle 2 pair manifest set is invalid")
    pair = _expect_mapping(pair_manifests[0])
    if pair != {
        **_CYCLE2_PAIR_COMMON,
        "allowed_input_goals": ["ORDER_ONLY", "LOGISTICS_REQUIRED"],
    }:
        raise ArtifactContractError("Cycle 2 pair manifest is invalid")
    return set(_CYCLE2_FIXTURE_REFS)


def _cycle2_validate_required_predicate(predicate: object) -> tuple[str, ...]:
    if not isinstance(predicate, str):
        raise ArtifactContractError("Cycle 2 required predicate is invalid")
    match = re.fullmatch(r"([A-Z_]+)\(([^()]*)\)", predicate)
    if match is None or match.group(1) not in _CYCLE2_PREDICATE_ARITY:
        raise ArtifactContractError("Cycle 2 required predicate name is invalid")
    name, serialized_operands = match.groups()
    operands = tuple(serialized_operands.split(","))
    if (
        len(operands) != _CYCLE2_PREDICATE_ARITY[name]
        or any(not operand or operand != operand.strip() for operand in operands)
        or any(
            operand.startswith("$") and operand not in _CYCLE2_SYMBOLS
            for operand in operands
        )
    ):
        raise ArtifactContractError("Cycle 2 required predicate operands are invalid")
    if name == "REQ_RECOVERY" and operands[2:] not in {
        ("PASS", "RETRY_CONDITIONS_REVALIDATED", "APPEND_ATTEMPT_2"),
        (
            "NOT_APPLICABLE",
            "PROCESS_RESTART_DETECTED",
            "INTERRUPT_NO_REDISPATCH",
        ),
        ("FAIL", "STATE_OR_BINDING_INVALIDATED", "INTERRUPT_NO_REDISPATCH"),
    }:
        raise ArtifactContractError("Cycle 2 recovery predicate tuple is invalid")
    if name == "REQ_RUN_NO_RESULT_CLOSURE" and operands != (
        "SUPERSEDED",
        "STATE_OR_BINDING_INVALIDATED",
        "BLOCKED",
        "NONE",
    ):
        raise ArtifactContractError("Cycle 2 no-result closure predicate is invalid")
    return (name, *operands)


def _cycle2_validate_cases(
    document: dict[str, Any],
    *,
    fixture_refs: set[str],
) -> tuple[EvalCaseArtifact, ...]:
    _expect_exact_keys(document, _CASE_CATALOG_KEYS)
    if (
        document.get("artifact_type") != "EVAL_CASE_DATASET"
        or document.get("artifact_id") != "e2e01-cycle2-cases"
        or document.get("schema_version") != "e2e01-cycle2-case-schema-v1"
        or document.get("dataset_version") != "e2e01-cycle2-dataset-v1"
        or document.get("shared_expectations") != list(_CYCLE2_SHARED_EXPECTATIONS)
    ):
        raise ArtifactContractError("Cycle 2 case catalog closed values are invalid")
    if _expect_mapping(document.get("fixture_ref")) != {
        "artifact_id": "e2e01-cycle2-fixture",
        "fixture_version": "e2e01-cycle2-fixture-v1",
        "path": _CYCLE2_EXPECTED_ARTIFACTS["e2e01-cycle2-fixture"][0],
    }:
        raise ArtifactContractError("Cycle 2 case fixture reference is invalid")
    if _expect_mapping(document.get("model_script_catalog_ref")) != {
        "artifact_id": "e2e01-cycle2-model-scripts",
        "model_script_catalog_version": "e2e01-cycle2-model-scripts-v1",
        "path": _CYCLE2_EXPECTED_ARTIFACTS["e2e01-cycle2-model-scripts"][0],
    }:
        raise ArtifactContractError("Cycle 2 script catalog reference is invalid")
    _cycle2_validate_manifest_ref(document.get("version_manifest_ref"))

    raw_cases = tuple(
        _expect_mapping(item) for item in _expect_list(document.get("cases"))
    )
    if tuple(case.get("case_id") for case in raw_cases) != _CYCLE2_CASE_IDS:
        raise ArtifactContractError("Cycle 2 Case identity set is invalid")
    views: list[EvalCaseArtifact] = []
    pair_cases: list[dict[str, Any]] = []
    for case in raw_cases:
        _expect_exact_keys(
            case,
            _CASE_KEYS,
            optional=frozenset({"pair_identity"}),
        )
        case_id = case.get("case_id")
        if (
            case.get("title") != case_id
            or case.get("lifecycle_status") != "CONTRACT_DEFINED"
        ):
            raise ArtifactContractError("Cycle 2 Case lifecycle or title is invalid")
        requirement_refs = _expect_nonempty_strings(case.get("requirement_refs"))
        if requirement_refs[0] != "EVAL-CASE" or any(
            ref not in {
                "EVAL-CASE",
                "BUS-E2E01",
                "BUS-SAFETY",
                "BUS-RESULT",
                "INTENT-NEXTMOVE",
                "INTENT-VERSION",
                "TOOL-REGISTRY",
                "TOOL-CALL",
                "TOOL-RETRY",
                "TOOL-RESULT",
                "CORE-RUN",
                "MEM-TASK",
                "MEM-OBS",
                "MEM-FRESH",
                "MEM-RUN-CLOSURE",
                "MATRIX-E2E01-02",
                "MATRIX-E2E01-03",
                "MATRIX-E2E01-05",
                "MATRIX-E2E01-06",
            }
            and re.fullmatch(r"SPEC-R(?:0[1-9]|1[0-8])", ref) is None
            for ref in requirement_refs
        ):
            raise ArtifactContractError("Cycle 2 requirement reference is invalid")
        expected_scope = (
            ["TRAJECTORY"]
            if str(case_id).startswith("T2-")
            else ["COMPONENT", "TRAJECTORY", "E2E"]
        )
        if case.get("scope_levels") != expected_scope:
            raise ArtifactContractError("Cycle 2 Case scope is invalid")

        input_projection = _expect_mapping(case.get("input"))
        _expect_exact_keys(
            input_projection,
            frozenset(
                {
                    "messages",
                    "trusted_context_fixture_ref",
                    "initial_state_fixture_refs",
                    "environment_fixture_refs",
                    "model_script_refs",
                }
            ),
            optional=frozenset({"fault_injection"}),
        )
        messages = _expect_list(input_projection.get("messages"))
        if len(messages) != 1:
            raise ArtifactContractError("Cycle 2 message profile is invalid")
        message = _expect_mapping(messages[0])
        _expect_exact_keys(message, frozenset({"role", "content"}))
        if (
            message.get("role") != "user"
            or message.get("content")
            not in {
                "帮我查一下最近买的那双鞋。",
                "第二个",
                "订单 O-1001 状态怎么样？",
                "订单 O-1001 到哪了？",
                "订单 O-1001 显示已送达，但我没有收到。",
                "第六个",
            }
        ):
            raise ArtifactContractError("Cycle 2 message is invalid")
        case_fixture_refs = {
            input_projection.get("trusted_context_fixture_ref"),
            *_expect_nonempty_strings(
                input_projection.get("initial_state_fixture_refs")
            ),
            *_expect_nonempty_strings(
                input_projection.get("environment_fixture_refs")
            ),
        }
        if (
            input_projection.get("trusted_context_fixture_ref") != "session:alice"
            or not case_fixture_refs <= fixture_refs
            or input_projection.get("model_script_refs") != [f"script:{case_id}"]
        ):
            raise ArtifactContractError("Cycle 2 Case reference closure is invalid")
        if "fault_injection" in input_projection:
            fault = _expect_mapping(input_projection["fault_injection"])
            _expect_exact_keys(fault, frozenset({"fault_ref"}))
            if not str(fault.get("fault_ref", "")).startswith("fault:"):
                raise ArtifactContractError("Cycle 2 fault reference is invalid")

        if case.get("shared_expectation_refs") != list(
            _CYCLE2_SHARED_EXPECTATIONS
        ):
            raise ArtifactContractError("Cycle 2 shared expectations are invalid")
        expectations = _expect_mapping(case.get("expectations"))
        _expect_exact_keys(
            expectations,
            frozenset(
                {
                    "expected_http_status",
                    "expected_user_outcome",
                    "expected_stop_reason",
                    "response_policy",
                    "required_events",
                    "forbidden_events",
                    "state_assertions",
                    "disclosure_assertions",
                    "critical_failure_refs",
                }
            ),
        )
        required = tuple(
            _cycle2_validate_required_predicate(item)
            for item in _expect_list(expectations.get("required_events"))
        )
        forbidden = _expect_nonempty_strings(expectations.get("forbidden_events"))
        if not required or not set(forbidden) <= _CYCLE2_FORBIDDEN_PREDICATES:
            raise ArtifactContractError("Cycle 2 predicate set is invalid")
        stop_predicates = tuple(item for item in required if item[0] == "REQ_STOP")
        if stop_predicates != (
            (
                "REQ_STOP",
                expectations.get("expected_user_outcome"),
                expectations.get("expected_stop_reason"),
            ),
        ):
            raise ArtifactContractError("Cycle 2 stop predicate is inconsistent")
        if expectations.get("expected_http_status") != 200:
            raise ArtifactContractError("Cycle 2 expected HTTP status is invalid")
        for key in (
            "state_assertions",
            "disclosure_assertions",
            "critical_failure_refs",
        ):
            if not _expect_nonempty_strings(expectations.get(key)):
                raise ArtifactContractError("Cycle 2 Case assertions are incomplete")

        grading = _expect_mapping(case.get("grading"))
        _expect_exact_keys(
            grading,
            frozenset({"graders", "rubric_version", "repeat_policy"}),
        )
        if (
            grading.get("graders") != list(_CYCLE2_GRADERS)
            or grading.get("rubric_version") != "e2e01-cycle2-rubric-v1"
            or grading.get("repeat_policy")
            != {"mode": "EXACTLY_ONCE", "repetitions": 1}
            or _expect_mapping(case.get("version_manifest"))
            != _CYCLE2_CASE_VERSION_MANIFEST
        ):
            raise ArtifactContractError("Cycle 2 grading or version contract is invalid")
        if "pair_identity" in case:
            pair_cases.append(case)
        serialized_case = json.dumps(
            case,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        if hashlib.sha256(serialized_case).hexdigest() != (
            _CYCLE2_CASE_CONTRACT_SHA256[case_id]
        ):
            raise ArtifactContractError(
                "Cycle 2 Case semantic contract digest does not match"
            )
        views.append(
            EvalCaseArtifact(
                case_id=case_id,
                lifecycle_status="CONTRACT_DEFINED",
                requirement_refs=requirement_refs,
                input=input_projection,
                expectations=expectations,
                grading=grading,
                version_manifest=_expect_mapping(case.get("version_manifest")),
            )
        )

    if tuple(case["case_id"] for case in pair_cases) != (
        "E2E01-05/order-only-no-shipment",
        "E2E01-05/logistics-required-uses-shipment",
    ):
        raise ArtifactContractError("Cycle 2 pair Case closure is invalid")
    for case, input_goal in zip(
        pair_cases,
        ("ORDER_ONLY", "LOGISTICS_REQUIRED"),
        strict=True,
    ):
        if _expect_mapping(case.get("pair_identity")) != {
            **_CYCLE2_PAIR_COMMON,
            "input_goal": input_goal,
        }:
            raise ArtifactContractError("Cycle 2 pair identity is invalid")
    return tuple(views)


def _cycle2_validate_scripts(
    document: dict[str, Any],
) -> tuple[ModelScriptArtifact, ...]:
    _expect_exact_keys(document, _SCRIPT_CATALOG_KEYS)
    if (
        document.get("artifact_type") != "SCRIPTED_SCENARIO_CATALOG"
        or document.get("artifact_id") != "e2e01-cycle2-model-scripts"
        or document.get("schema_version") != "e2e01-cycle2-model-script-schema-v1"
        or document.get("model_script_catalog_version")
        != "e2e01-cycle2-model-scripts-v1"
        or document.get("provider") != "ScriptedModelProvider"
        or document.get("network_access") != "FORBIDDEN"
        or document.get("credential_inputs") != []
    ):
        raise ArtifactContractError("Cycle 2 model script closed values are invalid")
    _cycle2_validate_manifest_ref(document.get("version_manifest_ref"))
    raw_scripts = tuple(
        _expect_mapping(item) for item in _expect_list(document.get("scenarios"))
    )
    if tuple(script.get("model_script_ref") for script in raw_scripts) != tuple(
        f"script:{case_id}" for case_id in _CYCLE2_CASE_IDS
    ):
        raise ArtifactContractError("Cycle 2 model script identity set is invalid")

    allowed_behaviors = {
        "REQUEST_UNDERSTANDING": {
            "PROPOSE_SEARCH_ORDERS",
            "PROPOSE_CANDIDATE_SELECTION",
            "PROPOSE_GET_ORDER",
            "PROPOSE_GET_SHIPMENT",
        },
        "CONTROL_CANDIDATE": {
            "PROPOSE_GET_ORDER",
            "PROPOSE_GET_SHIPMENT",
            "PROPOSE_ORDER_SUMMARY",
            "PROPOSE_CANDIDATE_QUESTION",
            "PROPOSE_SHIPMENT_ASSESSMENT",
            "PROPOSE_FIXED_RESPONSE",
        },
        "FAULT_DIRECTIVE": {
            "INJECT_TOOL_FAULT",
            "INJECT_RUNTIME_RECOVERY_FAULT",
        },
    }
    views: list[ModelScriptArtifact] = []
    for script, case_id in zip(raw_scripts, _CYCLE2_CASE_IDS, strict=True):
        _expect_exact_keys(script, _SCRIPT_KEYS)
        if (
            script.get("case_refs") != [case_id]
            or script.get("expected_control_result")
            != {
                "authority": "NONE",
                "sut_result_source": "DETERMINISTIC_RUNTIME_ONLY",
            }
        ):
            raise ArtifactContractError("Cycle 2 script authority boundary is invalid")
        steps = tuple(
            _expect_mapping(step) for step in _expect_list(script.get("steps"))
        )
        if not steps:
            raise ArtifactContractError("Cycle 2 model script cannot be empty")
        for step in steps:
            purpose = step.get("purpose")
            behavior = step.get("behavior")
            required_keys = frozenset({"purpose", "behavior", "candidate_arguments"})
            optional_keys = (
                frozenset({"fault_ref"})
                if purpose == "FAULT_DIRECTIVE"
                else frozenset()
            )
            _expect_exact_keys(step, required_keys, optional=optional_keys)
            if (
                purpose not in allowed_behaviors
                or behavior not in allowed_behaviors[purpose]
                or not isinstance(step.get("candidate_arguments"), dict)
            ):
                raise ArtifactContractError("Cycle 2 script directive is invalid")
            if purpose == "FAULT_DIRECTIVE":
                if not str(step.get("fault_ref", "")).startswith("fault:"):
                    raise ArtifactContractError("Cycle 2 script fault is invalid")
            elif "fault_ref" in step:
                raise ArtifactContractError("Cycle 2 candidate carries a fault")
        views.append(
            ModelScriptArtifact(
                model_script_ref=script["model_script_ref"],
                case_refs=(case_id,),
                steps=steps,
                expected_control_result=_expect_mapping(
                    script.get("expected_control_result")
                ),
            )
        )
    return tuple(views)


def _cycle2_validate_lane(document: dict[str, Any]) -> tuple[EvalLaneArtifact, ...]:
    _expect_exact_keys(
        document,
        frozenset(
            {
                "artifact_type",
                "artifact_id",
                "schema_version",
                "lane_manifest_version",
                "default_lane",
                "dataset_ref",
                "fixture_ref",
                "model_script_catalog_ref",
                "version_manifest_ref",
                "lanes",
            }
        ),
    )
    if (
        document.get("artifact_type") != "EVAL_LANE_MANIFEST"
        or document.get("artifact_id") != "e2e01-cycle2-lanes"
        or document.get("schema_version") != "e2e01-cycle2-lane-schema-v1"
        or document.get("lane_manifest_version") != "e2e01-cycle2-lanes-v1"
        or document.get("default_lane") != "offline_gate"
    ):
        raise ArtifactContractError("Cycle 2 lane manifest closed values are invalid")
    _cycle2_validate_manifest_ref(document.get("version_manifest_ref"))
    if _expect_mapping(document.get("dataset_ref")) != {
        "artifact_id": "e2e01-cycle2-cases",
        "dataset_version": "e2e01-cycle2-dataset-v1",
        "path": _CYCLE2_EXPECTED_ARTIFACTS["e2e01-cycle2-cases"][0],
    } or _expect_mapping(document.get("fixture_ref")) != {
        "artifact_id": "e2e01-cycle2-fixture",
        "fixture_version": "e2e01-cycle2-fixture-v1",
        "path": _CYCLE2_EXPECTED_ARTIFACTS["e2e01-cycle2-fixture"][0],
    } or _expect_mapping(document.get("model_script_catalog_ref")) != {
        "artifact_id": "e2e01-cycle2-model-scripts",
        "model_script_catalog_version": "e2e01-cycle2-model-scripts-v1",
        "path": _CYCLE2_EXPECTED_ARTIFACTS["e2e01-cycle2-model-scripts"][0],
    }:
        raise ArtifactContractError("Cycle 2 lane artifact reference is invalid")
    lane = _expect_mapping(document.get("lanes"))
    _expect_exact_keys(lane, _LANE_KEYS)
    if (
        lane.get("lane") != "offline_gate"
        or lane.get("provider_adapter") != "ScriptedModelProvider"
        or lane.get("model_config_version")
        != "scripted-model-provider-config-v1"
        or lane.get("deterministic") is not True
        or lane.get("release_gate") is not True
        or lane.get("network_access") != "FORBIDDEN"
        or lane.get("credential_policy")
        != {"required_env": [], "when_missing": "NOT_APPLICABLE"}
        or lane.get("case_refs") != list(_CYCLE2_CASE_IDS)
        or lane.get("result_policy")
        != {
            "lifecycle_hold": "CONTRACT_DEFINED",
            "sut_dispatch": "FORBIDDEN_UNTIL_LIFECYCLE_ACTIVATION",
            "missing_case_result": "FAIL_COMMAND",
        }
    ):
        raise ArtifactContractError("Cycle 2 offline lane is invalid")
    return (
        EvalLaneArtifact(
            lane="offline_gate",
            provider_adapter="ScriptedModelProvider",
            model_config_version="scripted-model-provider-config-v1",
            deterministic=True,
            release_gate=True,
            network_access="FORBIDDEN",
            credential_policy=_expect_mapping(lane["credential_policy"]),
            case_refs=_CYCLE2_CASE_IDS,
            result_policy=_expect_mapping(lane["result_policy"]),
        ),
    )


def _cycle2_validate_script_case_closure(
    cases: tuple[EvalCaseArtifact, ...],
    scripts: tuple[ModelScriptArtifact, ...],
) -> None:
    for case, script in zip(cases, scripts, strict=True):
        if (
            tuple(case.input.get("model_script_refs", ()))
            != (script.model_script_ref,)
            or script.case_refs != (case.case_id,)
        ):
            raise ArtifactContractError("Cycle 2 script Case closure is invalid")
        case_fault = case.input.get("fault_injection")
        script_faults = tuple(
            step.get("fault_ref")
            for step in script.steps
            if step.get("purpose") == "FAULT_DIRECTIVE"
        )
        expected_faults = (
            ()
            if case_fault is None
            else (case_fault.get("fault_ref"),)
        )
        if script_faults != expected_faults:
            raise ArtifactContractError("Cycle 2 fault reference closure is invalid")


def load_e2e01_cycle2_artifacts(
    repository_root: str | Path,
    *,
    candidate_version: str,
    runtime_version: str | None = None,
) -> LoadedE2E01Artifacts:
    """Authenticate and load only the exact Cycle 2 five-artifact bundle."""

    candidate_version, runtime_version = _validate_caller_versions(
        candidate_version,
        runtime_version,
    )
    try:
        root = Path(repository_root).resolve(strict=True)
    except (OSError, RuntimeError, TypeError):
        raise ArtifactIntegrityError("repository root cannot be resolved") from None
    if not root.is_dir():
        raise ArtifactIntegrityError("repository root is not a directory")

    manifest_path = _resolve_closed_file(root, CYCLE2_MANIFEST_RELATIVE_PATH)
    try:
        manifest_raw = manifest_path.read_bytes()
    except OSError:
        raise ArtifactIntegrityError("Cycle 2 version manifest cannot be read") from None
    if hashlib.sha256(manifest_raw).hexdigest() != CYCLE2_EXPECTED_MANIFEST_SHA256:
        raise ArtifactIntegrityError(
            "Cycle 2 version manifest exact-byte digest does not match"
        )
    manifest = _safe_json_loads(manifest_raw)
    entries = _cycle2_validate_manifest(manifest)

    parsed: dict[str, dict[str, Any]] = {}
    for entry in entries:
        artifact_path = _resolve_closed_file(root, entry["path"])
        try:
            raw = artifact_path.read_bytes()
        except OSError:
            raise ArtifactIntegrityError("Cycle 2 artifact cannot be read") from None
        if hashlib.sha256(raw).hexdigest() != entry["sha256"]:
            raise ArtifactIntegrityError(
                "Cycle 2 artifact exact-byte digest does not match"
            )
        document = _safe_json_loads(raw)
        if (
            document.get("artifact_id") != entry["artifact_id"]
            or document.get(entry["version_field"]) != entry["version"]
        ):
            raise ArtifactContractError(
                "Cycle 2 artifact identity or version does not match manifest"
            )
        parsed[entry["artifact_id"]] = document

    fixture = parsed["e2e01-cycle2-fixture"]
    fixture_refs = _cycle2_validate_fixture(fixture)
    cases = _cycle2_validate_cases(
        parsed["e2e01-cycle2-cases"],
        fixture_refs=fixture_refs,
    )
    scripts = _cycle2_validate_scripts(parsed["e2e01-cycle2-model-scripts"])
    lanes = _cycle2_validate_lane(parsed["e2e01-cycle2-lanes"])
    _cycle2_validate_script_case_closure(cases, scripts)
    return LoadedE2E01Artifacts(
        candidate_version=candidate_version,
        runtime_version=runtime_version,
        manifest=manifest,
        fixture=fixture,
        cases=cases,
        scripts=scripts,
        lanes=lanes,
    )
