---
phase: 02-cycle-2-e2e-01
plan: 02-15R1E
type: implementation
wave: W9
depends_on:
  - B_C2_W9_UNIQUE_TARGET_CORE
files_modified:
  - src/mini_agent/core/control_gateway.py
  - tests/component/core/test_control_gateway.py
autonomous: false
requirements: [E2E01-02, E2E01-05]
user_setup: []
must_haves:
  truths:
    - "UNIQUE auto-target get_order使用exact current product_description binding和独立verified_target_ref；Control Gateway不得把它误判为ordinal selection。"
    - "ordinal selection仍只接受candidate_ordinal；direct order-id与get_shipment路径保持不变。"
    - "Gateway的candidate validation与authorized-command reproving必须使用同一target-aware binding规则，任一target/owner/version/Observation替换均fail closed。"
  artifacts:
    - "Control Gateway UNIQUE auto-target binding closure。"
    - "Component regression证明UNIQUE route可授权且ordinal/direct-order paths不漂移。"
  key_links:
    - "B_C2_W9_UNIQUE_TARGET_CORE → reviewed 02-15R1E → B_C2_W9_UNIQUE_TARGET_GATE → fourth-refrozen 02-15R1。"
---

# Phase 2 Plan 02-15R1E｜UNIQUE auto-target Gateway closure

> **EXACT TASK PACKET / W9 CORE_GATE_OWNER_CORRECTION**
>
> `B_C2_W9_UNIQUE_TARGET_CORE = 1f5dd61154f0bd26e3286576a8e54429e8e6f864` /
> tree `f28eff6864902a1b6c8d41d4f592b32c725910ab` 已 reviewed。随后第三次冻结的
> R1只读实现对照确认：`route_cycle2_unique_next_move`按reviewed contract保留
> `product_description` argument binding，但现有Gateway在带`verified_target_ref`的
> `get_order`分支仍只接受`candidate_ordinal`，导致真实normal入口确定性REJECT。
> 本Packet只修复同一Core owner内的消费端闭包；R1 checkpoint继续unpublished，
> Cases继续为`CONTRACT_DEFINED`。

## Exact Task Packet

```yaml
task_id: 02-15R1E
goal: 对齐Control Gateway与reviewed UNIQUE auto-target route，使product_description query binding加独立verified target可被exact验证和授权，同时保留ordinal/direct-order兼容性。
repository: weijie567/mini-agent
remote: origin
head_branch: codex/e2e01-cycle2-w9-unique-target-gateway
base_branch: integration/e2e01-cycle2
base_sha: 4668ce1f61453f3f9186d7cd3a1e22e93e75e098
base_tree: a4bb056d71fb957b67bccb62d18150b437b09dd3
planning_control_base_sha: 4668ce1f61453f3f9186d7cd3a1e22e93e75e098
planning_control_base_tree: a4bb056d71fb957b67bccb62d18150b437b09dd3
worktree_id: e2e01-cycle2-w9-unique-target-gateway
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
  - AGENTS.md sections 3-8
  - Cycle 2 Spec sections 2.4, 3.2, 7.3.1-7.3.4 and 7.13
  - reviewed R1C durability contract and R1D Core route
read_first:
  - .planning/phases/02-cycle-2-e2e-01/02-15R1E-PLAN.md
  - docs/implementation/e2e01-cycle2-implementation-spec.md
  - src/mini_agent/core/control_gateway.py
  - src/mini_agent/core/request_processing.py
  - tests/component/core/test_control_gateway.py
  - tests/component/core/test_request_processing.py
required_product_blobs:
  AGENTS.md: 5904da48f4e3a2d95e86ffa04ebe29694caf5c0a
  docs/implementation/e2e01-cycle2-implementation-spec.md: b0d3ad29a86365903b1c2c3af3f809556c8a9c2d
  src/mini_agent/core/control_gateway.py: 1658feab7d3448157631a85ff3d7dfcb01023f74
  tests/component/core/test_control_gateway.py: 11b54e0a7b5e21e67380050451c76f79c27238b8c
dependencies:
  - exact B_C2_W9_UNIQUE_TARGET_CORE = 1f5dd61154f0bd26e3286576a8e54429e8e6f864
  - exact current integration planning successor = 4668ce1f61453f3f9186d7cd3a1e22e93e75e098
core_contract_decisions:
  - target-bearing get_order accepts product_description only when verified-target closure binds the same binding, order id, owner, Task/RequestUnit/version and source Observation
  - target-bearing get_order continues accepting candidate_ordinal for committed ordinal selection
  - direct get_order without verified_target_ref continues requiring accepted order_id binding
  - use one shared helper for Gate evaluation and authorized-command reproving to prevent rule drift
contract_changes: NO — correction aligns an existing deterministic consumer with the reviewed R1C/R1D contract.
security_impact: CRITICAL / exact target/binding authorization; no new authority or disclosure.
eval_impact: COMPONENT REGRESSION SUPPORT ONLY — no Case/artifact/Harness/Result/lifecycle mutation.
review_profile:
  planning_review: INDEPENDENT_EXACT_FILE_PASS
  implementation_review: TARGETED_CORE_GATE_SECURITY
  reviewer_timeout: 20_SECONDS_MAX; interrupt and narrow immediately on timeout
  focused_tests: uv run pytest tests/component/core/test_control_gateway.py tests/component/core/test_request_processing.py -q
  neighbor_tests: uv run pytest tests/component/core/test_candidate_selection_contract.py tests/component/core/test_cycle2_memory_contract.py tests/component/core/test_tool_system_contract.py -q
  full_suite_gate: NOT_RUN_FOR_R1E; W6 supplied mid-phase canonical full and next canonical full belongs W12
verification:
  compile: uv run python -m compileall -q src/mini_agent/core tests/component/core
  focused: exact focused_tests command
  neighbor: exact neighbor_tests command
  diff_check: git diff --check 4668ce1f61453f3f9186d7cd3a1e22e93e75e098...HEAD
  allowlist: git diff --name-only exact base...HEAD equals exact two-file owned_files set
  full: NOT_RUN_BY_REVIEW_PROFILE
required_checks:
  - exact base/tree/blobs/protection/branch absence/clean preflight PASS
  - UNIQUE route candidate evaluates ACCEPT and re-proves into AuthorizedToolCommandV2
  - target mutation and wrong binding family reject; ordinal/direct get_order remain green
  - no Application/Infrastructure/API/bootstrap/Eval/docs/planning/graphify implementation change
  - compile/focused/neighbor/diff/allowlist/commit containment PASS
  - bounded independent exact-head review closes BLOCK/HIGH and disposes MEDIUM
done_when:
  - reviewed exact-two-file PR merges and successor is recorded as B_C2_W9_UNIQUE_TARGET_GATE
  - 02-15R1 fourth-refreeze may use only the real successor; Cases remain CONTRACT_DEFINED
rollback:
  - before merge close PR and retain exact-head evidence
  - after merge revert this exact correction before R1/R2 depend on it
  - never repair by weakening verified-target closure or fabricating candidate_ordinal/order_id bindings
handoff_to: tech-lead
handoff_format: .planning/phases/02-cycle-2-e2e-01/02-15R1E-PLAN.md#handoff
output_barrier: B_C2_W9_UNIQUE_TARGET_GATE
```

## Tasks

1. RED：复现R1D UNIQUE candidate被Gateway错误拒绝，并锁定ordinal/direct-order兼容性。
2. GREEN：只修改Control Gateway共享target-aware binding predicate和对应tests。
3. VERIFY：compile、focused、neighbor、exact-two-file containment与20秒bounded review。

## Handoff

报告exact identity、两文件、UNIQUE/ordinal/direct-order矩阵、focused/neighbor、review
finding处置与`B_C2_W9_UNIQUE_TARGET_GATE`；明确Application/DB/HTTP/Eval lifecycle/
Result均未推进，R1 checkpoint仍未发布。
