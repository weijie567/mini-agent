from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from mini_agent.core.common import ContractVisibility
from mini_agent.core.identity import CustomerContext, RuntimePrivateContext
from mini_agent.core.presentation import PresentationInput, PresentationPlan
from mini_agent.core.request_understanding import (
    RequestUnderstandingInput,
    RequestUnderstandingOutput,
)
from mini_agent.core.tool_system import ToolSpec


def test_customer_context_is_runtime_private_and_requires_utc() -> None:
    context = CustomerContext(
        subject_ref="subject-safe-ref",
        customer_id="customer-private",
        auth_scopes=frozenset({"orders:read"}),
        authenticated_at=datetime(2030, 1, 1, tzinfo=UTC),
        session_ref_hash="sha256:opaque-session-ref",
    )

    assert context.contract_visibility is ContractVisibility.RUNTIME_PRIVATE
    assert RuntimePrivateContext(
        run_id=uuid4(), customer_context=context
    ).customer_context is context

    with pytest.raises(ValidationError, match="UTC"):
        CustomerContext(
            subject_ref="subject-safe-ref",
            customer_id="customer-private",
            auth_scopes=frozenset({"orders:read"}),
            authenticated_at=datetime(2030, 1, 1),
            session_ref_hash="sha256:opaque-session-ref",
        )

    with pytest.raises(ValidationError, match="UTC"):
        CustomerContext(
            subject_ref="subject-safe-ref",
            customer_id="customer-private",
            auth_scopes=frozenset({"orders:read"}),
            authenticated_at=datetime(
                2030, 1, 1, tzinfo=timezone(timedelta(hours=8))
            ),
            session_ref_hash="sha256:opaque-session-ref",
        )


def test_model_visible_contract_schemas_do_not_expose_identity_fields() -> None:
    forbidden = {
        "auth_scope",
        "auth_scopes",
        "authorization_scope",
        "customer_id",
        "owner_customer_id",
        "session_id",
        "session_ref_hash",
        "subject_ref",
        "trusted_context_ref",
    }
    model_visible_contracts = (
        RequestUnderstandingInput,
        RequestUnderstandingOutput,
        ToolSpec,
        PresentationInput,
        PresentationPlan,
    )

    for contract in model_visible_contracts:
        schema_text = str(contract.model_json_schema())
        for field_name in forbidden:
            assert field_name not in schema_text
