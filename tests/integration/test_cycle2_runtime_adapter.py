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
    Cycle2FaultBoundary,
    Cycle2FaultDirectiveKind,
    Cycle2FaultProtocolError,
    Cycle2InjectedProcessRestart,
    build_cycle2_detached_fault_controller,
    consume_cycle2_retry_finalize_boundary,
)
from mini_agent.infrastructure.cycle2_fixture_seed import cycle2_w12_fault_catalog

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


def _direct_order_graph() -> tuple[
    InitialToolCallV2ReadClosure,
    ToolCallRecordV2,
    ToolAttemptRecordV2,
]:
    closure, call, attempt = _graph(Cycle2ToolName.GET_ORDER)
    target_origin = closure.current_input_binding_records[0]
    direct_order = InputBindingV2(
        binding_id=uuid4(),
        name="order_id",
        normalized_value="O-1001",
        authority=InputAuthority.USER_CLAIM,
        source_refs=(uuid4(),),
        validation_status=InputValidationStatus.ACCEPTED,
        confirmed_by_user=True,
        created_at=NOW,
        updated_at=NOW,
    )
    request_unit = closure.current_request_unit_record.model_copy(
        update={
            "input_binding_refs": (
                target_origin.binding_id,
                direct_order.binding_id,
            )
        }
    )
    direct_closure = InitialToolCallV2ReadClosure(
        owner_scope=closure.owner_scope,
        current_task_record=closure.current_task_record,
        current_request_unit_record=request_unit,
        current_input_binding_records=(target_origin, direct_order),
        current_verified_order_targets=(
            closure.current_verified_order_targets
        ),
        current_target_observations=closure.current_target_observations,
        trusted_read_at=closure.trusted_read_at,
    )
    direct_call = ToolCallRecordV2.model_validate(
        {
            **call.model_dump(),
            "argument_binding_refs": (direct_order.binding_id,),
            "verified_target_ref": None,
        },
        strict=True,
    )
    return direct_closure, direct_call, attempt


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


async def test_runtime_handler_maps_direct_order_from_distinct_current_authorities() -> (
    None
):
    closure, call, attempt = _direct_order_graph()
    order = _OrderPort()
    handler = Cycle2BusinessReadHandler(
        runtime_record_port=_RecordPort(closure),
        search_orders_port=_SearchPort(),
        get_order_port=order,
        get_shipment_port=_ShipmentPort(),
        owner_scopes={closure.owner_scope.customer_id: closure.owner_scope},
        clock=lambda: NOW + timedelta(microseconds=1),
    )

    result = await handler(call, attempt, 137)

    assert result.outcome is ToolResultOutcome.SUCCESS
    assert call.verified_target_ref is None
    assert call.argument_binding_refs != (
        closure.current_verified_order_targets[0].input_binding_refs
    )
    assert order.queries == [
        GetOrderQuery(customer_id="customer-A", order_id="O-1001")
    ]


@pytest.mark.parametrize(
    "variant",
    (
        "wrong-binding-name",
        "wrong-binding-type",
        "missing-binding",
        "ambiguous-binding",
        "missing-target",
        "ambiguous-target",
        "missing-observation",
        "ambiguous-observation",
        "target-order-mismatch",
        "observation-target-mismatch",
        "merged-authority-binding",
        "superseded-target",
    ),
)
async def test_runtime_handler_rejects_incomplete_direct_order_authority(
    variant: str,
) -> None:
    closure, call, attempt = _direct_order_graph()
    target_origin, direct_order = closure.current_input_binding_records
    target = closure.current_verified_order_targets[0]
    observation = closure.current_target_observations[0]
    if variant == "wrong-binding-name":
        direct_order = direct_order.model_copy(
            update={"name": "product_description"}
        )
        closure = closure.model_copy(
            update={
                "current_input_binding_records": (
                    target_origin,
                    direct_order,
                )
            }
        )
    elif variant == "wrong-binding-type":
        direct_order = direct_order.model_copy(update={"normalized_value": 1001})
        closure = closure.model_copy(
            update={
                "current_input_binding_records": (
                    target_origin,
                    direct_order,
                )
            }
        )
    elif variant == "missing-binding":
        call = call.model_copy(update={"argument_binding_refs": (uuid4(),)})
    elif variant == "ambiguous-binding":
        call = call.model_copy(
            update={
                "argument_binding_refs": (
                    target_origin.binding_id,
                    direct_order.binding_id,
                )
            }
        )
    elif variant == "missing-target":
        closure = closure.model_copy(
            update={"current_verified_order_targets": ()}
        )
    elif variant == "ambiguous-target":
        closure = closure.model_copy(
            update={"current_verified_order_targets": (target, target)}
        )
    elif variant == "missing-observation":
        closure = closure.model_copy(
            update={"current_target_observations": ()}
        )
    elif variant == "ambiguous-observation":
        closure = closure.model_copy(
            update={"current_target_observations": (observation, observation)}
        )
    elif variant == "target-order-mismatch":
        closure = closure.model_copy(
            update={
                "current_verified_order_targets": (
                    target.model_copy(update={"order_id": "O-2002"}),
                )
            }
        )
    elif variant == "observation-target-mismatch":
        closure = closure.model_copy(
            update={
                "current_target_observations": (
                    observation.model_copy(
                        update={"verified_target_ref": uuid4()}
                    ),
                )
            }
        )
    elif variant == "merged-authority-binding":
        target = target.model_copy(
            update={"input_binding_refs": (direct_order.binding_id,)}
        )
        observation = observation.model_copy(
            update={"input_binding_refs": (direct_order.binding_id,)}
        )
        closure = closure.model_copy(
            update={
                "current_verified_order_targets": (target,),
                "current_target_observations": (observation,),
            }
        )
    else:
        closure = closure.model_copy(
            update={
                "current_verified_order_targets": (
                    target.model_copy(update={"superseded_by": uuid4()}),
                )
            }
        )
    order = _OrderPort()
    handler = Cycle2BusinessReadHandler(
        runtime_record_port=_RecordPort(closure),
        search_orders_port=_SearchPort(),
        get_order_port=order,
        get_shipment_port=_ShipmentPort(),
        owner_scopes={closure.owner_scope.customer_id: closure.owner_scope},
        clock=lambda: NOW + timedelta(microseconds=1),
    )

    with pytest.raises(Cycle2BusinessReadDispatchError):
        await handler(call, attempt, 137)

    assert order.queries == []


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


@pytest.mark.parametrize(
    ("fault_ref", "consumptions"),
    (
        (
            "fault:get-shipment:transient-once-v1",
            ((1, Cycle2FaultBoundary.BEFORE_DISPATCH, Cycle2FaultDirectiveKind.SYSTEM_FAILURE),),
        ),
        (
            "fault:get-shipment:transient-always-v1",
            (
                (1, Cycle2FaultBoundary.BEFORE_DISPATCH, Cycle2FaultDirectiveKind.SYSTEM_FAILURE),
                (2, Cycle2FaultBoundary.BEFORE_DISPATCH, Cycle2FaultDirectiveKind.SYSTEM_FAILURE),
            ),
        ),
        (
            "fault:get-shipment:source-integrity-v1",
            ((1, Cycle2FaultBoundary.BEFORE_DISPATCH, Cycle2FaultDirectiveKind.SYSTEM_FAILURE),),
        ),
        (
            "fault:get-shipment:timeout-after-dispatch-once-v1",
            ((1, Cycle2FaultBoundary.AFTER_DISPATCH, Cycle2FaultDirectiveKind.TIMEOUT),),
        ),
        (
            "fault:get-shipment:restart-after-retry-finalize-v1",
            (
                (1, Cycle2FaultBoundary.BEFORE_DISPATCH, Cycle2FaultDirectiveKind.SYSTEM_FAILURE),
                (1, Cycle2FaultBoundary.AFTER_RETRY_FINALIZE, Cycle2FaultDirectiveKind.PROCESS_RESTART),
            ),
        ),
        (
            "fault:get-shipment:restart-after-retry-finalize-state-invalidated-v1",
            ((1, Cycle2FaultBoundary.AFTER_RETRY_FINALIZE, Cycle2FaultDirectiveKind.PROCESS_RESTART),),
        ),
        (
            "fault:get-shipment:restart-with-unfinished-attempt-v1",
            ((1, Cycle2FaultBoundary.AFTER_ATTEMPT_START, Cycle2FaultDirectiveKind.PROCESS_RESTART),),
        ),
    ),
)
def test_w12_fault_controller_consumes_exact_attempt_and_boundary_once(
    fault_ref: str,
    consumptions: tuple[tuple[int, Cycle2FaultBoundary, Cycle2FaultDirectiveKind], ...],
) -> None:
    controller = build_cycle2_detached_fault_controller(
        cycle2_w12_fault_catalog()[fault_ref]
    )
    assert controller.is_detached
    controller.attach()
    for attempt_no, boundary, expected_kind in consumptions:
        directive = controller.consume(
            canonical_tool_name=Cycle2ToolName.GET_SHIPMENT,
            attempt_no=attempt_no,
            boundary=boundary,
        )
        assert directive is not None
        assert directive.kind is expected_kind
    controller.assert_exhausted()
    with pytest.raises(Cycle2FaultProtocolError):
        controller.consume(
            canonical_tool_name=Cycle2ToolName.GET_SHIPMENT,
            attempt_no=consumptions[-1][0],
            boundary=consumptions[-1][1],
        )
    controller.detach()
    controller.dispose()
    assert controller.is_disposed


def test_w12_fault_controller_rejects_wrong_phase_tool_and_use_before_attach() -> None:
    definition = cycle2_w12_fault_catalog()[
        "fault:get-shipment:timeout-after-dispatch-once-v1"
    ]
    controller = build_cycle2_detached_fault_controller(definition)
    with pytest.raises(Cycle2FaultProtocolError):
        controller.consume(
            canonical_tool_name=Cycle2ToolName.GET_SHIPMENT,
            attempt_no=1,
            boundary=Cycle2FaultBoundary.AFTER_DISPATCH,
        )
    controller.attach()
    with pytest.raises(Cycle2FaultProtocolError):
        controller.consume(
            canonical_tool_name=Cycle2ToolName.GET_ORDER,
            attempt_no=1,
            boundary=Cycle2FaultBoundary.AFTER_DISPATCH,
        )
    with pytest.raises(Cycle2FaultProtocolError):
        controller.consume(
            canonical_tool_name=Cycle2ToolName.GET_SHIPMENT,
            attempt_no=1,
            boundary=Cycle2FaultBoundary.BEFORE_DISPATCH,
        )


async def test_timeout_after_dispatch_reads_real_row_then_returns_timeout() -> None:
    closure, call, attempt = _graph(Cycle2ToolName.GET_SHIPMENT)
    shipment = _ShipmentPort()
    controller = build_cycle2_detached_fault_controller(
        cycle2_w12_fault_catalog()[
            "fault:get-shipment:timeout-after-dispatch-once-v1"
        ]
    )
    controller.attach()
    handler = Cycle2BusinessReadHandler(
        runtime_record_port=_RecordPort(closure),
        search_orders_port=_SearchPort(),
        get_order_port=_OrderPort(),
        get_shipment_port=shipment,
        owner_scopes={closure.owner_scope.customer_id: closure.owner_scope},
        clock=lambda: NOW + timedelta(microseconds=1),
        fault_controller=controller,
    )
    result = await handler(call, attempt, 137)
    assert len(shipment.queries) == 1
    assert result.outcome is ToolResultOutcome.TIMEOUT
    assert result.error_code == "TOOL_CALL_TIMEOUT"
    assert result.retryable is True
    controller.assert_exhausted()


def test_retry_finalize_restart_is_consumed_only_by_explicit_lifecycle_hook() -> None:
    controller = build_cycle2_detached_fault_controller(
        cycle2_w12_fault_catalog()[
            "fault:get-shipment:restart-after-retry-finalize-v1"
        ]
    )
    controller.attach()
    transient = controller.consume(
        canonical_tool_name=Cycle2ToolName.GET_SHIPMENT,
        attempt_no=1,
        boundary=Cycle2FaultBoundary.BEFORE_DISPATCH,
    )
    assert transient is not None
    assert transient.kind is Cycle2FaultDirectiveKind.SYSTEM_FAILURE
    assert transient.error_code == "SHIPMENT_SERVICE_TRANSIENT"
    with pytest.raises(Cycle2InjectedProcessRestart, match="RETRY_RECOVERY"):
        consume_cycle2_retry_finalize_boundary(
            controller,
            canonical_tool_name=Cycle2ToolName.GET_SHIPMENT,
            attempt_no=1,
        )
    controller.assert_exhausted()
