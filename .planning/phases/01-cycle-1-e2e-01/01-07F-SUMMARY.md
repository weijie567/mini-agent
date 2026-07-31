---
phase: 01-cycle-1-e2e-01
plan: 07F
subsystem: request-understanding-v2-core-expand
tags:
  - request-understanding
  - core
  - versioning
  - security
status: complete_evidence_indexed
completed_at: "2026-07-28T19:29:51+08:00"
duration: "NOT_RECORDED"
completed: "2026-07-28"
requirements:
  - E2E01-01
  - E2E01-04
requirements_completed: []
execution_base: 73696a138eb13fc4a90a0f760b13865f53d08704
planning_merge: 112d643ec12aa1556c3794874e8cc450f9a8b36b
published_head: 72f799832f5d0a0ed0b118aaf1671287fa6ddf29
integration_merge: 034cf57228c4a9da4764b0c7322dc5d34652a09c
key_files:
  modified:
    - src/mini_agent/core/request_understanding.py
    - src/mini_agent/core/task_state.py
    - src/mini_agent/core/request_processing.py
    - tests/component/core/test_request_understanding_contract.py
    - tests/component/core/test_task_state_contract.py
    - tests/component/core/test_request_processing.py
metrics:
  feature_commits: 5
  files_changed: 6
  focused_tests_passed: 92
  full_tests_passed: 1575
  full_tests_deselected: 1
---

# Phase 1 Packet 01-07F｜Request Understanding v2 Core Expand Summary

> **DERIVED / NON_NORMATIVE**
> 本 Summary 只索引 01-07F `CORE_EXPAND` 的已合并实现与可复现证据，不拥有 Request Understanding、Memory、Application codec、Runtime、Infra、Eval 或 lifecycle 语义。规范性内容仍由 [Intent owner](../../../docs/architecture/intent-design-reference.md)、[Thin Slice owner](../../../docs/implementation/e2e01-thin-slice-implementation-spec.md)、[execution map](../../../docs/implementation/e2e01-thin-slice-multi-agent-plan.md) 与 [01-07F Plan](01-07F-PLAN.md) 持有。

## Outcome

`01-07F` 已从 exact `B_O_STATUS` 以 additive、non-routable 方式增加 Request Understanding v2 Core surface：

- 增加显式 model-facing input/output、durable-safe contextualization/candidate/validation/accepted-delta DTO 与封闭 failure taxonomy；
- 以纯确定性函数完成 provenance projection、candidate/decision/accepted exact closure 与 keyed Task effect chain 校验；
- 拒绝 alias、隐式 v1 fallback、trusted/private field 注入、undeclared model state、candidate reconstruction 与 dangling accepted effect；
- 保持 41 个既有 v1 top-level definition 的 source/AST、binding、active consumer 与路由不变。

该 merge 形成 `B_F`，只授权后续 01-07E 从该 exact SHA 执行 `CODEC_EXPAND`；它不表示 Application codec、physical persistence、Runtime、Provider/Eval 或 active switch 已完成。

## Exact Evidence

| Evidence | Exact value / result |
|---|---|
| Planning PR / head / merge | [#70](https://github.com/weijie567/mini-agent/pull/70) / `c50faec647825f16a20c8b944099552fddfdf164` / `112d643ec12aa1556c3794874e8cc450f9a8b36b` |
| Plan blob | `d0630bfb9bebd43efbe5c1d8f110ef5dcc897ae1` |
| Execution base | `73696a138eb13fc4a90a0f760b13865f53d08704`（`B_O_STATUS`） |
| Feature head / tree | `72f799832f5d0a0ed0b118aaf1671287fa6ddf29` / `945acab8dab9d1ca71d188cf068a757e038c99b5` |
| Latest-integration overlay base / head / tree | `112d643ec12aa1556c3794874e8cc450f9a8b36b` / `4e18419c392d7a067f19fa4dbe988684a32657dd` / `c62d660213d8c74f922a7832ed778f3ac6f3b104` |
| Feature PR / integration merge / tree | [#71](https://github.com/weijie567/mini-agent/pull/71) / `034cf57228c4a9da4764b0c7322dc5d34652a09c` / `c62d660213d8c74f922a7832ed778f3ac6f3b104` |
| Scope | exact 5 commits、6 owned files；RED → GREEN → 3 review fixes |
| Protected-v1 oracle | 41 definitions unchanged；source/AST/binding gate通过 |
| Focused / full suite | `92 passed`；`1575 passed, 1 deselected, 12 warnings` |
| Independent review | feature与latest overlay最终均为 `CRITICAL/HIGH/MEDIUM = 0/0/0`、`PASS / MERGE` |

`B_F` 上三个 Core source blob 分别为：

- `request_understanding.py = 018ea446517c099cc061de6e99afe55db10e8afb`
- `task_state.py = 122b62b7a68ae0b92adfb3208ef9845fdd646fbe`
- `request_processing.py = 261c6318e60756d57d4d15bfcf62b5c2da236760`

## Security, Eval and Lifecycle Boundary

- **Security:** `customer_id`、owner scope与授权没有新增入口；用户/模型值仍只作为候选，trusted/private字段、undeclared state与非闭合 candidate effect fail closed。
- **Eval:** 新增 Core Component contract 证据；没有 Dataset、Grader、Trajectory、E2E Result或 Case lifecycle 变化。
- **Lifecycle:** `requirements_completed` 为空，canonical Case / Requirement 与派生 checkbox 均保持 `0/8`。
- **Nonclaims:** active consumer、Application codec、PostgreSQL、Runtime、Provider/Eval、v1 retirement与 readiness 均未切换。

## Self-Check: PASSED

- exact base、Plan、feature、overlay、review、merge与测试证据均有精确引用；
- six-file allowlist与 protected-v1 gate闭合；
- 未把 additive Core DTO、Component tests或 `B_F` 描述为真实纵向链或产品完成。
