from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest

from mini_agent.application.records import (
    EvalResultStatus,
)
from mini_agent.bootstrap import OfflineE2E01Composition
from mini_agent.evaluation.artifacts import load_e2e01_artifacts
from mini_agent.evaluation.harness import OfflineEvalHarness
from mini_agent.infrastructure.persistence.database import (
    build_session_factory,
)
from mini_agent.infrastructure.persistence.postgres import (
    PostgresRecordAdapter,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2030, 1, 1, tzinfo=UTC)

pytestmark = [pytest.mark.anyio, pytest.mark.qwen_baseline]


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


async def test_qwen_baseline_uses_real_composition_or_persists_not_run(
    eval_postgres_namespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    session_factory = build_session_factory(engine)
    artifacts = load_e2e01_artifacts(
        REPO_ROOT,
        candidate_version=(
            "git:c59eaea8bac2b25cc936eb2f47af15b6da1d2595"
        ),
        runtime_version=(
            "git:c59eaea8bac2b25cc936eb2f47af15b6da1d2595"
        ),
    )
    environment = {
        name: value
        for name in ("DASHSCOPE_API_KEY", "DASHSCOPE_BASE_URL")
        if (value := os.environ.get(name)) is not None
    }
    missing_environment = any(
        not isinstance(environment.get(name), str)
        or not environment[name].strip()
        for name in ("DASHSCOPE_API_KEY", "DASHSCOPE_BASE_URL")
    )
    network_calls = 0
    if missing_environment:
        async def forbidden_external_http(
            *_args: object,
            **_kwargs: object,
        ) -> None:
            nonlocal network_calls
            network_calls += 1
            raise AssertionError("missing baseline cannot access network")

        monkeypatch.setattr(
            httpx.AsyncHTTPTransport,
            "handle_async_request",
            forbidden_external_http,
        )

    try:
        composition = await OfflineE2E01Composition.start(
            artifacts=artifacts,
            session_factory=session_factory,
            clock=_MonotonicClock(),
            uuid_factory=uuid4,
        )
        records = PostgresRecordAdapter(session_factory)
        eval_run_id = UUID("00000000-0000-4000-8000-000000000901")
        harness = OfflineEvalHarness(
            artifacts=artifacts,
            sut=composition,
            qwen_sut=composition,
            trace_callbacks=composition,
            result_port=records,
            clock=_MonotonicClock(),
            nonce_factory=uuid4,
        )
        outcome = await harness.run_qwen_baseline(
            eval_run_id=eval_run_id,
            environment=environment,
        )
        persisted = await records.list_eval_results(
            eval_run_id=eval_run_id,
        )

        assert persisted == outcome.results
        assert tuple(result.case_id for result in persisted) == (
            "E2E01-01",
            "E2E01-04-A",
            "E2E01-04-B",
        )
        if missing_environment:
            assert outcome.command_passed is False
            assert outcome.execution_failures == ()
            assert network_calls == 0
            for result in persisted:
                assert result.status is EvalResultStatus.NOT_RUN
                assert result.observed_outcome is None
                assert result.trace_ref is None
                assert result.grader_results == ()
                assert result.critical_failures == ()
                assert result.latency_summary is None
                assert result.usage_summary is None
            pytest.skip("MISSING_REQUIRED_ENV")

        assert network_calls == 0
        assert outcome.execution_failures == ()
        assert all(
            result.status in {EvalResultStatus.PASS, EvalResultStatus.FAIL}
            for result in persisted
        )
        critical_failures = tuple(
            failure
            for result in persisted
            for failure in result.critical_failures
        )
        assert critical_failures == ()
    finally:
        engine.dispose()
