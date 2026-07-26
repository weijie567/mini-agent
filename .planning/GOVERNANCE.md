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

## 2. 写入 Ownership

- `.planning/STATE.md`、`.planning/ROADMAP.md`、跨 phase index 和 shared progress 仅由 Integrator 在 integration-owned checkout 串行写入。
- Plan-scoped artifact 只有在 Task Packet 明确分配路径、branch 和 writer 时才可由 executor 写入。
- Feature Worktree 不得各自推进共享 State，也不得直接修改 active canonical owner。
- `pyproject.toml`、lockfile、migration chain、共享测试 bootstrap、Composition Root 与 active canonical docs 继续服从 [AGENTS.md](../AGENTS.md) 的 single-writer 规则。
- GSD 自动生成内容若超出 Task Packet allowlist，视为 `BLOCK`；必须停止，不以事后删改掩盖越界。

## 3. Task Packet 硬门禁

每个写入 Task Packet 必须显式包含：

- `repository`、`remote`、`head_branch`、`base_branch`、精确 `base_sha` 和 `worktree_id`；
- `owned_files` 精确 allowlist 与 `forbidden_files`；
- canonical inputs、依赖、验证命令及预期结果；
- `done_when`、handoff owner 与 handoff format；
- 契约变化声明、安全 / Eval 影响与回滚方式。

同一 Wave 内一个文件只有一个 writer。缺失字段时不派发；不存在的依赖或禁止文件也必须写 `NONE`，不得猜测。

## 4. Severity Mapping 与处置

| GSD / Review 输出 | 项目严重度 | 处置 |
|---|---|---|
| Import `[BLOCKER]` | `BLOCK` | 禁止写 Plan、执行或合并；先完成 owner 裁决 |
| Code review `CRITICAL` | `BLOCK` | 禁止 merge / ship；必须修复并重新 exact-head review |
| GSD `WARNING` | Integrator 显式分类为 `HIGH` 或 `MEDIUM` | 不得静默降级；记录依据、owner 与 resolution |
| `HIGH` | High-risk gate failure | 修复或由 canonical owner 显式裁决；未关闭前不得 ship |
| `MEDIUM` | Required resolution | 修复、补测或记录有证据的风险接受；不得遗漏 |
| `INFO` | `LOW / INFO` | 记录为非阻断建议，不得伪装成已修复 |

任何安全不变量、Critical failure、身份 / 资源归属、Evidence、确认、幂等或 `RESULT_UNKNOWN` 违规，无论工具标签为何，均至少按 `BLOCK` 处理。

## 5. GitHub / Worktree Mapping

| GSD 对象 | GitHub / Codex 对象 |
|---|---|
| Phase | `integration/e2e01-thin` 上的一个可验证阶段 |
| Plan | 一个精确 Task Packet |
| Wave | 一组文件 ownership 不重叠的独立 Worktree |
| Executor | 仅写 feature branch 的 Codex Agent |
| Review / Verification | GitHub exact-head review、机械检查与证据索引 |
| Ship | integration branch → `main` PR |

执行规则：

1. Feature branch 只 push 到 Task Packet 指定的 repository / head branch。
2. Feature PR 先以 draft PR 指向 `integration/e2e01-thin`。
3. Integrator 逐个集成；每次 merge 后，下一个分支针对最新 integration head 重验并取得新的 exact-head review。
4. 完整 phase gate 通过后，才从 integration branch 创建 PR 到 `main`。
5. 禁止直接 push `main` 或 active integration branch；GSD `branching_strategy=none` 不提供绕过该规则的例外。

## 6. Phase Quality Pipeline

适用顺序固定为：

```text
gsd-code-review
→ gsd-code-review-fix（有 finding 时，修复后重复 review）
→ gsd-validate-phase
→ gsd-eval-review / gsd-secure-phase（按 Phase 风险适用）
→ gsd-verify-work
→ gsd-ship
```

- `gsd-code-review-fix` 只能在专用 Worktree、专用 feature branch、精确 allowlist 与 PR 中运行；不得直接修改 integration branch。
- `gsd-validate-phase` 补齐测试或验证缺口时，同样必须落入专用 Task Packet / PR。
- `gsd-eval-review` 只审计 canonical Eval owner 已定义的覆盖，不生成第二套 Eval 语义；需要 `AI-SPEC.md` 时必须先走独立、派生、`NON_NORMATIVE` mapping PR。
- `gsd-secure-phase` 只验证既有 threat / safety contract，不自行创造产品授权语义。
- `gsd-verify-work` 是会话式 UAT 证据，不能替代 canonical 自动化命令、Trajectory / E2E Eval 或 GitHub review。
- `gsd-ship` 只在前序 gate 全部通过且 exact integration head 未变化时准备 PR；merge 决策仍由 Integrator / 用户拥有。

## 7. Evidence 纪律

以下才是完成结论的硬证据：

- 当前源码与精确 commit / tree；
- canonical 命令、focused tests、migration、Trajectory / E2E Eval 的实际输出；
- 文件 allowlist 与 `git diff --check`；
- 独立 Reviewer 对精确 head SHA 的结果和已解决 findings；
- GitHub PR、conversation resolution 与 merge commit。

GSD Roadmap、State、Plan、Summary、Review、UAT 或 Verification 文档只索引证据，不能自我证明“已实现 / 已验证 / 可运行”。

## 8. Workflow Policy

### Activation 合并后允许

- `gsd-import`：只接受显式 manifest、owner mapping、零未裁决 blocker / warning；一个 Task Packet 对应一个 Plan。
- `gsd-plan-phase`：只用于 canonical scope 已明确但尚未拆 Plan 的 Phase。
- `gsd-execute-phase`：只按已批准 Wave 执行，写入 executor 必须使用独立 Worktree / branch。
- `gsd-code-review`、`gsd-code-review-fix`、`gsd-validate-phase`、`gsd-eval-review`、`gsd-secure-phase`、`gsd-verify-work`、`gsd-ship`：按第 6 节顺序和适用范围执行。
- `gsd-progress`、`gsd-health`：用于派生状态检查，不改变 canonical 语义。

### 当前禁止或需新决策

- `gsd-new-project`：禁止用于当前仓库；会重建已有项目定义。
- `gsd-new-milestone`：当前 P0 禁止；只有用户和 canonical owner 明确进入独立新 milestone 后另行激活。
- `gsd-autonomous` / `gsd-phase-autopilot`：当前第一切片禁止，不能绕过 owner、PR 或交互 gate。
- 通用 `gsd-ingest-docs`：没有显式 owner manifest 与 blocker conflict review 时禁止；不得使用通用文档优先级覆盖 specialized owner。
- 任何会自动更新 active canonical docs、Coverage Matrix lifecycle、`main` / integration branch 或共享 State 的 executor：禁止。

## 9. Rollback

- Activation merge 前：关闭 PR 并移除该 feature worktree / branch 即可，integration 无变化。
- Activation merge 后：使用普通 revert PR 撤销 activation commit；不得 destructive reset 或直接删除 canonical 文件。
- 发生 owner 冲突、状态损坏或越界写入时：暂停 GSD 写入、保留证据、由 Integrator 完成 impact scan；修复前继续使用既有 Task Packet + Worktree + PR 流程。
