# E2E-01 Cycle 2｜Codex 多 Agent 实施计划

更新日期：2026-08-02

状态：`NON_NORMATIVE / PLAN_APPROVED / W1-W11_COMPLETE / W12R13_CORRECTION_ACTIVE`

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
> PR #278/#279 已 reviewed 完成 R1B 并冻结
> `B_C2_W9_TYPED_READ_EXECUTION = 1fba65168fb487d3c4a8664213831a9c1c5dc815`；
> PR #280 又从其真实 successor 第二次重冻结 R1。R1 writer 在构造完整
> UNIQUE search → `get_order` 路径时确认两个跨 owner BLOCK：现有
> `ApplyOrderSearchOutcomeV2Command` 只保存 Search Observation / CandidateSet 与
> owner-scoped target mapping，没有形成可持久化的独立 verified-target capability；
> Core 也没有从 UNIQUE current closure 路由后续 `get_order` 的 reducer。把私有
> owner-scoped order ref、产品描述 binding 或模型参数直接当成 target 会绕过
> Intent / Memory / Gateway 的 binding 与 authority 规则。依据同一用户授权，
> Gate P2-A10 在 W9 原 wave 内增加串行 `02-15R1C` scoped Spec correction 与
> `02-15R1D` Core unique-target correction，将 slot 数从 34 调整为 36、不新增
> wave label。R1 当前两文件 checkpoint 继续 unpublished；R1C/R1D reviewed 后
> R1 必须从真实 successor 第三次重冻结。另两个同 owner 缺口——normal current
> closure 缺少 verified target / target Observation facts，以及 typed
> `ToolResult.payload` 到既有 private Result 的 strict mapping——仍在 R1 原六文件
> allowlist 内关闭，不新增 Packet。
>
> PR #287-#296随后reviewed完成R1E/R1F/R1G/R1H及R1第六次重冻结，分别闭合
> UNIQUE Gateway origin、Shipment target binding/Gateway/route与exact Observation
> version。R1第六次writer接线又确认Core Gateway把合法
> `RequestUnit.observation_refs`历史集合错误要求为exact等于唯一current target
> Observation集合，使`Search Observation → Order Observation`历史存在时
> `get_shipment`必然拒绝。Application不得删除历史或绕过Gateway。依据同一用户授权，
> Gate P2-A11在W9原wave内增加串行`02-15R1I`，总slot数从40调整为41、不新增wave
> label；R1 WIP继续unpublished，R1I reviewed后从真实successor第七次重冻结。
>
> W9–W11随后已全部reviewed串行完成：`02-15R2/02-15`形成真实pre-activation
> execution seam，`02-16` Coverage owner作出`APPROVED_FOR_EXECUTABLE`裁决，
> `02-17`把27个physical artifact与manifest/loader原子序列化为`EXECUTABLE`。
> W12原`02-18`三测试文件preflight证明它无法承接完整authenticated setup、Provider
> script、fault/recovery、actual mapper与root/supporting evidence。`02-18R13`
> scoped Spec correction已经独立review并由PR #347合并，形成
> `B_C2_W12_EXECUTION_CONTRACT_RULING =
> a1543d41da9f182d99f3be700911ae1703257581` / tree
> `c0278504a9f9e34bf1e8435a04802182f1bc50bd`。其cross-file scan同时确认：artifact
> bytes为`EXECUTABLE`，但Coverage Matrix、Eval Strategy、Cycle 2 Spec、`AGENTS.md`
> 与Intent current-state prose
> 仍保留旧`CONTRACT_DEFINED`表述；13个trajectory-only artifact仍错误携带HTTP
> `200`。依据用户“按照建议执行直到W12完成”的授权，本Plan增加一个严格串行的
> `W12R13` correction wave：先修master Plan，再按canonical owner逐文件关闭状态
> 差异，随后按Core/Application/Infrastructure/Eval/Composition边界实现，最后才从
> 真实successor重冻结原`02-18`。初次总slot数由41调整为51，wave label由16调整为17。
> `02-18R14`随后经PR #349 reviewed合并；R14A Coverage审查又发现Eval Strategy仍
> 声称`LIFECYCLE_HOLD / CONTRACT_DEFINED`且owner alignment/Activation缺失，同时
> scoped Spec current-state摘要也会在Coverage对齐后失真。Gate P2-A13因此新增
> `02-18R14R1/R14D/R14E`三个slot，把总数纠正为54，并要求在R14R1 merge后原位
> 重冻结R14A exact Task Packet。PR #351保持draft，不能用旧34f016 barrier执行。
> 不扩大并发上限，不推进lifecycle，也不把artifact值写成已有Result。
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
| Scoped contract | `CONTRACT_ACTIVE / W12_EXECUTION_CORRECTION_REVIEWED` |
| Case lifecycle | `27 ARTIFACTS_SERIALIZED_EXECUTABLE / OWNER_CURRENT_STATE_ALIGNMENT_PENDING / 0 PHASE_2_RESULTS` |
| Master Plan | `PLAN_APPROVED / R14 PR #349 MERGED / 02-18R14R1 ROUTE CORRECTION ACTIVE` |
| Future GSD Plans | `W1-W11 + 02-18R13/R14 COMPLETE / 02-18R14R1 ACTIVE / R14A/D/E/B/C + R15-R19 + REFROZEN 02-18 PENDING` |
| Task Packets | `42/54 COMPLETE / 02-18R14R1 ACTIVE / 02-18 REFROZEN PENDING` |
| Proposed Plan / Packet slots / Waves | `54 / 17`（历史41 + `02-18R13/R14/R14R1/R14A/R14D/R14E/R14B/R14C/R15/R16/R17/R18/R19` / 历史16 + `W12R13`） |
| Planning input SHA | `b96fe8adf8ce4bcadbdf2cf008e28be4ff9aa5a3` |
| `B_C2_PLAN_APPROVED` | `2879f5226a073051d1550fe079b4a427c1ec8cb1` / tree `d5ded99bb0439fb57bbb4d6057fbda7a12b21fdf` |
| Initial implementation base | `B_C2_START = 4dc6dc95de81080fb3b651bc2f0026fb046fd9f8` / tree `521ac2c7611b20683089ab41a74d07c9a2bb8fc7` |
| Integration branch | `integration/e2e01-cycle2 / ACTIVE / 9ae000a36ea54c013de9ebb84c204c290ed52645` / tree `c6df897bed07f257f5177d31bc7321d840bba566`（R14R1 planning-control barrier） |
| GSD config branch mapping | `integration/e2e01-cycle2 / ACTIVE` |
| `02-00` execution branch / Worktree | `COMPLETE / REVIEWED MERGE` |
| Integration / code feature branches / Worktrees | `W1..W11 + 02-18R13/R14 COMPLETE；R14A PR #351 DRAFT/PAUSED；02-18R14R1 master-Plan single writer ACTIVE` |
| Writer assignments | `Integrator 02-18R14R1 master-Plan single writer ACTIVE；implementation writer 0` |
| Execution concurrency | approved ceiling `2` writers；W12R13 effective ceiling `1`；当前 implementation writer `0` |

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

以下 54 个slot是当前冻结集合：历史41个slot保持编号与ownership；新增
`02-18R13/R14/R14R1/R14A/R14D/R14E/R14B/R14C/R15/R16/R17/R18/R19`十三个W12 correction slots，
原`02-18`保持final aggregate identity但必须从`02-18R19`真实reviewed successor
重新冻结。新增slots严格串行，不与历史slot并行回放。

历史集合中，原 `02-00..18` 保持编号与 ownership；
`02-02R/02-04R/02-05R` 是用户授权的 W4 前 correction set，
`02-09R1/02-09R2/02-09R3` 是 02-09 preflight 触发的 recovery owner correction
set，`02-09R4` 是 replacement exact-head review触发的 dispatch-grant correction，
`02-07R` 是 W6 preflight 触发的 Application Business Read Port owner correction，
`02-10R` 是后续 Adapter preflight 触发的 Infrastructure physical search-authority
correction，`02-11R` 是 02-11 实现验证触发的 immutable Task / RequestUnit
pre-image history correction；`02-15R0/R1/R2` 是W9 preflight触发的seed owner、
Application normal entry与Infrastructure normal evidence/dispatch corrections；
`02-15R1A`是R1写前preflight触发的Cycle2首轮RU Core owner correction；
`02-15R1B`是R1成功工具路径接线触发的Application executor result-envelope correction；
`02-15R1C`与`02-15R1D`是R1完整UNIQUE路径接线触发的scoped Spec verified-target
durability correction与Core unique-target routing correction；`02-15R1E/R1F/R1G/R1H`
依次闭合UNIQUE Gateway origin及Shipment target binding/Gateway/route；`02-15R1I`
只修Gateway current-target Observation与合法RequestUnit Observation历史的集合关系。
`02-18R13`是W12 authenticated execution scoped Spec correction；`02-18R14`首次更新
本master Plan；`02-18R14R1`修复R14A审查发现的active-owner漏路由；R14A先原位
重冻结exact Task Packet，再由`02-18R14A/R14D/R14E/R14B/R14C`依次以Coverage、
Eval Strategy、Cycle 2 Spec、项目指令与Intent consumer单文件关闭current-state
prose差异；`02-18R15..R19`依次拥有Core、Application、
Infrastructure、Eval与Composition实现边界。Eval slot同时原子同步13个T2的nullable
transport applicability；final `02-18`只拥有aggregate tests、Results与full gate。
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
- **Depends on:** reviewed `02-15R1I`真实successor、R1A-R1H/R0 contracts与
  `B_C2_RUNTIME`。
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

### `02-15R1C` — UNIQUE verified-target durability contract

- **Owner:** Cycle 2 scoped Spec owner / documentation single writer.
- **Goal:** 补齐现有“UNIQUE 自动绑定并继续”目标缺少的 durable verified-target
  capability record、query-binding/Observation/CandidateSet closure 与原子提交语义；
  不修改源码、测试、migration、artifact或Case lifecycle。
- **Proposed files:**
  - `docs/implementation/e2e01-cycle2-implementation-spec.md`
- **Depends on:** reviewed `B_C2_W9_TYPED_READ_EXECUTION`、R1 second-refrozen
  implementation BLOCK与用户2026-08-02“有问题按照你的建议走”的授权。
- **Acceptance:** UNIQUE target capability使用fresh Runtime UUID并独立于
  owner-scoped business target ref；只绑定exact current product-description binding、
  Search Observation唯一candidate与CandidateSet result version；同一原子提交写入且
  可由owner-scoped exact reader恢复；不得修改CandidateSet业务事实隔离、不得把
  private target/UUID投影给模型、Renderer、HTTP或ordinary Trace；MULTIPLE/ordinal
  selection语义保持不变。

### `02-15R1D` — UNIQUE auto-target Core contract

- **Owner:** Core / Task State + Request Processing single writer.
- **Goal:** 实现R1C定义的strict UNIQUE target record/factory与Gateway candidate route，
  只从closed Search Observation/CandidateSet/current query binding生成并验证capability；
  不写Application、Infrastructure、HTTP、Eval或持久化。
- **Proposed files:**
  - `src/mini_agent/core/task_state.py`
  - `src/mini_agent/core/request_processing.py`
  - `tests/component/core/test_candidate_selection_contract.py`
  - `tests/component/core/test_request_processing.py`
- **Depends on:** reviewed `02-15R1C`真实successor与既有R1A Core contract。
- **Acceptance:** caller-allocated fresh UUID只在exact UNIQUE closure中形成；record
  exact-copy owner/Conversation/Task/RequestUnit/query binding/Observation/CandidateSet/
  source version/order id与owner-scoped target ref；route输出`get_order` candidate并使
  `argument_binding_refs`仍指current query InputBinding、`verified_target_ref`独立；
  wrong-owner、MULTIPLE、stale/superseded/version drift、mapping缺失/重复、target或
  argument替换全部fail closed；现有ordinal route与Phase 1 public shape不变。

### `02-15R1E` — UNIQUE auto-target Gateway closure

- **Owner:** Core / Control Gateway single writer。
- **Goal:** 让UNIQUE auto-target的current `product_description` binding与独立
  `verified_target_ref`通过同一target-aware Gateway closure；保留ordinal/direct
  order paths。
- **Files:**
  - `src/mini_agent/core/control_gateway.py`
  - `tests/component/core/test_control_gateway.py`
- **Depends on:** reviewed `B_C2_W9_UNIQUE_TARGET_CORE`。
- **Acceptance:** candidate validation与authorized-command reproving使用同一
  owner/version/Observation closure；任一替换fail closed。

### `02-15R1F` — Shipment verified-target origin-binding contract

- **Owner:** Cycle 2 scoped Spec owner / documentation single writer。
- **Goal:** 冻结`get_shipment`只复制current verified target的exact origin binding；
  direct/UNIQUE/ordinal分别使用`order_id/product_description/candidate_ordinal`，不得
  伪造order-id Claim。
- **Files:**
  - `docs/implementation/e2e01-cycle2-implementation-spec.md`
- **Depends on:** reviewed `B_C2_W9_UNIQUE_TARGET_GATE`。
- **Acceptance:** binding family互斥且`verified_target_ref`独立；不修改代码、artifact
  或Case lifecycle。

### `02-15R1G` — Shipment target-origin Gateway closure

- **Owner:** Core / Control Gateway single writer。
- **Goal:** 实现R1F三类target-origin binding矩阵，同时重验argument order、target、
  owner、Task/RequestUnit/version与source Observation。
- **Files:**
  - `src/mini_agent/core/control_gateway.py`
  - `tests/component/core/test_control_gateway.py`
- **Depends on:** reviewed `B_C2_W9_SHIPMENT_TARGET_BINDING_CONTRACT`。
- **Acceptance:** 每次只命中target自身唯一binding ref；wrong family/ref/version全部
  REJECT，既有tool paths不漂移。

### `02-15R1H` — Shipment verified-target Core route

- **Owner:** Core / Request Processing single writer。
- **Goal:** 从current verified target正式形成`get_shipment` candidate，并让
  `shipment_not_received` continuation复用同一origin-binding closure。
- **Files:**
  - `src/mini_agent/core/request_processing.py`
  - `tests/component/core/test_request_processing.py`
- **Depends on:** reviewed `B_C2_W9_SHIPMENT_TARGET_GATE`。
- **Acceptance:** Application不直接构造Gateway authority；direct/UNIQUE/ordinal三类
  origin exact-copy，new Claim不成为Shipment target authority。

### `02-15R1I` — Gateway current-target Observation history correction

- **Owner:** Core / Control Gateway single writer.
- **Goal:** 允许RequestUnit保留此前Search/Order Observation历史，同时Gateway仍只把
  唯一current target Observation的exact ref/version/owner/task/unit/state/bindings作为
  target authority。
- **Proposed files:**
  - `src/mini_agent/core/control_gateway.py`
  - `tests/component/core/test_control_gateway.py`
- **Depends on:** reviewed `B_C2_W9_R1_SIXTH_REFREEZE`与用户授权。
- **Acceptance:** current target Observation必须属于RequestUnit历史且与manifest exact
  相等；额外历史ref不授权target；缺失current ref、同ref不同version、target/owner/
  state/binding/supersession drift、重复ref均fail closed；Application/DB/HTTP/Eval不变。

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

### `02-18R13` — W12 authenticated execution scoped Spec correction

- **Owner:** Cycle 2 scoped Spec owner / documentation single writer。
- **Goal:** 冻结23 fixture、7 fault、0/1/2-control、actual mapper、root/supporting
  evidence与真实14 HTTP + 13 non-HTTP execution contract；不修改实现或Result。
- **Files:**
  - `docs/implementation/e2e01-cycle2-implementation-spec.md`
- **Depends on:** reviewed `B_C2_OA10_INFRASTRUCTURE_EVIDENCE`。
- **Acceptance:** PR #347 final exact-head review `PASS / 0 findings`并已合并为
  `B_C2_W12_EXECUTION_CONTRACT_RULING =
  a1543d41da9f182d99f3be700911ae1703257581`；只关闭scoped contract。

### `02-18R14` — W12 master execution Plan correction

- **Owner:** Tech Lead / master Plan single writer。
- **Goal:** 把W1–W11、R13 barrier、当时51 slots / 17 wave labels、三份current-state
  alignment与五个implementation owners写入本Plan；不修改canonical语义。
- **Files:**
  - `docs/implementation/e2e01-cycle2-multi-agent-plan.md`
- **Depends on:** reviewed / merged `02-18R13`与reviewed `02-18R14-PLAN.md`。
- **Acceptance:** exact one-file review `PASS`；R14A只能从本slot真实merge successor
  冻结，不能使用R13或planning-control SHA代替。

### `02-18R14R1` — W12 lifecycle consumer route correction

- **Owner:** Tech Lead / master Plan single writer。
- **Goal:** 关闭R14A independent review发现的Eval Strategy HIGH drift与scoped Spec
  stale consumer漏路由，新增Strategy/Spec owner slots并纠正总数与依赖；不修改
  canonical owner正文。
- **Files:**
  - `docs/implementation/e2e01-cycle2-multi-agent-plan.md`
- **Depends on:** reviewed / merged `02-18R14`与reviewed R14A planning-control
  barrier `b87218af408c4684b24f44fbaa5ee09238df0f8e`。
- **Acceptance:** 冻结`42/54 COMPLETE / R14R1 ACTIVE`、54 slots / 17 wave labels；
  R14A implementation继续保持draft，并在本slot真实merge后先原位重冻结同一
  `02-18R14A-PLAN.md`的base/tree/dependency/required blobs。

### `02-18R14A` — Coverage lifecycle current-state owner alignment

- **Owner:** Eval Coverage canonical owner / documentation single writer。
- **Goal:** 基于W10 ruling与W11 exact artifact/manifest/loader sync，裁决并记录四个
  logical family / 27 physical Case的current effective lifecycle；明确0 Phase 2
  Result且不推进`REGRESSION_GATE`。
- **Files:**
  - `docs/evaluation/p0-eval-coverage-matrix.md`
- **Depends on:** reviewed / merged `02-18R14R1`；W10/W11证据与current artifact bytes；
  merged `02-18R14A-PLAN.md`必须先从R14R1真实successor原位重冻结，旧34f016
  base/dependency不可执行。
- **Acceptance:** 删除“sync仍未发生”的current-state误述，历史ruling保留；不修改
  Case bytes、grader、源码、测试、Result或其他owner语义。

### `02-18R14D` — Eval Strategy lifecycle current-state alignment

- **Owner:** Agent Evaluation Strategy canonical owner / documentation single writer。
- **Goal:** 把Cycle 2的`LIFECYCLE_HOLD / CONTRACT_DEFINED`与“owner alignment /
  Activation缺失”限定为历史状态，消费Coverage current effective lifecycle；不改
  通用lifecycle、Result、Gate或Dataset语义。
- **Files:**
  - `docs/evaluation/agent-evaluation-strategy.md`
- **Depends on:** reviewed / merged `02-18R14A`。
- **Acceptance:** exact one-file review `PASS`；当前四个logical/27 physical为
  `EXECUTABLE`，Phase 2 Result为0且无`REGRESSION_GATE`；不修改Coverage、Case、
  manifest、loader、grader、源码或测试。

### `02-18R14E` — Cycle 2 Spec lifecycle-status consumer alignment

- **Owner:** Cycle 2 scoped Spec owner / documentation single writer。
- **Goal:** 只把top banner、requirements/current state与9.1 status consumer prose从
  “Coverage/AGENTS冲突全部pending”对齐到reviewed Coverage/Strategy successor；
  不重开R13 authenticated execution contract。
- **Files:**
  - `docs/implementation/e2e01-cycle2-implementation-spec.md`
- **Depends on:** reviewed / merged `02-18R14D`。
- **Acceptance:** exact one-file review `PASS`；历史W11/R13冲突发现保留为历史，
  current state准确区分Coverage/Strategy已对齐与AGENTS/Intent仍待对齐；不修改
  exact fixture、fault、ordinal、transport、mapper、evidence或execution语义。

### `02-18R14B` — Project instruction current-state consumer alignment

- **Owner:** Project instruction hotspot / documentation single writer。
- **Goal:** 只把`AGENTS.md`的Cycle 2 current status与Coverage owner裁决、W11
  artifact值和0 Result事实对齐；保留所有安全、命令与多Agent治理规则。
- **Files:**
  - `AGENTS.md`
- **Depends on:** reviewed / merged `02-18R14E`。
- **Acceptance:** 不复制Coverage规则正文，不声称W12、full E2E、Qwen、UAT或
  production readiness完成；canonical suite数字只在实际新证据出现时更新。

### `02-18R14C` — Intent lifecycle-status consumer alignment

- **Owner:** Intent Design Reference / documentation single writer。
- **Goal:** 只修第10.7节已过期的Cycle 2 lifecycle consumer句；ordinal/input exact
  encoding继续委托active Cycle 2 Spec，不改通用Intent语义。
- **Files:**
  - `docs/architecture/intent-design-reference.md`
- **Depends on:** reviewed / merged `02-18R14B`。
- **Acceptance:** exact one-file review `PASS`；不复制Coverage lifecycle正文，不修改
  `TaskDeltaCandidate`、InputBinding authority或确定性validation contract。

### `02-18R15` — Core W12 Claim and selection decisions

- **Owner:** Core / Request Understanding + Task State + Control Gateway single writer。
- **Goal:** 实现`order_id` USER_CLAIM、`candidate_ordinal=1..99` Claim domain、
  CandidateSet `1..5` capability、六条accepted-Claim/rejected-selection typed decision
  与真实0/1/2-control provider边界需要的Core contract。
- **Proposed files:**
  - `src/mini_agent/core/request_understanding.py`
  - `src/mini_agent/core/task_state.py`
  - `src/mini_agent/core/control_gateway.py`
  - `tests/component/core/test_request_understanding_contract.py`
  - `tests/component/core/test_task_state_contract.py`
  - `tests/component/core/test_control_gateway.py`
- **Depends on:** reviewed / merged `02-18R14C`。
- **Acceptance:** ordinal 6可作为durable Claim但永不成为selection authority；六条
  rejection无Selection/target；`customer_id`与owner scope仍禁止来自模型/消息。

### `02-18R16` — Application W12 orchestration and actual outcome observation

- **Owner:** Application Runtime single writer。
- **Goal:** 串接独立RU/control calls、accepted Claim single-CAS、W12 fault/recovery
  orchestration与expectation-free imported/delta mapping observation Port。
- **Proposed files:**
  - `src/mini_agent/application/ports.py`
  - `src/mini_agent/application/records.py`
  - `src/mini_agent/application/run_result_mapper.py`
  - `src/mini_agent/application/agent_run_service.py`
  - `tests/component/application/test_agent_run_service.py`
- **Depends on:** reviewed / merged `02-18R15`。
- **Acceptance:** actual observation只在真实durable finalize后capture，production
  no-op；no-result recovery不伪造mapper evidence；0/1/2-control cursor严格耗尽。

### `02-18R17` — Infrastructure authenticated setup, fault and exact evidence

- **Owner:** Infrastructure / PostgreSQL + offline adapters single writer。
- **Goal:** 实现W12-only typed setup aggregate、pre-fold/fold/post-fold/atomic-write、
  23 fixture与7 fault、detached controller rollback、recovery historical USER closure、
  actual Registry pair digest与root/supporting exact evidence。
- **Proposed files:**
  - `src/mini_agent/infrastructure/cycle2_fixture_seed.py`
  - `src/mini_agent/infrastructure/cycle2_runtime.py`
  - `src/mini_agent/infrastructure/persistence/postgres.py`
  - `tests/integration/test_cycle2_fixture_seed.py`
  - `tests/integration/test_cycle2_runtime_adapter.py`
  - `tests/integration/test_postgres_record_adapters.py`
  - `tests/integration/test_postgres_recovery.py`
- **Depends on:** reviewed / merged `02-18R16`。
- **Acceptance:** all-or-nothing setup、owner隔离、zero synthetic expectation、七类
  fault/crash exact、same-snapshot evidence；不新增migration或production setup入口。

### `02-18R18` — Eval actual-evidence and transport applicability sync

- **Owner:** Eval Engineer / artifact-loader-harness-grader single writer。
- **Goal:** 让Scripted Provider真实实现Cycle 2 Port，扩展root/supporting actual
  evidence，并把13个trajectory-only Case的expected/actual transport原子改为
  `null / NOT_APPLICABLE`；14个longitudinal继续读取真实HTTP `200`。
- **Proposed files:**
  - `evals/cases/e2e01-cycle2.v1.json`
  - `evals/manifests/e2e01-cycle2.v1.json`
  - `src/mini_agent/evaluation/artifacts.py`
  - `src/mini_agent/evaluation/scripted_provider.py`
  - `src/mini_agent/evaluation/harness.py`
  - `src/mini_agent/evaluation/graders.py`
  - `tests/component/evaluation/test_e2e01_artifact_consistency.py`
  - `tests/component/evaluation/test_e2e01_versioned_artifact_loader.py`
  - `tests/component/evaluation/test_e2e01_scripted_model_provider.py`
  - `tests/component/evaluation/test_e2e01_graders.py`
- **Depends on:** reviewed / merged `02-18R17`。
- **Acceptance:** Case/manifest/loader/grader同一Packet同步；T2不得合成200；
  root-only grader不消费supporting attempts；missing/extra/source-edge mismatch在Result
  前成为execution failure。

### `02-18R19` — Real Cycle 2 Composition SUT

- **Owner:** Composition Root hotspot single writer。
- **Goal:** 在现有`OfflineE2E01Composition`中装配authenticated setup、real HTTP与
  non-HTTP trajectory SUT、actual mapping capture与exact evidence adapter；删除W12
  对synthetic Cycle 2 SUT的依赖。
- **Proposed files:**
  - `src/mini_agent/bootstrap.py`
  - `tests/integration/test_offline_composition_root.py`
- **Depends on:** reviewed / merged `02-18R18`。
- **Acceptance:** 同一Composition使用真实RegistrySnapshot、Session、Runtime、Mock
  business adapters与PostgreSQL；只注册三个READ tools；不出现Action surface。

### `02-18` — Post-activation Harness / HTTP E2E Results

- **Owner:** Tech Lead / Integrator.
- **Goal:** 从`02-18R19`真实reviewed successor重冻结，只运行/完善aggregate Harness、
  Trajectory与HTTP E2E，产生lifecycle-valid structured Results并执行canonical full。
- **Proposed files:**
  - `tests/integration/evaluation/test_e2e01_offline_harness.py`
  - `tests/e2e/test_e2e01_http_eval.py`
  - `tests/baseline/test_qwen_baseline.py`
- **Depends on:** reviewed / merged `02-18R13/R14/R14R1/R14A/R14D/R14E/R14B/R14C/R15/R16/R17/R18/R19`
  barriers；final exact Plan / Task Packet须从R19 successor重冻结。
- **Acceptance:** Phase 1 16 variants和 Phase 2 14 longitudinal + 13 trajectory 全部
  lifecycle-valid，T2 transport为`NOT_APPLICABLE`且longitudinal捕获真实HTTP status；
  same-registry pair exact；ordinary Trace disclosure negative
  assertions通过；全链不得注册或触发 Action、confirmation、ActionPolicy、
  idempotency、Action Ledger 或 `RESULT_UNKNOWN` side-effect recovery；无
  credential 时Qwen honest skip；canonical full gate、Eval review、Security audit与
  controlled UAT按第10节继续执行，不因27 PASS自动推进`REGRESSION_GATE`。

## 6. Execution Waves

| Wave | Ready slots | Concurrency | Merge order / exit barrier |
|---|---|---:|---|
| `W0` | `02-00` | 1 | zero-code owner correction；形成 `B_C2_OWNER_ALIGNED`；不创建 integration branch 或 `B_C2_START` |
| `W1` | `02-01, 02-02, 02-03` | max 2 | serial review/merge；形成 `B_C2_CORE_123` |
| `W2` | `02-04` | 1 | `B_C2_TOOL` |
| `W3` | `02-05` | 1 | `B_C2_APP_CONTRACT` |
| `W3R` | `02-02R → 02-04R → 02-05R` | 1 | exact-type dependencies require reviewed serial successors；形成 `B_C2_W4_READY` |
| `W4` | `02-06, 02-13, 02-08；02-09 continues after W4R/W4R2` | max 2；02-09 continuation=1 | Batch A exact review + serial merge；R1-R4 owner corrections后在同一W4 label恢复02-09，形成`B_C2_LEAVES` |
| `W4R` | `02-09R1 → 02-09R2 → 02-09R3` | 1 | recovery owner corrections serial merge；历史形成 `B_C2_02_09_READY` |
| `W4R2` | `02-09R4` | 1 | dispatch-grant contract correction；形成新的 exact `B_C2_02_09_DISPATCH_READY` |
| `W5` | `02-10` | 1 | `B_C2_PHYSICAL` |
| `W6` | `02-07R → 02-10R → 02-07 → 02-11R → 02-11` | 1 | 前四项依次补全 Application Port、search authority、business adapters 与 immutable record history；blocked 02-11 只能从真实 R successor 重冻结回放；形成 `B_C2_INFRA` |
| `W7` | `02-12` | 1 | `B_C2_RUNTIME` |
| `W8` | `02-14` | 1 | `B_C2_EVAL_MACHINERY`；Case 仍为 `CONTRACT_DEFINED` |
| `W9` | `02-15R0 → 02-15R1A → 02-15R1B → 02-15R1C → 02-15R1D → 02-15R1E → 02-15R1F → 02-15R1G → 02-15R1H → 02-15R1I → 02-15R1 → 02-15R2 → 02-15` | 1 | seed、initial RU、typed execution、UNIQUE/Shipment target与Gateway corrections、Application normal entry及Infrastructure normal evidence/dispatch依次reviewed后重冻结Composition；形成`B_C2_EXECUTION_SEAM`；Case仍为`CONTRACT_DEFINED` |
| `W10` | `02-16` | 1 | independent owner ruling `G_C2_APPROVED_FOR_EXECUTABLE` |
| `W11` | `02-17` | 1 | atomic consumer sync；形成 `B_C2_EXECUTABLE` |
| `W12R13` | `02-18R13 → 02-18R14 → 02-18R14R1 → R14A Task Packet refreeze → 02-18R14A → 02-18R14D → 02-18R14E → 02-18R14B → 02-18R14C → 02-18R15 → 02-18R16 → 02-18R17 → 02-18R18 → 02-18R19` | 1 | contract → Plan → route correction/refreeze → Coverage → Strategy → Spec → project status → Intent consumer → Core → Application → Infrastructure → Eval → Composition严格串行；形成`B_C2_W12_REAL_SUT` |
| `W12` | refrozen `02-18` | 1 | only from reviewed `B_C2_W12_REAL_SUT`；形成 `B_C2_VERTICAL` |

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
W9 scoped Spec UNIQUE verified-target durability correction
  ↓
W9 Core UNIQUE auto-target routing correction
  ↓
W9 Gateway current-target Observation history correction
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
W12R13 scoped authenticated-execution contract correction
  ↓
W12R13 master Plan correction
  ↓
W12R13 master Plan route correction → R14A exact Task Packet refreeze
  ↓
W12R13 Coverage → Eval Strategy → Cycle 2 Spec → AGENTS → Intent current-state alignment
  ↓
W12R13 Core → Application → Infrastructure → Eval → Composition
  ↓
refrozen W12 Harness / HTTP E2E and lifecycle-valid Results
  ↓
Post-execution quality gates
```

同一 Wave 只表示依赖允许，不表示同时启动全部 slot。Integrator 每次最多 dispatch
两个 writer，合并始终逐个进行。任一 proposed allowlist 出现交集时，该 slot 在
Task Packet freeze 前自动变为 `BLOCKED`。`W12R13`因每个Packet消费前一真实
successor且包含五个status owner/consumers与Composition hotspot，effective concurrency
固定为1，不能使用全局ceiling 2并行。

## 7. Requirement and decision coverage

| Requirement | Slots |
|---|---|
| `R01` | `13,14,15R0,15R1,15R2,15,16,17,18` |
| `R02` | `01,07,08,12,14,15R1C,15R1D,15R1,15R2,15,18` |
| `R03` | `01,07,13,14,15R0,15R2,15,18` |
| `R04` | `01,12,14,15R1,15R2,15,18` |
| `R05` | `02,05,06,11,15R1C,15R1D,15R1,15R2` |
| `R06` | `02,08,11,14,15R1,15R2` |
| `R07` | `07,08,12,14,15R1C,15R1D,15R1,15R2` |
| `R08` | `01,04,07,08,14,15R1C,15R1D,15R1,15R2` |
| `R09` | `01,02,07,11,14,15R1C,15R1D,15R1,15R2` |
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
| `E2E01-02` | `01,07,08,12,13,14,15R0,15R1C,15R1D,15R1,15R2,15,16,17,18` |
| `E2E01-03` | `02,08,11,12,13,14,15R0,15R1,15R2,15,16,17,18` |
| `E2E01-05` | `04,07,08,12,13,14,15R0,15R1C,15R1D,15R1,15R2,15,16,17,18` |
| `E2E01-06` | `01,02,03,04,07,09,11,12,13,14,15R0,15R1,15R2,15,16,17,18` |

上表保留历史41-slot coverage。W12R13 execution overlay不替代历史实现证据，按下表
增加consumer / executable-evidence closure：

| W12 correction scope | Added slots |
|---|---|
| `R01/R17/R18` status、Eval与release discipline | `18R13,18R14,18R14R1,18R14A,18R14D,18R14E,18R14B,18R14C,18R18,18R19,18` |
| `R02..R08/R14/R16` Claim、candidate、state与disclosure | `18R13,18R15,18R16,18R17,18R18,18R19,18` |
| `R09..R13` Shipment、freshness、retry/recovery与actual evidence | `18R13,18R15,18R16,18R17,18R18,18R19,18` |
| `R15` dynamic three-READ-tool pair | `18R13,18R15,18R16,18R17,18R18,18R19,18` |
| all four logical Case / 27 physical Case | `18R13,18R14,18R14R1,18R14A,18R14D,18R14E,18R14B,18R14C,18R15,18R16,18R17,18R18,18R19,18` |

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

- 历史上，`02-13/14/15`完成前Case保持`CONTRACT_DEFINED`，`02-15`只建立direct
  non-Harness seam；`02-16`随后完成Coverage owner
  `APPROVED_FOR_EXECUTABLE`裁决，`02-17`已经原子同步27个artifact、manifest与loader。
- 当前27个artifact均序列化为`EXECUTABLE`，但Coverage Matrix、Eval Strategy、Cycle 2
  Spec、`AGENTS.md`与Intent current-state prose尚未全部对齐，13个T2 transport
  encoding仍为HTTP `200`，Phase 2 lifecycle-valid Result仍为0。
  `02-18R14A/D/E/B/C`与`02-18R18`必须分别关闭这些差异；
  final dispatch在此之前禁止。
- refrozen `02-18`只有在`02-18R19`真实reviewed successor上才能运行Phase 2
  Harness / SUT并产生Result；R13-R19的Component/direct tests都不能抵扣该门禁。
- Phase 1 16 authenticated variants继续通过。
- Phase 2 14 longitudinal variants全部产生 lifecycle-valid Result。
- 13 mandatory non-HTTP Trajectory全部单独产生 lifecycle-valid Result；actual与
  expected transport均为`null / NOT_APPLICABLE`，不得合成HTTP `200`。
- Component、Trajectory、HTTP E2E均非空。
- `0 FAIL / 0 Critical failure / 0 execution failure`。
- exact artifact digest、predicate arity / symbol、pair identity、same registry /
  toolset / provider mapping。
- 14 longitudinal使用真实HTTP SUT并捕获actual status；13 trajectory使用真实
  Application/Infrastructure seam；二者都消费owner-scoped exact reader的
  root/supporting closure与actual mapper observation，禁止Synthetic SUT。

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
| model replaces order/package/candidate refs | CRITICAL | exact binding、verified target、owner-scoped reader；no model `package_id` | `02,04,08,11,14,15R1C,15R1D,15R1` |
| CandidateSet replay / version tamper | HIGH | content hash、15m TTL、current uniqueness、Task CAS、atomic selection | `02,05,06,11,15R1C,15R1D,15R1` |
| stale Shipment used in result | HIGH | 5m TTL、birth-stale rejection、forced refresh、no fallback | `01,02,09,12,14` |
| foreign/private/source token / Trace disclosure | CRITICAL | visible/private DTO split；ordinary Trace exact whitelist，禁止 raw customer/session scope、业务 payload、candidate summary、source token、prompt、stack / raw exception 与不必要 PII | `03,14,15,18` |
| unbounded retry / loop | HIGH | 500ms、max 2 attempts、run budget、no parallel ToolCall | `04,09,11,14` |
| mixed active v1/v2 | CRITICAL | full prevalidation、atomic cutover、strict readers/writers/recovery | `03,05,06,10,11` |
| obsolete Run overwrites new state / sends result | CRITICAL | conditional CAS、`SUPERSEDED`、null link result、no outbound/task write | `03,05,09,11,12,14` |
| model / Eval fabricates business evidence | CRITICAL | deterministic projection/mapper、authenticated artifacts、typed seed、real HTTP/non-HTTP SUT、actual mapper/root-supporting evidence | `12,13,14,15R0,15R2,15,18R13,18R16,18R17,18R18,18R19,18` |
| lifecycle prose / artifact值漂移或artifact自激活 | CRITICAL | Coverage owner先裁决current state；Eval Strategy、Cycle 2 Spec、AGENTS与Intent按各自owner/consumer边界串行消费；artifact/manifest/loader/grader原子；final Result gate独立 | `16,17,18R13,18R14R1,18R14A,18R14D,18R14E,18R14B,18R14C,18R18,18` |
| non-HTTP trajectory合成HTTP `200` | HIGH | T2 expected/actual transport同时为nullable `NOT_APPLICABLE`；只允许14 longitudinal捕获真实HTTP status | `18R13,18R18,18R19,18` |
| read-only phase enables Action / side effect | CRITICAL | exact Registry 仅三个 `READ` tools；无 confirmation、ActionPolicy、idempotency claim/key、Action Ledger write 或 `RESULT_UNKNOWN` side-effect recovery | `04,09R1,09R2,09R3,09R4,11,13,15R1,15R2,15,18R13,18R15,18R16,18R17,18R18,18R19,18` |
| fixture ref / static digest被误当成可信seed | CRITICAL | active Spec closed payload；typed all-or-nothing setup；post-fold canonical projection与actual Registry重算digest；禁止script/expectation/grader反推 | `15R0,15R2,15,18R13,18R17,18R18,18R19,18` |
| bootstrap直写DB或复制Application Runtime | CRITICAL | normal use-case/Port先由Application owner闭合，Infrastructure实现后Composition只装配 | `15R1,15R2,15,18R16,18R17,18R19` |
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
   Gate P2-A8增加`02-15R1A`，Gate P2-A9再增加`02-15R1B`，Gate P2-A10再增加
   `02-15R1C/R1D`；随后R1E-R1H及Gate P2-A11增加`02-15R1I`，均不新增
   wave label。W12 preflight与reviewed Spec correction再由Gate P2-A12增加
   `02-18R13/R14/R14A/R14B/R14C/R15/R16/R17/R18/R19`十个slots与`W12R13`
   一个wave label。R14A review发现的Strategy HIGH与Spec stale consumer再由Gate
   P2-A13增加`02-18R14R1/R14D/R14E`三个slots，不新增wave label。当前冻结集合为
   54 slots / 17 wave labels / global max 2 writers，
   但W12R13 effective max固定为1。
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

### Gate P2-A12 — W12 authenticated execution remediation

状态：`HISTORICAL APPROVAL / SUPERSEDED BY P2-A13 ROUTE CORRECTION`。W12 mechanical
preflight证明原`02-18`三测试文件不能解析25/27 setup组合，Scripted Provider缺少
Cycle 2 Port，六类fault/crash未实现，synthetic SUT与root-only evidence无法形成
真实Result。用户已授权按建议持续修正至W12完成；`02-18R13`经四轮local exact review
与PR #347 remote exact-head `PASS / 0 findings`后合并为
`a1543d41da9f182d99f3be700911ae1703257581`。`02-18R14` exact Plan又经独立review
`PASS`并由PR #348合并planning-control barrier
`7a73eb1042c18e38401f34d05338964f25ae4364`。

本Gate只批准十个新增slots与一个`W12R13` label，串行顺序固定为：

```text
18R13 → 18R14 → 18R14A → 18R14B → 18R14C
→ 18R15 → 18R16 → 18R17 → 18R18 → 18R19 → refrozen 18
```

它不授权跨owner写入、并行W12 writer、synthetic evidence、Action surface、提前
Result、`REGRESSION_GATE`或release；任一新cross-owner gap继续新增exact Packet，
不得扩大现有allowlist。

### Gate P2-A13 — W12 lifecycle owner/consumer route correction

状态：`USER_AUTHORIZED / R14 MERGED / R14R1 ACTIVE / R14A PR #351 DRAFT_PAUSED`。
`02-18R14`已由PR #349 reviewed合并为
`34f01611a2edb554d05cdf8400c34f16b1bb8f4c`；R14A planning control又由PR #350
合并为`b87218af408c4684b24f44fbaa5ee09238df0f8e`。Coverage implementation的
independent review确认内容本身准确，但以HIGH阻断：active Eval Strategy仍把Cycle 2
写为`LIFECYCLE_HOLD / CONTRACT_DEFINED`并声称owner alignment/Activation缺失；
cross-file scan同时确认Cycle 2 Spec current-state consumer在Coverage合并后也会失真。
PR #351因此保持draft。

本Gate增加`02-18R14R1/R14D/R14E`三个slots而不增加wave label；R14R1 planning
control已经independent exact-head `PASS`并由PR #352合并为
`9ae000a36ea54c013de9ebb84c204c290ed52645` / tree
`c6df897bed07f257f5177d31bc7321d840bba566`。纠正后冻结集合为54 slots / 17 wave
labels，R14R1开始时精确为42/54 complete，串行顺序固定为：

```text
18R13 → 18R14 → 18R14R1 → in-place R14A Task Packet refreeze
→ 18R14A → 18R14D → 18R14E → 18R14B → 18R14C
→ 18R15 → 18R16 → 18R17 → 18R18 → 18R19 → refrozen 18
```

原位R14A refreeze只更新同一`.planning/.../02-18R14A-PLAN.md`，使其exact base/tree/
dependency/required blobs消费R14R1真实merge successor；它不新增product slot或wave。
各active owner继续单文件串行，不能把Strategy、Spec、AGENTS或Intent并入Coverage PR。

### Gate P2-B — Exact Plan / Task Packet set

状态：`IN_PROGRESS / W1-W11 + 02-18R13/R14 COMPLETE / 42 OF 54 COMPLETE / 02-18R14R1 ACTIVE`。
P2-A 通过后始终按真实 dependency barrier 分批准备；不得给尚未产生的 barrier
填造 SHA。当前真实 integration planning-control successor为
`9ae000a36ea54c013de9ebb84c204c290ed52645` / tree
`c6df897bed07f257f5177d31bc7321d840bba566`；`02-18R14R1` implementation Packet
仍使用其exact Plan冻结的product base
`b87218af408c4684b24f44fbaa5ee09238df0f8e`，PR只允许修改master Plan。R14A必须
在R14R1真实merge后原位重冻结exact Task Packet，不能继续使用旧34f016 base或仅凭
master prose执行。

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
      增加`02-15R1A`，Gate P2-A9增加`02-15R1B`，Gate P2-A10增加
      `02-15R1C/R1D`，后续R1E-R1H与Gate P2-A11增加`02-15R1I`，均不新增wave
      label；Gate P2-A12再增加十个`02-18R13..R19` correction slots与一个
      `W12R13` label；Gate P2-A13再增加`02-18R14R1/R14D/R14E`三个slots且不新增
      label。当前冻结为54 slots / 17 wave labels，global并发上限仍为2，
      W12R13 effective并发固定为1。
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
