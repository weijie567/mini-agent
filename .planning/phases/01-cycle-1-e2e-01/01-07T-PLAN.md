---
phase: 01-cycle-1-e2e-01
plan: 07T
type: tdd
wave: 30
depends_on:
  - 01-07T-PHYSICAL-HANDOFF
files_modified:
  - src/mini_agent/application/persistence.py
  - tests/component/application/test_persistence_contract.py
autonomous: true
requirements:
  - E2E01-01
  - E2E01-04
user_setup: []
must_haves:
  truths:
    - "Application persistence codec不再导入、注册、编码或解码RequestUnderstandingRecord / AcceptedTaskDelta v1；RU唯一current codec pair为request_understanding_record.p0.v2。"
    - "P0_PERSISTENCE_REGISTRY与P0_RECORD_SCHEMA_VERSION_CATALOG均为17项current-only mapping：16个非RU v1加唯一RU v2。"
    - "无schema_version参数的codec入口继续服务16个非RU current-v1 record；RU generic encode/decode固定UNKNOWN_RECORD_SCHEMA_VERSION，不能推断版本或fallback。"
    - "P0_LOGICAL_CHILD_SPECS的ACCEPTED_TASK_DELTA current spec为AcceptedTaskDeltaV2；TaskStateTransition与ToolAttemptRecord不变，current projection counts冻结为70/8/49。"
    - "Infrastructure physical allowset与migration 0003继续允许RU-v1/v2共18 pair；codec closure不改physical data、不激活01-07R。"
    - "reviewed merge与post-merge gate只形成B_T，不推进W/V、Case lifecycle、Trajectory/E2E或产品readiness。"
  artifacts:
    - "17-pair current-only codec catalog、17-code active registry、3-child current mapping及RU-v1 static/runtime absence guard。"
    - "16个非RU generic codec回归、RU-v2 exact-version证据与historical RU-v1 raw metadata fail-closed证据。"
  key_links:
    - "B_T_PHYSICAL_HANDOFF → 01-07T → B_T。"
    - "P0_PERSISTENCE_REGISTRY[REQUEST_UNDERSTANDING_RECORD] → request_understanding_record.p0.v2 → RequestUnderstandingRecordV2 / AcceptedTaskDeltaV2。"
    - "B_T只解锁01-07W；W完成后再从B_W签发01-07V。"
---

# Phase 1 Plan 01-07T｜Application persistence codec v1-contract closure

> **REISSUED TASK PACKET / IMPLEMENTATION NOT STARTED**
> 被关闭的PR #137及其Plan `fabc546e...`因physical catalog ownership blocker而FAIL，不能复用、合并或作为feature base。本Packet只在01-07T-PHYSICAL-HANDOFF形成共同barrier后重新签发T。只有feature从exact `B_T_PHYSICAL_HANDOFF`完成独立review、latest-integration replay、串行merge与post-merge gate后才可命名`B_T`。

> **DERIVED / NON_NORMATIVE**
> Request Understanding、Memory、安全、Eval与产品结果语义仍由active canonical owner拥有。本Plan消费`p0-ru-v2-execution-map-r4`的T ownership，不建立第二套合同。Graphify按用户指令保持闲置。

<objective>
删除Application persistence codec中RU-v1 parent/child representation、18-pair compatibility catalog entry及generic/versioned success path，使Application executable codec只保留16个非RU v1 pair与唯一RU-v2 pair；同时保持Infrastructure physical18与migration 0003不变。

Purpose: 01-07T-PHYSICAL-HANDOFF已经把SQLAlchemy physical constraint从Application catalog解耦。T现在可以在双文件Application ownership内把executable catalog从18收敛为17，而不会使ORM metadata与数据库约束漂移。

Output: 双文件TDD feature。RED冻结RU-v1 executable absence与17/17/3 current closure；GREEN删除source surface并迁移Component contracts。Application Port/records与Core v1 types分别留给W/V。
</objective>

<preflight_evidence>

- `CONFIRMED`：input barrier为exact `B_T_PHYSICAL_HANDOFF = 0a703af6e56d8c0890b2506de795e7605049a78f`，tree `e502f98bf12d91d77952c9cc7a96262e9c6bc369`。
- `CONFIRMED`：handoff feature reviewed head `c4b422ce083e8a58ac15fde79ac7f667dda21d3f`以`PASS P0/P1/P2/P3 = 0/0/0/0`通过，PR #140 merge为上述barrier。
- `CONFIRMED`：handoff post-merge gate为focused/neighbor `366 passed`、canonical full `1974 passed, 1 deselected, 12 warnings`；migration 0003 blob仍为`bcd7dd85b4c5b82c764942ff0faf019d9e4744d0`。
- `CONFIRMED`：Infrastructure `_PHYSICAL_CODE_VERSION_PAIRS`是与0003 exact一致的immutable literal18，`_CODE_VERSION_PAIRS`只由其sorted派生，不再引用Application catalog。
- `CONFIRMED`：owned base blobs：
  - `src/mini_agent/application/persistence.py = 37db31ecf18707c21fff1ca9a9505cd9c4fb3555`
  - `tests/component/application/test_persistence_contract.py = 26d07270be74f87ca300d62979c97ec7b99e28ba`
- `CONFIRMED`：owned Component baseline为`233 passed`。
- `CONFIRMED`：当前active registry已经是17-code current mapping，RU为v2；Application catalog仍有18 pair，RU-v1/v2共存；private v1 registry、v1 accepted child spec与generic RU-v1 route仍存在。
- `CONFIRMED`：其他16个record family仍依赖generic encode/decode，T不能删除public generic functions或改变非RU语义。
- `CONFIRMED`：current closure exact counts为top-level projection `70`、child projection `8`、P0 reference projection `49`。
- `OPEN / NONCLAIM`：T不扫描、迁移、回填、重写或删除historical physical RU-v1 rows，不证明数据库不存在v1 row，不激活01-07R。
- `OPEN / NONCLAIM`：T不删除Application command/Port/records或Core v1 types，不完成zero/all-REJECT、multi-ACCEPT、atomic recovery、真实HTTP Trajectory/E2E、Case PASS或产品readiness。

</preflight_evidence>

<execution_context>
@AGENTS.md
@.planning/GOVERNANCE.md
@.planning/phases/01-cycle-1-e2e-01/01-07T-PHYSICAL-HANDOFF-PLAN.md
@docs/architecture/intent-design-reference.md
@docs/architecture/memory-design-reference.md
@docs/implementation/e2e01-thin-slice-implementation-spec.md
@docs/implementation/e2e01-thin-slice-multi-agent-plan.md
@src/mini_agent/application/persistence.py
@tests/component/application/test_persistence_contract.py

只使用项目受控execution adapter；不得调用stock GSD lifecycle命令。
</execution_context>

<interfaces>

## 1. Exact feature identity and ownership

repository: `/Users/ming/projects/mini-agent`

remote: `https://github.com/weijie567/mini-agent.git`

feature_branch: `codex/e2e01-01-ru-v1-codec-contract`

feature_worktree: `e2e01-01-ru-v1-codec-contract`

writer: `/root Integrator / Application persistence codec two-file sole writer`

pull_request_base: `integration/e2e01-thin`

base_sha: `0a703af6e56d8c0890b2506de795e7605049a78f`

base_tree: `e502f98bf12d91d77952c9cc7a96262e9c6bc369`

input_barrier: `B_T_PHYSICAL_HANDOFF`

output_barrier: `B_T / ONLY AFTER REVIEWED FEATURE MERGE AND POST-MERGE GATES`

owned_files_at_base:

- `src/mini_agent/application/persistence.py = 37db31ecf18707c21fff1ca9a9505cd9c4fb3555`
- `tests/component/application/test_persistence_contract.py = 26d07270be74f87ca300d62979c97ec7b99e28ba`

allowlist: exact two paths above.

forbidden_files: `ALL REPOSITORY FILES OUTSIDE THE TWO-FILE ALLOWLIST`，尤其包括`src/mini_agent/application/ports.py`、`records.py`、other Application files、`src/mini_agent/core/**`、`src/mini_agent/infrastructure/**`、`src/mini_agent/evaluation/**`、other `tests/**`、`evals/**`、`alembic/**`、`pyproject.toml`、`uv.lock`、`compose.yaml`、`docs/**`、`.planning/**`、`AGENTS.md`、`PROJECT_DIRECTION.md`、`README.md`、`graphify-out/**`。

Plan branch/worktree只拥有本Plan文件。feature必须从上述exact barrier另建clean Worktree；不得使用PR #137 head、execution-owner merge、本Plan merge或任何后续documentation SHA作为base。

## 2. Exact RU-v1 codec deletion boundary

T必须从`persistence.py`删除：

- `RequestUnderstandingRecord`与`AcceptedTaskDelta` v1 imports；
- RU-v1 parent spec与v1 `ACCEPTED_TASK_DELTA` child spec；
- `_P0_V1_PERSISTENCE_REGISTRY`及其RU-v1 compatibility含义；
- `(REQUEST_UNDERSTANDING_RECORD, "request_understanding_record.p0.v1")` catalog pair；
- generic与exact-version API对RU-v1 source/child/envelope的成功路径。

T必须保留：

- 17个`P0RecordCode`与3个`P0LogicalChildCode`；
- 16个非RU v1 specs及generic codec行为；
- RU-v2 exact pair、exact source/child types、projection/closure/owner/reference/version mirror校验；
- TaskStateTransition与ToolAttemptRecord child specs；
- strict JSON、exact type、no subclass/private state、zero-I/O/no fallback及bounded errors。

建议内部结构为immutable 16-code non-RU registry与两个non-RU child specs，再与RU-v2组装public current registry/catalog/child mapping。不得增加第二个public registry、alias、runtime register、config switch或latest selector。

## 3. Public behavior after closure

`P0_PERSISTENCE_REGISTRY`恰为17项且顺序等于`P0RecordCode`；`P0_RECORD_SCHEMA_VERSION_CATALOG`恰为17项并与current registry逐项one-to-one、object identity一致。RU-v1 lookup不存在。

`P0_LOGICAL_CHILD_SPECS`恰为：

- `ACCEPTED_TASK_DELTA → AcceptedTaskDeltaV2`
- `TASK_STATE_TRANSITION → TaskStateTransition`
- `TOOL_ATTEMPT_RECORD → ToolAttemptRecord`

generic API signatures保持。当record code为RU时，generic encode/decode固定bounded `UNKNOWN_RECORD_SCHEMA_VERSION`，不得按source type、payload、metadata、registry或catalog推断版本。RU callers必须使用existing exact-version APIs。

exact-version APIs只接受17 current pairs。RU-v1 exact pair与raw RU-v1 metadata必须`UNKNOWN_RECORD_SCHEMA_VERSION`；不得upgrade、fallback、rewrite或调用I/O。已知其他current version用于错误code时仍为`RECORD_SCHEMA_VERSION_MISMATCH`。

## 4. Component contract migration

owned test必须增加AST/runtime guard并最终做到：

- 不导入、实例化或动态访问v1 `RequestUnderstandingRecord` / `AcceptedTaskDelta`；
- 不存在private 17-v1 registry、RU-v1 spec、v1 accepted child spec或hidden alias；
- registry/catalog/child mapping exact为17/17/3，projection counts为70/8/49；
- `_record_cases()`只包含16个非RU generic fixtures，不先构造RU-v1再过滤；
- generic RU encode/decode、exact RU-v1 pair及raw physical-v1 metadata bounded fail closed；
- v2 exact pair及其zero/partial/multi-accepted、contextualization、candidate/decision、Task effect、trusted-time、owner/reference/child cardinality、strict type/version与mutation resistance证据保留；
- static dependency inventory仍限制versioned codec caller边界。

删除RU-v1参数化cases后focused test总数可下降，但不得以数量下降掩盖current v2或16个非RU证据缺失。

## 5. Commit, review and barrier protocol

1. RED commit只修改owned test，增加RU-v1 absence/current-only guard；在base source应因v1 surface存在而失败。
2. GREEN commit在双文件内删除source surface并迁移owned tests；不得amend/rebase掉RED。
3. findings只用append-only allowlist fix commits关闭。
4. exact review验证first parent exact barrier、linear/no merge、双文件scope、RU-v1 executable依赖为零、physical/migration blobs不变。
5. PASS后在包含本Plan merge的latest integration做throwaway overlay，证明owned base blobs未被docs delta改变且patch一致。
6. reviewed feature串行merge后复跑focused、Infrastructure/database neighbor、canonical full；共同tree才形成`B_T`并解锁W。

</interfaces>

<tasks>

<task type="auto">
  <name>Task 1: RED — 冻结RU current-only codec与v1 absence</name>
  <files>tests/component/application/test_persistence_contract.py</files>
  <action>增加exact AST/runtime guard，禁止v1 parent/child import、registry/catalog/spec与generic/versioned success，同时确认17/17/3目标、16个非RU generic与RU-v2 exact surface。</action>
  <verify><automated>uv run pytest tests/component/application/test_persistence_contract.py -q</automated></verify>
  <done>RED只命中RU-v1 compatibility，不误报其他16个v1 record或V2 types。</done>
</task>

<task type="auto">
  <name>Task 2: GREEN — 删除RU-v1 codec representation并迁移Component contracts</name>
  <files>src/mini_agent/application/persistence.py, tests/component/application/test_persistence_contract.py</files>
  <action>删除RU-v1 imports/specs/private registry/catalog pair；组装16非RU+RU-v2 current closure。generic RU固定UNKNOWN，exact APIs只认17 current pairs；迁移fixtures与projection/count/error矩阵。</action>
  <verify><automated>uv run pytest tests/component/application/test_persistence_contract.py -q</automated></verify>
  <done>owned source/test无RU-v1 executable dependency；17/17/3、16非RU generic与RU-v2 exact证据通过。</done>
</task>

<task type="auto">
  <name>Task 3: exact review、latest overlay与B_T gate</name>
  <files>exact two-file allowlist</files>
  <action>运行containment、AST、focused、neighbors、integration/full及independent review；PASS后overlay、串行merge与post-merge canonical gates。不得同步status或提前启动W。</action>
  <verify><automated>uv run pytest</automated></verify>
  <done>共同post-merge tree形成可复现B_T。</done>
</task>

</tasks>

<verification>

```bash
git diff --check
uv run pytest tests/component/application/test_persistence_contract.py -q
uv run pytest tests/component/application/test_ports_contract.py tests/integration/test_postgres_record_adapters.py tests/integration/test_postgres_v2_request_understanding_writes.py -q
uv run pytest tests/integration -q
uv sync --all-groups
docker compose up --wait -d db
docker compose --profile test up --wait -d db-test
uv run alembic upgrade head
uv run pytest
```

额外检查：

- first feature commit parent exact `0a703af6e56d8c0890b2506de795e7605049a78f`，linear/no merge；
- changed files exact双文件；
- source/test RU-v1 imports/spec/registry/codec success path为零；
- registry/catalog/child exact17/17/3，projection 70/8/49；
- generic RU不推断，exact RU-v1/raw metadata fail closed；
- 16非RU generic行为保持；
- Infrastructure physical18与0003 blob不变；
- independent review `0/0/0/0`；
- overlay patch一致；
- post-merge full通过后才记录`B_T`。

</verification>

<contract_changes>

`SCOPED / EXECUTION-MAP AUTHORIZED`：删除Application persistence codec RU-v1 representation、catalog pair及成功路径；current executable codec收敛为16个非RU v1加RU-v2。physical18、其他16个合同与RU-v2 exact-version合同不变；01-07R保持inactive。

</contract_changes>

<security_impact>

`BOUNDARY PRESERVING / DEFENSE IN DEPTH`：codec继续zero-I/O、不授权owner lookup、不证明provenance/business fact/readiness。删除v1 fallback面并要求RU exact version，保留strict校验与bounded errors；不投影raw payload、secret或PII。

</security_impact>

<eval_impact>

`COMPONENT CONTRACT UPDATE ONLY`：更新Application codec Component evidence；不新增/激活Dataset Case，不改变Trajectory/E2E Result或42 denominator。

</eval_impact>

<rollback>

未merge：关闭draft PR并保留证据。已merge但W未形成：普通revert T merge并复跑codec、Infrastructure/database/full，恢复到`B_T_PHYSICAL_HANDOFF`；不得reset/force。

若已有下游barrier，按`V → W → T`逆序普通revert并逐步复跑对应gate。T不迁移physical rows，rollback不得声称恢复或删除数据库内容。

</rollback>

<handoff>

```text
Task Packet: 01-07T
Base SHA / tree:
Branch / Worktree:
RED commit and expected failure:
GREEN/fix commits:
Reviewed exact head / tree:
Actual changed files:
Commands and exact results:
Allowlist / containment result:
Physical18 / 0003 preservation:
Contract changes:
Security impact:
Eval impact:
Latest integration overlay evidence:
PR / merge commit:
Post-merge B_T SHA / tree:
Unresolved risks:
Rollback:
Recommended next step:
```

Agent完成不等于`B_T`、`B_RU_V2_CONTRACT`、01-08或P0产品完成。

</handoff>

<cross_file_impact>

- execution-owner r4拥有`B_T_PHYSICAL_HANDOFF → T → W → V`顺序；本Plan只签发T。
- PR #137与旧Plan保留blocked历史证据，不得复用。
- handoff Plan与0003历史正文不改；physical18继续由Infrastructure/migration owner持有。
- Application Port/records留给W，Core v1 types留给V。
- derived status仍由dedicated status Packet更新；T不越界修改。
- Graphify保持闲置。

</cross_file_impact>
