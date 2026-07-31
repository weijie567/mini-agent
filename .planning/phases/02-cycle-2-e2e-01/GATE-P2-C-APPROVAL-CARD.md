# Gate P2-C｜审批卡

> **USER APPROVAL REQUIRED / IMPLEMENTATION NOT STARTED**
>
> 本卡只请求激活 Phase 2 initial integration base，并执行当前已具备真实 exact
> base 的 `02-01` 与 `02-03`。它不批准 `02-02` 或任何后续 Packet。

## 1. 已完成前置条件

| 项目 | 精确证据 |
|---|---|
| Gate P2-A master Plan | PR #203；`B_C2_PLAN_APPROVED = 2879f5226a073051d1550fe079b4a427c1ec8cb1` |
| `02-00` planning provenance | PR #204 merge successor `74db04a938f725f1e4bbf113b23de613dbbb433e` |
| `02-00` zero-code correction | PR #205 merge successor `4dc6dc95de81080fb3b651bc2f0026fb046fd9f8` |
| `B_C2_OWNER_ALIGNED` tree | `521ac2c7611b20683089ab41a74d07c9a2bb8fc7` |
| `C2-BLOCK-02` | `CLOSED`；model-script path 已对齐为 `evals/model_scripts/` |
| Phase 2 integration branch | `NOT_CREATED` |
| `B_C2_START` | `NOT_FROZEN` |
| Phase 2 功能代码 | `NOT_STARTED` |

## 2. 本轮 exact Packet

### `02-01` — Core business contracts

- Plan：[02-01-PLAN.md](02-01-PLAN.md)
- reviewed source head：`4d75811502fb297e5de67a685d007e9f0b172109`
- exact Plan blob：`a2c957cb97b9b0bedeb7fff0dfd7c2865f0d7748`
- implementation base：`4dc6dc95de81080fb3b651bc2f0026fb046fd9f8`
- future branch：`codex/e2e01-cycle2-core-business-contracts`（`NOT_CREATED`）
- owned files：两个新 Core module + 两个 component test files，详见 Packet。
- contract disposition：只实现已批准的 D1/D2/D5/D6/D7；不创建 Tool、Memory、
  Adapter、Persistence、Runtime 或 Eval artifact。
- independent exact-file review：`PASS / 0 BLOCK / 0 HIGH / 0 MEDIUM / 0 LOW / 0 INFO`。

### `02-03` — Run / Trace v2 Core contract

- Plan：[02-03-PLAN.md](02-03-PLAN.md)
- reviewed source head：`44692b0c157d2ffb5377790762530c2234a2f8df`
- exact Plan blob：`0ec86cc13f0cb352247521259a8e28c8fc4768a7`
- implementation base：`4dc6dc95de81080fb3b651bc2f0026fb046fd9f8`
- future branch：`codex/e2e01-cycle2-run-trace-v2-contract`（`NOT_CREATED`）
- owned files：`trace.py` + 一个专门 component test file，详见 Packet。
- contract disposition：实现批准的 OA-10 / stop vocabulary；不改变 shared
  `TraceEvent` field set，不实现 Persistence、Mapper、finalizer 或 retry executor。
- independent exact-file review：`PASS / 0 BLOCK / 0 HIGH / 0 MEDIUM / 0 LOW / 0 INFO`。

## 3. 为什么本轮没有 `02-02` exact Packet

`SearchOrdersObservation` 和 `ShipmentObservation.normalized_value` 必须直接消费
`02-01` 的 typed business projections。当前这些 types 在
`B_C2_OWNER_ALIGNED` 中尚不存在，因此无法填写真实 `base_sha`。

禁止用以下方式绕过：

- 在 Memory 重复定义 business types；
- 弱化为 `dict` / `Any`；
- 使用 synthetic overlay 冒充 reviewed dependency；
- 扩大 `02-02` allowlist 修改 `02-01` owned files。

`02-02` 维持 `NOT_CREATED / BLOCKED_UNTIL_B_C2_W1A`，不计入本轮批准。

## 4. 请求批准的精确动作

用户批准后，Integrator 只能按以下顺序执行：

1. 合并通过 final exact-head review 的本 planning PR。
2. 从 exact `B_C2_OWNER_ALIGNED` 创建 `integration/e2e01-cycle2`。
3. 立即证明 integration head/tree 与 owner-aligned SHA/tree 完全相同，并冻结：

   ```text
   B_C2_START = 4dc6dc95de81080fb3b651bc2f0026fb046fd9f8
   tree = 521ac2c7611b20683089ab41a74d07c9a2bb8fc7
   ```

4. equality preflight 通过后，创建 `02-01` / `02-03` 的独立 feature branch 与
   Worktree，最多两个 writer 并行。
5. 两个 feature 均须 Draft PR、exact-head review 与 latest-integration overlay；
   `02-03` 先 merge 为 `B_C2_TRACE`，`02-01` 后 overlay/merge 为 `B_C2_W1A`。
6. 到此停止并返回用户：只有这时才准备 `02-02` exact Plan / Task Packet 和下一张
   审批卡。

任一 SHA/tree equality、allowlist、review 或 overlay gate 失败即停止，不自动
rebase、不扩大范围、不猜测新 base。

## 5. 本轮明确不批准

- 不预先批准或执行 `02-02`。
- 不启动 W2 或 `02-04..18`。
- 不创建 migration、Adapter、Tool registration、Runtime orchestration、Eval
  artifact、Harness Result 或 lifecycle transition。
- 不改变 Phase 1 `get_order` contract 或历史 release evidence。
- 不直接 push `main` 或 active integration branch。

## 6. 建议批准语句

```text
批准合并本 Gate P2-C planning PR。
批准从 exact B_C2_OWNER_ALIGNED
4dc6dc95de81080fb3b651bc2f0026fb046fd9f8
创建 integration/e2e01-cycle2，并在 SHA/tree equality preflight 通过后冻结为
B_C2_START。

批准按 reviewed exact Packet 执行 02-01 与 02-03，最多两个 writer 并行；
02-03 先 merge，02-01 latest-overlay 后 merge。

不批准 02-02 或后续 Packet；B_C2_W1A 形成后必须重新提交 02-02 exact Packet
和审批卡。
```
