"""Pure policy gate for fact-free presentation plans."""

from __future__ import annotations

from pydantic import BaseModel

from .memory import (
    ObservationVisibility,
    OrderObservation,
)
from .order import OrderLineSummary, OrderSummaryProjection
from .presentation import PresentationPlan


class PresentationPolicyError(ValueError):
    """Bounded policy rejection without model- or business-supplied detail."""

    __slots__ = ()


def _is_exact_contract_model(value: object, expected_type: type[BaseModel]) -> bool:
    if type(value) is not expected_type:
        return False
    model = value
    return (
        set(vars(model)) == set(expected_type.model_fields)
        and model.__pydantic_extra__ is None
        and model.__pydantic_private__ is None
    )


def validate_presentation_plan(
    *,
    plan: PresentationPlan,
    observation: OrderObservation,
) -> PresentationPlan:
    """Accept only the canonical style plan and safe get_order provenance."""

    if not _is_exact_contract_model(plan, PresentationPlan):
        if type(plan) is not PresentationPlan:
            raise PresentationPolicyError("canonical PresentationPlan required")
        raise PresentationPolicyError("PresentationPlan must remain fact-free")

    safe_observation = (
        _is_exact_contract_model(observation, OrderObservation)
        and observation.source_tool == "get_order"
        and observation.normalized_type == "ORDER_SUMMARY"
        and observation.visibility is ObservationVisibility.MODEL_VISIBLE
        and _is_exact_contract_model(
            observation.normalized_value,
            OrderSummaryProjection,
        )
        and all(
            _is_exact_contract_model(line_item, OrderLineSummary)
            for line_item in observation.normalized_value.line_items
        )
    )
    if not safe_observation:
        raise PresentationPolicyError("safe Observation provenance required")
    return plan
