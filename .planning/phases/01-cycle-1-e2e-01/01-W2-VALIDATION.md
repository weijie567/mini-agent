---
phase: 01-cycle-1-e2e-01
slug: cycle-1-e2e-01-w2
scope: 01-04H-01-07-with-01-05R-01-06R
status: execution_evidence_in_progress
nyquist_compliant: true
wave_0_complete: true
created: "2026-07-27"
---

# Phase 1 W2｜Validation Strategy

> **DERIVED / NON_NORMATIVE**
> 本文件只定义已完成01-04H/01-05R、historical 01-05/06、replacement 01-06R与current 01-07 execution feedback sampling。Case、指标、Critical failure 与生命周期仍由 canonical Eval owner 持有；这里的绿色测试不能替代01-08真实纵向证据或post-execution quality gate。

## Test Infrastructure

| Property | Value |
|---|---|
| Framework | pytest / pytest-asyncio；PostgreSQL integration tests |
| Config | `pyproject.toml`、`tests/conftest.py`、`compose.yaml`、`alembic.ini` |
| Quick command | 每个 Task Packet 的 exact focused pytest command |
| Full suite | `uv run pytest` |
| Infra preflight | `uv sync --all-groups`；启动 disposable db / db-test；`uv run alembic upgrade head` |
| Current exact-base evidence | `660 passed` + `38 migration passed` at 01-05R merge / 01-06R base `fb607019130843c94825a47d7822518cbdb2143c` |
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
| 01-04H-01 | 01-04H | 9 | E2E01-01/04 | TERM-R01/TERM-T01 | RED覆盖partial terminal turn、非法reason/outcome/Task/status组合与Trace污染 | Component contract | `uv run pytest tests/component/application/test_record_contracts.py tests/component/application/test_ports_contract.py -x` | ✅ existing | ✅ green |
| 01-04H-02 | 01-04H | 9 | E2E01-01/04 | TERM-D01/TERM-E01 | GREEN冻结complete aggregate、APPLIED全写与non-APPLIED零写Port语义 | Component contract | `uv run pytest tests/component/application/test_record_contracts.py tests/component/application/test_ports_contract.py -x`；`uv run pytest` | ✅ existing | ✅ green |
| 01-05R-01 | 01-05R | 10 | E2E01-01/04 | RT-S01/RT-T01/RT-T02/RT-E01 | controlled donor replay；trusted identity、candidate validation、binding、state reducer与Gateway仍闭合 | Component replay | `uv run pytest tests/component/core/test_request_processing.py tests/component/core/test_control_gateway.py -x` | ✅ donor | ✅ green |
| 01-05R-02 | 01-05R | 10 | E2E01-01/04 | RT-R01/RT-D01/RT-I01/RT-T03 | durable fence、no retry、fact-free plan与safe renderer保持donor blob/behavior | Component replay | `uv run pytest tests/component/core/test_presentation_policy.py tests/component/application/test_read_tool_executor.py tests/component/application/test_deterministic_renderer.py -x` | ✅ donor | ✅ green |
| 01-05R-03 | 01-05R | 10 | E2E01-01/04 | RT-R04/RT-D02/RT-I03 | RED禁止split terminal writes；GREEN只用一个complete aggregate且APPLIED后无await | Component replacement | `uv run pytest tests/component/application/test_agent_run_service.py -x` | ✅ extend | ✅ green |
| 01-05R-04 | 01-05R | 10 | E2E01-01/04 | RT-R03/RT-T04 | restart不resume/replay；exact recovery events保持donor blob/behavior | Component replay | `uv run pytest tests/component/application/test_restart_recovery_service.py -x` | ✅ donor | ✅ green |
| 01-06R-01 | 01-06R | 11 | E2E01-01/04 | IF-T01/IF-T04/IF-I04 | controlled donor replay后以首个test-only RED只暴露raw disclosure与late ToolCall | Integration replacement | `uv run pytest tests/integration/test_postgres_record_adapters.py tests/integration/test_postgres_atomicity.py tests/integration/test_postgres_recovery.py -x` | ✅ donor/extend | ⬜ pending |
| 01-06R-02 | 01-06R | 11 | E2E01-01/04 | IF-T01/IF-T04/IF-I04/IF-D02 | bounded envelope/reference error；parent Run RUNNING fence；两种无sleep顺序无orphan | Integration replacement | `uv run pytest tests/integration/test_postgres_record_adapters.py tests/integration/test_postgres_atomicity.py tests/integration/test_postgres_recovery.py -x` | ✅ donor/extend | ⬜ pending |
| 01-06R-03 | 01-06R | 11 | E2E01-01/04 | IF-R03/IF-R04/IF-D02 | Task 2 GREEN后以第二个RED暴露partial terminal commit，再使with/no Task/FAILED complete transaction与逐child fault全回滚 | Integration replacement | `uv run pytest tests/integration/test_postgres_atomicity.py -x` | ✅ donor/extend | ⬜ pending |
| 01-07-01 | 01-07 | 1 | E2E01-01/04 | EV-T01/EV-E01 | closed manifest/path/hash/ref loader | Component | `uv run pytest tests/component/evaluation/test_e2e01_versioned_artifact_loader.py -x` | ❌ W0 | ⬜ pending |
| 01-07-02 | 01-07 | 1 | E2E01-01/04 | EV-S01/EV-I01 | strict script cursor；无network；raw error丢弃 | Component | `uv run pytest tests/component/evaluation/test_e2e01_scripted_model_provider.py -x` | ❌ W0 | ⬜ pending |
| 01-07-03 | 01-07 | 1 | E2E01-01/04 | EV-S02/EV-I03 | Qwen request allowlist、exact one target call、mock transport与raw error丢弃 | Component | `uv run pytest tests/component/model/test_qwen_responses_adapter.py -x` | ❌ W0 | ⬜ pending |
| 01-07-04 | 01-07 | 1 | E2E01-01/04 | EV-T02/EV-I02 | 13 graders均有pass与tamper-fail；CF强制FAIL | Component | `uv run pytest tests/component/evaluation/test_e2e01_graders.py -x` | ❌ W0 | ⬜ pending |
| 01-07-05 | 01-07 | 1 | E2E01-01/04 | EV-R01/EV-R02 | Result/Failure矩阵、run/case/lane/attempt append-only、cross-lane distinctness、paired completeness | Integration | `uv run pytest tests/integration/evaluation/test_e2e01_offline_harness.py -x` | ❌ W0 | ⬜ pending |
| 01-07-06 | 01-07 | 1 | E2E01-01/04 | EV-I04 | marker与missing-input / real-SUT-not-wired preflight；canonical SKIPPED/NOT_RUN且零network | Baseline preflight | `env -u DASHSCOPE_API_KEY -u DASHSCOPE_BASE_URL uv run pytest -m qwen_baseline tests/baseline/test_qwen_baseline.py -x`；`DASHSCOPE_API_KEY=not-a-real-key DASHSCOPE_BASE_URL=https://example.invalid uv run pytest -m qwen_baseline tests/baseline/test_qwen_baseline.py -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending/replay · ✅ green/feature · ❌ red · ⚠️ flaky；`feature`不表示已merge或通过latest-integration gate。*

## Wave 0 Requirements

Wave 0 是各 Packet的首个测试提交，不新增共享 bootstrap：

- 01-04H：扩展两个既有 Application contract test files，RED/GREEN与reviewed merge均已完成。
- historical 01-05：7个allowlisted Component test files与RED/GREEN保留在donor history；01-05R新增terminal aggregate RED并已完成reviewed merge。
- historical 01-06：扩展现有 migration test并创建5个Infra integration test files；01-06R受控replay后先扩展三份定向tests取得disclosure/fence RED，首轮GREEN后再单独扩展atomicity test取得terminal RED，继续复用byte-identical `tests/conftest.py`。
- 01-07：创建 6 个 allowlisted Eval / model / baseline test files。
- 不修改 `pyproject.toml`、`uv.lock`、共享 fixtures或canonical owners。

原01-05/06/07三个writer、01-04H与01-05R均已展示各自RED，因此`wave_0_complete=true`。它只记录既有Wave 0 evidence，不提前证明01-06R replacement RED或latest-integration compatibility。

## Packet Full Gates

### 01-04H Application terminal-turn contract

```bash
uv run pytest \
  tests/component/application/test_record_contracts.py \
  tests/component/application/test_ports_contract.py -x
uv run pytest
uv run python -m compileall -q \
  src/mini_agent/application/records.py \
  src/mini_agent/application/ports.py \
  tests/component/application/test_record_contracts.py \
  tests/component/application/test_ports_contract.py
git diff --check
```

01-04H changed-file set已精确等于四文件allowlist，269 focused / 560 full与post-merge 560通过。Ruff不是required gate，因为仓库尚无pinned / canonical Ruff入口。01-05R已完成并形成01-06R exact base；01-06R以独立replacement Plan补充本map，不复用historical 01-06状态。

### 01-05R Runtime replacement

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

01-05R还必须证明：

- `64992cf...<feature-head>` changed-file set精确等于14-file allowlist；
- donor range `c35687d...a27141b`也精确等于同一14-file set，且历史branch/PR未改变；
- 相对donor head仅`agent_run_service.py`与`test_agent_run_service.py`两个blob允许不同，其余12个blob byte-identical；
- terminal consumer source修改前，新的AgentRun test因split-write取得真实RED；GREEN后正常终态只有一个complete aggregate、仅APPLIED返回、APPLIED后无persistence await；
- `records.py`、`ports.py`、01-04H tests与所有forbidden files相对base byte-identical；
- reviewed feature head与latest-integration overlay都重复focused/full/containment。

以上证据已在PR #34 reviewed head `05f0182...`、overlay `26756cc...`与merge `fb607019...`满足：100 focused、660 full、38 migration、independent `PASS / NOT_FOUND`、post-merge Graphify通过。

### 01-06R Infra replacement

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

01-06R还必须证明：

- `fb607019...<feature-head>`与`<overlay-parent>...<overlay-head>` changed-file set都精确等于13-file allowlist；
- donor range `c35687d...054dcaf`为五个线性commits且只触及同一13-file set；
- replay点13/13 donor blob equality；最终只允许`postgres.py`、record-adapter/atomicity/recovery三份tests改变，其余九个blob匹配Plan固定SHA；
- 首个test-only RED真实暴露raw envelope/reference disclosure与recovery-first late ToolCall，首轮GREEN后第二个test-only RED再独立暴露不完整terminal transaction；
-两种ToolCall/recovery顺序使用barrier/event而非sleep，并证明零orphan；
- with/no Task/FAILED terminal projection及每个child/reference fault都证明同事务APPLIED或全回滚；
- reviewed feature head与latest-integration overlay重复focused/full/migration/containment。

### 01-07 Eval（feature PASS；latest replay pending）

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
| Latest-integration compatibility | E2E01-01/04 | 历史三个Sibling从同base开始，但replacement改为exact predecessor串行签发 | 每次merge前生成latest overlay并运行full suite，确认无hidden contract drift |
| Nonclaims / lifecycle discipline | E2E01-01/04 | 需要审查文案和manifest状态 | 确认Case仍`CONTRACT_DEFINED`、Requirements unchecked；Adapter测试不冒充真实Qwen Baseline或production claim |

01-08 的真实 HTTP / PostgreSQL / Trajectory / E2E、Security audit与UAT不属于这些Component/contract Packet的“manual替代”；它们是后续必须自动化或可复现执行的独立 gate。

## Validation Sign-off

- [x] 每个研究 task都有 planned automated command或Wave 0 test file。
- [x] 没有连续三个 task缺失自动化反馈。
- [x] 所有 missing test reference均在exact Packet allowlist内。
- [x] 无watch-mode flag。
- [x] `nyquist_compliant: true`。
- [x] 01-04H 两个结构化TDD task已有RED/GREEN、269 focused / 560 full、reviewed merge与post-merge Graphify evidence；physical transaction仍明确留给未来01-06R。
- [x] 01-05R exact base/new identity/14-file donor、真实RED、reviewed merge与post-merge gate已完成。
- [x] 01-06R exact base/new identity/13-file donor、两个可执行RED→GREEN循环已规划；planning merge前不启动写入。
- [x] 01-05/06/07 每个 task 均有 exact automated command 与 allowlisted Wave 0 test。
- [x] 初始 Plan Checker loop 3/3 `PASS` 已被 PR #26 首个 exact-head review 的 canonical/security findings 明确 supersede，不再作为 approval。
- [x] 超出三轮 cap 后的只读 checker audit 识别出两项 `MAJOR`；对应 approval 声明与第二条零网络命令已修正，不再启动第 5 个 planner loop。
- [x] planning PR #26 final published head `2922308b...` 已取得canonical与security/process两个Codex只读Reviewer的`PASS`，所有planning findings已关闭，并merge为`968b4a9...`；持久化记录见PR #26 [canonical evidence](https://github.com/weijie567/mini-agent/pull/26#issuecomment-5086174316)与[security/process evidence](https://github.com/weijie567/mini-agent/pull/26#issuecomment-5086174609)，不是GitHub Reviews API formal approvals。
- [x] **HISTORICAL PR #26 SIGN-OFF / SUPERSEDED FOR CURRENT INTEGRATION:** 原01-05/06/07 Wave 0 RED已进入published feature history；首轮focused/full为Runtime 83/549、Infra 68/496、Eval 111/577（1 deselected）。它们只证明当时feature形成，不批准当前合并。
- [x] Historical Runtime/Infra heads后续测试增长至95/561与23/506并被exact-head review判定BLOCK；它们保持历史evidence。
- [x] 01-04H planning/owner/review/merge/full/Graphify Gate通过，`wave_0_complete=true`。
- [x] Eval `b8ecbb0...`已通过150 grader+harness / 657 full（1 deselected）、two zero-network preflights与independent `PASS / NOT_FOUND`；仍不代表latest replay/merge。
- [x] 01-05R已在exact predecessor merge后完成planning、实现、review与merge。
- [ ] 01-06R在exact predecessor merge后完成planning、实现、review与merge。
- [ ] Runtime → Infra → Eval latest-integration compatibility、serial merge与post-merge gates全部PASS。

**Approval:** `01-05R_COMPLETE / 01-06R_PLANNING_REVIEW_PENDING`。PR #26只批准historical 01-05/06/07 Packet从`c35687d...`创建，不能据旧approval合并PR #30。当前01-06R必须先通过本planning PR、implementation exact-head review与merge；随后依次通过Eval latest-integration replay、01-08与post-execution quality gate。本文件不批准Case、Baseline、release或lifecycle结论。
