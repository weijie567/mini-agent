---
phase: 01-cycle-1-e2e-01
plan: 01
subsystem: architecture
status: complete_evidence_indexed
completed_at: "2026-07-26T12:06:08Z"
requirements:
  - E2E01-01
  - E2E01-04
requirements_completed: []
execution_base: 624475681847be5a8e463e32dafd28a0483b213b
planning_merge: a214dfa7b50ee942c4da1063c770245c72cf10c1
feature_head: 7c43ebe5d5edbc291fc29c14ba3681b100235587
integration_merge: c96dea9f9f798212227cd05ff2a7b1f029a60287
key_files:
  modified:
    - PROJECT_DIRECTION.md
  created: []
metrics:
  commits: 1
  files_changed: 1
  insertions: 39
  deletions: 0
  tests_passed: 181
---

# Phase 1 Plan 01-01｜Project Direction persistence ownership / Trace structure Summary

> **DERIVED / NON_NORMATIVE**
> 本 Summary 只索引已合并的 Task Packet 证据，不拥有产品、架构、契约、Eval 语义或 Case 生命周期。`PROJECT_DIRECTION.md` 是本次契约变化的 canonical owner；本文件不能把 `E2E01-01/04`、持久化实现或整个 Phase 宣称为已完成。

## Outcome

`01-01` 的单 owner Task Packet 已完成并合并。`PROJECT_DIRECTION.md` 现在固定了后续 Memory、Thin Slice 与实现 Plans 必须消费的项目级边界：

- persistence 的 `semantic owner`、`Python source owner`、`Port declaration owner` 与 `adapter owner` 四轴相互独立；
- `record_schema_version`、`state_version`、`artifact_schema_version`、`tool_registry_version` 与 Eval `version_manifest` 互不替代；
- 可信身份和授权范围不能由模型、用户消息、持久化 payload / metadata、源码位置或数据库字段创建、覆盖或扩大；
- owner-scoped lookup 的无行 / 无权访问继续返回相同安全结果；只有已读取 record / envelope 的必填字段、record code、版本或 payload 缺失、损坏、不受支持才属于 decode / integrity failure；
- 逻辑迁移必须先由对应 semantic owner 批准，Infrastructure 只执行已经批准的显式 physical / data migration，Adapter 不得静默 upgrade、downgrade、quarantine、rewrite 或 `fallback-to-latest`；
- `TraceEvent` 共享结构、公共字段和逻辑版本由 `Core Runtime / Project Direction owner` 唯一批准，专项 event type / payload / visibility 仍由对应 specialized owner 拥有。

该结果没有实现 `PersistenceEnvelope`、Schema registry、decoder、业务表、compatibility layer 或 migration。

## Exact Evidence

| Evidence | Exact value / result |
|---|---|
| Task Packet execution base | `624475681847be5a8e463e32dafd28a0483b213b` |
| Planning-status PR | [#11](https://github.com/weijie567/mini-agent/pull/11)，reviewed head `ab904947e7182a7db2ded15cd22c4d01c844dfb0` |
| Planning merge / tree | `a214dfa7b50ee942c4da1063c770245c72cf10c1` / `6ae440e7c4336dffbc2c60c25d5fd9b0ab1e7fe4` |
| `01-01-PLAN.md` blob | `42d671660e54c65d67c35cae77b1c2c80a05ed78` |
| Execution feature head / tree | `7c43ebe5d5edbc291fc29c14ba3681b100235587` / `7aac16ffd2704589423858224b09a81b5b99868e` |
| Owner PR | [#12](https://github.com/weijie567/mini-agent/pull/12)，base `integration/e2e01-thin` |
| Integration merge / tree | `c96dea9f9f798212227cd05ff2a7b1f029a60287` / `843f408c7e2d7537c0803b688f63007ff3541ca7` |
| Merged canonical blob | `PROJECT_DIRECTION.md` = `4e5eb5f46411d89f903c41b519d75eab98c4031b` |
| Scope | exactly 1 commit、1 changed file、`PROJECT_DIRECTION.md` `+39/-0` |
| Mechanical regression | `uv run pytest` → `181 passed` at exact feature head and again after merge |
| Independent exact-head review | `PASS`；`CRITICAL / HIGH / MEDIUM: NOT_FOUND` at `7c43ebe5d5edbc291fc29c14ba3681b100235587` |

## Commits

| Type | Commit | Description |
|---|---|---|
| Planning integration | `a214dfa7b50ee942c4da1063c770245c72cf10c1` | PR #11 建立 exact Plan / Task Packet |
| Feature | `7c43ebe5d5edbc291fc29c14ba3681b100235587` | 单写 `PROJECT_DIRECTION.md` 的 owner contract |
| Owner integration | `c96dea9f9f798212227cd05ff2a7b1f029a60287` | PR #12 squash merge，reviewed blob 不变 |

## Mechanical Evidence and Scope

- Branch、exact base、merge-base、clean state、one-commit / one-file allowlist 和 `git diff --check` 均通过。
- `PROJECT_DIRECTION.md` 的 owner、version、migration、Trace 和安全术语扫描通过。
- 仓库级 cross-file impact scan 覆盖 `AGENTS.md`、Project Direction、Memory、Intent、Tool、Eval、Thin Slice Spec、README、multi-agent plan、源码与测试；execution branch 没有越界修改扫描出的其他文件。
- Owner PR 合并后，integration 相对 planning merge 只改变 `PROJECT_DIRECTION.md`，且 merged blob 与 reviewed feature blob 完全相同。
- 当时 GitHub smart-HTTP 暂时不可用；planning provenance 使用 GitHub Git Database REST ref / commit / tree 与本地对象交叉验证的 fail-closed 等价路径，并在恢复后通过普通 push、GitHub PR 和最终 merge 重新确认。该偏差没有放宽 exact SHA、tree、blob 或 allowlist 门禁。

## Contract, Security and Eval Impact

- **Contract change:** `YES`。项目级 persistence ownership、版本维度、logical / physical migration approval 和 Trace shared-structure authority 已成为 canonical Project Direction。
- **Security impact:** `YES`。可信身份不从 persisted payload 获得；无行 / 无权访问不可区分；完整性失败不 fail open，普通 Trace / 诊断不得记录 raw payload、原始 Token 或不必要 PII。
- **Eval impact:** `YES / CONTRACT ONLY`。Eval `version_manifest` 保持 Eval owner 下的一次运行版本快照；没有生成 Eval result、没有改变 Case lifecycle。
- **Implementation claim:** `NONE`。本 Plan 不证明 codec、Adapter、数据库表、HTTP、Trajectory 或 E2E 已实现。

## Deviations

唯一执行偏差是 planning provenance 在 GitHub smart-HTTP 临时故障期间使用官方 REST ref / commit / tree 的等价 fail-closed 证据路径；所有 exact object 与 GitHub PR 证据均已保留。没有 scope、owner、contract 或测试偏差。

## Deferred and Unresolved

- `01-02` Memory owner 裁决 P0 exact-version 行为、decode / integrity failure、startup recovery readiness 与 migration runtime 边界。
- `01-03` Thin Slice owner 针对第 10.1 节当前 17 项最低持久化集合冻结 item code、版本和实现 API；不得在 `01-02` 提前定义。
- `01-04` 才实现经 01-01–01-03 批准的 contract；当前源码中把 records 笼统称为 Application-owned 的说明文字只作为后续 implementation impact，不在本 owner-only PR 越界修改。
- `E2E01-01` 与 `E2E01-04` 继续为 `Pending`；没有 canonical lifecycle 更新。

## Handoff to Plan 01-02

`01-02` 必须从 integration exact base `c96dea9f9f798212227cd05ff2a7b1f029a60287` 建立，只写 `docs/architecture/memory-design-reference.md`，消费上述四轴 ownership、五类 version、trusted identity、no-row / unauthorized 与 integrity failure 的区分，以及 semantic-owner-first migration approval。它不得定义 decoder / registry API、不得枚举或版本化 Thin Slice 的 17 项记录、不得声称实现存在。

## Self-Check: PASSED

- Summary 中的 planning、feature 与 integration SHA 均可由当前 Git object 和 GitHub PR #11/#12 复现。
- Reviewed feature blob 与 merged `PROJECT_DIRECTION.md` blob 完全相同。
- `01-01` execution scope 为一个 commit / 一个文件，181 个 serial tests 通过。
- Requirements completion 为空；本 Summary 没有把 Phase、Case 或 persistence implementation 标记为完成。
