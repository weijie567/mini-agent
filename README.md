# Mini Agent

面向已登录消费者的“订单与配送售后 Agent”P0。当前项目用一个自建站和可复现的合成数据模拟 Order、Shipment、Policy Knowledge 与 Refund 边界；P0 不连接真实电商、支付、退款或物流系统。

## 当前进度

第一最薄 `E2E01-01/04` 的 W1 / W2、RU v2 contract closure、offline vertical integration 与 Qwen runner 已经进入 `integration/e2e01-thin`：

- Python / uv 工具链、固定版本 PostgreSQL + pgvector、Alembic 与隔离测试 namespace；
- Core / Application 的身份、Request Understanding、Task、Tool、Observation、Trace 等 contract；
- 受控 Runtime、Session / HTTP Adapter、PostgreSQL record / `get_order` Adapter 与恢复路径；
- `e2e01-thin-fixture-v1`、versioned Eval artifacts、双 Provider Adapter、13 个确定性 Grader、Harness 及结构化 Result / Failure machinery；
- `OfflineE2E01Composition`、real `EvalCaseSut`、PostgreSQL exact owner-scoped `EvalEvidence` reader、直接 HTTP → Runtime → PostgreSQL 离线纵向 evidence 与 credential-aware Qwen runner；
- `B_RU_V2_CONTRACT = 5c84e0e...`、`B_01_08 = b8a2cf3...`、`B_01_08A_COMPOSITION = c59eaea...`、`B_01_08A = 11d6d08...` 已形成；Phase Review findings、controlled UAT、Eval / Security re-review 与 lifecycle activation 均已完成，exact security re-review barrier `22c4cfa...` 的 canonical offline gate 为 `2007 passed, 1 deselected, 12 warnings`。

这表示第一最薄 scoped deterministic offline slice 已形成真实 `REGRESSION_GATE`：六个 authenticated physical Case 的全部 16 个 variants 经 `OfflineEvalHarness → HTTP → Runtime → PostgreSQL` 得到 `16 PASS / 0 FAIL / 0 Critical failure / 0 execution failure`，并进入默认 `uv run pytest`。Controlled UAT 由获授权的 `CODEX_INTEGRATOR` 直接执行并作 scoped `PASS`，但 `end_user_uat` 为 `NOT_RUN`。当前仍没有 canonical 应用启动、真实 credentialed Qwen Baseline、hosted CI、完整 E2E-01 / P0 或 production readiness；`RTA-D01` 是否在 release gate 继续接受以及是否合并到 `main` 仍待用户裁决。

实时范围与权威边界见：

- [业务能力说明](docs/business-capabilities.md)
- [P0 架构方向](PROJECT_DIRECTION.md)
- [E2E01 最薄切片 Implementation Spec](docs/implementation/e2e01-thin-slice-implementation-spec.md)
- [多 Agent 实施计划](docs/implementation/e2e01-thin-slice-multi-agent-plan.md)
- [项目协作规则与 canonical 命令](AGENTS.md)

## 本地开发

需要 Python 3.12、[uv](https://docs.astral.sh/uv/) 与 Docker Compose。从仓库根目录执行：

```bash
uv sync --all-groups
docker compose up --wait -d db
docker compose --profile test up --wait -d db-test
uv run alembic upgrade head
uv run pytest
```

`db` 使用持久 volume；`db-test` 使用可丢弃的 tmpfs。测试只允许连接 `127.0.0.1:55433/mini_agent_test`，并为每个 worker / Eval Run 建立独立 schema。仓库已有测试专用 `OfflineE2E01Composition` 和 HTTP 纵向 evidence，但当前仍没有 canonical 的产品应用启动命令。

## 为什么先准备模拟数据

开发前需要冻结最小、确定性的 synthetic fixture，而不是等待生产数据，也不是一次性仿真完整生产环境。当前唯一 fixture 是 [`e2e01-thin-fixture-v1`](evals/fixtures/e2e01-thin-slice.v1.json)，它同时服务后续数据库 seed、HTTP E2E 和 Eval：

- Alice 可以访问 `O-1001`；
- Bob 拥有 `O-2001`，用于验证跨用户访问不泄漏；
- `O-9999` 是不得写入数据库的不存在订单 sentinel；
- Fixture、Case dataset、model-script catalog 与 lane artifact 都有固定版本，其 SHA-256 由 versioned manifest 记录；manifest 自身由 Git 版本化。

真实失败出现后再增量加入回归集；fixture 不包含真实客户、真实订单或生产凭据。

## 多 Agent 与 GitHub 流程

仓库是公开的：[weijie567/mini-agent](https://github.com/weijie567/mini-agent)。`main` 与 `integration/e2e01-thin` 受 branch protection 保护，开发变更必须走 feature branch 和 PR。

```text
每个 Task Packet 的 exact frozen SHA
├── ownership / dependency 允许时：多个 worktree 并行
└── shared contract 或 exact-base 依赖时：reviewed merge 后串行签发
        ↓ feature branch 独立验证与只读 review
Integrator 串行合并到 integration
        ↓ 完整 E2E gate
integration PR → main
```

写入 Agent 必须使用不同 Git Worktree、branch 和互不重叠的文件 ownership。一个 GSD Plan 只映射一个精确 Task Packet；Packet 不得跨 repository、branch、Worktree、writer 或 ownership boundary。每个 Packet 都要包含精确 `base_sha`、repository、head/base branch、allowlist、forbidden files、依赖、验证命令、契约变化、安全 / Eval 影响、回滚和交接格式；禁止直接 push `main` 或 integration。

`W2-CONTRACT-FREEZE` 已通过 PR #9 合并，GSD activation 已由 [PR #10](https://github.com/weijie567/mini-agent/pull/10) 生效。RU v2 contract closure、01-08 vertical integration 与 01-08A runner 依次由 PR #149、#153、#156 与 #158 形成 reviewed barriers；Phase Review 的 CR-01 / WR-01 分别由 PR #161 / #162 修复。完整 writer、allowlist、barrier、失败 lineage 与执行顺序只以[多 Agent 实施计划](docs/implementation/e2e01-thin-slice-multi-agent-plan.md)为准；README 不维护第二套 execution map 或计数。用户已明确暂时停用 Graphify；后续不运行或引用 Graphify，也不把 freshness 作为当前或后续 barrier 门禁。Historical Runtime [PR #28](https://github.com/weijie567/mini-agent/pull/28) 与 Infra [PR #30](https://github.com/weijie567/mini-agent/pull/30) 只保留 review evidence，不 rebase / force-push。

Post-execution review / fix closure、Validation、controlled UAT、Eval activation / Results / regression gate、mandatory Security re-review、execution-plan 与 `.planning` 派生状态同步均已完成。当前 release gate 只剩 `RTA-D01` 最终用户裁决，以及显式 integration → `main` PR 的合并决定；Phase completion transition在两项决定完成前保持锁定，禁止用 stock lifecycle API 自动推进 [STATE](.planning/STATE.md)、[ROADMAP](.planning/ROADMAP.md) 或 [REQUIREMENTS](.planning/REQUIREMENTS.md)。

## GSD

GSD 只作为派生的规划、审查和验证层，不能成为产品、架构、契约或 Eval 语义的第二套 canonical owner。Activation 已随 PR #10 合并而生效；后续仍必须按 [GSD Governance](.planning/GOVERNANCE.md)、[Activation Record](.planning/ACTIVATION.md) 与[当前派生 State](.planning/STATE.md) 受控使用。

当前明确禁用 stock `gsd-import`、`gsd-plan-phase`、`gsd-execute-phase`、`gsd-verify-work`、`phase.complete`、`requirements.mark-complete`、`roadmap.update-plan-progress` 和 `gsd-ship`。规划使用 GSD planner / checker 角色的只读建议，由 Integrator 在 dedicated planning-status Worktree 单写最终 Plan；UAT 使用无 lifecycle mutation 的受控 adapter。`.planning/config.json` 的 `parallelization=false` 与 `workflow.use_worktrees=false` 只关闭 GSD 自管并行 / Worktree，不关闭 Codex 多 Agent：Integrator 仍在 workflow 外预建精确 Task Packet Worktree / feature branch，Agent 实现并创建 draft feature → integration PR，Integrator 串行合并，最后显式创建 integration → `main` PR。Code review、fix、validation、Eval / Security audit 与 UAT 的条件和 containment gate 以 Governance 为准。
