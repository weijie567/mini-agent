# Mini Agent｜GSD Activation Record

> **DERIVED / NON_NORMATIVE**
> 本记录只描述 GSD 派生层的激活边界与证据，不拥有产品、架构、契约、Eval 语义或 Case 生命周期。Activation 已在独立 PR 的精确 head review 为 `PASS` 且合并到 `integration/e2e01-thin` 后生效。

## 1. Activation Identity

| 项目 | 值 |
|---|---|
| 状态 | `COMPLETE / EFFECTIVE` |
| GSD version | `1.38.3` |
| GSD SDK version | `gsd-sdk v0.1.0` |
| Activation branch | `codex/gsd-activation` |
| Base branch | `integration/e2e01-thin` |
| Exact base SHA | `85eb2a7fc4cc131e67e44dbba132b526e36ae6a3` |
| Branch relation | activation branch **forked from** exact base SHA；该 base 不是当前 activation head |
| Rejected candidate / review heads | `1e6999cbc60caa8f57d065ff4536dd238d48a911`, `f7408129b46f5a5bcaa0d4959e7b1cfe07b5e72d`, `b659c33d0670c57c1fc987e9487f6bd6165eb72c`, `f48461c9912d8240a8dba537087bffda08041f52`, `9565275ab24673350758d3d145e1f71b0450cd9c` |
| Reviewed feature head | `957cabd6b31dd2156848acd515d2e8dc3d19bd50` |
| Reviewed feature tree | `90b5d8db4d90dd8452660f5317c745d15103cbc4` |
| Activation PR / merge | [PR #10](https://github.com/weijie567/mini-agent/pull/10)；squash merge `624475681847be5a8e463e32dafd28a0483b213b` |
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
| persistence schema/version contract | `OPEN / PROPOSAL_ONLY` | Thin Slice Spec 只确认写入前经 Pydantic serialization 并保存 schema version；完整 owner、API、decode 与 unknown-version 行为等待 01-01 Project Direction → 01-02 Memory → 01-03 Thin Slice owner chain |
| Cross-file consumer alignment | `CONFIRMED_ON_REVIEWED_FEATURE_TREE` | [README.md](../README.md)、AGENTS 与实施计划在 reviewed feature tree 上统一 parser syntax、stock workflow、owner decision、Task Packet 与 lifecycle 边界 |

## 5. 隔离 Rehearsal 与实际证据

本 activation 在独立 worktree `/Users/ming/projects/mini-agent-worktrees/gsd-activation` 中手工建立；未运行任何会批量生成或覆盖项目状态的 GSD workflow。

| 检查 | 状态 | 实际结果 |
|---|---|---|
| Worktree / branch / exact base | `CONFIRMED` | `codex/gsd-activation` 从 `85eb2a7fc4cc131e67e44dbba132b526e36ae6a3` fork；`1e6999c...`、`f740812...`、`b659c33...`、`f48461c...` 为 blocked review heads，`9565275...` 因 time-sensitive W017 证据漂移在 review 前被本地 validation 拒绝 |
| GSD installed version | `CONFIRMED` | `/Users/ming/.codex/get-shit-done/VERSION` 为 `1.38.3` |
| GSD SDK version | `CONFIRMED` | `gsd-sdk --version` → `gsd-sdk v0.1.0` |
| Evidence capture | `HISTORICAL_CAPTURE + FINAL_EXACT_HEAD_CONFIRMED` | remediation tree capture 为 `2026-07-26T10:42:09Z` UTC；随后在 reviewed feature head `957cabd6...` 重跑 final checks |
| CJS health surface | `DEGRADED / TIME_SENSITIVE_COUNT` | `node /Users/ming/.codex/get-shit-done/bin/gsd-tools.cjs validate health --raw` → 本次 7×`W017`（6 个既有 W1 / W2 audit Worktree + 正在工作的 activation Worktree 被目录 mtime heuristic 判为 stale）、`errors=[]`、`repairable=0`；数量随时间变化，不作为稳定 gate |
| SDK health surface | `DEGRADED` | `gsd-sdk query validate.health` → 6×`W006`（Phase 1–6 directory 尚未创建）、`errors=[]`、`repairable=0` |
| SDK Phase 1 init surface | `OPEN / ADAPTER_SURFACE_DIFFERENCE` | `gsd-sdk query init.phase-op 1` 可解析 Phase 1 / State / Roadmap，但 `phase_dir=null`（import 前预期）且本地 agent-file 探测为 false；conditional workflow 还必须独立确认所需 Codex collaboration role 可用 |
| Dual-surface disposition | `OPEN / TOOL_SURFACE_DRIFT / ACCEPTED_FOR_ACTIVATION_WITH_CONTROLS` | warning code / object surface 不一致；未来创建 Phase 1 artifact directory 预计只减少一个 `W006`，不得声称整体 healthy |
| Repair / force | `NOT_RUN` | 未运行 `--repair` 或 `--force`；health 输出不构成 Worktree 删除授权 |
| JSON / supported keys / State / parser / review-scope / shape / links / diff / allowlist | `CONFIRMED_ON_REVIEWED_FEATURE_HEAD` | `957cabd6...` 上 `jq`、32 leaf keys / 0 unknown、6 个 Phase requirements、Success Criteria 4/3/3/3/3/3、literal review-scope requested=accepted=unique、valid/invalid path cases、6 Phase / 6 Phase-1 slots / 16 requirements、82 local links / 0 missing、84-line State、精确 10-file allowlist 与 `git diff --check` 均通过；未调用 paused stock workflow |
| Independent exact-head review | `PASS` | owner review 与 GSD compatibility review 均对 `957cabd6...` 给出 `PASS`，无 `CRITICAL / HIGH / MEDIUM` finding |
| GitHub PR merge | `CONFIRMED` | [PR #10](https://github.com/weijie567/mini-agent/pull/10) 已 squash merge；merge commit `624475681847be5a8e463e32dafd28a0483b213b` 的 tree 与 reviewed feature tree `90b5d8...` 完全相同 |

上述 activation 证据只证明派生治理层已生效，不证明 Phase 1 或任何运行时功能已经实现。

## 6. Activation 后第一个串行 Decision Gate

Activation merge 后不直接 import 或执行 persistence implementation，也不启动 W2 三路并行。独立 Plan Checker 进一步确认：一个 Task Packet 不得同时写 Project Direction、Memory、Tool、Eval 与 Thin Slice 多个 ownership boundary。因此首个串行 owner chain 是 01-01 → 01-02 → 01-03：

1. `CONFIRMED`：Integrator 已在 GSD workflow 外，从 activation merge SHA `6244756...` 预建 01-01 Worktree / feature branch `codex/e2e01-01-schema-owner-alignment`；其唯一 owned file 是 `PROJECT_DIRECTION.md`。
2. 01-01 只裁决 project-wide semantic/source/Port/adapter ownership、版本维度与 TraceEvent shared structure owner；不改其他 canonical owner。
3. 01-01 exact-head PR 合并后，Integrator 才从新 integration SHA 生成单 owner 的 01-02 Memory decode/recovery/migration contract。
4. 01-02 合并后，才生成只写 Thin Slice Spec 的 01-03 scoped 17-item minimum-persistence mapping；17 项严格派生自 Thin Slice Spec 第 10.1 节当前最低持久化集合（其中包含 `ModelVisibleToolsetArtifact`），不得把源码中的辅助模型或命令计入并误称为 20 条 Record。Tool / Eval owner 的现有语义通过引用消费，除非后续独立 owner Packet 证明必须演进。
5. 当前唯一 `CONFIRMED` 的 scoped 要求仍是：JSON persistence projection 在写入前经过 Pydantic serialization，并保存 schema version。`RecordSchemaSpec`、registry、strict decoder、unknown-version fail-closed 和固定 record-code allowlist 在对应 owner PR 合并前均为 `OPEN / PROPOSAL_ONLY`。
6. 只有 01-03 exact-head PR 合并后才生成 01-04 implementation；01-04 合并后还必须通过 Graphify freshness与 source / dependency audit。若 audit发现 shared contract gap，先建立单 owner dependency Packet并合并；只有 blocker关闭后，才从同一个新 integration SHA预建 Runtime / Infra / Eval三个 ownership不重叠的 Worktree。

Stock `gsd-import`、`gsd-plan-phase` 与 `gsd-execute-phase` 不参与上述实现。GSD planner / checker 角色可只读提供 Plan 建议；Integrator 在预建的 dedicated planning-status Worktree / branch 中单写最终 artifact。

## 7. Rollback

- Merge 前：关闭 activation PR；是否回收 `codex/gsd-activation` branch / Worktree 由用户或 Integrator 显式决定，`integration/e2e01-thin` 不受影响。
- Merge 后：创建 revert PR 撤销 activation commit，并在 [STATE.md](STATE.md) 标记 GSD 写入暂停；不得使用 destructive reset。
- 若某个 GSD workflow 越过 allowlist、出现 scope drift 或试图覆盖 canonical owner：立即停止、保存 diff / log、标记 `BLOCK`、不得 push，由 Integrator 做 cross-file impact scan。
- GSD 不获授权创建、合并、`--force` 清理或删除项目 Worktree。

## 8. Exit Criteria

- [x] 从 Git ref / GitHub PR head 解析的 final remediation exact head，其 JSON、32-key、State load、Roadmap parser、双 health、路径、术语、diff 与精确 allowlist检查全部有实际通过证据。
- [x] 独立 Reviewer 对 activation 精确 head SHA 给出 `PASS`。
- [x] Activation PR 合并到 `integration/e2e01-thin`。
- [x] Integrator 使用 activation merge SHA 创建 01-01 Project Direction owner Task Packet Worktree / branch；最终 Task Packet 由本次独立 planning-status PR 建立。

Activation Exit Criteria 已全部满足。后续 GSD 写入仍只允许通过 [GOVERNANCE.md](GOVERNANCE.md) 定义的受控 adapter 与独立 PR；这不解除 stock workflow 禁令。
