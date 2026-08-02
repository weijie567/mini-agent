from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from datetime import UTC, datetime

from pydantic import ValidationError

import pytest
from sqlalchemy import func, select

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
        setup.detach()
        setup.dispose()
    finally:
        engine.dispose()
