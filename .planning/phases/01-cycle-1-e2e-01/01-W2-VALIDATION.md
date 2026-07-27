---
phase: 01-cycle-1-e2e-01
slug: cycle-1-e2e-01-w2
scope: 01-04H-01-07G-complete-with-01-05R-01-06R
status: execution_evidence_complete_through_01_07C_01_07G
nyquist_compliant: true
wave_0_complete: true
created: "2026-07-27"
---

# Phase 1 W2｜Validation Strategy

> **DERIVED / NON_NORMATIVE**
> 本文件只定义已完成01-04H/01-05R/01-06R/01-07/01-07A/01-07B，以及01-07C/01-07G owner-document execution feedback sampling。Case、指标、Critical failure 与生命周期仍由 canonical Eval owner 持有；这里的绿色测试和owner ruling不能替代01-08真实纵向证据或post-execution quality gate。

## Test Infrastructure

| Property | Value |
|---|---|
| Framework | pytest / pytest-asyncio；PostgreSQL integration tests |
| Config | `pyproject.toml`、`tests/conftest.py`、`compose.yaml`、`alembic.ini` |
| Quick command | 每个 Task Packet 的 exact focused pytest command |
| Full suite | `uv run pytest` |
| Infra preflight | `uv sync --all-groups`；检查persistent `db`与disposable `db-test`可用；`uv run alembic upgrade head`验证development DB，migration regression test在`db-test`独立fresh schema执行 |
| Current reviewed evidence | C/G common barrier `327b39d...`; `1493 full, 1 deselected, 12 warnings`; C/G exact-head / overlay双review；Graphify全量安全重建`3098 nodes / 16904 edges / 68 hyperedges / 135 communities`并记录health warning |
| Max feedback latency | focused task tests应在每个原子 commit前完成；full suite在每个 Packet handoff前完成 |

仓库当前没有 canonical lint、type-check、build 或 app-start命令，也没有 pinned Ruff dependency；不得编造。允许的附加机械检查为 `compileall`、`git diff --check`、artifact SHA 与 changed-file containment。

## Sampling Rate

- 每个 TDD task：先运行新测试取得预期 RED，再完成 GREEN。
- 每个原子 commit 前：运行该 task 的 exact focused tests。
- 每个 Packet handoff 前：运行 Packet 全部 focused tests、`uv run pytest` 和机械 containment。
- 每个 feature PR 最新 head：独立 reviewer 读取 exact diff和测试证据；finding修复后重新运行受影响 focused + full suite。
- 每次串行合并前：在 latest integration overlay / merge candidate上重复 full suite。
- 01-08 前：Runtime、Infra、Eval、01-07A、01-07B及后续owner-ruling / implementation Packet都必须有 reviewed exact-head和latest-integration compatibility证据；01-08A credentialed runner在01-08之后独立执行。

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure behavior | Test type | Automated command | File exists | Status |
|---|---|---:|---|---|---|---|---|---|
| 01-04H-01 | 01-04H | 9 | E2E01-01/04 | TERM-R01/TERM-T01 | RED覆盖partial terminal turn、非法reason/outcome/Task/status组合与Trace污染 | Component contract | `uv run pytest tests/component/application/test_record_contracts.py tests/component/application/test_ports_contract.py -x` | ✅ existing | ✅ green |
| 01-04H-02 | 01-04H | 9 | E2E01-01/04 | TERM-D01/TERM-E01 | GREEN冻结complete aggregate、APPLIED全写与non-APPLIED零写Port语义 | Component contract | `uv run pytest tests/component/application/test_record_contracts.py tests/component/application/test_ports_contract.py -x`；`uv run pytest` | ✅ existing | ✅ green |
| 01-05R-01 | 01-05R | 10 | E2E01-01/04 | RT-S01/RT-T01/RT-T02/RT-E01 | controlled donor replay；trusted identity、candidate validation、binding、state reducer与Gateway仍闭合 | Component replay | `uv run pytest tests/component/core/test_request_processing.py tests/component/core/test_control_gateway.py -x` | ✅ donor | ✅ green |
| 01-05R-02 | 01-05R | 10 | E2E01-01/04 | RT-R01/RT-D01/RT-I01/RT-T03 | durable fence、no retry、fact-free plan与safe renderer保持donor blob/behavior | Component replay | `uv run pytest tests/component/core/test_presentation_policy.py tests/component/application/test_read_tool_executor.py tests/component/application/test_deterministic_renderer.py -x` | ✅ donor | ✅ green |
| 01-05R-03 | 01-05R | 10 | E2E01-01/04 | RT-R04/RT-D02/RT-I03 | RED禁止split terminal writes；GREEN只用一个complete aggregate且APPLIED后无await | Component replacement | `uv run pytest tests/component/application/test_agent_run_service.py -x` | ✅ extend | ✅ green |
| 01-05R-04 | 01-05R | 10 | E2E01-01/04 | RT-R03/RT-T04 | restart不resume/replay；exact recovery events保持donor blob/behavior | Component replay | `uv run pytest tests/component/application/test_restart_recovery_service.py -x` | ✅ donor | ✅ green |
| 01-06R-01 | 01-06R | 11 | E2E01-01/04 | IF-T01/IF-T04/IF-I04 | controlled donor replay后以首个test-only RED只暴露raw disclosure与late ToolCall | Integration replacement | `uv run pytest tests/integration/test_postgres_record_adapters.py tests/integration/test_postgres_atomicity.py tests/integration/test_postgres_recovery.py -x` | ✅ donor/extend | ✅ green |
| 01-06R-02 | 01-06R | 11 | E2E01-01/04 | IF-T01/IF-T04/IF-I04/IF-D02 | bounded envelope/reference error；parent Run RUNNING fence；两种无sleep顺序无orphan | Integration replacement | `uv run pytest tests/integration/test_postgres_record_adapters.py tests/integration/test_postgres_atomicity.py tests/integration/test_postgres_recovery.py -x` | ✅ donor/extend | ✅ green |
| 01-06R-03 | 01-06R | 11 | E2E01-01/04 | IF-R03/IF-R04/IF-D02 | Task 2 GREEN后以第二个RED暴露partial terminal commit，再使with/no Task/FAILED complete transaction与逐child fault全回滚 | Integration replacement | `uv run pytest tests/integration/test_postgres_atomicity.py -x` | ✅ donor/extend | ✅ green |
| 01-07-01 | 01-07 | 12 | E2E01-01/04 | EV-T01/EV-E01 | closed manifest/path/hash/ref loader | Component | `uv run pytest tests/component/evaluation/test_e2e01_versioned_artifact_loader.py -x` | ✅ created | ✅ green |
| 01-07-02 | 01-07 | 12 | E2E01-01/04 | EV-S01/EV-I01 | strict script cursor；无network；raw error丢弃 | Component | `uv run pytest tests/component/evaluation/test_e2e01_scripted_model_provider.py -x` | ✅ created | ✅ green |
| 01-07-03 | 01-07 | 12 | E2E01-01/04 | EV-S02/EV-I03 | Qwen request allowlist、exact one target call、mock transport与raw error丢弃 | Component | `uv run pytest tests/component/model/test_qwen_responses_adapter.py -x` | ✅ created | ✅ green |
| 01-07-04 | 01-07 | 12 | E2E01-01/04 | EV-T02/EV-I02 | 13 graders均有pass与tamper-fail；CF强制FAIL | Component | `uv run pytest tests/component/evaluation/test_e2e01_graders.py -x` | ✅ created | ✅ green |
| 01-07-05 | 01-07 | 12 | E2E01-01/04 | EV-R01/EV-R02 | Result/Failure矩阵、run/case/lane/attempt append-only、cross-lane distinctness、paired completeness | Integration | `uv run pytest tests/integration/evaluation/test_e2e01_offline_harness.py -x` | ✅ created | ✅ green |
| 01-07-06 | 01-07 | 12 | E2E01-01/04 | EV-I04 | marker与missing-input / real-SUT-not-wired preflight；canonical SKIPPED/NOT_RUN且零network | Baseline preflight | `env -u DASHSCOPE_API_KEY -u DASHSCOPE_BASE_URL uv run pytest -m qwen_baseline tests/baseline/test_qwen_baseline.py -x`；`DASHSCOPE_API_KEY=not-a-real-key DASHSCOPE_BASE_URL=https://example.invalid uv run pytest -m qwen_baseline tests/baseline/test_qwen_baseline.py -x` | ✅ created | ✅ green |
| 01-07A-01 | 01-07A | 13 | E2E01-01/04 | RTA-T01/RTA-T02/RTA-R01 | test-only RED复现purpose、fixed-result ResponseRendered与hook active-run identity缺口 | Component alignment | `uv run pytest tests/component/application/test_agent_run_service.py -x` | ✅ extend | ✅ green |
| 01-07A-02 | 01-07A | 13 | E2E01-01/04 | RTA-I01/RTA-D01/RTA-E01 | real Runtime Trace关闭缺口，保持terminal aggregate与FAILED fail-closed | Component alignment | `uv run pytest tests/component/application/test_agent_run_service.py -x`；`uv run pytest` | ✅ extend | ✅ green |
| 01-07B-01 | 01-07B | 14 | E2E01-01/04 | EVB-E01/EVB-T01/EVB-I01/EVB-S01 | 两条独立test-only RED证明SUT Case/嵌套message、Provider nested step与output-side `case_id`可见semantic identity/answers，zero-argument non-semantic nonce correlation缺失，以及actual mismatch被oracle覆盖的风险 | Eval contract | `uv run pytest tests/component/evaluation/test_e2e01_scripted_model_provider.py tests/integration/evaluation/test_e2e01_offline_harness.py -k 'execution_only or execution_ref or result_correlation or nonce or oracle or actual_mismatch'`；`uv run pytest tests/component/evaluation/test_e2e01_graders.py -k 'precedence or reordered'` | ✅ extend | ✅ green |
| 01-07B-02 | 01-07B | 14 | E2E01-01/04 | EVB-R01/EVB-S01 | closed execution-message/behavior-step projection与occurrence-aware variant-scoped safety-causal partial order；每个正常/故障variant的适用edge violation必须FAIL，合法额外事件继续PASS | Eval contract | `uv run pytest tests/component/evaluation/test_e2e01_graders.py tests/component/evaluation/test_e2e01_scripted_model_provider.py tests/integration/evaluation/test_e2e01_offline_harness.py`；`uv run pytest` | ✅ extend | ✅ green |
| 01-07C-01 | 01-07C | 15 | E2E01-01/04 | RUS-S01/RUS-T01/RUS-R01/RUS-I01/RUS-E01 | durable aggregate、独立版本轴、candidate/validation/accepted closure与可信时间的owner裁决 | Owner-document contract | exact one-file containment；focused field/axis scan；independent exact-head review | ✅ owner exists | ✅ green |
| 01-07C-02 | 01-07C | 15 | E2E01-01/04 | RUS-D01/RUS-I01 | exact-version、compatibility、migration与rollback fail-closed裁决；跨文件只读影响扫描 | Owner-document contract | `git diff --check`；focused compatibility scan；`uv run pytest`；latest-integration overlay | ✅ owner exists | ✅ green |
| 01-07G-01 | 01-07G | 15 | E2E01-01/04 | OSV-S01/OSV-T01/OSV-R01/OSV-I01/OSV-E01 | trusted owner-scoped authority、strict safe projection、canonical content hash、fixed vector及runtime-private exposure裁决 | Owner-document contract | exact one-file containment；algorithm/vector scan；independent exact-head review | ✅ owner exists | ✅ green |
| 01-07G-02 | 01-07G | 15 | E2E01-01/04 | OSV-D01/OSV-I01 | final FOUND/non-found/system-failure closed matrix、H additive→J fail-closed→K producer→M Core contract green migration、exact-copy、compatibility/ABA及rollback裁决 | Owner-document contract | `git diff --check`；outcome/staged-propagation scan；`uv run pytest`；latest-integration overlay | ✅ owner exists | ✅ green |

*Status: ⬜ pending/replay · ✅ green/feature · ❌ red · ⚠️ flaky；`feature`不表示已merge或通过latest-integration gate。*

## Wave 0 Requirements

Wave 0 是各 Packet的首个测试提交，不新增共享 bootstrap：

- 01-04H：扩展两个既有 Application contract test files，RED/GREEN与reviewed merge均已完成。
- historical 01-05：7个allowlisted Component test files与RED/GREEN保留在donor history；01-05R新增terminal aggregate RED并已完成reviewed merge。
- historical 01-06：扩展现有 migration test并创建5个Infra integration test files；01-06R受控replay后先扩展三份定向tests取得disclosure/fence RED，首轮GREEN后再单独扩展atomicity test取得terminal RED，继续复用byte-identical `tests/conftest.py`。
- 01-07：创建 6 个 allowlisted Eval / model / baseline test files并已通过reviewed merge。
- 01-07A：只扩展既有AgentRun Component test取得一个真实RED，再修改对应Runtime source；已完成reviewed merge。
- 01-07B：扩展既有Grader、ScriptedProvider与Harness三份tests，以两条独立命令取得Case/Script oracle和Trace precedence RED，再修改对应三份Eval source；不创建real SUT或PG reader。
- 01-07C：contract-only owner文档Packet，不创建test/bootstrap且不伪造TDD RED；两个Task使用exact one-file containment、focused owner / compatibility scan、`git diff --check`、full suite与latest overlay，已通过reviewed merge和post-merge gate。
- 01-07G：contract-only owner文档Packet，不创建test/bootstrap且不伪造TDD RED；两个Task使用exact one-file containment、algorithm/vector / outcome scan、`git diff --check`、full suite与latest overlay，已通过reviewed merge和post-merge gate。
- 不修改 `pyproject.toml`、`uv.lock`、共享 fixtures或canonical owners。

原01-05/06/07三个writer、01-04H、01-05R、01-06R与01-07A均已展示各自RED；01-07B又以test-only commit `8978655a...`形成独立RED，并由GREEN / review-fix、双review与merge证据闭环，因此当前scope的`wave_0_complete=true`。该状态只表示测试先行证据完整，不推进Case lifecycle。

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
docker compose --profile test up --wait -d db-test
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
docker compose up --wait -d db
docker compose --profile test up --wait -d db-test
uv run alembic upgrade head
uv run pytest tests/integration/test_database_migrations.py -x
uv run pytest \
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

### 01-07 Eval（reviewed merge complete）

```bash
uv sync --all-groups
docker compose --profile test up --wait -d db-test
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

01-07 只运行显式清除凭据的 preflight，证明 `NOT_RUN / SKIPPED` 与零network。真实 Qwen lane必须等01-08接入real `EvalCaseSut`且01-08A独立Eval-owner runner reviewed merge后，才在W4 exact integrated head具备显式配置时单独运行；默认 full gate因 marker排除它：

```bash
env -u DASHSCOPE_API_KEY -u DASHSCOPE_BASE_URL \
  uv run pytest -m qwen_baseline tests/baseline/test_qwen_baseline.py -x

DASHSCOPE_API_KEY=not-a-real-key \
DASHSCOPE_BASE_URL=https://example.invalid \
  uv run pytest -m qwen_baseline tests/baseline/test_qwen_baseline.py -x

# W4 only, after 01-08A credentialed runner:
uv run pytest -m qwen_baseline tests/baseline/test_qwen_baseline.py -x
```

缺失 `DASHSCOPE_API_KEY` / `DASHSCOPE_BASE_URL`、尚无01-08 real SUT wiring或尚无01-08A runner时必须得到 canonical `SKIPPED / NOT_RUN`，不得生成 PASS或访问网络；这不阻塞离线 release gate。

上述命令已在feature与latest overlay重复通过；post-merge为191 focused、40 migration与936 full（1 deselected）。当前仓库没有credentialed Qwen runner，因此缺凭据W4只能如实保持`NOT_RUN / SKIPPED`；真实Qwen执行需要后续独立Eval-owner Packet，不能由01-08复制Harness逻辑。

### 01-07A Runtime Trace alignment

```bash
uv sync --all-groups
docker compose up --wait -d db
docker compose --profile test up --wait -d db-test
uv run alembic upgrade head
uv run pytest tests/component/application/test_agent_run_service.py -x
uv run pytest \
  tests/component/core/test_request_processing.py \
  tests/component/core/test_control_gateway.py \
  tests/component/core/test_presentation_policy.py \
  tests/component/application/test_agent_run_service.py \
  tests/component/application/test_read_tool_executor.py \
  tests/component/application/test_deterministic_renderer.py \
  tests/component/application/test_restart_recovery_service.py -x
uv run pytest tests/integration/test_database_migrations.py -x
uv run pytest
uv run python -m compileall -q src tests
git diff --check
```

01-07A已保留test-only RED并证明Context Manifest purpose、每个normal result exactly-one ResponseRendered、pre-render FAILED zero ResponseRendered、post-render terminal failure保留一个真实reached-stage event但无result/ASSISTANT/RunStopped，以及explicit active-run hook identity；changed-file set精确为Runtime source/test pair。PR #37/#38 reviewed merge后为27 directed、100 Runtime focused、40 migration与936 full（1 deselected）。它不产生Eval Result，也不批准01-08。

### 01-07B Eval evidence boundary

```bash
uv sync --all-groups
docker compose up --wait -d db
docker compose --profile test up --wait -d db-test
uv run alembic upgrade head
uv run pytest \
  tests/component/evaluation/test_e2e01_graders.py \
  tests/component/evaluation/test_e2e01_scripted_model_provider.py \
  tests/integration/evaluation/test_e2e01_offline_harness.py -x
uv run pytest \
  tests/component/evaluation/test_e2e01_versioned_artifact_loader.py \
  tests/component/evaluation/test_e2e01_artifact_consistency.py \
  tests/component/evaluation/test_e2e01_scripted_model_provider.py \
  tests/component/model/test_qwen_responses_adapter.py \
  tests/component/evaluation/test_e2e01_graders.py \
  tests/integration/evaluation/test_e2e01_offline_harness.py -x
uv run pytest tests/integration/test_database_migrations.py -x
uv run pytest
uv run python -m compileall -q src tests
git diff --check
```

01-07B必须先用两条独立test-only RED证明完整`EvalCaseArtifact`、嵌套message extra key与semantic `model_script_ref`/`ModelScriptArtifact.expected_control_result`/nested step answer-like key可达，SUT output被迫携带semantic `case_id`且没有one-time non-semantic nonce correlation，以及reordered Trace false PASS；再以exact six-file GREEN引入只含opaque `execution_ref`、closed role/content message、trusted Session-fixture ref或closed behavior-specific step/runtime fault/opaque identity的execution-only SUT/Provider projection。`execution_ref`与Provider execution identity必须由不接收Case/script/expectation参数的zero-argument injected nonce factory分别生成，production default为`uuid4`；collision/reuse以及`uuid5`/hash等semantic deterministic derivation必须FAIL。SUT result只回传one-time `execution_ref`与unbound evidence/observable，Harness拒绝unknown/mismatch/replay并在成功关联后独自绑定authenticated `case_id`。Trace使用每个现有Case/script variant的closed safety-causal DAG：正常、not-found、Gateway拒绝、Request Understanding/provider/input fault与presentation fault各自canonical PASS，每条适用edge swap与缺失required endpoint必须FAIL；with-Task路径还必须验证`ResponseRendered → last TaskStateChanged → RunStopped`（含state-advanced fault），task-less路径验证`ResponseRendered → RunStopped`，合法额外事件继续PASS。Actual/expected mismatch必须形成正常grader `FAIL`，不能被SUT按answers补造为PASS。它不创建real SUT、PG reader、HTTP E2E或Eval lifecycle更新。

01-07B也不改变外部`ModelProvider`失败合同。当前invalid Request Understanding schema / trusted-field override在Scripted Provider会让raw `ValidationError`逃逸，Qwen Adapter又把同类Pydantic失败折叠为`ProviderProtocolError`，都不能形成Thin Slice §10.3规定的`COMPLETED / INPUT_INVALID`。该已确认阻断按owner边界进入未签发的既有Packet：01-07I的records/ports contract tests先冻结fresh parameterless、raw-diagnostic-free candidate-invalid signal，并保持framing/transport/zero-or-multiple/wrong-call及Presentation validation为`ProviderProtocolError`；01-07J的AgentRunService Component test证明只捕获该signal、无Task / RequestUnit / Gate / Tool / raw diagnostics并安全完成；01-07L沿用01-07既有Eval ownership修改Scripted与Qwen consumers及tests，并以必要的real-Runtime Eval test证明两个invalid-RU scripts得到`INPUT_INVALID`、协议与Presentation分支不漂移。01-07K仍只拥有strict reader/order physical adapter。source-version另采用H additive表示、J在Observation前对缺/坏version fail closed、K producer生成、M最终收紧Core FOUND validator的四阶段green migration；每个Packet都必须独立通过full suite。I→J→{K,L}→M的reviewed common barrier形成前不得签发01-08；新增M后目标总数为29。

### 01-07C / 01-07G Owner rulings

```bash
git diff --check
uv run pytest
graphify update .
```

两个Packet的执行与验证边界：

- 两者共同固定execution base `3f0753f7bef87fc02f314e28fe8b07860a819701`，分别只写`docs/architecture/intent-design-reference.md`与`docs/implementation/e2e01-thin-slice-implementation-spec.md`；
- 01-07G feature head `0fb892f...`、tree `aad28db...`、PR #50先经exact-head双review与latest-integration overlay后merge `bfc63c9...`；
- 01-07C首个Draft PR #51的`0/1/1` finding不被覆盖或改写；r1 Plan PR #52固定新execution identity但保持同一base/owner/scope/denominator，owner PR #53 remote head `b39a037...`、tree `c35ba07...`关闭finding并经latest overlay merge `327b39d...`；
- status-evidence independent review发现Project Direction仍保留C未开始快照；独立exact one-file owner PR #54通过`0/0/0` review、1493-test full与local/remote tree/blob identity后merge `ffcc562...`，只对齐implementation evidence snapshot，D/H execution base继续固定为`B_CG`；
- feature、独立review replay、latest overlay与最终post-merge均运行default full suite；共同barrier结果为`1493 passed, 1 deselected, 12 warnings`；
- Graphify增量候选因node shrink触发guard后没有force增量覆盖，而是从191-file corpus执行全量安全重建；最终`3098 nodes / 16904 edges / 68 hyperedges / 135 communities`绑定`327b39d...`；
- Graphify diagnostic必须保留`699` dangling endpoint、`687` directed与`713` undirected collapse candidate、`0` missing endpoint、`0` self-loop；这些warning不阻断图可用性，但禁止把health描述为全绿；
- [01-07C Summary](01-07C-SUMMARY.md)与[01-07G Summary](01-07G-SUMMARY.md)只索引证据；Case lifecycle仍为`0/8`。

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
- [x] 01-06R exact base/new identity/13-file donor、五个RED→GREEN repair pairs、reviewed merge与post-merge gate已完成。
- [x] 01-05/06/07 每个 task 均有 exact automated command 与 allowlisted Wave 0 test。
- [x] 初始 Plan Checker loop 3/3 `PASS` 已被 PR #26 首个 exact-head review 的 canonical/security findings 明确 supersede，不再作为 approval。
- [x] 超出三轮 cap 后的只读 checker audit 识别出两项 `MAJOR`；对应 approval 声明与第二条零网络命令已修正，不再启动第 5 个 planner loop。
- [x] planning PR #26 final published head `2922308b...` 已取得canonical与security/process两个Codex只读Reviewer的`PASS`，所有planning findings已关闭，并merge为`968b4a9...`；持久化记录见PR #26 [canonical evidence](https://github.com/weijie567/mini-agent/pull/26#issuecomment-5086174316)与[security/process evidence](https://github.com/weijie567/mini-agent/pull/26#issuecomment-5086174609)，不是GitHub Reviews API formal approvals。
- [x] **HISTORICAL PR #26 SIGN-OFF / SUPERSEDED FOR CURRENT INTEGRATION:** 原01-05/06/07 Wave 0 RED已进入published feature history；首轮focused/full为Runtime 83/549、Infra 68/496、Eval 111/577（1 deselected）。它们只证明当时feature形成，不批准当前合并。
- [x] Historical Runtime/Infra heads后续测试增长至95/561与23/506并被exact-head review判定BLOCK；它们保持历史evidence。
- [x] 01-04H planning/owner/review/merge/full/Graphify Gate通过；01-04H当时的Wave 0已完成。
- [x] Eval `b8ecbb0...`及latest overlay `ee46f38...`已通过191 focused / 936 full（1 deselected）、two zero-network preflights、independent `PASS / NOT_FOUND`并merge为`eee1c0e...`。
- [x] 01-05R已在exact predecessor merge后完成planning、实现、review与merge。
- [x] 01-06R在exact predecessor merge后完成planning、实现、review与merge。
- [x] Runtime → Infra → Eval latest-integration compatibility、serial merge与post-merge gates全部PASS。
- [x] 01-07A exact base/new identity/two-file ownership、真实RED→GREEN、review、merge与post-merge gate已完成。
- [x] 01-07B exact base/new identity/six-file ownership与真实RED→GREEN已完成；planning/status PR #42–#43、feature PR #44、双review、latest-integration overlay与post-merge gate均通过。
- [x] 01-07B完成planning、实现、review、merge与post-merge gate；Summary索引精确证据，Case lifecycle仍为0/8。
- [x] 01-07G exact base、one-file ownership、fixed vectors、双review、latest overlay与PR #50 merge已完成。
- [x] 01-07C blocked lineage保持不可变；r1 Plan / one-file owner、双review、latest overlay与PR #53 merge已关闭finding。
- [x] C/G共同barrier`327b39d...`通过1493-test post-merge full与Graphify全量安全重建；dangling / collapsed warning已显式保留，Case lifecycle仍为0/8。
- [x] Project Direction过期C状态已由独立one-file owner PR #54关闭并merge `ffcc562...`；没有把派生状态夹入owner PR，也没有改变`B_CG`。

**Approval:** `W2_THROUGH_01-07C_01-07G_SERIAL_MERGE_COMPLETE / OWNER_STATUS_ALIGNED_FFCC562 / B_CG_327B39D / 01-07D_01-07H_PLANNING_NEXT`。01-07C与01-07G已从共同execution base完成独立owner写入、exact-head双review、latest-integration overlay与串行merge；共同barrier为`327b39d...` / tree `49ad0f3...`。Project Direction状态对齐PR #54随后merge为`ffcc562...`，但只改变证据快照。下一步必须通过两个独立single-target planning PR分别固定01-07D与01-07H的同一`B_CG` execution base，不能把mapping与DTO合并签发；两个planning PR reviewed merge后才创建feature Worktree。之后按既定顺序推进codec/Core、Evidence Port/Provider failure signal、Runtime `INPUT_INVALID`和version fail-closed mapping、Infra reader/version producer、Eval mapper/Scripted-Qwen consumers，以及K/L共同barrier后的01-07M Core contract closure。01-07M reviewed merge后才签发01-08，01-08 reviewed merge后再签发01-08A credentialed runner，之后才进入post-execution quality gate。本文件不批准Case、credentialed Baseline、release或lifecycle结论；当前Task Packet完成为16/29，canonical lifecycle仍为0/8。
