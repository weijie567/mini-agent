from __future__ import annotations

import json
from hashlib import sha256

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from mini_agent.core.order import (
    GetOrderOutcome,
    GetOrderQuery,
    GetOrderResult,
    OrderSummaryProjection,
)
from mini_agent.infrastructure.persistence.models import MockOrderModel


def _mock_order_source_version(
    *,
    owner_customer_id: str,
    order_id: str,
    safe_projection: OrderSummaryProjection,
) -> str:
    canonical_payload = {
        "source_version_schema": "mock-order-source-version.p0.v1",
        "owner_customer_id": owner_customer_id,
        "order_id": order_id,
        "safe_projection": safe_projection.model_dump(mode="json"),
    }
    canonical_bytes = json.dumps(
        canonical_payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return (
        "mock-order-source-version.p0.v1:sha256:"
        f"{sha256(canonical_bytes).hexdigest()}"
    )


class PostgresGetOrderAdapter:
    """P0 owner-scoped mock-order query with a least-disclosing result."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    async def seed_mock_order(
        self,
        *,
        customer_id: str,
        order_summary: OrderSummaryProjection,
    ) -> None:
        payload = order_summary.model_dump(mode="json")
        statement = (
            insert(MockOrderModel)
            .values(
                customer_id=customer_id,
                order_id=order_summary.order_number,
                order_payload=payload,
            )
            .on_conflict_do_update(
                index_elements=(
                    MockOrderModel.customer_id,
                    MockOrderModel.order_id,
                ),
                set_={"order_payload": payload},
            )
        )
        with self.session_factory.begin() as session:
            session.execute(statement)

    async def get_order(self, query: GetOrderQuery) -> GetOrderResult:
        statement = select(MockOrderModel.order_payload).where(
            MockOrderModel.customer_id == query.customer_id,
            MockOrderModel.order_id == query.order_id,
        )
        try:
            with self.session_factory() as session:
                result = session.execute(statement)
                payload = result.scalar_one_or_none()
            if payload is None:
                return GetOrderResult(
                    outcome=GetOrderOutcome.NOT_FOUND_OR_NOT_ACCESSIBLE
                )
            projection = OrderSummaryProjection.model_validate_json(
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                strict=True,
            )
            if projection.order_number != query.order_id:
                raise ValueError("mock order projection does not match lookup key")
            return GetOrderResult(
                outcome=GetOrderOutcome.FOUND,
                order_summary=projection,
                source_version=_mock_order_source_version(
                    owner_customer_id=query.customer_id,
                    order_id=query.order_id,
                    safe_projection=projection,
                ),
            )
        except (SQLAlchemyError, ValidationError, TypeError, ValueError):
            return GetOrderResult(
                outcome=GetOrderOutcome.SYSTEM_FAILURE,
                failure_code="ORDER_STORE_UNAVAILABLE",
            )
