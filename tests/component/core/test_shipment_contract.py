from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from mini_agent.core.common import ContractVisibility
from mini_agent.core.shipment import (
    SHIPMENT_ASSESSMENT_RULE_VERSION,
    SHIPMENT_FRESHNESS_TTL,
    SHIPMENT_STALLED_THRESHOLD,
    ActivePackageRelation,
    GetShipmentAgentOutput,
    GetShipmentFailureCode,
    GetShipmentInput,
    GetShipmentInsufficiencyCode,
    GetShipmentOutcome,
    GetShipmentQuery,
    GetShipmentResult,
    ShipmentAssessment,
    ShipmentAssessmentReason,
    ShipmentAssessmentResult,
    ShipmentEventCode,
    ShipmentFreshnessDecision,
    ShipmentFreshnessDecisionResult,
    ShipmentFreshnessReason,
    ShipmentSourceVersion,
    ShipmentStatus,
    ShipmentSummaryProjection,
    assess_shipment,
    classify_active_package_relation,
    compute_shipment_source_version,
    decide_shipment_freshness,
    project_get_shipment_agent_output,
    shipment_snapshot_is_fresh_at_acceptance,
    shipment_valid_until,
)

NOW = datetime(2030, 4, 1, 12, 30, 45, 123456, tzinfo=UTC)
SOURCE_VERSION = "mock-shipment-source-version.p0.v1:sha256:" + "c" * 64
GET_SHIPMENT_INSUFFICIENCY_CODE_OWNER = (
    "SHIPMENT_LATEST_EVENT_MISSING",
    "SHIPMENT_PROMISE_MISSING_FOR_ACTIVE_DELIVERY",
    "SHIPMENT_DELIVERED_AT_MISSING",
)
GET_SHIPMENT_FAILURE_CODE_OWNER = (
    "SHIPMENT_SERVICE_TRANSIENT",
    "SHIPMENT_SERVICE_UNAVAILABLE",
    "SHIPMENT_RELATION_CARDINALITY_VIOLATION",
    "SHIPMENT_SOURCE_INTEGRITY",
    "SHIPMENT_SOURCE_VERSION_INVALID",
)


def _summary(
    *,
    status: ShipmentStatus = ShipmentStatus.IN_TRANSIT,
    event: ShipmentEventCode = ShipmentEventCode.ARRIVED_AT_FACILITY,
    latest_event_at: datetime = NOW - timedelta(hours=2),
    promised_delivery_at: datetime | None = NOW + timedelta(days=1),
    delivered_at: datetime | None = None,
) -> ShipmentSummaryProjection:
    return ShipmentSummaryProjection(
        shipment_status=status,
        latest_event_code=event,
        latest_event_at=latest_event_at,
        promised_delivery_at=promised_delivery_at,
        delivered_at=delivered_at,
    )


def _found_result(
    *,
    summary: ShipmentSummaryProjection | None = None,
    observed_at: datetime = NOW,
) -> GetShipmentResult:
    return GetShipmentResult(
        outcome=GetShipmentOutcome.FOUND,
        shipment_summary=summary or _summary(),
        source_resource_ref="active-package-ref",
        source_version=SOURCE_VERSION,
        observed_at=observed_at,
    )


def _assessment_kwargs(
    *,
    assessed_at: datetime,
    claim_binding_ref: UUID | None = None,
) -> dict[str, object]:
    return {
        "assessment_id": uuid4(),
        "private_owner_scope_ref": "owner-scope-ref",
        "task_id": uuid4(),
        "request_unit_id": uuid4(),
        "task_state_version": 3,
        "verified_order_target_ref": "verified-order-ref",
        "shipment_observation_ref": uuid4(),
        "shipment_observation_source_version": SOURCE_VERSION,
        "claim_binding_ref": claim_binding_ref,
        "assessed_at": assessed_at,
    }


@pytest.mark.parametrize(
    ("status", "event", "promised", "delivered"),
    [
        (
            ShipmentStatus.LABEL_CREATED,
            ShipmentEventCode.LABEL_CREATED,
            NOW + timedelta(days=2),
            None,
        ),
        (
            ShipmentStatus.IN_TRANSIT,
            ShipmentEventCode.PICKED_UP,
            NOW + timedelta(days=2),
            None,
        ),
        (
            ShipmentStatus.IN_TRANSIT,
            ShipmentEventCode.IN_TRANSIT,
            NOW + timedelta(days=2),
            None,
        ),
        (
            ShipmentStatus.IN_TRANSIT,
            ShipmentEventCode.ARRIVED_AT_FACILITY,
            NOW + timedelta(days=2),
            None,
        ),
        (
            ShipmentStatus.OUT_FOR_DELIVERY,
            ShipmentEventCode.OUT_FOR_DELIVERY,
            NOW + timedelta(days=2),
            None,
        ),
        (
            ShipmentStatus.DELIVERED,
            ShipmentEventCode.DELIVERED,
            None,
            NOW,
        ),
    ],
)
def test_complete_shipment_projection_truth_table_accepts_valid_rows(
    status: ShipmentStatus,
    event: ShipmentEventCode,
    promised: datetime | None,
    delivered: datetime | None,
) -> None:
    summary = _summary(
        status=status,
        event=event,
        latest_event_at=NOW,
        promised_delivery_at=promised,
        delivered_at=delivered,
    )
    assert summary.shipment_status is status


@pytest.mark.parametrize(
    ("status", "event", "promised", "delivered", "message"),
    [
        (
            ShipmentStatus.LABEL_CREATED,
            ShipmentEventCode.IN_TRANSIT,
            NOW,
            None,
            "incompatible",
        ),
        (
            ShipmentStatus.IN_TRANSIT,
            ShipmentEventCode.ARRIVED_AT_FACILITY,
            None,
            None,
            "promised_delivery_at",
        ),
        (
            ShipmentStatus.OUT_FOR_DELIVERY,
            ShipmentEventCode.OUT_FOR_DELIVERY,
            NOW,
            NOW,
            "delivered_at",
        ),
        (
            ShipmentStatus.DELIVERED,
            ShipmentEventCode.DELIVERED,
            None,
            None,
            "delivered_at",
        ),
        (
            ShipmentStatus.DELIVERED,
            ShipmentEventCode.DELIVERED,
            None,
            NOW - timedelta(seconds=1),
            "latest_event_at",
        ),
    ],
)
def test_projection_rejects_contradictory_or_incomplete_truth_table_rows(
    status: ShipmentStatus,
    event: ShipmentEventCode,
    promised: datetime | None,
    delivered: datetime | None,
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        _summary(
            status=status,
            event=event,
            latest_event_at=NOW,
            promised_delivery_at=promised,
            delivered_at=delivered,
        )


@pytest.mark.parametrize("status", tuple(ShipmentStatus))
@pytest.mark.parametrize("event", tuple(ShipmentEventCode))
def test_status_event_truth_table_is_closed_for_every_pair(
    status: ShipmentStatus,
    event: ShipmentEventCode,
) -> None:
    allowed = {
        ShipmentStatus.LABEL_CREATED: {ShipmentEventCode.LABEL_CREATED},
        ShipmentStatus.IN_TRANSIT: {
            ShipmentEventCode.PICKED_UP,
            ShipmentEventCode.IN_TRANSIT,
            ShipmentEventCode.ARRIVED_AT_FACILITY,
        },
        ShipmentStatus.OUT_FOR_DELIVERY: {ShipmentEventCode.OUT_FOR_DELIVERY},
        ShipmentStatus.DELIVERED: {ShipmentEventCode.DELIVERED},
    }
    delivered = status is ShipmentStatus.DELIVERED
    payload = {
        "shipment_status": status,
        "latest_event_code": event,
        "latest_event_at": NOW,
        "promised_delivery_at": None if delivered else NOW + timedelta(days=1),
        "delivered_at": NOW if delivered else None,
    }
    if event in allowed[status]:
        assert ShipmentSummaryProjection(**payload).latest_event_code is event
    else:
        with pytest.raises(ValidationError, match="incompatible"):
            ShipmentSummaryProjection(**payload)


def test_projection_rejects_naive_or_non_utc_times() -> None:
    with pytest.raises(ValidationError, match="UTC"):
        _summary(latest_event_at=NOW.replace(tzinfo=None))

    with pytest.raises(ValidationError, match="UTC"):
        _summary(
            promised_delivery_at=NOW.astimezone(
                tz=timezone(timedelta(hours=8))
            )
        )


@pytest.mark.parametrize(
    ("count", "expected"),
    [
        (0, ActivePackageRelation.NO_ACTIVE_PACKAGE),
        (1, ActivePackageRelation.ONE_ACTIVE_PACKAGE),
        (2, ActivePackageRelation.CARDINALITY_VIOLATION),
        (99, ActivePackageRelation.CARDINALITY_VIOLATION),
    ],
)
def test_active_package_relation_is_closed_for_zero_one_or_more(
    count: int,
    expected: ActivePackageRelation,
) -> None:
    assert classify_active_package_relation(count) is expected


@pytest.mark.parametrize("invalid", [-1, True, 1.0, "1"])
def test_active_package_relation_rejects_non_strict_counts(invalid: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        classify_active_package_relation(invalid)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("outcome", "summary", "insufficiency", "failure", "valid"),
    [
        (GetShipmentOutcome.FOUND, "summary", None, None, True),
        (GetShipmentOutcome.FOUND, None, None, None, False),
        (GetShipmentOutcome.NO_SHIPMENT, None, None, None, True),
        (
            GetShipmentOutcome.FACTS_INSUFFICIENT,
            None,
            GetShipmentInsufficiencyCode.SHIPMENT_LATEST_EVENT_MISSING,
            None,
            True,
        ),
        (GetShipmentOutcome.FACTS_INSUFFICIENT, None, None, None, False),
        (GetShipmentOutcome.NOT_FOUND_OR_NOT_ACCESSIBLE, None, None, None, True),
        (
            GetShipmentOutcome.SYSTEM_FAILURE,
            None,
            None,
            GetShipmentFailureCode.SHIPMENT_SERVICE_TRANSIENT,
            True,
        ),
        (GetShipmentOutcome.SYSTEM_FAILURE, None, None, None, False),
    ],
)
def test_get_shipment_result_closed_outcome_matrix(
    outcome: GetShipmentOutcome,
    summary: str | None,
    insufficiency: GetShipmentInsufficiencyCode | None,
    failure: GetShipmentFailureCode | None,
    valid: bool,
) -> None:
    found = outcome is GetShipmentOutcome.FOUND
    payload = {
        "outcome": outcome,
        "shipment_summary": _summary() if summary else None,
        "source_resource_ref": "active-package-ref" if found else None,
        "source_version": SOURCE_VERSION if found else None,
        "observed_at": NOW if found else None,
        "insufficiency_code": insufficiency,
        "failure_code": failure,
    }
    if valid:
        result = GetShipmentResult(**payload)
        assert result.outcome is outcome
    else:
        with pytest.raises(ValidationError):
            GetShipmentResult(**payload)


def test_result_rejects_partial_projection_authority_or_unknown_codes() -> None:
    with pytest.raises(ValidationError, match="authority metadata"):
        GetShipmentResult(
            outcome=GetShipmentOutcome.NO_SHIPMENT,
            source_resource_ref="private-ref",
        )
    with pytest.raises(ValidationError):
        GetShipmentResult(
            outcome=GetShipmentOutcome.SYSTEM_FAILURE,
            failure_code="SHIPMENT_SNAPSHOT_STALE",
        )
    with pytest.raises(ValidationError, match="latest_event_at"):
        _found_result(observed_at=NOW - timedelta(hours=3))


def test_shipment_insufficiency_allowlist_matches_exact_owner_strings() -> None:
    assert {code.value for code in GetShipmentInsufficiencyCode} == set(
        GET_SHIPMENT_INSUFFICIENCY_CODE_OWNER
    )


@pytest.mark.parametrize("code_value", GET_SHIPMENT_INSUFFICIENCY_CODE_OWNER)
def test_each_owned_insufficiency_code_forms_a_fact_insufficient_result(
    code_value: str,
) -> None:
    result = GetShipmentResult(
        outcome=GetShipmentOutcome.FACTS_INSUFFICIENT,
        insufficiency_code=code_value,
    )
    assert result.insufficiency_code is not None
    assert result.insufficiency_code.value == code_value


@pytest.mark.parametrize(
    "invalid_code",
    (
        "SHIPMENT_FACTS_MISSING",
        "shipment_latest_event_missing",
        "SHIPMENT_SERVICE_TRANSIENT",
    ),
)
def test_non_owned_shipment_insufficiency_codes_are_rejected(
    invalid_code: str,
) -> None:
    with pytest.raises(ValidationError):
        GetShipmentResult(
            outcome=GetShipmentOutcome.FACTS_INSUFFICIENT,
            insufficiency_code=invalid_code,
        )


def test_shipment_failure_allowlist_matches_exact_owner_strings() -> None:
    assert {code.value for code in GetShipmentFailureCode} == set(
        GET_SHIPMENT_FAILURE_CODE_OWNER
    )


@pytest.mark.parametrize("code_value", GET_SHIPMENT_FAILURE_CODE_OWNER)
def test_each_owned_failure_code_forms_a_system_failure_result(
    code_value: str,
) -> None:
    result = GetShipmentResult(
        outcome=GetShipmentOutcome.SYSTEM_FAILURE,
        failure_code=code_value,
    )
    assert result.failure_code is not None
    assert result.failure_code.value == code_value


@pytest.mark.parametrize(
    "invalid_code",
    (
        "SHIPMENT_SNAPSHOT_STALE",
        "shipment_service_transient",
        "SHIPMENT_LATEST_EVENT_MISSING",
    ),
)
def test_non_owned_shipment_failure_codes_are_rejected(
    invalid_code: str,
) -> None:
    with pytest.raises(ValidationError):
        GetShipmentResult(
            outcome=GetShipmentOutcome.SYSTEM_FAILURE,
            failure_code=invalid_code,
        )


def test_shipment_source_token_uses_exact_canonical_json_bytes() -> None:
    summary = _summary()
    token = compute_shipment_source_version(
        owner_customer_id="customer-a",
        order_id="O-1001",
        source_resource_ref="active-package-ref",
        observed_at=NOW,
        safe_projection=summary,
    )
    payload = {
        "source_version_schema": "mock-shipment-source-version.p0.v1",
        "owner_customer_id": "customer-a",
        "order_id": "O-1001",
        "source_resource_ref": "active-package-ref",
        "observed_at": "2030-04-01T12:30:45.123456Z",
        "safe_projection": {
            "shipment_status": "IN_TRANSIT",
            "latest_event_code": "ARRIVED_AT_FACILITY",
            "latest_event_at": "2030-04-01T10:30:45.123456Z",
            "promised_delivery_at": "2030-04-02T12:30:45.123456Z",
            "delivered_at": None,
        },
    }
    canonical = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    expected = "mock-shipment-source-version.p0.v1:sha256:" + hashlib.sha256(
        canonical
    ).hexdigest()
    assert token == expected
    assert compute_shipment_source_version(
        owner_customer_id="customer-a",
        order_id="O-1001",
        source_resource_ref="different-ref",
        observed_at=NOW,
        safe_projection=summary,
    ) != token


def test_freshness_at_acceptance_uses_five_minute_exclusive_boundary() -> None:
    result = _found_result()
    assert SHIPMENT_FRESHNESS_TTL == timedelta(minutes=5)
    assert shipment_valid_until(NOW) == NOW + timedelta(minutes=5)
    assert shipment_snapshot_is_fresh_at_acceptance(
        result,
        trusted_acceptance_now=NOW + timedelta(minutes=5) - timedelta(microseconds=1),
    )
    assert not shipment_snapshot_is_fresh_at_acceptance(
        result,
        trusted_acceptance_now=NOW + timedelta(minutes=5),
    )

    with pytest.raises(ValueError, match="before observed_at"):
        shipment_snapshot_is_fresh_at_acceptance(
            result,
            trusted_acceptance_now=NOW - timedelta(microseconds=1),
        )


@pytest.mark.parametrize(
    (
        "observation_present",
        "trusted_now",
        "target_matches",
        "source_matches",
        "decision",
        "reason",
    ),
    [
        (
            False,
            NOW,
            False,
            False,
            ShipmentFreshnessDecision.REFRESH_REQUIRED,
            ShipmentFreshnessReason.NO_OBSERVATION,
        ),
        (
            True,
            NOW + timedelta(minutes=5),
            True,
            True,
            ShipmentFreshnessDecision.REFRESH_REQUIRED,
            ShipmentFreshnessReason.TTL_EXPIRED,
        ),
        (
            True,
            NOW,
            False,
            True,
            ShipmentFreshnessDecision.REFRESH_REQUIRED,
            ShipmentFreshnessReason.TARGET_BINDING_MISMATCH,
        ),
        (
            True,
            NOW,
            True,
            False,
            ShipmentFreshnessDecision.REFRESH_REQUIRED,
            ShipmentFreshnessReason.SOURCE_VERSION_MISMATCH,
        ),
        (
            True,
            NOW,
            True,
            True,
            ShipmentFreshnessDecision.USE_CURRENT,
            None,
        ),
    ],
)
def test_freshness_decision_has_fixed_precedence_and_reason(
    observation_present: bool,
    trusted_now: datetime,
    target_matches: bool,
    source_matches: bool,
    decision: ShipmentFreshnessDecision,
    reason: ShipmentFreshnessReason | None,
) -> None:
    valid_until = NOW + timedelta(minutes=5) if observation_present else None
    result = decide_shipment_freshness(
        observation_present=observation_present,
        trusted_freshness_now=trusted_now,
        valid_until=valid_until,
        target_binding_matches=target_matches,
        source_version_matches=source_matches,
    )
    assert result == ShipmentFreshnessDecisionResult(
        decision=decision,
        reason_code=reason,
    )


def test_freshness_result_rejects_incomplete_decision_shape() -> None:
    with pytest.raises(ValidationError, match="reason_code"):
        ShipmentFreshnessDecisionResult(
            decision=ShipmentFreshnessDecision.REFRESH_REQUIRED
        )
    with pytest.raises(ValidationError, match="reason_code"):
        ShipmentFreshnessDecisionResult(
            decision=ShipmentFreshnessDecision.USE_CURRENT,
            reason_code=ShipmentFreshnessReason.TTL_EXPIRED,
        )


@pytest.mark.parametrize(
    ("summary", "assessed_at", "claim", "primary", "reasons"),
    [
        (
            _summary(),
            NOW,
            None,
            ShipmentAssessmentResult.NORMAL,
            (ShipmentAssessmentReason.NO_P0_SHIPMENT_EXCEPTION,),
        ),
        (
            _summary(promised_delivery_at=NOW - timedelta(microseconds=1)),
            NOW,
            None,
            ShipmentAssessmentResult.DELAYED,
            (ShipmentAssessmentReason.PROMISED_DELIVERY_TIME_PASSED,),
        ),
        (
            _summary(latest_event_at=NOW - timedelta(hours=120)),
            NOW,
            None,
            ShipmentAssessmentResult.STALLED,
            (ShipmentAssessmentReason.NO_TRACKING_UPDATE_FOR_120_HOURS,),
        ),
        (
            _summary(
                latest_event_at=NOW - timedelta(hours=121),
                promised_delivery_at=NOW - timedelta(hours=1),
            ),
            NOW,
            None,
            ShipmentAssessmentResult.STALLED,
            (
                ShipmentAssessmentReason.NO_TRACKING_UPDATE_FOR_120_HOURS,
                ShipmentAssessmentReason.PROMISED_DELIVERY_TIME_PASSED,
            ),
        ),
        (
            _summary(
                status=ShipmentStatus.DELIVERED,
                event=ShipmentEventCode.DELIVERED,
                latest_event_at=NOW - timedelta(hours=1),
                promised_delivery_at=None,
                delivered_at=NOW - timedelta(hours=1),
            ),
            NOW,
            UUID("00000000-0000-0000-0000-000000000001"),
            ShipmentAssessmentResult.DELIVERED_NOT_RECEIVED,
            (
                ShipmentAssessmentReason.DELIVERED_STATUS_WITH_CURRENT_NOT_RECEIVED_CLAIM,
            ),
        ),
    ],
)
def test_deterministic_assessment_vectors_and_fixed_reason_order(
    summary: ShipmentSummaryProjection,
    assessed_at: datetime,
    claim: UUID | None,
    primary: ShipmentAssessmentResult,
    reasons: tuple[ShipmentAssessmentReason, ...],
) -> None:
    observation_observed_at = assessed_at - timedelta(minutes=1)
    assessment = assess_shipment(
        shipment_summary=summary,
        observation_observed_at=observation_observed_at,
        observation_valid_until=shipment_valid_until(observation_observed_at),
        **_assessment_kwargs(assessed_at=assessed_at, claim_binding_ref=claim),
    )
    assert assessment.primary_result is primary
    assert assessment.reason_codes == reasons
    assert assessment.assessment_rule_version == SHIPMENT_ASSESSMENT_RULE_VERSION
    assert SHIPMENT_STALLED_THRESHOLD == timedelta(hours=120)


def test_delay_requires_strictly_after_promise_and_stall_is_inclusive() -> None:
    at_promise = _summary(promised_delivery_at=NOW)
    observation_observed_at = NOW - timedelta(minutes=1)
    normal = assess_shipment(
        shipment_summary=at_promise,
        observation_observed_at=observation_observed_at,
        observation_valid_until=shipment_valid_until(observation_observed_at),
        **_assessment_kwargs(assessed_at=NOW),
    )
    assert normal.primary_result is ShipmentAssessmentResult.NORMAL

    before_stall = _summary(
        latest_event_at=NOW - timedelta(hours=120) + timedelta(microseconds=1)
    )
    not_stalled = assess_shipment(
        shipment_summary=before_stall,
        observation_observed_at=observation_observed_at,
        observation_valid_until=shipment_valid_until(observation_observed_at),
        **_assessment_kwargs(assessed_at=NOW),
    )
    assert not_stalled.primary_result is ShipmentAssessmentResult.NORMAL


def test_delivered_without_current_claim_is_normal_not_lost_fact() -> None:
    delivered = _summary(
        status=ShipmentStatus.DELIVERED,
        event=ShipmentEventCode.DELIVERED,
        latest_event_at=NOW,
        promised_delivery_at=None,
        delivered_at=NOW,
    )
    assessment = assess_shipment(
        shipment_summary=delivered,
        observation_observed_at=NOW,
        observation_valid_until=NOW + timedelta(minutes=5),
        **_assessment_kwargs(assessed_at=NOW),
    )
    assert assessment.primary_result is ShipmentAssessmentResult.NORMAL
    assert assessment.claim_binding_ref is None


def test_assessment_requires_a_fresh_observation_window() -> None:
    with pytest.raises(ValueError, match="fresh Observation window"):
        assess_shipment(
            shipment_summary=_summary(),
            observation_observed_at=NOW,
            observation_valid_until=NOW + timedelta(minutes=5),
            **_assessment_kwargs(assessed_at=NOW + timedelta(minutes=5)),
        )


def test_assessment_model_rejects_invented_or_misordered_reasons() -> None:
    kwargs = _assessment_kwargs(assessed_at=NOW)
    with pytest.raises(ValidationError, match="reason_codes"):
        ShipmentAssessment(
            **kwargs,
            primary_result=ShipmentAssessmentResult.STALLED,
            reason_codes=(
                ShipmentAssessmentReason.PROMISED_DELIVERY_TIME_PASSED,
                ShipmentAssessmentReason.NO_TRACKING_UPDATE_FOR_120_HOURS,
            ),
        )


def test_assessment_rejects_self_supersession_in_factory_and_direct_model() -> None:
    assessment_id = uuid4()
    kwargs = _assessment_kwargs(assessed_at=NOW)
    kwargs["assessment_id"] = assessment_id

    with pytest.raises(ValidationError, match="supersedes_assessment_ref"):
        ShipmentAssessment(
            **kwargs,
            primary_result=ShipmentAssessmentResult.NORMAL,
            reason_codes=(ShipmentAssessmentReason.NO_P0_SHIPMENT_EXCEPTION,),
            supersedes_assessment_ref=assessment_id,
        )

    observation_observed_at = NOW - timedelta(minutes=1)
    with pytest.raises(ValidationError, match="supersedes_assessment_ref"):
        assess_shipment(
            shipment_summary=_summary(),
            observation_observed_at=observation_observed_at,
            observation_valid_until=shipment_valid_until(
                observation_observed_at
            ),
            supersedes_assessment_ref=assessment_id,
            **kwargs,
        )


def test_model_visible_shipment_types_are_separate_minimum_projections() -> None:
    input_value = GetShipmentInput(order_id="O-1001")
    query = GetShipmentQuery(customer_id="customer-a", order_id="O-1001")
    output = project_get_shipment_agent_output(_summary())

    assert input_value.contract_visibility is ContractVisibility.MODEL_VISIBLE
    assert query.contract_visibility is ContractVisibility.RUNTIME_PRIVATE
    assert output == GetShipmentAgentOutput(
        shipment_status=ShipmentStatus.IN_TRANSIT,
        latest_event_code=ShipmentEventCode.ARRIVED_AT_FACILITY,
        latest_event_at_utc=NOW - timedelta(hours=2),
        promised_delivery_at_utc=NOW + timedelta(days=1),
        delivered_at_utc=None,
    )
    assert set(GetShipmentAgentOutput.model_fields) == {
        "shipment_status",
        "latest_event_code",
        "latest_event_at_utc",
        "promised_delivery_at_utc",
        "delivered_at_utc",
    }
    schema = str(GetShipmentAgentOutput.model_json_schema()).casefold()
    for forbidden in (
        "customer_id",
        "package_id",
        "tracking",
        "source_resource_ref",
        "source_version",
        "observed_at",
        "failure_code",
        "raw_result",
    ):
        assert forbidden not in schema

    with pytest.raises(ValidationError, match="extra"):
        GetShipmentAgentOutput.model_validate(
            {
                **output.model_dump(),
                "source_version": SOURCE_VERSION,
            }
        )


def test_shipment_source_version_pattern_is_strict() -> None:
    assert ShipmentSourceVersion is not str
    with pytest.raises(ValidationError):
        GetShipmentResult(
            outcome=GetShipmentOutcome.FOUND,
            shipment_summary=_summary(),
            source_resource_ref="active-package-ref",
            source_version="mock-shipment-source-version.p0.v1:sha256:" + "C" * 64,
            observed_at=NOW,
        )
