---
phase: 02-cycle-2-e2e-01
plan: 02-15R1G
type: implementation
wave: W9
depends_on:
  - B_C2_W9_SHIPMENT_TARGET_BINDING_CONTRACT
files_modified:
  - src/mini_agent/core/control_gateway.py
  - tests/component/core/test_control_gateway.py
autonomous: false
requirements: [E2E01-03, E2E01-05, E2E01-06]
user_setup: []
must_haves:
  truths:
    - "target-bearing get_shipment接受exact current order_id/product_description/candidate_ordinal origin binding，但每次只能命中closed target自身的唯一binding ref。"
    - "argument order_id、verified_target_ref、owner、Task/RequestUnit/version和source Observation任一漂移均REJECT。"
    - "get_order三路径、search_orders和no-progress semantic identity保持兼容。"
  artifacts:
    - "Control Gateway Shipment target-origin binding implementation and component matrix。"
  key_links:
    - "B_C2_W9_SHIPMENT_TARGET_BINDING_CONTRACT → reviewed 02-15R1G → B_C2_W9_SHIPMENT_TARGET_GATE → fifth-refrozen 02-15R1。"
---

# Phase 2 Plan 02-15R1G｜Shipment target-origin Gateway closure

> **EXACT TASK PACKET / W9 CORE_GATE_OWNER_CORRECTION**
>
> R1F reviewed scoped Spec已定义三种互斥target-origin binding。本Packet只修改Control
> Gateway和其component tests，以同一verified-target predicate验证`get_shipment`；
> 不修改Application、Infrastructure、HTTP、Eval或持久化。Cases继续为
> `CONTRACT_DEFINED`。

## Exact Task Packet

```yaml
task_id: 02-15R1G
goal: 实现reviewed get_shipment target-origin binding矩阵，并保持target/owner/version/Observation exact closure与既有工具路径兼容。
repository: weijie567/mini-agent
remote: origin
head_branch: codex/e2e01-cycle2-w9-shipment-target-gateway
base_branch: integration/e2e01-cycle2
base_sha: a9d7d460d93df95e3dd59d118224322a12e6de56
base_tree: c09f39f8cc69b1d88785ff22a603581555bc78c5
planning_control_base_sha: a9d7d460d93df95e3dd59d118224322a12e6de56
planning_control_base_tree: c09f39f8cc69b1d88785ff22a603581555bc78c5
worktree_id: e2e01-cycle2-w9-shipment-target-gateway
agent_role: runtime-engineer
writer: cycle2-core-gateway-owner
pull_request_base: integration/e2e01-cycle2
pull_request_mode: draft until independent exact-head review PASS; never use admin bypass
owned_files:
  - src/mini_agent/core/control_gateway.py
  - tests/component/core/test_control_gateway.py
forbidden_files:
  - all repository files outside the exact two-file owned_files allowlist
  - src/mini_agent/application/**
  - src/mini_agent/infrastructure/**
  - src/mini_agent/api/**
  - src/mini_agent/bootstrap.py
  - src/mini_agent/evaluation/**
  - evals/**
  - alembic/**
  - docs/**
  - .planning/**
  - AGENTS.md
  - graphify-out/**
canonical_inputs:
  - docs/implementation/e2e01-cycle2-implementation-spec.md sections 7.3.4, 7.4, 7.5 and 7.11
  - existing reviewed Gateway target/Observation closure and no-progress identity
required_product_blobs:
  AGENTS.md: 5904da48f4e3a2d95e86ffa04ebe29694caf5c0a
  docs/implementation/e2e01-cycle2-implementation-spec.md: eb03403890fc61993f9b1375510cdbd8b9d37301
  src/mini_agent/core/control_gateway.py: 7e98dfd546589d2e4b282d915b776c7daf84504d
  tests/component/core/test_control_gateway.py: bfb8e35ea2cfa7ee7cfb7f1375577623fbc237c8
dependencies:
  - exact B_C2_W9_SHIPMENT_TARGET_BINDING_CONTRACT = a9d7d460d93df95e3dd59d118224322a12e6de56
core_contract_decisions:
  - add one shared target-origin predicate requiring binding name in order_id/product_description/candidate_ordinal and exact _cycle2_verified_target_closed result
  - use the predicate in get_shipment live Gate argument validation and no-progress semantic identity reproving
  - retain get_order-specific origin matrix: direct order_id without target, or target-bearing product_description/candidate_ordinal
  - reject wrong binding name/ref, target/order replacement, stale/superseded target, owner/version/Observation drift and target ref inside argument refs
contract_changes: NO — implementation of reviewed R1F scoped contract.
security_impact: CRITICAL / Shipment authorization remains conditioned on existing exact verified target; no Claim alone grants access.
eval_impact: COMPONENT REGRESSION SUPPORT ONLY — no Case/artifact/Harness/Result/lifecycle mutation.
review_profile:
  planning_review: INDEPENDENT_EXACT_FILE_PASS
  implementation_review: TARGETED_CORE_GATE_SECURITY
  reviewer_timeout: 20_SECONDS_MAX; interrupt and narrow immediately on timeout
  focused_tests: uv run pytest tests/component/core/test_control_gateway.py -q
  neighbor_tests: uv run pytest tests/component/core/test_request_processing.py tests/component/core/test_candidate_selection_contract.py tests/component/core/test_cycle2_memory_contract.py tests/component/core/test_tool_system_contract.py -q
  full_suite_gate: NOT_RUN_FOR_R1G; W6 supplied mid-phase canonical full and next canonical full belongs W12
verification:
  compile: uv run python -m compileall -q src/mini_agent/core tests/component/core
  focused: exact focused_tests command
  neighbor: exact neighbor_tests command
  diff_check: git diff --check a9d7d460d93df95e3dd59d118224322a12e6de56...HEAD
  allowlist: exact two files
  full: NOT_RUN_BY_REVIEW_PROFILE
required_checks:
  - exact base/tree/blobs/protection/branch absence/clean preflight PASS
  - direct/UNIQUE/ordinal Shipment Gate ACCEPT matrix plus wrong-family/target mutation REJECT
  - get_order/search/no-progress regression green
  - no outer-layer or Eval mutation
  - compile/focused/neighbor/diff/allowlist/commit containment PASS
  - bounded independent exact-head review closes BLOCK/HIGH and disposes MEDIUM
done_when:
  - reviewed exact-two-file PR merges as B_C2_W9_SHIPMENT_TARGET_GATE
  - R1 fifth-refreeze uses only real successor; Cases remain CONTRACT_DEFINED
rollback:
  - close before merge or revert exact Core commit before R1/R2 depend on it
  - never weaken verified-target closure or authorize from Claim name/value alone
handoff_to: tech-lead
handoff_format: .planning/phases/02-cycle-2-e2e-01/02-15R1G-PLAN.md#handoff
output_barrier: B_C2_W9_SHIPMENT_TARGET_GATE
```

## Tasks

1. RED：覆盖三origin binding的Shipment ACCEPT及wrong binding/target mutation拒绝。
2. GREEN：只在Gateway共享predicate和tests内实现reviewed contract。
3. VERIFY：compile、focused、neighbor、two-file containment与20秒bounded review。

## Handoff

报告exact identity、矩阵、focused/neighbor、review与`B_C2_W9_SHIPMENT_TARGET_GATE`；
明确Application/DB/HTTP/Eval lifecycle/Result均未推进。
