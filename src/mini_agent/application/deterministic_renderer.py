"""Deterministic safe rendering and bounded outward result mapping."""

from __future__ import annotations

from uuid import UUID

from mini_agent.application.records import AgentRunResult
from mini_agent.core.memory import OrderObservation
from mini_agent.core.order import OrderStatus
from mini_agent.core.presentation import (
    ClosingVariant,
    OpeningVariant,
    PresentationField,
    PresentationPlan,
)
from mini_agent.core.presentation_policy import validate_presentation_plan
from mini_agent.core.trace import AgentOutcome, StopReason

_SAFE_GENERIC_MESSAGE = "当前无法安全处理该请求，请稍后重试。"
_SAFE_NOT_FOUND_MESSAGE = "未找到可访问的订单，请核对订单号后重试。"
_SAFE_ORDER_UNAVAILABLE_MESSAGE = "订单服务暂时不可用，请稍后重试。"

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
