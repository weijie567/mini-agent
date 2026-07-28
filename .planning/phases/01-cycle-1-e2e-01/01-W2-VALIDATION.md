---
phase: 01-cycle-1-e2e-01
slug: cycle-1-e2e-01-w2
scope: 01-04H-through-01-07O-complete
status: evidence_complete_through_01_07N_01_07O_status_alignment_in_progress
nyquist_compliant: true
wave_0_complete: true
created: "2026-07-27"
---

# Phase 1 W2｜Validation Strategy

> **DERIVED / NON_NORMATIVE**
> 本文件只定义已完成01-04H至01-07O的实现/合同反馈与可复现验证索引。01-07D/H的Wave 16反馈、GREEN、reviewed merge，以及01-07N/O的Wave 17/18 owner-contract验证均已完成，因此当前scope的`wave_0_complete=true`；该字段不推进Case生命周期。Case、指标、Critical failure与生命周期仍由canonical Eval owner持有；Plan review、绿色测试和owner ruling不能替代01-07F/E、真实纵向证据或post-execution quality gate。

## Test Infrastructure

| Property | Value |
|---|---|
| Framework | pytest / pytest-asyncio；PostgreSQL integration tests |
| Config | `pyproject.toml`、`tests/conftest.py`、`compose.yaml`、`alembic.ini` |
| Quick command | 每个 Task Packet 的 exact focused pytest command |
| Full suite | `uv run pytest` |
| Infra preflight | `uv sync --all-groups`；检查persistent `db`与disposable `db-test`可用；`uv run alembic upgrade head`验证development DB，migration regression test在`db-test`独立fresh schema执行 |
| Current reviewed evidence | D/H共同barrier `B_DH = 4a7e802...`通过`1507 passed, 1 deselected, 12 warnings`；N owner merge `a4b1edb...`与O owner merge `7332091...`的feature/overlay均获independent `0/0/0/0`，PR #66 one-file状态校正也通过1507 full与independent review |
| Graphify status | 用户已明确暂时停用；不运行、不引用，也不作为status、F/E、共同barrier或发布门禁 |
| Max feedback latency | focused task tests应在每个原子 commit前完成；full suite在每个 Packet handoff前完成 |

仓库当前没有 canonical lint、type-check、build 或 app-start命令，也没有 pinned Ruff dependency；不得编造。允许的附加机械检查为 `compileall`、`git diff --check`、artifact SHA 与 changed-file containment。

## Sampling Rate

- 每个 TDD task：先运行新测试取得预期 RED，再完成 GREEN。
- 每个原子 commit 前：运行该 task 的 exact focused tests。
- 每个 Packet handoff 前：运行 Packet 全部 focused tests、`uv run pytest` 和机械 containment。
- 每个 feature PR 最新 head：独立 reviewer 读取 exact diff和测试证据；finding修复后重新运行受影响 focused + full suite。
- 每次串行合并前：在 latest integration overlay / merge candidate上重复 full suite。
- 01-07D / 01-07H已从`B_CG`以互斥allowlist执行并串行形成`B_DH`；01-07N/O又依次完成cutover remediation与唯一execution map。
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
| 01-07D-01 | 01-07D | 16 | E2E01-01/04 | RUM-S01/RUM-T01/RUM-R01/RUM-I01/RUM-E01 | Thin Slice exact schema axes、parent/local-child identity、actual candidate closure与无v1 fallback mapping | Scoped owner contract | exact field/relation scan、one-file containment、`git diff --check`、full suite | ✅ owner exists | ✅ green |
| 01-07D-02 | 01-07D | 16 | E2E01-01/04 | RUM-D01/RUM-I01 | marker-bounded 17/70/8/11 rows、49 reference rules、synthetic compatibility mutations与B_CG negative reason fail closed | Scoped owner contract | manifest equality、10 mutations、registry/catalog counts与latest-integration replay | ✅ owner exists | ✅ green |
| 01-07H-01 | 01-07H | 16 | E2E01-01/04 | OSVA-T01/OSVA-R01/OSVA-I01/OSVA-D01 | RED冻结strict optional `source_version`、legacy `FOUND + None`、non-FOUND prohibition与六个synthetic stub | Component contract | owned focused suite；RED `33 failed, 47 passed`；GREEN `80 passed` | ✅ existing | ✅ green |
| 01-07H-02 | 01-07H | 16 | E2E01-01/04 | OSVA-S01/OSVA-T01/OSVA-E01 | GREEN只扩展Core DTO representation，不暴露ToolSpec、不提前实现J/K/M并保持PostgreSQL legacy producer兼容 | Component + Integration | ToolSpec absence、PostgreSQL `3 passed`、full `1507 passed`与latest replay | ✅ existing | ✅ green |
| 01-07N-01 | 01-07N | 17 | E2E01-01/04 | RUV2-CUTOVER | `p0-ru-v2-cutover-r1`冻结nested DTO、closed rejection、provenance replay、v1/v2 staged cutover与nonclaims | Scoped owner contract | exact manifest byte equality、10 mutation gates、registry/catalog counts、future-symbol leakage scan、full suite | ✅ owner exists | ✅ green |
| 01-07O-01 | 01-07O | 18 | E2E01-01/04 | RUV2-EXECUTION-MAP | 唯一机械execution map冻结status chain、ownership、barriers、serial order、39 denominator与inactive R | Execution-owner contract | JSON byte equality、18 mutation gates、15 packets、39 target、six stale-consumer mappings、full suite | ✅ owner exists | ✅ green |

*Status: ⬜ pending/replay · ✅ green/feature · ❌ red · ⚠️ flaky；`feature`不表示已merge或通过latest-integration gate。*

## Wave 0 Requirements

Wave 0 是各 Packet的首个测试或合同反馈提交，不新增共享 bootstrap。01-04H至01-07O的当前scope均已有reviewed绿色证据，因此`wave_0_complete=true`：

- 01-04H：扩展两个既有 Application contract test files，RED/GREEN与reviewed merge均已完成。
- historical 01-05：7个allowlisted Component test files与RED/GREEN保留在donor history；01-05R新增terminal aggregate RED并已完成reviewed merge。
- historical 01-06：扩展现有 migration test并创建5个Infra integration test files；01-06R受控replay后先扩展三份定向tests取得disclosure/fence RED，首轮GREEN后再单独扩展atomicity test取得terminal RED，继续复用byte-identical `tests/conftest.py`。
- 01-07：创建 6 个 allowlisted Eval / model / baseline test files并已通过reviewed merge。
- 01-07A：只扩展既有AgentRun Component test取得一个真实RED，再修改对应Runtime source；已完成reviewed merge。
- 01-07B：扩展既有Grader、ScriptedProvider与Harness三份tests，以两条独立命令取得Case/Script oracle和Trace precedence RED，再修改对应三份Eval source；不创建real SUT或PG reader。
- 01-07C：contract-only owner文档Packet，不创建test/bootstrap且不伪造TDD RED；两个Task使用exact one-file containment、focused owner / compatibility scan、`git diff --check`、full suite与latest overlay，已通过reviewed merge和post-merge gate。
- 01-07G：contract-only owner文档Packet，不创建test/bootstrap且不伪造TDD RED；两个Task使用exact one-file containment、algorithm/vector / outcome scan、`git diff --check`、full suite与latest overlay，已通过reviewed merge和post-merge gate。
- 01-07D：Thin Slice单文件合同反馈、GREEN、feature/overlay independent review与PR #59 merge均已完成。
- 01-07H：三份owned tests的真实RED、Core/Order GREEN、focused/PostgreSQL/full、feature/overlay independent review与PR #60 merge均已完成。
- 01-07N：Thin Slice单文件cutover remediation通过manifest equality、mutation、registry/catalog、future-symbol leakage与feature/overlay full/review，PR #63已merge。
- 01-07O：execution owner单文件map通过JSON equality、mutation、packet/denominator/stale-consumer检查与feature/overlay full/review，PR #65已merge；PR #66又完成one-file计数校正。
- 不修改 `pyproject.toml`、`uv.lock`、共享 fixtures或canonical owners。

原01-05/06/07三个writer、01-04H、01-05R、01-06R与01-07A均已展示各自RED；01-07B又以test-only commit `8978655a...`形成独立RED，并由GREEN / review-fix、双review与merge证据闭环。D/H/N/O也已完成各自首个合同或测试反馈、GREEN、review与merge，所以当前scope的`wave_0_complete=true`。该字段不推进Case lifecycle，也不表示F/E或真实纵向链已实现。

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

01-07B也不改变外部`ModelProvider`失败合同；当时确认的invalid Request Understanding schema / trusted-field override、raw `ValidationError`与`ProviderProtocolError`分类，以及source-version producer / closure缺口都属于后续owner，而不是01-07B的完成内容。01-07N/O已经显式supersede本段曾使用的旧Packet顺序与旧分母；当前writer、allowlist、failure-taxonomy ownership、source-version阶段、active switch、v1 contract closure、barrier和目标`39`只由[多Agent实施计划](../../../docs/implementation/e2e01-thin-slice-multi-agent-plan.md)中的marker-bounded `P0-RU-V2-EXECUTION-MAP`拥有。本Validation不再维护第二套顺序，也不能从历史01-07B nonclaim推断J早于K/L/M或直接签发01-08。

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

### 01-07D / 01-07H / 01-07N / 01-07O completion and status barrier

- D/H分别通过Plan PR #56/#57与feature PR #59/#60从同一`B_CG`执行；allowlist交集为0，feature与latest overlay均获independent `0/0/0/0`，串行merge形成`B_DH = 4a7e802e8aebc54e0582a1e4d99f140b56e7b131` / tree `a5a60292ccdf116aba4dacaaea366576e183c532`。
- N Plan / owner PR #62/#63从exact `B_DH`关闭旧E/F同base授权，reviewed merge为`a4b1edb4c50a2e3e826571194bac58f7b31eab6d` / tree `469e26460c1041d9ca5042d39ae9a57ded7d5442`；它只冻结`p0-ru-v2-cutover-r1`，不实现Core、codec、migration或routing。
- O Plan / owner PR #64/#65从exact N merge执行；Plan merge为`274178bad8796e08831dcd9204b6610c19930982`，owner reviewed merge为`73320913a9321c52c220104f66ed295d692a0c33` / tree `359eb1961157f71e1b3cc48b50a901e831cb0be9`。feature与overlay均获independent `0/0/0/0`。
- PR #66以exact one-file correction把execution owner状态更新到O merged、22 Plans、20/39；完整suite为`1507 passed, 1 deselected, 12 warnings`，independent review为`0/0/0/0`，merge为`4ed68875fdf2330b6947b7f85235cec388d2af14`。
- 当前七文件planning-status Packet只索引N/O证据并形成`B_O_PLANNING_STATUS`；其后Project Direction sole writer独立形成`B_O_STATUS`。两道barrier都不推进lifecycle。
- F只能从`B_O_STATUS`形成`B_F`，E只能从reviewed`B_F`形成non-routable `B_FE_EXPAND`；后续严格服从唯一execution map。
- 用户已明确暂时停用Graphify；它不再参与当前或后续验证、freshness、status、F/E或共同barrier门禁。

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
- [x] 01-07D / 01-07H独立Plan已通过PR #56/#57以final `0/0/0/0` review签发；Plan merge/blob provenance、同一`B_CG` feature base与D/H allowlist交集0均已机械确认。
- [x] 01-07D / 01-07H feature已通过PR #59/#60完成合同反馈/RED、GREEN、exact-head review、latest replay与串行merge，形成`B_DH = 4a7e802...`；D/H Summary已索引。
- [x] 01-07N Plan/owner PR #62/#63完成cutover remediation；manifest equality、10 mutations、registry/catalog与future-symbol leakage检查均通过。
- [x] 01-07O Plan/owner PR #64/#65完成唯一execution map；JSON equality、18 mutations、15 packets、target 39与stale-consumer映射检查均通过。
- [x] PR #66完成execution owner post-merge计数校正；1507 full与independent `0/0/0/0` review通过。
- [x] 当前scope的Wave 0已完成，`wave_0_complete=true`；这不推进Case lifecycle。
- [ ] 当前七文件planning-status Packet尚待exact-head review与merge形成`B_O_PLANNING_STATUS`；其后还需独立Project Direction one-file Packet形成`B_O_STATUS`。

**Approval:** `W2_THROUGH_01-07O_COMPLETE / WAVE_0_COMPLETE / PLANNING_STATUS_ALIGNMENT_IN_PROGRESS / B_O_PLANNING_STATUS_PENDING`。D/H/N/O均已完成各自Plan、实现或owner合同、focused/full、exact-head review、latest-integration replay与串行merge；PR #66已把execution owner派生状态校正为`20/39`。当前正式签发22个Plan、20份Summary，numbered Plan evidence仍为7/8，canonical lifecycle与Requirements checkbox仍为0/8。现在先把本七文件Packetreviewed merge为`B_O_PLANNING_STATUS`，再由Project Direction sole writer形成`B_O_STATUS`；随后严格按`F → E → {I,P} → {K,L} → M → Q → J → {S,U} → X → T → W → V`执行。本文件不批准F/E、Case、credentialed Baseline、release或lifecycle结论。用户已暂停Graphify，它不参与当前或后续门禁。
