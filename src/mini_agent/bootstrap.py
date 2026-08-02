"""Explicit offline Composition Root for the first E2E01 vertical slice."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI
from sqlalchemy.orm import Session, sessionmaker

from mini_agent.api.http import create_agent_app
from mini_agent.application.agent_run_service import (
    AfterRevalidationHook,
    AgentRunService,
    Cycle2AgentRunHandler,
)
from mini_agent.application.deterministic_renderer import DeterministicRenderer
from mini_agent.application.ports import Cycle2RequestUnderstandingProvider
from mini_agent.application.read_tool_executor import (
    Cycle2ReadToolExecutor,
    ReadToolExecutor,
)
from mini_agent.application.records import (
    AgentRunCommand,
    AgentRunResult,
    ApplyTaskTransitionCommand,
    ConditionalWriteResult,
    Cycle2ExactRunEvidenceClosure,
    Cycle2RunBudgetPolicyEvidence,
    ExactRunEvidenceClosure,
    RecoveryWriteResult,
    TrustedOwnerScope,
)
from mini_agent.application.restart_recovery_service import RestartRecoveryService
from mini_agent.core.common import FrozenJsonDict, FrozenJsonList
from mini_agent.core.order import (
    OrderLineSummary,
    OrderStatus,
    OrderSummaryProjection,
)
from mini_agent.core.task_state import (
    RequestUnitRecord,
    TaskRecord,
    TaskStateTransition,
    TaskStatus,
)
from mini_agent.core.tool_system import (
    ExecutionPolicy,
    RegistrySnapshot,
    ToolEffect,
    ToolRegistration,
    build_cycle2_registry_snapshot,
    get_order_tool_spec,
)
from mini_agent.core.trace import TraceEvent, TraceEventType
from mini_agent.evaluation.artifacts import LoadedE2E01Artifacts
from mini_agent.evaluation.harness import (
    EvalCaseExecutionInput,
    EvalCaseSutResult,
    OfflineEvalHarness,
    map_exact_run_http_result_to_sut_result,
)
from mini_agent.evaluation.scripted_provider import (
    RuntimeFaultDirective,
    ScriptedModelProviderV2,
)
from mini_agent.infrastructure.auth.p0_session import (
    P0SessionAuthAdapter,
    P0SessionFixture,
)
from mini_agent.infrastructure.model.qwen_responses import (
    QwenResponsesAdapterV2,
)
from mini_agent.infrastructure.cycle2_fixture_seed import (
    ResolvedCycle2SeedPlan,
    apply_cycle2_seed_plan,
    resolve_cycle2_seed_plan,
)
from mini_agent.infrastructure.cycle2_runtime import Cycle2BusinessReadHandler
from mini_agent.infrastructure.order.postgres import (
    PostgresGetOrderAdapter,
    PostgresSearchOrdersAdapter,
)
from mini_agent.infrastructure.persistence.postgres import PostgresRecordAdapter
from mini_agent.infrastructure.persistence.recovery import (
    PostgresRestartRecoveryAdapter,
)
from mini_agent.infrastructure.shipment.postgres import (
    PostgresGetShipmentAdapter,
)


_FIXTURE_ROOT_KEYS: Final = frozenset(
    {
        "artifact_type",
        "artifact_id",
        "schema_version",
        "fixture_version",
        "classification",
        "version_manifest_ref",
        "consumers",
        "sessions",
        "orders",
        "nonexistent_order_sentinels",
        "versions",
    }
)
_SESSION_KEYS: Final = frozenset(
    {
        "fixture_ref",
        "label",
        "session_id",
        "trusted_customer_id",
        "trust_boundary",
    }
)
_ORDER_KEYS: Final = frozenset(
    {
        "fixture_ref",
        "owner_customer_id",
        "safe_projection",
    }
)
_SENTINEL_KEYS: Final = frozenset(
    {
        "fixture_ref",
        "order_number",
        "seed_behavior",
    }
)
_SAFE_PROJECTION_KEYS: Final = frozenset(
    {
        "order_number",
        "status",
        "line_items",
        "ordered_at",
        "status_updated_at",
    }
)
_LINE_ITEM_KEYS: Final = frozenset({"product_name", "quantity"})
_VERSION_KEYS: Final = frozenset(
    {
        "fixture_version",
        "dataset_version",
        "prompt_version",
        "tool_registry_version",
        "renderer_version",
        "redaction_policy_version",
        "runtime_version",
    }
)
_EXPECTED_VERSION_VALUES: Final = {
    "fixture_version": "e2e01-thin-fixture-v1",
    "dataset_version": "e2e01-thin-dataset-v1",
    "prompt_version": "e2e01-thin-prompt-v1",
    "tool_registry_version": "e2e01-thin-tools-v1",
    "renderer_version": "order-summary-renderer-v1",
    "redaction_policy_version": "e2e01-thin-redaction-v1",
    "runtime_version": "BOUND_AT_EVAL_RUN_FROM_SOURCE_REVISION_OR_BUILD_ID",
}
_EXPECTED_FIXTURE_COUNTS: Final = {
    "sessions": 2,
    "orders": 2,
    "nonexistent_order_sentinels": 1,
}
_START_TOKEN: Final = object()
_CYCLE2_START_TOKEN: Final = object()


class OfflineCompositionError(RuntimeError):
    """Bounded offline assembly failure without fixture or database diagnostics."""

    __slots__ = ()

    def __init__(self) -> None:
        super().__init__("OFFLINE_COMPOSITION_FAILED")


def _fresh_composition_error() -> OfflineCompositionError:
    error = OfflineCompositionError()
    error.__cause__ = None
    error.__context__ = None
    return error


def _exact_frozen_mapping(
    value: object,
    *,
    expected_keys: frozenset[str],
) -> FrozenJsonDict:
    if type(value) is not FrozenJsonDict or frozenset(value) != expected_keys:
        raise ValueError("fixture mapping shape is invalid")
    return value


def _exact_frozen_list(
    value: object,
    *,
    expected_length: int | None = None,
) -> FrozenJsonList:
    if type(value) is not FrozenJsonList:
        raise ValueError("fixture list shape is invalid")
    if expected_length is not None and len(value) != expected_length:
        raise ValueError("fixture list cardinality is invalid")
    return value


def _nonempty_exact_string(value: object) -> str:
    if type(value) is not str or not value:
        raise ValueError("fixture string is invalid")
    return value


def _positive_exact_integer(value: object) -> int:
    if type(value) is not int or value < 1:
        raise ValueError("fixture integer is invalid")
    return value


def _fixture_utc_datetime(value: object) -> datetime:
    text = _nonempty_exact_string(value)
    if not text.endswith("Z") or text.count("Z") != 1:
        raise ValueError("fixture datetime is invalid")
    try:
        parsed = datetime.fromisoformat(f"{text[:-1]}+00:00")
    except ValueError:
        raise ValueError("fixture datetime is invalid") from None
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise ValueError("fixture datetime is invalid")
    return parsed.astimezone(UTC)


def _exact_unique(values: tuple[str, ...]) -> None:
    if len(values) != len(set(values)):
        raise ValueError("fixture identities are not unique")


@dataclass(frozen=True, slots=True)
class _SessionConfig:
    fixture_ref: str
    opaque_session_id: str
    fixture: P0SessionFixture


@dataclass(frozen=True, slots=True)
class _OrderConfig:
    fixture_ref: str
    owner_customer_id: str
    safe_projection: OrderSummaryProjection


@dataclass(frozen=True, slots=True)
class _FixtureConfig:
    sessions: tuple[_SessionConfig, ...]
    orders: tuple[_OrderConfig, ...]
    sentinel_order_numbers: tuple[str, ...]
    tool_registry_version: str
    redaction_policy_version: str

    def raw_session_id_for_ref(self, fixture_ref: str) -> str:
        matches = tuple(
            item.opaque_session_id
            for item in self.sessions
            if item.fixture_ref == fixture_ref
        )
        if len(matches) != 1:
            raise ValueError("trusted Session fixture reference is invalid")
        return matches[0]


def _parse_session(value: object) -> _SessionConfig:
    raw = _exact_frozen_mapping(value, expected_keys=_SESSION_KEYS)
    fixture_ref = _nonempty_exact_string(raw["fixture_ref"])
    label = _nonempty_exact_string(raw["label"])
    opaque_session_id = _nonempty_exact_string(raw["session_id"])
    trusted_customer_id = _nonempty_exact_string(
        raw["trusted_customer_id"]
    )
    if raw["trust_boundary"] != "SERVER_SIDE_FIXTURE_ONLY":
        raise ValueError("Session fixture trust boundary is invalid")
    if not fixture_ref.startswith("session:"):
        raise ValueError("Session fixture reference is invalid")
    return _SessionConfig(
        fixture_ref=fixture_ref,
        opaque_session_id=opaque_session_id,
        fixture=P0SessionFixture(
            subject_ref=f"fixture-subject:{fixture_ref}:{label}",
            customer_id=trusted_customer_id,
            auth_scopes=frozenset({"orders:read"}),
            expires_at=datetime.max.replace(tzinfo=UTC),
        ),
    )


def _parse_order_line(value: object) -> OrderLineSummary:
    raw = _exact_frozen_mapping(value, expected_keys=_LINE_ITEM_KEYS)
    return OrderLineSummary(
        product_name=_nonempty_exact_string(raw["product_name"]),
        quantity=_positive_exact_integer(raw["quantity"]),
    )


def _parse_order(value: object) -> _OrderConfig:
    raw = _exact_frozen_mapping(value, expected_keys=_ORDER_KEYS)
    fixture_ref = _nonempty_exact_string(raw["fixture_ref"])
    owner_customer_id = _nonempty_exact_string(raw["owner_customer_id"])
    projection = _exact_frozen_mapping(
        raw["safe_projection"],
        expected_keys=_SAFE_PROJECTION_KEYS,
    )
    order_number = _nonempty_exact_string(projection["order_number"])
    if fixture_ref != f"order:{order_number}":
        raise ValueError("Order fixture identity is invalid")
    line_values = _exact_frozen_list(projection["line_items"])
    if not line_values:
        raise ValueError("Order fixture line items are empty")
    try:
        status = OrderStatus(_nonempty_exact_string(projection["status"]))
    except ValueError:
        raise ValueError("Order fixture status is invalid") from None
    return _OrderConfig(
        fixture_ref=fixture_ref,
        owner_customer_id=owner_customer_id,
        safe_projection=OrderSummaryProjection(
            order_number=order_number,
            status=status,
            line_items=tuple(_parse_order_line(item) for item in line_values),
            ordered_at=_fixture_utc_datetime(projection["ordered_at"]),
            status_updated_at=_fixture_utc_datetime(
                projection["status_updated_at"]
            ),
        ),
    )


def _parse_sentinel(value: object) -> tuple[str, str]:
    raw = _exact_frozen_mapping(value, expected_keys=_SENTINEL_KEYS)
    fixture_ref = _nonempty_exact_string(raw["fixture_ref"])
    order_number = _nonempty_exact_string(raw["order_number"])
    if (
        fixture_ref != f"order-sentinel:{order_number}"
        or raw["seed_behavior"] != "MUST_NOT_INSERT"
    ):
        raise ValueError("Order sentinel fixture is invalid")
    return fixture_ref, order_number


def _parse_fixture(artifacts: LoadedE2E01Artifacts) -> _FixtureConfig:
    fixture = _exact_frozen_mapping(
        artifacts.fixture,
        expected_keys=_FIXTURE_ROOT_KEYS,
    )
    if (
        fixture["artifact_type"] != "E2E_FIXTURE"
        or fixture["artifact_id"] != "e2e01-thin-fixture"
        or fixture["schema_version"] != "e2e01-thin-fixture-schema-v1"
        or fixture["fixture_version"] != "e2e01-thin-fixture-v1"
        or fixture["classification"] != "SYNTHETIC_DETERMINISTIC"
    ):
        raise ValueError("fixture root identity is invalid")

    sessions = tuple(
        _parse_session(item)
        for item in _exact_frozen_list(
            fixture["sessions"],
            expected_length=_EXPECTED_FIXTURE_COUNTS["sessions"],
        )
    )
    orders = tuple(
        _parse_order(item)
        for item in _exact_frozen_list(
            fixture["orders"],
            expected_length=_EXPECTED_FIXTURE_COUNTS["orders"],
        )
    )
    sentinels = tuple(
        _parse_sentinel(item)
        for item in _exact_frozen_list(
            fixture["nonexistent_order_sentinels"],
            expected_length=(
                _EXPECTED_FIXTURE_COUNTS["nonexistent_order_sentinels"]
            ),
        )
    )
    versions = _exact_frozen_mapping(
        fixture["versions"],
        expected_keys=_VERSION_KEYS,
    )
    if any(
        versions[key] != expected
        for key, expected in _EXPECTED_VERSION_VALUES.items()
    ):
        raise ValueError("fixture versions are invalid")

    _exact_unique(tuple(item.fixture_ref for item in sessions))
    _exact_unique(tuple(item.opaque_session_id for item in sessions))
    _exact_unique(tuple(item.fixture_ref for item in orders))
    _exact_unique(
        tuple(item.safe_projection.order_number for item in orders)
    )
    _exact_unique(tuple(item[0] for item in sentinels))
    _exact_unique(tuple(item[1] for item in sentinels))

    session_customers = {
        item.fixture.customer_id
        for item in sessions
    }
    if any(item.owner_customer_id not in session_customers for item in orders):
        raise ValueError("Order fixture owner has no trusted Session")
    order_numbers = {
        item.safe_projection.order_number
        for item in orders
    }
    sentinel_order_numbers = {item[1] for item in sentinels}
    if order_numbers & sentinel_order_numbers:
        raise ValueError("Order sentinel overlaps a seeded Order")

    session_refs = {item.fixture_ref for item in sessions}
    order_refs = {item.fixture_ref for item in orders}
    sentinel_refs = {item[0] for item in sentinels}
    for case in artifacts.cases:
        trusted_ref = case.input.get("trusted_context_fixture_ref")
        initial_refs = tuple(
            case.input.get("initial_state_fixture_refs", ())
        )
        environment_refs = tuple(
            case.input.get("environment_fixture_refs", ())
        )
        if (
            type(trusted_ref) is not str
            or trusted_ref not in session_refs
            or initial_refs
            or not set(environment_refs) <= (order_refs | sentinel_refs)
        ):
            raise ValueError("Case fixture ownership is invalid")

    return _FixtureConfig(
        sessions=sessions,
        orders=orders,
        sentinel_order_numbers=tuple(
            item[1] for item in sentinels
        ),
        tool_registry_version=versions["tool_registry_version"],
        redaction_policy_version=versions["redaction_policy_version"],
    )


def _registry_snapshot(tool_registry_version: str) -> RegistrySnapshot:
    return RegistrySnapshot.build(
        tool_registry_version=tool_registry_version,
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


def _project_task(
    task: TaskRecord,
    *,
    changed_at: datetime,
    reason_ref: UUID,
) -> TaskRecord:
    values = {
        field_name: getattr(task, field_name)
        for field_name in TaskRecord.model_fields
    }
    values.update(
        {
            "status": TaskStatus.WAITING_USER,
            "state_version": task.state_version + 1,
            "updated_at": changed_at,
            "last_outcome_ref": reason_ref,
        }
    )
    return TaskRecord(**values)


def _project_request_unit(
    request_unit: RequestUnitRecord,
    *,
    changed_at: datetime,
) -> RequestUnitRecord:
    values = {
        field_name: getattr(request_unit, field_name)
        for field_name in RequestUnitRecord.model_fields
    }
    values.update(
        {
            "status": TaskStatus.WAITING_USER,
            "state_version": request_unit.state_version + 1,
            "updated_at": changed_at,
        }
    )
    return RequestUnitRecord(**values)


class _OwnerCapturingHandler:
    __slots__ = ("_composition", "_service")

    def __init__(
        self,
        *,
        composition: OfflineE2E01Composition,
        service: AgentRunService,
    ) -> None:
        self._composition = composition
        self._service = service

    async def handle(self, command: AgentRunCommand) -> AgentRunResult:
        if type(command) is not AgentRunCommand:
            raise _fresh_composition_error()
        owner_scope = TrustedOwnerScope.from_customer_context(
            command.customer_context
        )
        result = await self._service.handle(command)
        self._composition._bind_owner_scope(
            run_id=result.run_id,
            owner_scope=owner_scope,
        )
        return result


class OfflineE2E01Composition:
    """Started, concrete offline wiring for real E2E01 HTTP/Eval execution."""

    __slots__ = (
        "_artifacts",
        "_clock",
        "_fixture",
        "_get_order",
        "_owner_scope_by_run",
        "_ready",
        "_records",
        "_registry_snapshot",
        "_session_auth",
        "_uuid_factory",
    )

    def __init__(
        self,
        *,
        _start_token: object,
        artifacts: LoadedE2E01Artifacts,
        fixture: _FixtureConfig,
        session_factory: sessionmaker[Session],
        clock: Callable[[], datetime],
        uuid_factory: Callable[[], UUID],
    ) -> None:
        if _start_token is not _START_TOKEN:
            raise _fresh_composition_error()
        self._artifacts = artifacts
        self._fixture = fixture
        self._clock = clock
        self._uuid_factory = uuid_factory
        self._records = PostgresRecordAdapter(session_factory)
        self._get_order = PostgresGetOrderAdapter(session_factory)
        self._session_auth = P0SessionAuthAdapter(
            {
                item.opaque_session_id: item.fixture
                for item in fixture.sessions
            },
            clock=clock,
        )
        self._registry_snapshot = _registry_snapshot(
            fixture.tool_registry_version
        )
        self._owner_scope_by_run: dict[UUID, TrustedOwnerScope] = {}
        self._ready = False

    @classmethod
    async def start(
        cls,
        *,
        artifacts: LoadedE2E01Artifacts,
        session_factory: sessionmaker[Session],
        clock: Callable[[], datetime],
        uuid_factory: Callable[[], UUID] = uuid4,
    ) -> OfflineE2E01Composition:
        setup_failed = False
        fixture: _FixtureConfig | None = None
        try:
            if (
                type(artifacts) is not LoadedE2E01Artifacts
                or not isinstance(session_factory, sessionmaker)
                or not callable(clock)
                or not callable(uuid_factory)
            ):
                raise TypeError("invalid Composition Root dependency")
            fixture = _parse_fixture(artifacts)
        except Exception:
            setup_failed = True
        if setup_failed or fixture is None:
            raise _fresh_composition_error()

        composition: OfflineE2E01Composition | None = None
        recovery: RestartRecoveryService | None = None
        startup_failed = False
        try:
            composition = cls(
                _start_token=_START_TOKEN,
                artifacts=artifacts,
                fixture=fixture,
                session_factory=session_factory,
                clock=clock,
                uuid_factory=uuid_factory,
            )
            recovery = RestartRecoveryService(
                restart_recovery_port=PostgresRestartRecoveryAdapter(
                    session_factory
                ),
                clock=clock,
                uuid_factory=uuid_factory,
            )
            while True:
                result = await recovery.recover_pending()
                if not result.ready:
                    startup_failed = True
                    break
                if not result.closure_found:
                    if result.write_result is not None:
                        startup_failed = True
                    break
                if result.write_result is not RecoveryWriteResult.APPLIED:
                    startup_failed = True
                    break
            if not startup_failed:
                for order in fixture.orders:
                    await composition._get_order.seed_mock_order(
                        customer_id=order.owner_customer_id,
                        order_summary=order.safe_projection,
                    )
        except Exception:
            startup_failed = True
        if startup_failed or composition is None:
            raise _fresh_composition_error()
        composition._ready = True
        return composition

    @property
    def ready(self) -> bool:
        return self._ready

    def _ensure_ready(self) -> None:
        if not self._ready:
            raise _fresh_composition_error()

    def _bind_owner_scope(
        self,
        *,
        run_id: UUID,
        owner_scope: TrustedOwnerScope,
    ) -> None:
        if type(run_id) is not UUID or type(owner_scope) is not TrustedOwnerScope:
            raise _fresh_composition_error()
        existing = self._owner_scope_by_run.get(run_id)
        if existing is not None and existing != owner_scope:
            raise _fresh_composition_error()
        self._owner_scope_by_run[run_id] = owner_scope

    def _runtime_fault_hook(
        self,
        runtime_fault: RuntimeFaultDirective | None,
    ) -> AfterRevalidationHook | None:
        if runtime_fault is None:
            return None
        if (
            type(runtime_fault) is not RuntimeFaultDirective
            or runtime_fault.behavior
            != "ADVANCE_TASK_STATE_AFTER_REVALIDATION_BEFORE_GATE"
            or runtime_fault.boundary != "AFTER_REVALIDATION_BEFORE_GATE"
        ):
            raise _fresh_composition_error()

        async def advance_task_state(
            run_id: UUID,
            task: TaskRecord,
            request_unit: RequestUnitRecord,
        ) -> None:
            changed_at = self._clock()
            reason_ref = self._uuid_factory()
            next_task = _project_task(
                task,
                changed_at=changed_at,
                reason_ref=reason_ref,
            )
            next_unit = _project_request_unit(
                request_unit,
                changed_at=changed_at,
            )
            write_result = (
                await self._records.apply_task_transition_if_current(
                    ApplyTaskTransitionCommand(
                        expected_task_record=task,
                        next_task_record=next_task,
                        expected_request_unit_record=request_unit,
                        next_request_unit_record=next_unit,
                        task_state_transition=TaskStateTransition(
                            task_id=task.task_id,
                            request_unit_id=request_unit.request_unit_id,
                            from_status=task.status,
                            to_status=TaskStatus.WAITING_USER,
                            base_state_version=task.state_version,
                            result_state_version=next_task.state_version,
                            reason_ref=reason_ref,
                            changed_at=changed_at,
                        ),
                    )
                )
            )
            if write_result is not ConditionalWriteResult.APPLIED:
                raise _fresh_composition_error()
            await self._records.append_trace_event(
                TraceEvent(
                    trace_event_id=self._uuid_factory(),
                    event_type=TraceEventType.TASK_STATE_CHANGED,
                    occurred_at=changed_at,
                    run_id=run_id,
                    task_id=task.task_id,
                    request_unit_id=request_unit.request_unit_id,
                )
            )

        return advance_task_state

    def build_case_app(
        self,
        *,
        scripted_provider: ScriptedModelProviderV2,
        runtime_fault: RuntimeFaultDirective | None,
    ) -> FastAPI:
        self._ensure_ready()
        if type(scripted_provider) is not ScriptedModelProviderV2:
            raise _fresh_composition_error()
        try:
            hook = self._runtime_fault_hook(runtime_fault)
        except OfflineCompositionError:
            raise
        return self._build_closed_case_app(
            model_provider=scripted_provider,
            provider_lane="offline_gate",
            after_revalidation_hook=hook,
        )

    def build_qwen_case_app(
        self,
        *,
        qwen_provider: QwenResponsesAdapterV2,
    ) -> FastAPI:
        self._ensure_ready()
        if type(qwen_provider) is not QwenResponsesAdapterV2:
            raise _fresh_composition_error()
        return self._build_closed_case_app(
            model_provider=qwen_provider,
            provider_lane="qwen_baseline",
            after_revalidation_hook=None,
        )

    def _build_closed_case_app(
        self,
        *,
        model_provider: ScriptedModelProviderV2 | QwenResponsesAdapterV2,
        provider_lane: str,
        after_revalidation_hook: AfterRevalidationHook | None,
    ) -> FastAPI:
        if (
            (
                type(model_provider) is ScriptedModelProviderV2
                and (
                    provider_lane != "offline_gate"
                    or (
                        after_revalidation_hook is not None
                        and not callable(after_revalidation_hook)
                    )
                )
            )
            or (
                type(model_provider) is QwenResponsesAdapterV2
                and (
                    provider_lane != "qwen_baseline"
                    or after_revalidation_hook is not None
                )
            )
            or type(model_provider)
            not in {ScriptedModelProviderV2, QwenResponsesAdapterV2}
        ):
            raise _fresh_composition_error()
        service = AgentRunService(
            model_provider=model_provider,
            registry_snapshot=self._registry_snapshot,
            toolset_artifact_port=self._records,
            conversation_record_port=self._records,
            runtime_record_port=self._records,
            read_tool_executor=ReadToolExecutor(
                runtime_record_port=self._records,
                get_order_port=self._get_order,
                clock=self._clock,
                uuid_factory=self._uuid_factory,
            ),
            deterministic_renderer=DeterministicRenderer(),
            clock=self._clock,
            uuid_factory=self._uuid_factory,
            provider_lane=provider_lane,
            redaction_policy_version=(
                self._fixture.redaction_policy_version
            ),
            after_revalidation_hook=after_revalidation_hook,
        )
        return create_agent_app(
            session_auth=self._session_auth,
            handler=_OwnerCapturingHandler(
                composition=self,
                service=service,
            ),
        )

    async def execute_case(
        self,
        *,
        execution_input: EvalCaseExecutionInput,
        scripted_provider: ScriptedModelProviderV2,
        runtime_fault: RuntimeFaultDirective | None,
    ) -> EvalCaseSutResult | None:
        self._ensure_ready()
        input_failed = False
        opaque_session_id: str | None = None
        try:
            if (
                type(execution_input) is not EvalCaseExecutionInput
                or type(scripted_provider) is not ScriptedModelProviderV2
                or (
                    runtime_fault is not None
                    and type(runtime_fault) is not RuntimeFaultDirective
                )
            ):
                raise TypeError("invalid Eval Case execution dependency")
            opaque_session_id = self._fixture.raw_session_id_for_ref(
                execution_input.trusted_context_fixture_ref
            )
            app = self.build_case_app(
                scripted_provider=scripted_provider,
                runtime_fault=runtime_fault,
            )
        except Exception:
            input_failed = True
        if input_failed or opaque_session_id is None:
            raise _fresh_composition_error()
        return await self._execute_http_case(
            execution_input=execution_input,
            opaque_session_id=opaque_session_id,
            app=app,
        )

    async def execute_qwen_case(
        self,
        *,
        execution_input: EvalCaseExecutionInput,
        qwen_provider: QwenResponsesAdapterV2,
    ) -> EvalCaseSutResult | None:
        self._ensure_ready()
        input_failed = False
        opaque_session_id: str | None = None
        app: FastAPI | None = None
        try:
            if (
                type(execution_input) is not EvalCaseExecutionInput
                or type(qwen_provider) is not QwenResponsesAdapterV2
            ):
                raise TypeError("invalid Qwen Case execution dependency")
            opaque_session_id = self._fixture.raw_session_id_for_ref(
                execution_input.trusted_context_fixture_ref
            )
            app = self.build_qwen_case_app(
                qwen_provider=qwen_provider,
            )
        except Exception:
            input_failed = True
        if input_failed or opaque_session_id is None or app is None:
            raise _fresh_composition_error()
        return await self._execute_http_case(
            execution_input=execution_input,
            opaque_session_id=opaque_session_id,
            app=app,
        )

    async def _execute_http_case(
        self,
        *,
        execution_input: EvalCaseExecutionInput,
        opaque_session_id: str,
        app: FastAPI,
    ) -> EvalCaseSutResult | None:
        response: httpx.Response | None = None
        request_failed = False
        try:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
                cookies={"p0_session": opaque_session_id},
            ) as client:
                response = await client.post(
                    "/v1/agent/runs",
                    json={"message": execution_input.messages[0].content},
                )
        except Exception:
            request_failed = True
        if request_failed or response is None:
            raise _fresh_composition_error()

        projection_failed = False
        agent_result: AgentRunResult | None = None
        closure = None
        try:
            agent_result = AgentRunResult.model_validate_json(
                response.content,
                strict=True,
            )
            owner_scope = self._owner_scope_by_run.get(agent_result.run_id)
            if owner_scope is None:
                raise ValueError("Run owner scope was not authenticated")
            closure = await self._records.load_exact_run_evidence_for_owner(
                owner_scope=owner_scope,
                run_id=agent_result.run_id,
            )
            if closure is None:
                raise ValueError("Run evidence closure is unavailable")
            ordered_trace = await self._records.list_trace_events_for_owner(
                owner_scope=owner_scope,
                run_id=agent_result.run_id,
            )
            closure_trace_by_id = {
                event.trace_event_id: event for event in closure.trace_events
            }
            ordered_trace_ids = tuple(
                event.trace_event_id for event in ordered_trace
            )
            ordered_trace_by_id = {
                event.trace_event_id: event for event in ordered_trace
            }
            if (
                len(closure_trace_by_id) != len(closure.trace_events)
                or len(ordered_trace_by_id) != len(ordered_trace)
                or closure_trace_by_id != ordered_trace_by_id
            ):
                raise ValueError("ordered Trace does not match exact closure")
            canonical_ordered_trace = tuple(
                closure_trace_by_id[event_id]
                for event_id in ordered_trace_ids
            )
            closure_fields = {
                field_name: getattr(closure, field_name)
                for field_name in ExactRunEvidenceClosure.model_fields
            }
            closure_fields["trace_events"] = canonical_ordered_trace
            closure = ExactRunEvidenceClosure(**closure_fields)
        except Exception:
            projection_failed = True
        if projection_failed or agent_result is None or closure is None:
            raise _fresh_composition_error()

        return map_exact_run_http_result_to_sut_result(
            execution_ref=execution_input.execution_ref,
            http_status=response.status_code,
            agent_result=agent_result,
            closure=closure,
        )

    async def append_eval_case_graded(self, event: TraceEvent) -> None:
        self._ensure_ready()
        validation_failed = False
        owner_scope: TrustedOwnerScope | None = None
        try:
            if (
                type(event) is not TraceEvent
                or event.event_type is not TraceEventType.EVAL_CASE_GRADED
                or event.case_id is None
            ):
                raise TypeError("invalid EvalCaseGraded event")
            owner_scope = self._owner_scope_by_run.get(event.run_id)
            if owner_scope is None:
                raise ValueError("Run owner scope is unavailable")
            run = await self._records.load_run_for_owner(
                owner_scope=owner_scope,
                run_id=event.run_id,
            )
            if run is None:
                raise ValueError("owner-scoped Run is unavailable")
        except Exception:
            validation_failed = True
        if validation_failed or owner_scope is None:
            raise _fresh_composition_error()
        append_failed = False
        try:
            await self._records.append_trace_event(event)
        except Exception:
            append_failed = True
        if append_failed:
            raise _fresh_composition_error()

    async def reload_trace(
        self,
        trace_ref: UUID,
    ) -> tuple[TraceEvent, ...]:
        self._ensure_ready()
        validation_failed = False
        events: tuple[TraceEvent, ...] | None = None
        try:
            if type(trace_ref) is not UUID:
                raise TypeError("invalid Trace reference")
            owner_scope = self._owner_scope_by_run.get(trace_ref)
            if owner_scope is None:
                raise ValueError("Run owner scope is unavailable")
            events = await self._records.list_trace_events_for_owner(
                owner_scope=owner_scope,
                run_id=trace_ref,
            )
            if not events or any(
                event.run_id != trace_ref for event in events
            ):
                raise ValueError("owner-scoped Trace is unavailable")
        except Exception:
            validation_failed = True
        if validation_failed or events is None:
            raise _fresh_composition_error()
        return events

    def build_harness(
        self,
        *,
        nonce_factory: Callable[[], UUID] = uuid4,
    ) -> OfflineEvalHarness:
        self._ensure_ready()
        if not callable(nonce_factory):
            raise _fresh_composition_error()
        return OfflineEvalHarness(
            artifacts=self._artifacts,
            sut=self,
            trace_callbacks=self,
            result_port=self._records,
            clock=self._clock,
            nonce_factory=nonce_factory,
        )


class _Cycle2OwnerCapturingHandler:
    __slots__ = ("_composition", "_service")

    def __init__(
        self,
        *,
        composition: Cycle2OfflineComposition,
        service: Cycle2AgentRunHandler,
    ) -> None:
        self._composition = composition
        self._service = service

    async def handle(self, command: AgentRunCommand) -> AgentRunResult:
        if type(command) is not AgentRunCommand:
            raise _fresh_composition_error()
        owner_scope = TrustedOwnerScope.from_customer_context(
            command.customer_context
        )
        result = await self._service.handle(command)
        self._composition._bind_owner_scope(
            run_id=result.run_id,
            owner_scope=owner_scope,
        )
        return result


class Cycle2OfflineComposition:
    """Explicit pre-activation wiring for direct Cycle 2 HTTP proofs."""

    __slots__ = (
        "_clock",
        "_get_order",
        "_get_shipment",
        "_owner_scope_by_run",
        "_owner_scopes",
        "_plan",
        "_ready",
        "_records",
        "_registry_snapshot",
        "_search_orders",
        "_session_auth",
        "_uuid_factory",
    )

    def __init__(
        self,
        *,
        _start_token: object,
        plan: ResolvedCycle2SeedPlan,
        session_factory: sessionmaker[Session],
        clock: Callable[[], datetime],
        uuid_factory: Callable[[], UUID],
    ) -> None:
        if _start_token is not _CYCLE2_START_TOKEN:
            raise _fresh_composition_error()
        self._plan = plan
        self._clock = clock
        self._uuid_factory = uuid_factory
        self._records = PostgresRecordAdapter(
            session_factory,
            cycle2_clock=clock,
            cycle2_run_budget_policy=Cycle2RunBudgetPolicyEvidence(
                policy_version="cycle2-offline-composition-budget.p0.v1",
                run_time_budget_ms=30_000,
            ),
            cycle2_session_owners=plan.session_owners_by_hash(),
        )
        self._search_orders = PostgresSearchOrdersAdapter(session_factory)
        self._get_order = PostgresGetOrderAdapter(session_factory)
        self._get_shipment = PostgresGetShipmentAdapter(session_factory)
        self._session_auth = P0SessionAuthAdapter(
            plan.session_fixtures(),
            clock=clock,
        )
        self._registry_snapshot = build_cycle2_registry_snapshot()
        self._owner_scopes: dict[str, TrustedOwnerScope] = {}
        self._owner_scope_by_run: dict[UUID, TrustedOwnerScope] = {}
        self._ready = False

    @classmethod
    async def start(
        cls,
        *,
        fixture_refs: tuple[str, ...],
        session_factory: sessionmaker[Session],
        clock: Callable[[], datetime],
        uuid_factory: Callable[[], UUID] = uuid4,
    ) -> Cycle2OfflineComposition:
        plan: ResolvedCycle2SeedPlan | None = None
        try:
            if (
                type(fixture_refs) is not tuple
                or any(type(ref) is not str or not ref for ref in fixture_refs)
                or not isinstance(session_factory, sessionmaker)
                or not callable(clock)
                or not callable(uuid_factory)
            ):
                raise TypeError("invalid Cycle 2 Composition dependency")
            plan = resolve_cycle2_seed_plan(fixture_refs)
        except Exception:
            raise _fresh_composition_error()

        composition: Cycle2OfflineComposition | None = None
        try:
            composition = cls(
                _start_token=_CYCLE2_START_TOKEN,
                plan=plan,
                session_factory=session_factory,
                clock=clock,
                uuid_factory=uuid_factory,
            )
            owner_scopes: dict[str, TrustedOwnerScope] = {}
            for session_seed in plan.session_seeds:
                context = await composition._session_auth.authenticate(
                    session_seed.opaque_session_id
                )
                if context is None:
                    raise ValueError("trusted Cycle 2 Session is unavailable")
                owner_scope = TrustedOwnerScope.from_customer_context(context)
                existing = owner_scopes.get(owner_scope.customer_id)
                if existing is not None and existing != owner_scope:
                    raise ValueError("Cycle 2 owner scope is ambiguous")
                owner_scopes[owner_scope.customer_id] = owner_scope
            if set(owner_scopes) != {plan.owner_customer_id}:
                raise ValueError("Cycle 2 owner scope escaped seed plan")
            composition._owner_scopes = owner_scopes
            apply_cycle2_seed_plan(session_factory, plan)
            await composition._records.put_toolset_artifact(
                composition._registry_snapshot.artifact()
            )
        except Exception:
            raise _fresh_composition_error()
        if composition is None:
            raise _fresh_composition_error()
        composition._ready = True
        return composition

    @property
    def ready(self) -> bool:
        return self._ready

    @property
    def resolved_seed_plan(self) -> ResolvedCycle2SeedPlan:
        self._ensure_ready()
        return self._plan

    @property
    def registry_snapshot(self) -> RegistrySnapshot:
        self._ensure_ready()
        return self._registry_snapshot

    def _ensure_ready(self) -> None:
        if not self._ready:
            raise _fresh_composition_error()

    def _bind_owner_scope(
        self,
        *,
        run_id: UUID,
        owner_scope: TrustedOwnerScope,
    ) -> None:
        if type(run_id) is not UUID or type(owner_scope) is not TrustedOwnerScope:
            raise _fresh_composition_error()
        expected = self._owner_scopes.get(owner_scope.customer_id)
        if expected != owner_scope:
            raise _fresh_composition_error()
        existing = self._owner_scope_by_run.get(run_id)
        if existing is not None and existing != owner_scope:
            raise _fresh_composition_error()
        self._owner_scope_by_run[run_id] = owner_scope

    def build_case_app(
        self,
        *,
        provider: Cycle2RequestUnderstandingProvider,
    ) -> FastAPI:
        self._ensure_ready()
        if not isinstance(provider, Cycle2RequestUnderstandingProvider):
            raise _fresh_composition_error()
        try:
            business_handler = Cycle2BusinessReadHandler(
                runtime_record_port=self._records,
                search_orders_port=self._search_orders,
                get_order_port=self._get_order,
                get_shipment_port=self._get_shipment,
                owner_scopes=self._owner_scopes,
                clock=self._clock,
                fault_plan=self._plan.attempt_faults,
            )
            service = Cycle2AgentRunHandler(
                runtime_record_port=self._records,
                context_record_port=self._records,
                request_understanding_provider=provider,
                read_tool_executor=Cycle2ReadToolExecutor(
                    runtime_record_port=self._records,
                    handler=business_handler,
                    uuid_factory=self._uuid_factory,
                ),
                deterministic_renderer=DeterministicRenderer(),
                clock=self._clock,
                uuid_factory=self._uuid_factory,
                provider_lane="offline_cycle2",
                redaction_policy_version="redaction-v1",
            )
        except Exception:
            raise _fresh_composition_error()
        return create_agent_app(
            session_auth=self._session_auth,
            handler=_Cycle2OwnerCapturingHandler(
                composition=self,
                service=service,
            ),
        )

    async def load_exact_run_evidence(
        self,
        run_id: UUID,
    ) -> Cycle2ExactRunEvidenceClosure:
        self._ensure_ready()
        closure: Cycle2ExactRunEvidenceClosure | None = None
        try:
            if type(run_id) is not UUID:
                raise TypeError("invalid Cycle 2 Run reference")
            owner_scope = self._owner_scope_by_run.get(run_id)
            if owner_scope is None:
                raise ValueError("Cycle 2 Run owner scope is unavailable")
            closure = await self._records.load_cycle2_exact_run_evidence_for_owner(
                owner_scope=owner_scope,
                run_id=run_id,
            )
        except Exception:
            raise _fresh_composition_error()
        if type(closure) is not Cycle2ExactRunEvidenceClosure:
            raise _fresh_composition_error()
        return closure
