from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event
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

UTC_NOW = datetime(2026, 7, 27, 8, 0, tzinfo=timezone.utc)

pytestmark = pytest.mark.anyio


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


def _summary(order_id: str, product_name: str) -> OrderSummaryProjection:
    return OrderSummaryProjection(
        order_number=order_id,
        status=OrderStatus.SHIPPED,
        line_items=(OrderLineSummary(product_name=product_name, quantity=1),),
        ordered_at=UTC_NOW,
        status_updated_at=UTC_NOW + timedelta(minutes=1),
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
            order_summary=_summary("O-1001", "轻量跑鞋"),
        )
        await adapter.seed_mock_order(
            customer_id="customer-B",
            order_summary=_summary("O-2001", "Bob private product"),
        )

        result = await adapter.get_order(
            GetOrderQuery(customer_id="customer-A", order_id="O-1001")
        )

        assert result.outcome is GetOrderOutcome.FOUND
        assert result.order_summary == _summary("O-1001", "轻量跑鞋")
        assert result.failure_code is None
        assert len(statements) == 1
        normalized_sql = " ".join(statements[0].lower().split())
        assert "mock_orders.customer_id =" in normalized_sql
        assert "mock_orders.order_id =" in normalized_sql
        assert "order_payload" in normalized_sql
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
            order_summary=_summary("O-2001", "Bob private product"),
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
        assert foreign.failure_code is None
        assert "Bob private product" not in foreign.model_dump_json()
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
    assert result.failure_code == "ORDER_STORE_UNAVAILABLE"
    assert "private raw database diagnostic" not in result.model_dump_json()
