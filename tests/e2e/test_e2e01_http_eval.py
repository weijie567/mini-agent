from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select

from mini_agent.application.persistence import P0RecordCode
from mini_agent.application.records import EvalResultStatus
from mini_agent.core.trace import AgentOutcome, TraceEventType
from mini_agent.evaluation.artifacts import load_e2e01_artifacts
from mini_agent.evaluation.harness import (
    EvalCaseExecutionInput,
    EvalExecutionMessage,
)
from mini_agent.evaluation.scripted_provider import ScriptedModelProviderV2
from mini_agent.infrastructure.persistence.database import build_session_factory
from mini_agent.infrastructure.persistence.models import P0RecordModel
from mini_agent.infrastructure.persistence.postgres import PostgresRecordAdapter

from mini_agent.bootstrap import OfflineE2E01Composition


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


async def test_real_http_runtime_postgres_and_eval_gate_pass(
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

        assert outcome.command_passed is True
        assert outcome.execution_failures == ()
        assert tuple(result.case_id for result in outcome.results) == (
            TARGET_CASE_IDS
        )
        assert all(
            result.status is EvalResultStatus.PASS
            for result in outcome.results
        )
        persisted = await records.list_eval_results(eval_run_id=eval_run_id)
        assert persisted == outcome.results
        assert all(
            result.version_manifest.candidate_version
            == "git:5c84e0e170e42853af85526805d904bf12671eaa"
            for result in persisted
        )
        assert all(result.trace_ref is not None for result in persisted)
        for result in persisted:
            assert result.trace_ref is not None
            trace = await composition.reload_trace(result.trace_ref)
            assert trace[-1].event_type is TraceEventType.EVAL_CASE_GRADED
            assert trace[-1].case_id == result.case_id
            assert all(
                event.run_id == result.trace_ref for event in trace
            )
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
            identity_override = await client.post(
                "/v1/agent/runs",
                cookies={"p0_session": RAW_ALICE_SESSION},
                json={
                    "message": "订单 O-1001 状态怎么样？",
                    "customer_id": "customer-B",
                },
            )
            missing = await client.post(
                "/v1/agent/runs",
                json={"message": "订单 O-1001 状态怎么样？"},
            )
            unknown = await client.post(
                "/v1/agent/runs",
                cookies={"p0_session": "raw-unknown-session"},
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
