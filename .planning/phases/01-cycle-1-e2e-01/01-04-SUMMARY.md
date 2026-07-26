---
phase: 01-cycle-1-e2e-01
plan: 04
subsystem: application
status: complete_evidence_indexed
completed_at: "2026-07-26T16:40:51Z"
requirements:
  - E2E01-01
  - E2E01-04
requirements_completed: []
execution_base: 9602fc18148b19c841889a8041daf10ccc5b8f1c
planning_merge: 390d615be8e4020008c45bce1feec6260e47d361
local_reviewed_head: 75d1d29c7a0580fe09e3c61ef6f820ec728e0586
published_head: 828fdb7f3e1560e6cf35fad763d22ac32798084e
integration_merge: bde99edec0bbb9ba331c6099c8b467c14fe24e58
key_files:
  created:
    - src/mini_agent/application/persistence.py
    - tests/component/application/test_persistence_contract.py
  modified: []
metrics:
  feature_commits: 1
  files_changed: 2
  insertions: 3642
  deletions: 0
  focused_tests_passed: 134
  full_tests_passed: 315
---

# Phase 1 Plan 01-04｜Persistence registry / codec Summary

> **DERIVED / NON_NORMATIVE**
> 本 Summary 只索引已合并的 Task Packet 与可复现证据，不拥有产品、架构、契约、Eval 语义或 Case 生命周期。`docs/implementation/e2e01-thin-slice-implementation-spec.md` 仍是本切片 scoped implementation owner，并服从上游 active canonical owners；本文件不能把 physical persistence、Runtime、HTTP、Eval、`E2E01-01/04` 或 Phase 1 宣称为已完成。

## Outcome

`01-04` 已实现并合并 owner 批准的 Application logical persistence registry / codec：

- closed registry 恰好包含 17 个 record code / schema version / source model binding；
- strict JSON codec 对 outer / inner envelope、record identity、owner、66 条 top-level projection、7 条 logical-child projection和 version mirror 重新计算并 fail closed；
- 45 条 reference-producing projection 只指向 closed 17-item target set，其中恰好 5 条 external-required relation 由调用方提供；
- `AcceptedTaskDelta`、`TaskStateTransition`、`ToolAttemptRecord` 三类 logical child 服从 parent equality、local correlation 与已批准 closure strategy；
- `TaskStateTransition` 仍保持 `GRAPH_REQUIRED`，codec 不声称 complete history、owner graph 或 restart readiness；
- bounded integrity diagnostics 只暴露封闭 category 与 opaque UUID，不泄露 payload、identity、owner 或底层异常链。

本 Packet 没有创建 Repository、table、migration、HTTP、Session、Runtime orchestration、Harness、Composition Root 或 physical recovery claim。

## Exact Evidence

| Evidence | Exact value / result |
|---|---|
| Task Packet execution base | `9602fc18148b19c841889a8041daf10ccc5b8f1c` |
| Planning-status PR | [#18](https://github.com/weijie567/mini-agent/pull/18) |
| Planning merge / tree | `390d615be8e4020008c45bce1feec6260e47d361` / `2ebfdbf40a2cff3936fe6156858a28a642dfa6f5` |
| `01-04-PLAN.md` blob | `e3045cecf4f60ce6cbd1952d054c7f1153b40d20` |
| `01-03-SUMMARY.md` blob consumed by Plan | `c96877d71a4ae4913487f1062e3dbb222e3717f4` |
| Local final reviewed head / tree | `75d1d29c7a0580fe09e3c61ef6f820ec728e0586` / `71eb2966a984b0e6c9330275b91c26d2861bc658` |
| Published feature head / tree | `828fdb7f3e1560e6cf35fad763d22ac32798084e` / `71eb2966a984b0e6c9330275b91c26d2861bc658` |
| Feature PR | [#19](https://github.com/weijie567/mini-agent/pull/19) |
| Integration merge / tree | `bde99edec0bbb9ba331c6099c8b467c14fe24e58` / `6bf8617c255e4e36d6f08705b0c5e9738ac9ea33` |
| Production source blob | `c90105ce6b934763f8deb4c9ae981bcf4f38c0b3` |
| Component test blob | `42853c29aacba8a79f776d10496542918026a741` |
| Scope | exactly 1 feature commit、2 created files、3642 insertions、0 deletions |
| Focused component regression | `uv run pytest tests/component/application/test_persistence_contract.py` → `134 passed` |
| Full regression | `uv run pytest` → `315 passed` |
| Static / mechanical gates | `ruff check`、`ruff format --check`、`compileall`、`git diff --check`、one-commit / two-file containment 全部 `PASS` |
| Final exact-head review | 两路 reviewer 对 current remote exact head 均为 `PASS`；最终 `CRITICAL/HIGH/MEDIUM/LOW = 0/0/0/0` |

本地与 published feature commit 的 SHA 不同，是因为本环境使用 Git Database REST API 发布；两者 parent 都是 exact execution base，tree 与两个 owned blobs 完全相同。GitHub squash merge 是 verified commit，Integrator 只以 `--ff-only` 更新 integration。

## Review and Repair History

首轮实现不是未经审查直接合并。两位独立 reviewer 发现：

- external reference identity 曾错误接受 `None`、`bool`、`int` 与非法 UUID；
- forged Pydantic `model_construct` / copy 输入可能绕过 bounded diagnostics 或保留可变 alias；
- 深层 JSON 可触发未封装的 `RecursionError`；
- 非字符串 Mapping key 曾可能被 stringify 后碰撞；
- forged `P0PersistenceEnvelope` 的非字符串 key 可能绕过 Mapping guard；
- 负向测试矩阵还没有覆盖上述边界。

原 writer 在同一 owned two-file Packet 内完成两轮修复与重验。最终 exact-head：

- 所有非法 external identity、forged model、deep JSON 与 key collision 均 fail closed；
- bounded integrity error 保持 opaque correlation UUID、封闭 category、空 unsafe exception chain；
- focused 134 tests 与 full 315 tests 全部通过；
- 两路 reviewer 对 remote exact head 复审均无 unresolved finding。

## Contract, Security and Eval Impact

- **Contract change:** `NO NEW SEMANTICS / IMPLEMENTS APPROVED CONTRACT`。实现严格消费 PR #16/#17 已冻结的 logical contract。
- **Security impact:** `YES`。类型、版本、identity、owner、reference、child、JSON 与 diagnostic safety 都由 deterministic code fail closed；codec 不构造 `TrustedOwnerScope`，也不执行授权或查询。
- **Eval impact:** `YES / COMPONENT TESTS ONLY`。新增 134 项 focused codec Component tests；没有生成 Eval Result、Trajectory、HTTP E2E 或 Case lifecycle 证据。
- **Physical persistence impact:** `NONE`。没有 table、migration、Repository、transaction 或 startup recovery。

## Graphify Serial Gate

在 PR #19 exact merge 后，Integrator 于 root integration checkout 串行完成：

1. `graphify update .` 的 AST refresh；
2. 对 `PROJECT_DIRECTION.md` 与 Thin Slice Spec 的受控 semantic re-extraction；
3. schema / endpoint / confidence / absolute-source-path 校验；
4. semantic cache 保存与 `graphify cluster-only .`；
5. stale marker 清除和 repository graph health 检查。

最终 gate：

- `graphify-out/graph.json`：3089 nodes、4822 edges；
- missing endpoint、dangling edge、self-loop、duplicate edge、collapsed edge 均为 0；
- 两个 `needs_update` marker 均不存在；
- tracked integration tree 保持 clean。

Graphify 的 community label 数量变化只影响派生导航质量，不构成 canonical contract 或 freshness blocker。

## Deferred and Unresolved

- `01-04D` 先关闭 Application Port / codec external relation context、initial/transition/Run-finalization原子 aggregate与 fenced recovery claim contract gap；
- `01-05` 实现 Core / Application Runtime behavior 与 Component tests；
- `01-06` 实现 Session / HTTP / PostgreSQL / migration / scoped `get_order` / recovery Adapter；
- `01-07` 实现 versioned Eval loader、Scripted / Qwen Adapter、Harness、Graders、structured result / failure 与 fault injection；
- `01-08` 由 Integrator串行建立 Composition Root与纵向 HTTP / Trace / Eval集成；
- complete owner graph、fenced recovery claim、physical transaction 与 startup readiness 只能由后续 Runtime / Infra / Integration 证据成立；
- `E2E01-01` 与 `E2E01-04` 仍为 `Pending / CONTRACT_DEFINED`；`requirements_completed` 为空，numbered Phase lifecycle保持 `0/8`。

## Handoff to Plans 01-05 / 01-06 / 01-07

Inserted Packet 01-04D必须先从 exact integration SHA `bde99edec0bbb9ba331c6099c8b467c14fe24e58` 执行并合并。随后三个 W2 Task Packet从新的同一个 exact integration SHA预建不同 Worktree / branch，并遵守：

- 只消费 01-04 public codec surface，不复制 registry / projection 语义；
- Runtime、Infra、Eval 文件 ownership 完全互斥；
- `pyproject.toml`、`uv.lock`、migration chain、`tests/conftest.py` 等 single-writer 热点只能归 01-06 或 Integrator，其他分支禁止写；
- `src/mini_agent/__init__.py`、`src/mini_agent/main.py`、`src/mini_agent/bootstrap.py` 保留给 01-08 Integrator；
- 任一分支发现需要修改 shared DTO / Port、active canonical owner 或其他 Workstream 文件时必须停止并提交 dependency request；
- 三个 feature PR 都先以 draft 形式目标 `integration/e2e01-thin`，由 Integrator 串行审查、重验和合并。

## Self-Check: PASSED

- 本 Summary 的 base、planning、feature、published 与 integration SHA / tree / blob 可从 Git object和 PR #18/#19 复现。
- 01-04 实际 changed-file set 与 Plan exact two-file allowlist 完全一致。
- 所有 review finding 已在 final remote exact head 关闭，完整 regression 为 315 passed。
- Graphify code + semantic freshness gate 已通过，tracked integration tree clean。
- Requirements completion 为空；本 Summary 没有把 Runtime、Infra、Eval、HTTP、Case 或 Phase 标为完成。
