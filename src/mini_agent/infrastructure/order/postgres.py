from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha256
from typing import Any
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from mini_agent.core.order import (
    GetOrderOutcome,
    GetOrderQuery,
    GetOrderResult,
    OrderStatus,
    OrderSummaryProjection,
)
from mini_agent.core.order_search import (
    ORDER_SEARCH_MAX_CANDIDATES,
    OrderCandidate,
    OrderSearchLine,
    OrderSearchFailureCode,
    SearchOrdersOutcome,
    SearchOrdersQuery,
    SearchOrdersResult,
    build_order_candidate_public_summary,
    compute_order_candidate_source_version,
    compute_order_search_snapshot_source_version,
    match_order_lines,
    order_is_within_search_window,
    sort_order_candidates,
)
from mini_agent.infrastructure.persistence.models import (
    MockOrderModel,
    MockOrderSearchDocumentModel,
    MockOrderSearchSnapshotModel,
)

_OWNER_ORDER_REF_SCHEMA = "mock-owner-order-ref.p0.v1"


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


def _utc_source_timestamp(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _owner_scoped_order_ref(*, customer_id: str, order_id: str) -> str:
    canonical_payload = {
        "ref_schema": _OWNER_ORDER_REF_SCHEMA,
        "owner_customer_id": customer_id,
        "order_id": order_id,
    }
    canonical_bytes = json.dumps(
        canonical_payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return (
        f"{_OWNER_ORDER_REF_SCHEMA}:sha256:"
        f"{sha256(canonical_bytes).hexdigest()}"
    )


@dataclass
class _SearchSourceOrder:
    order_id: str
    ordered_at: datetime
    order_number: str
    status: OrderStatus
    lines: list[OrderSearchLine] = field(default_factory=list)


def _search_snapshot_payload(
    *,
    query: SearchOrdersQuery,
    candidates: tuple[OrderCandidate, ...],
    truncated: bool,
) -> dict[str, object]:
    return {
        "source_version_schema": (
            "mock-order-search-snapshot-source-version.p0.v1"
        ),
        "owner_customer_id": query.customer_id,
        "normalized_query": query.product_description,
        "ordered_at_from": _utc_source_timestamp(query.ordered_at_from),
        "ordered_at_to": _utc_source_timestamp(query.ordered_at_to),
        "max_candidates": query.max_candidates,
        "matching_rule_version": query.matching_rule_version,
        "ordered_candidates": [
            {
                "ordinal": ordinal,
                "owner_scoped_order_ref": candidate.owner_scoped_order_ref,
                "candidate_source_version": candidate.candidate_source_version,
            }
            for ordinal, candidate in enumerate(candidates, start=1)
        ],
        "truncated": truncated,
    }


def _search_candidates_from_rows(
    *,
    query: SearchOrdersQuery,
    rows: tuple[Any, ...],
) -> tuple[OrderCandidate, ...]:
    source_orders: dict[str, _SearchSourceOrder] = {}
    for row in rows:
        if row.customer_id != query.customer_id:
            raise ValueError("search source row escaped trusted owner scope")
        if row.order_id != row.order_number:
            raise ValueError("search source order identity is inconsistent")
        GetOrderQuery(customer_id=query.customer_id, order_id=row.order_id)
        if not order_is_within_search_window(row.ordered_at, query=query):
            raise ValueError("search source row escaped the trusted time window")
        if type(row.search_aliases) is not list or any(
            type(alias) is not str for alias in row.search_aliases
        ):
            raise TypeError("search_aliases must be a JSON array of strings")

        source = source_orders.get(row.order_id)
        status = OrderStatus(row.status)
        if source is None:
            source = _SearchSourceOrder(
                order_id=row.order_id,
                ordered_at=row.ordered_at,
                order_number=row.order_number,
                status=status,
            )
            source_orders[row.order_id] = source
        elif (
            source.ordered_at != row.ordered_at
            or source.order_number != row.order_number
            or source.status is not status
        ):
            raise ValueError("search source order metadata is inconsistent")
        source.lines.append(
            OrderSearchLine(
                line_ordinal=row.line_ordinal,
                product_name=row.product_name,
                quantity=row.quantity,
                product_category=row.product_category,
                search_aliases=tuple(row.search_aliases),
            )
        )

    candidates: list[OrderCandidate] = []
    for source in source_orders.values():
        matched_lines = match_order_lines(query.product_description, source.lines)
        if not matched_lines:
            continue
        public_summary = build_order_candidate_public_summary(
            order_number=source.order_number,
            ordered_at=source.ordered_at,
            status=source.status,
            matched_lines=matched_lines,
        )
        candidates.append(
            OrderCandidate(
                owner_scoped_order_ref=_owner_scoped_order_ref(
                    customer_id=query.customer_id,
                    order_id=source.order_id,
                ),
                order_number=source.order_number,
                ordered_at=source.ordered_at,
                status=source.status,
                matched_lines=matched_lines,
                public_summary=public_summary,
                candidate_source_version=compute_order_candidate_source_version(
                    owner_customer_id=query.customer_id,
                    order_id=source.order_id,
                    ordered_at=source.ordered_at,
                    status=source.status,
                    matched_lines=matched_lines,
                    public_summary=public_summary,
                    matching_rule_version=query.matching_rule_version,
                ),
            )
        )
    return sort_order_candidates(candidates)


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


class PostgresSearchOrdersAdapter:
    """Owner-scoped search and durable raw snapshot in one transaction."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    async def search_orders(self, query: SearchOrdersQuery) -> SearchOrdersResult:
        statement = (
            select(
                MockOrderSearchDocumentModel.customer_id,
                MockOrderSearchDocumentModel.order_id,
                MockOrderSearchDocumentModel.line_ordinal,
                MockOrderSearchDocumentModel.ordered_at,
                MockOrderSearchDocumentModel.order_number,
                MockOrderSearchDocumentModel.status,
                MockOrderSearchDocumentModel.product_name,
                MockOrderSearchDocumentModel.quantity,
                MockOrderSearchDocumentModel.product_category,
                MockOrderSearchDocumentModel.search_aliases,
            )
            .where(
                MockOrderSearchDocumentModel.customer_id == query.customer_id,
                MockOrderSearchDocumentModel.ordered_at >= query.ordered_at_from,
                MockOrderSearchDocumentModel.ordered_at <= query.ordered_at_to,
            )
            .order_by(
                MockOrderSearchDocumentModel.ordered_at.desc(),
                MockOrderSearchDocumentModel.order_number.asc(),
                MockOrderSearchDocumentModel.order_id.asc(),
                MockOrderSearchDocumentModel.line_ordinal.asc(),
            )
        )
        try:
            with self.session_factory.begin() as session:
                rows = tuple(session.execute(statement).all())
                all_candidates = _search_candidates_from_rows(
                    query=query,
                    rows=rows,
                )
                if not all_candidates:
                    return SearchOrdersResult(outcome=SearchOrdersOutcome.NO_MATCH)

                truncated = len(all_candidates) > ORDER_SEARCH_MAX_CANDIDATES
                candidates = all_candidates[:ORDER_SEARCH_MAX_CANDIDATES]
                snapshot_source_version = (
                    compute_order_search_snapshot_source_version(
                        query=query,
                        ordered_candidates=candidates,
                        truncated=truncated,
                    )
                )
                snapshot_resource_ref = uuid4()
                session.execute(
                    insert(MockOrderSearchSnapshotModel).values(
                        snapshot_resource_ref=snapshot_resource_ref,
                        customer_id=query.customer_id,
                        observed_at=query.ordered_at_to,
                        snapshot_payload=_search_snapshot_payload(
                            query=query,
                            candidates=candidates,
                            truncated=truncated,
                        ),
                    )
                )
                outcome = (
                    SearchOrdersOutcome.UNIQUE
                    if len(candidates) == 1
                    else SearchOrdersOutcome.MULTIPLE
                )
                return SearchOrdersResult(
                    outcome=outcome,
                    candidates=candidates,
                    truncated=truncated,
                    snapshot_resource_ref=str(snapshot_resource_ref),
                    snapshot_source_version=snapshot_source_version,
                    observed_at=query.ordered_at_to,
                )
        except SQLAlchemyError:
            return SearchOrdersResult(
                outcome=SearchOrdersOutcome.SYSTEM_FAILURE,
                failure_code=OrderSearchFailureCode.ORDER_SEARCH_UNAVAILABLE,
            )
        except (ValidationError, TypeError, ValueError, UnicodeError):
            return SearchOrdersResult(
                outcome=SearchOrdersOutcome.SYSTEM_FAILURE,
                failure_code=OrderSearchFailureCode.ORDER_SEARCH_SOURCE_INTEGRITY,
            )
