from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from mini_agent.application.deterministic_renderer import (
    DeterministicRenderer,
    RendererInvariantError,
)
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
from mini_agent.core.trace import AgentOutcome, StopReason

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
                OrderLineSummary(product_name="轻量跑鞋", quantity=2),
                OrderLineSummary(product_name="运动袜", quantity=1),
            ),
            ordered_at=NOW,
            status_updated_at=NOW + timedelta(hours=2),
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
        field_order=(
            PresentationField.STATUS,
            PresentationField.ORDER_NUMBER,
            PresentationField.ITEMS,
            PresentationField.ORDERED_AT,
            PresentationField.STATUS_UPDATED_AT,
        ),
        closing_variant=ClosingVariant.OFFER_FOLLOW_UP,
    )


def test_renderer_injects_only_safe_observation_facts_in_plan_order() -> None:
    message = DeterministicRenderer().render_order_summary(
        observation=_observation(),
        plan=_plan(),
    )

    assert message.index("状态：已发货") < message.index("订单号：O-1001")
    assert "商品：轻量跑鞋 × 2、运动袜 × 1" in message
    assert "下单时间：2030-01-01 00:00 UTC" in message
    assert "状态更新时间：2030-01-01 02:00 UTC" in message
    assert "customer-A" not in message
    assert "verified-order-safe-ref" not in message
    assert "order-v1" not in message


def test_order_number_is_read_only_from_found_observation_projection() -> None:
    observation = _observation()
    message = DeterministicRenderer().render_order_summary(
        observation=observation,
        plan=_plan(),
    )

    assert observation.normalized_value.order_number == "O-1001"
    assert "order_number" not in _plan().model_dump()
    assert "O-1001" in message


def test_corrupted_safe_projection_causes_renderer_invariant_failure() -> None:
    corrupted_summary = _observation().normalized_value.model_copy(
        update={"status": "UNRECOGNIZED_PRIVATE_STATUS"}
    )
    corrupted = _observation().model_copy(
        update={"normalized_value": corrupted_summary}
    )

    with pytest.raises(RendererInvariantError, match="status"):
        DeterministicRenderer().render_order_summary(
            observation=corrupted,
            plan=_plan(),
        )


def test_not_found_mapping_is_identical_and_discards_lower_level_details() -> None:
    renderer = DeterministicRenderer()
    first = renderer.map_result(
        run_id=uuid4(),
        stop_reason=StopReason.NOT_FOUND_OR_NOT_ACCESSIBLE,
    )
    second = renderer.map_result(
        run_id=uuid4(),
        stop_reason=StopReason.NOT_FOUND_OR_NOT_ACCESSIBLE,
    )

    assert first.outcome is AgentOutcome.NOT_FOUND_OR_NOT_ACCESSIBLE
    assert second.outcome is first.outcome
    assert second.message == first.message
    assert first.message == "未找到可访问的订单，请核对订单号后重试。"
    assert "foreign" not in first.message
    assert "nonexistent" not in first.message


@pytest.mark.parametrize(
    ("stop_reason", "expected_message"),
    [
        (
            StopReason.ORDER_SERVICE_UNAVAILABLE,
            "订单服务暂时不可用，请稍后重试。",
        ),
        (
            StopReason.GATE_REJECTED,
            "当前无法安全处理该请求，请稍后重试。",
        ),
        (
            StopReason.PROVIDER_PROTOCOL_ERROR,
            "当前无法安全处理该请求，请稍后重试。",
        ),
        (
            StopReason.PRESENTATION_PLAN_REJECTED,
            "当前无法安全处理该请求，请稍后重试。",
        ),
        (
            StopReason.RENDERER_INVARIANT_FAILED,
            "当前无法安全处理该请求，请稍后重试。",
        ),
    ],
)
def test_bounded_stop_mapping_never_contains_raw_errors_or_private_ids(
    stop_reason: StopReason,
    expected_message: str,
) -> None:
    result = DeterministicRenderer().map_result(
        run_id=uuid4(),
        stop_reason=stop_reason,
    )

    assert result.outcome is AgentOutcome.BLOCKED
    assert result.message == expected_message
    assert "customer_id" not in result.message
    assert "traceback" not in result.message.casefold()


def test_goal_completed_requires_a_nonempty_deterministic_message() -> None:
    renderer = DeterministicRenderer()

    with pytest.raises(RendererInvariantError, match="rendered message"):
        renderer.map_result(
            run_id=uuid4(),
            stop_reason=StopReason.GOAL_COMPLETED,
        )

    result = renderer.map_result(
        run_id=uuid4(),
        stop_reason=StopReason.GOAL_COMPLETED,
        rendered_message="订单号：O-1001",
    )
    assert result.outcome is AgentOutcome.COMPLETED
    assert result.message == "订单号：O-1001"
