---
phase: 02-cycle-2-e2e-01
plan: 02-11R
type: correction
wave: W6
depends_on:
  - B_C2_BUSINESS_ADAPTERS
  - GATE_P2_A6
files_modified:
  - alembic/versions/20260802_0006_cycle2_record_state_history.py
  - src/mini_agent/infrastructure/persistence/models.py
  - tests/integration/test_database_migrations.py
autonomous: false
requirements:
  - E2E01-02
  - E2E01-03
  - E2E01-05
  - E2E01-06
user_setup: []
must_haves:
  truths:
    - "versioned superseded Run 的旧 Task / RequestUnit 图来自 durable exact pre-image，不从 current row、Memory、模型或推断补造。"
    - "history 只接受 trusted owner-scoped TaskRecord / RequestUnitRecord v1 envelope、exact logical identity 与 positive state version。"
    - "迁移前已丢失的历史不回填；后续 reader 无 exact pre-image 时继续 fail closed。"
    - "history 与 mutable current row 解耦；存在任何 history evidence 时 destructive downgrade fail closed。"
    - "本 correction 不实现 Adapter、OA-10 finalizer、Runtime、Eval Harness、Result 或 Case lifecycle。"
  artifacts:
    - "20260802_0006 linear correction migration。"
    - "ORM immutable record-state history table。"
    - "empty/current-head upgrade、closed admission、uniqueness、owner lookup、downgrade/race evidence。"
  key_links:
    - "B_C2_BUSINESS_ADAPTERS → reviewed 02-11R → 重新冻结并回放 02-11。"
---

# Phase 2 Plan 02-11R｜Immutable record-state history correction

> **EXACT TASK PACKET / W6 TARGETED_MIGRATION**
>
> `02-11` focused `109 passed`、neighbor `1340 passed` 后确认：现有
> `p0_records` 只保留 mutable current Task / RequestUnit，无法构造 canonical
> `SupersededRunReadClosure` 对 non-null `base_task_state_version` 要求的 exact old
> graph。该实现已保存为 unpublished blocked checkpoint
> `da8ee98178dc4a69c32253b68cc897c7c5556711`，没有发布或降低 OA-10。
> 用户于 2026-08-02 授权发现问题后按建议修复；master Plan owner-ruling PR #259
> 已 reviewed merge，slots `28 → 29` 且不新增 wave label。

## 目标与边界

新增唯一 linear revision `20260802_0006`：建立 owner-scoped immutable
`p0_record_state_history`，只保存被替换前的 `task_record.p0.v1` 与
`request_unit_record.p0.v1` exact envelopes。只修改 migration、ORM model 与 migration
integration tests；本 Packet 不写 Adapter，因此表初始为空，不重建已丢失历史。

## Exact Task Packet

```yaml
task_id: 02-11R
goal: 为现有 OA-10 exact obsolete graph contract 增加最小 owner-scoped immutable pre-image 物理承载。
repository: weijie567/mini-agent
remote: origin
head_branch: codex/e2e01-cycle2-record-history-physical-correction
base_branch: integration/e2e01-cycle2
base_sha: 096fa25a98632d38c3a38e64a6c9ad57f864e0e0
base_tree: db7599249ffe25f8ca9a483fbe5c8e9845dd9eaa
planning_control_base_sha: 096fa25a98632d38c3a38e64a6c9ad57f864e0e0
planning_control_base_tree: db7599249ffe25f8ca9a483fbe5c8e9845dd9eaa
worktree_id: e2e01-cycle2-record-history-physical-correction
agent_role: infra-engineer
writer: infra-engineer-migration
pull_request_base: integration/e2e01-cycle2
pull_request_mode: draft until independent final exact-head review PASS; never use admin bypass
owned_files:
  - alembic/versions/20260802_0006_cycle2_record_state_history.py
  - src/mini_agent/infrastructure/persistence/models.py
  - tests/integration/test_database_migrations.py
forbidden_files:
  - all repository files outside the exact three-file owned_files allowlist
  - all historical alembic revisions including 20260802_0005_cycle2_search_authority_correction.py
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
  - docs/architecture/memory-design-reference.md exact record/evidence and Memory non-authority boundaries
  - docs/implementation/e2e01-cycle2-implementation-spec.md OA-10 and persistence sections
  - docs/implementation/e2e01-cycle2-multi-agent-plan.md slot 02-11R and W6
read_first:
  - .planning/phases/02-cycle-2-e2e-01/GATE-W6-EXECUTION-CARD.md
  - .planning/phases/02-cycle-2-e2e-01/02-10R-PLAN.md
  - .planning/phases/02-cycle-2-e2e-01/02-11-PLAN.md
  - alembic/versions/20260802_0005_cycle2_search_authority_correction.py
  - src/mini_agent/core/task_state.py
  - src/mini_agent/application/records.py
  - src/mini_agent/infrastructure/persistence/models.py
  - tests/integration/test_database_migrations.py
required_product_blobs:
  AGENTS.md: 5904da48f4e3a2d95e86ffa04ebe29694caf5c0a
  PROJECT_DIRECTION.md: ed0ae8482c2d43278a1dd984d5ff55da5265cfda
  docs/architecture/memory-design-reference.md: fdcdd3c751eb03b7462257cfd62354c9c2917a69
  docs/implementation/e2e01-cycle2-implementation-spec.md: 0ab85bd7e8cbe8556472efa7003eb4aab4649ce0
  docs/implementation/e2e01-cycle2-multi-agent-plan.md: 8301075f80f029feeb9a7dc85d23b93c59667545
  alembic/versions/20260802_0005_cycle2_search_authority_correction.py: 29041e985e72483a3e0dfdc4663bfe10574e1e2a
  src/mini_agent/core/task_state.py: eb6b429b4e44b58a848faf476681a610670ca83b
  src/mini_agent/application/records.py: 408d2e87cab8a29ebd01e106e309ff1e1e3f141b
  src/mini_agent/infrastructure/persistence/models.py: 40c1b779542b7e19970e5f6cda7f0edf6720416f
  tests/integration/test_database_migrations.py: 0a5395ccbd6434b1d28f9b0fadbdebbd06ecb86b
required_planning_control_blobs:
  .planning/phases/02-cycle-2-e2e-01/GATE-W6-EXECUTION-CARD.md: f207a0a320ad0d57f70390c10305e8780ca62881
  .planning/phases/02-cycle-2-e2e-01/02-11-PLAN.md: 85e5572a2d785d4d09d005f475beea5ac815ae60
dependencies:
  - exact master owner-ruling successor = 096fa25a98632d38c3a38e64a6c9ad57f864e0e0
  - exact owner-ruling successor tree = db7599249ffe25f8ca9a483fbe5c8e9845dd9eaa
  - exact reviewed B_C2_BUSINESS_ADAPTERS = 78bce02c36ada33d6695d5a919d23b61bb8df21e
  - exact reviewed B_C2_BUSINESS_ADAPTERS tree = 032e0c5edfb3c2ffc18f34192ae72858bc0cec85
  - revision 20260802_0005 is the current unique migration head; 20260802_0006 is absent
  - blocked 02-11 checkpoint is clean, unpublished and forbidden as a direct feature head
physical_schema_decisions:
  table:
    - name p0_record_state_history
    - history_id UUID primary key with no server default; only Adapter supplies it
    - record_code VARCHAR restricted exactly to task_record or request_unit_record
    - record_schema_version VARCHAR restricted to matching p0.v1 code/version pairs
    - logical_identity JSONB array, scope_owner_customer_id non-empty VARCHAR, state_version BIGINT positive
    - envelope JSONB object containing the exact canonical P0PersistenceEnvelope
    - archived_at TIMESTAMPTZ database timestamp is audit metadata only and never business-fact evidence
  identity_and_lookup:
    - unique record_code + logical_identity + state_version prevents two historical truths for one logical version
    - owner + record_code + logical_identity + state_version index supports exact owner-scoped retrieval
    - no FK to mutable p0_records and no cascade; history must survive current-row replacement or later lifecycle cleanup
  admission:
    - database admits only the two closed code/version pairs, JSON array/object shapes and positive version
    - later Adapter must decode and exact-compare owner, identity, version and envelope before accepting duplicate or returning history
    - duplicate-identical may be idempotent; duplicate-conflicting must fail closed
  upgrade:
    - create the empty table and constraints/index only; do not inspect current rows to invent pre-images
    - both empty database and current 0005 head converge to the same schema
  downgrade:
    - lock p0_record_state_history before evidence check
    - if any history row exists, raise one bounded error before mutation
    - empty history permits dropping index/table
    - error and logs never disclose owner, identity, version or envelope
contract_changes: NONE — this implements the already-active SupersededRunReadClosure/OA-10 exact obsolete graph requirement; no semantic owner changes.
security_impact: CRITICAL STATE AUTHORITY / historical state is owner-scoped, immutable, non-model-visible and fail closed when absent or contradictory.
eval_impact: INFRASTRUCTURE PREREQUISITE ONLY — no Eval artifact, Harness, Result or Case lifecycle transition.
review_profile:
  planning_review: INDEPENDENT_EXACT_FILE_PASS
  implementation_review: TARGETED_MIGRATION
  reviewer_timeout: 30_SECONDS_MAX
  targeted_risk_checks:
    - exact three-file allowlist, unique revision/down_revision and no historical migration edits
    - closed Task/RequestUnit code-version pairs, exact JSON shapes, positive state version and no database-generated history identity
    - owner-scoped exact lookup and unique logical-version admission without FK/cascade to mutable current rows
    - empty/current-head upgrade paths converge without fabricating pre-existing history
    - non-empty history blocks downgrade before mutation; empty downgrade succeeds; DML/downgrade race is serialized
    - history table is not exposed to model, HTTP, Trace, Eval artifact or ordinary public projection
  focused_tests: uv run pytest tests/integration/test_database_migrations.py -q
  neighbor_tests: uv run pytest tests/integration/test_postgres_atomicity.py tests/component/application/test_record_contracts.py tests/component/core/test_cycle2_memory_contract.py -q
  full_suite_gate: NOT_RUN_FOR_02_11R; run once only at W6 exit after 02-11 merge
  phase_end_deep_audit: W12_ONLY
verification:
  service:
    - docker compose up --wait -d db
    - docker compose --profile test up --wait -d db-test
  focused: uv run pytest tests/integration/test_database_migrations.py -q
  neighbor: uv run pytest tests/integration/test_postgres_atomicity.py tests/component/application/test_record_contracts.py tests/component/core/test_cycle2_memory_contract.py -q
  migration_head: uv run alembic upgrade head
  compile: uv run python -m compileall -q alembic/versions/20260802_0006_cycle2_record_state_history.py src/mini_agent/infrastructure/persistence/models.py tests/integration/test_database_migrations.py
  diff_check: git diff --check 096fa25a98632d38c3a38e64a6c9ad57f864e0e0...HEAD
  full: NOT_RUN_BY_REVIEW_PROFILE
latest_integration_overlay: REQUIRED — replay only the exact three-file patch on latest integration, rerun both upgrade paths/focused/neighbor, verify blobs, then obtain bounded exact-head overlay review PASS.
required_checks:
  - exact base/tree/blobs/protection/branch absence/clean preflight PASS; exact three-file allowlist
  - revision 20260802_0006 has one parent 20260802_0005 and both upgrade paths converge
  - exact table/check/index/default/FK shape matches physical_schema_decisions
  - invalid code/version/identity/envelope/version and duplicate logical-version rows are rejected
  - no migration backfill fabricates old Task/RequestUnit graph
  - non-empty downgrade, DML/downgrade race and empty downgrade evidence PASS
  - focused/neighbor/migration-head/compile/diff PASS; canonical full accurately NOT RUN; exact-head review 0 BLOCK/HIGH
done_when:
  - reviewed PR merges serially and successor is recorded as B_C2_RECORD_HISTORY_PHYSICAL
  - 02-11 is re-frozen only from that real successor and writes/reads history atomically in its own five-file allowlist
rollback:
  - before merge close PR and retain two-path transcripts
  - after merge use ordinary revert only while p0_record_state_history is empty; otherwise preserve 0006 and fix forward
  - never edit historical migrations, force-push, fabricate old records, loosen owner/version checks or downgrade through evidence loss
handoff_to: tech-lead
handoff_format: .planning/phases/02-cycle-2-e2e-01/02-11R-PLAN.md#handoff
output_barrier: B_C2_RECORD_HISTORY_PHYSICAL
```

## Tasks

### Task 1 — RED：history shape / admission / downgrade oracle

冻结两种 record、exact code/version/identity/version/envelope、owner lookup、unique
logical-version、two-path upgrade、empty/non-empty downgrade 与 DML race vectors。

### Task 2 — GREEN：revision 0006 and ORM parity

实现最小 immutable history physical layer；无 Adapter、reader、OA-10 finalizer、Runtime
或 lifecycle 行为。

### Task 3 — Regression and bounded review

运行 focused/neighbor/two-path/migration-head/compile/diff，完成 30 秒内 feature 与
latest-integration exact-head review。

## W6 correction gate

```text
product/planning base == exact 096fa25a / db759924
AND master owner ruling authorizes 02-11R / 29 slots / no new wave
AND required blobs match
AND revision/feature branch/worktree absent
AND 02-11 checkpoint remains unpublished and blocked
AND planning review == PASS
```

## Handoff

报告 exact identity、三文件、两条 upgrade path、history admission/lookup/downgrade、
tests/review 与 `B_C2_RECORD_HISTORY_PHYSICAL`；明确 02-11 必须重新冻结回放，
Case lifecycle、Harness/Result 和 canonical full 均未推进。
