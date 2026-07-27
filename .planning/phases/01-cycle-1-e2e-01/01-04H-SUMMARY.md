---
phase: 01-cycle-1-e2e-01
plan: 04H
subsystem: application-terminal-turn
status: complete_evidence_indexed
completed_at: "2026-07-27T04:03:51Z"
requirements:
  - E2E01-01
  - E2E01-04
requirements_completed: []
execution_base: ea0a72fdac597a9ae78b2ed6fa34d14ef2c1eb57
planning_merge: db6e2581723591518f47b9d45574bbfe0dd32a30
published_head: c0306efa6714b2a2c50da430d426c6857e6e1ef7
integration_merge: 64992cf3bdc6205e00d0c36433309b1657a57531
key_files:
  modified:
    - src/mini_agent/application/ports.py
    - src/mini_agent/application/records.py
    - tests/component/application/test_ports_contract.py
    - tests/component/application/test_record_contracts.py
metrics:
  feature_commits: 7
  files_changed: 4
  focused_tests_passed: 269
  full_tests_passed: 560
---

# Phase 1 Packet 01-04H｜Normal terminal-turn atomicity Summary

> **DERIVED / NON_NORMATIVE**
> 本 Summary 只索引已合并的 Application contract 与可复现证据，不拥有产品、Memory、Trace、Runtime、physical transaction、Eval Case 或 lifecycle 语义。规范性边界仍服从 active canonical owners 与 [01-04H Plan](01-04H-PLAN.md)。

## Outcome

`01-04H` 已关闭 Application Port 允许正常终态 partial success 的 expressibility gap：

- `FinalizeRunCommand` 对正常 `COMPLETED` Run 同时携带可选 Task / RequestUnit transition、terminal Run/link、validated `AgentRunResult` binding、ASSISTANT `MessageRecord` 与闭合 terminal Trace；
- 无 Task 的正常终态精确包含一个 `RunStopped`，有 Task 的正常终态精确包含有序 `(TaskStateChanged, RunStopped)`；
- closed 9-row matrix绑定 stop reason、是否有 Task、user outcome 与 terminal Task status；
- Run、Conversation、Task、RequestUnit、result、Message、Trace identity/content/timestamp 必须一致；
- `RuntimeRecordPort.finalize_run_if_active` 只允许 compliant Adapter 在全部投影同一条件事务提交后返回 `APPLIED`；其他条件结果要求零写入；
- 未捕获异常的 `FAILED` closure不伪造 stop reason、用户结果、ASSISTANT Message或 `RunStopped`；
- public construction/copy/revalidation 会递归拒绝 non-canonical/hidden nested storage，并把错误限制为不保留 raw input 的 bounded `ValidationError`；
- shallow/deep copy、subclass default factory、JSON/schema/pickle 与现有 Application contract 保持兼容。

本 Packet 没有实现 Runtime consumer、PostgreSQL transaction、fault rollback、HTTP、Composition Root、Trajectory/E2E 或 Case lifecycle。

## Exact Evidence

| Evidence | Exact value / result |
|---|---|
| Planning PR / head / merge | [#31](https://github.com/weijie567/mini-agent/pull/31) / `c785ad381487b402139b1b2950b94185c085ac77` / `db6e2581723591518f47b9d45574bbfe0dd32a30` |
| Plan blob | `386001a8b642569729f33c61ee7b2b570e1d0135` |
| Thin Slice Spec blob | `08d90f1b02d6e34c2ac333a96615258ce04f0797` |
| Feature PR / final head | [#32](https://github.com/weijie567/mini-agent/pull/32) / `c0306efa6714b2a2c50da430d426c6857e6e1ef7` |
| Reviewed feature tree | `cced2a50fee77970a587791db69f8bdca87c6ca1` |
| Integration merge / tree | `64992cf3bdc6205e00d0c36433309b1657a57531` / `7f52141abfef170dc65e4d4e95b37c611e29111e` |
| Scope | 7 linear feature commits；exact 4 owned files |
| Final focused / full | `269 passed` / `560 passed` |
| Post-merge full | `560 passed in 2.80s` |
| Review | local exact-head与GitHub transport review均 `PASS / NOT_FOUND` |
| Mechanical gates | compileall、JSON/schema/pickle、`git diff --check`、four-file containment、clean worktree均 `PASS` |

Review / fix cycles依次关闭 nested model revalidation、active-link base-version、structured error disclosure、public copy/revalidation绕过、subclass default-factory与完整 shallow-copy identity。最终 reviewed head确认 base declared fields shallow/deep identity为9/9，且未发现 material finding。

## Post-merge Graphify Gate

在 exact integration merge `64992cf…` 上：

- `graphify update .` 完成，得到 3485 nodes、6350 edges、1340 communities；
- multigraph diagnostic 的 missing/dangling/self-loop/exact-duplicate/same-endpoint collapse均为0；
- focused query可从 `FinalizeRunCommand` / `RuntimeRecordPort` 定位 downstream Runtime / Infra consumers；
- `needs_update` / `.needs_update` marker不存在；
- tracked integration worktree clean。

## Security, Eval and Lifecycle Boundary

- **Security:** Application caller无法再表达正常终态状态已提交但可靠 Message/mandatory Trace缺失的“成功”；structured validation error不保留 raw private input。
- **Eval:** 后续 Trajectory grader可要求完整 terminal projection；本 Packet没有运行 Trajectory/E2E grader或生成 Eval Result。
- **Lifecycle:** `requirements_completed`为空；canonical `E2E01-01/04`、numbered Phase与派生checkbox均未推进。
- **Handoff:** 01-05R必须只消费这个 aggregate并在 `APPLIED` 后返回；01-06R必须证明 physical same-transaction与child-fault rollback；01-08负责真实纵向 wiring/evidence。

## Self-Check: PASSED

- planning provenance、feature head/tree、integration merge/tree、test、review与Graphify证据均有精确引用。
- feature cumulative diff精确等于四文件allowlist。
- 没有把 Application contract描述为Runtime、Infra、Eval、HTTP、生产或完整切片已经实现。
