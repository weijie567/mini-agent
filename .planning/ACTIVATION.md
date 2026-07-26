# Mini Agent｜GSD Activation Record

> **DERIVED / NON_NORMATIVE**
> 本记录只描述 GSD 派生层的激活边界与证据，不拥有产品、架构、契约、Eval 语义或 Case 生命周期。Activation 只有在独立 PR 的精确 head review 为 `PASS` 且合并到 `integration/e2e01-thin` 后才生效。

## 1. Activation Identity

| 项目 | 值 |
|---|---|
| 状态 | `IN_PROGRESS / NOT_EFFECTIVE_UNTIL_MERGED` |
| GSD version | `1.38.3` |
| Activation branch | `codex/gsd-activation` |
| Base branch | `integration/e2e01-thin` |
| Exact base SHA | `85eb2a7fc4cc131e67e44dbba132b526e36ae6a3` |
| Base evidence | [PR #9](https://github.com/weijie567/mini-agent/pull/9) 的 W2.0 contract-freeze merge |
| Governance | [GOVERNANCE.md](GOVERNANCE.md) |

## 2. 目标与非目标

目标：

- 为既有项目建立派生的 Project / Requirements / Roadmap / State。
- 显式映射 canonical owner，阻断跨 owner 冲突。
- 把 GSD Plan / Wave / executor / review 映射到现有 Task Packet、Worktree 与 GitHub PR 流程。
- 为后续 code review、fix、validation、Eval / Security audit、UAT 与 ship 提供受控执行顺序。

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
| 共享状态 writer | `CONFIRMED` | State / Roadmap / cross-phase index 仅 Integrator 单写 |
| Git 分支模型 | `CONFIRMED` | `branching_strategy=none`；现有 Task Packet / Worktree / PR 继续拥有写入隔离 |
| 自动推进 / UI 生成 | `CONFIRMED: DISABLED` | `auto_advance=false`、`ui_phase=false` |
| 未裁决 conflict | `NOT_FOUND` | 仍需独立 Reviewer 对 activation exact head 复核 |
| Cross-file consumer alignment | `CONFIRMED` | [README.md](../README.md)、AGENTS 与实施计划均使用 activation 前暂停、merge 后受控使用的长期表述 |

## 5. 隔离 Rehearsal 与实际证据

本 activation 在独立 worktree `/Users/ming/projects/mini-agent-worktrees/gsd-activation` 中手工建立；未运行任何会批量生成或覆盖项目状态的 GSD workflow。

| 检查 | 状态 | 实际结果 |
|---|---|---|
| Worktree / branch / exact base | `CONFIRMED` | `codex/gsd-activation` at `85eb2a7fc4cc131e67e44dbba132b526e36ae6a3` |
| GSD installed version | `CONFIRMED` | `/Users/ming/.codex/get-shit-done/VERSION` 为 `1.38.3` |
| JSON parse | `CONFIRMED` | `jq empty .planning/config.json` 通过 |
| GSD config supported-key check | `CONFIRMED` | 对 GSD `VALID_CONFIG_KEYS` 检查 32 个 leaf keys，无 unknown key；关键值断言通过 |
| Roadmap / Requirements shape | `CONFIRMED` | 6 个连续 Phase；16 个唯一 requirement；只有 Phase 1 active |
| Markdown links / referenced paths | `CONFIRMED` | 9 个变更 Markdown 中 76 个本地引用均存在 |
| `STATE.md` size | `CONFIRMED` | 52 行，小于 100 行 |
| `git diff --check` | `CONFIRMED` | tracked diff、7 个新文件 no-index check 与 trailing-whitespace scan 均通过 |
| Exact allowlist | `CONFIRMED` | 实际 10 个文件，精确等于第 3 节 allowlist |
| GSD planning health | `MEDIUM / ACCEPTED_FOR_ACTIVATION` | Integrator 已裁决：0 errors、`repairable_count=0`；6 个 `W017` 是已合并 PR 的审计 Worktree，不影响 activation 内容或 planning 结构；禁止自动或 `--force` 删除 |
| Independent exact-head review | `PENDING` | commit 后由 Reviewer 执行 |
| GitHub PR merge | `PENDING` | review 与 checks 通过后由 Integrator 执行 |

任何 `PENDING` 项不得提前描述为通过。

Follow-up gate：派发 W2.0b 前，Integrator 必须逐个只读验证上述 6 个 Worktree 的 clean 状态、branch、PR 与 merge 证据，再通过显式 Task Packet 决策保留或回收；不得把 GSD health 的通用建议直接当成删除授权。

## 6. Activation 后第一个串行 Prerequisite

Activation merge 后，不直接启动 W2 三路并行。Integrator 必须先用 activation merge SHA 导入并派发 `W2.0b Core RecordSchema`：

允许写入：

- `src/mini_agent/core/common.py`
- `src/mini_agent/core/record_schema.py`
- `tests/component/core/test_record_schema_contract.py`
- `tests/component/application/test_runtime_record_schema_coverage.py`

禁止写入：

- W2.0 已冻结的 `src/mini_agent/application/records.py` 与 `src/mini_agent/application/ports.py`；
- Infrastructure、Alembic、`pyproject.toml`、`uv.lock`；
- active canonical docs 与共享 `.planning` 文件。

该 prerequisite 只建立 Core-owned `RecordSchemaSpec` / strict JSON persistence codec 边界和覆盖测试；不得把全局 `ContractModel` 改为 `strict=True`，也不得复制 Application DTO。其 Task Packet、Plan 与最终语义仍需根据 canonical owner 和 exact-head review 裁决。

只有该 PR exact-head review 为 `PASS`、验证通过并合并后，W2 Runtime / Infra / Eval 才能从同一个新 integration SHA 创建三个独立 Worktree。

## 7. Rollback

- Merge 前：关闭 activation PR，移除 `codex/gsd-activation` worktree / branch；`integration/e2e01-thin` 不受影响。
- Merge 后：创建 revert PR 撤销 activation commit，并在 [STATE.md](STATE.md) 标记 GSD 写入暂停；不得使用 destructive reset。
- 若某个 GSD workflow 越过 allowlist 或试图覆盖 canonical owner：立即停止、保存 diff / log、标记 `BLOCK`，由 Integrator 做 cross-file impact scan。

## 8. Exit Criteria

- [x] JSON、supported keys、路径、术语、diff 与 allowlist 检查全部有实际通过证据。
- [ ] 独立 Reviewer 对 activation 精确 head SHA 给出 `PASS`。
- [ ] Activation PR 合并到 `integration/e2e01-thin`。
- [ ] Integrator 使用 activation merge SHA 更新共享 State，并创建首个 RecordSchema import manifest。

Exit Criteria 未全部满足前，依赖 Roadmap / Phase state 的 GSD 写入 workflow 保持暂停。
