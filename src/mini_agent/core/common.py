"""Shared primitives for Core-owned contract models."""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict


class ContractVisibility(StrEnum):
    """Where a contract may be projected."""

    MODEL_VISIBLE = "MODEL_VISIBLE"
    RUNTIME_PRIVATE = "RUNTIME_PRIVATE"
    AUDIT_ONLY = "AUDIT_ONLY"
    USER_VISIBLE = "USER_VISIBLE"


class ContractModel(BaseModel):
    """Strict, immutable base for deterministic boundary objects."""

    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)


class ModelVisibleModel(ContractModel):
    """Marker base for data that may cross the model boundary."""

    contract_visibility: ClassVar[ContractVisibility] = (
        ContractVisibility.MODEL_VISIBLE
    )


class RuntimePrivateModel(ContractModel):
    """Marker base for data that must remain inside the trusted runtime."""

    contract_visibility: ClassVar[ContractVisibility] = (
        ContractVisibility.RUNTIME_PRIVATE
    )


class AuditOnlyModel(ContractModel):
    """Marker base for records used by replay, audit, or Eval only."""

    contract_visibility: ClassVar[ContractVisibility] = ContractVisibility.AUDIT_ONLY


class UserVisibleModel(ContractModel):
    """Marker base for an approved outward-facing projection."""

    contract_visibility: ClassVar[ContractVisibility] = ContractVisibility.USER_VISIBLE


TRUSTED_ARGUMENT_FIELDS = frozenset(
    {
        "auth_scope",
        "auth_scopes",
        "authorization_scope",
        "customer_id",
        "idempotency_key",
        "owner_customer_id",
        "run_id",
        "session_id",
        "session_ref_hash",
        "subject_ref",
        "trusted_context_ref",
    }
)


class FrozenJsonDict(dict[str, Any]):
    """JSON object that cannot be mutated after boundary validation."""

    def _reject_mutation(self, *_args: Any, **_kwargs: Any) -> None:
        raise TypeError("validated JSON is immutable")

    __setitem__ = _reject_mutation
    __delitem__ = _reject_mutation
    clear = _reject_mutation
    pop = _reject_mutation
    popitem = _reject_mutation
    setdefault = _reject_mutation
    update = _reject_mutation

    def __deepcopy__(self, _memo: dict[int, Any]) -> FrozenJsonDict:
        return self


class FrozenJsonList(list[Any]):
    """JSON array that cannot be mutated after boundary validation."""

    def _reject_mutation(self, *_args: Any, **_kwargs: Any) -> None:
        raise TypeError("validated JSON is immutable")

    __setitem__ = _reject_mutation
    __delitem__ = _reject_mutation
    __iadd__ = _reject_mutation
    __imul__ = _reject_mutation
    append = _reject_mutation
    clear = _reject_mutation
    extend = _reject_mutation
    insert = _reject_mutation
    pop = _reject_mutation
    remove = _reject_mutation
    reverse = _reject_mutation
    sort = _reject_mutation

    def __deepcopy__(self, _memo: dict[int, Any]) -> FrozenJsonList:
        return self


def freeze_json_value(value: Any) -> Any:
    """Recursively copy JSON into mutation-rejecting dict/list subclasses."""

    if isinstance(value, dict):
        return FrozenJsonDict(
            {key: freeze_json_value(nested) for key, nested in value.items()}
        )
    if isinstance(value, list):
        return FrozenJsonList(freeze_json_value(item) for item in value)
    return value


def find_trusted_argument_field(value: Any) -> str | None:
    """Return the first Runtime-private field found in model-proposed JSON."""

    if isinstance(value, dict):
        for key, nested_value in value.items():
            normalized_key = str(key).casefold()
            if normalized_key in TRUSTED_ARGUMENT_FIELDS:
                return normalized_key
            found = find_trusted_argument_field(nested_value)
            if found is not None:
                return found
    elif isinstance(value, (list, tuple)):
        for item in value:
            found = find_trusted_argument_field(item)
            if found is not None:
                return found
    return None


def require_utc(value: datetime, *, field_name: str) -> datetime:
    """Reject naive or non-UTC timestamps instead of silently normalizing them."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware UTC")
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{field_name} must use UTC offset +00:00")
    return value
