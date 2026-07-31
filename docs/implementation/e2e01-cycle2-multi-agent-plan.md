# E2E-01 Cycle 2｜Codex 多 Agent 实施计划

更新日期：2026-07-31

状态：`NON_NORMATIVE / PLAN_APPROVED / 02-00_COMPLETE / GATE_P2_C_APPROVAL_PENDING / IMPLEMENTATION_NOT_AUTHORIZED`

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
> 用户 Gate P2-A 批准并经 planning PR 合并；Integrator 现按真实 dependency barrier
> 分批准备“一份 GSD Plan + 一个 exact Task Packet”。首份
> [`02-00`](../../.planning/phases/02-cycle-2-e2e-01/02-00-PLAN.md) 已获用户批准并
> 由 PR #204/#205 执行完成；当前只准备 [`02-01`](../../.planning/phases/02-cycle-2-e2e-01/02-01-PLAN.md)
> 与 [`02-03`](../../.planning/phases/02-cycle-2-e2e-01/02-03-PLAN.md) 的 exact
> proposal。`02-02` 必须等待真实 `B_C2_W1A`，不得预填 SHA。
>
> 在用户进一步批准当前可签发 Task Packet、对应 Wave、initial exact
> implementation base 与执行上限前，不创建 `integration/e2e01-cycle2`、任何
> 代码 feature branch / Worktree、migration、测试、Eval artifact 或功能代码。

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
- 五个新逻辑 record / projection、四个 v2 record cutover、owner-scoped reader、
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
| Future GSD Plans | `02-00 COMPLETE / 02-01+02-03 EXACT PROPOSAL / 02-02+02-04..18 NOT_CREATED` |
| Task Packets | `02-00 APPROVED+EXECUTED / 02-01+02-03 REVIEWED EXACT PROPOSAL / 02-02 BLOCKED UNTIL B_C2_W1A` |
| Proposed Plan / Packet slots / Waves | `19 / 13`（`02-00..18` / `W0..W12`） |
| Planning input SHA | `b96fe8adf8ce4bcadbdf2cf008e28be4ff9aa5a3` |
| `B_C2_PLAN_APPROVED` | `2879f5226a073051d1550fe079b4a427c1ec8cb1` / tree `d5ded99bb0439fb57bbb4d6057fbda7a12b21fdf` |
| `B_C2_OWNER_ALIGNED` | `4dc6dc95de81080fb3b651bc2f0026fb046fd9f8` / tree `521ac2c7611b20683089ab41a74d07c9a2bb8fc7` |
| Initial implementation base | `NOT_FROZEN`；Gate P2-C 后必须与 `B_C2_OWNER_ALIGNED` exact equal |
| Integration branch | `PROPOSED integration/e2e01-cycle2 / NOT_CREATED` |
| GSD config branch mapping | `integration/e2e01-cycle2 / RESERVED_MAPPING_ONLY` |
| `02-00` execution | `COMPLETE / PR #204+#205 / ZERO FUNCTION CODE` |
| Integration / code feature branches / Worktrees | `NOT_CREATED / PROHIBITED` |
| Writer assignments | role proposed; person / Agent `NOT_FROZEN` |
| Execution concurrency | approved ceiling `2` writers；当前 dispatch `0` |

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
`integration/e2e01-thin` 记录保持历史原文；Phase 2 mapping 不声明 branch
protection 已配置，因为 `integration/e2e01-cycle2` 当前尚不存在。

## 3. Approved base decision and remaining pre-activation correction

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

该 base chain 已获 Gate P2-A 批准；`02-00` 已执行并形成 exact
`B_C2_OWNER_ALIGNED = 4dc6dc95de81080fb3b651bc2f0026fb046fd9f8`
/ tree `521ac2c7611b20683089ab41a74d07c9a2bb8fc7`。`B_C2_START` 尚未形成；
`.planning/config.json` 的 Phase 2 branch mapping 仍只是 reserved governance
mapping，不证明分支存在，也不授权 branch activation 或代码执行。

### `C2-BLOCK-02` — Eval model script path

Cycle 2 Spec 曾指定 `evals/model-scripts/`，而仓库和 loader 使用
`evals/model_scripts/`。用户已批准 `02-00` 独立 zero-code contract correction，
并由 PR #204/#205 完成 underscore 路径对齐。该修正满足：

- 只改真正受影响的 active owner / consumer；
- 通过 cross-file impact scan 和独立 exact-file review；
- 不创建 Eval artifact、loader、测试或 lifecycle 结果；
- 合并后的 exact SHA 成为后续 Eval Packet dependency。

`02-00` planning provenance merge successor 为
`74db04a938f725f1e4bbf113b23de613dbbb433e`；PR #205 merge successor 即
`B_C2_OWNER_ALIGNED`。后续 Eval implementation allowlist 只消费已对齐的
`evals/model_scripts/`，不得恢复旧拼写。

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

以下 19 个 slot 是本 master Plan 的冻结提案：`02-00` 是零功能代码的 scoped-owner
correction；`02-01..18` 覆盖实现、lifecycle 与 post-activation verification。
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
- **Depends on:** exact `B_C2_START`；可与 `02-03` 首批并行。`02-03` 先合并后，
  本 Packet 必须在 latest integration overlay 复验再合并并形成 `B_C2_W1A`。
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
- **Depends on:** reviewed `B_C2_W1A`，因为 `SearchOrdersObservation` 与
  `ShipmentObservation.normalized_value` 必须直接消费 `02-01` 的 typed business
  projections；不得复制类型、弱化为 `dict/Any`、使用 synthetic overlay 或扩大
  allowlist。真实 barrier 形成前，本 Plan / Packet 保持 `NOT_CREATED`。
- **Acceptance:** CandidateSet 不复制业务事实；wrong-owner、dangling、duplicate、
  stale、superseded、wrong-version 和 out-of-range 均 fail closed。

### `02-03` — Run / Trace v2 contract

- **Owner:** Runtime Engineer / Core Runtime consumer.
- **Goal:** 冻结 `SUPERSEDED`、新增 stop reasons 与 Run / Trace terminal closed
  matrix；shared `TraceEvent` structure 不变。Run/Link persistence、conditional
  no-result writer 与 finalizer 留给后续 Packet。
- **Proposed files:**
  - `src/mini_agent/core/trace.py`
  - `tests/component/core/test_cycle2_trace_contract.py`（new）
- **Depends on:** exact `B_C2_START`；可与 `02-01` 首批并行，并按固定顺序先
  reviewed merge 为 `B_C2_TRACE`。
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

### `02-06` — Exact persistence codec

- **Owner:** Runtime Engineer / Application persistence.
- **Goal:** 新 record codes、v2 active versions、strict exact codec / version catalog、
  cutover validation 和 rollback categories。
- **Proposed files:**
  - `src/mini_agent/application/persistence.py`
  - `tests/component/application/test_persistence_contract.py`
- **Depends on:** reviewed `02-05` barrier。
- **Acceptance:** unknown version、mixed active version、logical child mismatch、
  conversion ambiguity 全部 fail closed；无 read-time fallback。

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
- **Depends on:** reviewed `02-01/02/04/05` barriers。
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
- **Depends on:** reviewed `02-02/03/04/05` barriers。
- **Acceptance:** attempt 1 失败证据不被最终 success 覆盖；deterministic failure
  不重试；state invalidation 形成 OA-10 no-result closure。

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
  - `$C2_MODEL_SCRIPTS_PATH`
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
| `W1` | `02-01, 02-02, 02-03` | max 2 | 先并行 `02-01 + 02-03`；`02-03` 先 merge → `B_C2_TRACE`；`02-01` overlay/merge → `B_C2_W1A`；再签发并执行 exact `02-02` → `B_C2_CORE_123` |
| `W2` | `02-04` | 1 | `B_C2_TOOL` |
| `W3` | `02-05` | 1 | `B_C2_APP_CONTRACT` |
| `W4` | `02-06, 02-08, 02-09, 02-13` | max 2 | each exact review + serial merge；形成 `B_C2_LEAVES` |
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
W1a `02-01` business contracts || `02-03` Run/Trace contract
  ↓ 02-03 reviewed merge = B_C2_TRACE
  ↓ 02-01 latest-overlay reviewed merge = B_C2_W1A
W1b issue exact `02-02` from B_C2_W1A
  ↓ reviewed merge = B_C2_CORE_123
  ↓
W2 Tool / Gateway
  ↓
W3 Application contracts
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

同一 Wave 只表示受同一个 exit barrier 管理，不表示同时启动全部 slot。W1 的
`02-02` 具有内部真实依赖，不能与 `02-01` 同 base 启动。Integrator 每次最多
dispatch 两个 writer，合并始终逐个进行。任一 proposed allowlist 出现交集或 typed
dependency 尚未形成时，该 slot 在 Task Packet freeze 前自动变为 `BLOCKED`。

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

## 9. Verification strategy

### 9.1 Per-slot minimum

- TDD 可适用的 DTO、state、mapper、algorithm、API 全部使用 RED → GREEN →
  focused hardening。
- `git diff --check`。
- exact `base_sha`、first parent、zero merge、commit list、allowlist containment。
- owned focused tests与直接 neighbor tests。
- independent exact-head code review。
- latest integration overlay 保持 owned blobs / patch语义。

### 9.2 Migration / persistence

- empty database → head。
- Phase 1 migration head → Phase 2 head。
- v1 rows 全量预验证后一次 cutover。
- unknown / contradictory / mixed version fail closed且零部分转换。
- CandidateSet / selection / attempt / no-result原子性和 crash-point tests。
- downgrade 在 v2-only evidence 前有界；其后明确 fail closed。

### 9.3 Eval / E2E

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

### 9.4 Canonical repository gate

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

`B_C2_VERTICAL` 只表示实现集成完成，不推进 Case 或 Phase。之后依序：

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
| read-only phase enables Action / side effect | CRITICAL | exact Registry 仅三个 `READ` tools；无 confirmation、ActionPolicy、idempotency claim/key、Action Ledger write 或 `RESULT_UNKNOWN` side-effect recovery | `04,11,13,15,18` |

任何 CRITICAL / HIGH threat 缺少可复现 mitigation evidence 都阻断 slot merge、Wave
barrier 与 release。

</threat_model>

## 11. Risk controls learned from Phase 1

1. **先完整暴露 slots，不用“大包”隐藏复杂度。** 当前 19 slots 是明确提案；增减
   任一 slot 都需要用户重新批准 master Plan。
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

### Gate P2-B — Exact Plan / Task Packet set

状态：`IN_PROGRESS / 02-00 COMPLETE / 02-01+02-03 EXACT / 02-02 WAITING`。
P2-A 通过后按真实 dependency barrier 分批准备；不得给尚未产生的 barrier 填造
SHA。`02-00` 已完成并形成 exact `B_C2_OWNER_ALIGNED`。当前只有 `02-01` 与
`02-03` 能从该唯一 `B_C2_START` 候选精确签发。

`02-02` 不在本轮 approval scope：它依赖 `02-01` 提供的 typed business
projections，只有 reviewed `B_C2_W1A` 真实形成后才能生成 exact Plan / Packet 并
返回用户批准。该顺序保留 19 slots、W0–W12 和 max concurrency 2，不新增 Wave。

用户需逐项或整组批准：

- 每个 GSD Plan / Task Packet的一对一映射；
- exact `B_C2_OWNER_ALIGNED` SHA / tree，并批准它作为唯一允许的
  `B_C2_START / initial implementation base` 值；branch / Worktree identity；
- allowlist / forbidden files；
- verification、security、Eval、rollback；
- Wave dispatch 上限。

### Gate P2-C — Implementation activation

仅当以下全部成立：

```text
master Plan approved + merged
AND C2-BLOCK-01 approved
AND 02-00 reviewed + merged
AND B_C2_OWNER_ALIGNED exact SHA/tree frozen
AND 02-01 and 02-03 Plan/Task Packet pairs exact-head reviewed
AND user approves branch activation + Wave + concurrency
```

以上是 Gate P2-C 的输入条件。Gate P2-C 只按以下顺序激活：

1. 从 exact `B_C2_OWNER_ALIGNED` 创建 `integration/e2e01-cycle2`；
2. 立即证明新 branch 的 exact head / tree 与 `B_C2_OWNER_ALIGNED` 相同，并冻结为
   `B_C2_START = initial implementation base`；
3. equality preflight 通过后，只允许为已批准的 `02-01` / `02-03` 创建代码
   Worktree / feature branch并写功能代码，最多两个 writer；
4. `02-03` reviewed merge 后冻结 `B_C2_TRACE`，`02-01` latest-overlay reviewed
   merge 后冻结 `B_C2_W1A`；
5. `B_C2_W1A` 形成后另行准备、review并请求用户批准 exact `02-02`，不得把本次
   Gate P2-C 批准解释为预先批准未来 `02-02`。

Gate P2-C 前不得创建 Phase 2 integration / feature branch；第 2 步失败时立即把
错误 branch 标记为不可用并停止，由 Integrator 提交精确 remediation / 用户裁决，
不得继续第 3 步。

## 14. Plan acceptance criteria

本 Plan 只有在以下条件全部满足后才能从 `PLAN_REVIEW_DRAFT` 变为
`PLAN_APPROVED`：

- [x] dependency / ownership / risk map 已独立复核。
- [x] `C2-BLOCK-01/02` 有明确用户裁决或被列为 Task Packet 前的强制 owner
      remediation，且不会由 Executor猜测。
- [x] 19 slots / 13 Waves / max concurrency 2 获用户批准。
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
