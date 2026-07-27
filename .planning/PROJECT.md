# Mini Agent｜GSD 派生执行上下文

> **DERIVED / NON_NORMATIVE**
> 本文件只为 GSD 提供精简执行上下文，不拥有产品、架构、契约、Eval 语义或实时实现事实。任何冲突都以 [AGENTS.md](../AGENTS.md) 列出的对应 canonical owner 为准；专门 owner 只在自身范围内优先，绝不采用 “newest wins”。

## What This Is

这是既有 Mini Agent P0 仓库的 GSD 派生执行上下文，只索引 canonical owner 已定义的目标、约束与证据。产品本身是什么、面向谁以及验收语义仍由下列 active owner 定义，本文件不另建项目定义。

## 权威来源

- P0 业务范围与两条 E2E：[业务能力说明](../docs/business-capabilities.md)。
- P0 架构方向：[PROJECT_DIRECTION.md](../PROJECT_DIRECTION.md)。
- Eval 方法与 Case 激活顺序：[Agent Evaluation Strategy](../docs/evaluation/agent-evaluation-strategy.md) 与 [P0 Eval Coverage Matrix](../docs/evaluation/p0-eval-coverage-matrix.md)。
- 第一最薄切片契约：[E2E-01 Thin Slice Implementation Spec](../docs/implementation/e2e01-thin-slice-implementation-spec.md)。
- 当前 Task Packet、ownership 与集成顺序：[Codex 多 Agent 实施计划](../docs/implementation/e2e01-thin-slice-multi-agent-plan.md)。
- GSD 派生层治理：[GOVERNANCE.md](GOVERNANCE.md)；激活证据：[ACTIVATION.md](ACTIVATION.md)。

## Core Value

在不制造第二套项目定义的前提下，把 canonical owner 已定义的 P0 目标转成可隔离、可审查、可验证、可追溯的执行阶段。

## Requirements

### Active

- [ ] 执行 [REQUIREMENTS.md](REQUIREMENTS.md) 映射的 Phase 1 `E2E01-01/04`，但只有 canonical lifecycle 与硬证据同步完成后才标记完成。

### Planned Mapping

- Phase 2–6 只保留 Case ID / Cycle mapping；对应 scoped implementation owner 出现前不生成实现细节。

### Out of Scope

- `.planning/` 不重新定义业务、架构、契约、Eval 或 Case lifecycle。
- GSD workflow 不绕过 Task Packet、Worktree、PR、review 或 canonical verification gate。

## 当前执行边界

- 当前 integration branch：`integration/e2e01-thin`；01-07B feature PR #44 的 reviewed code merge为`ccdafe87d5f118b729d6f3fff8635a0b92f3e3c5`。historical Runtime / Infra feature仍以`c35687d...`为只读证据；replacement Runtime / Infra分别从`64992cf...`与`fb607019...`执行并已合并。
- Activation feature base：`85eb2a7fc4cc131e67e44dbba132b526e36ae6a3`；reviewed feature head：`957cabd6b31dd2156848acd515d2e8dc3d19bd50`；effective integration merge：`624475681847be5a8e463e32dafd28a0483b213b`。
- 当前 active phase：Phase 1，Coverage Matrix Cycle 1 的 `E2E01-01/04`。
- Plan 01-01、01-02 与 01-03 已分别通过 planning / owner PR、181 个 serial tests 与独立 exact-head review完成 evidence index；Plan 01-04 已通过 planning PR #18、feature PR #19、134 个 focused / 315 个 full tests、两路 final exact-head review 与 Graphify code + semantic freshness gate；Packet 01-04D 已通过 planning PR #20、feature PR #21、210 个 focused / 344 个 full tests、两路 final exact-head review 与 post-merge Graphify gate。五个已完成 Packet 都不改变 `E2E01-01/04` lifecycle。
- 01-04E/F/G/H owner Packet已依序通过PR #23/#24/#25/#32合并；01-05R通过PR #33/#34 merge `fb607019...`，01-06R通过PR #35/#36 merge `8e21652...`，01-07 PR #29在latest-integration overlay复验后merge `eee1c0e...`。01-07A planning/Runtime PR #37/#38又merge为`4cfac0a...`；Business、Eval、项目规则状态PR #39–#41随后形成01-07B execution base。01-07B planning/status PR #42–#43与feature PR #44已reviewed merge为`ccdafe87...`，通过367 Harness、725 owned、762 Plan focused、40 migration、1493 full（1 deselected）、双review与Graphify gate；lifecycle仍为0/8。
- 当前 immediate gate：从本status alignment PR reviewed merge后的同一exact integration SHA分别签发`01-07C` RU semantic ruling与`01-07G` Thin Slice source-version ruling。01-07B已经关闭完整Case/Script、output-side semantic `case_id`答案暴露与variant-scoped安全因果Trace阻断，但不拥有外部`ModelProvider`异常合同；invalid-RU `ValidationError` / `ProviderProtocolError`分类缺口仍由后续01-07I/J/L分别按Application Port、Runtime、Eval-owned Provider consumer边界关闭。后续按`{01-07C, 01-07G} → {01-07D, 01-07H} → {01-07E, 01-07F} → 01-07I → 01-07J → {01-07K, 01-07L} → 01-08 → 01-08A`逐级签发；每组必须全部串行合并形成共同exact barrier后才进入下一组。当前证据仍不证明真实HTTP Trajectory/E2E、credentialed Qwen baseline或产品完成。
- 当前 Case 生命周期仍由 Coverage Matrix 拥有；本文件和其他 `.planning/` 文件不能将 Case 标为 `EXECUTABLE` 或 `REGRESSION_GATE`。

## 不属于 GSD 派生层的事项

- 不重新定义 P0 用户、业务目标、Tool Catalog、Mock 系统或安全不变量。
- 不重新定义 Core / Application DTO、Port、状态机、Evidence、Action Ledger 或 Eval 语义。
- 不以 `$gsd-new-project` 或 `$gsd-new-milestone` 重建当前 P0。
- 不让 GSD executor 直接写 `main`、`integration/e2e01-thin` 或共享 `.planning/STATE.md`。
- 不运行 stock `$gsd-execute-phase`、`phase.complete`、`requirements.mark-complete`、`roadmap.update-plan-progress` 或 `$gsd-ship`；实现、生命周期同步与两级 PR 均由 Integrator 按 [GOVERNANCE.md](GOVERNANCE.md) 显式控制。
- 不把计划、Review、UAT 或 GSD 报告自身当作“已实现 / 已通过”的充分证据。

## 执行决策

| 决策 | 理由 | 状态 |
|---|---|---|
| GSD 是派生编排层，canonical owner 保持不变 | 防止 `.planning/` 成为第二套产品 / 架构 / Eval 语义 | `CONFIRMED` |
| `git.branching_strategy=none` | 分支与 Worktree 继续由精确 Task Packet 和 GitHub PR 流程拥有 | `CONFIRMED` |
| `parallelization=false`、`workflow.use_worktrees=false` | 只关闭 GSD 自管并行 / Worktree；Codex Agent 仍在 Integrator 预建 Worktree 中并行 | `CONFIRMED` |
| 共享 Roadmap / State 由 Integrator 单写 | 避免多个 feature branch 推进相互冲突的执行状态 | `CONFIRMED` |
| 当前 P0 不运行 `new-project` / `new-milestone` / `autonomous` | 既有项目已有明确 owner、Spec 与执行基线 | `CONFIRMED` |
| 一个 GSD Plan 对应一个精确 Task Packet | Packet 可以含多个原子 task，但不能跨 repository、branch、Worktree、writer 或 ownership boundary | `CONFIRMED` |
| 持久化投影写入前经 Pydantic serialization，并保存 schema version | 这是 Thin Slice Spec 当前可确认的 scoped 要求 | `CONFIRMED` |
| Persistence 四轴 ownership、版本维度与 Trace shared-structure authority | 已由 Plan 01-01 / PR #12 写入 `PROJECT_DIRECTION.md`；不表示 decoder、registry、业务表或 migration 已实现 | `CONFIRMED / CONTRACT_ONLY` |
| P0 exact-version、decode / recovery / migration runtime 行为 | 已由 Plan 01-02 / PR #14 写入 Memory owner；不表示 codec、Adapter、业务表或 recovery 已实现 | `CONFIRMED / CONTRACT_ONLY` |
| Thin Slice 17-item item code、版本、projection 与实现 API | 已由 Plan 01-03 / PR #16 与 clarification PR #17 写入 Thin Slice scoped owner；不得从测试 fixture 或 Python 类名动态推断 | `CONFIRMED / CONTRACT_ONLY` |
| 01-04 Application logical persistence codec | PR #19 已合并；17-item registry、strict codec 与 Component tests 已实现；不拥有授权、complete graph、physical persistence 或 migration | `COMPLETE / EVIDENCE_INDEXED` |
| 01-04D Application persistence write / recovery Port closure | PR #21 已合并；relation-aware write、原子 initial/transition/Run finalization 与 fenced complete-graph claim boundary已有 Application contract和契约测试证据 | `COMPLETE / EVIDENCE_INDEXED` |
| 01-04E Memory token availability | 保持 required `TokenCounts` object；每个方向可为 strict `int \| None`，`None`表示未精确测量，禁止coercion、0占位或估算伪造 evidence | `COMPLETE / EVIDENCE_INDEXED / PR #23` |
| 01-04F Thin Slice / Eval fault alignment | stale-state变体以canonical Port执行`ACTIVE/v1 → WAITING_USER/v2` race，再由Gateway拒绝并推进`BLOCKED/v3`；fact-bearing raw presentation映射为 Provider protocol failure | `COMPLETE / EVIDENCE_INDEXED / PR #24` |
| 01-04G recovery Trace atomicity | Application command携带Core-produced exact recovery Trace；Port contract要求compliant Adapter将APPLIED state/link/Trace同事务并拒绝跨类型payload污染 | `COMPLETE / EVIDENCE_INDEXED / PR #25` |
| 01-04H terminal-turn contract | planning PR #31 + owner PR #32；reviewed head `c0306ef...`、merge `64992cf...`、269 focused / 560 full与post-merge Graphify gate | `COMPLETE / EVIDENCE_INDEXED` |
| 01-05R Runtime replacement | planning PR #33 + Runtime PR #34；reviewed head `05f0182...`、merge `fb607019...`、100 focused / 660 full、38 migration与post-merge Graphify gate | `COMPLETE / EVIDENCE_INDEXED` |
| 01-06R Infra replacement | planning PR #35 + Infra PR #36；reviewed head `377f837...`、merge `8e21652...`、83 focused / 40 migration / 745 full与post-merge Graphify gate | `COMPLETE / EVIDENCE_INDEXED` |
| 01-07 Eval | PR #29 head `b8ecbb0...`经post-Infra overlay `ee46f38...`复验并merge `eee1c0e...`；191 focused / 40 migration / 936 full（1 deselected）、双preflight与Graphify gate | `COMPLETE / EVIDENCE_INDEXED` |
| 01-07A Runtime Trace alignment | planning PR #37、Runtime PR #38；merge `4cfac0a...`；100 Runtime focused / 40 migration / 936 full（1 deselected）、双路feature/overlay review与Graphify gate | `COMPLETE / EVIDENCE_INDEXED` |
| 01-07B Eval evidence boundary | exact base `8544137...`；PR #44 merge `ccdafe87...`；six-file Eval ownership关闭Case/Script/nested/output-side oracle、one-time correlation、canonical boundary与variant-scoped safety-causal Trace precedence；[Summary](phases/01-cycle-1-e2e-01/01-07B-SUMMARY.md) | `COMPLETE / EVIDENCE_INDEXED` |
| 01-07C RU semantic ruling | Request Understanding owner裁决contextualization/candidates/created_at/base-result versions的exact durable shape、logical version evolution、compatibility与rollback | `READY_AFTER_STATUS_ALIGNMENT` |
| 01-07D Thin Slice RU exact mapping | scoped owner把01-07C映射为exact model-output/record version、registry/closure语义；与01-07G共享Thin Slice owner文件，必须等C/G串行合并后从同一exact SHA签发；只写active mapping | `BLOCKED_BY_01-07C/G` |
| 01-07E Application persistence codec | codec sole writer消费01-07D，落实per-record version registry/encode/decode与tests；不修改active docs或RU DTO；只从01-07D/H共同merge barrier签发 | `BLOCKED_BY_01-07D/H` |
| 01-07F RU Core implementation | RU owner消费01-07D，持久化actual output/candidates并区分logical record version与model-output schema；不修改codec；只从01-07D/H共同merge barrier签发 | `BLOCKED_BY_01-07D/H` |
| 01-07G Thin Slice `get_order` source-version ruling | scoped owner定义server-private version唯一来源/算法、FOUND必填、Observation/Manifest exact copy与禁止schema fallback；不实现Core DTO | `READY_AFTER_STATUS_ALIGNMENT` |
| 01-07H Core/Order DTO consumer | 独立Python source owner把01-07G映射到`GetOrderResult`合同与Component tests；与01-07D一起只从C/G merge barrier后的同一exact SHA签发，不修改Runtime/Infra/docs | `BLOCKED_BY_01-07C/G` |
| 01-07I Application exact-Run Evidence Port / Provider failure contract | 定义expectation-free、owner-scoped、transactionally-consistent closure DTO/Port及partial/torn fail-closed；同时由Port declaration owner冻结fresh parameterless、raw-free RU candidate-invalid signal及`ModelProvider`异常分类；不构造`EvalEvidence`、不实现Runtime或Adapter | `BLOCKED_BY_01-07E/F/H` |
| 01-07J Runtime consumer / INPUT_INVALID mapping | 消费01-07E/F/H/I，写canonical RU record、传播P0 source version且Manifest不fallback；只捕获01-07I bounded signal并映射`COMPLETED / INPUT_INVALID`，不得catch raw Pydantic/ValueError/Exception或泄露诊断 | `BLOCKED_BY_01-07E/F/H/I` |
| 01-07K Infra strict reader | 实现01-07I Port的一致snapshot与01-07G/H order version物理适配；不得定义DTO/Port/Eval语义 | `BLOCKED_BY_01-07J` |
| 01-07L Eval mapper / Scripted-Qwen consumers | 把真实HTTP结果与Application closure映射为`EvalEvidence`；只消费持久化RU output，不从script/expectations补造；按01-07 Eval ownership让Scripted与Qwen只将RU output Pydantic拒绝映射为01-07I signal，协议/Presentation分支仍是raw-free `ProviderProtocolError`，并以Component/real-Runtime tests防止分类漂移 | `BLOCKED_BY_01-07I/J` |
| 01-08 vertical integration | 等待01-07K/01-07L reviewed merge；Integrator只装配真实HTTP→Runtime→PostgreSQL→Eval链 | `BLOCKED_BY_01-07K/L` |
| 01-08A credentialed Qwen runner | 等待01-08 reviewed merge后由Eval owner签发；缺凭据只能记录`NOT_RUN / SKIPPED` | `BLOCKED_BY_01-08` |

## 完成证据规则

阶段完成必须同时具备适用的源码、测试 / migration / Eval 输出、文件 allowlist 检查、GitHub exact-head review 与 PR 记录。GSD 状态只索引这些证据，不取代这些证据。
