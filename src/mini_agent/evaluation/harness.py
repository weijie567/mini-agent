"""Injected E2E01 Eval Harness with structured Result/Failure separation."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import model_validator

from mini_agent.application.ports import EvalResultPort
from mini_agent.application.records import (
    EvalExecutionFailurePhase,
    EvalExecutionFailureRecord,
    EvalExecutionSafeErrorCode,
    EvalGraderReasonCode,
    EvalGraderResult,
    EvalGraderStatus,
    EvalResultRecord,
    EvalResultStatus,
    EvalVersionManifest,
    InsertOnlyWriteResult,
)
from mini_agent.core.common import AuditOnlyModel
from mini_agent.core.trace import TraceEvent, TraceEventType
from mini_agent.evaluation.artifacts import (
    ArtifactContractError,
    EvalCaseArtifact,
    EvalLaneArtifact,
    LoadedE2E01Artifacts,
)
from mini_agent.evaluation.graders import (
    EvalEvidence,
    GradingConfigurationError,
    GradingOutcome,
    SafeCaseObservable,
    determine_result_status,
    e2e01_04_safe_observables_match,
    grade_evidence,
    ordinary_trace_shape,
)
from mini_agent.evaluation.scripted_provider import (
    RuntimeFaultDirective,
    ScriptedModelProvider,
)


class EvalHarnessCommandError(RuntimeError):
    """Bounded command failure when even safe failure persistence is unavailable."""

    __slots__ = ()

    def __init__(self) -> None:
        super().__init__("EVAL_HARNESS_COMMAND_FAILED")


class EvalCaseSutResult(AuditOnlyModel):
    evidence: EvalEvidence
    safe_observable: SafeCaseObservable

    @model_validator(mode="after")
    def observable_matches_evidence(self) -> "EvalCaseSutResult":
        if (
            self.evidence.case_id != self.safe_observable.case_id
            or self.evidence.observed_outcome
            is not self.safe_observable.user_outcome
        ):
            raise ValueError("safe observable must match Eval evidence")
        return self


class EvalCaseSut(Protocol):
    async def execute_case(
        self,
        *,
        case: EvalCaseArtifact,
        scripted_provider: ScriptedModelProvider,
        runtime_fault: RuntimeFaultDirective | None,
    ) -> EvalCaseSutResult | None: ...


class EvalTraceCallbacks(Protocol):
    async def append_eval_case_graded(self, event: TraceEvent) -> None: ...

    async def reload_trace(self, trace_ref: UUID) -> tuple[TraceEvent, ...]: ...


GraderRunner = Callable[
    [Sequence[str], EvalEvidence],
    GradingOutcome,
]


class EvalLaneRunOutcome(AuditOnlyModel):
    lane: str
    results: tuple[EvalResultRecord, ...]
    execution_failures: tuple[EvalExecutionFailureRecord, ...]
    command_passed: bool

    @model_validator(mode="after")
    def command_status_matches_records(self) -> "EvalLaneRunOutcome":
        if self.command_passed and (
            self.execution_failures
            or not self.results
            or any(
                result.status is not EvalResultStatus.PASS
                for result in self.results
            )
        ):
            raise ValueError("passing command requires only complete PASS records")
        return self


class QwenBaselinePreflight(AuditOnlyModel):
    ready: bool
    not_run_record: EvalResultRecord | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def preflight_shape_is_consistent(self) -> "QwenBaselinePreflight":
        if self.ready:
            if self.not_run_record is not None or self.reason is not None:
                raise ValueError("ready baseline cannot carry NOT_RUN data")
        elif (
            self.not_run_record is None
            or self.not_run_record.status is not EvalResultStatus.NOT_RUN
            or self.not_run_record.lane != "qwen_baseline"
            or self.reason
            not in {"MISSING_REQUIRED_ENV", "REAL_EVAL_CASE_SUT_NOT_WIRED"}
        ):
            raise ValueError("not-ready baseline requires an empty NOT_RUN record")
        return self


@dataclass(frozen=True, slots=True)
class _StagedCase:
    case: EvalCaseArtifact
    result: EvalResultRecord
    safe_observable: SafeCaseObservable


_FAILURE_CODE_BY_PHASE = {
    EvalExecutionFailurePhase.HARNESS_SETUP: (
        EvalExecutionSafeErrorCode.HARNESS_SETUP_FAILED
    ),
    EvalExecutionFailurePhase.CASE_SETUP: (
        EvalExecutionSafeErrorCode.CASE_SETUP_FAILED
    ),
    EvalExecutionFailurePhase.SYSTEM_UNDER_TEST: (
        EvalExecutionSafeErrorCode.SYSTEM_UNDER_TEST_FAILED
    ),
    EvalExecutionFailurePhase.GRADING: (
        EvalExecutionSafeErrorCode.GRADING_FAILED
    ),
    EvalExecutionFailurePhase.RESULT_PERSISTENCE: (
        EvalExecutionSafeErrorCode.RESULT_PERSISTENCE_FAILED
    ),
    EvalExecutionFailurePhase.RESULT_COMPLETENESS: (
        EvalExecutionSafeErrorCode.RESULT_COMPLETENESS_FAILED
    ),
}


def _fresh_command_error() -> EvalHarnessCommandError:
    error = EvalHarnessCommandError()
    error.__cause__ = None
    error.__context__ = None
    return error


class OfflineEvalHarness:
    def __init__(
        self,
        *,
        artifacts: LoadedE2E01Artifacts,
        sut: EvalCaseSut,
        trace_callbacks: EvalTraceCallbacks,
        result_port: EvalResultPort,
        clock: Callable[[], datetime],
        grader_runner: GraderRunner | None = None,
    ) -> None:
        if type(artifacts) is not LoadedE2E01Artifacts:
            raise TypeError("artifacts must be an authenticated E2E01 bundle")
        if not callable(clock):
            raise TypeError("clock must be injected")
        self._artifacts = artifacts
        self._sut = sut
        self._trace_callbacks = trace_callbacks
        self._result_port = result_port
        self._clock = clock
        self._grader_runner = grader_runner or grade_evidence

    async def run_lane(
        self,
        *,
        eval_run_id: UUID,
        lane: str = "offline_gate",
        attempt: int = 1,
        case_ids: Sequence[str] | None = None,
        script_ref_by_case: Mapping[str, str] | None = None,
    ) -> EvalLaneRunOutcome:
        failures: list[EvalExecutionFailureRecord] = []
        setup_failed = False
        lane_artifact: EvalLaneArtifact | None = None
        try:
            if (
                lane != "offline_gate"
                or type(attempt) is not int
                or attempt < 1
            ):
                raise ArtifactContractError("offline Harness lane is invalid")
            lane_artifact = self._artifacts.lane_by_name(lane)
        except Exception:
            setup_failed = True
        if setup_failed or lane_artifact is None:
            failure = await self._append_failure(
                eval_run_id=eval_run_id,
                lane=lane or "INVALID_LANE",
                phase=EvalExecutionFailurePhase.HARNESS_SETUP,
                case=None,
                attempt=None,
                trace_ref=None,
                lane_artifact=None,
            )
            return EvalLaneRunOutcome(
                lane=lane or "INVALID_LANE",
                results=(),
                execution_failures=(failure,),
                command_passed=False,
            )

        selection_failed = False
        try:
            selected_ids = (
                tuple(lane_artifact.case_refs)
                if case_ids is None
                else tuple(case_ids)
            )
            script_selection = dict(script_ref_by_case or {})
        except Exception:
            selection_failed = True
            selected_ids = ()
            script_selection = {}
        if (
            selection_failed
            or not selected_ids
            or not all(
                isinstance(case_id, str) and case_id for case_id in selected_ids
            )
            or len(selected_ids) != len(set(selected_ids))
            or not set(selected_ids) <= set(lane_artifact.case_refs)
        ):
            failure = await self._append_failure(
                eval_run_id=eval_run_id,
                lane=lane,
                phase=EvalExecutionFailurePhase.HARNESS_SETUP,
                case=None,
                attempt=None,
                trace_ref=None,
                lane_artifact=lane_artifact,
            )
            return EvalLaneRunOutcome(
                lane=lane,
                results=(),
                execution_failures=(failure,),
                command_passed=False,
            )
        if not set(script_selection) <= set(selected_ids):
            failure = await self._append_failure(
                eval_run_id=eval_run_id,
                lane=lane,
                phase=EvalExecutionFailurePhase.HARNESS_SETUP,
                case=None,
                attempt=None,
                trace_ref=None,
                lane_artifact=lane_artifact,
            )
            return EvalLaneRunOutcome(
                lane=lane,
                results=(),
                execution_failures=(failure,),
                command_passed=False,
            )

        pair_ids = {"E2E01-04-A", "E2E01-04-B"}
        selected_pair = set(selected_ids) & pair_ids
        if selected_pair and selected_pair != pair_ids:
            for case_id in selected_ids:
                if case_id not in selected_pair:
                    continue
                case = self._artifacts.case_by_id(case_id)
                failures.append(
                    await self._append_failure(
                        eval_run_id=eval_run_id,
                        lane=lane,
                        phase=EvalExecutionFailurePhase.RESULT_COMPLETENESS,
                        case=case,
                        attempt=attempt,
                        trace_ref=None,
                        lane_artifact=lane_artifact,
                    )
                )
            return EvalLaneRunOutcome(
                lane=lane,
                results=(),
                execution_failures=tuple(failures),
                command_passed=False,
            )

        staged: dict[str, _StagedCase] = {}
        for case_id in selected_ids:
            case = self._artifacts.case_by_id(case_id)
            stage, failure = await self._stage_case(
                eval_run_id=eval_run_id,
                lane_artifact=lane_artifact,
                attempt=attempt,
                case=case,
                selected_script_ref=script_selection.get(case_id),
            )
            if failure is not None:
                failures.append(failure)
            elif stage is not None:
                staged[case_id] = stage

        if selected_pair == pair_ids:
            staged_pair = set(staged) & pair_ids
            if staged_pair != pair_ids:
                for case_id in staged_pair:
                    stage = staged.pop(case_id)
                    failures.append(
                        await self._append_failure(
                            eval_run_id=eval_run_id,
                            lane=lane,
                            phase=EvalExecutionFailurePhase.RESULT_COMPLETENESS,
                            case=stage.case,
                            attempt=attempt,
                            trace_ref=stage.result.trace_ref,
                            lane_artifact=lane_artifact,
                        )
                    )
            else:
                pair = {
                    case_id: staged[case_id].safe_observable
                    for case_id in pair_ids
                }
                if not e2e01_04_safe_observables_match(pair):
                    for case_id in pair_ids:
                        current = staged[case_id]
                        staged[case_id] = _StagedCase(
                            case=current.case,
                            result=_force_disclosure_failure(current.result),
                            safe_observable=current.safe_observable,
                        )

        persisted: list[EvalResultRecord] = []
        for case_id in selected_ids:
            stage = staged.get(case_id)
            if stage is None:
                continue
            persisted_record, failure = await self._append_result(
                stage.result,
                case=stage.case,
                lane_artifact=lane_artifact,
            )
            if failure is not None:
                failures.append(failure)
            elif persisted_record is not None:
                persisted.append(persisted_record)

        command_passed = (
            not failures
            and len(persisted) == len(selected_ids)
            and all(
                result.status is EvalResultStatus.PASS for result in persisted
            )
        )
        return EvalLaneRunOutcome(
            lane=lane,
            results=tuple(persisted),
            execution_failures=tuple(failures),
            command_passed=command_passed,
        )

    async def _stage_case(
        self,
        *,
        eval_run_id: UUID,
        lane_artifact: EvalLaneArtifact,
        attempt: int,
        case: EvalCaseArtifact,
        selected_script_ref: str | None,
    ) -> tuple[_StagedCase | None, EvalExecutionFailureRecord | None]:
        case_setup_failed = False
        provider: ScriptedModelProvider | None = None
        runtime_fault: RuntimeFaultDirective | None = None
        try:
            script_refs = tuple(case.input.get("model_script_refs", ()))
            if selected_script_ref is None:
                if len(script_refs) != 1:
                    raise ArtifactContractError(
                        "multi-script Case requires explicit script selection"
                    )
                selected_script_ref = script_refs[0]
            if (
                not isinstance(selected_script_ref, str)
                or selected_script_ref not in script_refs
            ):
                raise ArtifactContractError("selected script is not bound to Case")
            provider = ScriptedModelProvider(
                self._artifacts,
                model_script_ref=selected_script_ref,
            )
            runtime_fault = provider.take_runtime_fault_directive()
        except Exception:
            case_setup_failed = True
        if case_setup_failed or provider is None:
            return None, await self._append_failure(
                eval_run_id=eval_run_id,
                lane=lane_artifact.lane,
                phase=EvalExecutionFailurePhase.CASE_SETUP,
                case=case,
                attempt=attempt,
                trace_ref=None,
                lane_artifact=lane_artifact,
            )

        sut_failed = False
        sut_result: EvalCaseSutResult | None = None
        try:
            sut_result = await self._sut.execute_case(
                case=case,
                scripted_provider=provider,
                runtime_fault=runtime_fault,
            )
            if sut_result is not None:
                provider.assert_exhausted()
        except Exception:
            sut_failed = True
        if sut_failed:
            return None, await self._append_failure(
                eval_run_id=eval_run_id,
                lane=lane_artifact.lane,
                phase=EvalExecutionFailurePhase.SYSTEM_UNDER_TEST,
                case=case,
                attempt=attempt,
                trace_ref=None,
                lane_artifact=lane_artifact,
            )
        if type(sut_result) is not EvalCaseSutResult:
            return None, await self._append_failure(
                eval_run_id=eval_run_id,
                lane=lane_artifact.lane,
                phase=EvalExecutionFailurePhase.RESULT_COMPLETENESS,
                case=case,
                attempt=attempt,
                trace_ref=None,
                lane_artifact=lane_artifact,
            )
        evidence = sut_result.evidence
        if (
            evidence.case_id != case.case_id
            or not evidence.trace_events
            or any(
                event.event_type is TraceEventType.EVAL_CASE_GRADED
                for event in evidence.trace_events
            )
        ):
            return None, await self._append_failure(
                eval_run_id=eval_run_id,
                lane=lane_artifact.lane,
                phase=EvalExecutionFailurePhase.RESULT_COMPLETENESS,
                case=case,
                attempt=attempt,
                trace_ref=evidence.trace_ref,
                lane_artifact=lane_artifact,
            )

        configured_names = tuple(case.grading.get("graders", ()))
        if configured_names.count("TraceCompletenessGrader") != 1:
            return None, await self._append_failure(
                eval_run_id=eval_run_id,
                lane=lane_artifact.lane,
                phase=EvalExecutionFailurePhase.GRADING,
                case=case,
                attempt=attempt,
                trace_ref=evidence.trace_ref,
                lane_artifact=lane_artifact,
            )
        non_trace_names = tuple(
            name
            for name in configured_names
            if name != "TraceCompletenessGrader"
        )
        grading_failed = False
        initial_grading: GradingOutcome | None = None
        try:
            initial_grading = self._grader_runner(non_trace_names, evidence)
            _validate_grading_output(initial_grading, non_trace_names)
        except Exception:
            grading_failed = True
        if grading_failed or initial_grading is None:
            return None, await self._append_failure(
                eval_run_id=eval_run_id,
                lane=lane_artifact.lane,
                phase=EvalExecutionFailurePhase.GRADING,
                case=case,
                attempt=attempt,
                trace_ref=evidence.trace_ref,
                lane_artifact=lane_artifact,
            )

        graded_event = TraceEvent(
            trace_event_id=uuid5(
                NAMESPACE_URL,
                (
                    f"eval-case-graded:{eval_run_id}:{case.case_id}:"
                    f"{lane_artifact.lane}:{attempt}"
                ),
            ),
            event_type=TraceEventType.EVAL_CASE_GRADED,
            occurred_at=max(
                event.occurred_at for event in evidence.trace_events
            )
            + timedelta(microseconds=1),
            run_id=evidence.trace_events[0].run_id,
            case_id=case.case_id,
        )
        append_failed = False
        try:
            await self._trace_callbacks.append_eval_case_graded(graded_event)
        except Exception:
            append_failed = True
        if append_failed:
            return None, await self._append_failure(
                eval_run_id=eval_run_id,
                lane=lane_artifact.lane,
                phase=EvalExecutionFailurePhase.TRACE_PERSISTENCE,
                safe_error_code=(
                    EvalExecutionSafeErrorCode.TRACE_PERSISTENCE_FAILED
                ),
                case=case,
                attempt=attempt,
                trace_ref=evidence.trace_ref,
                lane_artifact=lane_artifact,
            )

        reload_failed = False
        final_trace: tuple[TraceEvent, ...] | None = None
        try:
            final_trace = await self._trace_callbacks.reload_trace(
                evidence.trace_ref
            )
        except Exception:
            reload_failed = True
        if reload_failed:
            return None, await self._append_failure(
                eval_run_id=eval_run_id,
                lane=lane_artifact.lane,
                phase=EvalExecutionFailurePhase.TRACE_PERSISTENCE,
                safe_error_code=EvalExecutionSafeErrorCode.TRACE_STORE_UNAVAILABLE,
                case=case,
                attempt=attempt,
                trace_ref=evidence.trace_ref,
                lane_artifact=lane_artifact,
            )
        if (
            not isinstance(final_trace, tuple)
            or not all(type(event) is TraceEvent for event in final_trace)
            or tuple(
                event
                for event in final_trace
                if event.event_type is TraceEventType.EVAL_CASE_GRADED
            )
            != (graded_event,)
        ):
            return None, await self._append_failure(
                eval_run_id=eval_run_id,
                lane=lane_artifact.lane,
                phase=EvalExecutionFailurePhase.RESULT_COMPLETENESS,
                case=case,
                attempt=attempt,
                trace_ref=evidence.trace_ref,
                lane_artifact=lane_artifact,
            )

        final_evidence = _replace_trace(evidence, final_trace)
        final_grading_failed = False
        final_grading: GradingOutcome | None = None
        try:
            final_grading = self._grader_runner(
                ("TraceCompletenessGrader",),
                final_evidence,
            )
            _validate_grading_output(
                final_grading,
                ("TraceCompletenessGrader",),
            )
        except Exception:
            final_grading_failed = True
        if final_grading_failed or final_grading is None:
            return None, await self._append_failure(
                eval_run_id=eval_run_id,
                lane=lane_artifact.lane,
                phase=EvalExecutionFailurePhase.GRADING,
                case=case,
                attempt=attempt,
                trace_ref=evidence.trace_ref,
                lane_artifact=lane_artifact,
            )

        result_by_name = {
            result.grader_name: result
            for result in (
                *initial_grading.grader_results,
                *final_grading.grader_results,
            )
        }
        grader_results = tuple(
            result_by_name[name] for name in configured_names
        )
        status = determine_result_status(
            grader_results,
            final_evidence.critical_failures,
        )
        result = EvalResultRecord(
            schema_version="eval_result_record.p0.v1",
            eval_run_id=eval_run_id,
            case_id=case.case_id,
            lane=lane_artifact.lane,
            attempt=attempt,
            status=status,
            grader_results=grader_results,
            critical_failures=final_evidence.critical_failures,
            observed_outcome=final_evidence.observed_outcome,
            trace_ref=final_evidence.trace_ref,
            version_manifest=self._version_manifest(case, lane_artifact),
            latency_summary=None,
            usage_summary=None,
            completed_at=max(event.occurred_at for event in final_trace),
        )
        safe_observable = SafeCaseObservable(
            case_id=sut_result.safe_observable.case_id,
            http_status=sut_result.safe_observable.http_status,
            user_outcome=sut_result.safe_observable.user_outcome,
            response_policy=sut_result.safe_observable.response_policy,
            ordinary_trace_shape=ordinary_trace_shape(final_trace),
            model_calls=sut_result.safe_observable.model_calls,
        )
        return (
            _StagedCase(
                case=case,
                result=result,
                safe_observable=safe_observable,
            ),
            None,
        )

    async def _append_result(
        self,
        record: EvalResultRecord,
        *,
        case: EvalCaseArtifact,
        lane_artifact: EvalLaneArtifact,
    ) -> tuple[EvalResultRecord | None, EvalExecutionFailureRecord | None]:
        append_failed = False
        write_result: InsertOnlyWriteResult | None = None
        try:
            write_result = await self._result_port.append_eval_result(record)
        except Exception:
            append_failed = True
        if not append_failed and write_result is InsertOnlyWriteResult.INSERTED:
            return record, None
        if (
            not append_failed
            and write_result is InsertOnlyWriteResult.ALREADY_EXISTS
        ):
            load_failed = False
            existing: EvalResultRecord | None = None
            try:
                existing = await self._result_port.load_eval_result(
                    eval_run_id=record.eval_run_id,
                    case_id=record.case_id,
                    lane=record.lane,
                    attempt=record.attempt,
                )
            except Exception:
                load_failed = True
            if not load_failed and existing == record:
                return existing, None
        failure = await self._append_failure(
            eval_run_id=record.eval_run_id,
            lane=record.lane,
            phase=EvalExecutionFailurePhase.RESULT_PERSISTENCE,
            case=case,
            attempt=record.attempt,
            trace_ref=record.trace_ref,
            lane_artifact=lane_artifact,
        )
        return None, failure

    async def _append_failure(
        self,
        *,
        eval_run_id: UUID,
        lane: str,
        phase: EvalExecutionFailurePhase,
        case: EvalCaseArtifact | None,
        attempt: int | None,
        trace_ref: UUID | None,
        lane_artifact: EvalLaneArtifact | None,
        safe_error_code: EvalExecutionSafeErrorCode | None = None,
    ) -> EvalExecutionFailureRecord:
        code = safe_error_code or _FAILURE_CODE_BY_PHASE[phase]
        failure = EvalExecutionFailureRecord(
            schema_version="eval_execution_failure_record.p0.v1",
            eval_run_id=eval_run_id,
            case_id=case.case_id if case is not None else None,
            lane=lane,
            attempt=attempt if case is not None else None,
            failure_phase=phase,
            safe_error_code=code,
            diagnostic_ref=None,
            trace_ref=trace_ref,
            version_manifest=self._version_manifest(case, lane_artifact),
            occurred_at=self._clock(),
        )
        append_failed = False
        try:
            await self._result_port.append_eval_execution_failure(failure)
        except Exception:
            append_failed = True
        if append_failed:
            raise _fresh_command_error()
        return failure

    def _version_manifest(
        self,
        case: EvalCaseArtifact | None,
        lane: EvalLaneArtifact | None,
    ) -> EvalVersionManifest:
        manifest_versions = self._artifacts.manifest["versions"]
        case_versions = case.version_manifest if case is not None else {}
        fixture_versions = tuple(
            case_versions.get(
                "fixture_versions",
                (manifest_versions["fixture_version"],),
            )
        )
        return EvalVersionManifest(
            dataset_version=case_versions.get(
                "dataset_version",
                manifest_versions["dataset_version"],
            ),
            candidate_version=self._artifacts.candidate_version,
            baseline_version=None,
            fixture_versions=fixture_versions,
            model_config_version=(
                lane.model_config_version if lane is not None else None
            ),
            prompt_version=case_versions.get(
                "prompt_version",
                manifest_versions["prompt_version"],
            ),
            tool_registry_version=case_versions.get(
                "tool_registry_version",
                manifest_versions["tool_registry_version"],
            ),
            corpus_version=None,
            runtime_version=self._artifacts.runtime_version,
        )


def build_qwen_baseline_preflight(
    *,
    artifacts: LoadedE2E01Artifacts,
    eval_run_id: UUID,
    case_id: str,
    attempt: int,
    environment: Mapping[str, str],
    real_sut: EvalCaseSut | None,
    completed_at: datetime,
) -> QwenBaselinePreflight:
    if type(artifacts) is not LoadedE2E01Artifacts:
        raise TypeError("artifacts must be an authenticated E2E01 bundle")
    lane = artifacts.lane_by_name("qwen_baseline")
    if (
        case_id not in lane.case_refs
        or type(attempt) is not int
        or attempt < 1
    ):
        raise ArtifactContractError("Qwen preflight Case identity is invalid")
    required_env = tuple(lane.credential_policy.get("required_env", ()))
    missing_env = any(
        not isinstance(environment.get(name), str)
        or not environment.get(name, "").strip()
        for name in required_env
    )
    if not missing_env and real_sut is not None:
        return QwenBaselinePreflight(ready=True)
    reason = (
        "MISSING_REQUIRED_ENV"
        if missing_env
        else "REAL_EVAL_CASE_SUT_NOT_WIRED"
    )
    case = artifacts.case_by_id(case_id)
    record = EvalResultRecord(
        schema_version="eval_result_record.p0.v1",
        eval_run_id=eval_run_id,
        case_id=case_id,
        lane="qwen_baseline",
        attempt=attempt,
        status=EvalResultStatus.NOT_RUN,
        grader_results=(),
        critical_failures=(),
        observed_outcome=None,
        trace_ref=None,
        version_manifest=EvalVersionManifest(
            dataset_version=case.version_manifest["dataset_version"],
            candidate_version=artifacts.candidate_version,
            baseline_version=None,
            fixture_versions=tuple(
                case.version_manifest["fixture_versions"]
            ),
            model_config_version=lane.model_config_version,
            prompt_version=case.version_manifest.get("prompt_version"),
            tool_registry_version=case.version_manifest.get(
                "tool_registry_version"
            ),
            corpus_version=None,
            runtime_version=artifacts.runtime_version,
        ),
        latency_summary=None,
        usage_summary=None,
        completed_at=completed_at,
    )
    return QwenBaselinePreflight(
        ready=False,
        not_run_record=record,
        reason=reason,
    )


async def append_qwen_not_run_record(
    *,
    result_port: EvalResultPort,
    record: EvalResultRecord,
) -> EvalResultRecord:
    if (
        type(record) is not EvalResultRecord
        or record.lane != "qwen_baseline"
        or record.status is not EvalResultStatus.NOT_RUN
    ):
        raise _fresh_command_error()
    failed = False
    write_result: InsertOnlyWriteResult | None = None
    try:
        write_result = await result_port.append_eval_result(record)
    except Exception:
        failed = True
    if not failed and write_result is InsertOnlyWriteResult.INSERTED:
        return record
    if not failed and write_result is InsertOnlyWriteResult.ALREADY_EXISTS:
        load_failed = False
        existing: EvalResultRecord | None = None
        try:
            existing = await result_port.load_eval_result(
                eval_run_id=record.eval_run_id,
                case_id=record.case_id,
                lane=record.lane,
                attempt=record.attempt,
            )
        except Exception:
            load_failed = True
        if not load_failed and existing == record:
            return existing
    raise _fresh_command_error()


def _validate_grading_output(
    outcome: object,
    configured_names: Sequence[str],
) -> None:
    if type(outcome) is not GradingOutcome or tuple(
        result.grader_name for result in outcome.grader_results
    ) != tuple(configured_names):
        raise GradingConfigurationError("grader output is incomplete")


def _replace_trace(
    evidence: EvalEvidence,
    trace_events: tuple[TraceEvent, ...],
) -> EvalEvidence:
    values = {
        field_name: getattr(evidence, field_name)
        for field_name in EvalEvidence.model_fields
    }
    values["trace_events"] = trace_events
    return EvalEvidence(**values)


def _force_disclosure_failure(record: EvalResultRecord) -> EvalResultRecord:
    replacement = EvalGraderResult(
        grader_name="DisclosureGrader",
        status=EvalGraderStatus.FAIL,
        reason_code=EvalGraderReasonCode.ASSERTION_FAILED,
    )
    grader_results = tuple(
        replacement
        if result.grader_name == "DisclosureGrader"
        else result
        for result in record.grader_results
    )
    if not any(
        result.grader_name == "DisclosureGrader"
        for result in record.grader_results
    ):
        raise GradingConfigurationError(
            "E2E01-04 requires DisclosureGrader"
        )
    return EvalResultRecord(
        schema_version=record.schema_version,
        eval_run_id=record.eval_run_id,
        case_id=record.case_id,
        lane=record.lane,
        attempt=record.attempt,
        status=EvalResultStatus.FAIL,
        grader_results=grader_results,
        critical_failures=record.critical_failures,
        observed_outcome=record.observed_outcome,
        trace_ref=record.trace_ref,
        version_manifest=record.version_manifest,
        latency_summary=record.latency_summary,
        usage_summary=record.usage_summary,
        completed_at=record.completed_at,
    )
