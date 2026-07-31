---
phase: 01-cycle-1-e2e-01
plan: 04G
subsystem: application-recovery-trace
status: complete_evidence_indexed
completed_at: "2026-07-26T22:12:24Z"
requirements:
  - E2E01-01
  - E2E01-04
requirements_completed: []
execution_base: a84d30188eaec75e45619e9939180ba78efa3b80
planning_merge: 55b406b30f6f34988fbde88b357fb2a9dcc842e0
published_head: d997502ff141def5bfa6c61fefe8952d02199c1c
integration_merge: c35687dafa3881bb322d91515068d8d39be79df6
key_files:
  modified:
    - src/mini_agent/application/ports.py
    - src/mini_agent/application/records.py
    - tests/component/application/test_ports_contract.py
    - tests/component/application/test_record_contracts.py
metrics:
  feature_commits: 3
  files_changed: 4
  focused_tests_passed: 175
  full_tests_passed: 466
---

# Phase 1 Packet 01-04G｜Recovery state + Trace atomicity Summary

> **DERIVED / NON_NORMATIVE**
> 本 Summary 只索引 Application contract 与证据。Memory、Tool、Trace、Runtime、physical transaction 与 Case 语义仍服从 active canonical owners。

## Outcome

`01-04G` 已关闭 recovery 状态提交后再追加 mandatory Trace 的永久 crash window：

- `ApplyRestartRecoveryCommand` 必须携带 1–3 个 Core/Runtime-produced `recovery_trace_events`；
- exact set 为一个 `RunStopped`、每个 Task transition 一个 `TaskStateChanged`、每个 ToolCall transition 一个 `ToolCallInterrupted`；
- event identity、Run/Task/RequestUnit/ToolCall binding、status、stop reason 与 timestamp 必须与 next projections 双射；
- 每类 event 只允许最小字段投影，其他 optional字段保持 canonical `None` / empty tuple；
- nested `TraceEvent` 在 Application boundary 按 exact type、known fields、无 hidden Pydantic storage 与 `strict=True` 重新验证；
- compliant Adapter 只有在同一事务提交所有 state/link/Trace 后才能返回 `APPLIED`；
- `CLOSURE_CONFLICT`、`NOT_APPLICABLE`、`RECONCILIATION_REQUIRED` 均要求零 state / Trace writes；
- 事后 `append_trace_event` 不能替代 recovery atomic command。

本 Packet 没有实现 Runtime event producer、PostgreSQL transaction、startup readiness 或 Action reconciliation。

## Exact Evidence

| Evidence | Exact value / result |
|---|---|
| Planning PR / merge | [#22](https://github.com/weijie567/mini-agent/pull/22) / `55b406b30f6f34988fbde88b357fb2a9dcc842e0` |
| Plan blob | `f5a7e4abf67b15677ff4694c58c846ee4b79a994` |
| Feature PR / final head | [#25](https://github.com/weijie567/mini-agent/pull/25) / `d997502ff141def5bfa6c61fefe8952d02199c1c` |
| Reviewed tree | `c9dc6590e01287972d7b8cacd0e606351d0a0af2` |
| Integration merge | `c35687dafa3881bb322d91515068d8d39be79df6` |
| Scope | 3 linear commits；exact 4 owned files |
| Initial TDD evidence | RED `26 passed, 1 failed`；initial GREEN `168 passed` |
| Review regression evidence | malformed/hidden nested event RED `5 failed`；final focused `175 passed` |
| Full integration regression | `466 passed` |
| Review | final GSD Plan checker `PASS`；independent code/contract/security `PASS`；0 actionable findings |
| Mechanical gates | exact-file Ruff / format、compileall、diff check、containment与latest-integration merge均 `PASS` |

独立 review 先发现 nested model instance 可绕过 strict contract并泄漏裸 `TypeError`，复审又发现 `__pydantic_extra__` hidden-storage silent strip。两项均使用追加 commit 修复，没有 amend / force-push；最终 attack matrix涵盖非法 UUID、不可哈希 ID、`None` / `()` 互换、unknown field、subclass、extra/private storage，全部产生受控 `ValidationError`。

## Post-merge Graphify Gate

在 integration merge `c35687d…` 上：

- `graphify update .` 完成 code-only AST refresh；
- `built_at_commit` 精确为 `c35687dafa3881bb322d91515068d8d39be79df6`；
- 3353 nodes、5999 edges、50 hyperedges；
- missing/dangling/self-loop/duplicate/same-endpoint collapse均为 0；
- `needs_update` marker不存在，absolute source path为0；
- `ApplyRestartRecoveryCommand` 可通过 query / explain 定位，tracked tree clean。

## Security, Eval and Lifecycle Boundary

- **Security:** 防止安全相关恢复状态与审计事实分裂，拒绝 cross-kind与隐藏 payload污染。
- **Eval:** 后续 Trajectory grader可以要求 recovery Trace；本 Packet没有执行该 grader。
- **Lifecycle:** `requirements_completed` 为空；Phase与 Case未推进。
- **Handoff:** 01-05产生 exact events；01-06以 physical transaction证明 APPLIED atomicity；01-08证明 startup recovery readiness。

## Self-Check: PASSED

- final head/tree、merge SHA、测试、review与 Graphify gate均可复现。
- 累计变更精确等于四文件 allowlist。
- 没有把 Application contract 声称为 Runtime、Infra、Eval、startup或纵向切片完成。
