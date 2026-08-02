---
phase: 02-cycle-2-e2e-01
plan: 02-15R1I
type: implementation
wave: W9
depends_on:
  - B_C2_W9_SHIPMENT_TARGET_ROUTE
  - B_C2_W9_R1_SIXTH_REFREEZE
files_modified:
  - src/mini_agent/core/control_gateway.py
  - tests/component/core/test_control_gateway.py
autonomous: false
requirements: [E2E01-05, E2E01-06]
user_setup: []
must_haves:
  truths:
    - "RequestUnit可保留此前真实Search/Order Observation历史，但Gateway当前target闭包仍只接受exact current ref/version/owner/task/unit/state/bindings/supersession。"
    - "额外历史Observation ref不授予target authority；缺少当前target ref、manifest漂移、同ref不同version或伪造current target仍fail closed。"
    - "修正只改变Core Gateway对合法Observation历史的完整性判定，不降低identity、binding、target、manifest、budget、progress或READ-only边界。"
  artifacts:
    - "Cycle 2 Gateway observation-history component regression proof。"
  key_links:
    - "B_C2_W9_R1_SIXTH_REFREEZE → reviewed 02-15R1I → B_C2_W9_OBSERVATION_HISTORY_GATE → seventh-refrozen 02-15R1。"
---

# Phase 2 Plan 02-15R1I｜Gateway current-target Observation history correction

> **EXACT TASK PACKET / W9 CORE_GATE_OWNER_CORRECTION**
>
> `02-15R1` sixth-refrozen Application writer在真实
> `search_orders → get_order → get_shipment`接线中确认：Search outcome按现行contract
> 追加Search Observation，get_order随后追加Order Observation，因此
> `RequestUnit.observation_refs`合法包含历史与当前两项；但Core Gateway当前把该完整
> 历史集合错误要求为exact等于唯一current target Observation集合，导致第二项存在时
> 必然拒绝Shipment。Application不得删除历史、伪造closure或绕过Gateway。依据用户
> 2026-08-02“有问题按照你的建议走”的授权，在W9原wave内增加本窄Packet；R1 WIP
> 继续unpublished，reviewed successor后必须第七次重冻结。

## Exact Task Packet

```yaml
task_id: 02-15R1I
goal: 修正Cycle 2 Gateway对RequestUnit Observation历史与唯一current target Observation闭包的集合关系，同时保持current target ref/version严格校验。
repository: weijie567/mini-agent
remote: origin
head_branch: codex/e2e01-cycle2-w9-observation-history-gate
base_branch: integration/e2e01-cycle2
base_sha: 24f1e181b54b0ae4d2889c653f4651064ce081e1
base_tree: 99f48fcde988b71adb5d0e19df99f69fd1b8854b
planning_control_base_sha: 24f1e181b54b0ae4d2889c653f4651064ce081e1
planning_control_base_tree: 99f48fcde988b71adb5d0e19df99f69fd1b8854b
worktree_id: e2e01-cycle2-w9-observation-history-gate
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
dependencies:
  - exact B_C2_W9_SHIPMENT_TARGET_ROUTE = 99ed7e4d44261b2ffca35dae69f97701b15e00f4
  - exact B_C2_W9_R1_SIXTH_REFREEZE = 24f1e181b54b0ae4d2889c653f4651064ce081e1
contract_changes: NO — implementation defect correction inside the reviewed Gateway closure semantics; Observation history remains Memory-owned and target authority remains exact-current only.
security_impact: HIGH / preserve exact current target and manifest closure while refusing to treat historical refs as authority.
eval_impact: PRE-ACTIVATION COMPONENT SUPPORT ONLY — Cases remain CONTRACT_DEFINED; no Harness dispatch, artifact, lifecycle, or Result mutation.
review_profile:
  planning_review: INDEPENDENT_EXACT_FILE_PASS
  implementation_review: TARGETED_GATEWAY_HISTORY_SECURITY
  reviewer_timeout: 20_SECONDS_MAX; interrupt and narrow immediately on timeout
  focused_tests: uv run pytest tests/component/core/test_control_gateway.py -q
  neighbor_tests: uv run pytest tests/component/core/test_cycle2_memory_contract.py tests/component/core/test_request_processing.py tests/component/core/test_tool_system_contract.py -q
  full_suite_gate: NOT_RUN_FOR_R1I; W6 supplied mid-phase canonical full and next canonical full belongs W12
verification:
  compile: uv run python -m compileall -q src/mini_agent/core tests/component/core
  focused: exact focused_tests command
  neighbor: exact neighbor_tests command
  diff_check: git diff --check 24f1e181b54b0ae4d2889c653f4651064ce081e1...HEAD
  allowlist: git diff --name-only exact base...HEAD equals exact two-file owned_files set
done_when:
  - reviewed exact-two-file PR merges and successor is recorded as B_C2_W9_OBSERVATION_HISTORY_GATE
  - R1 may refreeze only from the real successor; Cases remain CONTRACT_DEFINED
rollback:
  - before merge close PR and retain local exact-head evidence
  - after merge revert this exact Core correction before R1/R2/02-15 depend on it
  - never repair by deleting Observation history, widening target selection, or bypassing Gateway
handoff_to: tech-lead
output_barrier: B_C2_W9_OBSERVATION_HISTORY_GATE
```

## Tasks

1. RED：新增`Search Observation历史 + current Order Observation`接受例，以及缺失当前
   ref、manifest同ref不同version、伪造current target和重复ref拒绝例。
2. GREEN：只调整Gateway loaded-graph集合关系；current target与manifest仍exact。
3. VERIFY：compile、focused、neighbor、exact-two-file containment与20秒bounded review。

## Handoff

报告exact identity、两文件、正负矩阵、focused/neighbor、review与
`B_C2_W9_OBSERVATION_HISTORY_GATE`；明确Application/DB/HTTP/Eval均未推进。
