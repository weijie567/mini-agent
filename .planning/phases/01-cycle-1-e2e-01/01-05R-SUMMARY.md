---
phase: 01-cycle-1-e2e-01
plan: 05R
subsystem: runtime-orchestration
status: complete_evidence_indexed
completed_at: "2026-07-27T05:20:18Z"
requirements:
  - E2E01-01
  - E2E01-04
requirements_completed: []
execution_base: 64992cf3bdc6205e00d0c36433309b1657a57531
planning_merge: 0f94827386a749cb9f1c20392f95a22c8d4b5c08
published_head: 05f01828f57a106575058d7571ddf31aa1d9a78c
integration_merge: fb607019130843c94825a47d7822518cbdb2143c
key_files:
  added:
    - src/mini_agent/core/request_processing.py
    - src/mini_agent/core/control_gateway.py
    - src/mini_agent/core/presentation_policy.py
    - src/mini_agent/application/agent_run_service.py
    - src/mini_agent/application/read_tool_executor.py
    - src/mini_agent/application/deterministic_renderer.py
    - src/mini_agent/application/restart_recovery_service.py
    - tests/component/core/test_request_processing.py
    - tests/component/core/test_control_gateway.py
    - tests/component/core/test_presentation_policy.py
    - tests/component/application/test_agent_run_service.py
    - tests/component/application/test_read_tool_executor.py
    - tests/component/application/test_deterministic_renderer.py
    - tests/component/application/test_restart_recovery_service.py
metrics:
  feature_commits: 3
  files_changed: 14
  focused_tests_passed: 100
  migration_tests_passed: 38
  full_tests_passed: 660
---

# Phase 1 Packet 01-05R｜W2 Runtime replacement Summary

> **DERIVED / NON_NORMATIVE**
> 本 Summary 只索引已合并 Runtime Component 行为与可复现证据，不拥有产品、Core / Application contract、PostgreSQL transaction、Eval Case 或 lifecycle 语义。规范性边界仍服从 active canonical owners 与 [01-05R Plan](01-05R-PLAN.md)。

## Outcome

`01-05R` 已用新的 execution identity消费 01-04H normal terminal-turn aggregate：

- 从 historical Runtime head `a27141b...` 受控 replay exact 14 blobs；
- 取得 test-only RED，证明旧 consumer 因缺少 terminal Task transition 无法通过 01-04H validator；
- 正常九行 terminal matrix只提交一个完整 `FinalizeRunCommand`；
- with-Task精确携带 transition、result、ASSISTANT Message与有序 `(TaskStateChanged, RunStopped)`；
- no-Task精确携带 result、ASSISTANT Message与 `(RunStopped,)`；
- 删除 normal path 的提前 terminal Task CAS、post-commit Message / Trace与 degradation success；
- 只有 `APPLIED` 设置 committed cursor并返回，之后没有 terminal persistence await；
- conflict、exception与cancellation不暴露成功，`FAILED` closure的 transition/result/message/terminal Trace四项为空；
- trusted identity、binding、Gateway、dispatch fence、minimal disclosure、presentation与restart no-replay继续保持 donor行为。

本 Packet没有实现 PostgreSQL physical same-transaction / child-fault rollback、Composition Root、HTTP纵向 wiring、Trajectory / E2E Result或Case lifecycle。

## Exact Evidence

| Evidence | Exact value / result |
|---|---|
| Planning PR / reviewed head / merge | [#33](https://github.com/weijie567/mini-agent/pull/33) / `db7659b57f326b5da85df388d00dffbb3ec04536` / `0f94827386a749cb9f1c20392f95a22c8d4b5c08` |
| Planning head / merge tree | `0581abbf6ebad898366e4c457fb44d0e9a49863a` |
| 01-05R Plan blob | `db83429a2025a6fe858ff1629e4db8c95e00b331` |
| 01-04H Summary blob | `2e4932be6d7ce7594efaa64815cc3708f640e035` |
| Feature commits | replay `d4d78c4...` → RED `e1652a2...` → GREEN `05f0182...` |
| Feature PR / reviewed head / tree | [#34](https://github.com/weijie567/mini-agent/pull/34) / `05f01828f57a106575058d7571ddf31aa1d9a78c` / `a8e0ccb700ae45da5d261850dba01f9ff0dfa8ee` |
| Latest integration overlay | parent `0f948273...` / head `26756ccee19d0cc178f58a686a5fd184d41881b2` / tree `4b643208...` |
| Integration merge / tree | `fb607019130843c94825a47d7822518cbdb2143c` / `4b6432082a6c022ae4edee15264c83339fd444a0` |
| Scope | exact 14 owned files；12 donor blobs相同，只允许AgentRun consumer/test pair改变 |
| RED / paired GREEN | `26 collected, 1 failed` / `27 passed` |
| Focused / migration / full | `100 passed` / `38 passed` / `660 passed` |
| Independent review | feature与latest-integration overlay均 `PASS / NOT_FOUND` |
| Transport review | exact 14 remote blobs与local reviewed blobs `0 mismatch` |

## Post-merge Gate

在 exact integration merge `fb607019...` 上：

- root full offline suite为 `660 passed`；
- disposable PostgreSQL migration regression为 `38 passed`，`db-test` healthy；
- compileall与`git diff --check`通过；
- `graphify update .`得到3788 nodes、8309 edges、1353 communities；
- multigraph diagnostic 的missing/dangling/self-loop/exact-duplicate/same-endpoint collapse均为0；
- query可定位 `AgentRunService` → `FinalizeRunCommand` / `RuntimeRecordPort`及原子终态测试；
- stale marker不存在，tracked integration worktree clean。

## Security, Eval and Lifecycle Boundary

- **Security:** Runtime不能再通过split terminal writes返回partial success；可信身份、资源归属、最小披露、Gate/fence与restart no-replay保持确定性边界。
- **Eval:** 新增的是Component行为与后续Trajectory可消费的终态闭合证据；没有生成Eval Result或激活Case。
- **Lifecycle:** `requirements_completed`为空；`E2E01-01/04`、numbered Phase与派生checkbox均未推进。
- **Handoff:** 01-06R必须把完整 aggregate映射到一个PostgreSQL物理事务并对每个child fault证明rollback；01-08才负责真实Runtime/Infra/Eval wiring。

## Self-Check: PASSED

- planning provenance、feature/overlay head/tree、integration merge/tree、TDD、测试、review与Graphify证据均有精确引用。
- base→feature与overlay-parent→overlay-head changed-file set均精确等于14-file allowlist。
- 没有把Runtime Component证据描述为Infra、HTTP、Trajectory/E2E、生产或完整切片已经实现。
