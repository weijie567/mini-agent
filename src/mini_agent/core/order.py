"""Scoped ``get_order`` business Port value objects."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Self

from pydantic import Field, field_validator, model_validator

from .common import ModelVisibleModel, RuntimePrivateModel, require_utc

NonEmptyString = Annotated[str, Field(min_length=1)]
OrderId = Annotated[str, Field(pattern=r"^O-[0-9]{4,20}$")]
GetOrderSourceVersion = Annotated[
    str,
    Field(
        strict=True,
        pattern=r"^mock-order-source-version\.p0\.v1:sha256:[0-9a-f]{64}$",
    ),
]


class OrderStatus(StrEnum):
    CREATED = "CREATED"
    PAID = "PAID"
    FULFILLING = "FULFILLING"
    SHIPPED = "SHIPPED"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"


class OrderLineSummary(ModelVisibleModel):
    product_name: NonEmptyString
    quantity: Annotated[int, Field(ge=1)]


class OrderSummaryProjection(ModelVisibleModel):
    """Minimum-disclosure order facts approved for model/user projection."""

    order_number: OrderId
    status: OrderStatus
    line_items: Annotated[tuple[OrderLineSummary, ...], Field(min_length=1)]
    ordered_at: datetime
    status_updated_at: datetime

    @field_validator("ordered_at", "status_updated_at")
    @classmethod
    def order_timestamps_are_utc(cls, value: datetime) -> datetime:
        return require_utc(value, field_name="OrderSummaryProjection timestamp")

    @model_validator(mode="after")
    def status_update_is_not_before_order(self) -> Self:
        if self.status_updated_at < self.ordered_at:
            raise ValueError("status_updated_at cannot precede ordered_at")
        return self


class GetOrderQuery(RuntimePrivateModel):
    """Outbound query combining trusted identity and a validated business input."""

    customer_id: NonEmptyString
    order_id: OrderId


class GetOrderOutcome(StrEnum):
    FOUND = "FOUND"
    NOT_FOUND_OR_NOT_ACCESSIBLE = "NOT_FOUND_OR_NOT_ACCESSIBLE"
    SYSTEM_FAILURE = "SYSTEM_FAILURE"


class GetOrderResult(RuntimePrivateModel):
    outcome: GetOrderOutcome
    order_summary: OrderSummaryProjection | None = None
    source_version: GetOrderSourceVersion | None = None
    failure_code: NonEmptyString | None = None

    @model_validator(mode="after")
    def result_shape_matches_outcome(self) -> Self:
        if self.outcome is GetOrderOutcome.FOUND:
            if self.order_summary is None:
                raise ValueError("FOUND result requires order_summary")
            if self.failure_code is not None:
                raise ValueError("FOUND result cannot carry failure_code")
        else:
            if self.order_summary is not None:
                raise ValueError("non-FOUND result cannot carry order_summary")
            if self.source_version is not None:
                raise ValueError("non-FOUND result cannot carry source_version")
            if (
                self.outcome is GetOrderOutcome.NOT_FOUND_OR_NOT_ACCESSIBLE
                and self.failure_code is not None
            ):
                raise ValueError(
                    "safe not-found result cannot disclose a differentiated failure code"
                )
        return self
