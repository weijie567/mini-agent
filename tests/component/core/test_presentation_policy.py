from datetime import UTC, datetime
from uuid import uuid4

import pytest

from mini_agent.core.memory import (
    ObservationVisibility,
    OrderObservation,
)
from mini_agent.core.order import (
    OrderLineSummary,
    OrderStatus,
    OrderSummaryProjection,
)
from mini_agent.core.presentation import (
    ClosingVariant,
    OpeningVariant,
    PresentationField,
    PresentationPlan,
    PresentationTone,
)
from mini_agent.core.presentation_policy import (
    PresentationPolicyError,
    validate_presentation_plan,
)

NOW = datetime(2030, 1, 1, tzinfo=UTC)


def _observation() -> OrderObservation:
    return OrderObservation(
        observation_id=uuid4(),
        source_tool="get_order",
        source_resource_ref="verified-order-safe-ref",
        source_version="order-v1",
        normalized_type="ORDER_SUMMARY",
        normalized_value=OrderSummaryProjection(
            order_number="O-1001",
            status=OrderStatus.SHIPPED,
            line_items=(
                OrderLineSummary(product_name="轻量跑鞋", quantity=1),
            ),
            ordered_at=NOW,
            status_updated_at=NOW,
        ),
        observed_at=NOW,
        recorded_at=NOW,
        visibility=ObservationVisibility.MODEL_VISIBLE,
    )


def _plan() -> PresentationPlan:
    return PresentationPlan(
        template_id="ORDER_STATUS_SUMMARY_V1",
        tone=PresentationTone.WARM,
        opening_variant=OpeningVariant.ACKNOWLEDGE,
        field_order=tuple(PresentationField),
        closing_variant=ClosingVariant.OFFER_FOLLOW_UP,
    )


def test_fact_free_canonical_plan_with_safe_observation_is_accepted() -> None:
    plan = _plan()

    accepted = validate_presentation_plan(
        plan=plan,
        observation=_observation(),
    )

    assert accepted == plan
    assert set(type(accepted).model_fields) == {
        "schema_version",
        "template_id",
        "tone",
        "opening_variant",
        "field_order",
        "closing_variant",
    }
    assert "order_number" not in accepted.model_dump()
    assert "free_text" not in accepted.model_dump()


@pytest.mark.parametrize(
    "extra_field",
    [
        "free_text",
        "order_number",
        "status",
        "customer_id",
    ],
)
def test_fact_or_free_text_contamination_is_rejected(extra_field: str) -> None:
    bypassed = _plan().model_copy(
        update={extra_field: "model-supplied-value"}
    )

    with pytest.raises(PresentationPolicyError, match="fact-free"):
        validate_presentation_plan(
            plan=bypassed,
            observation=_observation(),
        )


def test_plain_dict_cannot_bypass_the_canonical_plan_contract() -> None:
    with pytest.raises(PresentationPolicyError, match="canonical"):
        validate_presentation_plan(
            plan=_plan().model_dump(),  # type: ignore[arg-type]
            observation=_observation(),
        )


@pytest.mark.parametrize(
    "observation",
    [
        _observation().model_copy(update={"source_tool": "search_orders"}),
        _observation().model_copy(update={"normalized_type": "RAW_ORDER"}),
        _observation().model_copy(
            update={"visibility": ObservationVisibility.AUDIT_ONLY}
        ),
        _observation().model_copy(update={"customer_id": "customer-A"}),
    ],
)
def test_only_exact_safe_get_order_observation_provenance_is_accepted(
    observation: OrderObservation,
) -> None:
    with pytest.raises(PresentationPolicyError, match="safe Observation"):
        validate_presentation_plan(plan=_plan(), observation=observation)
