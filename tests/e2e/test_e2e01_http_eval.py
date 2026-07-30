from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select

import mini_agent.bootstrap as bootstrap_module
from mini_agent.application.persistence import P0RecordCode
from mini_agent.application.records import (
    EvalExecutionFailurePhase,
    EvalExecutionSafeErrorCode,
    TrustedOwnerScope,
)
from mini_agent.core.identity import CustomerContext
from mini_agent.core.trace import AgentOutcome, TraceEvent, TraceEventType
from mini_agent.evaluation.artifacts import load_e2e01_artifacts
from mini_agent.evaluation.harness import (
    EvalCaseExecutionInput,
    EvalExecutionMessage,
)
from mini_agent.evaluation.scripted_provider import ScriptedModelProviderV2
from mini_agent.infrastructure.persistence.database import build_session_factory
from mini_agent.infrastructure.persistence.models import P0RecordModel
from mini_agent.infrastructure.persistence.postgres import PostgresRecordAdapter

from mini_agent.bootstrap import (
    OfflineCompositionError,
    OfflineE2E01Composition,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2030, 1, 1, tzinfo=UTC)
TARGET_CASE_IDS = ("E2E01-01", "E2E01-04-A", "E2E01-04-B")
RAW_ALICE_SESSION = "p0-session-alice"

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


def _artifacts():
    return load_e2e01_artifacts(
        REPO_ROOT,
        candidate_version=(
            "git:5c84e0e170e42853af85526805d904bf12671eaa"
        ),
        runtime_version=(
            "git:5c84e0e170e42853af85526805d904bf12671eaa"
        ),
    )


def _execution_input(artifacts, case_id: str) -> EvalCaseExecutionInput:
    case = artifacts.case_by_id(case_id)
    messages = tuple(case.input["messages"])
    assert len(messages) == 1
    return EvalCaseExecutionInput(
        execution_ref=uuid4(),
        messages=(
            EvalExecutionMessage(
                role="user",
                content=messages[0]["content"],
            ),
        ),
        trusted_context_fixture_ref=(
            case.input["trusted_context_fixture_ref"]
        ),
    )


def _provider(artifacts, case_id: str) -> ScriptedModelProviderV2:
    case = artifacts.case_by_id(case_id)
    script_refs = tuple(case.input["model_script_refs"])
    assert len(script_refs) == 1
    return ScriptedModelProviderV2(
        artifacts.script_by_ref(script_refs[0]),
        script_execution_ref=uuid4(),
    )


async def _execute_direct(composition, artifacts, case_id: str):
    provider = _provider(artifacts, case_id)
    return await composition.execute_case(
        execution_input=_execution_input(artifacts, case_id),
        scripted_provider=provider,
        runtime_fault=provider.take_runtime_fault_directive(),
    )


def _assert_bounded_composition_error(error: OfflineCompositionError) -> None:
    assert error.args == ("OFFLINE_COMPOSITION_FAILED",)
    assert error.__cause__ is None
    assert error.__context__ is None


async def test_real_http_runtime_postgres_and_contract_defined_eval_fail_closed(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    session_factory = build_session_factory(engine)
    artifacts = _artifacts()
    records = PostgresRecordAdapter(session_factory)

    try:
        composition = await OfflineE2E01Composition.start(
            artifacts=artifacts,
            session_factory=session_factory,
            clock=_MonotonicClock(),
            uuid_factory=uuid4,
        )

        success = await _execute_direct(
            composition,
            artifacts,
            "E2E01-01",
        )
        foreign = await _execute_direct(
            composition,
            artifacts,
            "E2E01-04-A",
        )
        nonexistent = await _execute_direct(
            composition,
            artifacts,
            "E2E01-04-B",
        )

        assert success is not None
        assert success.evidence.observed_outcome is AgentOutcome.COMPLETED
        assert len(success.evidence.request_understanding_records_v2) == 1
        assert len(success.evidence.accepted_task_deltas_v2) == 1
        assert len(success.evidence.observations) == 1
        assert success.evidence.agent_result is not None
        assert "轻量跑鞋" in success.evidence.agent_result.message

        assert foreign is not None
        assert nonexistent is not None
        assert len(
            {
                success.evidence.trace_ref,
                foreign.evidence.trace_ref,
                nonexistent.evidence.trace_ref,
            }
        ) == 3
        assert foreign.safe_observable == nonexistent.safe_observable
        assert foreign.evidence.observations == ()
        assert nonexistent.evidence.observations == ()
        assert foreign.evidence.agent_result is not None
        assert nonexistent.evidence.agent_result is not None
        assert (
            foreign.evidence.agent_result.message
            == nonexistent.evidence.agent_result.message
        )
        bounded_projection = (
            foreign.model_dump_json() + nonexistent.model_dump_json()
        )
        assert "合成隔离测试商品" not in bounded_projection
        assert "customer-B" not in bounded_projection
        assert "p0-session-bob" not in bounded_projection

        eval_run_id = uuid4()
        outcome = await composition.build_harness(
            nonce_factory=uuid4,
        ).run_lane(
            eval_run_id=eval_run_id,
            case_ids=TARGET_CASE_IDS,
        )

        assert outcome.command_passed is False
        assert outcome.results == ()
        assert tuple(
            failure.case_id for failure in outcome.execution_failures
        ) == TARGET_CASE_IDS
        assert all(
            failure.failure_phase
            is EvalExecutionFailurePhase.CASE_SETUP
            and failure.safe_error_code
            is EvalExecutionSafeErrorCode.CASE_SETUP_FAILED
            and failure.trace_ref is None
            for failure in outcome.execution_failures
        )
        persisted = await records.list_eval_results(eval_run_id=eval_run_id)
        persisted_failures = (
            await records.list_eval_execution_failures(
                eval_run_id=eval_run_id,
            )
        )
        assert persisted == ()
        assert persisted_failures == outcome.execution_failures
        assert all(
            failure.version_manifest.candidate_version
            == "git:5c84e0e170e42853af85526805d904bf12671eaa"
            for failure in persisted_failures
        )
        for direct_result in (success, foreign, nonexistent):
            assert direct_result.evidence.trace_ref is not None
            trace = await composition.reload_trace(
                direct_result.evidence.trace_ref
            )
            assert all(
                event.event_type is not TraceEventType.EVAL_CASE_GRADED
                for event in trace
            )
            assert all(
                event.run_id == direct_result.evidence.trace_ref
                for event in trace
            )
    finally:
        engine.dispose()


async def test_per_case_app_service_and_provider_instances_are_isolated(
    eval_postgres_namespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    session_factory = build_session_factory(engine)
    artifacts = _artifacts()
    handlers = []
    create_agent_app = bootstrap_module.create_agent_app

    def capture_handler(*, session_auth, handler):
        handlers.append(handler)
        return create_agent_app(
            session_auth=session_auth,
            handler=handler,
        )

    monkeypatch.setattr(
        bootstrap_module,
        "create_agent_app",
        capture_handler,
    )
    try:
        composition = await OfflineE2E01Composition.start(
            artifacts=artifacts,
            session_factory=session_factory,
            clock=_MonotonicClock(),
            uuid_factory=uuid4,
        )
        providers = (
            _provider(artifacts, "E2E01-01"),
            _provider(artifacts, "E2E01-04-A"),
        )
        apps = tuple(
            composition.build_case_app(
                scripted_provider=provider,
                runtime_fault=provider.take_runtime_fault_directive(),
            )
            for provider in providers
        )

        assert apps[0] is not apps[1]
        assert handlers[0] is not handlers[1]
        assert handlers[0]._service is not handlers[1]._service
        assert handlers[0]._service._model_provider is providers[0]
        assert handlers[1]._service._model_provider is providers[1]
    finally:
        engine.dispose()


async def test_same_id_different_trace_payload_is_rejected_before_mapping(
    eval_postgres_namespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    session_factory = build_session_factory(engine)
    artifacts = _artifacts()
    original_reader = PostgresRecordAdapter.list_trace_events_for_owner

    async def mismatched_trace(self, *, owner_scope, run_id):
        events = await original_reader(
            self,
            owner_scope=owner_scope,
            run_id=run_id,
        )
        poisoned = events[0].model_copy(
            update={
                "occurred_at": events[0].occurred_at
                + timedelta(seconds=1)
            }
        )
        return (poisoned, *events[1:])

    monkeypatch.setattr(
        PostgresRecordAdapter,
        "list_trace_events_for_owner",
        mismatched_trace,
    )
    try:
        composition = await OfflineE2E01Composition.start(
            artifacts=artifacts,
            session_factory=session_factory,
            clock=_MonotonicClock(),
            uuid_factory=uuid4,
        )
        with pytest.raises(OfflineCompositionError) as captured:
            await _execute_direct(
                composition,
                artifacts,
                "E2E01-01",
            )

        _assert_bounded_composition_error(captured.value)
    finally:
        engine.dispose()


async def test_missing_exact_closure_is_rejected_after_http_execution(
    eval_postgres_namespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    session_factory = build_session_factory(engine)
    artifacts = _artifacts()

    async def missing_closure(_self, *, owner_scope, run_id):
        return None

    monkeypatch.setattr(
        PostgresRecordAdapter,
        "load_exact_run_evidence_for_owner",
        missing_closure,
    )
    try:
        composition = await OfflineE2E01Composition.start(
            artifacts=artifacts,
            session_factory=session_factory,
            clock=_MonotonicClock(),
            uuid_factory=uuid4,
        )
        with pytest.raises(OfflineCompositionError) as captured:
            await _execute_direct(
                composition,
                artifacts,
                "E2E01-01",
            )

        _assert_bounded_composition_error(captured.value)
    finally:
        engine.dispose()


async def test_trace_callbacks_reject_unknown_owner_and_mismatched_run(
    eval_postgres_namespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    session_factory = build_session_factory(engine)
    artifacts = _artifacts()

    try:
        composition = await OfflineE2E01Composition.start(
            artifacts=artifacts,
            session_factory=session_factory,
            clock=_MonotonicClock(),
            uuid_factory=uuid4,
        )
        unknown_event = TraceEvent(
            trace_event_id=uuid4(),
            event_type=TraceEventType.EVAL_CASE_GRADED,
            occurred_at=NOW,
            run_id=uuid4(),
            case_id="E2E01-01",
        )
        with pytest.raises(OfflineCompositionError) as unknown_captured:
            await composition.append_eval_case_graded(unknown_event)
        _assert_bounded_composition_error(unknown_captured.value)

        result = await _execute_direct(
            composition,
            artifacts,
            "E2E01-01",
        )
        assert result is not None
        run_id = result.evidence.trace_ref
        assert run_id is not None
        alice_scope = composition._owner_scope_by_run[run_id]
        composition._owner_scope_by_run[run_id] = (
            TrustedOwnerScope.from_customer_context(
                CustomerContext(
                    subject_ref="fixture-subject:session:bob",
                    customer_id="customer-B",
                    auth_scopes=frozenset({"orders:read"}),
                    authenticated_at=NOW,
                    session_ref_hash="fixture-session-bob-hash",
                )
            )
        )
        wrong_owner_event = unknown_event.model_copy(
            update={
                "trace_event_id": uuid4(),
                "run_id": run_id,
            }
        )
        with pytest.raises(OfflineCompositionError) as owner_captured:
            await composition.append_eval_case_graded(wrong_owner_event)
        _assert_bounded_composition_error(owner_captured.value)

        composition._owner_scope_by_run[run_id] = alice_scope
        original_reader = PostgresRecordAdapter.list_trace_events_for_owner

        async def mismatched_run(self, *, owner_scope, run_id):
            events = await original_reader(
                self,
                owner_scope=owner_scope,
                run_id=run_id,
            )
            return (
                events[0].model_copy(update={"run_id": uuid4()}),
                *events[1:],
            )

        monkeypatch.setattr(
            PostgresRecordAdapter,
            "list_trace_events_for_owner",
            mismatched_run,
        )
        with pytest.raises(OfflineCompositionError) as trace_captured:
            await composition.reload_trace(run_id)
        _assert_bounded_composition_error(trace_captured.value)
    finally:
        engine.dispose()


async def test_composed_http_rejects_identity_fields_and_bad_sessions_before_run(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    session_factory = build_session_factory(engine)
    artifacts = _artifacts()

    try:
        composition = await OfflineE2E01Composition.start(
            artifacts=artifacts,
            session_factory=session_factory,
            clock=_MonotonicClock(),
            uuid_factory=uuid4,
        )
        provider = _provider(artifacts, "E2E01-01")
        app = composition.build_case_app(
            scripted_provider=provider,
            runtime_fault=provider.take_runtime_fault_directive(),
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            client.cookies.set("p0_session", RAW_ALICE_SESSION)
            identity_override = await client.post(
                "/v1/agent/runs",
                json={
                    "message": "订单 O-1001 状态怎么样？",
                    "customer_id": "customer-B",
                },
            )
            client.cookies.clear()
            missing = await client.post(
                "/v1/agent/runs",
                json={"message": "订单 O-1001 状态怎么样？"},
            )
            client.cookies.set("p0_session", "raw-unknown-session")
            unknown = await client.post(
                "/v1/agent/runs",
                json={"message": "订单 O-1001 状态怎么样？"},
            )

        assert identity_override.status_code == 422
        assert missing.status_code == 401
        assert unknown.status_code == 401
        response_projection = (
            identity_override.text + missing.text + unknown.text
        )
        assert RAW_ALICE_SESSION not in response_projection
        assert "raw-unknown-session" not in response_projection
        with session_factory() as session:
            run_count = session.scalar(
                select(func.count())
                .select_from(P0RecordModel)
                .where(
                    P0RecordModel.record_code
                    == P0RecordCode.AGENT_RUN_RECORD.value
                )
            )
        assert run_count == 0
    finally:
        engine.dispose()
