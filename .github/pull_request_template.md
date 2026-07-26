## 变更摘要

- 做了什么：
- 为什么：
- 用户或开发影响：

## Task 与 ownership

- Task Packet：
- `base_sha`：
- Head branch：
- Base branch：
- Worktree：
- 文件 allowlist：
- 实际变更文件：
- 契约变化：`NONE` / 说明并链接 canonical owner

## 验证

| 命令 / 检查 | 结果 | 证据或说明 |
|---|---|---|
| `git diff --check` |  |  |
| focused checks |  |  |
| cross-file impact scan |  |  |
| full offline gate（如适用） |  |  |

未执行的检查及原因：

## 安全与 Eval

- 可信身份、资源归属和最小披露是否受影响：
- Tool / Action / Evidence / 状态边界是否受影响：
- 新增或更新的 Component / Trajectory / E2E Case：
- 是否包含 secret、真实客户数据或不必要的 PII：`NO` / 说明

## 交接

- 推荐 merge 顺序：
- 已知风险：
- 未决事项：
- 回滚方式：

## Checklist

- [ ] PR 只包含 Task Packet 范围内的变更。
- [ ] 没有直接修改或覆盖其他 Agent 的 ownership。
- [ ] 没有把 Plan、Mock 或目标命令描述为已实现 / 已通过。
- [ ] 相关 active owner、派生文档与状态已完成 cross-file alignment。
- [ ] 已报告所有执行、未执行和失败的检查。
