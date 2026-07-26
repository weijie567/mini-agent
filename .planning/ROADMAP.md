# Mini Agent｜P0 GSD 派生执行 Roadmap

> **DERIVED / NON_NORMATIVE**
> 本 Roadmap 只派生执行顺序，不拥有产品、架构、契约、Eval 语义或 Case 生命周期。来源是 [P0 Eval Coverage Matrix](../docs/evaluation/p0-eval-coverage-matrix.md)、[业务能力说明](../docs/business-capabilities.md)、[第一最薄切片 Spec](../docs/implementation/e2e01-thin-slice-implementation-spec.md) 与[多 Agent 实施计划](../docs/implementation/e2e01-thin-slice-multi-agent-plan.md)。专门 owner 只在自身范围内优先，绝不采用 “newest wins”。

## Lifecycle Control

- 一个 GSD Plan 对应一个精确 Task Packet。Packet 可含多个原子 task，但不得跨 repository、branch、Worktree、writer 或 ownership boundary。
- Stock `roadmap.update-plan-progress`、`requirements.mark-complete`、`phase.complete` 与任何 transition / auto lifecycle mutation 当前禁用。
- Checkbox 和 Progress 只由 Integrator 在 Summary、PR、机械证据、post-execution quality gate 与 canonical lifecycle owner 更新完成后手工同步。
- `parallelization=false` 与 `workflow.use_worktrees=false` 只禁用 GSD 自管并行 / Worktree；Codex 多 Agent 仍使用 Integrator 在 workflow 外预建的独立 Worktree / feature branch。

## Overview

P0 依照 Coverage Matrix 的 Cycle 1–4 分成六个连续 Phase。只有 Phase 1 active，但 activation 仍 paused / not effective；Phase 2–6 在对应 scoped canonical contract 出现并通过冲突审查前，只保留 Case ID 与 gate mapping，不生成实现 Plan。

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

**Status:** `ACTIVE / ACTIVATION_PAUSED`

**Goal:** 为 canonical `E2E01-01/04` 取得可复现的源码、HTTP、Trace、结构化 Eval 与安全门禁证据。

**Depends on:** W1 骨架、W2.0 persistence contract freeze，以及 activation final exact-head `PASS` / merge。

**Requirements:** `E2E01-01`, `E2E01-04`

**Success Criteria:**

1. `E2E01-01` 的 canonical acceptance criteria 具有可复现 Component、Trajectory 与 HTTP E2E 证据。
2. `E2E01-04` 两个变体具有 canonical owner 要求的安全等价与禁止披露证据。
3. 适用 Critical failure 为零，结构化 Eval Result、Trace 与版本 manifest 可追溯；缺失证据不得以 GSD 状态代替。
4. Exact integration head 通过 canonical 命令、独立 review、validation、适用的 Eval / Security audit 与 UAT。

**Plans:** 6 plans（当前只是 execution / planning slots；实际 PLAN 文件须经受控 import / plan artifact PR 创建）

Plans:

- [ ] 01-01: persistence schema/version canonical-owner decision（串行）
- [ ] 01-02: W2.0b implementation slot（`BLOCKED`；仅在 01-01 exact merge 后按裁决生成 Task Packet）
- [ ] 01-03: W2 Runtime（依赖 01-02 merge）
- [ ] 01-04: W2 Infra（依赖 01-02 merge）
- [ ] 01-05: W2 Eval（依赖 01-02 merge）
- [ ] 01-06: W3 Composition Root 与纵向集成（Integrator 串行）

#### Phase 1 Execution Gates

| Gate | 工作 | 启动条件 |
|---|---|---|
| Activation | activation remediation / review / merge | final exact-head review `PASS`；本 Roadmap 才生效 |
| 01-01 | canonical-owner alignment PR | Integrator 在 workflow 外预建 exact Task Packet Worktree / branch |
| 01-02 | W2.0b implementation | 01-01 exact-head PR 已合并；Task Packet 只实现已裁决 contract |
| 01-03/04/05 | Runtime / Infra / Eval 并行 | Integrator 从同一 01-02 merge SHA 预建三个 ownership 不重叠的 Worktree；不调用 stock execute |
| 01-06 | W3 串行集成 | 三个 W2 feature PR 逐个审查、重验并合并 |
| Post-execution quality | review / fix / validation / Eval / Security / UAT / release decision | 01-06 exact integration head 已形成；本 gate 不计入 Plan count |

#### Post-execution Quality Gate（不是 Plan）

1. 在 exact-integration-SHA review-artifact Worktree 中运行受控 `gsd-code-review --files=<exact list>`；只允许写 Phase `REVIEW.md`。
2. Findings 只能在 Integrator 预建的专用 fix Worktree / feature branch 中处理；前后比较 base、head、allowlist、changed files 与 commits。
3. Validation 补缺只能在预建 validation Worktree / branch 中处理，并按同样 diff containment gate 审查。
4. `gsd-eval-review` 只有派生 AI / Eval mapping 明确引用 canonical Eval owner 后才构成 gate；`gsd-secure-phase` 只有完整 `<threat_model>` 映射项目安全不变量后才构成 gate。
5. `gsd-verify-work` 只产出 UAT artifact，必须在 gap / transition / execute 路由前停止。
6. Quality 全部通过后，先由 canonical Coverage Matrix owner依据硬证据更新 Case lifecycle。
7. Integrator 再手工同步 derived Requirements / Roadmap / State；不得调用自动 lifecycle API。
8. Release 使用显式 GitHub `head=integration/e2e01-thin`、`base=main` 创建 PR；不调用 `gsd-ship`。

### Phase 2: Cycle 2｜完成 E2E-01

**Status:** `PLANNED_MAPPING_ONLY`

**Goal:** 按 Coverage Matrix Cycle 2 覆盖 `E2E01-02/03/05/06`。

**Depends on:** Phase 1

**Requirements:** `E2E01-02`, `E2E01-03`, `E2E01-05`, `E2E01-06`

**Success Criteria:**

1. 四个 Case 的 canonical acceptance criteria 均有可复现证据。
2. `E2E01-05` 与确实需要 `get_shipment` 的配对 Case 在同一可用工具集中验证。
3. 第一版 Trajectory / E2E Baseline 依 canonical Eval owner 运行并保存结果。

**Plans:** `TBD`；等待 Phase 1 反馈与 scoped implementation contract。

### Phase 3: Cycle 3a｜RAG、Evidence 与资格判断

**Status:** `PLANNED_MAPPING_ONLY`

**Goal:** 通过 `G-RAG-INFRA`，并按 Coverage Matrix 覆盖 `E2E02-01/02/03`。

**Depends on:** Phase 2

**Requirements:** `E2E02-01`, `E2E02-02`, `E2E02-03`

**Success Criteria:**

1. `G-RAG-INFRA` 的 canonical gate 有可复现结果。
2. 三个 Case 的 canonical Evidence 与资格判断标准均有 Component、Trajectory 与 E2E 证据。
3. Evidence 无效或结论不可执行时，适用 Critical failure 保持为零。

**Plans:** `TBD`；等待 RAG / E2E-02 scoped implementation contract。

### Phase 4: Cycle 3b｜受控模拟退款动作

**Status:** `PLANNED_MAPPING_ONLY`

**Goal:** 按 Coverage Matrix 覆盖 `E2E02-04/05/06`。

**Depends on:** Phase 3

**Requirements:** `E2E02-04`, `E2E02-05`, `E2E02-06`

**Success Criteria:**

1. 确认、ActionPolicy、失效确认与幂等的 canonical criteria 均有可复现证据。
2. `create_refund` 只执行模拟退款，输出不声称真实支付渠道退款或到账。
3. 适用 Critical failure 为零。

**Plans:** `TBD`；等待动作阶段 scoped implementation contract。

### Phase 5: Cycle 3c｜未知结果与跨会话恢复

**Status:** `PLANNED_MAPPING_ONLY`

**Goal:** 按 Coverage Matrix 覆盖 `E2E02-07/08`。

**Depends on:** Phase 4

**Requirements:** `E2E02-07`, `E2E02-08`

**Success Criteria:**

1. `RESULT_UNKNOWN` 恢复与禁止重复执行的 canonical criteria 有可复现证据。
2. 新 Conversation 恢复仍重新通过身份、资源、Observation、Evidence 与确认校验。
3. 适用 Critical failure 为零。

**Plans:** `TBD`；等待故障 / 恢复 scoped implementation contract。

### Phase 6: Cycle 4｜跨场景贯通与 P0 Release Audit

**Status:** `PLANNED_MAPPING_ONLY`

**Goal:** 按 Coverage Matrix Cycle 4 覆盖 `CROSS-01`，并完成 P0 scope 的发布证据审计。

**Depends on:** Phase 5

**Requirements:** `CROSS-01`, `P0-RELEASE-AUDIT`

**Success Criteria:**

1. `CROSS-01` 的 canonical 多目标、依赖、条件与确认标准有可复现证据。
2. P0 scope 内所有应激活 Case、Critical failure、Trace、回归与未决风险完成 evidence-backed audit。
3. Integration → `main` PR 只在完整 quality gate 通过后进入 merge 决策。

**Plans:** `TBD`；等待前五个 Phase 的实测反馈。

## Progress

| Phase | Plans Complete | Status | Completed |
|---|---:|---|---|
| 1. 第一最薄 E2E-01 | 0/6 | `Activation remediation / paused` | - |
| 2. 完成 E2E-01 | 0/TBD | `Not started` | - |
| 3. RAG / Evidence / judgment | 0/TBD | `Not started` | - |
| 4. Simulated refund action | 0/TBD | `Not started` | - |
| 5. Result unknown / recovery | 0/TBD | `Not started` | - |
| 6. Cross / release audit | 0/TBD | `Not started` | - |

Phase 按 1 → 2 → 3 → 4 → 5 → 6 顺序推进。紧急插入只能通过显式 decimal phase、canonical impact scan 与 Integrator 裁决完成。
