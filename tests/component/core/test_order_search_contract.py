from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from mini_agent.core.common import ContractVisibility
from mini_agent.core.order import OrderStatus
from mini_agent.core.order_search import (
    ORDER_SEARCH_MATCHING_RULE_VERSION,
    ORDER_SEARCH_MAX_CANDIDATES,
    ORDER_SEARCH_WINDOW,
    MatchedOrderLine,
    OrderCandidate,
    OrderCandidatePublicSummary,
    OrderCandidateSourceVersion,
    OrderSearchFailureCode,
    OrderSearchLine,
    OrderSearchSnapshotSourceVersion,
    SearchOrdersAgentCandidate,
    SearchOrdersAgentOutcome,
    SearchOrdersAgentOutput,
    SearchOrdersInput,
    SearchOrdersOutcome,
    SearchOrdersQuery,
    SearchOrdersResult,
    build_order_candidate_public_summary,
    build_search_orders_query,
    compute_order_candidate_source_version,
    compute_order_search_snapshot_source_version,
    match_order_lines,
    normalize_product_description,
    normalize_search_aliases,
    order_is_within_search_window,
    project_search_orders_agent_output,
    sort_order_candidates,
)

NOW = datetime(2030, 4, 1, 12, 30, 45, 123456, tzinfo=UTC)
CANDIDATE_VERSION = (
    "mock-order-search-candidate-source-version.p0.v1:sha256:" + "a" * 64
)
SNAPSHOT_VERSION = (
    "mock-order-search-snapshot-source-version.p0.v1:sha256:" + "b" * 64
)
ORDER_SEARCH_FAILURE_CODE_OWNER = (
    "ORDER_SEARCH_TRANSIENT",
    "ORDER_SEARCH_UNAVAILABLE",
    "ORDER_SEARCH_SOURCE_INTEGRITY",
)


def _matched_line(
    ordinal: int,
    *,
    product_name: str = "示例跑步鞋",
    quantity: int = 1,
) -> MatchedOrderLine:
    return MatchedOrderLine(
        line_ordinal=ordinal,
        product_name=product_name,
        quantity=quantity,
        product_category="鞋",
        normalized_search_aliases=("running shoes", "运动鞋"),
    )


def _candidate(
    order_number: str,
    ordered_at: datetime,
    *,
    matched_lines: tuple[MatchedOrderLine, ...] | None = None,
) -> OrderCandidate:
    lines = matched_lines or (_matched_line(1),)
    summary = build_order_candidate_public_summary(
        order_number=order_number,
        ordered_at=ordered_at,
        status=OrderStatus.SHIPPED,
        matched_lines=lines,
    )
    return OrderCandidate(
        owner_scoped_order_ref=f"order-ref-{order_number}",
        order_number=order_number,
        ordered_at=ordered_at,
        status=OrderStatus.SHIPPED,
        matched_lines=lines,
        public_summary=summary,
        candidate_source_version=CANDIDATE_VERSION,
    )


def test_normalization_is_nfkc_trim_whitespace_collapse_and_casefold() -> None:
    assert normalize_product_description("  ＲＵＮＮＩＮＧ\u3000  Shoes  ") == (
        "running shoes"
    )
    assert normalize_product_description("Straße") == "strasse"


def test_normalization_precedes_the_one_to_eighty_scalar_boundary() -> None:
    raw_over_limit = "a" * 80 + " "
    assert len(raw_over_limit) > 80
    assert normalize_product_description(raw_over_limit) == "a" * 80
    assert SearchOrdersInput(product_description=raw_over_limit).product_description == (
        raw_over_limit
    )

    normalized_over_limit = " " + "a" * 81 + " "
    with pytest.raises(ValueError, match="after normalization"):
        normalize_product_description(normalized_over_limit)
    with pytest.raises(ValidationError, match="after normalization"):
        SearchOrdersInput(product_description=normalized_over_limit)


@pytest.mark.parametrize("invalid", ["", " \t\n ", "a" * 81, "\ud800", 1])
def test_normalization_rejects_non_scalar_empty_overlong_or_non_string(
    invalid: object,
) -> None:
    with pytest.raises((TypeError, ValueError)):
        normalize_product_description(invalid)  # type: ignore[arg-type]


def test_aliases_use_same_normalization_then_deduplicate_and_sort() -> None:
    assert normalize_search_aliases(
        (" 运动鞋 ", "ＲＵＮＮＩＮＧ  SHOES", "running shoes")
    ) == ("running shoes", "运动鞋")

    with pytest.raises(ValueError, match="empty"):
        normalize_search_aliases(("valid", " \t "))


def test_query_builder_uses_trusted_owner_exact_closed_window_and_constants() -> None:
    query = build_search_orders_query(
        customer_id="customer-a",
        product_description="  跑步鞋 ",
        trusted_now=NOW,
    )

    assert query.model_dump() == {
        "customer_id": "customer-a",
        "product_description": "跑步鞋",
        "ordered_at_from": NOW - timedelta(days=90),
        "ordered_at_to": NOW,
        "max_candidates": 5,
        "matching_rule_version": "order-search-matching.p0.v1",
    }
    assert ORDER_SEARCH_WINDOW == timedelta(days=90)
    assert ORDER_SEARCH_MAX_CANDIDATES == 5
    assert ORDER_SEARCH_MATCHING_RULE_VERSION == "order-search-matching.p0.v1"
    assert query.contract_visibility is ContractVisibility.RUNTIME_PRIVATE


def test_query_rejects_non_utc_or_non_exact_window_and_constants() -> None:
    valid = {
        "customer_id": "customer-a",
        "product_description": "鞋",
        "ordered_at_from": NOW - timedelta(days=90),
        "ordered_at_to": NOW,
    }
    invalid_payloads = (
        {**valid, "ordered_at_from": NOW - timedelta(days=89)},
        {**valid, "ordered_at_to": NOW.replace(tzinfo=None)},
        {**valid, "max_candidates": 4},
        {**valid, "max_candidates": 5.0},
        {**valid, "matching_rule_version": "order-search-matching.p0.v2"},
        {**valid, "product_description": " Shoes "},
    )

    for payload in invalid_payloads:
        with pytest.raises(ValidationError):
            SearchOrdersQuery.model_validate(payload)


@pytest.mark.parametrize(
    ("ordered_at", "included"),
    [
        (NOW - timedelta(days=90), True),
        (NOW, True),
        (NOW - timedelta(days=90, microseconds=1), False),
        (NOW + timedelta(microseconds=1), False),
    ],
)
def test_order_search_window_is_closed_and_excludes_old_or_future_orders(
    ordered_at: datetime,
    included: bool,
) -> None:
    query = build_search_orders_query(
        customer_id="customer-a",
        product_description="鞋",
        trusted_now=NOW,
    )
    assert order_is_within_search_window(ordered_at, query=query) is included


def test_matching_is_name_substring_or_exact_category_alias_only() -> None:
    lines = (
        OrderSearchLine(
            line_ordinal=4,
            product_name="Leather Care Kit",
            quantity=1,
            product_category="配件",
            search_aliases=("护理",),
        ),
        OrderSearchLine(
            line_ordinal=2,
            product_name="城市跑步鞋",
            quantity=2,
            product_category="鞋",
            search_aliases=("ＲＵＮＮＩＮＧ SHOES", "运动鞋", "running shoes"),
        ),
        OrderSearchLine(
            line_ordinal=3,
            product_name="鞋带",
            quantity=1,
            product_category="配件",
            search_aliases=(),
        ),
    )

    name_matches = match_order_lines("跑步", lines)
    assert tuple(line.line_ordinal for line in name_matches) == (2,)
    assert name_matches[0].normalized_search_aliases == ("running shoes", "运动鞋")

    category_matches = match_order_lines("鞋", lines)
    assert tuple(line.line_ordinal for line in category_matches) == (2, 3)

    alias_matches = match_order_lines("RUNNING\u3000SHOES", lines)
    assert tuple(line.line_ordinal for line in alias_matches) == (2,)

    assert match_order_lines("运动", lines) == ()


def test_matching_rejects_duplicate_line_ordinals() -> None:
    duplicate = OrderSearchLine(
        line_ordinal=1,
        product_name="鞋",
        quantity=1,
        product_category="鞋",
    )
    with pytest.raises(ValueError, match="line_ordinal"):
        match_order_lines("鞋", (duplicate, duplicate))


def test_public_summary_uses_utc_date_source_order_and_first_three_lines() -> None:
    lines = tuple(
        _matched_line(index, product_name=f"商品{index}", quantity=index)
        for index in range(1, 5)
    )
    summary = build_order_candidate_public_summary(
        order_number="O-1001",
        ordered_at=NOW,
        status=OrderStatus.PAID,
        matched_lines=lines,
    )

    assert summary.model_dump() == {
        "order_number": "O-1001",
        "ordered_on_utc": NOW.date(),
        "status": OrderStatus.PAID,
        "matching_items": (
            {"product_name": "商品1", "quantity": 1},
            {"product_name": "商品2", "quantity": 2},
            {"product_name": "商品3", "quantity": 3},
        ),
    }

    mismatched_summary = summary.model_copy(update={"status": OrderStatus.CANCELLED})
    with pytest.raises(ValidationError, match="public_summary"):
        OrderCandidate(
            owner_scoped_order_ref="order-ref-1",
            order_number="O-1001",
            ordered_at=NOW,
            status=OrderStatus.PAID,
            matched_lines=lines,
            public_summary=mismatched_summary,
            candidate_source_version=CANDIDATE_VERSION,
        )


def test_candidates_have_stable_ordered_at_desc_order_number_asc_order() -> None:
    candidates = (
        _candidate("O-1003", NOW - timedelta(days=1)),
        _candidate("O-1002", NOW),
        _candidate("O-1001", NOW),
    )
    ordered = sort_order_candidates(candidates)
    assert tuple(candidate.order_number for candidate in ordered) == (
        "O-1001",
        "O-1002",
        "O-1003",
    )

    with pytest.raises(ValidationError, match="stable order"):
        SearchOrdersResult(
            outcome=SearchOrdersOutcome.MULTIPLE,
            candidates=candidates,
            snapshot_resource_ref="search-snapshot-ref",
            snapshot_source_version=SNAPSHOT_VERSION,
            observed_at=NOW,
        )


def test_candidate_source_token_uses_exact_canonical_json_bytes() -> None:
    lines = (_matched_line(1),)
    summary = build_order_candidate_public_summary(
        order_number="O-1001",
        ordered_at=NOW,
        status=OrderStatus.SHIPPED,
        matched_lines=lines,
    )
    token = compute_order_candidate_source_version(
        owner_customer_id="customer-a",
        order_id="O-1001",
        ordered_at=NOW,
        status=OrderStatus.SHIPPED,
        matched_lines=lines,
        public_summary=summary,
    )
    payload = {
        "source_version_schema": "mock-order-search-candidate-source-version.p0.v1",
        "owner_customer_id": "customer-a",
        "order_id": "O-1001",
        "ordered_at": "2030-04-01T12:30:45.123456Z",
        "status": "SHIPPED",
        "matching_rule_version": "order-search-matching.p0.v1",
        "matched_lines": [
            {
                "line_ordinal": 1,
                "product_name": "示例跑步鞋",
                "quantity": 1,
                "product_category": "鞋",
                "normalized_search_aliases": ["running shoes", "运动鞋"],
            }
        ],
        "public_summary": {
            "order_number": "O-1001",
            "ordered_on_utc": "2030-04-01",
            "status": "SHIPPED",
            "matching_items": [{"product_name": "示例跑步鞋", "quantity": 1}],
        },
    }
    canonical = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    expected = (
        "mock-order-search-candidate-source-version.p0.v1:sha256:"
        + hashlib.sha256(canonical).hexdigest()
    )
    assert token == expected
    assert compute_order_candidate_source_version(
        owner_customer_id="customer-a",
        order_id="O-1001",
        ordered_at=NOW,
        status=OrderStatus.SHIPPED,
        matched_lines=(lines[0].model_copy(update={"quantity": 2}),),
        public_summary=summary.model_copy(
            update={
                "matching_items": (
                    summary.matching_items[0].model_copy(update={"quantity": 2}),
                )
            }
        ),
    ) != token


def test_snapshot_source_token_preserves_stable_candidate_order() -> None:
    query = build_search_orders_query(
        customer_id="customer-a",
        product_description="鞋",
        trusted_now=NOW,
    )
    candidates = (
        _candidate("O-1001", NOW),
        _candidate("O-1002", NOW - timedelta(days=1)),
    )
    token = compute_order_search_snapshot_source_version(
        query=query,
        ordered_candidates=candidates,
        truncated=False,
    )
    assert token.startswith(
        "mock-order-search-snapshot-source-version.p0.v1:sha256:"
    )
    assert len(token.rsplit(":", 1)[1]) == 64
    payload = {
        "source_version_schema": "mock-order-search-snapshot-source-version.p0.v1",
        "owner_customer_id": "customer-a",
        "normalized_query": "鞋",
        "ordered_at_from": "2030-01-01T12:30:45.123456Z",
        "ordered_at_to": "2030-04-01T12:30:45.123456Z",
        "max_candidates": 5,
        "matching_rule_version": "order-search-matching.p0.v1",
        "ordered_candidates": [
            {
                "ordinal": 1,
                "owner_scoped_order_ref": "order-ref-O-1001",
                "candidate_source_version": CANDIDATE_VERSION,
            },
            {
                "ordinal": 2,
                "owner_scoped_order_ref": "order-ref-O-1002",
                "candidate_source_version": CANDIDATE_VERSION,
            },
        ],
        "truncated": False,
    }
    canonical = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    assert token == (
        "mock-order-search-snapshot-source-version.p0.v1:sha256:"
        + hashlib.sha256(canonical).hexdigest()
    )
    with pytest.raises(ValueError, match="ordered_at DESC"):
        compute_order_search_snapshot_source_version(
            query=query,
            ordered_candidates=tuple(reversed(candidates)),
            truncated=False,
        )


@pytest.mark.parametrize(
    ("count", "valid"),
    [(2, False), (3, False), (4, False), (5, True)],
)
def test_truncated_snapshot_source_token_requires_exactly_five_candidates(
    count: int,
    valid: bool,
) -> None:
    query = build_search_orders_query(
        customer_id="customer-a",
        product_description="鞋",
        trusted_now=NOW,
    )
    candidates = tuple(
        _candidate(f"O-{1001 + index}", NOW - timedelta(days=index))
        for index in range(count)
    )

    if valid:
        token = compute_order_search_snapshot_source_version(
            query=query,
            ordered_candidates=candidates,
            truncated=True,
        )
        assert token.startswith(
            "mock-order-search-snapshot-source-version.p0.v1:sha256:"
        )
    else:
        with pytest.raises(ValueError, match="truncated=true"):
            compute_order_search_snapshot_source_version(
                query=query,
                ordered_candidates=candidates,
                truncated=True,
            )


@pytest.mark.parametrize(
    ("outcome", "count", "truncated", "failure_code", "valid"),
    [
        (SearchOrdersOutcome.UNIQUE, 1, False, None, True),
        (SearchOrdersOutcome.UNIQUE, 1, True, None, False),
        (SearchOrdersOutcome.MULTIPLE, 2, False, None, True),
        (SearchOrdersOutcome.MULTIPLE, 2, True, None, False),
        (SearchOrdersOutcome.MULTIPLE, 3, True, None, False),
        (SearchOrdersOutcome.MULTIPLE, 4, True, None, False),
        (SearchOrdersOutcome.MULTIPLE, 5, True, None, True),
        (SearchOrdersOutcome.MULTIPLE, 1, False, None, False),
        (SearchOrdersOutcome.NO_MATCH, 0, False, None, True),
        (SearchOrdersOutcome.NO_MATCH, 0, True, None, False),
        (
            SearchOrdersOutcome.SYSTEM_FAILURE,
            0,
            False,
            OrderSearchFailureCode.ORDER_SEARCH_TRANSIENT,
            True,
        ),
        (SearchOrdersOutcome.SYSTEM_FAILURE, 0, False, None, False),
    ],
)
def test_search_result_closed_outcome_matrix(
    outcome: SearchOrdersOutcome,
    count: int,
    truncated: bool,
    failure_code: OrderSearchFailureCode | None,
    valid: bool,
) -> None:
    candidates = tuple(
        _candidate(f"O-{1001 + index}", NOW - timedelta(days=index))
        for index in range(count)
    )
    success = outcome in {SearchOrdersOutcome.UNIQUE, SearchOrdersOutcome.MULTIPLE}
    payload = {
        "outcome": outcome,
        "candidates": candidates,
        "truncated": truncated,
        "snapshot_resource_ref": "snapshot-ref" if success else None,
        "snapshot_source_version": SNAPSHOT_VERSION if success else None,
        "observed_at": NOW if success else None,
        "failure_code": failure_code,
    }

    if valid:
        result = SearchOrdersResult(**payload)
        assert len(result.candidates) == count
    else:
        with pytest.raises(ValidationError):
            SearchOrdersResult(**payload)


@pytest.mark.parametrize(
    ("count", "valid"),
    [(2, False), (3, False), (4, False), (5, True)],
)
def test_truncated_agent_output_requires_exactly_five_candidates(
    count: int,
    valid: bool,
) -> None:
    candidates = tuple(
        SearchOrdersAgentCandidate(
            ordinal=index + 1,
            **_candidate(
                f"O-{1001 + index}",
                NOW - timedelta(days=index),
            ).public_summary.model_dump(),
        )
        for index in range(count)
    )
    payload = {
        "outcome": SearchOrdersAgentOutcome.MULTIPLE,
        "candidates": candidates,
        "truncated": True,
    }

    if valid:
        assert len(SearchOrdersAgentOutput(**payload).candidates) == 5
    else:
        with pytest.raises(ValidationError, match="truncated=true"):
            SearchOrdersAgentOutput(**payload)


def test_non_success_results_reject_partial_private_authority_metadata() -> None:
    with pytest.raises(ValidationError, match="authority metadata"):
        SearchOrdersResult(
            outcome=SearchOrdersOutcome.NO_MATCH,
            snapshot_resource_ref="must-not-leak",
        )

    with pytest.raises(ValidationError):
        SearchOrdersResult(
            outcome=SearchOrdersOutcome.SYSTEM_FAILURE,
            failure_code="UNKNOWN_FAILURE",
        )


def test_order_search_failure_code_allowlist_matches_the_exact_owner_strings() -> None:
    assert {code.value for code in OrderSearchFailureCode} == set(
        ORDER_SEARCH_FAILURE_CODE_OWNER
    )


@pytest.mark.parametrize("code_value", ORDER_SEARCH_FAILURE_CODE_OWNER)
def test_each_owned_order_search_failure_code_forms_a_system_failure_result(
    code_value: str,
) -> None:
    result = SearchOrdersResult(
        outcome=SearchOrdersOutcome.SYSTEM_FAILURE,
        failure_code=code_value,
    )
    assert result.failure_code is not None
    assert result.failure_code.value == code_value


@pytest.mark.parametrize(
    "invalid_code",
    (
        "ORDER_SEARCH_TIMEOUT",
        "order_search_transient",
        "SHIPMENT_SERVICE_TRANSIENT",
    ),
)
def test_non_owned_order_search_failure_codes_are_rejected(
    invalid_code: str,
) -> None:
    with pytest.raises(ValidationError):
        SearchOrdersResult(
            outcome=SearchOrdersOutcome.SYSTEM_FAILURE,
            failure_code=invalid_code,
        )


def test_model_visible_search_types_have_exact_minimum_disclosure() -> None:
    input_value = SearchOrdersInput(product_description="跑步鞋")
    result = SearchOrdersResult(
        outcome=SearchOrdersOutcome.UNIQUE,
        candidates=(_candidate("O-1001", NOW),),
        snapshot_resource_ref="snapshot-ref",
        snapshot_source_version=SNAPSHOT_VERSION,
        observed_at=NOW,
    )
    output = project_search_orders_agent_output(result)

    assert input_value.contract_visibility is ContractVisibility.MODEL_VISIBLE
    assert output.model_dump() == {
        "outcome": SearchOrdersAgentOutcome.UNIQUE,
        "candidates": (
            {
                "ordinal": 1,
                "order_number": "O-1001",
                "ordered_on_utc": NOW.date(),
                "status": OrderStatus.SHIPPED,
                "matching_items": (
                    {"product_name": "示例跑步鞋", "quantity": 1},
                ),
            },
        ),
        "truncated": False,
    }
    assert set(SearchOrdersAgentCandidate.model_fields) == {
        "ordinal",
        "order_number",
        "ordered_on_utc",
        "status",
        "matching_items",
    }
    assert set(SearchOrdersAgentOutput.model_fields) == {
        "outcome",
        "candidates",
        "truncated",
    }
    schema = str(SearchOrdersAgentOutput.model_json_schema()).casefold()
    assert "no_match" not in schema
    assert "system_failure" not in schema
    for forbidden in (
        "customer_id",
        "owner_scoped_order_ref",
        "source_version",
        "ordered_at_from",
        "failure_code",
        "raw_payload",
        "product_category",
        "line_ordinal",
    ):
        assert forbidden not in schema

    with pytest.raises(ValidationError, match="extra"):
        OrderCandidatePublicSummary.model_validate(
            {
                **result.candidates[0].public_summary.model_dump(),
                "customer_id": "private-owner",
            }
        )


def test_agent_projection_rejects_non_success_private_result() -> None:
    with pytest.raises(ValueError, match="successful"):
        project_search_orders_agent_output(
            SearchOrdersResult(outcome=SearchOrdersOutcome.NO_MATCH)
        )


def test_source_version_aliases_are_strict_patterns() -> None:
    assert OrderCandidateSourceVersion is not OrderSearchSnapshotSourceVersion
    with pytest.raises(ValidationError):
        OrderCandidate(
            owner_scoped_order_ref="order-ref",
            order_number="O-1001",
            ordered_at=NOW,
            status=OrderStatus.SHIPPED,
            matched_lines=(_matched_line(1),),
            public_summary=build_order_candidate_public_summary(
                order_number="O-1001",
                ordered_at=NOW,
                status=OrderStatus.SHIPPED,
                matched_lines=(_matched_line(1),),
            ),
            candidate_source_version=(
                "mock-order-source-version.p0.v1:sha256:" + "a" * 64
            ),
        )
