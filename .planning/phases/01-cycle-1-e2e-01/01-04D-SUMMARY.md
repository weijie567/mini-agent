---
phase: 01-cycle-1-e2e-01
plan: 04D
subsystem: application
status: complete_evidence_indexed
completed_at: "2026-07-26T18:49:41Z"
requirements:
  - E2E01-01
  - E2E01-04
requirements_completed: []
execution_base: bde99edec0bbb9ba331c6099c8b467c14fe24e58
planning_merge: 3a2b81a8f6f2c31d0b394fef85b2c2f59eb082d2
local_reviewed_head: d82e394b6500c61a6fa82043a7ccb67450961517
published_head: 581f9d9f54c63c15c21a63e26a29ad8f3cd672ea
integration_merge: a84d30188eaec75e45619e9939180ba78efa3b80
key_files:
  created: []
  modified:
    - src/mini_agent/application/ports.py
    - src/mini_agent/application/records.py
    - tests/component/application/test_persistence_contract.py
    - tests/component/application/test_ports_contract.py
    - tests/component/application/test_record_contracts.py
metrics:
  feature_commits: 1
  files_changed: 5
  insertions: 3041
  deletions: 382
  focused_tests_passed: 210
  full_tests_passed: 344
---

# Phase 1 Packet 01-04D｜Application Port closure Summary

> **DERIVED / NON_NORMATIVE**
> 本 Summary 只索引已合并 Task Packet 与可复现证据，不拥有产品、架构、契约、Eval 语义或 Case 生命周期。Application contract 的 scoped 实现语义仍服从 active canonical owners 与
> [`e2e01-thin-slice-implementation-spec.md`](../../../docs/implementation/e2e01-thin-slice-implementation-spec.md)；本文件不能把 Runtime、physical Adapter、HTTP、Provider、Eval、恢复 readiness、`E2E01-01/04` 或 Phase 1 宣称为已完成。

## Outcome

`01-04D` 已在 Application owner 范围内关闭 01-04 source audit 暴露的 DTO / Port dependency gap：

- `AgentRunCommand` 只接受服务端可信 `CustomerContext` 与用户消息，`AgentRunResult` 只返回 opaque `run_id`、既有 `AgentOutcome` 与安全消息；
- `ProviderProtocolError` 为 parameterless bounded error，`ModelProvider` 明确要求 Adapter 丢弃不可信 provider payload、异常文本与底层 exception chain；
- `RuntimeRecordPort` 以 relation-aware command 携带 codec 所需 external relation context，并冻结 Request Understanding、initial Task graph、Task transition、Run finalization 与 Observation 的条件写入边界；
- initial accepted graph、Task transition graph 与 Run terminal / `RunTaskLink` projection 均以 exact-set aggregate 表达，阻止独立 split write 留下不可恢复的永久半图；
- `RestartRecoveryClosure` 在同一 snapshot / fence 语义下绑定 Run、Task、Request Understanding、link、ToolCall 与 child histories；`ApplyRestartRecoveryCommand` 对 validated closure 与 next projections 做完整 bijection；
- `RestartRecoveryPort` 收窄为单一 load 与单一 atomic claim/apply；Infra 必须在 tuple materialization 前使用 `LIMIT 2` 或等价 stream cutoff，overflow 必须 fail closed；
- active `RUNNING ACTION` 保持 `RECONCILIATION_REQUIRED` / zero-write nonclaim，`RESULT_UNKNOWN` 仍由 Action owner 处理；
- 既有 ToolCall lifecycle API 与 Core / Intent source models 未被修改或全局收窄。

本 Packet 没有实现 Runtime orchestration、physical transaction、PostgreSQL Adapter、HTTP、Session、`get_order`、Provider Adapter、Harness、Graders、Composition Root 或真实恢复 readiness。

## Exact Evidence

| Evidence | Exact value / result |
|---|---|
| Task Packet execution base | `bde99edec0bbb9ba331c6099c8b467c14fe24e58` |
| Planning-status PR | [#20](https://github.com/weijie567/mini-agent/pull/20) |
| Planning merge / tree | `3a2b81a8f6f2c31d0b394fef85b2c2f59eb082d2` / `b3a7840d5e3f70e1f68a9c6432173de15a780ef3` |
| `01-04D-PLAN.md` blob | `e9836827cc322080299aff735265d0dfd7857c04` |
| `01-04-SUMMARY.md` blob consumed by Plan | `eaa801ebb9e021ec1cf1f6331f1c29ff5446ff2b` |
| Local final reviewed head / tree | `d82e394b6500c61a6fa82043a7ccb67450961517` / `fb36154bb36252638c256dc355f997c8d2f58915` |
| Published feature head / tree | `581f9d9f54c63c15c21a63e26a29ad8f3cd672ea` / `fb36154bb36252638c256dc355f997c8d2f58915` |
| Feature PR | [#21](https://github.com/weijie567/mini-agent/pull/21) |
| Integration merge / tree | `a84d30188eaec75e45619e9939180ba78efa3b80` / `261ac105765ab320993f55bc1e2c07491a7445e9` |
| Integration merge signature | GitHub API `verified=true` / `reason=valid` |
| Changed source / test blobs | `ports.py` `95912c43…`; `records.py` `7b573485…`; tests `4284751d…` / `0e8ddf30…` / `3cb69abf…` |
| Scope | exactly 1 feature commit、5 modified files、3041 insertions、382 deletions |
| Focused component regression | three owned test files → `210 passed` |
| Full regression | `uv run pytest` → `344 passed` before publication and after integration merge |
| Static / mechanical gates | `ruff check`、exact-five `ruff format --check`、`compileall`、`git diff --check`、one-commit / five-file containment 全部 `PASS` |
| Final local exact-head review | contract/integration 与 security/edge-case 两路 reviewer 均 `PASS`；`CRITICAL/HIGH/MEDIUM/LOW = 0/0/0/0` |
| Final remote exact-head review | 两路 reviewer 对 PR #21 remote head / tree / parent / merge-base / five blobs 复审均 `PASS`；无 publication drift |

本地与 published feature commit 的 SHA 不同，是因为 Git Database REST API 发布重新生成 commit object；两者 parent、tree 与五个 owned blob 完全相同。feature branch 从 execution base 与 planning-status merge 分叉，PR compare 的 `ahead=1 / behind=1` 是预期 sibling 形状，merge-base 精确为 execution base。

## Review and Repair History

首轮实现没有未经审查直接合并。两位独立 reviewer 先后发现并推动关闭：

- `state_version` 曾可能驱动 O(N) `range` 物化；
- initial graph 曾接受携带 `incomplete_reason` 的 dirty `RUNNING` Run；
- active ToolCall retry / `failure_code` / `result_ref` 可能破坏 recovery apply totality；
- recovery 与 normal finalization 对 dirty Run 和 recovery-only stop reason 的拒绝不完整；
- `CREATED` Run 携带 downstream graph、Task transition 早于 Task 创建时间等不一致输入缺少负例；
- first-slice tuple cardinality 与 Infra pre-materialization overflow guard 需要显式界定。

原 writer 在同一五文件 ownership 中完成三轮 amend。最终实现使用 O(1) cardinality 判断加 bounded `enumerate`，把 first-slice Application command / closure tuple 限定为 `max_length=1`，同时不收窄 Core / Intent source models；两位 reviewer 对 local 与 remote exact tree 都给出 `0/0/0/0`。

## Contract, Security and Eval Impact

- **Contract change:** `APPLICATION OWNER CLOSURE / APPROVED DERIVED PLAN`。替换并收窄 Application-owned command / Protocol；active canonical owner 与 codec source byte-unchanged。
- **Security impact:** `YES`。可信身份入口、Provider non-disclosure、exact-set aggregate、conditional write、fenced recovery、Action reconciliation nonclaim 与 bounded integrity failure 均由 deterministic contract fail closed。
- **Eval impact:** `YES / COMPONENT CONTRACT TESTS ONLY`。新增或扩展 210 项 focused component tests；没有生成 Trajectory、HTTP E2E、Eval Result 或 Case lifecycle 证据。
- **Physical persistence impact:** `NONE`。没有实现 table、migration、Repository、transaction、fence 或 startup recovery。

## Post-merge Repository and Graphify Gate

Integrator 在 PR #21 merge 后于 root integration checkout 串行完成：

1. `uv run pytest`：`344 passed`；
2. `uv run ruff check src tests`：`PASS`；
3. exact five changed files的 `ruff format --check`：`PASS`；
4. `compileall`、`git diff --check`、tracked-tree clean 与 GitHub verified merge检查；
5. `graphify update .` AST refresh；
6. `graphify explain RestartRecoveryClosure` 与 `graphify explain AgentRunCommand` 可查询性检查；
7. `graphify diagnose multigraph --json` 与 stale marker检查。

最终 Graphify gate：

- `graphify-out/graph.json` 的 `built_at_commit` 精确为 integration head `a84d3018…`；
- 3253 nodes、5814 edges；
- non-object、missing endpoint、dangling endpoint、self-loop、exact duplicate 与 same-endpoint collapse 均为 0；
- `graphify-out/needs_update` 与 `graphify-out/.needs_update` 均不存在；
- tracked integration tree保持 clean。

本次 merge 只修改代码和测试，因此项目规则只要求 AST refresh；没有文档或图像内容变化需要 semantic re-extraction。

仓库级 `ruff format --check src tests` 另报告三个 parent 中已经存在且本 Packet 未修改的文件会被 reformat：`src/mini_agent/core/tool_system.py`、`tests/component/evaluation/test_e2e01_artifact_consistency.py`、`tests/component/model/test_e2e01_scripted_scenario_catalog.py`。它们不是 PR #21 regression，也不在本 Packet ownership 内；01-04D 没有越界格式化这些文件。

## Deferred and Unresolved

- `01-04E` 必须由 Memory owner冻结 `TokenCounts` 的逐方向 nullable语义，明确 `None = 未精确测量`、`0 = 已观测精确零`；
- `01-04F` 必须由 Thin Slice / Eval owners对齐 stale-state注入点与 fact-bearing presentation protocol rejection场景，并重新计算 versioned manifest hashes；
- `01-04G` 必须由 Application owner把 Core产生的 recovery Trace随 apply command传入，并要求 Infra在 `APPLIED`时与恢复状态原子提交；
- `01-05` 实现 Core / Application Runtime behavior 与 Component tests；
- `01-06` 实现 Session / HTTP / PostgreSQL / migration / scoped `get_order` / recovery Adapter，并证明 snapshot / fence、`LIMIT 2` overflow 与 physical transaction；
- `01-07` 实现 versioned Eval loader、Scripted / Qwen Provider Adapter、Harness、Graders、structured result / failure 与 fault injection；
- `01-08` 由 Integrator 串行建立 Composition Root与纵向 HTTP / Trace / Eval证据；
- GitHub 当前没有 CI check run / status context；本地 exact-tree机械证据完整，但 CI基础设施仍是后续 repository-level gap；
- `E2E01-01` 与 `E2E01-04` 仍为 `Pending / CONTRACT_DEFINED`；`requirements_completed` 为空，numbered Phase lifecycle保持 `0/8`。

## Handoff to Packets 01-04E / 01-04F / 01-04G

独立 Plan Checker 对 `01-05/06/07` 候选计划的 owner alignment审查发现四项 W2 前置问题，并按 ownership归入三个 blocker Packet，因此不得从 `01-04D` 直接启动 W2。三个 dependency Packet都以 `01-04D` merge后的 exact integration SHA `a84d30188eaec75e45619e9939180ba78efa3b80` 为 execution base，使用互斥 ownership与预建 Worktree，并按 `01-04E` → `01-04F` → `01-04G` 串行 review / merge：

- `01-04E` 单写 Memory owner、Core contract与对应 Component test；
- `01-04F` 单写 Thin Slice scoped owner、两个 versioned semantic artifacts（Case、model script）、一个 version manifest与两个 artifact / catalog tests；共三个 JSON 文件；
- `01-04G` 单写 Application record / Port owner与两个 contract tests；
- 三者合并后的新 exact integration SHA才是 01-05 / 01-06 / 01-07 的共同 planning与 execution base；
- 任一 Packet发现需要修改 allowlist外 owner、其他 Packet文件或既有 frozen contract时必须停止并提交 dependency request。

## Self-Check: PASSED

- 本 Summary 的 base、planning、feature、published与 integration SHA / tree / blob可从 Git object和 PR #20/#21复现。
- 实际 changed-file set与 01-04D exact five-file allowlist完全一致；codec source与 canonical docs未修改。
- focused 210、full 344与双路 local / remote exact-head review均通过，最终 unresolved findings为0。
- Graphify code freshness与结构健康 gate通过，tracked integration tree clean。
- Requirements completion为空；本 Summary没有把 Runtime、Infra、Eval、HTTP、Case或 Phase标为完成。
