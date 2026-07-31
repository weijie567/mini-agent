"""Versioned E2E01 Eval artifact loading boundary."""

from __future__ import annotations

import hashlib
import json
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
