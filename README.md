# Mini Agent

面向已登录消费者的“订单与配送售后 Agent”P0。当前项目用一个自建站和可复现的合成数据模拟 Order、Shipment、Policy Knowledge 与 Refund 边界；P0 不连接真实电商、支付、退款或物流系统。

## 当前进度

W1 基础骨架已经进入 `integration/e2e01-thin`：

- Python / uv 工具链、固定版本 PostgreSQL + pgvector、Alembic 与隔离测试 namespace；
- Core / Application 的身份、Request Understanding、Task、Tool、Observation、Trace 等 contract；
- `e2e01-thin-fixture-v1`、E2E01-01/04 与安全故障场景的 versioned Eval artifacts；
- 根目录默认离线测试当前为 `125 passed`。

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

写入 Agent 必须使用不同 Git Worktree、branch 和互不重叠的文件 ownership。每个 Task Packet 都要包含精确 `base_sha`、repository、head/base branch、allowlist、forbidden files、依赖、验证命令和交接格式；禁止直接 push `main` 或 integration。

下一步不是立即并行写 W2，而是先完成串行 `W2-CONTRACT-FREEZE`：补齐跨 Runtime / Infra / Eval 共用的持久化 DTO、Port、恢复读取边界和测试 bootstrap contract。冻结 PR 合并后，三个 W2 worktree 才从同一精确 SHA 并行启动。

## GSD

当前不启用会写入 `.planning/` 的 GSD 流程。GSD 可以在未来作为派生的规划、执行和验证辅助，但必须先通过独立 activation PR 完成 active owner mapping、冲突审查和隔离演练；它不能成为产品、架构、契约或 Eval 语义的第二套 canonical owner。
