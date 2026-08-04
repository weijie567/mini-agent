from __future__ import annotations

import asyncio
import hashlib
import json
from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import ValidationError

import pytest
from sqlalchemy import func, select

from mini_agent.application.persistence import (
    P0PersistenceIntegrityCategory,
    P0PersistenceIntegrityError,
    P0RecordCode,
)
from mini_agent.application.records import (
    SupersededRunInvalidationKind,
    TrustedOwnerScope,
)
from mini_agent.core.identity import CustomerContext
from mini_agent.core.trace import AgentRunStatusV2
from mini_agent.infrastructure.cycle2_fixture_seed import (
    W12_SETUP_SCHEMA_VERSION,
    W12_TRUSTED_CLOCK,
    Cycle2ExecutionSetupPlanV1,
    Cycle2SeedError,
    apply_cycle2_execution_setup_plan,
    apply_cycle2_seed_plan,
    compute_cycle2_execution_setup_digest,
    compute_cycle2_pair_seed_digest,
    cycle2_w12_fault_catalog,
    cycle2_w12_fixture_catalog,
    cycle2_dispatchable_fixture_catalog,
    deterministic_cycle2_setup_uuid,
    fold_cycle2_runtime_records,
    resolve_cycle2_execution_setup_plan,
    resolve_cycle2_seed_plan,
)
from mini_agent.infrastructure.cycle2_runtime import Cycle2DetachedExecutionSetup
from mini_agent.core.tool_system import build_cycle2_registry_snapshot
from mini_agent.infrastructure.persistence.database import build_session_factory
from mini_agent.infrastructure.persistence.models import (
    MockOrderModel,
    MockOrderSearchDocumentModel,
    MockShipmentModel,
    P0RecordModel,
    P0RecordStateHistoryModel,
)
from mini_agent.infrastructure.persistence.postgres import (
    PostgresRecordAdapter,
    _cycle2_search_observation_source_edge_facts,
)


def _runtime_source(records, role: str):
    matches = tuple(
        record.source_record
        for record in records
        if record.record_role == role
    )
    assert len(matches) == 1
    return matches[0]


def _replace_runtime_source(records, *, role: str, update: dict[str, object]):
    assert sum(record.record_role == role for record in records) == 1
    return tuple(
        record.model_copy(
            update={
                "source_record": record.source_record.model_copy(update=update)
            }
        )
        if record.record_role == role
        else record
        for record in records
    )


def test_w9_catalog_is_closed_owner_scoped_and_never_preseeds_runtime() -> None:
    catalog = cycle2_dispatchable_fixture_catalog()
    assert set(catalog) == {
        "fx-search-unique-owner-a-with-foreign-decoy-v1",
        "fx-search-multiple-owner-a-v1",
        "fx-dynamic-tool-pair-owner-a-v1",
        "fx-shipment-refresh-stalled-owner-a-v1",
        "fx-shipment-current-owner-a-v1",
    }
    assert all(
        envelope.owner_customer_id == "customer-A"
        and envelope.initial_record_graph == ()
        and envelope.initial_record_references == ()
        and all(
            seed.owner_customer_id == "customer-A"
            for family in (
                envelope.session_seeds,
                envelope.order_seeds,
                envelope.search_document_seeds,
                envelope.shipment_seeds,
            )
            for seed in family
        )
        for envelope in catalog.values()
    )
    bounded = json.dumps(
        {
            ref: envelope.model_dump(mode="json")
            for ref, envelope in catalog.items()
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    assert "customer-B" not in bounded
    assert "O-9001" not in bounded


def test_w12_catalog_is_distinct_complete_and_closed() -> None:
    fixtures = cycle2_w12_fixture_catalog()
    faults = cycle2_w12_fault_catalog()
    assert len(fixtures) == 23
    assert set(fixtures) == {
        "fx-search-unique-owner-a-with-foreign-decoy-v1",
        "fx-search-no-match-owner-a-v1",
        "fx-search-multiple-owner-a-v1",
        "fx-order-targets-owner-a-v1",
        "fx-current-candidate-set-owner-a-v1",
        "fx-expired-candidate-set-owner-a-v1",
        "fx-candidate-set-other-task-owner-a-v1",
        "fx-verified-order-target-o1001-owner-a-v1",
        "fx-dynamic-tool-pair-owner-a-v1",
        "fx-stale-shipment-observation-owner-a-v1",
        "fx-candidate-owner-mismatch-owner-a-v1",
        "fx-superseded-candidate-set-owner-a-v1",
        "fx-zero-or-multiple-current-candidate-set-owner-a-v1",
        "fx-corrected-not-received-claim-owner-a-v1",
        "fx-retry-scheduled-obsolete-run-owner-a-v1",
        "fx-shipment-refresh-stalled-owner-a-v1",
        "fx-shipment-current-owner-a-v1",
        "fx-shipment-missing-promise-owner-a-v1",
        "fx-order-zero-active-package-owner-a-v1",
        "fx-shipment-delayed-boundary-owner-a-v1",
        "fx-shipment-delivered-owner-a-v1",
        "fx-shipment-refresh-born-stale-owner-a-v1",
        "fx-two-active-packages-owner-a-v1",
    }
    assert set(faults) == {
        "fault:get-shipment:transient-once-v1",
        "fault:get-shipment:transient-always-v1",
        "fault:get-shipment:source-integrity-v1",
        "fault:get-shipment:timeout-after-dispatch-once-v1",
        "fault:get-shipment:restart-after-retry-finalize-v1",
        "fault:get-shipment:restart-after-retry-finalize-state-invalidated-v1",
        "fault:get-shipment:restart-with-unfinished-attempt-v1",
    }
    assert set(cycle2_dispatchable_fixture_catalog()) < set(fixtures)
    assert all(definition.owner_customer_id == "customer-A" for definition in fixtures.values())
    assert all(definition.fixture_ref == fixture_ref for fixture_ref, definition in fixtures.items())
    assert all(definition.fault_ref == fault_ref for fault_ref, definition in faults.items())


def test_every_w12_fixture_materializes_through_the_closed_builder() -> None:
    for fixture_ref in cycle2_w12_fixture_catalog():
        initial_refs = (fixture_ref,)
        message = None
        if fixture_ref == "fx-corrected-not-received-claim-owner-a-v1":
            initial_refs = (
                "fx-verified-order-target-o1001-owner-a-v1",
                fixture_ref,
            )
        if fixture_ref == "fx-retry-scheduled-obsolete-run-owner-a-v1":
            message = "订单 O-1001 到哪了？"
        plan = resolve_cycle2_execution_setup_plan(
            trusted_context_fixture_ref="session:alice",
            initial_state_fixture_refs=initial_refs,
            environment_fixture_refs=(),
            fault_ref=None,
            authenticated_user_message=message,
            registry_snapshot=(
                build_cycle2_registry_snapshot()
                if fixture_ref == "fx-dynamic-tool-pair-owner-a-v1"
                else None
            ),
        )
        assert plan.fixture_refs
        fold_cycle2_runtime_records(plan.runtime_state)


def test_current_candidate_fixture_uses_real_adapter_sort_and_source_version() -> None:
    plan = resolve_cycle2_execution_setup_plan(
        trusted_context_fixture_ref="session:alice",
        initial_state_fixture_refs=("fx-current-candidate-set-owner-a-v1",),
        environment_fixture_refs=("fx-order-targets-owner-a-v1",),
        fault_ref=None,
    )
    graph = fold_cycle2_runtime_records(plan.runtime_state)
    candidate_set = next(
        record.source_record
        for record in graph
        if record.record_role == "candidate_set.search"
    )
    observation = next(
        record.source_record
        for record in graph
        if record.record_role == "observation.search.search"
    )
    public_by_ref = {
        candidate.observation_candidate_ref: candidate.public_summary.order_number
        for candidate in observation.normalized_value.ordered_candidates
    }
    assert tuple(
        public_by_ref[entry.observation_candidate_ref]
        for entry in candidate_set.ordered_candidates
    ) == ("O-1002", "O-1001")
    assert candidate_set.search_observation_source_version == observation.source_version


def test_w12_setup_uuid_digest_and_schema_are_exact_and_expectation_free() -> None:
    first = deterministic_cycle2_setup_uuid(
        "fx-current-candidate-set-owner-a-v1", "task.current"
    )
    second = deterministic_cycle2_setup_uuid(
        "fx-current-candidate-set-owner-a-v1", "task.current"
    )
    assert first == second
    assert first.version == 4
    assert first.variant == "specified in RFC 4122"

    plan = resolve_cycle2_execution_setup_plan(
        trusted_context_fixture_ref="session:alice",
        initial_state_fixture_refs=(),
        environment_fixture_refs=("fx-search-no-match-owner-a-v1",),
        fault_ref=None,
    )
    assert type(plan) is Cycle2ExecutionSetupPlanV1
    assert plan.setup_schema_version == W12_SETUP_SCHEMA_VERSION
    assert plan.trusted_clock_profile_ref == "clock:cycle2-w12-v1"
    assert W12_TRUSTED_CLOCK == datetime(2026, 7, 31, 12, 0, tzinfo=UTC)
    assert plan.setup_digest == compute_cycle2_execution_setup_digest(plan)
    serialized = plan.model_dump_json()
    for forbidden in (
        "case_id",
        "model_script_ref",
        "expected_outcome",
        "stop_reason",
        "response_policy",
        "grader",
        "reply",
    ):
        assert forbidden not in serialized
    tampered = plan.model_dump(mode="json")
    tampered["case_id"] = "forbidden"
    with pytest.raises(ValidationError):
        Cycle2ExecutionSetupPlanV1.model_validate(tampered, strict=True)


def test_w12_resolver_closes_overlay_pair_recovery_and_unknown_authority() -> None:
    pair = resolve_cycle2_execution_setup_plan(
        trusted_context_fixture_ref="session:alice",
        initial_state_fixture_refs=(
            "fx-verified-order-target-o1001-owner-a-v1",
        ),
        environment_fixture_refs=("fx-dynamic-tool-pair-owner-a-v1",),
        fault_ref=None,
        registry_snapshot=build_cycle2_registry_snapshot(),
    )
    assert pair.pair_evidence is not None
    assert pair.pair_evidence.pair_id == "PAIR-E2E01-05-V1"
    assert pair.pair_evidence.model_visible_toolset_hash == (
        build_cycle2_registry_snapshot().model_visible_toolset_hash
    )

    corrected = resolve_cycle2_execution_setup_plan(
        trusted_context_fixture_ref="session:alice",
        initial_state_fixture_refs=(
            "fx-corrected-not-received-claim-owner-a-v1",
            "fx-verified-order-target-o1001-owner-a-v1",
        ),
        environment_fixture_refs=("fx-shipment-delivered-owner-a-v1",),
        fault_ref=None,
    )
    assert len(corrected.runtime_state.overlays) == 1
    assert corrected.runtime_state.overlays[0].prerequisite_fixture_ref == (
        "fx-verified-order-target-o1001-owner-a-v1"
    )

    recovery = resolve_cycle2_execution_setup_plan(
        trusted_context_fixture_ref="session:alice",
        initial_state_fixture_refs=(
            "fx-retry-scheduled-obsolete-run-owner-a-v1",
        ),
        environment_fixture_refs=("fx-shipment-current-owner-a-v1",),
        fault_ref=(
            "fault:get-shipment:restart-after-retry-finalize-state-invalidated-v1"
        ),
        authenticated_user_message="订单 O-1001 到哪了？",
    )
    assert recovery.runtime_state.recovery_subject_run_id is not None
    assert len(recovery.runtime_state.historical_user_messages) == 1
    assert recovery.runtime_state.historical_user_messages[0].content == (
        "订单 O-1001 到哪了？"
    )

    with pytest.raises(Cycle2SeedError):
        resolve_cycle2_execution_setup_plan(
            trusted_context_fixture_ref="session:alice",
            initial_state_fixture_refs=("fx-name-derived-not-allowed-v1",),
            environment_fixture_refs=(),
            fault_ref=None,
        )
    with pytest.raises(Cycle2SeedError):
        resolve_cycle2_execution_setup_plan(
            trusted_context_fixture_ref="session:alice",
            initial_state_fixture_refs=(),
            environment_fixture_refs=("fx-search-no-match-owner-a-v1",),
            fault_ref="fault:get-shipment:unknown-v1",
        )


@pytest.mark.parametrize(
    "fixture_ref",
    (
        "fx-verified-order-target-o1001-owner-a-v1",
        "fx-stale-shipment-observation-owner-a-v1",
    ),
)
def test_unique_target_fixture_has_distinct_search_and_order_claim_sources(
    fixture_ref: str,
) -> None:
    plan = resolve_cycle2_execution_setup_plan(
        trusted_context_fixture_ref="session:alice",
        initial_state_fixture_refs=(fixture_ref,),
        environment_fixture_refs=(),
        fault_ref=None,
    )
    graph = fold_cycle2_runtime_records(plan.runtime_state)
    search_message = _runtime_source(
        graph, "message.historical_user.search"
    )
    order_message = _runtime_source(
        graph, "message.historical_user.order_id"
    )
    query_binding = _runtime_source(graph, "binding.product_description")
    order_binding = _runtime_source(graph, "binding.order_id")
    target = _runtime_source(graph, "auto_target.current")
    unit = _runtime_source(graph, "request_unit.current")

    assert plan.runtime_state.historical_user_messages == ()
    assert search_message.message_id != order_message.message_id
    assert order_message.content == "我要查询订单 O-1001。"
    assert order_message.message_id == deterministic_cycle2_setup_uuid(
        fixture_ref, "message.historical_user.order_id"
    )
    assert search_message.received_at < order_message.received_at
    assert query_binding.source_refs == (search_message.message_id,)
    assert order_binding.source_refs == (order_message.message_id,)
    assert order_binding.normalized_value == "O-1001"
    assert order_binding.supersedes is None
    assert order_binding.created_at == order_message.received_at
    assert order_binding.updated_at == order_message.received_at
    assert unit.goal_source_refs == (search_message.message_id,)
    assert unit.input_binding_refs.count(query_binding.binding_id) == 1
    assert unit.input_binding_refs.count(order_binding.binding_id) == 1
    assert target.query_input_binding_ref == query_binding.binding_id
    assert target.query_input_binding_ref != order_binding.binding_id


def test_recovery_fixture_materializes_old_fresh_and_invalidated_snapshots() -> None:
    plan = resolve_cycle2_execution_setup_plan(
        trusted_context_fixture_ref="session:alice",
        initial_state_fixture_refs=(
            "fx-retry-scheduled-obsolete-run-owner-a-v1",
        ),
        environment_fixture_refs=("fx-shipment-current-owner-a-v1",),
        fault_ref=(
            "fault:get-shipment:restart-after-retry-finalize-state-invalidated-v1"
        ),
        authenticated_user_message="订单 O-1001 到哪了？",
    )
    graph = fold_cycle2_runtime_records(plan.runtime_state)
    search_message = _runtime_source(
        graph, "message.historical_user.search"
    )
    order_message = _runtime_source(
        graph, "message.historical_user.order_id"
    )
    auxiliary = _runtime_source(
        graph, "message.historical_user.recovery"
    )
    query_binding = _runtime_source(graph, "binding.product_description")
    old_order_binding = _runtime_source(graph, "binding.order_id")
    fresh_order_binding = _runtime_source(
        graph, "binding.order_id.recovery_root"
    )
    task = _runtime_source(graph, "task.current")
    unit = _runtime_source(graph, "request_unit.current")
    target = _runtime_source(graph, "auto_target.current")
    run = _runtime_source(graph, "recovery_root.run")
    link = _runtime_source(graph, "recovery_root.link")
    replacement_run = _runtime_source(graph, "recovery_replacement.run")
    replacement_link = _runtime_source(graph, "recovery_replacement.link")
    manifest = _runtime_source(graph, "recovery_root.context_manifest")
    gate = _runtime_source(graph, "recovery_root.gate")
    tool = _runtime_source(graph, "recovery_root.tool_call")
    trace = _runtime_source(
        graph, "recovery_root.trace.message_accepted"
    )

    assert plan.runtime_state.historical_user_messages == (auxiliary,)
    assert search_message.received_at < order_message.received_at
    assert order_message.received_at < auxiliary.received_at
    assert auxiliary.received_at == run.started_at
    assert old_order_binding.source_refs == (order_message.message_id,)
    assert old_order_binding.supersedes is None
    assert fresh_order_binding.source_refs == (auxiliary.message_id,)
    assert fresh_order_binding.supersedes == old_order_binding.binding_id
    assert unit.goal_source_refs == (search_message.message_id,)
    assert unit.input_binding_refs == (
        query_binding.binding_id,
        fresh_order_binding.binding_id,
    )
    assert task.state_version == unit.state_version == 4
    assert link.base_task_state_version == 2
    assert link.result_task_state_version is None
    assert replacement_run.run_id != run.run_id
    assert replacement_run.conversation_id == run.conversation_id
    assert replacement_run.status is AgentRunStatusV2.RUNNING
    assert replacement_run.started_at >= run.started_at
    assert replacement_link.run_id == replacement_run.run_id
    assert replacement_link.task_id == task.task_id
    assert replacement_link.base_task_state_version == task.state_version
    assert replacement_link.result_task_state_version is None
    assert manifest.selected_message_refs == (auxiliary.message_id,)
    assert manifest.task_state_ref_and_version.state_version == 3
    assert gate.proposed_base_task_state_version == 3
    assert gate.validated_task_state_version == 3
    assert tool.validated_task_state_version == 3
    assert gate.argument_binding_refs == (query_binding.binding_id,)
    assert tool.argument_binding_refs == (query_binding.binding_id,)
    assert gate.verified_target_ref == target.verified_target_ref
    assert tool.verified_target_ref == target.verified_target_ref
    assert trace.message_ref == auxiliary.message_id
    assert task.updated_at == unit.updated_at
    assert task.updated_at > tool.attempts[0].finished_at


def test_corrected_claim_overlay_preserves_history_and_only_false_is_current() -> None:
    plan = resolve_cycle2_execution_setup_plan(
        trusted_context_fixture_ref="session:alice",
        initial_state_fixture_refs=(
            "fx-corrected-not-received-claim-owner-a-v1",
            "fx-verified-order-target-o1001-owner-a-v1",
        ),
        environment_fixture_refs=("fx-shipment-delivered-owner-a-v1",),
        fault_ref=None,
    )
    graph = fold_cycle2_runtime_records(plan.runtime_state)
    true_message = _runtime_source(
        graph, "message.historical_user.shipment_not_received.true"
    )
    false_message = _runtime_source(
        graph, "message.historical_user.shipment_not_received.false"
    )
    true_binding = _runtime_source(
        graph, "binding.shipment_not_received.true"
    )
    false_binding = _runtime_source(
        graph, "binding.shipment_not_received.false"
    )
    task = _runtime_source(graph, "task.current")
    unit = _runtime_source(graph, "request_unit.current")

    assert plan.runtime_state.historical_user_messages == ()
    assert true_message.message_id != false_message.message_id
    assert true_message.received_at < false_message.received_at
    assert true_binding.normalized_value is True
    assert true_binding.source_refs == (true_message.message_id,)
    assert true_binding.supersedes is None
    assert false_binding.normalized_value is False
    assert false_binding.source_refs == (false_message.message_id,)
    assert false_binding.supersedes == true_binding.binding_id
    assert true_binding.binding_id not in unit.input_binding_refs
    assert unit.input_binding_refs.count(false_binding.binding_id) == 1
    assert task.state_version == unit.state_version == 4
    assert task.updated_at == unit.updated_at == false_binding.updated_at


def test_unique_target_provenance_tampering_fails_closed() -> None:
    plan = resolve_cycle2_execution_setup_plan(
        trusted_context_fixture_ref="session:alice",
        initial_state_fixture_refs=(
            "fx-verified-order-target-o1001-owner-a-v1",
        ),
        environment_fixture_refs=(),
        fault_ref=None,
    )
    state = plan.runtime_state
    query_binding = _runtime_source(
        state.base_records, "binding.product_description"
    )
    order_message = _runtime_source(
        state.base_records, "message.historical_user.order_id"
    )
    unit = _runtime_source(state.base_records, "request_unit.current")
    tampered_records = (
        _replace_runtime_source(
            state.base_records,
            role="message.historical_user.order_id",
            update={"content": "我要查询订单 O-1002。"},
        ),
        _replace_runtime_source(
            state.base_records,
            role="binding.order_id",
            update={"source_refs": query_binding.source_refs},
        ),
        _replace_runtime_source(
            state.base_records,
            role="binding.order_id",
            update={"supersedes": query_binding.binding_id},
        ),
        _replace_runtime_source(
            state.base_records,
            role="request_unit.current",
            update={"input_binding_refs": (query_binding.binding_id,)},
        ),
    )
    for records in tampered_records:
        with pytest.raises(Cycle2SeedError):
            fold_cycle2_runtime_records(
                state.model_copy(update={"base_records": records})
            )
    with pytest.raises(Cycle2SeedError):
        fold_cycle2_runtime_records(
            state.model_copy(
                update={"historical_user_messages": (order_message,)}
            )
        )
    assert len(unit.input_binding_refs) == 2


def test_recovery_provenance_tampering_fails_closed() -> None:
    plan = resolve_cycle2_execution_setup_plan(
        trusted_context_fixture_ref="session:alice",
        initial_state_fixture_refs=(
            "fx-retry-scheduled-obsolete-run-owner-a-v1",
        ),
        environment_fixture_refs=("fx-shipment-current-owner-a-v1",),
        fault_ref=(
            "fault:get-shipment:restart-after-retry-finalize-state-invalidated-v1"
        ),
        authenticated_user_message="订单 O-1001 到哪了？",
    )
    state = plan.runtime_state
    old_order_binding = _runtime_source(state.base_records, "binding.order_id")
    query_binding = _runtime_source(
        state.base_records, "binding.product_description"
    )
    auxiliary = _runtime_source(
        state.base_records, "message.historical_user.recovery"
    )
    order_message = _runtime_source(
        state.base_records, "message.historical_user.order_id"
    )
    tool = _runtime_source(state.base_records, "recovery_root.tool_call")
    obsolete_run = _runtime_source(state.base_records, "recovery_root.run")
    tampered_records = (
        _replace_runtime_source(
            state.base_records,
            role="binding.order_id.recovery_root",
            update={"source_refs": (order_message.message_id,)},
        ),
        _replace_runtime_source(
            state.base_records,
            role="binding.order_id.recovery_root",
            update={"supersedes": None},
        ),
        _replace_runtime_source(
            state.base_records,
            role="request_unit.current",
            update={
                "input_binding_refs": (
                    query_binding.binding_id,
                    old_order_binding.binding_id,
                )
            },
        ),
        _replace_runtime_source(
            state.base_records,
            role="recovery_root.gate",
            update={
                "proposed_base_task_state_version": 2,
                "validated_task_state_version": 2,
            },
        ),
        _replace_runtime_source(
            state.base_records,
            role="task.current",
            update={"updated_at": tool.attempts[0].finished_at},
        ),
        tuple(
            record
            for record in state.base_records
            if record.record_role != "recovery_replacement.link"
        ),
        _replace_runtime_source(
            state.base_records,
            role="recovery_replacement.run",
            update={"run_id": obsolete_run.run_id},
        ),
        _replace_runtime_source(
            state.base_records,
            role="recovery_replacement.run",
            update={"conversation_id": uuid4()},
        ),
        _replace_runtime_source(
            state.base_records,
            role="recovery_replacement.link",
            update={"task_id": uuid4()},
        ),
        _replace_runtime_source(
            state.base_records,
            role="recovery_replacement.link",
            update={"base_task_state_version": 3},
        ),
    )
    for records in tampered_records:
        with pytest.raises(Cycle2SeedError):
            fold_cycle2_runtime_records(
                state.model_copy(update={"base_records": records})
            )
    with pytest.raises(Cycle2SeedError):
        fold_cycle2_runtime_records(
            state.model_copy(
                update={"historical_user_messages": (order_message,)}
            )
        )
    assert state.historical_user_messages == (auxiliary,)


def test_corrected_claim_overlay_tampering_fails_closed() -> None:
    plan = resolve_cycle2_execution_setup_plan(
        trusted_context_fixture_ref="session:alice",
        initial_state_fixture_refs=(
            "fx-corrected-not-received-claim-owner-a-v1",
            "fx-verified-order-target-o1001-owner-a-v1",
        ),
        environment_fixture_refs=("fx-shipment-delivered-owner-a-v1",),
        fault_ref=None,
    )
    state = plan.runtime_state
    overlay = state.overlays[0]
    true_message = _runtime_source(
        state.base_records,
        "message.historical_user.shipment_not_received.true",
    )
    true_binding = _runtime_source(
        state.base_records, "binding.shipment_not_received.true"
    )
    false_binding = _runtime_source(
        overlay.next_records, "binding.shipment_not_received.false"
    )
    unit = _runtime_source(overlay.next_records, "request_unit.current")
    tampered_next_records = (
        _replace_runtime_source(
            overlay.next_records,
            role="message.historical_user.shipment_not_received.false",
            update={"content": "订单 O-1001 仍未收到。"},
        ),
        _replace_runtime_source(
            overlay.next_records,
            role="binding.shipment_not_received.false",
            update={"source_refs": (true_message.message_id,)},
        ),
        _replace_runtime_source(
            overlay.next_records,
            role="binding.shipment_not_received.false",
            update={"supersedes": None},
        ),
        _replace_runtime_source(
            overlay.next_records,
            role="request_unit.current",
            update={
                "input_binding_refs": (
                    *unit.input_binding_refs,
                    true_binding.binding_id,
                )
            },
        ),
    )
    for next_records in tampered_next_records:
        with pytest.raises(Cycle2SeedError):
            fold_cycle2_runtime_records(
                state.model_copy(
                    update={
                        "overlays": (
                            overlay.model_copy(
                                update={"next_records": next_records}
                            ),
                        )
                    }
                )
            )
    assert false_binding.supersedes == true_binding.binding_id


def test_seed_resolution_rejects_unknown_fault_only_and_conflicting_rows() -> None:
    with pytest.raises(Cycle2SeedError):
        resolve_cycle2_seed_plan(["fx-reference-only-v1"])
    with pytest.raises(Cycle2SeedError):
        resolve_cycle2_seed_plan(
            ["fault:get-shipment:transient-once-v1"]
        )
    with pytest.raises(Cycle2SeedError):
        resolve_cycle2_seed_plan(
            [
                "fx-shipment-current-owner-a-v1",
                "fx-shipment-refresh-stalled-owner-a-v1",
            ]
        )


def test_pair_digest_is_recomputed_from_resolved_canonical_projection() -> None:
    plan = resolve_cycle2_seed_plan(
        ["fx-dynamic-tool-pair-owner-a-v1"]
    )
    digest = compute_cycle2_pair_seed_digest(plan)
    projection = {
        "digest_schema": "cycle2-owner-order-initial-state.p0.v1",
        "owner_customer_id": plan.owner_customer_id,
        "session_refs": ["session:alice"],
        "order_seeds": [
            seed.model_dump(mode="json") for seed in plan.order_seeds
        ],
        "search_document_seeds": [
            seed.model_dump(mode="json")
            for seed in plan.search_document_seeds
        ],
        "shipment_seeds": [
            seed.model_dump(mode="json") for seed in plan.shipment_seeds
        ],
        "initial_record_graph": [],
        "initial_record_references": [],
    }
    expected = hashlib.sha256(
        json.dumps(
            projection,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    assert digest == expected
    assert len(digest) == 64
    with_fault = resolve_cycle2_seed_plan(
        [
            "fx-dynamic-tool-pair-owner-a-v1",
            "fault:get-shipment:transient-once-v1",
        ]
    )
    assert compute_cycle2_pair_seed_digest(with_fault) == digest


def test_seed_loader_is_atomic_and_refreshes_only_the_exact_shipment_source(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    factory = build_session_factory(engine)
    try:
        partial = resolve_cycle2_seed_plan(
            ["fx-shipment-current-owner-a-v1"]
        )
        with pytest.raises(Cycle2SeedError):
            apply_cycle2_seed_plan(factory, partial)
        with factory() as session:
            assert session.scalar(select(func.count()).select_from(MockOrderModel)) == 0
            assert session.scalar(select(func.count()).select_from(MockShipmentModel)) == 0

        initial = resolve_cycle2_seed_plan(
            ["fx-dynamic-tool-pair-owner-a-v1"]
        )
        apply_cycle2_seed_plan(factory, initial)
        refresh = resolve_cycle2_seed_plan(
            ["fx-shipment-refresh-stalled-owner-a-v1"]
        )
        apply_cycle2_seed_plan(factory, refresh)
        with factory() as session:
            assert session.scalar(select(func.count()).select_from(MockOrderModel)) == 1
            assert session.scalar(
                select(func.count()).select_from(MockOrderSearchDocumentModel)
            ) == 1
            assert session.scalar(select(func.count()).select_from(MockShipmentModel)) == 1
            shipment = session.scalar(select(MockShipmentModel))
            assert shipment is not None
            assert (
                shipment.shipment_payload["latest_event_code"]
                == "ARRIVED_AT_FACILITY"
            )
            assert session.scalar(select(func.count()).select_from(P0RecordModel)) == 0
    finally:
        engine.dispose()


class _SetupAttachmentTarget:
    def __init__(
        self,
        *,
        fail: bool = False,
        fail_after_attach: bool = False,
    ) -> None:
        if fail and fail_after_attach:
            raise ValueError("attachment failure mode must be exact")
        self.fail = fail
        self.fail_after_attach = fail_after_attach
        self.setup: Cycle2DetachedExecutionSetup | None = None
        self.last_setup: Cycle2DetachedExecutionSetup | None = None

    def attach_cycle2_execution_setup(
        self,
        setup: Cycle2DetachedExecutionSetup,
    ) -> None:
        if self.fail:
            raise RuntimeError("controlled attach failure")
        if self.setup is not None:
            raise RuntimeError("setup already attached")
        self.setup = setup
        self.last_setup = setup
        if self.fail_after_attach:
            raise RuntimeError("controlled failure after target mutation")

    def detach_cycle2_execution_setup(
        self,
        setup: Cycle2DetachedExecutionSetup,
    ) -> None:
        if self.setup is setup:
            self.setup = None


class _CommitFailSessionFactory:
    def __init__(self, real_factory) -> None:
        self.real_factory = real_factory

    def __call__(self):
        return self.real_factory()

    @contextmanager
    def begin(self):
        with self.real_factory() as session:
            with session.begin():
                yield session
                session.rollback()
                raise RuntimeError("controlled commit failure")


def _verified_w12_plan(*, fault_ref: str | None = None):
    return resolve_cycle2_execution_setup_plan(
        trusted_context_fixture_ref="session:alice",
        initial_state_fixture_refs=(
            "fx-verified-order-target-o1001-owner-a-v1",
        ),
        environment_fixture_refs=("fx-shipment-current-owner-a-v1",),
        fault_ref=fault_ref,
    )


def test_w12_fold_materializes_one_final_graph_and_atomic_setup_attaches(
    eval_postgres_namespace,
) -> None:
    plan = _verified_w12_plan(
        fault_ref="fault:get-shipment:transient-once-v1"
    )
    graph = fold_cycle2_runtime_records(plan.runtime_state)
    assert graph
    assert len({(record.record_code, record.record_role) for record in graph}) == len(graph)

    engine = eval_postgres_namespace.build_engine()
    factory = build_session_factory(engine)
    target = _SetupAttachmentTarget()
    try:
        setup = apply_cycle2_execution_setup_plan(
            factory,
            plan,
            attachment_target=target,
        )
        assert setup.is_attached
        assert target.setup is setup
        assert setup.fault_controller is not None
        with factory() as session:
            assert session.scalar(select(func.count()).select_from(MockOrderModel)) == 1
            assert session.scalar(select(func.count()).select_from(MockShipmentModel)) == 1
            assert session.scalar(select(func.count()).select_from(P0RecordModel)) > 0
        setup.detach()
        setup.dispose()
        assert setup.is_disposed
        assert target.setup is None
    finally:
        engine.dispose()


def test_search_observation_candidate_history_reads_one_exact_source_edge(
    eval_postgres_namespace,
) -> None:
    plan = resolve_cycle2_execution_setup_plan(
        trusted_context_fixture_ref="session:alice",
        initial_state_fixture_refs=(
            "fx-superseded-candidate-set-owner-a-v1",
        ),
        environment_fixture_refs=(),
        fault_ref=None,
    )
    engine = eval_postgres_namespace.build_engine()
    factory = build_session_factory(engine)
    target = _SetupAttachmentTarget()
    setup = None
    try:
        setup = apply_cycle2_execution_setup_plan(
            factory,
            plan,
            attachment_target=target,
        )
        adapter = PostgresRecordAdapter(
            factory,
            cycle2_clock=lambda: W12_TRUSTED_CLOCK,
        )
        with factory() as session:
            observation_rows = adapter._cycle2_rows(
                session,
                owner_customer_id="customer-A",
                record_code=P0RecordCode.ORDER_SEARCH_OBSERVATION_RECORD,
            )
            candidate_rows = adapter._cycle2_rows(
                session,
                owner_customer_id="customer-A",
                record_code=P0RecordCode.ORDER_CANDIDATE_SET_RECORD,
            )
        assert len(observation_rows) == 1
        assert len(candidate_rows) == 2
        observation = observation_rows[0][1].source_record
        candidate_sets = tuple(
            row[1].source_record for row in candidate_rows
        )
        facts = _cycle2_search_observation_source_edge_facts(
            observation=observation,
            rooted_candidate_sets=candidate_sets,
        )
        assert facts[0] == observation.source_tool_call_id
        assert facts[1] is None
        assert {
            (record.task_id, record.request_unit_id)
            for record in candidate_sets
        } == {(facts[2], facts[3])}
    finally:
        if setup is not None:
            setup.detach()
            setup.dispose()
        engine.dispose()


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    (
        ("private_owner_scope_ref", "customer-B"),
        ("source_tool_call_id", uuid4()),
        ("task_id", uuid4()),
        ("request_unit_id", uuid4()),
        ("search_observation_ref", uuid4()),
        ("search_observation_record_schema_version", "wrong-schema"),
        ("search_observation_source_version", "wrong-version"),
    ),
)
def test_search_observation_candidate_history_source_tamper_fails_closed(
    field_name: str,
    bad_value: object,
) -> None:
    plan = resolve_cycle2_execution_setup_plan(
        trusted_context_fixture_ref="session:alice",
        initial_state_fixture_refs=(
            "fx-superseded-candidate-set-owner-a-v1",
        ),
        environment_fixture_refs=(),
        fault_ref=None,
    )
    graph = fold_cycle2_runtime_records(plan.runtime_state)
    observation = _runtime_source(graph, "observation.search.search")
    candidate_sets = tuple(
        record.source_record
        for record in graph
        if record.record_role.startswith("candidate_set.")
    )
    assert len(candidate_sets) == 2
    tampered = candidate_sets[1].model_copy(
        update={field_name: bad_value}
    )

    with pytest.raises(P0PersistenceIntegrityError) as caught:
        _cycle2_search_observation_source_edge_facts(
            observation=observation,
            rooted_candidate_sets=(candidate_sets[0], tampered),
        )
    assert caught.value.category is (
        P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH
    )


def test_search_observation_candidate_history_requires_one_rooted_set() -> None:
    plan = resolve_cycle2_execution_setup_plan(
        trusted_context_fixture_ref="session:alice",
        initial_state_fixture_refs=(
            "fx-superseded-candidate-set-owner-a-v1",
        ),
        environment_fixture_refs=(),
        fault_ref=None,
    )
    observation = _runtime_source(
        fold_cycle2_runtime_records(plan.runtime_state),
        "observation.search.search",
    )

    with pytest.raises(P0PersistenceIntegrityError) as caught:
        _cycle2_search_observation_source_edge_facts(
            observation=observation,
            rooted_candidate_sets=(),
        )
    assert caught.value.category is (
        P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH
    )


def test_w12_attach_failure_rolls_back_every_row_and_disposes_controller(
    eval_postgres_namespace,
) -> None:
    plan = _verified_w12_plan(
        fault_ref="fault:get-shipment:transient-once-v1"
    )
    engine = eval_postgres_namespace.build_engine()
    factory = build_session_factory(engine)
    target = _SetupAttachmentTarget(fail=True)
    try:
        with pytest.raises(Cycle2SeedError):
            apply_cycle2_execution_setup_plan(
                factory,
                plan,
                attachment_target=target,
            )
        assert target.setup is None
        with factory() as session:
            for model in (MockOrderModel, MockShipmentModel, P0RecordModel):
                assert session.scalar(select(func.count()).select_from(model)) == 0
        target.fail = False
        with pytest.raises(Cycle2SeedError):
            apply_cycle2_execution_setup_plan(
                factory,
                plan,
                attachment_target=target,
            )
    finally:
        engine.dispose()


def test_w12_partial_attach_failure_detaches_target_and_invalidates_namespace(
    eval_postgres_namespace,
) -> None:
    plan = _verified_w12_plan(
        fault_ref="fault:get-shipment:transient-once-v1"
    )
    engine = eval_postgres_namespace.build_engine()
    factory = build_session_factory(engine)
    target = _SetupAttachmentTarget(fail_after_attach=True)
    try:
        with pytest.raises(Cycle2SeedError):
            apply_cycle2_execution_setup_plan(
                factory,
                plan,
                attachment_target=target,
            )
        assert target.setup is None
        assert target.last_setup is not None
        assert target.last_setup.is_disposed
        with factory() as session:
            for model in (MockOrderModel, MockShipmentModel, P0RecordModel):
                assert session.scalar(select(func.count()).select_from(model)) == 0
        with pytest.raises(Cycle2SeedError):
            apply_cycle2_execution_setup_plan(
                factory,
                plan,
                attachment_target=_SetupAttachmentTarget(),
            )
    finally:
        engine.dispose()


def test_w12_commit_failure_detaches_disposes_and_leaves_namespace_empty(
    eval_postgres_namespace,
) -> None:
    plan = _verified_w12_plan(
        fault_ref="fault:get-shipment:transient-once-v1"
    )
    engine = eval_postgres_namespace.build_engine()
    real_factory = build_session_factory(engine)
    target = _SetupAttachmentTarget()
    try:
        with pytest.raises(Cycle2SeedError):
            apply_cycle2_execution_setup_plan(
                _CommitFailSessionFactory(real_factory),
                plan,
                attachment_target=target,
            )
        assert target.setup is None
        assert target.last_setup is not None
        assert target.last_setup.is_disposed
        with real_factory() as session:
            for model in (MockOrderModel, MockShipmentModel, P0RecordModel):
                assert session.scalar(select(func.count()).select_from(model)) == 0
        with pytest.raises(Cycle2SeedError):
            apply_cycle2_execution_setup_plan(
                real_factory,
                plan,
                attachment_target=_SetupAttachmentTarget(),
            )
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("initial_refs", "environment_refs", "fault_ref", "message"),
    (
        (
            (
                "fx-verified-order-target-o1001-owner-a-v1",
                "fx-corrected-not-received-claim-owner-a-v1",
            ),
            ("fx-shipment-delivered-owner-a-v1",),
            None,
            None,
        ),
        (
            ("fx-stale-shipment-observation-owner-a-v1",),
            (),
            None,
            None,
        ),
        (
            ("fx-retry-scheduled-obsolete-run-owner-a-v1",),
            ("fx-shipment-current-owner-a-v1",),
            "fault:get-shipment:restart-after-retry-finalize-state-invalidated-v1",
            "订单 O-1001 到哪了？",
        ),
    ),
)
def test_w12_overlay_stale_and_recovery_graphs_survive_atomic_postgres_encoding(
    eval_postgres_namespace,
    initial_refs: tuple[str, ...],
    environment_refs: tuple[str, ...],
    fault_ref: str | None,
    message: str | None,
) -> None:
    plan = resolve_cycle2_execution_setup_plan(
        trusted_context_fixture_ref="session:alice",
        initial_state_fixture_refs=initial_refs,
        environment_fixture_refs=environment_refs,
        fault_ref=fault_ref,
        authenticated_user_message=message,
    )
    engine = eval_postgres_namespace.build_engine()
    factory = build_session_factory(engine)
    target = _SetupAttachmentTarget()
    try:
        setup = apply_cycle2_execution_setup_plan(
            factory,
            plan,
            attachment_target=target,
        )
        with factory() as session:
            assert session.scalar(select(func.count()).select_from(P0RecordModel)) == len(
                fold_cycle2_runtime_records(plan.runtime_state)
            )
            history_rows = tuple(
                session.scalars(select(P0RecordStateHistoryModel))
            )
            if plan.runtime_state.recovery_subject_run_id is None:
                assert history_rows == ()
            else:
                assert {
                    (row.record_code, row.state_version)
                    for row in history_rows
                } == {
                    (P0RecordCode.TASK_RECORD.value, 2),
                    (P0RecordCode.TASK_RECORD.value, 3),
                    (P0RecordCode.REQUEST_UNIT_RECORD.value, 2),
                    (P0RecordCode.REQUEST_UNIT_RECORD.value, 3),
                }
                graph = fold_cycle2_runtime_records(plan.runtime_state)
                task = _runtime_source(graph, "task.current")
                unit = _runtime_source(graph, "request_unit.current")
                query_binding = _runtime_source(
                    graph, "binding.product_description"
                )
                old_order_binding = _runtime_source(
                    graph, "binding.order_id"
                )
                fresh_order_binding = _runtime_source(
                    graph, "binding.order_id.recovery_root"
                )
                target_record = _runtime_source(
                    graph, "auto_target.current"
                )
                recovery_tool = _runtime_source(
                    graph, "recovery_root.tool_call"
                )
                historical_task_v2 = (
                    PostgresRecordAdapter._cycle2_historical_row(
                        session,
                        owner_customer_id="customer-A",
                        record_code=P0RecordCode.TASK_RECORD,
                        logical_identity=(("task_id", task.task_id),),
                        state_version=2,
                    )
                )
                historical_unit_v2 = (
                    PostgresRecordAdapter._cycle2_historical_row(
                        session,
                        owner_customer_id="customer-A",
                        record_code=P0RecordCode.REQUEST_UNIT_RECORD,
                        logical_identity=(
                            ("request_unit_id", unit.request_unit_id),
                        ),
                        state_version=2,
                    )
                )
                historical_task_v3 = (
                    PostgresRecordAdapter._cycle2_historical_row(
                        session,
                        owner_customer_id="customer-A",
                        record_code=P0RecordCode.TASK_RECORD,
                        logical_identity=(("task_id", task.task_id),),
                        state_version=3,
                    )
                )
                historical_unit_v3 = (
                    PostgresRecordAdapter._cycle2_historical_row(
                        session,
                        owner_customer_id="customer-A",
                        record_code=P0RecordCode.REQUEST_UNIT_RECORD,
                        logical_identity=(
                            ("request_unit_id", unit.request_unit_id),
                        ),
                        state_version=3,
                    )
                )
                assert historical_task_v2 is not None
                assert historical_unit_v2 is not None
                assert historical_task_v3 is not None
                assert historical_unit_v3 is not None
                assert historical_task_v2.source_record.state_version == 2
                assert (
                    historical_task_v2.source_record.updated_at
                    == target_record.verified_at
                )
                assert (
                    historical_unit_v2.source_record.updated_at
                    == target_record.verified_at
                )
                assert historical_unit_v2.source_record.input_binding_refs == (
                    query_binding.binding_id,
                    old_order_binding.binding_id,
                )
                assert historical_task_v3.source_record.state_version == 3
                assert (
                    historical_task_v3.source_record.updated_at
                    == fresh_order_binding.updated_at
                )
                assert (
                    historical_unit_v3.source_record.updated_at
                    == fresh_order_binding.updated_at
                )
                assert historical_unit_v3.source_record.input_binding_refs == (
                    query_binding.binding_id,
                    fresh_order_binding.binding_id,
                )
                current_task = PostgresRecordAdapter._cycle2_row(
                    session,
                    owner_customer_id="customer-A",
                    record_code=P0RecordCode.TASK_RECORD,
                    logical_identity=(("task_id", task.task_id),),
                )
                current_unit = PostgresRecordAdapter._cycle2_row(
                    session,
                    owner_customer_id="customer-A",
                    record_code=P0RecordCode.REQUEST_UNIT_RECORD,
                    logical_identity=(
                        ("request_unit_id", unit.request_unit_id),
                    ),
                )
                assert current_task is not None
                assert current_unit is not None
                assert current_task[1].source_record.state_version == 4
                assert current_unit[1].source_record.state_version == 4
                assert current_unit[1].source_record.input_binding_refs == (
                    query_binding.binding_id,
                    fresh_order_binding.binding_id,
                )
                assert (
                    current_task[1].source_record.updated_at
                    == current_unit[1].source_record.updated_at
                )
                assert (
                    current_task[1].source_record.updated_at
                    > recovery_tool.attempts[0].finished_at
                )
        if plan.runtime_state.recovery_subject_run_id is not None:
            graph = fold_cycle2_runtime_records(plan.runtime_state)
            task = _runtime_source(graph, "task.current")
            unit = _runtime_source(graph, "request_unit.current")
            obsolete_run = _runtime_source(graph, "recovery_root.run")
            query_binding = _runtime_source(
                graph, "binding.product_description"
            )
            old_order_binding = _runtime_source(graph, "binding.order_id")
            fresh_order_binding = _runtime_source(
                graph, "binding.order_id.recovery_root"
            )
            replacement_run = _runtime_source(
                graph, "recovery_replacement.run"
            )
            replacement_link = _runtime_source(
                graph, "recovery_replacement.link"
            )
            replacement_run_id = replacement_run.run_id
            reader = PostgresRecordAdapter(
                factory,
                cycle2_clock=lambda: W12_TRUSTED_CLOCK,
            )
            owner_scope = TrustedOwnerScope.from_customer_context(
                CustomerContext(
                    subject_ref="subject-A",
                    customer_id="customer-A",
                    auth_scopes=frozenset({"orders:read"}),
                    authenticated_at=datetime(
                        2026, 7, 31, 11, 0, tzinfo=UTC
                    ),
                    session_ref_hash="0" * 64,
                )
            )
            superseded = asyncio.run(
                reader.load_superseded_run_closure_for_owner(
                    owner_scope=owner_scope,
                    obsolete_run_id=obsolete_run.run_id,
                    replacement_run_id=replacement_run_id,
                    request_unit_id=unit.request_unit_id,
                )
            )
            assert superseded is not None
            assert superseded.current_authoritative_run_record == replacement_run
            assert superseded.current_authoritative_link_record == replacement_link
            assert superseded.obsolete_task_record is not None
            assert superseded.obsolete_request_unit_record is not None
            assert superseded.obsolete_task_record.state_version == 2
            assert (
                superseded.obsolete_request_unit_record.input_binding_refs
                == (
                    query_binding.binding_id,
                    old_order_binding.binding_id,
                )
            )
            assert superseded.current_task_record.state_version == 4
            assert superseded.current_request_unit_record.input_binding_refs == (
                query_binding.binding_id,
                fresh_order_binding.binding_id,
            )
            assert (
                superseded.invalidation_kind
                is SupersededRunInvalidationKind.BINDING_INVALIDATED
            )
            assert superseded.obsolete_binding_refs == (
                old_order_binding.binding_id,
            )
            assert superseded.invalidated_binding_refs == (
                old_order_binding.binding_id,
            )
        setup.detach()
        setup.dispose()
    finally:
        engine.dispose()
