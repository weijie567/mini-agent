from datetime import UTC, datetime
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
    AcceptedTaskDeltaV2,
    CandidateRejectionReasonCode,
    CandidateValidationDecision,
    CandidateValidationRecordV2,
    DurableInputCandidateV2,
    DurableQueryContextualizationCandidateV2,
    DurableResolvedReferenceCandidateV2,
    DurableTaskDeltaCandidateV2,
    InputBinding,
    InputValidationStatus,
    RequestUnderstandingAggregateFailureCodeV2,
    RequestUnderstandingAtomicFailureCodeV2,
    RequestUnderstandingRecordV2,
    RequestUnitRecord,
    TaskRecord,
    TaskStateTransition,
    TaskStatus,
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
