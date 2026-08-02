"""Trusted Infrastructure dispatch for the three inactive Cycle 2 READ tools."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime

from mini_agent.application.ports import (
    Cycle2RuntimeRecordPort,
    GetOrderPort,
    GetShipmentPort,
    SearchOrdersPort,
)
from mini_agent.application.records import (
    InitialToolCallV2ReadClosure,
    TrustedOwnerScope,
)
from mini_agent.core.order import GetOrderOutcome, GetOrderQuery, GetOrderResult
from mini_agent.core.order_search import (
    SearchOrdersOutcome,
    SearchOrdersResult,
    build_search_orders_query,
)
from mini_agent.core.shipment import (
    GetShipmentFailureCode,
    GetShipmentOutcome,
    GetShipmentQuery,
    GetShipmentResult,
)
from mini_agent.core.tool_system import (
    Cycle2ToolName,
    ToolAttemptRecordV2,
    ToolCallRecordV2,
    ToolCallStatus,
    ToolResult,
    ToolResultOutcome,
)


class Cycle2BusinessReadDispatchError(RuntimeError):
    """Bounded failure before a business READ can be safely dispatched."""


@dataclass(frozen=True, slots=True)
class Cycle2AttemptFault:
    """Authenticated attempt-indexed fault input; never inferred from Eval data."""

    canonical_tool_name: Cycle2ToolName
    attempt_no: int
    error_code: str

    def __post_init__(self) -> None:
        if (
            self.canonical_tool_name is not Cycle2ToolName.GET_SHIPMENT
            or self.attempt_no != 1
            or self.error_code
            != GetShipmentFailureCode.SHIPMENT_SERVICE_TRANSIENT.value
        ):
            raise ValueError("unsupported Cycle 2 authenticated fault")


class Cycle2BusinessReadHandler:
    """Resolve durable bindings/targets and call only reviewed business Ports."""

    def __init__(
        self,
        *,
        runtime_record_port: Cycle2RuntimeRecordPort,
        search_orders_port: SearchOrdersPort,
        get_order_port: GetOrderPort,
        get_shipment_port: GetShipmentPort,
        owner_scopes: Mapping[str, TrustedOwnerScope],
        clock: Callable[[], datetime],
        fault_plan: tuple[Cycle2AttemptFault, ...] = (),
    ) -> None:
        self._runtime_record_port = runtime_record_port
        self._search_orders_port = search_orders_port
        self._get_order_port = get_order_port
        self._get_shipment_port = get_shipment_port
        self._owner_scopes = dict(owner_scopes)
        keyed = {
            (fault.canonical_tool_name, fault.attempt_no): fault
            for fault in fault_plan
        }
        if len(keyed) != len(fault_plan):
            raise ValueError("duplicate Cycle 2 attempt fault")
        self._fault_plan = keyed
        self._clock = clock

    async def __call__(
        self,
        tool_call: ToolCallRecordV2,
        attempt: ToolAttemptRecordV2,
        effective_timeout_ms: int,
    ) -> ToolResult:
        if (
            type(tool_call) is not ToolCallRecordV2
            or type(attempt) is not ToolAttemptRecordV2
            or type(effective_timeout_ms) is not int
            or effective_timeout_ms <= 0
            or tool_call.status is not ToolCallStatus.RUNNING
            or not tool_call.attempts
            or tool_call.attempts[-1] != attempt
            or attempt.tool_call_id != tool_call.tool_call_id
            or attempt.finished_at is not None
        ):
            raise Cycle2BusinessReadDispatchError("invalid durable dispatch grant")
        owner_scope = self._owner_scopes.get(tool_call.private_owner_scope_ref)
        if (
            type(owner_scope) is not TrustedOwnerScope
            or owner_scope.customer_id != tool_call.private_owner_scope_ref
        ):
            raise Cycle2BusinessReadDispatchError("unknown trusted owner scope")
        closure = await (
            self._runtime_record_port.load_initial_tool_call_v2_closure_for_owner(
                owner_scope=owner_scope,
                task_id=tool_call.task_id,
                request_unit_id=tool_call.request_unit_id,
                trusted_read_at=attempt.started_at,
            )
        )
        if (
            type(closure) is not InitialToolCallV2ReadClosure
            or closure.current_task_record.state_version
            != tool_call.validated_task_state_version
            or tuple(
                binding.binding_id
                for binding in closure.current_input_binding_records
                if binding.binding_id in tool_call.argument_binding_refs
            )
            != tool_call.argument_binding_refs
        ):
            raise Cycle2BusinessReadDispatchError("durable dispatch closure changed")

        fault = self._fault_plan.get(
            (tool_call.canonical_tool_name, attempt.attempt_no)
        )
        if fault is not None:
            result: SearchOrdersResult | GetOrderResult | GetShipmentResult = (
                GetShipmentResult(
                    outcome=GetShipmentOutcome.SYSTEM_FAILURE,
                    failure_code=GetShipmentFailureCode(
                        fault.error_code
                    ),
                )
            )
        elif tool_call.canonical_tool_name is Cycle2ToolName.SEARCH_ORDERS:
            binding = self._one_argument_binding(closure, tool_call)
            if binding.name != "product_description" or type(binding.normalized_value) is not str:
                raise Cycle2BusinessReadDispatchError("invalid search binding")
            result = await self._search_orders_port.search_orders(
                build_search_orders_query(
                    customer_id=owner_scope.customer_id,
                    product_description=binding.normalized_value,
                    trusted_now=attempt.started_at,
                )
            )
        else:
            targets = tuple(
                target
                for target in closure.current_verified_order_targets
                if target.verified_target_ref == tool_call.verified_target_ref
            )
            if len(targets) != 1:
                raise Cycle2BusinessReadDispatchError("verified target unavailable")
            target = targets[0]
            if tool_call.argument_binding_refs != target.input_binding_refs:
                raise Cycle2BusinessReadDispatchError("target origin binding changed")
            if tool_call.canonical_tool_name is Cycle2ToolName.GET_ORDER:
                result = await self._get_order_port.get_order(
                    GetOrderQuery(
                        customer_id=owner_scope.customer_id,
                        order_id=target.order_id,
                    )
                )
            elif tool_call.canonical_tool_name is Cycle2ToolName.GET_SHIPMENT:
                result = await self._get_shipment_port.get_shipment(
                    GetShipmentQuery(
                        customer_id=owner_scope.customer_id,
                        order_id=target.order_id,
                    )
                )
            else:
                raise Cycle2BusinessReadDispatchError("tool is not dispatchable")

        completed_at = max(self._clock(), attempt.started_at)
        system_failure = (
            result.outcome
            in {
                SearchOrdersOutcome.SYSTEM_FAILURE,
                GetOrderOutcome.SYSTEM_FAILURE,
                GetShipmentOutcome.SYSTEM_FAILURE,
            }
        )
        failure = getattr(result, "failure_code", None)
        error_code = None if failure is None else str(failure.value)
        observed_at = getattr(result, "observed_at", None)
        return ToolResult(
            tool_call_id=tool_call.tool_call_id,
            canonical_tool_name=tool_call.canonical_tool_name.value,
            outcome=(
                ToolResultOutcome.SYSTEM_FAILURE
                if system_failure
                else ToolResultOutcome.SUCCESS
            ),
            payload=result.model_dump(mode="json", round_trip=True),
            error_code=error_code,
            retryable=(
                error_code
                == GetShipmentFailureCode.SHIPMENT_SERVICE_TRANSIENT.value
            ),
            observed_at=observed_at,
            completed_at=completed_at,
        )

    @staticmethod
    def _one_argument_binding(
        closure: InitialToolCallV2ReadClosure,
        tool_call: ToolCallRecordV2,
    ):
        bindings = tuple(
            binding
            for binding in closure.current_input_binding_records
            if binding.binding_id in tool_call.argument_binding_refs
        )
        if len(bindings) != 1:
            raise Cycle2BusinessReadDispatchError("argument binding is ambiguous")
        return bindings[0]
