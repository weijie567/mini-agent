---
phase: 01-cycle-1-e2e-01
plan: 07G
subsystem: get-order-source-version-ruling
tags:
  - order
  - source-version
  - integrity
  - security
status: complete_evidence_indexed
completed_at: "2026-07-28T01:55:31+08:00"
duration: "NOT_RECORDED"
completed: "2026-07-28"
requirements:
  - E2E01-01
  - E2E01-04
requirements_completed: []
execution_base: 3f0753f7bef87fc02f314e28fe8b07860a819701
planning_merge: 2b746d50a4c52d8d4193e6049d7859f65b40e8f5
published_head: 0fb892fae9fe61444c0beb2d84d39112cc6e33aa
integration_merge: bfc63c9444ee1af204cc3806eac7e7e84fc1bb19
key_files:
  modified:
    - docs/implementation/e2e01-thin-slice-implementation-spec.md
metrics:
  feature_commits: 1
  files_changed: 1
  full_tests_passed: 1493
  full_tests_deselected: 1
---

# Phase 1 Packet 01-07G｜P0 `get_order` Source-Version Ruling Summary

> **DERIVED / NON_NORMATIVE**
> 本 Summary 只索引已合并的 01-07G Thin Slice owner ruling 与可复现证据，不拥有通用 Memory、Core DTO、Runtime、Infra producer、Eval 或 lifecycle 语义。规范性内容仍由 [Thin Slice owner](../../../docs/implementation/e2e01-thin-slice-implementation-spec.md) 与 [01-07G Plan](01-07G-PLAN.md) 持有。

## Outcome

`01-07G` 已在 Thin Slice owner 单文件范围内冻结 P0 `get_order` source-version 语义：

- 唯一 authority 是 Infra Adapter 在同一次 `customer_id + order_id` owner-scoped 查询返回后，对严格验证的 `OrderSummaryProjection` 计算 content version；
- canonical bytes、JSON 规则、SHA-256 token pattern 与 fixed vectors 已冻结；用户、模型、Provider、fixture、Runtime 与 Eval 均不得提供、覆盖或重新计算；
- `FOUND` 最终必须携带 source version，non-found / denied / system-failure 不得伪造；Observation 与 Context Manifest 只能 exact-copy，禁止 schema / fixture / timestamp fallback；
- source version 只证明本次安全投影内容，不授予权限、不替代 Observation freshness，也不承诺 monotonicity；
- green migration 固定为 `01-07H additive DTO → 01-07J Runtime fail-closed → 01-07K Infra producer → 01-07M Core contract closure`，每一步必须独立保持 full suite 绿色。

这些是 scoped owner-document contract 证据，不是 Core DTO、Infra producer、Runtime acceptance、Observation / Manifest 持久化或真实 E2E 已实现。

## Exact Evidence

| Evidence | Exact value / result |
|---|---|
| Planning PR / merge | [#48](https://github.com/weijie567/mini-agent/pull/48) / `2b746d50a4c52d8d4193e6049d7859f65b40e8f5` |
| Plan blob | `72c866f0afac449c7c9970c223c9eb182fb1e780` |
| Execution base / parent | `3f0753f7bef87fc02f314e28fe8b07860a819701` |
| Feature head / tree / owner blob | `0fb892fae9fe61444c0beb2d84d39112cc6e33aa` / `aad28db8eefefc039c541716752b9cc4fa4f3b52` / `538105706f471dabe9cf8964d1026c4abf484356` |
| Feature PR / merge | [#50](https://github.com/weijie567/mini-agent/pull/50) / `bfc63c9444ee1af204cc3806eac7e7e84fc1bb19` |
| Project Direction owner status alignment | [#54](https://github.com/weijie567/mini-agent/pull/54) / `ffcc562487be458073f4229e4f6f7b353bc8d9e0`；status-only，不替换`B_CG` |
| Latest-integration overlay | base `267fd0eba99b892b2b02c4cb99e40e7233856c11` / head `93599780b64ebd2e9923132b4220b6ce12102b2b` / tree `c6aafbdfd4b9d02cca9929a115a01f1eecbf4a5d` |
| Integration merge / tree | `bfc63c9444ee1af204cc3806eac7e7e84fc1bb19` / `c6aafbdfd4b9d02cca9929a115a01f1eecbf4a5d` |
| Scope | exact one commit、one owned file；`123+ / 4-` |
| O-1001 fixed vector | `mock-order-source-version.p0.v1:sha256:861c136b1a41ecef3cd9625dc58524ec452e939b5ca1eb70ebcab69181561c42` |
| O-2001 fixed vector | `mock-order-source-version.p0.v1:sha256:4801da34c67c9405986e368042209dedf87896b16aa5a1eead6031eed5c988be` |
| Feature / independent review / overlay tests | 各 `1493 passed, 1 deselected, 12 warnings` |
| Independent review | feature与latest overlay均 `PASS / CRITICAL-HIGH-MEDIUM = 0/0/0` |

## Post-merge Gate

01-07G 先串行合并，随后 01-07C r1 在 latest integration overlay 上复验并形成共同 barrier。最终共同 exact integration 为：

- merge `327b39da45cdcf564609a5385d52c4264da2c669`；
- tree `49ad0f3f5fc2c0cbe507763aca12bb6825fb7887`；
- default full offline suite `1493 passed, 1 deselected, 12 warnings`；
- Graphify 全量安全重建 `3098 nodes / 16904 edges / 68 hyperedges / 135 communities`，并记录 `699` dangling endpoint、`687` directed与`713` undirected collapse candidate、`0` missing endpoint、`0` self-loop；
- stale marker 不存在，tracked integration Worktree clean。

## Security, Eval and Lifecycle Boundary

- **Security:** version 只在 trusted owner-scoped read 与 strict safe-projection validation 后形成；foreign / missing 不产生 token，token不授予权限，raw row /私有身份不暴露给模型或用户。
- **Eval:** 仍缺 01-07H DTO、01-07J Runtime gate、01-07K producer、01-07M final validator，以及真实 Observation / Manifest / HTTP / PostgreSQL / Eval Result。
- **Lifecycle:** `requirements_completed` 为空；`E2E01-01/04` 与派生 checkbox 继续保持 `CONTRACT_DEFINED / 0/8`。与 01-07C 共同完成后，Task Packet 证据口径为 `16/29`。
- **Handoff:** `B_CG = 327b39d...`；下一步只允许从该 exact execution base 分别签发 01-07D 与 01-07H。

## Self-Check: PASSED WITH RECORDED GRAPH HEALTH WARNINGS

- owner ruling、fixed vectors、feature/overlay、review、merge、测试与 Graphify 证据均有精确引用；
- 已明确 Core / Runtime / Infra / Eval consumer 均未实现；
- 未把 content version 描述为授权、时间戳、schema version、真实支付/生产数据或完整 E2E 证据。
