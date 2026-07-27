# Mini Agent

面向已登录消费者的“订单与配送售后 Agent”P0。当前项目用一个自建站和可复现的合成数据模拟 Order、Shipment、Policy Knowledge 与 Refund 边界；P0 不连接真实电商、支付、退款或物流系统。

## 当前进度

W1 基础骨架已经进入 `integration/e2e01-thin`：

- Python / uv 工具链、固定版本 PostgreSQL + pgvector、Alembic 与隔离测试 namespace；
- Core / Application 的身份、Request Understanding、Task、Tool、Observation、Trace 等 contract；
- `e2e01-thin-fixture-v1`、E2E01-01/04 与安全故障场景的 versioned Eval artifacts；
- 根目录默认离线测试在 Packet 01-04D 合并后为 `344 passed`。

这不表示首条纵向切片已经可运行。HTTP API、完整持久化 Adapter、`get_order` 执行链、Provider、Harness、Trajectory / E2E Eval 与 Qwen Baseline 仍未实现，Case 生命周期继续是 `CONTRACT_DEFINED`。

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

`db` 使用持久 volume；`db-test` 使用可丢弃的 tmpfs。测试只允许连接 `127.0.0.1:55433/mini_agent_test`，并为每个 worker / Eval Run 建立独立 schema。当前没有 canonical 的应用启动命令，因为 Composition Root 和 HTTP 纵向链尚未实现。

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
同一冻结 SHA
├── Runtime worktree / feature branch
├── Infra worktree / feature branch
└── Eval worktree / feature branch
        ↓ 独立验证与只读 review
Integrator 串行合并到 integration
        ↓ 完整 E2E gate
integration PR → main
```

写入 Agent 必须使用不同 Git Worktree、branch 和互不重叠的文件 ownership。一个 GSD Plan 只映射一个精确 Task Packet；Packet 不得跨 repository、branch、Worktree、writer 或 ownership boundary。每个 Packet 都要包含精确 `base_sha`、repository、head/base branch、allowlist、forbidden files、依赖、验证命令、契约变化、安全 / Eval 影响、回滚和交接格式；禁止直接 push `main` 或 integration。

`W2-CONTRACT-FREEZE` 已通过 PR #9 合并，GSD activation 已由 [PR #10](https://github.com/weijie567/mini-agent/pull/10) 生效。Plan 01-01至01-04G的planning与owner链已通过PR #11–#25依序合并；01-04G merge `c35687dafa3881bb322d91515068d8d39be79df6` 是W2 Runtime / Infra / Eval共同execution base，并已通过466 tests与Graphify gate。W2 planning [PR #26](https://github.com/weijie567/mini-agent/pull/26) reviewed head `2922308b...`经两个Codex只读Reviewer复核后merge为`968b4a9fffa446a789f69cce9f04e1c49148d40f`；Reviewer记录已作为明确标注的[canonical evidence](https://github.com/weijie567/mini-agent/pull/26#issuecomment-5086174316)与[security/process evidence](https://github.com/weijie567/mini-agent/pull/26#issuecomment-5086174609)持久化，它们不是GitHub Reviews API formal approvals。三个互斥Worktree随后从`c35687d...`创建：Runtime [PR #28](https://github.com/weijie567/mini-agent/pull/28)、Infra [PR #30](https://github.com/weijie567/mini-agent/pull/30)、Eval [PR #29](https://github.com/weijie567/mini-agent/pull/29)均已发布为Draft并通过各自本地focused/full门禁；independent feature review、latest-integration overlay、Runtime → Infra → Eval serial merge与01-08仍待完成。实际Packet完成口径保持`8/12`，Case lifecycle保持`0/8`。实时状态与证据见[多 Agent 实施计划](docs/implementation/e2e01-thin-slice-multi-agent-plan.md)。

## GSD

GSD 只作为派生的规划、审查和验证层，不能成为产品、架构、契约或 Eval 语义的第二套 canonical owner。Activation 已随 PR #10 合并而生效；后续仍必须按 [GSD Governance](.planning/GOVERNANCE.md)、[Activation Record](.planning/ACTIVATION.md) 与[当前派生 State](.planning/STATE.md) 受控使用。

当前明确禁用 stock `gsd-import`、`gsd-plan-phase`、`gsd-execute-phase`、`gsd-verify-work`、`phase.complete`、`requirements.mark-complete`、`roadmap.update-plan-progress` 和 `gsd-ship`。规划使用 GSD planner / checker 角色的只读建议，由 Integrator 在 dedicated planning-status Worktree 单写最终 Plan；UAT 使用无 lifecycle mutation 的受控 adapter。`.planning/config.json` 的 `parallelization=false` 与 `workflow.use_worktrees=false` 只关闭 GSD 自管并行 / Worktree，不关闭 Codex 多 Agent：Integrator 仍在 workflow 外预建精确 Task Packet Worktree / feature branch，Agent 实现并创建 draft feature → integration PR，Integrator 串行合并，最后显式创建 integration → `main` PR。Code review、fix、validation、Eval / Security audit 与 UAT 的条件和 containment gate 以 Governance 为准。
