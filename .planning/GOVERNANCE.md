# Mini Agent｜GSD 派生层治理

> **DERIVED / NON_NORMATIVE**
> 本文件拥有的仅是 GSD 执行层治理，不拥有产品、架构、契约、HTTP、Schema、Fixture、Eval 语义或 Case 生命周期。项目级 canonical 规则仍由 [AGENTS.md](../AGENTS.md) 拥有；发生冲突时本文件必须阻断，不得反向覆盖 active owner。

## 1. Owner Mapping 与冲突优先级

| 语义范围 | Canonical owner | GSD 派生消费者 |
|---|---|---|
| P0 业务范围、两条 E2E、Tool Catalog、Mock 系统 | [business-capabilities.md](../docs/business-capabilities.md) | `PROJECT.md`、`REQUIREMENTS.md`、`ROADMAP.md` |
| P0 架构方向 | [PROJECT_DIRECTION.md](../PROJECT_DIRECTION.md) | Phase / dependency 摘要 |
| Request Understanding / `InputBinding` | [intent-design-reference.md](../docs/architecture/intent-design-reference.md) | Task Packet canonical inputs |
| Tool lifecycle / Gateway / Trace | [tool-calling-design-reference.md](../docs/architecture/tool-calling-design-reference.md) | Task Packet、Review / Security gate |
| Memory / Observation / Evidence / Action Ledger | [memory-design-reference.md](../docs/architecture/memory-design-reference.md) | Task Packet、Review / recovery gate |
| RAG | [rag-design-reference.md](../docs/architecture/rag-design-reference.md) | Phase 3 mapping |
| P0 图形架构基线与图形索引 | [consumer-after-sales-agent-business-application-architecture-v2.drawio](../docs/architecture/consumer-after-sales-agent-business-application-architecture-v2.drawio) 与 [architecture/README.md](../docs/architecture/README.md) | 只作导航；图形不得覆盖语义 owner |
| Eval 方法、Dataset、Grader、Gate | [agent-evaluation-strategy.md](../docs/evaluation/agent-evaluation-strategy.md) | validation / eval review 索引 |
| P0 Case ID、mapping、Critical failure、生命周期 | [p0-eval-coverage-matrix.md](../docs/evaluation/p0-eval-coverage-matrix.md) | `REQUIREMENTS.md`、Roadmap Phase mapping |
| `E2E01-01/04` scoped 实现契约 | [e2e01-thin-slice-implementation-spec.md](../docs/implementation/e2e01-thin-slice-implementation-spec.md) | Phase 1 Plans |
| Wave、ownership、Task Packet、集成顺序 | [e2e01-thin-slice-multi-agent-plan.md](../docs/implementation/e2e01-thin-slice-multi-agent-plan.md) | Phase 1 wave / status |

专门 owner **只在自身范围内优先**。不得用文档类别、提交时间、文件新旧或 `.planning/` 生成顺序静默覆盖其他 owner；绝不采用 “newest wins”。

### 冲突处理

1. 标记冲突为 `BLOCK`，记录涉及范围、文件、语义和下游影响。
2. 定位对应 specialized canonical owner；跨 owner 时逐项列出，不使用通用文档优先级代替裁决。
3. 停止受影响 Plan 的 import / execution / merge。
4. 由 owner / Integrator 完成问题说明、影响分析、裁决与 cross-file alignment。
5. 重新运行适用机械检查和独立 exact-head review 后，Integrator 才能同步 `.planning/` 派生视图。

## 2. 写入 Ownership 与外部执行模型

- `.planning/STATE.md`、`.planning/ROADMAP.md`、`.planning/REQUIREMENTS.md`、跨 phase index 和 shared progress 仅由 Integrator 在从 exact integration SHA 预建的 dedicated planning-status Worktree / feature branch 中串行写入，并通过 PR 合并；不得直接写 active integration branch。
- Plan-scoped artifact 只有在 Task Packet 明确分配路径、branch 和 writer 时才可写入；feature Worktree 不得各自推进共享 State，也不得直接修改 active canonical owner。
- `pyproject.toml`、lockfile、migration chain、共享测试 bootstrap、Composition Root 与 active canonical docs 继续服从 [AGENTS.md](../AGENTS.md) 的 single-writer 规则。
- GSD 自动生成内容若超出 Task Packet allowlist，视为 `BLOCK`；立即停止并保留现场，不以事后删改掩盖越界。

Stock GSD 1.38.3 的 Worktree / lifecycle 模型与本项目不兼容，因此实际写入执行固定为：

1. Integrator 在任何 workflow 外，按精确 Task Packet 预建一个 Worktree 和一个 feature branch。
2. Codex Agent 只在该 Worktree 内实现 Task Packet；可以与 ownership 不重叠的其他 Agent 并行。
3. Agent 完成 precheck、实现、postcheck 和 handoff，只向 Task Packet 指定的 remote / head branch push。
4. Feature branch 创建 draft PR 到 Task Packet 指定的 integration branch。
5. Integrator 串行 review、重验与合并；后续分支针对新的 exact integration head 重新验证。

`.planning/config.json` 的 `parallelization=false` 与 `workflow.use_worktrees=false` **只关闭 GSD 自己的并行和 Worktree 管理**。它们不关闭 Codex 多 Agent，也不禁止 Integrator 在 workflow 外预建隔离 Worktree。

## 3. Task Packet 硬门禁

一个 GSD Plan 必须且只能映射到一个精确 Task Packet。Packet 可以包含多个原子 task，但不得跨 repository、branch、Worktree、writer 或 ownership boundary。

每个写入 Task Packet 必须显式包含：

- `repository`、`remote`、`head_branch`、`base_branch`、精确 `base_sha` 和 `worktree_id`；
- `owned_files` 精确 allowlist 与 `forbidden_files`；
- `canonical_inputs`、`dependencies`、`required_checks` 及预期结果；
- `done_when`、`handoff_to` 与 `handoff_format`；
- `contract_changes`、`security_impact`、`eval_impact` 与 `rollback`。

启动前必须逐字段记录实际值。没有依赖、禁止文件、契约变化或某类影响时也必须显式写 `NONE`；不得留空、继承隐含默认值或由 Agent 猜测。同一 Wave 内一个文件只有一个 writer。

所有写入型 specialized workflow 还必须执行 containment check：

- precheck：精确 `base_sha`、当前 head、branch、clean state、allowlist 和禁止文件；
- adapter precheck：所需 GSD agent role 必须在当前 Codex collaboration runtime 中真实可用；SDK 的本地 agent-file 探测不能替代该检查，缺失 role 时为 `BLOCK`；
- postcheck：相对 base 的全部 changed files、全部 commits、当前 head 与预期输出；
- 任一 scope drift、非预期 commit 或禁止文件变化都标记 `BLOCK`，不得 push；
- GSD 永远没有创建、合并、清理或 `--force` 操作项目 Worktree 的授权。

## 4. Severity Mapping 与处置

| GSD / Review 输出 | 项目严重度 | 处置 |
|---|---|---|
| Import `[BLOCKER]` | `BLOCK` | 禁止写 Plan、执行或合并；先完成 owner 裁决 |
| Import `[WARNING]` | `HIGH` 或 `MEDIUM` | 停止 import；Integrator 先分类并记录影响，只有用户显式批准后才能继续，不得自动批准 |
| Code review `CRITICAL` | `BLOCK` | 禁止 merge / release；必须修复并重新 exact-head review |
| GSD `WARNING` | Integrator 显式分类为 `HIGH` 或 `MEDIUM` | 不得静默降级；记录依据、owner 与 resolution |
| `HIGH` | High-risk gate failure | 修复或由 canonical owner 显式裁决；未关闭前不得 release |
| `MEDIUM` | Required resolution | 修复、补测或记录有证据的风险接受；不得遗漏 |
| `INFO` | `LOW / INFO` | 记录为非阻断建议，不得伪装成已修复 |

任何安全不变量、Critical failure、身份 / 资源归属、Evidence、确认、幂等或 `RESULT_UNKNOWN` 违规，无论工具标签为何，均至少按 `BLOCK` 处理。

## 5. GitHub / Worktree Mapping

| GSD 对象 | GitHub / Codex 对象 |
|---|---|
| Phase | `integration/e2e01-thin` 上的一个可验证阶段 |
| Plan | 一个精确 Task Packet |
| Wave | 一组 ownership 不重叠、由 Integrator 预建的独立 Worktree |
| Executor | 只写 Task Packet feature branch 的 Codex Agent |
| Review / Verification | GitHub exact-head review、机械检查与证据索引 |
| Release | 显式 GitHub feature → integration 与 integration → `main` PR |

执行规则：

1. Feature branch 只 push 到 Task Packet 指定的 repository / head branch。
2. Feature PR 先以 draft PR 指向 Task Packet 指定的 integration branch。
3. Integrator 逐个集成；每次 merge 后，下一个分支针对最新 integration head 重验并取得新的 exact-head review。
4. 完整 phase gate 通过后，显式使用 `head=integration/e2e01-thin`、`base=main` 创建 release PR。
5. 禁止直接 push `main` 或 active integration branch；GSD `branching_strategy=none` 不提供例外。
6. 不调用 stock `gsd-ship`：它的单一 base 模型不能表达本项目 feature → integration 与 integration → `main` 两级 PR。

## 6. Phase Post-execution Quality Gate

以下是 Phase Plans 全部执行并串行集成后的质量门禁，**不是额外 Plan，也不计入 Plan count**：

```text
exact-integration-SHA code review artifact
→ dedicated fix PR（有 finding 时，修复后重复 review）
→ dedicated validation PR（需要补缺时）
→ Eval / Security audit（满足前置 contract 时）
→ UAT artifact
→ canonical lifecycle owner update
→ Integrator 手工同步 derived Requirements / Roadmap / State
→ 显式 integration → main GitHub PR
```

- `gsd-code-review` 只能在以 exact integration SHA 创建的只读 review-artifact Worktree 中，以 `--files=<exact list>` 运行；唯一允许写入的是对应 Phase 的 `REVIEW.md`。它不得修改源码、共享状态或其他 artifact。
- `gsd-code-review-fix` 仅在 Integrator 预建的 dedicated fix Worktree / feature branch 中条件使用，并服从第 3 节 precheck / postcheck；发现 scope drift 时 `BLOCK` 且不 push。
- `gsd-validate-phase` 仅在 Integrator 预建的 dedicated validation Worktree / feature branch 中条件使用；测试或验证补缺必须作为独立 Task Packet / PR，不能直接修改 integration。
- `gsd-eval-review` 只有在派生 AI / Eval mapping 明确引用 [canonical Eval owner](../docs/evaluation/agent-evaluation-strategy.md) 后才构成 gate；该 mapping 必须是 `DERIVED / NON_NORMATIVE`，不得创造第二套 Eval 语义。
- `gsd-secure-phase` 必须以完整 `<threat_model>` 映射 [AGENTS.md](../AGENTS.md) 的身份、资源归属、最小披露、Evidence、确认、ActionPolicy、幂等与 `RESULT_UNKNOWN` 等安全不变量。零条 threat 不构成通过。
- `gsd-verify-work` 只生成会话式 UAT artifact；必须在任何 gap、transition 或 execute 路由前停止。它不能替代 canonical 自动化命令、Trajectory / E2E Eval 或 GitHub review。
- 质量门禁完成后，先由 [Coverage Matrix](../docs/evaluation/p0-eval-coverage-matrix.md) canonical owner 根据硬证据更新 Case lifecycle；随后 Integrator 手工同步派生 Requirements / Roadmap / State。
- 禁止 `phase.complete`、`requirements.mark-complete`、`roadmap.update-plan-progress` 及其他自动 lifecycle mutation。
- release 只使用显式 GitHub head / base PR；不调用 `gsd-ship`。

## 7. Evidence 与工具健康纪律

以下才是完成结论的硬证据：

- 当前源码与精确 commit / tree；
- canonical 命令、focused tests、migration、Trajectory / E2E Eval 的实际输出；
- 文件 allowlist 与 `git diff --check`；
- 独立 Reviewer 对精确 head SHA 的结果和已解决 findings；
- GitHub PR、conversation resolution 与 merge commit。

GSD Roadmap、State、Plan、Summary、Review、UAT 或 Verification 文档只索引证据，不能自我证明“已实现 / 已验证 / 可运行”。

GSD 健康必须同时读取两个表面，并保留原始分类：

- CJS `validate health --raw`；
- SDK `query validate.health`。

两者 warning code 或对象模型不一致时标为 `OPEN / TOOL_SURFACE_DRIFT`，不得把其中一个结果改写成整体 healthy。`--repair`、`--force` 或 Worktree 删除必须有独立显式授权；本 activation 没有该授权。

`gsd-sdk query init.phase-op` 的本地 agent-file 探测与 Codex collaboration role registry 是两个不同表面。每次 conditional workflow 启动前都必须同时确认 `phase_found`、phase path / artifact prerequisites 和所需 Codex role；不得因 SDK 返回 phase metadata 就推断执行 Agent 已可用。

## 8. Workflow Matrix

| 分类 | Workflow / API | 当前策略 |
|---|---|---|
| Safe read-only | `gsd-progress` | 只读查看；关闭 / 拒绝任何自动 next-route |
| Safe read-only | `gsd-health` | 同时读取 CJS 与 SDK surface；不运行 `--repair` / `--force` |
| Conditional planning artifact | `gsd-import` | 只在 Integrator 预建 planning-artifact Worktree / branch；显式 manifest、owner mapping、零未裁决 blocker / warning；任何 warning 必须由用户显式批准；一个 Plan = 一个 Task Packet；postcheck 必须证明只更新一个既有 Roadmap slot、无重复 Plan、无未授权 lifecycle 变化 |
| Conditional planning artifact | `gsd-plan-phase` | 只在 scoped canonical contract 已存在时，于预建 planning-artifact Worktree / branch 生成；独立 review 后再合并 |
| Conditional review artifact | `gsd-code-review` | exact-integration-SHA review-artifact Worktree + exact `--files`；只写 Phase `REVIEW.md` |
| Conditional fix | `gsd-code-review-fix` | 预建 dedicated fix Worktree / branch；精确 Task Packet 与 containment check |
| Conditional validation | `gsd-validate-phase` | 预建 dedicated validation Worktree / branch；补缺走独立 PR |
| Conditional Eval audit | `gsd-eval-review` | 先有引用 canonical Eval owner 的派生 mapping；否则不构成 gate |
| Conditional security audit | `gsd-secure-phase` | 完整 `<threat_model>` 映射安全不变量；zero-threat 不通过 |
| Conditional UAT | `gsd-verify-work` | 只产 UAT artifact；在 gap / transition / execute route 前停止 |
| Disabled | `gsd-execute-phase` | 不运行；stock workflow 会枚举、合并并可能以 `--force` 清理所有非当前 Worktree，还会提前推进 phase lifecycle |
| Disabled | `phase.complete` | 不运行；Phase 完成必须等待 post-execution quality gate 与 canonical lifecycle owner |
| Disabled | `requirements.mark-complete` | 不运行；canonical Case lifecycle 不能由派生 checkbox 改写 |
| Disabled | `roadmap.update-plan-progress` | 不运行；Integrator 基于 Summary、PR 与硬证据手工同步 |
| Disabled | `gsd-ship` | 不运行；不能表达两级 PR 模型 |
| Disabled | `gsd-autonomous`, `gsd-phase-autopilot` | 不运行；会绕过 owner、Task Packet、PR 或交互 gate |
| Disabled | `gsd-new-project`, `gsd-new-milestone` | 当前 P0 不运行；仓库已有 canonical 项目与 milestone 定义 |
| Disabled | 自动 lifecycle mutations | 不运行任何自动 phase / requirement / roadmap transition |

通用 `gsd-ingest-docs` 也保持禁用，除非另有显式 owner manifest、blocker conflict review 与独立批准；不得用通用文档优先级覆盖 specialized owner。

## 9. 为什么 stock Execute / Ship 被禁用

GSD 1.38.3 的 stock `gsd-execute-phase` 会管理其视野内的非当前 Worktree，包括枚举、合并、清理以及在路径上使用 `--force`；同时会调用 `roadmap.update-plan-progress` 和 `phase.complete`。这与本项目“每个 Task Packet 一个预建 Worktree、Integrator 串行合并、质量 gate 后才更新 lifecycle”的规则冲突。

因此 `parallelization=false` 与 `workflow.use_worktrees=false` 是防误触控制，而不是执行授权。实际写入由 Codex Agent 在 Integrator 预建 Worktree 中完成；GSD 只提供受控 planning / review / validation artifact。

Stock `gsd-ship` 只有单一 base 概念，不能同时表达 feature → integration 和 integration → `main`。所有 feature / release PR 必须显式给出 GitHub repository、head 与 base。

## 10. Rollback

- Activation merge 前：关闭 PR，并按用户 / Integrator 的显式决定回收该 feature branch / Worktree；integration 无变化。
- Activation merge 后：使用普通 revert PR 撤销 activation commit；不得 destructive reset、`--force` cleanup 或直接删除 canonical 文件。
- 发生 owner 冲突、状态损坏、scope drift 或越界写入时：暂停 GSD 写入、保留 diff / log / commit 证据、禁止 push，由 Integrator 完成 impact scan。
- 修复期间继续使用既有 Task Packet + Integrator 预建 Worktree + Codex Agent + GitHub PR 流程；不授权 GSD 创建、合并或清理 Worktree。
