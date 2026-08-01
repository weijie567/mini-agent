from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from alembic import command
from sqlalchemy import event, text, update
from sqlalchemy.exc import OperationalError

from mini_agent.core.order import (
    GetOrderOutcome,
    GetOrderQuery,
    OrderLineSummary,
    OrderStatus,
    OrderSummaryProjection,
)
from mini_agent.infrastructure.order.postgres import PostgresGetOrderAdapter
from mini_agent.infrastructure.persistence.database import build_session_factory
from mini_agent.infrastructure.persistence.migrations import alembic_config
from mini_agent.infrastructure.persistence.models import MockOrderModel

UTC_NOW = datetime(2026, 7, 27, 8, 0, tzinfo=timezone.utc)
ALICE_ORDERED_AT = datetime(2026, 7, 20, 2, 15, tzinfo=timezone.utc)
ALICE_STATUS_UPDATED_AT = datetime(
    2026,
    7,
    24,
    9,
    30,
    tzinfo=timezone.utc,
)
BOB_ORDERED_AT = datetime(2026, 7, 19, 3, 20, tzinfo=timezone.utc)
BOB_STATUS_UPDATED_AT = datetime(
    2026,
    7,
    23,
    8,
    10,
    tzinfo=timezone.utc,
)
SOURCE_VERSION_A = (
    "mock-order-source-version.p0.v1:sha256:"
    "861c136b1a41ecef3cd9625dc58524ec452e939b5ca1eb70ebcab69181561c42"
)
SOURCE_VERSION_B = (
    "mock-order-source-version.p0.v1:sha256:"
    "4801da34c67c9405986e368042209dedf87896b16aa5a1eead6031eed5c988be"
)

pytestmark = pytest.mark.anyio


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


def _summary(order_id: str, product_name: str) -> OrderSummaryProjection:
    return OrderSummaryProjection(
        order_number=order_id,
        status=OrderStatus.SHIPPED,
        line_items=(OrderLineSummary(product_name=product_name, quantity=1),),
        ordered_at=ALICE_ORDERED_AT,
        status_updated_at=ALICE_STATUS_UPDATED_AT,
    )


def _alice_summary() -> OrderSummaryProjection:
    return _summary("O-1001", "轻量跑鞋")


def _bob_summary() -> OrderSummaryProjection:
    return OrderSummaryProjection(
        order_number="O-2001",
        status=OrderStatus.FULFILLING,
        line_items=(OrderLineSummary(product_name="合成隔离测试商品", quantity=2),),
        ordered_at=BOB_ORDERED_AT,
        status_updated_at=BOB_STATUS_UPDATED_AT,
    )


async def test_get_order_uses_one_composite_owner_predicate_and_returns_safe_projection(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    statements: list[str] = []

    @event.listens_for(engine, "before_cursor_execute")
    def capture_statement(
        _connection,
        _cursor,
        statement: str,
        _parameters,
        _context,
        _executemany,
    ) -> None:
        if "mock_orders" in statement and statement.lstrip().upper().startswith(
            "SELECT"
        ):
            statements.append(statement)

    adapter = PostgresGetOrderAdapter(build_session_factory(engine))
    try:
        await adapter.seed_mock_order(
            customer_id="customer-A",
            order_summary=_alice_summary(),
        )
        await adapter.seed_mock_order(
            customer_id="customer-B",
            order_summary=_bob_summary(),
        )

        result = await adapter.get_order(
            GetOrderQuery(customer_id="customer-A", order_id="O-1001")
        )

        assert result.outcome is GetOrderOutcome.FOUND
        assert result.order_summary == _alice_summary()
        assert result.source_version == SOURCE_VERSION_A
        assert result.failure_code is None
        assert len(statements) == 1
        normalized_sql = " ".join(statements[0].lower().split())
        assert "mock_orders.customer_id =" in normalized_sql
        assert "mock_orders.order_id =" in normalized_sql
        assert "order_payload" in normalized_sql
        assert "stored_at" not in normalized_sql
    finally:
        engine.dispose()


async def test_foreign_and_nonexistent_orders_are_exactly_indistinguishable(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    adapter = PostgresGetOrderAdapter(build_session_factory(engine))
    try:
        await adapter.seed_mock_order(
            customer_id="customer-B",
            order_summary=_bob_summary(),
        )

        foreign = await adapter.get_order(
            GetOrderQuery(customer_id="customer-A", order_id="O-2001")
        )
        nonexistent = await adapter.get_order(
            GetOrderQuery(customer_id="customer-A", order_id="O-9999")
        )

        assert foreign == nonexistent
        assert foreign.outcome is GetOrderOutcome.NOT_FOUND_OR_NOT_ACCESSIBLE
        assert foreign.order_summary is None
        assert foreign.source_version is None
        assert foreign.failure_code is None
        assert "合成隔离测试商品" not in foreign.model_dump_json()
    finally:
        engine.dispose()


async def test_database_failure_is_bounded_and_not_mapped_to_not_found() -> None:
    class FailingSession:
        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def execute(self, *_args: object, **_kwargs: object) -> None:
            raise OperationalError(
                "SELECT order_payload FROM mock_orders",
                {},
                RuntimeError("private raw database diagnostic"),
            )

    adapter = PostgresGetOrderAdapter(lambda: FailingSession())

    result = await adapter.get_order(
        GetOrderQuery(customer_id="customer-A", order_id="O-1001")
    )

    assert result.outcome is GetOrderOutcome.SYSTEM_FAILURE
    assert result.order_summary is None
    assert result.source_version is None
    assert result.failure_code == "ORDER_STORE_UNAVAILABLE"
    assert "private raw database diagnostic" not in result.model_dump_json()


async def test_source_version_matches_both_fixed_owner_vectors(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    adapter = PostgresGetOrderAdapter(build_session_factory(engine))
    try:
        await adapter.seed_mock_order(
            customer_id="customer-A",
            order_summary=_alice_summary(),
        )
        await adapter.seed_mock_order(
            customer_id="customer-B",
            order_summary=_bob_summary(),
        )

        alice = await adapter.get_order(
            GetOrderQuery(customer_id="customer-A", order_id="O-1001")
        )
        bob = await adapter.get_order(
            GetOrderQuery(customer_id="customer-B", order_id="O-2001")
        )

        assert alice.outcome is GetOrderOutcome.FOUND
        assert alice.source_version == SOURCE_VERSION_A
        assert bob.outcome is GetOrderOutcome.FOUND
        assert bob.source_version == SOURCE_VERSION_B
        assert alice.source_version != bob.source_version
    finally:
        engine.dispose()


async def test_source_version_is_content_sensitive_and_allows_aba_replay(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    adapter = PostgresGetOrderAdapter(build_session_factory(engine))
    original = _alice_summary()
    changed = _summary("O-1001", "轻量越野跑鞋")
    try:
        await adapter.seed_mock_order(
            customer_id="customer-A",
            order_summary=original,
        )
        version_a1 = (
            await adapter.get_order(
                GetOrderQuery(customer_id="customer-A", order_id="O-1001")
            )
        ).source_version

        await adapter.seed_mock_order(
            customer_id="customer-A",
            order_summary=changed,
        )
        version_b = (
            await adapter.get_order(
                GetOrderQuery(customer_id="customer-A", order_id="O-1001")
            )
        ).source_version

        await adapter.seed_mock_order(
            customer_id="customer-A",
            order_summary=original,
        )
        version_a2 = (
            await adapter.get_order(
                GetOrderQuery(customer_id="customer-A", order_id="O-1001")
            )
        ).source_version

        assert version_a1 == SOURCE_VERSION_A
        assert version_b is not None
        assert version_b != version_a1
        assert version_a2 == version_a1
    finally:
        engine.dispose()


@pytest.mark.parametrize("tamper_kind", ("invalid-payload", "order-id-drift"))
async def test_order_corruption_is_bounded_system_failure_without_token(
    eval_postgres_namespace,
    tamper_kind: str,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    adapter = PostgresGetOrderAdapter(build_session_factory(engine))
    try:
        await adapter.seed_mock_order(
            customer_id="customer-A",
            order_summary=_alice_summary(),
        )
        if tamper_kind == "invalid-payload":
            payload = {
                "order_number": "O-1001",
                "private_raw": "Cookie=order-store-secret",
            }
        else:
            payload = _summary(
                "O-9999",
                "Cookie=order-store-secret",
            ).model_dump(mode="json")
        with adapter.session_factory.begin() as session:
            result = session.execute(
                update(MockOrderModel)
                .where(
                    MockOrderModel.customer_id == "customer-A",
                    MockOrderModel.order_id == "O-1001",
                )
                .values(order_payload=payload)
            )
            assert result.rowcount == 1

        loaded = await adapter.get_order(
            GetOrderQuery(customer_id="customer-A", order_id="O-1001")
        )

        assert loaded.outcome is GetOrderOutcome.SYSTEM_FAILURE
        assert loaded.order_summary is None
        assert loaded.source_version is None
        assert loaded.failure_code == "ORDER_STORE_UNAVAILABLE"
        assert "Cookie" not in loaded.model_dump_json()
        assert "O-9999" not in loaded.model_dump_json()
    finally:
        engine.dispose()


async def test_source_version_ignores_forbidden_stored_at_version_source(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    adapter = PostgresGetOrderAdapter(build_session_factory(engine))
    try:
        await adapter.seed_mock_order(
            customer_id="customer-A",
            order_summary=_alice_summary(),
        )
        before = await adapter.get_order(
            GetOrderQuery(customer_id="customer-A", order_id="O-1001")
        )

        with adapter.session_factory.begin() as session:
            result = session.execute(
                update(MockOrderModel)
                .where(
                    MockOrderModel.customer_id == "customer-A",
                    MockOrderModel.order_id == "O-1001",
                )
                .values(stored_at=UTC_NOW + timedelta(days=10))
            )
            assert result.rowcount == 1

        after = await adapter.get_order(
            GetOrderQuery(customer_id="customer-A", order_id="O-1001")
        )

        assert before.source_version == SOURCE_VERSION_A
        assert after.source_version == before.source_version
    finally:
        engine.dispose()


async def test_cycle2_migration_preserves_phase1_order_payload_and_source_bytes(
    eval_postgres_namespace,
) -> None:
    config = alembic_config(
        eval_postgres_namespace.database_url,
        schema=eval_postgres_namespace.schema,
        testing=True,
    )
    command.downgrade(config, "20260728_0003")
    engine = eval_postgres_namespace.build_engine()
    adapter = PostgresGetOrderAdapter(build_session_factory(engine))

    def payload_bytes() -> bytes:
        with engine.connect() as connection:
            payload = connection.scalar(
                text(
                    """
                    SELECT order_payload::text
                    FROM mock_orders
                    WHERE customer_id = :customer_id
                      AND order_id = :order_id
                    """
                ),
                {"customer_id": "customer-A", "order_id": "O-1001"},
            )
        assert isinstance(payload, str)
        return payload.encode("utf-8")

    try:
        await adapter.seed_mock_order(
            customer_id="customer-A",
            order_summary=_alice_summary(),
        )
        before = await adapter.get_order(
            GetOrderQuery(customer_id="customer-A", order_id="O-1001")
        )
        before_payload = payload_bytes()
        before_projection = before.model_dump_json()

        command.upgrade(config, "20260731_0004")

        after_upgrade = await adapter.get_order(
            GetOrderQuery(customer_id="customer-A", order_id="O-1001")
        )
        assert payload_bytes() == before_payload
        assert after_upgrade.model_dump_json() == before_projection
        assert after_upgrade.source_version == before.source_version == SOURCE_VERSION_A

        command.downgrade(config, "20260728_0003")
        after_downgrade = await adapter.get_order(
            GetOrderQuery(customer_id="customer-A", order_id="O-1001")
        )
        assert payload_bytes() == before_payload
        assert after_downgrade.model_dump_json() == before_projection
        assert after_downgrade.source_version == SOURCE_VERSION_A
    finally:
        engine.dispose()
