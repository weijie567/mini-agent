---
phase: 01-cycle-1-e2e-01
slug: cycle-1-e2e-01-w2
scope: 01-05-01-07
status: execution_evidence_in_progress
nyquist_compliant: true
wave_0_complete: false
created: "2026-07-27"
---

# Phase 1 W2｜Validation Strategy

> **DERIVED / NON_NORMATIVE**
> 本文件只定义 01-05/06/07 execution feedback sampling。Case、指标、Critical failure 与生命周期仍由 canonical Eval owner 持有；这里的绿色测试不能替代 01-08 真实纵向证据。

## Test Infrastructure

| Property | Value |
|---|---|
| Framework | pytest / pytest-asyncio；PostgreSQL integration tests |
| Config | `pyproject.toml`、`tests/conftest.py`、`compose.yaml`、`alembic.ini` |
| Quick command | 每个 Task Packet 的 exact focused pytest command |
| Full suite | `uv run pytest` |
| Infra preflight | `uv sync --all-groups`；启动 disposable db / db-test；`uv run alembic upgrade head` |
| Current exact-base evidence | `466 passed` at `c35687dafa3881bb322d91515068d8d39be79df6` |
| Max feedback latency | focused task tests应在每个原子 commit前完成；full suite在每个 Packet handoff前完成 |

仓库当前没有 canonical lint、type-check、build 或 app-start命令，也没有 pinned Ruff dependency；不得编造。允许的附加机械检查为 `compileall`、`git diff --check`、artifact SHA 与 changed-file containment。

## Sampling Rate

- 每个 TDD task：先运行新测试取得预期 RED，再完成 GREEN。
- 每个原子 commit 前：运行该 task 的 exact focused tests。
- 每个 Packet handoff 前：运行 Packet 全部 focused tests、`uv run pytest` 和机械 containment。
- 每个 feature PR 最新 head：独立 reviewer 读取 exact diff和测试证据；finding修复后重新运行受影响 focused + full suite。
- 每次串行合并前：在 latest integration overlay / merge candidate上重复 full suite。
- 01-08 前：三个 Packet都必须有 reviewed exact-head和latest-integration compatibility证据。

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure behavior | Test type | Automated command | File exists | Status |
|---|---|---:|---|---|---|---|---|---|
| 01-05-01 | 01-05 | 1 | E2E01-01/04 | RT-S01/RT-T01 | trusted identity、candidate validation、binding、state reducer | Component | `uv run pytest tests/component/core/test_request_processing.py -x` | ❌ W0 | ⬜ pending |
| 01-05-02 | 01-05 | 1 | E2E01-01/04 | RT-T02/RT-E01 | snapshot/schema/binding/version Gate fail closed | Component | `uv run pytest tests/component/core/test_control_gateway.py -x` | ❌ W0 | ⬜ pending |
| 01-05-03 | 01-05 | 1 | E2E01-01/04 | RT-R01/RT-D01 | durable fence before唯一 read；no retry | Component | `uv run pytest tests/component/application/test_read_tool_executor.py -x` | ❌ W0 | ⬜ pending |
| 01-05-04 | 01-05 | 1 | E2E01-01/04 | RT-I01/RT-T03 | fact-free plan；renderer仅注入安全 Observation并完成bounded result mapping | Component | `uv run pytest tests/component/core/test_presentation_policy.py tests/component/application/test_deterministic_renderer.py -x` | ❌ W0 | ⬜ pending |
| 01-05-05 | 01-05 | 1 | E2E01-01/04 | RT-R02/RT-I02 | happens-before、budget、foreign/nonexistent等价、stale race | Component | `uv run pytest tests/component/application/test_agent_run_service.py -x` | ❌ W0 | ⬜ pending |
| 01-05-06 | 01-05 | 1 | E2E01-01/04 | RT-R03/RT-T04 | restart不resume/replay；exact recovery events | Component | `uv run pytest tests/component/application/test_restart_recovery_service.py -x` | ❌ W0 | ⬜ pending |
| 01-06-01 | 01-06 | 1 | E2E01-01/04 | IF-T01/IF-R01 | 三表、closed constraints、upgrade/downgrade | Integration | `uv run pytest tests/integration/test_database_migrations.py -x` | ✅ extend | ⬜ pending |
| 01-06-02 | 01-06 | 1 | E2E01-01/04 | IF-T02/IF-I01 | 17 record / 5 refs exact round-trip与owner filtering | Integration | `uv run pytest tests/integration/test_postgres_record_adapters.py -x` | ❌ W0 | ⬜ pending |
| 01-06-03 | 01-06 | 1 | E2E01-01/04 | IF-T03/IF-R02 | aggregate/CAS/fence/Observation单事务 | Integration | `uv run pytest tests/integration/test_postgres_atomicity.py -x` | ❌ W0 | ⬜ pending |
| 01-06-04 | 01-06 | 1 | E2E01-01/04 | IF-R03/IF-D01 | bounded closure；APPLIED state+Trace atomic | Integration | `uv run pytest tests/integration/test_postgres_recovery.py -x` | ❌ W0 | ⬜ pending |
| 01-06-05 | 01-06 | 1 | E2E01-04 | IF-S01/IF-I02 | trusted session；401等价；handler前认证 | Integration | `uv run pytest tests/integration/test_http_session_adapter.py -x` | ❌ W0 | ⬜ pending |
| 01-06-06 | 01-06 | 1 | E2E01-01/04 | IF-I03 | owner-scoped SQL；foreign/nonexistent不可区分 | Integration | `uv run pytest tests/integration/test_postgres_get_order.py -x` | ❌ W0 | ⬜ pending |
| 01-07-01 | 01-07 | 1 | E2E01-01/04 | EV-T01/EV-E01 | closed manifest/path/hash/ref loader | Component | `uv run pytest tests/component/evaluation/test_e2e01_versioned_artifact_loader.py -x` | ❌ W0 | ⬜ pending |
| 01-07-02 | 01-07 | 1 | E2E01-01/04 | EV-S01/EV-I01 | strict script cursor；无network；raw error丢弃 | Component | `uv run pytest tests/component/evaluation/test_e2e01_scripted_model_provider.py -x` | ❌ W0 | ⬜ pending |
| 01-07-03 | 01-07 | 1 | E2E01-01/04 | EV-S02/EV-I03 | Qwen request allowlist、exact one target call、mock transport与raw error丢弃 | Component | `uv run pytest tests/component/model/test_qwen_responses_adapter.py -x` | ❌ W0 | ⬜ pending |
| 01-07-04 | 01-07 | 1 | E2E01-01/04 | EV-T02/EV-I02 | 13 graders均有pass与tamper-fail；CF强制FAIL | Component | `uv run pytest tests/component/evaluation/test_e2e01_graders.py -x` | ❌ W0 | ⬜ pending |
| 01-07-05 | 01-07 | 1 | E2E01-01/04 | EV-R01/EV-R02 | Result/Failure矩阵、run/case/lane/attempt append-only、cross-lane distinctness、paired completeness | Integration | `uv run pytest tests/integration/evaluation/test_e2e01_offline_harness.py -x` | ❌ W0 | ⬜ pending |
| 01-07-06 | 01-07 | 1 | E2E01-01/04 | EV-I04 | marker与missing-input / real-SUT-not-wired preflight；canonical SKIPPED/NOT_RUN且零network | Baseline preflight | `env -u DASHSCOPE_API_KEY -u DASHSCOPE_BASE_URL uv run pytest -m qwen_baseline tests/baseline/test_qwen_baseline.py -x`；`DASHSCOPE_API_KEY=not-a-real-key DASHSCOPE_BASE_URL=https://example.invalid uv run pytest -m qwen_baseline tests/baseline/test_qwen_baseline.py -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

## Wave 0 Requirements

Wave 0 是各 Packet的首个测试提交，不新增共享 bootstrap：

- 01-05：创建 7 个 allowlisted Component test files。
- 01-06：扩展现有 migration test并创建 5 个 allowlisted Infra integration test files；复用 byte-identical `tests/conftest.py`。
- 01-07：创建 6 个 allowlisted Eval / model / baseline test files。
- 不修改 `pyproject.toml`、`uv.lock`、共享 fixtures或canonical owners。

`wave_0_complete` 只有三个 writer均提交并展示预期 RED 后才能改为 `true`。

## Packet Full Gates

### 01-05 Runtime

```bash
uv sync --all-groups
docker compose -p mini-agent \
  -f /Users/ming/projects/mini-agent/compose.yaml \
  --profile test up --wait -d db-test
uv run pytest tests/integration/test_database_migrations.py -x
uv run pytest \
  tests/component/core/test_request_processing.py \
  tests/component/core/test_control_gateway.py \
  tests/component/core/test_presentation_policy.py \
  tests/component/application/test_agent_run_service.py \
  tests/component/application/test_read_tool_executor.py \
  tests/component/application/test_deterministic_renderer.py \
  tests/component/application/test_restart_recovery_service.py -x
uv run pytest
```

### 01-06 Infra

```bash
uv sync --all-groups
docker compose -p mini-agent \
  -f /Users/ming/projects/mini-agent/compose.yaml \
  up --wait -d db
docker compose -p mini-agent \
  -f /Users/ming/projects/mini-agent/compose.yaml \
  --profile test up --wait -d db-test
uv run alembic upgrade head
uv run pytest tests/integration/test_database_migrations.py -x
uv run pytest \
  tests/integration/test_database_migrations.py \
  tests/integration/test_http_session_adapter.py \
  tests/integration/test_postgres_record_adapters.py \
  tests/integration/test_postgres_atomicity.py \
  tests/integration/test_postgres_recovery.py \
  tests/integration/test_postgres_get_order.py -x
uv run pytest
```

Migration tests必须包含upgrade → downgrade → upgrade；禁止对共享或未知数据库执行破坏操作。

### 01-07 Eval

```bash
uv sync --all-groups
docker compose -p mini-agent \
  -f /Users/ming/projects/mini-agent/compose.yaml \
  --profile test up --wait -d db-test
uv run pytest tests/integration/test_database_migrations.py -x
uv run pytest \
  tests/component/evaluation/test_e2e01_versioned_artifact_loader.py \
  tests/component/evaluation/test_e2e01_scripted_model_provider.py \
  tests/component/model/test_qwen_responses_adapter.py \
  tests/component/evaluation/test_e2e01_graders.py \
  tests/integration/evaluation/test_e2e01_offline_harness.py -x
shasum -a 256 \
  evals/fixtures/e2e01-thin-slice.v1.json \
  evals/cases/e2e01-thin-slice.v1.json \
  evals/model_scripts/e2e01-thin-slice.v1.json \
  evals/lanes/e2e01-thin-slice.v1.json \
  evals/manifests/e2e01-thin-slice.v1.json
uv run pytest
```

01-07 只运行显式清除凭据的 preflight，证明 `NOT_RUN / SKIPPED` 与零network。真实 Qwen lane必须等 01-08 接入 real `EvalCaseSut` 后，才在 W4 exact integrated head具备显式配置时单独运行；默认 full gate因 marker排除它：

```bash
env -u DASHSCOPE_API_KEY -u DASHSCOPE_BASE_URL \
  uv run pytest -m qwen_baseline tests/baseline/test_qwen_baseline.py -x

DASHSCOPE_API_KEY=not-a-real-key \
DASHSCOPE_BASE_URL=https://example.invalid \
  uv run pytest -m qwen_baseline tests/baseline/test_qwen_baseline.py -x

# W4 only, after 01-08 real SUT wiring:
uv run pytest -m qwen_baseline tests/baseline/test_qwen_baseline.py -x
```

缺失 `DASHSCOPE_API_KEY` / `DASHSCOPE_BASE_URL` 或尚无 01-08 real SUT wiring时必须得到 canonical `SKIPPED / NOT_RUN`，不得生成 PASS或访问网络；这不阻塞离线 release gate。

## Manual-only Verification

| Behavior | Requirement | Why manual | Instructions |
|---|---|---|---|
| GitHub branch / PR ownership | E2E01-01/04 | Git metadata不由pytest证明 | 比较exact base/head/tree、changed-file allowlist、PR base/head与reviewed SHA |
| Latest-integration compatibility | E2E01-01/04 | 三个Sibling branch都从相同base开始 | 每次merge前生成latest overlay并运行full suite，确认无hidden contract drift |
| Nonclaims / lifecycle discipline | E2E01-01/04 | 需要审查文案和manifest状态 | 确认Case仍`CONTRACT_DEFINED`、Requirements unchecked；Adapter测试不冒充真实Qwen Baseline或production claim |

01-08 的真实 HTTP / PostgreSQL / Trajectory / E2E、Security audit与UAT不属于这三个 Packet的“manual替代”；它们是后续必须自动化或可复现执行的独立 gate。

## Validation Sign-off

- [x] 每个研究 task都有 planned automated command或Wave 0 test file。
- [x] 没有连续三个 task缺失自动化反馈。
- [x] 所有 missing test reference均在exact Packet allowlist内。
- [x] 无watch-mode flag。
- [x] `nyquist_compliant: true`。
- [x] 01-05/06/07 每个 task 均有 exact automated command 与 allowlisted Wave 0 test。
- [x] 初始 Plan Checker loop 3/3 `PASS` 已被 PR #26 首个 exact-head review 的 canonical/security findings 明确 supersede，不再作为 approval。
- [x] 超出三轮 cap 后的只读 checker audit 识别出两项 `MAJOR`；对应 approval 声明与第二条零网络命令已修正，不再启动第 5 个 planner loop。
- [x] planning PR #26 final published head `2922308b...` 已取得canonical与security/process两个Codex只读Reviewer的`PASS`，所有planning findings已关闭，并merge为`968b4a9...`；持久化记录见PR #26 [canonical evidence](https://github.com/weijie567/mini-agent/pull/26#issuecomment-5086174316)与[security/process evidence](https://github.com/weijie567/mini-agent/pull/26#issuecomment-5086174609)，不是GitHub Reviews API formal approvals。
- [x] 三个 Packet Wave 0 RED证据已提交至各自published feature history。
- [x] 三个 Packet focused / full本地门禁均green：Runtime 83 / 549，Infra 68 / 496，Eval 111 / 577（1 deselected）；这些结果仍须独立review与latest-integration replay。
- [ ] 三个 exact-head review与latest-integration compatibility均PASS。

**Approval:** `PLANNING_GATE_PASS / FEATURE_REVIEW_AND_INTEGRATION_PENDING`。PR #26与post-merge preflight已允许三个execution Worktree从`c35687d...`创建；PR #28/#30/#29只证明published component feature heads与本地门禁已形成，不批准Case、Baseline、release或lifecycle结论。Feature exact-head review、latest-integration compatibility、serial merge与01-08纵向证据仍待产生。
