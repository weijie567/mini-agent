from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from mini_agent.application.agent_run_service import (
    AgentRunService,
    Cycle2AgentRunHandler,
)
from mini_agent.application.deterministic_renderer import DeterministicRenderer
from mini_agent.application.read_tool_executor import (
    Cycle2ReadToolExecutor,
    ReadToolExecutor,
)
from mini_agent.application.records import (
    AgentRunCommand,
    Cycle2ControlPurpose,
    Cycle2RunBudgetPolicyEvidence,
    TrustedOwnerScope,
)
from mini_agent.core.identity import CustomerContext
from mini_agent.core.order import (
    OrderLineSummary,
    OrderStatus,
    OrderSummaryProjection,
)
from mini_agent.core.request_understanding import (
    Cycle2ControlCandidate,
    Cycle2ControlCandidateKind,
    Cycle2InitialRequestUnderstandingOutputV2,
    Cycle2InitialTaskDeltaCandidateV2,
    Cycle2InputCandidate,
    NextMove,
    NextMoveKind,
    QueryContextualizationCandidateV2,
)
from mini_agent.core.task_state import TaskDeltaOperation
from mini_agent.core.task_state import TaskStatus
from mini_agent.core.tool_system import (
    ExecutionPolicy,
    RegistrySnapshot,
    ToolEffect,
    ToolRegistration,
    build_cycle2_registry_snapshot,
    get_order_tool_spec,
)
from mini_agent.core.trace import AgentOutcome, StopReason, TraceEventType
from mini_agent.evaluation.artifacts import load_e2e01_artifacts
from mini_agent.evaluation.scripted_provider import ScriptedModelProviderV2
from mini_agent.infrastructure.order.postgres import PostgresGetOrderAdapter
from mini_agent.infrastructure.order.postgres import PostgresSearchOrdersAdapter
from mini_agent.infrastructure.cycle2_fixture_seed import (
    TRUSTED_CLOCK,
    apply_cycle2_seed_plan,
    resolve_cycle2_seed_plan,
)
from mini_agent.infrastructure.cycle2_runtime import Cycle2BusinessReadHandler
from mini_agent.infrastructure.persistence.database import build_session_factory
from mini_agent.infrastructure.persistence.postgres import PostgresRecordAdapter

REPO_ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2030, 1, 1, tzinfo=UTC)
SOURCE_VERSION_A = (
    "mock-order-source-version.p0.v1:sha256:"
    "861c136b1a41ecef3cd9625dc58524ec452e939b5ca1eb70ebcab69181561c42"
)

pytestmark = pytest.mark.anyio


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


class _MonotonicClock:
    def __init__(self) -> None:
        self._next = NOW

    def __call__(self) -> datetime:
        value = self._next
        self._next += timedelta(microseconds=1)
        return value


def _context() -> CustomerContext:
    return CustomerContext(
        subject_ref="subject-A",
        customer_id="customer-A",
        auth_scopes=frozenset({"orders:read"}),
        authenticated_at=NOW,
        session_ref_hash="sha256:session-A",
    )


def _owner_scope() -> TrustedOwnerScope:
    return TrustedOwnerScope.from_customer_context(_context())


def _order_summary() -> OrderSummaryProjection:
    return OrderSummaryProjection(
        order_number="O-1001",
        status=OrderStatus.SHIPPED,
        line_items=(
            OrderLineSummary(product_name="轻量跑鞋", quantity=1),
        ),
        ordered_at=datetime(2026, 7, 20, 2, 15, tzinfo=UTC),
        status_updated_at=datetime(2026, 7, 24, 9, 30, tzinfo=UTC),
    )


def _snapshot() -> RegistrySnapshot:
    return RegistrySnapshot.build(
        tool_registry_version="runtime-tools-v1",
        registrations=(
            ToolRegistration(
                tool_spec=get_order_tool_spec(),
                provider_visible_name="get_order",
                effect=ToolEffect.READ,
                risk="LOW",
                idempotency="READ_ONLY",
                handler_ref="orders.get_order",
                execution_policy=ExecutionPolicy(
                    timeout_ms=500,
                    max_attempts=1,
                    interrupt_behavior="MARK_INTERRUPTED",
                ),
            ),
        ),
    )


async def _run_script(
    *,
    eval_postgres_namespace,
    script_ref: str,
):
    engine = eval_postgres_namespace.build_engine()
    session_factory = build_session_factory(engine)
    records = PostgresRecordAdapter(session_factory)
    orders = PostgresGetOrderAdapter(session_factory)
    clock = _MonotonicClock()
    provider = ScriptedModelProviderV2(
        load_e2e01_artifacts(
            REPO_ROOT,
            candidate_version="candidate",
        ).script_by_ref(script_ref),
        script_execution_ref=uuid4(),
    )
    try:
        await orders.seed_mock_order(
            customer_id="customer-A",
            order_summary=_order_summary(),
        )
        service = AgentRunService(
            model_provider=provider,
            registry_snapshot=_snapshot(),
            toolset_artifact_port=records,
            conversation_record_port=records,
            runtime_record_port=records,
            read_tool_executor=ReadToolExecutor(
                runtime_record_port=records,
                get_order_port=orders,
                clock=clock,
                uuid_factory=uuid4,
            ),
            deterministic_renderer=DeterministicRenderer(),
            clock=clock,
            uuid_factory=uuid4,
            provider_lane="scripted-v2",
            redaction_policy_version="redaction-v1",
        )
        result = await service.handle(
            AgentRunCommand(
                customer_context=_context(),
                message="请查询订单 O-1001",
            )
        )
        evidence = await records.load_exact_run_evidence_v3_for_owner(
            owner_scope=_owner_scope(),
            run_id=result.run_id,
        )
        return result, evidence
    finally:
        engine.dispose()


async def test_actual_v2_runtime_persists_exact_one_graph_before_tool_use(
    eval_postgres_namespace,
) -> None:
    result, evidence = await _run_script(
        eval_postgres_namespace=eval_postgres_namespace,
        script_ref="script:e2e01-01:success",
    )

    assert result.outcome is AgentOutcome.COMPLETED
    assert evidence is not None
    assert evidence.run_record.stop_reason is StopReason.GOAL_COMPLETED
    understanding = evidence.request_understanding_closure
    assert understanding is not None
    assert (
        understanding.record.record_schema_version
        == "request_understanding_record.p0.v3"
    )
    assert (
        understanding.record.model_input_schema_version
        == "e2e01-thin-v1"
    )
    assert (
        understanding.record.model_output_schema_version
        == "e2e01-thin-v2"
    )
    assert len(understanding.accepted_task_deltas) == 1
    assert len(evidence.task_records) == 1
    assert evidence.task_records[0].status is TaskStatus.COMPLETED
    assert len(evidence.request_unit_records) == 1
    assert len(evidence.input_binding_records) == 1
    assert len(evidence.conversation_task_links) == 1
    assert len(evidence.run_task_links) == 1
    assert len(evidence.gate_decisions) == 1
    assert len(evidence.tool_calls) == 1
    assert len(evidence.observation_records) == 1
    assert evidence.observation_records[0].source_version == SOURCE_VERSION_A
    observation_trace = next(
        event
        for event in evidence.trace_events
        if event.observation_ref
        == evidence.observation_records[0].observation_id
        and event.event_type is TraceEventType.OBSERVATION_RECORDED
    )
    assert (
        observation_trace.occurred_at
        == evidence.observation_records[0].recorded_at
    )
    assert len(evidence.context_manifests) == 2
    observation_manifests = tuple(
        manifest
        for manifest in evidence.context_manifests
        if manifest.observation_refs_and_versions
    )
    assert len(observation_manifests) == 1
    assert (
        observation_manifests[0]
        .observation_refs_and_versions[0]
        .version
        == SOURCE_VERSION_A
    )


@pytest.mark.parametrize(
    "script_ref",
    [
        "script:fault-provider:invalid-request-understanding-schema",
        "script:fault-provider:trusted-field-override",
    ],
)
async def test_actual_v2_candidate_invalid_scripts_stop_without_task_graph(
    eval_postgres_namespace,
    script_ref: str,
) -> None:
    result, evidence = await _run_script(
        eval_postgres_namespace=eval_postgres_namespace,
        script_ref=script_ref,
    )

    assert result.outcome is AgentOutcome.BLOCKED
    assert evidence is not None
    assert evidence.run_record.stop_reason is StopReason.INPUT_INVALID
    assert evidence.request_understanding_closure is None
    assert evidence.task_records == ()
    assert evidence.request_unit_records == ()
    assert evidence.input_binding_records == ()
    assert evidence.gate_decisions == ()
    assert evidence.tool_calls == ()
    assert evidence.observation_records == ()
    bounded_dump = evidence.model_dump_json()
    assert script_ref not in bounded_dump
    assert "customer-B" not in bounded_dump
    assert "ValidationError" not in bounded_dump


async def test_actual_v2_protocol_fault_remains_protocol_error(
    eval_postgres_namespace,
) -> None:
    result, evidence = await _run_script(
        eval_postgres_namespace=eval_postgres_namespace,
        script_ref="script:fault-provider:zero-target-functions",
    )

    assert result.outcome is AgentOutcome.BLOCKED
    assert evidence is not None
    assert (
        evidence.run_record.stop_reason
        is StopReason.PROVIDER_PROTOCOL_ERROR
    )
    assert evidence.request_understanding_closure is None
    assert evidence.task_records == ()
    assert evidence.gate_decisions == ()
    assert evidence.tool_calls == ()


class _Cycle2Clock:
    def __init__(self) -> None:
        self._next = TRUSTED_CLOCK

    def __call__(self) -> datetime:
        current = self._next
        self._next += timedelta(microseconds=1)
        return current


class _Cycle2UniqueProvider:
    async def propose_cycle2_initial(
        self,
        request,
    ) -> Cycle2InitialRequestUnderstandingOutputV2:
        return Cycle2InitialRequestUnderstandingOutputV2(
            schema_version="e2e01-cycle2-initial.p0.v1",
            message_ref=request.message_ref,
            contextualization=QueryContextualizationCandidateV2(
                text="查找最近购买的轻量跑鞋订单",
                resolved_reference_candidates=(),
                uncertainties=(),
                source_message_refs=(request.message_ref,),
            ),
            task_delta_candidates=(
                Cycle2InitialTaskDeltaCandidateV2(
                    candidate_id=uuid4(),
                    operation=TaskDeltaOperation.ADD_GOAL,
                    goal_patch="查找最近购买的轻量跑鞋订单",
                    input_candidates=(
                        Cycle2InputCandidate(
                            name="product_description",
                            candidate_value="轻量跑鞋",
                            source_ref=request.message_ref,
                            source_quote="轻量跑鞋",
                            confidence=0.99,
                        ),
                    ),
                    confidence=0.99,
                ),
            ),
            next_move_candidate=NextMove(
                kind=NextMoveKind.CALL_TOOL,
                requested_tool_name="search_orders",
                arguments={"product_description": "轻量跑鞋"},
            ),
        )

    async def propose_cycle2_continuation(self, _request):
        raise AssertionError("unique first turn must not use continuation")

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
        return Cycle2ControlCandidate(
            kind=Cycle2ControlCandidateKind.FINISH,
        )


async def test_cycle2_unique_first_turn_persists_real_normal_graph_and_exact_evidence(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    factory = build_session_factory(engine)
    plan = resolve_cycle2_seed_plan(
        ["fx-search-unique-owner-a-with-foreign-decoy-v1"]
    )
    apply_cycle2_seed_plan(factory, plan)
    clock = _Cycle2Clock()
    context = CustomerContext(
        subject_ref="fixture-subject:session:alice",
        customer_id="customer-A",
        auth_scopes=frozenset({"orders:read"}),
        authenticated_at=TRUSTED_CLOCK,
        session_ref_hash=sha256(b"session:alice").hexdigest(),
    )
    owner_scope = TrustedOwnerScope.from_customer_context(context)
    records = PostgresRecordAdapter(
        factory,
        cycle2_clock=clock,
        cycle2_run_budget_policy=Cycle2RunBudgetPolicyEvidence(
            policy_version="cycle2-w9-test-budget.v1",
            run_time_budget_ms=30_000,
        ),
        cycle2_session_owners=plan.session_owners_by_hash(),
    )
    search = PostgresSearchOrdersAdapter(factory)
    order = PostgresGetOrderAdapter(factory)
    handler = Cycle2BusinessReadHandler(
        runtime_record_port=records,
        search_orders_port=search,
        get_order_port=order,
        get_shipment_port=object(),
        owner_scopes={owner_scope.customer_id: owner_scope},
        clock=clock,
    )
    service = Cycle2AgentRunHandler(
        runtime_record_port=records,
        context_record_port=records,
        request_understanding_provider=_Cycle2UniqueProvider(),
        read_tool_executor=Cycle2ReadToolExecutor(
            runtime_record_port=records,
            handler=handler,
            uuid_factory=uuid4,
        ),
        deterministic_renderer=DeterministicRenderer(),
        clock=clock,
        uuid_factory=uuid4,
        provider_lane="scripted-cycle2",
        redaction_policy_version="redaction-v1",
    )
    try:
        await records.put_toolset_artifact(
            build_cycle2_registry_snapshot().artifact()
        )
        result = await service.handle(
            AgentRunCommand(
                customer_context=context,
                message="帮我查找最近购买的轻量跑鞋订单",
            )
        )
        evidence = await records.load_cycle2_exact_run_evidence_for_owner(
            owner_scope=owner_scope,
            run_id=result.run_id,
        )
        current = await records.load_current_session_task_for_owner(
            owner_scope=owner_scope,
            session_ref_hash=context.session_ref_hash,
            trusted_now=clock(),
        )
        foreign = CustomerContext(
            subject_ref="subject-B",
            customer_id="customer-B",
            auth_scopes=frozenset({"orders:read"}),
            authenticated_at=TRUSTED_CLOCK,
            session_ref_hash=sha256(b"session:bob").hexdigest(),
        )
        assert result.outcome is AgentOutcome.COMPLETED
        assert evidence is not None
        assert evidence.terminal_result == result
        assert evidence.supporting_run_records == ()
        assert len(evidence.task_records) == 1
        assert evidence.task_records[0].state_version == 3
        assert len(evidence.input_binding_records) == 1
        assert evidence.task_state_transition_records == ()
        assert len(evidence.candidate_set_records) == 1
        assert evidence.candidate_selection_records == ()
        assert len(evidence.auto_target_records) == 1
        assert len(evidence.search_observation_records) == 1
        assert len(evidence.order_observation_records) == 1
        assert evidence.shipment_observation_records == ()
        assert len(evidence.observation_source_edges) == 2
        assert evidence.shipment_assessment_records == ()
        assert len(evidence.tool_call_records) == 2
        assert len(evidence.gate_decision_records) == 2
        assert {
            record.gate_decision_id
            for record in evidence.gate_decision_records
        } == {
            record.gate_decision_id
            for record in evidence.tool_call_records
        }
        auto_target = evidence.auto_target_records[0]
        target_calls = tuple(
            record
            for record in evidence.tool_call_records
            if record.verified_target_ref is not None
        )
        assert len(target_calls) == 1
        assert target_calls[0].verified_target_ref == auto_target.verified_target_ref
        assert next(
            record
            for record in evidence.gate_decision_records
            if record.gate_decision_id == target_calls[0].gate_decision_id
        ).verified_target_ref == auto_target.verified_target_ref
        assert evidence.recovery_decision_records == ()
        assert evidence.superseded_run_finalizations == ()
        assert len(evidence.context_manifest_records) == 2
        assert len(evidence.model_visible_toolset_artifacts) == 1
        assert current is not None
        assert current.current_task_record == evidence.task_records[0]
        assert await records.load_cycle2_exact_run_evidence_for_owner(
            owner_scope=TrustedOwnerScope.from_customer_context(foreign),
            run_id=result.run_id,
        ) is None
        assert await records.load_current_session_task_for_owner(
            owner_scope=owner_scope,
            session_ref_hash="wrong-session-hash",
            trusted_now=clock(),
        ) is None
    finally:
        engine.dispose()
