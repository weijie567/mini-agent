"""Shared primitives for Core-owned contract models."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
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


class FrozenJsonDict(tuple[tuple[str, Any], ...], Mapping[str, Any]):
    """Tuple-backed JSON object with no mutable-builtin storage alias."""

    __slots__ = ()

    def __new__(
        cls,
        value: Mapping[str, Any] | Iterable[tuple[str, Any]],
    ) -> FrozenJsonDict:
        items = value.items() if isinstance(value, Mapping) else value
        return tuple.__new__(cls, tuple(items))

    def __getitem__(self, key: str) -> Any:
        for item_key, item_value in tuple.__iter__(self):
            if item_key == key:
                return item_value
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        return (key for key, _ in tuple.__iter__(self))

    def __contains__(self, key: object) -> bool:
        return any(item_key == key for item_key, _ in tuple.__iter__(self))

    def __repr__(self) -> str:
        return f"{type(self).__name__}({dict(self.items())!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Mapping):
            return False
        return dict(self.items()) == dict(other.items())

    __hash__ = None

    def __deepcopy__(self, _memo: dict[int, Any]) -> FrozenJsonDict:
        return self


class FrozenJsonList(tuple[Any, ...]):
    """Tuple-backed JSON array with no mutable-builtin storage alias."""

    __slots__ = ()

    def __new__(cls, value: Iterable[Any]) -> FrozenJsonList:
        return tuple.__new__(cls, tuple(value))

    def __repr__(self) -> str:
        return f"{type(self).__name__}({list(self)!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Sequence) or isinstance(
            other, (str, bytes, bytearray)
        ):
            return False
        return tuple.__eq__(self, tuple(other))

    __hash__ = None

    def __deepcopy__(self, _memo: dict[int, Any]) -> FrozenJsonList:
        return self


def freeze_json_value(value: Any) -> Any:
    """Recursively copy JSON into tuple-backed Mapping/Sequence values."""

    if isinstance(value, (FrozenJsonDict, FrozenJsonList)):
        return value
    if isinstance(value, Mapping):
        return FrozenJsonDict(
            (key, freeze_json_value(nested)) for key, nested in value.items()
        )
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        return FrozenJsonList(freeze_json_value(item) for item in value)
    return value


def thaw_json_value(value: Any) -> Any:
    """Project immutable JSON containers back to native serialization values."""

    if isinstance(value, Mapping):
        return {
            key: thaw_json_value(nested)
            for key, nested in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        return [thaw_json_value(item) for item in value]
    return value


def find_trusted_argument_field(value: Any) -> str | None:
    """Return the first Runtime-private field found in model-proposed JSON."""

    if isinstance(value, Mapping):
        for key, nested_value in value.items():
            normalized_key = str(key).casefold()
            if normalized_key in TRUSTED_ARGUMENT_FIELDS:
                return normalized_key
            found = find_trusted_argument_field(nested_value)
            if found is not None:
                return found
    elif isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
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
