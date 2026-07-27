# Mini Agent｜GSD 派生 Requirement Mapping

> **DERIVED / NON_NORMATIVE**
> 本文件只把 canonical Case ID 映射到执行 Phase，不复制 Case 语义，也不拥有生命周期状态。Case 期望、Critical failure、Grader 与激活顺序以 [P0 Eval Coverage Matrix](../docs/evaluation/p0-eval-coverage-matrix.md) 为准；业务成功语义以 [业务能力说明](../docs/business-capabilities.md) 为准。

## 使用规则

- 复选框表示 GSD 执行追踪，不等于 Case 已变为 `EXECUTABLE`、`REGRESSION_GATE` 或已经通过。
- 只有 post-execution quality gate 完成、canonical owner 已依据可复现证据更新生命周期后，Integrator 才能手工同步勾选对应条目。
- 禁止调用 `requirements.mark-complete` 或其他自动 lifecycle API；Roadmap / State progress 也只能由 Integrator 根据 Summary、PR 与硬证据手工同步。
- Phase 2–6 只是 Coverage Matrix Cycle 的顺序映射；在 scoped implementation owner 出现前，不生成或推断实现细节。
- 任何冲突都按 [GOVERNANCE.md](GOVERNANCE.md) 阻断并交由对应 specialized owner 裁决，绝不按文件更新时间覆盖。

## Phase 1｜Cycle 1：第一最薄 E2E-01（W2 RUNTIME / INFRA / EVAL PLANNING）

- [ ] **E2E01-01** — 按 Coverage Matrix 与 [Thin Slice Spec](../docs/implementation/e2e01-thin-slice-implementation-spec.md) 取得可复现的 Component、Trajectory 与 E2E 证据。
- [ ] **E2E01-04** — 按同一 owners 取得安全等价、最小披露与禁止私有 Observation 的可复现证据。

当前八个 numbered slot 中 `01-01`–`01-04`与`01-07`已有同名 evidence-indexed Summary，`01-05/06` slots由replacement `01-05R/06R` Summaries提供完成证据；插入式 dependency Packet `01-04D/E/F/G/H/07A/07B` 也均已完成并合并。01-07B通过planning/status PR #42–#43与feature PR #44关闭Eval Case/Script/output oracle、canonical boundary与variant-scoped安全因果precedence，merge为`ccdafe87...`；post-merge通过762项Plan focused、40项migration、1493项默认离线测试（1项baseline deselected）与Graphify gate。historical Runtime / Infra Plans与PR #28/#30继续冻结为不可复用证据。01-07C planning PR #46与Project Direction owner alignment PR #47已经reviewed merge；active owner不再复制易漂移的GSD进度计数。01-07C与01-07G现已分别签发固定base `3f0753f7...`、独立单owner文件的Plan，但两个feature execution都尚未开始。仍待关闭的owner blocker包括Request Understanding semantic/mapping/codec/Core闭环、P0 `get_order` source-version ruling与独立Core/Order DTO consumer、Application exact-Run Evidence Port、Infra strict reader、Eval mapper、invalid-RU Pydantic/trusted-field到`INPUT_INVALID`的Scripted/Qwen/Runtime分类闭环，以及credentialed Qwen runner。本planning PR reviewed merge后按`{01-07C RU semantic ruling, 01-07G Thin Slice source-version ruling} → {01-07D RU exact mapping, 01-07H Core/Order DTO} → {01-07E persistence codec, 01-07F RU Core} → 01-07I Application Evidence Port / Provider failure contract → 01-07J Runtime / INPUT_INVALID mapping → {01-07K Infra reader, 01-07L Eval mapper / Scripted-Qwen consumers} → 01-08 → 01-08A`逐级执行和签发，每组必须由Integrator全部串行合并形成共同exact barrier后才进入下一组。I/J/L分别通过records/ports contract test、Runtime Component test与Scripted/Qwen/real-Runtime Eval test证明fresh raw-free signal、无Task/Gate/Tool的safe stop及协议/Presentation分类不漂移。它们复用既有owner slots，所以新增依赖后目标Packet口径完成`14/28`，磁盘上正式签发18个Plan（7 numbered + 9 inserted D–H/07A/07B/07C/07G + 2 replacements）；`01-07D–01-07F`、`01-07H–01-07L`与`01-08/01-08A`仍未签发。若owner裁决要求额外migration、全局Memory version升级或新的外部契约，必须新增Packet并更新分母。Canonical lifecycle与本文件复选框保持`0/8`。

## Phase 2｜Cycle 2：完成 E2E-01（PLANNED MAPPING ONLY）

- [ ] **E2E01-02**
- [ ] **E2E01-03**
- [ ] **E2E01-05**
- [ ] **E2E01-06**

`E2E01-05` 必须等待 `get_order` 与 `get_shipment` 同时可用，并与确实需要物流的配对 Case 一起验证；第一最薄切片中未注册 `get_shipment` 不是该 Case 的通过证据。

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
| `E2E01-01` | Phase 1 | Coverage Matrix Cycle 1 + Thin Slice Spec | Pending |
| `E2E01-04` | Phase 1 | Coverage Matrix Cycle 1 + Thin Slice Spec | Pending |
| `E2E01-02` | Phase 2 | Coverage Matrix Cycle 2 | Pending |
| `E2E01-03` | Phase 2 | Coverage Matrix Cycle 2 | Pending |
| `E2E01-05` | Phase 2 | Coverage Matrix Cycle 2 | Pending |
| `E2E01-06` | Phase 2 | Coverage Matrix Cycle 2 | Pending |
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
