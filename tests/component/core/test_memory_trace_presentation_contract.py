from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from mini_agent.core.memory import (
    ContextManifest,
    ObservationVisibility,
    OrderObservation,
    TokenCounts,
)
from mini_agent.core.order import (
    GetOrderOutcome,
    GetOrderResult,
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
from mini_agent.core.tool_system import ToolCallStatus, ToolResultOutcome
from mini_agent.core.trace import (
    AgentOutcome,
    AgentRunRecord,
    AgentRunStatus,
    StopReason,
    TraceEvent,
    TraceEventType,
)

NOW = datetime(2030, 1, 1, tzinfo=UTC)
VALID_SOURCE_VERSION = (
    "mock-order-source-version.p0.v1:sha256:"
    "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
)


def _summary() -> OrderSummaryProjection:
    return OrderSummaryProjection(
        order_number="O-4242",
        status=OrderStatus.SHIPPED,
        line_items=(OrderLineSummary(product_name="示例商品", quantity=2),),
        ordered_at=NOW,
        status_updated_at=NOW + timedelta(hours=1),
    )


def _context_manifest_payload() -> dict[str, object]:
    return {
        "context_manifest_id": uuid4(),
        "run_id": uuid4(),
        "model_call_id": uuid4(),
        "tool_registry_version": "runtime-tools-v1",
        "model_visible_toolset_hash": f"sha256:{'a' * 64}",
        "selected_message_refs": (uuid4(),),
        "redaction_policy_version": "redaction-v1",
        "assembled_at": NOW,
    }


def test_order_projection_forbids_private_and_unapproved_fields() -> None:
    summary = _summary()
    assert set(summary.model_dump()) == {
        "order_number",
        "status",
        "line_items",
        "ordered_at",
        "status_updated_at",
    }

    with pytest.raises(ValidationError, match="extra"):
        OrderSummaryProjection.model_validate(
            {
                **summary.model_dump(),
                "customer_id": "private-owner",
            }
        )

    with pytest.raises(ValidationError, match="extra"):
        OrderSummaryProjection.model_validate(
            {
                **summary.model_dump(),
                "shipping_address": "must-not-disclose",
            }
        )


def test_not_found_result_cannot_disclose_payload_or_failure_difference() -> None:
    safe_result = GetOrderResult(outcome=GetOrderOutcome.NOT_FOUND_OR_NOT_ACCESSIBLE)
    assert safe_result.order_summary is None
    assert safe_result.source_version is None
    assert safe_result.failure_code is None

    with pytest.raises(ValidationError, match="cannot carry order_summary"):
        GetOrderResult(
            outcome=GetOrderOutcome.NOT_FOUND_OR_NOT_ACCESSIBLE,
            order_summary=_summary(),
        )

    with pytest.raises(ValidationError, match="differentiated failure code"):
        GetOrderResult(
            outcome=GetOrderOutcome.NOT_FOUND_OR_NOT_ACCESSIBLE,
            failure_code="NOT_OWNED",
        )


def test_found_result_requires_strict_source_version_exactly() -> None:
    with pytest.raises(
        ValidationError,
        match="FOUND result requires source_version",
    ):
        GetOrderResult(
            outcome=GetOrderOutcome.FOUND,
            order_summary=_summary(),
        )

    with pytest.raises(
        ValidationError,
        match="FOUND result requires order_summary",
    ):
        GetOrderResult(outcome=GetOrderOutcome.FOUND)

    with pytest.raises(
        ValidationError,
        match="FOUND result cannot carry failure_code",
    ):
        GetOrderResult(
            outcome=GetOrderOutcome.FOUND,
            order_summary=_summary(),
            failure_code="UNEXPECTED",
        )

    versioned_result = GetOrderResult(
        outcome=GetOrderOutcome.FOUND,
        order_summary=_summary(),
        source_version=VALID_SOURCE_VERSION,
    )

    assert versioned_result.source_version == VALID_SOURCE_VERSION


@pytest.mark.parametrize(
    "invalid_source_version",
    [
        "",
        "order-source-version.p0.v1:sha256:" + "b" * 64,
        "mock-order-source-version.p0.v2:sha256:" + "b" * 64,
        "mock-order-source-version.p0.v1:sha256:" + "b" * 63,
        "mock-order-source-version.p0.v1:sha256:" + "b" * 65,
        "mock-order-source-version.p0.v1:sha256:" + "B" * 64,
        " " + VALID_SOURCE_VERSION,
        VALID_SOURCE_VERSION + " ",
        VALID_SOURCE_VERSION + "\n",
        VALID_SOURCE_VERSION.encode(),
    ],
)
def test_found_result_rejects_malformed_or_coercible_source_version(
    invalid_source_version: object,
) -> None:
    with pytest.raises(ValidationError):
        GetOrderResult(
            outcome=GetOrderOutcome.FOUND,
            order_summary=_summary(),
            source_version=invalid_source_version,
        )


@pytest.mark.parametrize(
    ("outcome", "failure_code"),
    [
        (GetOrderOutcome.NOT_FOUND_OR_NOT_ACCESSIBLE, None),
        (GetOrderOutcome.SYSTEM_FAILURE, "ORDER_STORE_UNAVAILABLE"),
    ],
)
def test_non_found_result_cannot_carry_source_version(
    outcome: GetOrderOutcome,
    failure_code: str | None,
) -> None:
    with pytest.raises(
        ValidationError,
        match="non-FOUND result cannot carry source_version",
    ):
        GetOrderResult(
            outcome=outcome,
            source_version=VALID_SOURCE_VERSION,
            failure_code=failure_code,
        )


def test_observation_requires_the_minimum_safe_projection() -> None:
    observation = OrderObservation(
        observation_id=uuid4(),
        source_tool="get_order",
        source_resource_ref="verified-order-safe-ref",
        normalized_type="ORDER_SUMMARY",
        normalized_value=_summary(),
        observed_at=NOW,
        recorded_at=NOW,
        visibility=ObservationVisibility.MODEL_VISIBLE,
    )
    assert observation.normalized_value.order_number == "O-4242"

    with pytest.raises(ValidationError, match="extra"):
        OrderObservation.model_validate(
            {
                **observation.model_dump(),
                "customer_id": "private-owner",
            }
        )


def test_context_manifest_contains_only_refs_and_toolset_identity() -> None:
    manifest = ContextManifest(
        context_manifest_id=uuid4(),
        run_id=uuid4(),
        model_call_id=uuid4(),
        tool_registry_version="runtime-tools-v1",
        model_visible_toolset_hash=f"sha256:{'a' * 64}",
        selected_message_refs=(uuid4(),),
        redaction_policy_version="redaction-v1",
        token_counts=TokenCounts(input_tokens=100),
        assembled_at=NOW,
    )
    schema_text = str(ContextManifest.model_json_schema())

    assert manifest.task_state_ref_and_version is None
    assert "customer_id" not in schema_text
    assert "raw_result" not in schema_text
    assert "prompt" not in ContextManifest.model_fields

    with pytest.raises(ValidationError, match="extra"):
        ContextManifest.model_validate(
            {
                **manifest.model_dump(),
                "auth_scopes": ["orders:read"],
            }
        )


def test_context_manifest_requires_a_token_counts_object() -> None:
    with pytest.raises(ValidationError, match="token_counts"):
        ContextManifest.model_validate(_context_manifest_payload())

    with pytest.raises(ValidationError, match="token_counts"):
        ContextManifest.model_validate(
            {
                **_context_manifest_payload(),
                "token_counts": None,
            }
        )


def test_token_counts_default_to_unknown_for_both_directions() -> None:
    counts = TokenCounts()
    manifest = ContextManifest.model_validate(
        {
            **_context_manifest_payload(),
            "token_counts": counts,
        }
    )

    assert counts.model_dump() == {
        "input_tokens": None,
        "output_tokens": None,
    }
    assert manifest.token_counts == counts


@pytest.mark.parametrize(
    ("input_tokens", "output_tokens"),
    [
        (0, 0),
        (123, 45),
    ],
)
def test_token_counts_preserve_exact_non_negative_values(
    input_tokens: int,
    output_tokens: int,
) -> None:
    counts = TokenCounts(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )

    assert counts.input_tokens == input_tokens
    assert counts.output_tokens == output_tokens
    assert type(counts.input_tokens) is int
    assert type(counts.output_tokens) is int


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("input_tokens", -1),
        ("input_tokens", 1.0),
        ("input_tokens", "1"),
        ("input_tokens", True),
        ("output_tokens", -1),
        ("output_tokens", 1.0),
        ("output_tokens", "1"),
        ("output_tokens", True),
    ],
)
def test_token_counts_reject_invalid_or_coercible_values(
    field_name: str,
    invalid_value: object,
) -> None:
    payload: dict[str, object] = {
        "input_tokens": 0,
        "output_tokens": 0,
    }
    payload[field_name] = invalid_value

    with pytest.raises(ValidationError):
        TokenCounts.model_validate(payload)


def test_token_counts_forbid_extra_fields() -> None:
    with pytest.raises(ValidationError, match="extra"):
        TokenCounts.model_validate(
            {
                "input_tokens": 0,
                "output_tokens": 0,
                "estimated": False,
            }
        )


def test_run_and_trace_require_an_explicit_safe_stop_reason() -> None:
    run_id = uuid4()
    with pytest.raises(ValidationError, match="stop_reason"):
        AgentRunRecord(
            run_id=run_id,
            status=AgentRunStatus.COMPLETED,
            provider_lane="offline",
            started_at=NOW,
            completed_at=NOW,
        )

    run = AgentRunRecord(
        run_id=run_id,
        status=AgentRunStatus.COMPLETED,
        provider_lane="offline",
        started_at=NOW,
        completed_at=NOW,
        stop_reason=StopReason.NOT_FOUND_OR_NOT_ACCESSIBLE,
    )
    trace = TraceEvent(
        trace_event_id=uuid4(),
        event_type=TraceEventType.RUN_STOPPED,
        occurred_at=NOW,
        run_id=run_id,
        safe_tool_outcome=ToolResultOutcome.BUSINESS_FAILURE,
        user_outcome=AgentOutcome.NOT_FOUND_OR_NOT_ACCESSIBLE,
        stop_reason=run.stop_reason,
    )

    assert trace.stop_reason is StopReason.NOT_FOUND_OR_NOT_ACCESSIBLE
    trace_schema = str(TraceEvent.model_json_schema())
    assert "customer_id" not in trace_schema
    assert "raw_tool_result" not in trace_schema


@pytest.mark.parametrize(
    ("event_type", "terminal_status"),
    [
        (TraceEventType.TOOL_CALL_CREATED, ToolCallStatus.CREATED),
        (TraceEventType.TOOL_CALL_STARTED, ToolCallStatus.RUNNING),
        (TraceEventType.TOOL_CALL_SUCCEEDED, ToolCallStatus.SUCCEEDED),
        (TraceEventType.TOOL_CALL_FAILED, ToolCallStatus.FAILED),
        (TraceEventType.TOOL_CALL_TIMED_OUT, ToolCallStatus.TIMED_OUT),
        (TraceEventType.TOOL_CALL_INTERRUPTED, ToolCallStatus.INTERRUPTED),
    ],
)
def test_tool_lifecycle_trace_requires_id_and_matching_status(
    event_type: TraceEventType,
    terminal_status: ToolCallStatus,
) -> None:
    trace = TraceEvent(
        trace_event_id=uuid4(),
        event_type=event_type,
        occurred_at=NOW,
        run_id=uuid4(),
        tool_call_id=uuid4(),
        tool_call_terminal_status=terminal_status,
    )
    assert trace.tool_call_terminal_status is terminal_status

    with pytest.raises(ValidationError, match="requires tool_call_id"):
        TraceEvent(
            trace_event_id=uuid4(),
            event_type=event_type,
            occurred_at=NOW,
            run_id=uuid4(),
            tool_call_terminal_status=terminal_status,
        )

    mismatched_status = (
        ToolCallStatus.SUCCEEDED
        if terminal_status is not ToolCallStatus.SUCCEEDED
        else ToolCallStatus.FAILED
    )
    with pytest.raises(ValidationError, match="event and status must match"):
        TraceEvent(
            trace_event_id=uuid4(),
            event_type=event_type,
            occurred_at=NOW,
            run_id=uuid4(),
            tool_call_id=uuid4(),
            tool_call_terminal_status=mismatched_status,
        )


def test_tool_status_cannot_be_attached_to_non_lifecycle_trace_event() -> None:
    with pytest.raises(ValidationError, match="matching lifecycle Trace event"):
        TraceEvent(
            trace_event_id=uuid4(),
            event_type=TraceEventType.MESSAGE_ACCEPTED,
            occurred_at=NOW,
            run_id=uuid4(),
            tool_call_id=uuid4(),
            tool_call_terminal_status=ToolCallStatus.SUCCEEDED,
        )


def test_presentation_plan_is_style_only_and_uses_each_field_once() -> None:
    valid_order = tuple(PresentationField)
    plan = PresentationPlan(
        template_id="ORDER_STATUS_SUMMARY_V1",
        tone=PresentationTone.NEUTRAL,
        opening_variant=OpeningVariant.DIRECT,
        field_order=valid_order,
        closing_variant=ClosingVariant.NONE,
    )

    schema_fields = set(PresentationPlan.model_fields)
    assert schema_fields == {
        "schema_version",
        "template_id",
        "tone",
        "opening_variant",
        "field_order",
        "closing_variant",
    }
    assert "order_number" not in plan.model_dump()
    assert "message" not in plan.model_dump()

    with pytest.raises(ValidationError, match="approved presentation field"):
        PresentationPlan(
            template_id="ORDER_STATUS_SUMMARY_V1",
            tone=PresentationTone.WARM,
            opening_variant=OpeningVariant.ACKNOWLEDGE,
            field_order=(
                PresentationField.ORDER_NUMBER,
                PresentationField.STATUS,
                PresentationField.ITEMS,
                PresentationField.ORDERED_AT,
                PresentationField.ORDERED_AT,
            ),
            closing_variant=ClosingVariant.OFFER_FOLLOW_UP,
        )

    with pytest.raises(ValidationError, match="extra"):
        PresentationPlan.model_validate(
            {
                **plan.model_dump(),
                "free_text": "模型生成的事实或承诺",
            }
        )
