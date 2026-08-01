from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from mini_agent.core.memory import (
    ObservationVisibility,
    OrderObservation,
    SearchOrdersObservationSafeCandidate,
    SearchOrdersObservationSafeProjection,
)
from mini_agent.core.order import (
    OrderLineSummary,
    OrderStatus,
    OrderSummaryProjection,
)
from mini_agent.core.order_search import (
    OrderCandidateMatchingItem,
    OrderCandidatePublicSummary,
)
from mini_agent.core.presentation import (
    CandidatePresentationPlan,
    ClosingVariant,
    OpeningVariant,
    PresentationField,
    PresentationPlan,
    PresentationTone,
)
from mini_agent.core.presentation_policy import (
    PresentationPolicyError,
    validate_presentation_plan,
    validate_candidate_presentation_plan,
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
    ("field_name", "invalid_value"),
    [
        ("tone", "MODEL_CHOSEN_UNSAFE_TONE"),
        ("opening_variant", "FREE_TEXT_OPENING"),
        ("closing_variant", "UNBOUNDED_PROMISE"),
        (
            "field_order",
            (
                PresentationField.ORDER_NUMBER,
                PresentationField.STATUS,
                PresentationField.ITEMS,
                PresentationField.ORDERED_AT,
                PresentationField.ORDERED_AT,
            ),
        ),
    ],
)
def test_bypassed_existing_plan_fields_are_strictly_revalidated(
    field_name: str,
    invalid_value: object,
) -> None:
    bypassed = _plan().model_copy(update={field_name: invalid_value})

    with pytest.raises(PresentationPolicyError, match="canonical"):
        validate_presentation_plan(
            plan=bypassed,
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


def _candidate_projection() -> SearchOrdersObservationSafeProjection:
    return SearchOrdersObservationSafeProjection(
        matching_rule_version="order-search-matching.p0.v1",
        ordered_candidates=(
            SearchOrdersObservationSafeCandidate(
                ordinal=1,
                public_summary=OrderCandidatePublicSummary(
                    order_number="O-1001",
                    ordered_on_utc=NOW.date(),
                    status=OrderStatus.SHIPPED,
                    matching_items=(
                        OrderCandidateMatchingItem(
                            product_name="轻量跑鞋", quantity=1
                        ),
                    ),
                ),
            ),
        ),
        truncated=False,
    )


def test_candidate_policy_accepts_only_fact_free_plan_and_exact_projection() -> None:
    plan = CandidatePresentationPlan(
        tone=PresentationTone.NEUTRAL,
        opening_variant=OpeningVariant.DIRECT,
        closing_variant=ClosingVariant.NONE,
    )
    assert validate_candidate_presentation_plan(
        plan=plan, projection=_candidate_projection()
    ) == plan

    contaminated = plan.model_copy(update={"customer_id": "customer-B"})
    with pytest.raises(PresentationPolicyError, match="fact-free"):
        validate_candidate_presentation_plan(
            plan=contaminated, projection=_candidate_projection()
        )


def test_candidate_policy_rejects_bypassed_private_projection_field() -> None:
    projection = _candidate_projection().model_copy(
        update={"source_version": "private-version"}
    )
    with pytest.raises(PresentationPolicyError, match="safe candidate"):
        validate_candidate_presentation_plan(
            plan=CandidatePresentationPlan(
                tone=PresentationTone.WARM,
                opening_variant=OpeningVariant.ACKNOWLEDGE,
                closing_variant=ClosingVariant.OFFER_FOLLOW_UP,
            ),
            projection=projection,
        )
