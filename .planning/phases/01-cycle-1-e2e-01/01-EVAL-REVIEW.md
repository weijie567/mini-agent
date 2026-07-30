---
phase: 01-cycle-1-e2e-01
phase_number: 1
phase_name: Cycle 1 E2E-01
document: EVAL-REVIEW
status: DERIVED_NON_NORMATIVE
audit_date: 2026-07-31
audited_base_sha: 4be26e397a33d8d26cca5a7a8038023ab7db732d
audited_head_sha: 4be26e397a33d8d26cca5a7a8038023ab7db732d
ai_spec_present: false
canonical_eval_owners_present: true
coverage_score: 71
infrastructure_score: 70
overall_score: 71
verdict: NEEDS_WORK
critical_gap_count: 2
---

# EVAL-REVIEW — Phase 1: Cycle 1 E2E-01

> **DERIVED / NON_NORMATIVE**
>
> 本报告只回答“已实现系统是否交付了规划的 Eval strategy”，不拥有业务、架构、Case lifecycle、Requirement、发布或生产就绪语义，不推进任何状态。审计范围固定为 base/head `4be26e397a33d8d26cca5a7a8038023ab7db732d`。

**Audit Date:** 2026-07-31

**AI-SPEC Present:** No。Phase 目录没有 `AI-SPEC.md`；依据项目治理，使用 canonical [Agent Evaluation Strategy](../../../docs/evaluation/agent-evaluation-strategy.md) 与派生状态 owner [P0 Eval Coverage Matrix](../../../docs/evaluation/p0-eval-coverage-matrix.md) 代替 stock GSD AI-SPEC，不把 `.planning/` 升级为第二套 owner。

**Business / scoped implementation references:** [Business Capabilities](../../../docs/business-capabilities.md)、[E2E-01 Thin Slice Implementation Spec](../../../docs/implementation/e2e01-thin-slice-implementation-spec.md)

**Overall Score:** 71/100

**Verdict:** **NEEDS WORK**

## Executive Finding

结论是：**Phase 1 已交付大部分 Eval machinery、确定性质量判定与可复现的直接离线纵向证据，但尚未交付 canonical strategy 要求的 lifecycle-valid Trajectory / E2E Eval Result 与持续回归 Gate。**

`CONFIRMED`：

- versioned authenticated Fixture / Case / model script / lane / manifest、严格 loader、双 Provider Adapter、13 个确定性 Grader、`OfflineEvalHarness`、结构化 `EvalResult` / execution-failure persistence 均已实现。
- `OfflineE2E01Composition`、真实 `EvalCaseSut`、PostgreSQL exact owner-scoped evidence reader，以及 HTTP → Runtime → PostgreSQL 的直接离线纵向证据均存在。
- E2E01-01 本人订单、E2E01-04-A/B 非本人/不存在安全等价、参数绑定拒绝、Provider / Presentation 协议故障、Trace / persistence / replay 等关键行为已有自动化证据。
- post-remediation review 记录为 `P0/P1/P2/P3 = 0/0/0/0`；canonical 串行套件记录为 `2004 passed, 1 deselected, 12 warnings in 131.04s`，late-phase focused 记录为 `1787 passed in 123.01s`。

`CONFIRMED NOT DELIVERED`：

- 6 个 Phase Case artifacts、manifest 与 loader 均保持 `CONTRACT_DEFINED`。Harness 在 SUT / Provider / Trace / Grader / Result 之前按设计持久化 bounded `CASE_SETUP_FAILED`，不会生成 lifecycle-valid `PASS / FAIL`。
- 没有 lifecycle-valid Trajectory / E2E Eval Result、聚合回归报告或持续门禁。
- 缺凭据 Qwen baseline 的现有证据为 `1 skipped / MISSING_REQUIRED_ENV`；真实 credentialed Qwen Result 仍是 `NOT_RUN / SKIPPED`。该 lane 当前不是 release gate，不能用 MockTransport 或 test-only executable bundle替代。
- canonical app-start、生产 monitoring、普通质量/延迟/成本阈值及 controlled UAT / human calibration 尚未建立。

因此，当前实现证明“系统具备被评测的 machinery 和安全直接纵向行为”，但不能证明“canonical Case 已运行并通过”，更不能推出 Phase complete、P0 complete 或 production ready。

## Dimension Coverage

本表按 canonical strategy 的七个质量维度评分。`COVERED` 表示实现存在、针对该 rubric 行为且有自动化或已记录的直接纵向运行证据；它**不等于** lifecycle Case `PASS`。`PARTIAL` 不计入 numerator。

| Dimension | Status | Measurement | Finding |
|-----------|--------|-------------|---------|
| `CORRECTNESS` | **COVERED** | Code + deterministic graders + direct vertical test | RU v2、accepted `InputBinding`、Task / ToolCall 状态、exact tool arguments 与确定性 renderer 均有 component / integration 证据；`E2E01-01` 直接纵向得到本人订单的受控结果。没有 lifecycle-valid Case Result。 |
| `GROUNDING` | **COVERED** | Code + Trace / persistence graders | 订单事实来自 owner-scoped PostgreSQL Observation 和 strict source version；exact-run closure、Observation provenance、renderer fact equality 与 foreign/nonexistent 零私有 Observation 均被验证。 |
| `SAFETY` | **COVERED** | Code + adversarial variants + direct HTTP test | 身份来自 server session、请求体身份字段被拒绝、业务查询按 trusted owner 限定、非本人/不存在外部行为等价、模型参数漂移在 Gateway 前拒绝、Trace / response 不暴露私有数据。 |
| `ROBUSTNESS` | **COVERED** | Fault injection + deterministic graders | Provider protocol、presentation protocol、stale-state / binding、atomic persistence、restart recovery、owner/run mismatch 与 artifact tamper 均 fail closed；失败不会伪造为普通 Case `FAIL`。 |
| `EFFICIENCY` | **PARTIAL** | Code / Trace counters | 当前切片有确定性模型/工具/重试预算与 Trace 计数约束，但没有 lifecycle Result 分布、重复运行策略、真实 baseline 对比或已裁决的 latency / token / cost 阈值。 |
| `UX` | **PARTIAL** | Deterministic projection tests | 成功结果与安全失败回复使用受控 projection / renderer，最小披露行为有自动化证据；尚无 controlled UAT、human rubric 结果或 model-judge / human calibration。 |
| `AUDITABILITY` | **COVERED** | Trace + persistence + replay graders | Trace completeness、状态变化、停止原因、toolset snapshot replay、exact owner-scoped reload 与 direct HTTP trace closure 均有证据；原始 session / 私有 payload 不进入普通可观察投影。 |

**Coverage Score:** 5/7 = 71.4%，报告取整为 **71/100**。

### Eval Layer Coverage

canonical strategy 要求 Component、Trajectory、E2E 三层最低覆盖。该轴单列，避免把“直接纵向测试存在”误记为 lifecycle Case 已通过。

| Layer | Status | Finding |
|-------|--------|---------|
| `COMPONENT` | **COVERED** | 13 个 grader、artifact/loader、双 Provider、Harness、RU / Gateway / persistence / renderer / recovery 等 component 与 integration tests 已运行并形成可复现证据。 |
| `TRAJECTORY` | **PARTIAL** | 真实 HTTP → Runtime → PostgreSQL 路径和 exact Trace closure 已被直接测试；但 authenticated cases 仍在 Harness dispatch 前因 lifecycle fail closed，没有 lifecycle-valid Trajectory Result。 |
| `E2E` | **MISSING** | 没有基于 canonical `EXECUTABLE` / `REGRESSION_GATE` artifacts 生成的 E2E `PASS / FAIL`、聚合报告或发布 Gate。direct composition evidence 不能替代此项。 |

## Infrastructure Audit

基础设施按 `ok = 1`、`partial = 0.5`、`missing = 0` 计分。

| Component | Status | Finding |
|-----------|--------|---------|
| Eval tooling（internal pytest + `OfflineEvalHarness`） | **Configured / ok** | 工具不是仅列为依赖：loader、Harness、grader、result/failure port 与双 Provider 均被 tests 和 real composition 调用。无 Ragas、LangSmith、Braintrust、Promptfoo 等外部 eval library；canonical strategy 也未要求本切片必须采用它们。 |
| Reference dataset | **Partial** | 5 个 versioned/authenticated artifact 文件存在，Phase dataset 含 6 个 Case，synthetic Alice/Bob、本人/非本人/不存在 sentinel、协议故障与绑定攻击的组合可加载且 hash 固定；但全部仍是 `CONTRACT_DEFINED`，未吸收实际失败为 regression set，也没有 human-label provenance、repeat policy 或完整 P0 15-family executable coverage。 |
| CI/CD integration | **Missing** | 仓库没有 GitHub Actions workflow、Makefile/Taskfile eval target 或其他持续 Eval gate；只有 canonical 本地 `uv run pytest` 与历史命令证据。 |
| Online guardrails | **Implemented / ok** | 当前请求路径中的 trusted session identity、owner-scoped read、Control Gateway argument binding、safe error mapping、minimal projection、deterministic renderer、persistence/Trace exclusion 均为确定性实现，并有 HTTP / component / integration tests。这里不声称已实现通用内容 moderation 或生产线上策略。 |
| Tracing（internal PostgreSQL Trace） | **Configured / ok** | Trace 包裹真实 direct AI/request path，记录关键决策、ToolCall、状态、失败和停止；owner-scoped exact-run reader、callback、replay 与 grader 均实际调用。未发现 Langfuse/LangSmith/Phoenix/Arize/Braintrust 等外部 observability 接入，也没有生产 monitoring。 |

**Infrastructure Score:** `(1 + 0.5 + 0 + 1 + 1) / 5 = 70/100`。

**Overall Score:** `(71.4 × 0.6) + (70 × 0.4) = 70.84`，取整为 **71/100**。

## Case and Critical-Failure Mapping

### Phase Case artifacts

| Case | Artifact lifecycle | Implementation evidence | Audit finding |
|------|--------------------|-------------------------|---------------|
| `E2E01-01` | `CONTRACT_DEFINED` | 本人明确订单的 direct HTTP → Runtime → PostgreSQL success、Observation、Trace 与 renderer evidence | 行为 machinery **COVERED**；lifecycle Result **MISSING** |
| `E2E01-04-A` | `CONTRACT_DEFINED` | 非本人订单归一化、零私有 Observation、safe observable | 行为 machinery **COVERED**；lifecycle Result **MISSING** |
| `E2E01-04-B` | `CONTRACT_DEFINED` | 不存在订单归一化；与 A 的 message / observable 等价 | 行为 machinery **COVERED**；lifecycle Result **MISSING** |
| `E2E01-01+SEC-ARGUMENT-BINDING` | `CONTRACT_DEFINED` | 当前 accepted binding 与 model candidate 不一致时 Gateway 前拒绝 | 行为 machinery **COVERED**；lifecycle Result **MISSING** |
| `E2E01-01+FAULT-PROVIDER-PROTOCOL` | `CONTRACT_DEFINED` | Provider V2 protocol failure 分区、bounded failure、零伪造结果 | 行为 machinery **COVERED**；lifecycle Result **MISSING** |
| `E2E01-01+FAULT-PRESENTATION-PROTOCOL` | `CONTRACT_DEFINED` | presentation failure 的状态推进、Trace 与 safe stop | 行为 machinery **COVERED**；lifecycle Result **MISSING** |

Coverage Matrix 的 `SEC-IDENTITY-OVERRIDE` 与 `SEC-PRIVATE-DATA-INJECTION` 已由 shared expectations、HTTP 422/session tests、E2E01-04 disclosure/Observation/Trace tests覆盖，但当前没有独立 activated Case Result。它们不能被宣布为 canonical Case `PASS`。

### Applicable critical failures

| Critical failure | Evidence mapping | Finding |
|------------------|------------------|---------|
| `CF-01` / `CF-02` | Identity boundary、owner-scoped lookup、disclosure grader、E2E01-04 pair | 确定性防线有证据；没有 lifecycle run 的 `G-CF` 结论 |
| `CF-03` / `CF-04` | Observation provenance、persistence、RU/InputBinding、exact-run closure | 确定性防线有证据；没有 lifecycle run 的 `G-CF` 结论 |
| `CF-10` | ToolCall / Observation / error mapping、协议故障分区 | 确定性防线有证据；没有 lifecycle run 的 `G-CF` 结论 |
| `CF-12` | Schema / Task / Trace / persistence / immutable toolset replay | 确定性防线有证据；没有 lifecycle run 的 `G-CF` 结论 |
| `CF-13` | Deterministic renderer、safe projection、disclosure grader | 确定性防线有证据；没有 lifecycle run 的 `G-CF` 结论 |
| `CF-14` | RU v2、InputBinding、Task state、Gateway、toolset snapshot | 确定性防线有证据；没有 lifecycle run 的 `G-CF` 结论 |

`CF-05` 至 `CF-09` 与 `CF-11` 属于 E2E-02 / RAG / side-effect action 后续范围；本报告不把尚未进入 Phase 1 的能力算作 Phase 1 实现缺陷。

## Critical Gaps

### Current quality-gate blockers

1. **CRITICAL — lifecycle-valid Trajectory / E2E Result 缺失。**

   Planned：canonical Case 在 owner 裁决后以 authenticated `EXECUTABLE` artifacts 经 Harness 运行，产出完整 Result / Failure、Trace 和 grader evidence。

   Found：全部 6 个 Phase cases 与 manifest/loader 都是 `CONTRACT_DEFINED`；Harness 正确地在派发前 fail closed，`results == ()`。

   To reach COVERED：先完成 Security 与 controlled UAT，再由 Coverage Matrix owner 作 lifecycle ruling；随后使用独立 Eval activation packet 原子同步 Case、manifest、loader 与 tests，在 exact integrated head 运行 deterministic lane 并保存 lifecycle-valid Results。

2. **CRITICAL — 持续 regression gate / CI integration 缺失。**

   Planned：实际失败进入 regression set，`REGRESSION_GATE` 对候选版本持续运行，并以 critical failure、质量、latency/cost 与 Trace 回归阻止对应发布范围。

   Found：无 CI workflow、持续 Eval command、聚合 regression report 或 `REGRESSION_GATE` Case。

   To reach COVERED：在 lifecycle-valid baseline 之后定义 canonical eval command/report schema，把 owner 批准的 regression cases 加入持续门禁，并验证失败确实阻断 release。

### Production / future blockers（不是本 Phase 的已发现代码 bug）

- canonical app-start 与生产请求路径尚未建立，因而没有 production monitoring、告警、drift / safety 指标或真实 retention 证据。
- 普通质量、latency、token、cost 阈值保持 `OPEN`；应基于 activated dataset 与 baseline 分布裁决，不能在本报告中编造。
- 真实 credentialed Qwen baseline 尚未执行。当前 Qwen lane `release_gate: false`，所以这是 baseline 信息缺口，不是 deterministic current gate 的替代品或当前 release blocker。
- E2E-02 的 RAG Evidence、确认、幂等、`create_refund` 模拟副作用及 `RESULT_UNKNOWN` 恢复不属于 Phase 1，不能以本报告评分宣称已覆盖。

## Remediation Plan

### Must fix before the current scope can claim lifecycle Eval coverage

1. 保持本报告只读派生状态，完成独立 Security audit；不得由 Eval report 自行修改 canonical Case lifecycle。
2. 使用不含 lifecycle route 的 controlled UAT adapter 验证 E2E01-01 与 E2E01-04 的用户可观察结果、最小披露和失败措辞，记录 human rubric 与发现。
3. 将 Eval review、Security、controlled UAT 与 exact-head 自动化证据提交 Coverage Matrix owner，由 owner 明确裁决目标 Case 是否从 `CONTRACT_DEFINED` 进入 `EXECUTABLE`。
4. 仅在 owner 批准后，新建独立 Eval activation Task Packet，原子同步 authenticated Case / manifest / loader / consistency tests；不得把 test-only executable bundle 复制成 canonical lifecycle 证据。
5. 在 exact activated head 运行 deterministic offline lane，持久化 lifecycle-valid Result / Failure、Trace、version manifest 与 grader outputs；生成可复核的 per-case 和 aggregate report。
6. 把实际失败加入 versioned regression dataset；经 owner 再裁决后进入 `REGRESSION_GATE`，接入持续命令/CI，并证明 critical failure 或回归会阻断对应 release。

该顺序固定为：**Eval review → Security → controlled UAT → Coverage Matrix owner lifecycle ruling → independent Eval activation packet → lifecycle-valid results / regression gate**。

### Should fix soon

- 为 `UX` 增加 controlled human rubric、最小披露/可操作下一步评分与 grader calibration。
- 为 `EFFICIENCY` 在 activated runs 上记录 model/tool/retry count、latency、usage/cost 分布；先跑 baseline，再裁决普通阈值和 repeat policy。
- 在批准的安全环境中单独运行 credentialed Qwen baseline，保留固定 model snapshot、版本、usage 与 scrubbed failure evidence；它不得替代 deterministic release gate。
- 明确 Eval command 与 report 的 canonical owner、失败退出码、artifact retention 和 secret/PII policy。

### Nice to have

- 产品启动和真实流量存在后，再选择符合数据最小化约束的 observability / monitoring 方案；当前没有必要为了工具名引入外部平台。
- 后续 E2E-01 扩展与 E2E-02 实施时，按 canonical owners 增加 retrieval/evidence、action safety、恢复和 failure-regression cases。

## Files Found

### Versioned dataset / config

- `evals/cases/e2e01-thin-slice.v1.json`
- `evals/fixtures/e2e01-thin-slice.v1.json`
- `evals/lanes/e2e01-thin-slice.v1.json`
- `evals/manifests/e2e01-thin-slice.v1.json`
- `evals/model_scripts/e2e01-thin-slice.v1.json`

### Eval implementation

- `src/mini_agent/evaluation/artifacts.py`
- `src/mini_agent/evaluation/graders.py`
- `src/mini_agent/evaluation/harness.py`
- `src/mini_agent/evaluation/scripted_provider.py`
- `src/mini_agent/bootstrap.py`

### Eval / direct vertical tests

- `tests/component/evaluation/test_e2e01_artifact_consistency.py`
- `tests/component/evaluation/test_e2e01_graders.py`
- `tests/component/evaluation/test_e2e01_scripted_model_provider.py`
- `tests/component/evaluation/test_e2e01_versioned_artifact_loader.py`
- `tests/integration/evaluation/test_e2e01_offline_harness.py`
- `tests/e2e/test_e2e01_http_eval.py`
- `tests/baseline/test_qwen_baseline.py`

### Scan results

- Eval/test files：found，如上及相关 application/core/infrastructure tests。
- Tracing/observability platform：未发现 Langfuse、LangSmith、Arize、Phoenix、Braintrust 或 Promptfoo；发现并验证项目内部 PostgreSQL Trace 实现。
- External eval-library imports：未发现 Ragas、LangSmith 或 Braintrust import；项目使用内部 deterministic grader / Harness。
- Guardrail keyword scan：没有依赖通用 `guardrail`/`moderation` 命名；请求路径中的 trusted identity、Gateway、safe projection、renderer 和 persistence exclusion 通过具体模块与测试确认。
- Eval config/reference data：发现 5 个 versioned JSON artifacts；未发现 `promptfoo.yaml` 或独立外部 eval config。
- CI：`.github/` 只有 PR template，未发现 workflow；未发现 Makefile/Taskfile/justfile eval target。

## Evidence and Non-Claims

本审计读取了 Phase 目录全部 **49 份 PLAN.md artifacts** 与 **24 份 SUMMARY.md**，并对照 `01-W2-VALIDATION.md`、post-remediation `01-REVIEW.md`、canonical Eval owners、业务 owner、scoped implementation spec 和当前源码/测试。49 Plans 中的 task-level automated feedback 与 42/42 implementation targets green，不等于 Case lifecycle 或 Requirement 完成。

本次未重跑完整 2004-test suite，也未调用外部 Qwen；完整套件、1787 focused 和 missing-env Qwen 数字均明确作为 Phase Validation 已记录证据引用，而不是本审计新产生的命令结果。

本报告不宣称：

- Phase 1、Requirement 或 P0 已完成；
- Case 已从 `CONTRACT_DEFINED` 激活；
- 任何 canonical Case 已取得 `PASS / FAIL`；
- 真实 credentialed Qwen baseline 已运行；
- canonical app-start、回归 Gate、monitoring 或 production readiness 已存在；
- E2E-02、RAG 或 `create_refund` 安全动作已被 Phase 1 覆盖。
