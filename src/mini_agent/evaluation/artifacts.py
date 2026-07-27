"""Versioned E2E01 Eval artifact loading boundary."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from mini_agent.core.common import AuditOnlyModel


MANIFEST_RELATIVE_PATH = "evals/manifests/e2e01-thin-slice.v1.json"
EXPECTED_MANIFEST_SHA256 = (
    "ffd9d3f130813e3acec347c4ab23fc4372a0969288c35120e72aa8650fa7b8bd"
)


class EvalArtifactError(ValueError):
    """Bounded failure while authenticating or validating Eval artifacts."""


class ArtifactIntegrityError(EvalArtifactError):
    """An artifact failed exact-byte or path integrity validation."""


class ArtifactContractError(EvalArtifactError):
    """An authenticated artifact failed its closed semantic contract."""


class EvalCaseArtifact(AuditOnlyModel):
    case_id: str
    lifecycle_status: str
    requirement_refs: tuple[str, ...]
    input: Mapping[str, Any]
    expectations: Mapping[str, Any]
    grading: Mapping[str, Any]
    version_manifest: Mapping[str, Any]
    observable_equivalence: Mapping[str, Any] | None = None


class ModelScriptArtifact(AuditOnlyModel):
    model_script_ref: str
    case_refs: tuple[str, ...]
    steps: tuple[Mapping[str, Any], ...]
    expected_control_result: Mapping[str, Any]
    runtime_fault: Mapping[str, Any] | None = None


class EvalLaneArtifact(AuditOnlyModel):
    lane: str
    provider_adapter: str
    model_config_version: str
    deterministic: bool
    release_gate: bool
    network_access: str
    credential_policy: Mapping[str, Any]
    case_refs: tuple[str, ...]
    result_policy: Mapping[str, Any]
    model_snapshot: str | None = None


class LoadedE2E01Artifacts(AuditOnlyModel):
    candidate_version: str
    runtime_version: str | None
    manifest: Mapping[str, Any]
    fixture: Mapping[str, Any]
    cases: tuple[EvalCaseArtifact, ...]
    scripts: tuple[ModelScriptArtifact, ...]
    lanes: tuple[EvalLaneArtifact, ...]

    def case_by_id(self, case_id: str) -> EvalCaseArtifact:
        raise NotImplementedError

    def script_by_ref(self, model_script_ref: str) -> ModelScriptArtifact:
        raise NotImplementedError

    def lane_by_name(self, lane: str) -> EvalLaneArtifact:
        raise NotImplementedError


def load_e2e01_artifacts(
    repository_root: str | Any,
    *,
    candidate_version: str,
    runtime_version: str | None = None,
) -> LoadedE2E01Artifacts:
    """Authenticate and load the fixed five-artifact E2E01 bundle."""

    raise NotImplementedError
