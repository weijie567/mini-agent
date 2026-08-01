from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from mini_agent.application.deterministic_renderer import (
    DeterministicRenderer,
    RendererInvariantError,
)
from mini_agent.application.run_result_mapper import (
    Cycle2MapperSignal,
    RunResultMapper,
)
from mini_agent.core.memory import (
    ObservationVisibility,
    OrderObservation,
    SearchOrdersObservationSafeCandidate,
    SearchOrdersObservationSafeProjection,
    ShipmentObservation,
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
    ShipmentPresentationPlan,
)
from mini_agent.core.shipment import (
    ShipmentAssessment,
    ShipmentAssessmentReason,
    ShipmentAssessmentResult,
    ShipmentEventCode,
    ShipmentStatus,
    ShipmentSummaryProjection,
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
                            product_name="轻量跑鞋", quantity=2
                        ),
                    ),
                ),
            ),
        ),
        truncated=False,
    )


def test_candidate_renderer_uses_exact_safe_whitelist_only() -> None:
    message = DeterministicRenderer().render_candidate_summary(
        projection=_candidate_projection(),
        plan=CandidatePresentationPlan(
            tone=PresentationTone.NEUTRAL,
            opening_variant=OpeningVariant.DIRECT,
            closing_variant=ClosingVariant.OFFER_FOLLOW_UP,
        ),
    )

    assert "1. O-1001｜2030-01-01｜已发货｜轻量跑鞋 × 2" in message
    assert "order-search-matching" not in message
    assert "source_version" not in message
    assert "customer" not in message


def _shipment_pair() -> tuple[ShipmentObservation, ShipmentAssessment]:
    observation_id = uuid4()
    summary = ShipmentSummaryProjection(
        shipment_status=ShipmentStatus.IN_TRANSIT,
        latest_event_code=ShipmentEventCode.IN_TRANSIT,
        latest_event_at=NOW - timedelta(hours=121),
        promised_delivery_at=NOW - timedelta(hours=1),
    )
    observation = ShipmentObservation(
        observation_id=observation_id,
        private_owner_scope="customer-A",
        task_id=uuid4(),
        request_unit_id=uuid4(),
        verified_order_target_ref="selected-target-ref",
        source_tool="get_shipment",
        source_tool_call_id=uuid4(),
        source_resource_ref="private-package-ref",
        source_version=(
            "mock-shipment-source-version.p0.v1:sha256:" + "a" * 64
        ),
        normalized_type="SHIPMENT_SUMMARY",
        normalized_value=summary,
        observed_at=NOW,
        recorded_at=NOW,
        valid_until=NOW + timedelta(minutes=5),
        visibility=ObservationVisibility.AUDIT_ONLY,
    )
    assessment = ShipmentAssessment(
        assessment_id=uuid4(),
        private_owner_scope_ref="customer-A",
        task_id=observation.task_id,
        request_unit_id=observation.request_unit_id,
        task_state_version=2,
        verified_order_target_ref="selected-target-ref",
        shipment_observation_ref=observation_id,
        shipment_observation_source_version=observation.source_version,
        primary_result=ShipmentAssessmentResult.STALLED,
        reason_codes=(
            ShipmentAssessmentReason.NO_TRACKING_UPDATE_FOR_120_HOURS,
            ShipmentAssessmentReason.PROMISED_DELIVERY_TIME_PASSED,
        ),
        assessed_at=NOW + timedelta(minutes=1),
    )
    return observation, assessment


def test_shipment_renderer_uses_safe_facts_and_deterministic_primary_only() -> None:
    observation, assessment = _shipment_pair()
    message = DeterministicRenderer().render_shipment_assessment(
        observation=observation,
        assessment=assessment,
        plan=ShipmentPresentationPlan(
            tone=PresentationTone.WARM,
            opening_variant=OpeningVariant.ACKNOWLEDGE,
            closing_variant=ClosingVariant.NONE,
        ),
    )

    assert "配送状态：运输中" in message
    assert "物流较长时间没有更新" in message
    assert "customer-A" not in message
    assert "private-package-ref" not in message
    assert "NO_TRACKING_UPDATE" not in message
    assert observation.source_version not in message


def test_shipment_renderer_rejects_assessment_not_bound_to_safe_observation() -> None:
    observation, assessment = _shipment_pair()
    mismatched = assessment.model_copy(
        update={"verified_order_target_ref": "different-private-target"}
    )

    with pytest.raises(ValueError, match="derivation"):
        DeterministicRenderer().render_shipment_assessment(
            observation=observation,
            assessment=mismatched,
            plan=ShipmentPresentationPlan(
                tone=PresentationTone.NEUTRAL,
                opening_variant=OpeningVariant.DIRECT,
                closing_variant=ClosingVariant.NONE,
            ),
        )


def test_cycle2_non_outbound_rows_never_create_agent_result() -> None:
    renderer = DeterministicRenderer()
    mapper = RunResultMapper()
    for signal in (
        Cycle2MapperSignal.INTERNAL_RETRY_AUTHORIZED,
        Cycle2MapperSignal.ORDINARY_OBSOLETE_RUN,
        Cycle2MapperSignal.RETRY_RECOVERY_OBSOLETE_RUN,
        Cycle2MapperSignal.CONTRADICTORY_INTERRUPTION_EVIDENCE,
    ):
        assert renderer.map_cycle2_result(
            run_id=uuid4(), mapping=mapper.map_cycle2(signal)
        ) is None
