---
phase: 01-cycle-1-e2e-01
plan: 07AB
type: fix
wave: 28
depends_on:
  - 01-07AA
  - 01-07J-PLAN
files_modified:
  - tests/component/application/test_persistence_contract.py
autonomous: true
requirements:
  - E2E01-01
  - E2E01-04
user_setup: []
---

# Phase 1 Plan 01-07AB｜Exact-run reader dependency scope alignment

> **ISSUED ALIGNMENT PACKET / IMPLEMENTATION NOT STARTED**
>
> 本 Packet 只修正静态依赖清单，使 01-07J 已签发且强制要求的真实
> PostgreSQL exact-run oracle 成为已声明的 `ExactRunEvidencePort` test
> dependency。它不修改 reader、Runtime、业务契约或 01-07J feature。
> Graphify 按用户指令保持闲置。

## Objective

01-07J 在五文件 hard allowlist 内新增
`tests/integration/test_agent_run_service_v2_persistence.py`，并按 Plan 要求直接
调用 owner-scoped exact-run reader。Application regression 因
`test_codec_dependencies_are_scoped_without_active_routing_or_authority_claim`
的旧 closed dependency set 未登记该测试而得到 `672 passed, 1 failed`。

本 Packet 仅将该测试路径加入 `exact_reader_dependency_files`。这属于
consumer inventory 对齐，不授予 Runtime authority，不扩大 reader surface，
也不把 integration test 升级为 canonical owner。

## Exact Task Packet

```yaml
repository: /Users/ming/projects/mini-agent
remote: https://github.com/weijie567/mini-agent.git
base_sha: 023cce5a357122511823bc759ad767d75f8fb053
base_tree: 77552fad9132cad6c17c3a7f1b8511414a2c5fcb
feature_branch: codex/e2e01-01-exact-reader-scope-alignment
feature_worktree: e2e01-01-exact-reader-scope-alignment
writer: /root Integrator / persistence dependency inventory sole writer
pull_request_base: integration/e2e01-thin
allowlist:
  - tests/component/application/test_persistence_contract.py
base_blob:
  tests/component/application/test_persistence_contract.py: bbe319e4188bd350e95ffde298dc77692d3294e1
forbidden_files: ALL REPOSITORY FILES OUTSIDE THE ONE-FILE ALLOWLIST
dependencies:
  - reviewed 01-07J Plan merge 023cce5a357122511823bc759ad767d75f8fb053
  - provisional J feature head a00b53eedcf84d477f01d8a9cf06cd097361609b
  - J oracle blob 3c147a754ceae7bf8534e16ae2fd0d1f1531c5a3
  - 01-07J feature exact base remains B_J_READY; this Packet does not rebase it
contract_changes: NONE
security_impact: NONE; static dependency inventory only
eval_impact: YES; registers the already-required J PostgreSQL integration oracle
rollback: ordinary revert PR removing only the one dependency-set entry
```

Plan branch与feature branch均从上述 exact base 独立创建。Plan merge只记录
签发，不替换 feature base。

## Required change

在 `exact_reader_dependency_files` 中增加且只增加：

```python
"tests/integration/test_agent_run_service_v2_persistence.py",
```

不得放宽 subset assertion，不得引入 wildcard、目录级豁免、动态扫描例外，
不得修改 `files_referencing`、owner set、其他 codec dependency set 或测试
逻辑。

## Verification

1. RED 证据在 exact J feature head
   `a00b53eedcf84d477f01d8a9cf06cd097361609b` 复现：
   `uv run pytest tests/component/application/test_persistence_contract.py::test_codec_dependencies_are_scoped_without_active_routing_or_authority_claim -q`
   只因新 J oracle 路径为 extra item 而失败。01-07AB 自身 base 尚无该
   test 文件，因此不得伪称 base 单独为 RED。
2. GREEN 在 detached synthetic overlay 中验证：以 exact J head 为 tree
   输入，只应用 01-07AB one-line patch；同一命令通过。记录 overlay
   base/head/tree、J oracle blob 与 alignment target blob。
3. Application：
   `uv run pytest tests/component/application -q`，零失败。
4. 01-07J focused：
   在 latest-integration overlay 中运行 J 的三个 test 文件，零失败。
5. `uv run pytest`、`uv run alembic upgrade head`、canonical db/db-test health。
6. `git diff --check`；changed files 精确等于 one-file allowlist；线性、零 merge。
7. exact-head 独立审查与 latest-integration overlay 独立审查均为全零 findings。
8. 串行 squash merge；merge tree 等于 reviewed overlay tree；post-merge
   Application/full 通过后形成 `B_J_SCOPE`，供 01-07J latest overlay 使用。

## Nonclaims

- 不改变 `ExactRunEvidencePort` 或 PostgreSQL reader 实现。
- 不允许生产 Runtime 调用 exact-run reader。
- 不表示 01-07J 已审查、已合并或 `B_ACTIVE` 已形成。
- 不解决 zero/multi product outcome、Trajectory/E2E Result 或产品 readiness。

## Done when

单文件 exact dependency inventory 对齐经双重独立审查、串行 merge 与
post-merge gate 后形成 `B_J_SCOPE`；01-07J feature 仍保留原 exact
`B_J_READY` base，并在 `B_J_SCOPE` 上构造 latest-integration overlay。
