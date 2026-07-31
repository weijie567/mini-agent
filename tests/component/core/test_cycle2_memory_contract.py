from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from mini_agent.core.common import ContractVisibility
from mini_agent.core.memory import (
    ObservationVisibility,
    SearchObservationCandidateTargetBinding,
    SearchOrdersObservation,
    SearchOrdersObservationCandidate,
    SearchOrdersObservationSafeProjection,
    SearchOrdersObservationValue,
    ShipmentObservation,
    decide_loaded_shipment_observation_freshness,
    project_search_orders_observation_safe,
    validate_candidate_selection_closure,
    validate_search_candidate_set_observation_closure,
    validate_shipment_observation_supersession,
)
from mini_agent.core.order import OrderStatus
from mini_agent.core.order_search import (
    OrderCandidateMatchingItem,
    OrderCandidatePublicSummary,
)
from mini_agent.core.shipment import (
    ShipmentEventCode,
    ShipmentFreshnessDecision,
    ShipmentFreshnessReason,
    ShipmentStatus,
    ShipmentSummaryProjection,
)
from mini_agent.core.task_state import (
    ORDER_SEARCH_OBSERVATION_RECORD_SCHEMA_VERSION,
    OrderCandidateSelectionRequest,
    OrderCandidateSetEntry,
    OrderCandidateSetOutcome,
    OrderCandidateSetRecord,
    compute_order_candidate_set_version,
)

NOW = datetime(2030, 1, 1, 12, 0, 0, 123456, tzinfo=UTC)
OWNER = "owner-scope:session-1"
SNAPSHOT_VERSION = (
    "mock-order-search-snapshot-source-version.p0.v1:sha256:" + "a" * 64
)
CANDIDATE_VERSION_1 = (
    "mock-order-search-candidate-source-version.p0.v1:sha256:" + "1" * 64
)
CANDIDATE_VERSION_2 = (
    "mock-order-search-candidate-source-version.p0.v1:sha256:" + "2" * 64
)
SHIPMENT_VERSION = "mock-shipment-source-version.p0.v1:sha256:" + "b" * 64


def _public_summary(order_number: str) -> OrderCandidatePublicSummary:
    return OrderCandidatePublicSummary(
        order_number=order_number,
        ordered_on_utc=date(2029, 12, 31),
        status=OrderStatus.SHIPPED,
        matching_items=(
            OrderCandidateMatchingItem(product_name="示例鞋", quantity=1),
        ),
    )


def _search_observation(**overrides: object) -> SearchOrdersObservation:
    candidate_ref_1 = uuid4()
    candidate_ref_2 = uuid4()
    values: dict[str, object] = {
        "observation_id": uuid4(),
        "private_owner_scope": OWNER,
        "source_tool": "search_orders",
        "source_tool_call_id": uuid4(),
        "source_resource_ref": "order-search-snapshot:1",
        "source_version": SNAPSHOT_VERSION,
        "candidate_target_bindings": (
            SearchObservationCandidateTargetBinding(
                observation_candidate_ref=candidate_ref_1,
                owner_scoped_order_ref="owner-order:1",
                candidate_source_version=CANDIDATE_VERSION_1,
            ),
            SearchObservationCandidateTargetBinding(
                observation_candidate_ref=candidate_ref_2,
                owner_scoped_order_ref="owner-order:2",
                candidate_source_version=CANDIDATE_VERSION_2,
            ),
        ),
        "normalized_type": "ORDER_SEARCH_CANDIDATES",
        "normalized_value": SearchOrdersObservationValue(
            ordered_candidates=(
                SearchOrdersObservationCandidate(
                    observation_candidate_ref=candidate_ref_1,
                    candidate_source_version=CANDIDATE_VERSION_1,
                    public_summary=_public_summary("O-1001"),
                ),
                SearchOrdersObservationCandidate(
                    observation_candidate_ref=candidate_ref_2,
                    candidate_source_version=CANDIDATE_VERSION_2,
                    public_summary=_public_summary("O-1002"),
                ),
            ),
            truncated=False,
        ),
        "observed_at": NOW,
        "recorded_at": NOW + timedelta(seconds=1),
        "valid_until": NOW + timedelta(minutes=15, seconds=1),
        "visibility": ObservationVisibility.AUDIT_ONLY,
    }
    values.update(overrides)
    return SearchOrdersObservation.model_validate(values)


def _candidate_set(
    observation: SearchOrdersObservation,
    **overrides: object,
) -> OrderCandidateSetRecord:
    entries = tuple(
        OrderCandidateSetEntry(
            ordinal=ordinal,
            observation_candidate_ref=candidate.observation_candidate_ref,
            candidate_source_version=candidate.candidate_source_version,
        )
        for ordinal, candidate in enumerate(
            observation.normalized_value.ordered_candidates,
            start=1,
        )
    )
    values: dict[str, object] = {
        "candidate_set_id": uuid4(),
        "private_owner_scope_ref": observation.private_owner_scope,
        "conversation_id": uuid4(),
        "task_id": uuid4(),
        "request_unit_id": uuid4(),
        "outcome": (
            OrderCandidateSetOutcome.UNIQUE
            if len(entries) == 1
            else OrderCandidateSetOutcome.MULTIPLE
        ),
        "base_task_state_version": 3,
        "result_task_state_version": 4,
        "selection_expected_task_state_version": (
            None if len(entries) == 1 else 4
        ),
        "query_binding_refs": (uuid4(),),
        "source_tool_call_id": observation.source_tool_call_id,
        "search_observation_ref": observation.observation_id,
        "search_observation_record_schema_version": (
            ORDER_SEARCH_OBSERVATION_RECORD_SCHEMA_VERSION
        ),
        "search_observation_source_version": observation.source_version,
        "ordered_candidates": entries,
        "created_at": observation.recorded_at,
        "valid_until": observation.valid_until,
        "supersedes_candidate_set_ref": None,
    }
    values.update(overrides)
    values["candidate_set_version"] = compute_order_candidate_set_version(
        **{
            key: value
            for key, value in values.items()
            if key != "candidate_set_version"
        }
    )
    return OrderCandidateSetRecord.model_validate(values)


def _shipment_summary() -> ShipmentSummaryProjection:
    return ShipmentSummaryProjection(
        shipment_status=ShipmentStatus.IN_TRANSIT,
        latest_event_code=ShipmentEventCode.IN_TRANSIT,
        latest_event_at=NOW - timedelta(hours=1),
        promised_delivery_at=NOW + timedelta(days=1),
    )


def _shipment_observation(**overrides: object) -> ShipmentObservation:
    values: dict[str, object] = {
        "observation_id": uuid4(),
        "private_owner_scope": OWNER,
        "task_id": uuid4(),
        "request_unit_id": uuid4(),
        "verified_order_target_ref": "verified-order:1",
        "source_tool": "get_shipment",
        "source_tool_call_id": uuid4(),
        "source_resource_ref": "shipment:1",
        "source_version": SHIPMENT_VERSION,
        "normalized_type": "SHIPMENT_SUMMARY",
        "normalized_value": _shipment_summary(),
        "observed_at": NOW,
        "recorded_at": NOW + timedelta(minutes=1),
        "valid_until": NOW + timedelta(minutes=5),
        "visibility": ObservationVisibility.AUDIT_ONLY,
    }
    values.update(overrides)
    return ShipmentObservation.model_validate(values)


def test_search_observation_is_audit_only_and_safe_projection_is_exact() -> None:
    observation = _search_observation()
    projection = project_search_orders_observation_safe(observation)

    assert observation.contract_visibility is ContractVisibility.AUDIT_ONLY
    assert observation.visibility is ObservationVisibility.AUDIT_ONLY
    assert projection.contract_visibility is ContractVisibility.MODEL_VISIBLE
    assert tuple(SearchOrdersObservationSafeProjection.model_fields) == (
        "matching_rule_version",
        "ordered_candidates",
        "truncated",
    )
    assert tuple(type(projection.ordered_candidates[0]).model_fields) == (
        "ordinal",
        "public_summary",
    )
    serialized = projection.model_dump(mode="json")
    forbidden = {
        "private_owner_scope",
        "source_resource_ref",
        "source_version",
        "candidate_target_bindings",
        "owner_scoped_order_ref",
        "observation_candidate_ref",
        "candidate_source_version",
    }
    assert forbidden.isdisjoint(serialized)
    assert forbidden.isdisjoint(serialized["ordered_candidates"][0])
    assert projection.ordered_candidates[1].ordinal == 2


def test_search_observation_requires_exact_safe_private_mapping_and_ttl() -> None:
    observation = _search_observation()
    first = observation.candidate_target_bindings[0]
    second = observation.candidate_target_bindings[1]
    base_payload = observation.model_dump()

    with pytest.raises(ValidationError, match="exactly match"):
        SearchOrdersObservation.model_validate(
            {**base_payload, "candidate_target_bindings": (second, first)}
        )
    with pytest.raises(ValidationError, match="unique"):
        SearchOrdersObservation.model_validate(
            {
                **base_payload,
                "candidate_target_bindings": (
                    first,
                    second.model_copy(
                        update={
                            "owner_scoped_order_ref": first.owner_scoped_order_ref
                        }
                    ),
                ),
            }
        )
    with pytest.raises(ValidationError, match="15 minutes"):
        _search_observation(valid_until=NOW + timedelta(minutes=15))
    with pytest.raises(ValidationError):
        _search_observation(visibility=ObservationVisibility.MODEL_VISIBLE)


def test_candidate_set_and_search_observation_closure_is_exact() -> None:
    observation = _search_observation()
    candidate_set = _candidate_set(observation)

    validate_search_candidate_set_observation_closure(
        candidate_set=candidate_set,
        observation=observation,
    )

    other_observation = SearchOrdersObservation.model_validate(
        {**observation.model_dump(), "observation_id": uuid4()}
    )
    with pytest.raises(ValueError, match="ref mismatch"):
        validate_search_candidate_set_observation_closure(
            candidate_set=candidate_set,
            observation=other_observation,
        )


def test_private_candidate_mapping_is_exact_and_never_model_visible() -> None:
    observation = _search_observation()

    assert tuple(SearchObservationCandidateTargetBinding.model_fields) == (
        "observation_candidate_ref",
        "owner_scoped_order_ref",
        "candidate_source_version",
    )
    assert (
        observation.candidate_target_bindings[1].owner_scoped_order_ref
        == "owner-order:2"
    )
    projection_json = project_search_orders_observation_safe(observation).model_dump_json()
    assert "owner-order:2" not in projection_json


def test_selection_closure_returns_only_validated_opaque_mapping() -> None:
    observation = _search_observation()
    candidate_set = _candidate_set(observation)
    request = OrderCandidateSelectionRequest(
        source_message_ref=uuid4(),
        ordinal_input_binding_ref=uuid4(),
        ordinal=2,
    )
    resolution = validate_candidate_selection_closure(
        current_candidate_sets=(candidate_set,),
        observation=observation,
        request=request,
        trusted_owner_scope_ref=OWNER,
        conversation_id=candidate_set.conversation_id,
        task_id=candidate_set.task_id,
        request_unit_id=candidate_set.request_unit_id,
        pending_candidate_set_ref=candidate_set.candidate_set_id,
        current_task_state_version=4,
        current_query_binding_refs=candidate_set.query_binding_refs,
        trusted_now=observation.valid_until - timedelta(microseconds=1),
        resolved_owner_scoped_order_target_ref="owner-order:2",
    )

    assert resolution.decision == "ACCEPT"
    assert resolution.ordinal == 2
    assert "owner_scoped_order_target_ref" not in type(resolution).model_fields
    assert "selected_target_ref" not in type(resolution).model_fields
    assert "tool_call_id" not in type(resolution).model_fields

    with pytest.raises(ValueError, match="did not resolve"):
        validate_candidate_selection_closure(
            current_candidate_sets=(candidate_set,),
            observation=observation,
            request=request,
            trusted_owner_scope_ref=OWNER,
            conversation_id=candidate_set.conversation_id,
            task_id=candidate_set.task_id,
            request_unit_id=candidate_set.request_unit_id,
            pending_candidate_set_ref=candidate_set.candidate_set_id,
            current_task_state_version=4,
            current_query_binding_refs=candidate_set.query_binding_refs,
            trusted_now=NOW + timedelta(minutes=1),
            resolved_owner_scoped_order_target_ref=None,
        )
    with pytest.raises(ValueError, match="result mismatch"):
        validate_candidate_selection_closure(
            current_candidate_sets=(candidate_set,),
            observation=observation,
            request=request,
            trusted_owner_scope_ref=OWNER,
            conversation_id=candidate_set.conversation_id,
            task_id=candidate_set.task_id,
            request_unit_id=candidate_set.request_unit_id,
            pending_candidate_set_ref=candidate_set.candidate_set_id,
            current_task_state_version=4,
            current_query_binding_refs=candidate_set.query_binding_refs,
            trusted_now=NOW + timedelta(minutes=1),
            resolved_owner_scoped_order_target_ref="owner-order:other",
        )


def test_shipment_observation_enforces_exact_ttl_and_born_stale_gate() -> None:
    observation = _shipment_observation()

    assert observation.visibility is ObservationVisibility.AUDIT_ONLY
    assert observation.normalized_value == _shipment_summary()
    assert observation.valid_until == observation.observed_at + timedelta(minutes=5)

    with pytest.raises(ValidationError, match="5 minutes"):
        _shipment_observation(valid_until=NOW + timedelta(minutes=6))
    with pytest.raises(ValidationError, match="born stale"):
        _shipment_observation(recorded_at=NOW + timedelta(minutes=5))
    with pytest.raises(ValidationError, match="latest_event_at"):
        _shipment_observation(
            normalized_value=_shipment_summary().model_copy(
                update={"latest_event_at": NOW + timedelta(seconds=1)}
            )
        )
    with pytest.raises(ValidationError):
        _shipment_observation(visibility=ObservationVisibility.MODEL_VISIBLE)


def _freshness(
    observation: ShipmentObservation,
    **overrides: object,
):
    arguments: dict[str, object] = {
        "current_observations": (observation,),
        "trusted_freshness_now": NOW + timedelta(minutes=2),
        "trusted_owner_scope_ref": observation.private_owner_scope,
        "task_id": observation.task_id,
        "request_unit_id": observation.request_unit_id,
        "verified_order_target_ref": observation.verified_order_target_ref,
        "source_resource_ref": observation.source_resource_ref,
        "source_version": observation.source_version,
    }
    arguments.update(overrides)
    return decide_loaded_shipment_observation_freshness(**arguments)


def test_loaded_shipment_freshness_uses_exact_binding_and_ttl_boundary() -> None:
    observation = _shipment_observation()

    assert _freshness(observation).decision is ShipmentFreshnessDecision.USE_CURRENT
    expired = _freshness(
        observation,
        trusted_freshness_now=observation.valid_until,
    )
    assert expired.reason_code is ShipmentFreshnessReason.TTL_EXPIRED
    wrong_target = _freshness(
        observation,
        verified_order_target_ref="verified-order:other",
    )
    assert wrong_target.reason_code is ShipmentFreshnessReason.TARGET_BINDING_MISMATCH
    wrong_source = _freshness(
        observation,
        source_version="mock-shipment-source-version.p0.v1:sha256:" + "c" * 64,
    )
    assert wrong_source.reason_code is ShipmentFreshnessReason.SOURCE_VERSION_MISMATCH


def test_loaded_shipment_freshness_handles_missing_ambiguity_and_supersession() -> None:
    observation = _shipment_observation()

    missing = _freshness(observation, current_observations=())
    assert missing.decision is ShipmentFreshnessDecision.REFRESH_REQUIRED
    assert missing.reason_code is ShipmentFreshnessReason.NO_OBSERVATION

    with pytest.raises(ValueError, match="at most one"):
        _freshness(
            observation,
            current_observations=(observation, observation),
        )
    with pytest.raises(ValueError, match="superseded"):
        _freshness(
            observation,
            superseded_observation_refs=(observation.observation_id,),
        )
    with pytest.raises(ValueError, match="precede"):
        _freshness(
            observation,
            trusted_freshness_now=observation.observed_at - timedelta(microseconds=1),
        )


def test_shipment_supersession_is_append_only_same_owner_task_target() -> None:
    previous = _shipment_observation()
    current = _shipment_observation(
        private_owner_scope=previous.private_owner_scope,
        task_id=previous.task_id,
        verified_order_target_ref=previous.verified_order_target_ref,
        observed_at=previous.observed_at + timedelta(minutes=1),
        recorded_at=previous.recorded_at + timedelta(minutes=1),
        valid_until=previous.valid_until + timedelta(minutes=1),
        supersedes=previous.observation_id,
    )

    validate_shipment_observation_supersession(
        current=current,
        previous=previous,
    )

    wrong_owner = current.model_copy(update={"private_owner_scope": "owner:other"})
    with pytest.raises(ValueError, match="owner"):
        validate_shipment_observation_supersession(
            current=wrong_owner,
            previous=previous,
        )


def test_observation_models_reject_extra_private_or_business_fields() -> None:
    search = _search_observation()
    shipment = _shipment_observation()

    with pytest.raises(ValidationError, match="extra"):
        SearchOrdersObservation.model_validate(
            {**search.model_dump(), "customer_id": "must-not-copy"}
        )
    with pytest.raises(ValidationError, match="extra"):
        ShipmentObservation.model_validate(
            {**shipment.model_dump(), "order_number": "O-1001"}
        )
