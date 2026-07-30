# Mini Agent Project Instructions

> 本文件是当前项目唯一 canonical 的项目级协作规则。`CLAUDE.md` 只作为入口，不维护第二套规则、项目状态或命令。

## 0. 项目定位与 P0 原则

- 项目主体是面向已登录消费者的“订单与配送售后 Agent”，不是通用 Agent Runtime，也不是面向坐席的工作台。
- P0 只模拟一个自建站以及有状态的 Order、Shipment、Policy Knowledge 和 Refund 系统；不接入真实电商、支付、退款或物流系统。
- 项目采用模块化单体与 Ports & Adapters 边界；逻辑分层不表示微服务拆分。
- P0 用两条端到端场景验证 Request Understanding、`RequestUnit`、受控 ReAct、RAG Evidence、Tool / Action 安全边界、状态恢复、Trace 与 Agent Eval。
- Tool / Action System 不等同于模型原生 Tool Calling。模型只能提出候选；注册、Schema、授权、状态迁移、Evidence、确认、幂等、副作用执行和恢复由确定性代码控制。
- `create_refund` 是 P0 唯一代表性副作用动作，且只表示模拟退款；不得描述为真实支付渠道退款或到账。
- 每项 Agent 能力必须映射到 P0 用户目标、业务对象、端到端场景和可复现验证，不把无关技术 Demo 拼接成产品。
- 目标文档、架构图、示例契约和 Mock 设计不等于已经实现、验证或生产部署。
- `archive/` 中的旧 Runtime-first 设计只供历史参考，不得自动继承为当前产品、架构、契约或实现基线。

## 1. Active 文档权威

- [`docs/business-capabilities.md`](./docs/business-capabilities.md) 是 P0 业务范围、两条 E2E、Tool Catalog、Mock 系统和业务验收边界的 canonical owner。
- [`PROJECT_DIRECTION.md`](./PROJECT_DIRECTION.md) 是当前 P0 架构方向与 Runtime 主干基线；涉及业务范围时必须服从 `docs/business-capabilities.md`。
- [`docs/evaluation/agent-evaluation-strategy.md`](./docs/evaluation/agent-evaluation-strategy.md) 是 Eval-driven development、通用 EvalCase、Dataset 生命周期、Grader、指标 / Gate、报告和架构决策证据的 canonical owner；[`docs/evaluation/p0-eval-coverage-matrix.md`](./docs/evaluation/p0-eval-coverage-matrix.md) 是从业务与专项 owner 派生的 P0 Case ID、requirement mapping、Critical failure 和激活状态 owner，不得反向覆盖业务或组件语义。
- [`docs/architecture/intent-design-reference.md`](./docs/architecture/intent-design-reference.md) 是 Request Understanding、Query 上下文化、`TaskDeltaCandidate`、`InputBinding` 与确定性校验的规范性设计 owner。
- [`docs/architecture/tool-calling-design-reference.md`](./docs/architecture/tool-calling-design-reference.md) 是 Tool Registry / Executor、不可变工具集快照、Provider 名称映射、Control Gateway 工具校验、ToolCall 生命周期、超时、中断及工具调用专项 Trace / Eval 的规范性设计 owner。
- [`docs/architecture/memory-design-reference.md`](./docs/architecture/memory-design-reference.md) 是 Memory、Run / Task State、Observation、Evidence、Action Ledger 与 Context Manifest 的规范性设计 owner。
- [`docs/architecture/rag-design-reference.md`](./docs/architecture/rag-design-reference.md) 是 Policy Corpus 受控 ingestion、清洗、结构解析、Chunking、Hybrid Retrieval、RRF、Cross-Encoder、Evidence 组装处理与 RAG Eval 的规范性设计 owner；Evidence Binding 的权威语义仍服从 `memory-design-reference.md`，ToolCall 生命周期仍服从 `tool-calling-design-reference.md`。
- [`docs/implementation/e2e01-thin-slice-implementation-spec.md`](./docs/implementation/e2e01-thin-slice-implementation-spec.md) 是 `E2E01-01/04` 第一最薄切片的 scoped active implementation owner，只拥有该切片的具体编码、HTTP、Session Fixture、`get_order` Schema、Mock、持久化投影、Provider Adapter、Eval 数据与目标命令契约；它必须引用并服从上述业务、Intent、Tool、Memory 与 Eval canonical owner，不得把切片选择升级为整个 P0 的通用语义。`E2E01-05` 延至 `get_order` 与 `get_shipment` 同时可用的 E2E-01 扩展阶段。
- [`docs/architecture/consumer-after-sales-agent-business-application-architecture-v2.drawio`](./docs/architecture/consumer-after-sales-agent-business-application-architecture-v2.drawio) 及其 SVG / PNG 导出是当前最新、唯一的 P0 架构基线。
- [`docs/architecture/README.md`](./docs/architecture/README.md) 负责标识当前架构图、配套视图和历史图；图形表达不得覆盖上述语义 owner。
- 专门 owner 只在自身范围内优先。跨文件冲突必须显式标记并完成影响分析，不得用“较新文件”静默覆盖其他 owner。
- 当前 active Markdown 与 V2 图形统一使用“多意图”表述；active Markdown 中的 Request Understanding 已统一为开放目标 `TaskDeltaCandidate`，不采用业务 Intent / Capability 分类或 RequestUnit Tool allowlist，V2 图形只保留通用 Request Understanding / RequestUnit Board 抽象；独立公开产品知识服务已退出 P0。Flow V2 已区分 Observation、Evidence、Agent 本轮结果、Task 状态和 Action Ledger 状态；代码依赖 V2 已同步 Task Working Context、独立记录域、Application / Core Port 所有权与 P0 非 Redis 权威边界。Eval 已统一采用贯穿实现全过程的 Eval-driven development，并以 Product Outcome、Component / Trajectory / E2E、质量维度、Grader 和生命周期分轴表达。图形仍不得覆盖对应语义 owner。
- `archive/`、临时分析、Graphify 输出和历史图不是 active contract owner。

## 2. 文档语言

- 产品、规划、架构、复盘和说明文档默认使用中文。
- API、字段、类名、函数名、命令、路径、测试名和必要技术术语保留英文。
- 用户明确要求英文或双语时，以当次要求为准。

## 3. 证据与结论纪律

- 对仓库事实的判断优先使用 `rg` 定位，再读取必要上下文；Graphify 的使用规则见文末。
- 明确区分 `CONFIRMED`、`INFERRED`、`OPEN` 与 `NOT_FOUND`。当前仓库中找不到依据时直接说明，不补造结论。
- 不把 Proposal、Plan、Reference、示例 Schema、架构图或目标态描述成已经实现。
- 不把当前实现的偶然行为自动升级为正确产品设计或 canonical contract。
- 不虚构真实客户、生产数据、生产事故、采用率、付费、ROI、商业价值或生产验证。
- 所有“已实现”“已验证”“已修复”“可运行”结论都必须引用当前源码、测试、命令输出或其他可复现证据。

## 4. 架构与安全不变量

- `customer_id` 和授权范围只能来自服务端可信上下文；用户消息和模型不得生成、覆盖或扩大它们。
- 私有资源访问必须在业务系统边界使用当前可信身份限定；不存在和无权访问不得形成可区分的信息泄露。
- 读路径可以根据最新 Observation 动态形成，但身份、资源归属、最小披露、Evidence、精确确认、ActionPolicy、幂等和 `RESULT_UNKNOWN` 恢复是不可绕过的确定性边界。
- 用户陈述与模型推断只能作为 Claim 或候选；业务事实来自受控 Observation，知识依据来自可追溯的版本化 Evidence。
- Memory 用于继续任务，不证明最新业务事实，不授予权限，不代表用户确认，也不替代 Decision & Action Ledger。
- Eval 至少覆盖 Component、Trajectory 和 E2E；不能只验证最终回复文本。Trace 必须支持关键决策、工具、Evidence、状态变化、失败、重试和停止原因的追踪，同时不得记录原始 Token 或不必要的 PII。

## 5. 文档与契约演进

- 只有 active owner 中明确规范的内容约束后续 Plan 与实现；Research、Spike、Design Note、Graphify 报告和归档材料默认是 `NON_NORMATIVE` 参考。
- 禁止未声明的契约漂移。允许经过问题说明、影响分析、owner 裁决、cross-file alignment 和适用验证的契约演进。
- Plan 使用参考材料时，必须明确哪些是现行约束、哪些只是参考、是否提出契约变更，以及哪些决策仍待裁决。
- 发现 Spec 与 bug fix 冲突时，先判断是实现缺陷、Spec 错误、非权威差异还是临时偏差，不得为了机械符合旧文档而保留错误设计。
- 同时跨越多个 ownership boundary、外部契约或 verification gate 的工作，执行前拆成可独立验收的步骤。
- 延期事项必须指向明确 milestone、phase 或 decision gate，不写模糊的“以后处理”。

## 6. 实现与验证

- 当前项目的 canonical 本地命令如下；必须从仓库根目录执行：

  ```bash
  uv sync --all-groups
  docker compose up --wait -d db
  docker compose --profile test up --wait -d db-test
  uv run alembic upgrade head
  uv run pytest
  ```

- 上述命令证明当前依赖、PostgreSQL / pgvector、migration chain、隔离测试 namespace，以及已合并的 Core / Application、Runtime、Infrastructure 与 Eval component / integration 证据可复现；当前套件还覆盖显式 `OfflineE2E01Composition`、real `EvalCaseSut`、PostgreSQL exact owner-scoped evidence reader、直接 HTTP → Runtime → PostgreSQL 离线纵向 evidence、credential-aware Qwen runner 的零网络路径和真实 `CONTRACT_DEFINED` artifacts 的 Harness lifecycle fail-closed 边界。这些证据仍不证明 canonical 应用启动、lifecycle-valid Trajectory / E2E Eval Result、回归报告、真实 credentialed Qwen Baseline、production readiness 或 P0 产品已经完成。
- 当前尚未建立 canonical 的应用启动、lint、type-check 和构建命令；相关配置和实现真实出现并通过验证前不得编造。可选并行测试只能作为附加证据，不能替代上述默认串行门禁。
- 每个纵向切片在实现前先定义最小 Eval Contract；Component Eval 随实现增长，第一条完整纵向切片尽早运行 Trajectory / E2E Eval，实际失败必须进入回归集。不得在没有实现反馈时一次性冻结全部普通指标或阈值。
- 修改完成后必须运行与风险相称的机械检查、测试或可复现验证，并准确报告已执行、未执行和失败的项目。
- 没有自动化验证入口时，至少使用 `rg`、链接/路径检查和必要的源文件对照验证文档术语、状态、ID、范围及引用。

## 7. 文件与变更边界

- 用户给出的文件 allowlist 是硬边界；完成后检查实际变更范围。
- 保留用户已有改动，不覆盖、回退或格式化无关文件。
- 用户要求 `READ-ONLY`、独立审核或“不要修改文件”时，严格只读。
- 每次修改 active Product、Architecture、Spec、Validation、Plan、README、项目指令、代码或测试后，执行一次仓库级 cross-file impact scan，并在授权范围内对齐所有受影响的 active 文件。
- Cross-file alignment 从 canonical owner 出发：owner 保存规则正文，消费者通过引用、映射或派生视图对齐，不维护第二套 canonical 内容。
- 如果 READ-ONLY 或明确 allowlist 阻止同步修改，保持边界并列出仍需对齐的文件、差异和风险；不得声称仓库已完全 aligned。
- 归档材料的历史正文不随 active contract 变化而重写；只有状态横幅、当前权威链接或引用边界会造成误导时才调整。
- 项目规则保持精简；产品、架构、契约和评测细节放入对应 active 文档，不继续堆入本文件。

## 8. 多 Agent 并行开发

- 写入型并行工作使用不同 Git Worktree 和不同 branch；不得让多个 Agent 同时写同一个 checkout、branch 或文件。
- 一个 GSD Plan 只对应一个精确 Task Packet；Packet 可以包含多个原子 task，但不得跨 repository、branch、Worktree、writer 或 ownership boundary。每个 Task Packet 必须包含精确 `base_sha`、文件 allowlist、禁止文件、依赖、验证命令、`contract_changes`、`security_impact`、`eval_impact`、`rollback` 与交接格式；无适用项时显式填写 `NONE`，同一 wave 内一个文件只有一个 writer。
- `pyproject.toml`、lockfile、migration chain、共享测试 bootstrap、Composition Root 和 active canonical 文档属于 single-writer 热点，由明确 owner 或 Integrator 串行修改。
- 主任务 / Integrator 负责契约裁决、逐个集成、仓库级验证和 cross-file impact scan。子 Agent 默认用于只读探索、审查和测试分析；写入任务必须具备互不重叠的 ownership。
- Agent 交接必须报告 branch / commit、实际变更文件、执行命令与结果、allowlist 检查、契约变化和未决风险；任务完成不等于切片已实现。
- 写入任务只向 Task Packet 指定的 GitHub repository 和 feature branch push；未明确 `remote`、head branch 和 base branch 时不得猜测或发布。禁止直接 push `main` 或 active integration branch。
- 新建空 GitHub repository 时，Integrator 可以一次性 push 已确认的 `main` 与 active integration baseline 以建立 PR base；必须记录精确 commit，并在 bootstrap 后立即配置可用的 branch protection。该例外不适用于后续开发变更。
- E2E 实现 feature branch 先创建 draft PR 到对应 integration branch；Integrator 串行合并后，再由 integration branch 创建 PR 到 `main`。Repository 级流程或紧急修复可直接 PR 到 `main`，但仍不得绕过验证和 review。
- PR 必须使用 [`.github/pull_request_template.md`](./.github/pull_request_template.md)，如实记录 Task Packet、ownership、契约变化、检查结果、未执行项、安全 / Eval 影响、风险和回滚方式。
- GSD 只可作为派生的规划、审查与验证辅助；`.planning/` 不得成为产品、架构、契约或 Eval 语义的第二套 canonical owner。其 owner mapping、single-writer、severity、GitHub / Worktree 映射、quality gate 与 rollback 见 [`.planning/GOVERNANCE.md`](./.planning/GOVERNANCE.md)，activation 基线、allowlist、冲突审查与实际验证见 [`.planning/ACTIVATION.md`](./.planning/ACTIVATION.md)。Activation 只有在独立 PR 的 final exact-head review 为 `PASS` 且合并后才生效。
- Stock GSD 1.38.3 的 `gsd-import`、`gsd-plan-phase`、`gsd-execute-phase`、`gsd-verify-work`、`phase.complete`、`requirements.mark-complete`、`roadmap.update-plan-progress` 与 `gsd-ship` 在当前项目禁用：plan / import 会写共享 State，verify 没有 `--no-transition` 且会进入 `phase.complete`，execute 会管理并可能以 `--force` 清理全部非当前 Worktree并提前完成 phase，ship 的单一 base 不能表达 feature → integration 与 integration → `main` 两级 PR。GSD planner / checker 角色可只读提供建议，最终 Plan 由 Integrator 在 dedicated planning-status Worktree 单写。`parallelization=false` 与 `workflow.use_worktrees=false` 只关闭 GSD 自管并行 / Worktree；Codex 多 Agent 仍由 Integrator 在 workflow 外预建精确 Task Packet Worktree / feature branch，走 draft PR、串行合并与显式 release PR。
- `gsd-code-review` 只可在 exact-integration-SHA review-artifact Worktree 中用规范化绝对路径的 exact `--files` 写 Phase `REVIEW.md`；preflight 须证明 requested=accepted=unique、每项均为仓库内 regular tracked file 且 literal tracked 输出精确等于单个相对路径，workflow transcript scope 数量必须相等且不得出现 stock 的 outside-repository / file-not-found skip 输出。`gsd-code-review-fix` 与 `gsd-validate-phase` 只可在 Integrator 预建的 dedicated fix / validation Worktree 和 branch 中条件运行，并以前后 base/head/allowlist/changed-files/commits containment check 阻断 scope drift。`gsd-eval-review` 必须先有引用 canonical Eval owner 的派生 mapping；`gsd-secure-phase` 必须有完整 `<threat_model>` 映射且 zero-threat 不通过；会话式验收使用不含 lifecycle route 的受控 UAT adapter。
- `E2E01-01/04` 的具体 Wave、ownership 与 Task Packet 见 [`docs/implementation/e2e01-thin-slice-multi-agent-plan.md`](./docs/implementation/e2e01-thin-slice-multi-agent-plan.md)。该 Plan 只拥有执行拆分，不覆盖任何 active canonical owner。

## graphify

This project has a knowledge graph at `graphify-out/` with god nodes, community structure, and cross-file relationships.

When the user types `/graphify`, use the installed graphify skill or instructions before doing anything else.

Rules:

- For codebase questions, first run `graphify query "<question>"` when `graphify-out/graph.json` exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than `GRAPH_REPORT.md` or raw grep output.
- Dirty `graphify-out/` files are expected after hooks or incremental updates; dirty graph files alone are not a reason to skip Graphify.
- If `graphify-out/needs_update` or `graphify-out/.needs_update` exists, treat the graph as stale for current repository facts. It may still support historical navigation, but verify conclusions against active source files and update the graph when the task scope permits.
- If `graphify-out/wiki/index.md` exists, use it for broad navigation instead of raw source browsing.
- Read `graphify-out/GRAPH_REPORT.md` only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost). Documentation and image changes require an explicit semantic update when Graphify freshness is part of the task.
