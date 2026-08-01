---
phase: 02-cycle-2-e2e-01
plan: 02-02R
type: remediation
wave: W3R
depends_on:
  - B_C2_W3R_RULING
files_modified:
  - src/mini_agent/core/task_state.py
  - tests/component/core/test_task_state_contract.py
autonomous: false
requirements:
  - E2E01-02
  - E2E01-03
  - E2E01-05
  - E2E01-06
user_setup: []
must_haves:
  truths:
    - "InputBinding v1 owner model 与 active codec 保持不变；新增 InputBindingV2 仍只是 USER_CLAIM，不包含 Observation 或 verified target。"
    - "v2 只接受 order_id/string、product_description/normalized string、candidate_ordinal/strict int 1..5、shipment_not_received/strict bool 四个 exact name/value 组合。"
    - "v1→v2 只复制已通过 exact v1 owner model 的 order_id payload；不推断、补写或转换三个 v2-only name。"
    - "本 Packet 只形成 inactive Core contract；不切换 writer/reader/codec，不写 migration、Application CAS、Gateway 或 Eval artifact。"
  artifacts:
    - "InputBindingV2 与 deterministic exact-v1 conversion helper。"
    - "focused contract tests 覆盖 strict matrix、v1 compatibility、conversion identity 与 Claim boundary。"
  key_links:
    - "B_C2_W3R_RULING → reviewed 02-02R → B_C2_INPUT_BINDING_V2。"
    - "02-04R/02-05R 只在 B_C2_INPUT_BINDING_V2 后冻结；02-02R 不提前实现它们。"
---

# Phase 2 Plan 02-02R｜Cycle 2 accepted InputBinding completion

> **EXACT TASK PACKET / W3R TARGETED_CONTRACT**
>
> 本 Packet 以 owner-ruling PR #221 的真实 merge successor 为唯一 product base。
> 独立 exact-file planning review `PASS` 且本 Plan merge 前，不得创建 implementation
> branch / Worktree。实现只运行 focused / neighbor tests；canonical full 延至 W6。

## 目标与边界

在 Core Task State owner 中新增 inactive-until-cutover `InputBindingV2` 与纯确定性
v1→v2 conversion helper。v1 `InputBinding` 的字段、validator 与 public behavior 必须
保持兼容；active `input_binding_record.p0.v1` codec、writer、reader 与 physical row
均不切换。本 Packet 不拥有 continuation CAS、selected target、Gate/ToolCall、migration
或 Runtime routing。

## Exact Task Packet

```yaml
task_id: 02-02R
goal: 在不改变 v1 owner model 与 active persistence 的前提下，实现 Cycle 2 InputBindingV2 四项 strict name/value closure及 exact order-id identity conversion。
repository: weijie567/mini-agent
remote: origin
head_branch: codex/e2e01-cycle2-input-binding-v2-core
base_branch: integration/e2e01-cycle2
base_sha: ed61f4d4da9c75386aa96857a5e77e06de4c4804
base_tree: 02c06f70459cf9593946c599a2de33d1c5a15a91
planning_control_base_sha: ed61f4d4da9c75386aa96857a5e77e06de4c4804
planning_control_base_tree: 02c06f70459cf9593946c599a2de33d1c5a15a91
worktree_id: e2e01-cycle2-input-binding-v2-core
agent_role: runtime-engineer
writer: runtime-engineer-core-task-state
pull_request_base: integration/e2e01-cycle2
pull_request_mode: draft until independent final exact-head review PASS; never use admin bypass
owned_files:
  - src/mini_agent/core/task_state.py
  - tests/component/core/test_task_state_contract.py
forbidden_files:
  - all repository files outside the exact two-file owned_files allowlist
  - src/mini_agent/application/**
  - src/mini_agent/core/control_gateway.py
  - src/mini_agent/core/tool_system.py
  - src/mini_agent/core/request_understanding.py
  - src/mini_agent/core/request_processing.py
  - src/mini_agent/infrastructure/**
  - src/mini_agent/runtime.py
  - src/mini_agent/bootstrap.py
  - tests/** except tests/component/core/test_task_state_contract.py
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
  - docs/architecture/intent-design-reference.md section 10.4.1
  - docs/architecture/memory-design-reference.md Claim / Observation / durable-record boundaries
  - docs/implementation/e2e01-cycle2-implementation-spec.md sections 7.2.1.1 and 7.13
  - docs/implementation/e2e01-cycle2-multi-agent-plan.md slot 02-02R and W3R review profile
read_first:
  - AGENTS.md sections 3-8
  - docs/architecture/intent-design-reference.md sections 10.4-10.7
  - docs/architecture/memory-design-reference.md Claim / Observation boundaries
  - docs/implementation/e2e01-cycle2-implementation-spec.md sections 7.2.1.1 and 7.13
  - docs/implementation/e2e01-cycle2-multi-agent-plan.md slot 02-02R
  - src/mini_agent/core/common.py
  - src/mini_agent/core/order_search.py
  - src/mini_agent/core/task_state.py
  - tests/component/core/test_task_state_contract.py
required_product_blobs:
  AGENTS.md: 5904da48f4e3a2d95e86ffa04ebe29694caf5c0a
  PROJECT_DIRECTION.md: ed0ae8482c2d43278a1dd984d5ff55da5265cfda
  docs/architecture/intent-design-reference.md: bfe90f6afa8cd377e8fbcf5f8bf6cdecd570f5a6
  docs/architecture/memory-design-reference.md: fdcdd3c751eb03b7462257cfd62354c9c2917a69
  docs/implementation/e2e01-cycle2-implementation-spec.md: 57ec11693e74f52326e44ebb961ff009a48375be
  docs/implementation/e2e01-cycle2-multi-agent-plan.md: 529f3023272aa6f93d8d650d01d0d6193ce6a6d5
  src/mini_agent/core/common.py: b63030e628a7552815ef317b4a1f2403955de034
  src/mini_agent/core/order_search.py: 2c8b84ed82f982bc46b0ca4c2141f357b3d4eba4
  src/mini_agent/core/task_state.py: 71576cbc4a691befaa0c56173358e726564c9f3e
  tests/component/core/test_task_state_contract.py: 466a694cede64f7ae55ce0fe8a0a7e7b41d90192
dependencies:
  - exact B_C2_W3R_RULING = ed61f4d4da9c75386aa96857a5e77e06de4c4804
  - exact B_C2_W3R_RULING tree = 02c06f70459cf9593946c599a2de33d1c5a15a91
  - PR #221 squash parent is f484a5051d226eb0529646054c61b8539c603f4c and its merge tree equals reviewed remote-head tree
  - owner ruling review and exact remote transport review both PASS with no open BLOCK/HIGH
  - current integration branch protection requires PR flow, enforce-admins, linear history and conversation resolution; force-push/deletion disabled
contract_changes: NONE — implement the active owner-ruling contract exactly; do not alter InputBinding v1, vocabulary, version semantics, CAS, Gateway or migration contract.
security_impact: HIGH / CLAIM-FACT SEPARATION — strict type/name matrix, exact provenance copy, no verified target/business fact, no coercion or inferred authority.
eval_impact: COMPONENT ONLY — add deterministic Core contract vectors; create no EvalCase, artifact, Result, Case activation or lifecycle transition.
review_profile:
  planning_review: INDEPENDENT_EXACT_FILE_PASS
  implementation_review: TARGETED_CONTRACT
  targeted_risk_checks:
    - InputBinding v1 schema and behavior unchanged
    - v2 exact name/value cross-validation
    - strict bool/int/string non-coercion
    - normalized product description exactness and Unicode-scalar bound
    - Claim remains separate from Observation and verified target
    - v1-to-v2 conversion is exact identity copy with no defaults or inference
    - inactive contract only; no active codec or writer cutover
  focused_tests: uv run pytest tests/component/core/test_task_state_contract.py -q
  neighbor_tests: uv run pytest tests/component/core/test_order_search_contract.py tests/component/core/test_candidate_selection_contract.py tests/component/application/test_persistence_contract.py -q
  full_suite_gate: NOT_RUN_FOR_02_02R; next canonical full is W6 exit
  phase_end_deep_audit: W12_ONLY
verification:
  focused: uv run pytest tests/component/core/test_task_state_contract.py -q
  neighbor: uv run pytest tests/component/core/test_order_search_contract.py tests/component/core/test_candidate_selection_contract.py tests/component/application/test_persistence_contract.py -q
  compile: uv run python -m compileall -q src/mini_agent/core/task_state.py tests/component/core/test_task_state_contract.py
  diff_check: git diff --check ed61f4d4da9c75386aa96857a5e77e06de4c4804...HEAD
  migration: NOT_RUN — 02-10 owns physical migration/cutover
  integration: NOT_RUN_PER_PACKET
  full: NOT_RUN_BY_REVIEW_PROFILE
latest_integration_overlay: REQUIRED — before merge apply the exact two-file patch to the then-current integration head, prove owner blobs/ancestry, rerun focused/neighbor when upstream changed a dependency, and obtain independent targeted exact-head overlay review PASS.
required_checks:
  - exact base/tree, required blobs, branch/worktree absence, clean state and branch protection preflight PASS
  - changed files equal the exact two-file owned_files allowlist; no generated, planning, docs, persistence, migration or Graphify changes
  - InputBinding v1 model_fields, JSON schema, validation behavior and representative model_dump stay byte/structurally compatible
  - InputBindingV2 has the same audit/provenance/validation/confirmation/time/supersession fields and no verified_target_ref, Observation, owner scope or business-fact field
  - order_id accepts only strict O-[0-9]{4,20} string; product_description accepts only exact normalize_product_description output of 1..80 Unicode scalars
  - candidate_ordinal accepts only exact int 1..5, rejecting bool, numeric string, float and out-of-range values
  - shipment_not_received accepts only exact bool and rejects int/string; not_received_claim is rejected
  - authority is exact USER_CLAIM, validation exact ACCEPTED and confirmed_by_user exact true for every scoped name
  - created_at/updated_at are UTC and ordered; source_refs remain non-empty; supersedes semantics remain an optional UUID
  - conversion accepts only an exact InputBinding v1 order_id instance, copies every payload field exactly and produces InputBindingV2/order_id
  - conversion rejects subclass/foreign/malformed/v2 input and never supplies a v2-only name, target, fact, default or normalization
  - no active codec registry/version, writer/reader, Application command/Port, Gateway, Runtime route, migration or Eval lifecycle changes
  - focused/neighbor/compile/diff checks PASS; canonical full accurately NOT RUN
  - independent final exact-head review PASS with 0 BLOCK/HIGH; MEDIUM fixed or accepted with evidence; LOW/INFO recorded
  - PR targets integration/e2e01-cycle2 and remote head equals reviewed exact head
done_when:
  - inactive InputBindingV2 and exact conversion satisfy every targeted vector without changing v1 active behavior
  - focused/neighbor transcripts and targeted exact-head review PASS exist on the final head
  - reviewed PR is serially merged and exact successor is frozen as B_C2_INPUT_BINDING_V2
rollback:
  - before merge close the draft PR and retain planning/review evidence
  - after merge use a normal exact two-file revert PR before any 02-04R/02-05R consumer merge
  - never reset, force-push, delete evidence, widen v1, activate mixed versions or add fallback as rollback
handoff_to: tech-lead
handoff_format: .planning/phases/02-cycle-2-e2e-01/02-02R-PLAN.md#handoff
output_barrier: B_C2_INPUT_BINDING_V2
```

## Tasks

### Task 1 — RED：冻结 v1 compatibility 与 v2 closed matrix

先在 owned test 文件增加 v1 model/schema/behavior compatibility oracle、v2 四项 exact
name/value 正负矩阵、严格类型、UTC/time ordering 与 forbidden field vectors。测试必须
证明 Claim 不会因模型命名或类型 coercion 变成业务事实、Observation 或 target。

### Task 2 — GREEN：实现 inactive InputBindingV2

在 `task_state.py` 最小新增 v2 owner model，复用已 reviewed 的 order-id规则与
`normalize_product_description`；name/value 必须交叉验证。不得修改 v1 class、active
codec/import、RequestUnit、Task transition 或其他 Core owner。

### Task 3 — GREEN：exact v1→v2 conversion 与 hardening

新增纯确定性 conversion helper，仅接受 exact v1 `InputBinding` instance并逐字段复制。
完成 focused/neighbor、compile、containment 后交全新 reviewer 做窄范围
`TARGETED_CONTRACT` exact-head review；修复只重跑受影响 tests。

## W3R gate

```text
product base == ed61f4d4da9c75386aa96857a5e77e06de4c4804
AND product tree == 02c06f70459cf9593946c599a2de33d1c5a15a91
AND PR #221 state == MERGED
AND this exact Plan is present in reviewed planning provenance
AND all required product blobs equal the frozen literals
AND implementation branch/worktree do not already exist
AND planning review verdict == PASS
```

任一条件不成立即 `BLOCK`；不得自动换 base、扩大 allowlist、把 Application/Gateway
修复并入本 Packet，或提前切换 active codec。

## Handoff

只报告 exact base/head/tree、branch/PR、实际两文件、focused/neighbor结果、targeted
review finding disposition、contract/security/Eval impact、未决风险与下一 barrier。
明确标记 active codec、migration、Application/Gateway、canonical full、Phase 2 Eval /
Result/lifecycle 均未运行或未推进。
