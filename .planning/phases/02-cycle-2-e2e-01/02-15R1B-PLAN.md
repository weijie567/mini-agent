---
phase: 02-cycle-2-e2e-01
plan: 02-15R1B
type: implementation
wave: W9
depends_on: [B_C2_W9_INITIAL_RU]
files_modified:
  - src/mini_agent/application/read_tool_executor.py
  - tests/component/application/test_read_tool_executor.py
autonomous: false
requirements: [E2E01-02, E2E01-03, E2E01-05, E2E01-06]
user_setup: []
must_haves:
  truths:
    - "read executor可把terminal ToolCall与同attempt已校验ToolResult作为typed envelope返回给Application handler。"
    - "legacy execute()继续只返回ToolCallRecordV2，全部insert/fence/retry/CAS语义与现有调用者不变。"
    - "只有terminal finalize APPLIED才携带ToolResult；timeout/conflict/no-dispatch为None，retry只暴露attempt 2。"
    - "R1B不构造Observation/CandidateSet/Assessment，不修改handler、Port、DB、HTTP或Eval lifecycle。"
  artifacts:
    - "Backward-compatible Cycle2 read execution envelope/API。"
    - "Success/retry/timeout/conflict/legacy component evidence。"
  key_links:
    - "B_C2_W9_R1B_OWNER_APPROVED → reviewed 02-15R1B → B_C2_W9_TYPED_READ_EXECUTION → second-refrozen 02-15R1。"
---

# Phase 2 Plan 02-15R1B｜Cycle 2 typed read-execution envelope

> **EXACT TASK PACKET / W9 APPLICATION_EXECUTOR_OWNER_CORRECTION**
>
> R1A已形成`B_C2_W9_INITIAL_RU`，R1又从真实successor重冻结。writer在成功工具
> 路径接线前证明executor内部typed `ToolResult`未通过public返回面暴露；独立复核
> `CONFIRMED / NOT_FOUND`。one-file owner ruling PR #277批准R1B与34 slots / 16
> wave labels。当前R1两文件dirty checkpoint保持unpublished且未测试/提交。

## Exact Task Packet

```yaml
task_id: 02-15R1B
goal: 为Cycle2ReadToolExecutor增加additive typed result envelope，同时保持legacy execute和全部安全状态机语义。
repository: weijie567/mini-agent
remote: origin
head_branch: codex/e2e01-cycle2-w9-typed-read-execution
base_branch: integration/e2e01-cycle2
base_sha: d978629c119d6b4b61a77281795fac7250b9465b
base_tree: 2878321265f82e5aeecbb0f871d70776eded41a3
planning_control_base_sha: d978629c119d6b4b61a77281795fac7250b9465b
planning_control_base_tree: 2878321265f82e5aeecbb0f871d70776eded41a3
worktree_id: e2e01-cycle2-w9-typed-read-execution
agent_role: runtime-engineer
writer: cycle2-application-read-executor-owner
pull_request_base: integration/e2e01-cycle2
pull_request_mode: draft until independent exact-head review PASS; never use admin bypass
owned_files:
  - src/mini_agent/application/read_tool_executor.py
  - tests/component/application/test_read_tool_executor.py
forbidden_files:
  - all repository files outside exact two-file owned_files allowlist
  - src/mini_agent/application/records.py
  - src/mini_agent/application/ports.py
  - src/mini_agent/application/agent_run_service.py
  - src/mini_agent/core/**
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
  - Tool calling owner result/retry/fence/timeout contracts
  - Cycle 2 Spec retry and business-result authority sections
  - reviewed Gate P2-A9 owner ruling
read_first:
  - src/mini_agent/application/read_tool_executor.py
  - tests/component/application/test_read_tool_executor.py
  - src/mini_agent/application/agent_run_service.py
required_product_blobs:
  AGENTS.md: 5904da48f4e3a2d95e86ffa04ebe29694caf5c0a
  docs/implementation/e2e01-cycle2-implementation-spec.md: 70c370945ead30be220d127bbbf3fc3c9e4f5dc3
  docs/implementation/e2e01-cycle2-multi-agent-plan.md: 34092497df587d94416bb17df64d5c317a0dc6e3
  src/mini_agent/application/read_tool_executor.py: 4f7c0e42893fddf55f9e86eef3c2c59fcfb282f8
  tests/component/application/test_read_tool_executor.py: 833fd3d48f73822ca0eb73e880d0eab791df15ab
dependencies:
  - exact Gate P2-A9 owner-ruling successor = d978629c119d6b4b61a77281795fac7250b9465b
  - imported reviewed ToolCall attempt/fence/finalize/retry contracts
executor_contract_decisions:
  - add immutable RuntimePrivate Cycle2ReadToolExecution with terminal_tool_call and optional tool_result
  - add execute_with_result(CreateToolCallV2Command) using the same existing internal insert/fence/dispatch/retry/finalize path
  - keep execute(CreateToolCallV2Command)->ToolCallRecordV2 as a wrapper returning envelope.terminal_tool_call
  - include only the exact ToolResult already type-validated for the same ToolCall/attempt whose terminal finalize returned APPLIED
  - initialize tool_result absent before dispatch; timeout/synthetic failure, insert/fence/finalize non-APPLIED, recovery/no-dispatch and state invalidation never expose payload
  - recursive retry returns the final attempt envelope only; first transient result is not retained or surfaced
  - envelope is ephemeral Application output, not persistence authority/evidence and not model-visible
contract_changes: YES — additive Application executor return surface; legacy execute contract and Tool lifecycle semantics unchanged.
security_impact: HIGH / prevents payload fabrication, wrong-attempt leakage, CAS-conflict disclosure and Infrastructure contract drift.
eval_impact: PRE-ACTIVATION SUPPORT ONLY — no artifact/Harness/Case lifecycle/Result.
review_profile:
  planning_review: INDEPENDENT_EXACT_FILE_PASS
  implementation_review: TARGETED_TOOL_RESULT_INTEGRITY
  reviewer_timeout: 20_SECONDS_MAX; interrupt and narrow immediately on timeout
  targeted_risk_checks:
    - legacy execute exact return/behavior unchanged
    - ToolResult exact typed validation precedes envelope
    - envelope result belongs to terminal APPLIED same attempt
    - retry exposes only attempt2; timeout/conflict/no-dispatch None
    - no raw exception/payload in Trace and no model-visible/private expansion
    - no R1 checkpoint or non-owned file contamination
  focused_tests: uv run pytest tests/component/application/test_read_tool_executor.py -q
  neighbor_tests: uv run pytest tests/component/application/test_persistence_contract.py tests/component/application/test_agent_run_service.py tests/component/core/test_tool_system_contract.py tests/integration/test_agent_run_service_v2_persistence.py -q
  full_suite_gate: NOT_RUN_FOR_R1B; next canonical full belongs W12
  phase_end_deep_audit: DEFER_TO_W12
verification:
  compile: uv run python -m compileall -q src/mini_agent/application/read_tool_executor.py tests/component/application/test_read_tool_executor.py
  focused: exact focused_tests command
  neighbor: exact neighbor_tests command
  diff_check: git diff --check d978629c119d6b4b61a77281795fac7250b9465b...HEAD
  allowlist: git diff --name-only exact base...HEAD equals exact two-file owned_files set
  full: NOT_RUN_BY_REVIEW_PROFILE
required_checks:
  - exact base/tree/blobs/protection/branch absence/clean preflight PASS
  - success/legacy/retry/timeout/insert-fence-finalize conflict tests PASS
  - existing executor tests unchanged and PASS
  - compile/focused/neighbor/diff/two-file containment/commit containment PASS
  - bounded independent exact-head review closes BLOCK/HIGH and disposes MEDIUM
done_when:
  - reviewed exact-two-file PR merges and successor is recorded as B_C2_W9_TYPED_READ_EXECUTION
  - R1 is second-refrozen from the real successor; Cases remain CONTRACT_DEFINED
rollback:
  - before merge close PR and retain R1 dirty checkpoint unpublished
  - after merge revert exact additive executor packet before R1 depends on it
  - never repair by Infrastructure payload reconstruction, bypassing finalize CAS or returning unvalidated/earlier-attempt payload
handoff_to: tech-lead
handoff_format: .planning/phases/02-cycle-2-e2e-01/02-15R1B-PLAN.md#handoff
output_barrier: B_C2_W9_TYPED_READ_EXECUTION
```

## Tasks

1. RED：success/legacy/retry/timeout/conflict envelope tests。
2. GREEN：additive envelope + execute_with_result；legacy execute wrapper。
3. VERIFY：compile、focused、neighbor、two-file containment与bounded review。

## Handoff

报告exact identity、两文件、focused/neighbor、review与`B_C2_W9_TYPED_READ_EXECUTION`；
明确R1 checkpoint、Infrastructure、HTTP、Eval lifecycle均未推进。
