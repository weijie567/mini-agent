from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from mini_agent.application.records import (
    InitialToolCallV2ReadClosure,
    TrustedOwnerScope,
)
from mini_agent.core.control_gateway import (
    Cycle2TargetObservationFacts,
    Cycle2VerifiedOrderTargetFacts,
)
from mini_agent.core.identity import CustomerContext
from mini_agent.core.order import GetOrderOutcome, GetOrderQuery, GetOrderResult
from mini_agent.core.order_search import (
    SearchOrdersOutcome,
    SearchOrdersQuery,
    SearchOrdersResult,
)
from mini_agent.core.request_understanding import InputAuthority
from mini_agent.core.shipment import (
    GetShipmentOutcome,
    GetShipmentQuery,
    GetShipmentResult,
)
from mini_agent.core.task_state import (
    InputBindingV2,
    InputValidationStatus,
    RequestUnitRecord,
    TaskRecord,
    TaskStatus,
)
from mini_agent.core.tool_system import (
    Cycle2ToolName,
    ToolAttemptRecordV2,
    ToolCallRecordV2,
    ToolCallStatus,
    ToolEffect,
    ToolResultOutcome,
)
from mini_agent.infrastructure.cycle2_runtime import (
    Cycle2AttemptFault,
    Cycle2BusinessReadDispatchError,
    Cycle2BusinessReadHandler,
)

NOW = datetime(2026, 7, 31, 12, 0, tzinfo=UTC)

pytestmark = pytest.mark.anyio


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


def _owner() -> TrustedOwnerScope:
    context = CustomerContext(
        subject_ref="subject-A",
        customer_id="customer-A",
        auth_scopes=frozenset({"orders:read"}),
        authenticated_at=NOW,
        session_ref_hash="session-hash-A",
    )
    return TrustedOwnerScope.from_customer_context(context)


class _RecordPort:
    def __init__(self, closure: InitialToolCallV2ReadClosure) -> None:
        self.closure = closure
        self.loads = 0

    async def load_initial_tool_call_v2_closure_for_owner(self, **_kwargs):
        self.loads += 1
        return self.closure


class _SearchPort:
    def __init__(self) -> None:
        self.queries: list[SearchOrdersQuery] = []

    async def search_orders(self, query: SearchOrdersQuery) -> SearchOrdersResult:
        self.queries.append(query)
        return SearchOrdersResult(outcome=SearchOrdersOutcome.NO_MATCH)


class _OrderPort:
    def __init__(self) -> None:
        self.queries: list[GetOrderQuery] = []

    async def get_order(self, query: GetOrderQuery) -> GetOrderResult:
        self.queries.append(query)
        return GetOrderResult(outcome=GetOrderOutcome.NOT_FOUND_OR_NOT_ACCESSIBLE)


class _ShipmentPort:
    def __init__(self) -> None:
        self.queries: list[GetShipmentQuery] = []

    async def get_shipment(self, query: GetShipmentQuery) -> GetShipmentResult:
        self.queries.append(query)
        return GetShipmentResult(outcome=GetShipmentOutcome.NO_SHIPMENT)


def _graph(
    tool: Cycle2ToolName,
) -> tuple[InitialToolCallV2ReadClosure, ToolCallRecordV2, ToolAttemptRecordV2]:
    owner = _owner()
    task_id = uuid4()
    unit_id = uuid4()
    binding_id = uuid4()
    observation_ref = uuid4()
    verified_ref = uuid4()
    binding = InputBindingV2(
        binding_id=binding_id,
        name="product_description",
        normalized_value="轻量跑鞋",
        authority=InputAuthority.USER_CLAIM,
        source_refs=(uuid4(),),
        validation_status=InputValidationStatus.ACCEPTED,
        confirmed_by_user=True,
        created_at=NOW,
        updated_at=NOW,
    )
    task = TaskRecord(
        task_id=task_id,
        owner_customer_id=owner.customer_id,
        status=TaskStatus.ACTIVE,
        state_version=2,
        created_at=NOW,
        updated_at=NOW,
    )
    unit = RequestUnitRecord(
        request_unit_id=unit_id,
        task_id=task_id,
        goal_text="查询轻量跑鞋订单",
        goal_source_refs=binding.source_refs,
        input_binding_refs=(binding_id,),
        observation_refs=(observation_ref,) if tool is not Cycle2ToolName.SEARCH_ORDERS else (),
        status=TaskStatus.ACTIVE,
        state_version=2,
        created_at=NOW,
        updated_at=NOW,
    )
    target = Cycle2VerifiedOrderTargetFacts(
        verified_target_ref=verified_ref,
        private_owner_scope_ref=owner.customer_id,
        owner_customer_id=owner.customer_id,
        task_id=task_id,
        request_unit_id=unit_id,
        task_state_version=2,
        order_id="O-1001",
        source_observation_ref=observation_ref,
        source_observation_version="source-v1",
        input_binding_refs=(binding_id,),
    )
    observation = Cycle2TargetObservationFacts(
        observation_ref=observation_ref,
        observation_version="source-v1",
        private_owner_scope_ref=owner.customer_id,
        owner_customer_id=owner.customer_id,
        task_id=task_id,
        request_unit_id=unit_id,
        task_state_version=2,
        verified_target_ref=verified_ref,
        input_binding_refs=(binding_id,),
    )
    closure = InitialToolCallV2ReadClosure(
        owner_scope=owner,
        current_task_record=task,
        current_request_unit_record=unit,
        current_input_binding_records=(binding,),
        current_verified_order_targets=(
            () if tool is Cycle2ToolName.SEARCH_ORDERS else (target,)
        ),
        current_target_observations=(
            () if tool is Cycle2ToolName.SEARCH_ORDERS else (observation,)
        ),
        trusted_read_at=NOW,
    )
    tool_call_id = uuid4()
    attempt = ToolAttemptRecordV2(
        tool_call_id=tool_call_id,
        attempt_no=1,
        started_at=NOW,
    )
    call = ToolCallRecordV2(
        tool_call_id=tool_call_id,
        run_id=uuid4(),
        task_id=task_id,
        request_unit_id=unit_id,
        model_call_id=uuid4(),
        context_manifest_id=uuid4(),
        gate_decision_id=uuid4(),
        canonical_tool_name=tool,
        tool_registry_version="e2e01-cycle2-tools.p0.v1",
        private_owner_scope_ref=owner.customer_id,
        validated_task_state_version=2,
        argument_binding_refs=(binding_id,),
        verified_target_ref=(
            None if tool is Cycle2ToolName.SEARCH_ORDERS else verified_ref
        ),
        effect=ToolEffect.READ,
        attempt_count=1,
        attempts=(attempt,),
        status=ToolCallStatus.RUNNING,
        started_at=NOW,
    )
    return closure, call, attempt


@pytest.mark.parametrize(
    ("tool", "expected_query_type"),
    (
        (Cycle2ToolName.SEARCH_ORDERS, SearchOrdersQuery),
        (Cycle2ToolName.GET_ORDER, GetOrderQuery),
        (Cycle2ToolName.GET_SHIPMENT, GetShipmentQuery),
    ),
)
async def test_runtime_handler_maps_all_three_reads_from_durable_closure(
    tool: Cycle2ToolName,
    expected_query_type: type,
) -> None:
    closure, call, attempt = _graph(tool)
    records = _RecordPort(closure)
    search = _SearchPort()
    order = _OrderPort()
    shipment = _ShipmentPort()
    handler = Cycle2BusinessReadHandler(
        runtime_record_port=records,
        search_orders_port=search,
        get_order_port=order,
        get_shipment_port=shipment,
        owner_scopes={closure.owner_scope.customer_id: closure.owner_scope},
        clock=lambda: NOW + timedelta(microseconds=1),
    )

    result = await handler(call, attempt, 137)

    assert result.outcome is ToolResultOutcome.SUCCESS
    assert result.tool_call_id == call.tool_call_id
    assert result.canonical_tool_name == tool.value
    assert result.payload is not None
    queries = search.queries + order.queries + shipment.queries
    assert len(queries) == 1
    assert type(queries[0]) is expected_query_type
    assert queries[0].customer_id == "customer-A"
    assert "customer-B" not in result.model_dump_json()


async def test_fault_is_attempt_bound_and_skips_business_dispatch() -> None:
    closure, call, attempt = _graph(Cycle2ToolName.GET_SHIPMENT)
    shipment = _ShipmentPort()
    handler = Cycle2BusinessReadHandler(
        runtime_record_port=_RecordPort(closure),
        search_orders_port=_SearchPort(),
        get_order_port=_OrderPort(),
        get_shipment_port=shipment,
        owner_scopes={closure.owner_scope.customer_id: closure.owner_scope},
        clock=lambda: NOW + timedelta(microseconds=1),
        fault_plan=(
            Cycle2AttemptFault(
                canonical_tool_name=Cycle2ToolName.GET_SHIPMENT,
                attempt_no=1,
                error_code="SHIPMENT_SERVICE_TRANSIENT",
            ),
        ),
    )

    result = await handler(call, attempt, 137)

    assert result.outcome is ToolResultOutcome.SYSTEM_FAILURE
    assert result.error_code == "SHIPMENT_SERVICE_TRANSIENT"
    assert result.retryable is True
    assert shipment.queries == []


async def test_runtime_handler_rejects_unmapped_owner_before_business_read() -> None:
    closure, call, attempt = _graph(Cycle2ToolName.SEARCH_ORDERS)
    search = _SearchPort()
    handler = Cycle2BusinessReadHandler(
        runtime_record_port=_RecordPort(closure),
        search_orders_port=search,
        get_order_port=_OrderPort(),
        get_shipment_port=_ShipmentPort(),
        owner_scopes={},
        clock=lambda: NOW,
    )
    with pytest.raises(Cycle2BusinessReadDispatchError):
        await handler(call, attempt, 137)
    assert search.queries == []
