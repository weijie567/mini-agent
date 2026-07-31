# E2E-01 Cycle 2｜Dependency / Ownership / Risk Map

更新日期：2026-07-31

状态：`NON_NORMATIVE / RESEARCH_MAP / P2_A_AND_02_00_DECISIONS_APPLIED / GATE_P2_C_PENDING`

研究基线：`main@b96fe8adf8ce4bcadbdf2cf008e28be4ff9aa5a3`

> 本文把 active canonical owner、Phase 1 当前实现和 Cycle 2 scoped contract
> 转成规划输入。它不拥有产品、架构、Tool、Memory、Eval 或 Case lifecycle 语义，
> 不授权 Task Packet、implementation branch、代码 Worktree、migration、测试、
> Eval artifact 或功能代码。
>
> `b96fe8a...` 只是本次 planning input，不是已经冻结的 Phase 2 implementation
> base。任何后续实现基线都必须在 Plan 合并、Task Packet 准备和用户批准时重新
> 精确冻结。

后续 Gate P2-A 证据：planning PR
[#203](https://github.com/weijie567/mini-agent/pull/203) 已合并，
`B_C2_PLAN_APPROVED = 2879f5226a073051d1550fe079b4a427c1ec8cb1`
/ tree `d5ded99bb0439fb57bbb4d6057fbda7a12b21fdf`。后续 `02-00` 已由用户批准，
planning PR #204 与 zero-code owner correction PR #205 已合并；
`B_C2_OWNER_ALIGNED = 4dc6dc95de81080fb3b651bc2f0026fb046fd9f8`
/ tree `521ac2c7611b20683089ab41a74d07c9a2bb8fc7`。这仍不代表
`B_C2_START`、integration branch 或功能实现已完成。

## 1. 证据口径

本次结论分为：

- `CONFIRMED`：可由当前 active 文档、源码、Git 或机械查询复现。
- `INFERRED`：由已确认事实推导的规划建议，仍需后续 Plan / Task Packet 冻结。
- `OPEN`：当前 owner 或仓库没有唯一答案，不能由实现者猜测。
- `NOT_FOUND`：在本次检索范围中没有找到对应实现或 artifact。

本次只读研究使用：

- [Cycle 2 Implementation Spec](e2e01-cycle2-implementation-spec.md)；
- [Activation Readiness Decision Packet](e2e01-cycle2-activation-readiness-decision-packet.md)；
- [Business Capabilities](../business-capabilities.md)；
- [Project Direction](../../PROJECT_DIRECTION.md)；
- [Intent Reference](../architecture/intent-design-reference.md)；
- [Tool Reference](../architecture/tool-calling-design-reference.md)；
- [Memory Reference](../architecture/memory-design-reference.md)；
- [Eval Strategy](../evaluation/agent-evaluation-strategy.md)；
- [P0 Eval Coverage Matrix](../evaluation/p0-eval-coverage-matrix.md)；
- [GSD Governance](../../.planning/GOVERNANCE.md)、[Roadmap](../../.planning/ROADMAP.md)、
  [Requirements](../../.planning/REQUIREMENTS.md) 与
  [State](../../.planning/STATE.md)；
- 当前 `src/`、`tests/`、`evals/` 与 Alembic migration chain。

用户已明确暂时停用 Graphify；本文没有运行或引用 Graphify。

## 2. 当前事实与差距

### 2.1 已满足的上游条件

- `CONFIRMED`：Phase 1 已 release 到 `main`，当前六个 authenticated physical
  Case 的 16 variants 为默认回归基线。
- `CONFIRMED`：Cycle 2 owner alignment 已合并，scoped contract 已激活为
  `CONTRACT_ACTIVE / READY_FOR_PLANNING`。
- `CONFIRMED`：`E2E01-02/03/05/06` 仍是 `CONTRACT_DEFINED`；Plan、artifact 或
  测试的出现不能自行推进 lifecycle。
- `CONFIRMED`：当前依赖栈已经具有 Python、Pydantic、PostgreSQL、SQLAlchemy、
  Alembic、FastAPI、离线 Eval Harness 和 credential-aware Qwen lane。
- `INFERRED`：Cycle 2 没有已证明的新第三方依赖需求；`pyproject.toml` 与
  `uv.lock` 默认不进入未来 Packet。

### 2.2 尚不存在的交付

- `NOT_FOUND`：`search_orders`、`get_shipment`、
  `OrderCandidateSetRecord`、`OrderCandidateSelectionRecord`、
  `SearchOrdersObservation`、`ShipmentObservation`、
  `ShipmentAssessment` 的当前源码实现。
- `NOT_FOUND`：Cycle 2 Alembic revision、Mock Shipment physical model、
  Phase 2 Eval bundle、14 longitudinal Result、13 mandatory Trajectory Result。
- `CONFIRMED / POST-SNAPSHOT`：Phase 2 master execution Plan 已由 PR #203
  批准并合并；`02-00` 已经 PR #204/#205 reviewed merge 并关闭
  `C2-BLOCK-02`。
- `CONFIRMED`：`02-01` / `02-03` exact Plan / Task Packet proposal 已准备；
  `02-02` 因 typed business contract dependency 等待真实 `B_C2_W1A`。
- `NOT_FOUND`：Phase 2 implementation integration branch、代码 feature Worktree
  或功能代码。
- `CONFIRMED`：当前 RegistrySnapshot 只注册 `get_order`。
- `CONFIRMED`：当前 `ReadToolExecutor.execute_get_order` 强制
  `max_attempts == 1`，没有 Cycle 2 retry surface。
- `CONFIRMED`：Phase 1 mapper 目前位于
  `DeterministicRenderer.map_result`，没有独立 `RunResultMapper` 文件。

## 3. Dependency DAG

```text
Phase 1 released baseline
  + Cycle 2 scoped contract active
  + trusted Session / trusted UTC clock
  + PostgreSQL / Alembic / immutable RegistrySnapshot
                         │
                         ▼
              Master Plan reviewed + approved
                         │
        ┌────────────────┴────────────────┐
        ▼                                 ▼
Resolve integration base/branch   Resolve Eval artifact path
        └────────────────┬────────────────┘
                         ▼
      zero-code scoped-owner path correction reviewed
                         │
                         ▼
      Exact GSD Plan / Task Packet pairs frozen
                         │
                         ▼
  Business + Candidate/Memory + Run/Trace contracts
                         │
                         ▼
               Tool / Gateway contracts
                         │
                         ▼
           Application records / Ports contracts
                         │
        ┌────────────────┼────────────────┬────────────────┐
        ▼                ▼                ▼                ▼
 strict codecs      RU/task routing   retry executor   Eval bundle
        │                │                │                │
        ▼                │                │                │
 physical migration     │                │                │
        │                │                │                │
        ├────────────┐   │                │                │
        ▼            ▼   │                │                │
 business adapters  PostgreSQL writers/readers/recovery   │
        │            │   │                │                │
        └────────────┴───┴────────────────┴────────────────┘
                         ▼
                Runtime mapper/renderer
                         │
                         ▼
           authenticated Eval graders/Harness
                         │
                         ▼
       pre-activation Composition / HTTP seam
       (`CONTRACT_DEFINED`, Harness still fail closed)
                         │
                         ▼
     Coverage owner `APPROVED_FOR_EXECUTABLE` ruling
                         │
                         ▼
       atomic Eval lifecycle / manifest / loader sync
                         │
                         ▼
        Harness + real HTTP lifecycle-valid Results
                         │
                         ▼
  Phase 1+2 regression / Review / Validation / Security
        / Eval re-review / Controlled UAT / lifecycle ruling
```

### 3.1 外部依赖

| Dependency | 状态 | Planning consequence |
|---|---|---|
| Phase 1 release baseline | `CONFIRMED / SATISFIED` | 每个 Wave 都必须保留 Phase 1 回归；不得修改 `get_order` scoped contract |
| Cycle 2 scoped contract | `CONFIRMED / ACTIVE` | Plan 只能消费，不可静默演进 D1–D8、R01–R18 |
| PostgreSQL / Alembic | `CONFIRMED / AVAILABLE` | 必须同时验证 empty DB 与 Phase 1 head 两条升级路径 |
| Credentialed Qwen | `OPEN / OPTIONAL` | 无凭据时保持 `NOT_RUN / CREDENTIALS_UNAVAILABLE`，不是 release blocker |
| Canonical app startup / lint / type-check / build | `NOT_FOUND` | Plan 不得编造命令或将其设为 Gate |

### 3.2 内部硬依赖

1. Public Core contract 必须先于 Application、Infrastructure、Eval consumer。
2. Application record / Port contract 必须先于 codec、physical migration、writer、
   reader与 recovery。
3. Codec catalog 必须先于 migration exact pair 和 active-version cutover。
4. Search business contract 必须先于独立 search-authority physical model；该
   model 不得复用或改写 Phase 1 `mock_orders.order_payload`。
5. Migration 必须先于 PostgreSQL v2 writer / reader / recovery 的真实集成。
6. Business Adapter 和 Runtime component 可以在不共享文件的前提下开发，但最终
   Runtime/E2E 只能消费已 review 的 owner-scoped Adapter。
7. Eval bundle schema、loader、Provider、Grader 和 Harness 是同一个 authenticated
   digest chain；不能由不同 writer 各自发明字段或路径。处于
   `CONTRACT_DEFINED` 时 Harness 必须在 SUT / Provider / Trace / Grader /
   Result 前 fail closed。
8. authenticated artifact、loader、Grader / Harness machinery 和真实
   pre-activation Composition / HTTP execution seam 都通过 exact-head review
   后，Coverage Matrix owner 才可作出 `APPROVED_FOR_EXECUTABLE` 裁决。
9. owner ruling、lifecycle consumer sync 与 post-activation Result 各由独立
   Plan / Task Packet 串行完成；任何一步不得兼任前一步的批准者。
10. Composition Root 不能成为临时修复公共合同的入口；pre-activation seam 只证明
    可复现入口，保持 Harness pre-dispatch fail closed，实际 Phase 2 Harness /
    Result 只在 `EXECUTABLE` sync 后运行。

## 4. Ownership map

以下是后续 master Plan 的 physical ownership proposal。它不改变 Cycle 2 Spec
第 1.2 节的 semantic owner。

| Boundary | Semantic owner | Proposed writer | Primary files / hotspot | Dependency |
|---|---|---|---|---|
| Eval model-script path correction | scoped implementation | Tech Lead | Cycle 2 Spec only | master Plan + user ruling |
| Search / Shipment DTO 与 assessment | Business | Runtime Engineer | new `core/order_search.py`、new `core/shipment.py` | scoped contract |
| Candidate / Observation / Task | Intent + Memory | Runtime Engineer | `core/task_state.py`、`core/memory.py` | scoped contract |
| Run / stop / no-result Trace | Core Runtime | Runtime Engineer | `core/trace.py` | scoped contract |
| ToolSpec / Registry / Gateway | Tool | Runtime Engineer | `core/tool_system.py`、`core/control_gateway.py` | Core contracts |
| Application commands / Ports | Application | Runtime Engineer | `application/records.py`、`application/ports.py` | Core contracts |
| Exact persistence codec | Application persistence | Runtime Engineer | `application/persistence.py` | Application contracts |
| RU / task routing | Intent + Core Runtime | Runtime Engineer | `core/request_understanding.py`、`core/request_processing.py` | Candidate + Tool + Application |
| Retry / restart behavior | Tool + Application | Runtime Engineer | `read_tool_executor.py`、`restart_recovery_service.py` | Tool + Application |
| Result mapper / Renderer | Business + Application | Runtime Engineer | `agent_run_service.py`、`deterministic_renderer.py`、Presentation files | Adapters + routing + retry |
| Physical catalog / migration | Infrastructure persistence | Infra Engineer | Alembic chain、`models.py`、migration tests | codec |
| Business read adapters | Business physical implementation | Infra Engineer | `infrastructure/order/postgres.py`、new shipment adapter | Business + Application |
| Atomic record persistence / recovery | Infrastructure persistence | Infra Engineer | `persistence/postgres.py`、`persistence/recovery.py` | migration + codecs |
| Bundle / loader / scripted Provider | Eval | Eval Engineer | five JSON artifacts、`artifacts.py`、`scripted_provider.py` | Tool + Application |
| Graders / Harness | Eval | Eval Engineer | `graders.py`、`harness.py` | persistence + Runtime + bundle |
| Pre-activation Composition seam | Integrator | Tech Lead | `bootstrap.py`、HTTP integration tests | Runtime + authenticated Eval machinery |
| Case lifecycle owner ruling | Eval Coverage | Canonical owner | `p0-eval-coverage-matrix.md` 独立 Plan / Packet / PR | authenticated artifacts + Grader / Harness + execution seam review |
| Lifecycle consumer sync | Eval | Eval Engineer | Cycle 2 case / manifest、`artifacts.py`、loader tests | owner ruling |
| Post-activation Harness / HTTP | Integrator | Tech Lead | Eval integration / E2E tests | all implementation + lifecycle barriers |

### 4.1 Single-writer hotspots

以下路径在同一 Wave 中不能有第二 writer：

- `src/mini_agent/core/tool_system.py`
- `src/mini_agent/core/trace.py`
- `src/mini_agent/application/records.py`
- `src/mini_agent/application/persistence.py`
- `src/mini_agent/application/agent_run_service.py`
- `src/mini_agent/infrastructure/persistence/models.py`
- Alembic revision chain
- `src/mini_agent/infrastructure/persistence/postgres.py`
- `src/mini_agent/evaluation/artifacts.py`
- `src/mini_agent/evaluation/graders.py`
- `src/mini_agent/evaluation/harness.py`
- `src/mini_agent/bootstrap.py`
- `tests/conftest.py`
- `pyproject.toml` 与 `uv.lock`
- active canonical docs 与 `.planning` shared state

### 4.2 文件拆分建议

- `INFERRED / PLAN CHOICE`：新增 `core/order_search.py` 与 `core/shipment.py`，
  不修改 Phase 1 `core/order.py` 的 `get_order` DTO。
- `INFERRED / PLAN CHOICE`：新增独立 search-authority physical model /
  `MockOrderSearchDocumentModel` / `mock_order_search_documents` table，存储 scoped Spec 要求的
  `line_ordinal`、`product_name`、`quantity`、`product_category`、
  `search_aliases` 与 owner / order identity；不扩写或重编码现有
  `mock_orders.order_payload`。
- `INFERRED`：新增 `infrastructure/shipment/postgres.py`，不把 Shipment
  cardinality/source-version 混入 `get_order` Adapter。
- `INFERRED`：新增独立 `application/run_result_mapper.py`，把 imported Phase 1
  rows 与 Cycle 2 delta 显式分离；若选择保留在 Renderer，必须由同一个 Packet
  单写并证明 zero-overlap。
- `INFERRED`：优先新建 Cycle 2 专项测试文件，避免多个 Packet 同写 Phase 1
  regression test。

## 5. Requirement coverage map

| Scoped requirement | Primary boundary | Downstream evidence |
|---|---|---|
| `R01` lifecycle / evidence truth | Plan + Eval + release | exact status and owner ruling |
| `R02–R04` search / matching / disclosure | Business + Adapter + Runtime | Component + longitudinal |
| `R05–R07` Observation / CandidateSet / ordinal | Intent + Memory + persistence | Component + Trajectory + HTTP |
| `R08–R11` Shipment / freshness / assessment | Business + Memory + Adapter + Runtime | Component + Trajectory + HTTP |
| `R12–R13` retry / no-retry | Tool + persistence + recovery + Runtime | Component + Trajectory |
| `R14` Mapper / stop / obsolete Run | Core Runtime + Application | Component + Trajectory |
| `R15` dynamic three-tool selection | Tool + Runtime + Eval | paired Trajectory + HTTP |
| `R16` records / Trace / recovery | Application + Infrastructure | migration + integration + Trajectory |
| `R17` Component / Trajectory / HTTP | Eval + Composition | 14 + 13 physical cases |
| `R18` aggregate / lifecycle | Integrator + canonical owners | post-execution quality gate |

| Case | Required implementation chain |
|---|---|
| `E2E01-02` | Business search → owner Adapter → Runtime unique route → Mapper → Eval / HTTP |
| `E2E01-03` | Search Observation → CandidateSet → ordinal CAS → target refresh → Eval / HTTP |
| `E2E01-05` | three-tool snapshot → same-hash paired route → zero/required Shipment calls |
| `E2E01-06` | Shipment Adapter → freshness → retry/recovery → assessment / safe failure |

## 6. Risk register

| ID | Severity | Evidence | Risk | Mandatory mitigation |
|---|---|---|---|---|
| `C2-RISK-01` | BLOCK | `CONFIRMED / PARTIALLY CLOSED` | `B_C2_OWNER_ALIGNED` 已冻结，但 integration branch / `B_C2_START` 仍未形成 | Gate P2-C 只可从 exact owner-aligned SHA 创建 branch并证明 SHA/tree equality；失败即停 |
| `C2-RISK-02` | BLOCK | `CLOSED / PR #205` | scoped Spec 与 repository/loader 的 model-script 目录曾不一致 | 保留 reviewed zero-code correction；后续 Eval Packet只消费 underscore 路径 |
| `C2-RISK-03` | HIGH | `CONFIRMED` | v1→v2 转换无法唯一重建时可能伪造 attempt / terminal evidence | 全量预验证；unknown/contradictory fail closed；禁止默认值和 read-time fallback |
| `C2-RISK-04` | HIGH | `CONFIRMED` | codec、DB constraint、reader/writer/recovery 分步激活形成 mixed active versions | 单一 cutover gate；所有 consumer ready 前不启用 v2 write |
| `C2-RISK-05` | HIGH | `CONFIRMED` | CandidateSet、pending question、selection、target 分事务会留下悬空 capability | owner-scoped exact reader + CAS + one-transaction closure；dangling/wrong-owner/duplicate reject |
| `C2-RISK-06` | HIGH | `CONFIRMED` | stale Shipment 或 Claim 被写成业务事实 | TTL / birth-stale gate、Claim/Observation 分离、assessment exact binding |
| `C2-RISK-07` | HIGH | `CONFIRMED` | retry 后成功覆盖 attempt 1 timeout / failure | append-only attempt child；final ToolCall 保留全部历史；max 2 |
| `C2-RISK-08` | HIGH | `CONFIRMED` | obsolete Run 覆盖新 Task 或补发旧回复 | `SUPERSEDED` CAS closure；no Task/RequestUnit/result/message/response write |
| `C2-RISK-09` | HIGH | `CONFIRMED` | model / Renderer 生成或改写事实与 assessment | safe projection + deterministic mapper/renderer；适用时触发 `CF-13` |
| `C2-RISK-10` | HIGH | `CONFIRMED` | 现有 `MockOrderModel.order_payload` 缺少 `line_ordinal`、`product_category`、`search_aliases`；直接扩写会改变 Phase 1 `get_order` parser/hash | 新建独立 search-authority physical model/table；现有 `mock_orders.order_payload` 不变；每 Wave byte-identical Phase 1 regression |
| `C2-RISK-11` | HIGH | `CONFIRMED` | Eval artifact 物理存在被误写成 `EXECUTABLE`，或 `CONTRACT_DEFINED` Case 被提前 dispatch | digest authentication、Grader/Harness、pre-activation execution seam、Coverage owner ruling、lifecycle sync 与 Result 分离；sync 前 Harness 在 SUT 前 fail closed |
| `C2-RISK-12` | MEDIUM | `CONFIRMED` | 大型热点文件导致 same-wave 冲突或 scope creep | 一个 hotspot 一个 writer；max concurrency 2；越界变更必须 dependency request |
| `C2-RISK-13` | MEDIUM | `INFERRED` | 过少大 Packet 会重演 Phase 1 返工；过多临时插入会失控 | master Plan 预列完整 slots；数量变化和新 slot 都回到用户审批 |
| `C2-RISK-14` | CRITICAL | `CONFIRMED` | 只读 Cycle 2 意外注册或触发 Action / side-effect recovery | Registry exact 等于三个 READ tools；无 confirmation、ActionPolicy、idempotency claim、Action Ledger write 或 `RESULT_UNKNOWN` side-effect recovery |
| `C2-RISK-15` | CRITICAL | `CONFIRMED` | ordinary Trace 泄露 trusted scope、业务 payload、候选摘要、source token、prompt、stack 或不必要 PII | Core exact whitelist + typed disclosure grader + HTTP / Trajectory negative evidence |
| `C2-RISK-16` | BLOCK | `CONFIRMED` | `02-02` 的 Search/Shipment Observation 直接依赖 `02-01` 的 typed business projection；从 `B_C2_START` 独立签发会迫使复制、弱化或越权实现 | `02-01` / `02-03` 可并行；先合并 `02-03`，再 overlay/merge `02-01` 形成 `B_C2_W1A`；之后才签发 exact `02-02` |

## 7. Gate decisions and remaining blockers

### 7.1 `C2-BLOCK-01`：integration branch / exact base

以下机械事实是 `b96fe8a...` 研究快照，不冒充当前 `main`：

```text
.planning/config.json git.base_branch = integration/e2e01-cycle2
integration/e2e01-cycle2 = NOT_CREATED / RESERVED_MAPPING_ONLY
main = b96fe8adf8ce4bcadbdf2cf008e28be4ff9aa5a3
integration/e2e01-thin = 250e4d2bf96e873592a687fe0e2629708a9a817d
git rev-list --left-right --count main...integration/e2e01-thin = 4 194
merge-base = 5d668f71b565dff9ecf353d215c41affe86cb637
```

`integration/e2e01-thin` 继续作为 Phase 1 历史 integration 证据，不被重命名、
重用或覆盖；它不是安全的 Cycle 2 start。Phase 2 推荐裁决：

```text
B_C2_PLAN_APPROVED
= planning PR merge successor

B_C2_OWNER_ALIGNED
= 02-00 merge successor

integration/e2e01-cycle2
= branch created from exact B_C2_OWNER_ALIGNED

B_C2_START
= integration/e2e01-cycle2 exact head/tree immediately after creation
= initial implementation base
```

因此 `B_C2_START` 的 SHA / tree 必须与 `B_C2_OWNER_ALIGNED` 相同；任何差异均
`BLOCK`。`.planning/config.json` 中的新值只是 Phase 2 reserved mapping，不证明
分支已存在，也不授权创建分支、Task Packet execution、代码 Worktree 或功能代码。
Gate P2-A 后已冻结 `B_C2_PLAN_APPROVED =
2879f5226a073051d1550fe079b4a427c1ec8cb1` / tree
`d5ded99bb0439fb57bbb4d6057fbda7a12b21fdf`；`02-00` reviewed merge 后又冻结
`B_C2_OWNER_ALIGNED = 4dc6dc95de81080fb3b651bc2f0026fb046fd9f8`
/ tree `521ac2c7611b20683089ab41a74d07c9a2bb8fc7`。当前仍不创建 integration branch，
也不冻结 `B_C2_START`。

### 7.2 `C2-BLOCK-02`：Eval model script 目录（已关闭）

`02-00` 修正前，Cycle 2 Spec 第 9.1 节曾指定：

```text
evals/model-scripts/e2e01-cycle2.v1.json
```

当前 active Spec、loader、Phase 1 manifests、tests 与 tracked directory 已统一使用：

```text
evals/model_scripts/
```

已执行裁决：保留现有 package / loader 约定，把 scoped Spec 的目标路径最小更正为
`evals/model_scripts/e2e01-cycle2.v1.json`。用户已批准 `02-00`；planning PR #204
与 zero-code owner correction PR #205 均已 reviewed merge，后者形成 exact
`B_C2_OWNER_ALIGNED`。该 blocker 不再阻止 Gate P2-C。

## 8. Planning conclusions

1. Phase 2 master execution Plan 已通过 Gate P2-A 与 PR #203；这不批准任一
   implementation Packet。
2. `C2-BLOCK-02` 已由获批并执行的 `02-00` 关闭；`B_C2_OWNER_ALIGNED` 已精确
   冻结。Gate P2-C 用户批准和 equality preflight 前，仍不得创建 Phase 2
   integration branch 或冻结 `B_C2_START`。
3. 推荐把全部已知后续工作拆成 19 个一对一 GSD Plan / Task Packet slots：
   `02-00` 零代码 scoped-owner correction、`02-01..18` 实现 / lifecycle /
   verification slots；共 13 个受控 Waves（`W0..W12`），最多两个并行 writer。
4. master Plan 批准不等于批准 Task Packet；Task Packet 批准不等于代码已经实现。
5. 当前只有 `02-01` / `02-03` 可从 owner-aligned base 精确签发；两者 reviewed
   串行 merge 形成真实 `B_C2_W1A` 后，才可生成 `02-02` exact Packet。该内部
   dependency refinement 不增加 slot、Wave 或并发上限。
6. 用户批准当前可签发 exact Packet、对应 Wave、initial base chain 与执行上限
   前，不创建 implementation branch、代码 Worktree 或功能代码；未来 Packet
   必须等真实 dependency barrier 产生后逐批签发，不能预填未来 SHA。
