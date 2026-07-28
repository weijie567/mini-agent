# Mini Agent｜P0 GSD 派生执行 Roadmap

> **DERIVED / NON_NORMATIVE**
> 本 Roadmap 只派生执行顺序，不拥有产品、架构、契约、Eval 语义或 Case 生命周期。来源是 [P0 Eval Coverage Matrix](../docs/evaluation/p0-eval-coverage-matrix.md)、[业务能力说明](../docs/business-capabilities.md)、[第一最薄切片 Spec](../docs/implementation/e2e01-thin-slice-implementation-spec.md) 与[多 Agent 实施计划](../docs/implementation/e2e01-thin-slice-multi-agent-plan.md)。专门 owner 只在自身范围内优先，绝不采用 “newest wins”。

## Lifecycle Control

- 一个 GSD Plan 对应一个精确 Task Packet。Packet 可含多个原子 task，但不得跨 repository、branch、Worktree、writer 或 ownership boundary。
- Stock `roadmap.update-plan-progress`、`requirements.mark-complete`、`phase.complete` 与任何 transition / auto lifecycle mutation 当前禁用。
- Stock `gsd-import`、`gsd-plan-phase` 与 `gsd-verify-work` 当前也禁用：前两者会在 artifact 生成路径中写共享 State，后者没有 `--no-transition` 模式并会调用 `phase.complete`。后续 Plan 与 UAT 使用受控、无 lifecycle mutation 的项目适配流程。
- Checkbox 和 Progress 只由 Integrator 在 Summary、PR、机械证据、post-execution quality gate 与 canonical lifecycle owner 更新完成后手工同步。
- `parallelization=false` 与 `workflow.use_worktrees=false` 只禁用 GSD 自管并行 / Worktree；Codex 多 Agent 仍使用 Integrator 在 workflow 外预建的独立 Worktree / feature branch。

## Overview

P0 依照 Coverage Matrix 的 Cycle 1–4 分成六个连续 Phase。Activation 已通过 [PR #10](https://github.com/weijie567/mini-agent/pull/10) 生效，只有 Phase 1 active；Phase 2–6 在对应 scoped canonical contract 出现并通过冲突审查前，只保留 Case ID 与 gate mapping，不生成实现 Plan。

## 🚧 **v0.1 GSD-only P0 execution**

> `v0.1` 只是 GSD 1.38.3 parser 使用的派生 execution milestone 标识，不是产品版本、发布承诺或 canonical milestone。产品范围与生命周期仍由 active owners 拥有。

## Phases

- [ ] **Phase 1: Cycle 1｜第一最薄 E2E-01** — 使 `E2E01-01/04` 从已定义契约走到可复现纵向证据。
- [ ] **Phase 2: Cycle 2｜完成 E2E-01** — 覆盖 `E2E01-02/03/05/06` 与真实按需物流工具选择。
- [ ] **Phase 3: Cycle 3a｜RAG、Evidence 与资格判断** — 通过 `G-RAG-INFRA` 并覆盖 `E2E02-01/02/03`。
- [ ] **Phase 4: Cycle 3b｜受控模拟退款动作** — 覆盖 `E2E02-04/05/06` 的确认、ActionPolicy 与幂等。
- [ ] **Phase 5: Cycle 3c｜未知结果与跨会话恢复** — 覆盖 `E2E02-07/08`。
- [ ] **Phase 6: Cycle 4｜跨场景贯通与 P0 Release Audit** — 覆盖 `CROSS-01` 并审计 P0 发布证据。

## Phase Details

### Phase 1: Cycle 1｜第一最薄 E2E-01

**Status**: `ACTIVE / 01-07D_01-07H_FEATURE_COMPLETE / 01-07E_01-07F_PLANNING_NEXT`

**Goal**: 为 canonical `E2E01-01/04` 取得可复现的源码、HTTP、Trace、结构化 Eval 与安全门禁证据。

**Depends on**: W1 骨架、W2.0 persistence contract freeze、activation final exact-head `PASS` / merge、Plan 01-01 Project Direction owner merge `c96dea9f9f798212227cd05ff2a7b1f029a60287`、Plan 01-02 Memory owner merge `af5afd2c93d429e1b090bfaf7af22c0fc4ec3c7b`、Plan 01-03 mapping / clarification chain `9632c18532baa2f4cd6ab7526d0e6db30328ea65` → `9602fc18148b19c841889a8041daf10ccc5b8f1c`、Plan 01-04 persistence codec merge `bde99edec0bbb9ba331c6099c8b467c14fe24e58`、Packet 01-04D Application Port closure merge `a84d30188eaec75e45619e9939180ba78efa3b80`、Packet 01-04E Memory token availability merge `be68490b9d8440a29a43fa8143e9dd5d4bcbfeda`、Packet 01-04F Thin Slice / Eval fault alignment merge `1d47fae3c2a3b910d92acb4713f2015199f54d49`、Packet 01-04G recovery Trace atomicity merge `c35687dafa3881bb322d91515068d8d39be79df6`、Packet 01-04H normal terminal-turn atomicity merge `64992cf3bdc6205e00d0c36433309b1657a57531`、Packet 01-05R Runtime merge `fb607019130843c94825a47d7822518cbdb2143c`、Packet 01-06R Infra merge `8e21652fbfcba4e9efb351e298b9a0c58f4a46d8`、Plan 01-07 Eval merge `eee1c0e46e1bca1160dea54d586d477c173daadc`、Packet 01-07A Runtime Trace alignment merge `4cfac0a4ccfac6b75afa565f6010f7b1544abd7a`、Business / Eval / project-rule status alignment merge chain `b46a967...` → `d15f8db...` → 01-07B execution base `8544137cfbcaebda603cd3000312fb5d2406327c`、01-07B feature merge `ccdafe87d5f118b729d6f3fff8635a0b92f3e3c5`、01-07C/01-07G共同barrier `327b39da45cdcf564609a5385d52c4264da2c669`、01-07D / 01-07H Plan merge `5d72cb70bf5dc97ae2f74ab1697a61e77a23b725` / `e6c8cbaf782ac64e0fced492b9b552f246d0e940`，以及D/H reviewed feature PR #59/#60串行merge形成的共同barrier `B_DH = 4a7e802e8aebc54e0582a1e4d99f140b56e7b131` / tree `a5a60292ccdf116aba4dacaaea366576e183c532`（均已满足；`B_DH`是01-07E/F唯一planning input，不代表E/F已签发或实现）。

**Requirements**: [E2E01-01, E2E01-04]

**Success Criteria**:

1. `E2E01-01` 的 canonical acceptance criteria 具有可复现 Component、Trajectory 与 HTTP E2E 证据。
2. `E2E01-04` 两个变体具有 canonical owner 要求的安全等价与禁止披露证据。
3. 适用 Critical failure 为零，结构化 Eval Result、Trace 与版本 manifest 可追溯；缺失证据不得以 GSD 状态代替。
4. Exact integration head 通过 canonical 命令、独立 review、validation、适用的 Eval / Security audit 与 UAT。

**Plans**: 当前磁盘正式签发20个Plan（7个numbered + 11个inserted dependency Packets `01-04D`–`01-04H` / `01-07A` / `01-07B` / `01-07C` / `01-07D` / `01-07G` / `01-07H` + 2个replacement `01-05R/01-06R`），并有18份Summary。01-07D / 01-07H均从`B_CG = 327b39da45cdcf564609a5385d52c4264da2c669`执行且allowlist交集为0；D [PR #59](https://github.com/weijie567/mini-agent/pull/59)先reviewed merge `5f793fd9aa667073c0a465383459fefb979d09c4`，H [PR #60](https://github.com/weijie567/mini-agent/pull/60)再于D latest-integration overlay上取得independent `0/0/0/0`并merge `4a7e802e8aebc54e0582a1e4d99f140b56e7b131`，形成`B_DH` / tree `a5a60292ccdf116aba4dacaaea366576e183c532`。证据见[01-07D Summary](phases/01-cycle-1-e2e-01/01-07D-SUMMARY.md)与[01-07H Summary](phases/01-cycle-1-e2e-01/01-07H-SUMMARY.md)；combined canonical full为`1507 passed, 1 deselected, 12 warnings`。目标Packet完成口径为`18/29`，numbered Plan evidence仍为`7/8`，canonical lifecycle与Requirements checkbox仍为`0/8`。01-07E/F的planning prerequisite现已满足，但两份Plan尚未签发且实现未开始；它们必须分别从`B_DH`签发并保持Application codec / RU Core ownership分离。H继续保持additive与legacy `FOUND + None`，J fail closed，K produce，M closure。当前Graphify仍绑定`b656103...`；本状态merge后的code update与semantic refresh仍是Integrator gate。若后续owner裁决要求其他migration、全局Memory version升级或新的外部契约，必须继续插入新Packet并更新分母，不得扩大既有allowlist。

Plans:

- [ ] 01-01: Project Direction persistence ownership / Trace structure decision（`TASK_PACKET_COMPLETE / EVIDENCE_INDEXED`：owner PR #12 merged；依据 Lifecycle Control，checkbox 保持未勾选，不提前推进 Phase / Case progress）
- [ ] 01-02: Memory persistence decode / recovery / migration contract（`TASK_PACKET_COMPLETE / EVIDENCE_INDEXED`：owner PR #14 merged；security finding 已修复复审；checkbox 保持未勾选）
- [ ] 01-03: Thin Slice 17-item minimum-persistence schema/version scoped mapping（`TASK_PACKET_COMPLETE / EVIDENCE_INDEXED`：owner PR #16 与 clarification PR #17 merged；checkbox 保持未勾选）
- [ ] 01-04: persistence schema/version implementation（`TASK_PACKET_COMPLETE / EVIDENCE_INDEXED`：PR #19 merge `bde99ed...`；134 focused / 315 full tests、双 reviewer final `PASS` 与 Graphify gate通过；checkbox 保持未勾选）
- [ ] 01-04D: Application persistence write / recovery Port closure（`TASK_PACKET_COMPLETE / EVIDENCE_INDEXED`：planning PR #20、feature PR #21 merge `a84d301...`；210 focused / 344 full tests、双 reviewer与 Graphify gate通过；不计入8个主 Plan）
- [ ] 01-04E: Memory token availability（插入式 `TASK_PACKET_COMPLETE / EVIDENCE_INDEXED`；PR #23 merge `be68490...`；required TokenCounts object + nullable strict per-direction exact counts；[Summary](phases/01-cycle-1-e2e-01/01-04E-SUMMARY.md)）
- [ ] 01-04F: Thin Slice / Eval fault-path alignment（插入式 `TASK_PACKET_COMPLETE / EVIDENCE_INDEXED`；PR #24 merge `1d47fae...`；canonical ACTIVE/v1 → WAITING_USER/v2 → BLOCKED/v3；[Summary](phases/01-cycle-1-e2e-01/01-04F-SUMMARY.md)）
- [ ] 01-04G: restart recovery state + Trace atomicity（插入式 `TASK_PACKET_COMPLETE / EVIDENCE_INDEXED`；PR #25 merge / W2 base `c35687d...`；Port-level APPLIED state/link/Trace atomicity与per-event exact projection；[Summary](phases/01-cycle-1-e2e-01/01-04G-SUMMARY.md)）
- [ ] 01-04H: normal terminal-turn atomicity（插入式 `TASK_PACKET_COMPLETE / EVIDENCE_INDEXED`；planning PR #31、owner PR #32 merge `64992cf...`；269 focused / 560 full、independent `PASS / NOT_FOUND`与Graphify gate；[Summary](phases/01-cycle-1-e2e-01/01-04H-SUMMARY.md)）
- [ ] 01-05: W2 Runtime historical Packet（`EXECUTED_FEATURE / REVIEW_BLOCKED`；旧 [PR #28](https://github.com/weijie567/mini-agent/pull/28) current head `a27141b...`，exact 14 files、95 focused / 561 full；旧race/cancellation finding已关闭，但post-commit Message/RunStopped degradation为confirmed HIGH；本Plan不改写）
- [ ] 01-05R: W2 Runtime replacement（`TASK_PACKET_COMPLETE / EVIDENCE_INDEXED`；planning [PR #33](https://github.com/weijie567/mini-agent/pull/33)、Runtime [PR #34](https://github.com/weijie567/mini-agent/pull/34) merge `fb607019...`；100 focused / 660 full、38 migration、feature/overlay `PASS / NOT_FOUND`与Graphify gate；[Summary](phases/01-cycle-1-e2e-01/01-05R-SUMMARY.md)）
- [ ] 01-06: W2 Infra historical Packet（`EXECUTED_FEATURE / REVIEW_BLOCKED`；旧 [PR #30](https://github.com/weijie567/mini-agent/pull/30) current head `054dcaf...`，exact 13 files、23 focused / 506 full；phantom schedule已关闭，raw ValidationError disclosure与recovery-first late ToolCall为confirmed blocker；本Plan不改写）
- [ ] 01-06R: W2 Infra replacement（`TASK_PACKET_COMPLETE / EVIDENCE_INDEXED`；planning [PR #35](https://github.com/weijie567/mini-agent/pull/35)、Infra [PR #36](https://github.com/weijie567/mini-agent/pull/36) merge `8e21652...`；83 focused / 40 migration / 745 full、feature/overlay `PASS / NOT_FOUND`与Graphify gate；[Summary](phases/01-cycle-1-e2e-01/01-06R-SUMMARY.md)）
- [ ] 01-07: W2 Eval（`TASK_PACKET_COMPLETE / EVIDENCE_INDEXED`；[PR #29](https://github.com/weijie567/mini-agent/pull/29) head `b8ecbb0...`经latest overlay `ee46f38...`复验并merge `eee1c0e...`；191 focused / 40 migration / 936 full、1 deselected，双preflight、双review与Graphify gate；[Summary](phases/01-cycle-1-e2e-01/01-07-SUMMARY.md)）
- [ ] 01-07A: Runtime Trace alignment（插入式 `TASK_PACKET_COMPLETE / EVIDENCE_INDEXED`；planning [PR #37](https://github.com/weijie567/mini-agent/pull/37)、Runtime [PR #38](https://github.com/weijie567/mini-agent/pull/38) merge `4cfac0a...`；100 focused / 40 migration / 936 full（1 deselected）、feature/overlay双路`PASS / NOT_FOUND`与Graphify gate；[Summary](phases/01-cycle-1-e2e-01/01-07A-SUMMARY.md)）
- [ ] 01-07B: Eval oracle isolation / Trace precedence（插入式 `TASK_PACKET_COMPLETE / EVIDENCE_INDEXED`；[Plan](phases/01-cycle-1-e2e-01/01-07B-PLAN.md)固定base `8544137...`与six-file ownership；[PR #44](https://github.com/weijie567/mini-agent/pull/44) merge `ccdafe87...`；[Summary](phases/01-cycle-1-e2e-01/01-07B-SUMMARY.md)；checkbox因lifecycle仍为0/8而保持未勾选）
- [ ] 01-07C: RU semantic ruling（插入式 `TASK_PACKET_COMPLETE / EVIDENCE_INDEXED`；[Plan](phases/01-cycle-1-e2e-01/01-07C-PLAN.md)固定base `3f0753f7...`与Intent owner单文件ownership；PR #51 blocked lineage保留，r1 Plan PR #52与owner PR #53关闭findings并merge `327b39d...`；[Summary](phases/01-cycle-1-e2e-01/01-07C-SUMMARY.md)；checkbox因lifecycle仍为0/8而保持未勾选）
- [ ] 01-07D: Thin Slice RU exact mapping（`TASK_PACKET_COMPLETE / EVIDENCE_INDEXED`；[Plan](phases/01-cycle-1-e2e-01/01-07D-PLAN.md)、feature [PR #59](https://github.com/weijie567/mini-agent/pull/59) merge `5f793fd...`、one-file parser/mutation gates、independent `0/0/0/0`；[Summary](phases/01-cycle-1-e2e-01/01-07D-SUMMARY.md)；checkbox因lifecycle仍为0/8而保持未勾选）
- [ ] 01-07E: Application persistence codec（`PLANNING_READY_FROM_B_DH / NOT_ISSUED`；唯一input为`B_DH = 4a7e802...` / tree `a5a6029...`；codec sole writer须落实per-record version registry/encode/decode及tests，不修改active docs/RU DTO；Plan reviewed merge前不得写实现）
- [ ] 01-07F: RU Core implementation（`PLANNING_READY_FROM_B_DH / NOT_ISSUED`；唯一input为`B_DH = 4a7e802...` / tree `a5a6029...`；RU owner须落实actual output/candidates与logical/model双version区分，不修改codec；Plan reviewed merge前不得写实现）
- [ ] 01-07G: Thin Slice `get_order` source-version ruling（插入式 `TASK_PACKET_COMPLETE / EVIDENCE_INDEXED`；[Plan](phases/01-cycle-1-e2e-01/01-07G-PLAN.md)固定base `3f0753f7...`与Thin Slice owner单文件ownership；PR #50 merge `bfc63c9...`冻结authority/算法/fixed vectors/exact-copy与green migration；[Summary](phases/01-cycle-1-e2e-01/01-07G-SUMMARY.md)；checkbox因lifecycle仍为0/8而保持未勾选）
- [ ] 01-07H: Core/Order DTO additive expand（`TASK_PACKET_COMPLETE / EVIDENCE_INDEXED`；[Plan](phases/01-cycle-1-e2e-01/01-07H-PLAN.md)、RED `93705ce...`、GREEN `3c5345e...`、feature [PR #60](https://github.com/weijie567/mini-agent/pull/60) merge `4a7e802...`；80 focused / 3 PostgreSQL / 1507 full、independent `0/0/0/0`；保持legacy `FOUND + None`；[Summary](phases/01-cycle-1-e2e-01/01-07H-SUMMARY.md)；checkbox因lifecycle仍为0/8而保持未勾选）
- [ ] 01-07I: Application exact-Run Evidence Port / Provider failure contract（`BLOCKED_BY_01-07E/F/H`；定义expectation-free、owner-scoped、transactionally-consistent closure DTO/Port及partial/torn fail-closed；Port owner另冻结fresh parameterless、raw-free RU candidate-invalid signal与`ModelProvider`异常分类）
- [ ] 01-07J: Runtime consumer / INPUT_INVALID mapping（`BLOCKED_BY_01-07E/F/H/I`；写canonical RU record；FOUND缺失/损坏version必须bounded SYSTEM_FAILURE且无Observation/Manifest，合法version exact-copy且不fallback；只把01-07I signal映射为`COMPLETED / INPUT_INVALID`）
- [ ] 01-07K: Infra strict reader / order-version producer（`BLOCKED_BY_01-07J`；实现01-07I一致snapshot，并在同一次owner-scoped读取上计算和返回order version，不定义DTO/Port/Eval语义）
- [ ] 01-07L: Eval HTTP/closure mapper / Scripted-Qwen consumers（`BLOCKED_BY_01-07I/J`；只从真实HTTP与Application closure构造`EvalEvidence`，不从script/expectations补造；按01-07既有ownership让两类Provider只将RU output Pydantic拒绝映射为01-07I signal，其他协议/Presentation错误仍为raw-free `ProviderProtocolError`）
- [ ] 01-07M: Core source-version contract closure（`BLOCKED_BY_01-07K/L`；从K/L共同barrier签发；收紧`GetOrderResult.FOUND`为non-empty exact-pattern version必填，保留non-FOUND禁止并运行full suite）
- [ ] 01-08: W3 Composition Root 与纵向集成（`BLOCKED_BY_01-07M`；从M reviewed merge后的exact integration SHA规划与执行）
- [ ] 01-08A: credentialed Qwen runner（`BLOCKED_BY_01-08`；独立Eval-owner Packet；缺凭据保持`NOT_RUN / SKIPPED`）

#### Phase 1 Execution Gates

| Gate | 工作 | 启动条件 |
|---|---|---|
| Activation | activation remediation / review / merge | `PASS / MERGED`：reviewed feature head `957cabd6...`，PR #10 merge `6244756...` |
| 01-01 | Project Direction owner PR | `COMPLETE / EVIDENCE_INDEXED`：PR #12 merge `c96dea9...`，181 tests，independent exact-head `PASS` |
| 01-02 | Memory owner PR | `COMPLETE / EVIDENCE_INDEXED`：PR #14 merge `af5afd2...`，181 tests，初始 HIGH 已修复并经 current-remote exact-head review `PASS` |
| 01-03 | Thin Slice scoped mapping PR | `COMPLETE / EVIDENCE_INDEXED`：PR #16 merge `9632c18...`；projection clarification PR #17 merge `9602fc1...`；181 tests；双 reviewer final `PASS` |
| 01-04 | schema/version implementation | `COMPLETE / EVIDENCE_INDEXED`：PR #19 merge `bde99ed...`；315 tests、two-file containment、final dual review与 Graphify gate通过 |
| 01-04D | Application Port owner dependency | `COMPLETE / EVIDENCE_INDEXED`：PR #21 merge `a84d301...`；344 tests、five-file containment、双 reviewer与 Graphify gate通过 |
| 01-04E | Memory token availability | `COMPLETE / EVIDENCE_INDEXED`：PR #23 merge `be68490...`；357 tests；nullable strict per-direction exact counts |
| 01-04F | Thin Slice / Eval fault alignment | `COMPLETE / EVIDENCE_INDEXED`：PR #24 merge `1d47fae...`；364 tests；canonical Port/transition与fact-bearing presentation error stage已对齐 |
| 01-04G | Recovery Trace atomicity | `COMPLETE / EVIDENCE_INDEXED`：PR #25 merge `c35687d...`；466 tests；Graphify 3353 nodes / 5999 links / 50 hyperedges，health error为0 |
| 01-04H | Normal terminal-turn atomicity | `COMPLETE / EVIDENCE_INDEXED`：PR #31/#32；merge `64992cf...`；560-test与Graphify gate |
| 01-05R | Runtime replacement | `COMPLETE / EVIDENCE_INDEXED`：PR #33/#34；merge `fb607019...`；660-test、38 migration与Graphify gate |
| 01-06R | Infra replacement | `COMPLETE / EVIDENCE_INDEXED`：PR #35/#36；merge `8e21652...`；83 focused / 40 migration / 745 full、review与Graphify gate |
| 01-07 | Eval | `COMPLETE / EVIDENCE_INDEXED`：PR #29 merge `eee1c0e...`；191 focused / 40 migration / 936 full（1 deselected）、preflight/review与Graphify gate |
| 01-07A | Runtime Trace alignment | `COMPLETE / EVIDENCE_INDEXED`：PR #37/#38 merge `4cfac0a...`；100 focused / 40 migration / 936 full（1 deselected）、review与Graphify gate |
| 01-07B | Eval evidence boundary | `COMPLETE / EVIDENCE_INDEXED`：PR #42–#44，merge `ccdafe87...`；367 Harness / 725 owned / 762 Plan focused / 40 migration / 1493 full（1 deselected）、双review与Graphify gate |
| 01-07C / 01-07G | RU semantic / source-version rulings | `COMPLETE / EVIDENCE_INDEXED`：PR #50/#53串行merge形成`B_CG = 327b39d...` / tree `49ad0f3...`；1493 full（1 deselected）、双review、latest overlay与Graphify全量安全重建完成；PR #54又以one-file owner alignment关闭过期Project Direction状态，execution base不变；health warning已显式记录 |
| 01-07D / 01-07H | RU exact mapping / Core-Order additive DTO | `COMPLETE / EVIDENCE_INDEXED`：feature PR #59/#60从`B_CG`执行、allowlist交集0、均获independent `0/0/0/0`；串行merge形成`B_DH = 4a7e802...` / tree `a5a6029...`，combined canonical full为1507 passed；D/H Summary已索引，Graphify为post-status merge gate |
| 01-07E / 01-07F | persistence codec / RU Core | `PLANNING_READY_FROM_B_DH / NOT_ISSUED`：唯一input为`B_DH = 4a7e802...` / tree `a5a6029...`；E/F ownership与文件必须不重叠，分别经single-target Plan PR签发，feature仍由Integrator串行合并 |
| 01-07I | Application Evidence Port / Provider failure contract | 01-07E/01-07F/01-07H reviewed merge后从新的exact SHA签发；records/ports contract tests必须证明fresh parameterless/raw-free signal与RU-vs-protocol/Presentation分类 |
| 01-07J | Runtime consumer / INPUT_INVALID mapping | 01-07I reviewed merge后消费全部RU/source-version/Application contracts；Component test必须同时证明invalid-RU安全完成，以及缺失/坏version的FOUND在Observation前bounded fail-closed |
| 01-07K / 01-07L | Infra reader/version producer / Eval mapper + Provider consumers | 01-07J reviewed merge后从同一新exact SHA签发；K只写reader/order physical adapter并生成version，L按01-07 Eval ownership写mapper及Scripted/Qwen consumers；Component/real-Runtime tests覆盖两条invalid-RU script与协议/Presentation不漂移；Integrator串行合并 |
| 01-07M | Core source-version contract closure | 01-07K/01-07L共同barrier后由Core owner收紧FOUND validator；full suite必须证明所有physical/test producer已迁移，reviewed merge前01-08保持blocked |
| 01-08 | W3 串行集成 | 01-07M reviewed merge后，由 Integrator从新的exact SHA完成 Composition Root与真实纵向证据 |
| 01-08A | credentialed Qwen runner | 01-08 reviewed merge后由Eval owner签发；配置存在才运行，缺失凭据明确`NOT_RUN / SKIPPED` |
| Post-execution quality | review / fix / validation / Eval / Security / UAT / release decision | 01-08A exact integration head 已形成；本 gate 不计入 Plan count |

#### Post-execution Quality Gate（不是 Plan）

1. 在 01-08A exact-integration-SHA review-artifact Worktree 中运行受控 `gsd-code-review --files=<normalized absolute exact list>`；启动前确认 requested / accepted 路径数量完全相等、每项均为仓库内 tracked file；workflow transcript 必须显示完全相同的 `File scope: <N> files`，且不含真实的 outside-repository / file-not-found skip 输出；只允许写 Phase `REVIEW.md`。
2. Findings 只能在 Integrator 预建的专用 fix Worktree / feature branch 中处理；前后比较 base、head、allowlist、changed files 与 commits。
3. Validation 补缺只能在预建 validation Worktree / branch 中处理，并按同样 diff containment gate 审查。
4. `gsd-eval-review` 只有派生 AI / Eval mapping 明确引用 canonical Eval owner 后才构成 gate；`gsd-secure-phase` 只有完整 `<threat_model>` 映射项目安全不变量后才构成 gate。
5. 使用受控 UAT adapter 生成会话式 UAT artifact；stock `gsd-verify-work` 禁用，因为当前版本没有 `--no-transition` 模式并会自动进入 transition。
6. Quality 全部通过后，先由 canonical Coverage Matrix owner依据硬证据更新 Case lifecycle。
7. Integrator 再手工同步 derived Requirements / Roadmap / State；不得调用自动 lifecycle API。
8. Release 使用显式 GitHub `head=integration/e2e01-thin`、`base=main` 创建 PR；不调用 `gsd-ship`。

### Phase 2: Cycle 2｜完成 E2E-01

**Status**: `PLANNED_MAPPING_ONLY`

**Goal**: 按 Coverage Matrix Cycle 2 覆盖 `E2E01-02/03/05/06`。

**Depends on**: Phase 1

**Requirements**: [E2E01-02, E2E01-03, E2E01-05, E2E01-06]

**Success Criteria**:

1. 四个 Case 的 canonical acceptance criteria 均有可复现证据。
2. `E2E01-05` 与确实需要 `get_shipment` 的配对 Case 在同一可用工具集中验证。
3. 第一版 Trajectory / E2E Baseline 依 canonical Eval owner 运行并保存结果。

**Plans**: `TBD`；等待 Phase 1 反馈与 scoped implementation contract。

### Phase 3: Cycle 3a｜RAG、Evidence 与资格判断

**Status**: `PLANNED_MAPPING_ONLY`

**Goal**: 通过 `G-RAG-INFRA`，并按 Coverage Matrix 覆盖 `E2E02-01/02/03`。

**Depends on**: Phase 2

**Requirements**: [E2E02-01, E2E02-02, E2E02-03]

**Success Criteria**:

1. `G-RAG-INFRA` 的 canonical gate 有可复现结果。
2. 三个 Case 的 canonical Evidence 与资格判断标准均有 Component、Trajectory 与 E2E 证据。
3. Evidence 无效或结论不可执行时，适用 Critical failure 保持为零。

**Plans**: `TBD`；等待 RAG / E2E-02 scoped implementation contract。

### Phase 4: Cycle 3b｜受控模拟退款动作

**Status**: `PLANNED_MAPPING_ONLY`

**Goal**: 按 Coverage Matrix 覆盖 `E2E02-04/05/06`。

**Depends on**: Phase 3

**Requirements**: [E2E02-04, E2E02-05, E2E02-06]

**Success Criteria**:

1. 确认、ActionPolicy、失效确认与幂等的 canonical criteria 均有可复现证据。
2. `create_refund` 只执行模拟退款，输出不声称真实支付渠道退款或到账。
3. 适用 Critical failure 为零。

**Plans**: `TBD`；等待动作阶段 scoped implementation contract。

### Phase 5: Cycle 3c｜未知结果与跨会话恢复

**Status**: `PLANNED_MAPPING_ONLY`

**Goal**: 按 Coverage Matrix 覆盖 `E2E02-07/08`。

**Depends on**: Phase 4

**Requirements**: [E2E02-07, E2E02-08]

**Success Criteria**:

1. `RESULT_UNKNOWN` 恢复与禁止重复执行的 canonical criteria 有可复现证据。
2. 新 Conversation 恢复仍重新通过身份、资源、Observation、Evidence 与确认校验。
3. 适用 Critical failure 为零。

**Plans**: `TBD`；等待故障 / 恢复 scoped implementation contract。

### Phase 6: Cycle 4｜跨场景贯通与 P0 Release Audit

**Status**: `PLANNED_MAPPING_ONLY`

**Goal**: 按 Coverage Matrix Cycle 4 覆盖 `CROSS-01`，并完成 P0 scope 的发布证据审计。

**Depends on**: Phase 5

**Requirements**: [CROSS-01, P0-RELEASE-AUDIT]

**Success Criteria**:

1. `CROSS-01` 的 canonical 多目标、依赖、条件与确认标准有可复现证据。
2. P0 scope 内所有应激活 Case、Critical failure、Trace、回归与未决风险完成 evidence-backed audit。
3. Integration → `main` PR 只在完整 quality gate 通过后进入 merge 决策。

**Plans**: `TBD`；等待前五个 Phase 的实测反馈。

## Progress

| Phase | Plans Complete | Status | Completed |
|---|---:|---|---|
| 1. 第一最薄 E2E-01 | 0/8 | `Derived lifecycle 0/8；numbered Plan evidence indexed 7/8；目标Packet完成18/29、正式签发20个Plan、18份Summary；01-07D/01-07H feature complete并形成B_DH=4a7e802...；01-07E/F planning ready但尚未签发或实现；其余等待各自前置exact base` | - |
| 2. 完成 E2E-01 | 0/TBD | `Not started` | - |
| 3. RAG / Evidence / judgment | 0/TBD | `Not started` | - |
| 4. Simulated refund action | 0/TBD | `Not started` | - |
| 5. Result unknown / recovery | 0/TBD | `Not started` | - |
| 6. Cross / release audit | 0/TBD | `Not started` | - |

Phase 按 1 → 2 → 3 → 4 → 5 → 6 顺序推进。紧急插入只能通过显式 decimal phase、canonical impact scan 与 Integrator 裁决完成。
