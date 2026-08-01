---
phase: 02-cycle-2-e2e-01
plan: 02-10R
type: correction
wave: W6
depends_on:
  - B_C2_BUSINESS_READ_PORTS
  - GATE_P2_A5
files_modified:
  - alembic/versions/20260802_0005_cycle2_search_authority_correction.py
  - src/mini_agent/infrastructure/persistence/models.py
  - tests/integration/test_database_migrations.py
autonomous: false
requirements:
  - E2E01-02
  - E2E01-05
  - E2E01-06
user_setup: []
must_haves:
  truths:
    - "搜索权威行显式持久化 canonical OrderStatus，不从摘要、query、模型或 Adapter 猜测。"
    - "受限 raw search snapshot 具有 Adapter 分配的 opaque durable ref，数据库不得自动生成该 ref。"
    - "Phase 1 head 的已有行只从同 owner/order 的受控 order_payload 全量预验证并原子回填；任何坏行使整个 migration 零可见变更。"
    - "已有 search document 或 snapshot evidence 时 downgrade fail closed；空 evidence 时可逆。"
    - "本 correction 不实现 Adapter、Runtime、Eval Harness、Result 或 Case lifecycle。"
  artifacts:
    - "20260802_0005 linear correction migration。"
    - "ORM search status admission 与受限 raw snapshot table。"
    - "两条 upgrade path、atomic backfill、constraint、downgrade 与 Phase 1 byte-identity evidence。"
  key_links:
    - "B_C2_BUSINESS_READ_PORTS → reviewed 02-10R → 重新冻结 02-07/02-11。"
---

# Phase 2 Plan 02-10R｜Search authority physical correction

> **EXACT TASK PACKET / W6 TARGETED_MIGRATION**
>
> `02-07/02-11` dispatch preflight 已确认 W5 schema 无法承载现行 canonical
> `OrderCandidate.status` 与 Adapter-owned durable raw snapshot ref。用户于
> 2026-08-02 授权按建议修正；master Plan owner-ruling PR #254 已reviewed merge，
> slots `27 → 28` 且不新增 wave label。早期 `02-07/02-11` Plans 与 clean Worktrees
> 保持暂停，必须在真实 `02-10R` successor 后重新冻结。

## 目标与边界

新增唯一 linear revision `20260802_0005`：为 `mock_order_search_documents`
补充受控 `status`，并新增只允许 owner-scoped exact reader / audit recovery 使用的
`mock_order_search_snapshots`。只修改 migration、ORM model 与 migration integration
tests；不改变 canonical payload、业务语义、Adapter、records、Runtime 或 Eval。

## Exact Task Packet

```yaml
task_id: 02-10R
goal: 补全搜索权威 status 与 durable raw snapshot 的最小物理承载，并提供原子 upgrade/downgrade evidence。
repository: weijie567/mini-agent
remote: origin
head_branch: codex/e2e01-cycle2-search-authority-physical-correction
base_branch: integration/e2e01-cycle2
base_sha: d05933238db26939e06421d148060c513a0aed6a
base_tree: d37da0d30f2d76c7a572d1900ea6c50bb9a5db90
planning_control_base_sha: d05933238db26939e06421d148060c513a0aed6a
planning_control_base_tree: d37da0d30f2d76c7a572d1900ea6c50bb9a5db90
worktree_id: e2e01-cycle2-search-authority-physical-correction
agent_role: infra-engineer
writer: infra-engineer-migration
pull_request_base: integration/e2e01-cycle2
pull_request_mode: draft until independent final exact-head review PASS; never use admin bypass
owned_files:
  - alembic/versions/20260802_0005_cycle2_search_authority_correction.py
  - src/mini_agent/infrastructure/persistence/models.py
  - tests/integration/test_database_migrations.py
forbidden_files:
  - all repository files outside the exact three-file owned_files allowlist
  - all historical alembic revisions including 20260731_0004_cycle2_records_v2.py
  - src/mini_agent/application/**
  - src/mini_agent/core/**
  - src/mini_agent/infrastructure/order/**
  - src/mini_agent/infrastructure/shipment/**
  - src/mini_agent/infrastructure/persistence/postgres.py
  - src/mini_agent/infrastructure/persistence/recovery.py
  - src/mini_agent/evaluation/**
  - src/mini_agent/runtime.py
  - src/mini_agent/bootstrap.py
  - tests/** except tests/integration/test_database_migrations.py
  - evals/**
  - docs/**
  - .planning/**
  - pyproject.toml
  - uv.lock
  - compose.yaml
  - AGENTS.md
  - graphify-out/**
canonical_inputs:
  - AGENTS.md sections 3-8
  - docs/architecture/memory-design-reference.md Evidence and exact-reader boundaries
  - docs/implementation/e2e01-cycle2-implementation-spec.md sections 7.2.3-7.2.4 and 10
  - docs/implementation/e2e01-cycle2-multi-agent-plan.md slot 02-10R and W6
read_first:
  - .planning/phases/02-cycle-2-e2e-01/GATE-W6-EXECUTION-CARD.md
  - .planning/phases/02-cycle-2-e2e-01/02-10-PLAN.md
  - alembic/versions/20260731_0004_cycle2_records_v2.py
  - src/mini_agent/core/order.py
  - src/mini_agent/core/order_search.py
  - src/mini_agent/infrastructure/persistence/models.py
  - tests/integration/test_database_migrations.py
  - tests/integration/test_postgres_get_order.py
required_product_blobs:
  AGENTS.md: 5904da48f4e3a2d95e86ffa04ebe29694caf5c0a
  PROJECT_DIRECTION.md: ed0ae8482c2d43278a1dd984d5ff55da5265cfda
  docs/architecture/memory-design-reference.md: fdcdd3c751eb03b7462257cfd62354c9c2917a69
  docs/implementation/e2e01-cycle2-implementation-spec.md: 0ab85bd7e8cbe8556472efa7003eb4aab4649ce0
  docs/implementation/e2e01-cycle2-multi-agent-plan.md: 8da86e8e1726dd03ddfb2d75809a29004c4072c1
  .planning/phases/02-cycle-2-e2e-01/02-10-PLAN.md: a941f013cee68b69e2e0660350f82ec97092f71e
  .planning/phases/02-cycle-2-e2e-01/02-07R-PLAN.md: b9d564002916d7f343acaf705bb53d2d8632994e
  alembic/versions/20260731_0004_cycle2_records_v2.py: 5ccc46fd1feac54ffe41b7e2b11bc8c7ed7fbda5
  src/mini_agent/core/order.py: 30f88e6c9dedd52e5fdab848e7cec371428ae971
  src/mini_agent/core/order_search.py: 2c8b84ed82f982bc46b0ca4c2141f357b3d4eba4
  src/mini_agent/infrastructure/persistence/models.py: c74c3706e76f11dfc603b554d259d09b4d0e2ad5
  tests/component/core/test_order_search_contract.py: b6d50ac9fe5b10845acd2bc5a874d2794bb0fde7
  tests/integration/test_database_migrations.py: 981c07c6824f6165db781e761754cbc151f5bcfc
  tests/integration/test_postgres_get_order.py: 653dfe73f201d9bd99a9bb8d9011607407051d63
required_planning_control_blobs:
  .planning/phases/02-cycle-2-e2e-01/GATE-W6-EXECUTION-CARD.md: b7c5fe9c725debc90da9cb37a5ff2f0ab454d961
dependencies:
  - exact master owner-ruling successor = d05933238db26939e06421d148060c513a0aed6a
  - exact owner-ruling successor tree = d37da0d30f2d76c7a572d1900ea6c50bb9a5db90
  - exact reviewed B_C2_BUSINESS_READ_PORTS = c775ef45eb42c9f03e63d0065d493e2fb2a43556
  - exact reviewed B_C2_BUSINESS_READ_PORTS tree = c598651b56db003e6ab77a08d266d709a0ff8e76
  - revision 20260731_0004 is the current unique migration head; 20260802_0005 is absent
  - old 02-07/02-11 Plans and clean Worktrees are paused and not executable
physical_schema_decisions:
  search_status:
    - add VARCHAR status with no server default
    - frozen allowed literals CREATED, PAID, FULFILLING, SHIPPED, DELIVERED, CANCELLED
    - migration contains frozen SQL literals and tests compare them with Core OrderStatus; migration must not import runtime code
    - existing rows backfill only from same customer_id/order_id mock_orders.order_payload.status after full graph prevalidation
  raw_snapshot:
    - table mock_order_search_snapshots
    - snapshot_resource_ref UUID primary key with no server default; only Adapter supplies it
    - customer_id VARCHAR not null, observed_at TIMESTAMPTZ not null, snapshot_payload JSONB object not null
    - index customer_id + snapshot_resource_ref supports owner-scoped exact lookup
    - snapshot_payload has exactly the canonical section 7.2.4 search snapshot keys and canonical JSON semantics
    - no order foreign key because one snapshot may reference multiple orders; audit evidence must not cascade-delete
    - no redundant source-version column; exact reader recomputes the token from preserved canonical payload bytes
    - P0 retention is durable/no deletion; this Packet adds no delete API or retention worker
  upgrade:
    - lock mock_orders and mock_order_search_documents before validation/backfill
    - prevalidate every parent payload as an object, exact owner/order identity and controlled status before the first visible mutation
    - nullable add, owner/order backfill, assert no NULL, then add CHECK and NOT NULL in one transaction
    - any malformed, missing, null, type-drifted, unknown or owner-mismatched source aborts the whole revision
  downgrade:
    - lock mock_orders, mock_order_search_documents and mock_order_search_snapshots
    - if any search document or snapshot exists, raise one bounded error before mutation
    - empty evidence permits dropping snapshot index/table then search status check/column
    - error and logs never disclose payload, owner or ref
contract_changes: NONE — this implements already-active canonical status and durable snapshot requirements; no semantic owner changes.
security_impact: HIGH / TARGETED_MIGRATION — trusted owner scope, source authority, raw snapshot restriction, non-disclosure and fail-closed downgrade.
eval_impact: INFRASTRUCTURE PREREQUISITE ONLY — no Eval artifact, Harness, Result or Case lifecycle transition.
review_profile:
  planning_review: INDEPENDENT_EXACT_FILE_PASS
  implementation_review: TARGETED_MIGRATION
  reviewer_timeout: 45_SECONDS_MAX
  targeted_risk_checks:
    - exact three-file allowlist, unique revision/down_revision and no historical migration edits
    - search status enum equals Core OrderStatus with no default or guessed backfill
    - whole-set prevalidation and locks precede any visible schema/data change
    - both empty DB and Phase 1 head upgrade paths converge
    - raw snapshot ref is Adapter-supplied UUID with no database default and owner-scoped exact lookup
    - snapshot payload is restricted, exact and not duplicated into ordinary Trace/model/HTTP surfaces
    - existing search/snapshot evidence blocks downgrade before mutation; empty downgrade succeeds
    - Phase 1 order_payload/get_order projection/source bytes remain byte-identical
  focused_tests: uv run pytest tests/integration/test_database_migrations.py -q
  neighbor_tests: uv run pytest tests/integration/test_postgres_get_order.py tests/component/core/test_order_search_contract.py tests/component/application/test_ports_contract.py -q
  full_suite_gate: NOT_RUN_FOR_02_10R; run once only at W6 exit after 02-07 and 02-11 merge
  phase_end_deep_audit: W12_ONLY
verification:
  service:
    - docker compose up --wait -d db
    - docker compose --profile test up --wait -d db-test
  focused: uv run pytest tests/integration/test_database_migrations.py -q
  neighbor: uv run pytest tests/integration/test_postgres_get_order.py tests/component/core/test_order_search_contract.py tests/component/application/test_ports_contract.py -q
  migration_head: uv run alembic upgrade head
  compile: uv run python -m compileall -q alembic/versions/20260802_0005_cycle2_search_authority_correction.py src/mini_agent/infrastructure/persistence/models.py tests/integration/test_database_migrations.py
  diff_check: git diff --check d05933238db26939e06421d148060c513a0aed6a...HEAD
  full: NOT_RUN_BY_REVIEW_PROFILE
latest_integration_overlay: REQUIRED — replay only the exact three-file patch on latest integration, rerun both upgrade paths/focused/neighbor, verify blobs, then obtain bounded exact-head overlay review PASS.
required_checks:
  - exact base/tree/blobs/protection/branch absence/clean preflight PASS; exact three-file allowlist
  - revision 20260802_0005 has one parent 20260731_0004 and both upgrade paths converge
  - six allowed status literals equal Core OrderStatus; null/unknown/type drift are rejected
  - existing-row backfill is owner/order exact and atomic; injected invalid row leaves zero visible correction
  - snapshot table has exact PK/owner/time/payload/check/index shape and no UUID default/order cascade/source-version copy
  - snapshot exact payload/owner lookup, DML lock race and downgrade race tests PASS
  - Phase 1 order_payload/get_order canonical source bytes remain exact
  - focused/neighbor/migration-head/compile/diff PASS; canonical full accurately NOT RUN; exact-head review 0 BLOCK/HIGH
done_when:
  - reviewed PR merges serially and successor is recorded as B_C2_SEARCH_AUTHORITY_PHYSICAL
  - 02-07/02-11 are re-frozen only from that real successor
rollback:
  - before merge close PR and retain two-path transcripts
  - after merge use ordinary revert only while search/snapshot tables are empty; otherwise preserve 0005 and fix forward
  - never edit historical migrations, force-push, guess status, database-generate snapshot refs or downgrade through evidence loss
handoff_to: tech-lead
handoff_format: .planning/phases/02-cycle-2-e2e-01/02-10R-PLAN.md#handoff
output_barrier: B_C2_SEARCH_AUTHORITY_PHYSICAL
```

## Tasks

### Task 1 — RED：two-path / status / snapshot / downgrade oracle

冻结六状态、existing-row source validation、whole-migration atomicity、snapshot shape、
owner-scoped lookup、DML/downgrade race 与 Phase 1 byte-identity vectors。

### Task 2 — GREEN：revision 0005 and ORM parity

实现最小 status correction 与 restricted snapshot storage；无 Adapter、reader、Runtime
或 lifecycle 行为。

### Task 3 — Regression and bounded review

运行 focused/neighbor/two-path/migration-head/compile/diff，完成 45 秒内 feature 与
latest-integration exact-head review。

## W6 correction gate

```text
product/planning base == exact d0593323 / d37da0d3
AND master owner ruling authorizes 02-10R / 28 slots / no new wave
AND required blobs match
AND revision/feature branch/worktree absent
AND old 02-07/02-11 remain paused
AND planning review == PASS
```

## Handoff

报告 exact identity、三文件、两条 upgrade path、status/snapshot/downgrade、tests/review 与
`B_C2_SEARCH_AUTHORITY_PHYSICAL`；明确 02-07/02-11 必须重冻结，Case lifecycle、
Harness/Result 和 canonical full 均未推进。
