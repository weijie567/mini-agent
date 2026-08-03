import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from mini_agent.core.common import ContractVisibility
from mini_agent.core.request_understanding import (
    InputAuthority,
    InputSourceKind,
    ReferenceSourceKindV2,
    TaskDeltaOperation,
    UncertaintyReasonCodeV2,
    UncertaintyV2,
)
from mini_agent.core.task_state import (
    AcceptedAddGoalTaskDeltaV3,
    AcceptedSupplyInputTaskDeltaV3,
    AcceptedTaskDeltaV2,
    CandidateRejectionReasonCode,
    CandidateValidationDecision,
    CandidateValidationRecordV2,
    DurableCycle2AddGoalTaskDeltaCandidateV3,
    DurableCycle2ContinuationTaskDeltaCandidateV3,
    DurableCycle2InputCandidateV3,
    DurableInputCandidateV2,
    DurablePhase1AddGoalTaskDeltaCandidateV3,
    DurableQueryContextualizationCandidateV2,
    DurableResolvedReferenceCandidateV2,
    DurableTaskDeltaCandidateV2,
    InputBinding,
    InputBindingV2,
    InputValidationStatus,
    RequestUnderstandingAggregateFailureCodeV2,
    RequestUnderstandingAtomicFailureCodeV2,
    RequestUnderstandingRecordV2,
    RequestUnderstandingRecordV3,
    RequestUnitRecord,
    TaskRecord,
    TaskStateTransition,
    TaskStatus,
    convert_input_binding_v1_to_v2,
)

NOW = datetime(2030, 1, 1, tzinfo=UTC)


def _binding(**overrides: object) -> InputBinding:
    values: dict[str, object] = {
        "binding_id": uuid4(),
        "name": "order_id",
        "normalized_value": "O-4242",
        "authority": InputAuthority.USER_CLAIM,
        "source_refs": (uuid4(),),
        "validation_status": InputValidationStatus.ACCEPTED,
        "confirmed_by_user": True,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return InputBinding.model_validate(values)


def _binding_v2(
    *,
    name: object = "order_id",
    normalized_value: object = "O-4242",
    **overrides: object,
) -> InputBindingV2:
    values: dict[str, object] = {
        "binding_id": uuid4(),
        "name": name,
        "normalized_value": normalized_value,
        "authority": InputAuthority.USER_CLAIM,
        "source_refs": (uuid4(),),
        "validation_status": InputValidationStatus.ACCEPTED,
        "confirmed_by_user": True,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return InputBindingV2.model_validate(values)


def test_input_binding_v1_shape_schema_and_dump_remain_compatible() -> None:
    binding_id = uuid4()
    source_ref = uuid4()
    supersedes = uuid4()
    updated_at = NOW + timedelta(seconds=1)
    binding = _binding(
        binding_id=binding_id,
        source_refs=(source_ref,),
        updated_at=updated_at,
        supersedes=supersedes,
    )

    assert tuple(InputBinding.model_fields) == (
        "binding_id",
        "name",
        "normalized_value",
        "authority",
        "source_refs",
        "validation_status",
        "confirmed_by_user",
        "created_at",
        "updated_at",
        "supersedes",
    )
    schema_bytes = json.dumps(
        InputBinding.model_json_schema(),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    assert hashlib.sha256(schema_bytes).hexdigest() == (
        "3625b69289512f6420b307a86e7a93b3b5c1f344a98f0e942f813890394de68d"
    )
    assert binding.model_dump() == {
        "binding_id": binding_id,
        "name": "order_id",
        "normalized_value": "O-4242",
        "authority": InputAuthority.USER_CLAIM,
        "source_refs": (source_ref,),
        "validation_status": InputValidationStatus.ACCEPTED,
        "confirmed_by_user": True,
        "created_at": NOW,
        "updated_at": updated_at,
        "supersedes": supersedes,
    }


@pytest.mark.parametrize(
    ("name", "normalized_value"),
    [
        ("order_id", "O-0000"),
        ("order_id", f"O-{'1' * 20}"),
        ("product_description", "red shoes"),
        ("candidate_ordinal", 1),
        ("candidate_ordinal", 5),
        ("candidate_ordinal", 99),
        ("shipment_not_received", False),
        ("shipment_not_received", True),
    ],
)
def test_input_binding_v2_accepts_only_the_closed_name_value_matrix(
    name: str,
    normalized_value: object,
) -> None:
    binding = _binding_v2(name=name, normalized_value=normalized_value)

    assert binding.name == name
    assert binding.normalized_value == normalized_value
    assert type(binding.normalized_value) is type(normalized_value)
    assert binding.authority is InputAuthority.USER_CLAIM
    assert binding.validation_status is InputValidationStatus.ACCEPTED
    assert binding.confirmed_by_user is True


@pytest.mark.parametrize(
    ("name", "normalized_value"),
    [
        ("order_id", "O-123"),
        ("order_id", f"O-{'1' * 21}"),
        ("order_id", "red shoes"),
        ("order_id", b"O-4242"),
        ("order_id", 1),
        ("order_id", True),
        ("product_description", " Red  Shoes "),
        ("product_description", ""),
        ("product_description", "鞋" * 81),
        ("product_description", "\ud800"),
        ("product_description", b"red shoes"),
        ("product_description", 1),
        ("product_description", False),
        ("candidate_ordinal", 0),
        ("candidate_ordinal", 100),
        ("candidate_ordinal", True),
        ("candidate_ordinal", "1"),
        ("candidate_ordinal", 1.0),
        ("shipment_not_received", 0),
        ("shipment_not_received", 1),
        ("shipment_not_received", "true"),
        ("shipment_not_received", 0.0),
    ],
)
def test_input_binding_v2_rejects_wrong_or_non_strict_name_value_pairs(
    name: str,
    normalized_value: object,
) -> None:
    with pytest.raises(ValidationError):
        _binding_v2(name=name, normalized_value=normalized_value)


def test_input_binding_v2_product_description_requires_exact_normalization() -> None:
    assert _binding_v2(
        name="product_description",
        normalized_value="strasse shoes",
    ).normalized_value == "strasse shoes"
    assert _binding_v2(
        name="product_description",
        normalized_value="鞋" * 80,
    ).normalized_value == "鞋" * 80

    with pytest.raises(ValidationError):
        _binding_v2(
            name="product_description",
            normalized_value="  STRAẞE   ＳＨＯＥＳ  ",
        )


def test_input_binding_v2_remains_claim_only_and_has_no_target_or_fact() -> None:
    assert tuple(InputBindingV2.model_fields) == tuple(InputBinding.model_fields)
    assert InputBindingV2.contract_visibility is ContractVisibility.AUDIT_ONLY
    forbidden_fields = {
        "business_fact",
        "customer_id",
        "observation_ref",
        "owner_customer_id",
        "verified_target_ref",
    }
    assert forbidden_fields.isdisjoint(InputBindingV2.model_fields)

    for field_name in forbidden_fields:
        with pytest.raises(ValidationError, match="extra"):
            _binding_v2(**{field_name: uuid4()})

    for field_name, value in (
        ("name", "not_received_claim"),
        ("authority", "BUSINESS_OBSERVATION"),
        ("validation_status", "PENDING"),
        ("confirmed_by_user", False),
        ("source_refs", ()),
    ):
        with pytest.raises(ValidationError):
            _binding_v2(**{field_name: value})


def test_input_binding_v2_preserves_time_and_supersession_invariants() -> None:
    supersedes = uuid4()
    binding = _binding_v2(
        updated_at=NOW + timedelta(seconds=1),
        supersedes=supersedes,
    )
    assert binding.supersedes == supersedes

    with pytest.raises(ValidationError, match="UTC"):
        _binding_v2(created_at=datetime(2030, 1, 1))
    with pytest.raises(ValidationError, match="precede"):
        _binding_v2(updated_at=NOW - timedelta(microseconds=1))


def test_input_binding_v1_to_v2_conversion_is_an_exact_order_id_copy() -> None:
    source = _binding(
        updated_at=NOW + timedelta(seconds=1),
        supersedes=uuid4(),
    )

    converted = convert_input_binding_v1_to_v2(source)

    assert type(converted) is InputBindingV2
    assert converted.name == "order_id"
    assert converted.model_dump() == source.model_dump()
    assert converted.binding_id == source.binding_id
    assert converted.source_refs == source.source_refs
    assert converted.supersedes == source.supersedes


def test_input_binding_v1_to_v2_conversion_rejects_non_exact_sources() -> None:
    source = _binding()

    class InputBindingSubclass(InputBinding):
        pass

    subclass = InputBindingSubclass.model_validate(source.model_dump())
    v2 = _binding_v2()
    malformed_v1 = InputBinding.model_construct(
        **{**source.model_dump(), "normalized_value": "4242"}
    )

    for value in (subclass, v2, source.model_dump(), object()):
        with pytest.raises(TypeError, match="exact InputBinding"):
            convert_input_binding_v1_to_v2(value)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        convert_input_binding_v1_to_v2(malformed_v1)


def test_input_binding_is_only_an_accepted_user_claim() -> None:
    binding = _binding()

    assert binding.authority is InputAuthority.USER_CLAIM
    assert binding.validation_status is InputValidationStatus.ACCEPTED
    assert "verified_target_ref" not in InputBinding.model_fields

    with pytest.raises(ValidationError):
        _binding(normalized_value="4242")

    with pytest.raises(ValidationError):
        _binding(authority="BUSINESS_OBSERVATION")

    with pytest.raises(ValidationError):
        _binding(confirmed_by_user=False)


def test_runtime_owner_scope_is_not_copied_into_request_unit() -> None:
    task_id = uuid4()
    binding_ref = uuid4()
    message_ref = uuid4()

    task = TaskRecord(
        task_id=task_id,
        owner_customer_id="customer-private",
        status=TaskStatus.ACTIVE,
        state_version=1,
        created_at=NOW,
        updated_at=NOW,
    )
    request_unit = RequestUnitRecord(
        request_unit_id=uuid4(),
        task_id=task_id,
        goal_text="查询当前订单状态",
        goal_source_refs=(message_ref,),
        input_binding_refs=(binding_ref,),
        status=TaskStatus.ACTIVE,
        state_version=1,
        created_at=NOW,
        updated_at=NOW,
    )

    assert task.contract_visibility is ContractVisibility.RUNTIME_PRIVATE
    assert "owner_customer_id" not in RequestUnitRecord.model_fields
    assert "customer_id" not in RequestUnitRecord.model_fields

    with pytest.raises(ValidationError, match="extra"):
        RequestUnitRecord.model_validate(
            {
                **request_unit.model_dump(),
                "customer_id": "attacker-selected",
            }
        )


def test_state_transition_requires_monotonic_version_increment() -> None:
    transition = TaskStateTransition(
        task_id=uuid4(),
        request_unit_id=uuid4(),
        from_status=TaskStatus.ACTIVE,
        to_status=TaskStatus.COMPLETED,
        base_state_version=1,
        result_state_version=2,
        reason_ref=uuid4(),
        changed_at=NOW,
    )
    assert transition.result_state_version == 2

    with pytest.raises(ValidationError, match="increment"):
        TaskStateTransition(
            task_id=uuid4(),
            request_unit_id=uuid4(),
            from_status=TaskStatus.ACTIVE,
            to_status=TaskStatus.BLOCKED,
            base_state_version=1,
            result_state_version=3,
            reason_ref=uuid4(),
            changed_at=NOW,
        )


def _durable_resolved_v2(
    *,
    source_ref: object | None = None,
    start: object = 3,
    end: object = 14,
    quote_hash: object = "a" * 64,
) -> DurableResolvedReferenceCandidateV2:
    return DurableResolvedReferenceCandidateV2(
        name="order_id",
        candidate_value="O-4242",
        source_kind=ReferenceSourceKindV2.CURRENT_MESSAGE,
        source_ref=source_ref or uuid4(),
        source_span_start=start,
        source_span_end_exclusive=end,
        source_quote_sha256=quote_hash,
        confidence=0.98,
    )


def _durable_input_v2(
    *,
    source_ref: object | None = None,
    start: object = 3,
    end: object = 14,
    quote_hash: object = "a" * 64,
) -> DurableInputCandidateV2:
    return DurableInputCandidateV2(
        name="order_id",
        candidate_value="O-4242",
        semantic_role="TARGET_RESOURCE_IDENTIFIER",
        authority=InputAuthority.USER_CLAIM,
        source_kind=InputSourceKind.CURRENT_MESSAGE,
        source_ref=source_ref or uuid4(),
        source_span_start=start,
        source_span_end_exclusive=end,
        source_quote_sha256=quote_hash,
        confidence=0.98,
    )


def _durable_context_v2(
    *,
    message_ref: object,
) -> DurableQueryContextualizationCandidateV2:
    return DurableQueryContextualizationCandidateV2(
        text="查询订单 O-4242 的当前状态",
        resolved_reference_candidates=(
            _durable_resolved_v2(source_ref=message_ref),
        ),
        uncertainties=(),
        source_message_refs=(message_ref,),
    )


def _durable_candidate_v2(
    *,
    candidate_id: object,
    message_ref: object,
) -> DurableTaskDeltaCandidateV2:
    return DurableTaskDeltaCandidateV2(
        candidate_id=candidate_id,
        operation=TaskDeltaOperation.ADD_GOAL,
        goal_patch="查询订单状态",
        input_candidates=(_durable_input_v2(source_ref=message_ref),),
        confidence=0.97,
    )


def test_v2_durable_provenance_leaf_fields_are_exact_and_quote_free() -> None:
    assert tuple(DurableResolvedReferenceCandidateV2.model_fields) == (
        "name",
        "candidate_value",
        "source_kind",
        "source_ref",
        "source_span_start",
        "source_span_end_exclusive",
        "source_quote_sha256",
        "confidence",
    )
    assert tuple(DurableInputCandidateV2.model_fields) == (
        "name",
        "candidate_value",
        "semantic_role",
        "authority",
        "source_kind",
        "source_ref",
        "source_span_start",
        "source_span_end_exclusive",
        "source_quote_sha256",
        "confidence",
    )
    assert "source_quote" not in DurableResolvedReferenceCandidateV2.model_fields
    assert "source_quote" not in DurableInputCandidateV2.model_fields

    leaf = _durable_resolved_v2()
    with pytest.raises(ValidationError, match="extra"):
        DurableResolvedReferenceCandidateV2.model_validate(
            {**leaf.model_dump(), "source_quote": "订单 O-4242"}
        )


@pytest.mark.parametrize(
    ("start", "end", "quote_hash"),
    [
        (-1, 2, "a" * 64),
        (2, 2, "a" * 64),
        (3, 2, "a" * 64),
        (True, 2, "a" * 64),
        (0, True, "a" * 64),
        (0, 2, "A" * 64),
        (0, 2, "a" * 63),
        (0, 2, b"a" * 64),
    ],
)
def test_v2_durable_provenance_rejects_invalid_span_or_hash(
    start: object,
    end: object,
    quote_hash: object,
) -> None:
    with pytest.raises(ValidationError):
        _durable_resolved_v2(
            start=start,
            end=end,
            quote_hash=quote_hash,
        )
    with pytest.raises(ValidationError):
        _durable_input_v2(
            start=start,
            end=end,
            quote_hash=quote_hash,
        )


def test_v2_failure_partitions_are_closed_and_ordered() -> None:
    assert [item.value for item in CandidateRejectionReasonCode] == [
        "OPERATION_NOT_SUPPORTED",
        "GOAL_PATCH_NOT_ACTIONABLE",
        "REQUIRED_INPUT_MISSING",
        "INPUT_VALUE_INVALID",
        "REFERENCE_UNRESOLVED",
        "REFERENCE_AMBIGUOUS",
        "NEXT_MOVE_INCONSISTENT",
    ]
    assert [
        item.value for item in RequestUnderstandingAggregateFailureCodeV2
    ] == [
        "MODEL_INPUT_SCHEMA_INVALID",
        "MODEL_OUTPUT_SCHEMA_INVALID",
        "MODEL_SCHEMA_VERSION_INVALID",
        "TRUSTED_OR_PRIVATE_FIELD_PRESENT",
        "SOURCE_PROVENANCE_INVALID",
    ]
    assert [
        item.value for item in RequestUnderstandingAtomicFailureCodeV2
    ] == [
        "TASK_STATE_CAS_CONFLICT",
        "TASK_COMMIT_FAILED",
        "DURABLE_CLOSURE_COMMIT_FAILED",
    ]
    assert (
        set(CandidateRejectionReasonCode)
        .isdisjoint(RequestUnderstandingAggregateFailureCodeV2)
    )
    assert (
        set(CandidateRejectionReasonCode)
        .isdisjoint(RequestUnderstandingAtomicFailureCodeV2)
    )


def test_v2_candidate_validation_uses_only_keyed_bounded_reasons() -> None:
    candidate_ref = uuid4()
    accepted = CandidateValidationRecordV2(
        candidate_ref=candidate_ref,
        decision=CandidateValidationDecision.ACCEPT,
        reason_code=None,
    )
    rejected = CandidateValidationRecordV2(
        candidate_ref=candidate_ref,
        decision=CandidateValidationDecision.REJECT,
        reason_code=CandidateRejectionReasonCode.INPUT_VALUE_INVALID,
    )
    assert accepted.reason_code is None
    assert (
        rejected.reason_code is CandidateRejectionReasonCode.INPUT_VALUE_INVALID
    )

    with pytest.raises(ValidationError, match="reason"):
        CandidateValidationRecordV2(
            candidate_ref=candidate_ref,
            decision=CandidateValidationDecision.REJECT,
            reason_code=None,
        )
    with pytest.raises(ValidationError, match="reason"):
        CandidateValidationRecordV2(
            candidate_ref=candidate_ref,
            decision=CandidateValidationDecision.ACCEPT,
            reason_code=CandidateRejectionReasonCode.INPUT_VALUE_INVALID,
        )
    with pytest.raises(ValidationError):
        CandidateValidationRecordV2(
            candidate_ref=candidate_ref,
            decision=CandidateValidationDecision.REJECT,
            reason_code="caller supplied detail",  # type: ignore[arg-type]
        )


def test_v2_accepted_delta_inlines_one_task_effect_and_trusted_time() -> None:
    assert tuple(AcceptedTaskDeltaV2.model_fields) == (
        "accepted_delta_id",
        "candidate_ref",
        "message_ref",
        "operation",
        "goal_text",
        "input_binding_refs",
        "accepted_at",
        "task_id",
        "base_task_state_version",
        "result_task_state_version",
    )
    accepted = AcceptedTaskDeltaV2(
        accepted_delta_id=uuid4(),
        candidate_ref=uuid4(),
        message_ref=uuid4(),
        operation=TaskDeltaOperation.ADD_GOAL,
        goal_text="查询订单状态",
        input_binding_refs=(uuid4(),),
        accepted_at=NOW,
        task_id=uuid4(),
        base_task_state_version=None,
        result_task_state_version=1,
    )
    assert accepted.base_task_state_version is None
    assert accepted.result_task_state_version == 1

    with pytest.raises(ValidationError):
        AcceptedTaskDeltaV2.model_validate(
            {**accepted.model_dump(), "base_task_state_version": 0}
        )
    with pytest.raises(ValidationError):
        AcceptedTaskDeltaV2.model_validate(
            {**accepted.model_dump(), "result_task_state_version": 0}
        )
    with pytest.raises(ValidationError, match="UTC"):
        AcceptedTaskDeltaV2.model_validate(
            {**accepted.model_dump(), "accepted_at": datetime(2030, 1, 1)}
        )


def test_v2_request_understanding_record_has_exact_versioned_parent_shape() -> None:
    assert tuple(RequestUnderstandingRecordV2.model_fields) == (
        "request_understanding_record_id",
        "run_id",
        "message_ref",
        "schema_version",
        "model_input_schema_version",
        "model_output_schema_version",
        "contextualization",
        "task_delta_candidates",
        "candidate_validation",
        "accepted_delta_refs",
        "proposed_base_task_state_version",
        "validated_task_state_version",
        "next_move_candidate_ref",
        "created_at",
    )
    message_ref = uuid4()
    candidate_ref = uuid4()
    accepted_delta_ref = uuid4()
    record = RequestUnderstandingRecordV2(
        request_understanding_record_id=uuid4(),
        run_id=uuid4(),
        message_ref=message_ref,
        schema_version="request_understanding_record.p0.v2",
        model_input_schema_version="e2e01-thin-v1",
        model_output_schema_version="e2e01-thin-v2",
        contextualization=_durable_context_v2(message_ref=message_ref),
        task_delta_candidates=(
            _durable_candidate_v2(
                candidate_id=candidate_ref,
                message_ref=message_ref,
            ),
        ),
        candidate_validation=(
            CandidateValidationRecordV2(
                candidate_ref=candidate_ref,
                decision=CandidateValidationDecision.ACCEPT,
                reason_code=None,
            ),
        ),
        accepted_delta_refs=(accepted_delta_ref,),
        proposed_base_task_state_version=None,
        validated_task_state_version=1,
        next_move_candidate_ref=uuid4(),
        created_at=NOW,
    )
    assert record.schema_version == "request_understanding_record.p0.v2"
    assert record.model_input_schema_version == "e2e01-thin-v1"
    assert record.model_output_schema_version == "e2e01-thin-v2"
    assert "accepted_task_deltas" not in RequestUnderstandingRecordV2.model_fields
    assert (
        "task_state_version_bindings"
        not in RequestUnderstandingRecordV2.model_fields
    )

    for field, value in (
        ("schema_version", "request_understanding_record.p0.v1"),
        ("model_input_schema_version", "e2e01-thin-v2"),
        ("model_output_schema_version", "e2e01-thin-v1"),
    ):
        with pytest.raises(ValidationError):
            RequestUnderstandingRecordV2.model_validate(
                {**record.model_dump(), field: value}
            )

    with pytest.raises(ValidationError, match="extra"):
        RequestUnderstandingRecordV2.model_validate(
            {**record.model_dump(), "customer_id": "attacker-selected"}
        )
    with pytest.raises(ValidationError, match="next_move"):
        RequestUnderstandingRecordV2.model_validate(
            {
                **record.model_dump(),
                "next_move_candidate_ref": None,
                "validated_task_state_version": 1,
            }
        )


def test_v3_request_understanding_models_have_exact_breaking_shapes() -> None:
    assert tuple(RequestUnderstandingRecordV3.model_fields) == (
        "request_understanding_record_id",
        "run_id",
        "message_ref",
        "record_schema_version",
        "model_input_schema_version",
        "model_output_schema_version",
        "contextualization",
        "task_delta_candidates",
        "candidate_validation",
        "accepted_delta_refs",
        "proposed_base_task_state_version",
        "validated_task_state_version",
        "next_move_candidate_ref",
        "created_at",
    )
    assert "schema_version" not in RequestUnderstandingRecordV3.model_fields
    assert tuple(AcceptedAddGoalTaskDeltaV3.model_fields) == (
        "accepted_delta_id",
        "candidate_ref",
        "message_ref",
        "operation",
        "goal_text",
        "input_binding_refs",
        "accepted_at",
        "task_id",
        "base_task_state_version",
        "result_task_state_version",
    )
    assert tuple(AcceptedSupplyInputTaskDeltaV3.model_fields) == (
        "accepted_delta_id",
        "candidate_ref",
        "message_ref",
        "operation",
        "task_id",
        "target_request_unit_id",
        "input_binding_refs",
        "accepted_at",
        "base_task_state_version",
        "result_task_state_version",
    )

    message_ref = uuid4()
    candidate_ref = uuid4()
    durable_input = DurableCycle2InputCandidateV3(
        name="shipment_not_received",
        normalized_candidate_value=True,
        authority=InputAuthority.USER_CLAIM,
        source_kind=InputSourceKind.CURRENT_MESSAGE,
        source_ref=message_ref,
        source_span_start=8,
        source_span_end_exclusive=12,
        source_quote_sha256="a" * 64,
        confidence=0.99,
    )
    candidate = DurableCycle2ContinuationTaskDeltaCandidateV3(
        candidate_id=candidate_ref,
        operation=TaskDeltaOperation.SUPPLY_INPUT,
        target_task_alias="task-1",
        target_request_unit_alias="unit-1",
        input_candidates=(durable_input,),
        confidence=0.98,
    )
    record = RequestUnderstandingRecordV3(
        request_understanding_record_id=uuid4(),
        run_id=uuid4(),
        message_ref=message_ref,
        record_schema_version="request_understanding_record.p0.v3",
        model_input_schema_version="e2e01-thin-v1",
        model_output_schema_version="e2e01-cycle2-continuation.p0.v2",
        contextualization=_durable_context_v2(message_ref=message_ref),
        task_delta_candidates=(candidate,),
        candidate_validation=(
            CandidateValidationRecordV2(
                candidate_ref=candidate_ref,
                decision=CandidateValidationDecision.REJECT,
                reason_code=CandidateRejectionReasonCode.INPUT_VALUE_INVALID,
            ),
        ),
        accepted_delta_refs=(),
        created_at=NOW,
    )
    assert '"source_quote":' not in record.model_dump_json()

    phase1 = DurablePhase1AddGoalTaskDeltaCandidateV3(
        candidate_id=candidate_ref,
        operation=TaskDeltaOperation.ADD_GOAL,
        goal_patch="查询订单状态",
        input_candidates=(
            _durable_candidate_v2(
                candidate_id=candidate_ref,
                message_ref=message_ref,
            ).input_candidates[0],
        ),
        confidence=0.98,
    )
    with pytest.raises(ValidationError, match="continuation"):
        RequestUnderstandingRecordV3.model_validate(
            {**record.model_dump(), "task_delta_candidates": (phase1,)}
        )

    product_input = DurableCycle2InputCandidateV3(
        name="product_description",
        normalized_candidate_value="轻量 跑鞋",
        authority=InputAuthority.USER_CLAIM,
        source_kind=InputSourceKind.CURRENT_MESSAGE,
        source_ref=message_ref,
        source_span_start=2,
        source_span_end_exclusive=7,
        source_quote_sha256="b" * 64,
        confidence=0.99,
    )
    initial_candidate = DurableCycle2AddGoalTaskDeltaCandidateV3(
        candidate_id=candidate_ref,
        operation=TaskDeltaOperation.ADD_GOAL,
        goal_patch="查找轻量跑鞋订单",
        input_candidates=(product_input,),
        confidence=0.98,
    )
    initial_delta_ref = uuid4()
    initial_record = RequestUnderstandingRecordV3(
        request_understanding_record_id=uuid4(),
        run_id=uuid4(),
        message_ref=message_ref,
        record_schema_version="request_understanding_record.p0.v3",
        model_input_schema_version="e2e01-thin-v1",
        model_output_schema_version="e2e01-cycle2-initial.p0.v1",
        contextualization=_durable_context_v2(message_ref=message_ref),
        task_delta_candidates=(initial_candidate,),
        candidate_validation=(
            CandidateValidationRecordV2(
                candidate_ref=candidate_ref,
                decision=CandidateValidationDecision.ACCEPT,
            ),
        ),
        accepted_delta_refs=(initial_delta_ref,),
        proposed_base_task_state_version=None,
        validated_task_state_version=1,
        next_move_candidate_ref=uuid4(),
        created_at=NOW,
    )
    assert initial_record.model_output_schema_version == (
        "e2e01-cycle2-initial.p0.v1"
    )

    with pytest.raises(ValidationError, match="accepted Candidate"):
        RequestUnderstandingRecordV3.model_validate(
            {
                **initial_record.model_dump(),
                "candidate_validation": (
                    CandidateValidationRecordV2(
                        candidate_ref=candidate_ref,
                        decision=CandidateValidationDecision.REJECT,
                        reason_code=CandidateRejectionReasonCode.INPUT_VALUE_INVALID,
                    ),
                ),
                "accepted_delta_refs": (),
            }
        )
    with pytest.raises(ValidationError, match="Phase 1"):
        RequestUnderstandingRecordV3.model_validate(
            {
                **initial_record.model_dump(),
                "model_output_schema_version": "e2e01-thin-v2",
            }
        )
    with pytest.raises(ValidationError, match="continuation"):
        RequestUnderstandingRecordV3.model_validate(
            {
                **initial_record.model_dump(),
                "model_output_schema_version": (
                    "e2e01-cycle2-continuation.p0.v2"
                ),
                "proposed_base_task_state_version": None,
                "validated_task_state_version": None,
                "next_move_candidate_ref": None,
            }
        )
