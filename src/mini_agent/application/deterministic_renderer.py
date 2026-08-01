"""Deterministic safe rendering and bounded outward result mapping."""

from __future__ import annotations

from uuid import UUID

from mini_agent.application.records import AgentRunResult
from mini_agent.application.run_result_mapper import (
    Cycle2ResultMapping,
    MapperDisposition,
    ResponsePolicy,
)
from mini_agent.core.memory import (
    OrderObservation,
    SearchOrdersObservationSafeProjection,
    ShipmentObservation,
)
from mini_agent.core.order import OrderStatus
from mini_agent.core.presentation import (
    ClosingVariant,
    OpeningVariant,
    PresentationField,
    PresentationPlan,
    CandidatePresentationPlan,
    ShipmentPresentationPlan,
)
from mini_agent.core.presentation_policy import (
    validate_candidate_presentation_plan,
    validate_presentation_plan,
    validate_shipment_presentation_plan,
)
from mini_agent.core.shipment import (
    ShipmentAssessment,
    ShipmentAssessmentResult,
    ShipmentEventCode,
    ShipmentStatus,
)
from mini_agent.core.trace import AgentOutcome, StopReason

_SAFE_GENERIC_MESSAGE = "当前无法安全处理该请求，请稍后重试。"
_SAFE_NOT_FOUND_MESSAGE = "未找到可访问的订单，请核对订单号后重试。"
_SAFE_ORDER_UNAVAILABLE_MESSAGE = "订单服务暂时不可用，请稍后重试。"
_CLARIFICATION_MESSAGE = "请补充要查询的商品描述。"
_CANDIDATE_REFRESH_MESSAGE = "候选订单已失效，请重新描述要查询的商品。"
_CLAIM_TARGET_MESSAGE = "请先确认要查询的订单，再说明是否未收到。"
_DEPENDENCY_BLOCKED_MESSAGE = "查询服务暂时不可用，请稍后重试。"
_INTEGRITY_BLOCKED_MESSAGE = "当前无法安全确认查询结果，请稍后重试。"
_NO_SHIPMENT_MESSAGE = "当前没有可确认的配送记录，建议联系人工客服核实。"
_INSUFFICIENT_SHIPMENT_MESSAGE = "当前配送信息不足，建议联系人工客服核实。"

_STATUS_LABELS: dict[OrderStatus, str] = {
    OrderStatus.CREATED: "已创建",
    OrderStatus.PAID: "已支付",
    OrderStatus.FULFILLING: "履约中",
    OrderStatus.SHIPPED: "已发货",
    OrderStatus.DELIVERED: "已送达",
    OrderStatus.CANCELLED: "已取消",
}


class RendererInvariantError(ValueError):
    """A bounded deterministic renderer invariant failure."""

    __slots__ = ()


class DeterministicRenderer:
    """Inject facts only from a validated safe Observation projection."""

    def render_order_summary(
        self,
        *,
        observation: OrderObservation,
        plan: PresentationPlan,
    ) -> str:
        validate_presentation_plan(plan=plan, observation=observation)
        summary = observation.normalized_value
        try:
            status_label = _STATUS_LABELS[summary.status]
        except KeyError:
            raise RendererInvariantError("unrecognized safe order status") from None

        field_values = {
            PresentationField.ORDER_NUMBER: f"订单号：{summary.order_number}",
            PresentationField.STATUS: f"状态：{status_label}",
            PresentationField.ITEMS: "商品："
            + "、".join(
                f"{item.product_name} × {item.quantity}"
                for item in summary.line_items
            ),
            PresentationField.ORDERED_AT: (
                f"下单时间：{summary.ordered_at.strftime('%Y-%m-%d %H:%M UTC')}"
            ),
            PresentationField.STATUS_UPDATED_AT: (
                "状态更新时间："
                f"{summary.status_updated_at.strftime('%Y-%m-%d %H:%M UTC')}"
            ),
        }
        if set(plan.field_order) != set(field_values):
            raise RendererInvariantError("presentation field set mismatch")

        opening = (
            "已为你查到订单信息："
            if plan.opening_variant is OpeningVariant.ACKNOWLEDGE
            else "订单信息如下："
        )
        parts = [opening, *(field_values[field] for field in plan.field_order)]
        if plan.closing_variant is ClosingVariant.OFFER_FOLLOW_UP:
            parts.append("如需继续查询配送信息，请告诉我。")
        message = "\n".join(parts)

        required_facts = (
            summary.order_number,
            status_label,
            *(item.product_name for item in summary.line_items),
        )
        if any(str(fact) not in message for fact in required_facts):
            raise RendererInvariantError("rendered fact consistency failure")
        return message

    def render_candidate_summary(
        self,
        *,
        projection: SearchOrdersObservationSafeProjection,
        plan: CandidatePresentationPlan,
    ) -> str:
        """Render only ordinal and approved candidate summary fields."""

        validate_candidate_presentation_plan(plan=plan, projection=projection)
        opening = (
            "找到了以下可能的订单，请回复序号："
            if plan.opening_variant is OpeningVariant.ACKNOWLEDGE
            else "请选择一个订单序号："
        )
        parts = [opening]
        for candidate in projection.ordered_candidates:
            summary = candidate.public_summary
            try:
                status_label = _STATUS_LABELS[summary.status]
            except KeyError:
                raise RendererInvariantError(
                    "unrecognized safe candidate status"
                ) from None
            items = "、".join(
                f"{item.product_name} × {item.quantity}"
                for item in summary.matching_items
            )
            parts.append(
                f"{candidate.ordinal}. {summary.order_number}｜"
                f"{summary.ordered_on_utc.isoformat()}｜{status_label}｜{items}"
            )
        if projection.truncated:
            parts.append(
                "仅显示最近 5 个匹配订单，可选择其中一个或补充商品描述。"
            )
        elif plan.closing_variant is ClosingVariant.OFFER_FOLLOW_UP:
            parts.append("请回复对应序号。")
        return "\n".join(parts)

    def render_shipment_assessment(
        self,
        *,
        observation: ShipmentObservation,
        assessment: ShipmentAssessment,
        plan: ShipmentPresentationPlan,
    ) -> str:
        """Render approved Shipment facts and deterministic primary result."""

        validate_shipment_presentation_plan(
            plan=plan,
            observation=observation,
            assessment=assessment,
        )
        summary = observation.normalized_value
        status_labels = {
            ShipmentStatus.LABEL_CREATED: "已创建运单",
            ShipmentStatus.IN_TRANSIT: "运输中",
            ShipmentStatus.OUT_FOR_DELIVERY: "派送中",
            ShipmentStatus.DELIVERED: "已签收",
        }
        event_labels = {
            ShipmentEventCode.LABEL_CREATED: "运单已创建",
            ShipmentEventCode.PICKED_UP: "承运商已揽收",
            ShipmentEventCode.IN_TRANSIT: "运输中",
            ShipmentEventCode.ARRIVED_AT_FACILITY: "已到达站点",
            ShipmentEventCode.OUT_FOR_DELIVERY: "正在派送",
            ShipmentEventCode.DELIVERED: "已签收",
        }
        assessment_messages = {
            ShipmentAssessmentResult.DELIVERED_NOT_RECEIVED: (
                "物流显示已签收，但你反馈未收到，建议联系人工客服核实。"
            ),
            ShipmentAssessmentResult.STALLED: (
                "物流较长时间没有更新，建议联系人工客服核实。"
            ),
            ShipmentAssessmentResult.DELAYED: "配送已超过承诺时间。",
            ShipmentAssessmentResult.NORMAL: "当前配送进度未见异常。",
        }
        try:
            parts = [
                (
                    "已为你核对配送信息："
                    if plan.opening_variant is OpeningVariant.ACKNOWLEDGE
                    else "配送信息如下："
                ),
                f"配送状态：{status_labels[summary.shipment_status]}",
                f"最新动态：{event_labels[summary.latest_event_code]}",
                "动态时间："
                f"{summary.latest_event_at.strftime('%Y-%m-%d %H:%M UTC')}",
                assessment_messages[assessment.primary_result],
            ]
        except KeyError:
            raise RendererInvariantError(
                "unrecognized safe Shipment projection"
            ) from None
        if summary.promised_delivery_at is not None:
            parts.insert(
                4,
                "承诺送达："
                f"{summary.promised_delivery_at.strftime('%Y-%m-%d %H:%M UTC')}",
            )
        if summary.delivered_at is not None:
            parts.insert(
                4,
                f"签收时间：{summary.delivered_at.strftime('%Y-%m-%d %H:%M UTC')}",
            )
        if plan.closing_variant is ClosingVariant.OFFER_FOLLOW_UP:
            parts.append("如需继续处理，请告诉我。")
        return "\n".join(parts)

    def map_cycle2_result(
        self,
        *,
        run_id: UUID,
        mapping: Cycle2ResultMapping,
        rendered_message: str | None = None,
    ) -> AgentRunResult | None:
        """Materialize only mapper rows that authorize an outbound result."""

        if type(mapping) is not Cycle2ResultMapping:
            raise RendererInvariantError("canonical Cycle 2 mapping required")
        if mapping.disposition is not MapperDisposition.EMIT:
            if rendered_message is not None:
                raise RendererInvariantError(
                    "non-outbound mapping cannot carry rendered content"
                )
            return None
        if mapping.outcome is None or mapping.stop_reason is None:
            raise RendererInvariantError("outbound mapping is incomplete")
        if mapping.response_policy in {
            ResponsePolicy.CANDIDATE_SUMMARY_DETERMINISTIC,
            ResponsePolicy.SHIPMENT_ASSESSMENT_DETERMINISTIC,
        }:
            if type(rendered_message) is not str or not rendered_message:
                raise RendererInvariantError(
                    "deterministic mapping requires rendered content"
                )
            message = rendered_message
        else:
            if rendered_message is not None:
                raise RendererInvariantError(
                    "fixed mapping cannot accept caller-rendered content"
                )
            fixed = {
                ResponsePolicy.CLARIFICATION_FIXED: _CLARIFICATION_MESSAGE,
                ResponsePolicy.CANDIDATE_REFRESH_FIXED: _CANDIDATE_REFRESH_MESSAGE,
                ResponsePolicy.CLAIM_TARGET_CLARIFICATION_FIXED: _CLAIM_TARGET_MESSAGE,
                ResponsePolicy.SAFE_NOT_FOUND_FIXED: _SAFE_NOT_FOUND_MESSAGE,
                ResponsePolicy.DEPENDENCY_BLOCKED_FIXED: _DEPENDENCY_BLOCKED_MESSAGE,
                ResponsePolicy.INTEGRITY_BLOCKED_FIXED: _INTEGRITY_BLOCKED_MESSAGE,
                ResponsePolicy.NO_SHIPMENT_NEED_HUMAN_FIXED: _NO_SHIPMENT_MESSAGE,
                ResponsePolicy.FACTS_INSUFFICIENT_NEED_HUMAN_FIXED: (
                    _INSUFFICIENT_SHIPMENT_MESSAGE
                ),
            }
            try:
                message = fixed[mapping.response_policy]
            except KeyError:
                raise RendererInvariantError(
                    "unsupported Cycle 2 response policy"
                ) from None
        return AgentRunResult(
            run_id=run_id,
            outcome=mapping.outcome,
            message=message,
        )

    def map_result(
        self,
        *,
        run_id: UUID,
        stop_reason: StopReason,
        rendered_message: str | None = None,
    ) -> AgentRunResult:
        if stop_reason is StopReason.GOAL_COMPLETED:
            if type(rendered_message) is not str or not rendered_message:
                raise RendererInvariantError(
                    "GOAL_COMPLETED requires rendered message"
                )
            return AgentRunResult(
                run_id=run_id,
                outcome=AgentOutcome.COMPLETED,
                message=rendered_message,
            )
        if stop_reason is StopReason.NOT_FOUND_OR_NOT_ACCESSIBLE:
            return AgentRunResult(
                run_id=run_id,
                outcome=AgentOutcome.NOT_FOUND_OR_NOT_ACCESSIBLE,
                message=_SAFE_NOT_FOUND_MESSAGE,
            )
        if stop_reason is StopReason.ORDER_SERVICE_UNAVAILABLE:
            return AgentRunResult(
                run_id=run_id,
                outcome=AgentOutcome.BLOCKED,
                message=_SAFE_ORDER_UNAVAILABLE_MESSAGE,
            )
        if type(stop_reason) is not StopReason:
            raise RendererInvariantError("unsupported stop reason")
        return AgentRunResult(
            run_id=run_id,
            outcome=AgentOutcome.BLOCKED,
            message=_SAFE_GENERIC_MESSAGE,
        )
