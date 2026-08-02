---
phase: 02-cycle-2-e2e-01
plan: 02-15R1D
type: implementation
wave: W9
depends_on:
  - B_C2_W9_UNIQUE_TARGET_CONTRACT
files_modified:
  - src/mini_agent/core/task_state.py
  - src/mini_agent/core/request_processing.py
  - tests/component/core/test_candidate_selection_contract.py
  - tests/component/core/test_request_processing.py
autonomous: false
requirements: [E2E01-02, E2E01-05]
user_setup: []
must_haves:
  truths:
    - "OrderCandidateAutoTargetRecord只从exact current owner/query-binding/UNIQUE CandidateSet/Search Observation/private mapping与caller-allocated fresh UUID形成，不执行IO也不从public或model值制造authority。"
    - "UNIQUE get_order route只使用current product_description binding作为argument_binding_ref，并以独立verified_target_ref绑定closed target/Observation facts；不得伪造order_id USER_CLAIM binding。"
    - "wrong-owner、MULTIPLE、stale/superseded、mapping或source/version不唯一、UUID复用、target/order_id/NextMove替换全部fail closed。"
    - "Phase 1 direct order-id与Cycle 2 ordinal selected-target routes保持兼容；本Packet不写Application、Infrastructure、HTTP、Eval或持久化。"
  artifacts:
    - "Core OrderCandidateAutoTargetRecord exact model and pure builder。"
    - "Core route_cycle2_unique_next_move exact Gateway-candidate reducer。"
    - "Component proofs for positive closure and fail-closed mutations。"
  key_links:
    - "B_C2_W9_UNIQUE_TARGET_CONTRACT → reviewed 02-15R1D → B_C2_W9_UNIQUE_TARGET_CORE → third-refrozen 02-15R1。"
---

# Phase 2 Plan 02-15R1D｜UNIQUE auto-target Core contract

> **EXACT TASK PACKET / W9 CORE_TARGET_OWNER_CORRECTION**
>
> PR #282/#283 已 reviewed 完成 R1C planning/implementation，并形成真实
> `B_C2_W9_UNIQUE_TARGET_CONTRACT = dd1e972763534198e6d2601baa2b60bb3312ad80` /
> tree `394d022adfa80ef4d935216393fecf19892d4316`。本Packet只实现该active scoped
> contract的Core record/factory/route；旧R1 checkpoint继续unpublished，必须等
> R1D reviewed successor后第三次重冻结。Cases继续为`CONTRACT_DEFINED`。

## Exact Task Packet

```yaml
task_id: 02-15R1D
goal: 实现OrderCandidateAutoTargetRecord exact Core model/pure builder及UNIQUE get_order Gateway candidate route，不制造或扩大target authority。
repository: weijie567/mini-agent
remote: origin
head_branch: codex/e2e01-cycle2-w9-unique-target-core
base_branch: integration/e2e01-cycle2
base_sha: dd1e972763534198e6d2601baa2b60bb3312ad80
base_tree: 394d022adfa80ef4d935216393fecf19892d4316
planning_control_base_sha: dd1e972763534198e6d2601baa2b60bb3312ad80
planning_control_base_tree: 394d022adfa80ef4d935216393fecf19892d4316
worktree_id: e2e01-cycle2-w9-unique-target-core
agent_role: runtime-engineer
writer: cycle2-core-target-owner
pull_request_base: integration/e2e01-cycle2
pull_request_mode: draft until independent exact-head review PASS; never use admin bypass
owned_files:
  - src/mini_agent/core/task_state.py
  - src/mini_agent/core/request_processing.py
  - tests/component/core/test_candidate_selection_contract.py
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
  - Cycle 2 Spec sections 2.4, 3.2, 7.3.1-7.3.4 and 7.13
  - Intent sections 10.4/10.7, Memory section 14.4 and Tool sections 8.2/8.3 referenced by the scoped Spec
  - existing Cycle2VerifiedOrderTargetFacts/Cycle2TargetObservationFacts and Control Gateway closure
read_first:
  - .planning/phases/02-cycle-2-e2e-01/02-15R1D-PLAN.md
  - docs/implementation/e2e01-cycle2-implementation-spec.md
  - src/mini_agent/core/task_state.py
  - src/mini_agent/core/request_processing.py
  - src/mini_agent/core/control_gateway.py
  - src/mini_agent/core/memory.py
  - tests/component/core/test_candidate_selection_contract.py
  - tests/component/core/test_request_processing.py
required_product_blobs:
  AGENTS.md: 5904da48f4e3a2d95e86ffa04ebe29694caf5c0a
  docs/implementation/e2e01-cycle2-implementation-spec.md: b0d3ad29a86365903b1c2c3af3f809556c8a9c2d
  docs/implementation/e2e01-cycle2-multi-agent-plan.md: 93cca906cb96bd9df36769a856ab7512a4bcf08c
  src/mini_agent/core/task_state.py: eb6b429b4e44b58a848faf476681a610670ca83b
  src/mini_agent/core/request_processing.py: 08025e48bfc617b1f4b9f9f2f5759d2f57c6dab6
  tests/component/core/test_candidate_selection_contract.py: 214d5deca6614761a62eeefe2a072007c708d834
  tests/component/core/test_request_processing.py: 9a3a5f014393e75f5df6bec7bc6c2b5848157069
dependencies:
  - exact B_C2_W9_UNIQUE_TARGET_CONTRACT = dd1e972763534198e6d2601baa2b60bb3312ad80
  - imported reviewed Cycle 2 InputBindingV2, CandidateSet/Search Observation and selected-target Gateway contracts
core_contract_decisions:
  - add ORDER_CANDIDATE_AUTO_TARGET_RECORD_SCHEMA_VERSION and strict OrderCandidateAutoTargetRecord in task_state.py with the exact R1C field set
  - verified_target_ref is canonical fresh UUIDv4 record identity; self/same-graph identity alias and invalid supersession are rejected
  - add build_cycle2_unique_auto_target_record pure builder in request_processing.py; caller supplies trusted current graph, already owner-resolved target ref/order_id, fresh UUID and trusted time; builder performs no IO
  - builder requires exact UNIQUE CandidateSet/Search Observation closure, exact-one product_description query binding, source ToolCall/binding/version equality, exact private target mapping, base/result version and verified_at equality
  - add route_cycle2_unique_next_move; it consumes the committed auto-target record plus exact current Cycle2VerifiedOrderTargetFacts and produces one get_order Cycle2GatewayCandidate
  - route requires argument_binding_refs=(query_input_binding_ref,), verified_target_ref=record identity and arguments.order_id=closed target.order_id at exact result Task version
  - keep route_cycle2_selected_next_move and route_cycle2_continuation_next_move behavior unchanged
contract_changes: YES — additive Core record/builder/route implementing the reviewed R1C scoped contract; no public Phase 1 shape or canonical owner override.
security_impact: CRITICAL / exact target issuance and route authority; no identity/model/private-ref reconstruction.
eval_impact: COMPONENT CONTRACT SUPPORT ONLY — Core tests only; no Case/artifact/Harness/Result/lifecycle mutation.
review_profile:
  planning_review: INDEPENDENT_EXACT_FILE_PASS
  implementation_review: TARGETED_CORE_TARGET_SECURITY
  reviewer_timeout: 20_SECONDS_MAX; interrupt and narrow immediately on timeout
  targeted_risk_checks:
    - UUIDv4 freshness/identity separation and no deterministic target reconstruction
    - owner/Conversation/Task/RequestUnit/query binding/CandidateSet/Observation/mapping/source/version closure
    - MULTIPLE/stale/superseded/wrong-owner/duplicate/target/order-id/next-move mutation rejection
    - Gateway candidate binding refs and verified target remain separate
    - existing ordinal/continuation/direct order-id routes and public Phase 1 models unchanged
  focused_tests: uv run pytest tests/component/core/test_candidate_selection_contract.py tests/component/core/test_request_processing.py -q
  neighbor_tests: uv run pytest tests/component/core/test_control_gateway.py tests/component/core/test_cycle2_memory_contract.py tests/component/core/test_order_search_contract.py tests/component/core/test_task_state_contract.py -q
  full_suite_gate: NOT_RUN_FOR_R1D; W6 already supplied mid-phase canonical full and next canonical full belongs W12
verification:
  compile: uv run python -m compileall -q src/mini_agent/core tests/component/core
  focused: exact focused_tests command
  neighbor: exact neighbor_tests command
  diff_check: git diff --check dd1e972763534198e6d2601baa2b60bb3312ad80...HEAD
  allowlist: git diff --name-only exact base...HEAD equals exact four-file owned_files set
  full: NOT_RUN_BY_REVIEW_PROFILE
required_checks:
  - exact base/tree/blobs/protection/branch absence/clean preflight PASS
  - record/builder/route positive closure and field-by-field negative mutation tests
  - existing selected/continuation/direct routes remain green
  - no Application/Infrastructure/API/bootstrap/Eval/docs/planning/graphify change
  - compile/focused/neighbor/diff/allowlist/commit containment PASS
  - bounded independent exact-head review closes BLOCK/HIGH and disposes MEDIUM
done_when:
  - reviewed exact-four-file PR merges and successor is recorded as B_C2_W9_UNIQUE_TARGET_CORE
  - 02-15R1 third-refreeze may use only the real successor; Cases remain CONTRACT_DEFINED
rollback:
  - before merge close PR and retain exact-head evidence
  - after merge revert this exact additive Core packet before R1/R2 depend on it
  - never repair by weakening UUID/owner/current/mapping/Gateway checks or constructing target authority in Application/Infrastructure
handoff_to: tech-lead
handoff_format: .planning/phases/02-cycle-2-e2e-01/02-15R1D-PLAN.md#handoff
output_barrier: B_C2_W9_UNIQUE_TARGET_CORE
```

## Tasks

1. RED：在两份Core component tests先证明record/builder/route正向闭包及owner/version/
   UUID/mapping/NextMove mutation fail closed。
2. GREEN：只在Core owner两文件增加exact record、pure builder和UNIQUE route；复用
   CandidateSet/Observation/Gateway现有验证，不复制Application或DB逻辑。
3. VERIFY：compile、focused、neighbor、exact-four-file containment与20秒bounded
   independent exact-head review。

## Handoff

报告exact identity、四文件、record/builder/route、focused/neighbor、review findings与
`B_C2_W9_UNIQUE_TARGET_CORE`；明确Application/DB/HTTP/fixture/Eval lifecycle/Result
均未推进，R1 checkpoint仍未发布。
