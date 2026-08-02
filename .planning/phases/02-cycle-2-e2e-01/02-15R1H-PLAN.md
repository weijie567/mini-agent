---
phase: 02-cycle-2-e2e-01
plan: 02-15R1H
type: implementation
wave: W9
depends_on:
  - B_C2_W9_SHIPMENT_TARGET_GATE
files_modified:
  - src/mini_agent/core/request_processing.py
  - tests/component/core/test_request_processing.py
autonomous: false
requirements: [E2E01-03, E2E01-05, E2E01-06]
user_setup: []
must_haves:
  truths:
    - "Application只能通过reviewed Core route从current verified target形成get_shipment candidate，不直接构造Gateway authority。"
    - "post-order与shipment_not_received continuation复用同一target-origin binding closure；新Claim不是Shipment target authority。"
    - "direct/UNIQUE/ordinal三类origin binding保持互斥并精确复制target.input_binding_refs。"
  artifacts:
    - "route_cycle2_verified_target_next_move pure Core route and shared closure tests。"
  key_links:
    - "B_C2_W9_SHIPMENT_TARGET_GATE → reviewed 02-15R1H → B_C2_W9_SHIPMENT_TARGET_ROUTE → sixth-refrozen 02-15R1。"
---

# Phase 2 Plan 02-15R1H｜Shipment verified-target Core route

> **EXACT TASK PACKET / W9 CORE_ROUTE_OWNER_CORRECTION**
>
> R1F/R1G已reviewed对齐Spec和Gateway，但Application仍缺少一个能从current verified
> target正式形成`get_shipment` candidate的Core route；现有
> `route_cycle2_continuation_next_move`也仍硬编码查找`order_id` binding。禁止
> Application直接构造GatewayCandidate。本Packet只在Request Processing owner内增加
> pure route并复用同一closure；Cases继续为`CONTRACT_DEFINED`。

## Exact Task Packet

```yaml
task_id: 02-15R1H
goal: 增加target-bound get_shipment pure route，并让shipment_not_received continuation复用同一三origin-binding closure。
repository: weijie567/mini-agent
remote: origin
head_branch: codex/e2e01-cycle2-w9-shipment-target-route
base_branch: integration/e2e01-cycle2
base_sha: 60b31fd4921f717e7155e6b5ae701d8b542adad8
base_tree: e383c2499004ede02a66dfb42f172fbd6899da62
planning_control_base_sha: 60b31fd4921f717e7155e6b5ae701d8b542adad8
planning_control_base_tree: e383c2499004ede02a66dfb42f172fbd6899da62
worktree_id: e2e01-cycle2-w9-shipment-target-route
agent_role: runtime-engineer
writer: cycle2-core-request-processing-owner
pull_request_base: integration/e2e01-cycle2
pull_request_mode: draft until independent exact-head review PASS; never use admin bypass
owned_files:
  - src/mini_agent/core/request_processing.py
  - tests/component/core/test_request_processing.py
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
  - reviewed R1G Gateway target-origin predicate
required_product_blobs:
  AGENTS.md: 5904da48f4e3a2d95e86ffa04ebe29694caf5c0a
  docs/implementation/e2e01-cycle2-implementation-spec.md: eb03403890fc61993f9b1375510cdbd8b9d37301
  src/mini_agent/core/request_processing.py: d493b817aef3ddcdc9a13911a11b0470532bfb17
  tests/component/core/test_request_processing.py: 70c7ce85047e80415484ff0a9b33b1702cf87e0f
dependencies:
  - exact B_C2_W9_SHIPMENT_TARGET_GATE = 60b31fd4921f717e7155e6b5ae701d8b542adad8
core_contract_decisions:
  - add one private exact target-origin resolver over current accepted InputBindingV2 records and Cycle2VerifiedOrderTargetFacts
  - accepted origin names are order_id/product_description/candidate_ordinal; target.input_binding_refs must equal the one resolved binding ref
  - order_id binding value must equal target.order_id; product-description/ordinal values remain Claims and are never compared or rewritten as order facts
  - add route_cycle2_verified_target_next_move for get_shipment only, exact current Task version and target order_id
  - existing shipment_not_received continuation validates its trigger Claim separately, then delegates target authorization to the shared resolver
contract_changes: NO — Request Processing implementation of reviewed R1F/R1G contract.
security_impact: CRITICAL / pure route prevents Application authority reconstruction and Claim-only Shipment access.
eval_impact: COMPONENT SUPPORT ONLY — no artifact/Harness/Result/lifecycle mutation.
review_profile:
  planning_review: INDEPENDENT_EXACT_FILE_PASS
  implementation_review: TARGETED_CORE_ROUTE_SECURITY
  reviewer_timeout: 20_SECONDS_MAX; interrupt and narrow immediately on timeout
  focused_tests: uv run pytest tests/component/core/test_request_processing.py -q
  neighbor_tests: uv run pytest tests/component/core/test_control_gateway.py tests/component/core/test_candidate_selection_contract.py tests/component/core/test_cycle2_memory_contract.py -q
  full_suite_gate: NOT_RUN_FOR_R1H; W6 supplied mid-phase canonical full and next canonical full belongs W12
verification:
  compile: uv run python -m compileall -q src/mini_agent/core tests/component/core
  focused: exact focused_tests command
  neighbor: exact neighbor_tests command
  diff_check: git diff --check 60b31fd4921f717e7155e6b5ae701d8b542adad8...HEAD
  allowlist: exact two files
required_checks:
  - exact base/tree/blobs/protection/branch absence/clean preflight PASS
  - positive direct/UNIQUE/ordinal post-order route and shipment-not-received continuation
  - wrong binding/ref/target/order/owner/version/Observation and Claim substitution fail closed
  - no outer-layer/Eval mutation; compile/focused/neighbor/diff/allowlist PASS
  - bounded independent exact-head review closes BLOCK/HIGH and disposes MEDIUM
done_when:
  - reviewed exact-two-file PR merges as B_C2_W9_SHIPMENT_TARGET_ROUTE
  - R1 sixth-refreeze uses only real successor; Cases remain CONTRACT_DEFINED
rollback:
  - close before merge or revert exact Core route commit before R1/R2 depend on it
  - never repair by direct GatewayCandidate construction in Application
handoff_to: tech-lead
handoff_format: .planning/phases/02-cycle-2-e2e-01/02-15R1H-PLAN.md#handoff
output_barrier: B_C2_W9_SHIPMENT_TARGET_ROUTE
```

## Tasks

1. RED：锁定三origin post-order route、Claim continuation与negative substitutions。
2. GREEN：增加共享target-origin resolver和pure get_shipment route。
3. VERIFY：compile、focused、neighbor、two-file containment与20秒bounded review。

## Handoff

报告exact identity、route/continuation矩阵、focused/neighbor、review与
`B_C2_W9_SHIPMENT_TARGET_ROUTE`；明确Application/DB/HTTP/Eval均未推进。
