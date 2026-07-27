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

当前八个 numbered Plan 中 `01-01`–`01-04` 已形成 evidence-indexed Summary；插入式 dependency Packet `01-04D/E/F/G` 也均已完成并合并。`01-05` Runtime、`01-06` Infra、`01-07` Eval 的planning PR #26 reviewed head `2922308b...`已取得两个Codex只读Reviewer的`PASS`并merge为`968b4a9...`；Reviewer记录见PR #26 [canonical evidence](https://github.com/weijie567/mini-agent/pull/26#issuecomment-5086174316)与[security/process evidence](https://github.com/weijie567/mini-agent/pull/26#issuecomment-5086174609)，它们不是GitHub Reviews API formal approvals。三个execution Worktree随后从共同 exact base `c35687dafa3881bb322d91515068d8d39be79df6`创建；Runtime / Infra / Eval已分别发布Draft PR #28/#30/#29，但independent feature review、latest-integration overlay与serial merge仍待完成。实际 Packet完成口径保持`8/12`，canonical lifecycle与本文件复选框保持`0/8`。

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
