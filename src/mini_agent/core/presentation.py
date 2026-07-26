"""Model-safe presentation planning contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, field_validator

from .common import ModelVisibleModel
from .order import OrderSummaryProjection

PRESENTATION_PLAN_SCHEMA_VERSION = "presentation-plan-v1"


class PresentationPurpose(StrEnum):
    ORDER_STATUS_SUMMARY = "ORDER_STATUS_SUMMARY"


class PresentationInput(ModelVisibleModel):
    purpose: Literal[PresentationPurpose.ORDER_STATUS_SUMMARY]
    order_summary: OrderSummaryProjection
    allowed_plan_schema_version: Literal["presentation-plan-v1"] = (
        PRESENTATION_PLAN_SCHEMA_VERSION
    )


class PresentationTone(StrEnum):
    NEUTRAL = "NEUTRAL"
    WARM = "WARM"


class OpeningVariant(StrEnum):
    DIRECT = "DIRECT"
    ACKNOWLEDGE = "ACKNOWLEDGE"


class PresentationField(StrEnum):
    ORDER_NUMBER = "ORDER_NUMBER"
    STATUS = "STATUS"
    ITEMS = "ITEMS"
    ORDERED_AT = "ORDERED_AT"
    STATUS_UPDATED_AT = "STATUS_UPDATED_AT"


class ClosingVariant(StrEnum):
    NONE = "NONE"
    OFFER_FOLLOW_UP = "OFFER_FOLLOW_UP"


class PresentationPlan(ModelVisibleModel):
    """Style-only model output; all factual values stay in the safe projection."""

    schema_version: Literal["presentation-plan-v1"] = (
        PRESENTATION_PLAN_SCHEMA_VERSION
    )
    template_id: Literal["ORDER_STATUS_SUMMARY_V1"]
    tone: PresentationTone
    opening_variant: OpeningVariant
    field_order: Annotated[
        tuple[PresentationField, ...],
        Field(min_length=5, max_length=5),
    ]
    closing_variant: ClosingVariant

    @field_validator("field_order")
    @classmethod
    def field_order_contains_each_approved_field_once(
        cls, value: tuple[PresentationField, ...]
    ) -> tuple[PresentationField, ...]:
        if set(value) != set(PresentationField):
            raise ValueError(
                "field_order must contain every approved presentation field once"
            )
        return value
