---
phase: 01-cycle-1-e2e-01
plan: 07Z
type: tdd
wave: 25
depends_on:
  - 01-07Q
files_modified:
  - src/mini_agent/application/records.py
  - src/mini_agent/application/ports.py
  - tests/component/application/test_record_contracts.py
  - tests/component/application/test_ports_contract.py
autonomous: true
requirements:
  - E2E01-01
  - E2E01-04
user_setup: []
must_haves:
  truths:
    - "01-07Z 只增加两个互斥、exact-v2 Application conditional write contract：合法zero/all-REJECT no-task closure，以及exact-one emitted/accepted initial Task graph。"
    - "两个command都必须携带可信owner scope、exact Conversation、全部referenced Message projections与active Run roots；Message ID payload不能自证owner，caller不能省略、union、alias或fallback。"
    - "No-task command只能携带RU-v2 parent且没有ACCEPT、accepted child、Task effect或NextMove audit；initial-graph command只接受exact-one emitted/accepted Candidate，并携带一个child及与之bijective的clean initial InputBinding、Task、RequestUnit和links。"
    - "RuntimeRecordPort增加两个显式方法，分别只接受对应exact command并返回ConditionalWriteResult；不得通过optional参数、single union method、latest selector或dynamic capability probing合并。"
    - "既有v1 SaveRequestUnderstandingCommand、CreateInitialTaskGraphCommand和create_initial_task_graph_if_current保持原名称、字段、signature与行为，直到01-07W；Z本身不切换Runtime或实现PostgreSQL。"
    - "01-07Z 不决定zero/all-REJECT的Runtime用户结果，不声明B_YZ/B_J_READY/B_ACTIVE或完整切片。"
  artifacts:
    - "src/mini_agent/application/records.py 中 SaveRequestUnderstandingV2AcceptedCommand、SaveRequestUnderstandingV2NoTaskCommand 与 CreateInitialTaskGraphV2Command。"
    - "src/mini_agent/application/ports.py 中 save_request_understanding_v2_no_task_if_current 与 create_initial_task_graph_v2_if_current exact Port methods。"
    - "两个owned Component test中的exact field/signature、owner/closure/tamper、v1 compatibility与non-routing matrix。"
  key_links:
    - "Intent owner durable exact-set与Task effect → 两条互斥Application command shape。"
    - "Memory owner trusted owner root与atomic conditional write → command preconditions及ConditionalWriteResult。"
    - "Execution map r2 → exact B_Q → 01-07Y + 01-07Z → B_YZ；Z与Y无文件或new-symbol依赖。"
    - "01-07Z Port → 后续01-07AA PostgreSQL writer实现；01-07J只能从B_J_READY显式调用。"
---

# Phase 1 Plan 01-07Z｜Request Understanding v2 write contracts

> **ISSUED ACTIVE_SWITCH PREREQUISITE TASK PACKET / IMPLEMENTATION NOT STARTED**
> 本 Packet 只冻结Application command / Port合同。Plan、Component test或Z feature完成都不表示PostgreSQL已经实现这些方法、Runtime已经调用、任何RU-v2 row已写入、`B_YZ` / `B_J_READY` / `B_ACTIVE`已形成，或Case/E2E已经通过。

> **DERIVED / NON_NORMATIVE**
> Request Understanding aggregate、owner graph、版本与atomic write义务仍由Intent / Memory / Thin Slice canonical owner拥有。本Plan只消费execution map r2的Application ownership，不创建第二套语义。

<objective>
以TDD RED→GREEN增加两个显式、互斥的RU-v2 conditional write contract：一个只保存合法no-task Request Understanding closure；一个保存exact-one emitted/accepted Request Understanding child及完整initial Task graph。两者都在Application边界锁定trusted owner roots、referenced Message exact set、closed graph与zero-partial-write返回语义。

Purpose: 关闭exact B_Q中“Application只有v1 initial graph command/Port”的真实阻断，让后续01-07AA可以实现静态exact-version PostgreSQL writer，让01-07J可以显式选择v2 route，而不使用v1/v2 union、alias、fallback或Runtime `hasattr` probing。

Output: 一个只改两个owned Component tests的RED commit，以及一个只改`records.py` / `ports.py`的GREEN commit；review finding只用append-only fix。Z不创建Summary、不修改shared State、canonical docs、Core、Infrastructure、Eval或Runtime。
</objective>

<execution_context>
@AGENTS.md
@.planning/GOVERNANCE.md
@.planning/phases/01-cycle-1-e2e-01/01-07I-PLAN.md
@.planning/phases/01-cycle-1-e2e-01/01-07Q-PLAN.md
@docs/architecture/intent-design-reference.md
@docs/architecture/memory-design-reference.md
@docs/implementation/e2e01-thin-slice-implementation-spec.md
@docs/implementation/e2e01-thin-slice-multi-agent-plan.md
@src/mini_agent/application/records.py
@src/mini_agent/application/ports.py
@src/mini_agent/core/task_state.py
@tests/component/application/test_record_contracts.py
@tests/component/application/test_ports_contract.py

只使用项目受控execution adapter；不得调用stock `gsd-plan-phase`、`gsd-execute-phase`、`gsd-verify-work`、lifecycle mutation或`gsd-ship`。Graphify按用户指令保持闲置：不读取、不运行、不更新，也不作为gate。
</execution_context>

<interfaces>

## 1. Exact accepted-child command

Z在`records.py` additive增加：

```python
class SaveRequestUnderstandingV2AcceptedCommand(_StrictRuntimePrivateRecord):
    record: RequestUnderstandingRecordV2
    accepted_delta: AcceptedTaskDeltaV2
```

它只表示initial-graph route内部的一个完整parent/child aggregate，不是独立Port：

- `record.schema_version == request_understanding_record.p0.v2`由exact DTO固定；
- record必须恰有一个actual Candidate、一个validation且为`ACCEPT`；partial与multi closure不能构造该wrapper；
- `accepted_delta_refs == (accepted_delta.accepted_delta_id,)`，child `candidate_ref`精确绑定唯一ACCEPT；
- child message与parent message相同，`base_task_state_version is None`、`result_task_state_version == 1`；
- child input binding refs恰有一个且unique；
- parent `proposed_base_task_state_version is None`、`validated_task_state_version == 1`、`next_move_candidate_ref`非空；
- parent `created_at == child.accepted_at`。
- parent与child必须是exact Core types并通过recursive canonical rebuild；subclass、`model_construct` undeclared state或noncanonical nested value一律fail closed。

任何missing/extra/duplicate/wrong candidate/Task version/Message/time relation都在command construction fail closed；不得保留partial child、caller error text或v1 projection。

## 2. No-task exact conditional command

```python
class SaveRequestUnderstandingV2NoTaskCommand(_StrictRuntimePrivateRecord):
    owner_scope: TrustedOwnerScope
    expected_conversation_record: ConversationRecord
    expected_message_records: Annotated[
        tuple[MessageRecord, ...],
        Field(min_length=1, max_length=8),
    ]
    expected_active_run_record: AgentRunRecord
    request_understanding_record: RequestUnderstandingRecordV2
```

Root与closure规则：

- Conversation owner必须等于`owner_scope.customer_id`；
- `expected_message_records`的Message ID必须unique，全部属于该Conversation；RU `message_ref`对应的current Message必须exactly one且为`USER`，其余referenced Message保留各自真实direction；
- expected Message ID集合必须与RU parent的全部top-level Message references精确相等：parent `message_ref`、contextualization `source_message_refs`、resolved/uncertainty source refs与全部TaskDelta input source refs的union；不得缺失、额外、重复或只信任payload ID；
- Run必须是该Conversation中的clean `RUNNING` Run；
- RU parent必须绑定exact Run / Message；
- parent可有zero或多个actual Candidate，但所有decision必须是REJECT，`accepted_delta_refs=()`；
- `proposed_base_task_state_version`、`validated_task_state_version`、`next_move_candidate_ref`全部为`None`；
- parent `created_at`不得早于current Message `received_at`或Run `started_at`；
- command field surface没有Task、RequestUnit、InputBinding、link、accepted child、用户结果或diagnostic。
- `TrustedOwnerScope`必须是既有trusted exact instance并通过exact field/private-state projection guard，不得从其`customer_id`反造`CustomerContext`来自证可信；其余roots与parent必须是exact types并通过recursive canonical rebuild。subclass、`model_construct` undeclared state或noncanonical nested value一律fail closed。

合法zero/all-REJECT aggregate与aggregate-invalid不同：只有前者可以构造此command。此command不决定Runtime对用户返回什么。

## 3. Exact-one initial graph command

```python
class CreateInitialTaskGraphV2Command(_StrictRuntimePrivateRecord):
    owner_scope: TrustedOwnerScope
    expected_conversation_record: ConversationRecord
    expected_message_records: Annotated[
        tuple[MessageRecord, ...],
        Field(min_length=1, max_length=8),
    ]
    expected_active_run_record: AgentRunRecord
    request_understanding: SaveRequestUnderstandingV2AcceptedCommand
    initial_task: CreateTaskCommand
    initial_request_unit: CreateRequestUnitCommand
    input_binding: SaveInputBindingCommand
    conversation_task_link: ConversationTaskLinkRecord
    run_task_link: CreateRunTaskLinkCommand
```

Z有意使用单个`input_binding`而不是tuple：当前RU-v2 direct-binding DTO与E2E01 exact mapping只允许一个accepted `ADD_GOAL`和一个`order_id` binding；未来扩容必须新contract，不能让现有command接受optional/multi shape。

除复用v1 command已有owner/root/link检查外，v2 graph额外强制：

- referenced Message projections使用与no-task command相同的exact-set算法；全部Message属于trusted Conversation，current `record.message_ref`对应exact USER Message，Run属于同一Conversation且为clean `RUNNING`；
- parent必须恰有一个actual Candidate、一个validation且为`ACCEPT`、一个accepted child；一个ACCEPT加其他REJECT的partial closure与multi-ACCEPT都不能进入此active exact-one command；
- Task owner与trusted scope相同，Task / RequestUnit都是`ACTIVE/v1`且identity/status/version一致；
- AcceptedTaskDeltaV2 `task_id`等于initial Task，result version等于Task/RequestUnit version `1`；
- RequestUnit goal/message/binding与accepted child exact；
- InputBinding只引用exact USER Message，且`request_unit_id`精确；
- ConversationTaskLink是active exact Task link；RunTaskLink绑定exact Run/new Task，base与result都按现有initial active-link contract保持`None`；
- initial Task固定`last_outcome_ref=None`；initial RequestUnit固定`contextualization_ref=None`、`constraint_refs=()`、`dependency_refs=()`、`open_questions=()`、`observation_refs=()`、`evidence_binding_refs=()`、`pending_action_ref=None`、`result_refs=()`；initial InputBinding固定`supersedes=None`；
- parent / child / Task / RequestUnit / InputBinding使用Y的同一次trusted timestamp：parent `created_at == child.accepted_at == Task.created_at == Task.updated_at == RequestUnit.created_at == RequestUnit.updated_at == InputBinding.created_at == InputBinding.updated_at`；ConversationTaskLink `linked_at`使用同一initial timestamp且`ended_at=None`；
- command construction对`TrustedOwnerScope`执行exact instance/projection guard，对其他nested model执行exact-type、recursive canonical rebuild，拒绝subclass、`model_construct` undeclared state与noncanonical nested value；不得从一个对象重建另一个，也不得接受v1 record/child。

## 4. Two explicit RuntimeRecordPort methods

`ports.py`显式import三个new command types，并在`RuntimeRecordPort`中additive增加：

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

两者doc必须明确：

- `APPLIED`只在trusted roots仍exact current且完整command在一个事务提交时返回；
- `PROJECTION_CONFLICT` / `NOT_APPLICABLE`保证所有RU/child/Task/InputBinding/link均zero writes；
- no-task route绝不创建Task families；initial graph route绝不降级为no-task；
- owner不存在与无权访问不可区分，具体数据库判定归01-07AA；
- exact replay/conflict的物理实现、version dispatch、lock与closed-set验证归01-07AA，本Packet只冻结Application contract。

禁止增加：

- `save_request_understanding_v2(command: A | B)`之类union Port；
- optional child/Task fields、version enum/default/latest、record type dispatch、alias或overload；
- `hasattr`/`getattr` capability probing、try-v2-then-v1、dynamic import或fallback；
- 独立的unconditional RU/child/Task insert bypass。

## 5. Staged v1 compatibility

以下existing symbols的field set、signature、type hints与behavior必须保持：

- `SaveRequestUnderstandingCommand`
- `CreateInitialTaskGraphCommand`
- `RuntimeRecordPort.create_initial_task_graph_if_current`
- existing owner-scoped v1 read methods

Z不修改existing Runtime caller或PostgreSQL adapter，因此B_YZ前后v1 path仍可回归，但它是等待后续J/W关闭的compatibility surface，不是新v2 route的fallback。01-07W独占Application v1 contract removal。

</interfaces>

<packet_contract>
repository: `https://github.com/weijie567/mini-agent`
remote: `origin`
head_branch: `codex/e2e01-01-ru-v2-write-contract`
base_branch: `integration/e2e01-thin`
base_sha: `2b9fde6f0e09308a53b86a4929ea3b639660f82e`
base_tree: `a68738b62695593a114c816cab2264b670494537`
input_barrier: `B_Q`
output_barrier: `B_YZ / ONLY AFTER 01-07Y AND 01-07Z BOTH FEATURE EXACT-HEAD AND LATEST-INTEGRATION OVERLAY REVIEWED-SERIAL-MERGED`
worktree_id: `e2e01-01-ru-v2-write-contract`
writer: `Application v2 Request Understanding write-contract sole writer, supervised by /root Integrator`
agent_role: `runtime-engineer / Application-contract-only`
active_routing: `false`

planning_and_owner_provenance:

- exact feature base/tree `B_Q = 2b9fde6f0e09308a53b86a4929ea3b639660f82e` / `a68738b62695593a114c816cab2264b670494537`
- Q Plan / category amendment / feature PR #104/#105/#106 formed exact B_Q
- execution-owner r2 remediation PR #107 reviewed merge `e602bc282c2929cc69a297d991093b236ebad156` / tree `7d5521cf06f0416c4b7cac07fe365cfdf0ae4417`; it authorizes Z but does not replace feature base B_Q
- Intent / Memory / Thin Slice owner blobs `456be9c7d7884e2a58c4d07b867765ed336aa6f5` / `5c27ba3bd2ed74e5164bdd0812133041ed96f242` / `233a9c06ef6ef9300bef1a0e4f86659b0ec26a13`
- execution-map blob at feature base / reviewed r2 planning context `c8970d6195a61064fdf3b4186d338fd8cfe8eee8` / `ff0db79e00795c8f655c92c97c4a7e7de27fb215`
- official 01-07Z Plan merge SHA/blob由Integrator在Plan PR reviewed merge后捕获；Plan或owner merge不替换feature exact base B_Q

owned_files_at_base:

- `src/mini_agent/application/records.py` = `53372a47d1aded5f02afa958f7dcec96fccf1688`
- `src/mini_agent/application/ports.py` = `4b4d5c7556f13a072a8fb83cfcf539441f76eaa1`
- `tests/component/application/test_record_contracts.py` = `4ad7cec6e5dcc230c4007ecca08eabbc41a05acc`
- `tests/component/application/test_ports_contract.py` = `3e0143a67b7ff1bdd229938d9264c6414f40e911`

owned_files:

- `src/mini_agent/application/records.py`
- `src/mini_agent/application/ports.py`
- `tests/component/application/test_record_contracts.py`
- `tests/component/application/test_ports_contract.py`

allowlist:

- `src/mini_agent/application/records.py`
- `src/mini_agent/application/ports.py`
- `tests/component/application/test_record_contracts.py`
- `tests/component/application/test_ports_contract.py`

forbidden_files: `ALL REPOSITORY FILES OUTSIDE THE FOUR-FILE ALLOWLIST`，尤其包括 other `src/mini_agent/application/**`、all `src/mini_agent/core/**`、`src/mini_agent/infrastructure/**`、`src/mini_agent/evaluation/**`、other `tests/**`、`evals/**`、`alembic/**`、`tests/conftest.py`、`pyproject.toml`、`uv.lock`、`compose.yaml`、`docs/**`、`.planning/**`、`AGENTS.md`、`PROJECT_DIRECTION.md`、`README.md`、`graphify-out/**`。

canonical_inputs:

- `docs/architecture/intent-design-reference.md` §13.1–13.8 durable aggregate/identity/exact-set/Task effect/replay。
- `docs/architecture/memory-design-reference.md` trusted owner、Port ownership、atomic graph、exact-version与fail-closed read/write边界。
- `docs/implementation/e2e01-thin-slice-implementation-spec.md` RU-v2 DTO mapping、local closure、conditional write顺序与failure matrix。
- `docs/implementation/e2e01-thin-slice-multi-agent-plan.md` reviewed r2 `B_Q → {01-07Y,01-07Z} → B_YZ`、Z four-file ownership与barrier nonclaims。
- exact B_Q中的Application strict records/Ports、v2 Core record types、v1 initial graph regression与owned source/test blobs。

dependencies:

- `01-07I = REVIEWED_MERGED`：Application exact-Run/v2 record imports与trusted Port patterns存在。
- `01-07Q = REVIEWED_MERGED`：形成exact B_Q。
- `01-07Z EXECUTION OWNER = REVIEWED_ALIGNED`：PR #107把缺失Application command/Port映射为本Packet，target denominator为42。
- `01-07Y`与Z同wave但文件无交集；Z只能依赖B_Q已有Core DTO，不得import Y new result type或复制Y reducer。
- `01-07AA`必须等待Y/Z reviewed serial merge形成B_YZ后才实现这两个Port。
- new external/package/schema/migration dependency: `NONE`。

required_checks:

- Gate A exact branch/worktree/base/tree/four blobs/clean state；feature必须直接从B_Q创建。
- focused baseline `uv run pytest tests/component/application/test_record_contracts.py tests/component/application/test_ports_contract.py -q`；B_Q参考为`357 passed`。
- RED只改两个owned tests且只因new exact commands/Port methods缺失而失败；现有v1 contract tests保持绿色。
- GREEN后focused全绿，并运行`uv run pytest tests/component/application/test_persistence_contract.py -q`与Runtime Component regression。
- canonical environment可用；`uv run alembic upgrade head`与`uv run pytest` full gate通过。B_Q参考为`1901 passed, 1 deselected, 12 warnings`，新增Z tests允许总数只按实际新增增长。
- exact field/type/signature、trusted-scope exact projection guard、其他nested recursive canonical rebuild、strict/frozen/extra-forbid、referenced Message exact-set owner roots、no-task/exact-one closure、clean-initial Task/InputBinding/link bijection、tamper、no-union/no-bypass与v1 compatibility matrix。
- four-file changed-files、逐commit RED→GREEN/fix subject与scope、no-merge、no-Core/Infra/Runtime change、exact branch/worktree及clean Worktree。
- repository-level cross-file impact scan（显式排除`graphify-out/**`）。
- feature exact-head及latest-integration overlay独立review，unresolved `CRITICAL/HIGH/MEDIUM/LOW = 0/0/0/0`。

commit_protocol:

1. RED `test(01-07Z): require ru v2 write contracts`只改两个owned Component tests。冻结三个command exact fields/cardinality/model config与两个Port exact signatures/docs；覆盖zero/all-reject、exact-one emitted/accepted、current+recent referenced Message exact set、wrong owner/root/message/run、missing/extra child、全部initial-empty refs、Task/binding/link/version/time、subclass/undeclared-state/noncanonical nested tamper、v1 type rejection、no-union/no-bypass与existing v1 protection。Source blobs必须仍为base值。
2. GREEN `feat(01-07Z): add ru v2 write contracts`只改`records.py`和`ports.py`。增加三个exact command、trusted-scope projection guard、其他nested recursive closed validators、two explicit Protocol methods与bounded docs；不改existing v1 definitions/signatures，不实现Adapter，不import Y result，不增加external dependency。
3. Review finding只用append-only `fix(01-07Z): ...`，始终限四文件；不得amend、rebase或force-push已审历史。每个新head重跑focused/full/containment并重新review。

done_when:

- RED/GREEN/fix的SHA、tree、scope、失败/通过原因可复现。
- no-task command只能表达zero/all-REJECT exact parent且没有任何Task/child/next-move effect。
- initial-graph command只能表达exact-one emitted/accepted、一个child、一个binding、一个clean initial Task/RequestUnit和exact links；全部referenced Message owner root、version/time与empty-state闭合。
- RuntimeRecordPort只有两个显式v2 conditional methods，无union/optional/alias/fallback/bypass；AA可以静态实现。
- existing v1 command/Port exact protected surface和Runtime regression保持。
- canonical environment、focused/persistence/Runtime/Alembic/full、逐commit four-file containment、feature/latest-overlay patch-identity与独立review全部通过。
- Y与Z reviewed serial merge后才形成B_YZ；Z单独merge不解锁AA/J。

contract_changes: `YES / ADDITIVE APPLICATION V2 WRITE CONTRACTS` — 增加三个exact command和两个RuntimeRecordPort方法；不修改canonical owner、v1 surface、physical schema、PostgreSQL实现、Runtime/HTTP。
security_impact: `YES / TRUSTED OWNER AND ATOMIC GRAPH PRECONDITIONS` — 两条route都绑定trusted owner、exact Conversation、referenced Message exact set与Run；accepted route关闭clean initial Task/InputBinding/link图；no-task route不能偷偷写Task；non-APPLIED必须由AA实现zero writes。
eval_impact: `YES / COMPONENT AND INFRA PREREQUISITE` — 增加Application Component contract/tamper matrix，为AA/J integration oracle提供typed boundary；不改EvalCase、Dataset、Grader、Result、threshold、Baseline或lifecycle。
rollback: 合并前关闭PR；合并后用普通revert PR撤销01-07Z feature commits，并阻塞B_YZ、AA、J及全部下游。不得reset/force-push、修改B_Q、删除v1 contract或让AA/J保留对已撤销v2 methods的调用。

handoff_to: `/root Integrator`
handoff_format: repository/remote/branch/worktree、exact B_Q base/tree、Plan merge/blob、four base/head blobs、RED/GREEN/fix SHAs与输出、canonical environment/focused/persistence/Runtime/Alembic/full结果、referenced Message exact-set/command field/cardinality/clean-initial/tamper/Port signature/v1 protection矩阵、逐commit changed-files containment、cross-file scan、contract/security/Eval nonclaims、feature/overlay patch identity/review、PR/merge SHA、与Y串行merge后B_YZ tree、风险与rollback。
</packet_contract>

<cross_file_impact>

- `CONFIRMED`：Intent / Memory / Thin Slice owner已批准zero/all-reject durable closure、scoped exact-one accepted Task effect、referenced Message owner root与atomic conditional write；Z只冻结Application boundary，无需修改canonical docs。
- `CONFIRMED`：Y纯Core result不属于Application contract；Z只引用B_Q已有`RequestUnderstandingRecordV2` / `AcceptedTaskDeltaV2` / Task records，保持同wave独立。
- `CONFIRMED`：PostgreSQL尚无这两个methods；01-07AA从B_YZ实现。Z feature/Protocol declaration不能被描述为Adapter可运行。
- `CONFIRMED`：Runtime仍调用v1 command/Port；01-07J从B_J_READY显式切换。Z不得修改AgentRunService或使用capability probing。
- `OPEN / NONCLAIM`：zero/all-REJECT、multi-ACCEPT与atomic failure后的Runtime结果未冻结；Application command只表达持久化shape。
- `CONFIRMED / DERIVED STATUS DRIFT`：`.planning/PROJECT.md`、Requirements/Roadmap/State/Validation、`PROJECT_DIRECTION.md`与`README.md`仍显示旧B_IP/39快照；不在Z allowlist，由dedicated single writer后续对齐。
- `NOT_FOUND`：没有owner要求Z修改codec、migration、Provider/Eval、Tool/Action或HTTP contract。
</cross_file_impact>

<threat_model>

| threat_id | category | boundary | disposition | mitigation |
|---|---|---|---|---|
| `Z-S01` | Spoofing | record payload → owner/root authority | `MITIGATE / BLOCK` | TrustedOwnerScope + exact Conversation/referenced Message set/RUNNING Run；payload ID不能自证owner |
| `Z-T01` | Tampering | no-task command → hidden ACCEPT/Task effect | `MITIGATE / BLOCK` | exact fields；all decisions REJECT；accepted/version/next refs empty |
| `Z-T02` | Tampering | accepted parent/child → missing/extra/wrong Task effect | `MITIGATE / BLOCK` | exact-one emitted/accepted + child/binding/clean Task/Unit bijection、base-null/result-1与全部initial refs empty |
| `Z-T03` | Tampering | v1/v2 union/default → wrong writer route | `MITIGATE / BLOCK` | two exact command/method pairs；no union/alias/latest/fallback |
| `Z-R01` | Repudiation | conditional write → partial/unknown route | `MITIGATE / BLOCK` | explicit APPLIED/conflict/not-applicable docs；AA必须提供transaction/replay evidence |
| `Z-I01` | Information Disclosure | owner mismatch/raw record → differentiated result | `MITIGATE / BLOCK` | Port docs要求absent/unauthorized indistinguishable；bounded result；无raw diagnostic fields |
| `Z-D01` | Denial of Service | graph cardinality expansion → unbounded write | `MITIGATE / BLOCK` | referenced Messages限定1..8 exact set；exact-one emitted/accepted/binding/Task graph；no-task exact zero family |
| `Z-E01` | Elevation of Privilege | Application contract → DB/Runtime readiness | `MITIGATE / BLOCK` | Z不实现Adapter、不route Runtime；B_YZ仍non-routable |

</threat_model>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: RED — freeze two exact v2 conditional write contracts</name>
  <files>tests/component/application/test_record_contracts.py, tests/component/application/test_ports_contract.py</files>
  <read_first>Intent §13、Memory Port/owner/atomic rules、Thin Slice v2 local closure、execution map Z acceptance、existing v1 initial graph command/Port tests</read_first>
  <action>只改两个owned tests。增加三个command import/field/config/cardinality与two Protocol method exact signature/doc tests；构造canonical no-task、all-reject、exact-one emitted/accepted及current+recent contextualization fixtures，逐项tamper owner/root/referenced Message exact set/run/decision/child/task/binding/link/version/time、全部initial-empty refs、subclass/undeclared state/noncanonical nested value；证明partial/multi不能进入accepted command、v1 model不能进入v2 command、v2 model不能进入v1 command，且没有union/optional/alias/bypass method。保持existing v1 tests与test fixture边界，不用DB/network/skip/xfail。</action>
  <verify>
    <automated>uv run pytest tests/component/application/test_record_contracts.py tests/component/application/test_ports_contract.py -q</automated>
    RED必须非零且只因additive Z symbols/behavior缺失；四个source blobs保持B_Q值。
  </verify>
  <done>测试精确冻结no-task与exact-one accepted graph两条互斥shape、referenced Message owner closure、clean initial state和Port signatures。</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: GREEN — add Application v2 commands and Ports</name>
  <files>src/mini_agent/application/records.py, src/mini_agent/application/ports.py</files>
  <read_first>Task 1 RED、existing strict record helpers、v1 initial graph validators、ConditionalWriteResult与RuntimeRecordPort</read_first>
  <action>只改两个owned Application source。增加三个strict/frozen command、TrustedOwnerScope exact projection guard及其他nested recursive exact closed validators；ports显式import并声明两个exact async methods。复用现有canonical projection/rebuild helpers、TrustedOwnerScope、Conversation/Message/Run、CreateTask/RequestUnit/InputBinding/link commands与ConditionalWriteResult。不得从scope payload反造trusted context，不得实现I/O、修改v1 symbols、增加union/default/fallback/hasattr probing或导入Y result。</action>
  <verify>
    <automated>uv run pytest tests/component/application/test_record_contracts.py tests/component/application/test_ports_contract.py -q
uv run pytest tests/component/application/test_persistence_contract.py tests/component/application/test_agent_run_service.py -q</automated>
    Z focused及邻接codec/Runtime Component回归全部通过。
  </verify>
  <done>Application公开两个带referenced Message exact-set与clean initial closure、可由AA静态实现并由J显式调用的v2 conditional write contract；v1 surface保持。</done>
</task>

</tasks>

<verification>

Feature Gate A必须在任何RED编辑前从feature Worktree根执行并记录：

```bash
set -euo pipefail

base_sha=2b9fde6f0e09308a53b86a4929ea3b639660f82e
base_tree=a68738b62695593a114c816cab2264b670494537
expected_branch=codex/e2e01-01-ru-v2-write-contract
expected_worktree_id=e2e01-01-ru-v2-write-contract
expected_remote=https://github.com/weijie567/mini-agent.git
current_root="$(git rev-parse --show-toplevel)"

test "$(git remote get-url origin)" = "$expected_remote"
test "$(git branch --show-current)" = "$expected_branch"
test "$(basename "$current_root")" = "$expected_worktree_id"
test "$(git rev-parse HEAD)" = "$base_sha"
test "$(git rev-parse HEAD^{tree})" = "$base_tree"
test "$(git rev-parse "${base_sha}:src/mini_agent/application/records.py")" = \
  53372a47d1aded5f02afa958f7dcec96fccf1688
test "$(git rev-parse "${base_sha}:src/mini_agent/application/ports.py")" = \
  4b4d5c7556f13a072a8fb83cfcf539441f76eaa1
test "$(git rev-parse "${base_sha}:tests/component/application/test_record_contracts.py")" = \
  4ad7cec6e5dcc230c4007ecca08eabbc41a05acc
test "$(git rev-parse "${base_sha}:tests/component/application/test_ports_contract.py")" = \
  3e0143a67b7ff1bdd229938d9264c6414f40e911
test -z "$(git status --short --untracked-files=all)"
uv run pytest \
  tests/component/application/test_record_contracts.py \
  tests/component/application/test_ports_contract.py -q
```

Gate B / final：

```bash
set -euo pipefail

base_sha=2b9fde6f0e09308a53b86a4929ea3b639660f82e
expected_branch=codex/e2e01-01-ru-v2-write-contract
expected_worktree_id=e2e01-01-ru-v2-write-contract
expected_changed="$(printf '%s\n' \
  src/mini_agent/application/records.py \
  src/mini_agent/application/ports.py \
  tests/component/application/test_record_contracts.py \
  tests/component/application/test_ports_contract.py | LC_ALL=C sort)"
expected_red_changed="$(printf '%s\n' \
  tests/component/application/test_record_contracts.py \
  tests/component/application/test_ports_contract.py | LC_ALL=C sort)"
expected_green_changed="$(printf '%s\n' \
  src/mini_agent/application/records.py \
  src/mini_agent/application/ports.py | LC_ALL=C sort)"
current_root="$(git rev-parse --show-toplevel)"

test "$(git branch --show-current)" = "$expected_branch"
test "$(basename "$current_root")" = "$expected_worktree_id"
test -z "$(git status --short --untracked-files=all)"
git diff --check "$base_sha"...HEAD
actual_changed="$(git diff --name-only "$base_sha"...HEAD | LC_ALL=C sort)"
test "$(printf '%s\n' "$actual_changed" | sed '/^$/d' | wc -l | tr -d ' ')" = 4
test "$actual_changed" = "$expected_changed"
test -z "$(git log --merges --format=%H "$base_sha"..HEAD)"

commit_count="$(git rev-list --count "$base_sha"..HEAD)"
test "$commit_count" -ge 2
commits="$(git rev-list --reverse "$base_sha"..HEAD)"
red_sha="$(printf '%s\n' "$commits" | sed -n '1p')"
green_sha="$(printf '%s\n' "$commits" | sed -n '2p')"
test "$(git show -s --format=%s "$red_sha")" = \
  "test(01-07Z): require ru v2 write contracts"
test "$(git show -s --format=%s "$green_sha")" = \
  "feat(01-07Z): add ru v2 write contracts"
test "$(git diff-tree --no-commit-id --name-only -r "$red_sha" | LC_ALL=C sort)" = \
  "$expected_red_changed"
test "$(git diff-tree --no-commit-id --name-only -r "$green_sha" | LC_ALL=C sort)" = \
  "$expected_green_changed"
test "$(git rev-parse "${red_sha}:src/mini_agent/application/records.py")" = \
  53372a47d1aded5f02afa958f7dcec96fccf1688
test "$(git rev-parse "${red_sha}:src/mini_agent/application/ports.py")" = \
  4b4d5c7556f13a072a8fb83cfcf539441f76eaa1
if test "$commit_count" -gt 2; then
  test -z "$(git log --reverse --format=%s "${green_sha}..HEAD" |
    rg -v '^fix\\(01-07Z\\): ' || true)"
fi
for commit in $commits; do
  test -z "$(git diff-tree --no-commit-id --name-only -r "$commit" |
    rg -v '^(src/mini_agent/application/(records|ports)\\.py|tests/component/application/test_(record_contracts|ports_contract)\\.py)$' ||
    true)"
done

uv sync --all-groups
docker compose up --wait -d db
docker compose --profile test up --wait -d db-test
uv run pytest \
  tests/component/application/test_record_contracts.py \
  tests/component/application/test_ports_contract.py -q
uv run pytest \
  tests/component/application/test_persistence_contract.py \
  tests/component/application/test_agent_run_service.py -q
uv run alembic upgrade head
uv run pytest
```

Latest-integration overlay必须在Integrator预建的detached read-only review Worktree中把同一Z patch重放到当时的exact integration head；不得再用`B_Q...overlay_head`计算全仓containment：

```bash
set -euo pipefail

feature_base_sha=2b9fde6f0e09308a53b86a4929ea3b639660f82e
feature_head_sha=__CAPTURE_REVIEWED_01_07Z_FEATURE_HEAD__
overlay_base_sha=__CAPTURE_LATEST_INTEGRATION_BEFORE_REPLAY__
overlay_head_sha="$(git rev-parse HEAD)"
expected_overlay_worktree_id=e2e01-01-ru-v2-write-contract-overlay-review
expected_changed="$(printf '%s\n' \
  src/mini_agent/application/records.py \
  src/mini_agent/application/ports.py \
  tests/component/application/test_record_contracts.py \
  tests/component/application/test_ports_contract.py | LC_ALL=C sort)"
current_root="$(git rev-parse --show-toplevel)"

test -z "$(git branch --show-current)"
test "$(basename "$current_root")" = "$expected_overlay_worktree_id"
test "$overlay_base_sha" != "$feature_base_sha"
test "$(git merge-base "$overlay_base_sha" "$overlay_head_sha")" = \
  "$overlay_base_sha"
test -z "$(git status --short --untracked-files=all)"
test -z "$(git log --merges --format=%H "${overlay_base_sha}..${overlay_head_sha}")"
git diff --check "$overlay_base_sha"...HEAD
test "$(git diff --name-only "$feature_base_sha" "$feature_head_sha" |
  LC_ALL=C sort)" = "$expected_changed"
test "$(git diff --name-only "$overlay_base_sha" "$overlay_head_sha" |
  LC_ALL=C sort)" = "$expected_changed"

feature_patch_id="$(
  git diff --full-index --binary \
    "$feature_base_sha" "$feature_head_sha" -- $expected_changed |
    git patch-id --stable | awk '{print $1}'
)"
overlay_patch_id="$(
  git diff --full-index --binary \
    "$overlay_base_sha" "$overlay_head_sha" -- $expected_changed |
    git patch-id --stable | awk '{print $1}'
)"
test -n "$feature_patch_id"
test "$overlay_patch_id" = "$feature_patch_id"

uv run pytest \
  tests/component/application/test_record_contracts.py \
  tests/component/application/test_ports_contract.py -q
uv run pytest \
  tests/component/application/test_persistence_contract.py \
  tests/component/application/test_agent_run_service.py -q
uv run alembic upgrade head
uv run pytest
```

Repository-level impact scan：

```bash
rg -n \
  'SaveRequestUnderstanding(V2)?|CreateInitialTaskGraph(V2)?|save_request_understanding_v2_no_task_if_current|create_initial_task_graph(_v2)?_if_current|RuntimeRecordPort|B_Q|B_YZ|01-07[ZYAJW]' \
  AGENTS.md README.md PROJECT_DIRECTION.md docs .planning src tests evals \
  --glob '!graphify-out/**'
```

scan只报告canonical owner、existing v1 caller/adapter、后续AA/J/W consumer与已知derived status drift；Z writer不得越allowlist修正。Feature exact head必须对四项changed files取得独立`PASS / 0/0/0/0` review。Integrator串行merge时若Z是Y之后合入者，必须在上述detached latest-integration overlay中证明Z aggregate patch identity、四文件overlay-relative containment、focused/full gate与独立exact-head review；只有Y/Z都reviewed merged后才命名B_YZ。

</verification>

<success_criteria>

1. RED/GREEN提交、失败/通过原因、four-file scope、SHA/tree与测试输出可复现。
2. no-task route只有owner-bound RU-v2 parent、全部referenced Message exact projections和zero/all-REJECT closure；无Task family或NextMove audit。
3. accepted route恰好一个emitted/accepted parent/child/binding/clean initial Task/Unit及exact links，owner/referenced Message/run/version/time/empty-state闭合。
4. RuntimeRecordPort两方法exact、互斥、无union/optional/alias/fallback/bypass；v1 surface保持。
5. canonical environment、focused、persistence/Runtime neighbor、Alembic/full、逐commit containment、feature/latest-overlay patch-identity与exact-head review全部通过。
6. Z单独完成不形成B_YZ；只有Y/Z串行reviewed merge才解锁01-07AA。

</success_criteria>

<output>
完成后不创建Summary或共享State。Executor只按`handoff_format`交接；Integrator在Y/Z共同reviewed merge后另行索引B_YZ证据。
</output>
