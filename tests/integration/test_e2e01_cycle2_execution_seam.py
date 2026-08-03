from __future__ import annotations

import json
from datetime import datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import event, select

from mini_agent.application.persistence import (
    P0PersistenceIntegrityCategory,
    P0PersistenceIntegrityError,
    P0PersistenceEnvelope,
    P0RecordCode,
    P0RecordReference,
)
from mini_agent.application.records import (
    AgentRunResult,
    Cycle2ControlPurpose,
    Cycle2ExactRunEvidenceClosure,
    MessageDirection,
    MessageRecord,
    RunTaskLinkRecordV2,
)
from mini_agent.bootstrap import Cycle2OfflineComposition
from mini_agent.core.request_understanding import (
    Cycle2ControlCandidate,
    Cycle2ControlCandidateKind,
    Cycle2ContinuationRequestUnderstandingOutputV2,
    Cycle2ContinuationTaskDeltaCandidateV2,
    Cycle2InitialRequestUnderstandingOutputV2,
    Cycle2InitialTaskDeltaCandidateV2,
    Cycle2InputCandidate,
    ModelVisibleTaskSummary,
    NextMove,
    NextMoveKind,
    QueryContextualizationCandidateV2,
    RequestUnderstandingInput,
)
from mini_agent.core.task_state import (
    InputBindingV2,
    TaskDeltaOperation,
    TaskStateTransition,
    TaskStatus,
)
from mini_agent.core.tool_system import (
    Cycle2ToolName,
    ToolCallRecordV2,
    ToolCallStatus,
    ToolResultOutcome,
    ToolRetryDecision,
    build_cycle2_registry_snapshot,
)
from mini_agent.core.trace import (
    AgentOutcome,
    AgentRunRecordV2,
    AgentRunStatusV2,
    StopReasonV2,
    TraceEventType,
    TraceEventV2,
)
from mini_agent.infrastructure.cycle2_fixture_seed import (
    TRUSTED_CLOCK,
    ResolvedCycle2SeedPlan,
    resolve_cycle2_seed_plan,
)
from mini_agent.infrastructure.persistence.database import build_session_factory
from mini_agent.infrastructure.persistence.models import (
    MockOrderModel,
    MockOrderSearchDocumentModel,
    MockShipmentModel,
    P0RecordModel,
)
from mini_agent.infrastructure.persistence.postgres import PostgresRecordAdapter


pytestmark = pytest.mark.anyio


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


class _MonotonicClock:
    def __init__(self, start: datetime = TRUSTED_CLOCK) -> None:
        self._next = start

    def __call__(self) -> datetime:
        value = self._next
        self._next += timedelta(microseconds=1)
        return value


class _Cycle2DirectProvider:
    def __init__(
        self,
        *,
        product_description: str,
        include_shipment: bool = False,
    ) -> None:
        self._product_description = product_description
        self._include_shipment = include_shipment

    async def propose_cycle2_initial(
        self,
        request,
    ) -> Cycle2InitialRequestUnderstandingOutputV2:
        return Cycle2InitialRequestUnderstandingOutputV2(
            schema_version="e2e01-cycle2-initial.p0.v1",
            message_ref=request.message_ref,
            contextualization=QueryContextualizationCandidateV2(
                text=f"查找最近购买的{self._product_description}订单",
                resolved_reference_candidates=(),
                uncertainties=(),
                source_message_refs=(request.message_ref,),
            ),
            task_delta_candidates=(
                Cycle2InitialTaskDeltaCandidateV2(
                    candidate_id=uuid4(),
                    operation=TaskDeltaOperation.ADD_GOAL,
                    goal_patch=f"查找最近购买的{self._product_description}订单",
                    input_candidates=(
                        Cycle2InputCandidate(
                            name="product_description",
                            candidate_value=self._product_description,
                            source_ref=request.message_ref,
                            source_quote=self._product_description,
                            confidence=0.99,
                        ),
                    ),
                    confidence=0.99,
                ),
            ),
            next_move_candidate=NextMove(
                kind=NextMoveKind.CALL_TOOL,
                requested_tool_name="search_orders",
                arguments={"product_description": self._product_description},
                base_task_state_version=None,
            ),
        )

    async def propose_cycle2_continuation(
        self,
        request,
    ) -> Cycle2InputCandidate:
        return Cycle2InputCandidate(
            name="candidate_ordinal",
            candidate_value=2,
            source_ref=request.message_ref,
            source_quote=request.original_query,
            confidence=0.99,
        )

    async def propose_cycle2_continuation_v3(
        self,
        request,
    ) -> Cycle2ContinuationRequestUnderstandingOutputV2:
        return Cycle2ContinuationRequestUnderstandingOutputV2(
            schema_version="e2e01-cycle2-continuation.p0.v2",
            message_ref=request.message_ref,
            contextualization=QueryContextualizationCandidateV2(
                text="选择当前订单候选",
                resolved_reference_candidates=(),
                uncertainties=(),
                source_message_refs=(request.message_ref,),
            ),
            task_delta_candidates=(
                Cycle2ContinuationTaskDeltaCandidateV2(
                    candidate_id=uuid4(),
                    operation=TaskDeltaOperation.SUPPLY_INPUT,
                    target_task_alias="current-task",
                    target_request_unit_alias="current-request",
                    input_candidates=(
                        Cycle2InputCandidate(
                            name="candidate_ordinal",
                            candidate_value=2,
                            source_ref=request.message_ref,
                            source_quote="第二",
                            confidence=0.99,
                        ),
                    ),
                    confidence=0.99,
                ),
            ),
        )

    async def propose_cycle2_control(
        self,
        _request,
        purpose: Cycle2ControlPurpose,
    ) -> Cycle2ControlCandidate:
        if purpose is Cycle2ControlPurpose.PROPOSE_GET_ORDER:
            return Cycle2ControlCandidate(
                kind=Cycle2ControlCandidateKind.CALL_TOOL,
                requested_tool_name="get_order",
            )
        if (
            purpose is Cycle2ControlPurpose.PROPOSE_POST_ORDER
            and self._include_shipment
        ):
            return Cycle2ControlCandidate(
                kind=Cycle2ControlCandidateKind.CALL_TOOL,
                requested_tool_name="get_shipment",
            )
        return Cycle2ControlCandidate(
            kind=Cycle2ControlCandidateKind.FINISH,
        )


async def test_direct_provider_v3_continuation_is_exact_frozen_envelope() -> None:
    snapshot = build_cycle2_registry_snapshot()
    run_id = uuid4()
    message_ref = uuid4()
    focused = ModelVisibleTaskSummary(
        task_alias="current-task",
        request_unit_alias="current-request",
        goal_summary="查找最近购买的跑鞋订单",
        status=TaskStatus.WAITING_USER.value,
        open_questions=("请选择订单候选",),
    )
    request = RequestUnderstandingInput(
        run_id=run_id,
        message_ref=message_ref,
        original_query="第二个",
        active_task_summaries=(focused,),
        focused_task_summary=focused,
        provider_visible_tool_specs=snapshot.provider_visible_toolset,
        model_visible_toolset_hash=snapshot.model_visible_toolset_hash,
    )

    output = await _Cycle2DirectProvider(
        product_description="跑鞋"
    ).propose_cycle2_continuation_v3(request)
    assert (
        Cycle2ContinuationRequestUnderstandingOutputV2.model_validate(
            output.model_dump(mode="python"),
            strict=True,
        )
        == output
    )
    assert output.schema_version == "e2e01-cycle2-continuation.p0.v2"
    assert output.message_ref == message_ref
    assert output.contextualization.text == "选择当前订单候选"
    assert output.contextualization.resolved_reference_candidates == ()
    assert output.contextualization.uncertainties == ()
    assert output.contextualization.source_message_refs == (message_ref,)
    assert len(output.task_delta_candidates) == 1
    delta = output.task_delta_candidates[0]
    assert delta.candidate_id not in {run_id, message_ref}
    assert delta.operation is TaskDeltaOperation.SUPPLY_INPUT
    assert delta.target_task_alias == focused.task_alias
    assert delta.target_request_unit_alias == focused.request_unit_alias
    assert delta.confidence == 0.99
    assert len(delta.input_candidates) == 1
    candidate = delta.input_candidates[0]
    assert candidate.name == "candidate_ordinal"
    assert candidate.candidate_value == 2
    assert candidate.source_ref == message_ref
    assert candidate.source_quote == "第二"
    assert candidate.confidence == 0.99


async def _post(app, message: str) -> AgentRunResult:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        cookies={"p0_session": "session:alice"},
    ) as client:
        response = await client.post(
            "/v1/agent/runs",
            json={"message": message},
        )
    assert response.status_code == 200
    return AgentRunResult.model_validate_json(response.content, strict=True)


def _tool_calls(session_factory, *run_ids) -> tuple[ToolCallRecordV2, ...]:
    with session_factory() as session:
        rows = tuple(
            session.scalars(
                select(P0RecordModel)
                .where(
                    P0RecordModel.record_code
                    == P0RecordCode.TOOL_CALL_RECORD.value,
                    P0RecordModel.run_id.in_(run_ids),
                )
                .order_by(P0RecordModel.stored_at, P0RecordModel.record_id)
            )
        )
        decoded = tuple(
            PostgresRecordAdapter._cycle2_decode_row(
                session,
                row,
                owner_customer_id="customer-A",
                expected_code=P0RecordCode.TOOL_CALL_RECORD,
            ).source_record
            for row in rows
        )
    assert all(type(record) is ToolCallRecordV2 for record in decoded)
    return decoded


def _expected_seed_projection(plan: ResolvedCycle2SeedPlan) -> tuple[object, ...]:
    return (
        tuple(
            (
                seed.owner_customer_id,
                seed.order_id,
                seed.order_payload.model_dump(mode="json"),
            )
            for seed in plan.order_seeds
        ),
        tuple(
            (
                seed.owner_customer_id,
                seed.order_id,
                seed.line_ordinal,
                seed.ordered_at,
                seed.order_number,
                seed.status.value,
                seed.product_name,
                seed.quantity,
                seed.product_category,
                seed.search_aliases,
            )
            for seed in plan.search_document_seeds
        ),
        tuple(
            (
                seed.owner_customer_id,
                seed.order_id,
                seed.package_id,
                dict(seed.shipment_payload),
            )
            for seed in plan.shipment_seeds
        ),
    )


def _stored_seed_projection(session_factory) -> tuple[object, ...]:
    with session_factory() as session:
        orders = tuple(
            session.scalars(
                select(MockOrderModel).order_by(
                    MockOrderModel.customer_id,
                    MockOrderModel.order_id,
                )
            )
        )
        searches = tuple(
            session.scalars(
                select(MockOrderSearchDocumentModel).order_by(
                    MockOrderSearchDocumentModel.customer_id,
                    MockOrderSearchDocumentModel.order_id,
                    MockOrderSearchDocumentModel.line_ordinal,
                )
            )
        )
        shipments = tuple(
            session.scalars(
                select(MockShipmentModel).order_by(
                    MockShipmentModel.customer_id,
                    MockShipmentModel.order_id,
                    MockShipmentModel.package_id,
                )
            )
        )
    return (
        tuple(
            (row.customer_id, row.order_id, row.order_payload)
            for row in orders
        ),
        tuple(
            (
                row.customer_id,
                row.order_id,
                row.line_ordinal,
                row.ordered_at,
                row.order_number,
                row.status,
                row.product_name,
                row.quantity,
                row.product_category,
                tuple(row.search_aliases),
            )
            for row in searches
        ),
        tuple(
            (
                row.customer_id,
                row.order_id,
                row.package_id,
                row.shipment_payload,
            )
            for row in shipments
        ),
    )


async def _start(
    namespace,
    *,
    fixture_refs: tuple[str, ...],
    clock_start: datetime = TRUSTED_CLOCK,
):
    engine = namespace.build_engine()
    session_factory = build_session_factory(engine)
    composition = await Cycle2OfflineComposition.start(
        fixture_refs=fixture_refs,
        session_factory=session_factory,
        clock=_MonotonicClock(clock_start),
    )
    return engine, session_factory, composition


def _seed_oa10_projection_root(
    composition: Cycle2OfflineComposition,
    source_evidence: Cycle2ExactRunEvidenceClosure,
    *,
    trace_mode: str,
    link_mode: str = "exact",
) -> AgentRunRecordV2:
    assert trace_mode in {"exact", "missing", "wrong", "duplicate"}
    assert link_mode in {"exact", "missing", "wrong", "extra"}
    source_completed_at = source_evidence.run_record.completed_at
    assert source_completed_at is not None
    assert len(source_evidence.task_records) == 1
    assert len(source_evidence.request_unit_records) == 1
    task = source_evidence.task_records[0]
    unit = source_evidence.request_unit_records[0]
    started_at = source_completed_at + timedelta(microseconds=10)
    completed_at = started_at + timedelta(microseconds=1)
    run = AgentRunRecordV2(
        run_id=uuid4(),
        conversation_id=source_evidence.conversation_record.conversation_id,
        status=AgentRunStatusV2.SUPERSEDED,
        provider_lane="offline_cycle2",
        started_at=started_at,
        completed_at=completed_at,
        stop_reason=StopReasonV2.STATE_OR_BINDING_INVALIDATED,
    )
    message = MessageRecord(
        schema_version="message_record.p0.v1",
        message_id=uuid4(),
        conversation_id=source_evidence.conversation_record.conversation_id,
        direction=MessageDirection.USER,
        content="恢复时发现旧 Run 已失效",
        received_at=started_at,
    )
    link = RunTaskLinkRecordV2(
        run_id=run.run_id,
        task_id=task.task_id,
        base_task_state_version=task.state_version,
        result_task_state_version=(
            task.state_version if link_mode == "wrong" else None
        ),
    )

    def stopped_trace(*, exact: bool) -> TraceEventV2:
        return TraceEventV2(
            trace_event_id=uuid4(),
            event_type=TraceEventType.RUN_STOPPED,
            occurred_at=completed_at,
            run_id=run.run_id,
            task_id=task.task_id,
            request_unit_id=unit.request_unit_id,
            user_outcome=(
                AgentOutcome.BLOCKED if exact else AgentOutcome.COMPLETED
            ),
            stop_reason=(
                StopReasonV2.STATE_OR_BINDING_INVALIDATED
                if exact
                else StopReasonV2.GOAL_COMPLETED
            ),
        )

    traces = {
        "exact": (stopped_trace(exact=True),),
        "missing": (),
        "wrong": (stopped_trace(exact=False),),
        "duplicate": (
            stopped_trace(exact=True),
            stopped_trace(exact=True),
        ),
    }[trace_mode]
    records = composition._records
    envelopes = [
        records._cycle2_encode(P0RecordCode.MESSAGE_RECORD, message),
        records._cycle2_encode(P0RecordCode.AGENT_RUN_RECORD, run),
        *(
            ()
            if link_mode == "missing"
            else (
                records._cycle2_encode(
                    P0RecordCode.RUN_TASK_LINK_RECORD,
                    link,
                ),
            )
        ),
        *[
            records._cycle2_encode(P0RecordCode.TRACE_EVENT_RECORD, trace)
            for trace in traces
        ],
    ]
    if link_mode == "extra":
        extra_task_id = uuid4()
        extra_unit_id = uuid4()
        extra_task = task.model_copy(update={"task_id": extra_task_id})
        extra_unit = unit.model_copy(
            update={
                "request_unit_id": extra_unit_id,
                "task_id": extra_task_id,
            }
        )
        envelopes.extend(
            (
                records._cycle2_encode(
                    P0RecordCode.TASK_RECORD,
                    extra_task,
                ),
                records._cycle2_encode(
                    P0RecordCode.REQUEST_UNIT_RECORD,
                    extra_unit,
                ),
                records._cycle2_encode(
                    P0RecordCode.RUN_TASK_LINK_RECORD,
                    RunTaskLinkRecordV2(
                        run_id=run.run_id,
                        task_id=extra_task_id,
                        base_task_state_version=extra_task.state_version,
                        result_task_state_version=None,
                    ),
                ),
            )
        )
    with records.session_factory.begin() as session:
        records._cycle2_insert(
            session,
            tuple(envelopes),
            owner_customer_id=source_evidence.owner_scope.customer_id,
        )
    return run


def _replace_task_transition_children(
    composition: Cycle2OfflineComposition,
    evidence: Cycle2ExactRunEvidenceClosure,
    *,
    children: tuple[TaskStateTransition, ...],
) -> None:
    records = composition._records
    task = evidence.task_records[0]
    with records.session_factory.begin() as session:
        row = session.scalar(
            select(P0RecordModel).where(
                P0RecordModel.record_code == P0RecordCode.TASK_RECORD.value,
                P0RecordModel.task_id == task.task_id,
            )
        )
        assert row is not None
        records._cycle2_replace(
            session,
            row,
            owner_customer_id=evidence.owner_scope.customer_id,
            expected_record=task,
            next_envelope=records._cycle2_encode(
                P0RecordCode.TASK_RECORD,
                task,
                logical_children=children,
            ),
        )


def _insert_unrelated_task_pair(
    composition: Cycle2OfflineComposition,
    evidence: Cycle2ExactRunEvidenceClosure,
) -> tuple[object, object]:
    records = composition._records
    task = evidence.task_records[0]
    unit = evidence.request_unit_records[0]
    unrelated_task = task.model_copy(update={"task_id": uuid4()})
    unrelated_unit = unit.model_copy(
        update={
            "request_unit_id": uuid4(),
            "task_id": unrelated_task.task_id,
        }
    )
    with records.session_factory.begin() as session:
        records._cycle2_insert(
            session,
            (
                records._cycle2_encode(
                    P0RecordCode.TASK_RECORD,
                    unrelated_task,
                ),
                records._cycle2_encode(
                    P0RecordCode.REQUEST_UNIT_RECORD,
                    unrelated_unit,
                ),
            ),
            owner_customer_id=evidence.owner_scope.customer_id,
        )
    return unrelated_task, unrelated_unit


def _replace_current_binding_but_keep_historical_reference(
    composition: Cycle2OfflineComposition,
    evidence: Cycle2ExactRunEvidenceClosure,
) -> tuple[InputBindingV2, InputBindingV2]:
    records = composition._records
    unit = evidence.request_unit_records[0]
    historical_binding_ref = (
        evidence.candidate_set_records[0].query_binding_refs[0]
    )
    historical = next(
        binding
        for binding in evidence.input_binding_records
        if binding.binding_id == historical_binding_ref
    )
    replacement = historical.model_copy(
        update={
            "binding_id": uuid4(),
            "created_at": unit.updated_at + timedelta(microseconds=1),
            "updated_at": unit.updated_at + timedelta(microseconds=1),
            "supersedes": historical.binding_id,
        }
    )
    next_unit = unit.model_copy(
        update={
            "input_binding_refs": (replacement.binding_id,),
            "updated_at": replacement.updated_at,
        }
    )
    with records.session_factory.begin() as session:
        records._cycle2_insert(
            session,
            (
                records._cycle2_encode_input_binding(
                    replacement,
                    request_unit_id=unit.request_unit_id,
                ),
            ),
            owner_customer_id=evidence.owner_scope.customer_id,
        )
        row = session.scalar(
            select(P0RecordModel).where(
                P0RecordModel.record_code
                == P0RecordCode.REQUEST_UNIT_RECORD.value,
                P0RecordModel.request_unit_id == unit.request_unit_id,
            )
        )
        assert row is not None
        records._cycle2_replace(
            session,
            row,
            owner_customer_id=evidence.owner_scope.customer_id,
            expected_record=unit,
            next_envelope=records._cycle2_encode(
                P0RecordCode.REQUEST_UNIT_RECORD,
                next_unit,
            ),
        )
    return historical, replacement


def _tamper_order_observation_source_call(
    composition: Cycle2OfflineComposition,
    evidence: Cycle2ExactRunEvidenceClosure,
) -> None:
    records = composition._records
    order_observation = evidence.order_observation_records[0]
    wrong_call = next(
        call
        for call in evidence.tool_call_records
        if call.canonical_tool_name is Cycle2ToolName.SEARCH_ORDERS
    )
    with records.session_factory.begin() as session:
        row = session.scalar(
            select(P0RecordModel).where(
                P0RecordModel.record_code
                == P0RecordCode.OBSERVATION_RECORD.value,
                P0RecordModel.logical_identity
                == [["observation_id", str(order_observation.observation_id)]],
            )
        )
        assert row is not None
        envelope = P0PersistenceEnvelope.model_validate(row.envelope)
        references = tuple(
            P0RecordReference(
                relation=reference.relation,
                target_record_code=reference.target_record_code,
                target_logical_identity=(
                    ("tool_call_id", str(wrong_call.tool_call_id)),
                ),
            )
            if reference.relation == "source_tool_call_id"
            else reference
            for reference in envelope.record_references
        )
        decoded = records._cycle2_decode_row(
            session,
            row,
            owner_customer_id=evidence.owner_scope.customer_id,
            expected_code=P0RecordCode.OBSERVATION_RECORD,
        )
        records._cycle2_replace(
            session,
            row,
            owner_customer_id=evidence.owner_scope.customer_id,
            expected_record=decoded.source_record,
            expected_children=decoded.logical_children,
            next_envelope=records._cycle2_encode(
                P0RecordCode.OBSERVATION_RECORD,
                decoded.source_record,
                external_references=references,
            ),
        )


async def test_unique_search_runs_through_authenticated_http_and_exact_evidence(
    eval_postgres_namespace,
) -> None:
    engine, session_factory, composition = await _start(
        eval_postgres_namespace,
        fixture_refs=("fx-search-unique-owner-a-with-foreign-decoy-v1",),
    )
    try:
        result = await _post(
            composition.build_case_app(
                provider=_Cycle2DirectProvider(
                    product_description="轻量跑鞋"
                )
            ),
            "帮我查找最近购买的轻量跑鞋订单",
        )
        evidence = await composition.load_exact_run_evidence(result.run_id)
        calls = _tool_calls(session_factory, result.run_id)

        assert result.outcome is AgentOutcome.COMPLETED
        assert type(evidence) is Cycle2ExactRunEvidenceClosure
        assert evidence.terminal_result == result
        assert evidence.supporting_run_records == ()
        assert evidence.task_state_transition_records == ()
        assert len(evidence.candidate_set_records) == 1
        assert evidence.candidate_selection_records == ()
        assert len(evidence.search_observation_records) == 1
        assert len(evidence.order_observation_records) == 1
        assert evidence.shipment_observation_records == ()
        assert len(evidence.observation_source_edges) == 2
        assert evidence.shipment_assessment_records == ()
        assert len(evidence.tool_call_records) == 2
        assert evidence.recovery_decision_records == ()
        assert evidence.superseded_run_finalizations == ()
        assert len(evidence.context_manifest_records) == 2
        assert len(evidence.model_visible_toolset_artifacts) == 1
        assert tuple(call.canonical_tool_name for call in calls) == (
            Cycle2ToolName.SEARCH_ORDERS,
            Cycle2ToolName.GET_ORDER,
        )

        run = evidence.run_record
        assert run.completed_at is not None
        timestamp_collisions = (
            MessageRecord(
                schema_version="message_record.p0.v1",
                message_id=uuid4(),
                conversation_id=run.conversation_id,
                direction=MessageDirection.USER,
                content="未引用的 started_at 碰撞消息",
                received_at=run.started_at,
            ),
            MessageRecord(
                schema_version="message_record.p0.v1",
                message_id=uuid4(),
                conversation_id=run.conversation_id,
                direction=MessageDirection.USER,
                content="未引用的 completed_at 碰撞消息",
                received_at=run.completed_at,
            ),
            MessageRecord(
                schema_version="message_record.p0.v1",
                message_id=uuid4(),
                conversation_id=run.conversation_id,
                direction=MessageDirection.ASSISTANT,
                content="非 terminal assistant",
                received_at=run.started_at,
            ),
        )
        with composition._records.session_factory.begin() as session:
            composition._records._cycle2_insert(
                session,
                tuple(
                    composition._records._cycle2_encode(
                        P0RecordCode.MESSAGE_RECORD,
                        message,
                    )
                    for message in timestamp_collisions
                ),
                owner_customer_id=evidence.owner_scope.customer_id,
            )
        isolated = await composition.load_exact_run_evidence(result.run_id)
        assert not {
            message.message_id for message in timestamp_collisions
        } & {message.message_id for message in isolated.message_records}

        duplicate_terminal = MessageRecord(
            schema_version="message_record.p0.v1",
            message_id=uuid4(),
            conversation_id=run.conversation_id,
            direction=MessageDirection.ASSISTANT,
            content="伪造的 terminal assistant",
            received_at=run.completed_at,
        )
        with composition._records.session_factory.begin() as session:
            composition._records._cycle2_insert(
                session,
                (
                    composition._records._cycle2_encode(
                        P0RecordCode.MESSAGE_RECORD,
                        duplicate_terminal,
                    ),
                ),
                owner_customer_id=evidence.owner_scope.customer_id,
            )
        with pytest.raises(P0PersistenceIntegrityError):
            await composition._records.load_cycle2_exact_run_evidence_for_owner(
                owner_scope=evidence.owner_scope,
                run_id=result.run_id,
            )
    finally:
        engine.dispose()


async def test_exact_reader_uses_one_repeatable_read_snapshot(
    eval_postgres_namespace,
) -> None:
    engine, session_factory, composition = await _start(
        eval_postgres_namespace,
        fixture_refs=("fx-search-unique-owner-a-with-foreign-decoy-v1",),
    )
    try:
        result = await _post(
            composition.build_case_app(
                provider=_Cycle2DirectProvider(
                    product_description="轻量跑鞋"
                )
            ),
            "帮我查找最近购买的轻量跑鞋订单",
        )
        with session_factory() as session:
            run_row = session.scalar(
                select(P0RecordModel).where(
                    P0RecordModel.record_code
                    == P0RecordCode.AGENT_RUN_RECORD.value,
                    P0RecordModel.run_id == result.run_id,
                )
            )
            assert run_row is not None
            run = composition._records._cycle2_decode_row(
                session,
                run_row,
                owner_customer_id="customer-A",
                expected_code=P0RecordCode.AGENT_RUN_RECORD,
            ).source_record
        assert type(run) is AgentRunRecordV2
        assert run.completed_at is not None
        concurrent_terminal = MessageRecord(
            schema_version="message_record.p0.v1",
            message_id=uuid4(),
            conversation_id=run.conversation_id,
            direction=MessageDirection.ASSISTANT,
            content="在 reader 首次 SELECT 后提交",
            received_at=run.completed_at,
        )
        state = {"injected": False, "saw_repeatable_read": False}

        def inject_after_snapshot_select(
            _connection,
            _cursor,
            statement,
            _parameters,
            _context,
            _executemany,
        ) -> None:
            normalized = " ".join(statement.upper().split())
            if normalized.startswith(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
            ):
                state["saw_repeatable_read"] = True
                return
            if (
                state["injected"]
                or not state["saw_repeatable_read"]
                or not normalized.startswith("SELECT")
                or "P0_RECORD" not in normalized
            ):
                return
            state["injected"] = True
            with session_factory.begin() as other_session:
                composition._records._cycle2_insert(
                    other_session,
                    (
                        composition._records._cycle2_encode(
                            P0RecordCode.MESSAGE_RECORD,
                            concurrent_terminal,
                        ),
                    ),
                    owner_customer_id="customer-A",
                )

        event.listen(engine, "after_cursor_execute", inject_after_snapshot_select)
        try:
            evidence = await composition.load_exact_run_evidence(result.run_id)
        finally:
            event.remove(
                engine,
                "after_cursor_execute",
                inject_after_snapshot_select,
            )
        assert state == {"injected": True, "saw_repeatable_read": True}
        assert concurrent_terminal not in evidence.message_records
        with pytest.raises(P0PersistenceIntegrityError):
            await composition._records.load_cycle2_exact_run_evidence_for_owner(
                owner_scope=evidence.owner_scope,
                run_id=result.run_id,
            )
    finally:
        engine.dispose()


@pytest.mark.parametrize("transition_mode", ("valid", "wrong_request_unit"))
async def test_exact_reader_bounds_persisted_task_transitions(
    eval_postgres_namespace,
    transition_mode: str,
) -> None:
    engine, _session_factory, composition = await _start(
        eval_postgres_namespace,
        fixture_refs=("fx-search-unique-owner-a-with-foreign-decoy-v1",),
    )
    try:
        result = await _post(
            composition.build_case_app(
                provider=_Cycle2DirectProvider(
                    product_description="轻量跑鞋"
                )
            ),
            "帮我查找最近购买的轻量跑鞋订单",
        )
        evidence = await composition.load_exact_run_evidence(result.run_id)
        task = evidence.task_records[0]
        unit = evidence.request_unit_records[0]
        link = next(
            record
            for record in evidence.run_task_link_records
            if record.run_id == result.run_id
        )
        assert link.result_task_state_version is not None
        valid = TaskStateTransition(
            task_id=task.task_id,
            request_unit_id=unit.request_unit_id,
            from_status=TaskStatus.ACTIVE,
            to_status=TaskStatus.WAITING_USER,
            base_state_version=1,
            result_state_version=2,
            reason_ref=result.run_id,
            changed_at=task.updated_at,
        )
        if transition_mode == "valid":
            outside = TaskStateTransition(
                task_id=task.task_id,
                request_unit_id=unit.request_unit_id,
                from_status=TaskStatus.WAITING_USER,
                to_status=TaskStatus.COMPLETED,
                base_state_version=link.result_task_state_version,
                result_state_version=link.result_task_state_version + 1,
                reason_ref=result.run_id,
                changed_at=task.updated_at + timedelta(microseconds=1),
            )
            _replace_task_transition_children(
                composition,
                evidence,
                children=(valid, outside),
            )
            reread = await composition.load_exact_run_evidence(result.run_id)
            assert reread.task_state_transition_records == (valid,)
        else:
            _, unrelated_unit = _insert_unrelated_task_pair(
                composition,
                evidence,
            )
            wrong = valid.model_copy(
                update={"request_unit_id": unrelated_unit.request_unit_id}
            )
            _replace_task_transition_children(
                composition,
                evidence,
                children=(wrong,),
            )
            with pytest.raises(P0PersistenceIntegrityError):
                await (
                    composition._records
                    .load_cycle2_exact_run_evidence_for_owner(
                        owner_scope=evidence.owner_scope,
                        run_id=result.run_id,
                    )
                )
    finally:
        engine.dispose()


async def test_exact_reader_rejects_tampered_observation_source_edge(
    eval_postgres_namespace,
) -> None:
    engine, _session_factory, composition = await _start(
        eval_postgres_namespace,
        fixture_refs=("fx-search-unique-owner-a-with-foreign-decoy-v1",),
    )
    try:
        result = await _post(
            composition.build_case_app(
                provider=_Cycle2DirectProvider(
                    product_description="轻量跑鞋"
                )
            ),
            "帮我查找最近购买的轻量跑鞋订单",
        )
        evidence = await composition.load_exact_run_evidence(result.run_id)
        _tamper_order_observation_source_call(composition, evidence)
        with pytest.raises(P0PersistenceIntegrityError):
            await composition._records.load_cycle2_exact_run_evidence_for_owner(
                owner_scope=evidence.owner_scope,
                run_id=result.run_id,
            )
    finally:
        engine.dispose()


async def test_exact_reader_rejects_historical_candidate_query_after_current_binding_replaced(
    eval_postgres_namespace,
) -> None:
    engine, _session_factory, composition = await _start(
        eval_postgres_namespace,
        fixture_refs=("fx-search-unique-owner-a-with-foreign-decoy-v1",),
    )
    try:
        result = await _post(
            composition.build_case_app(
                provider=_Cycle2DirectProvider(
                    product_description="轻量跑鞋"
                )
            ),
            "帮我查找最近购买的轻量跑鞋订单",
        )
        evidence = await composition.load_exact_run_evidence(result.run_id)
        _historical, _replacement = (
            _replace_current_binding_but_keep_historical_reference(
                composition,
                evidence,
            )
        )
        with pytest.raises(P0PersistenceIntegrityError) as caught:
            await composition._records.load_cycle2_exact_run_evidence_for_owner(
                owner_scope=evidence.owner_scope,
                run_id=result.run_id,
            )
        assert caught.value.category is (
            P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH
        )
    finally:
        engine.dispose()


async def test_multiple_then_second_uses_current_candidate_without_research(
    eval_postgres_namespace,
) -> None:
    engine, session_factory, composition = await _start(
        eval_postgres_namespace,
        fixture_refs=("fx-search-multiple-owner-a-v1",),
    )
    try:
        app = composition.build_case_app(
            provider=_Cycle2DirectProvider(product_description="跑鞋")
        )
        first = await _post(app, "帮我查找最近购买的跑鞋订单")
        second = await _post(app, "第二个")
        first_evidence = await composition.load_exact_run_evidence(first.run_id)
        second_evidence = await composition.load_exact_run_evidence(second.run_id)
        calls = _tool_calls(session_factory, first.run_id, second.run_id)

        assert first.outcome is AgentOutcome.ASK_USER
        assert second.outcome is AgentOutcome.COMPLETED
        assert first_evidence.terminal_result == first
        assert second_evidence.terminal_result == second
        assert len(second_evidence.supporting_run_records) == 1
        assert second_evidence.supporting_run_records[0].run_id == first.run_id
        supporting_links = tuple(
            link
            for link in second_evidence.run_task_link_records
            if link.run_id == first.run_id
        )
        assert len(supporting_links) == 1
        assert len(second_evidence.candidate_set_records) == 1
        assert len(second_evidence.candidate_selection_records) == 1
        assert len(second_evidence.observation_source_edges) == 2
        historical_binding_refs = set(
            second_evidence.candidate_set_records[0].query_binding_refs
        )
        historical_bindings = tuple(
            binding
            for binding in second_evidence.input_binding_records
            if binding.binding_id in historical_binding_refs
        )
        assert historical_bindings
        assert all(
            binding.created_at < second_evidence.run_record.started_at
            for binding in historical_bindings
        )
        assert {
            call.run_id for call in second_evidence.tool_call_records
        } == {first.run_id, second.run_id}
        assert tuple(call.canonical_tool_name for call in calls).count(
            Cycle2ToolName.SEARCH_ORDERS
        ) == 1
        assert tuple(call.canonical_tool_name for call in calls).count(
            Cycle2ToolName.GET_ORDER
        ) == 1
    finally:
        engine.dispose()


async def test_same_pair_seed_and_registry_select_shipment_only_for_logistics(
    postgres_namespace_factory,
) -> None:
    fixture_refs = ("fx-dynamic-tool-pair-owner-a-v1",)
    expected_seed = _expected_seed_projection(
        resolve_cycle2_seed_plan(fixture_refs)
    )
    expected_registry = build_cycle2_registry_snapshot()
    results: dict[
        bool,
        tuple[tuple[object, ...], tuple[str, ...], tuple[Cycle2ToolName, ...]],
    ] = {}

    for include_shipment in (False, True):
        namespace = postgres_namespace_factory.create(
            f"cycle2-pair-{include_shipment}"
        )
        engine, session_factory, composition = await _start(
            namespace,
            fixture_refs=fixture_refs,
            clock_start=TRUSTED_CLOCK - timedelta(hours=2, minutes=54),
        )
        try:
            result = await _post(
                composition.build_case_app(
                    provider=_Cycle2DirectProvider(
                        product_description="轻量跑鞋",
                        include_shipment=include_shipment,
                    )
                ),
                (
                    "查找轻量跑鞋订单并告诉我物流"
                    if include_shipment
                    else "查找轻量跑鞋订单"
                ),
            )
            evidence = await composition.load_exact_run_evidence(result.run_id)
            calls = _tool_calls(session_factory, result.run_id)
            assert result.outcome is AgentOutcome.COMPLETED
            assert evidence.terminal_result == result
            results[include_shipment] = (
                _stored_seed_projection(session_factory),
                tuple(sorted({call.tool_registry_version for call in calls})),
                tuple(call.canonical_tool_name for call in calls),
            )
        finally:
            engine.dispose()
            postgres_namespace_factory.drop(namespace)

    assert results[False][0] == results[True][0] == expected_seed
    assert results[False][1] == results[True][1] == (
        expected_registry.tool_registry_version,
    )
    assert Cycle2ToolName.GET_SHIPMENT not in results[False][2]
    assert Cycle2ToolName.GET_SHIPMENT in results[True][2]


async def test_authenticated_transient_shipment_fault_retries_once_then_succeeds(
    eval_postgres_namespace,
) -> None:
    engine, session_factory, composition = await _start(
        eval_postgres_namespace,
        fixture_refs=(
            "fx-dynamic-tool-pair-owner-a-v1",
            "fault:get-shipment:transient-once-v1",
        ),
        clock_start=TRUSTED_CLOCK - timedelta(hours=2, minutes=54),
    )
    try:
        result = await _post(
            composition.build_case_app(
                provider=_Cycle2DirectProvider(
                    product_description="轻量跑鞋",
                    include_shipment=True,
                )
            ),
            "查找轻量跑鞋订单并告诉我物流",
        )
        evidence = await composition.load_exact_run_evidence(result.run_id)
        shipment_calls = tuple(
            call
            for call in _tool_calls(session_factory, result.run_id)
            if call.canonical_tool_name is Cycle2ToolName.GET_SHIPMENT
        )

        assert result.outcome is AgentOutcome.COMPLETED
        assert evidence.terminal_result == result
        assert len(evidence.search_observation_records) == 1
        assert len(evidence.order_observation_records) == 1
        assert len(evidence.shipment_observation_records) == 1
        assert len(evidence.shipment_assessment_records) == 1
        assert len(evidence.observation_source_edges) == 3
        assert len(evidence.tool_call_records) == 3
        assert len(evidence.recovery_decision_records) == 1
        assert len(shipment_calls) == 1
        call = shipment_calls[0]
        assert call.status is ToolCallStatus.SUCCEEDED
        assert call.attempt_count == 2
        assert call.attempts[0].outcome is ToolResultOutcome.SYSTEM_FAILURE
        assert (
            call.attempts[0].retry_decision
            is ToolRetryDecision.RETRY_SCHEDULED
        )
        assert call.attempts[1].outcome is ToolResultOutcome.SUCCESS
        assert (
            call.attempts[1].retry_decision
            is ToolRetryDecision.NOT_APPLICABLE
        )

        task = evidence.task_records[0]
        unit = evidence.request_unit_records[0]
        persisted_history = TaskStateTransition(
            task_id=task.task_id,
            request_unit_id=unit.request_unit_id,
            from_status=TaskStatus.ACTIVE,
            to_status=TaskStatus.WAITING_USER,
            base_state_version=1,
            result_state_version=2,
            reason_ref=result.run_id,
            changed_at=task.updated_at,
        )
        _replace_task_transition_children(
            composition,
            evidence,
            children=(persisted_history,),
        )
        oa10_run = _seed_oa10_projection_root(
            composition,
            evidence,
            trace_mode="exact",
        )
        oa10_evidence = await (
            composition._records.load_cycle2_exact_run_evidence_for_owner(
                owner_scope=evidence.owner_scope,
                run_id=oa10_run.run_id,
            )
        )
        assert oa10_evidence is not None
        assert len(oa10_evidence.superseded_run_finalizations) == 1
        assert (
            oa10_evidence.superseded_run_finalizations[0]
            .superseded_run_record
            == oa10_run
        )
        assert oa10_evidence.terminal_result is None
        assert oa10_evidence.task_state_transition_records == ()
        assert len(oa10_evidence.supporting_run_records) == 1
        assert oa10_evidence.supporting_run_records[0].run_id == result.run_id
        supporting_links = tuple(
            link
            for link in oa10_evidence.run_task_link_records
            if link.run_id == result.run_id
        )
        assert len(supporting_links) == 1
        assert {
            tool_call.run_id
            for tool_call in oa10_evidence.tool_call_records
        } == {result.run_id}
        assert len(oa10_evidence.tool_call_records) == 3
        assert oa10_evidence.recovery_decision_records == ()

        for trace_mode in ("missing", "wrong", "duplicate"):
            invalid = _seed_oa10_projection_root(
                composition,
                evidence,
                trace_mode=trace_mode,
            )
            with pytest.raises(P0PersistenceIntegrityError):
                await (
                    composition._records
                    .load_cycle2_exact_run_evidence_for_owner(
                        owner_scope=evidence.owner_scope,
                        run_id=invalid.run_id,
                    )
                )

        for link_mode in ("missing", "wrong", "extra"):
            invalid = _seed_oa10_projection_root(
                composition,
                evidence,
                trace_mode="exact",
                link_mode=link_mode,
            )
            with pytest.raises(P0PersistenceIntegrityError):
                await (
                    composition._records
                    .load_cycle2_exact_run_evidence_for_owner(
                        owner_scope=evidence.owner_scope,
                        run_id=invalid.run_id,
                    )
                )
    finally:
        engine.dispose()
