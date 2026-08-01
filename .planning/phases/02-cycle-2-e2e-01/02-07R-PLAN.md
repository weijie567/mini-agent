---
phase: 02-cycle-2-e2e-01
plan: 02-07R
type: correction
wave: W6
depends_on:
  - B_C2_PHYSICAL
  - GATE_P2_A4
files_modified:
  - src/mini_agent/application/ports.py
  - tests/component/application/test_ports_contract.py
autonomous: false
requirements:
  - E2E01-02
  - E2E01-05
  - E2E01-06
user_setup: []
must_haves:
  truths:
    - "SearchOrdersPort 与 GetShipmentPort 由 Application 声明，不由 Infrastructure Adapter 自定义边界。"
    - "两个 Port 只接收 canonical trusted query DTO 并返回对应 canonical result DTO。"
    - "本 correction 不实现 Adapter、Runtime、Tool registration、Action 或 Case lifecycle。"
  artifacts:
    - "Application-owned SearchOrdersPort / GetShipmentPort runtime-checkable Protocols。"
    - "精确的 async signature 与禁止身份扩张 component contract tests。"
  key_links:
    - "reviewed 02-07R → 从真实 successor 重冻结 02-07/02-11。"
---

# Phase 2 Plan 02-07R｜Application Business Read Port owner correction

> **EXACT TASK PACKET / W6 OWNER CORRECTION**
>
> W6 preflight 已确认 canonical Cycle 2 Spec 把 `SearchOrdersQuery/Result` 与
> `GetShipmentQuery/Result` 的 outbound Business Read Port 声明归属 Application；
> 原 `02-07` Infrastructure allowlist 无权补全该边界。用户于 2026-08-02
> 授权 `02-07R` 与 slots `26 → 27`，master Plan correction PR #250 已
> reviewed merge。本 Packet 仅冻结两个 Application 文件；早期 W6 draft 不可执行。

## 目标与边界

按现行 canonical DTO 定义补全 `SearchOrdersPort.search_orders()` 与
`GetShipmentPort.get_shipment()` async Protocol。不新增 DTO、查询语义、授权来源、
Adapter、persistence、Runtime orchestration、Tool surface、Eval artifact 或 lifecycle。

## Exact Task Packet

```yaml
task_id: 02-07R
goal: 在 Application owner 内补全两个只读业务 Port Protocol。
repository: weijie567/mini-agent
remote: origin
head_branch: codex/e2e01-cycle2-business-read-ports
base_branch: integration/e2e01-cycle2
base_sha: 89041f73f490831073bcc41b14757a51757248c9
base_tree: 3364efa2fbdd3e64ac5142fbd4562a439713af2a
planning_control_base_sha: 89041f73f490831073bcc41b14757a51757248c9
planning_control_base_tree: 3364efa2fbdd3e64ac5142fbd4562a439713af2a
worktree_id: e2e01-cycle2-business-read-ports
agent_role: runtime-engineer
writer: runtime-engineer-application-ports
pull_request_base: integration/e2e01-cycle2
pull_request_mode: draft until independent final exact-head review PASS; never use admin bypass
owned_files:
  - src/mini_agent/application/ports.py
  - tests/component/application/test_ports_contract.py
forbidden_files:
  - all repository files outside the exact two-file owned_files allowlist
  - src/mini_agent/core/**
  - src/mini_agent/infrastructure/**
  - src/mini_agent/evaluation/**
  - src/mini_agent/runtime.py
  - src/mini_agent/bootstrap.py
  - tests/** except tests/component/application/test_ports_contract.py
  - alembic/**
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
  - docs/implementation/e2e01-cycle2-implementation-spec.md ownership matrix and Business Read Port contracts
  - docs/implementation/e2e01-cycle2-multi-agent-plan.md slot 02-07R and W6
read_first:
  - src/mini_agent/application/ports.py
  - src/mini_agent/core/order_search.py
  - src/mini_agent/core/shipment.py
  - tests/component/application/test_ports_contract.py
required_product_blobs:
  AGENTS.md: 5904da48f4e3a2d95e86ffa04ebe29694caf5c0a
  docs/implementation/e2e01-cycle2-implementation-spec.md: 0ab85bd7e8cbe8556472efa7003eb4aab4649ce0
  docs/implementation/e2e01-cycle2-multi-agent-plan.md: f1043063d1442e25734c367a875d161a71c1fc9a
  src/mini_agent/application/ports.py: 3c03e3c0da42409bba3a533faa99ea8dadad625c
  src/mini_agent/core/order_search.py: 2c8b84ed82f982bc46b0ca4c2141f357b3d4eba4
  src/mini_agent/core/shipment.py: c0db0f4b2220a29848152833820ddcead448ef7f
  tests/component/application/test_ports_contract.py: 5155c4d2873fdfc469cc907d99058dde0c4cbc4a
  tests/component/core/test_order_search_contract.py: b6d50ac9fe5b10845acd2bc5a874d2794bb0fde7
  tests/component/core/test_shipment_contract.py: 573febaf55f8f65cd8f20e3c292e19fa119c18bf
  tests/component/core/test_tool_system_contract.py: 1cdf02d243df81640369ca5a6c49a68b35549c9a
dependencies:
  - exact master-plan owner-ruling successor = 89041f73f490831073bcc41b14757a51757248c9
  - exact reviewed B_C2_PHYSICAL = bf8e88b2c0124aee82dffc7e54ae03ec0fdbea50
  - exact reviewed B_C2_PHYSICAL tree = fccc5a1f87a0b00dd31ba61ee8c960901c7601da
  - user-approved Gate P2-A4 adds exactly 02-07R and changes slots 26 to 27 without a new wave label
contract_changes: NONE — closes the missing Application declaration required by the existing canonical Spec and reviewed master-Plan correction.
security_impact: HIGH BOUNDARY / trusted customer_id remains inside canonical query DTOs; the Port cannot accept message/model identity overrides.
eval_impact: COMPONENT CONTRACT ONLY — no Eval artifact, Harness, Result or Case lifecycle transition.
review_profile:
  planning_review: INDEPENDENT_EXACT_FILE_PASS
  implementation_review: TARGETED_APPLICATION_PORT
  targeted_risk_checks:
    - exact two-file allowlist and no DTO/core/adapter/runtime changes
    - runtime-checkable async Protocol signatures use exact canonical query/result DTOs
    - no raw customer_id parameter or user/model identity override surface
    - no query implementation, tool registration, persistence, Action or lifecycle behavior
  focused_tests: uv run pytest tests/component/application/test_ports_contract.py -q
  neighbor_tests: uv run pytest tests/component/core/test_order_search_contract.py tests/component/core/test_shipment_contract.py tests/component/core/test_tool_system_contract.py -q
  full_suite_gate: NOT_RUN_FOR_02_07R; W6 exit only
  migration_gate: NOT_APPLICABLE
verification:
  focused: uv run pytest tests/component/application/test_ports_contract.py -q
  neighbor: uv run pytest tests/component/core/test_order_search_contract.py tests/component/core/test_shipment_contract.py tests/component/core/test_tool_system_contract.py -q
  compile: uv run python -m compileall -q src/mini_agent/application/ports.py tests/component/application/test_ports_contract.py
  diff_check: git diff --check 89041f73f490831073bcc41b14757a51757248c9...HEAD
  full: NOT_RUN_BY_REVIEW_PROFILE
latest_integration_overlay: REQUIRED — replay exact two-file patch on current integration, rerun focused/neighbor, verify owned blobs, and obtain targeted overlay review PASS.
required_checks:
  - exact base/tree/blobs/protection/branch absence/clean preflight PASS
  - imports and Protocol signatures point to exact SearchOrders/GetShipment canonical DTO pairs
  - implementation classes with the exact async methods satisfy runtime_checkable Protocols
  - wrong names, sync methods, raw identity parameters and wrong result annotations fail contract tests
  - focused/neighbor/compile/diff PASS; canonical full accurately NOT RUN
  - independent exact-head and latest-integration overlay review report 0 BLOCK/HIGH
done_when:
  - reviewed implementation PR merges serially and its exact successor is recorded
  - 02-07 and 02-11 are frozen only after that real successor exists
rollback:
  - before merge close PR and retain review/test transcript
  - after merge revert the exact two-file change before any dependent Adapter Packet merges
  - never bypass the Port by implementing Infrastructure against an unowned local interface
handoff_to: tech-lead
handoff_format: .planning/phases/02-cycle-2-e2e-01/02-07R-PLAN.md#handoff
output_barrier: B_C2_BUSINESS_READ_PORTS
```

## Tasks

### Task 1 — RED：exact Application Port contract

在现有 Application Port component suite 中锁定两个 Protocol 的 exact async
query/result annotation、`runtime_checkable` 行为与无 raw identity override surface。

### Task 2 — GREEN：minimal Protocol declarations

仅在 `ports.py` 导入 canonical DTO 并添加两个 Protocol，不实现任何调用或适配。

### Task 3 — Regression and bounded review

运行focused/neighbor/compile/diff，完成feature与latest-integration overlay的限时独立复核。

## W6 correction gate

```text
product/planning base == exact 89041f73 / 3364efa2
AND required blobs match
AND exact two-file implementation branch/worktree absent before planning merge
AND planning review == PASS
AND Case lifecycle remains CONTRACT_DEFINED
```

## Handoff

报告exact base/head/tree、两文件、focused/neighbor/compile/diff、review/overlay与
`B_C2_BUSINESS_READ_PORTS`；明确 `02-07/02-11` 尚未冻结，Adapter、Runtime、
canonical full、Eval artifact 与 Case lifecycle 均未推进。
