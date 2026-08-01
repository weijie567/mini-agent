# Mini Agent｜GSD 派生执行上下文

> **DERIVED / NON_NORMATIVE**
> 本文件只为 GSD 提供精简执行上下文，不拥有产品、架构、契约、Eval 语义或实时实现事实。任何冲突都以 [AGENTS.md](../AGENTS.md) 列出的对应 canonical owner 为准；专门 owner 只在自身范围内优先，绝不采用 “newest wins”。

## What This Is

这是既有 Mini Agent P0 仓库的 GSD 派生执行上下文，只索引 canonical owner 已定义的目标、约束与证据。产品本身是什么、面向谁以及验收语义仍由下列 active owner 定义，本文件不另建项目定义。

## 权威来源

- P0 业务范围与两条 E2E：[业务能力说明](../docs/business-capabilities.md)。
- P0 架构方向：[PROJECT_DIRECTION.md](../PROJECT_DIRECTION.md)。
- Eval 方法与 Case 激活顺序：[Agent Evaluation Strategy](../docs/evaluation/agent-evaluation-strategy.md) 与 [P0 Eval Coverage Matrix](../docs/evaluation/p0-eval-coverage-matrix.md)。
- 第一最薄切片契约：[E2E-01 Thin Slice Implementation Spec](../docs/implementation/e2e01-thin-slice-implementation-spec.md)。
- Cycle 2 scoped 契约：[E2E-01 Cycle 2 Implementation Spec](../docs/implementation/e2e01-cycle2-implementation-spec.md)。
- Phase 1 已完成的 historical Task Packet、ownership 与集成顺序：[Codex 多 Agent 实施计划](../docs/implementation/e2e01-thin-slice-multi-agent-plan.md)。
- Phase 2 当前 Task Packet：W1–W3R、W4 `02-06/02-13/02-08` 与 `02-09R1` 已
  reviewed merge。当前 integration / `B_C2_RECOVERY_CORE =
  fe627a5d81d909e096e9e60773fcca03b51f84be`，tree
  `42767c8535dbc05837ab9dabeee2c1432813e0fb`。02-09 source 仍保持 clean/blocked；
  当前只从该真实 R1 successor冻结并审阅 exact `02-09R2` Plan。`02-09R3` 与
  refrozen `02-09` 必须分别等待前驱真实 merge SHA/tree，不得预填未来 barrier；
  writer 上限仍为 2。
  `integration/e2e01-cycle2` 已启用 PR-required、enforce-admins、linear-history、
  conversation-resolution 保护，并禁用 force-push / deletion；dispatch 与 merge 前
  仍须从 GitHub API 机械复核。
- GSD 派生层治理：[GOVERNANCE.md](GOVERNANCE.md)；激活证据：[ACTIVATION.md](ACTIVATION.md)。

## Core Value

在不制造第二套项目定义的前提下，把 canonical owner 已定义的 P0 目标转成可隔离、可审查、可验证、可追溯的执行阶段。

## Requirements

### Completed

- [x] [REQUIREMENTS.md](REQUIREMENTS.md) 映射的 Phase 1 release transition已完成：`E2E01-01/04`实现与quality evidence完整，用户继续接受有界`RTA-D01`，reviewed PR #199已squash merge到`main`（`f15320e3...`）。

### Active Contract / Planned Execution

- Phase 2 scoped implementation owner 已激活为 `CONTRACT_ACTIVE / READY_FOR_PLANNING`；
  master Plan 已由 PR #203 批准并合并；PR #204 合并 `02-00` planning provenance，
  PR #205 完成零代码 path correction 并形成 exact `B_C2_OWNER_ALIGNED`。PR #207 /
  #208 已 reviewed 串行合入并形成历史 `B_C2_W1A`；PR #212/#213 已依次完成
  full-gate repair 与 `02-02` exact Packet refreeze，PR #214 完成四状态文件 alignment，
  PR #215 完成 02-02 r2 implementation / review / overlay merge。PR #216/#217 又完成
  W2 planning、02-04 implementation、feature/overlay review 与串行 merge，冻结
  `B_C2_TOOL = f9a2a75...`。PR #218/#219 随后完成 02-05 planning、implementation、
  feature/overlay review 与串行 merge，冻结 `B_C2_APP_CONTRACT = 86d1b835...`；旧
  `ecfad7e...` 实现 head 保持 quarantined。02-02R/02-04R/02-05R 已reviewed完成；
  PR #227 形成真实`B_C2_W4_READY = 5f2fa6d...`。W4 planning PR #228 与
  implementation PR #229/#230/#232 已依次形成 `B_C2_CODEC`、`B_C2_EVAL_BUNDLE` 与
  `B_C2_RU_ROUTING`；owner-ruling PR #231 关闭 02-09 recovery contract 冲突，
  R1 planning/implementation PR #233/#234 又形成 `B_C2_RECOVERY_CORE = fe627a5d...`。
  02-09 old Plan 已 fail-closed blocked，当前只允许 `02-09R2` planning provenance。
- Phase 3–6 仍只保留 Case ID / Cycle mapping；对应 scoped implementation owner 出现前不生成实现细节。

### Out of Scope

- `.planning/` 不重新定义业务、架构、契约、Eval 或 Case lifecycle。
- GSD workflow 不绕过 Task Packet、Worktree、PR、review 或 canonical verification gate。

## 当前执行边界

- 01-07I/P形成`B_IP = bbe14fadc0cd2e14ad35e19177b079fcab685dfc`后，01-07K/L经PR #94–#98串行形成`B_DEPENDENCY = e54a6a4d77208695440c2caf03c3ab32f9d37108`；01-07M经PR #99–#101形成`B_DEPENDENCY_M = 42fa2ec7ef1a61a2edfd78d69ca4e6a5d32aa1c3`；Q oracle remediation与Plan/feature PR #102–#106形成`B_Q = 2b9fde6f0e09308a53b86a4929ea3b639660f82e`。Execution-owner r2 PR #107把Y/Z/AA纳入唯一map并把目标分母修正为42；Y/Z PR #108–#111形成`B_YZ = d704b87480f0a4252744f4c009cef9a86c08fa05`，AA及其quality-gate remediation PR #112–#120形成`B_J_READY = b8d32d50775a0d3f4a0d3e7e609c717f6c540b33`。J Plan、exact-reader scope alignment与Runtime feature PR #121–#124最终形成scoped `B_ACTIVE = 7f92b5e0a05714a6a9d7325861499d7cc0bf04dd`、tree `f70b20215e569acf3ad196cc050e9a23700d4bae`。
- Activation feature base：`85eb2a7fc4cc131e67e44dbba132b526e36ae6a3`；reviewed feature head：`957cabd6b31dd2156848acd515d2e8dc3d19bd50`；effective integration merge：`624475681847be5a8e463e32dafd28a0483b213b`。
- Phase 1 / Coverage Matrix Cycle 1 的 `E2E01-01/04`已完成scoped release transition；Phase 2 scoped contract 以 owner-alignment merge `9ee260f12a82b706269f8a62c460c781c64f1f47` 为精确 base，经独立 Activation 激活为 `READY_FOR_PLANNING`。Gate P2-A planning PR #203 已形成 `B_C2_PLAN_APPROVED = 2879f5226a073051d1550fe079b4a427c1ec8cb1`；这只授权 Gate P2-B planning，不实现 Phase。
- Phase 2 `02-00` 已按用户批准执行：planning PR #204 merge successor 为
  `74db04a938f725f1e4bbf113b23de613dbbb433e`，zero-code owner correction PR #205
  merge successor / `B_C2_OWNER_ALIGNED` 为
  `4dc6dc95de81080fb3b651bc2f0026fb046fd9f8`，tree
  `521ac2c7611b20683089ab41a74d07c9a2bb8fc7`。`C2-BLOCK-02` 已关闭；
  `integration/e2e01-cycle2` 已创建并冻结等值 `B_C2_START`，随后形成
  `B_C2_TRACE = 985564d...` 与历史 `B_C2_W1A = b5de7f4...`。PR #212 reviewed
  merge 形成当前产品实现 base `B_C2_W1_GATE_REPAIRED = 015c1e8...`、tree
  `26b71d2...`；PR #213 reviewed merge `fedd2d1...` 只推进 refreeze planning
  provenance，不替换该 repaired product base。PR #214 status alignment merge
  `2aec3663...` 后，PR #215 reviewed merge 形成当前 W1 barrier
  `B_C2_CORE_123 = 241cf6b83761f5d91da5de7719f26838e2626e26`、tree
  `83fcbf90770ffdc30ef37e35e94169bcb9ead3b3`；canonical full 为
  `2340 passed, 1 deselected, 12 warnings`。PR #216 的 W2 planning provenance 合入后，
  PR #217 的 feature exact head 与 latest-integration overlay 均独立 review `PASS`，
  merge successor / 当前 W3 product base 为
  `B_C2_TOOL = f9a2a75135ba63347e81e13f2b981cf550977875`、tree
  `59afeccec3705b7bae754c00b012f669a049a9ac`，canonical full 为
  `2499 passed, 1 deselected, 12 warnings`。
- Plan 01-01、01-02 与 01-03 已分别通过 planning / owner PR、181 个 serial tests 与独立 exact-head review完成 evidence index；Plan 01-04 已通过 planning PR #18、feature PR #19、134 个 focused / 315 个 full tests、两路 final exact-head review 与 Graphify code + semantic freshness gate；Packet 01-04D 已通过 planning PR #20、feature PR #21、210 个 focused / 344 个 full tests、两路 final exact-head review 与 post-merge Graphify gate。五个已完成 Packet 都不改变 `E2E01-01/04` lifecycle。
- 01-04E/F/G/H owner Packet已依序通过PR #23/#24/#25/#32合并；01-05R通过PR #33/#34 merge `fb607019...`，01-06R通过PR #35/#36 merge `8e21652...`，01-07 PR #29在latest-integration overlay复验后merge `eee1c0e...`。01-07A planning/Runtime PR #37/#38又merge为`4cfac0a...`；Business、Eval、项目规则状态PR #39–#41随后形成01-07B execution base。01-07B planning/status PR #42–#43与feature PR #44已reviewed merge为`ccdafe87...`；这些历史证据已由后续42/42实现与post-execution gates supersede。
- 当前 immediate gate：全部42个implementation targets已完成；01-07S/U/X/T/W/V形成`B_RU_V2_CONTRACT = 5c84e0e...`，01-08 / Composition handoff / 01-08A依序形成`B_01_08 = b8a2cf3...`、`B_01_08A_COMPOSITION = c59eaea...`与`B_01_08A = 11d6d08...`。PR #172–#186完成review / fix、Validation、controlled UAT、Eval activation / Results / regression gate与mandatory Eval / Security re-review。真实credentialed Qwen Baseline、canonical产品启动和production readiness仍未完成，但它们不是当前scoped deterministic offline release的未完成Task Packet。
- 当前 Case lifecycle仍由Coverage Matrix拥有；其已将六个authenticated physical Case推进为`REGRESSION_GATE`。本derived文件只同步该状态，不自行裁决；默认离线链为`16 PASS / 0 FAIL / 0 Critical failure / 0 execution failure`，canonical full为`2007 passed, 1 deselected, 12 warnings`。
- Phase 1 release closure已完成：用户继续接受`RTA-D01`有界availability residual risk，reviewed integration → `main` PR #199已squash merge为`f15320e3c98a408727b1488db5a5c7f0a7a57931`。Phase 2 已完成 W1–W3R；W4 的 02-06/13/08 与 recovery R1 也已 reviewed merge，当前 integration 为 `B_C2_RECOVERY_CORE = fe627a5...`。02-09 因 shared recovery gap 保持 clean/blocked，PR #231 已裁决三个 single-writer correction，当前处于 `02-09R2` exact Plan review。Case仍为`CONTRACT_DEFINED`；canonical full延至W6，Phase末全面深审延至W12。Phase 3–6仍需各自scoped owner与activation。Graphify只作导航且不作为当前barrier或实现证据。

## 不属于 GSD 派生层的事项

- 不重新定义 P0 用户、业务目标、Tool Catalog、Mock 系统或安全不变量。
- 不重新定义 Core / Application DTO、Port、状态机、Evidence、Action Ledger 或 Eval 语义。
- 不以 `$gsd-new-project` 或 `$gsd-new-milestone` 重建当前 P0。
- 不让 GSD executor 直接写 `main`、任何 phase-specific integration branch
  （Phase 1 历史 `integration/e2e01-thin`、Phase 2 reserved
  `integration/e2e01-cycle2`）或共享 `.planning/STATE.md`。
- 不运行 stock `$gsd-execute-phase`、`phase.complete`、`requirements.mark-complete`、`roadmap.update-plan-progress` 或 `$gsd-ship`；实现、生命周期同步与两级 PR 均由 Integrator 按 [GOVERNANCE.md](GOVERNANCE.md) 显式控制。
- 不把计划、Review、UAT 或 GSD 报告自身当作“已实现 / 已通过”的充分证据。

## 执行决策

| 决策 | 理由 | 状态 |
|---|---|---|
| GSD 是派生编排层，canonical owner 保持不变 | 防止 `.planning/` 成为第二套产品 / 架构 / Eval 语义 | `CONFIRMED` |
| `git.branching_strategy=none` | 分支与 Worktree 继续由精确 Task Packet 和 GitHub PR 流程拥有 | `CONFIRMED` |
| `parallelization=false`、`workflow.use_worktrees=false` | 只关闭 GSD 自管并行 / Worktree；Codex Agent 仍在 Integrator 预建 Worktree 中并行 | `CONFIRMED` |
| 共享 Roadmap / State 由 Integrator 单写 | 避免多个 feature branch 推进相互冲突的执行状态 | `CONFIRMED` |
| 当前 P0 不运行 `new-project` / `new-milestone` / `autonomous` | 既有项目已有明确 owner、Spec 与执行基线 | `CONFIRMED` |
| 一个 GSD Plan 对应一个精确 Task Packet | Packet 可以含多个原子 task，但不能跨 repository、branch、Worktree、writer 或 ownership boundary | `CONFIRMED` |
| 持久化投影写入前经 Pydantic serialization，并保存 schema version | 这是 Thin Slice Spec 当前可确认的 scoped 要求 | `CONFIRMED` |
| Persistence 四轴 ownership、版本维度与 Trace shared-structure authority | 已由 Plan 01-01 / PR #12 写入 `PROJECT_DIRECTION.md`；不表示 decoder、registry、业务表或 migration 已实现 | `CONFIRMED / CONTRACT_ONLY` |
| P0 exact-version、decode / recovery / migration runtime 行为 | 已由 Plan 01-02 / PR #14 写入 Memory owner；不表示 codec、Adapter、业务表或 recovery 已实现 | `CONFIRMED / CONTRACT_ONLY` |
| Thin Slice 17-item item code、版本、projection 与实现 API | 已由 Plan 01-03 / PR #16 与 clarification PR #17 写入 Thin Slice scoped owner；不得从测试 fixture 或 Python 类名动态推断 | `CONFIRMED / CONTRACT_ONLY` |
| 01-04 Application logical persistence codec | PR #19 已合并；17-item registry、strict codec 与 Component tests 已实现；不拥有授权、complete graph、physical persistence 或 migration | `COMPLETE / EVIDENCE_INDEXED` |
| 01-04D Application persistence write / recovery Port closure | PR #21 已合并；relation-aware write、原子 initial/transition/Run finalization 与 fenced complete-graph claim boundary已有 Application contract和契约测试证据 | `COMPLETE / EVIDENCE_INDEXED` |
| 01-04E Memory token availability | 保持 required `TokenCounts` object；每个方向可为 strict `int \| None`，`None`表示未精确测量，禁止coercion、0占位或估算伪造 evidence | `COMPLETE / EVIDENCE_INDEXED / PR #23` |
| 01-04F Thin Slice / Eval fault alignment | stale-state变体以canonical Port执行`ACTIVE/v1 → WAITING_USER/v2` race，再由Gateway拒绝并推进`BLOCKED/v3`；fact-bearing raw presentation映射为 Provider protocol failure | `COMPLETE / EVIDENCE_INDEXED / PR #24` |
| 01-04G recovery Trace atomicity | Application command携带Core-produced exact recovery Trace；Port contract要求compliant Adapter将APPLIED state/link/Trace同事务并拒绝跨类型payload污染 | `COMPLETE / EVIDENCE_INDEXED / PR #25` |
| 01-04H terminal-turn contract | planning PR #31 + owner PR #32；reviewed head `c0306ef...`、merge `64992cf...`、269 focused / 560 full与post-merge Graphify gate | `COMPLETE / EVIDENCE_INDEXED` |
| 01-05R Runtime replacement | planning PR #33 + Runtime PR #34；reviewed head `05f0182...`、merge `fb607019...`、100 focused / 660 full、38 migration与post-merge Graphify gate | `COMPLETE / EVIDENCE_INDEXED` |
| 01-06R Infra replacement | planning PR #35 + Infra PR #36；reviewed head `377f837...`、merge `8e21652...`、83 focused / 40 migration / 745 full与post-merge Graphify gate | `COMPLETE / EVIDENCE_INDEXED` |
| 01-07 Eval | PR #29 head `b8ecbb0...`经post-Infra overlay `ee46f38...`复验并merge `eee1c0e...`；191 focused / 40 migration / 936 full（1 deselected）、双preflight与Graphify gate | `COMPLETE / EVIDENCE_INDEXED` |
| 01-07A Runtime Trace alignment | planning PR #37、Runtime PR #38；merge `4cfac0a...`；100 Runtime focused / 40 migration / 936 full（1 deselected）、双路feature/overlay review与Graphify gate | `COMPLETE / EVIDENCE_INDEXED` |
| 01-07B Eval evidence boundary | exact base `8544137...`；PR #44 merge `ccdafe87...`；six-file Eval ownership关闭Case/Script/nested/output-side oracle、one-time correlation、canonical boundary与variant-scoped safety-causal Trace precedence；[Summary](phases/01-cycle-1-e2e-01/01-07B-SUMMARY.md) | `COMPLETE / EVIDENCE_INDEXED` |
| 01-07C RU semantic ruling | [Plan](phases/01-cycle-1-e2e-01/01-07C-PLAN.md)固定base `3f0753f7...`与Intent owner单文件ownership；PR #51 blocked证据保留，r1 Plan PR #52与owner PR #53关闭findings并merge为共同barrier`327b39d...`；[Summary](phases/01-cycle-1-e2e-01/01-07C-SUMMARY.md) | `COMPLETE / EVIDENCE_INDEXED` |
| 01-07D Thin Slice RU exact mapping | [Plan](phases/01-cycle-1-e2e-01/01-07D-PLAN.md)与[Summary](phases/01-cycle-1-e2e-01/01-07D-SUMMARY.md)索引PR #56/#59、exact one-file mapping、review与merge `5f793fd...` | `COMPLETE / EVIDENCE_INDEXED` |
| 01-07E Application persistence codec | [Plan](phases/01-cycle-1-e2e-01/01-07E-PLAN.md)与[Summary](phases/01-cycle-1-e2e-01/01-07E-SUMMARY.md)索引PR #72/#73/#74、exact two-file codec expand、review与共同 `B_FE_EXPAND` | `COMPLETE / EVIDENCE_INDEXED` |
| 01-07F RU Core implementation | [Plan](phases/01-cycle-1-e2e-01/01-07F-PLAN.md)与[Summary](phases/01-cycle-1-e2e-01/01-07F-SUMMARY.md)索引PR #70/#71、exact six-file Core expand、review与 `B_F` | `COMPLETE / EVIDENCE_INDEXED` |
| 01-07G Thin Slice `get_order` source-version ruling | [Plan](phases/01-cycle-1-e2e-01/01-07G-PLAN.md)固定base `3f0753f7...`与Thin Slice owner单文件ownership；owner PR #50定义server-private content version唯一authority/算法、fixed vectors、FOUND必填、Observation/Manifest exact copy与禁止schema fallback并merge；[Summary](phases/01-cycle-1-e2e-01/01-07G-SUMMARY.md) | `COMPLETE / EVIDENCE_INDEXED` |
| 01-07H Core/Order DTO additive expand | [Plan](phases/01-cycle-1-e2e-01/01-07H-PLAN.md)与[Summary](phases/01-cycle-1-e2e-01/01-07H-SUMMARY.md)索引PR #57/#60、RED→GREEN、review与共同 `B_DH` | `COMPLETE / EVIDENCE_INDEXED` |
| 01-07N RU v2 cutover remediation | [Plan](phases/01-cycle-1-e2e-01/01-07N-PLAN.md)与[Summary](phases/01-cycle-1-e2e-01/01-07N-SUMMARY.md)索引PR #62/#63；只冻结 `p0-ru-v2-cutover-r1`，不实现Core、codec、migration或routing | `COMPLETE / EVIDENCE_INDEXED` |
| 01-07O execution-map alignment | [Plan](phases/01-cycle-1-e2e-01/01-07O-PLAN.md)与[Summary](phases/01-cycle-1-e2e-01/01-07O-SUMMARY.md)索引PR #64/#65及PR #66计数校正；唯一map已落盘 | `COMPLETE / EVIDENCE_INDEXED` |
| 01-07I / 01-07P dependency expand | [I Plan](phases/01-cycle-1-e2e-01/01-07I-PLAN.md) / [Summary](phases/01-cycle-1-e2e-01/01-07I-SUMMARY.md)与[P Plan](phases/01-cycle-1-e2e-01/01-07P-PLAN.md) / [Summary](phases/01-cycle-1-e2e-01/01-07P-SUMMARY.md)索引PR #80–#87、review remediation、exact tests与共同 `B_IP` | `COMPLETE / EVIDENCE_INDEXED` |
| 01-07K / 01-07L dependency consumers | Plan/feature/security amendment PR #94–#98；strict PostgreSQL reader、authoritative order producer、Eval mapper与v2 Provider consumers reviewed串行merge | `COMPLETE / B_DEPENDENCY = e54a6a4...` |
| 01-07M Core source-version contract closure | Plan/shell correction/feature PR #99–#101从exact`B_DEPENDENCY`收紧`GetOrderResult.FOUND`合同 | `COMPLETE / B_DEPENDENCY_M = 42fa2ec...` |
| 01-07Q Application codec active switch | Oracle remediation与Plan/category/feature PR #102–#106切换public active RU codec mapping并保留v1隔离面 | `COMPLETE / B_Q = 2b9fde6...` |
| 01-07Y / 01-07Z / 01-07AA J prerequisites | Execution-map r2与PR #108–#120增加v2 reducer、Application write contracts、PostgreSQL atomic writers及quality-gate remediation | `COMPLETE / B_J_READY = b8d32d5...` |
| 01-07J Runtime v2 active switch | Plan、exact-reader scope alignment与feature PR #121–#124；双独立review、merge-tree equality与post-merge full gate通过 | `COMPLETE / SCOPED B_ACTIVE = 7f92b5e...` |
| 01-07S/U/X/T/W/V v1 contract closure | 依唯一map按`{S,U} → X → T → W → V`删除各owner v1 surface，V最后执行 | `COMPLETE / B_RU_V2_CONTRACT = 5c84e0e...` |
| 01-08 vertical integration | Integrator装配真实HTTP→Runtime→PostgreSQL→Eval离线链 | `COMPLETE / B_01_08 = b8a2cf3...` |
| 01-08A credential-aware Qwen runner | runner与zero-network missing-env路径已完成；真实credentialed运行需要外部配置 | `COMPLETE / B_01_08A = 11d6d08... / REAL_QWEN_NOT_RUN` |
| Post-execution quality | review / fix、Validation、controlled UAT、Eval/Security re-review、regression gate与release transition | `COMPLETE / RELEASED_TO_MAIN` |

## 完成证据规则

阶段完成必须同时具备适用的源码、测试 / migration / Eval 输出、文件 allowlist 检查、GitHub exact-head review 与 PR 记录。GSD 状态只索引这些证据，不取代这些证据。
