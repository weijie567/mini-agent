from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from uuid import UUID

import pytest
from sqlalchemy import event, func, select, update
from sqlalchemy.exc import OperationalError

from mini_agent.core.order_search import (
    OrderSearchFailureCode,
    SearchOrdersOutcome,
    build_search_orders_query,
    compute_order_search_snapshot_source_version,
    project_search_orders_agent_output,
)
from mini_agent.infrastructure.order.postgres import PostgresSearchOrdersAdapter
from mini_agent.infrastructure.persistence.database import build_session_factory
from mini_agent.infrastructure.persistence.models import (
    MockOrderModel,
    MockOrderSearchDocumentModel,
    MockOrderSearchSnapshotModel,
)

NOW = datetime(2026, 8, 2, 8, 0, tzinfo=timezone.utc)
ORDER_REF_A_1001 = (
    "mock-owner-order-ref.p0.v1:sha256:"
    "1ca24f9c63edd7133086e932b5d499901a68cadbee8bbd87f034ab66d5dc3dd5"
)
ORDER_REF_B_1001 = (
    "mock-owner-order-ref.p0.v1:sha256:"
    "619a8e99b05347db8fbcf2efb415b3da4d124c87be8f0f0ec720d35d3445b274"
)

pytestmark = pytest.mark.anyio


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


def _seed_document(
    session_factory,
    *,
    customer_id: str,
    order_id: str,
    ordered_at: datetime,
    line_ordinal: int = 1,
    product_name: str = "轻量跑鞋",
    quantity: int = 1,
    product_category: str = "运动鞋",
    search_aliases: list[object] | None = None,
) -> None:
    with session_factory.begin() as session:
        if session.get(MockOrderModel, (customer_id, order_id)) is None:
            session.add(
                MockOrderModel(
                    customer_id=customer_id,
                    order_id=order_id,
                    order_payload={},
                )
            )
        session.add(
            MockOrderSearchDocumentModel(
                customer_id=customer_id,
                order_id=order_id,
                line_ordinal=line_ordinal,
                ordered_at=ordered_at,
                order_number=order_id,
                status="SHIPPED",
                product_name=product_name,
                quantity=quantity,
                product_category=product_category,
                search_aliases=(search_aliases if search_aliases is not None else []),
            )
        )


async def test_search_orders_filters_owner_and_closed_window_before_stable_top_five(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    session_factory = build_session_factory(engine)
    query = build_search_orders_query(
        customer_id="customer-A",
        product_description="  轻量跑鞋 ",
        trusted_now=NOW,
    )
    own_rows = (
        ("O-1002", NOW),
        ("O-1001", NOW),
        ("O-1003", NOW - timedelta(days=1)),
        ("O-1004", NOW - timedelta(days=2)),
        ("O-1005", NOW - timedelta(days=3)),
        ("O-1006", NOW - timedelta(days=4)),
        ("O-1007", query.ordered_at_from),
    )
    try:
        for order_id, ordered_at in own_rows:
            _seed_document(
                session_factory,
                customer_id="customer-A",
                order_id=order_id,
                ordered_at=ordered_at,
            )
        _seed_document(
            session_factory,
            customer_id="customer-B",
            order_id="O-9001",
            ordered_at=NOW,
        )
        _seed_document(
            session_factory,
            customer_id="customer-A",
            order_id="O-8001",
            ordered_at=query.ordered_at_from - timedelta(microseconds=1),
        )
        _seed_document(
            session_factory,
            customer_id="customer-A",
            order_id="O-8002",
            ordered_at=NOW + timedelta(microseconds=1),
        )

        statements: list[str] = []

        @event.listens_for(engine, "before_cursor_execute")
        def capture_search_sql(
            _connection,
            _cursor,
            statement: str,
            _parameters,
            _context,
            _executemany,
        ) -> None:
            if "mock_order_search_documents" in statement:
                statements.append(statement)

        result = await PostgresSearchOrdersAdapter(session_factory).search_orders(query)

        assert result.outcome is SearchOrdersOutcome.MULTIPLE
        assert tuple(candidate.order_number for candidate in result.candidates) == (
            "O-1001",
            "O-1002",
            "O-1003",
            "O-1004",
            "O-1005",
        )
        assert result.truncated is True
        assert result.observed_at == NOW
        candidate_refs = tuple(
            candidate.owner_scoped_order_ref for candidate in result.candidates
        )
        assert len(set(candidate_refs)) == len(candidate_refs)
        assert all(
            ref.startswith("mock-owner-order-ref.p0.v1:sha256:")
            and len(ref.rsplit(":", 1)[-1]) == 64
            for ref in candidate_refs
        )
        assert all(
            candidate.order_number not in candidate.owner_scoped_order_ref
            and "customer-A" not in candidate.owner_scoped_order_ref
            for candidate in result.candidates
        )
        safe_json = project_search_orders_agent_output(result).model_dump_json()
        assert "customer-A" not in safe_json
        assert "mock-owner-order-ref" not in safe_json
        assert all(ref not in safe_json for ref in candidate_refs)
        assert len(statements) == 1
        normalized_sql = " ".join(statements[0].lower().split())
        assert "customer_id =" in normalized_sql
        assert "ordered_at >=" in normalized_sql
        assert "ordered_at <=" in normalized_sql
        assert "ordered_at desc" in normalized_sql
        assert "order_number asc" in normalized_sql

        with session_factory() as session:
            snapshots = tuple(
                session.scalars(select(MockOrderSearchSnapshotModel)).all()
            )
        assert len(snapshots) == 1
        snapshot = snapshots[0]
        assert str(snapshot.snapshot_resource_ref) == result.snapshot_resource_ref
        assert snapshot.customer_id == "customer-A"
        assert snapshot.observed_at == NOW
        assert set(snapshot.snapshot_payload) == {
            "source_version_schema",
            "owner_customer_id",
            "normalized_query",
            "ordered_at_from",
            "ordered_at_to",
            "max_candidates",
            "matching_rule_version",
            "ordered_candidates",
            "truncated",
        }
        assert snapshot.snapshot_payload["normalized_query"] == "轻量跑鞋"
        assert snapshot.snapshot_payload["truncated"] is True
        assert result.snapshot_source_version == (
            compute_order_search_snapshot_source_version(
                query=query,
                ordered_candidates=result.candidates,
                truncated=True,
            )
        )
        snapshot_bytes = json.dumps(
            snapshot.snapshot_payload,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        assert result.snapshot_source_version == (
            "mock-order-search-snapshot-source-version.p0.v1:sha256:"
            f"{sha256(snapshot_bytes).hexdigest()}"
        )
    finally:
        engine.dispose()


async def test_search_matches_name_category_and_alias_and_projects_only_three_lines(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    session_factory = build_session_factory(engine)
    try:
        rows = (
            (1, "通勤鞋", "鞋靴", [" 跑鞋 "]),
            (2, "缓震跑鞋", "鞋靴", []),
            (3, "训练鞋", "跑鞋", []),
            (4, "竞速鞋", "鞋靴", ["ＲＵＮ", "跑鞋", "跑鞋"]),
            (5, "雨靴", "鞋靴", []),
        )
        for ordinal, name, category, aliases in rows:
            _seed_document(
                session_factory,
                customer_id="customer-A",
                order_id="O-1001",
                ordered_at=NOW,
                line_ordinal=ordinal,
                product_name=name,
                product_category=category,
                search_aliases=aliases,
            )
        result = await PostgresSearchOrdersAdapter(session_factory).search_orders(
            build_search_orders_query(
                customer_id="customer-A",
                product_description="跑鞋",
                trusted_now=NOW,
            )
        )

        assert result.outcome is SearchOrdersOutcome.UNIQUE
        candidate = result.candidates[0]
        assert tuple(line.line_ordinal for line in candidate.matched_lines) == (
            1,
            2,
            3,
            4,
        )
        assert tuple(
            item.product_name for item in candidate.public_summary.matching_items
        ) == ("通勤鞋", "缓震跑鞋", "训练鞋")
        assert candidate.matched_lines[3].normalized_search_aliases == ("run", "跑鞋")
    finally:
        engine.dispose()


async def test_no_match_and_foreign_only_write_no_snapshot(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    session_factory = build_session_factory(engine)
    try:
        _seed_document(
            session_factory,
            customer_id="customer-B",
            order_id="O-2001",
            ordered_at=NOW,
        )
        _seed_document(
            session_factory,
            customer_id="customer-A",
            order_id="O-1001",
            ordered_at=NOW,
            product_name="雨伞",
            product_category="雨具",
        )
        result = await PostgresSearchOrdersAdapter(session_factory).search_orders(
            build_search_orders_query(
                customer_id="customer-A",
                product_description="跑鞋",
                trusted_now=NOW,
            )
        )

        assert result == type(result)(outcome=SearchOrdersOutcome.NO_MATCH)
        with session_factory() as session:
            assert session.scalar(
                select(func.count()).select_from(MockOrderSearchSnapshotModel)
            ) == 0
        assert "O-2001" not in result.model_dump_json()
    finally:
        engine.dispose()


async def test_canonical_source_versions_ignore_alias_order_but_change_with_content(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    session_factory = build_session_factory(engine)
    query = build_search_orders_query(
        customer_id="customer-A",
        product_description="跑鞋",
        trusted_now=NOW,
    )
    try:
        _seed_document(
            session_factory,
            customer_id="customer-A",
            order_id="O-1001",
            ordered_at=NOW,
            product_name="训练鞋",
            search_aliases=["跑鞋", "ＲＵＮ", "跑鞋"],
        )
        adapter = PostgresSearchOrdersAdapter(session_factory)
        first = await adapter.search_orders(query)
        with session_factory.begin() as session:
            session.execute(
                update(MockOrderSearchDocumentModel)
                .values(search_aliases=["run", " 跑鞋 "])
                .where(
                    MockOrderSearchDocumentModel.customer_id == "customer-A",
                    MockOrderSearchDocumentModel.order_id == "O-1001",
                )
            )
        reordered = await adapter.search_orders(query)
        with session_factory.begin() as session:
            session.execute(
                update(MockOrderSearchDocumentModel)
                .values(quantity=2)
                .where(
                    MockOrderSearchDocumentModel.customer_id == "customer-A",
                    MockOrderSearchDocumentModel.order_id == "O-1001",
                )
            )
        mutated = await adapter.search_orders(query)

        assert first.candidates[0].candidate_source_version == (
            reordered.candidates[0].candidate_source_version
        )
        assert first.candidates[0].owner_scoped_order_ref == ORDER_REF_A_1001
        assert reordered.candidates[0].owner_scoped_order_ref == ORDER_REF_A_1001
        assert "customer-A" not in ORDER_REF_A_1001
        assert "O-1001" not in ORDER_REF_A_1001
        assert first.snapshot_source_version == reordered.snapshot_source_version
        assert first.snapshot_resource_ref != reordered.snapshot_resource_ref
        assert UUID(first.snapshot_resource_ref) != UUID(
            reordered.snapshot_resource_ref
        )
        assert mutated.candidates[0].candidate_source_version != (
            first.candidates[0].candidate_source_version
        )
        assert mutated.snapshot_source_version != first.snapshot_source_version

        _seed_document(
            session_factory,
            customer_id="customer-B",
            order_id="O-1001",
            ordered_at=NOW,
            product_name="训练鞋",
            search_aliases=["跑鞋"],
        )
        other_owner = await adapter.search_orders(
            build_search_orders_query(
                customer_id="customer-B",
                product_description="跑鞋",
                trusted_now=NOW,
            )
        )
        assert other_owner.candidates[0].owner_scoped_order_ref == ORDER_REF_B_1001
        assert other_owner.candidates[0].owner_scoped_order_ref != ORDER_REF_A_1001
        assert other_owner.snapshot_source_version != first.snapshot_source_version
    finally:
        engine.dispose()


async def test_malformed_source_row_fails_closed_without_snapshot(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    session_factory = build_session_factory(engine)
    try:
        _seed_document(
            session_factory,
            customer_id="customer-A",
            order_id="O-1001",
            ordered_at=NOW,
            search_aliases=[1],
        )
        result = await PostgresSearchOrdersAdapter(session_factory).search_orders(
            build_search_orders_query(
                customer_id="customer-A",
                product_description="跑鞋",
                trusted_now=NOW,
            )
        )

        assert result.outcome is SearchOrdersOutcome.SYSTEM_FAILURE
        assert result.failure_code is (
            OrderSearchFailureCode.ORDER_SEARCH_SOURCE_INTEGRITY
        )
        assert result.candidates == ()
        assert result.snapshot_resource_ref is None
        with session_factory() as session:
            assert session.scalar(
                select(func.count()).select_from(MockOrderSearchSnapshotModel)
            ) == 0
    finally:
        engine.dispose()


async def test_late_snapshot_insert_failure_rolls_back_and_returns_bounded_failure(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    session_factory = build_session_factory(engine)
    try:
        _seed_document(
            session_factory,
            customer_id="customer-A",
            order_id="O-1001",
            ordered_at=NOW,
        )

        @event.listens_for(engine, "before_cursor_execute")
        def fail_snapshot_insert(
            _connection,
            _cursor,
            statement: str,
            parameters,
            _context,
            _executemany,
        ) -> None:
            if statement.lstrip().upper().startswith("INSERT") and (
                "mock_order_search_snapshots" in statement
            ):
                raise OperationalError(
                    statement,
                    parameters,
                    RuntimeError("private snapshot insert diagnostic"),
                )

        result = await PostgresSearchOrdersAdapter(session_factory).search_orders(
            build_search_orders_query(
                customer_id="customer-A",
                product_description="跑鞋",
                trusted_now=NOW,
            )
        )

        assert result.outcome is SearchOrdersOutcome.SYSTEM_FAILURE
        assert result.failure_code is OrderSearchFailureCode.ORDER_SEARCH_UNAVAILABLE
        assert result.candidates == ()
        assert result.snapshot_resource_ref is None
        assert "private snapshot insert diagnostic" not in result.model_dump_json()
        with session_factory() as session:
            assert session.scalar(
                select(func.count()).select_from(MockOrderSearchSnapshotModel)
            ) == 0
    finally:
        engine.dispose()
