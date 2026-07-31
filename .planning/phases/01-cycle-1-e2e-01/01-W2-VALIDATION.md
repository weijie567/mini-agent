---
phase: 01-cycle-1-e2e-01
slug: cycle-1-e2e-01-w2
scope: phase-01-plan-task-feedback-through-01-08A-post-remediation
status: nyquist_plan_task_feedback_and_post_quality_alignment_complete
nyquist_compliant: true
wave_0_complete: true
created: "2026-07-27"
audited: "2026-07-31"
audit_base_sha: 7097641424b88a814bd2f3510ebd563b3cfd40b4
audit_base_tree: ab393e73986feddc4ca3dd771312bfd142cfae36
plan_artifacts: 49
summary_artifacts: 24
implementation_targets: "42/42"
canonical_lifecycle: "E2E01-01/04_REGRESSION_GATE"
release_transition: "COMPLETE_PR_199_MERGED_TO_MAIN"
---

# Phase 1 W2｜Validation Strategy

> **DERIVED / NON_NORMATIVE**
> 本文件只索引Phase 01截至01-08A及post-execution quality gate的Plan-task自动化反馈证据。`nyquist_compliant: true`本身不推进Case lifecycle；canonical Eval owner已在后续独立PR中将六个authenticated physical Case推进为`REGRESSION_GATE`。本文件只同步该事实，不表示真实Qwen Baseline、canonical产品启动或production readiness；最终release completion另由用户风险确认、PR #199 exact-head review与`main` merge证据建立。

## Test Infrastructure

| Property | Value |
|---|---|
| Framework | pytest / pytest-asyncio；PostgreSQL integration tests |
| Config | `pyproject.toml`、`tests/conftest.py`、`compose.yaml`、`alembic.ini` |
| Quick command | 每个 Task Packet 的 exact focused pytest command |
| Full suite | `uv run pytest` |
| Infra preflight | `uv sync --all-groups`；检查persistent `db`与disposable `db-test`可用；`uv run alembic upgrade head`验证development DB，migration regression test在`db-test`独立fresh schema执行 |
| Product barriers | `B_RU_V2_CONTRACT = 5c84e0e...`；`B_01_08 = b8a2cf3...`；`B_01_08A_COMPOSITION = c59eaea...`；`B_01_08A = 11d6d088...` |
| Current reviewed evidence | post-remediation REVIEW在PR #172合并；PR #173完成本Validation；PR #184同步`REGRESSION_GATE`；PR #185/#186完成mandatory Eval/Security re-review |
| Current exact full | exact Security re-review barrier `22c4cfa672e7a4a91916100e9868585e6b2bcdf9`：`2007 passed, 1 deselected, 12 warnings in 147.45s` |
| Current late-phase focused | 01-07S/U/X/T/W/V、01-08、01-08A相关21个focused test files：`1787 passed in 123.01s` |
| Credential preflight | 缺失Qwen环境变量：`1 skipped`，reason `MISSING_REQUIRED_ENV`；无失败、无外部network |
| Max feedback latency | focused task tests应在每个原子 commit前完成；full suite在每个 Packet handoff前完成 |

仓库当前没有 canonical lint、type-check、build 或 app-start命令，也没有 pinned Ruff dependency；不得编造。允许的附加机械检查为 `compileall`、`git diff --check`、artifact SHA 与 changed-file containment。

## Sampling Rate

- 每个 TDD task：先运行新测试取得预期 RED，再完成 GREEN。
- 每个原子 commit 前：运行该 task 的 exact focused tests。
- 每个 Packet handoff 前：运行 Packet 全部 focused tests、`uv run pytest` 和机械 containment。
- 每个 feature PR 最新 head：独立 reviewer 读取 exact diff和测试证据；finding修复后重新运行受影响 focused + full suite。
- 每次串行合并前：在 latest integration overlay / merge candidate上重复 full suite。
- 01-07D / 01-07H已从`B_CG`以互斥allowlist执行并串行形成`B_DH`；01-07N/O又依次完成cutover remediation与唯一execution map。
- 01-07F从exact `B_O_STATUS`形成`B_F`，01-07E再从reviewed `B_F`形成non-routable `B_FE_EXPAND`；两者feature与latest overlay均重复scope、protected-v1、focused、full与独立review。
- 01-07I从exact `B_FE_EXPAND`完成Application dependency expand；01-07P经dedicated oracle remediation后从exact `B_I_E_ORACLE_FIX`完成r1 acceptance replay；两者串行形成non-routable `B_IP`，feature与latest overlay均重复scope、focused/database/full与独立review。
- **HISTORICAL BARRIER CHAIN：** 01-07K/L从exact `B_IP`以互斥ownership执行并串行形成`B_DEPENDENCY`；M与Q依序形成`B_DEPENDENCY_M`和`B_Q`。Execution-map r2新增Y/Z/AA后，Y/Z形成`B_YZ`，AA形成`B_J_READY`，J形成当时的scoped `B_ACTIVE`；该入口已由当前`B_RU_V2_CONTRACT`、`B_01_08`、`B_01_08A_COMPOSITION`和`B_01_08A`后续barrier supersede。
- 01-07S/U/X/T/W/V、01-08、01-08A均已完成reviewed exact-head、latest-integration compatibility与post-remediation复验；真实credentialed Qwen执行仍是独立环境门禁，缺凭据preflight保持`NOT_RUN / SKIPPED`。

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure behavior | Test type | Automated command | File exists | Status |
|---|---|---:|---|---|---|---|---|---|---|
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
| 01-07F-01 | 01-07F | 19 | E2E01-01/04 | RUV2-S01/RUV2-T01/RUV2-R01/RUV2-I01/RUV2-D01/RUV2-E01 | additive v2 Core DTO、pure projection与exact local closure；拒绝trusted/private/undeclared state且保护全部v1 definitions | Component contract | 92 focused；41-definition source/AST oracle；1575 full；feature/latest-overlay review | ✅ existing | ✅ green |
| 01-07E-01 | 01-07E | 20 | E2E01-01/04 | RUC-S01/RUC-T01/RUC-R01/RUC-I01/RUC-D01/RUC-E01 | immutable 18-pair catalog、exact-version API、RU v2 8+4 projection、child closure、bounded metadata与17-pair legacy parity | Component contract | 233 focused；60-definition/12-mutant oracle；catalog/consumer gate；1671 full；feature/latest-overlay review | ✅ existing | ✅ green |
| 01-07I-01 | 01-07I | 21 | E2E01-01/04 | ERI-S01/ERI-T01/ERI-R01/ERI-I01/ERI-D01/ERI-E01 | owner-scoped、transactionally-consistent exact-Run logical closure、不可区分read Port、bounded candidate-invalid signal与additive ModelProviderV2；v1 surface与active routing不变 | Component contract | 357 focused；protected-v1/closure/Port/signal oracle；1759 full；feature/latest-overlay review | ✅ existing | ✅ green |
| 01-07P-01 | 01-07P | 21 | E2E01-01/04 | RUP-S01/RUP-T01/RUP-R01/RUP-I01/RUP-D01/RUP-E01 | exact 17-code/18-pair physical admission、self-contained 0003与同事务fail-closed downgrade lock；不切换logical codec/reader/writer | Migration integration | 48 focused；119 database；downgrade AST/order/concurrency/atomicity；1767 full；feature/latest-overlay review | ✅ existing | ✅ green |
| 01-07K-01 | 01-07K | 22 | E2E01-01/04 | K-S01/K-T01/K-R01/K-I01/K-D01/K-E01 | owner-scoped exact-Run strict PostgreSQL reader与authoritative order source-version producer；pre-payload indistinguishability、single-snapshot closure与fixed-vector parity | Infrastructure integration | feature/overlay 59 focused；protected oracle `58 + 2 exact`；1813 full；exact-head/latest-overlay review | ✅ existing | ✅ green |
| 01-07L-01 | 01-07L | 22 | E2E01-01/04 | L-S01/L-T01/L-R01/L-I01/L-D01/L-E01 | v2 Scripted/Qwen Provider failure partition、case-free exact-Run HTTP mapper与logical-v2 evidence validation；Runtime catch仍归J | Eval component + integration | feature/overlay 837 focused；mapper 386；Qwen zero-network 23；latest overlay 1901 full；review findings closed | ✅ existing | ✅ green |
| 01-07M-01 | 01-07M | 23 | E2E01-01/04 | M-S01/M-T01/M-R01/M-I01/M-D01/M-E01 | `GetOrderResult.FOUND`强制strict source version并保持negative错误优先级、ToolSpec non-exposure与既有producer闭合 | Core component contract | RED `1 failed, 38 passed`；GREEN 39；feature/overlay 1901 full；independent review | ✅ existing | ✅ green |
| 01-07Q-01 | 01-07Q | 24 | E2E01-01/04 | Q-S01/Q-T01/Q-T02/Q-R01/Q-I01/Q-D01/Q-E01 | public RU persistence mapping切换v2，同时保持legacy API隔离、exact catalog与physical migration oracle | Application component contract | component 233；K isolation 50；migration oracle 48；feature/overlay 1901 full；independent review | ✅ existing | ✅ green |
| 01-07Y-01 | 01-07Y | 25 | E2E01-01/04 | Y-S01/Y-T01/Y-T02/Y-T03/Y-R01/Y-I01/Y-D01/Y-E01 | 纯确定性v2 initial decision与post-write revalidation；拒绝把整体失败伪装成REJECT或自行定义Runtime结果 | Core component contract | focused 88；neighbors 37；feature/overlay 1934 full；双review全零 | ✅ existing | ✅ green |
| 01-07Z-01 | 01-07Z | 25 | E2E01-01/04 | Z-S01/Z-T01/Z-T02/Z-T03/Z-R01/Z-I01/Z-D01/Z-E01 | exact-v2 Application command/Port写合同；不实现Adapter、不路由Runtime、不通过动态fallback探测 | Application component contract | feature/overlay 368 focused；latest overlay 1945 full；双review全零 | ✅ existing | ✅ green |
| 01-07AA-01 | 01-07AA | 26 | E2E01-01/04 | 01-07AA Plan security acceptance | owner-scoped PostgreSQL RU-v2 atomic writers、static exact-version chain、CAS/closed-set/concurrency/fault replay与bounded failure | Infrastructure integration | RED 12 expected failures；focused+codec 38；neighbors 136；feature/overlay 1987 full；双review全零 | ✅ existing | ✅ green |
| 01-07J-01 | 01-07J | 27 | E2E01-01/04 | 01-07J Plan security acceptance | Runtime切换到reviewed v2 reducer/command/writer；authoritative Message reload、source-version exact-copy、INPUT_INVALID raw-free与exact-one PostgreSQL闭合 | Application component + integration | focused 87；Application 707；neighbors 165；full 2033；exact-head/latest-overlay review与merge-tree equality | ✅ existing | ✅ green |
| 01-07S-01 | 01-07S | 28 | E2E01-01/04 | 01-07S Plan security acceptance | Eval / Provider executable surface只接受RU v2；artifact未激活时fail closed，failure taxonomy与zero-network边界保持闭合 | Eval component + integration | `uv run pytest tests/component/evaluation/test_e2e01_artifact_consistency.py tests/component/evaluation/test_e2e01_graders.py tests/component/evaluation/test_e2e01_scripted_model_provider.py tests/component/model/test_qwen_responses_adapter.py tests/integration/evaluation/test_e2e01_offline_harness.py -x` | ✅ existing | ✅ green |
| 01-07U-01 | 01-07U | 28 | E2E01-01/04 | 01-07U Plan security acceptance | active Runtime与owned double不保留v1 / `source_version` fallback或动态别名绕行 | Runtime component | `uv run pytest tests/component/application/test_agent_run_service.py -x` | ✅ existing | ✅ green |
| 01-07X-01 | 01-07X | 29 | E2E01-01/04 | 01-07X Plan security acceptance | PostgreSQL surface只接受RU v2；physical collision、并发、fault rollback与recovery均fail closed且无mutation泄露 | Infrastructure integration | `uv run pytest tests/integration/test_postgres_record_adapters.py tests/integration/test_postgres_v2_request_understanding_writes.py tests/integration/test_postgres_atomicity.py -x` | ✅ existing | ✅ green |
| 01-07T-01 | 01-07T | 30 | E2E01-01/04 | 01-07T Plan security acceptance | Application codec只暴露current RU v2 projection；roundtrip、tamper与physical pair admission保持closed | Application component + migration integration | `uv run pytest tests/component/application/test_persistence_contract.py tests/component/application/test_record_contracts.py tests/integration/test_database_migrations.py -x` | ✅ existing | ✅ green |
| 01-07W-01 | 01-07W | 31 | E2E01-01/04 | 01-07W Plan security acceptance | Application records / ports无可执行v1静态或动态alias，V2 public contract保持exact | Application component | `uv run pytest tests/component/application/test_ports_contract.py tests/component/application/test_record_contracts.py -x` | ✅ existing | ✅ green |
| 01-07V-01 | 01-07V | ru-v1-contract-final | E2E01-01/04 | 01-07V Plan security acceptance | Core无legacy v1 executable surface；zero/all reject、exact-one、multi、revalidation与stale-state保持确定性closed behavior | Core component | `uv run pytest tests/component/core/test_request_processing.py tests/component/core/test_control_gateway.py tests/component/core/test_identity_contract.py tests/component/core/test_request_understanding_contract.py tests/component/core/test_task_state_contract.py -x` | ✅ existing | ✅ green |
| 01-08-01 | 01-08 | w3-offline-vertical-integration | E2E01-01/04 | 01-08 Plan security acceptance | strict fixture、startup recovery、composition isolation与直接HTTP → Runtime → PostgreSQL owner-scoped path；foreign/nonexistent保持不可区分且零Observation泄露 | Offline vertical integration / E2E evidence | `uv run pytest tests/integration/test_offline_composition_root.py tests/e2e/test_e2e01_http_eval.py -x`；这是offline vertical evidence，不是lifecycle-valid Trajectory / E2E Eval Result或PASS | ✅ existing | ✅ green |
| 01-08A-01 | 01-08A | w3-credentialed-qwen-baseline | E2E01-01/04 | 01-08A Plan security acceptance | credential-aware runner、preflight、adapter isolation、secret cleanup、zero-network fail-closed与MockTransport real composition均被覆盖 | Eval integration + baseline preflight | `uv run pytest tests/integration/evaluation/test_e2e01_offline_harness.py -x`；`env -u DASHSCOPE_API_KEY -u DASHSCOPE_BASE_URL uv run pytest -m qwen_baseline tests/baseline/test_qwen_baseline.py -x`；真实credentialed result仍为`NOT_RUN / SKIPPED` | ✅ existing | ✅ green |

*Status: ⬜ pending/replay · ✅ green/feature · ❌ red · ⚠️ flaky；`feature`不表示已merge或通过latest-integration gate。*

### Denominator-neutral handoff / remediation classification

以下Plan只修复dependency、scope、acceptance oracle或owner handoff，不重复计入产品行为denominator；其变更由相邻owner Packet的同一自动化命令和exact changed-file containment覆盖：

| Plan | Classification | Covered by |
|---|---|---|
| `01-07AA-CODEC-BOUNDARY-SCOPE-AMENDMENT` | codec boundary scope amendment | 01-07AA / 01-07T codec、writer与migration tests |
| `01-07AA-CODEC-HANDOFF` | codec owner handoff | 01-07AA / 01-07T persistence与PostgreSQL v2 write tests |
| `01-07AA-ORACLE-FIX` | acceptance oracle remediation | 01-07AA / 01-07T migration、catalog与physical pair oracle |
| `01-07AB` | exact-reader scope alignment | 01-07K / 01-07X PostgreSQL exact reader tests |
| `01-07T-PHYSICAL-HANDOFF` | physical metadata owner handoff | 01-07T / 01-07X migration与physical collision tests |
| `01-07V-EVAL-HANDOFF` | Eval consumer remediation | 01-07S / 01-07V v2-only Eval与Core tests |
| `01-08A-COMPOSITION-HANDOFF` | Qwen composition seam handoff | 01-08 / 01-08A composition、Harness与zero-network tests |

## Wave 0 Requirements

Wave 0 是各 Packet的首个测试或合同反馈提交，不新增共享 bootstrap。01-04H至01-07J的当前scope均已有reviewed绿色证据，因此`wave_0_complete=true`：

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
- 01-07F：三份Core tests先取得缺失v2 surface的真实RED，再以三份Core source完成GREEN与review fixes；feature/overlay最终92 focused、1575 full、protected-v1与independent `0/0/0`通过，PR #71已merge。
- 01-07E：Application persistence contract先取得`138 passed / 66 failed`的真实RED，再以persistence source完成GREEN与review fixes；feature/overlay最终233 focused、1671 full、60-symbol oracle、catalog/consumer与independent `0/0/0`通过，PR #74已merge。
- 01-07I：两份Application tests先取得缺失closure/Port/signal/Provider v2 surface的真实RED，再以两份source完成GREEN与append-only fixes；feature/overlay最终357 focused、1759 full与independent `0/0/0/0`通过，PR #83已merge。
- 01-07P：migration integration test先取得缺失0003/18-pair/downgrade合同的真实RED；原PR #82因跨Packet oracle冲突关闭未合并，经PR #84/#85 remediation后r1重放byte-identical GREEN patch并追加downgrade lock oracle fix；feature/overlay最终48 focused、119 database、1767 full与independent `0/0/0/0`通过，PR #87已merge。
- 01-07K/L：分别以Infrastructure与Eval互斥allowlist完成strict reader/order producer及v2 Provider/mapper反馈；L首轮`0/3/3/0` findings由security amendment与append-only fixes关闭，PR #96/#98串行merge形成`B_DEPENDENCY`。
- 01-07M/Q：M以单一预期RED关闭`FOUND + None`，Q以Application codec contract反馈切换public active mapping；PR #101/#106依序形成`B_DEPENDENCY_M`与`B_Q`。
- 01-07Y/Z：Core reducer与Application write-contract两个互斥writer均完成真实RED→GREEN、exact-head与latest overlay；PR #110/#111串行形成`B_YZ`。
- 01-07AA：经closure与codec quality-gate remediation后，r2在最终acceptance base重放fresh RED→GREEN并通过PostgreSQL atomicity/concurrency/fault矩阵；PR #120形成`B_J_READY`。
- 01-07J：三个owned tests取得Runtime仍走v1、缺v2 writer调用与source-version copy的真实RED；两个source完成GREEN与append-only review fix，PR #124通过双review、merge-tree equality与post-merge full形成scoped `B_ACTIVE`。
- 01-07S/U/X/T/W/V：Eval / Provider、Runtime、Infrastructure、Application codec / ports与Core依次关闭v1 executable surface；适用focused、neighbor、database、full、exact-head review与latest-integration replay均已完成，形成`B_RU_V2_CONTRACT = 5c84e0e...`。
- 01-08：显式`OfflineE2E01Composition`、real `EvalCaseSut`、PostgreSQL exact owner-scoped evidence reader及直接HTTP → Runtime → PostgreSQL离线纵向evidence已完成，形成`B_01_08 = b8a2cf3...`；该证据不激活Case lifecycle。
- 01-08A-COMPOSITION-HANDOFF / 01-08A：先形成`B_01_08A_COMPOSITION = c59eaea...`，再完成credential-aware runner与fail-closed preflight，形成`B_01_08A = 11d6d088...`；真实credentialed baseline仍未运行。
- 不修改 `pyproject.toml`、`uv.lock`、共享 fixtures或canonical owners。

原01-05/06/07三个writer、01-04H、01-05R、01-06R与01-07A均已展示各自RED；01-07B又以test-only commit `8978655a...`形成独立RED，并由GREEN / review-fix、双review与merge证据闭环。D/H/N/O/F/E/I/P/K/L/M/Q/Y/Z/AA/J及后续S/U/X/T/W/V/08/08A也已完成各自首个合同或测试反馈、GREEN、review与merge，所以当前scope的`wave_0_complete=true`。该字段仅表示Plan-task反馈入口完整，不推进Case lifecycle、Requirements或release状态。

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

### HISTORICAL 01-07 Eval gate（superseded by current 01-08A evidence）

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

下列命令记录01-07当时的historical gate：只运行显式清除凭据的preflight，证明`NOT_RUN / SKIPPED`与零network。其“等待01-08 / 01-08A实现”的前提已经被当前实现supersede；默认full gate仍因marker排除真实credentialed lane：

```bash
env -u DASHSCOPE_API_KEY -u DASHSCOPE_BASE_URL \
  uv run pytest -m qwen_baseline tests/baseline/test_qwen_baseline.py -x

DASHSCOPE_API_KEY=not-a-real-key \
DASHSCOPE_BASE_URL=https://example.invalid \
  uv run pytest -m qwen_baseline tests/baseline/test_qwen_baseline.py -x

# Explicit credentialed lane only; requires real configured environment:
uv run pytest -m qwen_baseline tests/baseline/test_qwen_baseline.py -x
```

当前01-08 real SUT wiring与01-08A runner均已存在。缺失`DASHSCOPE_API_KEY` / `DASHSCOPE_BASE_URL`时仍必须得到canonical `SKIPPED / NOT_RUN`，不得生成PASS或访问网络；当前exact preflight为`1 skipped / MISSING_REQUIRED_ENV`。

上述historical命令已在feature与latest overlay重复通过；当时post-merge为191 focused、40 migration与936 full（1 deselected）。当前credential-aware runner已由01-08A实现并reviewed merge，但真实credentialed Qwen结果仍是`NOT_RUN / SKIPPED`，不能由MockTransport或test-only executable bundle替代。

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

01-07A已保留test-only RED并证明Context Manifest purpose、每个normal result exactly-one ResponseRendered、pre-render FAILED zero ResponseRendered、post-render terminal failure保留一个真实reached-stage event但无result/ASSISTANT/RunStopped，以及explicit active-run hook identity；changed-file set精确为Runtime source/test pair。PR #37/#38 reviewed merge后为27 directed、100 Runtime focused、40 migration与936 full（1 deselected）。**HISTORICAL：** 它当时不产生Eval Result，也不批准01-08；当前01-08后续证据单独索引在Per-Task map。

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

01-07B也不改变外部`ModelProvider`失败合同；当时确认的invalid Request Understanding schema / trusted-field override、raw `ValidationError`与`ProviderProtocolError`分类，以及source-version producer / closure缺口都属于后续owner，而不是01-07B的完成内容。01-07N/O及execution-owner r2已经显式supersede本段曾使用的旧Packet顺序与39分母；当前writer、allowlist、failure-taxonomy ownership、source-version阶段、active switch、v1 contract closure、barrier和目标`42`只由[多Agent实施计划](../../../docs/implementation/e2e01-thin-slice-multi-agent-plan.md)中的marker-bounded `P0-RU-V2-EXECUTION-MAP`拥有。本Validation只索引reviewed evidence，不维护第二套顺序。**HISTORICAL：** 当时不能从scoped `B_ACTIVE`推断01-08解锁；当前01-08已由独立reviewed barrier完成。

### HISTORICAL 01-07C / 01-07G Owner rulings

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

### HISTORICAL 01-07D / 01-07H / 01-07N / 01-07O / 01-07F / 01-07E / 01-07I / 01-07P / 01-07K–J completion and barriers

- D/H分别通过Plan PR #56/#57与feature PR #59/#60从同一`B_CG`执行；allowlist交集为0，feature与latest overlay均获independent `0/0/0/0`，串行merge形成`B_DH = 4a7e802e8aebc54e0582a1e4d99f140b56e7b131` / tree `a5a60292ccdf116aba4dacaaea366576e183c532`。
- N Plan / owner PR #62/#63从exact `B_DH`关闭旧E/F同base授权，reviewed merge为`a4b1edb4c50a2e3e826571194bac58f7b31eab6d` / tree `469e26460c1041d9ca5042d39ae9a57ded7d5442`；它只冻结`p0-ru-v2-cutover-r1`，不实现Core、codec、migration或routing。
- O Plan / owner PR #64/#65从exact N merge执行；Plan merge为`274178bad8796e08831dcd9204b6610c19930982`，owner reviewed merge为`73320913a9321c52c220104f66ed295d692a0c33` / tree `359eb1961157f71e1b3cc48b50a901e831cb0be9`。feature与overlay均获independent `0/0/0/0`。
- PR #66以exact one-file correction把execution owner状态更新到O merged、22 Plans、20/39；完整suite为`1507 passed, 1 deselected, 12 warnings`，independent review为`0/0/0/0`，merge为`4ed68875fdf2330b6947b7f85235cec388d2af14`。
- B_O planning-status / Project Direction evidence alignment已依次形成exact `B_O_STATUS = 73696a138eb13fc4a90a0f760b13865f53d08704`，不推进lifecycle。
- F Plan / feature PR #70/#71从exact `B_O_STATUS`执行；feature与latest overlay均获independent `0/0/0`，串行merge形成`B_F = 034cf57228c4a9da4764b0c7322dc5d34652a09c` / tree `c62d660213d8c74f922a7832ed778f3ac6f3b104`。
- E Plan PR #72从reviewed `B_F`签发；PR #73修复Plan containment正则；feature PR #74经两轮finding closure、feature与latest-overlay independent `0/0/0`后形成`B_FE_EXPAND = 294ada386ec160ec2a48fc8883b5a38f1880e4ba` / tree `97b0928100edae965004338d52ce87dff7325fd1`。
- I Plan / feature PR #80/#83从exact `B_FE_EXPAND`完成Application exact-Run closure、Port、bounded signal与additive Provider v2 declaration；feature与latest overlay最终357 focused、1759 full及independent `0/0/0/0`通过，reviewed merge为`b14a15d60b17eda8d8b5aed892c5d00f16005310`。
- P原PR #82只保留blocked lineage并关闭未合并；dedicated oracle fix PR #84形成`B_I_E_ORACLE_FIX = 0fb4d0ba5fb9d673f2d116041ce023dd367a52ec`，execution-owner remediation PR #85与r1 Plan PR #86授权同一Packet acceptance replay。P-r1 feature PR #87经首轮`0/0/1/0` finding closure后，feature/overlay最终48 focused、119 database、1767 full及independent `0/0/0/0`通过。
- P-r1 reviewed serial merge形成`B_IP = bbe14fadc0cd2e14ad35e19177b079fcab685dfc` / tree `65415ff5846892f257e95d8b8bd34f50752980a2`；exact post-merge Alembic head为`20260728_0003`，full为`1767 passed, 1 deselected, 12 warnings`，namespace contamination为0。
- K/L Plan、feature与security amendment PR #94–#98从exact `B_IP`执行并串行形成`B_DEPENDENCY = e54a6a4d77208695440c2caf03c3ab32f9d37108`；exact full为`1901 passed, 1 deselected, 12 warnings`。
- M Plan、shell correction与feature PR #99–#101形成`B_DEPENDENCY_M = 42fa2ec7ef1a61a2edfd78d69ca4e6a5d32aa1c3`；Q oracle remediation与Plan/category/feature PR #102–#106形成`B_Q = 2b9fde6f0e09308a53b86a4929ea3b639660f82e`。
- Execution-owner r2 PR #107把Y/Z/AA纳入42 denominator；Y/Z PR #108–#111形成`B_YZ = d704b87480f0a4252744f4c009cef9a86c08fa05`，AA与quality-gate remediation PR #112–#120形成`B_J_READY = b8d32d50775a0d3f4a0d3e7e609c717f6c540b33`。
- J Plan、exact-reader scope alignment与feature PR #121–#124通过exact-head/latest-overlay双review、merge-tree equality与post-merge focused 87、Application 707、neighbors 165、full `2033 passed, 1 deselected, 12 warnings`，形成historical scoped `B_ACTIVE = 7f92b5e0a05714a6a9d7325861499d7cc0bf04dd` / tree `f70b20215e569acf3ad196cc050e9a23700d4bae`。
- **CURRENT POST-QUALITY UPDATE：** 01-07S/U/X/T/W/V已完成v1 contract closure并形成`B_RU_V2_CONTRACT = 5c84e0e...`；01-08和01-08A又依次形成`B_01_08 = b8a2cf3...`、`B_01_08A_COMPOSITION = c59eaea...`、`B_01_08A = 11d6d088...`。六个authenticated physical Case已为`REGRESSION_GATE`，全部16 variants生成lifecycle-valid Result并PASS；readiness、canonical产品启动与真实credentialed Qwen仍未完成。
- 用户已明确暂时停用Graphify；后续不运行、不引用，也不把freshness作为门禁。

## Manual-only Verification

| Behavior | Requirement | Why manual | Instructions |
|---|---|---|---|
| GitHub branch / PR ownership | E2E01-01/04 | Git metadata不由pytest证明 | 比较exact base/head/tree、changed-file allowlist、PR base/head与reviewed SHA |
| Latest-integration containment | E2E01-01/04 | pytest不证明reviewed SHA、merge ancestry或单writer allowlist | 核对`7097641424...` / tree `ab393e73...`为review/remediation descendant，且post-review只含派生文档变化 |
| Real credentialed Qwen | E2E01-01/04 | 需要显式真实credential与受控external transport；缺凭据preflight只能证明fail-closed | 在approved exact integrated head配置凭据后单独运行`uv run pytest -m qwen_baseline tests/baseline/test_qwen_baseline.py -x`；在此之前保持`NOT_RUN / SKIPPED` |
| Canonical lifecycle ruling | E2E01-01/04 | Case / artifact lifecycle只能由canonical Eval owner裁决 | `CONFIRMED`：PR #178/#180推进`EXECUTABLE`，PR #183/#184推进`REGRESSION_GATE`；本Validation只消费结果 |
| Controlled UAT | E2E01-01/04 | 用户可观察体验与人工验收不是pytest替代项 | `COMPLETE / scoped PASS`：`CODEX_INTEGRATOR`以`DIRECT_CONTROLLED_EXECUTION`运行16 variants；`end_user_uat = NOT_RUN` |
| Release decision | E2E01-01/04 | release需要跨owner证据与明确审批 | `COMPLETE`：用户继续接受有界`RTA-D01`；exact-head review `PASS`的PR #199已squash merge到`main`（`f15320e3...`） |

01-08的直接HTTP → Runtime → PostgreSQL测试和后续16-variant lifecycle-valid Results均已形成；controlled UAT也已完成scoped Integrator验收。它们仍不能替代真实credentialed Qwen、canonical产品启动或end-user UAT，也不能单独替代最终release decision；该decision已由用户确认与PR #199 merge独立建立。

## Validation Sign-off

- [x] 当前磁盘49份Plan artifact、24份Summary均已分类；42/42 implementation target已有自动化行为或合同反馈。
- [x] 每个适用Plan task都有actual automated command、existing test file或contract-only机械反馈；没有真实测试缺口。
- [x] 01-07S/U/X/T/W/V、01-08、01-08A八项旧索引缺口均已补入Per-Task map并标记green。
- [x] denominator-neutral amendments / handoffs / oracle remediation已单独分类，不重复计入产品行为denominator。
- [x] 无watch-mode flag。
- [x] post-remediation REVIEW已在PR #172合并，`P0/P1/P2/P3 = 0/0/0/0`；exact validation base为`7097641424...` / tree `ab393e73...`。
- [x] current exact full为`2007 passed, 1 deselected, 12 warnings in 147.45s`；late-phase Validation的21-file focused历史证据为`1787 passed in 123.01s`。
- [x] 缺凭据Qwen baseline为`1 skipped / MISSING_REQUIRED_ENV`；runner/preflight已覆盖，但没有真实credentialed result。
- [x] `nyquist_compliant: true`只表示Plan-task automated feedback coverage；后续Case lifecycle变化来自canonical owner，不由本Validation宣布。
- [x] 六个authenticated physical Case已为`REGRESSION_GATE`；全部16 variants有lifecycle-valid Result并PASS。
- [x] 当前没有canonical app-start、真实credentialed Qwen Result、production readiness或P0完成证据。
- [x] 本次audit没有新增测试，也没有修改Case、artifact、manifest或loader lifecycle。

## Validation Audit 2026-07-30

| Metric | Count |
|---|---:|
| Gaps found | 8 |
| Resolved | 8 |
| Escalated | 0 |
| Tests added | 0 |

八个gap均为01-07S/U/X/T/W/V、01-08、01-08A已存在绿色自动化证据未进入旧Validation索引；没有发现真实测试缺口或实现缺陷。denominator-neutral handoff / remediation另行分类，不计入这八个产品行为映射gap。

**Approval:** `NYQUIST_PLAN_TASK_FEEDBACK_COVERED_THROUGH_01_08A / VALIDATION_INDEX_REFRESHED / NO_TEST_GAP / POST_QUALITY_STATUS_ALIGNED / PHASE_1_RELEASE_COMPLETE`。本派生Validation覆盖49份Plan artifact、42/42 implementation target及post-quality evidence；Case lifecycle当前为`REGRESSION_GATE`，全部16 variants为PASS。用户已继续接受有界`RTA-D01`，reviewed PR #199已合并到`main`。真实credentialed Qwen、canonical app-start、end-user UAT和production readiness仍未完成。
