"""Trusted Infrastructure dispatch for the three inactive Cycle 2 READ tools."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from threading import RLock
from typing import Protocol

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


class Cycle2FaultProtocolError(RuntimeError):
    """The authenticated fault script and the real runtime boundary diverged."""


class Cycle2InjectedProcessRestart(RuntimeError):
    """Offline-only process boundary; it never represents a business failure."""


class Cycle2FaultBoundary(StrEnum):
    BEFORE_DISPATCH = "BEFORE_DISPATCH"
    AFTER_DISPATCH = "AFTER_DISPATCH"
    AFTER_ATTEMPT_START = "AFTER_ATTEMPT_START"
    AFTER_RETRY_FINALIZE = "AFTER_RETRY_FINALIZE"


class Cycle2FaultDirectiveKind(StrEnum):
    SYSTEM_FAILURE = "SYSTEM_FAILURE"
    TIMEOUT = "TIMEOUT"
    PROCESS_RESTART = "PROCESS_RESTART"


class Cycle2RestartKind(StrEnum):
    RETRY_RECOVERY = "RETRY_RECOVERY"
    RETRY_STATE_INVALIDATED = "RETRY_STATE_INVALIDATED"
    UNFINISHED_ATTEMPT = "UNFINISHED_ATTEMPT"


@dataclass(frozen=True, slots=True)
class Cycle2FaultDirective:
    canonical_tool_name: Cycle2ToolName
    attempt_no: int
    boundary: Cycle2FaultBoundary
    kind: Cycle2FaultDirectiveKind
    error_code: str | None = None
    retryable: bool = False
    restart_kind: Cycle2RestartKind | None = None

    def __post_init__(self) -> None:
        if (
            self.canonical_tool_name is not Cycle2ToolName.GET_SHIPMENT
            or type(self.attempt_no) is not int
            or self.attempt_no not in {1, 2}
        ):
            raise ValueError("fault directive must target one get_shipment attempt")
        if self.kind is Cycle2FaultDirectiveKind.SYSTEM_FAILURE:
            if self.boundary is not Cycle2FaultBoundary.BEFORE_DISPATCH:
                raise ValueError("system failure must be injected before dispatch")
            if self.error_code not in {
                GetShipmentFailureCode.SHIPMENT_SERVICE_TRANSIENT.value,
                GetShipmentFailureCode.SHIPMENT_SOURCE_INTEGRITY.value,
            }:
                raise ValueError("unsupported controlled get_shipment failure")
            if self.retryable != (
                self.error_code
                == GetShipmentFailureCode.SHIPMENT_SERVICE_TRANSIENT.value
            ):
                raise ValueError("fault retryability does not match the failure code")
            if self.restart_kind is not None:
                raise ValueError("system failure cannot carry restart metadata")
        elif self.kind is Cycle2FaultDirectiveKind.TIMEOUT:
            if (
                self.boundary is not Cycle2FaultBoundary.AFTER_DISPATCH
                or self.error_code != "TOOL_CALL_TIMEOUT"
                or not self.retryable
                or self.restart_kind is not None
            ):
                raise ValueError("timeout must be the exact retryable after-dispatch shape")
        elif (
            self.kind is Cycle2FaultDirectiveKind.PROCESS_RESTART
            and (
                self.boundary
                not in {
                    Cycle2FaultBoundary.AFTER_ATTEMPT_START,
                    Cycle2FaultBoundary.AFTER_RETRY_FINALIZE,
                }
                or self.error_code is not None
                or self.retryable
                or self.restart_kind is None
            )
        ):
            raise ValueError("process restart directive is not closed")


class _Cycle2FaultDefinition(Protocol):
    fault_ref: str
    directives: tuple[Cycle2FaultDirective, ...]


class Cycle2DetachedFaultController:
    """One-use offline controller attached only to an isolated composition."""

    def __init__(
        self,
        *,
        fault_ref: str,
        directives: tuple[Cycle2FaultDirective, ...],
    ) -> None:
        if type(fault_ref) is not str or not fault_ref or not directives:
            raise ValueError("closed fault definition required")
        identities = tuple(
            (item.canonical_tool_name, item.attempt_no, item.boundary)
            for item in directives
        )
        if len(identities) != len(set(identities)):
            raise ValueError("duplicate fault directive boundary")
        self._fault_ref = fault_ref
        self._directives = directives
        self._cursor = 0
        self._attached = False
        self._disposed = False
        self._lock = RLock()

    @property
    def fault_ref(self) -> str:
        return self._fault_ref

    @property
    def is_detached(self) -> bool:
        return not self._attached and not self._disposed

    @property
    def is_disposed(self) -> bool:
        return self._disposed

    def attach(self) -> None:
        with self._lock:
            if not self.is_detached:
                raise Cycle2FaultProtocolError("fault controller is not detached")
            self._attached = True

    def detach(self) -> None:
        with self._lock:
            if not self._attached or self._disposed:
                raise Cycle2FaultProtocolError("fault controller is not attached")
            self._attached = False

    def dispose(self) -> None:
        with self._lock:
            if self._attached:
                self._attached = False
            if self._disposed:
                return
            self._disposed = True

    def _require_attached(self) -> None:
        if not self._attached or self._disposed:
            raise Cycle2FaultProtocolError("fault controller is not active")

    def _next(self) -> Cycle2FaultDirective:
        if self._cursor >= len(self._directives):
            raise Cycle2FaultProtocolError("fault directive was duplicated or exhausted")
        return self._directives[self._cursor]

    def consume(
        self,
        *,
        canonical_tool_name: Cycle2ToolName,
        attempt_no: int,
        boundary: Cycle2FaultBoundary,
    ) -> Cycle2FaultDirective:
        with self._lock:
            self._require_attached()
            expected = self._next()
            if (
                expected.canonical_tool_name is not canonical_tool_name
                or expected.attempt_no != attempt_no
                or expected.boundary is not boundary
            ):
                raise Cycle2FaultProtocolError(
                    "fault directive consumed at the wrong tool, attempt, or phase"
                )
            self._cursor += 1
            return expected

    def maybe_consume(
        self,
        *,
        canonical_tool_name: Cycle2ToolName,
        attempt_no: int,
        boundary: Cycle2FaultBoundary,
    ) -> Cycle2FaultDirective | None:
        with self._lock:
            self._require_attached()
            if self._cursor >= len(self._directives):
                return None
            expected = self._directives[self._cursor]
            if (
                expected.canonical_tool_name is canonical_tool_name
                and expected.attempt_no == attempt_no
                and expected.boundary is boundary
            ):
                self._cursor += 1
                return expected
            return None

    def assert_exhausted(self) -> None:
        with self._lock:
            self._require_attached()
            if self._cursor != len(self._directives):
                raise Cycle2FaultProtocolError("fault directive was not consumed")


class Cycle2ExecutionSetupAttachmentTarget(Protocol):
    """Offline composition hook invoked before the setup transaction commits."""

    def attach_cycle2_execution_setup(
        self,
        setup: Cycle2DetachedExecutionSetup,
    ) -> None: ...

    def detach_cycle2_execution_setup(
        self,
        setup: Cycle2DetachedExecutionSetup,
    ) -> None: ...


class Cycle2DetachedExecutionSetup:
    """Validated session/clock/fault bundle with one explicit attach lifetime."""

    def __init__(
        self,
        *,
        setup_digest: str,
        trusted_context_fixture_ref: str,
        owner_customer_id: str,
        trusted_clock: datetime,
        fault_controller: Cycle2DetachedFaultController | None,
    ) -> None:
        if (
            type(setup_digest) is not str
            or not setup_digest.startswith("sha256:")
            or len(setup_digest) != 71
            or type(trusted_context_fixture_ref) is not str
            or not trusted_context_fixture_ref
            or type(owner_customer_id) is not str
            or not owner_customer_id
            or type(trusted_clock) is not datetime
            or trusted_clock.tzinfo is None
            or (
                fault_controller is not None
                and type(fault_controller) is not Cycle2DetachedFaultController
            )
        ):
            raise ValueError("detached execution setup is not canonical")
        self.setup_digest = setup_digest
        self.trusted_context_fixture_ref = trusted_context_fixture_ref
        self.owner_customer_id = owner_customer_id
        self.trusted_clock = trusted_clock
        self.fault_controller = fault_controller
        self._target: Cycle2ExecutionSetupAttachmentTarget | None = None
        self._disposed = False
        self._lock = RLock()

    @property
    def is_detached(self) -> bool:
        return self._target is None and not self._disposed

    @property
    def is_attached(self) -> bool:
        return self._target is not None and not self._disposed

    @property
    def is_disposed(self) -> bool:
        return self._disposed

    def attach(self, target: Cycle2ExecutionSetupAttachmentTarget) -> None:
        with self._lock:
            if not self.is_detached:
                raise Cycle2FaultProtocolError("execution setup is not detached")
            try:
                target.attach_cycle2_execution_setup(self)
                if self.fault_controller is not None:
                    self.fault_controller.attach()
            except Exception:
                try:
                    if (
                        self.fault_controller is not None
                        and not self.fault_controller.is_detached
                        and not self.fault_controller.is_disposed
                    ):
                        self.fault_controller.detach()
                finally:
                    target.detach_cycle2_execution_setup(self)
                raise
            self._target = target

    def detach(self) -> None:
        with self._lock:
            target = self._target
            if target is None or self._disposed:
                raise Cycle2FaultProtocolError("execution setup is not attached")
            if self.fault_controller is not None and not self.fault_controller.is_detached:
                self.fault_controller.detach()
            target.detach_cycle2_execution_setup(self)
            self._target = None

    def dispose(self) -> None:
        with self._lock:
            if self._target is not None:
                self.detach()
            if self.fault_controller is not None:
                self.fault_controller.dispose()
            self._disposed = True


def build_cycle2_detached_fault_controller(
    definition: _Cycle2FaultDefinition,
) -> Cycle2DetachedFaultController:
    if (
        type(getattr(definition, "fault_ref", None)) is not str
        or type(getattr(definition, "directives", None)) is not tuple
        or not all(
            type(item) is Cycle2FaultDirective
            for item in definition.directives
        )
    ):
        raise TypeError("exact typed W12 fault definition required")
    return Cycle2DetachedFaultController(
        fault_ref=definition.fault_ref,
        directives=definition.directives,
    )


def consume_cycle2_retry_finalize_boundary(
    controller: Cycle2DetachedFaultController | None,
    *,
    canonical_tool_name: Cycle2ToolName,
    attempt_no: int,
) -> None:
    """Consume the crash point after durable retry finalization and before a fence."""

    if controller is None:
        return
    directive = controller.maybe_consume(
        canonical_tool_name=canonical_tool_name,
        attempt_no=attempt_no,
        boundary=Cycle2FaultBoundary.AFTER_RETRY_FINALIZE,
    )
    if directive is None:
        return
    if (
        directive.kind is not Cycle2FaultDirectiveKind.PROCESS_RESTART
        or directive.restart_kind
        not in {
            Cycle2RestartKind.RETRY_RECOVERY,
            Cycle2RestartKind.RETRY_STATE_INVALIDATED,
        }
    ):
        raise Cycle2FaultProtocolError("retry-finalize fault is not a restart")
    raise Cycle2InjectedProcessRestart(directive.restart_kind.value)


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
        fault_controller: Cycle2DetachedFaultController | None = None,
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
        if fault_plan and fault_controller is not None:
            raise ValueError("W9 fault plan and W12 controller are mutually exclusive")
        self._fault_plan = keyed
        self._fault_controller = fault_controller
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

        controller = self._fault_controller
        restart_directive = (
            None
            if controller is None
            else controller.maybe_consume(
                canonical_tool_name=tool_call.canonical_tool_name,
                attempt_no=attempt.attempt_no,
                boundary=Cycle2FaultBoundary.AFTER_ATTEMPT_START,
            )
        )
        if restart_directive is not None:
            if restart_directive.kind is not Cycle2FaultDirectiveKind.PROCESS_RESTART:
                raise Cycle2FaultProtocolError("attempt-start fault is not a restart")
            raise Cycle2InjectedProcessRestart(restart_directive.restart_kind.value)

        w12_fault = (
            None
            if controller is None
            else controller.maybe_consume(
                canonical_tool_name=tool_call.canonical_tool_name,
                attempt_no=attempt.attempt_no,
                boundary=Cycle2FaultBoundary.BEFORE_DISPATCH,
            )
        )
        fault = self._fault_plan.get(
            (tool_call.canonical_tool_name, attempt.attempt_no)
        )
        if w12_fault is not None:
            if w12_fault.kind is not Cycle2FaultDirectiveKind.SYSTEM_FAILURE:
                raise Cycle2FaultProtocolError("pre-dispatch fault is not a failure")
            result: SearchOrdersResult | GetOrderResult | GetShipmentResult = (
                GetShipmentResult(
                    outcome=GetShipmentOutcome.SYSTEM_FAILURE,
                    failure_code=GetShipmentFailureCode(
                        w12_fault.error_code
                    ),
                )
            )
        elif fault is not None:
            result = GetShipmentResult(
                outcome=GetShipmentOutcome.SYSTEM_FAILURE,
                failure_code=GetShipmentFailureCode(fault.error_code),
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
        elif (
            tool_call.canonical_tool_name is Cycle2ToolName.GET_ORDER
            and tool_call.verified_target_ref is None
        ):
            binding = self._one_argument_binding(closure, tool_call)
            if (
                binding.name != "order_id"
                or type(binding.normalized_value) is not str
                or len(closure.current_verified_order_targets) != 1
                or len(closure.current_target_observations) != 1
            ):
                raise Cycle2BusinessReadDispatchError(
                    "direct order authority unavailable"
                )
            target = closure.current_verified_order_targets[0]
            observation = closure.current_target_observations[0]
            current_binding_ids = {
                current.binding_id
                for current in closure.current_input_binding_records
            }
            if (
                target.order_id != binding.normalized_value
                or binding.binding_id in target.input_binding_refs
                or not target.input_binding_refs
                or not set(target.input_binding_refs).issubset(
                    current_binding_ids
                )
                or target.source_observation_ref
                not in closure.current_request_unit_record.observation_refs
                or target.private_owner_scope_ref != owner_scope.customer_id
                or target.owner_customer_id != owner_scope.customer_id
                or target.task_id != tool_call.task_id
                or target.request_unit_id != tool_call.request_unit_id
                or target.task_state_version
                != tool_call.validated_task_state_version
                or target.superseded_by is not None
                or observation.verified_target_ref
                != target.verified_target_ref
                or observation.observation_ref
                != target.source_observation_ref
                or observation.observation_version
                != target.source_observation_version
                or observation.private_owner_scope_ref
                != owner_scope.customer_id
                or observation.owner_customer_id != owner_scope.customer_id
                or observation.task_id != target.task_id
                or observation.request_unit_id != target.request_unit_id
                or observation.task_state_version
                != target.task_state_version
                or observation.input_binding_refs
                != target.input_binding_refs
                or observation.superseded_by is not None
            ):
                raise Cycle2BusinessReadDispatchError(
                    "direct order authority changed"
                )
            result = await self._get_order_port.get_order(
                GetOrderQuery(
                    customer_id=owner_scope.customer_id,
                    order_id=binding.normalized_value,
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

        after_dispatch = (
            None
            if controller is None
            else controller.maybe_consume(
                canonical_tool_name=tool_call.canonical_tool_name,
                attempt_no=attempt.attempt_no,
                boundary=Cycle2FaultBoundary.AFTER_DISPATCH,
            )
        )

        completed_at = max(self._clock(), attempt.started_at)
        if after_dispatch is not None:
            if after_dispatch.kind is not Cycle2FaultDirectiveKind.TIMEOUT:
                raise Cycle2FaultProtocolError("after-dispatch fault is not a timeout")
            return ToolResult(
                tool_call_id=tool_call.tool_call_id,
                canonical_tool_name=tool_call.canonical_tool_name.value,
                outcome=ToolResultOutcome.TIMEOUT,
                payload=None,
                error_code=after_dispatch.error_code,
                retryable=after_dispatch.retryable,
                completed_at=completed_at,
            )
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
