"""Model-safe presentation planning contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, field_validator

from .common import ModelVisibleModel
from .memory import SearchOrdersObservationSafeProjection
from .order import OrderSummaryProjection
from .shipment import ShipmentSummaryProjection

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

    schema_version: Literal["presentation-plan-v1"] = PRESENTATION_PLAN_SCHEMA_VERSION
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


CANDIDATE_PRESENTATION_PLAN_SCHEMA_VERSION = "candidate-presentation-plan-v1"
SHIPMENT_PRESENTATION_PLAN_SCHEMA_VERSION = "shipment-presentation-plan-v1"


class CandidatePresentationInput(ModelVisibleModel):
    """Exact safe search projection; no private Observation metadata."""

    purpose: Literal["CANDIDATE_SUMMARY"] = "CANDIDATE_SUMMARY"
    candidates: SearchOrdersObservationSafeProjection
    allowed_plan_schema_version: Literal[
        "candidate-presentation-plan-v1"
    ] = CANDIDATE_PRESENTATION_PLAN_SCHEMA_VERSION


class CandidatePresentationPlan(ModelVisibleModel):
    """Fact-free style controls for deterministic candidate rendering."""

    schema_version: Literal["candidate-presentation-plan-v1"] = (
        CANDIDATE_PRESENTATION_PLAN_SCHEMA_VERSION
    )
    template_id: Literal["CANDIDATE_SUMMARY_V1"] = "CANDIDATE_SUMMARY_V1"
    tone: PresentationTone
    opening_variant: OpeningVariant
    closing_variant: ClosingVariant


class ShipmentPresentationInput(ModelVisibleModel):
    """Only the approved Shipment fact projection crosses the model boundary."""

    purpose: Literal["SHIPMENT_ASSESSMENT"] = "SHIPMENT_ASSESSMENT"
    shipment_summary: ShipmentSummaryProjection
    allowed_plan_schema_version: Literal[
        "shipment-presentation-plan-v1"
    ] = SHIPMENT_PRESENTATION_PLAN_SCHEMA_VERSION


class ShipmentPresentationPlan(ModelVisibleModel):
    """Fact-free style controls for deterministic Shipment rendering."""

    schema_version: Literal["shipment-presentation-plan-v1"] = (
        SHIPMENT_PRESENTATION_PLAN_SCHEMA_VERSION
    )
    template_id: Literal["SHIPMENT_ASSESSMENT_V1"] = (
        "SHIPMENT_ASSESSMENT_V1"
    )
    tone: PresentationTone
    opening_variant: OpeningVariant
    closing_variant: ClosingVariant
