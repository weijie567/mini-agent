---
phase: 01-cycle-1-e2e-01
plan: 07M
type: tdd
wave: 23
depends_on:
  - 01-07K
  - 01-07L
files_modified:
  - src/mini_agent/core/order.py
  - tests/component/core/test_memory_trace_presentation_contract.py
autonomous: true
requirements:
  - E2E01-01
  - E2E01-04
user_setup: []
must_haves:
  truths:
    - "01-07M 只执行 DEPENDENCY_EXPAND 的 Core contract closure：GetOrderResult.FOUND 必须同时携带安全 order_summary 与 non-empty exact-pattern source_version，并继续禁止 failure_code。"
    - "GetOrderResult.source_version 的 strict 类型、完整 regex 与 byte-for-byte 值保持不变；M 只把 FOUND + None 从临时迁移态收紧为固定 bounded validation failure。"
    - "NOT_FOUND_OR_NOT_ACCESSIBLE 与 SYSTEM_FAILURE 继续禁止任何 non-None source_version；既有 order_summary / failure_code 矩阵不得漂移。"
    - "01-07M 只从 exact B_DEPENDENCY 签发；01-07K authoritative PostgreSQL producer与01-07L Eval consumers已经reviewed、串行merge，但M不得修改或重新实现它们。"
    - "通用 persisted historical OrderObservation.source_version? 继续 optional；M不做backfill、read-time migration、physical schema/Alembic变化或全局Memory字段升级。"
    - "source_version 仍是Runtime-private snapshot metadata，不进入Agent-visible ToolSpec、Provider输入、Presentation、HTTP响应、用户回复或普通Trace，也不授予权限。"
    - "01-07M 不修改Application/Infrastructure/Runtime/Eval、active codec/registry、Composition Root、Case lifecycle或readiness；reviewed feature merge只形成B_DEPENDENCY_M并解锁01-07Q的规划入口。"
  artifacts:
    - "src/mini_agent/core/order.py 中只收紧 GetOrderResult.result_shape_matches_outcome 的 FOUND completeness gate。"
    - "tests/component/core/test_memory_trace_presentation_contract.py 中把唯一 legacy FOUND + None oracle替换为最终required matrix。"
  key_links:
    - "Thin Slice §6.2.1 final outcome matrix → GetOrderResult.FOUND source_version required validation。"
    - "01-07K same-read authoritative producer → M闭合后的所有正常PostgreSQL FOUND继续可构造。"
    - "Memory owner historical OrderObservation.source_version? → 保持scoped optional，不被Core Result closure反向升级。"
    - "P0-RU-V2-EXECUTION-MAP：B_DEPENDENCY → 01-07M → B_DEPENDENCY_M → 01-07Q；M不执行active switch。"
---

# Phase 1 Plan 01-07M｜GetOrderResult source-version contract closure

> **ISSUED CORE CONTRACT-CLOSURE TASK PACKET / IMPLEMENTATION NOT STARTED**
> 本 Packet 只关闭 `GetOrderResult.FOUND + source_version=None` 的临时迁移能力。Plan签发、Component test或M feature完成都不表示active codec、Runtime v2、真实HTTP纵向链、Trajectory / E2E Result或产品ready。

> **DERIVED / NON_NORMATIVE**
> 业务、Memory、Thin Slice source-version语义与execution order仍由active canonical owner拥有。本Plan只把现行最终矩阵映射为一个精确Core Task Packet，不维护第二套产品、Memory或Eval合同。

> **EXECUTION PREFLIGHT AMENDMENT / ZSH REVISION SYNTAX**
> 首次feature Gate A在clean exact-base Worktree复现：zsh会把未加花括号的`base_sha` revision插值解析为parameter modifier，导致错误revision。四处blob preflight已统一使用braced parameter expansion；本修订不改变feature base、两文件ownership、RED/GREEN、合同、安全、Eval、active routing或barrier顺序。

<objective>
以TDD RED→GREEN把`GetOrderResult.FOUND.source_version`从01-07H的strict optional迁移态闭合为non-empty exact-pattern必填，同时完整保留所有non-FOUND prohibition与边界非暴露规则。

Purpose: 在reviewed 01-07K producer与01-07L consumers共同barrier之后，移除Core DTO中最后一个可经正常validation构造`FOUND + None`的入口，为后续01-07Q active codec switch提供单一精确输入barrier。

Output: 一个只改owned Core test的RED commit和一个只改`GetOrderResult`既有validator的GREEN commit；不创建Summary，不修改共享State、canonical owner或任何下游实现。
</objective>

<execution_context>
@AGENTS.md
@.planning/GOVERNANCE.md
@.planning/phases/01-cycle-1-e2e-01/01-07G-PLAN.md
@.planning/phases/01-cycle-1-e2e-01/01-07H-PLAN.md
@.planning/phases/01-cycle-1-e2e-01/01-07K-PLAN.md
@.planning/phases/01-cycle-1-e2e-01/01-07L-PLAN.md
@docs/architecture/memory-design-reference.md
@docs/implementation/e2e01-thin-slice-implementation-spec.md
@docs/implementation/e2e01-thin-slice-multi-agent-plan.md
@src/mini_agent/core/order.py
@tests/component/core/test_memory_trace_presentation_contract.py
@src/mini_agent/core/tool_system.py
@src/mini_agent/infrastructure/order/postgres.py

只使用项目受控execution adapter；不得调用stock `gsd-plan-phase`、`gsd-execute-phase`、`gsd-verify-work`、lifecycle mutation或`gsd-ship`。Graphify按用户指令保持闲置：不读取、不运行、不更新，也不作为gate。
</execution_context>

<interfaces>

## 1. Exact Core delta

`GetOrderSourceVersion`和`GetOrderResult`字段声明保持B_DEPENDENCY字节：

```python
GetOrderSourceVersion = Annotated[
    str,
    Field(
        strict=True,
        pattern=r"^mock-order-source-version\.p0\.v1:sha256:[0-9a-f]{64}$",
    ),
]

class GetOrderResult(RuntimePrivateModel):
    outcome: GetOrderOutcome
    order_summary: OrderSummaryProjection | None = None
    source_version: GetOrderSourceVersion | None = None
    failure_code: NonEmptyString | None = None
```

字段必须继续允许`None`，因为两个non-FOUND outcome合法地省略该字段；M只能在既有`result_shape_matches_outcome`的FOUND branch中追加：

```python
if self.source_version is None:
    raise ValueError("FOUND result requires source_version")
```

检查必须位于既有`order_summary` required与`failure_code` prohibition之后，从而保留现有negative-case错误优先级：缺summary仍报告`FOUND result requires order_summary`，携带failure code仍报告`FOUND result cannot carry failure_code`，只有前两项均合法且version缺失时才报告新错误。错误文本必须是上述固定bounded字符串，不包含token、summary、identity、模型输入或raw exception。不得：

- 把field声明改成全局required，从而破坏non-FOUND构造；
- 新增第二个validator、model hook、factory、alias、normalizer或fallback；
- trim、case-fold、parse、rehash、重算、替换或生成token；
- 修改`GetOrderSourceVersion` pattern、strictness、schema或现有outcome enum；
- 使用`model_construct`、unchecked `model_copy`或其他绕过validation的路径伪装合同已闭合。

## 2. Final outcome matrix

| outcome | order_summary | source_version | failure_code | M result |
|---|---|---|---|---|
| `FOUND` | required safe projection | required、strict、exact pattern、byte-for-byte | forbidden | valid |
| `NOT_FOUND_OR_NOT_ACCESSIBLE` | forbidden | forbidden | forbidden | valid without payload |
| `SYSTEM_FAILURE` | forbidden | forbidden | existing bounded code only | valid without payload |

原有empty、wrong prefix/schema、63/65 hex、uppercase、leading/trailing whitespace、newline与bytes negative matrix必须继续失败。M的新增RED把唯一`legacy_result`断言替换为三项闭合矩阵：`FOUND + summary + omitted source_version`匹配`FOUND result requires source_version`；同时缺summary/version仍优先匹配`FOUND result requires order_summary`；携带summary/failure且缺version仍优先匹配`FOUND result cannot carry failure_code`。valid exact token仍成功并exact-copy，其他39-test baseline behavior保持不变。

## 3. Boundary nonchanges

- 01-07K `PostgresGetOrderAdapter`已经从同一次owner-scoped strict read生成exact token；M不读取数据库、不验证authority来源、不修改Adapter。
- pattern-valid token本身不是授权凭据；Core validation只证明表示与completeness，trusted authority仍来自K producer和服务端身份边界。
- `OrderObservation.source_version: ... | None`及历史持久化records保持原样；旧记录可继续解码，但不能支持新的Presentation Manifest或通过最终Eval evidence。
- `get_order_tool_spec().output_schema["properties"]`继续不含`source_version`；M不修改ToolSpec、Provider、Presentation、HTTP、Trace或Renderer。
- 01-07Q、01-07J与01-08仍是独立后续Packet；M不active-route、不捕获Provider signal、不创建Observation/Manifest，也不宣告Case通过。

</interfaces>

<packet_contract>
repository: `https://github.com/weijie567/mini-agent`
remote: `origin`
head_branch: `codex/e2e01-01-order-source-version-closure`
base_branch: `integration/e2e01-thin`
base_sha: `e54a6a4d77208695440c2caf03c3ab32f9d37108`
base_tree: `0a1b159c4a272d4c78cb708abddcebe4f60f0ce0`
input_barrier: `B_DEPENDENCY`
output_barrier: `B_DEPENDENCY_M / ONLY AFTER 01-07M FEATURE EXACT-HEAD AND LATEST-INTEGRATION OVERLAY REVIEWED-MERGED`
worktree_id: `e2e01-01-order-source-version-closure`
writer: `Order Core contract sole writer with one owned Component test, supervised by /root Integrator`
agent_role: `runtime-engineer / Core-only`
active_routing: `false`

planning_and_owner_provenance:

- exact `B_DEPENDENCY` merge/tree `e54a6a4d77208695440c2caf03c3ab32f9d37108` / `0a1b159c4a272d4c78cb708abddcebe4f60f0ce0`
- 01-07K [PR #96](https://github.com/weijie567/mini-agent/pull/96) reviewed merge/tree `27d084a9eeacb4c3819b94df16e8922927fd2888` / `fe35bb3325b5589182fc0734e576b42fbb244588`
- 01-07L security amendment [PR #97](https://github.com/weijie567/mini-agent/pull/97) merge `58d5387bf9b7f7ca7f8c50d03eb81c1c19a79dd9`
- 01-07L [PR #98](https://github.com/weijie567/mini-agent/pull/98) reviewed merge `e54a6a4d77208695440c2caf03c3ab32f9d37108`
- B_DEPENDENCY canonical gate observed before issuance: `1901 passed, 1 deselected, 12 warnings`
- Thin Slice owner blob `233a9c06ef6ef9300bef1a0e4f86659b0ec26a13`
- execution-map blob `ea2b5bcac4cb10c928a9e578c1286febb243c7d6`
- Memory owner blob `5c27ba3bd2ed74e5164bdd0812133041ed96f242`
- 01-07G / H / K / L Plan blobs `72c866f0afac449c7c9970c223c9eb182fb1e780` / `52ffe6652284d75b8f2546d50439762b63dfdfa0` / `45a573332136f5954358e6e077f2222b2e932259` / `7bc14608f3312ef17d92ecbb79e0fb42af2259c1`
- official 01-07M Plan merge SHA/blob由Integrator在Plan PR reviewed merge后捕获；planning merge不替换feature exact base `B_DEPENDENCY`

owned_files_at_base:

- `src/mini_agent/core/order.py` = `6f6188d6b848d4d628b5933df36580c21c84c024`
- `tests/component/core/test_memory_trace_presentation_contract.py` = `22a3ac0744bcf0bb01d9d98c1bf2c38f235bcb76`

owned_files:

- `src/mini_agent/core/order.py`
- `tests/component/core/test_memory_trace_presentation_contract.py`

allowlist:

- `src/mini_agent/core/order.py`
- `tests/component/core/test_memory_trace_presentation_contract.py`

forbidden_files: `ALL REPOSITORY FILES OUTSIDE THE TWO-FILE ALLOWLIST`，尤其包括 other `src/mini_agent/core/**`、`src/mini_agent/application/**`、`src/mini_agent/infrastructure/**`、`src/mini_agent/evaluation/**`、other `tests/**`、`evals/**`、`alembic/**`、`tests/conftest.py`、`pyproject.toml`、`uv.lock`、`compose.yaml`、`docs/**`、`.planning/**`、`AGENTS.md`、`PROJECT_DIRECTION.md`、`README.md`、`graphify-out/**`。

canonical_inputs:

- `docs/implementation/e2e01-thin-slice-implementation-spec.md` §6.2 / §6.2.1 final matrix与Expand→enforce→produce→close表。
- `docs/architecture/memory-design-reference.md` historical `OrderObservation.source_version?`与exact version引用语义。
- `docs/implementation/e2e01-thin-slice-multi-agent-plan.md` exact `B_DEPENDENCY → 01-07M → B_DEPENDENCY_M` execution map。
- exact B_DEPENDENCY中的`GetOrderResult` source/test blobs与reviewed K producer。

dependencies:

- `01-07K = REVIEWED_MERGED`，merge `27d084a9eeacb4c3819b94df16e8922927fd2888`。
- `01-07L = REVIEWED_MERGED`，merge `e54a6a4d77208695440c2caf03c3ab32f9d37108`。
- shared exact barrier `B_DEPENDENCY = e54a6a4d77208695440c2caf03c3ab32f9d37108`。
- new external/package/schema/migration dependency: `NONE`。

required_checks:

- Gate A exact branch/worktree/base/tree/two-blob/clean-state preflight before RED edit。
- focused baseline `39 passed`；RED必须只因missing source-version未被拒绝而非零；GREEN focused必须恢复`39 passed`，并覆盖summary/failure/version三种combined-invalid错误优先级。
- Agent-visible ToolSpec source-version absence。
- canonical environment：`uv sync --all-groups`、dev/test PostgreSQL healthy、`uv run alembic upgrade head`。
- canonical full `uv run pytest`。
- two-file changed-files、commit-order、commit-scope、no-merge、no-forbidden-import与protected-surface oracle。
- repository-level cross-file impact scan（显式排除`graphify-out/**`）与clean Worktree。
- feature exact-head及latest-integration overlay独立review，unresolved `CRITICAL/HIGH/MEDIUM/LOW = 0/0/0/0`。

commit_protocol:

1. RED `test(01-07M): require get_order source version`只改owned test，把旧optional test重命名为`test_found_result_requires_strict_source_version_exactly`；对合法summary + omitted version断言新fixed error，并分别冻结missing summary与present failure code在同时missing version时的既有错误优先级；`order.py`仍为base blob。Focused命令必须恰因当前validator未拒绝第一种missing-version输入而失败。
2. GREEN `feat(01-07M): close get_order source version contract`只改`src/mini_agent/core/order.py`既有validator，加入唯一missing-version gate；不得改imports、field/type alias、其他class/method或下游文件。
3. 正常history相对B_DEPENDENCY恰为以上两个commit。Review finding只用append-only `fix(01-07M): ...` commit，仍限两文件，并对新exact head重跑全部checks/review；不得amend、rebase或force-push已审历史。

done_when:

- RED/GREEN原因、输出、SHA、tree和两文件containment可复现。
- final outcome/negative/non-exposure矩阵、protected surface与full suite全绿。
- feature和latest-integration overlay均取得exact-head独立`0/0/0/0` review。
- draft PR精确使用M head → `integration/e2e01-thin`，由Integrator串行merge并捕获新的exact `B_DEPENDENCY_M`。
- 只解锁01-07Q规划；不推进Case、Requirement、Phase、01-08或产品lifecycle。

contract_changes: `YES / CORE ENFORCEMENT OF EXISTING CANONICAL FINAL CONTRACT` — 移除Runtime-private `GetOrderResult.FOUND + source_version=None`的临时兼容性；不修改canonical owner、外部API、Agent-visible schema、Memory record或producer算法。
security_impact: `YES / FAIL-CLOSED COMPLETENESS` — 缺失token不能再作为FOUND通过正常Core validation；non-FOUND最小披露与fixed raw-free error保持。M不把pattern-valid token变成authority或授权，可信来源仍只属于01-07K owner-scoped producer。
eval_impact: `YES / COMPONENT REGRESSION AND DOWNSTREAM PREREQUISITE` — Core contract test切换到final matrix并运行full suite；不改EvalCase、Dataset、Grader、Result、threshold、Baseline或lifecycle。
rollback: 合并前关闭PR；合并后用普通revert PR严格逆序撤销01-07M feature/fix commits，并重新阻塞`B_DEPENDENCY_M`、01-07Q、01-07J及全部后续active/contract/01-08/01-08A路径。不得reset、force-push、修改数据库、把Infra producer回退成`FOUND + None`或放宽non-FOUND。

handoff_to: `/root Integrator`
handoff_format: repository/remote/branch/worktree、exact base/planning/head/tree、Plan blob、two base/head blobs、RED/GREEN/fix SHAs与输出、canonical environment/focused/full结果、protected oracle、changed-files/commit containment、cross-file scan、contract/security/Eval nonclaims、feature/overlay review、PR/merge SHA、`B_DEPENDENCY_M` tree、风险与rollback。
</packet_contract>

<cross_file_impact>

- `CONFIRMED`：Thin Slice owner、Memory owner与execution map对M的scope、最终矩阵、历史optional Memory字段和后续Q/J顺序一致；无需修改canonical owner。
- `CONFIRMED`：exact B_DEPENDENCY中01-07K normal FOUND producer已携带exact token，现有Application FOUND test stubs也已携带synthetic valid token；全suite只有owned Core test仍显式保留legacy `FOUND + None`。
- `CONFIRMED / DERIVED STATUS DRIFT`：`README.md`、`PROJECT_DIRECTION.md`、`.planning/PROJECT.md`、`.planning/ROADMAP.md`、`.planning/STATE.md`与`.planning/REQUIREMENTS.md`仍停在B_IP/K-L签发前状态，Roadmap还把M写为`BLOCKED_BY_B_DEPENDENCY`。这些共享派生状态不覆盖exact barrier或用户本次签发，但不在本单Plan allowlist内；Integrator必须在独立single-writer status Packet中对齐，M writer不得越界或声称repository-wide status aligned。
- `NOT_FOUND`：没有active owner要求M修改ToolSpec、Memory、Infra、Runtime、Eval、migration或tracked artifacts。
</cross_file_impact>

<threat_model>

| threat_id | category | boundary | disposition | mitigation |
|---|---|---|---|---|
| `M-S01` | Spoofing | caller/model supplied valid-looking token → authority | `MITIGATE / TRANSFER` | M不生成或授权token；K仍是唯一trusted producer，ToolSpec/Provider/HTTP不暴露字段 |
| `M-T01` | Tampering | missing/malformed token → accepted FOUND | `MITIGATE / BLOCK` | existing strict exact pattern + new FOUND non-None validator + directed Core matrix |
| `M-R01` | Repudiation | closure claim → unverifiable change | `MITIGATE / BLOCK` | exact base/blobs、RED/GREEN commits、protected AST、full gate和双exact-head review |
| `M-I01` | Information Disclosure | token/error → model/user/Trace | `MITIGATE / BLOCK` | two-file scope、ToolSpec absence check、fixed raw-free error、无Presentation/HTTP/Trace修改 |
| `M-D01` | Denial of Service | global required field → non-FOUND breakage | `MITIGATE / BLOCK` | field保持optional；只在FOUND branch收紧；两个non-FOUND分支回归 |
| `M-E01` | Elevation of Privilege | source_version → authorization/readiness | `MITIGATE / BLOCK` | token永不授权；M active_routing=false，merge只形成dependency barrier |

</threat_model>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: RED — replace the legacy FOUND + None oracle with the final matrix</name>
  <files>tests/component/core/test_memory_trace_presentation_contract.py</files>
  <read_first>Thin Slice §6.2.1 final matrix、01-07H temporary optional contract、exact B_DEPENDENCY Core test、K producer evidence</read_first>
  <action>只改现有`test_found_result_accepts_optional_strict_source_version_exactly`函数：重命名为`test_found_result_requires_strict_source_version_exactly`；把`legacy_result`成功构造与`None`断言替换为`pytest.raises(ValidationError, match="FOUND result requires source_version")`包裹的`FOUND + _summary() + omitted source_version`。在同一函数再加入两项combined-invalid oracle：`FOUND`同时缺summary/version必须匹配`FOUND result requires order_summary`；`FOUND + _summary() + failure_code="UNEXPECTED" + omitted version`必须匹配`FOUND result cannot carry failure_code`。保留valid exact token构造与byte-for-byte断言。不要修改negative/non-FOUND tests、helper/constants/imports或任何source。运行focused command取得单一、预期的DID NOT RAISE类RED后提交精确subject。</action>
  <verify>
    <automated>uv run pytest tests/component/core/test_memory_trace_presentation_contract.py -q</automated>
    RED必须非零且只由current validator仍允许missing version造成；`src/mini_agent/core/order.py`保持base blob。
  </verify>
  <done>唯一legacy optional oracle被最终required matrix替代，失败原因可复现且没有提前实现GREEN。</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: GREEN — close FOUND source-version completeness in the existing validator</name>
  <files>src/mini_agent/core/order.py</files>
  <read_first>Task 1 RED commit/output、exact base validator、GetOrderSourceVersion alias与final outcome matrix</read_first>
  <action>只在`GetOrderResult.result_shape_matches_outcome`的FOUND branch、既有summary-required与failure-code-prohibited检查之后加入`self.source_version is None`检查并抛`ValueError("FOUND result requires source_version")`，保持两条既有negative错误优先级。不改字段、alias、regex、imports、枚举、其他模型、non-FOUND branch或文件。Focused恢复39 passed后，运行ToolSpec absence、canonical环境、migration和full suite；全部通过才提交精确GREEN subject。</action>
  <verify>
    <automated>uv run pytest tests/component/core/test_memory_trace_presentation_contract.py -q
uv run python -c 'from mini_agent.core.tool_system import get_order_tool_spec; assert "source_version" not in get_order_tool_spec().output_schema["properties"]'
uv sync --all-groups
docker compose up --wait -d db
docker compose --profile test up --wait -d db-test
uv run alembic upgrade head
uv run pytest</automated>
  </verify>
  <done>正常validation不能再构造FOUND + None；其余Core/outcome/non-exposure与全仓回归保持通过。</done>
</task>

</tasks>

<verification>

Gate A / first-edit preflight必须在feature Worktree从仓库根完整成功：

```bash
set -euo pipefail

base_sha=e54a6a4d77208695440c2caf03c3ab32f9d37108
base_tree=0a1b159c4a272d4c78cb708abddcebe4f60f0ce0
expected_branch=codex/e2e01-01-order-source-version-closure
expected_worktree_id=e2e01-01-order-source-version-closure
expected_remote=https://github.com/weijie567/mini-agent.git
current_root="$(git rev-parse --show-toplevel)"

test "$(git remote get-url origin)" = "$expected_remote"
test "$(git branch --show-current)" = "$expected_branch"
test "$(basename "$current_root")" = "$expected_worktree_id"
test "$(git worktree list --porcelain | awk -v root="$current_root" '
  $1 == "worktree" { current = $2 }
  $1 == "branch" && current == root { print $2 }
')" = "refs/heads/$expected_branch"
test "$(git rev-parse HEAD^0)" = "$base_sha"
test "$(git rev-parse "$base_sha^{tree}")" = "$base_tree"
test "$(git rev-parse "${base_sha}:src/mini_agent/core/order.py")" = \
  6f6188d6b848d4d628b5933df36580c21c84c024
test "$(git rev-parse "${base_sha}:tests/component/core/test_memory_trace_presentation_contract.py")" = \
  22a3ac0744bcf0bb01d9d98c1bf2c38f235bcb76
test -z "$(git status --short --untracked-files=all)"
uv run pytest tests/component/core/test_memory_trace_presentation_contract.py -q
```

Gate B / post-implementation final不再要求`HEAD == base_sha`，但必须完整重验：

```bash
set -euo pipefail

base_sha=e54a6a4d77208695440c2caf03c3ab32f9d37108
base_tree=0a1b159c4a272d4c78cb708abddcebe4f60f0ce0
expected_branch=codex/e2e01-01-order-source-version-closure
expected_worktree_id=e2e01-01-order-source-version-closure
expected_remote=https://github.com/weijie567/mini-agent.git
current_root="$(git rev-parse --show-toplevel)"

test "$(git remote get-url origin)" = "$expected_remote"
test "$(git branch --show-current)" = "$expected_branch"
test "$(basename "$current_root")" = "$expected_worktree_id"
test "$(git worktree list --porcelain | awk -v root="$current_root" '
  $1 == "worktree" { current = $2 }
  $1 == "branch" && current == root { print $2 }
')" = "refs/heads/$expected_branch"
test "$(git merge-base HEAD "$base_sha")" = "$base_sha"
test "$(git rev-parse "$base_sha^{tree}")" = "$base_tree"
test "$(git rev-parse "${base_sha}:src/mini_agent/core/order.py")" = \
  6f6188d6b848d4d628b5933df36580c21c84c024
test "$(git rev-parse "${base_sha}:tests/component/core/test_memory_trace_presentation_contract.py")" = \
  22a3ac0744bcf0bb01d9d98c1bf2c38f235bcb76

uv sync --all-groups
docker compose up --wait -d db
docker compose --profile test up --wait -d db-test
uv run alembic upgrade head
uv run pytest tests/component/core/test_memory_trace_presentation_contract.py -q
uv run python -c 'from mini_agent.core.tool_system import get_order_tool_spec; assert "source_version" not in get_order_tool_spec().output_schema["properties"]'
uv run pytest

git diff --check "$base_sha...HEAD"
test "$(git rev-list --count "$base_sha..HEAD")" -ge 2
test "$(git rev-list --merges --count "$base_sha..HEAD")" -eq 0
red_sha="$(git rev-list --reverse "$base_sha..HEAD" | sed -n '1p')"
green_sha="$(git rev-list --reverse "$base_sha..HEAD" | sed -n '2p')"
test "$(git show -s --format=%s "$red_sha")" = \
  "test(01-07M): require get_order source version"
test "$(git show -s --format=%s "$green_sha")" = \
  "feat(01-07M): close get_order source version contract"
test "$(git diff-tree --no-commit-id --name-only -r "$red_sha")" = \
  tests/component/core/test_memory_trace_presentation_contract.py
test "$(git diff-tree --no-commit-id --name-only -r "$green_sha")" = \
  src/mini_agent/core/order.py
test -z "$(git log --reverse --format=%s "$base_sha..HEAD" |
  sed '1,2d' |
  rg -v '^fix\(01-07M\): .+$' || true)"
for fix_sha in $(git rev-list --reverse "$base_sha..HEAD" | sed '1,2d'); do
  test -z "$(git diff-tree --no-commit-id --name-only -r "$fix_sha" |
    rg -v '^(src/mini_agent/core/order\.py|tests/component/core/test_memory_trace_presentation_contract\.py)$' ||
    true)"
done
test "$(git diff --name-only "$base_sha...HEAD" | LC_ALL=C sort)" = "$(printf '%s\n' \
  src/mini_agent/core/order.py \
  tests/component/core/test_memory_trace_presentation_contract.py)"
test -z "$(git status --short --untracked-files=all)"
```

Protected-surface oracle必须作为同一Gate B运行：

```bash
base_sha=e54a6a4d77208695440c2caf03c3ab32f9d37108
uv run python - "$base_sha" <<'PY'
from __future__ import annotations

import ast
from pathlib import Path
import subprocess
import sys

BASE = sys.argv[1]
SOURCE = "src/mini_agent/core/order.py"
TEST = "tests/component/core/test_memory_trace_presentation_contract.py"
OLD_TEST = "test_found_result_accepts_optional_strict_source_version_exactly"
NEW_TEST = "test_found_result_requires_strict_source_version_exactly"
MUTABLE_METHOD = "result_shape_matches_outcome"
FORBIDDEN_CALLS = frozenset(
    {"__import__", "eval", "exec", "globals", "locals", "setattr"}
)


def base_text(path: str) -> str:
    return subprocess.check_output(
        ["git", "show", f"{BASE}:{path}"],
        text=True,
        encoding="utf-8",
    )


def segment(text: str, node: ast.AST) -> str:
    start = node.lineno
    decorators = getattr(node, "decorator_list", ())
    if decorators:
        start = min(start, *(item.lineno for item in decorators))
    lines = text.splitlines(keepends=True)
    return "".join(lines[start - 1 : node.end_lineno])


def exact(before: str, after: str, left: ast.AST, right: ast.AST) -> None:
    assert segment(before, left) == segment(after, right)
    assert ast.dump(left, include_attributes=False) == ast.dump(
        right,
        include_attributes=False,
    )


before_source = base_text(SOURCE)
after_source = Path(SOURCE).read_text(encoding="utf-8")
before_tree = ast.parse(before_source)
after_tree = ast.parse(after_source)
before_classes = [
    node
    for node in before_tree.body
    if isinstance(node, ast.ClassDef) and node.name == "GetOrderResult"
]
after_classes = [
    node
    for node in after_tree.body
    if isinstance(node, ast.ClassDef) and node.name == "GetOrderResult"
]
assert len(before_classes) == len(after_classes) == 1
before_class = before_classes[0]
after_class = after_classes[0]
before_other_source_nodes = [
    node for node in before_tree.body if node is not before_class
]
after_other_source_nodes = [
    node for node in after_tree.body if node is not after_class
]
assert len(after_other_source_nodes) == len(before_other_source_nodes)
for left, right in zip(before_other_source_nodes, after_other_source_nodes, strict=True):
    exact(before_source, after_source, left, right)

assert isinstance(before_class, ast.ClassDef)
assert isinstance(after_class, ast.ClassDef)
assert [
    ast.dump(node, include_attributes=False) for node in after_class.bases
] == [ast.dump(node, include_attributes=False) for node in before_class.bases]
assert [
    ast.dump(node, include_attributes=False) for node in after_class.keywords
] == [ast.dump(node, include_attributes=False) for node in before_class.keywords]
assert [
    ast.dump(node, include_attributes=False)
    for node in after_class.decorator_list
] == [
    ast.dump(node, include_attributes=False)
    for node in before_class.decorator_list
]
before_methods = {
    node.name: node
    for node in before_class.body
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
}
after_methods = {
    node.name: node
    for node in after_class.body
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
}
assert set(after_methods) == set(before_methods) == {MUTABLE_METHOD}
before_method = before_methods[MUTABLE_METHOD]
after_method = after_methods[MUTABLE_METHOD]
assert type(after_method) is type(before_method)
assert ast.dump(after_method.args, include_attributes=False) == ast.dump(
    before_method.args,
    include_attributes=False,
)
assert ast.dump(after_method.returns, include_attributes=False) == ast.dump(
    before_method.returns,
    include_attributes=False,
)
assert [
    ast.dump(node, include_attributes=False)
    for node in after_method.decorator_list
] == [
    ast.dump(node, include_attributes=False)
    for node in before_method.decorator_list
]
assert after_method.type_comment == before_method.type_comment
assert len(before_method.body) == len(after_method.body) == 2
before_outcome_branch, before_return = before_method.body
after_outcome_branch, after_return = after_method.body
assert isinstance(before_outcome_branch, ast.If)
assert isinstance(after_outcome_branch, ast.If)
exact(before_source, after_source, before_return, after_return)
assert ast.dump(
    after_outcome_branch.test,
    include_attributes=False,
) == ast.dump(before_outcome_branch.test, include_attributes=False)
assert [
    ast.dump(node, include_attributes=False)
    for node in after_outcome_branch.orelse
] == [
    ast.dump(node, include_attributes=False)
    for node in before_outcome_branch.orelse
]
assert len(after_outcome_branch.body) == len(before_outcome_branch.body) + 1
for left, right in zip(
    before_outcome_branch.body,
    after_outcome_branch.body[:-1],
    strict=True,
):
    exact(before_source, after_source, left, right)
expected_insertion = ast.parse(
    'if self.source_version is None:\n'
    '    raise ValueError("FOUND result requires source_version")\n'
).body[0]
assert ast.dump(
    after_outcome_branch.body[-1],
    include_attributes=False,
) == ast.dump(expected_insertion, include_attributes=False)
before_non_methods = [
    ast.dump(node, include_attributes=False)
    for node in before_class.body
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
]
after_non_methods = [
    ast.dump(node, include_attributes=False)
    for node in after_class.body
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
]
assert after_non_methods == before_non_methods

before_test = base_text(TEST)
after_test = Path(TEST).read_text(encoding="utf-8")
before_test_tree = ast.parse(before_test)
after_test_tree = ast.parse(after_test)
before_targets = [
    node
    for node in before_test_tree.body
    if isinstance(node, ast.FunctionDef) and node.name == OLD_TEST
]
after_targets = [
    node
    for node in after_test_tree.body
    if isinstance(node, ast.FunctionDef) and node.name == NEW_TEST
]
assert len(before_targets) == len(after_targets) == 1
assert not any(
    isinstance(node, ast.FunctionDef) and node.name == NEW_TEST
    for node in before_test_tree.body
)
assert not any(
    isinstance(node, ast.FunctionDef) and node.name == OLD_TEST
    for node in after_test_tree.body
)
before_other_test_nodes = [
    node for node in before_test_tree.body if node is not before_targets[0]
]
after_other_test_nodes = [
    node for node in after_test_tree.body if node is not after_targets[0]
]
assert len(after_other_test_nodes) == len(before_other_test_nodes)
for left, right in zip(before_other_test_nodes, after_other_test_nodes, strict=True):
    exact(before_test, after_test, left, right)

target_source = segment(after_test, after_targets[0])
for required_fragment in (
    'match="FOUND result requires source_version"',
    'match="FOUND result requires order_summary"',
    'match="FOUND result cannot carry failure_code"',
    'failure_code="UNEXPECTED"',
    "source_version=VALID_SOURCE_VERSION",
    "assert versioned_result.source_version == VALID_SOURCE_VERSION",
):
    assert target_source.count(required_fragment) == 1, required_fragment

for tree in (after_tree, after_test_tree):
    counts = {
        name: sum(
            1
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == name
        )
        for name in FORBIDDEN_CALLS
    }
    baseline_tree = before_tree if tree is after_tree else before_test_tree
    baseline = {
        name: sum(
            1
            for node in ast.walk(baseline_tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == name
        )
        for name in FORBIDDEN_CALLS
    }
    assert counts == baseline

assert after_source.count('ValueError("FOUND result requires source_version")') == 1
print("01-07M protected surface: PASS")
PY
```

Repository-level cross-file impact scan：

```bash
rg -n \
  'GetOrderResult|source_version|OrderObservation|B_DEPENDENCY(_M)?|01-07[HKLMQJ]|FOUND' \
  AGENTS.md README.md PROJECT_DIRECTION.md docs .planning src tests evals \
  --glob '!graphify-out/**'
```

scan只报告canonical alignment、已知derived status drift与Q/J/01-08下游；feature writer不得越allowlist修正。Feature exact head必须对两项changed files完成独立correctness/security/test review并取得`PASS / CRITICAL-HIGH-MEDIUM-LOW = 0/0/0/0`。随后Integrator在包含01-07M Plan merge的latest `integration/e2e01-thin`上创建no-conflict overlay，证明patch identity，重复focused/full/protected gates与独立review，再串行merge。只有该reviewed feature merge SHA才命名为`B_DEPENDENCY_M`。

</verification>

<success_criteria>

1. RED/ GREEN两提交的失败/通过原因、scope、SHA与输出可复现；review fix只可append并保持两文件allowlist。
2. 正常Core validation要求FOUND同时携带summary与strict exact source-version，且禁止failure code；所有non-FOUND规则保持。
3. type alias、field声明、ToolSpec、Memory、Infra、Runtime、Eval、migration与active routing零变化；historical Observation optionality不被升级。
4. focused 39、canonical migration/full suite、protected oracle、two-file containment与feature/latest-overlay独立review全部通过。
5. reviewed feature merge形成exact `B_DEPENDENCY_M`并只解锁01-07Q规划；不宣告B_Q、B_ACTIVE、01-08或产品完成。

</success_criteria>

<output>
完成后不创建Summary或共享State。Executor只按`handoff_format`交接；Integrator在reviewed merge后另行索引`B_DEPENDENCY_M`证据并处理derived status alignment。
</output>
