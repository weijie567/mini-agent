from __future__ import annotations

import asyncio
import sys
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text, update

from mini_agent.application.persistence import (
    P0PersistenceIntegrityError,
    P0RecordCode,
)
from mini_agent.application.records import (
    AgentRunCommand,
    ConditionalWriteResult,
    CreateRunCommand,
    Cycle2WriteResult,
    InsertOnlyWriteResult,
    MessageDirection,
    MessageRecord,
    RunTaskLinkRecordV2,
    SaveRejectedContinuationUnderstandingV3Command,
    StartCycle2RunCommand,
    TransitionRunCommand,
    TrustedOwnerScope,
)
from mini_agent.core.memory import ContextManifest, TokenCounts
from mini_agent.core.request_processing import (
    RejectedCycle2ContinuationDecisionV3,
    RequestUnderstandingClosureV3,
)
from mini_agent.core.task_state import (
    CandidateRejectionReasonCode,
    CandidateValidationDecision,
    CandidateValidationRecordV2,
    TaskStateTransition,
    TaskStatus,
)
from mini_agent.core.trace import (
    AgentRunRecord,
    AgentRunRecordV2,
    AgentRunStatus,
    AgentRunStatusV2,
    StopReasonV2,
)
from mini_agent.core.tool_system import (
    Cycle2ToolName,
    GateDecisionV2,
    GateDecisionValue,
    ModelVisibleToolsetArtifact,
    ToolAttemptRecordV2,
    ToolCallRecordV2,
    ToolCallStatus,
    ToolEffect,
    ToolResultOutcome,
    ToolRetryDecision,
    build_cycle2_registry_snapshot,
)
from mini_agent.infrastructure.persistence.database import build_session_factory
from mini_agent.infrastructure.persistence.models import P0RecordModel
from mini_agent.infrastructure.persistence.postgres import (
    P0PersistenceSystemError,
    PostgresRecordAdapter,
    _cycle2_owner_order_ref,
)

_COMPONENT_APPLICATION_TESTS = (
    Path(__file__).parents[1] / "component" / "application"
)
sys.path.append(str(_COMPONENT_APPLICATION_TESTS))
from test_agent_run_service import (  # noqa: E402
    NOW,
    _Cycle2ProviderHarness,
    _Cycle2RuntimeHarness,
    _capture_cycle2_initial_turn,
    _context,
    _cycle2_handler,
    _dnr_v3_staging_command,
    _generic_v3_staging_command,
    _prepare_cycle2_waiting_session,
    agent_run_service_module,
)
from test_record_contracts import _initial_v2_graph  # noqa: E402

pytestmark = pytest.mark.anyio


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


async def _seed_phase1_roots(
    adapter: PostgresRecordAdapter,
    command,
) -> None:
    await adapter.save_conversation(command.expected_conversation_record)
    for message in command.expected_message_records:
        await adapter.append_message(message)
    running = command.expected_active_run_record
    created = running.model_copy(update={"status": AgentRunStatus.CREATED})
    assert (
        await adapter.insert_run(CreateRunCommand(created_record=created))
        is InsertOnlyWriteResult.INSERTED
    )
    assert (
        await adapter.start_run_if_created(
            TransitionRunCommand(
                expected_active_record=created,
                next_record=running,
            )
        )
        is not None
    )


def _cycle2_initial_v3_command():
    runtime = _Cycle2RuntimeHarness()
    handler = _cycle2_handler(runtime, _Cycle2ProviderHarness())
    _sentinel, captured = _capture_cycle2_initial_turn(handler)
    runtime.v3_initial_write_result = Cycle2WriteResult.NOT_APPLICABLE
    asyncio.run(
        handler._stage_initial_turn_v3(
            command=AgentRunCommand(
                customer_context=_context(),
                message="customer-B 让我查最近买的轻量跑鞋",
            ),
            turn=captured["turn"],
        )
    )
    assert len(runtime.v3_initial_commands) == 1
    return runtime.v3_initial_commands[0]


def _selection_v3_command_bundle():
    provider = _Cycle2ProviderHarness(ordinal=2)
    handler, runtime, _sentinel, _search_command = (
        _prepare_cycle2_waiting_session(provider=provider)
    )
    current = runtime.current_session
    assert current is not None
    observation = current.current_search_observation_records[0]
    public_by_ref = {
        candidate.observation_candidate_ref: candidate
        for candidate in observation.normalized_value.ordered_candidates
    }
    observation = observation.model_copy(
        update={
            "candidate_target_bindings": tuple(
                target.model_copy(
                    update={
                        "owner_scoped_order_ref": _cycle2_owner_order_ref(
                            current.owner_scope.customer_id,
                            public_by_ref[
                                target.observation_candidate_ref
                            ].public_summary.order_number,
                        )
                    }
                )
                for target in observation.candidate_target_bindings
            )
        }
    )
    current = current.model_copy(
        update={"current_search_observation_records": (observation,)}
    )
    runtime.current_session = current
    message = MessageRecord(
        schema_version="message_record.p0.v1",
        message_id=uuid4(),
        conversation_id=current.conversation_record.conversation_id,
        direction=MessageDirection.USER,
        content="第二个",
        received_at=NOW,
    )
    running = AgentRunRecordV2(
        run_id=uuid4(),
        conversation_id=current.conversation_record.conversation_id,
        status=AgentRunStatusV2.RUNNING,
        provider_lane="scripted-cycle2",
        started_at=NOW,
    )
    link = RunTaskLinkRecordV2(
        run_id=running.run_id,
        task_id=current.current_task_record.task_id,
        base_task_state_version=current.current_task_record.state_version,
    )
    turn = agent_run_service_module._Cycle2Turn(
        owner_scope=current.owner_scope,
        conversation=current.conversation_record,
        user_message=message,
        running_run=running,
        active_link=link,
        request_input=handler._request_input(
            run=running,
            message=message,
            current_session=current,
        ),
        tool_progress=[],
    )
    runtime.v3_saved_user_message = message
    runtime.v3_running_run = running
    runtime.v3_active_link = link
    asyncio.run(
        handler._stage_continuation_turn_v3(
            command=AgentRunCommand(
                customer_context=_context(),
                message=message.content,
            ),
            turn=turn,
            current_session=current,
        )
    )
    assert len(runtime.v3_selection_commands) == 1
    return runtime.v3_selection_commands[0], current


def _seed_cycle2_initial_roots(
    adapter: PostgresRecordAdapter,
    command,
) -> None:
    with adapter.session_factory.begin() as session:
        adapter._cycle2_insert(
            session,
            (
                adapter._cycle2_encode(
                    P0RecordCode.CONVERSATION_RECORD,
                    command.expected_conversation_record,
                ),
                adapter._cycle2_encode(
                    P0RecordCode.MESSAGE_RECORD,
                    command.expected_user_message_record,
                ),
                adapter._cycle2_encode(
                    P0RecordCode.AGENT_RUN_RECORD,
                    command.expected_running_run_record,
                ),
            ),
            owner_customer_id=command.owner_scope.customer_id,
        )


def _seed_continuation_roots(
    adapter: PostgresRecordAdapter,
    command,
) -> None:
    loaded = command.loaded_closure
    record = command.decision.closure.record
    historical_message_refs = {
        *loaded.current_request_unit_record.goal_source_refs,
        *(
            source_ref
            for binding in loaded.current_input_binding_records
            for source_ref in binding.source_refs
        ),
    } - {loaded.saved_user_message_record.message_id}
    historical_messages = tuple(
        loaded.saved_user_message_record.model_copy(
            update={
                "message_id": message_ref,
                "content": "historical task source",
            }
        )
        for message_ref in sorted(historical_message_refs, key=str)
    )
    running = AgentRunRecordV2(
        run_id=record.run_id,
        conversation_id=loaded.trusted_conversation_record.conversation_id,
        status=AgentRunStatusV2.RUNNING,
        provider_lane="scripted-cycle2",
        started_at=loaded.saved_user_message_record.received_at,
    )
    run_link = RunTaskLinkRecordV2(
        run_id=running.run_id,
        task_id=loaded.current_task_record.task_id,
        base_task_state_version=loaded.current_task_record.state_version,
    )
    with adapter.session_factory.begin() as session:
        adapter._cycle2_insert(
            session,
            (
                adapter._cycle2_encode(
                    P0RecordCode.CONVERSATION_RECORD,
                    loaded.trusted_conversation_record,
                ),
                adapter._cycle2_encode(
                    P0RecordCode.MESSAGE_RECORD,
                    loaded.saved_user_message_record,
                ),
                *(
                    adapter._cycle2_encode(
                        P0RecordCode.MESSAGE_RECORD,
                        message,
                    )
                    for message in historical_messages
                ),
                adapter._cycle2_encode(
                    P0RecordCode.AGENT_RUN_RECORD,
                    running,
                ),
                adapter._cycle2_encode(
                    P0RecordCode.TASK_RECORD,
                    loaded.current_task_record,
                ),
                adapter._cycle2_encode(
                    P0RecordCode.REQUEST_UNIT_RECORD,
                    loaded.current_request_unit_record,
                ),
                *(
                    adapter._cycle2_encode_input_binding(
                        binding,
                        request_unit_id=(
                            loaded.current_request_unit_record.request_unit_id
                        ),
                    )
                    for binding in loaded.current_input_binding_records
                ),
                adapter._cycle2_encode(
                    P0RecordCode.CONVERSATION_TASK_LINK_RECORD,
                    loaded.current_conversation_task_link_record,
                ),
                adapter._cycle2_encode(
                    P0RecordCode.RUN_TASK_LINK_RECORD,
                    run_link,
                ),
            ),
            owner_customer_id=loaded.owner_scope.customer_id,
        )


def _selection_supporting_records(command):
    closure = command.loaded_closure
    snapshot = build_cycle2_registry_snapshot()
    artifact = ModelVisibleToolsetArtifact(
        model_visible_toolset_hash=snapshot.model_visible_toolset_hash,
        provider_visible_tool_specs=snapshot.provider_visible_toolset,
    )
    model_call_id = uuid4()
    context_manifest_id = uuid4()
    gate_decision_id = uuid4()
    binding_ref = closure.current_query_binding.binding_ref
    manifest = ContextManifest(
        context_manifest_id=context_manifest_id,
        run_id=closure.current_run_record.run_id,
        model_call_id=model_call_id,
        tool_registry_version=snapshot.tool_registry_version,
        model_visible_toolset_hash=snapshot.model_visible_toolset_hash,
        selected_message_refs=(
            closure.current_query_binding.source_message_record.message_id,
        ),
        redaction_policy_version="redaction-v1",
        token_counts=TokenCounts(input_tokens=None, output_tokens=None),
        assembled_at=closure.trusted_now,
    )
    gate = GateDecisionV2(
        gate_decision_id=gate_decision_id,
        model_call_id=model_call_id,
        context_manifest_id=context_manifest_id,
        requested_provider_tool_name=Cycle2ToolName.SEARCH_ORDERS.value,
        resolved_canonical_tool_name=Cycle2ToolName.SEARCH_ORDERS.value,
        snapshot_match=True,
        registration_valid=True,
        schema_valid=True,
        trusted_field_valid=True,
        argument_binding_valid=True,
        argument_binding_refs=(binding_ref,),
        budget_valid=True,
        progress_valid=True,
        validated_task_state_version=(
            closure.current_candidate_set_record.base_task_state_version
        ),
        state_version_valid=True,
        action_boundary_valid=True,
        decision=GateDecisionValue.ACCEPT,
        decided_at=closure.trusted_now,
        validated_arguments={"product_description": "轻量跑鞋"},
    )
    tool_call_id = closure.current_candidate_set_record.source_tool_call_id
    attempt = ToolAttemptRecordV2(
        tool_call_id=tool_call_id,
        attempt_no=1,
        started_at=closure.trusted_now,
        finished_at=closure.trusted_now,
        outcome=ToolResultOutcome.SUCCESS,
        retry_decision=ToolRetryDecision.NOT_APPLICABLE,
    )
    tool_call = ToolCallRecordV2(
        tool_call_id=tool_call_id,
        run_id=closure.current_run_record.run_id,
        task_id=closure.current_task_record.task_id,
        request_unit_id=closure.current_request_unit_record.request_unit_id,
        model_call_id=model_call_id,
        context_manifest_id=context_manifest_id,
        gate_decision_id=gate_decision_id,
        canonical_tool_name=Cycle2ToolName.SEARCH_ORDERS,
        tool_registry_version=snapshot.tool_registry_version,
        private_owner_scope_ref=closure.owner_scope.customer_id,
        validated_task_state_version=(
            closure.current_candidate_set_record.base_task_state_version
        ),
        argument_binding_refs=(binding_ref,),
        effect=ToolEffect.READ,
        attempt_count=1,
        attempts=(attempt,),
        status=ToolCallStatus.SUCCEEDED,
        started_at=closure.trusted_now,
        finished_at=closure.trusted_now,
        result_ref=closure.search_observation_record.observation_id,
    )
    return artifact, manifest, gate, tool_call


async def _seed_selection_roots(
    adapter: PostgresRecordAdapter,
    command,
    current,
) -> None:
    closure = command.loaded_closure
    artifact, manifest, gate, tool_call = _selection_supporting_records(command)
    await adapter.put_toolset_artifact(artifact)
    with adapter.session_factory.begin() as session:
        adapter._cycle2_insert(
            session,
            (
                adapter._cycle2_encode(
                    P0RecordCode.CONVERSATION_RECORD,
                    closure.trusted_conversation_record,
                ),
                adapter._cycle2_encode(
                    P0RecordCode.MESSAGE_RECORD,
                    closure.current_query_binding.source_message_record,
                ),
                adapter._cycle2_encode(
                    P0RecordCode.MESSAGE_RECORD,
                    closure.saved_selection_message_record,
                ),
                adapter._cycle2_encode(
                    P0RecordCode.AGENT_RUN_RECORD,
                    closure.current_run_record,
                ),
                adapter._cycle2_encode(
                    P0RecordCode.TASK_RECORD,
                    closure.current_task_record,
                ),
                adapter._cycle2_encode(
                    P0RecordCode.REQUEST_UNIT_RECORD,
                    closure.current_request_unit_record,
                ),
                adapter._cycle2_encode_input_binding(
                    current.current_input_binding_records[0],
                    request_unit_id=(
                        closure.current_request_unit_record.request_unit_id
                    ),
                ),
                adapter._cycle2_encode(
                    P0RecordCode.CONVERSATION_TASK_LINK_RECORD,
                    current.current_conversation_task_link_record,
                ),
                adapter._cycle2_encode(
                    P0RecordCode.RUN_TASK_LINK_RECORD,
                    closure.current_run_task_link_record,
                ),
                adapter._cycle2_encode(
                    P0RecordCode.CONTEXT_MANIFEST_RECORD,
                    manifest,
                ),
                adapter._cycle2_encode(
                    P0RecordCode.GATE_DECISION_RECORD,
                    gate,
                ),
                adapter._cycle2_encode(
                    P0RecordCode.TOOL_CALL_RECORD,
                    tool_call,
                    logical_children=tool_call.attempts,
                ),
                adapter._cycle2_encode(
                    P0RecordCode.ORDER_SEARCH_OBSERVATION_RECORD,
                    closure.search_observation_record,
                ),
                adapter._cycle2_encode(
                    P0RecordCode.ORDER_CANDIDATE_SET_RECORD,
                    closure.current_candidate_set_record,
                ),
            ),
            owner_customer_id=closure.owner_scope.customer_id,
        )


def _rejected_continuation_command():
    accepted = _dnr_v3_staging_command()
    record = accepted.decision.closure.record
    candidate = record.task_delta_candidates[0]
    rejected_record = record.model_copy(
        update={
            "candidate_validation": (
                CandidateValidationRecordV2(
                    candidate_ref=candidate.candidate_id,
                    decision=CandidateValidationDecision.REJECT,
                    reason_code=(
                        CandidateRejectionReasonCode.INPUT_VALUE_INVALID
                    ),
                ),
            ),
            "accepted_delta_refs": (),
        }
    )
    return SaveRejectedContinuationUnderstandingV3Command(
        loaded_closure=accepted.loaded_closure,
        decision=RejectedCycle2ContinuationDecisionV3(
            closure=RequestUnderstandingClosureV3(
                record=rejected_record,
                accepted_task_deltas=(),
            )
        ),
    )


def _ru_counts(adapter: PostgresRecordAdapter) -> tuple[int, int]:
    with adapter.session_factory() as session:
        return tuple(
            session.scalar(
                select(func.count())
                .select_from(P0RecordModel)
                .where(
                    P0RecordModel.record_code
                    == P0RecordCode.REQUEST_UNDERSTANDING_RECORD.value,
                    P0RecordModel.record_schema_version == version,
                )
            )
            for version in (
                "request_understanding_record.p0.v2",
                "request_understanding_record.p0.v3",
            )
        )


@pytest.mark.parametrize(
    "candidate_values",
    ((), ("BAD",), ("O-1001",), ("O-1001", "O-1002")),
)
async def test_generic_v3_writers_are_identity_first_and_exact(
    postgres_namespace_factory,
    candidate_values: tuple[str, ...],
) -> None:
    namespace = postgres_namespace_factory.create(
        f"ru-v3-generic-{len(candidate_values)}-{uuid4().hex[:6]}"
    )
    adapter = PostgresRecordAdapter(
        build_session_factory(namespace.build_engine())
    )
    command = _generic_v3_staging_command(candidate_values)
    try:
        await _seed_phase1_roots(adapter, command)
        if hasattr(command, "accepted_task_graphs"):
            first = await adapter.create_initial_task_graph_v3_if_current(command)
            replay = await adapter.create_initial_task_graph_v3_if_current(command)
        else:
            first = await adapter.save_request_understanding_v3_no_task_if_current(
                command
            )
            replay = await adapter.save_request_understanding_v3_no_task_if_current(
                command
            )
        assert first is Cycle2WriteResult.APPLIED
        assert replay is Cycle2WriteResult.ALREADY_APPLIED
        evidence = await adapter.load_exact_run_evidence_v3_for_owner(
            owner_scope=command.owner_scope,
            run_id=command.expected_active_run_record.run_id,
        )
        assert evidence is not None
        assert evidence.request_understanding_closure == (
            command.request_understanding
        )
        assert _ru_counts(adapter) == (0, 1)
        assert await adapter.assert_request_understanding_v3_ready() is None
    finally:
        postgres_namespace_factory.drop(namespace)


async def test_same_v3_identity_concurrent_first_write_is_one_apply_one_replay(
    postgres_namespace_factory,
) -> None:
    namespace = postgres_namespace_factory.create("ru-v3-concurrent-replay")
    adapter = PostgresRecordAdapter(
        build_session_factory(namespace.build_engine())
    )
    command = _generic_v3_staging_command(())
    try:
        await _seed_phase1_roots(adapter, command)

        def write_once() -> Cycle2WriteResult:
            return asyncio.run(
                adapter.save_request_understanding_v3_no_task_if_current(
                    command
                )
            )

        loop = asyncio.get_running_loop()
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = await asyncio.gather(
                *(loop.run_in_executor(executor, write_once) for _ in range(2))
            )

        assert sorted(result.value for result in results) == [
            Cycle2WriteResult.ALREADY_APPLIED.value,
            Cycle2WriteResult.APPLIED.value,
        ]
        assert _ru_counts(adapter) == (0, 1)
    finally:
        postgres_namespace_factory.drop(namespace)


async def test_v3_identity_mutation_conflicts_before_any_effect(
    postgres_namespace_factory,
) -> None:
    namespace = postgres_namespace_factory.create("ru-v3-mutated-replay")
    adapter = PostgresRecordAdapter(
        build_session_factory(namespace.build_engine())
    )
    command = _generic_v3_staging_command(())
    try:
        await _seed_phase1_roots(adapter, command)
        assert (
            await adapter.save_request_understanding_v3_no_task_if_current(
                command
            )
            is Cycle2WriteResult.APPLIED
        )
        with adapter.session_factory.begin() as session:
            row = session.scalar(
                select(P0RecordModel).where(
                    P0RecordModel.record_code
                    == P0RecordCode.REQUEST_UNDERSTANDING_RECORD.value
                )
            )
            assert row is not None
            envelope = deepcopy(row.envelope)
            envelope["payload"]["data"]["contextualization"]["text"] = (
                "same identity, different durable bytes"
            )
            session.execute(
                update(P0RecordModel)
                .where(P0RecordModel.record_id == row.record_id)
                .values(envelope=envelope)
            )

        assert (
            await adapter.save_request_understanding_v3_no_task_if_current(
                command
            )
            is Cycle2WriteResult.PROJECTION_CONFLICT
        )
        assert _ru_counts(adapter) == (0, 1)
    finally:
        postgres_namespace_factory.drop(namespace)


async def test_v3_writer_rejects_non_authoritative_provenance_before_write(
    postgres_namespace_factory,
) -> None:
    namespace = postgres_namespace_factory.create("ru-v3-writer-provenance")
    adapter = PostgresRecordAdapter(
        build_session_factory(namespace.build_engine())
    )
    command = _generic_v3_staging_command(("O-1001",))
    record = command.request_understanding.record
    candidate = record.task_delta_candidates[0]
    candidate_input = candidate.input_candidates[0].model_copy(
        update={"source_quote_sha256": "0" * 64}
    )
    candidate = candidate.model_copy(update={"input_candidates": (candidate_input,)})
    record = record.model_copy(update={"task_delta_candidates": (candidate,)})
    tampered = command.model_copy(
        update={
            "request_understanding": command.request_understanding.model_copy(
                update={"record": record}
            )
        }
    )
    try:
        await _seed_phase1_roots(adapter, command)
        with pytest.raises(P0PersistenceIntegrityError):
            await adapter.create_initial_task_graph_v3_if_current(tampered)
        assert _ru_counts(adapter) == (0, 0)
        assert (
            await adapter.create_initial_task_graph_v3_if_current(command)
            is Cycle2WriteResult.APPLIED
        )
        with adapter.session_factory.begin() as session:
            message = session.scalar(
                select(P0RecordModel).where(
                    P0RecordModel.record_code == P0RecordCode.MESSAGE_RECORD.value
                )
            )
            assert message is not None
            envelope = deepcopy(message.envelope)
            envelope["payload"]["data"]["content"] = "authoritative drift"
            session.execute(
                update(P0RecordModel)
                .where(P0RecordModel.record_id == message.record_id)
                .values(envelope=envelope)
            )
        with pytest.raises(P0PersistenceIntegrityError):
            await adapter.create_initial_task_graph_v3_if_current(command)
        assert _ru_counts(adapter) == (0, 1)
    finally:
        postgres_namespace_factory.drop(namespace)


async def test_zero_child_v3_replay_reader_and_readiness_reject_assistant_message(
    postgres_namespace_factory,
) -> None:
    namespace = postgres_namespace_factory.create("ru-v3-direct-message-direction")
    adapter = PostgresRecordAdapter(
        build_session_factory(namespace.build_engine())
    )
    command = _generic_v3_staging_command(())
    try:
        await _seed_phase1_roots(adapter, command)
        assert (
            await adapter.save_request_understanding_v3_no_task_if_current(
                command
            )
            is Cycle2WriteResult.APPLIED
        )
        current_message = next(
            message
            for message in command.expected_message_records
            if message.message_id == command.request_understanding.record.message_ref
        )
        with adapter.session_factory.begin() as session:
            loaded = adapter._cycle2_row(
                session,
                owner_customer_id=command.owner_scope.customer_id,
                record_code=P0RecordCode.MESSAGE_RECORD,
                logical_identity=(("message_id", current_message.message_id),),
                for_update=True,
            )
            assert loaded is not None
            adapter._cycle2_replace(
                session,
                loaded[0],
                owner_customer_id=command.owner_scope.customer_id,
                expected_record=current_message,
                next_envelope=adapter._cycle2_encode(
                    P0RecordCode.MESSAGE_RECORD,
                    current_message.model_copy(
                        update={"direction": MessageDirection.ASSISTANT}
                    ),
                ),
            )
        with pytest.raises(P0PersistenceIntegrityError):
            await adapter.save_request_understanding_v3_no_task_if_current(command)
        with pytest.raises(P0PersistenceIntegrityError):
            await adapter.load_exact_run_evidence_v3_for_owner(
                owner_scope=command.owner_scope,
                run_id=command.expected_active_run_record.run_id,
            )
        with pytest.raises(P0PersistenceIntegrityError):
            await adapter.assert_request_understanding_v3_ready()
    finally:
        postgres_namespace_factory.drop(namespace)


async def test_absent_v3_identity_with_stale_roots_is_zero_write_not_applicable(
    postgres_namespace_factory,
) -> None:
    namespace = postgres_namespace_factory.create("ru-v3-stale-absent")
    adapter = PostgresRecordAdapter(
        build_session_factory(namespace.build_engine())
    )
    command = _generic_v3_staging_command(())
    try:
        assert (
            await adapter.save_request_understanding_v3_no_task_if_current(
                command
            )
            is Cycle2WriteResult.NOT_APPLICABLE
        )
        assert _ru_counts(adapter) == (0, 0)
    finally:
        postgres_namespace_factory.drop(namespace)


async def test_v3_reader_is_owner_scoped_and_rejects_provenance_drift(
    postgres_namespace_factory,
) -> None:
    namespace = postgres_namespace_factory.create("ru-v3-owner-provenance")
    adapter = PostgresRecordAdapter(
        build_session_factory(namespace.build_engine())
    )
    command = _generic_v3_staging_command(("O-1001",))
    try:
        await _seed_phase1_roots(adapter, command)
        assert (
            await adapter.create_initial_task_graph_v3_if_current(command)
            is Cycle2WriteResult.APPLIED
        )
        assert (
            await adapter.load_exact_run_evidence_v3_for_owner(
                owner_scope=TrustedOwnerScope.from_customer_context(
                    type(_context())(
                        **{
                            **_context().model_dump(),
                            "subject_ref": "subject-B",
                            "customer_id": "customer-B",
                        }
                    )
                ),
                run_id=command.expected_active_run_record.run_id,
            )
            is None
        )
        message_id = command.expected_message_records[0].message_id
        with adapter.session_factory.begin() as session:
            row = session.scalar(
                select(P0RecordModel).where(
                    P0RecordModel.record_code
                    == P0RecordCode.MESSAGE_RECORD.value,
                    P0RecordModel.logical_identity
                    == [["message_id", str(message_id)]],
                )
            )
            assert row is not None
            envelope = deepcopy(row.envelope)
            envelope["payload"]["data"]["content"] = "tampered message"
            session.execute(
                update(P0RecordModel)
                .where(P0RecordModel.record_id == row.record_id)
                .values(envelope=envelope)
            )
        with pytest.raises(P0PersistenceIntegrityError):
            await adapter.load_exact_run_evidence_v3_for_owner(
                owner_scope=command.owner_scope,
                run_id=command.expected_active_run_record.run_id,
            )
    finally:
        postgres_namespace_factory.drop(namespace)


async def test_cycle2_initial_v3_writer_and_reader_share_one_exact_closure(
    postgres_namespace_factory,
) -> None:
    namespace = postgres_namespace_factory.create("ru-v3-cycle2-initial")
    adapter = PostgresRecordAdapter(
        build_session_factory(namespace.build_engine())
    )
    command = await asyncio.to_thread(_cycle2_initial_v3_command)
    try:
        _seed_cycle2_initial_roots(adapter, command)
        assert (
            await adapter.create_cycle2_initial_task_graph_v3_if_current(command)
            is Cycle2WriteResult.APPLIED
        )
        assert (
            await adapter.create_cycle2_initial_task_graph_v3_if_current(command)
            is Cycle2WriteResult.ALREADY_APPLIED
        )
        evidence = await adapter.load_cycle2_exact_run_evidence_v3_for_owner(
            owner_scope=command.owner_scope,
            run_id=command.expected_running_run_record.run_id,
        )
        assert evidence is not None
        assert evidence.request_understanding_closures == (
            command.reducer_decision.closure,
        )
        assert await adapter.assert_request_understanding_v3_ready() is None
    finally:
        postgres_namespace_factory.drop(namespace)


@pytest.mark.parametrize("mutation_mode", ("version", "status"))
async def test_readiness_rejects_v3_task_effect_drift(
    postgres_namespace_factory,
    mutation_mode: str,
) -> None:
    namespace = postgres_namespace_factory.create("ru-v3-readiness-task-drift")
    adapter = PostgresRecordAdapter(
        build_session_factory(namespace.build_engine())
    )
    command = await asyncio.to_thread(_cycle2_initial_v3_command)
    try:
        _seed_cycle2_initial_roots(adapter, command)
        assert (
            await adapter.create_cycle2_initial_task_graph_v3_if_current(command)
            is Cycle2WriteResult.APPLIED
        )
        with adapter.session_factory.begin() as session:
            for record_code in (
                P0RecordCode.TASK_RECORD,
                P0RecordCode.REQUEST_UNIT_RECORD,
            ):
                row = session.scalar(
                    select(P0RecordModel).where(
                        P0RecordModel.record_code == record_code.value
                    )
                )
                assert row is not None
                envelope = deepcopy(row.envelope)
                values: dict[str, object] = {"envelope": envelope}
                if mutation_mode == "version":
                    envelope["payload"]["data"]["state_version"] = 2
                    values["state_version"] = 2
                else:
                    envelope["payload"]["data"]["status"] = (
                        TaskStatus.WAITING_USER.value
                    )
                    values["lifecycle_status"] = TaskStatus.WAITING_USER.value
                session.execute(
                    update(P0RecordModel)
                    .where(P0RecordModel.record_id == row.record_id)
                    .values(**values)
                )
        with pytest.raises(P0PersistenceIntegrityError):
            await adapter.assert_request_understanding_v3_ready()
    finally:
        postgres_namespace_factory.drop(namespace)


@pytest.mark.parametrize("mutation_mode", ("future_transition", "unexplained_v2"))
async def test_v3_replay_and_readiness_reject_unclosed_task_timeline(
    postgres_namespace_factory,
    mutation_mode: str,
) -> None:
    namespace = postgres_namespace_factory.create(
        f"ru-v3-task-timeline-{mutation_mode}"
    )
    adapter = PostgresRecordAdapter(
        build_session_factory(namespace.build_engine())
    )
    command = _generic_v3_staging_command(("O-1001",))
    try:
        await _seed_phase1_roots(adapter, command)
        assert (
            await adapter.create_initial_task_graph_v3_if_current(command)
            is Cycle2WriteResult.APPLIED
        )
        graph = command.accepted_task_graphs[0]
        task = graph.initial_task.initial_record
        unit = graph.initial_request_unit.initial_record
        with adapter.session_factory.begin() as session:
            task_loaded = adapter._cycle2_row(
                session,
                owner_customer_id=command.owner_scope.customer_id,
                record_code=P0RecordCode.TASK_RECORD,
                logical_identity=(("task_id", task.task_id),),
                for_update=True,
            )
            assert task_loaded is not None
            if mutation_mode == "future_transition":
                transition = TaskStateTransition(
                    task_id=task.task_id,
                    request_unit_id=unit.request_unit_id,
                    from_status=TaskStatus.ACTIVE,
                    to_status=TaskStatus.WAITING_USER,
                    base_state_version=1,
                    result_state_version=2,
                    reason_ref=uuid4(),
                    changed_at=task.updated_at,
                )
                adapter._cycle2_replace(
                    session,
                    task_loaded[0],
                    owner_customer_id=command.owner_scope.customer_id,
                    expected_record=task,
                    next_envelope=adapter._cycle2_encode(
                        P0RecordCode.TASK_RECORD,
                        task,
                        logical_children=(transition,),
                    ),
                )
            else:
                changed_at = task.updated_at + timedelta(seconds=1)
                next_task = task.model_copy(
                    update={"state_version": 2, "updated_at": changed_at}
                )
                adapter._cycle2_replace(
                    session,
                    task_loaded[0],
                    owner_customer_id=command.owner_scope.customer_id,
                    expected_record=task,
                    next_envelope=adapter._cycle2_encode(
                        P0RecordCode.TASK_RECORD,
                        next_task,
                    ),
                )
                unit_loaded = adapter._cycle2_row(
                    session,
                    owner_customer_id=command.owner_scope.customer_id,
                    record_code=P0RecordCode.REQUEST_UNIT_RECORD,
                    logical_identity=(("request_unit_id", unit.request_unit_id),),
                    for_update=True,
                )
                assert unit_loaded is not None
                adapter._cycle2_replace(
                    session,
                    unit_loaded[0],
                    owner_customer_id=command.owner_scope.customer_id,
                    expected_record=unit,
                    next_envelope=adapter._cycle2_encode(
                        P0RecordCode.REQUEST_UNIT_RECORD,
                        unit.model_copy(
                            update={"state_version": 2, "updated_at": changed_at}
                        ),
                    ),
                )
        assert (
            await adapter.create_initial_task_graph_v3_if_current(command)
            is Cycle2WriteResult.PROJECTION_CONFLICT
        )
        with pytest.raises(P0PersistenceIntegrityError):
            await adapter.assert_request_understanding_v3_ready()
    finally:
        postgres_namespace_factory.drop(namespace)


@pytest.mark.parametrize("result_state_version", (1, 999))
async def test_readiness_rejects_active_run_link_result(
    postgres_namespace_factory,
    result_state_version: int,
) -> None:
    namespace = postgres_namespace_factory.create(
        f"ru-v3-readiness-link-result-{result_state_version}"
    )
    adapter = PostgresRecordAdapter(
        build_session_factory(namespace.build_engine())
    )
    command = await asyncio.to_thread(_cycle2_initial_v3_command)
    try:
        _seed_cycle2_initial_roots(adapter, command)
        assert (
            await adapter.create_cycle2_initial_task_graph_v3_if_current(command)
            is Cycle2WriteResult.APPLIED
        )
        with adapter.session_factory.begin() as session:
            row = session.scalar(
                select(P0RecordModel).where(
                    P0RecordModel.record_code
                    == P0RecordCode.RUN_TASK_LINK_RECORD.value
                )
            )
            assert row is not None
            envelope = deepcopy(row.envelope)
            envelope["payload"]["data"]["result_task_state_version"] = (
                result_state_version
            )
            session.execute(
                update(P0RecordModel)
                .where(P0RecordModel.record_id == row.record_id)
                .values(envelope=envelope)
            )
        with pytest.raises(P0PersistenceIntegrityError):
            await adapter.assert_request_understanding_v3_ready()
    finally:
        postgres_namespace_factory.drop(namespace)


async def test_readiness_accepts_superseded_run_with_no_result_link(
    postgres_namespace_factory,
) -> None:
    namespace = postgres_namespace_factory.create(
        "ru-v3-readiness-superseded-no-result"
    )
    adapter = PostgresRecordAdapter(
        build_session_factory(namespace.build_engine())
    )
    command = await asyncio.to_thread(_cycle2_initial_v3_command)
    owner = command.owner_scope.customer_id
    try:
        _seed_cycle2_initial_roots(adapter, command)
        assert (
            await adapter.create_cycle2_initial_task_graph_v3_if_current(command)
            is Cycle2WriteResult.APPLIED
        )
        with adapter.session_factory.begin() as session:
            run_loaded = adapter._cycle2_row(
                session,
                owner_customer_id=owner,
                record_code=P0RecordCode.AGENT_RUN_RECORD,
                logical_identity=((
                    "run_id",
                    command.expected_running_run_record.run_id,
                ),),
                for_update=True,
            )
            assert run_loaded is not None
            running = run_loaded[1].source_record
            assert type(running) is AgentRunRecordV2
            adapter._cycle2_replace(
                session,
                run_loaded[0],
                owner_customer_id=owner,
                expected_record=running,
                next_envelope=adapter._cycle2_encode(
                    P0RecordCode.AGENT_RUN_RECORD,
                    running.model_copy(
                        update={
                            "status": AgentRunStatusV2.SUPERSEDED,
                            "completed_at": running.started_at,
                            "stop_reason": (
                                StopReasonV2.STATE_OR_BINDING_INVALIDATED
                            ),
                        }
                    ),
                ),
            )
        assert await adapter.assert_request_understanding_v3_ready() is None
    finally:
        postgres_namespace_factory.drop(namespace)


async def test_readiness_rejects_same_owner_cross_conversation_stitch(
    postgres_namespace_factory,
) -> None:
    namespace = postgres_namespace_factory.create("ru-v3-readiness-conversation")
    adapter = PostgresRecordAdapter(
        build_session_factory(namespace.build_engine())
    )
    command = await asyncio.to_thread(_cycle2_initial_v3_command)
    owner = command.owner_scope.customer_id
    try:
        _seed_cycle2_initial_roots(adapter, command)
        assert (
            await adapter.create_cycle2_initial_task_graph_v3_if_current(command)
            is Cycle2WriteResult.APPLIED
        )
        second_conversation = command.expected_conversation_record.model_copy(
            update={"conversation_id": uuid4()}
        )
        with adapter.session_factory.begin() as session:
            adapter._cycle2_insert(
                session,
                (
                    adapter._cycle2_encode(
                        P0RecordCode.CONVERSATION_RECORD,
                        second_conversation,
                    ),
                ),
                owner_customer_id=owner,
            )
            message = adapter._cycle2_row(
                session,
                owner_customer_id=owner,
                record_code=P0RecordCode.MESSAGE_RECORD,
                logical_identity=((
                    "message_id",
                    command.expected_user_message_record.message_id,
                ),),
                for_update=True,
            )
            assert message is not None
            stitched = command.expected_user_message_record.model_copy(
                update={"conversation_id": second_conversation.conversation_id}
            )
            adapter._cycle2_replace(
                session,
                message[0],
                owner_customer_id=owner,
                expected_record=command.expected_user_message_record,
                next_envelope=adapter._cycle2_encode(
                    P0RecordCode.MESSAGE_RECORD,
                    stitched,
                ),
            )
        with pytest.raises(P0PersistenceIntegrityError):
            await adapter.create_cycle2_initial_task_graph_v3_if_current(command)
        with pytest.raises(P0PersistenceIntegrityError):
            await adapter.assert_request_understanding_v3_ready()
    finally:
        postgres_namespace_factory.drop(namespace)


async def test_readiness_rejects_missing_initial_conversation_task_link(
    postgres_namespace_factory,
) -> None:
    namespace = postgres_namespace_factory.create("ru-v3-readiness-missing-link")
    adapter = PostgresRecordAdapter(
        build_session_factory(namespace.build_engine())
    )
    command = _generic_v3_staging_command(("O-1001",))
    try:
        await _seed_phase1_roots(adapter, command)
        assert (
            await adapter.create_initial_task_graph_v3_if_current(command)
            is Cycle2WriteResult.APPLIED
        )
        with adapter.session_factory.begin() as session:
            link = session.scalar(
                select(P0RecordModel).where(
                    P0RecordModel.record_code
                    == P0RecordCode.CONVERSATION_TASK_LINK_RECORD.value
                )
            )
            assert link is not None
            session.delete(link)
        with pytest.raises(P0PersistenceIntegrityError):
            await adapter.assert_request_understanding_v3_ready()
    finally:
        postgres_namespace_factory.drop(namespace)


async def test_cycle2_v3_multirow_failure_rolls_back_parent_and_all_effects(
    postgres_namespace_factory,
) -> None:
    namespace = postgres_namespace_factory.create("ru-v3-transaction-rollback")
    adapter = PostgresRecordAdapter(
        build_session_factory(namespace.build_engine())
    )
    command = await asyncio.to_thread(_cycle2_initial_v3_command)
    try:
        _seed_cycle2_initial_roots(adapter, command)
        with adapter.session_factory.begin() as session:
            session.execute(
                text(
                    """
                    CREATE FUNCTION reject_v3_trace_insert()
                    RETURNS trigger LANGUAGE plpgsql AS $$
                    BEGIN
                        RAISE EXCEPTION 'forced v3 trace rollback';
                    END
                    $$
                    """
                )
            )
            session.execute(
                text(
                    """
                    CREATE TRIGGER reject_v3_trace_insert
                    BEFORE INSERT ON p0_records
                    FOR EACH ROW
                    WHEN (NEW.record_code = 'trace_event_record')
                    EXECUTE FUNCTION reject_v3_trace_insert()
                    """
                )
            )
        with pytest.raises(P0PersistenceSystemError):
            await adapter.create_cycle2_initial_task_graph_v3_if_current(
                command
            )
        assert _ru_counts(adapter) == (0, 0)
        with adapter.session_factory() as session:
            assert session.scalar(
                select(func.count())
                .select_from(P0RecordModel)
                .where(
                    P0RecordModel.task_id
                    == command.reducer_decision.task_graph.task.task_id
                )
            ) == 0
    finally:
        postgres_namespace_factory.drop(namespace)


async def test_dnr_v3_continuation_is_atomic_and_identity_first(
    postgres_namespace_factory,
) -> None:
    namespace = postgres_namespace_factory.create("ru-v3-dnr")
    adapter = PostgresRecordAdapter(
        build_session_factory(namespace.build_engine())
    )
    command = _dnr_v3_staging_command(with_current_dnr=True)
    try:
        _seed_continuation_roots(adapter, command)
        assert (
            await adapter.apply_continuation_task_delta_if_current(command)
            is Cycle2WriteResult.APPLIED
        )
        assert (
            await adapter.apply_continuation_task_delta_if_current(command)
            is Cycle2WriteResult.ALREADY_APPLIED
        )
        with adapter.session_factory.begin() as session:
            loaded = adapter._cycle2_row(
                session,
                owner_customer_id=command.loaded_closure.owner_scope.customer_id,
                record_code=P0RecordCode.TASK_RECORD,
                logical_identity=(("task_id", command.next_task_record.task_id),),
            )
            assert loaded is not None
            assert loaded[1].source_record == command.next_task_record
        assert await adapter.assert_request_understanding_v3_ready() is None
        with adapter.session_factory.begin() as session:
            row = session.scalar(
                select(P0RecordModel).where(
                    P0RecordModel.record_code
                    == P0RecordCode.REQUEST_UNIT_RECORD.value
                )
            )
            assert row is not None
            envelope = deepcopy(row.envelope)
            envelope["payload"]["data"]["open_questions"] = ["drift"]
            session.execute(
                update(P0RecordModel)
                .where(P0RecordModel.record_id == row.record_id)
                .values(envelope=envelope)
            )
        with pytest.raises(P0PersistenceIntegrityError):
            await adapter.assert_request_understanding_v3_ready()
    finally:
        postgres_namespace_factory.drop(namespace)


async def test_readiness_accepts_terminal_run_link_at_historical_task_version(
    postgres_namespace_factory,
) -> None:
    namespace = postgres_namespace_factory.create("ru-v3-historical-run-link")
    adapter = PostgresRecordAdapter(
        build_session_factory(namespace.build_engine())
    )
    command = _dnr_v3_staging_command(with_current_dnr=True)
    owner = command.loaded_closure.owner_scope.customer_id
    child = command.decision.closure.accepted_task_deltas[0]
    try:
        _seed_continuation_roots(adapter, command)
        assert (
            await adapter.apply_continuation_task_delta_if_current(command)
            is Cycle2WriteResult.APPLIED
        )
        with adapter.session_factory.begin() as session:
            run_loaded = adapter._cycle2_row(
                session,
                owner_customer_id=owner,
                record_code=P0RecordCode.AGENT_RUN_RECORD,
                logical_identity=(("run_id", command.decision.closure.record.run_id),),
                for_update=True,
            )
            link_loaded = adapter._cycle2_row(
                session,
                owner_customer_id=owner,
                record_code=P0RecordCode.RUN_TASK_LINK_RECORD,
                logical_identity=(
                    ("run_id", command.decision.closure.record.run_id),
                    ("task_id", command.next_task_record.task_id),
                ),
                for_update=True,
            )
            assert run_loaded is not None and link_loaded is not None
            running = run_loaded[1].source_record
            active_link = link_loaded[1].source_record
            assert type(running) is AgentRunRecordV2
            assert type(active_link) is RunTaskLinkRecordV2
            adapter._cycle2_replace(
                session,
                link_loaded[0],
                owner_customer_id=owner,
                expected_record=active_link,
                next_envelope=adapter._cycle2_encode(
                    P0RecordCode.RUN_TASK_LINK_RECORD,
                    active_link.model_copy(
                        update={
                            "result_task_state_version": (
                                child.result_task_state_version
                            )
                        }
                    ),
                ),
            )
            adapter._cycle2_replace(
                session,
                run_loaded[0],
                owner_customer_id=owner,
                expected_record=running,
                next_envelope=adapter._cycle2_encode(
                    P0RecordCode.AGENT_RUN_RECORD,
                    running.model_copy(
                        update={
                            "status": AgentRunStatusV2.COMPLETED,
                            "completed_at": child.accepted_at,
                            "stop_reason": StopReasonV2.GOAL_COMPLETED,
                        }
                    ),
                ),
            )
        changed_at = child.accepted_at + timedelta(seconds=1)
        next_task = command.next_task_record.model_copy(
            update={
                "status": TaskStatus.COMPLETED,
                "state_version": child.result_task_state_version + 1,
                "updated_at": changed_at,
            }
        )
        next_unit = command.next_request_unit_record.model_copy(
            update={
                "status": TaskStatus.COMPLETED,
                "state_version": child.result_task_state_version + 1,
                "updated_at": changed_at,
            }
        )
        transition = TaskStateTransition(
            task_id=next_task.task_id,
            request_unit_id=next_unit.request_unit_id,
            from_status=command.next_task_record.status,
            to_status=TaskStatus.COMPLETED,
            base_state_version=child.result_task_state_version,
            result_state_version=child.result_task_state_version + 1,
            reason_ref=uuid4(),
            changed_at=changed_at,
        )
        with adapter.session_factory.begin() as session:
            task_loaded = adapter._cycle2_row(
                session,
                owner_customer_id=owner,
                record_code=P0RecordCode.TASK_RECORD,
                logical_identity=(("task_id", next_task.task_id),),
                for_update=True,
            )
            unit_loaded = adapter._cycle2_row(
                session,
                owner_customer_id=owner,
                record_code=P0RecordCode.REQUEST_UNIT_RECORD,
                logical_identity=(("request_unit_id", next_unit.request_unit_id),),
                for_update=True,
            )
            assert task_loaded is not None and unit_loaded is not None
            adapter._cycle2_replace(
                session,
                task_loaded[0],
                owner_customer_id=owner,
                expected_record=command.next_task_record,
                next_envelope=adapter._cycle2_encode(
                    P0RecordCode.TASK_RECORD,
                    next_task,
                    logical_children=(transition,),
                ),
            )
            adapter._cycle2_replace(
                session,
                unit_loaded[0],
                owner_customer_id=owner,
                expected_record=command.next_request_unit_record,
                next_envelope=adapter._cycle2_encode(
                    P0RecordCode.REQUEST_UNIT_RECORD,
                    next_unit,
                ),
            )
        assert await adapter.assert_request_understanding_v3_ready() is None
    finally:
        postgres_namespace_factory.drop(namespace)


async def test_rejected_v3_continuation_persists_only_zero_child_parent(
    postgres_namespace_factory,
) -> None:
    namespace = postgres_namespace_factory.create("ru-v3-rejected-continuation")
    adapter = PostgresRecordAdapter(
        build_session_factory(namespace.build_engine())
    )
    command = _rejected_continuation_command()
    try:
        _seed_continuation_roots(adapter, command)
        before_task = command.loaded_closure.current_task_record
        assert (
            await adapter.save_rejected_continuation_understanding_if_current(
                command
            )
            is Cycle2WriteResult.APPLIED
        )
        assert (
            await adapter.save_rejected_continuation_understanding_if_current(
                command
            )
            is Cycle2WriteResult.ALREADY_APPLIED
        )
        with adapter.session_factory.begin() as session:
            loaded = adapter._cycle2_row(
                session,
                owner_customer_id=command.loaded_closure.owner_scope.customer_id,
                record_code=P0RecordCode.TASK_RECORD,
                logical_identity=(("task_id", before_task.task_id),),
            )
            assert loaded is not None
            assert loaded[1].source_record == before_task
        assert _ru_counts(adapter) == (0, 1)
        assert await adapter.assert_request_understanding_v3_ready() is None
    finally:
        postgres_namespace_factory.drop(namespace)


async def test_v3_ordinal_selection_is_one_identity_first_cas(
    postgres_namespace_factory,
) -> None:
    namespace = postgres_namespace_factory.create("ru-v3-ordinal-selection")
    adapter = PostgresRecordAdapter(
        build_session_factory(namespace.build_engine())
    )
    command, current = await asyncio.to_thread(_selection_v3_command_bundle)
    try:
        await _seed_selection_roots(adapter, command, current)
        loaded = await adapter.load_order_candidate_selection_closure_for_owner(
            owner_scope=command.loaded_closure.owner_scope,
            conversation_id=command.loaded_closure.conversation_id,
            task_id=command.loaded_closure.current_task_record.task_id,
            request_unit_id=(
                command.loaded_closure.current_request_unit_record.request_unit_id
            ),
            selection_request=command.loaded_closure.selection_request,
            trusted_now=command.loaded_closure.trusted_now,
        )
        assert loaded == command.loaded_closure
        assert (
            await adapter.apply_order_candidate_selection_v3_if_current(
                command
            )
            is Cycle2WriteResult.APPLIED
        )
        assert (
            await adapter.apply_order_candidate_selection_v3_if_current(
                command
            )
            is Cycle2WriteResult.ALREADY_APPLIED
        )
        with adapter.session_factory.begin() as session:
            task = adapter._cycle2_row(
                session,
                owner_customer_id=command.loaded_closure.owner_scope.customer_id,
                record_code=P0RecordCode.TASK_RECORD,
                logical_identity=(("task_id", command.next_task_record.task_id),),
            )
            selection = adapter._cycle2_row(
                session,
                owner_customer_id=command.loaded_closure.owner_scope.customer_id,
                record_code=P0RecordCode.ORDER_CANDIDATE_SELECTION_RECORD,
                logical_identity=(("selection_id", command.selection_record.selection_id),),
            )
            assert task is not None
            assert task[1].source_record == command.next_task_record
            assert selection is not None
            assert selection[1].source_record == command.selection_record
        assert _ru_counts(adapter) == (0, 1)
        assert await adapter.assert_request_understanding_v3_ready() is None
    finally:
        postgres_namespace_factory.drop(namespace)


async def test_empty_head_is_v3_ready(postgres_namespace_factory) -> None:
    namespace = postgres_namespace_factory.create("ru-v3-empty-readiness")
    adapter = PostgresRecordAdapter(
        build_session_factory(namespace.build_engine())
    )
    try:
        assert await adapter.assert_request_understanding_v3_ready() is None
    finally:
        postgres_namespace_factory.drop(namespace)


async def test_readiness_rejects_weakened_physical_pair_constraint(
    postgres_namespace_factory,
) -> None:
    namespace = postgres_namespace_factory.create("ru-v3-readiness-weak-check")
    adapter = PostgresRecordAdapter(
        build_session_factory(namespace.build_engine())
    )
    try:
        with adapter.session_factory.begin() as session:
            definition = session.scalar(
                text(
                    """
                    SELECT pg_get_constraintdef(oid)
                    FROM pg_constraint
                    WHERE conrelid = 'p0_records'::regclass
                      AND conname = 'ck_p0_records_code_version_closed'
                    """
                )
            )
            assert type(definition) is str and definition.startswith("CHECK ")
            expression = definition.removeprefix("CHECK ")
            session.execute(
                text(
                    "ALTER TABLE p0_records DROP CONSTRAINT "
                    "ck_p0_records_code_version_closed"
                )
            )
            session.execute(
                text(
                    "ALTER TABLE p0_records ADD CONSTRAINT "
                    "ck_p0_records_code_version_closed CHECK ("
                    f"{expression} OR (record_code = "
                    "'request_understanding_record' AND "
                    "record_schema_version = "
                    "'request_understanding_record.p0.future'))"
                )
            )
        with pytest.raises(P0PersistenceIntegrityError):
            await adapter.assert_request_understanding_v3_ready()
    finally:
        postgres_namespace_factory.drop(namespace)


async def test_readiness_fails_global_residual_v2_and_malformed_v3(
    postgres_namespace_factory,
) -> None:
    residual_namespace = postgres_namespace_factory.create(
        "ru-v3-readiness-residual-v2"
    )
    residual_adapter = PostgresRecordAdapter(
        build_session_factory(residual_namespace.build_engine())
    )
    graph = _initial_v2_graph()
    try:
        await _seed_phase1_roots(residual_adapter, graph)
        assert (
            await residual_adapter.create_initial_task_graph_v2_if_current(
                graph
            )
            is ConditionalWriteResult.APPLIED
        )
        with pytest.raises(P0PersistenceIntegrityError):
            await residual_adapter.assert_request_understanding_v3_ready()
    finally:
        postgres_namespace_factory.drop(residual_namespace)

    malformed_namespace = postgres_namespace_factory.create(
        "ru-v3-readiness-malformed-v3"
    )
    malformed_adapter = PostgresRecordAdapter(
        build_session_factory(malformed_namespace.build_engine())
    )
    command = _generic_v3_staging_command(())
    try:
        await _seed_phase1_roots(malformed_adapter, command)
        assert (
            await malformed_adapter.save_request_understanding_v3_no_task_if_current(
                command
            )
            is Cycle2WriteResult.APPLIED
        )
        with malformed_adapter.session_factory.begin() as session:
            row = session.scalar(
                select(P0RecordModel).where(
                    P0RecordModel.record_code
                    == P0RecordCode.REQUEST_UNDERSTANDING_RECORD.value
                )
            )
            assert row is not None
            envelope = deepcopy(row.envelope)
            envelope["payload"]["data"]["contextualization"]["text"] = 42
            session.execute(
                update(P0RecordModel)
                .where(P0RecordModel.record_id == row.record_id)
                .values(envelope=envelope)
            )
        with pytest.raises(P0PersistenceIntegrityError):
            await malformed_adapter.assert_request_understanding_v3_ready()
    finally:
        postgres_namespace_factory.drop(malformed_namespace)
