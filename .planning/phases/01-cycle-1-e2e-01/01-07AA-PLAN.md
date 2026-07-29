---
phase: 01-cycle-1-e2e-01
plan: 07AA
type: tdd
wave: 26
depends_on:
  - 01-07Y
  - 01-07Z
  - 01-07AA-ORACLE-FIX
  - 01-07AA-CODEC-HANDOFF
  - 01-07AA-CODEC-BOUNDARY-SCOPE-AMENDMENT
files_modified:
  - src/mini_agent/infrastructure/persistence/postgres.py
  - tests/integration/test_postgres_v2_request_understanding_writes.py
autonomous: true
requirements:
  - E2E01-01
  - E2E01-04
user_setup: []
must_haves:
  truths:
    - "01-07AA 只实现01-07Z两个exact-v2 RuntimeRecordPort方法的PostgreSQL Adapter，并且两个route都在一个owner-consistent transaction中原子完成。"
    - "writer必须静态提供exact record-code/version map，并让encode、decode、projection、persist、normalized references、physical validation与owner closure全链使用该map；不得从payload/envelope推断version，也不得只替换encoder后调用legacy helper。"
    - "no-task route只持久化一个RU-v2 parent且没有accepted child、Task、RequestUnit、InputBinding或links；initial-graph route持久化RU-v2 parent/唯一accepted child与完整Task graph。"
    - "writer先以trusted owner scope锁定exact Conversation、全部referenced Message与active Run roots，再拒绝current-v1 RU collision、owner/version/closure/CAS冲突；NOT_APPLICABLE、PROJECTION_CONFLICT与任一异常都必须零部分写。"
    - "exact replay必须保持所有record identity、created_at、physical row/reference count与payload不变；partial replay、conflicting replay、v1/v2混合或同Run第二个RU整体fail closed。"
    - "成功写入必须由01-07K load_exact_run_evidence_for_owner回读为exact RU-v2 no-task或initial graph closure；不得用raw SQL、codec输出或writer返回值代替reader oracle。"
    - "既有v1 create_initial_task_graph_if_current surface与行为保留到01-07X；01-07AA不修改migration、Application contract、Core、Runtime、Eval或active routing。"
    - "01-07AA完成只形成reviewed B_J_READY；不表示01-07J已切换、B_ACTIVE已形成、Case/E2E已通过或切片已ready。"
  artifacts:
    - "PostgresRecordAdapter.save_request_understanding_v2_no_task_if_current 的exact-v2 atomic writer。"
    - "PostgresRecordAdapter.create_initial_task_graph_v2_if_current 的exact-v2 atomic initial-graph writer。"
    - "writer-private exact-version persistence/physical-validation chain与tests/integration/test_postgres_v2_request_understanding_writes.py故障、冲突、replay、reader round-trip证据。"
  key_links:
    - "01-07Y deterministic reducer output → 01-07Z exact-v2 commands → 01-07AA static-version PostgreSQL writers。"
    - "01-07K owner-scoped exact-v2 reader → writer成功后的authoritative round-trip oracle。"
    - "Memory owner atomic graph/trusted owner/exact-version/replay → same-transaction locks、closed set、zero-partial-write与bounded failure。"
    - "Execution map r2的产品依赖仍为exact B_YZ → 01-07AA → B_J_READY；acceptance route经reviewed Application closure与codec dependency remediation精确收敛为B_AA_CODEC_HANDOFF → 01-07AA-r2 → B_J_READY，01-07J仍只能从reviewed B_J_READY启动。"
---

# Phase 1 Plan 01-07AA｜PostgreSQL RU-v2 atomic writers

> **ISSUED ACTIVE_SWITCH PREREQUISITE TASK PACKET / IMPLEMENTATION NOT STARTED**
> 本Packet只冻结Infrastructure PostgreSQL writer实现。Plan、RED test或AA feature完成都不表示Runtime已调用v2 Port、`B_ACTIVE`已形成、Case/E2E已通过或产品ready。

> **ACCEPTANCE REPLAY AMENDMENT**
> 原始B_YZ donor已形成exact RED `4f6b9befece09ac89947d5c90cb8f3b307f1c3b3`与GREEN `c28d3536a5034d5ae0c3030a561952d5d75b06e1`，但其exact head缺少Application closure oracle remediation。r1从reviewed closure remediation merge `119a05737a00fde219094c5bb192ceaeae84c0ad` clean创建，fresh RED/GREEN为`fbc91d1a658ba3506749907502b624e8ed6e30dd` / `5345e70e696942e3b7d4eaed59eaa39b5e258458`，随后因pre-writer codec dependency guard与AA contract冲突而冻结，未push、送审或merge。reviewed codec handoff merge `9a58aa6dff9895bef3425a075bf3495b4e858b74` 已形成exact `B_AA_CODEC_HANDOFF`。本r2只从该barrier clean创建，以fresh commits重放r1的同一two-file RED→GREEN patch；所有旧branch/worktree只作read-only patch provenance，不新增产品Packet、不改变42分母。

> **DERIVED / NON_NORMATIVE**
> RU-v2 aggregate、Application command、trusted owner、exact-version、atomic write与reader语义仍由Intent、Memory、Thin Slice及已经reviewed的Y/Z/K owner拥有。本Plan只消费execution map r2的AA ownership，不创建第二套canonical语义。

<objective>
以TDD RED→GREEN实现01-07Z已经冻结的两个exact-v2 conditional write Port：合法zero/all-REJECT no-task parent write，以及exact-one accepted initial Task graph write。

Purpose: 关闭原始`B_YZ`中“Application已经有exact-v2 command/Port，但PostgreSQL Adapter仍只有legacy-v1 initial graph writer”的最后一道01-07J前置阻断；并在reviewed closure remediation之后让01-07K authoritative reader能够验收合法lowercase candidate / canonical binding graph。后续Runtime可以显式调用v2 route，而不通过active/default/latest、v1/v2 union、payload inference或legacy helper fallback持久化。

Output: 从冻结donor逐commit重放一个只增加owned Integration test的RED，以及一个只修改`postgres.py`的GREEN；fresh commits保持原subject/patch equivalence，review finding只用append-only fix。AA不创建Summary、不修改shared State、canonical docs、Application/Core/Runtime/Eval、migration或shared test bootstrap。
</objective>

<execution_context>
@AGENTS.md
@.planning/GOVERNANCE.md
@.planning/phases/01-cycle-1-e2e-01/01-07K-PLAN.md
@.planning/phases/01-cycle-1-e2e-01/01-07Y-PLAN.md
@.planning/phases/01-cycle-1-e2e-01/01-07Z-PLAN.md
@.planning/phases/01-cycle-1-e2e-01/01-07AA-ORACLE-FIX-PLAN.md
@docs/architecture/intent-design-reference.md
@docs/architecture/memory-design-reference.md
@docs/implementation/e2e01-thin-slice-implementation-spec.md
@docs/implementation/e2e01-thin-slice-multi-agent-plan.md
@src/mini_agent/application/persistence.py
@src/mini_agent/application/records.py
@src/mini_agent/application/ports.py
@src/mini_agent/infrastructure/persistence/models.py
@src/mini_agent/infrastructure/persistence/postgres.py
@tests/integration/test_postgres_record_adapters.py
@tests/integration/test_postgres_atomicity.py

只使用项目受控execution adapter；不得调用stock `gsd-plan-phase`、`gsd-execute-phase`、`gsd-verify-work`、lifecycle mutation或`gsd-ship`。Graphify按用户指令保持闲置：不读取、不运行、不更新，也不作为gate。
</execution_context>

<interfaces>

## 1. Exact public Adapter surface

`PostgresRecordAdapter`实现既有Application Port的exact methods，不增加第三个public v2 writer：

```python
async def save_request_understanding_v2_no_task_if_current(
    self,
    command: SaveRequestUnderstandingV2NoTaskCommand,
) -> ConditionalWriteResult: ...

async def create_initial_task_graph_v2_if_current(
    self,
    command: CreateInitialTaskGraphV2Command,
) -> ConditionalWriteResult: ...
```

- 输入必须是Z已构造并递归canonical验证的exact command；Infrastructure不得用mapping、subclass、alias、field duck typing、`hasattr`、dynamic import或v1/v2 union重新解释。
- `APPLIED`表示完整目标aggregate已在本事务新写入，或数据库中已经存在byte-for-byte相同的完整exact replay。
- trusted roots absent / unauthorized统一`NOT_APPLICABLE`且零写；root已owner-scoped选中但不再等于command、同Run闭包或目标identity冲突统一`PROJECTION_CONFLICT`且零写。
- root或closure physical corruption、unknown/wrong version、owner drift、reference/metadata/payload mismatch使用现有最窄bounded `P0PersistenceIntegrityError`；SQLAlchemy/database failure继续经现有bounded system-error boundary清除raw context。
- 返回结果、exception或日志不得携带customer/message/payload、SQL、secret、raw token或第二份authority。

existing `create_initial_task_graph_if_current(CreateInitialTaskGraphCommand)`的public signature、legacy-v1 encode/decode/persist path与无same-Run collision时的既有成功/冲突语义保持不变；v1 writer只作为未路由compatibility surface保留到01-07X，绝不作为v2 writer fallback。AA唯一获准触及legacy method的改动，是在它已经锁定并验证exact Run后、任何target insert前调用Section 3同一个version-neutral metadata-only same-Run RU/RunTaskLink collision fence；该guard只让此前可能形成第二个不同identity RU closure的状态fail closed，不读取或解释v2 payload，也不把v1 method改造成v2 route。

## 2. Writer-owned static exact-version chain

AA在`postgres.py`内增加private、immutable exact map，至少覆盖两条route会触及的全部family：

| record code | expected version |
|---|---|
| `conversation_record` | `conversation_record.p0.v1` |
| `message_record` | `message_record.p0.v1` |
| `agent_run_record` | `agent_run_record.p0.v1` |
| `request_understanding_record` | `request_understanding_record.p0.v2` |
| `task_record` | `task_record.p0.v1` |
| `request_unit_record` | `request_unit_record.p0.v1` |
| `input_binding_record` | `input_binding_record.p0.v1` |
| `conversation_task_link_record` | `conversation_task_link_record.p0.v1` |
| `run_task_link_record` | `run_task_link_record.p0.v1` |

该map由writer call site静态选择，不读取或推断自：

- envelope/payload中的version；
- active registry/default/latest；
- source model的`schema_version`镜像；
- database row已有version；
- Runtime参数、caller hint、try-v2-then-v1或异常fallback。

writer-private helper全链必须显式接收expected-version map并保持相同pair：

1. 使用`encode_persistence_record_versioned(code, expected_version, ...)`构造目标envelope；
2. 立即使用`decode_persistence_record_versioned(... expected_record_code=code, expected_schema_version=expected_version ...)`验证source/children与目标exact相等；
3. 从同一validated decoded source/envelope投影physical columns；
4. 以deterministic `(record_code, logical_identity)`顺序insert/lock records与normalized references；
5. 对每个row使用同一exact pair重读、versioned decode并验证metadata/payload/reference/owner parity；
6. 从同一versioned decoded graph验证direct/scope owner closure和所有external/top-level references；
7. commit前再次验证完整目标closed set与Run recovery anchor。

禁止只把RU encoder改为versioned，然后调用现有`_persist_envelopes`、`_decode_envelope`、`_decode_row`、`_validate_physical_projection`或`_derive_owner_from_graph`来完成v2链；这些legacy helpers可继续服务既有v1 methods，但不能成为AA active v2 write chain。允许提取不含version选择的机械primitive，但new v2 call path的版本输入必须从static map贯穿。

## 3. Trusted root locks and current-Run closure

两个route在同一个`session_factory.begin()`事务内完成全部precondition、lock、write、physical validation与replay判断。任何会取得row lock的selector都必须先形成bounded identity set，再按canonical `(record_code, logical_identity)`排序后逐项`SELECT ... FOR UPDATE`；不能先按command field顺序锁Conversation / Message再锁Run。按当前record-code值，trusted root set中的exact owner-scoped active Run是与recovery/finalization共享的首锁，随后才是Conversation与按identity稳定排序的全部referenced Message。root set锁定后，same-Run已有RU与全部目标identity也按同一canonical row key排序锁定；initial-graph route再把Task / RequestUnit / InputBinding / link target identities纳入该稳定目标集合。不得在锁间执行无界扫描、按数据库返回顺序加锁，或让no-task与initial-graph采用不同排序。

root规则：

- Conversation / Message / Run trusted-root query必须同时限定exact logical identity与`scope_owner_customer_id=command.owner_scope.customer_id`；尤其必须先以该owner-scoped方式选中并strict-validate exact Run。任一trusted root零行时，不读取该identity或Run closure的private payload、不运行global collision probe，统一返回`NOT_APPLICABLE`。
- 每个selected root都使用static exact-v1 pair完成physical validation，并与command expected projection byte-for-byte相同；Conversation、Messages、Run任一CAS漂移为`PROJECTION_CONFLICT`。
- Message set必须逐项锁定且数量、identity、owner、Conversation、direction/content projection与command完全相同；不得只锁current Message、按Conversation扩大扫描或信任RU payload自报owner。
- Run必须仍为exact clean `RUNNING` root；writer通过existing no-op recovery-anchor CAS或等价single-row fence，保证与restart recovery/finalization使用同一真实Run首锁与后续canonical锁序。
- root选择后出现duplicate、wrong physical version、owner drift或metadata/reference corruption是bounded integrity failure，不降级为absence。

只有exact owner-scoped Run已经选中并通过static-v1 physical validation后，writer才运行private metadata-only collision selectors：

- same-Run selector只投影`record_id`、`record_code`、`logical_identity`、`record_schema_version`、`scope_owner_customer_id`以及用于selector的`run_id`，固定查询`request_understanding_record + exact trusted run_id`并以`ORDER BY logical_identity LIMIT 2 FOR UPDATE`检测zero/exact-one/overflow；两个route都以同样metadata-only、bounded方式探测`run_task_link_record + exact trusted run_id`，再从locked link metadata/normalized reference identity闭合目标集合。no-task首次写入要求link set为zero，no-task replay仍为zero；initial首次写入要求zero，initial exact replay要求恰有command中的一个link。不得选择ORM entity、`envelope`、direct payload owner、JSON path或任何payload-bearing expression。
- 每个command目标identity也先用exact code/identity的metadata-only `LIMIT 2 FOR UPDATE`探测；selected metadata的`scope_owner_customer_id`必须等于trusted scope，version必须等于writer static map。wrong-owner/wrong-version/duplicate在不读取envelope的情况下抛最窄bounded integrity error，error不得携带observed owner/identity。
- 只有metadata owner/version通过的row，才可再次以`record_id + exact code/identity + scope_owner_customer_id=trusted owner`执行payload-bearing read，并进入static-version decode/physical parity/owner closure；不得把metadata owner反向用作authority。
- selector的`LIMIT 2`是P0 exact current-Run cardinality的overflow sentinel，不是truncate。第二个RU、第二个RunTaskLink、同identity duplicate sentinel或selector结果在锁前后变化都整体fail closed；不得读取第二行envelope来决定结果。
- 所有compliant v1/v2 initial writer都先锁同一exact Run，并且都在获得Run锁后、insert前重跑同一个version-neutral metadata-only same-Run RU/RunTaskLink selector；Run首锁加双侧predicate recheck共同形成serialization fence，单独持有row lock不能替代recheck。AA不新增migration/index。legacy-v1 writer发现任意existing same-Run RU或RunTaskLink都保留其`PROJECTION_CONFLICT`/零写语义；AA writers再按static expected-version map区分legal exact replay与collision。Integration concurrency必须覆盖legacy先锁/AA后锁与AA先锁/legacy后锁两个顺序，证明最多一个完整RU closure提交。

same-Run RU closure在lock后必须证明：

- no-task route写入前该Run没有current RU row，或只有完整byte-identical RU-v2 no-task replay；
- initial-graph route写入前该Run没有current RU graph，或只有完整byte-identical RU-v2 initial graph replay；
- 任意RU-v1 row、第二个RU identity、v1/v2 mix、wrong-owner metadata、partial desired identities、extra accepted child/Task family或相同identity不同payload都整体`PROJECTION_CONFLICT`或最窄integrity failure；wrong-owner row的payload始终不可读。
- 不得覆盖、删除、repair、backfill、rewrite或把v1历史投影为v2。

## 4. No-task exact-v2 route

`save_request_understanding_v2_no_task_if_current`只编码一个：

```text
request_understanding_record.p0.v2 parent
logical_children = ()
```

- parent必须等于command的exact RU-v2 no-task record；
- normalized references必须由versioned codec生成并精确指向command已锁定的Run / Message set；
- 不创建Task、RequestUnit、InputBinding、ConversationTaskLink、RunTaskLink或accepted child；
- successful replay要求parent envelope、physical projections、normalized references、owner closure与row identity全相等；
- replay返回`APPLIED`但不得更新`record_id`、`stored_at`、logical `created_at`、envelope、reference identity/order或row/reference count。

01-07AA不决定zero/all-REJECT的Runtime用户结果；该route仍是non-routable prerequisite。

## 5. Exact-one initial Task graph route

`create_initial_task_graph_v2_if_current`构造以下exact envelopes：

- `request_understanding_record.p0.v2` parent，logical children恰为`(accepted_delta,)`；
- `task_record.p0.v1`；
- `request_unit_record.p0.v1`；
- 一个`input_binding_record.p0.v1`，保留现有`request_unit_id` external reference；
- `conversation_task_link_record.p0.v1`；
- `run_task_link_record.p0.v1`。

所有source和child直接取自Z command，不从RU payload重建Task family，也不把codec output当新authority。versioned encode/decode后须再次证明：

- RU parent / child / Task / RequestUnit / InputBinding / links exact等于command投影；
- RU child到Task/InputBinding、InputBinding到RequestUnit以及Task/Run/Conversation graph的normalized references完整、同owner且closed；
- target identity预查不存在时可以insert；全部目标identity已经存在且完整exact闭合时是legal replay；
- 任一目标identity单独存在、缺一项、extra row/reference、payload不同、wrong version/owner或target closure改变都是整体conflict/fail-closed；
- no-task parent不能被升级成initial graph，initial graph不能降级成no-task。

成功和replay后都必须在事务内重新versioned read-back；事务提交后Integration oracle再调用01-07K：

```python
await adapter.load_exact_run_evidence_for_owner(
    owner_scope=command.owner_scope,
    run_id=command.expected_active_run_record.run_id,
)
```

reader返回closure必须只含exact RU-v2，no-task route的Task family为空；initial graph route的accepted child / Task / RequestUnit / InputBinding / links与command exact相等。不得以writer helper直接读取、raw SQL row、mock/spy或codec round-trip替代该oracle。

## 6. Atomicity, concurrency, replay and bounded failures

Integration matrix至少覆盖：

- 两条route首次成功与01-07K exact reader round-trip；
- 两条routeexact replay：两次返回`APPLIED`，全部record/reference count、record IDs、`stored_at`、logical timestamps与envelope保持；
- missing与foreign owner roots得到不可区分`NOT_APPLICABLE`且零写；
- root stale/CAS、current RU-v1 collision、second RU、partial target set、conflicting target identity、owner drift、wrong code/version、payload/physical/reference mismatch整体零写；
- no-task不能留下accepted child/Task family；initial graph不能缺失任何parent/child/Task family；
- no-task与initial graph互相竞争、两个不同initial graph竞争，最多一个完整结果提交，另一个conflict，数据库不存在hybrid；
- restart recovery/finalization与v2 initial graph竞争沿同一stable lock order收敛，不死锁且不留下orphan；
- fault injection分别落在versioned encode/decode、physical projection、record insert、reference insert、post-insert validation、owner closure与recovery-anchor fence；任一异常后records/references精确回到baseline；
- database failure通过现有bounded system error暴露，`__cause__` / `__context__`清空，error projection不含owner、message、payload、SQL或secret。

测试不得使用`skip` / `xfail`、shared bootstrap修改或预先把expected v2 rows写入后只测reader。并发测试必须有bounded timeout和deterministic synchronization，不用sleep证明原子性。

</interfaces>

<packet_contract>
repository: `https://github.com/weijie567/mini-agent`
remote: `origin`
head_branch: `codex/e2e01-01-ru-v2-atomic-writer-r2`
base_branch: `integration/e2e01-thin`
base_sha: `9a58aa6dff9895bef3425a075bf3495b4e858b74`
base_tree: `1f8cc68f043f33e91d3f01a4f4cc9c5a3dd03587`
original_input_barrier: `B_YZ = d704b87480f0a4252744f4c009cef9a86c08fa05`
acceptance_base_sha: `9a58aa6dff9895bef3425a075bf3495b4e858b74`
acceptance_base_tree: `1f8cc68f043f33e91d3f01a4f4cc9c5a3dd03587`
input_barrier: `B_AA_CODEC_HANDOFF = 9a58aa6dff9895bef3425a075bf3495b4e858b74 / REVIEWED CODEC DEPENDENCY-GATE REMEDIATION DESCENDANT OF B_YZ`
output_barrier: `B_J_READY / ONLY AFTER 01-07AA FEATURE EXACT-HEAD AND LATEST-INTEGRATION OVERLAY REVIEWED-SERIAL-MERGED`
worktree_id: `e2e01-01-ru-v2-atomic-writer-r2`
writer: `Infrastructure PostgreSQL v2 Request Understanding writer sole writer, supervised by /root Integrator`
agent_role: `infra-engineer`
active_routing: `false`
denominator_delta: `0`

planning_and_owner_provenance:

- original product input barrier/tree `B_YZ = d704b87480f0a4252744f4c009cef9a86c08fa05` / `1162ba009147c5c8cefb8a0c2bc39254b96facef`
- first replacement acceptance base/tree `B_YZ_CLOSURE_ORACLE_FIX = 119a05737a00fde219094c5bb192ceaeae84c0ad` / `31ffed26d8e108bfdbb33053505104b219efad4f`
- final replacement acceptance base/tree `B_AA_CODEC_HANDOFF = 9a58aa6dff9895bef3425a075bf3495b4e858b74` / `1f8cc68f043f33e91d3f01a4f4cc9c5a3dd03587`
- 01-07Y final exact feature head/tree `04d2cfe9b1db0eba5321f389d5578b1af035ba53` / `4e3d338ab2e4735478872f77e11764a5f2072b7f`
- 01-07Y reviewed merge `d4777ac760f67875657deefcc8df20785bd9bc2d`
- 01-07Z final exact feature head/tree `61d47fa1c84d42c7f41da879af52e063505f31f2` / `7f8527128fcd7fabaee6b255bcf6d012ef7a8e0d`
- 01-07Z reviewed merge `d704b87480f0a4252744f4c009cef9a86c08fa05`
- execution-map r2 blob at B_YZ `ff0db79e00795c8f655c92c97c4a7e7de27fb215`
- 01-07Y / 01-07Z Plan blobs `8a2ea72deb4287484839caee211aba79478048e0` / `197ae41fd6c32cd5122f6ff32146a57ff0bfb611`
- Intent / Memory / Thin Slice owner blobs `456be9c7d7884e2a58c4d07b867765ed336aa6f5` / `5c27ba3bd2ed74e5164bdd0812133041ed96f242` / `233a9c06ef6ef9300bef1a0e4f86659b0ec26a13`
- original AA Plan reviewed head/merge/blob `a80b1b1e35509ade685b3bc3e083a51a126c9756` / `3d0d3d557960bbfd3267d321d485ad623f035924` / `a42295cb5402fbd4af6cb17679262e985cf43101`
- original donor RED/GREEN commits `4f6b9befece09ac89947d5c90cb8f3b307f1c3b3` / `c28d3536a5034d5ae0c3030a561952d5d75b06e1`；per-commit stable patch-id `10a3ab02bf8b2dc2a9ad478fefdfa370a7faa907` / `eede66b91e3d0fda9b1b08fdd39a88e4f0b44c0a`；cumulative stable patch-id `fe8112bcddc83c9c45c94f8cc37a2c5598aff611`
- frozen r1 donor branch/head/tree `codex/e2e01-01-ru-v2-atomic-writer-r1` / `5345e70e696942e3b7d4eaed59eaa39b5e258458` / `790564947a929ec7624974f784127b84d435ed68`；RED/GREEN commits `fbc91d1a658ba3506749907502b624e8ed6e30dd` / `5345e70e696942e3b7d4eaed59eaa39b5e258458`；subjects、per-commit与cumulative patch-id精确保持原donor值；不得push、review或merge
- donor final source/test blobs `f3049ea9781270e6ea707f689e4adf341853f86d` / `7fc5beb5fd87dd8075804128738ad7e353449395`
- closure oracle Plan [PR #113](https://github.com/weijie567/mini-agent/pull/113) reviewed merge/tree `02a691f0010765f4a5892d09e0ef5ae8b240ef9e` / `359e3f9faef643196d7f300b863d43a451f0ba6e`
- closure oracle feature [PR #114](https://github.com/weijie567/mini-agent/pull/114) reviewed head/merge/tree `a968330127f47cfc5fa7ba0044af093a20a65b69` / `119a05737a00fde219094c5bb192ceaeae84c0ad` / `31ffed26d8e108bfdbb33053505104b219efad4f`；post-merge Application/Ports `373 passed`、full `1950 passed, 1 deselected`
- codec handoff Plan / scope amendment / feature PR `#116` / `#117` / `#118`；reviewed merge `8cd842cd4cc2605de506011a2f979dedc998a2ed` / `4eaf9a5a791d04494248e650ba24e75437954489` / `9a58aa6dff9895bef3425a075bf3495b4e858b74`；feature merge tree `1f8cc68f043f33e91d3f01a4f4cc9c5a3dd03587`精确等于reviewed overlay tree；post-merge focused `1 passed`、Application/Ports `251 passed`、full `1950 passed, 1 deselected, 12 warnings`
- official 01-07AA r2 acceptance amendment merge SHA/blob由Integrator在本Plan PR reviewed merge后捕获；该planning merge不替换feature exact base `B_AA_CODEC_HANDOFF`

owned_files_at_base:

- `src/mini_agent/infrastructure/persistence/postgres.py` = `f2c79015c19e53b3a2cc75af46413e9b693568f6`
- `tests/integration/test_postgres_v2_request_understanding_writes.py` = `ABSENT`

owned_files:

- `src/mini_agent/infrastructure/persistence/postgres.py`
- `tests/integration/test_postgres_v2_request_understanding_writes.py`

allowlist:

- `src/mini_agent/infrastructure/persistence/postgres.py`
- `tests/integration/test_postgres_v2_request_understanding_writes.py`

forbidden_files: `ALL REPOSITORY FILES OUTSIDE THE TWO-FILE ALLOWLIST`，尤其包括 other `src/mini_agent/infrastructure/**`、all `src/mini_agent/application/**`、`src/mini_agent/core/**`、`src/mini_agent/evaluation/**`、other `tests/**`、`evals/**`、`alembic/**`、`tests/conftest.py`、`pyproject.toml`、`uv.lock`、`compose.yaml`、`docs/**`、`.planning/**`、`AGENTS.md`、`PROJECT_DIRECTION.md`、`README.md`、`graphify-out/**`。

canonical_inputs:

- `docs/architecture/intent-design-reference.md` durable RU-v2 aggregate、accepted child、Task effect、provenance与replay。
- `docs/architecture/memory-design-reference.md` trusted owner、exact-version、atomic graph、physical parity、conditional write与zero-partial-write。
- `docs/implementation/e2e01-thin-slice-implementation-spec.md` scoped RU-v2 mapping、PostgreSQL order、failure matrix与recovery boundary。
- `docs/implementation/e2e01-thin-slice-multi-agent-plan.md` reviewed r2 `B_YZ → 01-07AA → B_J_READY`、two-file ownership与barrier nonclaims；closure与codec remediation只替换acceptance base，不改变该产品依赖。
- `.planning/phases/01-cycle-1-e2e-01/01-07AA-CODEC-HANDOFF-PLAN.md` 与 `01-07AA-CODEC-BOUNDARY-SCOPE-AMENDMENT-PLAN.md`：reviewed dependency guard handoff、bounded static dependency proof与Postgres positive use-site containment。
- 01-07Y reviewed Core reducer、01-07Z reviewed exact-v2 commands/Ports、01-07K reviewed exact-v2 owner-scoped reader、B_YZ现有PostgreSQL adapter，以及reviewed closure oracle fix。

dependencies:

- `01-07Y`: deterministic output→canonical RU-v2 parent/accepted child/Task effect。
- `01-07Z`: two exact command types and `RuntimeRecordPort` method signatures。
- `01-07K`: `load_exact_run_evidence_for_owner` authoritative exact-v2 round-trip reader。
- `01-07Q`: RU-v2 active public codec mapping；AA仍必须显式调用versioned codec，不可依赖active selection。
- `01-07AA closure oracle remediation`: reviewed [PR #114](https://github.com/weijie567/mini-agent/pull/114)让`ExactRunEvidenceClosure`复用Z command的order-id normalizer、精确绑定source tuple并清除target error的raw input；形成replacement acceptance base `119a05737a00fde219094c5bb192ceaeae84c0ad`。
- `01-07AA codec dependency remediation`: reviewed PR #116–#118让dependency guard接纳scoped writer/oracle依赖、明确其非Python sandbox，并正向冻结Postgres exact codec use-site；形成final acceptance base `B_AA_CODEC_HANDOFF = 9a58aa6dff9895bef3425a075bf3495b4e858b74`。
- PostgreSQL migrations/physical v2 pair from01-07P已经存在；AA不得修改migration chain。

required_checks:

- `preflight containment`: actual repository/remote/head branch/base branch/worktree/base SHA/tree逐项等于本Packet；worktree clean；new test path在base为ABSENT；预期`PASS`，任一偏差`BLOCK`。
- `adapter precheck`: collaboration runtime必须真实提供本Packet声明的`infra-engineer`能力，且唯一writer明确为执行本Packet的`/root`；只记录availability，不授权新Agent、第二writer或共享checkout写入；预期`PASS`，role缺失或writer不唯一时`BLOCK`。
- `donor containment`: original donor branch/head `codex/e2e01-01-ru-v2-atomic-writer` / `c28d3536a5034d5ae0c3030a561952d5d75b06e1`与r1 donor branch/head `codex/e2e01-01-ru-v2-atomic-writer-r1` / `5345e70e696942e3b7d4eaed59eaa39b5e258458`只作read-only patch provenance，不得push、review、PR、merge、rebase或amend。r1两个donor commits `fbc91d1…` / `5345e70…`分别只改test/source，subject、patch-id与final blobs等于本Packet冻结值。
- `RED provenance`: r2从exact `B_AA_CODEC_HANDOFF` clean创建，只重放r1 RED `fbc91d1a658ba3506749907502b624e8ed6e30dd`为fresh first commit；commit只增加`tests/integration/test_postgres_v2_request_understanding_writes.py`，patch-id等于`10a3ab02bf8b2dc2a9ad478fefdfa370a7faa907`，test blob等于`7fc5beb5fd87dd8075804128738ad7e353449395`，`postgres.py`仍为base blob `f2c79015c19e53b3a2cc75af46413e9b693568f6`。focused命令预期non-zero且失败只来自两个missing methods或明确列出的static-version/atomic behavior，环境/migration/test-construction失败`BLOCK`。
- `GREEN replay`: r2 second commit只重放r1 GREEN `5345e70e696942e3b7d4eaed59eaa39b5e258458`，patch-id等于`eede66b91e3d0fda9b1b08fdd39a88e4f0b44c0a`，source blob等于`f3049ea9781270e6ea707f689e4adf341853f86d`，累计patch-id等于`fe8112bcddc83c9c45c94f8cc37a2c5598aff611`；fresh SHA允许变化，两个subjects与顺序必须保持。任何差异或冲突先`BLOCK`，不得手工扩大patch。
- `focused GREEN`: `uv run pytest tests/integration/test_postgres_v2_request_understanding_writes.py -q`；预期exit 0、zero failures/skip/xfail。
- `neighbor regression`: `uv run pytest tests/integration/test_postgres_v2_request_understanding_writes.py tests/integration/test_postgres_atomicity.py tests/integration/test_postgres_record_adapters.py -q`；预期exit 0、zero failures/skip/xfail。
- `canonical environment`: `uv sync --all-groups`、`docker compose up --wait -d db`、`docker compose --profile test up --wait -d db-test`与`uv run alembic upgrade head`依次从仓库根执行；预期全部exit 0、dev/test database healthy、migration head，无dependency/lock/migration/source drift。
- `canonical full serial gate`: `uv run pytest`；预期exit 0、zero failures，既有单个credentialed deselection可以保留，warning count须如实报告且不能新增未裁决warning。
- `mechanical source gate`: `git diff --check`、exact public signatures/imports、immutable static version map、v2 call graph forbidden legacy-helper tripwires及v1 protected method diff；预期全部PASS，v2 writer不得调用legacy encode/persist/decode/projection/physical-validation chain；v1 public signature、legacy encode/decode/persist call graph及无collision behavior不得漂移，protected method唯一允许的diff是Run锁后调用shared metadata-only collision fence。
- `allowlist containment`: `git diff --name-only 9a58aa6dff9895bef3425a075bf3495b4e858b74...HEAD`排序后精确等于两个owned files；预期requested=accepted=unique=2，零第三文件、零merge commit、linear replay RED→GREEN→append-only fix history。
- `security/atomicity matrix`: first-write、exact replay、foreign/absent、stale root、v1 collision、second-RU identity、wrong-owner same-Run/target metadata、owner/version/closure/CAS conflict、fault injection与bounded deterministic concurrency；SQL capture必须证明trusted Run通过前不运行collision probe，probe只选择allowlisted metadata columns且从不选择`envelope`，wrong-owner envelope sentinel/secret从未materialize；预期每个APPLIED都是完整closed graph，每个non-APPLIED/exception都是records/references相对baseline零变化，errors raw-free。
- `authoritative round-trip`: 两条writer success/replay后只通过01-07K `load_exact_run_evidence_for_owner`读取；预期no-task closure无Task family，initial closure与command parent/child/Task/RequestUnit/InputBinding/links exact相等且只含RU-v2。
- `cross-file impact scan`: 从active owner出发扫描Application/Core/Runtime/Eval/migration/status消费者；预期AA two-file实现无需owner同步；allowlist外派生状态债只报告、不混写。
- `independent exact-head review`: reviewed local head/tree与PR head精确相等，`CRITICAL/HIGH/MEDIUM/LOW = 0/0/0/0`；任一finding未关闭`BLOCK`。
- `latest-integration overlay`: 在当时latest integration base上重放exact feature patch并记录base SHA/tree、patch-id、synthetic tree、focused/neighbor/Alembic/full；预期全部PASS且第二份independent overlay review为`0/0/0/0`。
- `serial merge/post-merge`: reviewed overlay tree精确等于squash merge tree，integration从previous exact head单步串行前进；post-merge focused/neighbor/Alembic/full与clean status预期PASS，之后才实例化`B_J_READY`。

done_when:

- RED→GREEN与任何append-only remediation均在线性feature history中可复现；
- original donor与r1 donor保持未推送/未送审/未合并，r2前两个fresh commits与冻结r1 donor逐commit及累计patch equivalence成立；
- actual changed-files精确等于two-file allowlist，所有required_checks达到上述预期；
- 两个exact-v2 Port writer通过static-version、owner lock、atomic/replay/conflict、bounded failure与01-07K round-trip gate；
- exact feature head与latest-integration overlay分别取得独立`0/0/0/0` review；
- draft PR head等于reviewed head并由Integrator串行squash merge，merge tree等于reviewed overlay tree；
- exact post-merge integration gate通过并记录`B_J_READY` SHA/tree；01-07J仅从该exact barrier另行签发；
- Runtime active routing、`B_ACTIVE`、Case/E2E lifecycle与readiness仍保持未声明。

handoff_to: `/root Integrator；由Integrator执行exact-head/overlay裁决、GitHub PR串行merge、post-merge gate与B_J_READY命名。`

handoff_format:

- `identity`: repository、remote、r2 feature branch/worktree ID、original barrier、final replacement base SHA/tree、original/r1 donor final head/tree、r2 linear commit SHAs/subjects；
- `scope`: expected/actual changed-files、owned/forbidden containment结果、dirty/untracked/merge-commit检查；
- `verification`: RED失败、focused、neighbor、db health、Alembic、full、mechanical source、atomicity/concurrency/fault/replay、01-07K round-trip逐项命令/exit/count；
- `review`: exact-head reviewer/verdict/finding resolution；latest integration SHA/tree、patch-id、synthetic tree、overlay reviewer/verdict；
- `contract_and_risk`: `contract_changes`、`security_impact`、`eval_impact`、raw/PII检查、cross-file scan、未执行项、known/open risks；
- `integration`: PR URL/number/head、recommended serial order、reviewed merge SHA/tree、post-merge checks、rollback；未merge前不得填写或claim `B_J_READY`。

contract_changes: `NONE to canonical owners and Application/Core contracts. Infrastructure implements two already-reviewed exact-v2 Port methods and adds writer-private static-version mechanics.`
security_impact: `YES — private owner-scoped write path. Trusted owner roots remain server supplied; absence/unauthorized stays indistinguishable; all selected roots and written closure remain same-owner; bounded errors contain no raw content/SQL/secret; every non-APPLIED or exception path proves zero partial writes.`
eval_impact: `YES — adds Integration component evidence for exact-v2 persistence, reader round-trip, replay, collision, atomic failure and concurrency. Does not activate or pass Trajectory/E2E Case lifecycle.`
rollback: `分阶段逆序普通revert，禁止reset、force-push或直接改写integration历史：(1) r2未merge时，关闭/放弃feature PR并删除本地feature Worktree即可，B_J_READY仍未形成；(2) AA已merge但01-07J尚未merge时，普通revert reviewed AA feature merge，撤销B_J_READY claim并阻断01-07J；(3) 01-07J、B_ACTIVE或任一后继已形成时，先阻断新流量/后继签发，按依赖逆序普通revert J及所有后继，再普通revert AA feature merge，最后撤销B_ACTIVE/B_J_READY claims。AA新增test与postgres.py实现是additive，既有v1 writer、migration与Application/Core contracts保留；任何阶段都必须重跑当时适用的post-revert gates。`

handoff:

- report exact original/r1 donor branch/head、r2 branch/head、original B_YZ、final `B_AA_CODEC_HANDOFF` base and linear commit list；
- report r1 donor→r2 per-commit/cumulative patch equivalence与final blob equality；
- report actual changed files and `git diff --name-only B_AA_CODEC_HANDOFF...HEAD` exact equality to two-file allowlist；
- report RED failure reason and GREEN/final command results；
- report static expected-version map and proof that v2 routes do not call legacy persist/decode/physical-validation chain；
- report no-task/initial graph first write, replay, collision, concurrency, fault-injection and01-07K reader round-trip evidence；
- report `contract_changes`、`security_impact`、`eval_impact`、remaining risks and rollback；
- do not claim B_J_READY until exact-head review, latest-integration overlay, serial merge and post-merge gates all pass。
</packet_contract>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: RED replay — freeze two exact-v2 PostgreSQL writer oracles</name>
  <files>tests/integration/test_postgres_v2_request_understanding_writes.py</files>
  <action>从exact `B_AA_CODEC_HANDOFF`，以普通cherry-pick重放r1 donor RED `fbc91d1a658ba3506749907502b624e8ed6e30dd`；不得携带GREEN或手工编辑。验证fresh commit只增加新owned Integration test、subject exact、patch-id与test blob等于冻结值，`postgres.py`仍为base blob。该test复用现有public fixtures/builders而不修改shared bootstrap；构造Z exact commands，覆盖Section 1–6的first-write、01-07K round-trip、exact replay、root/owner/version/closure/CAS conflicts、v1 collision、no-task/initial互斥、fault injection、bounded errors和deterministic concurrency。static source assertions/monkeypatch tripwires证明v2 methods不调用legacy encoder/persist/decode/projection/physical-validation helpers。</action>
  <verify>
    <automated>uv run pytest tests/integration/test_postgres_v2_request_understanding_writes.py -q</automated>
    RED必须非零且只因两个Port methods或writer-private exact-version behavior尚未实现；`postgres.py` blob仍等于replacement base。
  </verify>
  <done>RED精确证明两个missing Infrastructure methods与static-version/atomic/replay obligations，不因环境、migration或test oracle错误失败。</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: GREEN replay — implement static-version no-task and initial-graph transactions</name>
  <files>src/mini_agent/infrastructure/persistence/postgres.py</files>
  <action>在RED已真实复现后，以普通cherry-pick重放r1 donor GREEN `5345e70e696942e3b7d4eaed59eaa39b5e258458`；验证fresh second commit只改`postgres.py`、subject exact、per-commit/cumulative patch-id与source/test final blobs等于冻结值。该patch只在PostgresRecordAdapter及module-private surface增加Z两个Port method imports、immutable writer version map、versioned encode/decode/projection/persist/physical parity/owner closure helpers和两个transactional methods。先稳定锁定trusted roots与same-Run closure，再执行all-new或all-exact-replay判定；按Section 4/5写入完整aggregate、touch recovery anchor并commit前重验。legacy-v1 method只增加Run锁后、target insert前的shared version-neutral metadata-only collision-fence调用，其他legacy代码、signature与codec/persist path不得修改；不得修改migration、Application/Core或其他Adapter。</action>
  <verify>
    <automated>uv run pytest tests/integration/test_postgres_v2_request_understanding_writes.py -q</automated>
    两条route、static-version tripwires、reader round-trip、replay/conflict/fault/concurrency matrix全部通过。
  </verify>
  <done>新v2 writer path完整转绿且两文件以外零改动。</done>
</task>

<task type="auto">
  <name>Task 3: Final containment and repository gates</name>
  <files>src/mini_agent/infrastructure/persistence/postgres.py, tests/integration/test_postgres_v2_request_understanding_writes.py</files>
  <action>只允许append-only remediation commits。验证base/head/range线性、RED先于GREEN、changed-files exact equality、forbidden symbol/path与legacy-v1 regression；运行focused、neighbor、Alembic与canonical full serial gate。执行repo级cross-file impact scan，只报告allowlist阻止同步的派生status债，不修改第三个文件。</action>
  <verify>
    <automated>uv run pytest tests/integration/test_postgres_v2_request_understanding_writes.py tests/integration/test_postgres_atomicity.py tests/integration/test_postgres_record_adapters.py -q</automated>
    <automated>uv run alembic upgrade head</automated>
    <automated>uv run pytest</automated>
    <automated>git diff --check &amp;&amp; test "$(git diff --name-only 9a58aa6dff9895bef3425a075bf3495b4e858b74...HEAD | sort)" = "$(printf '%s\n' src/mini_agent/infrastructure/persistence/postgres.py tests/integration/test_postgres_v2_request_understanding_writes.py | sort)"</automated>
  </verify>
  <done>所有适用门禁通过并准确记录未执行项；feature exact head可以进入独立review。</done>
</task>

</tasks>

<verification>

1. Preflight精确证明r2 feature branch/worktree从`B_AA_CODEC_HANDOFF=9a58aa6...`创建；本Plan amendment PR merge只作为issuance evidence，不替换feature base。
2. 原B_YZ donor与r1 donor保持read-only、不push/review/merge；r2两个fresh commits逐一重放exact r1 RED/GREEN并证明subject、patch-id、blob与顺序等价。RED只改new Integration test且失败只因AA missing writer surface/behavior；GREEN及fix保持two-file allowlist。
3. independent exact-head review检查`CRITICAL/HIGH/MEDIUM/LOW = 0/0/0/0`，所有finding append-only关闭。
4. PR最初为draft，head SHA精确等于reviewed local head；不得direct push integration或main。
5. merge前以latest `integration/e2e01-thin`重放同一feature patch，记录base SHA/tree、patch-id、synthetic tree、focused/neighbor/Alembic/full结果并取得第二份independent overlay PASS。
6. Integrator只在exact-head与latest-overlay都PASS后串行squash merge；merge tree必须等于reviewed overlay tree。
7. post-merge从exact integration merge重新运行适用gates，才命名`B_J_READY`并允许签发01-07J。

</verification>

<success_criteria>

- 两个exact-v2 PostgreSQL Port methods真实存在并通过Integration oracle。
- static expected-version map贯穿encode/decode/projection/persist/physical validation/owner closure；没有payload inference或legacy helper fallback。
- no-task与initial graph均owner-consistent、same-transaction、closed、replay-safe且任何失败零部分写。
- 01-07K从数据库authoritative回读exact RU-v2 closure；v1 writer regression保持。
- exact two-file allowlist、RED→GREEN历史、focused/neighbor/Alembic/full、exact-head和latest-overlay review全部可复现。
- 只在reviewed merge后形成`B_J_READY`；Runtime active routing、B_ACTIVE、Case/E2E与readiness仍明确未声明。

</success_criteria>
