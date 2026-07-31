---
phase: 01-cycle-1-e2e-01
plan: 01-07AA-CODEC-BOUNDARY-SCOPE-AMENDMENT
type: contract-remediation
status: reviewed-plan-required
base_sha: dc21e906183647c9fdf9aeffa47f256ad1a823ae
planning_base_sha: 8cd842cd4cc2605de506011a2f979dedc998a2ed
feature_base_sha: dc21e906183647c9fdf9aeffa47f256ad1a823ae
feature_branch: codex/e2e01-01-ru-v2-codec-handoff
feature_worktree: e2e01-01-ru-v2-codec-handoff
feature_current_head: 6f550e53b6dd2f32b8622bd6cc8ad0b8a760eefa
files:
  - tests/component/application/test_persistence_contract.py
autonomous: false
contract_changes: YES
security_impact: YES
eval_impact: YES
---

# 01-07AA Codec Boundary Scope Amendment Plan

## 1. 问题与裁决

`01-07AA-CODEC-HANDOFF-PLAN.md` 的目标是把 01-07Q pre-writer guard 演进为可接受 01-07AA exact writer / reader oracle 的 dependency-scope contract，同时对 `PostgresRecordAdapter` 的 versioned codec use-site 做 AST containment。

现有未发布 feature 在独立审查中不断扩张为“通过有限 AST denylist 证明任意 Python 反射、re-export、loader、alias、container、call-return 和跨模块 transfer 都不可能取得 codec”。这一主张不可由当前 Component test 证明，也不是 P0 Runtime 安全模型：

- 仓库只执行受审查的 trusted application code，不执行用户或模型提供的 Python；
- 用户 / 模型不能修改 import graph、调用 `eval` / loader 或注入 callable；
- authorization、owner scope、Evidence、ActionPolicy 和副作用边界仍由确定性运行时代码负责；
- Component dependency guard 是 repository maintenance contract，不是 Python sandbox、capability security monitor 或运行时授权器。

因此裁决如下：

1. `repo-wide dependency gate` 只拥有可机械证明的静态依赖范围：direct import / direct `Name` / direct attribute、exact symbol text、可静态折叠的 symbol string，以及明确列出的 module-object / common dynamic-import syntax。它不得宣称穷举 Python 全部对象反射或跨模块数据流。
2. `Postgres dedicated containment` 使用正向 use-site allowlist：versioned encoder / decoder 的 direct imported binding、每个 binding reference、direct `Call.func`、method / class / body ancestry 和禁止的隐式 scope都必须可枚举；未出现在正向集合中的同名 binding/reference一律失败。
3. 任意 trusted source 通过 legacy callable 的 `.__globals__`、第三方 loader、任意 identity function、mutation 或自定义 re-export 取得 module 的假设，属于恶意源码 / Python sandbox threat，不由本 dependency test承诺。实际源码出现这类行为仍是 review blocker；不能因为“不在 Component oracle 保证内”而允许合并。
4. `tests/integration/test_postgres_v2_request_understanding_writes.py` 继续只获得 named-file dependency 许可；它的 direct versioned encode、exact reader用途和无 dynamic lookup由 AA exact-head source review负责。
5. 如果未来引入 untrusted Python、插件代码、用户脚本或模型生成代码执行，必须在独立 phase 建立 runtime sandbox / process isolation / import policy；不得复用本 guard 作为安全证明。

该裁决收窄的是测试证明边界，不放宽任何产品 authorization、owner、Evidence、Tool / Action 或副作用不变量。

## 2. 独立审查 findings 处置

Avicenna 对未发布 `6f550e53…` 报告的四类 P1 按以下方式处理：

| finding | 处置 |
|---|---|
| callable taint 无法覆盖所有 Call / mutation / re-export | `CONTRACT_SCOPE_CORRECTION`：删除“闭包式 taint 证明”主张；不再以有限 taint helper 作为 PASS 依据 |
| loader / parent package / re-export denylist 可绕过 | `CONTRACT_SCOPE_CORRECTION`：repo-wide 只声明静态 dependency syntax，不声明 Python loader sandbox |
| Postgres 可经父包 / reflection 取得隐藏 codec | `IMPLEMENTATION_FIX + REVIEW`：正向冻结 direct imported codec binding 与全部同名 use-site；源码 review 明确阻断任何 hidden acquisition |
| nested `ClassDef` / generator function 延迟执行 | `IMPLEMENTATION_FIX`：ancestry 禁止 nested class / comprehension / Lambda；目标 method 含 `Yield` / `YieldFrom` 必须失败；call必须位于method body |

上述 findings 不能在未修改 contract 文本时由 Integrator 静默降级。只有本 amendment final exact-head review PASS 且合并后，才可按新边界复审 feature。

## 3. 实现契约

### 3.1 Repo-wide static dependency gate

`files_referencing(*symbols)` 必须至少检测：

- exact source symbol；
- AST direct imported name / `Name` / attribute；
- `folded_string` 已支持的 literal、`+`、静态 f-string与静态 `join`；
- direct `import mini_agent.application.persistence`；
- direct `from mini_agent.application import persistence`，含明确 relative form；
- direct persistence star / dunder import；
- direct `builtins` / `importlib` / `sys.modules` common dynamic surface。

它不得：

- 命名为或描述为 arbitrary capability closure；
- 用有限 dataflow helper 宣称覆盖所有 Python assignment / mutation / return / loader；
- 把 `pkgutil.resolve_name`、任意第三方 loader 或任意 user-defined identity function 的缺失覆盖描述为安全漏洞已关闭；
- 扩大 symbol dependency allow-set 以容纳 Runtime / Core / provider / HTTP / Eval 的实际 versioned codec引用。

### 3.2 Postgres positive use-site allowlist

对 `src/mini_agent/infrastructure/persistence/postgres.py`：

- `encode_persistence_record_versioned` 与 `decode_persistence_record_versioned` 只能从 exact absolute owner module direct import且无 alias；
- 所有 exact codec `Name` reference 均须被枚举；
- 每个 reference 的 parent 必须是 `Call` 且该 reference 精确为 `Call.func`；
- encoder enclosing class 精确为 `PostgresRecordAdapter`，method精确为 `_ru_v2_write_encode`；
- decoder enclosing class 精确为 `PostgresRecordAdapter`，method精确为 `load_exact_run_evidence_for_owner` 或 `_ru_v2_write_*`；
- call到method之间不得出现 `Lambda`、`GeneratorExp`、`ListComp`、`SetComp`、`DictComp` 或 nested `ClassDef`；
- method direct child必须属于 method body，不接受 default、decorator、annotation或class-body evaluation；
- enclosing method AST 内不得出现 `Yield` / `YieldFrom`；
- codec binding不得出现 Store / Del、argument、alias、nested definition、exception或pattern binding；
- module attribute形式与额外 exact method-name reference失败；
- 对 Postgres source 的 common module-object / dynamic import / unsafe direct `getattr` 检查可保留为 defense-in-depth，但不得替代上述正向 use-site证明。

### 3.3 Integration oracle

AA composition source review必须确认：

- `encode_persistence_record_versioned` 只构造 bounded wrong-owner fixture；
- `load_exact_run_evidence_for_owner` 只用于成功、replay和并发后的 authoritative closure；
- 无 active registry / catalog owner / Runtime active-routing claim；
- 无 module-object、reflection或dynamic lookup取得 codec。

## 4. Task Packet

repository:

- `weijie567/mini-agent`

remote:

- `origin` / `git@github.com:weijie567/mini-agent.git`

base_branch:

- `integration/e2e01-thin`

planning_base_sha:

- `8cd842cd4cc2605de506011a2f979dedc998a2ed`

base_sha:

- `dc21e906183647c9fdf9aeffa47f256ad1a823ae`

feature_base_sha:

- `dc21e906183647c9fdf9aeffa47f256ad1a823ae`

head_branch:

- `codex/e2e01-01-ru-v2-codec-handoff`

feature_branch:

- `codex/e2e01-01-ru-v2-codec-handoff`

feature_worktree:

- `e2e01-01-ru-v2-codec-handoff`

worktree_id:

- `e2e01-01-ru-v2-codec-handoff`

current_unpublished_feature_head:

- `6f550e53b6dd2f32b8622bd6cc8ad0b8a760eefa`

file_allowlist:

- `tests/component/application/test_persistence_contract.py`

owned_files:

- `tests/component/application/test_persistence_contract.py`

forbidden_files:

- `src/**`
- 除 owned file 外的 `tests/**`
- `alembic/**`
- `docs/**`
- `.planning/**`
- `pyproject.toml`
- `uv.lock`
- `AGENTS.md`

dependencies:

- merged `01-07AA-CODEC-HANDOFF-PLAN.md`
- exact 01-07Q / 01-07K integration state
- frozen unpushed AA r1 donor
- PostgreSQL dev/test databases

canonical_inputs:

- `AGENTS.md`
- `docs/architecture/memory-design-reference.md`
- `docs/implementation/e2e01-thin-slice-implementation-spec.md`
- `docs/implementation/e2e01-thin-slice-multi-agent-plan.md`
- `.planning/phases/01-cycle-1-e2e-01/01-07Q-PLAN.md`
- `.planning/phases/01-cycle-1-e2e-01/01-07K-PLAN.md`
- `.planning/phases/01-cycle-1-e2e-01/01-07AA-PLAN.md`
- `.planning/phases/01-cycle-1-e2e-01/01-07AA-CODEC-HANDOFF-PLAN.md`

required_checks:

```bash
uv sync --all-groups
docker compose up --wait -d db
docker compose --profile test up --wait -d db-test
uv run alembic upgrade head
uv run pytest tests/component/application/test_persistence_contract.py::test_codec_dependencies_are_scoped_without_active_routing_or_authority_claim -q
uv run pytest tests/component/application/test_persistence_contract.py tests/component/application/test_ports_contract.py -q
uv run pytest
```

composition_sidecar_checks:

```bash
uv run pytest tests/component/application/test_persistence_contract.py::test_codec_dependencies_are_scoped_without_active_routing_or_authority_claim tests/integration/test_postgres_v2_request_understanding_writes.py -q
uv run pytest tests/integration/test_postgres_v2_request_understanding_writes.py tests/integration/test_postgres_atomicity.py tests/integration/test_postgres_record_adapters.py -q
uv run pytest
```

contract_changes:

- `YES`：明确 dependency guard 的静态证明边界，并把 Postgres containment改为正向 use-site allowlist；不改变 codec、owner、authorization、active routing或readiness语义。

security_impact:

- `YES`：删除不可证明的“AST oracle 等于 Python sandbox”安全暗示；真实运行时安全边界不变，且项目继续禁止 untrusted Python执行。

eval_impact:

- `YES`：Component grader scope被精确化；AA composition / PostgreSQL / full-suite gates不变。

rollback:

- amendment未合并：不得按新边界复审或发布 feature；
- amendment已合并、feature未合并：普通 revert amendment merge，冻结 feature；
- feature已合并但 AA-r2未形成：先 revert feature，再 revert amendment；
- AA-r2 / `B_J_READY`已形成：按依赖逆序 revert 后继、feature、amendment，撤销 barrier claim并阻断 01-07J。

handoff_format:

- branch / commit / tree；
- planning base、feature base与actual changed files；
- required / sidecar commands及count；
- exact-head与latest-overlay reviewer、P0/P1/P2/P3；
- contract/security/eval impact；
- unresolved risks与rollback。

precheck:

- branch / worktree / `base_sha` 必须精确为 Packet 值；
- `git merge-base HEAD dc21e906183647c9fdf9aeffa47f256ad1a823ae` 必须等于 exact base；
- current unpublished head必须是base的线性后代，worktree clean；
- current changed files必须精确等于 `owned_files`，无merge commit。

postcheck:

- final head仍是 `dc21e906…` 的线性后代；
- changed files精确等于 `tests/component/application/test_persistence_contract.py`；
- `git diff --check dc21e906…HEAD` PASS；
- required / composition sidecar checks全部exit 0；
- exact-head与latest-integration overlay reviewer均为 `P0=0/P1=0/P2=0/P3=0 PASS`。

expected_results:

- feature baseline：focused `1 passed`、Application contracts按当时collection全绿、canonical full zero failure且既有credentialed deselection可保留；
- composition：renamed guard + 12 AA focused tests、111 neighbor tests与canonical full zero failure；
- exact counts若因已合并的合法测试增长发生变化，必须报告base/head collection差异，不得静默沿用旧数字。

done_when:

- repo gate只声明本 Plan 第3.1节的静态dependency证明边界；
- Postgres exact codec import/reference/call/method/body/scope由正向集合证明；
- nested class与generator-method adversarial均失败；
- single-file containment、required checks、fresh AA sidecar与两轮independent review全部PASS；
- squash merge tree精确等于reviewed latest-overlay tree并形成 `B_AA_CODEC_HANDOFF`。

handoff_to:

- `Integrator`：串行发布 feature PR、构建latest-integration overlay、合并并实例化 `B_AA_CODEC_HANDOFF`；
- `01-07AA acceptance-base amendment owner`：只从 exact `B_AA_CODEC_HANDOFF` 冻结后继 replay base。

## 5. 执行顺序

1. 本 amendment 在 dedicated planning-status Worktree 只写本文件。
2. 独立 reviewer 对 exact head给出 `P0=0/P1=0/P2=0/P3=0 PASS`。
3. 创建 Plan PR并串行 squash merge；merge tree必须等于reviewed tree。
4. feature仍以 `dc21e906…` 为 base，不rebase到Plan merge。
5. 在现有 feature branch追加单文件 cleanup commit：
   - 删除不可证明的任意 capability closure claim / helper；
   - 保留有界 repo static dependency checks；
   - 完成 Postgres positive use-site、nested class与generator-method约束。
6. 运行 required checks和fresh frozen-AA sidecar。
7. exact-head reviewer必须按本 amendment scope复审 actual code与AA source；不得把 guard描述为Python sandbox，也不得忽略实际恶意 reflection源码。
8. PASS后才push feature、建draft PR、运行latest-integration overlay review并串行merge。

## 6. Done When

- amendment exact head与merge tree一致；
- feature final diff仍精确单文件；
- repo gate不再声称 arbitrary Python capability closure；
- Postgres exact codec import/reference/call/method/body/scope均由正向集合证明；
- nested class与generator method adversarial均失败；
- feature `665` Application contracts、`1950` canonical suite及AA sidecar `13 / 111 / 1962`（或当时精确新增总数）全绿；
- exact-head与latest-overlay均独立 `PASS`；
- merge后形成的 barrier仅命名为 `B_AA_CODEC_HANDOFF`，不提前声称 `B_J_READY`。
