# E2E-01 Cycle 2｜Codex 多 Agent 实施计划

更新日期：2026-08-01

状态：`NON_NORMATIVE / PLAN_APPROVED / W4_BATCH_A_MERGED / 02-09_OWNER_GAP_RULING`

规划输入：`main@b96fe8adf8ce4bcadbdf2cf008e28be4ff9aa5a3`

批准证据：planning PR
[#203](https://github.com/weijie567/mini-agent/pull/203) 已于 2026-07-31
squash merge；`B_C2_PLAN_APPROVED =
2879f5226a073051d1550fe079b4a427c1ec8cb1`，tree
`d5ded99bb0439fb57bbb4d6057fbda7a12b21fdf`。

> 本文是 Phase 2 的 phase-level master execution Plan。它只拥有未来 GSD
> Plan / Task Packet 的拆分、依赖、文件 ownership proposal、Wave、门禁、交接和
> 回滚顺序；不拥有产品、架构、业务、Tool、Memory、Eval 或 Case lifecycle 语义。
>
> 本文不是任一 implementation Task Packet。本文已通过独立 exact-head review、
> 用户 Gate P2-A 批准并经 planning PR 合并；Integrator 按真实 dependency barrier
> 分批准备“一份 GSD Plan + 一个 exact Task Packet”。历史首份
> [`02-00`](../../.planning/phases/02-cycle-2-e2e-01/02-00-PLAN.md) 与 W1–W3
> `02-01..05` 均已 reviewed merge。W4 preflight 已确认三个跨 owner 的 contract
> 缺口；用户于 2026-08-01 明确授权“有问题先修复完成后开始 W4”。因此先增加
> `02-02R/02-04R/02-05R` 三个一对一 correction Packet。三者已reviewed串行完成；
> PR #227 的实际 merge successor
> `B_C2_W4_READY = 5f2fa6d28575bcdcaf8a4c650469acc7dd19b7de` / tree
> `174fbebcfa622336ffeade113cfae74a5611edae` 与 reviewed overlay相等。W4
> `02-06/08/09/13` 已从该同一 product barrier重冻结。Batch A 的 02-06 与 02-13
> 已分别经 bounded feature/residual/overlay review 和 PR #229/#230 串行 merge，
> 当前 integration successor 为 `15d3bd41f83b0ae42e01aae48e0682d1d1ba66ed` / tree
> `f91732eabf3672961681383a92cf578b999be604`。Batch B 的 02-08 正在原 Packet 内执行；
> 02-09 preflight 后确认 shared recovery contract 无法表示 unfinished parent-only
> terminal、durable recovery decision child 与 `RETRY_SCHEDULED + budget exhausted`
> terminal，因此 source 保持 clean，先增加 `02-09R1/R2/R3` 三个 single-writer
> correction Packet，再从真实 correction barrier 重冻结 02-09。
>
> `integration/e2e01-cycle2` 已在 historical Gate P2-C 从 exact `B_C2_START`
> 创建。后续仍只有 exact Packet、planning review 与当前 user directive 都满足后，
> 才创建对应 feature branch / Worktree；Plan、artifact 或测试的存在不推进 Case
> lifecycle。

## 1. Authority and scope

实施必须服从：

- [Business Capabilities](../business-capabilities.md)；
- [PROJECT_DIRECTION.md](../../PROJECT_DIRECTION.md)；
- [Intent Design Reference](../architecture/intent-design-reference.md)；
- [Tool Calling Design Reference](../architecture/tool-calling-design-reference.md)；
- [Memory Design Reference](../architecture/memory-design-reference.md)；
- [Agent Evaluation Strategy](../evaluation/agent-evaluation-strategy.md)；
- [P0 Eval Coverage Matrix](../evaluation/p0-eval-coverage-matrix.md)；
- [Cycle 2 Implementation Spec](e2e01-cycle2-implementation-spec.md)；
- [Dependency / Ownership / Risk Map](e2e01-cycle2-dependency-ownership-risk-map.md)；
- [GSD Governance](../../.planning/GOVERNANCE.md) 与项目级 `AGENTS.md`。

冲突时从 canonical owner 出发做影响分析；不得使用“Plan 更新”或“实现更方便”
覆盖 owner。任何 D1–D8、R01–R18、Mapper row、record shape、failure code、
freshness / retry budget、Case mapping 或 Critical failure 的变化都先暂停并走
contract change。

### 1.1 In scope

- `E2E01-02`：自然语言唯一定位本人近期订单。
- `E2E01-03`：多候选最小摘要、当前候选集和跨轮 ordinal 绑定。
- `E2E01-05`：同一三工具 RegistrySnapshot 中的动态 Tool 选择配对证据。
- `E2E01-06`：Shipment freshness、refresh、有限重试、deterministic failure 与
  `BLOCKED / NEED_HUMAN`。
- 五个新逻辑 record / projection、六个 v2 record cutover、owner-scoped reader、
  atomic writer 与 recovery。
- Component、14 longitudinal variants、13 mandatory Trajectory cases、真实 HTTP
  E2E、Phase 1 回归与 post-execution quality gates。

### 1.2 Out of scope

- RAG、Policy Evidence、退款资格、`create_refund`、confirmation、ActionPolicy、
  idempotency claim / key、Action Ledger write 与 `RESULT_UNKNOWN` side-effect
  recovery。
- 多 active Package、真实电商 / 物流 / 支付 / 退款系统。
- UI、通用语义搜索、Embedding、并行 ToolCall、streaming tool arguments。
- 修改 Phase 1 `get_order` Schema、source version、500ms / one-attempt contract。
- 新第三方依赖、canonical product startup、lint、type-check 或 build 命令，除非另有
  独立 owner 和批准。
- 在 Gate P2-C 前创建 implementation 资源。

## 2. Planning status

| Item | Current state |
|---|---|
| Scoped contract | `CONTRACT_ACTIVE / READY_FOR_PLANNING` |
| Case lifecycle | `E2E01-02/03/05/06 = CONTRACT_DEFINED` |
| Master Plan | `PLAN_APPROVED / PR #203 MERGED` |
| Future GSD Plans | `02-00..05 + W3R COMPLETE / 02-06+13 MERGED / 02-08 IN PROGRESS / 02-09 BLOCKED FOR R1-R3` |
| Task Packets | `W4 BATCH A REVIEWED MERGE / 02-09 OWNER GAP CONFIRMED / R1-R3 PLAN PENDING` |
| Proposed Plan / Packet slots / Waves | `25 / 15`（原 `02-00..18` + `02-02R/04R/05R` + `02-09R1/R2/R3` / 原 `W0..W12` + `W3R/W4R`） |
| Planning input SHA | `b96fe8adf8ce4bcadbdf2cf008e28be4ff9aa5a3` |
| `B_C2_PLAN_APPROVED` | `2879f5226a073051d1550fe079b4a427c1ec8cb1` / tree `d5ded99bb0439fb57bbb4d6057fbda7a12b21fdf` |
| Initial implementation base | `B_C2_START = 4dc6dc95de81080fb3b651bc2f0026fb046fd9f8` / tree `521ac2c7611b20683089ab41a74d07c9a2bb8fc7` |
| Integration branch | `integration/e2e01-cycle2 / ACTIVE / 15d3bd41f83b0ae42e01aae48e0682d1d1ba66ed` |
| GSD config branch mapping | `integration/e2e01-cycle2 / ACTIVE` |
| `02-00` execution branch / Worktree | `COMPLETE / REVIEWED MERGE` |
| Integration / code feature branches / Worktrees | `W1..W3R + W4 Batch A COMPLETE；02-08 ACTIVE；02-09 CLEAN/BLOCKED` |
| Writer assignments | `02-08 writer ACTIVE；02-09 writer PAUSED；Integrator owner-ruling single writer ACTIVE` |
| Execution concurrency | approved ceiling `2` writers；当前 writers `2`（02-08 + owner ruling） |

### 2.1 Gate P2-A planning PR exact scope

Gate P2-A planning PR #203 只包含以下七个文件：

- `docs/implementation/e2e01-cycle2-dependency-ownership-risk-map.md`
- `docs/implementation/e2e01-cycle2-multi-agent-plan.md`
- `.planning/config.json`
- `.planning/GOVERNANCE.md`
- `.planning/PROJECT.md`
- `.planning/ROADMAP.md`
- `.planning/STATE.md`

其 reviewed exact head 为
`17743d1a78e015b7f2d736bf676762d000f4a475`，merge successor 即上述
`B_C2_PLAN_APPROVED`。`.planning/ACTIVATION.md`、Phase 1 Plans / Summaries、
canonical contract、源码、
测试、migration、Eval artifact 与 Case lifecycle 均不得修改。Phase 1 的
`integration/e2e01-thin` 记录保持历史原文；本段最后一句只描述 Gate P2-A 当时
状态。后续 Gate P2-C 已创建 `integration/e2e01-cycle2`，当前保护配置仍需每次
dispatch / merge 通过 GitHub API 机械复核。

## 3. Approved base decision and historical pre-activation correction

### `C2-BLOCK-01` — branch and base strategy

旧 `integration/e2e01-thin` 与 planning input `main` 已明显分叉，且名称 /
history 均属于 Phase 1。Gate P2-A 已批准：

1. planning PR 只从 `main@b96fe8a...` 演进，并已满足 exact 7-file scope。
2. reviewed planning merge 的 exact successor 已冻结为
   `B_C2_PLAN_APPROVED = 2879f5226a073051d1550fe079b4a427c1ec8cb1`
   / tree `d5ded99bb0439fb57bbb4d6057fbda7a12b21fdf`。
3. 先在独立 owner-alignment branch 执行并 review `02-00`，其合并到 `main`
   的 exact successor 命名为 `B_C2_OWNER_ALIGNED`。
4. Gate P2-C 的 branch activation 操作才可从 exact `B_C2_OWNER_ALIGNED`
   创建 `integration/e2e01-cycle2`。
5. 创建后立即读取并冻结 integration branch 的 exact head / tree 为
   `B_C2_START`；它必须与 `B_C2_OWNER_ALIGNED` 的 SHA / tree 相同，并且是
   Phase 2 initial implementation base。
6. 只有第 5 步的 equality preflight 通过后，才可创建首个代码 feature
   branch / Worktree 或写功能代码。
7. 后续 Packet 不共享一个陈旧 base；每个 Wave 从已 reviewed、已串行 merge 的最新
   barrier 单独冻结 `base_sha`。

该 base chain 后续已完成：`02-00` reviewed merge 形成
`B_C2_OWNER_ALIGNED = B_C2_START = 4dc6dc95de81080fb3b651bc2f0026fb046fd9f8`
/ tree `521ac2c7611b20683089ab41a74d07c9a2bb8fc7`，并据此创建
`integration/e2e01-cycle2`。本段保留原批准顺序作为历史治理证据，不再表示当前
branch 或 implementation 未激活。

### `C2-BLOCK-02` — Eval model script path

Cycle 2 Spec 指定 `evals/model-scripts/`，当前仓库和 loader 使用
`evals/model_scripts/`。已按批准方向准备 `02-00` 独立 zero-code contract
correction，把 Cycle 2 路径更正为 underscore 版本。该修正必须：

- 只改真正受影响的 active owner / consumer；
- 通过 cross-file impact scan 和独立 exact-file review；
- 不创建 Eval artifact、loader、测试或 lifecycle 结果；
- 合并后的 exact SHA 成为后续 Eval Packet dependency。

[`02-00` exact Plan / Task Packet](../../.planning/phases/02-cycle-2-e2e-01/02-00-PLAN.md)
及其 zero-code owner correction 已 reviewed merge，scoped Spec 与仓库 loader 统一为
`evals/model_scripts/`。后续 02-13 必须把 exact artifact path 冻结为
`evals/model_scripts/e2e01-cycle2.v1.json`，不得继续使用变量或目录级 allowlist。

## 4. Collaboration model

```text
User approval gate
        │
Tech Lead / Integrator
├── Runtime Engineer
├── Infrastructure Engineer
├── Eval Engineer
└── Independent Reviewer（read-only）
```

- Integrator：owner conflict、Plan / Packet、base barrier、Worktree、串行 merge、
  Composition、全仓验证、状态同步。
- Runtime Engineer：Core 与 Application 的指定文件；不得依赖具体 SQLAlchemy /
  FastAPI / Provider SDK。
- Infrastructure Engineer：migration、PostgreSQL、Mock Order / Shipment 和 exact
  persistence；不得复制 Core DTO 或 Eval contract。
- Eval Engineer：authenticated bundle、Provider、Grader、Harness；不得从 script、
  expectation 或 Provider capture 补造 SUT 事实。
- Reviewer：只读 review exact head；发现由原 owner 在原 Packet allowlist 内修复，
  不直接写被审分支。

所有写入 Agent 必须使用 Integrator 预建的独立 Worktree / branch。最大并发 writer
为 2；同一 Wave 可以包含更多 ready slots，但一次只 dispatch 两个，且所有 merge
仍由 Integrator 串行执行。

## 5. Future Plan / Task Packet slots

以下 25 个 slot 是当前冻结集合：原 `02-00..18` 保持编号与 ownership；
`02-02R/02-04R/02-05R` 是用户授权的 W4 前 correction set，
`02-09R1/02-09R2/02-09R3` 是 02-09 exact preflight 触发的 recovery owner correction
set。`02-00` 是零功能代码的
scoped-owner correction；其余 slot 覆盖实现、remediation、lifecycle 与
post-activation verification。
每个 slot 后续必须形成且只形成：

```text
1 GSD Plan
↔ 1 exact Task Packet
↔ 1 repository / branch / Worktree
↔ 1 writer
↔ 1 ownership boundary
```

当前表中的文件是 proposed allowlist；只有后续 Task Packet 才能冻结 exact
`base_sha`、branch、worktree、owned / forbidden files 和 commands。

### `02-00` — Eval model-script path owner alignment

- **Owner:** Tech Lead / scoped Spec owner.
- **Goal:** 把 Cycle 2 Spec 的 model-script 目标路径从 hyphen 目录最小更正为
  仓库 / loader 已有的 underscore 目录；不创建 Eval artifact、loader、测试、
  lifecycle 结果或功能代码。
- **Proposed files:**
  - `docs/implementation/e2e01-cycle2-implementation-spec.md`
- **Depends on:** reviewed / merged master Plan；用户批准 `C2-BLOCK-02` 推荐裁决。
- **Acceptance:** exact-file owner review `PASS`；仓库级 cross-file impact scan
  确认 active consumers 唯一使用 `evals/model_scripts/`；除 scoped Spec 外
  changed-files 为零；合并 successor 冻结为 `B_C2_OWNER_ALIGNED`。

### `02-01` — Core business contracts

- **Owner:** Runtime Engineer / Business consumer.
- **Goal:** 冻结 search normalization、90 天窗口、stable sort、safe candidate
  projection、Shipment truth table、source version 和 deterministic assessment。
- **Proposed files:**
  - `src/mini_agent/core/order_search.py`（new）
  - `src/mini_agent/core/shipment.py`（new）
  - `tests/component/core/test_order_search_contract.py`（new）
  - `tests/component/core/test_shipment_contract.py`（new）
- **Depends on:** `B_C2_START`。
- **Acceptance:** D1/D2/D5/D6/D7 与 R02–R04/R08–R11 均有 exact typed component
  vectors；Phase 1 `GetOrder*` public shape 和 source hash 不变。

### `02-02` — Candidate / Memory contracts

- **Owner:** Runtime Engineer / Intent + Memory consumer.
- **Goal:** 实现 Search / Shipment Observation、CandidateSet、Selection、TTL、
  owner/private refs、Task version 与 CAS closed models。
- **Proposed files:**
  - `src/mini_agent/core/task_state.py`
  - `src/mini_agent/core/memory.py`
  - `tests/component/core/test_candidate_selection_contract.py`（new）
  - `tests/component/core/test_cycle2_memory_contract.py`（new）
- **Depends on:** `B_C2_START`。
- **Acceptance:** CandidateSet 不复制业务事实；wrong-owner、dangling、duplicate、
  stale、superseded、wrong-version 和 out-of-range 均 fail closed。

### `02-03` — Run / Trace v2 contract

- **Owner:** Runtime Engineer / Core Runtime consumer.
- **Goal:** 冻结 `SUPERSEDED`、新增 stop reasons、no-result closure 与 v2
  Run / Link / Trace record semantics；shared `TraceEvent` structure 不变。
- **Proposed files:**
  - `src/mini_agent/core/trace.py`
  - `tests/component/core/test_cycle2_trace_contract.py`（new）
- **Depends on:** `B_C2_START`。
- **Acceptance:** obsolete Run 不产生 Agent result / Message / ResponseRendered /
  Task / RequestUnit write；unknown / contradictory reason fail closed；ordinary
  Trace 只允许 exact safe whitelist，明确拒绝 raw customer / session scope、业务
  payload、candidate summary、source-version token、prompt、stack / raw exception
  与不必要 PII。

### `02-04` — Tool / Gateway contracts

- **Owner:** Runtime Engineer / Tool consumer.
- **Goal:** 新增两个 closed ToolSpec、三工具 immutable snapshot、binding Gate、
  attempt / timeout / retry / recovery truth table。
- **Proposed files:**
  - `src/mini_agent/core/tool_system.py`
  - `src/mini_agent/core/control_gateway.py`
  - `tests/component/core/test_tool_system_contract.py`
  - `tests/component/core/test_control_gateway.py`
- **Depends on:** reviewed `02-01/02/03` barriers。
- **Acceptance:** `get_order` 仍 one attempt；`search_orders/get_shipment` 为 500ms、
  max 2；only exact retryable codes；visible schema 不含 trusted/private fields。
  RegistrySnapshot 的 exact Tool 集合只能是 `search_orders`、`get_order`、
  `get_shipment` 且全部为 `READ`；不得注册 `PROPOSE_ACTION`、`create_refund` 或
  confirmation / ActionPolicy capability。

### `02-05` — Application records and Ports

- **Owner:** Runtime Engineer / Application.
- **Goal:** 新 record / v2 command、append attempt fence、candidate atomic commands、
  owner-scoped exact readers、no-result closure Port。
- **Proposed files:**
  - `src/mini_agent/application/records.py`
  - `src/mini_agent/application/ports.py`
  - `tests/component/application/test_record_contracts.py`
  - `tests/component/application/test_ports_contract.py`
- **Depends on:** reviewed `02-01..04` barriers。
- **Acceptance:** five new record / projection and four v2 parent records have closed
  commands / responses；no Adapter semantics leak into Port。

### `02-02R` — Cycle 2 accepted InputBinding completion

- **Owner:** Runtime Engineer / Core Task State single writer.
- **Goal:** 新增 inactive-until-cutover `InputBindingV2`，补全
  `product_description`、`candidate_ordinal`、`shipment_not_received` 的 strict
  name/value closure；保留 v1 owner model，并冻结
  `input_binding_record.p0.v1 → p0.v2` exact order-id conversion。
- **Proposed files:**
  - `src/mini_agent/core/task_state.py`
  - `tests/component/core/test_task_state_contract.py`
- **Depends on:** 本 owner ruling reviewed merge 后的 exact integration barrier。
- **Acceptance:** 四个 name/value 组合严格；bool/int/string 不互换；Claim 不成为
  Observation/verified target；v1 class 不变，v2 order-id projection兼容且 conversion
  只复制 exact v1 payload；本 Packet 不切换 active codec/writer。

### `02-04R` — Selected-target Gateway completion

- **Owner:** Runtime Engineer / Control Gateway single writer.
- **Goal:** 新增 inactive-until-cutover `GateDecisionV2` /
  `AuthorizedToolCommandV2` 的独立 `verified_target_ref`，保留 Phase 1 direct
  order-id binding 路径，同时为 ordinal selection 后的 `get_order` 增加 exact
  verified-target authorization；统一 Claim name，并修复 `get_shipment` 的同类
  mixed-ref 问题。
- **Proposed files:**
  - `src/mini_agent/core/tool_system.py`
  - `src/mini_agent/core/control_gateway.py`
  - `tests/component/core/test_tool_system_contract.py`
  - `tests/component/core/test_control_gateway.py`
- **Depends on:** reviewed `02-02R` barrier；planning PR #224 与 implementation PR #225
  已 bounded review `PASS` 并形成 `B_C2_SELECTED_TARGET_GATEWAY = 53e36aa...`。
- **Acceptance:** selected-target 路径只接受 exact
  `argument_binding_refs=[ordinal_input_binding_ref]` + 独立
  `verified_target_ref=selected_target_ref`、current result version 和匹配 `order_id`；
  direct/selected 两路径不可混用或 fallback；get_shipment 同样分离 binding/target；
  `verified_target_ref` 使用既有 UUID logical identity；SelectionRecord 的
  `selected_target_ref` 只保存其 canonical lowercase UUID text，并要求
  `str(UUID(text)) == text` exact round-trip。不得从 owner-scoped ref、摘要或 payload
  哈希推导 target；v1 Gate/Command shape 不变；
  拒绝 stale/wrong-owner/wrong-target；只使用 `shipment_not_received`。

### `02-05R` — Continuation binding and atomic ordinal-selection writer

- **Owner:** Runtime Engineer / Application single writer.
- **Goal:** 补全 existing Task 的 continuation InputBinding writer，并把 ordinal
  binding、RequestUnit ref、SelectionRecord、selected target、closed pending 与
  Task/RequestUnit version 放入同一个 CAS command/Port closure。
- **Proposed files:**
  - `src/mini_agent/application/records.py`
  - `src/mini_agent/application/ports.py`
  - `tests/component/application/test_record_contracts.py`
  - `tests/component/application/test_ports_contract.py`
- **Depends on:** reviewed `02-04R` merge successor
  `B_C2_SELECTED_TARGET_GATEWAY = 53e36aa88fab1ab99d2b076a1d731f63dced064a` /
  tree `3f9852e825a69c9ceb8a19e18c810263ef74349e`。该 Packet 已从真实 successor
  重新冻结 base/tree/blobs，仍须独立 planning/focused/overlay review-green。
- **Acceptance:** continuation write 需要 current owner/Task/RequestUnit/message；
  ordinal 路径禁止 pre-CAS binding write/version bump；CAS 冲突无半写；selection
  command 允许且只允许 exact binding-ref/open-question/target/version delta；v2
  complete graph 要求 GateDecisionV2 / AuthorizedToolCommandV2 / ToolCallRecordV2 的
  `verified_target_ref` exact-copy，同时 `argument_binding_refs` 全部解析为当前
  RequestUnit InputBindingV2 refs。

### `02-06` — Exact persistence codec

- **Owner:** Runtime Engineer / Application persistence.
- **Goal:** 新 record codes、v2 active versions、strict exact codec / version catalog、
  cutover validation 和 rollback categories。
- **Proposed files:**
  - `src/mini_agent/application/persistence.py`
  - `tests/component/application/test_persistence_contract.py`
- **Depends on:** reviewed `02-02R/02-04R/02-05R` 后的 exact `B_C2_W4_READY`；旧
  02-06 Plan 必须在该真实 barrier 重冻结。
- **Acceptance:** 五个新增 record 加 InputBinding / GateDecision / ToolCall /
  AgentRun / RunTaskLink / TraceEvent 六个 v2 parent 的 catalog 与 exact conversion
  闭合；unknown version、mixed active version、logical child mismatch、conversion
  ambiguity 全部 fail closed；无 read-time fallback。

### `02-07` — Mock Order / Shipment business adapters

- **Owner:** Infrastructure Engineer / Business physical implementation.
- **Goal:** owner-scoped `search_orders` 和 `get_shipment`；single-read authority、
  stable query、0/1/>1 Package、canonical source bytes。
- **Proposed files:**
  - `src/mini_agent/infrastructure/order/postgres.py`
  - `src/mini_agent/infrastructure/shipment/__init__.py`（new）
  - `src/mini_agent/infrastructure/shipment/postgres.py`（new）
  - `tests/integration/test_postgres_search_orders.py`（new）
  - `tests/integration/test_postgres_get_shipment.py`（new）
- **Depends on:** reviewed `02-01/05/10` barriers。
- **Acceptance:** foreign owner never enters result；search stable；Package cardinality
  >1 deterministic failure；source version只由同一次 owner-scoped read生成；
  `search_orders` 只读 reviewed search-authority table，Phase 1 `get_order` 的
  projection、parser 与 canonical bytes 不变。

### `02-08` — Request understanding and task routing

- **Owner:** Runtime Engineer / Intent + Core Runtime.
- **Goal:** product query、candidate ordinal、not-received Claim 的 deterministic
  candidate validation、Task/current-version revalidation 与 NextMove routing。
- **Proposed files:**
  - `src/mini_agent/core/request_understanding.py`
  - `src/mini_agent/core/request_processing.py`
  - `tests/component/core/test_request_understanding_contract.py`
  - `tests/component/core/test_request_processing.py`
- **Depends on:** reviewed `02-01/02/04/05` 与 `02-02R/02-04R/02-05R` barriers。
- **Acceptance:** ordinal 只绑定 current unique CandidateSet；旧 Task / binding /
  target 无 ToolCall；Claim 不成为 Observation。

### `02-09` — Read executor and restart recovery

- **Owner:** Runtime Engineer / Tool + Application.
- **Goal:** 同一 ToolCall 下 append-only max-two attempts、timeout phase、retry
  decision、second fence、unfinished / retry-scheduled restart closure。
- **Proposed files:**
  - `src/mini_agent/application/read_tool_executor.py`
  - `src/mini_agent/application/restart_recovery_service.py`
  - `tests/component/application/test_read_tool_executor.py`
  - `tests/component/application/test_restart_recovery_service.py`
- **Depends on:** reviewed `02-02/03/04/05`、`02-04R/02-05R` 与
  `02-09R1/02-09R2/02-09R3` exact barriers；旧四文件 Plan 在 R1-R3 merge 前不可执行。
- **Acceptance:** attempt 1 失败证据不被最终 success 覆盖；deterministic failure
  不重试；state invalidation 形成 OA-10 no-result closure。

### `02-09R1` — Core recovery terminal closed matrix

- **Owner:** Runtime Engineer / Tool Core single writer。
- **Goal:** 修复 `RETRY_SCHEDULED + RUN_BUDGET_EXHAUSTED` 无合法 parent terminal 的
  owner bug；attempt 1 保持 immutable，parent exact 投影为原 `FAILED / TIMED_OUT`，
  新增专用 recovery disposition，不改变 shared Trace structure。
- **Proposed files:**
  - `src/mini_agent/core/tool_system.py`
  - `tests/component/core/test_tool_system_contract.py`
- **Depends on:** 本 owner ruling reviewed merge；exact base 由后续 Plan 在真实
  integration successor 冻结。
- **Acceptance:** budget terminal、state invalidation 与 unfinished 三种 exception
  互斥；unknown/contradictory evidence fail closed；无 persistence/dispatch claim。

### `02-09R2` — Application recovery records and Ports

- **Owner:** Runtime Engineer / Application contract single writer。
- **Goal:** 增加 exact owner-scoped v2 recovery closure、durable
  `ToolRetryRecoveryDecisionRecordV2`、recovered second-fence / terminal / OA-10 atomic
  commands 与 Port surface；禁止 service-local private Port 绕过 shared owner。
- **Proposed files:**
  - `src/mini_agent/application/records.py`
  - `src/mini_agent/application/ports.py`
  - `tests/component/application/test_record_contracts.py`
  - `tests/component/application/test_ports_contract.py`
- **Depends on:** reviewed `02-09R1` barrier。
- **Acceptance:** APPLIED 才能原子写 decision child + second fence 或完整 terminal
  closure；其他结果零写、零 dispatch；unfinished child 与 attempt 1 decision 不改写。

### `02-09R3` — Recovery logical-child codec

- **Owner:** Runtime Engineer / Application persistence codec single writer。
- **Goal:** 把 `ToolRetryRecoveryDecisionRecordV2` 加入 `tool_call_record.p0.v2` exact
  logical-child catalog/closure；不新增 top-level business record，不改变 Phase 1 codec。
- **Proposed files:**
  - `src/mini_agent/application/persistence.py`
  - `tests/component/application/test_persistence_contract.py`
- **Depends on:** reviewed `02-09R2` barrier。
- **Acceptance:** parent/ref/identity/cardinality/ordering/unknown child fail closed；
  02-06 五个 top-level 与六个 v2 parent family 保持不变。

### `02-10` — Physical schema and migration

- **Owner:** Infrastructure Engineer / persistence single writer.
- **Goal:** code/version physical admission、Mock Shipment storage、独立
  `MockOrderSearchDocumentModel` / `mock_order_search_documents` search-authority
  table、v1→v2
  full pre-validation、atomic cutover 与 downgrade / rollback fence。search table
  提供 owner / order identity 以及 `line_ordinal`、`product_name`、`quantity`、
  `product_category`、`search_aliases`；现有 `mock_orders.order_payload` 保持不变。
- **Proposed files:**
  - `alembic/versions/20260731_0004_cycle2_records_v2.py`（proposed new）
  - `src/mini_agent/infrastructure/persistence/models.py`
  - `tests/integration/test_database_migrations.py`
  - `tests/integration/test_postgres_get_order.py`
- **Depends on:** reviewed `02-01/03/04/05/06` barriers。
- **Acceptance:** empty DB 和 Phase 1 head 两条升级路径；未知 / 矛盾 conversion
  整体失败；v2-only evidence 后禁止 destructive downgrade；Phase 1
  `get_order` 读取与 canonical source bytes 在迁移前后 byte-identical。

### `02-11` — PostgreSQL records and exact readers

- **Owner:** Infrastructure Engineer / persistence.
- **Goal:** atomic CandidateSet / Selection / Observation / Assessment writers，
  append-attempt CAS、owner-scoped candidate reader、v2 recovery 与 exact-Run evidence。
- **Proposed files:**
  - `src/mini_agent/infrastructure/persistence/postgres.py`
  - `src/mini_agent/infrastructure/persistence/recovery.py`
  - `tests/integration/test_postgres_record_adapters.py`
  - `tests/integration/test_postgres_recovery.py`
  - `tests/integration/test_postgres_atomicity.py`
- **Depends on:** reviewed `02-06/10` barriers。
- **Acceptance:** half-write、wrong-owner、dangling、duplicate、mixed version、
  retry fence conflict 全部零部分写入并 fail closed；本 slot 不产生 confirmation、
  ActionPolicy、idempotency claim / key、Action Ledger write 或 `RESULT_UNKNOWN`
  side-effect recovery。

### `02-12` — Runtime mapper / Renderer

- **Owner:** Runtime Engineer / Application.
- **Goal:** search → clarify / select → `get_order` → optional Shipment orchestration；
  imported Phase 1 mapper + Cycle 2 delta；freshness / assessment；safe Renderer。
- **Proposed files:**
  - `src/mini_agent/application/agent_run_service.py`
  - `src/mini_agent/application/run_result_mapper.py`（proposed new）
  - `src/mini_agent/application/deterministic_renderer.py`
  - `src/mini_agent/core/presentation.py`
  - `src/mini_agent/core/presentation_policy.py`
  - `tests/component/application/test_agent_run_service.py`
  - `tests/component/application/test_deterministic_renderer.py`
  - `tests/component/core/test_presentation_policy.py`
- **Depends on:** reviewed `02-07/08/09` barriers。
- **Acceptance:** effective Mapper rows complete、互斥、无 unmapped；order-only 不查
  Shipment；stale facts不进入 Context / reply；Renderer只消费 safe projection。

### `02-13` — Eval bundle and authenticated loader

- **Owner:** Eval Engineer.
- **Goal:** 14 longitudinal + 13 trajectory exact artifact、pair identity、manifest
  digest、versioned loader 和 multi-step scripted Provider。
- **Proposed files:**
  - `src/mini_agent/evaluation/artifacts.py`
  - `src/mini_agent/evaluation/scripted_provider.py`
  - `evals/cases/e2e01-cycle2.v1.json`
  - `evals/fixtures/e2e01-cycle2.v1.json`
  - `evals/model_scripts/e2e01-cycle2.v1.json`
  - `evals/manifests/e2e01-cycle2.v1.json`
  - `evals/lanes/e2e01-cycle2.v1.json`
  - `tests/component/evaluation/test_e2e01_artifact_consistency.py`
  - `tests/component/evaluation/test_e2e01_scripted_model_provider.py`
  - `tests/component/model/test_e2e01_scripted_scenario_catalog.py`
- **Depends on:** reviewed `02-00/04/05` barriers。
- **Acceptance:** 27 Case IDs unique；all predicates parse；digest mismatch /
  missing artifact / unexpected field fail closed；artifact existence不改变 lifecycle；
  catalog / scripts / expectations 不包含 Action、confirmation、ActionPolicy、
  idempotency、Action Ledger 或 `RESULT_UNKNOWN` side-effect recovery 路径。

### `02-14` — Graders and offline Harness

- **Owner:** Eval Engineer.
- **Goal:** Candidate、Shipment、retry/recovery、Mapper、OA-10 typed graders，
  actual-evidence Harness machinery 与 disclosure guards；不推进 Case lifecycle，
  不运行 Phase 2 SUT / Provider / Grader / Result chain。
- **Proposed files:**
  - `src/mini_agent/evaluation/graders.py`
  - `src/mini_agent/evaluation/harness.py`
  - `tests/component/evaluation/test_e2e01_graders.py`
  - `tests/integration/evaluation/test_e2e01_offline_harness.py`
- **Depends on:** reviewed `02-11/12/13` barriers。
- **Acceptance:** Provider/script/expectation不能补造 SUT evidence；typed grader
  明确断言 ordinary Trace 不含 raw customer / session scope、业务 payload、
  candidate summary、source-version token、prompt、stack / raw exception 或不必要
  PII；derived `CONTRACT_DEFINED` batch 必须在 SUT / Provider / Trace / Grader /
  Result 前 fail closed；本 slot 不声称存在 Phase 2 lifecycle-valid Result。

### `02-15` — Pre-activation Composition / HTTP execution seam

- **Owner:** Tech Lead / Integrator.
- **Goal:** 在 Case 保持 `CONTRACT_DEFINED` 时完成三工具真实装配、Fixture seed
  与 HTTP → trusted Session → Runtime → owner-scoped Mock systems →
  PostgreSQL → exact evidence 的可复现 execution seam；不得通过 Eval Harness
  dispatch 或生成 Phase 2 Eval Result。
- **Proposed files:**
  - `src/mini_agent/bootstrap.py`
  - `src/mini_agent/api/http.py`（only if exact HTTP contract evidence requires）
  - `tests/integration/test_offline_composition_root.py`
  - `tests/integration/test_http_session_adapter.py`
  - `tests/integration/test_e2e01_cycle2_execution_seam.py`（new）
- **Depends on:** reviewed `02-07/11/12/14` barriers。
- **Acceptance:** direct non-Harness integration tests证明四个 Case 的真实入口能产生
  typed Run / record / Trace evidence；同一 RegistrySnapshot exact 包含三个 READ
  tools；Phase 1 Composition 回归通过；同时 Harness 对 Cycle 2
  `CONTRACT_DEFINED` batch 仍在 SUT 前 fail closed，Phase 2 Result 数为零。

### `02-16` — Coverage owner `APPROVED_FOR_EXECUTABLE` ruling

- **Owner:** Eval Coverage canonical owner / documentation single writer.
- **Goal:** 基于 reviewed `02-13/14/15` exact-head evidence，独立裁决
  `E2E01-02/03/05/06` 是否具备可复现执行入口并允许进入 activation sync；
  不修改代码、artifact、manifest、loader、测试、Result 或 `.planning`。
- **Proposed files:**
  - `docs/evaluation/p0-eval-coverage-matrix.md`
- **Depends on:** reviewed `02-13/14/15` barriers；canonical owner 可用。
- **Acceptance:** 本 slot 拥有独立 GSD Plan / exact Task Packet、base、single-file
  allowlist、rollback 与用户批准；exact-file owner review `PASS`；裁决明确为
  `APPROVED_FOR_EXECUTABLE` 或保持 `BLOCKED`，不得由 artifact existence、
  Integrator 或 Eval writer 代替。未批准时 `02-17/18` 不得启动。

### `02-17` — EvalCase `EXECUTABLE` activation sync

- **Owner:** Eval Engineer / lifecycle consumer single writer.
- **Goal:** 在 reviewed `02-16` 已作出 `APPROVED_FOR_EXECUTABLE` 裁决后，原子
  同步 Cycle 2 Case lifecycle、manifest digest、versioned loader 与 consistency
  evidence。
- **Proposed files:**
  - `evals/cases/e2e01-cycle2.v1.json`
  - `evals/manifests/e2e01-cycle2.v1.json`
  - `src/mini_agent/evaluation/artifacts.py`
  - `tests/component/evaluation/test_e2e01_artifact_consistency.py`
  - `tests/component/evaluation/test_e2e01_versioned_artifact_loader.py`
- **Depends on:** reviewed `02-13/14/15/16` barriers。
- **Acceptance:** ruling 前仍为 `CONTRACT_DEFINED` 且 Harness pre-dispatch
  fail closed；ruling 后 lifecycle / manifest / loader 在一个 exact Packet 中同步，
  loader 才接受 `EXECUTABLE`；digest / lifecycle 任一不一致都 fail closed；本
  slot 不声称实际 Phase 2 Result 已产生。

### `02-18` — Post-activation Harness / HTTP E2E Results

- **Owner:** Tech Lead / Integrator.
- **Goal:** 在 `EXECUTABLE` atomic sync 后，使用 reviewed real execution seam
  运行 Harness、Trajectory 与 HTTP E2E，产生 lifecycle-valid structured Results。
- **Proposed files:**
  - `tests/integration/evaluation/test_e2e01_offline_harness.py`
  - `tests/e2e/test_e2e01_http_eval.py`
  - `tests/baseline/test_qwen_baseline.py`
- **Depends on:** reviewed `02-15/17` barriers。
- **Acceptance:** Phase 1 16 variants和 Phase 2 14 longitudinal + 13 trajectory 全部
  lifecycle-valid；same-registry pair exact；ordinary Trace disclosure negative
  assertions通过；全链不得注册或触发 Action、confirmation、ActionPolicy、
  idempotency、Action Ledger 或 `RESULT_UNKNOWN` side-effect recovery；无
  credential 时 Qwen honest skip。

## 6. Execution Waves

| Wave | Ready slots | Concurrency | Merge order / exit barrier |
|---|---|---:|---|
| `W0` | `02-00` | 1 | zero-code owner correction；形成 `B_C2_OWNER_ALIGNED`；不创建 integration branch 或 `B_C2_START` |
| `W1` | `02-01, 02-02, 02-03` | max 2 | serial review/merge；形成 `B_C2_CORE_123` |
| `W2` | `02-04` | 1 | `B_C2_TOOL` |
| `W3` | `02-05` | 1 | `B_C2_APP_CONTRACT` |
| `W3R` | `02-02R → 02-04R → 02-05R` | 1 | exact-type dependencies require reviewed serial successors；形成 `B_C2_W4_READY` |
| `W4` | `02-06, 02-13, 02-08；02-09 waits for W4R` | max 2 | each exact review + serial merge；Batch A 已完成 |
| `W4R` | `02-09R1 → 02-09R2 → 02-09R3` | 1 | recovery owner corrections serial merge；形成 `B_C2_02_09_READY` |
| `W4 resumed` | `02-09` | 1 | 从 exact `B_C2_02_09_READY` 重冻结后执行；形成 `B_C2_LEAVES` |
| `W5` | `02-10` | 1 | `B_C2_PHYSICAL` |
| `W6` | `02-07, 02-11` | max 2 | business / record Adapter files不重叠；serial merge；形成 `B_C2_INFRA` |
| `W7` | `02-12` | 1 | `B_C2_RUNTIME` |
| `W8` | `02-14` | 1 | `B_C2_EVAL_MACHINERY`；Case 仍为 `CONTRACT_DEFINED` |
| `W9` | `02-15` | 1 | `B_C2_EXECUTION_SEAM`；Case 仍为 `CONTRACT_DEFINED` |
| `W10` | `02-16` | 1 | independent owner ruling `G_C2_APPROVED_FOR_EXECUTABLE` |
| `W11` | `02-17` | 1 | atomic consumer sync；形成 `B_C2_EXECUTABLE` |
| `W12` | `02-18` | 1 | `B_C2_VERTICAL` |

```text
W0 scoped-owner path correction (zero feature code)
  ↓
P2-C branch activation:
create integration/e2e01-cycle2 from B_C2_OWNER_ALIGNED
and freeze equal SHA/tree as B_C2_START
  ↓
W1 Core contracts
  ↓
W2 Tool / Gateway
  ↓
W3 Application contracts
  ↓
W3R accepted-binding Core correction
  ↓
W3R Gateway selected-target correction
  ↓
W3R Application atomic continuation correction
  ↓
W4 codecs + RU + retry + Eval bundle
  ↓
W5 migration
  ↓
W6 business adapters || PostgreSQL persistence / recovery
  ↓
W7 Runtime mapper / Renderer
  ↓
W8 Graders / Harness machinery; pre-dispatch fail closed
  ↓
W9 pre-activation Composition / HTTP execution seam
   (`CONTRACT_DEFINED`; no Eval Result)
  ↓
W10 Coverage owner `G_C2_APPROVED_FOR_EXECUTABLE`
  ↓
W11 atomic lifecycle / manifest / loader sync
  ↓
W12 Harness / HTTP E2E and lifecycle-valid Results
  ↓
Post-execution quality gates
```

同一 Wave 只表示依赖允许，不表示同时启动全部 slot。Integrator 每次最多 dispatch
两个 writer，合并始终逐个进行。任一 proposed allowlist 出现交集时，该 slot 在
Task Packet freeze 前自动变为 `BLOCKED`。

## 7. Requirement and decision coverage

| Requirement | Slots |
|---|---|
| `R01` | `13,14,15,16,17,18` |
| `R02` | `01,07,08,12,14,15,18` |
| `R03` | `01,07,13,14,15,18` |
| `R04` | `01,12,14,15,18` |
| `R05` | `02,05,06,11` |
| `R06` | `02,08,11,14` |
| `R07` | `07,08,12,14` |
| `R08` | `01,04,07,08,14` |
| `R09` | `01,02,07,11,14` |
| `R10` | `02,09,12,14` |
| `R11` | `01,02,12,14` |
| `R12` | `04,05,09,11,14` |
| `R13` | `04,07,09,12,14` |
| `R14` | `03,05,09,12,14` |
| `R15` | `04,08,13,15,18` |
| `R16` | `02,03,05,06,09,10,11,14` |
| `R17` | `13,14,15,16,17,18` |
| `R18` | `16,17,18` + post-execution quality gates |

| Case | Slots |
|---|---|
| `E2E01-02` | `01,07,08,12,13,14,15,16,17,18` |
| `E2E01-03` | `02,08,11,12,13,14,15,16,17,18` |
| `E2E01-05` | `04,07,08,12,13,14,15,16,17,18` |
| `E2E01-06` | `01,02,03,04,07,09,11,12,13,14,15,16,17,18` |

| Frozen decision | Slots |
|---|---|
| `D1/D2` | `01,07,08,12,13,14` |
| `D3/D4` | `02,05,08,11,14` |
| `D5/D6` | `01,02,04,07,11,14` |
| `D7` | `01,02,12,14` |
| `D8` | `04,05,09,10,11,14` |

## 8. Task Packet freeze gate

master Plan 获批后，Integrator 逐 slot 创建 exact GSD Plan / Task Packet proposal。
每个 Packet 必须显式填写：

- `repository`、`remote`、`head_branch`、`base_branch`、exact `base_sha` /
  `base_tree`、`worktree_id`；
- writer role / Agent、owned files、forbidden files、dependency barriers；
- 2–3 个原子 tasks、`read_first`、concrete actions、mechanical
  acceptance criteria；
- focused、neighbor、migration、integration、full verification；
- `contract_changes`、`security_impact`、`eval_impact`；
- `review_profile`：`planning_review`、`implementation_review`、
  `targeted_risk_checks`、`focused_tests`、`neighbor_tests`、`full_suite_gate`、
  `phase_end_deep_audit`；
- rollback、handoff、output barrier；
- branch protection / PR base、exact-head review 和 latest-integration overlay
  requirement。

没有适用项时写 `NONE`；不得留空、继承隐含值或由 Executor猜测。Task Packet
必须通过：

1. slot 唯一；
2. 同名 Plan / Packet `NOT_FOUND`；
3. owned files 与同 Wave Packet 交集为零；
4. shared hotspot 有唯一 writer；
5. exact base 是当前已 reviewed dependency barrier；
6. canonical owner没有 unresolved conflict；
7. independent exact-head planning review `PASS`；
8. 用户批准 Packet 数量、Wave、initial base chain 与并发上限。

W3R 的 current user directive 已批准 correction set、`W3R` 插入与最大两个 writer；
但每个 correction Packet 仍必须从当时真实 integration head 单独冻结 exact
`base_sha`，不得从本 master Plan 预填未来 `B_C2_W4_READY` SHA。

## 9. Verification strategy

### 9.1 W4 起的风险分级审阅

从 W4 开始，Packet review 使用“普通 exact-head 审阅 + 风险专项验证，Phase 末统一
全面深审”。每个 Packet 仍必须由独立 reviewer 检查 exact base/head、parent、
ancestry、commit/allowlist、当前 Packet diff、直接 canonical owner、focused / neighbor
tests 与本 Packet 明确拥有的安全不变量。reviewer 不重复阅读全部 canonical 文档、
审计全部历史 Wave、复现 Phase 2 全部攻击向量、运行完整仓库套件或提前执行 Phase
级 Eval / Security / UAT；未修改的 reviewed barrier 作为 imported evidence，只检查当前
Packet 是否正确消费其公开合同。

同一 exact SHA 已有有效 transcript 时不得无理由重复测试。finding remediation 只运行
对应 focused / neighbor tests；最终候选稳定后再做 final exact-head review。BLOCK /
HIGH 必须关闭；MEDIUM 必须修复或有证据接受；LOW / INFO 必须记录。finding 若要求
contract change、扩大 allowlist、改变 Wave / Packet 数量或跨 ownership boundary，立即
停止并请求裁决。

W4 profile 固定为：

- `02-06 = TARGETED_CONTRACT`：unknown/mixed version、logical child mismatch、
  conversion ambiguity、no read-time fallback 与 Phase 1 codec compatibility；
- `02-08 = TARGETED_SECURITY`：current/unique/unexpired ordinal binding、stale /
  wrong-version/task/target prohibition、Claim/Observation 分离、trusted/private binding
  不可由模型替换、旧 Task 不复活；
- `02-09 = TARGETED_HIGH_RISK`：append-only max-two attempts、exact retryability、
  second fence、restart/obsolete Run/OA-10 no-result closure，且绝不进入 Action 域；
- `02-13 = TARGETED_EVAL_INTEGRITY`：27 IDs、bundle/digest/lane identity、strict loader、
  evidence non-fabrication、artifact 不推进 lifecycle，且绝不包含 Action 域。

W4R correction review 同样有界：

- `02-09R1 = TARGETED_CORE_RECOVERY`：只审三种 recovery exception、immutable
  attempt 1、budget terminal metadata 与 pure decision fail-closed；
- `02-09R2 = TARGETED_ATOMIC_RECOVERY_CONTRACT`：只审 trusted closure、decision
  child、second-fence/terminal/OA-10 command 与 Port 的 APPLIED/zero-write 边界；
- `02-09R3 = TARGETED_CHILD_CODEC`：只审 recovery child identity/ref/cardinality、
  unknown/mixed child fail-closed 与 Phase 1 codec compatibility。

W3R correction review 同样有界：

- `02-02R = TARGETED_CORE_CONTRACT`：只审 strict name/value matrix、Phase 1
  `order_id` compatibility、Claim/Observation 分离与 owned focused/neighbor tests；
- `02-04R = TARGETED_GATEWAY_SECURITY`：只审 direct/selected 双路径、exact refs、
  current version/owner/target、Claim name 与 negative vectors；
- `02-05R = TARGETED_ATOMICITY`：只审 continuation closure、ordinal single-CAS、
  half-write/CAS-conflict prohibition 与 command/Port exact shape。

每个 reviewer 只读 exact diff、直接 canonical paragraphs 和定向测试 transcript；
不重跑 canonical full、不复审历史 Wave。只有产生 finding 才对受影响范围做一次聚焦
复审。

Wave / Phase full gates 固定为：W4 只做 integration-focused / neighbor 与 Phase 1
直接相关回归；W5 只做 migration 两条升级路径；W6 合并完成后运行一次 canonical full
suite；W7–W11 依各自专项 focused / neighbor / owner evidence 审阅；W12 纵向实现完成后
启动 Phase 2 唯一一次全面深审，并运行 canonical repository full gate、Eval review、
Security audit 与 Controlled UAT。Phase 末 finding 修复期间只跑 focused / neighbor，
最终候选 head 稳定后只再运行一次 canonical full suite。

### 9.2 Per-slot minimum

- TDD 可适用的 DTO、state、mapper、algorithm、API 全部使用 RED → GREEN →
  focused hardening。
- `git diff --check`。
- exact `base_sha`、first parent、zero merge、commit list、allowlist containment。
- owned focused tests与直接 neighbor tests。
- independent exact-head code review。
- latest integration overlay 保持 owned blobs / patch语义。

### 9.3 Migration / persistence

- empty database → head。
- Phase 1 migration head → Phase 2 head。
- v1 rows 全量预验证后一次 cutover。
- unknown / contradictory / mixed version fail closed且零部分转换。
- CandidateSet / selection / attempt / no-result原子性和 crash-point tests。
- downgrade 在 v2-only evidence 前有界；其后明确 fail closed。

### 9.4 Eval / E2E

- `02-13/14/15` exact-head review完成前保持 `CONTRACT_DEFINED`；`02-15`
  只通过 direct non-Harness integration 建立可复现 execution seam，Harness
  仍必须在 SUT / Provider / Trace / Grader / Result 前 fail closed。
- `02-16` Coverage Matrix owner 独立裁决 `APPROVED_FOR_EXECUTABLE` 后，
  `02-17` 才可原子同步 lifecycle / manifest / loader；`02-18` 才可运行
  Phase 2 Harness / SUT 并产生 Result。
- Phase 1 16 authenticated variants继续通过。
- Phase 2 14 longitudinal variants全部产生 lifecycle-valid Result。
- 13 mandatory non-HTTP Trajectory全部单独产生 lifecycle-valid Result。
- Component、Trajectory、HTTP E2E均非空。
- `0 FAIL / 0 Critical failure / 0 execution failure`。
- exact artifact digest、predicate arity / symbol、pair identity、same registry /
  toolset / provider mapping。
- 真实 HTTP SUT 和 owner-scoped exact-Run reader；禁止 Synthetic SUT。

### 9.5 Canonical repository gate

从仓库根目录运行：

```bash
uv sync --all-groups
docker compose up --wait -d db
docker compose --profile test up --wait -d db-test
uv run alembic upgrade head
uv run pytest
```

当前没有 canonical lint、type-check、build 或 product-startup 命令；不得编造。

## 10. Post-execution quality gates

`B_C2_VERTICAL` 只表示实现集成完成，不推进 Case 或 Phase。W12 后只启动一次 Phase 2
全面深度审计，统一覆盖跨 Wave contract alignment、identity / owner scope、
CandidateSet / ordinal、Shipment freshness、retry / recovery / `SUPERSEDED`、Mapper /
Renderer / `CF-13`、Trace / PII、Eval artifact / Harness / lifecycle、Component /
Trajectory / HTTP E2E 与 canonical repository full gate。之后依序：

1. exact-integration-SHA code review；
2. findings 只通过新的 exact fix Packet关闭；
3. Validation；
4. Eval re-review；
5. Security audit；
6. Controlled UAT；
7. Coverage Matrix owner基于实际 Results / quality evidence 裁决是否推进
   `REGRESSION_GATE`；这与执行前 `APPROVED_FOR_EXECUTABLE` 是两个独立裁决；
8. Integrator 手工同步 `.planning`；
9. integration → `main` release PR、独立 exact-head review、用户 merge decision；
10. 显式 Phase 2 release/status closure。

Review、Validation、Eval、Security 或 UAT branch不得直接修功能代码；发现进入新的
一对一 Plan / Task Packet，并重新经过用户审批。

`REGRESSION_GATE` owner ruling、atomic lifecycle consumer sync 与 release/status
closure 需要后续独立 exact Plan / Task Packet 和用户批准；其 evidence 与 base
只有在 `B_C2_VERTICAL` 及质量结果真实存在后才能冻结，本 Plan 不提前伪造。

<threat_model>

| Threat | Severity | Required mitigation | Evidence slots |
|---|---|---|---|
| forged `customer_id` / owner scope | CRITICAL | server `CustomerContext` only；business query owner predicate；safe equivalence | `04,07,08,12,15,18` |
| model replaces order/package/candidate refs | CRITICAL | exact binding、verified target、owner-scoped reader；no model `package_id` | `02,04,08,11,14` |
| CandidateSet replay / version tamper | HIGH | content hash、15m TTL、current uniqueness、Task CAS、atomic selection | `02,05,06,11` |
| stale Shipment used in result | HIGH | 5m TTL、birth-stale rejection、forced refresh、no fallback | `01,02,09,12,14` |
| foreign/private/source token / Trace disclosure | CRITICAL | visible/private DTO split；ordinary Trace exact whitelist，禁止 raw customer/session scope、业务 payload、candidate summary、source token、prompt、stack / raw exception 与不必要 PII | `03,14,15,18` |
| unbounded retry / loop | HIGH | 500ms、max 2 attempts、run budget、no parallel ToolCall | `04,09,11,14` |
| mixed active v1/v2 | CRITICAL | full prevalidation、atomic cutover、strict readers/writers/recovery | `03,05,06,10,11` |
| obsolete Run overwrites new state / sends result | CRITICAL | conditional CAS、`SUPERSEDED`、null link result、no outbound/task write | `03,05,09,11,12,14` |
| model / Eval fabricates business evidence | CRITICAL | deterministic projection/mapper、authenticated artifacts、real HTTP SUT | `12,13,14,15,18` |
| `CONTRACT_DEFINED` Case dispatched或 artifact 自激活 | CRITICAL | Harness pre-dispatch fail closed；reviewed execution seam；独立 owner ruling；atomic lifecycle / manifest / loader sync | `13,14,15,16,17,18` |
| read-only phase enables Action / side effect | CRITICAL | exact Registry 仅三个 `READ` tools；无 confirmation、ActionPolicy、idempotency claim/key、Action Ledger write 或 `RESULT_UNKNOWN` side-effect recovery | `04,09R1,09R2,09R3,11,13,15,18` |

任何 CRITICAL / HIGH threat 缺少可复现 mitigation evidence 都阻断 slot merge、Wave
barrier 与 release。

</threat_model>

## 11. Risk controls learned from Phase 1

1. **先完整暴露 slots，不用“大包”隐藏复杂度。** 原 19 slots 仍保留；当前用户已
   明确批准增加 `02-02R/02-04R/02-05R`，形成 22 slots。后续再增减任一 slot 仍需
   用户重新批准 master Plan。
2. **不在执行中偷渡 contract。** 发现 owner gap，停止对应 Wave，先做最小
   contract change / review；不生成临时 replacement Plan。
3. **同一 finding 优先在原 Packet 内关闭。** 只有跨 allowlist / owner / base 的
   finding 才创建新 fix Packet。
4. **每个 Wave 有用户 checkpoint。** Integrator 提交 merged barriers、实际变更、
   测试和风险；用户确认后才 dispatch 下一 Wave。
5. **最大并发为 2。** 避免三个 writer 同时把 shared interfaces推向不兼容状态。
6. **Composition 和全量 Eval 不提前。** 公共合同、migration、atomic persistence
   未稳定前，不用临时 bootstrap / Harness glue掩盖缺口。
7. **数量不是进度。** Plan、Packet、commit、测试数量都不证明 Case完成；只看
   exact evidence和 lifecycle owner ruling。

## 12. Rollback and escalation

### 12.1 Per-slot rollback

- merge前：关闭 draft PR，保留 branch、diff、tests 和 review evidence。
- merge后：普通 revert PR；不使用 reset、force push或强制 Worktree cleanup。
- 下游已 merge：按严格逆依赖顺序先 revert下游，再 revert源 slot。

### 12.2 Migration rollback

- 首条 v2-only evidence 前：按冻结 backup / restore 和 downgrade步骤回滚。
- 首条 v2-only evidence 后：不得降到无法表达 v2语义的 Runtime / schema；只允许
  owner批准的 v2-capable rollback 或 forward fix。
- 失败数据库证据不能通过清库、手工改 row 或删除 migration history掩盖。

### 12.3 Escalation triggers

以下任一事件立即停止 dispatch / push / merge并保留现场：

- owner conflict 或 contract drift；
- allowlist外文件、unexpected commit、same-wave file overlap；
- exact migration无法唯一转换；
- unknown / contradictory Mapper or recovery reason；
- partial atomic write、wrong-owner read、Critical failure；
- Plan / Task Packet数量或 Wave需要改变；
- 当前 dependency barrier 与 Packet `base_sha` 不一致。

## 13. User approval gates

### Gate P2-A — Master Plan

状态：`PASSED / PR #203 MERGED / B_C2_PLAN_APPROVED FROZEN`。用户已批准：

- 19 Plan / Task Packet slots（`02-00..18`）；
- 13 controlled Waves（`W0..W12`）；
- max 2 concurrent writers；
- new `integration/e2e01-cycle2` recommendation；
- 两个 pre-approval blockers 的处理方向；
- `02-00` zero-code owner correction 和 `02-16` canonical lifecycle ruling 均按
  一对一 Plan / Task Packet 管理；
- 每 Wave完成后回到用户 checkpoint。

### Gate P2-A1 — W4 prerequisite remediation amendment

状态：`USER_APPROVED / CORRECTION SET REVIEWED MERGED / B_C2_W4_READY CONFIRMED / W4 REFREEZE REVIEW`。W4 preflight 证明旧
`02-06/08/09/13` freeze 假设无法形成可执行闭包；用户于 2026-08-01 授权先修复再
开始 W4，并要求缩短 reviewer 周期。该授权只增加：

- `02-02R/02-04R/02-05R` 三个一对一 correction Packet；
- `W3R` correction wave；
- 22 slots / 14 wave labels / max 2 writers；
- 在真实 `B_C2_W4_READY` 上重冻结 W4 四个 Packet。

它不授权修改 Case lifecycle、扩大 P0 scope、跳过 planning/final exact-head review、
并行 merge 或伪造未来 SHA。

### Gate P2-A2 — 02-09 recovery owner correction

状态：`OWNER_GAP_CONFIRMED / OWNER_RULING REVIEW`。02-09 exact preflight 后的只读
owner review 证明现有四文件 Packet 无法通过 shared contract 表达 unfinished
parent-only recovery、durable recovery decision child 或
`RETRY_SCHEDULED + RUN_BUDGET_EXHAUSTED` terminal。当前 02-09 source 保持 clean；
禁止在 service 文件内私藏 command / Port。最小 correction set 固定为
`02-09R1/R2/R3` 三个 single-writer Packet，后续必须逐个用真实 predecessor SHA/tree
重冻结、bounded review、串行 merge，再重冻结 02-09。该裁决不推进 Case lifecycle，
不增加 Action、`RESULT_UNKNOWN`、shared Trace 字段或 top-level business record。

### Gate P2-B — Exact Plan / Task Packet set

状态：`IN_PROGRESS / W1-W3R COMPLETE / W4 BATCH A MERGED / 02-09 R1-R3 PENDING`。P2-A 通过后始终按
真实 dependency barrier 分批准备；不得给尚未产生的 barrier 填造 SHA。W3 reviewed
merge 已真实形成 `B_C2_APP_CONTRACT = 86d1b8357f817882b017e5c4306ec855e0b288e6`
/ tree `b27f5f805c85e8ce76c30be254a004cb5f127b4e`；owner-ruling、02-02R 与 02-04R
已依次形成 `B_C2_W3R_RULING`、`B_C2_INPUT_BINDING_V2`、
`B_C2_SELECTED_TARGET_GATEWAY` 与最终 `B_C2_W4_READY = 5f2fa6d...` / tree
`174fbebc...`。W4 `02-06/08/09/13` 四份Plan已从该同一product base重冻结并经
planning provenance merge；02-06/13 已 reviewed implementation merge，02-08 正在执行。
02-09 必须等待 Gate P2-A2 owner ruling 与 R1-R3 exact Plan provenance，旧 Plan 不再是
当前可执行输入。

用户需逐项或整组批准：

- 每个 GSD Plan / Task Packet的一对一映射；
- exact `B_C2_OWNER_ALIGNED` SHA / tree，并批准它作为唯一允许的
  `B_C2_START / initial implementation base` 值；branch / Worktree identity；
- allowlist / forbidden files；
- verification、security、Eval、rollback；
- Wave dispatch 上限。

### Gate P2-C — Implementation activation

状态：`PASSED / HISTORICAL`。以下保留 activation 输入与顺序；W4 不重复创建
integration branch，而是继续使用受保护的 `integration/e2e01-cycle2`。

仅当以下全部成立：

```text
master Plan approved + merged
AND C2-BLOCK-01 approved
AND 02-00 reviewed + merged
AND B_C2_OWNER_ALIGNED exact SHA/tree frozen
AND all launchable Plan/Task Packet pairs exact-head reviewed
AND user approves branch activation + Wave + concurrency
```

以上是 Gate P2-C 的输入条件。Gate P2-C 只按以下顺序激活：

1. 从 exact `B_C2_OWNER_ALIGNED` 创建 `integration/e2e01-cycle2`；
2. 立即证明新 branch 的 exact head / tree 与 `B_C2_OWNER_ALIGNED` 相同，并冻结为
   `B_C2_START = initial implementation base`；
3. equality preflight 通过后，才允许为已批准的首个 Wave 创建代码 Worktree /
   feature branch并写功能代码。

Gate P2-C 前不得创建 Phase 2 integration / feature branch；第 2 步失败时立即把
错误 branch 标记为不可用并停止，由 Integrator 提交精确 remediation / 用户裁决，
不得继续第 3 步。

## 14. Plan acceptance criteria

本 Plan 只有在以下条件全部满足后才能从 `PLAN_REVIEW_DRAFT` 变为
`PLAN_APPROVED`：

- [x] dependency / ownership / risk map 已独立复核。
- [x] `C2-BLOCK-01/02` 有明确用户裁决或被列为 Task Packet 前的强制 owner
      remediation，且不会由 Executor猜测。
- [x] 原 19 slots / 13 Waves / max concurrency 2 已由 Gate P2-A 批准；当前用户又
      明确批准三个 correction slots 与 `W3R`，形成 22 slots / 14 wave labels，
      并发上限仍为 2。
- [x] 每个 R01–R18、D1–D8、四个 Case至少有一个实现和一个验证 owner。
- [x] same-wave proposed file intersection为零。
- [x] single-writer hotspots唯一。
- [x] `.planning/config.json`、`.planning/GOVERNANCE.md`、Project / Roadmap /
      State 的 Phase 2 reserved branch mapping一致，且没有改写 Phase 1 历史
      branch 证据。
- [x] threat model覆盖 owner scope、binding、freshness、retry、migration、
      obsolete Run、disclosure、Eval lifecycle / evidence 与 read-only
      Action hard prohibition。
- [x] independent exact-head Plan review为 `PASS`。
- [x] planning PR只包含获批 planning artifacts、Phase 2 branch
      governance / config 与必要状态索引，无源码、测试、migration、Eval artifact
      或 Case lifecycle mutation。
- [x] planning PR合并后才准备 exact GSD Plan / Task Packet set。
