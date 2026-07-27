---
phase: 01-cycle-1-e2e-01
plan: 07H
type: tdd
wave: 16
depends_on:
  - 01-07C
  - 01-07G
files_modified:
  - src/mini_agent/core/order.py
  - tests/component/core/test_memory_trace_presentation_contract.py
  - tests/component/application/test_read_tool_executor.py
  - tests/component/application/test_agent_run_service.py
autonomous: true
requirements:
  - E2E01-01
  - E2E01-04
user_setup: []
must_haves:
  truths:
    - "GetOrderResult 新增 optional source_version；存在时只能是严格字符串并完整匹配 ^mock-order-source-version\\.p0\\.v1:sha256:[0-9a-f]{64}$，值 byte-for-byte 保留。"
    - "迁移期 FOUND + order_summary + None 继续合法；01-07H 不提前执行 01-07J/01-07K/01-07M 的 enforce、producer 或 final closure。"
    - "NOT_FOUND_OR_NOT_ACCESSIBLE 与 SYSTEM_FAILURE 均禁止任何 non-None source_version，且现有 order_summary / failure_code 矩阵不变。"
    - "空串、错误 prefix/schema、63/65 位 hex、大写、首尾空白、换行和 bytes 均被拒绝；没有 coercion、trim、大小写归一、fallback 或 fixed-vector 借用。"
    - "六个 Application FOUND 测试替身使用明显合成、pattern-valid 的 64 个 a token；PostgreSQL producer 的 FOUND + None 保持原样且现有 Integration test 不修改并通过。"
    - "Agent-visible get_order ToolSpec.output_schema 仍不含 source_version；H 不生成、重算、传播或公开 token。"
    - "本 Packet 只修改一个 Core DTO 文件及三个 owned Component test 文件，不改 Runtime/Application source、Infra、Memory、ToolSpec、HTTP、Eval、migration 或 toolchain。"
  artifacts:
    - "src/mini_agent/core/order.py 中 optional strict source_version 表示与 outcome validator。"
    - "三个 owned Component test 文件中的 RED/GREEN contract matrix、六个合成 FOUND stub 与 Agent-visible schema 非暴露断言。"
  key_links:
    - "01-07G owner §6.2.1 additive-expand 行 → GetOrderResult.source_version strict optional field。"
    - "01-07H 与同 wave 的 01-07D 均只从 B_CG 签发、互不依赖；二者 allowlist 必须不相交并由 Integrator 串行集成后才可签发 01-07E/01-07F。"
---

# Phase 1 Plan 01-07H｜GetOrderResult source_version additive expand

> **ISSUED ADDITIVE-EXPAND TASK PACKET / IMPLEMENTATION NOT STARTED**
> 本 Packet 只增加 `GetOrderResult` 对受控 source-version token 的可选表示与严格验证能力。它不把 token 变成 authority，不执行最终 FOUND completeness gate，也不改变当前 PostgreSQL producer。

> **DERIVED / NON_NORMATIVE**
> source-version 语义由 Thin Slice scoped owner 拥有；本 Plan 只把其 expand 阶段映射为一个精确 Core / Order Task Packet，不反向覆盖 owner、Tool、Memory 或 Eval contract。

<objective>
以 TDD RED→GREEN 为 `GetOrderResult` 增加 optional、strict、exact-pattern 的 `source_version`，并迁移 owned Application FOUND 测试替身。

Purpose: 为后续 01-07J Runtime enforce、01-07K producer 与 01-07M Core closure 提供可独立全绿的 additive representation。

Output: 三个 test-only RED 文件与一个 Core GREEN 文件，形成两个有序原子提交。
</objective>

<execution_context>
@AGENTS.md
@.planning/GOVERNANCE.md
@.planning/phases/01-cycle-1-e2e-01/01-07C-PLAN.md
@.planning/phases/01-cycle-1-e2e-01/01-07G-PLAN.md
@docs/implementation/e2e01-thin-slice-implementation-spec.md
@src/mini_agent/core/order.py
@src/mini_agent/core/tool_system.py
@tests/component/core/test_memory_trace_presentation_contract.py
@tests/component/application/test_read_tool_executor.py
@tests/component/application/test_agent_run_service.py
@tests/integration/test_postgres_get_order.py

只使用受控 execution adapter；不得调用 stock `gsd-plan-phase`、`gsd-execute-phase`、`gsd-verify-work`、lifecycle mutation 或 `gsd-ship`。不得引用 B_CG 中不存在的 01-07C / 01-07G Summary 作为执行输入。
</execution_context>

<interfaces>
当前 `GetOrderResult` 是 frozen `RuntimePrivateModel`，字段为 `outcome`、`order_summary`、`failure_code`；validator 已要求 FOUND 有 summary 且无 failure_code、所有 non-FOUND 无 summary、safe not-found 无 differentiated failure code。GREEN 只能 additive 增加：

```python
GetOrderSourceVersion = Annotated[
    str,
    Field(
        strict=True,
        pattern=r"^mock-order-source-version\.p0\.v1:sha256:[0-9a-f]{64}$",
    ),
]

class GetOrderResult(RuntimePrivateModel):
    source_version: GetOrderSourceVersion | None = None
```

`get_order_tool_spec().output_schema["properties"]` 当前只有 Agent-visible `outcome`、`order_summary` 与 `failure_code`；H 不修改该 Schema。
</interfaces>

<packet_contract>
repository: `https://github.com/weijie567/mini-agent`
remote: `origin`
head_branch: `codex/e2e01-01-order-source-version-additive-expand`
base_branch: `integration/e2e01-thin`
base_sha: `327b39da45cdcf564609a5385d52c4264da2c669`
base_tree: `49ad0f3f5fc2c0cbe507763aca12bb6825fb7887`
worktree_id: `e2e01-01-order-source-version-additive-expand`
writer: `Core / Order sole writer with owned tests, supervised by /root Integrator`
agent_role: `runtime-engineer`

物理 Worktree path 只在 private dispatch handoff 中传递，不写入 Plan、commit 或 PR。

planning_and_owner_provenance:

- 01-07C Plan current commit `79ae0a921cb8a6ff64f308ddf377c93354701cf8`，blob `66a3a974f5d7408239b8ba3691abdb0c1781fa63`
- 01-07G Plan commit `2b746d50a4c52d8d4193e6049d7859f65b40e8f5`，blob `72c866f0afac449c7c9970c223c9eb182fb1e780`
- Thin Slice source-version ruling commit `bfc63c9444ee1af204cc3806eac7e7e84fc1bb19`，owner blob `538105706f471dabe9cf8964d1026c4abf484356`
- 本 Plan 的 official planning merge SHA / blob 由 Integrator 在 planning-status PR reviewed merge 后从 official integration ref 捕获；本地未合并 blob 不能作为 execution provenance

owned_files:

- `src/mini_agent/core/order.py` = `fab765d29008b90b13d58f2a2ab1da9b22151c8d`
- `tests/component/core/test_memory_trace_presentation_contract.py` = `c4d8f59ed0396cd6edcd40bef73da9e2b21ac9b3`
- `tests/component/application/test_read_tool_executor.py` = `6e47672b4863a8dc27773b8bb337b6637a541a20`
- `tests/component/application/test_agent_run_service.py` = `045b7ea34ce75c0fa3f6526927b4906df814fe43`

canonical_inputs:

- `AGENTS.md` 与 `.planning/GOVERNANCE.md`：项目级写入边界、Task Packet 与 security / Eval / rollback 规则。
- `.planning/phases/01-cycle-1-e2e-01/01-07C-PLAN.md`：commit `79ae0a921cb8a6ff64f308ddf377c93354701cf8`，blob `66a3a974f5d7408239b8ba3691abdb0c1781fa63`；提供 Request Understanding durable semantic ruling，以及 C/G reviewed merge 后记录 common exact integration barrier、再签发 D/H 的输入，不拥有 Order Core contract。
- `.planning/phases/01-cycle-1-e2e-01/01-07G-PLAN.md`：commit `2b746d50a4c52d8d4193e6049d7859f65b40e8f5`，blob `72c866f0afac449c7c9970c223c9eb182fb1e780`；提供 additive-expand 与 common-barrier 裁决。
- `docs/implementation/e2e01-thin-slice-implementation-spec.md`：commit `bfc63c9444ee1af204cc3806eac7e7e84fc1bb19`，blob `538105706f471dabe9cf8964d1026c4abf484356`；§6.1 拥有 scoped Agent-visible ToolSpec，§6.2.1 拥有第一最薄切片 `get_order` 的具体 source-version 编码。
- 冻结的 B_CG 输入：`src/mini_agent/core/order.py` blob `fab765d29008b90b13d58f2a2ab1da9b22151c8d`；`tests/component/core/test_memory_trace_presentation_contract.py` blob `c4d8f59ed0396cd6edcd40bef73da9e2b21ac9b3`；`tests/component/application/test_read_tool_executor.py` blob `6e47672b4863a8dc27773b8bb337b6637a541a20`；`tests/component/application/test_agent_run_service.py` blob `045b7ea34ce75c0fa3f6526927b4906df814fe43`。这些 blob 是实现输入，不升级为 canonical authority。
- B_CG 只读反馈输入：`src/mini_agent/core/tool_system.py` blob `8da111b17eb7c331702a21cdcaca66798d2d20ac` 提供 `get_order_tool_spec()`；`src/mini_agent/infrastructure/order/postgres.py` blob `e1909e06bac2e64b8349154f66c2b777164f1847` 是 legacy producer；`tests/integration/test_postgres_get_order.py` blob `df6bef3de4c4925f4ccbc2cdf6bc071beb2a0b42` 提供 unchanged PostgreSQL regression evidence。三者均为只读，不得借本包修改。
- 执行前由 Integrator 记录 official planning merge SHA、该 SHA 下的 `01-07H-PLAN.md` blob 与精确 feature `base_sha`；任一 provenance 缺失即 `BLOCK`。

forbidden_files:

- every repository path outside the four exact owned files
- especially `AGENTS.md`、`README.md`、`PROJECT_DIRECTION.md`、`docs/**`、`.planning/**`、`src/mini_agent/application/**`、`src/mini_agent/runtime/**`、`src/mini_agent/infrastructure/**`、other `src/mini_agent/core/**`、other `tests/**`、`evals/**`、`alembic/**`、`pyproject.toml`、`uv.lock`、`compose.yaml`、`graphify-out/**`
- specifically `src/mini_agent/core/memory.py`、`src/mini_agent/core/tool_system.py`、`tests/integration/test_postgres_get_order.py`

dependencies:

- 首次编辑前，feature Worktree 必须证明branch精确匹配、`HEAD == B_CG`、tree/merge-base/四个owned blob精确匹配且`git status --short`为空；official planning head中的四个owned blob也必须与B_CG相同。
- 01-07H 依赖 01-07C 与 01-07G 的 reviewed merge，不依赖同 wave 的 01-07D；H 与 D 都必须以 B_CG 为 merge-base。
- Integrator 在 dispatch 前取得 official 01-07D Plan allowlist；D/H allowlist 交集非空立即 `BLOCK`。
- D/H feature PR 各自先对 exact feature head 独立 review，再由 Integrator 串行合并；后合并者必须在 latest integration overlay 重跑全部门禁并取得独立 exact-head review。
- 只有 D/H 均 reviewed merge 且 combined integration head 全绿后，才可签发 01-07E / 01-07F。

required_checks:

- `source_version` 是 optional；FOUND + summary + None 在 H 后仍合法。
- non-None 值必须是 strict `str` 且完整匹配 exact regex；不得 coercion、strip、normalize、case-fold、parse、rehash 或 fallback。
- FOUND 可携带 exact valid token并 byte-for-byte 保留；所有 non-FOUND 均拒绝 non-None token。
- 现有 summary / failure_code outcome matrix逐项保留。
- RED 覆盖 legacy None、valid exact-copy、empty、wrong prefix、wrong schema、63/65 hex、uppercase、leading/trailing whitespace、newline、bytes，以及两种 non-FOUND + valid token。
- `test_read_tool_executor.py` 与 `test_agent_run_service.py` 各自逐文件定义 exact literal `SYNTHETIC_SOURCE_VERSION = "mock-order-source-version.p0.v1:sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"`；前者五个 FOUND stub 与后者一个 `_found_result` 恰好六处显式传入该常量。
- 合成 token 不是 authority；不得使用 owner 的 `861c136b...` fixed vector，因为这些 stub 的安全投影与 owner Fixture 不同。
- `get_order_tool_spec().output_schema` 不出现 `source_version`；PostgreSQL FOUND + None 继续通过未修改的 Integration test。
- H 不生成或验证内容 authority，不复制到 Observation / Manifest，不改变 schema fallback、ToolSpec、HTTP、Eval、producer、migration 或 toolchain。
- PostgreSQL / full-suite 前必须完成 `uv sync --all-groups`、`docker compose --profile test up --wait -d db-test` 与容器内 `pg_isready`；不得用 `down -v`、prune、删除数据或其他 broad teardown。
- `BLOCK` 条件：D/H allowlist 交集不为零；B_CG / canonical provenance 漂移；RED 未因当前 DTO 缺少 additive `source_version` contract 而失败，或 GREEN 后 `FOUND + None` 不再可构造；non-FOUND 可携带 metadata；owner fixed vector 污染 synthetic stub；任一 focused / PostgreSQL / full-suite / frontmatter / structure / scope / hygiene check 失败；review 未满足；或所有 commit/check 完成后 `git status --short --untracked-files=all` 非空。

cross_file_impact:

- Thin Slice owner与multi-agent执行视图均已明确H additive、J enforce、K produce、M close，未发现active contract冲突。
- B_CG中的`.planning/ROADMAP.md`、`.planning/STATE.md`与`.planning/REQUIREMENTS.md`仍把H描述为未签发/blocked或C/G未执行；它们是本Packet禁止修改的derived status surface，不覆盖exact base与owner裁决。
- Integrator必须在独立single-writer planning/status PR中对齐这些derived状态；feature writer只报告差异，不得声称repository-wide aligned或推进lifecycle。

commit_protocol:

1. RED commit `test(01-07H): define additive get_order source version contract` 只改三个 owned test 文件；Core source blob仍等于 B_CG，focused command因新增 source_version contract 断言而失败，不得因 import/syntax/fixture错误失败。
2. GREEN commit `feat(01-07H): add optional strict get_order source version` 只改 `src/mini_agent/core/order.py`；focused、unchanged PostgreSQL integration 与 full suite 全绿。
3. 正常 feature history 相对 B_CG 恰为以上两个提交。Review finding 若需要修复，先 `BLOCK` ready 状态；修复只能留在四文件 allowlist、使用独立 `fix(01-07H): ...` commit，并对新 exact head 重跑全套 review，不得 amend/rebase/force-push已审历史。

done_when:

- RED 与 GREEN 顺序、原因、命令、commit SHA 可复现；四文件以外零变化。
- strict optional field、完整 outcome matrix、六个合成 stub 与 no-Agent-schema 断言全部通过。
- unchanged PostgreSQL Integration test与完整 `uv run pytest` 通过。
- feature / latest-integration overlay exact-head review unresolved `CRITICAL / HIGH / MEDIUM = 0 / 0 / 0`。
- draft PR 精确使用 head branch → `integration/e2e01-thin`，不推进 Case / Requirement / Phase lifecycle。

contract_changes: `YES / ADDITIVE CORE DTO ONLY` — 新增 optional strict runtime-private `GetOrderResult.source_version`；不改变最终 FOUND completeness、Agent-visible、HTTP、Memory或producer contract。
security_impact: `YES / REPRESENTATION ONLY` — H 只拒绝 malformed / coercible representation，并阻止 non-FOUND 携带 metadata；任何 pattern-valid forged token 在 H 阶段仍可表示。authority / spoofing prevention 仅由 trusted 01-07K producer 建立，并由 01-07J acceptance 与 01-07M closure fail closed；token 永不授权且不向模型/用户披露。
eval_impact: `YES / COMPONENT REGRESSION ONLY` — owned Component tests增加 contract matrix并迁移六个 stub；不改 EvalCase、Dataset、Grader、Result、threshold或lifecycle。
new_dependencies: `NONE`
graphify_disposition: `INTEGRATOR POST-MERGE GATE` — feature writer不改图；合并后 Integrator 运行 `graphify update .`，若工具/图不可用则记录 `NOT_RUN` 并用 source scan验证 owner/consumer关系，不声称图已fresh。
rollback: 合并前关闭 PR；合并后用普通 revert PR 按 `${base_sha}..feature_head` 的严格逆序撤销 feature range 内每一个 commit，包括所有 `fix(01-07H): ...` review-fix commit；随后重新阻塞完整传递链 01-07E、01-07F、01-07I、01-07J、01-07K、01-07L、01-07M、01-08、01-08A。不得 reset、force-push、删除/改写数据、声称 data migration，或发明 schema / data migration rollback。

handoff_to: `/root Integrator`
handoff_format: branch、exact base/planning/head/commits/tree、Plan与四个base/head blobs、RED/GREEN输出、changed files/commit containment、六stub计数、schema/Integration/full-suite结果、cross-file scan、contract/security/Eval nonclaims、feature/overlay review、风险与rollback。
</packet_contract>

<source_coverage_audit>

| source | item | status | implementation |
|---|---|---|---|
| GOAL | owner 的 01-07H additive expand | COVERED | Task 1 RED + Task 2 GREEN |
| REQ | `E2E01-01` safe FOUND representation | COVERED | strict optional token与legacy compatibility |
| REQ | `E2E01-04` non-FOUND indistinguishability | COVERED | 两种 non-FOUND均禁止 token，原矩阵不变 |
| RESEARCH | Phase W2 research为`NON_NORMATIVE`，本Packet无新增research scope | EXCLUDED | 以active owner和exact base为准 |
| CONTEXT | 本次dispatch冻结的base/allowlist/matrix/commit/review rulings | COVERED | packet contract与两项task逐项落实 |

无未规划项；01-07J/K/M、01-07D/E/F属于已命名依赖边界，不是本 Packet 缺口。
</source_coverage_audit>

<threat_model>

| threat_id | category | boundary | disposition | mitigation |
|---|---|---|---|---|
| `OSVA-S01` | Spoofing | caller/model → source_version | `TRANSFER / DEFERRED` | H 不阻止 pattern-valid forged token；authority / spoofing prevention 仅由 trusted 01-07K producer 建立，01-07J acceptance 与 01-07M closure 必须 fail closed |
| `OSVA-T01` | Tampering | malformed token → Core DTO | `MITIGATE / BLOCK` | 完整regex和negative matrix；无coercion/trim/case normalization |
| `OSVA-R01` | Repudiation | RED/GREEN →交接证据 | `MITIGATE / BLOCK` | 两个有序原子commit、base blobs、focused/full输出和exact-head review |
| `OSVA-I01` | Information Disclosure | DTO → Agent-visible schema | `MITIGATE / BLOCK` | ToolSpec schema absence机械断言；禁止ToolSpec/HTTP/Trace/Presentation修改 |
| `OSVA-D01` | Denial of Service | expand期legacy producer → DTO | `MITIGATE / BOUNDED` | FOUND + None保持合法；PostgreSQL test不改且通过 |
| `OSVA-E01` | Elevation of Privilege | valid-looking token → authorization | `MITIGATE / BLOCK` | token 永不授权；H 仅校验 representation，可信 producer authority 留给 01-07K，最终接受/关闭留给 01-07J / 01-07M |
</threat_model>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: RED — freeze additive DTO and six-stub behavior matrix</name>
  <files>tests/component/core/test_memory_trace_presentation_contract.py, tests/component/application/test_read_tool_executor.py, tests/component/application/test_agent_run_service.py</files>
  <read_first>Thin Slice owner §6.1/§6.2.1、01-07G Plan、四个 B_CG owned blobs、current GetOrderResult validator、get_order_tool_spec、unchanged PostgreSQL integration test</read_first>
  <behavior>
    - FOUND + summary + None accepted; valid token accepted and byte-for-byte equal.
    - empty/wrong prefix/wrong schema/63/65 hex/uppercase/leading/trailing whitespace/newline/bytes rejected.
    - NOT_FOUND_OR_NOT_ACCESSIBLE + valid token and SYSTEM_FAILURE + valid token rejected while existing failure_code rules remain.
    - exactly six Application FOUND stubs use the synthetic 64-a token; ToolSpec remains source_version-free.
  </behavior>
  <action>只改三个test文件。把完整参数矩阵加入Core contract test；直接断言`get_order_tool_spec().output_schema["properties"]`不含`source_version`。在两个Application test文件各定义 exact literal `SYNTHETIC_SOURCE_VERSION = "mock-order-source-version.p0.v1:sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"`，迁移已定位的五加一FOUND构造点，不增加第七处，不使用owner fixed vector；现有PostgreSQL test不改。运行focused command取得因当前DTO拒绝extra `source_version`而产生的真实RED，然后提交精确RED message。</action>
  <verify>
    <automated>uv run pytest tests/component/core/test_memory_trace_presentation_contract.py tests/component/application/test_read_tool_executor.py tests/component/application/test_agent_run_service.py -q</automated>
    RED必须非零退出且新失败指向缺少additive field；production source、shared bootstrap、Integration/Eval文件保持B_CG字节。
  </verify>
  <acceptance_criteria>三个test文件覆盖全部矩阵；两个指定Application test逐文件各有且只有一个exact 64-lowercase-a constant assignment，FOUND stub使用按5+1分布且总计恰为六个`source_version=SYNTHETIC_SOURCE_VERSION`，owner fixed vector缺席；RED commit只含三个test文件。</acceptance_criteria>
  <done>行为先于实现被固定，失败原因正确且可复现。</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: GREEN — add strict optional source_version without downstream wiring</name>
  <files>src/mini_agent/core/order.py</files>
  <read_first>Task 1 RED commit/output、current order.py、Thin Slice additive row与最终矩阵的阶段区分</read_first>
  <behavior>
    - strict exact-pattern values pass unchanged; every directed malformed/coercible value fails.
    - FOUND None compatibility and all pre-existing summary/failure rules remain.
    - both non-FOUND outcomes reject every non-None source_version.
  </behavior>
  <action>在`order.py`增加接口块中的`GetOrderSourceVersion` exact alias与`source_version: GetOrderSourceVersion | None = None`。扩展现有`result_shape_matches_outcome`：FOUND不要求version；任何non-FOUND且`source_version is not None`都抛出bounded validation error；其余分支原样保留。不要新增validator做strip/normalize/fallback，不导入hash/json，不触碰Application/Infra/Memory/ToolSpec。focused、schema-absence、unchanged PostgreSQL integration与full suite全绿后提交精确GREEN message。</action>
  <verify>
    <automated>uv sync --all-groups
uv run pytest tests/component/core/test_memory_trace_presentation_contract.py tests/component/application/test_read_tool_executor.py tests/component/application/test_agent_run_service.py -q
uv run python -c 'from mini_agent.core.tool_system import get_order_tool_spec; assert "source_version" not in get_order_tool_spec().output_schema["properties"]'
docker compose --profile test up --wait -d db-test
docker compose --profile test exec -T db-test sh -ec 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
uv run pytest tests/integration/test_postgres_get_order.py -q
uv run pytest</automated>
  </verify>
  <acceptance_criteria>四文件diff、两个有序commit、strict matrix、六stub、ToolSpec non-exposure、unchanged Integration和full suite全部通过。</acceptance_criteria>
  <done>H additive contract完成且没有提前实现J/K/M或越过owner boundary。</done>
</task>

</tasks>

<verification>

```bash
set -euo pipefail

base_sha=327b39da45cdcf564609a5385d52c4264da2c669
base_tree=49ad0f3f5fc2c0cbe507763aca12bb6825fb7887
expected_branch=codex/e2e01-01-order-source-version-additive-expand

test "$(git branch --show-current)" = "$expected_branch"
test "$(git rev-parse "${base_sha}^{tree}")" = "$base_tree"
test "$(git merge-base HEAD "$base_sha")" = "$base_sha"
test "$(git rev-parse "${base_sha}:src/mini_agent/core/order.py")" = fab765d29008b90b13d58f2a2ab1da9b22151c8d
test "$(git rev-parse "${base_sha}:tests/component/core/test_memory_trace_presentation_contract.py")" = c4d8f59ed0396cd6edcd40bef73da9e2b21ac9b3
test "$(git rev-parse "${base_sha}:tests/component/application/test_read_tool_executor.py")" = 6e47672b4863a8dc27773b8bb337b6637a541a20
test "$(git rev-parse "${base_sha}:tests/component/application/test_agent_run_service.py")" = 045b7ea34ce75c0fa3f6526927b4906df814fe43

test "$(git diff --name-only "${base_sha}...HEAD" | LC_ALL=C sort)" = $'src/mini_agent/core/order.py\ntests/component/application/test_agent_run_service.py\ntests/component/application/test_read_tool_executor.py\ntests/component/core/test_memory_trace_presentation_contract.py'
git diff --check "${base_sha}...HEAD"
test "$(git rev-list --count "${base_sha}..HEAD")" -ge 2
test "$(git log --reverse --format=%s "${base_sha}..HEAD" | sed -n '1p')" = "test(01-07H): define additive get_order source version contract"
test "$(git log --reverse --format=%s "${base_sha}..HEAD" | sed -n '2p')" = "feat(01-07H): add optional strict get_order source version"
test "$(git log --reverse --format=%s "${base_sha}..HEAD" | sed -n '3,$p' | awk '!/^fix\\(01-07H\\): / {bad++} END {print bad+0}')" -eq 0

red_sha=$(git rev-list --reverse "${base_sha}..HEAD" | sed -n '1p')
green_sha=$(git rev-list --reverse "${base_sha}..HEAD" | sed -n '2p')
test "$(git diff-tree --no-commit-id --name-only -r "$red_sha" | LC_ALL=C sort)" = $'tests/component/application/test_agent_run_service.py\ntests/component/application/test_read_tool_executor.py\ntests/component/core/test_memory_trace_presentation_contract.py'
test "$(git diff-tree --no-commit-id --name-only -r "$green_sha")" = "src/mini_agent/core/order.py"
test "$(git log --format= --name-only "${base_sha}..HEAD" | sed '/^$/d' | LC_ALL=C sort -u)" = $'src/mini_agent/core/order.py\ntests/component/application/test_agent_run_service.py\ntests/component/application/test_read_tool_executor.py\ntests/component/core/test_memory_trace_presentation_contract.py'

synthetic_token=mock-order-source-version.p0.v1:sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
for synthetic_file in \
  tests/component/application/test_read_tool_executor.py \
  tests/component/application/test_agent_run_service.py
do
  test "$(rg -n -F -x "SYNTHETIC_SOURCE_VERSION = \"$synthetic_token\"" "$synthetic_file" | wc -l | tr -d ' ')" -eq 1
done
test "$(rg -n -F 'outcome=GetOrderOutcome.FOUND' tests/component/application/test_read_tool_executor.py | wc -l | tr -d ' ')" -eq 5
test "$(rg -n -F 'outcome=GetOrderOutcome.FOUND' tests/component/application/test_agent_run_service.py | wc -l | tr -d ' ')" -eq 1
test "$(rg -n -F 'source_version=SYNTHETIC_SOURCE_VERSION' tests/component/application/test_read_tool_executor.py | wc -l | tr -d ' ')" -eq 5
test "$(rg -n -F 'source_version=SYNTHETIC_SOURCE_VERSION' tests/component/application/test_agent_run_service.py | wc -l | tr -d ' ')" -eq 1
! rg -n '861c136b1a41ecef3cd9625dc58524ec452e939b5ca1eb70ebcab69181561c42' tests/component/application/test_read_tool_executor.py tests/component/application/test_agent_run_service.py

uv sync --all-groups
uv run pytest tests/component/core/test_memory_trace_presentation_contract.py tests/component/application/test_read_tool_executor.py tests/component/application/test_agent_run_service.py -q
uv run python -c 'from mini_agent.core.tool_system import get_order_tool_spec; assert "source_version" not in get_order_tool_spec().output_schema["properties"]'
docker compose --profile test up --wait -d db-test
docker compose --profile test exec -T db-test sh -ec 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
uv run pytest tests/integration/test_postgres_get_order.py -q
uv run pytest

rg -n 'GetOrderResult|source_version|get_order_tool_spec|PostgresGetOrderAdapter' docs src tests evals
test -z "$(git status --short --untracked-files=all)"
```

Feature writer交接exact containment后，Integrator还必须做D/H allowlist交集检查、latest-integration overlay、两个exact-head independent review、PR conversation resolution、combined-head full suite与post-merge Graphify/source-scan gate。

`db-test` 是共享验证依赖且数据目录为 tmpfs；默认在 handoff 中报告由谁启动并保持运行。只有 Integrator 明确分配 teardown 时才可执行 narrow `docker compose --profile test stop db-test`；禁止 `docker compose down`、`down -v`、`rm`、prune、volume/data 删除或影响 `db` 服务。

下列任一情况均为`BLOCK`：D/H allowlist相交；任一owned B_CG blob或canonical provenance drift；FOUND + None被拒绝；owner/fixed-vector/任何forbidden source被修改；两个指定test的exact constant、5+1/六stub计数或fixed-vector absence不符；ToolSpec暴露；env/readiness/focused/Integration/full test失败；commit顺序或scope不符；feature/overlay review失败；存在未关闭`CRITICAL / HIGH / MEDIUM`；最终`git status --short --untracked-files=all`非空。
</verification>

<success_criteria>

1. `GetOrderResult.source_version`是optional strict exact-pattern字段，valid值exact-copy，所有negative matrix与non-FOUND prohibition通过。
2. Legacy FOUND + None和未修改PostgreSQL producer/test保持可用；summary/failure矩阵无回归。
3. 六个Application stub只使用合成token；Agent-visible schema、Observation/Manifest、Runtime/Infra/Eval均无新wiring。
4. RED→GREEN、四文件containment、full suite、cross-file scan、feature/overlay exact-head review均有可复现证据。
5. H与D串行集成后才解锁E/F；Plan或测试通过不宣称最终source-version链路、E2E、Case lifecycle或产品完成。

</success_criteria>

<output>
完成后不创建Summary或共享State。Executor只按`handoff_format`交接；Integrator在reviewed merge后另行索引证据并执行Graphify/combined-head/status门禁。
</output>
