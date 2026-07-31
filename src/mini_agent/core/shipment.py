"""Cycle 2 owner-scoped Shipment business contracts and pure rules."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Annotated, Literal, Self, cast
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from .common import ModelVisibleModel, RuntimePrivateModel, require_utc

SHIPMENT_FRESHNESS_TTL = timedelta(minutes=5)
SHIPMENT_STALLED_THRESHOLD = timedelta(hours=120)
SHIPMENT_ASSESSMENT_RULE_VERSION = "shipment-assessment-rules.p0.v1"
_SHIPMENT_SOURCE_SCHEMA = "mock-shipment-source-version.p0.v1"

StrictNonEmptyString = Annotated[str, Field(strict=True, min_length=1)]
StrictPositiveInt = Annotated[int, Field(strict=True, ge=1)]
OrderId = Annotated[str, Field(strict=True, pattern=r"^O-[0-9]{4,20}$")]
ShipmentSourceVersion = Annotated[
    str,
    Field(
        strict=True,
        pattern=(
            r"^mock-shipment-source-version\.p0\.v1:sha256:[0-9a-f]{64}$"
        ),
    ),
]


class ShipmentStatus(StrEnum):
    LABEL_CREATED = "LABEL_CREATED"
    IN_TRANSIT = "IN_TRANSIT"
    OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY"
    DELIVERED = "DELIVERED"


class ShipmentEventCode(StrEnum):
    LABEL_CREATED = "LABEL_CREATED"
    PICKED_UP = "PICKED_UP"
    IN_TRANSIT = "IN_TRANSIT"
    ARRIVED_AT_FACILITY = "ARRIVED_AT_FACILITY"
    OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY"
    DELIVERED = "DELIVERED"


_ALLOWED_EVENTS: dict[ShipmentStatus, frozenset[ShipmentEventCode]] = {
    ShipmentStatus.LABEL_CREATED: frozenset({ShipmentEventCode.LABEL_CREATED}),
    ShipmentStatus.IN_TRANSIT: frozenset(
        {
            ShipmentEventCode.PICKED_UP,
            ShipmentEventCode.IN_TRANSIT,
            ShipmentEventCode.ARRIVED_AT_FACILITY,
        }
    ),
    ShipmentStatus.OUT_FOR_DELIVERY: frozenset(
        {ShipmentEventCode.OUT_FOR_DELIVERY}
    ),
    ShipmentStatus.DELIVERED: frozenset({ShipmentEventCode.DELIVERED}),
}


class ShipmentSummaryProjection(ModelVisibleModel):
    """The complete minimum-safe Shipment fact projection."""

    shipment_status: ShipmentStatus
    latest_event_code: ShipmentEventCode
    latest_event_at: datetime
    promised_delivery_at: datetime | None = None
    delivered_at: datetime | None = None

    @field_validator(
        "latest_event_at",
        "promised_delivery_at",
        "delivered_at",
    )
    @classmethod
    def projection_timestamps_are_utc(
        cls,
        value: datetime | None,
    ) -> datetime | None:
        if value is None:
            return None
        return require_utc(value, field_name="ShipmentSummaryProjection timestamp")

    @model_validator(mode="after")
    def projection_matches_complete_truth_table(self) -> Self:
        if self.latest_event_code not in _ALLOWED_EVENTS[self.shipment_status]:
            raise ValueError(
                "latest_event_code is incompatible with shipment_status"
            )
        if self.shipment_status is ShipmentStatus.DELIVERED:
            if self.delivered_at is None:
                raise ValueError("DELIVERED requires delivered_at")
            if self.delivered_at != self.latest_event_at:
                raise ValueError("delivered_at must equal latest_event_at")
        else:
            if self.promised_delivery_at is None:
                raise ValueError(
                    "non-DELIVERED Shipment requires promised_delivery_at"
                )
            if self.delivered_at is not None:
                raise ValueError("non-DELIVERED Shipment cannot carry delivered_at")
        return self


class GetShipmentInput(ModelVisibleModel):
    """The only model-proposable Shipment field."""

    order_id: OrderId


class GetShipmentAgentOutput(ModelVisibleModel):
    """Provider-visible success shape, separate from private result metadata."""

    shipment_status: ShipmentStatus
    latest_event_code: ShipmentEventCode
    latest_event_at_utc: datetime
    promised_delivery_at_utc: datetime | None = None
    delivered_at_utc: datetime | None = None

    @field_validator(
        "latest_event_at_utc",
        "promised_delivery_at_utc",
        "delivered_at_utc",
    )
    @classmethod
    def output_timestamps_are_utc(
        cls,
        value: datetime | None,
    ) -> datetime | None:
        if value is None:
            return None
        return require_utc(value, field_name="GetShipmentAgentOutput timestamp")

    @model_validator(mode="after")
    def output_matches_safe_projection_truth_table(self) -> Self:
        ShipmentSummaryProjection(
            shipment_status=self.shipment_status,
            latest_event_code=self.latest_event_code,
            latest_event_at=self.latest_event_at_utc,
            promised_delivery_at=self.promised_delivery_at_utc,
            delivered_at=self.delivered_at_utc,
        )
        return self


def project_get_shipment_agent_output(
    summary: ShipmentSummaryProjection,
) -> GetShipmentAgentOutput:
    """Explicitly copy the safe whitelist without private authority metadata."""

    return GetShipmentAgentOutput(
        shipment_status=summary.shipment_status,
        latest_event_code=summary.latest_event_code,
        latest_event_at_utc=summary.latest_event_at,
        promised_delivery_at_utc=summary.promised_delivery_at,
        delivered_at_utc=summary.delivered_at,
    )


class GetShipmentQuery(RuntimePrivateModel):
    """Trusted identity plus the current verified order target."""

    customer_id: StrictNonEmptyString
    order_id: OrderId


class ActivePackageRelation(StrEnum):
    NO_ACTIVE_PACKAGE = "NO_ACTIVE_PACKAGE"
    ONE_ACTIVE_PACKAGE = "ONE_ACTIVE_PACKAGE"
    CARDINALITY_VIOLATION = "CARDINALITY_VIOLATION"


def classify_active_package_relation(package_count: int) -> ActivePackageRelation:
    """Classify the private 0/1/>1 relation without exposing the count."""

    if type(package_count) is not int:
        raise TypeError("package_count must be a strict integer")
    if package_count < 0:
        raise ValueError("package_count cannot be negative")
    if package_count == 0:
        return ActivePackageRelation.NO_ACTIVE_PACKAGE
    if package_count == 1:
        return ActivePackageRelation.ONE_ACTIVE_PACKAGE
    return ActivePackageRelation.CARDINALITY_VIOLATION


class GetShipmentOutcome(StrEnum):
    FOUND = "FOUND"
    NO_SHIPMENT = "NO_SHIPMENT"
    FACTS_INSUFFICIENT = "FACTS_INSUFFICIENT"
    NOT_FOUND_OR_NOT_ACCESSIBLE = "NOT_FOUND_OR_NOT_ACCESSIBLE"
    SYSTEM_FAILURE = "SYSTEM_FAILURE"


class GetShipmentInsufficiencyCode(StrEnum):
    SHIPMENT_LATEST_EVENT_MISSING = "SHIPMENT_LATEST_EVENT_MISSING"
    SHIPMENT_PROMISE_MISSING_FOR_ACTIVE_DELIVERY = (
        "SHIPMENT_PROMISE_MISSING_FOR_ACTIVE_DELIVERY"
    )
    SHIPMENT_DELIVERED_AT_MISSING = "SHIPMENT_DELIVERED_AT_MISSING"


class GetShipmentFailureCode(StrEnum):
    SHIPMENT_SERVICE_TRANSIENT = "SHIPMENT_SERVICE_TRANSIENT"
    SHIPMENT_SERVICE_UNAVAILABLE = "SHIPMENT_SERVICE_UNAVAILABLE"
    SHIPMENT_RELATION_CARDINALITY_VIOLATION = (
        "SHIPMENT_RELATION_CARDINALITY_VIOLATION"
    )
    SHIPMENT_SOURCE_INTEGRITY = "SHIPMENT_SOURCE_INTEGRITY"
    SHIPMENT_SOURCE_VERSION_INVALID = "SHIPMENT_SOURCE_VERSION_INVALID"


class GetShipmentResult(RuntimePrivateModel):
    outcome: GetShipmentOutcome
    shipment_summary: ShipmentSummaryProjection | None = None
    source_resource_ref: StrictNonEmptyString | None = None
    source_version: ShipmentSourceVersion | None = None
    observed_at: datetime | None = None
    insufficiency_code: GetShipmentInsufficiencyCode | None = None
    failure_code: GetShipmentFailureCode | None = None

    @field_validator("observed_at")
    @classmethod
    def observed_at_is_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return require_utc(value, field_name="GetShipmentResult.observed_at")

    @model_validator(mode="after")
    def result_shape_matches_closed_outcome_matrix(self) -> Self:
        authority = (
            self.source_resource_ref,
            self.source_version,
            self.observed_at,
        )
        authority_complete = all(value is not None for value in authority)
        authority_absent = all(value is None for value in authority)

        if self.outcome is GetShipmentOutcome.FOUND:
            if self.shipment_summary is None or not authority_complete:
                raise ValueError(
                    "FOUND requires safe summary and complete authority metadata"
                )
            if self.insufficiency_code is not None or self.failure_code is not None:
                raise ValueError("FOUND cannot carry failure or insufficiency code")
            if self.shipment_summary.latest_event_at > cast(datetime, self.observed_at):
                raise ValueError("latest_event_at cannot be after observed_at")
        elif self.outcome is GetShipmentOutcome.FACTS_INSUFFICIENT:
            if self.shipment_summary is not None or not authority_absent:
                raise ValueError(
                    "FACTS_INSUFFICIENT cannot carry partial projection or authority "
                    "metadata"
                )
            if self.insufficiency_code is None or self.failure_code is not None:
                raise ValueError(
                    "FACTS_INSUFFICIENT requires only an allowlisted insufficiency_code"
                )
        elif self.outcome is GetShipmentOutcome.SYSTEM_FAILURE:
            if self.shipment_summary is not None or not authority_absent:
                raise ValueError(
                    "SYSTEM_FAILURE cannot carry projection or authority metadata"
                )
            if self.failure_code is None or self.insufficiency_code is not None:
                raise ValueError(
                    "SYSTEM_FAILURE requires only an allowlisted failure_code"
                )
        else:
            if self.shipment_summary is not None or not authority_absent:
                raise ValueError(
                    "safe non-FOUND outcome cannot carry projection or authority "
                    "metadata"
                )
            if self.insufficiency_code is not None or self.failure_code is not None:
                raise ValueError("safe non-FOUND outcome cannot carry internal code")
        return self


def _utc_source_timestamp(value: datetime, *, field_name: str) -> str:
    value = require_utc(value, field_name=field_name)
    return value.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _optional_utc_source_timestamp(
    value: datetime | None,
    *,
    field_name: str,
) -> str | None:
    if value is None:
        return None
    return _utc_source_timestamp(value, field_name=field_name)


def _require_non_empty_string(value: str, *, field_name: str) -> None:
    if type(value) is not str or not value:
        raise ValueError(f"{field_name} must be a non-empty string")


def compute_shipment_source_version(
    *,
    owner_customer_id: str,
    order_id: str,
    source_resource_ref: str,
    observed_at: datetime,
    safe_projection: ShipmentSummaryProjection,
) -> ShipmentSourceVersion:
    """Hash the exact Shipment source payload; this does not confer authority."""

    query = GetShipmentQuery(customer_id=owner_customer_id, order_id=order_id)
    _require_non_empty_string(source_resource_ref, field_name="source_resource_ref")
    observed_at = require_utc(observed_at, field_name="observed_at")
    if safe_projection.latest_event_at > observed_at:
        raise ValueError("latest_event_at cannot be after observed_at")

    payload: dict[str, object] = {
        "source_version_schema": _SHIPMENT_SOURCE_SCHEMA,
        "owner_customer_id": query.customer_id,
        "order_id": query.order_id,
        "source_resource_ref": source_resource_ref,
        "observed_at": _utc_source_timestamp(
            observed_at,
            field_name="observed_at",
        ),
        "safe_projection": {
            "shipment_status": safe_projection.shipment_status.value,
            "latest_event_code": safe_projection.latest_event_code.value,
            "latest_event_at": _utc_source_timestamp(
                safe_projection.latest_event_at,
                field_name="latest_event_at",
            ),
            "promised_delivery_at": _optional_utc_source_timestamp(
                safe_projection.promised_delivery_at,
                field_name="promised_delivery_at",
            ),
            "delivered_at": _optional_utc_source_timestamp(
                safe_projection.delivered_at,
                field_name="delivered_at",
            ),
        },
    }
    canonical_bytes = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return cast(
        ShipmentSourceVersion,
        (
            f"{_SHIPMENT_SOURCE_SCHEMA}:sha256:"
            f"{hashlib.sha256(canonical_bytes).hexdigest()}"
        ),
    )


def shipment_valid_until(observed_at: datetime) -> datetime:
    observed_at = require_utc(observed_at, field_name="observed_at")
    return observed_at + SHIPMENT_FRESHNESS_TTL


def shipment_snapshot_is_fresh_at_acceptance(
    result: GetShipmentResult,
    *,
    trusted_acceptance_now: datetime,
) -> bool:
    """Apply the born-stale gate without rewriting the successful Tool result."""

    if result.outcome is not GetShipmentOutcome.FOUND or result.observed_at is None:
        raise ValueError("freshness-at-acceptance requires a FOUND Shipment result")
    trusted_acceptance_now = require_utc(
        trusted_acceptance_now,
        field_name="trusted_acceptance_now",
    )
    if trusted_acceptance_now < result.observed_at:
        raise ValueError("trusted_acceptance_now cannot be before observed_at")
    return trusted_acceptance_now < shipment_valid_until(result.observed_at)


class ShipmentFreshnessDecision(StrEnum):
    USE_CURRENT = "USE_CURRENT"
    REFRESH_REQUIRED = "REFRESH_REQUIRED"


class ShipmentFreshnessReason(StrEnum):
    NO_OBSERVATION = "NO_OBSERVATION"
    TTL_EXPIRED = "TTL_EXPIRED"
    TARGET_BINDING_MISMATCH = "TARGET_BINDING_MISMATCH"
    SOURCE_VERSION_MISMATCH = "SOURCE_VERSION_MISMATCH"


class ShipmentFreshnessDecisionResult(RuntimePrivateModel):
    decision: ShipmentFreshnessDecision
    reason_code: ShipmentFreshnessReason | None = None

    @model_validator(mode="after")
    def decision_shape_is_closed(self) -> Self:
        if self.decision is ShipmentFreshnessDecision.USE_CURRENT:
            if self.reason_code is not None:
                raise ValueError("USE_CURRENT cannot carry reason_code")
        elif self.reason_code is None:
            raise ValueError("REFRESH_REQUIRED requires reason_code")
        return self


def decide_shipment_freshness(
    *,
    observation_present: bool,
    trusted_freshness_now: datetime,
    valid_until: datetime | None,
    target_binding_matches: bool,
    source_version_matches: bool,
) -> ShipmentFreshnessDecisionResult:
    """Apply the exact no-observation/TTL/binding/version precedence."""

    for name, value in (
        ("observation_present", observation_present),
        ("target_binding_matches", target_binding_matches),
        ("source_version_matches", source_version_matches),
    ):
        if type(value) is not bool:
            raise TypeError(f"{name} must be a strict boolean")
    trusted_freshness_now = require_utc(
        trusted_freshness_now,
        field_name="trusted_freshness_now",
    )

    if not observation_present:
        if valid_until is not None:
            raise ValueError("absent Observation cannot carry valid_until")
        return ShipmentFreshnessDecisionResult(
            decision=ShipmentFreshnessDecision.REFRESH_REQUIRED,
            reason_code=ShipmentFreshnessReason.NO_OBSERVATION,
        )
    if valid_until is None:
        raise ValueError("present Observation requires valid_until")
    valid_until = require_utc(valid_until, field_name="valid_until")
    if trusted_freshness_now >= valid_until:
        return ShipmentFreshnessDecisionResult(
            decision=ShipmentFreshnessDecision.REFRESH_REQUIRED,
            reason_code=ShipmentFreshnessReason.TTL_EXPIRED,
        )
    if not target_binding_matches:
        return ShipmentFreshnessDecisionResult(
            decision=ShipmentFreshnessDecision.REFRESH_REQUIRED,
            reason_code=ShipmentFreshnessReason.TARGET_BINDING_MISMATCH,
        )
    if not source_version_matches:
        return ShipmentFreshnessDecisionResult(
            decision=ShipmentFreshnessDecision.REFRESH_REQUIRED,
            reason_code=ShipmentFreshnessReason.SOURCE_VERSION_MISMATCH,
        )
    return ShipmentFreshnessDecisionResult(
        decision=ShipmentFreshnessDecision.USE_CURRENT,
    )


class ShipmentAssessmentResult(StrEnum):
    DELIVERED_NOT_RECEIVED = "DELIVERED_NOT_RECEIVED"
    STALLED = "STALLED"
    DELAYED = "DELAYED"
    NORMAL = "NORMAL"


class ShipmentAssessmentReason(StrEnum):
    DELIVERED_STATUS_WITH_CURRENT_NOT_RECEIVED_CLAIM = (
        "DELIVERED_STATUS_WITH_CURRENT_NOT_RECEIVED_CLAIM"
    )
    NO_TRACKING_UPDATE_FOR_120_HOURS = "NO_TRACKING_UPDATE_FOR_120_HOURS"
    PROMISED_DELIVERY_TIME_PASSED = "PROMISED_DELIVERY_TIME_PASSED"
    NO_P0_SHIPMENT_EXCEPTION = "NO_P0_SHIPMENT_EXCEPTION"


_VALID_REASON_SHAPES: dict[
    ShipmentAssessmentResult,
    frozenset[tuple[ShipmentAssessmentReason, ...]],
] = {
    ShipmentAssessmentResult.DELIVERED_NOT_RECEIVED: frozenset(
        {
            (
                ShipmentAssessmentReason.DELIVERED_STATUS_WITH_CURRENT_NOT_RECEIVED_CLAIM,
            )
        }
    ),
    ShipmentAssessmentResult.STALLED: frozenset(
        {
            (ShipmentAssessmentReason.NO_TRACKING_UPDATE_FOR_120_HOURS,),
            (
                ShipmentAssessmentReason.NO_TRACKING_UPDATE_FOR_120_HOURS,
                ShipmentAssessmentReason.PROMISED_DELIVERY_TIME_PASSED,
            ),
        }
    ),
    ShipmentAssessmentResult.DELAYED: frozenset(
        {(ShipmentAssessmentReason.PROMISED_DELIVERY_TIME_PASSED,)}
    ),
    ShipmentAssessmentResult.NORMAL: frozenset(
        {(ShipmentAssessmentReason.NO_P0_SHIPMENT_EXCEPTION,)}
    ),
}


class ShipmentAssessment(RuntimePrivateModel):
    """Deterministic derivation bound to one exact fresh Observation."""

    assessment_id: UUID
    private_owner_scope_ref: StrictNonEmptyString
    task_id: UUID
    request_unit_id: UUID
    task_state_version: StrictPositiveInt
    verified_order_target_ref: StrictNonEmptyString
    shipment_observation_ref: UUID
    shipment_observation_source_version: ShipmentSourceVersion
    claim_binding_ref: UUID | None = None
    assessment_rule_version: Literal["shipment-assessment-rules.p0.v1"] = (
        SHIPMENT_ASSESSMENT_RULE_VERSION
    )
    primary_result: ShipmentAssessmentResult
    reason_codes: Annotated[
        tuple[ShipmentAssessmentReason, ...],
        Field(min_length=1, max_length=3),
    ]
    assessed_at: datetime
    supersedes_assessment_ref: UUID | None = None

    @field_validator("assessed_at")
    @classmethod
    def assessed_at_is_utc(cls, value: datetime) -> datetime:
        return require_utc(value, field_name="ShipmentAssessment.assessed_at")

    @model_validator(mode="after")
    def assessment_reason_shape_is_exact(self) -> Self:
        if self.reason_codes not in _VALID_REASON_SHAPES[self.primary_result]:
            raise ValueError(
                "reason_codes do not match primary_result or fixed reason order"
            )
        if self.supersedes_assessment_ref == self.assessment_id:
            raise ValueError(
                "supersedes_assessment_ref cannot equal assessment_id"
            )
        if (
            self.primary_result is ShipmentAssessmentResult.DELIVERED_NOT_RECEIVED
            and self.claim_binding_ref is None
        ):
            raise ValueError(
                "DELIVERED_NOT_RECEIVED requires a current Claim binding ref"
            )
        return self


def assess_shipment(
    *,
    assessment_id: UUID,
    private_owner_scope_ref: str,
    task_id: UUID,
    request_unit_id: UUID,
    task_state_version: int,
    verified_order_target_ref: str,
    shipment_observation_ref: UUID,
    shipment_observation_source_version: str,
    shipment_summary: ShipmentSummaryProjection,
    observation_observed_at: datetime,
    observation_valid_until: datetime,
    assessed_at: datetime,
    claim_binding_ref: UUID | None = None,
    supersedes_assessment_ref: UUID | None = None,
) -> ShipmentAssessment:
    """Compute the approved primary result and all applicable stable reasons.

    A non-``None`` ``claim_binding_ref`` means the caller has already proven the
    accepted binding is current for this exact owner/Task/RequestUnit/target and
    Task version.  Claim text is never accepted or converted into a Shipment fact.
    """

    observation_observed_at = require_utc(
        observation_observed_at,
        field_name="observation_observed_at",
    )
    observation_valid_until = require_utc(
        observation_valid_until,
        field_name="observation_valid_until",
    )
    assessed_at = require_utc(assessed_at, field_name="assessed_at")
    if observation_valid_until != shipment_valid_until(observation_observed_at):
        raise ValueError("Observation valid_until must equal observed_at plus 5 minutes")
    if shipment_summary.latest_event_at > observation_observed_at:
        raise ValueError("latest_event_at cannot be after Observation observed_at")
    if not observation_observed_at <= assessed_at < observation_valid_until:
        raise ValueError("assessed_at must be inside the fresh Observation window")

    is_delivered = shipment_summary.shipment_status is ShipmentStatus.DELIVERED
    delivered_not_received = is_delivered and claim_binding_ref is not None
    stalled = (
        not is_delivered
        and assessed_at - shipment_summary.latest_event_at
        >= SHIPMENT_STALLED_THRESHOLD
    )
    delayed = (
        not is_delivered
        and shipment_summary.promised_delivery_at is not None
        and assessed_at > shipment_summary.promised_delivery_at
    )

    reasons: list[ShipmentAssessmentReason] = []
    if delivered_not_received:
        reasons.append(
            ShipmentAssessmentReason.DELIVERED_STATUS_WITH_CURRENT_NOT_RECEIVED_CLAIM
        )
    if stalled:
        reasons.append(ShipmentAssessmentReason.NO_TRACKING_UPDATE_FOR_120_HOURS)
    if delayed:
        reasons.append(ShipmentAssessmentReason.PROMISED_DELIVERY_TIME_PASSED)
    if not reasons:
        reasons.append(ShipmentAssessmentReason.NO_P0_SHIPMENT_EXCEPTION)

    if delivered_not_received:
        primary = ShipmentAssessmentResult.DELIVERED_NOT_RECEIVED
    elif stalled:
        primary = ShipmentAssessmentResult.STALLED
    elif delayed:
        primary = ShipmentAssessmentResult.DELAYED
    else:
        primary = ShipmentAssessmentResult.NORMAL

    return ShipmentAssessment(
        assessment_id=assessment_id,
        private_owner_scope_ref=private_owner_scope_ref,
        task_id=task_id,
        request_unit_id=request_unit_id,
        task_state_version=task_state_version,
        verified_order_target_ref=verified_order_target_ref,
        shipment_observation_ref=shipment_observation_ref,
        shipment_observation_source_version=shipment_observation_source_version,
        claim_binding_ref=claim_binding_ref,
        primary_result=primary,
        reason_codes=tuple(reasons),
        assessed_at=assessed_at,
        supersedes_assessment_ref=supersedes_assessment_ref,
    )
