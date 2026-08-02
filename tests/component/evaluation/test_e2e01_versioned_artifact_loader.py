from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

import mini_agent.evaluation.artifacts as artifact_module
from mini_agent.evaluation.artifacts import (
    ArtifactContractError,
    ArtifactIntegrityError,
    load_e2e01_artifacts,
    load_e2e01_cycle2_artifacts,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
MANIFEST = Path("evals/manifests/e2e01-thin-slice.v1.json")
REFERENCED = (
    Path("evals/fixtures/e2e01-thin-slice.v1.json"),
    Path("evals/cases/e2e01-thin-slice.v1.json"),
    Path("evals/model_scripts/e2e01-thin-slice.v1.json"),
    Path("evals/lanes/e2e01-thin-slice.v1.json"),
)
EXPECTED_HASHES = {
    REFERENCED[0]: "3940f5755ab001339d254077b36b3ae2965e590adee43ea0fb4e1d7cd2648c33",
    REFERENCED[1]: "65524cb244d4856c02beed6eca970170f6088038a26d31b92cc0d0a8216441a6",
    REFERENCED[2]: "2b42415c1c705b30b34f7a80d810726d59f7891da52daa390208d62fa1aa7176",
    REFERENCED[3]: "61e43e8a560c3b31d1444759360941bb038d41a94ee1326be7c8cce52808158d",
    MANIFEST: "cf7683133145cf5c2c161b396be852ce4c226e3bc9d3154fd2b1dc8149166cb9",
}
CYCLE2_MANIFEST = Path("evals/manifests/e2e01-cycle2.v1.json")
CYCLE2_REFERENCED = (
    Path("evals/fixtures/e2e01-cycle2.v1.json"),
    Path("evals/cases/e2e01-cycle2.v1.json"),
    Path("evals/model_scripts/e2e01-cycle2.v1.json"),
    Path("evals/lanes/e2e01-cycle2.v1.json"),
)


def _copy_artifacts(tmp_path: Path) -> Path:
    for relative in (*REFERENCED, MANIFEST):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO_ROOT / relative, target)
    return tmp_path


def _read_json(root: Path, relative: Path) -> dict[str, object]:
    loaded = json.loads((root / relative).read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _write_json(root: Path, relative: Path, value: dict[str, object]) -> None:
    (root / relative).write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _reauthenticate_manifest(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    digest = hashlib.sha256((root / MANIFEST).read_bytes()).hexdigest()
    monkeypatch.setattr(artifact_module, "EXPECTED_MANIFEST_SHA256", digest)


def _copy_cycle2_artifacts(tmp_path: Path) -> Path:
    for relative in (*CYCLE2_REFERENCED, CYCLE2_MANIFEST):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO_ROOT / relative, target)
    return tmp_path


def _reauthenticate_cycle2_manifest(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    digest = hashlib.sha256((root / CYCLE2_MANIFEST).read_bytes()).hexdigest()
    monkeypatch.setattr(
        artifact_module,
        "CYCLE2_EXPECTED_MANIFEST_SHA256",
        digest,
    )


def _reauthenticate_cycle2_cases(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _read_json(root, CYCLE2_MANIFEST)
    case_entry = next(
        entry
        for entry in manifest["artifacts"]  # type: ignore[union-attr]
        if entry["artifact_id"] == "e2e01-cycle2-cases"
    )
    case_entry["sha256"] = hashlib.sha256(
        (root / CYCLE2_REFERENCED[1]).read_bytes()
    ).hexdigest()
    _write_json(root, CYCLE2_MANIFEST, manifest)
    _reauthenticate_cycle2_manifest(root, monkeypatch)


def test_loads_exact_five_artifacts_and_binds_caller_versions() -> None:
    bundle = load_e2e01_artifacts(
        REPO_ROOT,
        candidate_version="candidate:c35687d",
        runtime_version="runtime:01-08",
    )

    assert bundle.candidate_version == "candidate:c35687d"
    assert bundle.runtime_version == "runtime:01-08"
    assert bundle.manifest["case_lifecycle_status"] == "REGRESSION_GATE"
    assert bundle.manifest["eval_result_artifacts_created"] is False
    assert bundle.manifest["baseline_result_artifacts_created"] is False
    assert {case.case_id for case in bundle.cases} == {
        "E2E01-01",
        "E2E01-04-A",
        "E2E01-04-B",
        "E2E01-01+SEC-ARGUMENT-BINDING",
        "E2E01-01+FAULT-PROVIDER-PROTOCOL",
        "E2E01-01+FAULT-PRESENTATION-PROTOCOL",
    }
    assert bundle.script_by_ref("script:e2e01-01:success").steps
    assert bundle.lane_by_name("offline_gate").release_gate is True
    with pytest.raises(ValidationError):
        bundle.candidate_version = "changed"  # type: ignore[misc]


def test_tracked_artifact_hashes_are_the_fixed_expected_bytes() -> None:
    assert {
        relative: hashlib.sha256((REPO_ROOT / relative).read_bytes()).hexdigest()
        for relative in (*REFERENCED, MANIFEST)
    } == EXPECTED_HASHES


def test_manifest_tamper_fails_integrity_before_json_parse(tmp_path: Path) -> None:
    root = _copy_artifacts(tmp_path)
    (root / MANIFEST).write_bytes(b"{not-json")

    with pytest.raises(ArtifactIntegrityError):
        load_e2e01_artifacts(root, candidate_version="candidate")


def test_authenticated_manifest_lifecycle_downgrade_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _copy_artifacts(tmp_path)
    manifest = _read_json(root, MANIFEST)
    manifest["case_lifecycle_status"] = "EXECUTABLE"
    _write_json(root, MANIFEST, manifest)
    _reauthenticate_manifest(root, monkeypatch)

    with pytest.raises(
        ArtifactContractError,
        match="version manifest closed values are invalid",
    ):
        load_e2e01_artifacts(root, candidate_version="candidate")


def test_authenticated_case_lifecycle_downgrade_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _copy_artifacts(tmp_path)
    cases = _read_json(root, REFERENCED[1])
    for case in cases["cases"]:  # type: ignore[union-attr]
        case["lifecycle_status"] = "EXECUTABLE"
    _write_json(root, REFERENCED[1], cases)

    manifest = _read_json(root, MANIFEST)
    case_entry = next(
        entry
        for entry in manifest["artifacts"]  # type: ignore[union-attr]
        if entry["artifact_id"] == "e2e01-thin-cases"
    )
    case_entry["sha256"] = hashlib.sha256(
        (root / REFERENCED[1]).read_bytes()
    ).hexdigest()
    _write_json(root, MANIFEST, manifest)
    _reauthenticate_manifest(root, monkeypatch)

    with pytest.raises(
        ArtifactContractError,
        match="case lifecycle is not REGRESSION_GATE",
    ):
        load_e2e01_artifacts(root, candidate_version="candidate")


@pytest.mark.parametrize("relative", REFERENCED)
def test_referenced_artifact_tamper_fails_hash_before_parse(
    tmp_path: Path,
    relative: Path,
) -> None:
    root = _copy_artifacts(tmp_path)
    (root / relative).write_bytes(b"{not-json")

    with pytest.raises(ArtifactIntegrityError):
        load_e2e01_artifacts(root, candidate_version="candidate")


def test_symlink_escape_is_rejected_even_when_target_bytes_match(
    tmp_path: Path,
) -> None:
    root = _copy_artifacts(tmp_path / "repo")
    outside = tmp_path / "outside.json"
    shutil.copyfile(REPO_ROOT / REFERENCED[0], outside)
    (root / REFERENCED[0]).unlink()
    (root / REFERENCED[0]).symlink_to(outside)

    with pytest.raises(ArtifactIntegrityError):
        load_e2e01_artifacts(root, candidate_version="candidate")


def test_duplicate_manifest_artifact_id_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _copy_artifacts(tmp_path)
    manifest = _read_json(root, MANIFEST)
    artifacts = list(manifest["artifacts"])  # type: ignore[arg-type]
    artifacts[1] = dict(artifacts[0])
    manifest["artifacts"] = artifacts
    _write_json(root, MANIFEST, manifest)
    _reauthenticate_manifest(root, monkeypatch)

    with pytest.raises(ArtifactContractError):
        load_e2e01_artifacts(root, candidate_version="candidate")


def test_authenticated_wrong_version_and_dangling_script_ref_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _copy_artifacts(tmp_path)
    cases = _read_json(root, REFERENCED[1])
    cases["dataset_version"] = "wrong-version"
    first_case = cases["cases"][0]  # type: ignore[index]
    first_case["input"]["model_script_refs"] = ["script:missing"]  # type: ignore[index]
    _write_json(root, REFERENCED[1], cases)

    manifest = _read_json(root, MANIFEST)
    case_entry = next(
        entry
        for entry in manifest["artifacts"]  # type: ignore[union-attr]
        if entry["artifact_id"] == "e2e01-thin-cases"
    )
    case_entry["sha256"] = hashlib.sha256(
        (root / REFERENCED[1]).read_bytes()
    ).hexdigest()
    _write_json(root, MANIFEST, manifest)
    _reauthenticate_manifest(root, monkeypatch)

    with pytest.raises(ArtifactContractError):
        load_e2e01_artifacts(root, candidate_version="candidate")


@pytest.mark.parametrize(
    ("candidate_version", "runtime_version"),
    [
        ("", None),
        ("candidate", ""),
        ("candidate", "BOUND_AT_EVAL_RUN_FROM_SOURCE_REVISION_OR_BUILD_ID"),
    ],
)
def test_caller_version_binding_rejects_missing_or_placeholder_values(
    candidate_version: str,
    runtime_version: str | None,
) -> None:
    with pytest.raises(ArtifactContractError):
        load_e2e01_artifacts(
            REPO_ROOT,
            candidate_version=candidate_version,
            runtime_version=runtime_version,
        )


def test_cycle2_loads_the_atomic_executable_bundle() -> None:
    bundle = load_e2e01_cycle2_artifacts(
        REPO_ROOT,
        candidate_version="candidate:cycle2-executable",
        runtime_version="runtime:cycle2-executable",
    )

    assert len(bundle.cases) == 27
    assert {case.lifecycle_status for case in bundle.cases} == {"EXECUTABLE"}
    assert bundle.manifest["case_lifecycle_status"] == "EXECUTABLE"
    assert bundle.manifest["eval_result_artifacts_created"] is False
    assert bundle.manifest["baseline_result_artifacts_created"] is False


def test_cycle2_reauthenticated_manifest_lifecycle_downgrade_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _copy_cycle2_artifacts(tmp_path)
    manifest = _read_json(root, CYCLE2_MANIFEST)
    manifest["case_lifecycle_status"] = "CONTRACT_DEFINED"
    _write_json(root, CYCLE2_MANIFEST, manifest)
    _reauthenticate_cycle2_manifest(root, monkeypatch)

    with pytest.raises(
        ArtifactContractError,
        match="version manifest closed values are invalid",
    ):
        load_e2e01_cycle2_artifacts(root, candidate_version="candidate")


def test_cycle2_reauthenticated_mixed_case_lifecycle_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _copy_cycle2_artifacts(tmp_path)
    cases = _read_json(root, CYCLE2_REFERENCED[1])
    first_case = cases["cases"][0]  # type: ignore[index]
    first_case["lifecycle_status"] = "CONTRACT_DEFINED"  # type: ignore[index]
    _write_json(root, CYCLE2_REFERENCED[1], cases)
    _reauthenticate_cycle2_cases(root, monkeypatch)

    with pytest.raises(
        ArtifactContractError,
        match="Case lifecycle or title is invalid",
    ):
        load_e2e01_cycle2_artifacts(root, candidate_version="candidate")


def test_cycle2_reauthenticated_registry_version_drift_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _copy_cycle2_artifacts(tmp_path)
    cases = _read_json(root, CYCLE2_REFERENCED[1])
    first_case = cases["cases"][0]  # type: ignore[index]
    first_case["version_manifest"]["tool_registry_version"] = (  # type: ignore[index]
        "e2e01-cycle2-tools-v1"
    )
    _write_json(root, CYCLE2_REFERENCED[1], cases)
    _reauthenticate_cycle2_cases(root, monkeypatch)

    with pytest.raises(
        ArtifactContractError,
        match="grading or version contract is invalid",
    ):
        load_e2e01_cycle2_artifacts(root, candidate_version="candidate")


@pytest.mark.parametrize(
    ("case_index", "transport_value"),
    ((0, None), (14, 200)),
)
def test_cycle2_reauthenticated_transport_applicability_drift_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case_index: int,
    transport_value: int | None,
) -> None:
    root = _copy_cycle2_artifacts(tmp_path)
    cases = _read_json(root, CYCLE2_REFERENCED[1])
    case = cases["cases"][case_index]  # type: ignore[index]
    case["expectations"]["expected_http_status"] = transport_value  # type: ignore[index]
    _write_json(root, CYCLE2_REFERENCED[1], cases)
    _reauthenticate_cycle2_cases(root, monkeypatch)

    with pytest.raises(
        ArtifactContractError,
        match="expected HTTP status is invalid",
    ):
        load_e2e01_cycle2_artifacts(root, candidate_version="candidate")
