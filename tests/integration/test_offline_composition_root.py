from __future__ import annotations

import inspect
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import httpx
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
from mini_agent.core.presentation import (
    ClosingVariant,
    OpeningVariant,
    PresentationField,
    PresentationPlan,
    PresentationTone,
)
from mini_agent.core.request_understanding import (
    InputAuthority,
    InputCandidate,
    InputSourceKind,
    NextMove,
    NextMoveKind,
    QueryContextualizationCandidateV2,
    ReferenceSourceKindV2,
    ResolvedReferenceCandidateV2,
    RequestUnderstandingOutputV2,
    TaskDeltaCandidate,
    TaskDeltaOperation,
)
from mini_agent.core.trace import (
    AgentOutcome,
    AgentRunRecord,
    AgentRunStatus,
    StopReason,
)
from mini_agent.evaluation.artifacts import load_e2e01_artifacts
from mini_agent.evaluation.harness import (
    EvalCaseExecutionInput,
    EvalExecutionMessage,
)
from mini_agent.evaluation.scripted_provider import ScriptedModelProviderV2
from mini_agent.infrastructure.model.qwen_responses import (
    QwenResponsesAdapterV2,
)
from mini_agent.infrastructure.persistence.database import build_session_factory
from mini_agent.infrastructure.persistence.models import (
    MockOrderModel,
    P0RecordModel,
)
from mini_agent.infrastructure.persistence.postgres import PostgresRecordAdapter

from mini_agent.bootstrap import (
    Cycle2OfflineComposition,
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


async def test_cycle2_composition_rejects_unknown_seed_before_any_write(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    session_factory = build_session_factory(engine)

    with pytest.raises(OfflineCompositionError, match="OFFLINE_COMPOSITION_FAILED"):
        await Cycle2OfflineComposition.start(
            fixture_refs=("fx-not-dispatchable-v1",),
            session_factory=session_factory,
            clock=_MonotonicClock(),
        )

    assert _order_row_count(session_factory) == 0
    assert _record_row_count(session_factory) == 0
    engine.dispose()


def _execution_input(artifacts) -> EvalCaseExecutionInput:
    case = artifacts.case_by_id("E2E01-01")
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


def _scripted_provider(artifacts) -> ScriptedModelProviderV2:
    case = artifacts.case_by_id("E2E01-01")
    script_refs = tuple(case.input["model_script_refs"])
    assert len(script_refs) == 1
    return ScriptedModelProviderV2(
        artifacts.script_by_ref(script_refs[0]),
        script_execution_ref=uuid4(),
    )


def _qwen_request_output(
    raw_input: dict[str, object],
) -> RequestUnderstandingOutputV2:
    message_ref = UUID(str(raw_input["message_ref"]))
    query = str(raw_input["original_query"])
    return RequestUnderstandingOutputV2(
        schema_version="e2e01-thin-v2",
        message_ref=message_ref,
        contextualization=QueryContextualizationCandidateV2(
            text=query,
            resolved_reference_candidates=(
                ResolvedReferenceCandidateV2(
                    name="order_id",
                    candidate_value="O-1001",
                    source_kind=ReferenceSourceKindV2.CURRENT_MESSAGE,
                    source_ref=message_ref,
                    source_quote="O-1001",
                    confidence=1.0,
                ),
            ),
            uncertainties=(),
            source_message_refs=(message_ref,),
        ),
        task_delta_candidates=(
            TaskDeltaCandidate(
                candidate_id=uuid4(),
                operation=TaskDeltaOperation.ADD_GOAL,
                goal_patch="查询订单状态",
                input_candidates=(
                    InputCandidate(
                        name="order_id",
                        candidate_value="O-1001",
                        semantic_role="TARGET_RESOURCE_IDENTIFIER",
                        authority=InputAuthority.USER_CLAIM,
                        source_kind=InputSourceKind.CURRENT_MESSAGE,
                        source_ref=message_ref,
                        source_quote="O-1001",
                        confidence=1.0,
                    ),
                ),
                confidence=1.0,
            ),
        ),
        next_move_candidate=NextMove(
            kind=NextMoveKind.CALL_TOOL,
            requested_tool_name="get_order",
            arguments={"order_id": "O-1001"},
            base_task_state_version=None,
        ),
    )


def _qwen_presentation_plan() -> PresentationPlan:
    return PresentationPlan(
        template_id="ORDER_STATUS_SUMMARY_V1",
        tone=PresentationTone.WARM,
        opening_variant=OpeningVariant.ACKNOWLEDGE,
        field_order=tuple(PresentationField),
        closing_variant=ClosingVariant.OFFER_FOLLOW_UP,
    )


def _qwen_handler(seen: list[str]):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        tool_name = body["tool_choice"]["name"]
        seen.append(tool_name)
        if tool_name == "submit_next_move":
            arguments = _qwen_request_output(
                body["input"],
            ).model_dump(mode="json")
        elif tool_name == "submit_presentation_plan":
            arguments = _qwen_presentation_plan().model_dump(mode="json")
        else:
            raise AssertionError("unexpected Qwen tool request")
        return httpx.Response(
            200,
            json={
                "output": [
                    {
                        "type": "function_call",
                        "name": tool_name,
                        "arguments": json.dumps(arguments),
                    }
                ]
            },
        )

    return handler


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


async def test_qwen_public_seam_is_exact_and_has_no_runtime_fault() -> None:
    scripted_signature = inspect.signature(
        OfflineE2E01Composition.execute_case
    )
    assert tuple(scripted_signature.parameters) == (
        "self",
        "execution_input",
        "scripted_provider",
        "runtime_fault",
    )

    build_signature = inspect.signature(
        OfflineE2E01Composition.build_qwen_case_app
    )
    execute_signature = inspect.signature(
        OfflineE2E01Composition.execute_qwen_case
    )
    assert tuple(build_signature.parameters) == ("self", "qwen_provider")
    assert tuple(execute_signature.parameters) == (
        "self",
        "execution_input",
        "qwen_provider",
    )
    assert "runtime_fault" not in build_signature.parameters
    assert "runtime_fault" not in execute_signature.parameters


async def test_qwen_mock_transport_runs_real_isolated_vertical_path(
    eval_postgres_namespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    session_factory = build_session_factory(engine)
    artifacts = _artifacts()
    handlers = []
    create_agent_app = bootstrap_module.create_agent_app
    external_network_calls = 0

    def capture_handler(*, session_auth, handler):
        handlers.append(handler)
        return create_agent_app(
            session_auth=session_auth,
            handler=handler,
        )

    async def forbidden_external_http(
        *_args: object,
        **_kwargs: object,
    ) -> None:
        nonlocal external_network_calls
        external_network_calls += 1
        raise AssertionError("external HTTP transport is forbidden")

    monkeypatch.setattr(
        bootstrap_module,
        "create_agent_app",
        capture_handler,
    )
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
        seen_by_adapter = ([], [])
        async with (
            httpx.AsyncClient(
                transport=httpx.MockTransport(
                    _qwen_handler(seen_by_adapter[0])
                )
            ) as first_client,
            httpx.AsyncClient(
                transport=httpx.MockTransport(
                    _qwen_handler(seen_by_adapter[1])
                )
            ) as second_client,
        ):
            adapters = (
                QwenResponsesAdapterV2(
                    base_url="https://first-qwen.invalid/v1",
                    api_key="synthetic-secret-one",
                    client=first_client,
                ),
                QwenResponsesAdapterV2(
                    base_url="https://second-qwen.invalid/v1",
                    api_key="synthetic-secret-two",
                    client=second_client,
                ),
            )
            results = (
                await composition.execute_qwen_case(
                    execution_input=_execution_input(artifacts),
                    qwen_provider=adapters[0],
                ),
                await composition.execute_qwen_case(
                    execution_input=_execution_input(artifacts),
                    qwen_provider=adapters[1],
                ),
            )

        assert external_network_calls == 0
        assert seen_by_adapter == (
            ["submit_next_move", "submit_presentation_plan"],
            ["submit_next_move", "submit_presentation_plan"],
        )
        assert len(handlers) == 2
        assert handlers[0] is not handlers[1]
        assert handlers[0]._service is not handlers[1]._service
        assert handlers[0]._service._model_provider is adapters[0]
        assert handlers[1]._service._model_provider is adapters[1]
        assert handlers[0]._service._provider_lane == "qwen_baseline"
        assert handlers[1]._service._provider_lane == "qwen_baseline"
        assert results[0] is not None
        assert results[1] is not None
        assert (
            results[0].evidence.observed_outcome
            is AgentOutcome.COMPLETED
        )
        assert (
            results[1].evidence.observed_outcome
            is AgentOutcome.COMPLETED
        )
        assert (
            results[0].evidence.run_record.provider_lane
            == "qwen_baseline"
        )
        assert (
            results[1].evidence.run_record.provider_lane
            == "qwen_baseline"
        )
        assert len(results[0].evidence.request_understanding_records_v2) == 1
        assert len(results[1].evidence.request_understanding_records_v2) == 1
        assert len(results[0].evidence.observations) == 1
        assert len(results[1].evidence.observations) == 1
        assert (
            results[0].evidence.trace_ref
            != results[1].evidence.trace_ref
        )
        projection = (
            results[0].model_dump_json()
            + results[1].model_dump_json()
        )
        assert "synthetic-secret" not in projection
        assert "first-qwen.invalid" not in projection
        assert "second-qwen.invalid" not in projection
    finally:
        engine.dispose()


async def test_qwen_seam_rejects_non_exact_provider_with_fresh_errors(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    session_factory = build_session_factory(engine)

    class QwenSubclass(QwenResponsesAdapterV2):
        pass

    try:
        composition = await OfflineE2E01Composition.start(
            artifacts=_artifacts(),
            session_factory=session_factory,
            clock=_MonotonicClock(),
            uuid_factory=uuid4,
        )
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(_qwen_handler([]))
        ) as client:
            subclass = QwenSubclass(
                base_url="https://qwen.invalid/v1",
                api_key="raw-secret",
                client=client,
            )
            rejected = (
                object(),
                _scripted_provider(_artifacts()),
                subclass,
            )
            errors = []
            for provider in rejected:
                with pytest.raises(OfflineCompositionError) as captured:
                    composition.build_qwen_case_app(
                        qwen_provider=provider,
                    )
                errors.append(captured.value)

        assert len({id(error) for error in errors}) == len(errors)
        for error in errors:
            assert error.args == ("OFFLINE_COMPOSITION_FAILED",)
            assert error.__cause__ is None
            assert error.__context__ is None
            assert "raw-secret" not in f"{error!s} {error!r}"
    finally:
        engine.dispose()
