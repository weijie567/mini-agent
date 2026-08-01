---
phase: 02-cycle-2-e2e-01
plan: 02-15R1A
type: implementation
wave: W9
depends_on: [B_C2_W9_SEED_CONTRACT]
files_modified:
  - src/mini_agent/core/request_understanding.py
  - src/mini_agent/core/request_processing.py
  - tests/component/core/test_request_understanding_contract.py
  - tests/component/core/test_request_processing.py
autonomous: false
requirements: [E2E01-02, E2E01-03, E2E01-05, E2E01-06]
user_setup: []
must_haves:
  truths:
    - "Cycle 2 first-turn output可表达且只表达当前消息中的product_description USER_CLAIM，不扩大trusted/private authority。"
    - "initial reducer形成clean Task/RequestUnit/InputBindingV2与可复核next move，不执行Tool、不生成Observation或business fact。"
    - "Phase 1 RequestUnderstandingOutputV2、order_id initial reducer与public shape保持不变。"
    - "ordinal与shipment_not_received仍只允许已有current Task的continuation路径。"
  artifacts:
    - "Core Cycle 2 first-turn RU output/candidate graph。"
    - "Pure initial product-description reducer producing InputBindingV2。"
    - "Positive and fail-closed Core component evidence。"
  key_links:
    - "B_C2_W9_R1A_OWNER_APPROVED → reviewed 02-15R1A → B_C2_W9_INITIAL_RU → refrozen 02-15R1。"
---

# Phase 2 Plan 02-15R1A｜Cycle 2 initial product-description RU contract

> **EXACT TASK PACKET / W9 CORE_INTENT_OWNER_CORRECTION**
>
> R1 planning PR #272已merge，但writer在任何写入前证明现有
> `RequestUnderstandingOutputV2`与initial reducer只支持`order_id`；独立复核确认R1
> 六文件边界无法真实构造首轮`product_description → search_orders`。one-file owner
> ruling PR #273已将W9修正为`R0→R1A→R1→R2→15`、33 slots / 16 wave labels。
> R1 worktree保持clean；本Packet不把该blocked attempt计为完成。

## Exact Task Packet

```yaml
task_id: 02-15R1A
goal: 增加closed Cycle 2 first-turn product-description RU output与pure initial reducer，使R1可合法构造真实首轮search Task graph。
repository: weijie567/mini-agent
remote: origin
head_branch: codex/e2e01-cycle2-w9-initial-ru
base_branch: integration/e2e01-cycle2
base_sha: 48dd7bca378fdf2496f12fd86e2b7c7cebdc96f2
base_tree: 9987534ef7a05603102f97b5ef0f5d789d14e5af
planning_control_base_sha: 48dd7bca378fdf2496f12fd86e2b7c7cebdc96f2
planning_control_base_tree: 9987534ef7a05603102f97b5ef0f5d789d14e5af
worktree_id: e2e01-cycle2-w9-initial-ru
agent_role: runtime-engineer
writer: cycle2-core-request-understanding-owner
pull_request_base: integration/e2e01-cycle2
pull_request_mode: draft until independent exact-head review PASS; never use admin bypass
owned_files:
  - src/mini_agent/core/request_understanding.py
  - src/mini_agent/core/request_processing.py
  - tests/component/core/test_request_understanding_contract.py
  - tests/component/core/test_request_processing.py
forbidden_files:
  - all repository files outside the exact four-file owned_files allowlist
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
  - Intent Design Reference open TaskDeltaCandidate/InputBinding rules
  - Cycle 2 Spec product_description vocabulary, search routing and first-turn real Runtime graph
  - reviewed Gate P2-A8 exact owner ruling
read_first:
  - .planning/phases/02-cycle-2-e2e-01/GATE-W9-CORRECTION-EXECUTION-CARD.md
  - docs/architecture/intent-design-reference.md
  - docs/implementation/e2e01-cycle2-implementation-spec.md
  - src/mini_agent/core/request_understanding.py
  - src/mini_agent/core/request_processing.py
required_product_blobs:
  AGENTS.md: 5904da48f4e3a2d95e86ffa04ebe29694caf5c0a
  docs/implementation/e2e01-cycle2-implementation-spec.md: 70c370945ead30be220d127bbbf3fc3c9e4f5dc3
  docs/implementation/e2e01-cycle2-multi-agent-plan.md: 489e428fa07109db8eb1f3df33d093069981deb9
  src/mini_agent/core/request_understanding.py: 9dcedc295129efe8cd6d046983e8f8c391cf1346
  src/mini_agent/core/request_processing.py: d2b7b9f18e3917cc518a2d5eb19c331caeaaa459
  tests/component/core/test_request_understanding_contract.py: 3e9510b3523a7ed0d00b718e42245b835329a88c
  tests/component/core/test_request_processing.py: 4b4e5c4c7554d20acbf47b623a5f04a0a100cd0d
dependencies:
  - exact Gate P2-A8 owner-ruling successor = 48dd7bca378fdf2496f12fd86e2b7c7cebdc96f2
  - imported reviewed Cycle2InputCandidate/InputBindingV2/order-search normalization contracts
core_contract_decisions:
  - add a distinct versioned Cycle2 first-turn output/task-delta type; do not widen or mutate Phase 1 RequestUnderstandingOutputV2/InputCandidate
  - first-turn task delta is exact-one ADD_GOAL with exact-one product_description Cycle2InputCandidate from current message
  - contextualization/source refs/quote/confidence/next move remain bounded and exact; no customer_id, owner ref, verified target, Observation or business fact can appear
  - reducer consumes same-request trusted CustomerContext, authoritative current message, caller-allocated unique identities and trusted UTC time
  - reducer normalizes product_description via existing Core function, emits accepted USER_CLAIM InputBindingV2 and clean ACTIVE Task/RequestUnit at state_version 1
  - next move may request only search_orders with exact normalized product_description and matching base task state; ordinal/shipment_not_received/order_id/multiple or zero candidates fail closed for this reducer
  - output/decision types remain immutable/canonical under existing anti-forgery discipline; caller cannot manually manufacture a trusted accepted graph
contract_changes: YES — additive Core/Intent implementation contract for Cycle 2 first turn; Phase 1 contracts remain unchanged.
security_impact: HIGH / preserves Claim-only authority, same-message quote/source, trusted owner/time, exact-one graph and anti-forgery boundary.
eval_impact: PRE-ACTIVATION COMPONENT SUPPORT ONLY — no artifact/Harness/Case lifecycle/Result; Cases remain CONTRACT_DEFINED.
review_profile:
  planning_review: INDEPENDENT_EXACT_FILE_PASS
  implementation_review: TARGETED_CORE_INTENT_SECURITY
  reviewer_timeout: 20_SECONDS_MAX; interrupt and narrow immediately on timeout
  targeted_risk_checks:
    - no Phase1 public shape or reducer behavior change
    - product_description only; ordinal/shipment/order_id/multi-candidate rejected
    - current-message source/quote and same-request customer context exact
    - no trusted/private/owner/target/business fact in model-visible types
    - InputBindingV2 USER_CLAIM accepted/confirmed and clean Task graph
    - canonical/immutable decision cannot be forged, copied or replayed as authority
    - no Tool dispatch/Runtime write/Application/Infrastructure/Eval mutation
  focused_tests: uv run pytest tests/component/core/test_request_understanding_contract.py tests/component/core/test_request_processing.py -q
  neighbor_tests: uv run pytest tests/component/core/test_task_state_contract.py tests/component/core/test_order_search_contract.py tests/component/core/test_control_gateway.py tests/component/application/test_record_contracts.py tests/component/application/test_ports_contract.py -q
  full_suite_gate: NOT_RUN_FOR_R1A; next canonical full belongs W12
  phase_end_deep_audit: DEFER_TO_W12
verification:
  compile: uv run python -m compileall -q src/mini_agent/core tests/component/core
  focused: exact focused_tests command
  neighbor: exact neighbor_tests command
  diff_check: git diff --check 48dd7bca378fdf2496f12fd86e2b7c7cebdc96f2...HEAD
  allowlist: git diff --name-only exact base...HEAD equals exact four-file owned_files set
  full: NOT_RUN_BY_REVIEW_PROFILE
required_checks:
  - exact base/tree/blobs/protection/branch absence/clean preflight PASS
  - positive first-turn product description plus wrong type/source/quote/identity/shape negative tests
  - existing Phase 1 order-id tests unchanged and PASS
  - compile/focused/neighbor/diff/four-file containment/commit containment PASS
  - bounded independent exact-head review closes BLOCK/HIGH and disposes MEDIUM
done_when:
  - reviewed exact-four-file PR merges and successor is recorded as B_C2_W9_INITIAL_RU
  - R1 is refrozen from the real successor; Cases remain CONTRACT_DEFINED
rollback:
  - before merge close PR and retain clean blocked R1 evidence
  - after merge revert this exact additive Core packet before R1/R2/02-15 depend on it
  - never repair by Application parsing, Runtime preseed, direct DB/bootstrap writes or widening Phase1 types
handoff_to: tech-lead
handoff_format: .planning/phases/02-cycle-2-e2e-01/02-15R1A-PLAN.md#handoff
output_barrier: B_C2_W9_INITIAL_RU
```

## Tasks

1. RED：证明现有首轮不能表达product_description，并加入positive/negative contract tests。
2. GREEN：增加distinct Cycle2 output与pure initial reducer，复用现有normalization和
   InputBindingV2；Phase1路径不变。
3. VERIFY：compile、focused、neighbor、exact-four-file containment与bounded review。

## Handoff

报告exact identity、四文件、first-turn output/reducer、focused/neighbor结果、review与
`B_C2_W9_INITIAL_RU`；明确Application/Infrastructure/HTTP/Runtime write/Eval lifecycle
均未推进，R1必须重新冻结。
