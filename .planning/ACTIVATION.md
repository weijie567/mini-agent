# Mini Agent｜GSD Activation Record

> **DERIVED / NON_NORMATIVE**
> 本记录只描述 GSD 派生层的激活边界与证据，不拥有产品、架构、契约、Eval 语义或 Case 生命周期。Activation 只有在独立 PR 的精确 head review 为 `PASS` 且合并到 `integration/e2e01-thin` 后才生效。

## 1. Activation Identity

| 项目 | 值 |
|---|---|
| 状态 | `BLOCKED_REVIEW_SCOPE_REMEDIATION / PAUSED / NOT_EFFECTIVE` |
| GSD version | `1.38.3` |
| GSD SDK version | `gsd-sdk v0.1.0` |
| Activation branch | `codex/gsd-activation` |
| Base branch | `integration/e2e01-thin` |
| Exact base SHA | `85eb2a7fc4cc131e67e44dbba132b526e36ae6a3` |
| Branch relation | activation branch **forked from** exact base SHA；该 base 不是当前 activation head |
| Blocked review heads | `1e6999cbc60caa8f57d065ff4536dd238d48a911`, `f7408129b46f5a5bcaa0d4959e7b1cfe07b5e72d`, `b659c33d0670c57c1fc987e9487f6bd6165eb72c` |
| Current candidate head | 由 `git rev-parse HEAD` / GitHub PR head 在外部审查证据中解析；不在同一 commit 内容内自引用硬编码 |
| Base evidence | [PR #9](https://github.com/weijie567/mini-agent/pull/9) 的 W2.0 contract-freeze merge |
| Governance | [GOVERNANCE.md](GOVERNANCE.md) |

## 2. 目标与非目标

目标：

- 为既有项目建立派生的 Project / Requirements / Roadmap / State。
- 显式映射 canonical owner，阻断跨 owner 冲突。
- 把 GSD Plan / Wave / executor / review 映射到现有 Task Packet、Worktree 与 GitHub PR 流程。
- 为后续 code review、fix、validation、Eval / Security audit、UAT 与显式 GitHub release PR 提供受控执行顺序。

非目标：

- 不运行 `gsd-new-project` 或 `gsd-new-milestone` 重写当前 P0。
- 不生成第二套产品、架构、DTO / Port、RAG、Memory、Tool 或 Eval 语义。
- 不声称 Phase 1、HTTP、Harness、Trajectory / E2E、Qwen Baseline 或 P0 已实现。

## 3. Activation PR 精确 Allowlist

唯一允许写入：

- `.planning/config.json`
- `.planning/PROJECT.md`
- `.planning/REQUIREMENTS.md`
- `.planning/ROADMAP.md`
- `.planning/STATE.md`
- `.planning/GOVERNANCE.md`
- `.planning/ACTIVATION.md`
- `AGENTS.md`
- `README.md`
- `docs/implementation/e2e01-thin-slice-multi-agent-plan.md`

禁止修改：

- `src/**`、`tests/**`、`evals/**`；
- `pyproject.toml`、`uv.lock`、Compose、Alembic / migration；
- active business、architecture、implementation spec 与 Eval canonical owners；
- `main` 或 `integration/e2e01-thin` 的直接 branch state。

## 4. Owner Mapping 与 Conflict Review

完整 mapping 见 [GOVERNANCE.md §1](GOVERNANCE.md#1-owner-mapping-与冲突优先级)。

| 检查 | 结果 | 证据 / 处置 |
|---|---|---|
| 业务范围是否被 `.planning` 重定义 | `CONFIRMED: NO` | Roadmap 只引用业务 owner 与 Case ID |
| 架构 / DTO / Port / 状态机是否被重定义 | `CONFIRMED: NO` | Activation allowlist 禁止 source 与 canonical architecture owner |
| Eval 语义或 lifecycle 是否被 GSD 接管 | `CONFIRMED: NO` | `REQUIREMENTS.md` 明确 checkbox 不改变 lifecycle；`ai_integration_phase=false` |
| specialized owner 冲突优先级 | `CONFIRMED` | Governance 禁止 “newest wins”，冲突为 `BLOCK` |
| 共享状态 writer | `CONFIRMED` | State / Roadmap / Requirements / cross-phase index 仅由 Integrator 在 dedicated planning-status feature branch 单写并通过 PR 合并；不得直接写 integration |
| Git 分支模型 | `CONFIRMED` | `branching_strategy=none`；现有 Task Packet / Worktree / PR 继续拥有写入隔离 |
| GSD 自管并行 / Worktree | `CONFIRMED: DISABLED` | `parallelization=false`、`workflow.use_worktrees=false`；不影响 Integrator 预建 Worktree 的 Codex 多 Agent 并行 |
| 自动推进 / UI 生成 | `CONFIRMED: DISABLED` | `auto_advance=false`、`ui_phase=false` |
| stock planning / execute / verify / lifecycle / ship | `CONFIRMED: DISABLED` | 不运行 `gsd-import`、`gsd-plan-phase`、`gsd-execute-phase`、`gsd-verify-work`、`phase.complete`、`requirements.mark-complete`、`roadmap.update-plan-progress` 或 `gsd-ship` |
| persistence schema/version contract | `OPEN / PROPOSAL_ONLY` | Thin Slice Spec 只确认写入前经 Pydantic serialization 并保存 schema version；owner、API、decode 与 unknown-version 行为等待 01-01 alignment PR |
| Cross-file consumer alignment | `CONFIRMED_ON_COMPAT_REMEDIATION_WORKTREE` | [README.md](../README.md)、AGENTS 与实施计划已统一 parser syntax、stock workflow、owner decision、Task Packet 与 lifecycle 边界；commit 后仍需 final exact-head review |

## 5. 隔离 Rehearsal 与实际证据

本 activation 在独立 worktree `/Users/ming/projects/mini-agent-worktrees/gsd-activation` 中手工建立；未运行任何会批量生成或覆盖项目状态的 GSD workflow。

| 检查 | 状态 | 实际结果 |
|---|---|---|
| Worktree / branch / exact base | `CONFIRMED` | `codex/gsd-activation` 从 `85eb2a7fc4cc131e67e44dbba132b526e36ae6a3` fork；blocked review heads 为 `1e6999c...` 与 `f740812...` |
| GSD installed version | `CONFIRMED` | `/Users/ming/.codex/get-shit-done/VERSION` 为 `1.38.3` |
| GSD SDK version | `CONFIRMED` | `gsd-sdk --version` → `gsd-sdk v0.1.0` |
| Evidence captured at | `CONFIRMED_ON_REVIEW_SCOPE_REMEDIATION_TREE` | `2026-07-26T10:33:33Z` UTC；commit 后仍须对 exact head 重跑 |
| CJS health surface | `DEGRADED` | `node /Users/ming/.codex/get-shit-done/bin/gsd-tools.cjs validate health --raw` → 6×`W017`（既有 W1 / W2 audit Worktree）、`errors=[]`、`repairable=0` |
| SDK health surface | `DEGRADED` | `gsd-sdk query validate.health` → 6×`W006`（Phase 1–6 directory 尚未创建）、`errors=[]`、`repairable=0` |
| SDK Phase 1 init surface | `OPEN / ADAPTER_SURFACE_DIFFERENCE` | `gsd-sdk query init.phase-op 1` 可解析 Phase 1 / State / Roadmap，但 `phase_dir=null`（import 前预期）且本地 agent-file 探测为 false；conditional workflow 还必须独立确认所需 Codex collaboration role 可用 |
| Dual-surface disposition | `OPEN / TOOL_SURFACE_DRIFT / ACCEPTED_FOR_ACTIVATION_WITH_CONTROLS` | warning code / object surface 不一致；未来创建 Phase 1 artifact directory 预计只减少一个 `W006`，不得声称整体 healthy |
| Repair / force | `NOT_RUN` | 未运行 `--repair` 或 `--force`；health 输出不构成 Worktree 删除授权 |
| JSON / supported keys / State / parser / review-scope / shape / links / diff / allowlist | `CONFIRMED_ON_REVIEW_SCOPE_REMEDIATION_TREE / EXACT_HEAD_REVIEW_PENDING` | `jq` 通过；32 leaf keys / 0 unknown；State milestone=`v0.1`、status=`paused`；6 个 Phase 的 Requirements 均为非空 clean ID，Success Criteria 数量为 4/3/3/3/3/3；2-file review-scope rehearsal 为 requested=accepted=unique=transcript scope=`2`，无 skip 输出；6 Phase / 6 Phase-1 Plans / 16 requirements；82 个本地链接 / 0 missing；84-line State；相对 base 精确 10-file allowlist 与 `git diff --check` 通过。commit 后须对 exact head 重跑 |
| Independent exact-head review | `BLOCKED_ON_1e6999c_f740812_b659c33 / FINAL_PENDING` | `b659c33...` 的 compatibility review 为 `PASS`，owner review 因 path-skip token 与 stock 实际输出不一致而 `BLOCK`；新 remediation head 必须重新取得双 `PASS` |
| GitHub PR merge | `PENDING` | review 与 checks 通过后由 Integrator 执行 |

任何 `PENDING` 项不得提前描述为通过。

## 6. Activation 后第一个串行 Decision Gate

Activation merge 后不直接 import 或执行 W2.0b，也不启动 W2 三路并行。首个 Plan slot 是 `01-01 persistence schema/version canonical-owner decision`：

1. Integrator 在 GSD workflow 外，从 activation merge SHA 预建一个精确 Task Packet Worktree / feature branch。
2. 该 PR 对照 [Thin Slice Spec](../docs/implementation/e2e01-thin-slice-implementation-spec.md)、[PROJECT_DIRECTION.md](../PROJECT_DIRECTION.md) 与相关 active owner，裁决 Core / Application / Infra ownership、API 命名、decode / migration 责任以及 unknown-version 行为。
3. 当前唯一 `CONFIRMED` 的 scoped 要求是：JSON persistence projection 在写入前经过 Pydantic serialization，并保存 schema version。
4. `RecordSchemaSpec`、registry、strict decoder、unknown-version fail-closed 和固定 record-code allowlist 都是 `OPEN / PROPOSAL_ONLY`；activation 不得把它们描述成已决定 contract。
5. 只有 01-01 exact-head review、验证与 merge 完成后，Integrator 才能按裁决生成一对一的 `01-02 W2.0b` Task Packet / Plan。
6. 只有 01-02 exact-head PR 合并后，才从同一个新 integration SHA 预建 W2 Runtime / Infra / Eval 三个 ownership 不重叠的 Worktree。

Stock `gsd-import`、`gsd-plan-phase` 与 `gsd-execute-phase` 不参与上述实现。GSD planner / checker 角色可只读提供 Plan 建议；Integrator 在预建的 dedicated planning-status Worktree / branch 中单写最终 artifact。

## 7. Rollback

- Merge 前：关闭 activation PR；是否回收 `codex/gsd-activation` branch / Worktree 由用户或 Integrator 显式决定，`integration/e2e01-thin` 不受影响。
- Merge 后：创建 revert PR 撤销 activation commit，并在 [STATE.md](STATE.md) 标记 GSD 写入暂停；不得使用 destructive reset。
- 若某个 GSD workflow 越过 allowlist、出现 scope drift 或试图覆盖 canonical owner：立即停止、保存 diff / log、标记 `BLOCK`、不得 push，由 Integrator 做 cross-file impact scan。
- GSD 不获授权创建、合并、`--force` 清理或删除项目 Worktree。

## 8. Exit Criteria

- [ ] 从 Git ref / GitHub PR head 解析的 final remediation exact head，其 JSON、32-key、State load、Roadmap parser、双 health、路径、术语、diff 与精确 allowlist 检查全部有实际通过证据。
- [ ] 独立 Reviewer 对 activation 精确 head SHA 给出 `PASS`。
- [ ] Activation PR 合并到 `integration/e2e01-thin`。
- [ ] Integrator 使用 activation merge SHA 创建 01-01 persistence schema/version canonical-owner alignment Task Packet。

Exit Criteria 未全部满足前，依赖 Roadmap / Phase state 的 GSD 写入 workflow 保持暂停。
