# Mini Agent｜GSD 派生 Requirement Mapping

> **DERIVED / NON_NORMATIVE**
> 本文件只把 canonical Case ID 映射到执行 Phase，不复制 Case 语义，也不拥有生命周期状态。Case 期望、Critical failure、Grader 与激活顺序以 [P0 Eval Coverage Matrix](../docs/evaluation/p0-eval-coverage-matrix.md) 为准；业务成功语义以 [业务能力说明](../docs/business-capabilities.md) 为准。

## 使用规则

- 复选框表示 GSD 执行追踪，不等于 Case 已变为 `EXECUTABLE`、`REGRESSION_GATE` 或已经通过。
- 只有 post-execution quality gate 完成、canonical owner 已依据可复现证据更新生命周期后，Integrator 才能手工同步勾选对应条目。
- Phase 1已满足上述证据前提并完成release transition：用户继续接受有界`RTA-D01`，reviewed PR #199已squash merge到`main`（`f15320e3...`），Integrator据此手工同步completion checkbox。
- 禁止调用 `requirements.mark-complete` 或其他自动 lifecycle API；Roadmap / State progress 也只能由 Integrator 根据 Summary、PR 与硬证据手工同步。
- Phase 2 已有 scoped active implementation owner、master Plan 与 exact Task Packet；
  W1–W3R 已 reviewed merge。W4 `02-06/13/08` 又由 PR #229/#230/#232 依次
  reviewed merge，当前 integration 为 `B_C2_RU_ROUTING = d0f37e2d...` / tree
  `252a092b...`。`02-09` preflight 暴露的 recovery owner gap 已由 PR #231 owner
  ruling关闭并拆为 `02-09R1/R2/R3`；原 `02-09` 保持 clean、blocked。当前只把
  `02-09R1` 从真实 `B_C2_RU_ROUTING` 重冻结并送独立 planning review；不得猜测
  `02-09R2/R3` 或重冻结后 `02-09` 的未来 SHA。Phase 3–6 只保留 Coverage
  Matrix Cycle 的顺序映射，在各自 owner 出现前不生成或推断实现细节。
- 任何冲突都按 [GOVERNANCE.md](GOVERNANCE.md) 阻断并交由对应 specialized owner 裁决，绝不按文件更新时间覆盖。

## Phase 1｜Cycle 1：第一最薄 E2E-01（W2 RUNTIME / INFRA / EVAL PLANNING）

- [x] **E2E01-01** — 可复现的 Component、Trajectory 与 E2E evidence已完成并进入`REGRESSION_GATE`；Phase 1 release transition已完成。
- [x] **E2E01-04** — 安全等价、最小披露与禁止私有 Observation evidence已完成并进入`REGRESSION_GATE`；Phase 1 release transition已完成。

当前八个numbered Plan与全部42个implementation targets均有reviewed merge和自动化反馈证据。01-07S/U/X/T/W/V已形成`B_RU_V2_CONTRACT = 5c84e0e...`；01-08、Composition handoff与01-08A已形成`B_01_08 = b8a2cf3...`、`B_01_08A_COMPOSITION = c59eaea...`和`B_01_08A = 11d6d08...`。PR #172–#186完成review / fix、Validation、controlled UAT、Eval activation / Results / regression gate与mandatory Eval / Security re-review。六个authenticated physical Case的全部16 variants为`16 PASS / 0 FAIL / 0 Critical failure / 0 execution failure`，canonical full为`2007 passed, 1 deselected, 12 warnings`。本文件不把真实Qwen `NOT_RUN`、无canonical产品启动或无production readiness伪装成已完成；它们也不是本次scoped deterministic offline Phase 1 requirement的隐藏Task Packet。用户已明确暂时停用Graphify；后续不运行、不引用，也不把freshness作为门禁。

## Phase 2｜Cycle 2：完成 E2E-01（CONTRACT ACTIVE / B_C2_RU_ROUTING / 02-09R1 PLANNING）

- [ ] **E2E01-02**
- [ ] **E2E01-03**
- [ ] **E2E01-05**
- [ ] **E2E01-06**

`E2E01-05` 必须等待 `get_order` 与 `get_shipment` 同时可用，并与确实需要物流的配对 Case 一起验证；第一最薄切片中未注册 `get_shipment` 不是该 Case 的通过证据。

Cycle 2 scoped contract 已激活；W1–W3R 与 W4 `02-06/13/08` 已 reviewed merge，
并依次形成 `B_C2_CODEC = 6514c7d0...`、`B_C2_EVAL_BUNDLE = 15d3bd41...` 与
`B_C2_RU_ROUTING = d0f37e2d...`。旧 `02-02` head `ecfad7e...` 保持隔离。Core /
Tool / Application contracts 与这些 W4 leaf contracts 均不构成四个 Case 的执行
证据或 lifecycle 推进。`02-09` 的 recovery owner gap 已由 PR #231 规范化为
`02-09R1/R2/R3` 前置链；当前仅 `02-09R1` exact Plan 进入 review，原 `02-09`
没有源码 commit。四个 Case继续保持`CONTRACT_DEFINED`，
上方 checkbox 继续未勾选；当前没有 Phase 2 Eval artifact、Case activation、完整
E2E-01 evidence，也没有 Runtime / Tool composition cutover。

## Phase 3｜Cycle 3a：RAG、Evidence 与资格判断（PLANNED MAPPING ONLY）

- [ ] **E2E02-01**
- [ ] **E2E02-02**
- [ ] **E2E02-03**

本 Phase 还依赖 Coverage Matrix 定义的 `G-RAG-INFRA`，但本文件不重述 RAG 或 Evidence 语义。

## Phase 4｜Cycle 3b：受控模拟退款动作（PLANNED MAPPING ONLY）

- [ ] **E2E02-04**
- [ ] **E2E02-05**
- [ ] **E2E02-06**

`create_refund` 只表示模拟退款，不表示真实支付渠道退款或到账。

## Phase 5｜Cycle 3c：未知结果与跨会话恢复（PLANNED MAPPING ONLY）

- [ ] **E2E02-07**
- [ ] **E2E02-08**

## Phase 6｜Cycle 4：贯通与 P0 Release Audit（PLANNED MAPPING ONLY）

- [ ] **CROSS-01**
- [ ] **P0-RELEASE-AUDIT** — 派生执行门禁：审计 P0 scope 内 Case、Critical failure、Trace、回归证据与未决风险；不新增业务 Case，也不自行更新 canonical lifecycle。

## Traceability

| Requirement | Phase | Canonical source | GSD 状态 |
|---|---:|---|---|
| `E2E01-01` | Phase 1 | Coverage Matrix Cycle 1 + Thin Slice Spec | `REGRESSION_GATE / PHASE_1_RELEASE_COMPLETE` |
| `E2E01-04` | Phase 1 | Coverage Matrix Cycle 1 + Thin Slice Spec | `REGRESSION_GATE / PHASE_1_RELEASE_COMPLETE` |
| `E2E01-02` | Phase 2 | Coverage Matrix Cycle 2 + Cycle 2 Spec | `CONTRACT_DEFINED / B_C2_RU_ROUTING / 02-09R1_PLANNING` |
| `E2E01-03` | Phase 2 | Coverage Matrix Cycle 2 + Cycle 2 Spec | `CONTRACT_DEFINED / B_C2_RU_ROUTING / 02-09R1_PLANNING` |
| `E2E01-05` | Phase 2 | Coverage Matrix Cycle 2 + Cycle 2 Spec | `CONTRACT_DEFINED / B_C2_RU_ROUTING / 02-09R1_PLANNING` |
| `E2E01-06` | Phase 2 | Coverage Matrix Cycle 2 + Cycle 2 Spec | `CONTRACT_DEFINED / B_C2_RU_ROUTING / 02-09R1_PLANNING` |
| `E2E02-01` | Phase 3 | Coverage Matrix Cycle 3（先 Evidence / judgment） | Pending |
| `E2E02-02` | Phase 3 | Coverage Matrix Cycle 3（先 Evidence / judgment） | Pending |
| `E2E02-03` | Phase 3 | Coverage Matrix Cycle 3（先 Evidence / judgment） | Pending |
| `E2E02-04` | Phase 4 | Coverage Matrix Cycle 3（再 action / idempotency） | Pending |
| `E2E02-05` | Phase 4 | Coverage Matrix Cycle 3（再 action / idempotency） | Pending |
| `E2E02-06` | Phase 4 | Coverage Matrix Cycle 3（再 action / idempotency） | Pending |
| `E2E02-07` | Phase 5 | Coverage Matrix Cycle 3（最后 failure / recovery） | Pending |
| `E2E02-08` | Phase 5 | Coverage Matrix Cycle 3（最后 failure / recovery） | Pending |
| `CROSS-01` | Phase 6 | Coverage Matrix Cycle 4 | Pending |
| `P0-RELEASE-AUDIT` | Phase 6 | 派生执行 gate | Pending |
