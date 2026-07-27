---
phase: 01-cycle-1-e2e-01
plan: 07A
subsystem: runtime-trace
tags:
  - runtime
  - trace
  - evaluation
status: complete_evidence_indexed
completed_at: "2026-07-27T09:00:47Z"
duration: "NOT_RECORDED"
completed: "2026-07-27"
requirements:
  - E2E01-01
  - E2E01-04
requirements_completed: []
execution_base: eee1c0e46e1bca1160dea54d586d477c173daadc
planning_merge: 36f56f57df6c62d125008b3de4efa973513c458b
published_head: 0617c4915d9d240fa509f9793778356fc164f154
integration_merge: 4cfac0a4ccfac6b75afa565f6010f7b1544abd7a
key_files:
  modified:
    - src/mini_agent/application/agent_run_service.py
    - tests/component/application/test_agent_run_service.py
metrics:
  feature_commits: 2
  files_changed: 2
  directed_tests_passed: 27
  focused_tests_passed: 100
  migration_tests_passed: 40
  full_tests_passed: 936
  full_tests_deselected: 1
---

# Phase 1 Packet 01-07A｜Runtime Trace Alignment Summary

> **DERIVED / NON_NORMATIVE**
> 本 Summary 只索引已合并的 Runtime Trace 对齐与可复现证据，不拥有产品、Trace DTO、Application Port、Eval Case、lifecycle 或发布语义。规范性边界仍服从 active canonical owners 与 [01-07A Plan](01-07A-PLAN.md)。

## Outcome

`01-07A` 已用 exact two-file Runtime ownership 关闭 01-07 real Eval 暴露的三个真实 Trace gap：

- 两个 `ContextManifestRecorded` call site分别持久化 `REQUEST_UNDERSTANDING` 与 `PRESENTATION` purpose；
- every normal returned `AgentRunResult` 在 terminal aggregate前形成 exactly one standalone `ResponseRendered`，包括 fixed safe failure与 not-found路径；
- pre-render failure不产生 `ResponseRendered`，post-render terminal aggregate conflict / error / cancellation保留已到达的一个 render event，但不返回 result、不写 ASSISTANT Message，也不伪造 `RunStopped`；
- post-revalidation / pre-reload / pre-Gateway hook显式接收 active `run_id`、Task与RequestUnit；
- stale-state Component matrix证明 `ACTIVE/v1 → WAITING_USER/v2 → BLOCKED/v3`、active Run identity与三个真实 `TaskStateChanged`；
- normal terminal aggregate仍只包含既有 `TaskStateChanged? / RunStopped`，没有修改 Core DTO、Application Port、PostgreSQL schema、Eval artifact、Composition Root或lifecycle。

这些证据允许 01-08 的 real Eval SUT从真实 Runtime / PostgreSQL记录读取 purpose、render与stale transition，不允许 Eval reader补造它们。

## Exact Evidence

| Evidence | Exact value / result |
|---|---|
| Planning PR / merge | [#37](https://github.com/weijie567/mini-agent/pull/37) / `36f56f57df6c62d125008b3de4efa973513c458b` |
| 01-07A Plan Git blob | `0a8c3cd770fb1a0cd1987ef6dafd5a666815dfe4` |
| Test-only RED | `c76c5e7aca97bbe4df7a9b753c9fe2adaa229f53` |
| GREEN / published feature head / tree | `0617c4915d9d240fa509f9793778356fc164f154` / `d4b98616b82968b519bcddfa762c67f92f48fdea` |
| Feature PR | [#38](https://github.com/weijie567/mini-agent/pull/38) |
| Latest-integration overlay | base `36f56f57df6c62d125008b3de4efa973513c458b` / direct parent `5cdd79ed1370c2276c91d80f3e366d8558d98110` / head `add83f98afa9efadbc00f632abee896772ae6bee` / tree `168a9f281bc1ac29206c79494c0031b77c008dc3` |
| Integration merge / tree | `4cfac0a4ccfac6b75afa565f6010f7b1544abd7a` / `168a9f281bc1ac29206c79494c0031b77c008dc3` |
| Scope / provenance | exact 2 owned files；test-only RED → production-only GREEN；feature / overlay patch-id与owned blobs相同 |
| Directed / focused / migration / full | `27 passed` / `100 passed` / `40 passed` / `936 passed, 1 deselected` |
| Independent review | feature双路 `PASS / NOT_FOUND`；latest-integration overlay双路 `PASS / NOT_FOUND` |
| Review evidence | [PR #38 evidence](https://github.com/weijie567/mini-agent/pull/38#issuecomment-5089342040) |

## Post-merge Gate

在 exact integration merge `4cfac0a...` 上：

- migration regression为 `40 passed`；
- default full offline suite为 `936 passed, 1 deselected`；
- compileall与 `git diff --check` 通过；
- `graphify update .` 得到 4376 nodes、12359 edges、1362 communities；
- stale marker不存在，tracked integration Worktree clean。

## Active-owner Status Alignment

01-07A merge后，三个独立 status packet只对齐已合并证据，不推进 Case：

| Owner / consumer | PR / merge | Result |
|---|---|---|
| Business owner | [#39](https://github.com/weijie567/mini-agent/pull/39) / `b46a96756d6e45a49d51ddbb681a3f29e8d510d8` | W2限为 Component / Integration evidence；`0/8`不变 |
| Eval owners | [#40](https://github.com/weijie567/mini-agent/pull/40) / `d15f8dbd58035e5baa5dd9cfceae330c9654a151` | machinery限为 Component / in-process；真实纵向链仍 `NOT_FOUND` |
| Project rules / plan consumer | [#41](https://github.com/weijie567/mini-agent/pull/41) / `8544137cfbcaebda603cd3000312fb5d2406327c` | canonical命令不变；证据边界与两个owners一致 |

三个 feature / latest-integration overlay均取得独立 `PASS / NOT_FOUND`。它们是状态对齐，不是新增 Runtime、Infra或Eval实现。

## Security, Eval and Lifecycle Boundary

- **Security:** hook新增 authority只包含 active Run UUID；Trace字段仍为 allowlisted opaque references，不含 `customer_id`、原始消息、订单 payload、Provider envelope或不必要 PII。
- **Eval:** real `EvalCaseSut`、Request Understanding semantic/mapping/codec/Core闭环、P0 source-version/Core DTO、Application Evidence Port、PostgreSQL reader、Eval mapper、invalid-RU Pydantic/trusted-field到`INPUT_INVALID`的Application signal / Runtime mapping / Eval-owned Scripted-Qwen consumers、Composition Root、真实 HTTP / Trajectory / E2E Result与 credentialed Qwen runner仍未实现。01-08 preflight已把它们拆为01-07B→01-07C–01-07L→01-08→01-08A；failure taxonomy由既有未签发I/J/L slots按owner关闭，不扩大01-07B或01-08。
- **Lifecycle:** `requirements_completed`为空；`E2E01-01/04`、numbered Phase与派生checkbox继续保持 `CONTRACT_DEFINED / 0/8`。
- **Handoff（已被后续preflight supersede）:** `8544137cfbcaebda603cd3000312fb5d2406327c`只作为01-07B execution base；不得再把它当作01-08 base。01-08只能从01-07B及01-07C–01-07L reviewed merge后的新exact integration SHA签发，并直接读取真实HTTP、Runtime与PostgreSQL记录，不得复制artifact事实或合成缺失Request Understanding output、版本、Trace或evidence。

## Self-Check: PASSED

- planning、RED/GREEN、feature、overlay、merge、测试、review、Graphify与status-owner证据均有精确引用。
- feature与overlay changed-file set均精确等于 two-file allowlist，merge tree等于reviewed overlay tree。
- 已显式保留 01-08 blockers与 `0/8` lifecycle，没有把 Component Trace evidence描述成纵向 Case PASS。
