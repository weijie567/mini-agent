from __future__ import annotations

import hashlib
import json

import pytest
from sqlalchemy import func, select

from mini_agent.infrastructure.cycle2_fixture_seed import (
    Cycle2SeedError,
    apply_cycle2_seed_plan,
    compute_cycle2_pair_seed_digest,
    cycle2_dispatchable_fixture_catalog,
    resolve_cycle2_seed_plan,
)
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
