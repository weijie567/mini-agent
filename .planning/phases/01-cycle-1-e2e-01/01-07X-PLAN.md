---
phase: 01-cycle-1-e2e-01
plan: 07X
type: tdd
wave: 29
depends_on:
  - 01-07S
  - 01-07U
files_modified:
  - src/mini_agent/infrastructure/persistence/postgres.py
  - tests/integration/test_postgres_record_adapters.py
  - tests/integration/test_postgres_atomicity.py
  - tests/integration/test_postgres_v2_request_understanding_writes.py
autonomous: true
requirements:
  - E2E01-01
  - E2E01-04
user_setup: []
must_haves:
  truths:
    - "PostgresRecordAdapter不再定义、导入或暴露RU-v1 initial-graph writer、RU-v1 parent reader或AcceptedTaskDelta-v1 reader；active Infrastructure RU path只保留两个exact-v2 writer与现有owner-scoped exact-v2 evidence reader。"
    - "删除live v1 writer不能削弱historical physical-v1 collision fail-closed：现存同Run request_understanding_record.p0.v1 row仍使v2 writer返回PROJECTION_CONFLICT且零写入，X不迁移或删除历史物理row。"
    - "AA已经建立的v2 success、replay、conflict、atomicity、owner isolation、v2-v2 concurrency、v2/recovery及v2/finalization lock-order证据必须保留；只删除live v1/v2双writer共存oracle。"
    - "Application的CreateInitialTaskGraphCommand、RuntimeRecordPort legacy methods与对应contract tests继续隔离保留到01-07W；Application codec v1 representation留给01-07T，Core v1 types留给01-07V。"
    - "01-07X不得修改migration、Application、Core、Runtime、Eval、Composition Root、canonical owner、派生status或Case lifecycle；X reviewed merge与post-merge gate只形成B_X。"
  artifacts:
    - "PostgresRecordAdapter RU-v2-only executable surface与exact AST/API absence guard。"
    - "historical-v1 collision零写入、v2 atomicity/recovery/finalization及通用Task transition回归证据。"
  key_links:
    - "B_SU → 01-07X Infrastructure closure → B_X。"
    - "PostgresRecordAdapter → CreateInitialTaskGraphV2Command / SaveRequestUnderstandingV2NoTaskCommand → request_understanding_record.p0.v2。"
    - "B_X只解锁01-07T；T → W → V后才形成B_RU_V2_CONTRACT。"
---

# Phase 1 Plan 01-07X｜Infrastructure persistence v1-contract closure

> **ISSUED CONTRACT-CLOSURE TASK PACKET / IMPLEMENTATION NOT STARTED**
> 本Packet只关闭Infrastructure PostgreSQL Adapter的可执行RU-v1合同。Plan、RED/GREEN feature head或owner-remediation merge均不形成`B_X`；只有feature从exact `B_SU`完成独立review、latest-integration replay、串行merge与post-merge gate后才可命名该barrier。

> **DERIVED / NON_NORMATIVE**
> Request Understanding、Memory、Tool、安全、Eval与产品结果语义仍由active canonical owner拥有。本Plan只消费`p0-ru-v2-execution-map-r3`中的01-07X ownership，不建立第二套合同。Graphify按用户指令保持闲置，不读取、不运行、不更新、不作为gate。

<objective>
以最小TDD变更删除PostgreSQL Adapter中已被01-07AA/J替代的RU-v1 writer与两个v1-only reader，并将Infra integration tests从“live v1/v2 writer共存”收敛为“v2-only active writer + historical-v1 row fail-closed”。

Purpose: exact `B_SU`上的active Runtime已不调用legacy writer，但`PostgresRecordAdapter`仍公开`create_initial_task_graph_if_current`、`load_request_understanding_for_owner`与`load_accepted_task_delta_for_owner`。五个atomicity direct caller和AA-owned integration file中的三个direct caller继续让Infra v1 surface可执行。X删除这些入口及对应v1 type imports，同时保留v2 writer的同Run physical-v1 collision fence、严格投影、原子性与恢复并发证据。

Output: 一个四文件、单一Infrastructure writer的feature Packet。RED先冻结exact AST/API absence；GREEN再删除source surface并迁移/收窄owned integration tests。Application Port、codec与Core closure严格留给T/W/V。
</objective>

<preflight_evidence>

- `CONFIRMED`：feature input必须是exact `B_SU = f037582446598512a0132a90504e24b5d701c0f6`，tree `4d9eb4b419301cd6b4ec7b272ca6f4bc0290f7cd`；S/U共同post-merge focused为`871 passed`，canonical full为`1980 passed, 1 deselected, 12 warnings`。
- `CONFIRMED`：execution-owner remediation [PR #134](https://github.com/weijie567/mini-agent/pull/134) reviewed merge为`de3b9b7795ee7d569526936da4f3f10e8e7d93e2`、tree `c2bc6495f03caf5079a8b81b928e4084fe7f7125`，只把遗漏的AA-owned integration test加入X并补全acceptance；它不替换feature base、不新增Packet、不改变42分母或`B_SU → B_X`。
- `CONFIRMED`：`postgres.py`唯一live RU-v1 writer为`create_initial_task_graph_if_current(CreateInitialTaskGraphCommand)`；同文件还存在无仓库caller的`load_request_understanding_for_owner -> RequestUnderstandingRecord`与`load_accepted_task_delta_for_owner -> AcceptedTaskDelta`。
- `CONFIRMED`：`test_postgres_atomicity.py`有五个legacy writer direct calls；`test_postgres_v2_request_understanding_writes.py`有三个direct calls，分布在live v1/v2顺序与lock-order coexistence tests。全仓没有其他production direct caller或dynamic string caller；Application Protocol definition与contract test归01-07W。
- `CONFIRMED`：AA-owned v2 suite已独立覆盖v2 roundtrip/replay、legacy-chain isolation、mid-reference rollback、distinct-v2 conflict、v2-v2 concurrency、fault matrix、bounded database failure、Run-first locking、no-task/initial nonhybrid closure、v2/recovery及v2/finalization convergence。
- `CONFIRMED`：exact B_SU三份owned integration test baseline为`136 passed`。第四个owned production file通过这些tests间接覆盖。
- `CONFIRMED`：physical-v1 version字符串仍被`_ru_v2_write_check_metadata_rows`用于同Run collision fail-closed；它不是live v1 API，X不得以全局字符串删除破坏该guard。`test_postgres_record_adapters.py`的strict exact-v2 reader tamper oracle同样必须保留。
- `OPEN / NONCLAIM`：X不迁移、不删除或声明不存在历史physical v1 rows；默认inactive的01-07R不因X激活。X不完成Application codec/Port/records、Core closure、zero/all-REJECT、multi-ACCEPT、atomic failure恢复产品结果、Composition Root或真实HTTP E2E。

</preflight_evidence>

<execution_context>
@AGENTS.md
@.planning/GOVERNANCE.md
@.planning/phases/01-cycle-1-e2e-01/01-07AA-PLAN.md
@.planning/phases/01-cycle-1-e2e-01/01-07S-PLAN.md
@.planning/phases/01-cycle-1-e2e-01/01-07U-PLAN.md
@docs/architecture/intent-design-reference.md
@docs/architecture/memory-design-reference.md
@docs/implementation/e2e01-thin-slice-implementation-spec.md
@docs/implementation/e2e01-thin-slice-multi-agent-plan.md
@src/mini_agent/infrastructure/persistence/postgres.py
@tests/integration/test_postgres_record_adapters.py
@tests/integration/test_postgres_atomicity.py
@tests/integration/test_postgres_v2_request_understanding_writes.py

只使用项目受控execution adapter；不得调用stock `gsd-plan-phase`、`gsd-execute-phase`、`gsd-verify-work`、lifecycle mutation或`gsd-ship`。
</execution_context>

<interfaces>

## 1. Exact feature identity and ownership

repository: `/Users/ming/projects/mini-agent`

remote: `https://github.com/weijie567/mini-agent.git`

feature_branch: `codex/e2e01-01-ru-v1-infra-contract`

feature_worktree: `e2e01-01-ru-v1-infra-contract`

writer: `/root Integrator / Infrastructure persistence adapter four-file sole writer`

pull_request_base: `integration/e2e01-thin`

base_sha: `f037582446598512a0132a90504e24b5d701c0f6`

base_tree: `4d9eb4b419301cd6b4ec7b272ca6f4bc0290f7cd`

input_barrier: `B_SU`

output_barrier: `B_X / ONLY AFTER REVIEWED FEATURE MERGE AND POST-MERGE GATES`

owned_files_at_base:

- `src/mini_agent/infrastructure/persistence/postgres.py` = `8843e3d4256a8df0ac53ab930eb9c52d473238cf`
- `tests/integration/test_postgres_record_adapters.py` = `3e4197487fc074966771154d32fd4a1249e0c954`
- `tests/integration/test_postgres_atomicity.py` = `b4df0061944bf4495e8aac86d9a5ba219b46513a`
- `tests/integration/test_postgres_v2_request_understanding_writes.py` = `0e981eb9f1d24341be97307ebc7d9aa8a6f371c2`

allowlist: the exact four paths above.

expected_actual_change: all four paths。`test_postgres_record_adapters.py`拥有RED结构guard；另外两个test files移除或迁移direct callers并保留v2/historical evidence；`postgres.py`删除legacy executable surface。

forbidden_files: `ALL REPOSITORY FILES OUTSIDE THE FOUR-FILE ALLOWLIST`，尤其包括`src/mini_agent/application/**`、`src/mini_agent/core/**`、`src/mini_agent/evaluation/**`、other `src/mini_agent/infrastructure/**`、other `tests/**`、`tests/conftest.py`、`evals/**`、`alembic/**`、`pyproject.toml`、`uv.lock`、`compose.yaml`、`docs/**`、`.planning/**`、`AGENTS.md`、`PROJECT_DIRECTION.md`、`README.md`、`graphify-out/**`。

Plan branch/worktree从owner-remediation后的latest integration创建并只拥有本Plan文件；Plan merge只记录签发。feature必须从上述exact `B_SU`另建clean Worktree，不得使用PR #134 merge、本Plan merge、status merge或其后任一documentation SHA作为base。

## 2. Exact Infrastructure RU-v1 deletion boundary

X必须从`postgres.py`删除以下exact legacy imports / executable members：

- `CreateInitialTaskGraphCommand`
- `AcceptedTaskDelta`
- `RequestUnderstandingRecord`
- `PostgresRecordAdapter.create_initial_task_graph_if_current`
- `PostgresRecordAdapter.load_request_understanding_for_owner`
- `PostgresRecordAdapter.load_accepted_task_delta_for_owner`

AST/API guard必须按exact identifier、import alias、class member和attribute call检查；带显式`V2`后缀的`CreateInitialTaskGraphV2Command`、`AcceptedTaskDeltaV2`、`RequestUnderstandingRecordV2`与`create_initial_task_graph_v2_if_current`不能被误报或删除。

X不得删除或放松：

- `save_request_understanding_v2_no_task_if_current`
- `create_initial_task_graph_v2_if_current`
- exact-Run v2 reader / evidence closure
- `_ru_v2_write_*` owner/version/projection/CAS/collision chain
- 对`request_understanding_record.p0.v1` historical row的metadata-only collision detection
- 非RU record使用的generic `encode_persistence_record` / `decode_persistence_record`

Application `RuntimeRecordPort`的legacy writer/readers及其DTO imports仍可在B_X至B_W窗口存在，但active Runtime不得调用。X不得通过alias、`__getattr__`、optional callback、union command、test-only method、dynamic probing或v2→v1 projection保留Infra compatibility surface。

## 3. Integration test migration and preservation

`test_postgres_record_adapters.py`增加exact AST/API contract guard，证明六个legacy import/member/call surface为零，并明确两个v2 writer与v2 record/child types仍存在。strict exact-v2 reader面对physical-v1 version、foreign owner、projection/reference drift的fail-closed tests保持。

`test_postgres_atomicity.py`移除对legacy writer的五个direct calls：

- v1-writer专属且已被AA v2 suite更强覆盖的rollback/recovery/finalization并发oracle可以删除；
- 通用Task transition仍需以reviewed v2 initial graph建立前置状态后继续验证exact projection CAS与单一atomic child；
- 若保留其他通用atomicity test，必须改用`create_initial_task_graph_v2_if_current`与v2 roots，不能复制AA私有writer逻辑或降低断言。

`test_postgres_v2_request_understanding_writes.py`删除live legacy writer invocation与“两种writer都可赢”的共存结论。至少保留一个显式historical fixture：直接持久化合法`request_understanding_record.p0.v1` envelope或等价预存row，再调用active v2 writer，断言`PROJECTION_CONFLICT`、完整physical snapshot不变且没有第二个Task graph。该fixture只证明历史row隔离，不重新暴露legacy writer。

以下AA证据必须继续存在并通过：v2 success/replay、v2-v2 conflict/concurrency、wrong-owner isolation、mid-write/fault rollback、bounded error、Run-first lock、no-task/initial nonhybrid、v2/recovery与v2/finalization convergence。删除重复legacy oracle后允许focused test总数下降，但不得用数量下降掩盖上述命名行为缺失。

## 4. Commit, replay and barrier protocol

1. RED commit只在`test_postgres_record_adapters.py`增加exact AST/API absence guard；在未改source时应仅因六个legacy surface存在而失败，v2 presence assertions应通过。
2. GREEN commit在四文件allowlist内删除source surface、移除direct callers、迁移通用atomicity setup并增加historical-v1 collision oracle；不得amend/rebase掉RED证据。
3. 任何review/test finding只用append-only allowlist内fix commit关闭；不得扩大owner或修改exact base。
4. exact-head review前证明feature从B_SU线性起始、无merge commit、changed files为四文件子集且所有direct callers/imports/members精确为零。
5. PASS后在包含PR #134与X Plan merge的latest integration上建立throwaway overlay；两次documentation merge不应改变四个feature blobs，仍须机械证明merge-tree与reviewed patch一致。
6. feature串行merge后运行focused、Infrastructure/database neighbor、canonical environment/full gate；只有该共同integration tree可命名`B_X`并解锁01-07T。

</interfaces>

<tasks>

<task type="auto">
  <name>Task 1: RED — 冻结PostgreSQL Adapter RU-v2-only executable surface</name>
  <files>tests/integration/test_postgres_record_adapters.py</files>
  <action>
    增加exact AST/API contract test，禁止三个legacy type imports、三个legacy Adapter members及其dynamic alias/call，同时确认两个v2 writer、V2 parent/child types与historical collision guard仍存在。先只提交test并记录它因当前source legacy members存在而RED。
  </action>
  <verify>
    <automated>uv run pytest tests/integration/test_postgres_record_adapters.py -q</automated>
  </verify>
  <done>RED只指向exact legacy imports/members，不误报V2后缀或physical-v1 collision string。</done>
</task>

<task type="auto">
  <name>Task 2: GREEN — 删除legacy writer/readers并迁移owned integration callers</name>
  <files>src/mini_agent/infrastructure/persistence/postgres.py, tests/integration/test_postgres_record_adapters.py, tests/integration/test_postgres_atomicity.py, tests/integration/test_postgres_v2_request_understanding_writes.py</files>
  <action>
    删除三个legacy imports与三个Adapter methods。移除八个direct callers和live v1/v2 coexistence oracle；通用Task transition改由v2 graph建立，历史v1 row改以非路由physical fixture证明v2 writer fail-closed/零写入。保留AA v2 writer、owner isolation、atomicity、recovery/finalization lock-order与strict reader tests。
  </action>
  <verify>
    <automated>uv run pytest tests/integration/test_postgres_record_adapters.py tests/integration/test_postgres_atomicity.py tests/integration/test_postgres_v2_request_understanding_writes.py -q</automated>
  </verify>
  <done>legacy executable surface与direct callers为零；v2/historical fail-closed证据通过，实际变更不出四文件。</done>
</task>

<task type="auto">
  <name>Task 3: exact-head review、latest overlay与B_X gate</name>
  <files>exact four-file allowlist</files>
  <action>
    执行scope/commit containment、AST scan、focused、Application Port isolation neighbor、Infrastructure/database/full gates和独立exact-head review。PASS后在latest integration replay并验证documentation-only delta；串行merge后复跑canonical gates，记录exact SHA/tree为B_X。不得同步status或提前启动T。
  </action>
  <verify>
    <automated>uv run pytest</automated>
  </verify>
  <done>reviewed X在单一post-merge tree形成可复现B_X；Case lifecycle与下游owner未推进。</done>
</task>

</tasks>

<verification>

最低机械gate：

```bash
git diff --check
uv run pytest tests/integration/test_postgres_record_adapters.py tests/integration/test_postgres_atomicity.py tests/integration/test_postgres_v2_request_understanding_writes.py -q
uv run pytest tests/integration/test_agent_run_service_v2_persistence.py tests/component/application/test_ports_contract.py -q
uv run pytest tests/integration -q
uv sync --all-groups
docker compose up --wait -d db
docker compose --profile test up --wait -d db-test
uv run alembic upgrade head
uv run pytest
```

exact-head与latest overlay必须额外检查：

- first feature commit parent精确为`f037582446598512a0132a90504e24b5d701c0f6`，线性、无merge；
- changed files是四文件allowlist的子集，禁止文件相对B_SU均不变；
- exact legacy imports、Adapter definitions与全仓Infra direct callers为零；
- Application Port/records/codec与Core v1 surface保持B_SU blob，等待T/W/V；
- historical physical-v1 collision仍fail closed且零变更；
- v2-v2、v2/recovery、v2/finalization与strict exact-v2 reader证据仍存在；
- independent reviewer `P0/P1/P2/P3 = 0/0/0/0`；
- latest overlay无冲突，feature patch/tree与reviewed head一致；
- post-merge canonical full gate通过后才记录`B_X`。

</verification>

<contract_changes>

`SCOPED / EXECUTION-MAP AUTHORIZED`：删除Infrastructure PostgreSQL Adapter的RU-v1 writer、RU-v1 parent reader、AcceptedTaskDelta-v1 reader及对应type imports。保留physical-v1 row的隔离检测与Application/Core/codec阶段性合同；不激活01-07R。

</contract_changes>

<security_impact>

`BOUNDARY PRESERVING / DEFENSE IN DEPTH`：不改变可信身份、授权或最小披露；删除未路由legacy入口，继续要求owner-scoped roots、same-Run current-v1 collision、strict version/projection/reference校验与零部分写入。任何absent/unauthorized差异仍不可区分，bounded errors不得暴露payload或PII。

</security_impact>

<eval_impact>

`COMPONENT / INTEGRATION EVIDENCE MAINTENANCE ONLY`：不新增或推进EvalCase lifecycle，不修改Dataset/Grader/Result。删除live v1/v2 coexistence oracle，保留active v2 writer与historical-v1 isolation、atomicity、recovery/finalization轨迹的可复现integration evidence。

</eval_impact>

<rollback>

Plan未执行时：普通revert Plan merge即可撤销签发记录，不影响`B_SU`。

Feature未merge时：关闭draft PR并保留branch/commit/test evidence，不修改integration。

Feature已merge但T尚未形成时：普通revert X merge并运行四文件focused、database/full gate，恢复到`B_SU`兼容面；不得reset/force。

若`B_X`后已有下游barrier，按`V → W → T → X`的实际依赖逆序先revert下游，再revert X。若部署环境已产生只能由新版本解释的状态，必须先由对应owner给出兼容性裁决；X本身不迁移或删除physical v1 rows。

</rollback>

<handoff>

handoff_to: `/root Integrator`

handoff_format:

```text
Task / branch / worktree:
Exact base SHA / tree:
RED commit / observed failure:
GREEN and fix commits:
Exact head SHA / tree:
Actual changed files:
Commands run:
Results:
Legacy AST/API/direct-caller scan:
Historical-v1 collision evidence:
V2 evidence retained:
Contract changes:
Security impact:
Eval impact:
Allowlist / forbidden-file check:
Assumptions:
Unresolved risks:
Rollback:
Recommended merge order:
```

Agent完成只表示01-07X feature可交给Integrator审查，不表示`B_X`、`B_RU_V2_CONTRACT`、01-08或P0产品完成。

</handoff>

<cross_file_impact>

- `docs/implementation/e2e01-thin-slice-multi-agent-plan.md`已由PR #134升级为r3并拥有四文件X scope；feature不得修改该owner。
- `.planning/phases/01-cycle-1-e2e-01/01-07O-PLAN.md`是已执行历史派生Plan，其三文件旧快照不随active owner重写；本Plan引用r3并覆盖当前X签发。
- `.planning/PROJECT.md`、`.planning/STATE.md`、`.planning/ROADMAP.md`、`.planning/REQUIREMENTS.md`、W2 Validation、`PROJECT_DIRECTION.md`与`README.md`仍待各自dedicated status Packet对齐S/U/B_SU/X进度；本Plan不越界更新。
- 01-07T/W/V必须分别从reviewed前一barrier签发；X不得提前删除其Application codec/Port/records或Core surface。
- Graphify保持用户要求的闲置状态。

</cross_file_impact>

