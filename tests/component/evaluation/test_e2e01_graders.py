from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from mini_agent.application.records import (
    AgentRunResult,
    CriticalFailureCode,
    EvalGraderReasonCode,
    EvalGraderResult,
    EvalGraderStatus,
    EvalResultStatus,
)
from mini_agent.core.trace import (
    AgentOutcome,
    AgentRunRecord,
    AgentRunStatus,
    StopReason,
    TraceEvent,
    TraceEventType,
)
from mini_agent.evaluation.graders import (
    GRADER_NAMES,
    EvalEvidence,
    GradingConfigurationError,
    SafeCaseObservable,
    TraceEventCountExpectation,
    determine_result_status,
    e2e01_04_safe_observables_match,
    grade_evidence,
    grader_registry,
    ordinary_trace_shape,
)


RUN_ID = UUID("00000000-0000-4000-8000-000000000501")
TRACE_REF = UUID("00000000-0000-4000-8000-000000000502")
NOW = datetime(2026, 7, 27, 8, 0, tzinfo=UTC)

CHECK_FIELD_BY_GRADER = {
    "SchemaGrader": "schema_assertions_pass",
    "IdentityBoundaryGrader": "identity_boundary_assertions_pass",
    "RequestUnderstandingGrader": "request_understanding_assertions_pass",
    "InputBindingGrader": "input_binding_assertions_pass",
    "TaskStateGrader": "task_state_assertions_pass",
    "ToolCallGrader": "tool_call_assertions_pass",
    "ObservationGrader": "observation_assertions_pass",
    "DisclosureGrader": "disclosure_assertions_pass",
    "RendererFactGrader": "renderer_fact_assertions_pass",
    "ErrorMappingGrader": "error_mapping_assertions_pass",
    "PersistenceGrader": "persistence_assertions_pass",
    "ToolsetReplayGrader": "toolset_replay_assertions_pass",
}


def _trace(
    event_type: TraceEventType,
    *,
    offset: int,
    case_id: str = "E2E01-01",
) -> TraceEvent:
    values: dict[str, object] = {
        "trace_event_id": UUID(int=600 + offset),
        "event_type": event_type,
        "occurred_at": NOW + timedelta(milliseconds=offset),
        "run_id": RUN_ID,
        "case_id": case_id,
    }
    if event_type is TraceEventType.RUN_STOPPED:
        values.update(
            {
                "user_outcome": AgentOutcome.COMPLETED,
                "stop_reason": StopReason.GOAL_COMPLETED,
            }
        )
    return TraceEvent(**values)


def _valid_evidence(**overrides: object) -> EvalEvidence:
    trace_events = (
        _trace(TraceEventType.RUN_STARTED, offset=1),
        _trace(TraceEventType.RUN_STOPPED, offset=2),
        _trace(TraceEventType.EVAL_CASE_GRADED, offset=3),
    )
    values: dict[str, object] = {
        "case_id": "E2E01-01",
        "observed_outcome": AgentOutcome.COMPLETED,
        "trace_ref": TRACE_REF,
        "trace_events": trace_events,
        "required_trace_events": (
            TraceEventType.RUN_STARTED,
            TraceEventType.RUN_STOPPED,
            TraceEventType.EVAL_CASE_GRADED,
        ),
        "forbidden_trace_events": (TraceEventType.TOOL_CALL_FAILED,),
        "expected_event_counts": (
            TraceEventCountExpectation(
                event_type=TraceEventType.EVAL_CASE_GRADED,
                count=1,
            ),
        ),
        "run_record": AgentRunRecord(
            run_id=RUN_ID,
            status=AgentRunStatus.COMPLETED,
            provider_lane="offline_gate",
            started_at=NOW,
            completed_at=NOW + timedelta(seconds=1),
            stop_reason=StopReason.GOAL_COMPLETED,
        ),
        "agent_result": AgentRunResult(
            run_id=RUN_ID,
            outcome=AgentOutcome.COMPLETED,
            message="合成结果",
        ),
    }
    values.update(overrides)
    return EvalEvidence(**values)


def test_registry_membership_is_exactly_the_13_artifact_names() -> None:
    registry = grader_registry()
    assert tuple(registry) == GRADER_NAMES
    assert len(registry) == 13
    assert all(registry[name].name == name for name in GRADER_NAMES)


@pytest.mark.parametrize("grader_name", GRADER_NAMES)
def test_every_registered_grader_passes_valid_typed_evidence(
    grader_name: str,
) -> None:
    result = grader_registry()[grader_name].grade(_valid_evidence())
    assert result == EvalGraderResult(
        grader_name=grader_name,
        status=EvalGraderStatus.PASS,
    )


@pytest.mark.parametrize(
    ("grader_name", "check_field"),
    tuple(CHECK_FIELD_BY_GRADER.items()),
)
def test_each_non_trace_grader_rejects_directed_tamper(
    grader_name: str,
    check_field: str,
) -> None:
    result = grader_registry()[grader_name].grade(
        _valid_evidence(**{check_field: False})
    )
    assert result.status is EvalGraderStatus.FAIL
    assert result.reason_code is EvalGraderReasonCode.ASSERTION_FAILED


def test_missing_component_evidence_uses_stable_missing_record_reason() -> None:
    result = grader_registry()["ObservationGrader"].grade(
        _valid_evidence(observation_assertions_pass=None)
    )
    assert result.status is EvalGraderStatus.FAIL
    assert result.reason_code is EvalGraderReasonCode.MISSING_RECORD


@pytest.mark.parametrize(
    "overrides",
    [
        {
            "required_trace_events": (
                TraceEventType.RUN_STARTED,
                TraceEventType.OBSERVATION_RECORDED,
            )
        },
        {"forbidden_trace_events": (TraceEventType.RUN_STARTED,)},
        {
            "expected_event_counts": (
                TraceEventCountExpectation(
                    event_type=TraceEventType.EVAL_CASE_GRADED,
                    count=2,
                ),
            )
        },
        {
            "trace_events": (
                _trace(TraceEventType.RUN_STOPPED, offset=2),
                _trace(TraceEventType.RUN_STARTED, offset=1),
            )
        },
    ],
)
def test_trace_grader_rejects_missing_forbidden_count_and_order_tamper(
    overrides: dict[str, object],
) -> None:
    result = grader_registry()["TraceCompletenessGrader"].grade(
        _valid_evidence(**overrides)
    )
    assert result.status is EvalGraderStatus.FAIL
    assert result.reason_code in {
        EvalGraderReasonCode.TRACE_EVENT_MISSING,
        EvalGraderReasonCode.ASSERTION_FAILED,
    }


@pytest.mark.parametrize(
    "configured",
    [
        (),
        ("SchemaGrader", "SchemaGrader"),
        ("UnknownGrader",),
        ("",),
    ],
)
def test_unknown_duplicate_or_missing_grader_configuration_fails_closed(
    configured: tuple[str, ...],
) -> None:
    with pytest.raises(GradingConfigurationError):
        grade_evidence(configured, _valid_evidence())


def test_applicable_critical_failure_forces_case_fail() -> None:
    passing = tuple(
        EvalGraderResult(
            grader_name=name,
            status=EvalGraderStatus.PASS,
        )
        for name in GRADER_NAMES
    )
    assert (
        determine_result_status(passing, (CriticalFailureCode.CF_14,))
        is EvalResultStatus.FAIL
    )
    outcome = grade_evidence(
        GRADER_NAMES,
        _valid_evidence(critical_failures=(CriticalFailureCode.CF_14,)),
    )
    assert outcome.status is EvalResultStatus.FAIL
    assert outcome.critical_failures == (CriticalFailureCode.CF_14,)


@pytest.mark.parametrize(
    ("field", "grader_name"),
    [
        ("identity_boundary_assertions_pass", "IdentityBoundaryGrader"),
        ("input_binding_assertions_pass", "InputBindingGrader"),
        ("task_state_assertions_pass", "TaskStateGrader"),
        ("renderer_fact_assertions_pass", "RendererFactGrader"),
        ("error_mapping_assertions_pass", "ErrorMappingGrader"),
    ],
)
def test_identity_substitution_stale_and_fact_bearing_faults_fail(
    field: str,
    grader_name: str,
) -> None:
    result = grader_registry()[grader_name].grade(
        _valid_evidence(**{field: False})
    )
    assert result.status is EvalGraderStatus.FAIL


def _safe_observable(
    case_id: str,
    **overrides: object,
) -> SafeCaseObservable:
    values: dict[str, object] = {
        "case_id": case_id,
        "http_status": 200,
        "user_outcome": AgentOutcome.NOT_FOUND_OR_NOT_ACCESSIBLE,
        "response_policy": "FIXED_NOT_FOUND_OR_NOT_ACCESSIBLE",
        "ordinary_trace_shape": ordinary_trace_shape(
            (
                _trace(TraceEventType.RUN_STARTED, offset=1, case_id=case_id),
                TraceEvent(
                    trace_event_id=UUID(int=702),
                    event_type=TraceEventType.RUN_STOPPED,
                    occurred_at=NOW + timedelta(milliseconds=2),
                    run_id=RUN_ID,
                    case_id=case_id,
                    user_outcome=AgentOutcome.NOT_FOUND_OR_NOT_ACCESSIBLE,
                    stop_reason=StopReason.NOT_FOUND_OR_NOT_ACCESSIBLE,
                ),
            )
        ),
        "model_calls": 1,
    }
    values.update(overrides)
    return SafeCaseObservable(**values)


def test_e2e01_04_requires_complete_equal_pair() -> None:
    foreign = _safe_observable("E2E01-04-A")
    nonexistent = _safe_observable("E2E01-04-B")
    assert e2e01_04_safe_observables_match(
        {"E2E01-04-A": foreign, "E2E01-04-B": nonexistent}
    )
    assert not e2e01_04_safe_observables_match({"E2E01-04-A": foreign})


@pytest.mark.parametrize(
    ("field", "different"),
    [
        ("http_status", 404),
        ("user_outcome", AgentOutcome.BLOCKED),
        ("response_policy", "DIFFERENT"),
        ("model_calls", 2),
        ("ordinary_trace_shape", "DIFFERENT_TRACE_SHAPE"),
    ],
)
def test_e2e01_04_rejects_difference_in_each_safe_observable(
    field: str,
    different: object,
) -> None:
    if different == "DIFFERENT_TRACE_SHAPE":
        different = ordinary_trace_shape(
            (_trace(TraceEventType.RUN_STARTED, offset=1),)
        )
    assert not e2e01_04_safe_observables_match(
        {
            "E2E01-04-A": _safe_observable("E2E01-04-A"),
            "E2E01-04-B": _safe_observable(
                "E2E01-04-B",
                **{field: different},
            ),
        }
    )


def test_ordinary_trace_shape_exposes_only_allowlisted_safe_fields() -> None:
    shape = ordinary_trace_shape(_valid_evidence().trace_events)
    assert shape
    assert set(shape[0].model_dump(mode="json")) == {
        "event_type",
        "count",
        "status",
        "reason",
    }
    serialized = repr(tuple(item.model_dump(mode="json") for item in shape))
    for forbidden in (
        str(RUN_ID),
        str(TRACE_REF),
        "customer-A",
        "O-1001",
        "raw_payload",
    ):
        assert forbidden not in serialized


def test_evidence_aggregate_references_existing_records_without_copying_business_dto() -> None:
    evidence = _valid_evidence()
    assert type(evidence.run_record) is AgentRunRecord
    assert type(evidence.agent_result) is AgentRunResult
    assert {
        "customer_id",
        "order_number",
        "raw_payload",
        "rendered_text",
    }.isdisjoint(EvalEvidence.model_fields)
