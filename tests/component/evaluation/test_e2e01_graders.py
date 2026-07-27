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
from mini_agent.core.memory import (
    ContextManifest,
    ObservationVisibility,
    OrderObservation,
    TaskStateRefAndVersion,
    TokenCounts,
    VersionedRecordRef,
)
from mini_agent.core.order import (
    OrderLineSummary,
    OrderStatus,
    OrderSummaryProjection,
)
from mini_agent.core.request_understanding import (
    InputAuthority,
    InputCandidate,
    InputSourceKind,
    NextMove,
    NextMoveKind,
    RequestUnderstandingOutput,
    TaskDeltaCandidate,
    TaskDeltaOperation,
)
from mini_agent.core.task_state import (
    InputBinding,
    InputValidationStatus,
    RequestUnitRecord,
    TaskRecord,
    TaskStatus,
)
from mini_agent.core.tool_system import (
    GateDecision,
    GateDecisionValue,
    ToolCallRecord,
    ToolCallStatus,
    ToolEffect,
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
    EvalCaseExpectations,
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
OTHER_RUN_ID = UUID("00000000-0000-4000-8000-000000000599")
TRACE_REF = UUID("00000000-0000-4000-8000-000000000502")
MESSAGE_REF = UUID("00000000-0000-4000-8000-000000000503")
CANDIDATE_ID = UUID("00000000-0000-4000-8000-000000000504")
BINDING_ID = UUID("00000000-0000-4000-8000-000000000505")
TASK_ID = UUID("00000000-0000-4000-8000-000000000506")
REQUEST_UNIT_ID = UUID("00000000-0000-4000-8000-000000000507")
MODEL_CALL_1 = UUID("00000000-0000-4000-8000-000000000508")
MODEL_CALL_2 = UUID("00000000-0000-4000-8000-000000000509")
CONTEXT_1 = UUID("00000000-0000-4000-8000-000000000510")
CONTEXT_2 = UUID("00000000-0000-4000-8000-000000000511")
GATE_ID = UUID("00000000-0000-4000-8000-000000000512")
TOOL_CALL_ID = UUID("00000000-0000-4000-8000-000000000513")
OBSERVATION_ID = UUID("00000000-0000-4000-8000-000000000514")
NOW = datetime(2026, 7, 27, 8, 0, tzinfo=UTC)
TOOLSET_HASH = f"sha256:{'a' * 64}"

REQUIRED_EVENTS = (
    TraceEventType.RUN_STARTED,
    TraceEventType.CONTEXT_MANIFEST_RECORDED,
    TraceEventType.INPUT_BINDING_RECORDED,
    TraceEventType.GATE_DECISION_RECORDED,
    TraceEventType.TOOL_CALL_CREATED,
    TraceEventType.TOOL_CALL_STARTED,
    TraceEventType.TOOL_CALL_SUCCEEDED,
    TraceEventType.OBSERVATION_RECORDED,
    TraceEventType.RUN_STOPPED,
    TraceEventType.EVAL_CASE_GRADED,
)

LEGACY_ASSERTION_FIELDS = (
    "schema_assertions_pass",
    "identity_boundary_assertions_pass",
    "request_understanding_assertions_pass",
    "input_binding_assertions_pass",
    "task_state_assertions_pass",
    "tool_call_assertions_pass",
    "observation_assertions_pass",
    "disclosure_assertions_pass",
    "renderer_fact_assertions_pass",
    "error_mapping_assertions_pass",
    "persistence_assertions_pass",
    "toolset_replay_assertions_pass",
)


def _expectations(**overrides: object) -> EvalCaseExpectations:
    values: dict[str, object] = {
        "case_id": "E2E01-01",
        "trusted_customer_id": "customer-A",
        "expected_http_status": 200,
        "expected_outcome": AgentOutcome.COMPLETED,
        "expected_run_status": AgentRunStatus.COMPLETED,
        "expected_stop_reason": StopReason.GOAL_COMPLETED,
        "expected_response_policy": "DETERMINISTIC_ORDER_SUMMARY_V1",
        "request_understanding_required": True,
        "expected_binding_order_id": "O-1001",
        "expected_next_move_order_id": "O-1001",
        "expected_requested_tool_name": "get_order",
        "expected_task_status": TaskStatus.COMPLETED,
        "expected_request_unit_status": TaskStatus.COMPLETED,
        "expected_task_state_version": 2,
        "expected_request_unit_state_version": 2,
        "expected_gate_decision": GateDecisionValue.ACCEPT,
        "expected_gate_reason": None,
        "expected_validated_task_state_version": 1,
        "expected_tool_call_status": ToolCallStatus.SUCCEEDED,
        "expected_tool_calls": 1,
        "expected_observations": 1,
        "expected_model_calls": 2,
        "expected_presentation_model_calls": 1,
        "expected_tool_registry_version": "e2e01-thin-tools-v1",
        "required_trace_events": REQUIRED_EVENTS,
        "forbidden_trace_events": (TraceEventType.TOOL_CALL_FAILED,),
        "expected_event_counts": (
            TraceEventCountExpectation(
                event_type=TraceEventType.CONTEXT_MANIFEST_RECORDED,
                count=2,
            ),
            TraceEventCountExpectation(
                event_type=TraceEventType.EVAL_CASE_GRADED,
                count=1,
            ),
        ),
        "applicable_critical_failures": (
            CriticalFailureCode.CF_01,
            CriticalFailureCode.CF_02,
            CriticalFailureCode.CF_04,
            CriticalFailureCode.CF_10,
            CriticalFailureCode.CF_12,
            CriticalFailureCode.CF_13,
            CriticalFailureCode.CF_14,
        ),
    }
    values.update(overrides)
    return EvalCaseExpectations(**values)


def _request_understanding(
    *,
    binding_value: str = "O-1001",
    next_move_value: str = "O-1001",
) -> RequestUnderstandingOutput:
    return RequestUnderstandingOutput(
        message_ref=MESSAGE_REF,
        task_delta_candidates=(
            TaskDeltaCandidate(
                candidate_id=CANDIDATE_ID,
                operation=TaskDeltaOperation.ADD_GOAL,
                goal_patch="查询指定订单状态",
                input_candidates=(
                    InputCandidate(
                        name="order_id",
                        candidate_value=binding_value,
                        semantic_role="TARGET_RESOURCE_IDENTIFIER",
                        authority=InputAuthority.USER_CLAIM,
                        source_kind=InputSourceKind.CURRENT_MESSAGE,
                        source_ref=MESSAGE_REF,
                        source_quote=binding_value,
                        confidence=1.0,
                    ),
                ),
                confidence=1.0,
            ),
        ),
        next_move_candidate=NextMove(
            kind=NextMoveKind.CALL_TOOL,
            requested_tool_name="get_order",
            arguments={"order_id": next_move_value},
            base_task_state_version=None,
        ),
    )


def _observation(*, order_id: str = "O-1001") -> OrderObservation:
    return OrderObservation(
        observation_id=OBSERVATION_ID,
        source_tool="get_order",
        source_resource_ref=order_id,
        source_version="order-v7",
        normalized_type="ORDER_SUMMARY",
        normalized_value=OrderSummaryProjection(
            order_number=order_id,
            status=OrderStatus.SHIPPED,
            line_items=(OrderLineSummary(product_name="轻量跑鞋", quantity=1),),
            ordered_at=datetime(2026, 7, 20, 2, 15, tzinfo=UTC),
            status_updated_at=datetime(2026, 7, 24, 9, 30, tzinfo=UTC),
        ),
        observed_at=NOW,
        recorded_at=NOW,
        visibility=ObservationVisibility.MODEL_VISIBLE,
    )


def _manifest(
    *,
    context_id: UUID,
    model_call_id: UUID,
    toolset_hash: str = TOOLSET_HASH,
    include_observation: bool = False,
) -> ContextManifest:
    return ContextManifest(
        context_manifest_id=context_id,
        run_id=RUN_ID,
        model_call_id=model_call_id,
        tool_registry_version="e2e01-thin-tools-v1",
        model_visible_toolset_hash=toolset_hash,
        selected_message_refs=(MESSAGE_REF,),
        task_state_ref_and_version=TaskStateRefAndVersion(
            task_id=TASK_ID,
            state_version=1,
        ),
        observation_refs_and_versions=(
            (
                VersionedRecordRef(
                    record_ref=OBSERVATION_ID,
                    version="order-v7",
                ),
            )
            if include_observation
            else ()
        ),
        redaction_policy_version="p0-redaction-v1",
        token_counts=TokenCounts(),
        assembled_at=NOW,
    )


def _trace(
    event_type: TraceEventType,
    *,
    offset: int,
    context_index: int | None = None,
    case_id: str = "E2E01-01",
) -> TraceEvent:
    values: dict[str, object] = {
        "trace_event_id": UUID(int=600 + offset),
        "event_type": event_type,
        "occurred_at": NOW + timedelta(milliseconds=offset),
        "run_id": RUN_ID,
        "case_id": case_id,
    }
    if event_type is TraceEventType.CONTEXT_MANIFEST_RECORDED:
        values.update(
            {
                "context_manifest_id": (CONTEXT_1 if context_index == 1 else CONTEXT_2),
                "model_call_id": (MODEL_CALL_1 if context_index == 1 else MODEL_CALL_2),
                "tool_registry_version": "e2e01-thin-tools-v1",
                "model_visible_toolset_hash": TOOLSET_HASH,
            }
        )
    elif event_type is TraceEventType.INPUT_BINDING_RECORDED:
        values["input_binding_ref"] = BINDING_ID
    elif event_type is TraceEventType.GATE_DECISION_RECORDED:
        values["gate_decision"] = GateDecisionValue.ACCEPT
    elif event_type in {
        TraceEventType.TOOL_CALL_CREATED,
        TraceEventType.TOOL_CALL_STARTED,
        TraceEventType.TOOL_CALL_SUCCEEDED,
    }:
        status_by_type = {
            TraceEventType.TOOL_CALL_CREATED: ToolCallStatus.CREATED,
            TraceEventType.TOOL_CALL_STARTED: ToolCallStatus.RUNNING,
            TraceEventType.TOOL_CALL_SUCCEEDED: ToolCallStatus.SUCCEEDED,
        }
        values.update(
            {
                "tool_call_id": TOOL_CALL_ID,
                "tool_call_terminal_status": status_by_type[event_type],
            }
        )
    elif event_type is TraceEventType.OBSERVATION_RECORDED:
        values["observation_ref"] = OBSERVATION_ID
    elif event_type is TraceEventType.RUN_STOPPED:
        values.update(
            {
                "user_outcome": AgentOutcome.COMPLETED,
                "stop_reason": StopReason.GOAL_COMPLETED,
            }
        )
    return TraceEvent(**values)


def _trace_events() -> tuple[TraceEvent, ...]:
    return (
        _trace(TraceEventType.RUN_STARTED, offset=1),
        _trace(
            TraceEventType.CONTEXT_MANIFEST_RECORDED,
            offset=2,
            context_index=1,
        ),
        _trace(TraceEventType.INPUT_BINDING_RECORDED, offset=3),
        _trace(TraceEventType.GATE_DECISION_RECORDED, offset=4),
        _trace(TraceEventType.TOOL_CALL_CREATED, offset=5),
        _trace(TraceEventType.TOOL_CALL_STARTED, offset=6),
        _trace(TraceEventType.TOOL_CALL_SUCCEEDED, offset=7),
        _trace(TraceEventType.OBSERVATION_RECORDED, offset=8),
        _trace(
            TraceEventType.CONTEXT_MANIFEST_RECORDED,
            offset=9,
            context_index=2,
        ),
        _trace(TraceEventType.RUN_STOPPED, offset=10),
        _trace(TraceEventType.EVAL_CASE_GRADED, offset=11),
    )


def _rendered_message(observation: OrderObservation) -> str:
    summary = observation.normalized_value
    return "\n".join(
        (
            "已为你查到订单信息：",
            f"订单号：{summary.order_number}",
            "状态：已发货",
            "商品："
            + "、".join(
                f"{item.product_name} × {item.quantity}" for item in summary.line_items
            ),
            f"下单时间：{summary.ordered_at.strftime('%Y-%m-%d %H:%M UTC')}",
            (
                "状态更新时间："
                f"{summary.status_updated_at.strftime('%Y-%m-%d %H:%M UTC')}"
            ),
            "如需继续查询配送信息，请告诉我。",
        )
    )


def _evidence(**overrides: object) -> EvalEvidence:
    observation = _observation()
    trace_events = _trace_events()
    values: dict[str, object] = {
        "case_id": "E2E01-01",
        "observed_outcome": AgentOutcome.COMPLETED,
        "trace_ref": TRACE_REF,
        "trace_events": trace_events,
        "safe_observable": SafeCaseObservable(
            case_id="E2E01-01",
            http_status=200,
            user_outcome=AgentOutcome.COMPLETED,
            response_policy="DETERMINISTIC_ORDER_SUMMARY_V1",
            ordinary_trace_shape=ordinary_trace_shape(trace_events),
            model_calls=2,
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
            message=_rendered_message(observation),
        ),
        "request_understanding_output": _request_understanding(),
        "input_bindings": (
            InputBinding(
                binding_id=BINDING_ID,
                name="order_id",
                normalized_value="O-1001",
                authority=InputAuthority.USER_CLAIM,
                source_refs=(MESSAGE_REF,),
                validation_status=InputValidationStatus.ACCEPTED,
                confirmed_by_user=True,
                created_at=NOW,
                updated_at=NOW,
            ),
        ),
        "task_records": (
            TaskRecord(
                task_id=TASK_ID,
                owner_customer_id="customer-A",
                status=TaskStatus.COMPLETED,
                state_version=2,
                created_at=NOW,
                updated_at=NOW + timedelta(seconds=1),
            ),
        ),
        "request_units": (
            RequestUnitRecord(
                request_unit_id=REQUEST_UNIT_ID,
                task_id=TASK_ID,
                goal_text="查询指定订单状态",
                goal_source_refs=(MESSAGE_REF,),
                input_binding_refs=(BINDING_ID,),
                observation_refs=(OBSERVATION_ID,),
                status=TaskStatus.COMPLETED,
                state_version=2,
                created_at=NOW,
                updated_at=NOW + timedelta(seconds=1),
            ),
        ),
        "gate_decisions": (
            GateDecision(
                gate_decision_id=GATE_ID,
                model_call_id=MODEL_CALL_1,
                context_manifest_id=CONTEXT_1,
                provider_tool_call_id="provider-call-1",
                requested_provider_tool_name="get_order",
                resolved_canonical_tool_name="get_order",
                snapshot_match=True,
                registration_valid=True,
                schema_valid=True,
                trusted_field_valid=True,
                argument_binding_valid=True,
                argument_binding_refs=(BINDING_ID,),
                budget_valid=True,
                progress_valid=True,
                proposed_base_task_state_version=None,
                validated_task_state_version=1,
                state_version_valid=True,
                action_boundary_valid=True,
                decision=GateDecisionValue.ACCEPT,
                decided_at=NOW,
            ),
        ),
        "tool_calls": (
            ToolCallRecord(
                tool_call_id=TOOL_CALL_ID,
                run_id=RUN_ID,
                task_id=TASK_ID,
                request_unit_id=REQUEST_UNIT_ID,
                model_call_id=MODEL_CALL_1,
                context_manifest_id=CONTEXT_1,
                gate_decision_id=GATE_ID,
                provider_tool_call_id="provider-call-1",
                canonical_tool_name="get_order",
                tool_registry_version="e2e01-thin-tools-v1",
                validated_task_state_version=1,
                argument_binding_refs=(BINDING_ID,),
                effect=ToolEffect.READ,
                attempt_count=1,
                status=ToolCallStatus.SUCCEEDED,
                started_at=NOW,
                finished_at=NOW + timedelta(milliseconds=500),
                result_ref=OBSERVATION_ID,
            ),
        ),
        "observations": (observation,),
        "context_manifests": (
            _manifest(
                context_id=CONTEXT_1,
                model_call_id=MODEL_CALL_1,
            ),
            _manifest(
                context_id=CONTEXT_2,
                model_call_id=MODEL_CALL_2,
                include_observation=True,
            ),
        ),
    }
    values.update({field: True for field in LEGACY_ASSERTION_FIELDS})
    values.update(overrides)
    return EvalEvidence(**values)


def _minimal_self_attested_evidence() -> EvalEvidence:
    events = (
        _trace(TraceEventType.RUN_STARTED, offset=1),
        _trace(TraceEventType.RUN_STOPPED, offset=2),
        _trace(TraceEventType.EVAL_CASE_GRADED, offset=3),
    )
    values: dict[str, object] = {
        "case_id": "E2E01-01",
        "observed_outcome": AgentOutcome.COMPLETED,
        "trace_ref": TRACE_REF,
        "trace_events": events,
        "safe_observable": SafeCaseObservable(
            case_id="E2E01-01",
            http_status=200,
            user_outcome=AgentOutcome.COMPLETED,
            response_policy="DETERMINISTIC_ORDER_SUMMARY_V1",
            ordinary_trace_shape=ordinary_trace_shape(events),
            model_calls=2,
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
            message="SUT claims this is valid",
        ),
    }
    values.update({field: True for field in LEGACY_ASSERTION_FIELDS})
    return EvalEvidence(**values)


def _tampered(grader_name: str) -> EvalEvidence:
    evidence = _evidence()
    if grader_name == "SchemaGrader":
        return _evidence(
            agent_result=AgentRunResult(
                run_id=OTHER_RUN_ID,
                outcome=AgentOutcome.COMPLETED,
                message=evidence.agent_result.message,
            )
        )
    if grader_name == "IdentityBoundaryGrader":
        task = evidence.task_records[0].model_copy(
            update={"owner_customer_id": "customer-B"}
        )
        return _evidence(task_records=(task,))
    if grader_name == "RequestUnderstandingGrader":
        return _evidence(
            request_understanding_output=_request_understanding(
                next_move_value="O-2001"
            )
        )
    if grader_name == "InputBindingGrader":
        binding = evidence.input_bindings[0].model_copy(
            update={"normalized_value": "O-2001"}
        )
        return _evidence(input_bindings=(binding,))
    if grader_name == "TaskStateGrader":
        task = evidence.task_records[0].model_copy(update={"state_version": 3})
        return _evidence(task_records=(task,))
    if grader_name == "ToolCallGrader":
        call = evidence.tool_calls[0].model_copy(
            update={
                "status": ToolCallStatus.FAILED,
                "failure_code": "ORDER_LOOKUP_FAILED",
                "result_ref": None,
            }
        )
        return _evidence(tool_calls=(call,))
    if grader_name == "ObservationGrader":
        return _evidence(observations=(_observation(order_id="O-2001"),))
    if grader_name == "DisclosureGrader":
        observable = evidence.safe_observable.model_copy(
            update={"response_policy": "FIXED_SAFE_PROCESSING_ERROR"}
        )
        return _evidence(safe_observable=observable)
    if grader_name == "RendererFactGrader":
        return _evidence(
            agent_result=AgentRunResult(
                run_id=RUN_ID,
                outcome=AgentOutcome.COMPLETED,
                message="O-1001",
            )
        )
    if grader_name == "ErrorMappingGrader":
        run = evidence.run_record.model_copy(
            update={
                "stop_reason": StopReason.NOT_FOUND_OR_NOT_ACCESSIBLE,
            }
        )
        return _evidence(run_record=run)
    if grader_name == "TraceCompletenessGrader":
        return _evidence(
            trace_events=tuple(
                event
                for event in evidence.trace_events
                if event.event_type is not TraceEventType.EVAL_CASE_GRADED
            )
        )
    if grader_name == "PersistenceGrader":
        unit = evidence.request_units[0].model_copy(update={"task_id": UUID(int=999)})
        return _evidence(request_units=(unit,))
    if grader_name == "ToolsetReplayGrader":
        manifest = _manifest(
            context_id=CONTEXT_2,
            model_call_id=MODEL_CALL_2,
            toolset_hash=f"sha256:{'b' * 64}",
            include_observation=True,
        )
        return _evidence(context_manifests=(evidence.context_manifests[0], manifest))
    raise AssertionError(f"unhandled grader {grader_name}")


def test_registry_membership_is_exactly_the_13_artifact_names() -> None:
    registry = grader_registry()
    assert tuple(registry) == GRADER_NAMES
    assert len(registry) == 13
    assert all(registry[name].name == name for name in GRADER_NAMES)


def test_boolean_self_attestation_cannot_replace_typed_evidence() -> None:
    outcome = grade_evidence(
        GRADER_NAMES,
        _minimal_self_attested_evidence(),
        _expectations(),
    )

    assert outcome.status is EvalResultStatus.FAIL
    assert any(
        result.reason_code is EvalGraderReasonCode.MISSING_RECORD
        for result in outcome.grader_results
    )
    assert CriticalFailureCode.CF_14 in outcome.critical_failures


@pytest.mark.parametrize("grader_name", GRADER_NAMES)
def test_every_registered_grader_passes_valid_typed_evidence(
    grader_name: str,
) -> None:
    result = grader_registry()[grader_name].grade(
        _evidence(),
        _expectations(),
    )
    assert result == EvalGraderResult(
        grader_name=grader_name,
        status=EvalGraderStatus.PASS,
    )


@pytest.mark.parametrize("grader_name", GRADER_NAMES)
def test_each_grader_rejects_directed_typed_evidence_tamper(
    grader_name: str,
) -> None:
    result = grader_registry()[grader_name].grade(
        _tampered(grader_name),
        _expectations(),
    )
    assert result.status is EvalGraderStatus.FAIL
    assert result.reason_code in {
        EvalGraderReasonCode.MISSING_RECORD,
        EvalGraderReasonCode.ASSERTION_FAILED,
        EvalGraderReasonCode.TRACE_EVENT_MISSING,
    }


@pytest.mark.parametrize(
    "gate_update",
    [
        {"argument_binding_refs": (UUID(int=901),)},
        {"validated_task_state_version": 999},
        {"context_manifest_id": UUID(int=902)},
    ],
)
def test_tool_call_grader_closes_gate_and_tool_call_graph(
    gate_update: dict[str, object],
) -> None:
    evidence = _evidence()
    gate = evidence.gate_decisions[0].model_copy(update=gate_update)

    result = grader_registry()["ToolCallGrader"].grade(
        _evidence(gate_decisions=(gate,)),
        _expectations(),
    )

    assert result.status is EvalGraderStatus.FAIL
    assert result.reason_code is EvalGraderReasonCode.ASSERTION_FAILED


def test_renderer_fact_grader_rejects_any_extra_unapproved_fact() -> None:
    evidence = _evidence()
    assert evidence.agent_result is not None
    result = grader_registry()["RendererFactGrader"].grade(
        _evidence(
            agent_result=evidence.agent_result.model_copy(
                update={
                    "message": (
                        f"{evidence.agent_result.message}\n"
                        "另一个订单 O-2001，商品：未授权商品，"
                        "地址：他人私有地址"
                    )
                }
            )
        ),
        _expectations(),
    )

    assert result.status is EvalGraderStatus.FAIL
    assert result.reason_code is EvalGraderReasonCode.ASSERTION_FAILED


def test_trace_grader_rejects_tampered_task_state_top_level_refs() -> None:
    tampered_task_event = TraceEvent(
        trace_event_id=UUID(int=903),
        event_type=TraceEventType.TASK_STATE_CHANGED,
        occurred_at=NOW + timedelta(microseconds=9500),
        run_id=RUN_ID,
        case_id="E2E01-01",
        task_id=UUID(int=904),
        request_unit_id=UUID(int=905),
    )
    events = tuple(
        sorted(
            (*_trace_events(), tampered_task_event),
            key=lambda event: event.occurred_at,
        )
    )

    result = grader_registry()["TraceCompletenessGrader"].grade(
        _evidence(trace_events=events),
        _expectations(),
    )

    assert result.status is EvalGraderStatus.FAIL
    assert result.reason_code is EvalGraderReasonCode.ASSERTION_FAILED


@pytest.mark.parametrize(
    ("grader_name", "field_name"),
    [
        ("InputBindingGrader", "input_bindings"),
        ("TaskStateGrader", "task_records"),
        ("TaskStateGrader", "request_units"),
        ("ToolCallGrader", "gate_decisions"),
    ],
)
def test_extra_typed_record_is_mismatch_not_missing(
    grader_name: str,
    field_name: str,
) -> None:
    evidence = _evidence()
    records = getattr(evidence, field_name)
    identity_field = {
        "input_bindings": "binding_id",
        "task_records": "task_id",
        "request_units": "request_unit_id",
        "gate_decisions": "gate_decision_id",
    }[field_name]
    extra = records[0].model_copy(
        update={identity_field: UUID(int=910 + len(field_name))}
    )

    result = grader_registry()[grader_name].grade(
        _evidence(**{field_name: (*records, extra)}),
        _expectations(),
    )

    assert result.status is EvalGraderStatus.FAIL
    assert result.reason_code is EvalGraderReasonCode.ASSERTION_FAILED


def test_missing_applicable_observation_uses_stable_missing_record_reason() -> None:
    result = grader_registry()["ObservationGrader"].grade(
        _evidence(observations=()),
        _expectations(),
    )
    assert result.status is EvalGraderStatus.FAIL
    assert result.reason_code is EvalGraderReasonCode.MISSING_RECORD


def test_trace_expectations_are_external_to_sut_evidence() -> None:
    evidence = _evidence(
        trace_events=tuple(
            event
            for event in _trace_events()
            if event.event_type is not TraceEventType.OBSERVATION_RECORDED
        )
    )
    result = grader_registry()["TraceCompletenessGrader"].grade(
        evidence,
        _expectations(),
    )
    assert result.status is EvalGraderStatus.FAIL
    assert result.reason_code is EvalGraderReasonCode.TRACE_EVENT_MISSING
    assert {
        "required_trace_events",
        "forbidden_trace_events",
        "expected_event_counts",
        "critical_failures",
    }.isdisjoint(EvalEvidence.model_fields)


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
        grade_evidence(configured, _evidence(), _expectations())


def test_critical_failures_are_derived_from_typed_grader_failures() -> None:
    expectations = _expectations(
        applicable_critical_failures=(CriticalFailureCode.CF_14,)
    )
    outcome = grade_evidence(
        ("InputBindingGrader",),
        _tampered("InputBindingGrader"),
        expectations,
    )
    assert outcome.status is EvalResultStatus.FAIL
    assert outcome.critical_failures == (CriticalFailureCode.CF_14,)

    passing = (
        EvalGraderResult(
            grader_name="SchemaGrader",
            status=EvalGraderStatus.PASS,
        ),
    )
    assert (
        determine_result_status(passing, (CriticalFailureCode.CF_14,))
        is EvalResultStatus.FAIL
    )


def _safe_observable(
    case_id: str,
    **overrides: object,
) -> SafeCaseObservable:
    trace_events = (
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
    values: dict[str, object] = {
        "case_id": case_id,
        "http_status": 200,
        "user_outcome": AgentOutcome.NOT_FOUND_OR_NOT_ACCESSIBLE,
        "response_policy": "FIXED_NOT_FOUND_OR_NOT_ACCESSIBLE",
        "ordinary_trace_shape": ordinary_trace_shape(trace_events),
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
    shape = ordinary_trace_shape(_evidence().trace_events)
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


def test_evidence_aggregate_references_existing_records_without_copying_business_dto() -> (
    None
):
    evidence = _evidence()
    assert type(evidence.run_record) is AgentRunRecord
    assert type(evidence.agent_result) is AgentRunResult
    assert {
        "customer_id",
        "order_number",
        "raw_payload",
        "rendered_text",
    }.isdisjoint(EvalEvidence.model_fields)
