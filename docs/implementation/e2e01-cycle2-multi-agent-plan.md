# E2E-01 Cycle 2｜Codex 多 Agent 实施计划

更新日期：2026-08-02

状态：`NON_NORMATIVE / PLAN_APPROVED / W9_OWNER_CORRECTIONS_APPROVED`

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
> `02-06/08/09/13` 已从该同一 product barrier重冻结并 reviewed merge。02-09
> preflight 后确认 shared recovery contract 无法表示 unfinished parent-only
> terminal、durable recovery decision child 与 `RETRY_SCHEDULED + budget exhausted`
> terminal，因此先增加 `02-09R1/R2/R3` 三个 single-writer correction Packet；三者
> 已由 PR #234/#237/#239 reviewed merge并形成
> `B_C2_02_09_READY = cdf8c194ff80c9f47d6587bef9b5b386f29e5341` / tree
> `2e82f1b9708f44df1bec7b16eaa7774e55d60ed3`。replacement 02-09 exact-head
> review 随后发现两个跨 shared Application owner 的 HIGH：initial bare ToolCall CAS
> 未在 fence 时重验 current state/bindings；recovered fence 只返回 enum，使 executor
> 继续使用 pre-CAS budget。该 implementation head未发布；先增加 `02-09R4 / W4R2`
> dispatch-grant correction，再从真实 R4 successor第二次重冻结 02-09。
> W5 已完成并形成
> `B_C2_PHYSICAL = bf8e88b2c0124aee82dffc7e54ae03ec0fdbea50` / tree
> `fccc5a1f87a0b00dd31ba61ee8c960901c7601da`。W6 preflight 证明 canonical
> Cycle 2 Spec 把 `SearchOrdersQuery/Result` 与 `GetShipmentQuery/Result` 的 outbound
> Business Read Port 声明归属 Application，但当前 `02-07` Infrastructure allowlist
> 无权补全该边界。用户于 2026-08-02 明确授权先新增 `02-07R`
> Application-owner correction Packet，将总 slot 数从 26 调整为 27；不新增
> Wave label。`02-07/02-11` 只能在 reviewed `02-07R` 真实 successor 上重冻结。
> PR #251/#252 随后reviewed完成 `02-07R` 并形成
> `B_C2_BUSINESS_READ_PORTS = c775ef45eb42c9f03e63d0065d493e2fb2a43556` /
> tree `c598651b56db003e6ab77a08d266d709a0ff8e76`；PR #253 又从该
> successor 重冻结 `02-07/02-11`。但 02-07 preflight 证明 W5 physical schema
> 未实现现行 canonical contract 必需的 search-authority `status` 与
> `snapshot_resource_ref` 指向的 durable raw snapshot storage；现有 02-07
> allowlist 无法合法生成两者。用户于 2026-08-02 明确授权“有问题的话
> 就按照你的建议走”，因此先增加 `02-10R` Infrastructure physical correction，
> 将 slot 数从 27 调整为 28，不新增 Wave label。`02-07/02-11`
> 的旧 exact Plans 与 clean Worktrees 都保持暂停，必须等 reviewed `02-10R`
> 真实 successor 后再重冻结。该 correction 只补全已有 contract 的物理
> 表示，不改写 Business / source-version / disclosure / lifecycle 语义。
> PR #255/#256 随后 reviewed 完成 `02-10R` 并形成
> `B_C2_SEARCH_AUTHORITY_PHYSICAL = 64254f170ced8a71d58fd2f0b0d1adfaa8f275a5` /
> tree `ad332f6b862d34feec342c57e679d7234179e24e`；PR #257 从其真实
> successor 第二次重冻结 `02-07/02-11`，PR #258 reviewed 完成 `02-07` 并形成
> `B_C2_BUSINESS_ADAPTERS = 78bce02c36ada33d6695d5a919d23b61bb8df21e` /
> tree `032e0c5edfb3c2ffc18f34192ae72858bc0cec85`。`02-11` focused / neighbor
> 实现验证随后暴露 existing OA-10 contract 的物理历史缺口：versioned
> superseded Run 必须读取与 `base_task_state_version` 精确匹配的旧
> `TaskRecord` 与 `RequestUnitRecord` 图，而当前 `p0_records` 只保留 mutable current
> projection，无法无损重建旧 binding / open-question / observation 状态。该
> implementation 已保存为 unpublished blocked checkpoint，严格返回 no closure，
> 不伪造旧图。依据用户同日“有问题按照你的建议走”的授权，增加 `02-11R`
> record-history physical correction，将 slot 数从 28 调整为 29，不新增 Wave
> label；先建立 owner-scoped immutable pre-image storage，再从其 reviewed
> successor 重冻结并回放 `02-11`。该 correction 不降低
> `SupersededRunReadClosure` 或改变 OA-10 canonical 语义。
>
> W7/W8 已reviewed完成并分别冻结`B_C2_RUNTIME`与`B_C2_EVAL_MACHINERY`。
> W9 `02-15`只读preflight随后确认三个跨owner BLOCK：active Spec只有fixture ref
> 与静态digest而没有可认证seed payload；Application没有实现正常Cycle 2
> `AgentRunHandler`、v2 Run / Message / ordinary Trace terminal contract；
> Infrastructure没有这些normal writes / exact reader与三READ business-result
> dispatch adapter。把这些逻辑或直写SQL塞进`bootstrap.py`会跨越Spec、Application、
> Infrastructure ownership并形成第二套Runtime，违反§11.6。依据用户2026-08-02
> “有问题按照你的建议走”的授权，W9在原wave内增加串行`02-15R0/R1/R2`，slot数
> 从29调整为32、不新增wave label：R0只修active seed contract，R1只补Application
> normal use-case / Port，R2只补Infrastructure implementation / typed seed；之后才从
> 真实reviewed successors重冻结`02-15`。`http.py`现有trusted Session边界足够，
> correction与02-15均不得无证据修改外部HTTP contract。
>
> `02-15R1` planning reviewed后、writer写入前又确认一个独立Core/Intent owner BLOCK：
> `ModelProviderV2`的`RequestUnderstandingOutputV2`只能表达`order_id`，existing initial
> reducer也只生成v1 `InputBinding`；现有`Cycle2InputCandidate`虽能表达
> `product_description`，但其reducers全部要求已存在current Task。因此在R1六文件
> Application allowlist内无法真实形成首轮`search_orders`，若由Application自行解析会
> 复制或绕过Intent/Core contract。依据同一用户授权，Gate P2-A8在W9原wave内增加
> 串行`02-15R1A` Core correction，将slot数从32调整为33、不新增wave label；R1A
> 只补Cycle2首轮RU output/reducer与InputBindingV2，reviewed后R1必须从真实successor
> 重冻结回放，不得提交只支持旧`order_id`的partial handler。
>
> R1A reviewed完成且R1从真实successor重冻结后，writer在成功工具路径接线前又确认
> 一个更窄的Application executor symbol BLOCK：`Cycle2ReadToolExecutor`内部接收并
> 校验typed `ToolResult`，但public `execute()`只返回`ToolCallRecordV2`，导致normal
> handler无法将search/shipment payload交给既有step service；当前没有post-execution
> typed envelope。把该mapping推给Infrastructure会越过Application ownership。依据同一
> 用户授权，Gate P2-A9在W9原wave内增加串行`02-15R1B`，slot数从33调整为34、不新增
> wave label；R1B只给read executor增加backward-compatible typed execution envelope，
> 保留legacy `execute()`形状。当前R1两文件dirty checkpoint不发布，R1B reviewed后
> R1再次从真实successor重冻结回放。
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
| Future GSD Plans | `W1-W8 + 02-15R0/R1A COMPLETE / 02-15R1B EXECUTOR CORRECTION APPROVED / 02-15R1 IMPLEMENTATION BLOCKED UNTIL SECOND REFREEZE` |
| Task Packets | `27 COMPLETE / 02-15R1B PLAN PENDING / 02-15R1 REFROZEN-BLOCKED / 02-15R2/15 NOT REFROZEN` |
| Proposed Plan / Packet slots / Waves | `34 / 16`（原 `02-00..18` + `02-02R/04R/05R` + `02-09R1/R2/R3/R4` + `02-07R/10R/11R` + `02-15R0/R1A/R1B/R1/R2` / 原 `W0..W12` + `W3R/W4R/W4R2`） |
| Planning input SHA | `b96fe8adf8ce4bcadbdf2cf008e28be4ff9aa5a3` |
| `B_C2_PLAN_APPROVED` | `2879f5226a073051d1550fe079b4a427c1ec8cb1` / tree `d5ded99bb0439fb57bbb4d6057fbda7a12b21fdf` |
| Initial implementation base | `B_C2_START = 4dc6dc95de81080fb3b651bc2f0026fb046fd9f8` / tree `521ac2c7611b20683089ab41a74d07c9a2bb8fc7` |
| Integration branch | `integration/e2e01-cycle2 / ACTIVE / d6fdcbb3cdd4e6bb41fb2ae0b1ff5b80629b4efb` / tree `8ab6f2aeab53bfae73edff219cab70623c437ebc` |
| GSD config branch mapping | `integration/e2e01-cycle2 / ACTIVE` |
| `02-00` execution branch / Worktree | `COMPLETE / REVIEWED MERGE` |
| Integration / code feature branches / Worktrees | `W1..W8 + 02-15R0/R1A COMPLETE；02-15R1 refrozen dirty-blocked unpublished；02-15R1B/R2与02-15尚未dispatch` |
| Writer assignments | `Integrator W9 owner-ruling single writer ACTIVE；implementation writer 0` |
| Execution concurrency | approved ceiling `2` writers；当前 implementation writer `0` |

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

以下 34 个 slot 是当前冻结集合：原 `02-00..18` 保持编号与 ownership；
`02-02R/02-04R/02-05R` 是用户授权的 W4 前 correction set，
`02-09R1/02-09R2/02-09R3` 是 02-09 preflight 触发的 recovery owner correction
set，`02-09R4` 是 replacement exact-head review触发的 dispatch-grant correction，
`02-07R` 是 W6 preflight 触发的 Application Business Read Port owner correction，
`02-10R` 是后续 Adapter preflight 触发的 Infrastructure physical search-authority
correction，`02-11R` 是 02-11 实现验证触发的 immutable Task / RequestUnit
pre-image history correction；`02-15R0/R1/R2` 是W9 preflight触发的seed owner、
Application normal entry与Infrastructure normal evidence/dispatch corrections；
`02-15R1A`是R1写前preflight触发的Cycle2首轮RU Core owner correction；
`02-15R1B`是R1成功工具路径接线触发的Application executor result-envelope correction。
`02-00` 是零功能代码的
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

### `02-07R` — Application Business Read Port owner correction

- **Owner:** Runtime Engineer / Application outbound ports（single writer）。
- **Goal:** 仅按现行 Cycle 2 Spec 补全 `SearchOrdersPort` 与
  `GetShipmentPort` 的 Application-owned Protocol 声明，使后续 Infrastructure
  Adapter 实现有明确 Port 边界；不更改 DTO、Adapter、Runtime、Action 或
  Case lifecycle。
- **Proposed files:**
  - `src/mini_agent/application/ports.py`
  - `tests/component/application/test_ports_contract.py`
- **Depends on:** reviewed `B_C2_PHYSICAL` 与 2026-08-02 用户对 owner correction /
  `26 → 27` slot 调整的明确授权。
- **Acceptance:** 两个 Protocol 只消费 canonical `SearchOrdersQuery/Result` 与
  `GetShipmentQuery/Result`；保持 async 调用面与 strict DTO 边界；不扩大
  `customer_id` 或授权来源；不实现查询、持久化、组装、工具注册或
  lifecycle 变更。

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
- **Depends on:** reviewed `02-01/05/10` barriers 与 reviewed `02-07R` 真实 merge
  successor，以及 reviewed `02-10R` 真实 merge successor；PR #253 的旧 Plan
  不可执行，必须从 `02-10R` successor 重冻结 exact base/tree/blobs。
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
  `02-09R1/02-09R2/02-09R3/02-09R4` exact barriers；当前四文件 head因两个
  shared-owner HIGH未发布，只有 R4 真实 successor 后的 replacement Plan可执行。
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

### `02-09R4` — Application dispatch-fence grant contract

- **Owner:** Runtime Engineer / Application contract single writer。
- **Goal:** 关闭 initial fence current-state TOCTOU 与 recovered fence pre-CAS budget
  authority；增加非持久化 `Cycle2ReadDispatchGrant`、initial atomic wrapper，并使
  initial / recovered Port 只以 same-CAS `APPLIED` identity + timeout grant授权 dispatch。
- **Proposed files:**
  - `src/mini_agent/application/records.py`
  - `src/mini_agent/application/ports.py`
  - `tests/component/application/test_record_contracts.py`
  - `tests/component/application/test_ports_contract.py`
- **Depends on:** 本 dispatch-grant owner ruling reviewed merge；exact base由后续 Plan
  在真实 integration successor冻结。
- **Acceptance:** initial CAS重验 owner/current Run/link/Task/RequestUnit/bindings/target /
  budget；recovered CAS返回本次 attempt2 same-CAS timeout；non-APPLIED grant全空、零写、
  零dispatch；裸 enum / old closure number无authority；grant无schema/codec/migration /
  Action surface。

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

### `02-10R` — Physical search-authority closure

- **Owner:** Infrastructure Engineer / migration + ORM single writer。
- **Goal:** 关闭 02-07 preflight 确认的两个 existing-contract physical 缺口：
  为 `mock_order_search_documents` 增加 closed `OrderStatus` authority，并增加
  `snapshot_resource_ref` 指向的 owner-scoped durable raw search snapshot storage；
  不修改历史 revision `20260731_0004`。
- **Proposed files:**
  - `alembic/versions/20260802_0005_cycle2_search_authority_correction.py`（new）
  - `src/mini_agent/infrastructure/persistence/models.py`
  - `tests/integration/test_database_migrations.py`
- **Depends on:** reviewed `B_C2_BUSINESS_READ_PORTS`、PR #253 planning-control
  successor、两个 independent `PASS-CONFIRMED BLOCK` reviews，以及 2026-08-02
  用户对按建议执行 correction 的明确授权。
- **Acceptance:** new linear head 仅以 `20260731_0004` 为 parent；search status
  与 Core `OrderStatus` closed set 精确相等；existing row 只从 exact owner/order
  parent payload 全量预验证后原子回填，不猜测默认值；durable snapshot 使用
  Adapter-supplied opaque ref、trusted owner、UTC observed time 与 closed JSON object，无
  DB default ref；non-empty search evidence 阻断 destructive downgrade；两条 upgrade
  path、DML/downgrade lock race、Phase 1 `order_payload/get_order` byte identity、exact
  model/schema/index/check 均有可复现证据。

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
- **Depends on:** reviewed `02-06/10` barriers、reviewed `02-07R/10R/11R` 与
  reviewed `02-07` 真实 merge successors；blocked checkpoint
  `da8ee98178dc4a69c32253b68cc897c7c5556711` 只可作为 source patch 参考，
  不得发布或直接作为 feature head；必须从真实 `02-11R` successor 重冻结
  exact base/tree/blobs 并回放。
- **Acceptance:** half-write、wrong-owner、dangling、duplicate、mixed version、
  retry fence conflict 全部零部分写入并 fail closed；本 slot 不产生 confirmation、
  ActionPolicy、idempotency claim / key、Action Ledger write 或 `RESULT_UNKNOWN`
  side-effect recovery。

### `02-11R` — Immutable Task / RequestUnit pre-image history

- **Owner:** Infrastructure Engineer / migration + ORM single writer。
- **Goal:** 补全 OA-10 已有 exact obsolete graph contract 的物理承载：新增
  owner-scoped immutable `TaskRecord` / `RequestUnitRecord` pre-image history；
  不修改 `SupersededRunReadClosure`、不把 Memory 当业务事实，也不为迁移前已丢失的
  历史补造内容。
- **Proposed files:**
  - `alembic/versions/20260802_0006_cycle2_record_state_history.py`（new）
  - `src/mini_agent/infrastructure/persistence/models.py`
  - `tests/integration/test_database_migrations.py`
- **Depends on:** reviewed `B_C2_BUSINESS_ADAPTERS`、02-11 blocked checkpoint 的
  focused `109 passed` / neighbor `1340 passed` / compile / diff evidence，以及
  2026-08-02 用户对按建议修复后继续的明确授权。
- **Acceptance:** new linear head 仅以 `20260802_0005` 为 parent；history row 使用
  Adapter-supplied UUID、trusted owner scope、closed `task_record/request_unit_record`
  code/version、exact logical identity、positive state version 与 closed JSON object
  envelope，无 DB-generated identity；`record_code + logical_identity + state_version`
  唯一并有 owner-scoped lookup index；表不以 FK 绑定 mutable current row；非空
  history 阻断 destructive downgrade。升级只创建空 history，不猜测既有 pre-image；
  后续 `02-11` 必须在替换 current Task / RequestUnit 前于同一事务写入并校验 exact
  pre-image，按 trusted owner + identity + exact version 读取，duplicate-identical 可
  幂等、duplicate-conflicting fail closed，事务 rollback 不得留下孤立 history。

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

### `02-15R0` — Authenticated offline fixture seed contract

- **Owner:** Cycle 2 scoped Spec owner / documentation single writer.
- **Goal:** 把现有fixture ref升级为可实现、可认证、不可由Eval oracle反推的closed
  offline seed contract；不修改artifact、loader、源码、测试或Case lifecycle。
- **Proposed files:**
  - `docs/implementation/e2e01-cycle2-implementation-spec.md`
- **Depends on:** reviewed `B_C2_EVAL_MACHINERY`、W9 preflight BLOCK与用户
  2026-08-02“有问题按照你的建议走”的授权。
- **Acceptance:** 每个W9所需fixture ref拥有exact owner/session、trusted clock、
  order/search/shipment或initial record graph payload与fault plan；未知、缺失、冲突
  或跨owner seed零写fail closed；pair digest由解析后真实共同seed canonical
  projection重算，不能由常量自证；script、expectation与grader predicate不得成为
  seed、业务事实或fault authority。

### `02-15R1` — Normal Cycle 2 Application entry and evidence contracts

- **Owner:** Runtime Engineer / Application single writer.
- **Goal:** 补全真正实现`AgentRunHandler`的normal Cycle 2 use-case，以及v2 Run、
  USER/ASSISTANT Message、initial product-description graph、ordinary Trace与terminal
  exact evidence的commands / Ports；复用既有reducers、Gateway、W7 step service与三
  Business Read Ports，不把Composition或Infrastructure细节引入Application。
- **Proposed files:**
  - `src/mini_agent/application/records.py`
  - `src/mini_agent/application/ports.py`
  - `src/mini_agent/application/agent_run_service.py`
  - `tests/component/application/test_record_contracts.py`
  - `tests/component/application/test_ports_contract.py`
  - `tests/component/application/test_agent_run_service.py`
- **Depends on:** reviewed `02-15R1B`真实successor、R1A/R0 contracts与`B_C2_RUNTIME`。
- **Acceptance:** message-only trusted command可形成normal v2 Run closure；
  UNIQUE/MULTIPLE/ordinal/order-only/shipment/retry/obsolete routes只消费exact current
  authority；normal terminal把Run/link/Task/Message/ordinary Trace/result在一个Port
  command中原子闭合；wrong-owner、stale、partial、contradictory与OA-10路径零错误
  出站；不实现DB、seed、HTTP、Harness或lifecycle。

### `02-15R1A` — Cycle 2 initial product-description RU contract

- **Owner:** Core / Request Understanding single writer.
- **Goal:** 在不改变Phase 1 `RequestUnderstandingOutputV2`和initial reducer的前提下，
  增加closed Cycle2 first-turn output与initial reducer，使可信current message中的
  `product_description` USER_CLAIM能够形成clean initial Task / RequestUnit /
  `InputBindingV2`及可由Gateway复核的next move；不执行Tool、不写Runtime。
- **Proposed files:**
  - `src/mini_agent/core/request_understanding.py`
  - `src/mini_agent/core/request_processing.py`
  - `tests/component/core/test_request_understanding_contract.py`
  - `tests/component/core/test_request_processing.py`
- **Depends on:** reviewed `B_C2_W9_SEED_CONTRACT`、R1 clean preflight BLOCK与用户
  2026-08-02“有问题按照你的建议走”的授权。
- **Acceptance:** first-turn output只允许exact `product_description` Claim和已存在的
  bounded next-move shape；source ref/quote/current message/customer owner/time/UUID与
  exact-one candidate graph全部确定性校验；reducer产生`InputBindingV2`和clean v1
  Task/RequestUnit roots，不生成owner、verified target、Observation、Tool result或
  business fact；unknown/ordinal/shipment flag/multiple/duplicate/wrong-source/
  model-trusted field全部fail closed；Phase 1模型与reducer public shape不变。

### `02-15R1B` — Cycle 2 typed read-execution envelope

- **Owner:** Runtime Engineer / Application read executor single writer.
- **Goal:** 为`Cycle2ReadToolExecutor`增加additive typed execution envelope，使normal
  handler能同时消费terminal `ToolCallRecordV2`与本次已校验`ToolResult`；保留现有
  `execute()`返回形状和全部fence/retry/CAS语义。
- **Proposed files:**
  - `src/mini_agent/application/read_tool_executor.py`
  - `tests/component/application/test_read_tool_executor.py`
- **Depends on:** reviewed `B_C2_W9_INITIAL_RU`、R1 refrozen dirty checkpoint BLOCK与用户
  2026-08-02“有问题按照你的建议走”的授权。
- **Acceptance:** 新`execute_with_result()`复用同一insert/fence/dispatch/retry/finalize
  流程；只有terminal finalize `APPLIED`才返回该attempt exact validated `ToolResult`；
  timeout、insert/fence/finalize conflict、recovery/no-dispatch均为`None`；transient retry
  只暴露attempt 2结果，不返回attempt 1 payload；legacy `execute()`继续只返回terminal
  ToolCall且现有tests不变；不创建Infrastructure Port、不构造Observation/CandidateSet/
  Assessment、不修改handler、DB、HTTP、Harness或Case lifecycle。

### `02-15R2` — Normal Cycle 2 Infrastructure and typed seed adapters

- **Owner:** Infrastructure Engineer / PostgreSQL + offline Mock adapters single writer.
- **Goal:** 实现R1 normal writes / owner-scoped exact reader、三READ business-result
  dispatch adapter与R0 typed seed catalog；复用现有generic records/reference schema与
  business tables，不以bootstrap SQL、Eval oracle或test helper替代生产边界。
- **Proposed files:**
  - `src/mini_agent/infrastructure/persistence/postgres.py`
  - `src/mini_agent/infrastructure/cycle2_runtime.py`（proposed new）
  - `src/mini_agent/infrastructure/cycle2_fixture_seed.py`（proposed new）
  - `tests/integration/test_postgres_record_adapters.py`
  - `tests/integration/test_agent_run_service_v2_persistence.py`
  - `tests/integration/test_cycle2_runtime_adapter.py`（proposed new）
  - `tests/integration/test_cycle2_fixture_seed.py`（proposed new）
- **Depends on:** reviewed `02-15R1`真实successor与R0 seed contract。
- **Acceptance:** normal v2 root/start/finalize/Trace写入和exact-Run reader使用同一
  owner-scoped transaction closure；三READ dispatch把受控Business Port结果映射为
  exact `ToolResult`，fault只来自authenticated seed plan；seed unknown/missing/
  conflict/cross-owner零写；pair digest从真实seed重算；现有schema足够时不得新增
  migration；不装配HTTP/Harness、不生成Eval Result或推进Case。

### `02-15` — Pre-activation Composition / HTTP execution seam

- **Owner:** Tech Lead / Integrator.
- **Goal:** 在 Case 保持 `CONTRACT_DEFINED` 时完成三工具真实装配、Fixture seed
  与 HTTP → trusted Session → Runtime → owner-scoped Mock systems →
  PostgreSQL → exact evidence 的可复现 execution seam；不得通过 Eval Harness
  dispatch 或生成 Phase 2 Eval Result。
- **Proposed files:**
  - `src/mini_agent/bootstrap.py`
  - `tests/integration/test_offline_composition_root.py`
  - `tests/integration/test_e2e01_cycle2_execution_seam.py`（new）
- **Depends on:** reviewed `02-07/11/12/14/15R0/15R1/15R2`真实barriers。
- **Acceptance:** direct non-Harness integration tests证明四个 Case 的真实入口能产生
  typed Run / record / Trace evidence；同一 RegistrySnapshot exact 包含三个 READ
  tools；Phase 1 Composition 回归通过；同时 Harness 对 Cycle 2
  `CONTRACT_DEFINED` batch 仍在 SUT 前 fail closed，Phase 2 Result 数为零；现有
  `http.py` trusted Session contract只作为imported regression，不在本slot修改。

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
| `W4R` | `02-09R1 → 02-09R2 → 02-09R3` | 1 | recovery owner corrections serial merge；历史形成 `B_C2_02_09_READY` |
| `W4R2` | `02-09R4` | 1 | dispatch-grant contract correction；形成新的 exact `B_C2_02_09_DISPATCH_READY` |
| `W4 resumed` | `02-09` | 1 | 仅从 `B_C2_02_09_DISPATCH_READY` 第二次重冻结后执行；形成 `B_C2_LEAVES` |
| `W5` | `02-10` | 1 | `B_C2_PHYSICAL` |
| `W6` | `02-07R → 02-10R → 02-07 → 02-11R → 02-11` | 1 | 前四项依次补全 Application Port、search authority、business adapters 与 immutable record history；blocked 02-11 只能从真实 R successor 重冻结回放；形成 `B_C2_INFRA` |
| `W7` | `02-12` | 1 | `B_C2_RUNTIME` |
| `W8` | `02-14` | 1 | `B_C2_EVAL_MACHINERY`；Case 仍为 `CONTRACT_DEFINED` |
| `W9` | `02-15R0 → 02-15R1A → 02-15R1B → 02-15R1 → 02-15R2 → 02-15` | 1 | seed contract、Core first-turn RU、typed read-execution envelope、Application normal entry与Infrastructure normal evidence/dispatch依次reviewed后重冻结Composition；形成`B_C2_EXECUTION_SEAM`；Case仍为`CONTRACT_DEFINED` |
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
W6 Application Business Read Port correction
  ↓
W6 physical search-authority correction
  ↓
W6 business adapters
  ↓
W6 immutable Task / RequestUnit pre-image history correction
  ↓
W6 PostgreSQL persistence / recovery
  ↓
W7 Runtime mapper / Renderer
  ↓
W8 Graders / Harness machinery; pre-dispatch fail closed
  ↓
W9 seed contract owner correction
  ↓
W9 Core initial product-description RU correction
  ↓
W9 Application typed read-execution envelope correction
  ↓
W9 Application normal entry/evidence correction
  ↓
W9 Infrastructure normal evidence/dispatch/typed-seed correction
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
| `R01` | `13,14,15R0,15R1,15R2,15,16,17,18` |
| `R02` | `01,07,08,12,14,15R1,15R2,15,18` |
| `R03` | `01,07,13,14,15R0,15R2,15,18` |
| `R04` | `01,12,14,15R1,15R2,15,18` |
| `R05` | `02,05,06,11,15R1,15R2` |
| `R06` | `02,08,11,14,15R1,15R2` |
| `R07` | `07,08,12,14,15R1,15R2` |
| `R08` | `01,04,07,08,14,15R1,15R2` |
| `R09` | `01,02,07,11,14,15R1,15R2` |
| `R10` | `02,09,12,14,15R1,15R2` |
| `R11` | `01,02,12,14,15R1,15R2` |
| `R12` | `04,05,09,11,14,15R1,15R2` |
| `R13` | `04,07,09,12,14,15R1` |
| `R14` | `03,05,09,12,14,15R1` |
| `R15` | `04,08,13,15R0,15R2,15,18` |
| `R16` | `02,03,05,06,09,10,11,14,15R1,15R2` |
| `R17` | `13,14,15R0,15R1,15R2,15,16,17,18` |
| `R18` | `16,17,18` + post-execution quality gates |

| Case | Slots |
|---|---|
| `E2E01-02` | `01,07,08,12,13,14,15R0,15R1,15R2,15,16,17,18` |
| `E2E01-03` | `02,08,11,12,13,14,15R0,15R1,15R2,15,16,17,18` |
| `E2E01-05` | `04,07,08,12,13,14,15R0,15R1,15R2,15,16,17,18` |
| `E2E01-06` | `01,02,03,04,07,09,11,12,13,14,15R0,15R1,15R2,15,16,17,18` |

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
- `02-09R4 = TARGETED_DISPATCH_GRANT_CONTRACT`：只审 initial/recovered atomic wrapper、
  owner/current graph与budget same-CAS、APPLIED grant closed matrix、identity/timeout exact
  bind、bare-enum/old-budget旁路消失，以及 non-persistent/no-codec/no-Action boundary。

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
| model / Eval fabricates business evidence | CRITICAL | deterministic projection/mapper、authenticated artifacts、typed seed、real HTTP SUT | `12,13,14,15R0,15R2,15,18` |
| `CONTRACT_DEFINED` Case dispatched或 artifact 自激活 | CRITICAL | Harness pre-dispatch fail closed；reviewed execution seam；独立 owner ruling；atomic lifecycle / manifest / loader sync | `13,14,15R0,15R1,15R2,15,16,17,18` |
| read-only phase enables Action / side effect | CRITICAL | exact Registry 仅三个 `READ` tools；无 confirmation、ActionPolicy、idempotency claim/key、Action Ledger write 或 `RESULT_UNKNOWN` side-effect recovery | `04,09R1,09R2,09R3,09R4,11,13,15R1,15R2,15,18` |
| fixture ref / static digest被误当成可信seed | CRITICAL | active Spec closed payload；typed seed loader；真实canonical projection重算digest；禁止script/expectation/grader反推 | `15R0,15R2,15` |
| bootstrap直写DB或复制Application Runtime | CRITICAL | normal use-case/Port先由Application owner闭合，Infrastructure实现后Composition只装配 | `15R1,15R2,15` |
| bare ToolCall CAS or stale budget grants dispatch | CRITICAL | initial/recovered writer same-CAS重验完整current graph与budget；只返回identity-bound `Cycle2ReadDispatchGrant`；裸enum/old closure无authority | `09R4,09` |
| mutable current rows丢失 obsolete exact graph | CRITICAL | Task / RequestUnit pre-image按owner/identity/version不可变保存；与current replace同事务；迁移前缺失历史继续fail closed | `11R,11` |

任何 CRITICAL / HIGH threat 缺少可复现 mitigation evidence 都阻断 slot merge、Wave
barrier 与 release。

</threat_model>

## 11. Risk controls learned from Phase 1

1. **先完整暴露 slots，不用“大包”隐藏复杂度。** 原 19 slots / 13 wave labels 与
   Gate P2-A1 的 22 / 14 都保留为历史批准层级；本轮“有问题先修复”的用户指令经
   Gate P2-A2 收口为增加 `02-09R1/R2/R3` 与 `W4R`；replacement 02-09 review的两个
   HIGH 再由 Gate P2-A3 增加 `02-09R4 / W4R2`；W6 Application Port owner
   缺口经 2026-08-02 用户明确授权由 Gate P2-A4 增加 `02-07R`，不增加
   wave label；Adapter preflight 确认的 physical 缺口经同日用户“有问题按建议走”
   授权由 Gate P2-A5 增加 `02-10R`，仍不增加 wave label；02-11 实现验证发现的
   OA-10 physical history 缺口又经同日用户授权由 Gate P2-A6 增加 `02-11R`，仍不
   新增 wave label。W9 preflight发现的seed、Application normal entry与Infrastructure
   normal evidence/dispatch跨owner缺口又经同日用户授权由Gate P2-A7增加
   `02-15R0/R1/R2`，仍不新增wave label。R1写前确认的首轮RU Core owner缺口再由
   Gate P2-A8增加`02-15R1A`，Gate P2-A9再增加`02-15R1B`，均不新增wave label。
   当前冻结集合为34 slots / 16 wave labels /
   max 2 writers。
   后续再增减任一 slot 仍需重新裁决 master Plan。
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

### Gate P2-A3 — 02-09 dispatch-grant owner correction

状态：`OWNER_GAP_CONFIRMED / OWNER_RULING REVIEW`。R1/R2/R3 reviewed merge并从真实
`B_C2_02_09_READY` 重冻结 02-09 后，bounded exact-head review发现两个不能在四文件
service Packet内关闭的 HIGH：initial attempt只CAS ToolCall，无法证明 fence时 Task /
binding/target仍current；recovered writer same-CAS重算预算却只返回enum，使Executor可用
pre-CAS数字设定timeout。该02-09 head保持local clean且未发布。最小correction固定为
`02-09R4 / W4R2`：Application-private non-persistent dispatch grant + initial/recovered
atomic Port contract。R4 reviewed merge后必须从真实 successor第二次重冻结02-09；不得
rebase/push旧head。该裁决不推进Case lifecycle，不增加codec/migration/top-level record、
Action或`RESULT_UNKNOWN` side-effect path。

### Gate P2-B — Exact Plan / Task Packet set

状态：`IN_PROGRESS / W1-W3R COMPLETE / W4 02-06/13/08 + R1/R2/R3 MERGED / 02-09R4 OWNER RULING`。P2-A 通过后始终按
真实 dependency barrier 分批准备；不得给尚未产生的 barrier 填造 SHA。W3 reviewed
merge 已真实形成 `B_C2_APP_CONTRACT = 86d1b8357f817882b017e5c4306ec855e0b288e6`
/ tree `b27f5f805c85e8ce76c30be254a004cb5f127b4e`；owner-ruling、02-02R 与 02-04R
已依次形成 `B_C2_W3R_RULING`、`B_C2_INPUT_BINDING_V2`、
`B_C2_SELECTED_TARGET_GATEWAY` 与最终 `B_C2_W4_READY = 5f2fa6d...` / tree
`174fbebc...`。W4 `02-06/08/09/13` 四份Plan已从该同一product base重冻结并经
planning provenance merge；02-06/13/08 与 R1/R2/R3 已 reviewed implementation merge，
并形成 `B_C2_02_09_READY = cdf8c194...`。第一次 refrozen 02-09 head因Gate P2-A3的
两个HIGH未发布；必须等待R4 exact Plan、reviewed merge与第二次refreeze，旧Plan/head
均不再是当前可执行输入。

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
- [x] 原 19 slots / 13 Waves / max concurrency 2 已由 Gate P2-A 批准；Gate P2-A1
      历史增加三个 W3R correction slots，形成 22 / 14；本轮用户“有问题先修复”
      指令经 Gate P2-A2 增加 `02-09R1/R2/R3` 与 `W4R`，又经 Gate P2-A3增加
      `02-09R4 / W4R2`；Gate P2-A4 又增加 `02-07R` 但不新增 wave
      label；Gate P2-A5 又增加 `02-10R` 但不新增 wave label；Gate P2-A6 又增加
      `02-11R` 但不新增 wave label；Gate P2-A7再增加`02-15R0/R1/R2`，Gate P2-A8
      增加`02-15R1A`，Gate P2-A9增加`02-15R1B`，均不新增wave label；当前冻结为34 slots / 16 wave labels，
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
