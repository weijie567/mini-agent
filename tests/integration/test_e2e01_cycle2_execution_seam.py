from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from mini_agent.application.persistence import (
    P0RecordCode,
)
from mini_agent.application.records import (
    AgentRunResult,
    Cycle2ContinuationProviderProposal,
    Cycle2ExactRunEvidenceClosure,
)
from mini_agent.bootstrap import Cycle2OfflineComposition
from mini_agent.core.request_understanding import (
    Cycle2InitialRequestUnderstandingOutputV2,
    Cycle2InitialTaskDeltaCandidateV2,
    Cycle2InputCandidate,
    NextMove,
    NextMoveKind,
    QueryContextualizationCandidateV2,
)
from mini_agent.core.task_state import TaskDeltaOperation
from mini_agent.core.tool_system import (
    Cycle2ToolName,
    ToolCallRecordV2,
    ToolCallStatus,
    ToolResultOutcome,
    ToolRetryDecision,
    build_cycle2_registry_snapshot,
)
from mini_agent.core.trace import AgentOutcome
from mini_agent.infrastructure.cycle2_fixture_seed import (
    TRUSTED_CLOCK,
    compute_cycle2_pair_seed_digest,
    resolve_cycle2_seed_plan,
)
from mini_agent.infrastructure.persistence.database import build_session_factory
from mini_agent.infrastructure.persistence.models import P0RecordModel
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
    ) -> Cycle2ContinuationProviderProposal:
        return Cycle2ContinuationProviderProposal(
            input_candidate=Cycle2InputCandidate(
                name="candidate_ordinal",
                candidate_value=2,
                source_ref=request.message_ref,
                source_quote=request.original_query,
                confidence=0.99,
            ),
            next_move_candidate=NextMove(
                kind=NextMoveKind.CALL_TOOL,
                requested_tool_name="get_order",
                arguments={"order_id": "O-1001"},
                base_task_state_version=3,
            ),
        )

    async def propose_cycle2_search_followup(
        self,
        _request,
        _projection,
        current_task_state_version: int,
    ) -> NextMove:
        return NextMove(
            kind=NextMoveKind.CALL_TOOL,
            requested_tool_name="get_order",
            arguments={"order_id": "O-1001"},
            base_task_state_version=current_task_state_version,
        )

    async def propose_cycle2_order_followup(
        self,
        _request,
        order_summary,
        current_task_state_version: int,
    ) -> NextMove:
        return NextMove(
            kind=(
                NextMoveKind.CALL_TOOL
                if self._include_shipment
                else NextMoveKind.FINISH
            ),
            requested_tool_name=(
                "get_shipment" if self._include_shipment else None
            ),
            arguments=(
                {"order_id": order_summary.order_number}
                if self._include_shipment
                else None
            ),
            base_task_state_version=current_task_state_version,
        )


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
        assert tuple(call.canonical_tool_name for call in calls) == (
            Cycle2ToolName.SEARCH_ORDERS,
            Cycle2ToolName.GET_ORDER,
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
    expected_digest = compute_cycle2_pair_seed_digest(
        resolve_cycle2_seed_plan(fixture_refs)
    )
    expected_registry = build_cycle2_registry_snapshot()
    results: dict[bool, tuple[tuple[str, ...], tuple[Cycle2ToolName, ...]]] = {}

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
                tuple(sorted({call.tool_registry_version for call in calls})),
                tuple(call.canonical_tool_name for call in calls),
            )
        finally:
            engine.dispose()
            postgres_namespace_factory.drop(namespace)

    assert len(expected_digest) == 64
    assert results[False][0] == results[True][0] == (
        expected_registry.tool_registry_version,
    )
    assert Cycle2ToolName.GET_SHIPMENT not in results[False][1]
    assert Cycle2ToolName.GET_SHIPMENT in results[True][1]


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
    finally:
        engine.dispose()
