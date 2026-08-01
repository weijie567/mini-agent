---
phase: 02-cycle-2-e2e-01
plan: 02-04R
type: remediation
wave: W3R
depends_on:
  - B_C2_INPUT_BINDING_V2
files_modified:
  - src/mini_agent/core/tool_system.py
  - src/mini_agent/core/control_gateway.py
  - tests/component/core/test_tool_system_contract.py
  - tests/component/core/test_control_gateway.py
autonomous: false
requirements:
  - E2E01-02
  - E2E01-03
  - E2E01-05
  - E2E01-06
user_setup: []
must_haves:
  truths:
    - "v1 GateDecision / AuthorizedToolCommand 与 Phase 1 direct get_order 行为保持兼容；新增 v2 类型和 Gateway 路径在 cutover 前 inactive。"
    - "argument_binding_refs 只含 current RequestUnit InputBindingV2 refs；verified target 使用独立 UUID logical identity，并在 GateDecisionV2 → AuthorizedToolCommandV2 → ToolCallRecordV2 精确复制。"
    - "selected get_order、direct get_order、get_shipment 与 search_orders 四条路径不可混用、fallback 或从摘要/订单号反推 target。"
    - "Gateway 唯一 Claim 名为 shipment_not_received，保持 strict bool Claim，不成为 target、Observation 或工具参数。"
  artifacts:
    - "GateDecisionV2、AuthorizedToolCommandV2、exact v1 Gate conversion 与 target-preserving dispatch/progress contract。"
    - "selected/direct/shipment fail-closed Gateway component vectors。"
  key_links:
    - "B_C2_INPUT_BINDING_V2 → reviewed 02-04R → B_C2_SELECTED_TARGET_GATEWAY。"
    - "02-05R 必须从真实 B_C2_SELECTED_TARGET_GATEWAY successor 重新冻结，不与本 Packet 同 base 并行。"
---

# Phase 2 Plan 02-04R｜Selected-target Gateway completion

> **EXACT TASK PACKET / W3R TARGETED_SECURITY**
>
> 本 Packet 以 reviewed 02-02R 的真实 merge successor 为唯一 base。独立 planning
> review `PASS` 且本 Plan merge 前不得创建 implementation Worktree。02-05R 因
> exact-type import 依赖改为等待本 Packet reviewed successor，不再从同一 base 并行。

## 目标与边界

在 Tool owner 与 Control Gateway 中实现 inactive v2 target/binding 分域，修复旧 Cycle 2
helper 把 target 混入 `argument_binding_refs`、只允许 direct `get_order`、以及旧 Claim
名的问题。现有 Gateway/Gate/Command/ToolCall v2 identity 已使用 UUID；本 Packet 保持
该 logical type，使 Application neighbor 与既有 inactive ToolCallV2 shape 兼容。
Task State `selected_target_ref: StrictOpaqueRef` 只作为持久化文本边界：02-05R 必须生成
新的 UUID，并保存其 canonical lowercase text，且满足 `str(UUID(text)) == text` 无损
round-trip；禁止从 `owner_scoped_order_target_ref`、摘要或 payload 哈希推导 target。
v1 records、active codec、Runtime
dispatch、Application CAS 与 migration 均不切换。本 Packet 只闭合 Gate→Command 与
ToolCallV2 target type/dispatch facts；三者 durable insert/CAS exact-copy 由依赖本
successor 的 02-05R Application command/Port 拥有。

## Exact Task Packet

```yaml
task_id: 02-04R
goal: 实现 inactive GateDecisionV2/AuthorizedToolCommandV2 与 selected-target Gateway fail-closed 路径，严格分离 InputBinding refs 和 verified target。
repository: weijie567/mini-agent
remote: origin
head_branch: codex/e2e01-cycle2-selected-target-gateway
base_branch: integration/e2e01-cycle2
base_sha: 5efd8fabc5c7af5100e10535e983c424e3fd7ad4
base_tree: 5a5b3081bb816f5b276b53de9922173290c9f9ca
planning_control_base_sha: 5efd8fabc5c7af5100e10535e983c424e3fd7ad4
planning_control_base_tree: 5a5b3081bb816f5b276b53de9922173290c9f9ca
worktree_id: e2e01-cycle2-selected-target-gateway
agent_role: runtime-engineer
writer: runtime-engineer-control-gateway
pull_request_base: integration/e2e01-cycle2
pull_request_mode: draft until independent final exact-head review PASS; never use admin bypass
owned_files:
  - src/mini_agent/core/tool_system.py
  - src/mini_agent/core/control_gateway.py
  - tests/component/core/test_tool_system_contract.py
  - tests/component/core/test_control_gateway.py
forbidden_files:
  - all repository files outside the exact four-file owned_files allowlist
  - src/mini_agent/core/task_state.py
  - src/mini_agent/core/request_understanding.py
  - src/mini_agent/core/request_processing.py
  - src/mini_agent/application/**
  - src/mini_agent/infrastructure/**
  - src/mini_agent/runtime.py
  - src/mini_agent/bootstrap.py
  - tests/** except the exact two owned Core test files
  - evals/**
  - alembic/**
  - docs/**
  - .planning/**
  - pyproject.toml
  - uv.lock
  - compose.yaml
  - AGENTS.md
  - graphify-out/**
canonical_inputs:
  - AGENTS.md sections 3-8
  - PROJECT_DIRECTION.md sections 8-9
  - docs/architecture/intent-design-reference.md sections 10.4.1 and 10.7
  - docs/architecture/tool-calling-design-reference.md sections 8.2-8.3 and 10
  - docs/architecture/memory-design-reference.md Claim / target / Observation boundaries
  - docs/implementation/e2e01-cycle2-implementation-spec.md sections 7.2.1.1, 7.4, 7.5, 7.13
  - docs/implementation/e2e01-cycle2-multi-agent-plan.md slot 02-04R
read_first:
  - AGENTS.md sections 3-8
  - docs/architecture/intent-design-reference.md sections 10.4-10.7
  - docs/architecture/tool-calling-design-reference.md sections 8.2-8.3 and 10
  - docs/implementation/e2e01-cycle2-implementation-spec.md sections 7.4-7.5 and 7.13
  - docs/implementation/e2e01-cycle2-multi-agent-plan.md slot 02-04R
  - src/mini_agent/core/task_state.py
  - src/mini_agent/core/tool_system.py
  - src/mini_agent/core/control_gateway.py
  - tests/component/core/test_tool_system_contract.py
  - tests/component/core/test_control_gateway.py
required_product_blobs:
  AGENTS.md: 5904da48f4e3a2d95e86ffa04ebe29694caf5c0a
  PROJECT_DIRECTION.md: ed0ae8482c2d43278a1dd984d5ff55da5265cfda
  docs/architecture/intent-design-reference.md: bfe90f6afa8cd377e8fbcf5f8bf6cdecd570f5a6
  docs/architecture/tool-calling-design-reference.md: c696e172da82f9343a50f563922dfbd4abe29509
  docs/architecture/memory-design-reference.md: fdcdd3c751eb03b7462257cfd62354c9c2917a69
  docs/implementation/e2e01-cycle2-implementation-spec.md: 57ec11693e74f52326e44ebb961ff009a48375be
  docs/implementation/e2e01-cycle2-multi-agent-plan.md: 529f3023272aa6f93d8d650d01d0d6193ce6a6d5
  src/mini_agent/core/task_state.py: eb6b429b4e44b58a848faf476681a610670ca83b
  src/mini_agent/core/tool_system.py: e49a453a292160d877fa999b83091a932ec5f79e
  src/mini_agent/core/control_gateway.py: 51cb11f1a5ff04410512a26d4ff1e689b20f3b38
  tests/component/core/test_tool_system_contract.py: be0bc677b57a6d14bb8decd3843c688d6194c073
  tests/component/core/test_control_gateway.py: c061e003917ecc8172e020adaa9d1375362f7c60
dependencies:
  - exact B_C2_INPUT_BINDING_V2 = 5efd8fabc5c7af5100e10535e983c424e3fd7ad4
  - exact B_C2_INPUT_BINDING_V2 tree = 5a5b3081bb816f5b276b53de9922173290c9f9ca
  - PR #223 reviewed feature/overlay PASS and merge tree equals reviewed overlay tree
  - InputBindingV2 and convert_input_binding_v1_to_v2 are inactive Core contracts; active codec remains p0.v1
  - 02-05R exact-type dependency is unresolved at this base and must wait for this Packet's reviewed successor
contract_changes: NONE — implement the active W3R owner ruling; keep the existing UUID logical target and require only its lossless canonical text at the SelectionRecord persistence boundary.
security_impact: HIGH / TARGET AUTHORIZATION — reject mixed refs, stale/foreign/wrong-target closure, public/model target authority, coercion, target inference and rejected-Gate target retention.
eval_impact: COMPONENT ONLY — add deterministic Tool/Gateway vectors; create no Eval artifact, Case activation, Result or lifecycle transition.
review_profile:
  planning_review: INDEPENDENT_EXACT_FILE_PASS
  implementation_review: TARGETED_SECURITY
  targeted_risk_checks:
    - v1 GateDecision/AuthorizedToolCommand and direct get_order compatibility
    - Gate-to-Command exact target propagation and ToolCallV2 target-type compatibility
    - UUID logical target with canonical lowercase text round-trip at SelectionRecord boundary
    - direct versus selected get_order non-fallback
    - get_shipment binding/target separation
    - shipment_not_received strict Claim vocabulary
    - progress identity includes target outside binding refs
    - rejected or malformed candidate creates no authorization identity
  focused_tests: uv run pytest tests/component/core/test_tool_system_contract.py tests/component/core/test_control_gateway.py -q
  neighbor_tests: uv run pytest tests/component/core/test_task_state_contract.py tests/component/core/test_candidate_selection_contract.py tests/component/core/test_shipment_contract.py tests/component/application/test_record_contracts.py -q
  full_suite_gate: NOT_RUN_FOR_02_04R; next canonical full is W6 exit
  phase_end_deep_audit: W12_ONLY
verification:
  focused: uv run pytest tests/component/core/test_tool_system_contract.py tests/component/core/test_control_gateway.py -q
  neighbor: uv run pytest tests/component/core/test_task_state_contract.py tests/component/core/test_candidate_selection_contract.py tests/component/core/test_shipment_contract.py tests/component/application/test_record_contracts.py -q
  compile: uv run python -m compileall -q src/mini_agent/core/tool_system.py src/mini_agent/core/control_gateway.py tests/component/core/test_tool_system_contract.py tests/component/core/test_control_gateway.py
  diff_check: git diff --check 5efd8fabc5c7af5100e10535e983c424e3fd7ad4...HEAD
  migration: NOT_RUN — 02-10 owns physical migration/cutover
  integration: NOT_RUN_PER_PACKET
  full: NOT_RUN_BY_REVIEW_PROFILE
latest_integration_overlay: REQUIRED — before merge replay the exact four-file patch on current integration, prove frozen dependency blobs unchanged, rerun focused/neighbor only when a dependency changed, and obtain independent targeted exact-head overlay review PASS.
required_checks:
  - exact base/tree, required blobs, branch/worktree absence, clean state and branch protection preflight PASS
  - changed files equal the exact four-file allowlist; no Application, persistence, migration, Runtime, Eval, docs/planning or Graphify changes
  - v1 GateDecision and AuthorizedToolCommand model fields/behavior remain compatible; direct Phase 1 get_order remains order-id binding plus null target
  - additive GateDecisionV2 and AuthorizedToolCommandV2 use an independent UUID verified_target_ref and reject target inside argument_binding_refs
  - exact GateDecision v1-to-v2 conversion requires exact validated v1 input, preserves every v1 field and sets target only to null
  - rejected GateDecisionV2 always stores null target and cannot produce AuthorizedToolCommandV2; accepted search/direct paths also keep target null
  - accepted selected get_order uses exactly one current candidate_ordinal InputBindingV2 ref, one exact current non-null target, matching order_id and result Task/RU version
  - accepted direct get_order uses exactly one current order_id InputBindingV2 ref and null target; selected/direct refs or target cannot mix/fallback
  - accepted get_shipment uses exactly one current order_id InputBindingV2 ref and one independent exact current target; Claim alone cannot authorize it
  - target closure verifies owner, Task, RequestUnit, state version, currentness, Observation/manifest provenance and exact order_id; zero/multiple/missing/mismatch rejects
  - search_orders uses one product_description binding and null target; shipment_not_received is strict bool Claim, not tool argument/target/fact; not_received_claim rejects
  - Cycle2 progress identity carries target separately, so binding refs stay pure while different targets are distinguishable
  - accepted GateDecisionV2 to AuthorizedToolCommandV2 copies gate/tool/arguments/binding refs/version/target exactly; model cannot supply target
  - ToolCallRecordV2 and Cycle2 dispatch facts retain the same UUID target type; existing Application neighbor fixtures stay compatible; durable three-way insert and canonical SelectionRecord text are 02-05R-owned
  - raw constructed/subclass/coerced/extra values fail closed with no tool_call_id, command or Handler dispatch
  - focused/neighbor/compile/diff checks PASS; canonical full accurately NOT RUN
  - independent final exact-head review PASS with 0 BLOCK/HIGH; MEDIUM fixed or accepted with evidence; LOW/INFO recorded
  - PR targets integration/e2e01-cycle2 and remote head equals reviewed exact head
done_when:
  - all four tool/path shapes and target/binding separation satisfy targeted positive/negative vectors without active cutover
  - focused/neighbor transcripts and feature/overlay exact-head reviews PASS
  - reviewed PR is serially merged and exact successor is frozen as B_C2_SELECTED_TARGET_GATEWAY
rollback:
  - before merge close the draft PR and retain review evidence
  - after merge use a normal exact four-file revert PR before 02-05R or any codec/migration consumer merge
  - never reset, force-push, delete evidence, restore mixed refs, infer target or add fallback as rollback
handoff_to: tech-lead
handoff_format: .planning/phases/02-cycle-2-e2e-01/02-04R-PLAN.md#handoff
output_barrier: B_C2_SELECTED_TARGET_GATEWAY
```

## Tasks

### Task 1 — RED：冻结 v1 compatibility 与四路径 oracle

先增加 v1 schema/behavior snapshot、v2 target type/propagation、四条路径正向和
stale/foreign/mixed/coerced negative vectors。旧测试中把 target 塞进 binding refs 或接受
`not_received_claim` 的期望必须改为 canonical fail-closed，不得保留双行为。

### Task 2 — GREEN：additive Tool v2 contract

新增 GateDecisionV2、AuthorizedToolCommandV2 和 exact v1 Gate conversion；保持现有
inactive ToolCallRecordV2/dispatch facts UUID target。SelectionRecord textual UUID 的
生成/round-trip validation 明确留给 02-05R。v1 classes 不修改，不增加 active codec 或
Handler route。

### Task 3 — GREEN：Gateway selected-target 与 hardening

按 direct/selected/shipment/search 四路径重写 binding/target验证与 progress identity，
accepted Gate 到 command 只 exact-copy，所有 reject/malformed path 均无授权 identity。
完成 focused/neighbor/compile/containment 后做窄范围 TARGETED_SECURITY review。

## W3R gate

```text
product base == 5efd8fabc5c7af5100e10535e983c424e3fd7ad4
AND product tree == 5a5b3081bb816f5b276b53de9922173290c9f9ca
AND PR #223 state == MERGED
AND this exact Plan is present in reviewed planning provenance
AND all required product blobs equal the frozen literals
AND implementation branch/worktree do not already exist
AND planning review verdict == PASS
```

任一条件不成立即 `BLOCK`；不得扩大 allowlist、在 Application 复制 Tool owner 类型、
从 owner ref/摘要推导 UUID、接受非 canonical textual UUID、或让 02-05R 绕过本 Packet successor。

## Handoff

只报告 exact base/head/tree、branch/PR、实际四文件、focused/neighbor结果、targeted
review disposition、target identity、contract/security/Eval impact与下一 barrier。
明确标记 active codec/Runtime/Application/migration/full/Eval lifecycle 均未推进。
