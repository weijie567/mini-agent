"""Pure policy gate for fact-free presentation plans."""

from __future__ import annotations

from pydantic import BaseModel, ValidationError

from .memory import (
    ObservationVisibility,
    OrderObservation,
    SearchOrdersObservationSafeCandidate,
    SearchOrdersObservationSafeProjection,
    ShipmentObservation,
)
from .order import (
    OrderLineSummary,
    OrderSummaryProjection,
)
from .order_search import (
    OrderCandidateMatchingItem,
    OrderCandidatePublicSummary,
)
from .presentation import (
    CandidatePresentationPlan,
    PresentationPlan,
    ShipmentPresentationPlan,
)
from .shipment import ShipmentAssessment, ShipmentSummaryProjection, assess_shipment


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
    try:
        canonical_plan = PresentationPlan.model_validate(
            dict(vars(plan)),
            strict=True,
        )
    except ValidationError:
        raise PresentationPolicyError(
            "PresentationPlan must remain fact-free and canonical"
        ) from None

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
    return canonical_plan


def validate_candidate_presentation_plan(
    *,
    plan: CandidatePresentationPlan,
    projection: SearchOrdersObservationSafeProjection,
) -> CandidatePresentationPlan:
    """Accept only fact-free controls plus the exact candidate whitelist."""

    if not _is_exact_contract_model(plan, CandidatePresentationPlan):
        raise PresentationPolicyError(
            "canonical fact-free CandidatePresentationPlan required"
        )
    try:
        canonical = CandidatePresentationPlan.model_validate(
            dict(vars(plan)), strict=True
        )
    except ValidationError:
        raise PresentationPolicyError(
            "CandidatePresentationPlan must remain fact-free and canonical"
        ) from None
    safe_projection = (
        _is_exact_contract_model(
            projection, SearchOrdersObservationSafeProjection
        )
        and all(
            _is_exact_contract_model(
                candidate, SearchOrdersObservationSafeCandidate
            )
            and _is_exact_contract_model(
                candidate.public_summary, OrderCandidatePublicSummary
            )
            and all(
                _is_exact_contract_model(item, OrderCandidateMatchingItem)
                for item in candidate.public_summary.matching_items
            )
            for candidate in projection.ordered_candidates
        )
    )
    if not safe_projection:
        raise PresentationPolicyError("exact safe candidate projection required")
    return canonical


def validate_shipment_presentation_plan(
    *,
    plan: ShipmentPresentationPlan,
    observation: ShipmentObservation,
    assessment: ShipmentAssessment,
) -> ShipmentPresentationPlan:
    """Reprove the exact fresh Observation-to-Assessment derivation."""

    if not _is_exact_contract_model(plan, ShipmentPresentationPlan):
        raise PresentationPolicyError(
            "canonical fact-free ShipmentPresentationPlan required"
        )
    try:
        canonical = ShipmentPresentationPlan.model_validate(
            dict(vars(plan)), strict=True
        )
    except ValidationError:
        raise PresentationPolicyError(
            "ShipmentPresentationPlan must remain fact-free and canonical"
        ) from None
    safe_observation = (
        _is_exact_contract_model(observation, ShipmentObservation)
        and observation.source_tool == "get_shipment"
        and observation.normalized_type == "SHIPMENT_SUMMARY"
        and observation.visibility is ObservationVisibility.AUDIT_ONLY
        and _is_exact_contract_model(
            observation.normalized_value, ShipmentSummaryProjection
        )
        and observation.recorded_at < observation.valid_until
    )
    if not safe_observation or not _is_exact_contract_model(
        assessment, ShipmentAssessment
    ):
        raise PresentationPolicyError(
            "exact safe Shipment Observation and Assessment required"
        )
    try:
        expected = assess_shipment(
            assessment_id=assessment.assessment_id,
            private_owner_scope_ref=observation.private_owner_scope,
            task_id=observation.task_id,
            request_unit_id=observation.request_unit_id,
            task_state_version=assessment.task_state_version,
            verified_order_target_ref=observation.verified_order_target_ref,
            shipment_observation_ref=observation.observation_id,
            shipment_observation_source_version=observation.source_version,
            shipment_summary=observation.normalized_value,
            observation_observed_at=observation.observed_at,
            observation_valid_until=observation.valid_until,
            assessed_at=assessment.assessed_at,
            claim_binding_ref=assessment.claim_binding_ref,
            supersedes_assessment_ref=assessment.supersedes_assessment_ref,
        )
    except (TypeError, ValueError):
        raise PresentationPolicyError(
            "Shipment Assessment derivation is not current and exact"
        ) from None
    if expected != assessment:
        raise PresentationPolicyError(
            "Shipment Assessment derivation is not current and exact"
        )
    return canonical
