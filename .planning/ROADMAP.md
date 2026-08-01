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

P0 依照 Coverage Matrix 的 Cycle 1–4 分成六个连续 Phase。Phase 1 已完成并 release；
Phase 2 scoped contract 已在 owner-alignment 冲突审查后激活为
`CONTRACT_ACTIVE / READY_FOR_PLANNING`；master Plan 已由 PR #203 合并，`02-00`
已获批并由 PR #204/#205 完成。`02-03` 与 `02-01` 已由 PR #207/#208 reviewed
串行合入并形成历史 `B_C2_W1A`；PR #212 修复 test-only full-gate regression 后
形成 `B_C2_W1_GATE_REPAIRED`，PR #213 refreeze `02-02`，PR #214/#215 reviewed
merge 后冻结 `B_C2_CORE_123` 并关闭 W1。PR #216/#217 随后完成 W2 planning、
02-04 feature/overlay 独立审阅与串行 merge，冻结 `B_C2_TOOL = f9a2a75...`。
PR #218/#219 又完成 W3 `02-05` planning、implementation、feature/overlay review 与
串行 merge，冻结 `B_C2_APP_CONTRACT = 86d1b835...`。W4 preflight 随后确认
InputBinding / atomic ordinal selection / selected-target Gateway 缺口；用户授权先
完成 `02-02R/02-04R/02-05R` 再开始 W4。旧 02-06 Plan 不可执行；真实
`B_C2_W4_READY` 形成前不创建 W4 实现分支。Phase 3–6
在对应 scoped canonical contract 出现并通过冲突审查前，只保留 Case ID 与 gate
mapping。

Phase 2 integration branch 当前已启用 PR-required、enforce-admins、linear-history、
conversation-resolution 保护，并禁用 force-push / deletion；每个 Packet preflight
仍须从 GitHub API 机械验证，不把一次配置视为永久事实。

## 🚧 **v0.1 GSD-only P0 execution**

> `v0.1` 只是 GSD 1.38.3 parser 使用的派生 execution milestone 标识，不是产品版本、发布承诺或 canonical milestone。产品范围与生命周期仍由 active owners 拥有。

## Phases

- [x] **Phase 1: Cycle 1｜第一最薄 E2E-01** — `E2E01-01/04` 已从已定义契约走到可复现纵向证据，并完成 scoped release transition。
- [ ] **Phase 2: Cycle 2｜完成 E2E-01** — 覆盖 `E2E01-02/03/05/06` 与真实按需物流工具选择。
- [ ] **Phase 3: Cycle 3a｜RAG、Evidence 与资格判断** — 通过 `G-RAG-INFRA` 并覆盖 `E2E02-01/02/03`。
- [ ] **Phase 4: Cycle 3b｜受控模拟退款动作** — 覆盖 `E2E02-04/05/06` 的确认、ActionPolicy 与幂等。
- [ ] **Phase 5: Cycle 3c｜未知结果与跨会话恢复** — 覆盖 `E2E02-07/08`。
- [ ] **Phase 6: Cycle 4｜跨场景贯通与 P0 Release Audit** — 覆盖 `CROSS-01` 并审计 P0 发布证据。

## Phase Details

### Phase 1: Cycle 1｜第一最薄 E2E-01

**Status**: `COMPLETE / IMPLEMENTATION_42_OF_42 / REGRESSION_GATE / QUALITY_GATES_COMPLETE / RELEASED_TO_MAIN`

**Goal**: 为 canonical `E2E01-01/04` 取得可复现的源码、HTTP、Trace、结构化 Eval 与安全门禁证据。

**Depends on**: 全部implementation dependency已满足。历史barrier链经`B_ACTIVE`、`B_RU_V2_CONTRACT = 5c84e0e...`、`B_01_08 = b8a2cf3...`、`B_01_08A_COMPOSITION = c59eaea...`最终形成`B_01_08A = 11d6d08...`；后续quality / status证据不替换这些产品barrier。

**Requirements**: [E2E01-01, E2E01-04]

**Success Criteria**:

1. `E2E01-01` 的 canonical acceptance criteria 具有可复现 Component、Trajectory 与 HTTP E2E 证据。
2. `E2E01-04` 两个变体具有 canonical owner 要求的安全等价与禁止披露证据。
3. 适用 Critical failure 为零，结构化 Eval Result、Trace 与版本 manifest 可追溯；缺失证据不得以 GSD 状态代替。
4. Exact integration head 通过 canonical 命令、独立 review、validation、适用的 Eval / Security audit 与 UAT。

**Plans**: Phase 1 的49份historical `*-PLAN.md` artifact与24份Summary均已由Validation分类；八个numbered Plan和全部42个implementation targets完成。Phase 2 `02-00` 已作为独立 zero-code Packet 完成，不计入 Phase 1 完成数；`02-01` / `02-03` proposal 也不表示功能已实现。PR #172–#186完成review / fix、Validation、controlled UAT、Eval activation / Results / regression gate与mandatory Eval / Security re-review；六个authenticated physical Case的全部16 variants为`16 PASS / 0 FAIL / 0 Critical failure / 0 execution failure`，canonical full为`2007 passed, 1 deselected, 12 warnings`。用户已继续接受有界`RTA-D01`，reviewed PR #199已squash merge到`main`（`f15320e3...`），Phase与已完成Task Packet checkbox由Integrator手工同步；historical blocked replacement rows仍保持未勾选。用户已明确暂时停用Graphify；后续不运行、不引用，也不把freshness作为门禁。

Plans:

- [x] 01-01: Project Direction persistence ownership / Trace structure decision（`TASK_PACKET_COMPLETE / EVIDENCE_INDEXED`：owner PR #12 merged；release transition已完成）
- [x] 01-02: Memory persistence decode / recovery / migration contract（`TASK_PACKET_COMPLETE / EVIDENCE_INDEXED`：owner PR #14 merged；security finding 已修复复审；release transition已完成）
- [x] 01-03: Thin Slice 17-item minimum-persistence schema/version scoped mapping（`TASK_PACKET_COMPLETE / EVIDENCE_INDEXED`：owner PR #16 与 clarification PR #17 merged；release transition已完成）
- [x] 01-04: persistence schema/version implementation（`TASK_PACKET_COMPLETE / EVIDENCE_INDEXED`：PR #19 merge `bde99ed...`；134 focused / 315 full tests、双 reviewer final `PASS` 与 Graphify gate通过；release transition已完成）
- [x] 01-04D: Application persistence write / recovery Port closure（`TASK_PACKET_COMPLETE / EVIDENCE_INDEXED`：planning PR #20、feature PR #21 merge `a84d301...`；210 focused / 344 full tests、双 reviewer与 Graphify gate通过；不计入8个主 Plan）
- [x] 01-04E: Memory token availability（插入式 `TASK_PACKET_COMPLETE / EVIDENCE_INDEXED`；PR #23 merge `be68490...`；required TokenCounts object + nullable strict per-direction exact counts；[Summary](phases/01-cycle-1-e2e-01/01-04E-SUMMARY.md)）
- [x] 01-04F: Thin Slice / Eval fault-path alignment（插入式 `TASK_PACKET_COMPLETE / EVIDENCE_INDEXED`；PR #24 merge `1d47fae...`；canonical ACTIVE/v1 → WAITING_USER/v2 → BLOCKED/v3；[Summary](phases/01-cycle-1-e2e-01/01-04F-SUMMARY.md)）
- [x] 01-04G: restart recovery state + Trace atomicity（插入式 `TASK_PACKET_COMPLETE / EVIDENCE_INDEXED`；PR #25 merge / W2 base `c35687d...`；Port-level APPLIED state/link/Trace atomicity与per-event exact projection；[Summary](phases/01-cycle-1-e2e-01/01-04G-SUMMARY.md)）
- [x] 01-04H: normal terminal-turn atomicity（插入式 `TASK_PACKET_COMPLETE / EVIDENCE_INDEXED`；planning PR #31、owner PR #32 merge `64992cf...`；269 focused / 560 full、independent `PASS / NOT_FOUND`与Graphify gate；[Summary](phases/01-cycle-1-e2e-01/01-04H-SUMMARY.md)）
- [ ] 01-05: W2 Runtime historical Packet（`EXECUTED_FEATURE / REVIEW_BLOCKED`；旧 [PR #28](https://github.com/weijie567/mini-agent/pull/28) current head `a27141b...`，exact 14 files、95 focused / 561 full；旧race/cancellation finding已关闭，但post-commit Message/RunStopped degradation为confirmed HIGH；本Plan不改写）
- [x] 01-05R: W2 Runtime replacement（`TASK_PACKET_COMPLETE / EVIDENCE_INDEXED`；planning [PR #33](https://github.com/weijie567/mini-agent/pull/33)、Runtime [PR #34](https://github.com/weijie567/mini-agent/pull/34) merge `fb607019...`；100 focused / 660 full、38 migration、feature/overlay `PASS / NOT_FOUND`与Graphify gate；[Summary](phases/01-cycle-1-e2e-01/01-05R-SUMMARY.md)）
- [ ] 01-06: W2 Infra historical Packet（`EXECUTED_FEATURE / REVIEW_BLOCKED`；旧 [PR #30](https://github.com/weijie567/mini-agent/pull/30) current head `054dcaf...`，exact 13 files、23 focused / 506 full；phantom schedule已关闭，raw ValidationError disclosure与recovery-first late ToolCall为confirmed blocker；本Plan不改写）
- [x] 01-06R: W2 Infra replacement（`TASK_PACKET_COMPLETE / EVIDENCE_INDEXED`；planning [PR #35](https://github.com/weijie567/mini-agent/pull/35)、Infra [PR #36](https://github.com/weijie567/mini-agent/pull/36) merge `8e21652...`；83 focused / 40 migration / 745 full、feature/overlay `PASS / NOT_FOUND`与Graphify gate；[Summary](phases/01-cycle-1-e2e-01/01-06R-SUMMARY.md)）
- [x] 01-07: W2 Eval（`TASK_PACKET_COMPLETE / EVIDENCE_INDEXED`；[PR #29](https://github.com/weijie567/mini-agent/pull/29) head `b8ecbb0...`经latest overlay `ee46f38...`复验并merge `eee1c0e...`；191 focused / 40 migration / 936 full、1 deselected，双preflight、双review与Graphify gate；[Summary](phases/01-cycle-1-e2e-01/01-07-SUMMARY.md)）
- [x] 01-07A: Runtime Trace alignment（插入式 `TASK_PACKET_COMPLETE / EVIDENCE_INDEXED`；planning [PR #37](https://github.com/weijie567/mini-agent/pull/37)、Runtime [PR #38](https://github.com/weijie567/mini-agent/pull/38) merge `4cfac0a...`；100 focused / 40 migration / 936 full（1 deselected）、feature/overlay双路`PASS / NOT_FOUND`与Graphify gate；[Summary](phases/01-cycle-1-e2e-01/01-07A-SUMMARY.md)）
- [x] 01-07B: Eval oracle isolation / Trace precedence（插入式 `TASK_PACKET_COMPLETE / EVIDENCE_INDEXED`；[Plan](phases/01-cycle-1-e2e-01/01-07B-PLAN.md)固定base `8544137...`与six-file ownership；[PR #44](https://github.com/weijie567/mini-agent/pull/44) merge `ccdafe87...`；[Summary](phases/01-cycle-1-e2e-01/01-07B-SUMMARY.md)；release transition已完成）
- [x] 01-07C: RU semantic ruling（插入式 `TASK_PACKET_COMPLETE / EVIDENCE_INDEXED`；[Plan](phases/01-cycle-1-e2e-01/01-07C-PLAN.md)固定base `3f0753f7...`与Intent owner单文件ownership；PR #51 blocked lineage保留，r1 Plan PR #52与owner PR #53关闭findings并merge `327b39d...`；[Summary](phases/01-cycle-1-e2e-01/01-07C-SUMMARY.md)；release transition已完成）
- [x] 01-07D: Thin Slice RU exact mapping（`TASK_PACKET_COMPLETE / EVIDENCE_INDEXED`；[Plan](phases/01-cycle-1-e2e-01/01-07D-PLAN.md)、feature [PR #59](https://github.com/weijie567/mini-agent/pull/59) merge `5f793fd...`、one-file parser/mutation gates、independent `0/0/0/0`；[Summary](phases/01-cycle-1-e2e-01/01-07D-SUMMARY.md)；release transition已完成）
- [x] 01-07E: Application persistence codec（`TASK_PACKET_COMPLETE / EVIDENCE_INDEXED`；Plan / correction / feature [PR #72](https://github.com/weijie567/mini-agent/pull/72) / [#73](https://github.com/weijie567/mini-agent/pull/73) / [#74](https://github.com/weijie567/mini-agent/pull/74)；形成non-routable `B_FE_EXPAND = 294ada3...`；[Summary](phases/01-cycle-1-e2e-01/01-07E-SUMMARY.md)；release transition已完成）
- [x] 01-07F: RU Core implementation（`TASK_PACKET_COMPLETE / EVIDENCE_INDEXED`；Plan / feature [PR #70](https://github.com/weijie567/mini-agent/pull/70) / [#71](https://github.com/weijie567/mini-agent/pull/71)；形成 `B_F = 034cf57...`；[Summary](phases/01-cycle-1-e2e-01/01-07F-SUMMARY.md)；release transition已完成）
- [x] 01-07G: Thin Slice `get_order` source-version ruling（插入式 `TASK_PACKET_COMPLETE / EVIDENCE_INDEXED`；[Plan](phases/01-cycle-1-e2e-01/01-07G-PLAN.md)固定base `3f0753f7...`与Thin Slice owner单文件ownership；PR #50 merge `bfc63c9...`冻结authority/算法/fixed vectors/exact-copy与green migration；[Summary](phases/01-cycle-1-e2e-01/01-07G-SUMMARY.md)；release transition已完成）
- [x] 01-07H: Core/Order DTO additive expand（`TASK_PACKET_COMPLETE / EVIDENCE_INDEXED`；[Plan](phases/01-cycle-1-e2e-01/01-07H-PLAN.md)、RED `93705ce...`、GREEN `3c5345e...`、feature [PR #60](https://github.com/weijie567/mini-agent/pull/60) merge `4a7e802...`；80 focused / 3 PostgreSQL / 1507 full、independent `0/0/0/0`；保持legacy `FOUND + None`；[Summary](phases/01-cycle-1-e2e-01/01-07H-SUMMARY.md)；release transition已完成）
- [x] 01-07N: RU v2 cutover remediation（`TASK_PACKET_COMPLETE / EVIDENCE_INDEXED`；Plan / owner [PR #62](https://github.com/weijie567/mini-agent/pull/62) / [PR #63](https://github.com/weijie567/mini-agent/pull/63) reviewed merge `a4b1edb...`；[Summary](phases/01-cycle-1-e2e-01/01-07N-SUMMARY.md)）
- [x] 01-07O: execution-map alignment（`TASK_PACKET_COMPLETE / EVIDENCE_INDEXED`；Plan / owner [PR #64](https://github.com/weijie567/mini-agent/pull/64) / [PR #65](https://github.com/weijie567/mini-agent/pull/65) reviewed merge `7332091...`，PR #66校正派生状态；[Summary](phases/01-cycle-1-e2e-01/01-07O-SUMMARY.md)）
- [x] 01-07I: Application exact-Run evidence boundary（`TASK_PACKET_COMPLETE / EVIDENCE_INDEXED`；Plan / feature [PR #80](https://github.com/weijie567/mini-agent/pull/80) / [#83](https://github.com/weijie567/mini-agent/pull/83)；357 focused / 1759 full；[Summary](phases/01-cycle-1-e2e-01/01-07I-SUMMARY.md)；release transition已完成）
- [x] 01-07P: migration-chain physical expand（`TASK_PACKET_COMPLETE / EVIDENCE_INDEXED`；原PR #82 closed/unmerged，remediation PR #84/#85，r1 Plan / feature [PR #86](https://github.com/weijie567/mini-agent/pull/86) / [#87](https://github.com/weijie567/mini-agent/pull/87)；48 focused / 119 database / 1767 full；形成`B_IP = bbe14fa...`；[Summary](phases/01-cycle-1-e2e-01/01-07P-SUMMARY.md)；release transition已完成）
- [x] 01-07K / 01-07L: Infra reader/order producer / Eval mapper+Provider dependency consumers（`TASK_PACKET_COMPLETE / EVIDENCE_INDEXED`；Plan/feature/security amendment [PR #94](https://github.com/weijie567/mini-agent/pull/94)–[#98](https://github.com/weijie567/mini-agent/pull/98) reviewed串行merge形成`B_DEPENDENCY = e54a6a4...`；canonical full `1901 passed, 1 deselected, 12 warnings`；release transition已完成）
- [x] 01-07M: Core source-version contract closure（`TASK_PACKET_COMPLETE / EVIDENCE_INDEXED`；Plan/shell correction/feature [PR #99](https://github.com/weijie567/mini-agent/pull/99)–[#101](https://github.com/weijie567/mini-agent/pull/101)形成`B_DEPENDENCY_M = 42fa2ec...`；full `1901 passed, 1 deselected, 12 warnings`；release transition已完成）
- [x] 01-07Q: Application codec active switch（`TASK_PACKET_COMPLETE / EVIDENCE_INDEXED`；oracle remediation与Plan/category/feature [PR #102](https://github.com/weijie567/mini-agent/pull/102)–[#106](https://github.com/weijie567/mini-agent/pull/106)形成`B_Q = 2b9fde6...`；full `1901 passed, 1 deselected, 12 warnings`；Runtime当时仍未切换）
- [x] 01-07Y / 01-07Z: RU-v2 reducer与Application write contracts（`TASK_PACKET_COMPLETE / EVIDENCE_INDEXED`；execution-map r2 [PR #107](https://github.com/weijie567/mini-agent/pull/107)，Plan/feature [PR #108](https://github.com/weijie567/mini-agent/pull/108)–[#111](https://github.com/weijie567/mini-agent/pull/111)从exact`B_Q`执行并串行形成`B_YZ = d704b87...`）
- [x] 01-07AA: PostgreSQL RU-v2 atomic writers（`TASK_PACKET_COMPLETE / EVIDENCE_INDEXED`；Plan、closure/codec quality-gate remediation与feature [PR #112](https://github.com/weijie567/mini-agent/pull/112)–[#120](https://github.com/weijie567/mini-agent/pull/120)形成`B_J_READY = b8d32d5...`；post-merge full `1987 passed, 1 deselected, 12 warnings`）
- [x] 01-07J: Runtime v2 active switch / INPUT_INVALID mapping（`TASK_PACKET_COMPLETE / EVIDENCE_INDEXED`；Plan、exact-reader scope alignment与feature [PR #121](https://github.com/weijie567/mini-agent/pull/121)–[#124](https://github.com/weijie567/mini-agent/pull/124)；exact-head与latest-overlay均`P0/P1/P2/P3 = 0/0/0/0`；merge-tree equality；post-merge focused 87、Application 707、neighbors 165、full `2033 passed, 1 deselected, 12 warnings`；形成scoped`B_ACTIVE = 7f92b5e...`）
- [x] 01-07S / 01-07U: Eval Provider / Runtime v1-contract closure（`TASK_PACKET_COMPLETE / EVIDENCE_INDEXED`；从exact`B_ACTIVE`执行并串行形成`B_SU`；release transition已完成）
- [x] 01-07X: Infra persistence v1-contract closure（`TASK_PACKET_COMPLETE / EVIDENCE_INDEXED`；形成`B_X`）
- [x] 01-07T: Application codec v1-contract closure（`TASK_PACKET_COMPLETE / EVIDENCE_INDEXED`；形成`B_T`）
- [x] 01-07W: Application Port/records v1-contract closure（`TASK_PACKET_COMPLETE / EVIDENCE_INDEXED`；形成`B_W`）
- [x] 01-07V: RU Core v1-contract closure（`TASK_PACKET_COMPLETE / EVIDENCE_INDEXED`；最后形成`B_RU_V2_CONTRACT = 5c84e0e...`）
- [x] 01-08: W3 Composition Root 与纵向集成（`TASK_PACKET_COMPLETE / EVIDENCE_INDEXED`；形成`B_01_08 = b8a2cf3...`）
- [x] 01-08A: credential-aware Qwen runner（`TASK_PACKET_COMPLETE / EVIDENCE_INDEXED`；形成`B_01_08A = 11d6d08...`；真实credentialed结果保持`NOT_RUN / SKIPPED`）

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
| 01-07D / 01-07H | RU exact mapping / Core-Order additive DTO | `COMPLETE / EVIDENCE_INDEXED`：feature PR #59/#60从`B_CG`执行、allowlist交集0、均获independent `0/0/0/0`；串行merge形成`B_DH = 4a7e802...` / tree `a5a6029...`，combined canonical full为1507 passed |
| 01-07N / 01-07O | cutover remediation / unique execution map | `COMPLETE / EVIDENCE_INDEXED`：Plan/owner PR #62–#65 reviewed merge；N形成`a4b1edb...`，O形成`7332091...`；PR #66将owner计数校正为20/39 |
| Status barriers | planning-status / Project Direction | `B_O_STATUS = 73696a1...`已形成并被F精确消费；F/E、I/P与本次B_ACTIVE后的派生状态对齐均不创建第二道implementation barrier、不推进lifecycle |
| 01-07F | RU Core expand | `COMPLETE / EVIDENCE_INDEXED`：PR #70/#71；`B_F = 034cf57...`；41-definition protected-v1 gate与1575 full通过 |
| 01-07E | persistence codec expand | `COMPLETE / EVIDENCE_INDEXED`：PR #72/#73/#74；`B_FE_EXPAND = 294ada3...`；60-definition oracle与1671 full通过；active routing未切换 |
| 01-07I / 01-07P | Application Port / migration-chain dependency expand | `COMPLETE / EVIDENCE_INDEXED`：PR #80–#87；I/P分别完成Application与physical expand；serial merge形成`B_IP = bbe14fa...` / tree `65415ff...`；exact B_IP full为1767 passed |
| 01-07K / 01-07L | Infra reader/order producer / Eval mapper+Provider consumers | `COMPLETE / EVIDENCE_INDEXED`：PR #94–#98形成`B_DEPENDENCY = e54a6a4...` |
| 01-07M / 01-07Q | Core closure / codec active switch | `COMPLETE / EVIDENCE_INDEXED`：PR #99–#106依序形成`B_DEPENDENCY_M = 42fa2ec...`与`B_Q = 2b9fde6...` |
| 01-07Y / 01-07Z / 01-07AA | J durable-v2 prerequisites | `COMPLETE / EVIDENCE_INDEXED`：PR #107–#120形成`B_YZ = d704b87...`与`B_J_READY = b8d32d5...` |
| 01-07J | Runtime v2 active switch | `COMPLETE / EVIDENCE_INDEXED`：PR #121–#124形成scoped`B_ACTIVE = 7f92b5e...` / tree `f70b202...` |
| 01-07S/U → X → T → W → V | v1 contract closure | `COMPLETE / B_RU_V2_CONTRACT = 5c84e0e...` |
| 01-08 | W3 串行集成 | `COMPLETE / B_01_08 = b8a2cf3...`；真实offline HTTP→Runtime→PostgreSQL evidence已形成 |
| 01-08A | credential-aware Qwen runner | `COMPLETE / B_01_08A = 11d6d08...`；缺失凭据明确`NOT_RUN / SKIPPED` |
| Post-execution quality | review / fix / validation / Eval / Security / UAT / release decision | `COMPLETE`：用户继续接受有界`RTA-D01`；PR #199 exact-head review `PASS`并merge到`main` |

#### Post-execution Quality Gate（不是 Plan）

1. 在 01-08A exact-integration-SHA review-artifact Worktree 中运行受控 `gsd-code-review --files=<normalized absolute exact list>`；启动前确认 requested / accepted 路径数量完全相等、每项均为仓库内 tracked file；workflow transcript 必须显示完全相同的 `File scope: <N> files`，且不含真实的 outside-repository / file-not-found skip 输出；只允许写 Phase `REVIEW.md`。
2. Findings 只能在 Integrator 预建的专用 fix Worktree / feature branch 中处理；前后比较 base、head、allowlist、changed files 与 commits。
3. Validation 补缺只能在预建 validation Worktree / branch 中处理，并按同样 diff containment gate 审查。
4. `gsd-eval-review` 只有派生 AI / Eval mapping 明确引用 canonical Eval owner 后才构成 gate；`gsd-secure-phase` 只有完整 `<threat_model>` 映射项目安全不变量后才构成 gate。
5. 使用受控 UAT adapter 生成会话式 UAT artifact；stock `gsd-verify-work` 禁用，因为当前版本没有 `--no-transition` 模式并会自动进入 transition。
6. Quality 全部通过后，先由 canonical Coverage Matrix owner依据硬证据更新 Case lifecycle。
7. Integrator 再手工同步 derived Requirements / Roadmap / State；不得调用自动 lifecycle API。
8. Release 使用显式 GitHub `head=integration/e2e01-thin`、`base=main` 创建 PR；不调用 `gsd-ship`。

截至 2026-07-31，第1–8项已完成：review/fix、Validation、controlled UAT、Case activation、exhaustive Result、`REGRESSION_GATE` synchronization、Eval re-audit与mandatory Security re-review均已有reviewed PR evidence；用户继续接受有界`RTA-D01`后，release PR #199以exact-head `PASS`合并到`main`。Phase 2 owner alignment 已由 PR #201 合并为 `9ee260f12a82b706269f8a62c460c781c64f1f47`，后续独立 Activation 只推进 scoped contract，不改变 Phase 1 release evidence。

### Phase 2: Cycle 2｜完成 E2E-01

**Status**:
`CONTRACT_ACTIVE / W3R_02_02R_PLANNING_REVIEW / W4_BLOCKED / CASES_CONTRACT_DEFINED`

**Goal**: 按 Coverage Matrix Cycle 2 覆盖 `E2E01-02/03/05/06`。

**Depends on**: Phase 1（已完成并 release）

**Requirements**: [E2E01-02, E2E01-03, E2E01-05, E2E01-06]

**Success Criteria**:

1. 四个 Case 的 canonical acceptance criteria 均有可复现证据。
2. `E2E01-05` 与确实需要 `get_shipment` 的配对 Case 在同一可用工具集中验证。
3. 第一版 Trajectory / E2E Baseline 依 canonical Eval owner 运行并保存结果。

**Plans**: 原 master Plan 的 `19` 个一对一 Plan / Task Packet slots
（`02-00..18`）、`W0..W12`、最大并发 `2` 已获 Gate P2-A 批准并由 PR #203
合并。当前用户又批准 `02-02R/02-04R/02-05R` 与 `W3R`，因此目标为 22 slots /
14 wave labels，最大并发仍为 `2`。`02-00/01/02/03` 已批准并执行；PR #214 完成 repaired status alignment，
PR #215 reviewed merge 形成 W1 barrier `B_C2_CORE_123 = 241cf6b...`；PR #216/#217
完成 W2 planning 与 02-04 implementation/overlay review，形成 W2 barrier
`B_C2_TOOL = f9a2a75...`。PR #218/#219 完成 W3 02-05 并冻结
`B_C2_APP_CONTRACT = 86d1b835...`；旧 `ecfad7e...` head 保持 quarantined。PR #221
已 reviewed merge 并形成真实 `B_C2_W3R_RULING = ed61f4d...`；当前从该 barrier
签发 `02-02R`，其 reviewed merge 后签发
`02-04R/02-05R`。三者形成 `B_C2_W4_READY` 后，重新冻结
`02-06/08/09/13`；每份全新 planning review `PASS`/merge 前不创建对应 implementation
branch。旧 02-06 Plan 仅保留为历史 planning artifact。

**Branch mapping**:

```text
B_C2_PLAN_APPROVED
= 2879f5226a073051d1550fe079b4a427c1ec8cb1
= planning PR #203 merge successor

B_C2_OWNER_ALIGNED
= 4dc6dc95de81080fb3b651bc2f0026fb046fd9f8
= tree 521ac2c7611b20683089ab41a74d07c9a2bb8fc7
= PR #205 merge successor

integration/e2e01-cycle2
= created from exact B_C2_OWNER_ALIGNED at Gate P2-C

B_C2_START
= branch exact head/tree immediately after creation
= B_C2_OWNER_ALIGNED exact SHA/tree
= initial implementation base

B_C2_W1A
= b5de7f4f48404b61d9b4386c99cd2c37e744641a
= historical reviewed 02-03/02-01 barrier; no longer executable after its full-gate regression

B_C2_W1_GATE_REPAIRED
= 015c1e8be204717dfa1af80d930a8333a41e8b92
= tree 26b71d2ba3f2c638204cab7c078252c97b374f05
= PR #212 reviewed merge successor and exact 02-02 r2 product base

B_C2_W1B_REFREEZE_CONTROL
= fedd2d1a10ae088d3c762875bffd68ed828d8e3f
= PR #213 reviewed planning-only merge successor; does not replace product base

B_C2_W1_STATUS_ALIGNED
= 2aec3663a5d8e2456e6bf69f37ac1f8f343a6c19
= PR #214 reviewed four-file status alignment successor

B_C2_CORE_123
= 241cf6b83761f5d91da5de7719f26838e2626e26
= tree 83fcbf90770ffdc30ef37e35e94169bcb9ead3b3
= PR #215 reviewed merge successor and exact W2 product base

B_C2_TOOL
= f9a2a75135ba63347e81e13f2b981cf550977875
= tree 59afeccec3705b7bae754c00b012f669a049a9ac
= PR #217 reviewed merge successor and exact W3 product base

B_C2_APP_CONTRACT
= 86d1b8357f817882b017e5c4306ec855e0b288e6
= tree b27f5f805c85e8ce76c30be254a004cb5f127b4e
= PR #219 reviewed merge successor and exact pre-remediation product barrier

B_C2_W3R_RULING
= ed61f4d4da9c75386aa96857a5e77e06de4c4804
= tree 02c06f70459cf9593946c599a2de33d1c5a15a91
= PR #221 reviewed owner-ruling merge successor and exact 02-02R product base

B_C2_W4_READY
= OPEN; only the actual reviewed serial-merge successor of 02-02R/02-04R/02-05R
= future exact W4 product base; must not be guessed
```

`.planning/config.json` 中的 mapping 已用于创建 `integration/e2e01-cycle2`；
`B_C2_START` 已冻结为 `B_C2_OWNER_ALIGNED` exact SHA/tree，随后 reviewed 02-03/02-01
串行形成历史 `B_C2_W1A`。Phase 1 的 `integration/e2e01-thin` 保留为历史 release
证据。W1 `02-02` r2 已从 exact repaired product base 形成 reviewed merge；旧
`ecfad7e...` 未进入 ancestry。W2 `02-04` 与 W3 `02-05` 已依次完成；W4 四个
implementation Packet 必须等 W3R 完成后固定到真实 `B_C2_W4_READY`。旧
`B_C2_APP_CONTRACT` 与旧 02-06 Plan 均不得作为 W4 dispatch base。

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
| 1. 第一最薄 E2E-01 | 8/8 | `Implementation 42/42；六Case REGRESSION_GATE；16 PASS；quality gates complete；RTA-D01 accepted；PR #199 merged to main` | 2026-07-31 |
| 2. 完成 E2E-01 | 6/22 | `02-00..05 complete；B_C2_W3R_RULING frozen；02-02R planning review；functional implementation 5/21；Cases CONTRACT_DEFINED` | - |
| 3. RAG / Evidence / judgment | 0/TBD | `Not started` | - |
| 4. Simulated refund action | 0/TBD | `Not started` | - |
| 5. Result unknown / recovery | 0/TBD | `Not started` | - |
| 6. Cross / release audit | 0/TBD | `Not started` | - |

Phase 按 1 → 2 → 3 → 4 → 5 → 6 顺序推进。紧急插入只能通过显式 decimal phase、canonical impact scan 与 Integrator 裁决完成。
