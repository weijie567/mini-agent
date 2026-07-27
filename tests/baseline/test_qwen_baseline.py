from __future__ import annotations

import os
import socket
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from mini_agent.application.records import EvalResultStatus
from mini_agent.evaluation.artifacts import load_e2e01_artifacts
from mini_agent.evaluation.harness import build_qwen_baseline_preflight


REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.qwen_baseline
def test_qwen_baseline_preflight_is_empty_not_run_and_zero_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    network_calls = 0

    def forbidden_connect(*_args: object, **_kwargs: object) -> None:
        nonlocal network_calls
        network_calls += 1
        raise AssertionError("01-07 baseline preflight cannot access network")

    monkeypatch.setattr(socket.socket, "connect", forbidden_connect)
    artifacts = load_e2e01_artifacts(
        REPO_ROOT,
        candidate_version="candidate:c35687d",
    )
    environment = {
        name: value
        for name in ("DASHSCOPE_API_KEY", "DASHSCOPE_BASE_URL")
        if (value := os.environ.get(name)) is not None
    }
    preflight = build_qwen_baseline_preflight(
        artifacts=artifacts,
        eval_run_id=UUID("00000000-0000-4000-8000-000000000901"),
        case_id="E2E01-01",
        attempt=1,
        environment=environment,
        real_sut=None,
        completed_at=datetime(2026, 7, 27, 10, 0, tzinfo=UTC),
    )

    assert preflight.ready is False
    assert preflight.reason in {
        "MISSING_REQUIRED_ENV",
        "REAL_EVAL_CASE_SUT_NOT_WIRED",
    }
    record = preflight.not_run_record
    assert record is not None
    assert record.lane == "qwen_baseline"
    assert record.status is EvalResultStatus.NOT_RUN
    assert record.observed_outcome is None
    assert record.trace_ref is None
    assert record.grader_results == ()
    assert record.critical_failures == ()
    assert record.latency_summary is None
    assert record.usage_summary is None
    assert network_calls == 0
    pytest.skip(preflight.reason)
