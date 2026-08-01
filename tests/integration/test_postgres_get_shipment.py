from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event, select, update
from sqlalchemy.exc import OperationalError

from mini_agent.core.shipment import (
    GetShipmentFailureCode,
    GetShipmentInsufficiencyCode,
    GetShipmentOutcome,
    GetShipmentQuery,
    ShipmentEventCode,
    ShipmentStatus,
    compute_shipment_source_version,
    project_get_shipment_agent_output,
)
from mini_agent.infrastructure.persistence.database import build_session_factory
from mini_agent.infrastructure.persistence.models import (
    MockOrderModel,
    MockShipmentModel,
)
from mini_agent.infrastructure.shipment.postgres import PostgresGetShipmentAdapter

OBSERVED_AT = datetime(2026, 8, 2, 8, 0, tzinfo=timezone.utc)
LATEST_EVENT_AT = datetime(2026, 8, 2, 7, 0, tzinfo=timezone.utc)
PROMISED_AT = datetime(2026, 8, 4, 8, 0, tzinfo=timezone.utc)
PACKAGE_REF_A_1001_1 = (
    "mock-owner-package-ref.p0.v1:sha256:"
    "50597e5922582e6739728b5e40136456c0c91daf537e2705ed70941f029b8e34"
)
PACKAGE_REF_B_1001_1 = (
    "mock-owner-package-ref.p0.v1:sha256:"
    "1748f2763b8892efdc6de1766584876198f98691b7c7975b6b968b8038d0546b"
)
PACKAGE_REF_A_1002_1 = (
    "mock-owner-package-ref.p0.v1:sha256:"
    "734d3499cba74f56f3964d99695ca941ffe3a5bdd45bc5a7bb577c5abaceaf82"
)
PACKAGE_REF_A_1001_2 = (
    "mock-owner-package-ref.p0.v1:sha256:"
    "5e0d45e59f51daa8e31fdd7e7dcb070c8ec4d7cf51d4e6da2270f3ac52dfe3ea"
)

pytestmark = pytest.mark.anyio


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


def _timestamp(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _payload(
    *,
    status: str = "IN_TRANSIT",
    event_code: str = "ARRIVED_AT_FACILITY",
) -> dict[str, object]:
    delivered = status == "DELIVERED"
    return {
        "shipment_status": status,
        "latest_event_code": event_code,
        "latest_event_at": _timestamp(LATEST_EVENT_AT),
        "promised_delivery_at": None if delivered else _timestamp(PROMISED_AT),
        "delivered_at": _timestamp(LATEST_EVENT_AT) if delivered else None,
        "observed_at": _timestamp(OBSERVED_AT),
    }


def _seed_order(session_factory, *, customer_id: str, order_id: str) -> None:
    with session_factory.begin() as session:
        session.add(
            MockOrderModel(
                customer_id=customer_id,
                order_id=order_id,
                order_payload={},
            )
        )


def _seed_shipment(
    session_factory,
    *,
    customer_id: str = "customer-A",
    order_id: str = "O-1001",
    package_id: str = "PKG-private-1",
    payload: dict[str, object] | None = None,
) -> None:
    with session_factory.begin() as session:
        session.add(
            MockShipmentModel(
                customer_id=customer_id,
                order_id=order_id,
                package_id=package_id,
                shipment_payload=payload if payload is not None else _payload(),
            )
        )


@pytest.mark.parametrize(
    ("status", "event_code"),
    (
        ("LABEL_CREATED", "LABEL_CREATED"),
        ("IN_TRANSIT", "PICKED_UP"),
        ("IN_TRANSIT", "IN_TRANSIT"),
        ("IN_TRANSIT", "ARRIVED_AT_FACILITY"),
        ("OUT_FOR_DELIVERY", "OUT_FOR_DELIVERY"),
        ("DELIVERED", "DELIVERED"),
    ),
)
async def test_exact_one_package_uses_one_owner_relation_read_and_truth_table(
    eval_postgres_namespace,
    status: str,
    event_code: str,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    session_factory = build_session_factory(engine)
    try:
        _seed_order(session_factory, customer_id="customer-A", order_id="O-1001")
        _seed_shipment(
            session_factory,
            payload=_payload(status=status, event_code=event_code),
        )
        statements: list[str] = []

        @event.listens_for(engine, "before_cursor_execute")
        def capture_relation_sql(
            _connection,
            _cursor,
            statement: str,
            _parameters,
            _context,
            _executemany,
        ) -> None:
            if statement.lstrip().upper().startswith("SELECT") and (
                "mock_shipments" in statement
            ):
                statements.append(statement)

        query = GetShipmentQuery(customer_id="customer-A", order_id="O-1001")
        result = await PostgresGetShipmentAdapter(session_factory).get_shipment(query)

        assert result.outcome is GetShipmentOutcome.FOUND
        assert result.shipment_summary is not None
        assert result.shipment_summary.shipment_status is ShipmentStatus(status)
        assert result.shipment_summary.latest_event_code is ShipmentEventCode(
            event_code
        )
        assert result.observed_at == OBSERVED_AT
        assert result.source_resource_ref == PACKAGE_REF_A_1001_1
        assert "customer-A" not in result.source_resource_ref
        assert "O-1001" not in result.source_resource_ref
        assert "PKG-private-1" not in result.source_resource_ref
        assert result.source_version == compute_shipment_source_version(
            owner_customer_id=query.customer_id,
            order_id=query.order_id,
            source_resource_ref=result.source_resource_ref,
            observed_at=result.observed_at,
            safe_projection=result.shipment_summary,
        )
        assert len(statements) == 1
        normalized_sql = " ".join(statements[0].lower().split())
        assert "mock_orders.customer_id =" in normalized_sql
        assert "mock_orders.order_id =" in normalized_sql
        assert "stored_at" not in normalized_sql

        safe_json = project_get_shipment_agent_output(
            result.shipment_summary
        ).model_dump_json()
        assert "PKG-private-1" not in safe_json
        assert "owner-package" not in safe_json
        assert "customer-A" not in safe_json
        assert "source_version" not in safe_json
    finally:
        engine.dispose()


async def test_foreign_and_absent_orders_are_exactly_indistinguishable(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    session_factory = build_session_factory(engine)
    try:
        _seed_order(session_factory, customer_id="customer-B", order_id="O-2001")
        _seed_shipment(
            session_factory,
            customer_id="customer-B",
            order_id="O-2001",
            package_id="PKG-foreign-secret",
        )
        adapter = PostgresGetShipmentAdapter(session_factory)
        foreign = await adapter.get_shipment(
            GetShipmentQuery(customer_id="customer-A", order_id="O-2001")
        )
        absent = await adapter.get_shipment(
            GetShipmentQuery(customer_id="customer-A", order_id="O-9999")
        )

        assert foreign == absent
        assert foreign.outcome is GetShipmentOutcome.NOT_FOUND_OR_NOT_ACCESSIBLE
        assert "PKG-foreign-secret" not in foreign.model_dump_json()
    finally:
        engine.dispose()


async def test_verified_own_order_without_package_is_no_shipment(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    session_factory = build_session_factory(engine)
    try:
        _seed_order(session_factory, customer_id="customer-A", order_id="O-1001")
        result = await PostgresGetShipmentAdapter(session_factory).get_shipment(
            GetShipmentQuery(customer_id="customer-A", order_id="O-1001")
        )
        assert result == type(result)(outcome=GetShipmentOutcome.NO_SHIPMENT)
    finally:
        engine.dispose()


async def test_multiple_packages_fail_closed_without_count_or_payload_disclosure(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    session_factory = build_session_factory(engine)
    try:
        _seed_order(session_factory, customer_id="customer-A", order_id="O-1001")
        _seed_shipment(session_factory, package_id="PKG-private-1")
        _seed_shipment(session_factory, package_id="PKG-private-2")
        result = await PostgresGetShipmentAdapter(session_factory).get_shipment(
            GetShipmentQuery(customer_id="customer-A", order_id="O-1001")
        )

        assert result.outcome is GetShipmentOutcome.SYSTEM_FAILURE
        assert result.failure_code is (
            GetShipmentFailureCode.SHIPMENT_RELATION_CARDINALITY_VIOLATION
        )
        assert result.shipment_summary is None
        assert result.source_resource_ref is None
        assert "PKG-private" not in result.model_dump_json()
        assert "2" not in result.model_dump_json()
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("missing_key", "expected_code"),
    (
        (
            "latest_event_code",
            GetShipmentInsufficiencyCode.SHIPMENT_LATEST_EVENT_MISSING,
        ),
        (
            "promised_delivery_at",
            GetShipmentInsufficiencyCode.SHIPMENT_PROMISE_MISSING_FOR_ACTIVE_DELIVERY,
        ),
    ),
)
async def test_missing_active_business_fact_is_bounded_facts_insufficient(
    eval_postgres_namespace,
    missing_key: str,
    expected_code: GetShipmentInsufficiencyCode,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    session_factory = build_session_factory(engine)
    try:
        _seed_order(session_factory, customer_id="customer-A", order_id="O-1001")
        payload = _payload()
        payload.pop(missing_key)
        _seed_shipment(session_factory, payload=payload)
        result = await PostgresGetShipmentAdapter(session_factory).get_shipment(
            GetShipmentQuery(customer_id="customer-A", order_id="O-1001")
        )

        assert result.outcome is GetShipmentOutcome.FACTS_INSUFFICIENT
        assert result.insufficiency_code is expected_code
        assert result.shipment_summary is None
        assert result.source_resource_ref is None
    finally:
        engine.dispose()


async def test_missing_delivered_at_is_bounded_facts_insufficient(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    session_factory = build_session_factory(engine)
    try:
        _seed_order(session_factory, customer_id="customer-A", order_id="O-1001")
        payload = _payload(status="DELIVERED", event_code="DELIVERED")
        payload.pop("delivered_at")
        _seed_shipment(session_factory, payload=payload)
        result = await PostgresGetShipmentAdapter(session_factory).get_shipment(
            GetShipmentQuery(customer_id="customer-A", order_id="O-1001")
        )

        assert result.outcome is GetShipmentOutcome.FACTS_INSUFFICIENT
        assert result.insufficiency_code is (
            GetShipmentInsufficiencyCode.SHIPMENT_DELIVERED_AT_MISSING
        )
    finally:
        engine.dispose()


def _extra_key(payload: dict[str, object]) -> None:
    payload["tracking_number"] = "PRIVATE-TRACKING"


def _incompatible_event(payload: dict[str, object]) -> None:
    payload["latest_event_code"] = "DELIVERED"


def _future_event(payload: dict[str, object]) -> None:
    payload["latest_event_at"] = _timestamp(OBSERVED_AT + timedelta(seconds=1))


def _unexpected_delivered_at(payload: dict[str, object]) -> None:
    payload["delivered_at"] = payload["latest_event_at"]


def _non_utc_observed_at(payload: dict[str, object]) -> None:
    payload["observed_at"] = "2026-08-02T16:00:00.000000+08:00"


def _missing_envelope_identity(payload: dict[str, object]) -> None:
    payload.pop("observed_at")


def _missing_promise_with_conflicting_delivery(payload: dict[str, object]) -> None:
    payload.pop("promised_delivery_at")
    payload["delivered_at"] = payload["latest_event_at"]


@pytest.mark.parametrize(
    "mutate",
    (
        _extra_key,
        _incompatible_event,
        _future_event,
        _unexpected_delivered_at,
        _non_utc_observed_at,
        _missing_envelope_identity,
        _missing_promise_with_conflicting_delivery,
    ),
)
async def test_malformed_source_is_integrity_failure_without_partial_data(
    eval_postgres_namespace,
    mutate,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    session_factory = build_session_factory(engine)
    try:
        _seed_order(session_factory, customer_id="customer-A", order_id="O-1001")
        payload = _payload()
        mutate(payload)
        _seed_shipment(session_factory, payload=payload)
        result = await PostgresGetShipmentAdapter(session_factory).get_shipment(
            GetShipmentQuery(customer_id="customer-A", order_id="O-1001")
        )

        assert result.outcome is GetShipmentOutcome.SYSTEM_FAILURE
        assert result.failure_code is GetShipmentFailureCode.SHIPMENT_SOURCE_INTEGRITY
        assert result.shipment_summary is None
        assert result.source_resource_ref is None
        assert "PRIVATE-TRACKING" not in result.model_dump_json()
    finally:
        engine.dispose()


async def test_source_version_ignores_storage_metadata_and_changes_with_safe_content(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    session_factory = build_session_factory(engine)
    query = GetShipmentQuery(customer_id="customer-A", order_id="O-1001")
    try:
        _seed_order(session_factory, customer_id="customer-A", order_id="O-1001")
        original_payload = _payload()
        _seed_shipment(session_factory, payload=original_payload)
        adapter = PostgresGetShipmentAdapter(session_factory)
        first = await adapter.get_shipment(query)
        with session_factory.begin() as session:
            session.execute(
                update(MockShipmentModel)
                .values(stored_at=OBSERVED_AT + timedelta(days=30))
                .where(
                    MockShipmentModel.customer_id == "customer-A",
                    MockShipmentModel.order_id == "O-1001",
                )
            )
        metadata_only = await adapter.get_shipment(query)
        changed_payload = deepcopy(original_payload)
        changed_payload["promised_delivery_at"] = _timestamp(
            PROMISED_AT + timedelta(days=1)
        )
        with session_factory.begin() as session:
            session.execute(
                update(MockShipmentModel)
                .values(shipment_payload=changed_payload)
                .where(
                    MockShipmentModel.customer_id == "customer-A",
                    MockShipmentModel.order_id == "O-1001",
                )
            )
        changed = await adapter.get_shipment(query)

        assert first.outcome is GetShipmentOutcome.FOUND
        assert first.source_resource_ref == PACKAGE_REF_A_1001_1
        assert metadata_only.source_resource_ref == PACKAGE_REF_A_1001_1
        assert first.source_version == metadata_only.source_version
        assert first.source_version != changed.source_version
    finally:
        engine.dispose()


async def test_package_ref_is_stable_and_separates_owner_order_and_package(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    session_factory = build_session_factory(engine)
    try:
        for customer_id, order_id in (
            ("customer-A", "O-1001"),
            ("customer-A", "O-1002"),
            ("customer-B", "O-1001"),
        ):
            _seed_order(
                session_factory,
                customer_id=customer_id,
                order_id=order_id,
            )
            _seed_shipment(
                session_factory,
                customer_id=customer_id,
                order_id=order_id,
            )

        adapter = PostgresGetShipmentAdapter(session_factory)
        first = await adapter.get_shipment(
            GetShipmentQuery(customer_id="customer-A", order_id="O-1001")
        )
        replay = await adapter.get_shipment(
            GetShipmentQuery(customer_id="customer-A", order_id="O-1001")
        )
        other_order = await adapter.get_shipment(
            GetShipmentQuery(customer_id="customer-A", order_id="O-1002")
        )
        other_owner = await adapter.get_shipment(
            GetShipmentQuery(customer_id="customer-B", order_id="O-1001")
        )

        assert first.source_resource_ref == replay.source_resource_ref
        assert first.source_version == replay.source_version
        assert first.source_resource_ref == PACKAGE_REF_A_1001_1
        assert other_order.source_resource_ref == PACKAGE_REF_A_1002_1
        assert other_owner.source_resource_ref == PACKAGE_REF_B_1001_1

        with session_factory.begin() as session:
            session.execute(
                update(MockShipmentModel)
                .values(package_id="PKG-private-2")
                .where(
                    MockShipmentModel.customer_id == "customer-A",
                    MockShipmentModel.order_id == "O-1001",
                )
            )
        other_package = await adapter.get_shipment(
            GetShipmentQuery(customer_id="customer-A", order_id="O-1001")
        )
        refs = {
            first.source_resource_ref,
            other_order.source_resource_ref,
            other_owner.source_resource_ref,
            other_package.source_resource_ref,
        }
        assert other_package.source_resource_ref == PACKAGE_REF_A_1001_2
        assert len(refs) == 4
        assert all(
            ref is not None
            and ref.startswith("mock-owner-package-ref.p0.v1:sha256:")
            for ref in refs
        )
        assert all(
            raw_id not in ref
            for ref in refs
            for raw_id in (
                "customer-A",
                "customer-B",
                "O-1001",
                "O-1002",
                "PKG-private-1",
                "PKG-private-2",
            )
        )
        assert other_package.source_version != first.source_version
    finally:
        engine.dispose()


async def test_database_failure_is_bounded_and_does_not_leak_diagnostic(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    session_factory = build_session_factory(engine)
    try:
        @event.listens_for(engine, "before_cursor_execute")
        def fail_relation_read(
            _connection,
            _cursor,
            statement: str,
            parameters,
            _context,
            _executemany,
        ) -> None:
            if statement.lstrip().upper().startswith("SELECT") and (
                "mock_shipments" in statement
            ):
                raise OperationalError(
                    statement,
                    parameters,
                    RuntimeError("private shipment database diagnostic"),
                )

        result = await PostgresGetShipmentAdapter(session_factory).get_shipment(
            GetShipmentQuery(customer_id="customer-A", order_id="O-1001")
        )

        assert result.outcome is GetShipmentOutcome.SYSTEM_FAILURE
        assert result.failure_code is (
            GetShipmentFailureCode.SHIPMENT_SERVICE_UNAVAILABLE
        )
        assert "private shipment database diagnostic" not in result.model_dump_json()
    finally:
        engine.dispose()
