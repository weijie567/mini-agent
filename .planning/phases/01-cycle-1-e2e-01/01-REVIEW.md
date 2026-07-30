---
phase: 01
reviewed: 2026-07-30T12:59:50Z
depth: standard
reviewed_head: 11d6d0886d34a64b37ca34b0cfbc1aa1434b3044
files_reviewed: 73
files_reviewed_list:
  - AGENTS.md
  - PROJECT_DIRECTION.md
  - README.md
  - alembic/versions/20260727_0002_p0_records.py
  - alembic/versions/20260728_0003_request_understanding_v2_expand.py
  - docs/architecture/intent-design-reference.md
  - docs/architecture/memory-design-reference.md
  - docs/business-capabilities.md
  - docs/evaluation/agent-evaluation-strategy.md
  - docs/evaluation/p0-eval-coverage-matrix.md
  - docs/implementation/e2e01-thin-slice-implementation-spec.md
  - docs/implementation/e2e01-thin-slice-multi-agent-plan.md
  - evals/cases/e2e01-thin-slice.v1.json
  - evals/manifests/e2e01-thin-slice.v1.json
  - evals/model_scripts/e2e01-thin-slice.v1.json
  - src/mini_agent/api/http.py
  - src/mini_agent/application/agent_run_service.py
  - src/mini_agent/application/deterministic_renderer.py
  - src/mini_agent/application/persistence.py
  - src/mini_agent/application/ports.py
  - src/mini_agent/application/read_tool_executor.py
  - src/mini_agent/application/records.py
  - src/mini_agent/application/restart_recovery_service.py
  - src/mini_agent/bootstrap.py
  - src/mini_agent/core/control_gateway.py
  - src/mini_agent/core/memory.py
  - src/mini_agent/core/order.py
  - src/mini_agent/core/presentation_policy.py
  - src/mini_agent/core/request_processing.py
  - src/mini_agent/core/request_understanding.py
  - src/mini_agent/core/task_state.py
  - src/mini_agent/evaluation/artifacts.py
  - src/mini_agent/evaluation/graders.py
  - src/mini_agent/evaluation/harness.py
  - src/mini_agent/evaluation/scripted_provider.py
  - src/mini_agent/infrastructure/auth/p0_session.py
  - src/mini_agent/infrastructure/model/qwen_responses.py
  - src/mini_agent/infrastructure/order/postgres.py
  - src/mini_agent/infrastructure/persistence/models.py
  - src/mini_agent/infrastructure/persistence/postgres.py
  - src/mini_agent/infrastructure/persistence/recovery.py
  - tests/baseline/test_qwen_baseline.py
  - tests/component/application/test_agent_run_service.py
  - tests/component/application/test_deterministic_renderer.py
  - tests/component/application/test_persistence_contract.py
  - tests/component/application/test_ports_contract.py
  - tests/component/application/test_read_tool_executor.py
  - tests/component/application/test_record_contracts.py
  - tests/component/application/test_restart_recovery_service.py
  - tests/component/core/test_control_gateway.py
  - tests/component/core/test_identity_contract.py
  - tests/component/core/test_memory_trace_presentation_contract.py
  - tests/component/core/test_presentation_policy.py
  - tests/component/core/test_request_processing.py
  - tests/component/core/test_request_understanding_contract.py
  - tests/component/core/test_task_state_contract.py
  - tests/component/evaluation/test_e2e01_artifact_consistency.py
  - tests/component/evaluation/test_e2e01_graders.py
  - tests/component/evaluation/test_e2e01_scripted_model_provider.py
  - tests/component/evaluation/test_e2e01_versioned_artifact_loader.py
  - tests/component/model/test_e2e01_scripted_scenario_catalog.py
  - tests/component/model/test_qwen_responses_adapter.py
  - tests/e2e/test_e2e01_http_eval.py
  - tests/integration/evaluation/test_e2e01_offline_harness.py
  - tests/integration/test_agent_run_service_v2_persistence.py
  - tests/integration/test_database_migrations.py
  - tests/integration/test_http_session_adapter.py
  - tests/integration/test_offline_composition_root.py
  - tests/integration/test_postgres_atomicity.py
  - tests/integration/test_postgres_get_order.py
  - tests/integration/test_postgres_record_adapters.py
  - tests/integration/test_postgres_recovery.py
  - tests/integration/test_postgres_v2_request_understanding_writes.py
findings:
  critical: 1
  warning: 2
  info: 0
  total: 3
status: issues_found
---

# Phase 01：代码审查报告

**Reviewed:** 2026-07-30T12:59:50Z
**Depth:** standard
**Files Reviewed:** 73
**Status:** issues_found

## Summary

本次在独立 review-artifact Worktree 中，对 Phase 01 从 activation base `624475681847be5a8e463e32dafd28a0483b213b` 到 exact HEAD `11d6d0886d34a64b37ca34b0cfbc1aa1434b3044` 的 73 个显式文件执行 standard review。审查覆盖可信 Session / HTTP 身份边界、Request Understanding v2、Runtime 状态与持久化、Control Gateway、read Tool、恢复、Qwen Adapter、真实 offline Composition、PostgreSQL exact-Run Evidence、Eval Harness / Grader / artifacts 及相关 Component / Integration / E2E 测试。

- `CONFIRMED`：requested = accepted = unique = 73；每项均为仓库内 regular tracked file，literal `git ls-files -- <path>` 精确返回单一路径；HEAD 与 tree 分别为 `11d6d0886d34a64b37ca34b0cfbc1aa1434b3044`、`2814fdccb79a6739b33156a4ca13e104ea64daf2`。
- `CONFIRMED`：未运行 Graphify；review 前工作树干净。
- `CONFIRMED`：定向执行 127 项高风险测试，结果为 `127 passed in 37.35s`；覆盖 Qwen Adapter、PresentationPolicy、AgentRunService、ReadToolExecutor、RestartRecoveryService 与真实 HTTP → Runtime → PostgreSQL → Eval E2E。
- `CONFIRMED`：`git diff --check` 对 scope 内变更无输出。
- `OPEN`：未执行 canonical 全量 `uv run pytest`；没有在本次 review 重跑 migration chain 或完整 Component / Integration suite。
- `CONFIRMED`：`DASHSCOPE_API_KEY` 与 `DASHSCOPE_BASE_URL` 在 review 环境中均缺失，因此未运行 credentialed Qwen Baseline；不能据此形成真实 Qwen PASS / FAIL。

审查发现 1 个 Critical 与 2 个 Warning。未发现可证实的 Info 项。`CR-01` 必须完成修复、验证和重新 exact-head review，不得以 owner 裁决替代修复；两个 Warning 必须修复，或由对应 canonical owner 按治理规则显式裁决。上述条件满足前，Phase 01 不得推进 lifecycle / release gate。

## Critical

### CR-01：Qwen Adapter 允许通过明文 HTTP 发送 API Key

**File:** `src/mini_agent/infrastructure/model/qwen_responses.py:46-64`

**Issue:** `CONFIRMED`：构造器把 `http` 和 `https` 都视为合法 scheme；随后 `_invoke_presentation()`（125–132 行）和 `_v2_invoke_request_understanding()`（204–211 行）无条件把真实 `api_key` 放入 `Authorization: Bearer ...`。credentialed runner 又直接消费 `DASHSCOPE_BASE_URL`。因此 `DASHSCOPE_BASE_URL=http://...` 是当前代码接受的配置，并会在真实网络请求中明文传输凭据。Spec 给出的 DashScope endpoint 是 HTTPS；现有测试没有断言 HTTP endpoint 必须在发起 transport 前失败。`OPEN`：是否还要把 host 限定为批准的地域 / Workspace endpoint，应由 Provider / security owner 裁决；但最低限度的 HTTPS 要求不依赖该裁决。

**Fix:**

```python
try:
    parsed_url = httpx.URL(base_url)
except Exception:
    raise ValueError("base_url must be a valid HTTPS URL") from None
if parsed_url.scheme != "https" or parsed_url.host is None:
    raise ValueError("base_url must be a valid HTTPS URL")
```

同时增加 negative test：传入 `http://...` 时构造或 baseline preflight 必须 fail closed，MockTransport / external transport 调用次数保持为 0；若批准代理或地域 endpoint，需要以显式 allowlist 表达，不能回退到任意 HTTP。

## Warnings

### WR-01：Harness 可把 `CONTRACT_DEFINED` Case 持久化为 `PASS`

**File:** `src/mini_agent/evaluation/harness.py:2324-2464`

**Issue:** `CONFIRMED`：Harness 选择 Case 后直接执行、持久化 `EvalResultRecord`，并在所有结果为 `PASS` 时设置 `command_passed=True`，没有检查 `case.lifecycle_status`。与此同时 artifact loader 在 `src/mini_agent/evaluation/artifacts.py:351`、`492-493` 强制 manifest 与每个 Case 都是 `CONTRACT_DEFINED`；`evals/cases/e2e01-thin-slice.v1.json` 与 manifest 也保持该值。canonical Eval owner 在 `docs/evaluation/agent-evaluation-strategy.md:273-282` 明确规定 `CONTRACT_DEFINED` 尚无可运行 Harness / Fixture，且“不得把 `CONTRACT_DEFINED` 记为通过”。本次实际通过的 E2E test 在 `tests/e2e/test_e2e01_http_eval.py:178-193` 正好证明当前链会对这批 Case 产出 `command_passed=True` 和 `PASS` records。这会让 lifecycle 尚未裁决的执行证据被下游误用为 gate PASS。

**Fix:** 在 lifecycle 尚为 `CONTRACT_DEFINED` 时先修复代码侧的 fail-closed 边界，不得用当前错误的 `PASS` 结果反向推进 lifecycle。Harness 应在任何受测执行或 Result staging 前拒绝非 `EXECUTABLE` / `REGRESSION_GATE` Case：

```python
executable = {"EXECUTABLE", "REGRESSION_GATE"}
if any(
    self._artifacts.case_by_id(case_id).lifecycle_status not in executable
    for case_id in selected_ids
):
    return EvalLaneRunOutcome(
        lane=lane,
        results=(),
        execution_failures=(lifecycle_failure,),
        command_passed=False,
    )
```

在 lifecycle 尚未切换时，测试应断言不会写入 `PASS`，而不是以 `command_passed=True` 证明 release gate。待其余 post-execution quality gate 通过后，再由 canonical Coverage Matrix owner 根据已经对齐的实现事实裁决 lifecycle；随后由独立 Eval implementation Packet 同步 Case artifact、manifest、authenticated hash 与 loader 的 closed value，并重跑适用门禁。这个后继 activation 不得与当前 fail-closed 修复混为一次未经审查的状态跳变。

### WR-02：Active 状态 owner 仍把 exact HEAD 已实现的纵向组件写成 `NOT_FOUND`

**File:** `docs/evaluation/p0-eval-coverage-matrix.md:7`

**Issue:** `CONFIRMED`：该 active Eval mapping 在 7、269–282 行仍称真实 `EvalCaseSut`、PostgreSQL `EvalEvidence` reader、Composition Root、HTTP / Trajectory / E2E Result 与 credentialed runner 未出现；`docs/evaluation/agent-evaluation-strategy.md:483`、`PROJECT_DIRECTION.md:347`、`README.md:15,68` 也保留同类结论。exact HEAD 已存在 `OfflineE2E01Composition`（`src/mini_agent/bootstrap.py:518`）、真实 `execute_case`（811 行）、PostgreSQL exact owner-scoped reader（`src/mini_agent/infrastructure/persistence/postgres.py:947`）、Harness wiring（`src/mini_agent/bootstrap.py:1022`）和 credential-aware Qwen runner（`src/mini_agent/evaluation/harness.py:1991`）；本次定向 E2E 又实际通过。Case lifecycle 是否晋级仍是独立 owner 决策，但“实现是否存在”已不是 `NOT_FOUND`。当前漂移会把后续 planning 错误路由成重复实现，也违反项目的 owner-first cross-file alignment 规则。

**Fix:** 在任何 lifecycle 晋级之前，先按 single-writer owner 顺序更新 canonical Eval owner 的实现事实：把真实 offline vertical 与 credential-aware runner 标为 `CONFIRMED / IMPLEMENTED`，把本环境 credentialed result 保持为 `NOT_RUN`，并明确此时 lifecycle 仍是 `CONTRACT_DEFINED`。随后按 owner 引用关系分别同步 `PROJECT_DIRECTION.md`、`README.md`、`AGENTS.md` 与 `docs/business-capabilities.md` 的状态横幅。只有事实前提已对齐且其余 post-execution quality gate 通过后，Coverage Matrix owner 才进行一次 lifecycle 裁决；不得先在错误事实下裁决再重复裁决，也不得把“代码存在 / offline E2E 可复现”扩大成 canonical product startup、真实 Qwen Result、production readiness 或整个 P0 完成。

## Verification

执行命令：

```text
PYTHONDONTWRITEBYTECODE=1 uv run pytest -p no:cacheprovider -q \
  tests/component/model/test_qwen_responses_adapter.py \
  tests/component/core/test_presentation_policy.py \
  tests/component/application/test_agent_run_service.py \
  tests/component/application/test_read_tool_executor.py \
  tests/component/application/test_restart_recovery_service.py \
  tests/e2e/test_e2e01_http_eval.py
```

结果：

```text
127 passed in 37.35s
```

未执行：

- canonical 全量 `uv run pytest`
- `uv run alembic upgrade head`
- `uv run pytest -m qwen_baseline`（两项必需环境变量均缺失）
- lint / type-check / build（项目尚无 canonical 命令）

---

_Reviewed: 2026-07-30T12:59:50Z_
_Reviewer: Codex (gsd-code-reviewer)_
_Depth: standard_
