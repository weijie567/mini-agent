from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from mini_agent.application.persistence import (
    P0PersistenceIntegrityCategory,
    P0PersistenceIntegrityError,
    P0RecordCode,
    encode_persistence_record,
    encode_persistence_record_versioned,
)
from mini_agent.core.tool_system import ToolCallStatus
from mini_agent.core.trace import (
    AgentOutcome,
    AgentRunRecord,
    AgentRunRecordV2,
    AgentRunStatus,
    AgentRunStatusV2,
    StopReason,
    StopReasonV2,
    TraceEvent,
    TraceEventType,
    TraceEventV2,
)

NOW = datetime(2030, 1, 1, tzinfo=UTC)

V1_RUN_STATUSES = {
    "CREATED",
    "RUNNING",
    "COMPLETED",
    "FAILED",
    "INCOMPLETE",
}
V1_STOP_REASONS = {
    "GOAL_COMPLETED",
    "NOT_FOUND_OR_NOT_ACCESSIBLE",
    "INPUT_INVALID",
    "GATE_REJECTED",
    "PROVIDER_PROTOCOL_ERROR",
    "ORDER_SERVICE_UNAVAILABLE",
    "PRESENTATION_PLAN_REJECTED",
    "RENDERER_INVARIANT_FAILED",
    "PROCESS_RESTART_DETECTED",
}
V2_STOP_REASONS = V1_STOP_REASONS | {
    "CLARIFICATION_REQUIRED",
    "CANDIDATE_CLARIFICATION_REQUIRED",
    "CANDIDATE_REFRESH_REQUIRED",
    "CLAIM_TARGET_CLARIFICATION_REQUIRED",
    "ORDER_SEARCH_UNAVAILABLE",
    "SHIPMENT_SERVICE_UNAVAILABLE",
    "DEPENDENCY_RETRY_EXHAUSTED",
    "DEPENDENCY_EXECUTION_INTERRUPTED",
    "INTEGRITY_CHECK_FAILED",
    "SHIPMENT_SNAPSHOT_STALE",
    "SHIPMENT_DATA_UNAVAILABLE",
    "STATE_OR_BINDING_INVALIDATED",
}
TRACE_FIELDS = {
    "trace_event_id",
    "event_type",
    "occurred_at",
    "run_id",
    "case_id",
    "message_ref",
    "accepted_delta_ref",
    "task_id",
    "request_unit_id",
    "input_binding_ref",
    "model_call_id",
    "model_call_purpose",
    "context_manifest_id",
    "provider_name",
    "model_snapshot",
    "tool_registry_version",
    "model_visible_toolset_hash",
    "next_move_kind",
    "requested_tool_name",
    "proposed_base_task_state_version",
    "validated_task_state_version",
    "argument_binding_refs",
    "gate_decision",
    "gate_reason_code",
    "tool_call_id",
    "tool_call_terminal_status",
    "safe_tool_outcome",
    "observation_ref",
    "presentation_plan_ref",
    "user_outcome",
    "stop_reason",
    "timing_and_usage_summary",
}
FORBIDDEN_TRACE_FIELDS = {
    "payload",
    "owner_scope",
    "owner_customer_id",
    "customer_id",
    "session_id",
    "source_version",
    "source_version_token",
    "candidate_summary",
    "raw_token",
    "prompt",
    "stack",
}


def _v2_run(**updates: object) -> AgentRunRecordV2:
    values: dict[str, object] = {
        "run_id": uuid4(),
        "status": AgentRunStatusV2.RUNNING,
        "provider_lane": "offline",
        "started_at": NOW,
    }
    values.update(updates)
    return AgentRunRecordV2.model_validate(values)


def _v2_trace_payload(**updates: object) -> dict[str, object]:
    values: dict[str, object] = {
        "trace_event_id": uuid4(),
        "event_type": TraceEventType.MESSAGE_ACCEPTED,
        "occurred_at": NOW,
        "run_id": uuid4(),
    }
    values.update(updates)
    return values


def test_v2_vocabulary_is_separate_and_exact() -> None:
    assert {status.value for status in AgentRunStatus} == V1_RUN_STATUSES
    assert {status.value for status in AgentRunStatusV2} == V1_RUN_STATUSES | {
        "SUPERSEDED"
    }
    assert "CANCELLED" not in AgentRunStatusV2.__members__
    assert {reason.value for reason in StopReason} == V1_STOP_REASONS
    assert {reason.value for reason in StopReasonV2} == V2_STOP_REASONS

    assert AgentRunStatusV2 is not AgentRunStatus
    assert StopReasonV2 is not StopReason


@pytest.mark.parametrize(
    "terminal_fields",
    [
        pytest.param({}, id="created"),
        pytest.param({"status": AgentRunStatusV2.RUNNING}, id="running"),
        pytest.param(
            {
                "status": AgentRunStatusV2.COMPLETED,
                "completed_at": NOW,
                "stop_reason": StopReasonV2.GOAL_COMPLETED,
            },
            id="completed",
        ),
        pytest.param(
            {
                "status": AgentRunStatusV2.FAILED,
                "completed_at": NOW,
            },
            id="failed",
        ),
        pytest.param(
            {
                "status": AgentRunStatusV2.INCOMPLETE,
                "completed_at": NOW,
                "stop_reason": StopReasonV2.PROCESS_RESTART_DETECTED,
                "incomplete_reason": "process restart recovery",
            },
            id="incomplete",
        ),
        pytest.param(
            {
                "status": AgentRunStatusV2.SUPERSEDED,
                "completed_at": NOW,
                "stop_reason": StopReasonV2.STATE_OR_BINDING_INVALIDATED,
            },
            id="superseded",
        ),
    ],
)
def test_v2_run_accepts_only_valid_active_and_terminal_shapes(
    terminal_fields: dict[str, object],
) -> None:
    status = terminal_fields.get("status", AgentRunStatusV2.CREATED)
    run = _v2_run(
        status=status,
        **{
            key: value
            for key, value in terminal_fields.items()
            if key != "status"
        },
    )

    assert run.status is status
    if status is AgentRunStatusV2.SUPERSEDED:
        assert run.completed_at == NOW
        assert run.stop_reason is StopReasonV2.STATE_OR_BINDING_INVALIDATED
        assert run.incomplete_reason is None


@pytest.mark.parametrize(
    "invalid_fields",
    [
        pytest.param({"completed_at": NOW}, id="active-completed-at"),
        pytest.param(
            {"stop_reason": StopReasonV2.GOAL_COMPLETED},
            id="active-stop-reason",
        ),
        pytest.param(
            {"incomplete_reason": "terminal-only"},
            id="active-incomplete-reason",
        ),
        pytest.param(
            {"status": AgentRunStatusV2.COMPLETED},
            id="completed-missing-completed-at",
        ),
        pytest.param(
            {"status": AgentRunStatusV2.COMPLETED, "completed_at": NOW},
            id="completed-missing-stop-reason",
        ),
        pytest.param(
            {
                "status": AgentRunStatusV2.COMPLETED,
                "completed_at": NOW,
                "stop_reason": StopReasonV2.PROCESS_RESTART_DETECTED,
            },
            id="completed-restart-reason",
        ),
        pytest.param(
            {
                "status": AgentRunStatusV2.COMPLETED,
                "completed_at": NOW,
                "stop_reason": StopReasonV2.STATE_OR_BINDING_INVALIDATED,
            },
            id="completed-invalidation-reason",
        ),
        pytest.param(
            {
                "status": AgentRunStatusV2.FAILED,
                "completed_at": NOW,
                "stop_reason": StopReasonV2.INTEGRITY_CHECK_FAILED,
            },
            id="failed-with-stop-reason",
        ),
        pytest.param(
            {
                "status": AgentRunStatusV2.FAILED,
                "completed_at": NOW,
                "incomplete_reason": "not incomplete",
            },
            id="failed-with-incomplete-reason",
        ),
        pytest.param(
            {
                "status": AgentRunStatusV2.INCOMPLETE,
                "completed_at": NOW,
            },
            id="incomplete-missing-reason",
        ),
        pytest.param(
            {
                "status": AgentRunStatusV2.INCOMPLETE,
                "completed_at": NOW,
                "stop_reason": StopReasonV2.STATE_OR_BINDING_INVALIDATED,
            },
            id="incomplete-invalidation-reason",
        ),
        pytest.param(
            {
                "status": AgentRunStatusV2.SUPERSEDED,
                "completed_at": NOW,
            },
            id="superseded-missing-reason",
        ),
        pytest.param(
            {
                "status": AgentRunStatusV2.SUPERSEDED,
                "completed_at": NOW,
                "stop_reason": StopReasonV2.PROCESS_RESTART_DETECTED,
            },
            id="superseded-restart-reason",
        ),
        pytest.param(
            {
                "status": AgentRunStatusV2.SUPERSEDED,
                "completed_at": NOW,
                "stop_reason": StopReasonV2.STATE_OR_BINDING_INVALIDATED,
                "incomplete_reason": "must remain null",
            },
            id="superseded-incomplete-reason",
        ),
        pytest.param(
            {
                "status": AgentRunStatusV2.SUPERSEDED,
                "completed_at": NOW - timedelta(microseconds=1),
                "stop_reason": StopReasonV2.STATE_OR_BINDING_INVALIDATED,
            },
            id="terminal-time-precedes-start",
        ),
    ],
)
def test_v2_run_rejects_every_open_matrix_shape(
    invalid_fields: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        _v2_run(**invalid_fields)


@pytest.mark.parametrize(
    "status",
    [
        AgentRunStatusV2.CREATED,
        AgentRunStatusV2.RUNNING,
    ],
)
@pytest.mark.parametrize(
    "terminal_field",
    [
        {"completed_at": NOW},
        {"stop_reason": StopReasonV2.GOAL_COMPLETED},
        {"incomplete_reason": "terminal-only"},
    ],
)
def test_each_v2_active_status_rejects_each_terminal_field(
    status: AgentRunStatusV2,
    terminal_field: dict[str, object],
) -> None:
    with pytest.raises(ValidationError, match="active v2 Run"):
        _v2_run(status=status, **terminal_field)


@pytest.mark.parametrize(
    ("status", "valid_reason"),
    [
        (AgentRunStatusV2.COMPLETED, StopReasonV2.GOAL_COMPLETED),
        (AgentRunStatusV2.FAILED, None),
        (
            AgentRunStatusV2.INCOMPLETE,
            StopReasonV2.PROCESS_RESTART_DETECTED,
        ),
        (
            AgentRunStatusV2.SUPERSEDED,
            StopReasonV2.STATE_OR_BINDING_INVALIDATED,
        ),
    ],
)
def test_each_v2_terminal_status_requires_completed_at(
    status: AgentRunStatusV2,
    valid_reason: StopReasonV2 | None,
) -> None:
    with pytest.raises(ValidationError, match="requires completed_at"):
        _v2_run(status=status, stop_reason=valid_reason)


@pytest.mark.parametrize(
    "status",
    [
        AgentRunStatusV2.COMPLETED,
        AgentRunStatusV2.FAILED,
        AgentRunStatusV2.INCOMPLETE,
        AgentRunStatusV2.SUPERSEDED,
    ],
)
@pytest.mark.parametrize("reason", [None, *StopReasonV2])
def test_v2_terminal_status_and_stop_reason_matrix_is_closed(
    status: AgentRunStatusV2,
    reason: StopReasonV2 | None,
) -> None:
    valid = (
        (
            status is AgentRunStatusV2.COMPLETED
            and reason
            not in {
                None,
                StopReasonV2.PROCESS_RESTART_DETECTED,
                StopReasonV2.STATE_OR_BINDING_INVALIDATED,
            }
        )
        or (status is AgentRunStatusV2.FAILED and reason is None)
        or (
            status is AgentRunStatusV2.INCOMPLETE
            and reason is StopReasonV2.PROCESS_RESTART_DETECTED
        )
        or (
            status is AgentRunStatusV2.SUPERSEDED
            and reason is StopReasonV2.STATE_OR_BINDING_INVALIDATED
        )
    )

    if valid:
        run = _v2_run(
            status=status,
            completed_at=NOW,
            stop_reason=reason,
        )
        assert run.stop_reason is reason
    else:
        with pytest.raises(ValidationError):
            _v2_run(
                status=status,
                completed_at=NOW,
                stop_reason=reason,
            )


def test_v1_models_continue_to_reject_v2_only_values() -> None:
    with pytest.raises(ValueError):
        AgentRunStatus("SUPERSEDED")
    with pytest.raises(ValueError):
        StopReason("STATE_OR_BINDING_INVALIDATED")

    with pytest.raises(ValidationError):
        AgentRunRecord.model_validate(
            {
                "run_id": uuid4(),
                "status": "SUPERSEDED",
                "provider_lane": "offline",
                "started_at": NOW,
                "completed_at": NOW,
                "stop_reason": "STATE_OR_BINDING_INVALIDATED",
            }
        )
    with pytest.raises(ValidationError):
        TraceEvent.model_validate(
            _v2_trace_payload(
                event_type=TraceEventType.RUN_STOPPED,
                user_outcome=AgentOutcome.BLOCKED,
                stop_reason="STATE_OR_BINDING_INVALIDATED",
            )
        )


def test_v1_phase1_run_matrix_remains_usable() -> None:
    active = AgentRunRecord(
        run_id=uuid4(),
        status=AgentRunStatus.RUNNING,
        provider_lane="offline",
        started_at=NOW,
    )
    complete = AgentRunRecord(
        run_id=uuid4(),
        status=AgentRunStatus.COMPLETED,
        provider_lane="offline",
        started_at=NOW,
        completed_at=NOW,
        stop_reason=StopReason.GOAL_COMPLETED,
    )
    incomplete = AgentRunRecord(
        run_id=uuid4(),
        status=AgentRunStatus.INCOMPLETE,
        provider_lane="offline",
        started_at=NOW,
        completed_at=NOW,
        stop_reason=StopReason.PROCESS_RESTART_DETECTED,
    )

    assert active.status is AgentRunStatus.RUNNING
    assert complete.stop_reason is StopReason.GOAL_COMPLETED
    assert incomplete.stop_reason is StopReason.PROCESS_RESTART_DETECTED


def test_v1_and_v2_trace_fields_equal_the_exact_shared_whitelist() -> None:
    assert set(TraceEvent.model_fields) == TRACE_FIELDS
    assert set(TraceEventV2.model_fields) == TRACE_FIELDS
    assert not TRACE_FIELDS.intersection(FORBIDDEN_TRACE_FIELDS)


@pytest.mark.parametrize("trace_model", [TraceEvent, TraceEventV2])
@pytest.mark.parametrize("forbidden_field", sorted(FORBIDDEN_TRACE_FIELDS))
def test_trace_generations_reject_forbidden_disclosure_fields(
    trace_model: type[TraceEvent] | type[TraceEventV2],
    forbidden_field: str,
) -> None:
    with pytest.raises(ValidationError, match="extra"):
        trace_model.model_validate(
            {
                **_v2_trace_payload(),
                forbidden_field: "must-not-enter-ordinary-trace",
            }
        )


def test_v2_run_stopped_accepts_only_exact_invalidation_audit_pair() -> None:
    trace = TraceEventV2.model_validate(
        _v2_trace_payload(
            event_type=TraceEventType.RUN_STOPPED,
            user_outcome=AgentOutcome.BLOCKED,
            stop_reason=StopReasonV2.STATE_OR_BINDING_INVALIDATED,
        )
    )

    assert trace.user_outcome is AgentOutcome.BLOCKED
    assert trace.stop_reason is StopReasonV2.STATE_OR_BINDING_INVALIDATED

    for updates in (
        {"stop_reason": StopReasonV2.STATE_OR_BINDING_INVALIDATED},
        {"user_outcome": AgentOutcome.BLOCKED},
        {
            "user_outcome": AgentOutcome.COMPLETED,
            "stop_reason": StopReasonV2.STATE_OR_BINDING_INVALIDATED,
        },
        {
            "user_outcome": AgentOutcome.BLOCKED,
            "stop_reason": "UNKNOWN_INVALIDATION_REASON",
        },
    ):
        with pytest.raises(ValidationError):
            TraceEventV2.model_validate(
                _v2_trace_payload(
                    event_type=TraceEventType.RUN_STOPPED,
                    **updates,
                )
            )


def test_v2_trace_preserves_phase1_tool_lifecycle_validation() -> None:
    tool_call_id = uuid4()
    trace = TraceEventV2.model_validate(
        _v2_trace_payload(
            event_type=TraceEventType.TOOL_CALL_STARTED,
            tool_call_id=tool_call_id,
            tool_call_terminal_status=ToolCallStatus.RUNNING,
        )
    )
    assert trace.tool_call_id == tool_call_id

    with pytest.raises(ValidationError, match="event and status must match"):
        TraceEventV2.model_validate(
            _v2_trace_payload(
                event_type=TraceEventType.TOOL_CALL_STARTED,
                tool_call_id=tool_call_id,
                tool_call_terminal_status=ToolCallStatus.SUCCEEDED,
            )
        )


def test_active_v1_persistence_encoders_reject_v2_source_models() -> None:
    v2_records = (
        (
            P0RecordCode.AGENT_RUN_RECORD,
            _v2_run(
                status=AgentRunStatusV2.SUPERSEDED,
                completed_at=NOW,
                stop_reason=StopReasonV2.STATE_OR_BINDING_INVALIDATED,
            ),
        ),
        (
            P0RecordCode.TRACE_EVENT_RECORD,
            TraceEventV2.model_validate(
                _v2_trace_payload(
                    event_type=TraceEventType.RUN_STOPPED,
                    user_outcome=AgentOutcome.BLOCKED,
                    stop_reason=StopReasonV2.STATE_OR_BINDING_INVALIDATED,
                )
            ),
        ),
    )

    for record_code, record in v2_records:
        for encode in (
            lambda: encode_persistence_record(record_code, record),
            lambda: encode_persistence_record_versioned(
                record_code,
                f"{record_code.value}.p0.v1",
                record,
            ),
        ):
            with pytest.raises(P0PersistenceIntegrityError) as error:
                encode()
            assert (
                error.value.category
                is P0PersistenceIntegrityCategory.SOURCE_MODEL_MISMATCH
            )


def test_active_v1_persistence_bindings_still_emit_only_v1_envelopes() -> None:
    run_envelope = encode_persistence_record(
        P0RecordCode.AGENT_RUN_RECORD,
        AgentRunRecord(
            run_id=uuid4(),
            status=AgentRunStatus.RUNNING,
            provider_lane="offline",
            started_at=NOW,
        ),
    )
    trace_envelope = encode_persistence_record(
        P0RecordCode.TRACE_EVENT_RECORD,
        TraceEvent.model_validate(_v2_trace_payload()),
    )

    assert run_envelope.record_schema_version == "agent_run_record.p0.v1"
    assert trace_envelope.record_schema_version == "trace_event_record.p0.v1"
