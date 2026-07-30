from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

import mini_agent.bootstrap as bootstrap_module
from mini_agent.application.records import (
    ConversationRecord,
    CreateRunCommand,
    RecoveryWriteResult,
    TrustedOwnerScope,
)
from mini_agent.application.restart_recovery_service import (
    RestartRecoveryResult,
    RestartRecoveryService,
)
from mini_agent.core.common import freeze_json_value, thaw_json_value
from mini_agent.core.identity import CustomerContext
from mini_agent.core.trace import AgentRunRecord, AgentRunStatus, StopReason
from mini_agent.evaluation.artifacts import load_e2e01_artifacts
from mini_agent.infrastructure.persistence.database import build_session_factory
from mini_agent.infrastructure.persistence.models import (
    MockOrderModel,
    P0RecordModel,
)
from mini_agent.infrastructure.persistence.postgres import PostgresRecordAdapter

from mini_agent.bootstrap import (
    OfflineCompositionError,
    OfflineE2E01Composition,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2030, 1, 1, tzinfo=UTC)

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


def _owner_scope() -> TrustedOwnerScope:
    context = CustomerContext(
        subject_ref="fixture-subject:session:alice",
        customer_id="customer-A",
        auth_scopes=frozenset({"orders:read"}),
        authenticated_at=NOW,
        session_ref_hash="fixture-session-hash",
    )
    return TrustedOwnerScope.from_customer_context(context)


def _order_row_count(session_factory) -> int:
    with session_factory() as session:
        return int(
            session.scalar(select(func.count()).select_from(MockOrderModel))
            or 0
    )


def _record_row_count(session_factory) -> int:
    with session_factory() as session:
        return int(
            session.scalar(select(func.count()).select_from(P0RecordModel))
            or 0
        )


def _tampered_artifacts(mutation: str):
    artifacts = _artifacts()
    raw_fixture = thaw_json_value(artifacts.fixture)
    if mutation == "session_unknown":
        raw_fixture["sessions"][0]["customer_id"] = "customer-B"
    elif mutation == "session_missing":
        raw_fixture["sessions"][0].pop("trust_boundary")
    elif mutation == "session_duplicate":
        raw_fixture["sessions"].append(dict(raw_fixture["sessions"][0]))
    elif mutation == "order_unknown":
        raw_fixture["orders"][0]["private_note"] = "not-allowed"
    elif mutation == "order_missing":
        raw_fixture["orders"][0].pop("owner_customer_id")
    elif mutation == "order_duplicate":
        raw_fixture["orders"].append(dict(raw_fixture["orders"][0]))
    elif mutation == "sentinel_unknown":
        raw_fixture["nonexistent_order_sentinels"][0]["owner"] = "unknown"
    elif mutation == "sentinel_missing":
        raw_fixture["nonexistent_order_sentinels"][0].pop("seed_behavior")
    elif mutation == "sentinel_duplicate":
        raw_fixture["nonexistent_order_sentinels"].append(
            dict(raw_fixture["nonexistent_order_sentinels"][0])
        )
    elif mutation == "sentinel_overlap":
        sentinel = raw_fixture["nonexistent_order_sentinels"][0]
        sentinel["fixture_ref"] = "order-sentinel:O-1001"
        sentinel["order_number"] = "O-1001"
    else:
        raise AssertionError("unknown fixture mutation")
    return artifacts.model_copy(
        update={"fixture": freeze_json_value(raw_fixture)}
    )


@pytest.mark.parametrize(
    "mutation",
    (
        "session_unknown",
        "session_missing",
        "session_duplicate",
        "order_unknown",
        "order_missing",
        "order_duplicate",
        "sentinel_unknown",
        "sentinel_missing",
        "sentinel_duplicate",
        "sentinel_overlap",
    ),
)
async def test_strict_fixture_tamper_fails_before_database_side_effect(
    eval_postgres_namespace,
    mutation: str,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    session_factory = build_session_factory(engine)

    try:
        with pytest.raises(OfflineCompositionError) as captured:
            await OfflineE2E01Composition.start(
                artifacts=_tampered_artifacts(mutation),
                session_factory=session_factory,
                clock=_MonotonicClock(),
                uuid_factory=uuid4,
            )

        error = captured.value
        assert error.args == ("OFFLINE_COMPOSITION_FAILED",)
        assert error.__cause__ is None
        assert error.__context__ is None
        assert "customer-B" not in f"{error!s} {error!r}"
        assert _record_row_count(session_factory) == 0
        assert _order_row_count(session_factory) == 0
    finally:
        engine.dispose()


async def test_startup_recovers_created_run_before_composition_is_ready(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    session_factory = build_session_factory(engine)
    records = PostgresRecordAdapter(session_factory)
    conversation_id = UUID("10000000-0000-4000-8000-000000000001")
    run_id = UUID("10000000-0000-4000-8000-000000000002")
    await records.save_conversation(
        ConversationRecord(
            schema_version="conversation_record.p0.v1",
            conversation_id=conversation_id,
            owner_customer_id="customer-A",
            created_at=NOW,
        )
    )
    await records.insert_run(
        CreateRunCommand(
            created_record=AgentRunRecord(
                run_id=run_id,
                conversation_id=conversation_id,
                status=AgentRunStatus.CREATED,
                provider_lane="offline_gate",
                started_at=NOW,
            )
        )
    )

    try:
        composition = await OfflineE2E01Composition.start(
            artifacts=_artifacts(),
            session_factory=session_factory,
            clock=_MonotonicClock(),
            uuid_factory=uuid4,
        )

        assert composition.ready is True
        recovered = await records.load_run_for_owner(
            owner_scope=_owner_scope(),
            run_id=run_id,
        )
        assert recovered is not None
        assert recovered.status is AgentRunStatus.INCOMPLETE
        assert recovered.stop_reason is StopReason.PROCESS_RESTART_DETECTED
        assert recovered.incomplete_reason == "PROCESS_RESTART_DETECTED"
        assert _order_row_count(session_factory) == 2
    finally:
        engine.dispose()


async def test_non_applied_recovery_result_blocks_readiness_and_seeding(
    eval_postgres_namespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    session_factory = build_session_factory(engine)

    async def conflicting_recovery(
        _self: RestartRecoveryService,
    ) -> RestartRecoveryResult:
        return RestartRecoveryResult(
            ready=False,
            closure_found=True,
            write_result=RecoveryWriteResult.CLOSURE_CONFLICT,
        )

    monkeypatch.setattr(
        RestartRecoveryService,
        "recover_pending",
        conflicting_recovery,
    )
    try:
        with pytest.raises(OfflineCompositionError) as captured:
            await OfflineE2E01Composition.start(
                artifacts=_artifacts(),
                session_factory=session_factory,
                clock=_MonotonicClock(),
                uuid_factory=uuid4,
            )

        assert captured.value.args == ("OFFLINE_COMPOSITION_FAILED",)
        assert captured.value.__cause__ is None
        assert captured.value.__context__ is None
        assert _order_row_count(session_factory) == 0
    finally:
        engine.dispose()


async def test_bootstrap_module_has_no_global_app_provider_or_engine() -> None:
    namespace = vars(bootstrap_module)

    assert "app" not in namespace
    assert "engine" not in namespace
    assert "model_provider" not in namespace
    assert "scripted_provider" not in namespace
    assert all(
        type(value).__name__
        not in {"FastAPI", "Engine", "ScriptedModelProviderV2"}
        for value in namespace.values()
    )
