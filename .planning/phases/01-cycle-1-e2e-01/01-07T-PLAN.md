---
phase: 01-cycle-1-e2e-01
plan: 07T
type: tdd
wave: 30
depends_on:
  - 01-07X
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
    - "P0_PERSISTENCE_REGISTRY保持17-code immutable current mapping；P0_RECORD_SCHEMA_VERSION_CATALOG从18-pair compatibility catalog收敛为17-pair current-only catalog，其中16项仍为各自v1，RU只有v2。"
    - "无schema_version参数的既有codec入口只继续服务16个非RU current-v1 record，不得对RU推断版本；RU无论v1/v2都必须通过exact-version API，unversioned RU调用bounded fail closed。"
    - "P0_LOGICAL_CHILD_SPECS的ACCEPTED_TASK_DELTA current spec切为AcceptedTaskDeltaV2；TaskStateTransition与ToolAttemptRecord保持原spec，current projection counts与reference closure必须机械冻结。"
    - "01-07T不得修改Infrastructure、Application Port/records、Core、Runtime、Provider/Eval、migration、canonical owner、派生status或Case lifecycle；reviewed merge与post-merge gate只形成B_T。"
  artifacts:
    - "17-pair current-only codec catalog、17-code active registry、current v2 AcceptedTaskDelta child mapping及RU-v1 static/runtime absence guard。"
    - "16个非RU unversioned codec回归证据、RU-v2 exact-version codec证据及historical-v1 raw metadata fail-closed证据。"
  key_links:
    - "B_X → 01-07T Application codec closure → B_T。"
    - "P0_PERSISTENCE_REGISTRY[REQUEST_UNDERSTANDING_RECORD] → request_understanding_record.p0.v2 → RequestUnderstandingRecordV2 / AcceptedTaskDeltaV2。"
    - "B_T只解锁01-07W；W完成后再从B_W签发01-07V，三者共同形成B_RU_V2_CONTRACT。"
---

# Phase 1 Plan 01-07T｜Application persistence codec v1-contract closure

> **ISSUED CONTRACT-CLOSURE TASK PACKET / IMPLEMENTATION NOT STARTED**
> 本Packet只关闭Application persistence codec中的RU-v1合同。Plan、RED/GREEN feature head或status merge均不形成`B_T`；只有feature从exact `B_X`完成独立review、latest-integration replay、串行merge与post-merge gate后才可命名该barrier。

> **DERIVED / NON_NORMATIVE**
> Request Understanding、Memory、安全、Eval与产品结果语义仍由active canonical owner拥有。本Plan只消费`p0-ru-v2-execution-map-r3`中的01-07T ownership，不建立第二套合同。Graphify按用户指令保持闲置，不读取、不运行、不更新、不作为gate。

<objective>
以最小TDD变更删除Application persistence codec中为01-07Q至01-07T窗口保留的RU-v1 compatibility pair、source/child model与generic encode/decode route，使RU只剩exact v2 current codec；同时保持16个非RU record的既有unversioned v1行为及所有current v2 strict closure。

Purpose: `B_X`已经删除Infrastructure RU-v1 writer/readers及其direct callers，但`persistence.py`仍导入`RequestUnderstandingRecord` / `AcceptedTaskDelta`，把RU-v1放入private 17-v1 registry、18-pair catalog、v1 child mapping，并允许generic与explicit-version codec继续生成/读取RU-v1。该表面会阻断后续01-07W删除Application command/Port records和01-07V删除Core v1 types。

Output: 一个双文件、单一Application codec writer的feature Packet。RED先冻结RU-v1 static/runtime absence与17-pair current-only closure；GREEN再删除v1 spec并迁移Component contract tests。Infrastructure与Application Port/records/Core严格留给各自后续owner。
</objective>

<preflight_evidence>

- `CONFIRMED`：feature input必须是exact `B_X = 9e8c70db39786b35c1ebea5070a32a1bc36e0df7`，tree `4b01798be73c15ae0b3eda42483078cbd7cdf7dc`；X independent review为`P0/P1/P2/P3 = 0/0/0/0`，post-merge focused+neighbor为`152 passed`，canonical full为`1974 passed, 1 deselected, 12 warnings`。
- `CONFIRMED`：active execution map `p0-ru-v2-execution-map-r3`只给01-07T两个owned files，branch `codex/e2e01-01-ru-v1-codec-contract`，input/output为`B_X → B_T`。
- `CONFIRMED`：owned base blobs为：
  - `src/mini_agent/application/persistence.py = 37db31ecf18707c21fff1ca9a9505cd9c4fb3555`
  - `tests/component/application/test_persistence_contract.py = 26d07270be74f87ca300d62979c97ec7b99e28ba`
- `CONFIRMED`：owned Component baseline为`233 passed`。
- `CONFIRMED`：当前`P0_PERSISTENCE_REGISTRY`已经是17-code current mapping，包含16个record-specific v1 spec与唯一RU-v2 spec；RU active spec与18-pair catalog中的v2 entry为同一对象。
- `CONFIRMED`：当前`P0_RECORD_SCHEMA_VERSION_CATALOG`仍有18个exact pair，其中RU同时存在v1/v2；`_P0_V1_PERSISTENCE_REGISTRY`仍有17个v1 spec，generic encode/decode与versioned APIs都可消费RU-v1。
- `CONFIRMED`：当前`P0_LOGICAL_CHILD_SPECS[ACCEPTED_TASK_DELTA]`仍绑定`AcceptedTaskDelta` v1，v2 child另在private exact-v2 catalog；source还直接导入`RequestUnderstandingRecord`与`AcceptedTaskDelta`。
- `CONFIRMED`：全仓Production仍广泛使用generic `encode_persistence_record` / `decode_persistence_record`处理其他16个record family；T两文件allowlist不能删除这些public functions或改变其非RU语义。
- `CONFIRMED`：X已经从owned integration tests移除RU-v1 generic envelope chain；active RU writers/readers使用exact-version v2 path，physical-v1 isolation只依赖raw metadata fence，不需要v1 Core DTO或codec。
- `CONFIRMED`：以现有active top-level registry、非RU children及v2 accepted child计算，current closure exact counts为top-level projection `70`、child projection `8`、P0 reference projection `49`。
- `OPEN / NONCLAIM`：T不迁移、回填、重写或删除数据库中的historical physical-v1 rows，不激活01-07R；不存在“catalog不再识别v1”即可证明数据库中没有v1 row的结论。
- `OPEN / NONCLAIM`：T不完成Application command/Port/records或Core v1 type删除；这些分别属于W/V。T也不完成zero/all-REJECT、multi-ACCEPT、atomic failure恢复、真实HTTP Trajectory/E2E、Case PASS或产品readiness。

</preflight_evidence>

<execution_context>
@AGENTS.md
@.planning/GOVERNANCE.md
@.planning/phases/01-cycle-1-e2e-01/01-07E-PLAN.md
@.planning/phases/01-cycle-1-e2e-01/01-07Q-PLAN.md
@.planning/phases/01-cycle-1-e2e-01/01-07X-PLAN.md
@docs/architecture/intent-design-reference.md
@docs/architecture/memory-design-reference.md
@docs/implementation/e2e01-thin-slice-implementation-spec.md
@docs/implementation/e2e01-thin-slice-multi-agent-plan.md
@src/mini_agent/application/persistence.py
@tests/component/application/test_persistence_contract.py

只使用项目受控execution adapter；不得调用stock `gsd-plan-phase`、`gsd-execute-phase`、`gsd-verify-work`、lifecycle mutation或`gsd-ship`。
</execution_context>

<interfaces>

## 1. Exact feature identity and ownership

repository: `/Users/ming/projects/mini-agent`

remote: `https://github.com/weijie567/mini-agent.git`

feature_branch: `codex/e2e01-01-ru-v1-codec-contract`

feature_worktree: `e2e01-01-ru-v1-codec-contract`

writer: `/root Integrator / Application persistence codec two-file sole writer`

pull_request_base: `integration/e2e01-thin`

base_sha: `9e8c70db39786b35c1ebea5070a32a1bc36e0df7`

base_tree: `4b01798be73c15ae0b3eda42483078cbd7cdf7dc`

input_barrier: `B_X`

output_barrier: `B_T / ONLY AFTER REVIEWED FEATURE MERGE AND POST-MERGE GATES`

owned_files_at_base:

- `src/mini_agent/application/persistence.py = 37db31ecf18707c21fff1ca9a9505cd9c4fb3555`
- `tests/component/application/test_persistence_contract.py = 26d07270be74f87ca300d62979c97ec7b99e28ba`

allowlist: the exact two paths above.

expected_actual_change: both paths。Component test拥有RED absence/current-only guard并迁移legacy fixtures；source删除RU-v1 codec surface。

forbidden_files: `ALL REPOSITORY FILES OUTSIDE THE TWO-FILE ALLOWLIST`，尤其包括`src/mini_agent/application/ports.py`、`src/mini_agent/application/records.py`、other `src/mini_agent/application/**`、`src/mini_agent/core/**`、`src/mini_agent/infrastructure/**`、`src/mini_agent/evaluation/**`、other `tests/**`、`evals/**`、`alembic/**`、`pyproject.toml`、`uv.lock`、`compose.yaml`、`docs/**`、`.planning/**`、`AGENTS.md`、`PROJECT_DIRECTION.md`、`README.md`、`graphify-out/**`。

Plan branch/worktree从`B_X`后的current integration创建并只拥有本Plan文件；Plan merge只记录签发。feature必须从上述exact `B_X`另建clean Worktree，不得使用本Plan merge、status merge或其后任一documentation SHA作为base。

## 2. Exact RU-v1 codec deletion boundary

T必须从`persistence.py`删除以下RU-v1 executable representation：

- exact imports `RequestUnderstandingRecord`、`AcceptedTaskDelta`；
- `_REGISTRY[P0RecordCode.REQUEST_UNDERSTANDING_RECORD]`中的v1 parent spec；
- v1 `P0LogicalChildCode.ACCEPTED_TASK_DELTA` child spec；
- `_P0_V1_PERSISTENCE_REGISTRY`及其17-v1 compatibility含义；
- `(REQUEST_UNDERSTANDING_RECORD, "request_understanding_record.p0.v1")` catalog pair；
- generic与explicit-version API对RU-v1 source/child/envelope的成功路径。

T保留且不得放松：

- `P0RecordCode` 17个code与`P0LogicalChildCode` 3个code；
- `P0_PERSISTENCE_REGISTRY` 17-code immutable current mapping；
- RU current exact pair `request_understanding_record.p0.v2`；
- `RequestUnderstandingRecordV2` / `AcceptedTaskDeltaV2` exact-type、projection、closure、owner/reference与version mirror校验；
- 其他16个record的v1 source spec、identity、owner/reference/child/version及generic codec行为；
- `TaskStateTransition` / `ToolAttemptRecord` child specs；
- bounded error、strict JSON、no subclass、no undeclared private state、zero-I/O/no fallback约束。

建议内部结构为一个immutable 16-code non-RU registry与两个non-RU child specs；public current registry/catalog/child mapping在v2 spec定义后由16个非RU spec加RU-v2 spec组装。内部命名不得继续把RU-v1称为current/legacy compatibility，也不得增加第二个public registry、alias、runtime register、config switch或latest selector。

## 3. Public and exact-version API behavior after closure

`P0_PERSISTENCE_REGISTRY`必须恰为17项，顺序仍等于`P0RecordCode`，RU spec exact为v2；其他16项对象与各自现有v1 spec相同。

`P0_RECORD_SCHEMA_VERSION_CATALOG`必须恰为17项，并与public current registry形成one-to-one exact pair：

- 16个非RU pair仍为`<record_code>.p0.v1`；
- RU唯一pair为`request_understanding_record.p0.v2`；
- catalog spec对象与active registry对象逐项`is`相同；
- RU-v1 pair lookup必须不存在，不能保留hidden alias或由type/payload fallback。

`P0_LOGICAL_CHILD_SPECS`必须恰为3项：

- `ACCEPTED_TASK_DELTA → AcceptedTaskDeltaV2`；
- `TASK_STATE_TRANSITION → TaskStateTransition`；
- `TOOL_ATTEMPT_RECORD → ToolAttemptRecord`。

existing generic APIs的signature保持，避免越界修改非RU Infrastructure callers；但其适用面收窄为16个非RU current-v1 record：

```python
encode_persistence_record(record_code, record, *, external_references=(), logical_children=())
decode_persistence_record(envelope, *, expected_record_code, correlation_ref)
```

当`record_code`或`expected_record_code`为RU时，generic API不得按source type、payload、outer metadata、active registry或catalog推断v1/v2，也不得尝试versioned path；必须bounded fail closed，固定为`UNKNOWN_RECORD_SCHEMA_VERSION`。RU caller必须使用两个existing exact-version APIs并显式提供code/version。

`encode_persistence_record_versioned` / `decode_persistence_record_versioned`签名保持；它们只接受17-pair current catalog。请求RU-v1 exact pair、用RU-v1 raw metadata喂给v2 decode或把v1 metadata写入v2 envelope均不得重建/升级/fallback；removed exact pair统一按`UNKNOWN_RECORD_SCHEMA_VERSION` fail closed。已知其他current code的version用于错误record code时仍为`RECORD_SCHEMA_VERSION_MISMATCH`。

## 4. Component test migration and preservation

`test_persistence_contract.py`增加exact AST/runtime guard，证明：

- source没有v1 parent/child imports、name/attribute/dynamic alias；
- source没有`_P0_V1_PERSISTENCE_REGISTRY`、RU-v1 parent spec或v1 accepted child spec；
- catalog/active registry/current child mapping为上述exact 17/17/3 closure；
- generic RU encode/decode不推断版本；
- explicit RU-v1 pair与raw physical-v1 metadata bounded fail closed；
- v2 pair、types与strict closure仍存在。

现有`_record_cases()`从17项v1 fixture收敛为16项非RU fixture；所有generic codec参数化tests相应改名并保持16项identity/owner/reference/child/version/error矩阵。不得先构造RU-v1 DTO/envelope再过滤；owned test最终不得导入、实例化或动态访问v1 `RequestUnderstandingRecord` / `AcceptedTaskDelta`。

现有v2 fixture/tests继续覆盖RU current record与child。原“18-pair / all-17-v1 parity / cross-version v1-v2 coexistence”断言改为“17-pair current-only / 16 non-RU generic parity / removed-v1 raw metadata isolation”。historical-v1 oracle只能从v2 envelope做raw metadata literal drift，不得调用v1 codec或Core DTO。

以下证据必须继续存在并通过：

- 16个非RU source/identity/owner/reference/child roundtrip、replay、strict JSON与bounded error；
- v2 exact pair success/replay、zero/partial/multi-accepted closure；
- v2 contextualization、candidate/decision exact-set、Task effect与trusted-time projection；
- v2 owner/reference/child cardinality、metadata mirror、wrong pair/unknown version、subclass/private state与mutation resistance；
- current registry/catalog immutability与no register/alias/fallback；
- static dependency inventory对versioned codec caller的边界。

删除RU-v1 parameterized cases后允许focused test总数下降，但不得用数量下降掩盖current v2或16个非RU行为缺失。

## 5. Commit, replay and barrier protocol

1. RED commit只在`test_persistence_contract.py`增加RU-v1 absence/current-only contract guard；在未改source时应因v1 imports/registry/catalog/child/generic route存在而失败。
2. GREEN commit只在双文件allowlist内删除source surface并迁移全部owned tests；不得amend/rebase掉RED证据。
3. 任何review/test finding只用append-only allowlist内fix commit关闭；不得扩大owner或修改exact base。
4. exact-head review前证明feature从B_X线性起始、无merge commit、changed files恰为双文件且所有RU-v1 source/test executable依赖为零。
5. PASS后在包含T Plan merge的latest integration上建立throwaway overlay；Plan/documentation merge不得改变两个feature base blobs，仍须机械证明overlay patch与reviewed patch一致。
6. feature串行merge后运行focused、Infrastructure/database neighbor、canonical environment/full gate；只有该共同integration tree可命名`B_T`并解锁01-07W。

</interfaces>

<tasks>

<task type="auto">
  <name>Task 1: RED — 冻结RU current-only codec与v1 absence</name>
  <files>tests/component/application/test_persistence_contract.py</files>
  <action>
    增加exact AST/runtime contract test，禁止v1 parent/child import、private 17-v1 registry、RU-v1 catalog pair及generic/versioned成功路径，同时确认17-code active、17-pair catalog、v2 child/current pair与16个非RU generic surface仍存在。先只提交test并记录它因当前source compatibility surface而RED。
  </action>
  <verify>
    <automated>uv run pytest tests/component/application/test_persistence_contract.py -q</automated>
  </verify>
  <done>RED只指向RU-v1 compatibility，不误报其他16个v1 record或带V2后缀types。</done>
</task>

<task type="auto">
  <name>Task 2: GREEN — 删除RU-v1 codec representation并迁移Component contracts</name>
  <files>src/mini_agent/application/persistence.py, tests/component/application/test_persistence_contract.py</files>
  <action>
    删除RU-v1 imports、parent/child specs、private 17-v1 registry与catalog pair；组装16非RU+RU-v2的current registry/catalog及v2 accepted child mapping。generic API对RU固定UNKNOWN_RECORD_SCHEMA_VERSION，对16非RU保持行为；versioned API只接受17 current pairs。测试移除RU-v1 DTO/envelope fixture与coexistence结论，保留raw metadata isolation并将projection/count/category矩阵更新到current-only exact值。
  </action>
  <verify>
    <automated>uv run pytest tests/component/application/test_persistence_contract.py -q</automated>
  </verify>
  <done>owned source/test无RU-v1 executable依赖；17/17/3 current closure、16非RU generic与RU-v2 exact-version证据全部通过。</done>
</task>

<task type="auto">
  <name>Task 3: exact-head review、latest overlay与B_T gate</name>
  <files>exact two-file allowlist</files>
  <action>
    执行scope/commit containment、AST scan、focused、Application/Infrastructure/database neighbors、full gate和独立exact-head review。PASS后在latest integration replay并证明Plan-only delta未改变owned blobs；串行merge后复跑canonical gates，记录exact SHA/tree为B_T。不得同步status或提前启动W。
  </action>
  <verify>
    <automated>uv run pytest</automated>
  </verify>
  <done>reviewed T在单一post-merge tree形成可复现B_T；Case lifecycle与W/V owner未推进。</done>
</task>

</tasks>

<verification>

最低机械gate：

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

exact-head与latest overlay必须额外检查：

- first feature commit parent精确为`9e8c70db39786b35c1ebea5070a32a1bc36e0df7`，线性、无merge；
- changed files恰为双文件allowlist，禁止文件相对B_X均不变；
- source与owned test中的v1 parent/child imports、spec、registry、codec success path精确为零；
- catalog/active registry/current child mapping exact为17/17/3，projection counts为70/8/49；
- generic RU入口不推断版本，exact-version RU-v1 pair/raw metadata fail closed；
- 16个非RU generic行为与B_X一致；
- Infrastructure、Application Port/records与Core blobs保持B_X，等待W/V；
- independent reviewer `P0/P1/P2/P3 = 0/0/0/0`；
- latest overlay无冲突，feature patch与reviewed head一致；
- post-merge canonical full gate通过后才记录`B_T`。

</verification>

<contract_changes>

`SCOPED / EXECUTION-MAP AUTHORIZED`：删除Application persistence codec的RU-v1 parent/child representation、catalog pair及generic/explicit成功路径；current codec收敛为16个非RU v1加RU-v2。保留其他16个record的现行v1合同与RU-v2 exact-version合同；不激活01-07R。

</contract_changes>

<security_impact>

`BOUNDARY PRESERVING / DEFENSE IN DEPTH`：codec仍为zero-I/O，不授权owner lookup，不证明provenance、business fact或readiness。删除v1 fallback面并要求RU exact-version入口，继续保持strict type/version/owner/reference/closure校验与bounded errors；raw payload、secret和PII不得进入错误投影。

</security_impact>

<eval_impact>

`COMPONENT CONTRACT UPDATE ONLY`：更新Application codec Component tests以冻结current-only 17/17/3 closure、16个非RU回归与RU-v2 strict behavior。T不新增/激活Dataset Case，不改变Trajectory/E2E Result，不宣称产品结果完成。

</eval_impact>

<rollback>

Feature未merge时：关闭draft PR并保留branch/commit/test evidence，不修改integration。

Feature已merge但W尚未形成时：普通revert T merge并运行codec focused、Infrastructure/database/full gate，恢复到B_X compatibility面；不得reset/force。

若B_T后已有下游barrier，按`V → W → T`的实际依赖逆序先revert下游，再revert T。T不迁移或删除physical v1 rows，因此rollback不得声称恢复/丢失数据库内容。

</rollback>

<handoff>

Agent交接必须报告：

```text
Task Packet: 01-07T
Base SHA / tree:
Branch / Worktree:
RED commit and expected failure:
GREEN/fix commits:
Reviewed exact head / tree:
Actual changed files:
Commands and exact results:
Allowlist/containment result:
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

Agent完成只表示01-07T feature可交给Integrator审查，不表示`B_T`、`B_RU_V2_CONTRACT`、01-08或P0产品完成。

</handoff>

<cross_file_impact>

- `docs/implementation/e2e01-thin-slice-multi-agent-plan.md`是T两文件ownership与`B_X → B_T`顺序owner；feature不得修改。
- 01-07Q Plan中的18-pair/v1 compatibility正文是其执行时历史窗口证据，不随T重写；本Plan拥有当前T签发。
- `src/mini_agent/application/ports.py`、`records.py`及其tests仍保留v1 command/Port至01-07W；Core v1 DTO/tests仍保留至01-07V。
- `.planning/PROJECT.md`、`.planning/STATE.md`、`.planning/ROADMAP.md`、`.planning/REQUIREMENTS.md`、W2 Validation、`PROJECT_DIRECTION.md`与`README.md`仍待dedicated status Packet；T不越界更新。
- Graphify保持用户要求的闲置状态。

</cross_file_impact>
