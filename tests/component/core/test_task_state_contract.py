from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from mini_agent.core.common import ContractVisibility
from mini_agent.core.request_understanding import InputAuthority
from mini_agent.core.task_state import (
    InputBinding,
    InputValidationStatus,
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
