"""Cycle 2 owner-scoped order-search business contracts.

Model-visible projections are deliberately distinct from Runtime-private query,
candidate, result, and authority metadata.  The pure helpers in this module do
not grant authority; trusted identity and source-version production remain at
the controlled business boundary.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Iterable, Sequence
from datetime import date, datetime, timedelta
from enum import StrEnum
from typing import Annotated, Literal, Self, cast

from pydantic import Field, field_validator, model_validator

from .common import ModelVisibleModel, RuntimePrivateModel, require_utc
from .order import OrderStatus

ORDER_SEARCH_MATCHING_RULE_VERSION = "order-search-matching.p0.v1"
ORDER_SEARCH_WINDOW = timedelta(days=90)
ORDER_SEARCH_MAX_CANDIDATES = 5
ORDER_SEARCH_MAX_MATCHING_ITEMS = 3

_ORDER_ID_PATTERN = re.compile(r"^O-[0-9]{4,20}$")
_CANDIDATE_SOURCE_SCHEMA = "mock-order-search-candidate-source-version.p0.v1"
_SNAPSHOT_SOURCE_SCHEMA = "mock-order-search-snapshot-source-version.p0.v1"

StrictNonEmptyString = Annotated[str, Field(strict=True, min_length=1)]
OrderId = Annotated[str, Field(strict=True, pattern=r"^O-[0-9]{4,20}$")]
StrictPositiveInt = Annotated[int, Field(strict=True, ge=1)]
OrderCandidateSourceVersion = Annotated[
    str,
    Field(
        strict=True,
        pattern=(
            r"^mock-order-search-candidate-source-version\.p0\.v1:sha256:"
            r"[0-9a-f]{64}$"
        ),
    ),
]
OrderSearchSnapshotSourceVersion = Annotated[
    str,
    Field(
        strict=True,
        pattern=(
            r"^mock-order-search-snapshot-source-version\.p0\.v1:sha256:"
            r"[0-9a-f]{64}$"
        ),
    ),
]


def _require_unicode_scalars(value: str, *, field_name: str) -> None:
    if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
        raise ValueError(f"{field_name} must contain only Unicode scalar values")


def _normalize_search_text(value: str, *, field_name: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{field_name} must be a string")
    _require_unicode_scalars(value, field_name=field_name)
    normalized = unicodedata.normalize("NFKC", value)
    normalized = " ".join(normalized.split()).casefold()
    _require_unicode_scalars(normalized, field_name=field_name)
    if not normalized:
        raise ValueError(f"{field_name} is empty after normalization")
    return normalized


def normalize_product_description(value: str) -> str:
    """Return the exact P0 NFKC/whitespace/casefold query representation."""

    normalized = _normalize_search_text(value, field_name="product_description")
    if len(normalized) > 80:
        raise ValueError(
            "product_description must contain at most 80 Unicode scalars after "
            "normalization"
        )
    return normalized


def normalize_search_aliases(aliases: Iterable[str]) -> tuple[str, ...]:
    """Normalize, deduplicate, and sort controlled source aliases."""

    if isinstance(aliases, (str, bytes, bytearray)):
        raise TypeError("search_aliases must be an iterable of strings")
    return tuple(
        sorted(
            {
                _normalize_search_text(alias, field_name="search_alias")
                for alias in aliases
            }
        )
    )


class SearchOrdersInput(ModelVisibleModel):
    """The only model-proposable order-search field."""

    product_description: Annotated[str, Field(strict=True, min_length=1, max_length=80)]

    @field_validator("product_description")
    @classmethod
    def normalized_value_must_be_bounded(cls, value: str) -> str:
        normalize_product_description(value)
        return value


class SearchOrdersQuery(RuntimePrivateModel):
    """Trusted owner/window inputs passed to the business read Port."""

    customer_id: StrictNonEmptyString
    product_description: Annotated[str, Field(strict=True, min_length=1, max_length=80)]
    ordered_at_from: datetime
    ordered_at_to: datetime
    max_candidates: Literal[5] = ORDER_SEARCH_MAX_CANDIDATES
    matching_rule_version: Literal["order-search-matching.p0.v1"] = (
        ORDER_SEARCH_MATCHING_RULE_VERSION
    )

    @field_validator("max_candidates", mode="before")
    @classmethod
    def max_candidates_is_strict_five(cls, value: object) -> object:
        if type(value) is not int or value != ORDER_SEARCH_MAX_CANDIDATES:
            raise ValueError("max_candidates must be the strict integer 5")
        return value

    @field_validator("ordered_at_from", "ordered_at_to")
    @classmethod
    def query_timestamps_are_utc(cls, value: datetime) -> datetime:
        return require_utc(value, field_name="SearchOrdersQuery timestamp")

    @field_validator("product_description")
    @classmethod
    def query_is_exact_normalized_binding(cls, value: str) -> str:
        if normalize_product_description(value) != value:
            raise ValueError("product_description must be the exact normalized binding")
        return value

    @model_validator(mode="after")
    def query_uses_exact_closed_window(self) -> Self:
        if self.ordered_at_to - self.ordered_at_from != ORDER_SEARCH_WINDOW:
            raise ValueError("search window must be exactly 90 days")
        return self


def build_search_orders_query(
    *,
    customer_id: str,
    product_description: str,
    trusted_now: datetime,
) -> SearchOrdersQuery:
    """Build the closed 90-day query from one trusted UTC clock sample."""

    trusted_now = require_utc(trusted_now, field_name="trusted_now")
    return SearchOrdersQuery(
        customer_id=customer_id,
        product_description=normalize_product_description(product_description),
        ordered_at_from=trusted_now - ORDER_SEARCH_WINDOW,
        ordered_at_to=trusted_now,
    )


def order_is_within_search_window(
    ordered_at: datetime,
    *,
    query: SearchOrdersQuery,
) -> bool:
    """Apply the exact closed owner-query time window to a source timestamp."""

    ordered_at = require_utc(ordered_at, field_name="ordered_at")
    return query.ordered_at_from <= ordered_at <= query.ordered_at_to


class OrderSearchLine(RuntimePrivateModel):
    """One controlled owner-scoped source line before matching."""

    line_ordinal: StrictPositiveInt
    product_name: StrictNonEmptyString
    quantity: StrictPositiveInt
    product_category: StrictNonEmptyString
    search_aliases: tuple[StrictNonEmptyString, ...] = ()

    @model_validator(mode="after")
    def source_text_is_normalizable(self) -> Self:
        _normalize_search_text(self.product_name, field_name="product_name")
        _normalize_search_text(self.product_category, field_name="product_category")
        normalize_search_aliases(self.search_aliases)
        return self


class MatchedOrderLine(RuntimePrivateModel):
    """Canonical matched source facts retained in a private candidate."""

    line_ordinal: StrictPositiveInt
    product_name: StrictNonEmptyString
    quantity: StrictPositiveInt
    product_category: StrictNonEmptyString
    normalized_search_aliases: tuple[StrictNonEmptyString, ...] = ()

    @model_validator(mode="after")
    def aliases_are_exact_canonical_order(self) -> Self:
        canonical = normalize_search_aliases(self.normalized_search_aliases)
        if self.normalized_search_aliases != canonical:
            raise ValueError(
                "normalized_search_aliases must be sorted unique normalized values"
            )
        _normalize_search_text(self.product_name, field_name="product_name")
        _normalize_search_text(self.product_category, field_name="product_category")
        return self


def match_order_lines(
    product_description: str,
    lines: Iterable[OrderSearchLine],
) -> tuple[MatchedOrderLine, ...]:
    """Apply exact P0 matching and return source ``line_ordinal`` order."""

    normalized_query = normalize_product_description(product_description)
    source_lines = tuple(lines)
    ordinals = tuple(line.line_ordinal for line in source_lines)
    if len(set(ordinals)) != len(ordinals):
        raise ValueError("source line_ordinal values must be unique")

    matched: list[MatchedOrderLine] = []
    for line in source_lines:
        normalized_name = _normalize_search_text(
            line.product_name,
            field_name="product_name",
        )
        normalized_category = _normalize_search_text(
            line.product_category,
            field_name="product_category",
        )
        normalized_aliases = normalize_search_aliases(line.search_aliases)
        is_match = (
            normalized_query in normalized_name
            or normalized_query == normalized_category
            or normalized_query in normalized_aliases
        )
        if is_match:
            matched.append(
                MatchedOrderLine(
                    line_ordinal=line.line_ordinal,
                    product_name=line.product_name,
                    quantity=line.quantity,
                    product_category=line.product_category,
                    normalized_search_aliases=normalized_aliases,
                )
            )
    return tuple(sorted(matched, key=lambda line: line.line_ordinal))


class OrderCandidateMatchingItem(ModelVisibleModel):
    product_name: StrictNonEmptyString
    quantity: StrictPositiveInt


class OrderCandidatePublicSummary(ModelVisibleModel):
    """Safe candidate facts before Runtime assigns a selection ordinal."""

    order_number: OrderId
    ordered_on_utc: date
    status: OrderStatus
    matching_items: Annotated[
        tuple[OrderCandidateMatchingItem, ...],
        Field(min_length=1, max_length=ORDER_SEARCH_MAX_MATCHING_ITEMS),
    ]


def _validate_matched_line_order(lines: Sequence[MatchedOrderLine]) -> None:
    ordinals = tuple(line.line_ordinal for line in lines)
    if not ordinals:
        raise ValueError("matched_lines must not be empty")
    if ordinals != tuple(sorted(ordinals)) or len(set(ordinals)) != len(ordinals):
        raise ValueError("matched_lines must use unique line_ordinal ASC order")


def build_order_candidate_public_summary(
    *,
    order_number: str,
    ordered_at: datetime,
    status: OrderStatus,
    matched_lines: Sequence[MatchedOrderLine],
) -> OrderCandidatePublicSummary:
    """Project only the first three matching source lines."""

    ordered_at = require_utc(ordered_at, field_name="ordered_at")
    _validate_matched_line_order(matched_lines)
    return OrderCandidatePublicSummary(
        order_number=order_number,
        ordered_on_utc=ordered_at.date(),
        status=status,
        matching_items=tuple(
            OrderCandidateMatchingItem(
                product_name=line.product_name,
                quantity=line.quantity,
            )
            for line in matched_lines[:ORDER_SEARCH_MAX_MATCHING_ITEMS]
        ),
    )


class OrderCandidate(RuntimePrivateModel):
    owner_scoped_order_ref: StrictNonEmptyString
    order_number: OrderId
    ordered_at: datetime
    status: OrderStatus
    matched_lines: Annotated[tuple[MatchedOrderLine, ...], Field(min_length=1)]
    public_summary: OrderCandidatePublicSummary
    candidate_source_version: OrderCandidateSourceVersion

    @field_validator("ordered_at")
    @classmethod
    def ordered_at_is_utc(cls, value: datetime) -> datetime:
        return require_utc(value, field_name="OrderCandidate.ordered_at")

    @model_validator(mode="after")
    def candidate_projection_is_exact(self) -> Self:
        _validate_matched_line_order(self.matched_lines)
        expected = build_order_candidate_public_summary(
            order_number=self.order_number,
            ordered_at=self.ordered_at,
            status=self.status,
            matched_lines=self.matched_lines,
        )
        if self.public_summary != expected:
            raise ValueError("public_summary must be the exact safe candidate projection")
        return self


def sort_order_candidates(
    candidates: Iterable[OrderCandidate],
) -> tuple[OrderCandidate, ...]:
    """Sort by ``ordered_at DESC, order_number ASC`` without relevance scoring."""

    ordered = sorted(candidates, key=lambda candidate: candidate.order_number)
    ordered.sort(key=lambda candidate: candidate.ordered_at, reverse=True)
    return tuple(ordered)


class SearchOrdersOutcome(StrEnum):
    UNIQUE = "UNIQUE"
    MULTIPLE = "MULTIPLE"
    NO_MATCH = "NO_MATCH"
    SYSTEM_FAILURE = "SYSTEM_FAILURE"


class SearchOrdersAgentOutcome(StrEnum):
    UNIQUE = "UNIQUE"
    MULTIPLE = "MULTIPLE"


class OrderSearchFailureCode(StrEnum):
    ORDER_SEARCH_TRANSIENT = "ORDER_SEARCH_TRANSIENT"
    ORDER_SEARCH_UNAVAILABLE = "ORDER_SEARCH_UNAVAILABLE"
    ORDER_SEARCH_SOURCE_INTEGRITY = "ORDER_SEARCH_SOURCE_INTEGRITY"


class SearchOrdersResult(RuntimePrivateModel):
    outcome: SearchOrdersOutcome
    candidates: Annotated[
        tuple[OrderCandidate, ...],
        Field(max_length=ORDER_SEARCH_MAX_CANDIDATES),
    ] = ()
    truncated: Annotated[bool, Field(strict=True)] = False
    snapshot_resource_ref: StrictNonEmptyString | None = None
    snapshot_source_version: OrderSearchSnapshotSourceVersion | None = None
    observed_at: datetime | None = None
    failure_code: OrderSearchFailureCode | None = None

    @field_validator("observed_at")
    @classmethod
    def observed_at_is_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return require_utc(value, field_name="SearchOrdersResult.observed_at")

    @model_validator(mode="after")
    def result_shape_matches_closed_outcome_matrix(self) -> Self:
        authority = (
            self.snapshot_resource_ref,
            self.snapshot_source_version,
            self.observed_at,
        )
        authority_complete = all(value is not None for value in authority)
        authority_absent = all(value is None for value in authority)
        count = len(self.candidates)

        if self.outcome is SearchOrdersOutcome.UNIQUE:
            if count != 1 or self.truncated:
                raise ValueError("UNIQUE requires one candidate and truncated=false")
            if not authority_complete:
                raise ValueError("UNIQUE requires complete snapshot authority metadata")
            if self.failure_code is not None:
                raise ValueError("UNIQUE cannot carry failure_code")
        elif self.outcome is SearchOrdersOutcome.MULTIPLE:
            if not 2 <= count <= ORDER_SEARCH_MAX_CANDIDATES:
                raise ValueError("MULTIPLE requires two to five candidates")
            if not authority_complete:
                raise ValueError("MULTIPLE requires complete snapshot authority metadata")
            if self.failure_code is not None:
                raise ValueError("MULTIPLE cannot carry failure_code")
        elif self.outcome is SearchOrdersOutcome.NO_MATCH:
            if count or self.truncated or not authority_absent:
                raise ValueError(
                    "NO_MATCH cannot carry candidates, truncation, or authority metadata"
                )
            if self.failure_code is not None:
                raise ValueError("NO_MATCH cannot carry failure_code")
        else:
            if count or self.truncated or not authority_absent:
                raise ValueError(
                    "SYSTEM_FAILURE cannot carry candidates, truncation, or authority "
                    "metadata"
                )
            if self.failure_code is None:
                raise ValueError("SYSTEM_FAILURE requires an allowlisted failure_code")

        if count:
            refs = tuple(candidate.owner_scoped_order_ref for candidate in self.candidates)
            numbers = tuple(candidate.order_number for candidate in self.candidates)
            if len(set(refs)) != count or len(set(numbers)) != count:
                raise ValueError("candidate identities must be unique")
            if self.candidates != sort_order_candidates(self.candidates):
                raise ValueError(
                    "candidates must use stable ordered_at DESC, order_number ASC order"
                )
        return self


class SearchOrdersAgentCandidate(ModelVisibleModel):
    ordinal: Annotated[int, Field(strict=True, ge=1, le=ORDER_SEARCH_MAX_CANDIDATES)]
    order_number: OrderId
    ordered_on_utc: date
    status: OrderStatus
    matching_items: Annotated[
        tuple[OrderCandidateMatchingItem, ...],
        Field(min_length=1, max_length=ORDER_SEARCH_MAX_MATCHING_ITEMS),
    ]


class SearchOrdersAgentOutput(ModelVisibleModel):
    outcome: SearchOrdersAgentOutcome
    candidates: Annotated[
        tuple[SearchOrdersAgentCandidate, ...],
        Field(min_length=1, max_length=ORDER_SEARCH_MAX_CANDIDATES),
    ]
    truncated: Annotated[bool, Field(strict=True)]

    @model_validator(mode="after")
    def output_contains_only_success_shapes(self) -> Self:
        ordinals = tuple(candidate.ordinal for candidate in self.candidates)
        if ordinals != tuple(range(1, len(self.candidates) + 1)):
            raise ValueError("candidate ordinals must be contiguous from one")
        if self.outcome is SearchOrdersAgentOutcome.UNIQUE:
            if len(self.candidates) != 1 or self.truncated:
                raise ValueError("UNIQUE Agent output requires one untruncated candidate")
        elif self.outcome is SearchOrdersAgentOutcome.MULTIPLE:
            if len(self.candidates) < 2:
                raise ValueError("MULTIPLE Agent output requires at least two candidates")
        else:
            raise ValueError("only successful outcomes have Agent-visible output")
        return self


def project_search_orders_agent_output(
    result: SearchOrdersResult,
) -> SearchOrdersAgentOutput:
    """Explicitly copy the safe whitelist from a successful private result."""

    if result.outcome not in {
        SearchOrdersOutcome.UNIQUE,
        SearchOrdersOutcome.MULTIPLE,
    }:
        raise ValueError("only a successful search result has an Agent projection")
    return SearchOrdersAgentOutput(
        outcome=SearchOrdersAgentOutcome(result.outcome.value),
        candidates=tuple(
            SearchOrdersAgentCandidate(
                ordinal=ordinal,
                order_number=candidate.public_summary.order_number,
                ordered_on_utc=candidate.public_summary.ordered_on_utc,
                status=candidate.public_summary.status,
                matching_items=candidate.public_summary.matching_items,
            )
            for ordinal, candidate in enumerate(result.candidates, start=1)
        ),
        truncated=result.truncated,
    )


def _utc_source_timestamp(value: datetime, *, field_name: str) -> str:
    value = require_utc(value, field_name=field_name)
    return value.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _source_version_token(*, schema: str, payload: dict[str, object]) -> str:
    canonical_bytes = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"{schema}:sha256:{hashlib.sha256(canonical_bytes).hexdigest()}"


def _require_non_empty_string(value: str, *, field_name: str) -> None:
    if type(value) is not str or not value:
        raise ValueError(f"{field_name} must be a non-empty string")


def compute_order_candidate_source_version(
    *,
    owner_customer_id: str,
    order_id: str,
    ordered_at: datetime,
    status: OrderStatus,
    matched_lines: Sequence[MatchedOrderLine],
    public_summary: OrderCandidatePublicSummary,
    matching_rule_version: Literal["order-search-matching.p0.v1"] = (
        ORDER_SEARCH_MATCHING_RULE_VERSION
    ),
) -> OrderCandidateSourceVersion:
    """Hash the exact candidate source payload; this does not confer authority."""

    _require_non_empty_string(owner_customer_id, field_name="owner_customer_id")
    if type(order_id) is not str or _ORDER_ID_PATTERN.fullmatch(order_id) is None:
        raise ValueError("order_id must be a validated P0 Order ID")
    if matching_rule_version != ORDER_SEARCH_MATCHING_RULE_VERSION:
        raise ValueError("unknown order-search matching rule version")
    _validate_matched_line_order(matched_lines)
    expected_summary = build_order_candidate_public_summary(
        order_number=public_summary.order_number,
        ordered_at=ordered_at,
        status=status,
        matched_lines=matched_lines,
    )
    if public_summary != expected_summary:
        raise ValueError("public_summary does not match candidate source facts")

    payload: dict[str, object] = {
        "source_version_schema": _CANDIDATE_SOURCE_SCHEMA,
        "owner_customer_id": owner_customer_id,
        "order_id": order_id,
        "ordered_at": _utc_source_timestamp(ordered_at, field_name="ordered_at"),
        "status": status.value,
        "matching_rule_version": matching_rule_version,
        "matched_lines": [
            {
                "line_ordinal": line.line_ordinal,
                "product_name": line.product_name,
                "quantity": line.quantity,
                "product_category": line.product_category,
                "normalized_search_aliases": list(line.normalized_search_aliases),
            }
            for line in matched_lines
        ],
        "public_summary": {
            "order_number": public_summary.order_number,
            "ordered_on_utc": public_summary.ordered_on_utc.isoformat(),
            "status": public_summary.status.value,
            "matching_items": [
                {
                    "product_name": item.product_name,
                    "quantity": item.quantity,
                }
                for item in public_summary.matching_items
            ],
        },
    }
    return cast(
        OrderCandidateSourceVersion,
        _source_version_token(schema=_CANDIDATE_SOURCE_SCHEMA, payload=payload),
    )


def compute_order_search_snapshot_source_version(
    *,
    query: SearchOrdersQuery,
    ordered_candidates: Sequence[OrderCandidate],
    truncated: bool,
) -> OrderSearchSnapshotSourceVersion:
    """Hash the exact owner-scoped ordered search snapshot payload."""

    if type(truncated) is not bool:
        raise TypeError("truncated must be a strict boolean")
    candidates = tuple(ordered_candidates)
    if not 1 <= len(candidates) <= ORDER_SEARCH_MAX_CANDIDATES:
        raise ValueError("snapshot requires one to five ordered candidates")
    if candidates != sort_order_candidates(candidates):
        raise ValueError(
            "ordered_candidates must use ordered_at DESC, order_number ASC order"
        )
    refs = tuple(candidate.owner_scoped_order_ref for candidate in candidates)
    if len(set(refs)) != len(refs):
        raise ValueError("ordered candidate refs must be unique")

    payload: dict[str, object] = {
        "source_version_schema": _SNAPSHOT_SOURCE_SCHEMA,
        "owner_customer_id": query.customer_id,
        "normalized_query": query.product_description,
        "ordered_at_from": _utc_source_timestamp(
            query.ordered_at_from,
            field_name="ordered_at_from",
        ),
        "ordered_at_to": _utc_source_timestamp(
            query.ordered_at_to,
            field_name="ordered_at_to",
        ),
        "max_candidates": query.max_candidates,
        "matching_rule_version": query.matching_rule_version,
        "ordered_candidates": [
            {
                "ordinal": ordinal,
                "owner_scoped_order_ref": candidate.owner_scoped_order_ref,
                "candidate_source_version": candidate.candidate_source_version,
            }
            for ordinal, candidate in enumerate(candidates, start=1)
        ],
        "truncated": truncated,
    }
    return cast(
        OrderSearchSnapshotSourceVersion,
        _source_version_token(schema=_SNAPSHOT_SOURCE_SCHEMA, payload=payload),
    )
