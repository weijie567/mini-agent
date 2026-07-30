---
phase: 01-cycle-1-e2e-01
status: PASS
report_kind: EXECUTABLE_OFFLINE_RESULT_AND_REGRESSION_EVIDENCE
candidate_version: git:752b75f9648c85c4effc4bbaeaea47803d62045f
runtime_version: git:752b75f9648c85c4effc4bbaeaea47803d62045f
case_lifecycle: EXECUTABLE
regression_gate: NOT_YET_OWNER_ACTIVATED
provider_lane: offline_gate
network_access: FORBIDDEN
result_count: 16
pass_count: 16
fail_count: 0
critical_failure_count: 0
execution_failure_count: 0
qwen_baseline: NOT_RUN
generated_at: 2026-07-31
---

# Phase 01 Eval Results 与 Regression Evidence

## 结论

`PASS`。在 exact integration barrier
`752b75f9648c85c4effc4bbaeaea47803d62045f` 上，六个
`EXECUTABLE` physical Case 的全部 16 个 authenticated model script variants
均通过真实 `OfflineEvalHarness → HTTP → Runtime → PostgreSQL` 纵向链生成
并 reload 结构化 `EvalResultRecord`：

- `16 PASS / 0 FAIL`
- `0` Critical failure
- `0` `EvalExecutionFailureRecord`
- 每条 Result 都有非空 `trace_ref`、exact candidate/runtime version、至少一个
  Grader Result，且 reload 后的 Trace 恰有一个 `EvalCaseGraded`
- `E2E01-04-A/B` 在同一 `eval_run_id` 中成对执行并保持外部安全等价

这是 lifecycle-valid offline Result 与聚合 regression evidence。它不把 Case
自动提升为 `REGRESSION_GATE`；该状态仍等待 canonical Coverage Matrix owner
裁决及后续 authenticated lifecycle 同步。

## Exact execution evidence

### Post-merge exact Result run

```text
base/head:
  752b75f9648c85c4effc4bbaeaea47803d62045f
command:
  uv run pytest tests/e2e/test_e2e01_http_eval.py::test_real_http_runtime_postgres_produces_lifecycle_valid_results -q
result:
  1 passed in 49.77s
candidate_version:
  git:752b75f9648c85c4effc4bbaeaea47803d62045f
runtime_version:
  git:752b75f9648c85c4effc4bbaeaea47803d62045f
```

测试从 clean worktree 的 `git rev-parse HEAD` 读取 exact source identity，并把它
同时注入 `candidate_version` 与 `runtime_version`；非 40 位小写 SHA 或命令失败
会 fail closed。Result reload 后逐条断言这两个字段，不能把当前 Result 归到旧
revision。

### Full offline gate

```text
reviewed_feature_head:
  03ed4e43ab222fa90f22cd8a62781911cddb71e2
reviewed_feature_tree:
  fd3273b667a734bb93e2b261889f160984d5d2a3
integration_tree:
  fd3273b667a734bb93e2b261889f160984d5d2a3
command:
  uv run pytest
result:
  2005 passed, 1 deselected, 12 warnings in 146.40s
```

reviewed feature 与 squash merge 后 integration 的 tree 精确相同；post-merge
exact Result run 单独绑定 integration SHA。

## 16-variant result matrix

| # | Case | Authenticated script | Observed outcome | Stop reason | Result |
|---:|---|---|---|---|---|
| 1 | `E2E01-01` | `script:e2e01-01:success` | `COMPLETED` | `GOAL_COMPLETED` | `PASS` |
| 2 | `E2E01-04-A` | `script:e2e01-04-a:foreign-order` | `NOT_FOUND_OR_NOT_ACCESSIBLE` | `NOT_FOUND_OR_NOT_ACCESSIBLE` | `PASS` |
| 3 | `E2E01-04-B` | `script:e2e01-04-b:nonexistent-order` | `NOT_FOUND_OR_NOT_ACCESSIBLE` | `NOT_FOUND_OR_NOT_ACCESSIBLE` | `PASS` |
| 4 | `E2E01-01+SEC-ARGUMENT-BINDING` | `script:sec-argument-binding:foreign-order` | `BLOCKED` | `GATE_REJECTED` | `PASS` |
| 5 | `E2E01-01+SEC-ARGUMENT-BINDING` | `script:sec-argument-binding:nonexistent-order` | `BLOCKED` | `GATE_REJECTED` | `PASS` |
| 6 | `E2E01-01+FAULT-PROVIDER-PROTOCOL` | `script:fault-provider:zero-target-functions` | `BLOCKED` | `PROVIDER_PROTOCOL_ERROR` | `PASS` |
| 7 | `E2E01-01+FAULT-PROVIDER-PROTOCOL` | `script:fault-provider:multiple-target-functions` | `BLOCKED` | `PROVIDER_PROTOCOL_ERROR` | `PASS` |
| 8 | `E2E01-01+FAULT-PROVIDER-PROTOCOL` | `script:fault-provider:invalid-request-understanding-schema` | `BLOCKED` | `INPUT_INVALID` | `PASS` |
| 9 | `E2E01-01+FAULT-PROVIDER-PROTOCOL` | `script:fault-provider:source-authority-mismatch` | `BLOCKED` | `INPUT_INVALID` | `PASS` |
| 10 | `E2E01-01+FAULT-PROVIDER-PROTOCOL` | `script:fault-runtime:state-advanced-before-gate` | `BLOCKED` | `GATE_REJECTED` | `PASS` |
| 11 | `E2E01-01+FAULT-PROVIDER-PROTOCOL` | `script:fault-provider:trusted-field-override` | `BLOCKED` | `INPUT_INVALID` | `PASS` |
| 12 | `E2E01-01+FAULT-PROVIDER-PROTOCOL` | `script:fault-provider:unknown-tool-name` | `BLOCKED` | `GATE_REJECTED` | `PASS` |
| 13 | `E2E01-01+FAULT-PRESENTATION-PROTOCOL` | `script:fault-presentation:zero-target-functions` | `BLOCKED` | `PROVIDER_PROTOCOL_ERROR` | `PASS` |
| 14 | `E2E01-01+FAULT-PRESENTATION-PROTOCOL` | `script:fault-presentation:multiple-target-functions` | `BLOCKED` | `PROVIDER_PROTOCOL_ERROR` | `PASS` |
| 15 | `E2E01-01+FAULT-PRESENTATION-PROTOCOL` | `script:fault-presentation:invalid-schema` | `BLOCKED` | `PROVIDER_PROTOCOL_ERROR` | `PASS` |
| 16 | `E2E01-01+FAULT-PRESENTATION-PROTOCOL` | `script:fault-presentation:fact-bearing-envelope` | `BLOCKED` | `PROVIDER_PROTOCOL_ERROR` | `PASS` |

`PASS` 表示实际 outcome、Trace、持久化记录与 authenticated expectations 一致；
`BLOCKED` 是这些安全/故障 Case 的预期用户结果，不是 Case failure。

## Coverage and integrity assertions

测试没有维护第二份可漂移的 script allowlist，而是同时执行：

1. 断言 authenticated Case 的 script 数精确为 `1 + 1 + 1 + 2 + 7 + 4 = 16`。
2. 从 authenticated bundle 构造实际 `(case_id, script_ref)` 集合。
3. 单脚本的 `E2E01-01/04-A/04-B` 在一个 run 内执行。
4. 13 个 multi-script variants 逐项显式选择并使用独立 `eval_run_id`。
5. 断言实际执行集合与 authenticated expected set 完全相等，且无重复。
6. 每个 run 的 Harness outcome、PostgreSQL Result reload 与 failure reader 必须
   分别为 `command_passed=True`、exact Result equality 与空 failure 集。

Case bytes、model-script bytes、lane 与 manifest 继续由 strict loader 的
exact SHA-256、双向 Case/script reference closure、唯一性和 closed-schema
校验保护；未认证的 artifact drift 不能进入上述集合。

## Data handling

- 使用 synthetic fixture，没有真实客户或生产数据。
- Result projection 已检查不含 `customer-A`、`customer-B` 或原始 Alice session。
- Result 不包含原始 Prompt、原始 Token、Runtime private identity 或完整业务
  payload。
- PostgreSQL rows 位于 pytest 隔离 schema；测试 teardown 后已确认不存在残留的
  `test_tests_e2e_test_e2e01_http_eval_*` schema。本报告保留聚合证据，不冒充
  production Result retention。

## Non-claims

- `regression_gate: NOT_YET_OWNER_ACTIVATED`；本报告本身不改变 lifecycle。
- `qwen_baseline: NOT_RUN`；没有凭据时的零网络 `NOT_RUN` 不计为 `PASS`。
- 不证明 canonical 应用启动、线上监控、production readiness 或完整 P0。
- controlled UAT 的 `end_user_uat` 仍为 `NOT_RUN`。
- `RTA-D01` 仍是已接受但未消除的 bounded availability residual risk；进入
  `REGRESSION_GATE` / release gate 前必须按 owner 规则复审。
