from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from mini_agent.application.agent_run_service import AgentRunService
from mini_agent.application.deterministic_renderer import DeterministicRenderer
from mini_agent.application.read_tool_executor import ReadToolExecutor
from mini_agent.application.records import AgentRunCommand, TrustedOwnerScope
from mini_agent.core.identity import CustomerContext
from mini_agent.core.order import (
    OrderLineSummary,
    OrderStatus,
    OrderSummaryProjection,
)
from mini_agent.core.task_state import TaskStatus
from mini_agent.core.tool_system import (
    ExecutionPolicy,
    RegistrySnapshot,
    ToolEffect,
    ToolRegistration,
    get_order_tool_spec,
)
from mini_agent.core.trace import AgentOutcome, StopReason, TraceEventType
from mini_agent.evaluation.artifacts import load_e2e01_artifacts
from mini_agent.evaluation.scripted_provider import ScriptedModelProviderV2
from mini_agent.infrastructure.order.postgres import PostgresGetOrderAdapter
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
        evidence = await records.load_exact_run_evidence_for_owner(
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
    assert evidence.request_understanding_record is not None
    assert (
        evidence.request_understanding_record.schema_version
        == "request_understanding_record.p0.v2"
    )
    assert (
        evidence.request_understanding_record.model_input_schema_version
        == "e2e01-thin-v1"
    )
    assert (
        evidence.request_understanding_record.model_output_schema_version
        == "e2e01-thin-v2"
    )
    assert len(evidence.accepted_task_deltas) == 1
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
    assert evidence.request_understanding_record is None
    assert evidence.accepted_task_deltas == ()
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
    assert evidence.request_understanding_record is None
    assert evidence.task_records == ()
    assert evidence.gate_decisions == ()
    assert evidence.tool_calls == ()
