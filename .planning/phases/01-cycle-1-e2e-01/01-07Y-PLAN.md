---
phase: 01-cycle-1-e2e-01
plan: 07Y
type: tdd
wave: 25
depends_on:
  - 01-07Q
files_modified:
  - src/mini_agent/core/request_processing.py
  - tests/component/core/test_request_processing.py
autonomous: true
requirements:
  - E2E01-01
  - E2E01-04
user_setup: []
must_haves:
  truths:
    - "01-07Y 只增加纯 Core 的 Request Understanding v2 initial decision/revalidation；它不读写数据库、不生成可信身份、不切换 Runtime，也不修改既有 v1 reducer。"
    - "canonical RequestUnderstandingOutputV2 的实际 Candidate 必须逐项得到 keyed ACCEPT/REJECT；aggregate-invalid 与 atomic-failure 不能伪装成 Candidate REJECT。"
    - "零 Candidate、全部 REJECT、部分接受与multi-ACCEPT都按独立Candidate逐项形成quote-free exact v2 closure；Y不得仅因Candidate数量发明REJECT reason、任意选择或静默丢弃。"
    - "每个 ACCEPT 都必须与自己的 AcceptedTaskDeltaV2、InputBinding、Task、RequestUnit 形成 exact bijection；每个新 Task effect固定base=null/result=1，父记录和全部child使用同一次可信UTC clock sample。"
    - "只有恰好一个emitted且accepted Candidate时保留shared NextMove供active thin-slice revalidation；partial/multi时保留Task decisions/effects但保守丢弃不再唯一绑定的NextMove，Runtime用户结果继续是nonclaim。"
    - "01-07Y 不冻结 zero/all-REJECT、multi-ACCEPT 或 atomic write failure 的 Runtime 用户结果；这些路径不得被声称为 B_ACTIVE。"
  artifacts:
    - "src/mini_agent/core/request_processing.py 中 additive trusted candidate identity allocation、accepted Task graph、no-task/routable/unrouted decision types，以及validate_and_reduce_initial_request_v2与revalidate_next_move_v2。"
    - "tests/component/core/test_request_processing.py 中 candidate decision、provenance、closure、Task effect、revalidation、bounded failure与v1保护矩阵。"
  key_links:
    - "Intent owner §13.3–13.7 → canonical projection、keyed candidate decisions、accepted child exact set、Task effect和单次可信时间。"
    - "Thin Slice cutover manifest → aggregate_invalid_no_record / candidate_reject / atomic_failure_no_record 三个互斥 bucket。"
    - "Execution map r2 → exact B_Q → 01-07Y + 01-07Z → B_YZ；Y不依赖execution-owner merge作为feature base。"
    - "01-07Y result → 后续01-07J消费；01-07Z Application command只消费既有Core records，不依赖Y private result type。"
---

# Phase 1 Plan 01-07Y｜Request Understanding v2 initial decision

> **ISSUED ACTIVE_SWITCH PREREQUISITE TASK PACKET / IMPLEMENTATION NOT STARTED**
> 本 Packet 只实现纯确定性的 Core v2 initial decision 与 post-write revalidation。Plan、Component test或Y feature完成都不表示Application write contract、PostgreSQL writer、Runtime route、`B_YZ`、`B_J_READY`、`B_ACTIVE`、真实HTTP/Eval或产品ready已经形成。

> **DERIVED / NON_NORMATIVE**
> Request Understanding durable aggregate、版本、provenance与Task effect语义仍由Intent / Memory / Thin Slice canonical owner拥有。本Plan只把execution map r2中的01-07Y映射为一个精确Task Packet，不维护第二套产品或架构合同。

<objective>
以TDD RED→GREEN在现有quote-free v2 closure builder之上增加一个纯Core initial decision：对actual `RequestUnderstandingOutputV2.task_delta_candidates`逐项给出稳定、keyed的最终裁决；合法无Task、partial与multi结果都形成完整v2 closure，每个ACCEPT同时形成自己的真实`base=null/result=1` Task effect、`InputBinding`、`Task`与`RequestUnit`；只有exact-one emitted/accepted active thin-slice结果继续携带可写后重验的shared NextMove。

Purpose: 关闭exact B_Q中“ModelProviderV2 success没有确定性v2 reducer”的真实阻断，使后续01-07Z/AA/J可以消费现有owner批准的record types，而不把v2投影回v1、把整体失败伪装成REJECT或让Runtime自行发明Task effect。

Output: 一个只改owned Component test的RED commit和一个只改owned Core source的GREEN commit；review finding只用append-only fix commit。Y不创建Summary、不修改共享State、canonical docs、Application、Infrastructure、Eval或Runtime。
</objective>

<execution_context>
@AGENTS.md
@.planning/GOVERNANCE.md
@.planning/phases/01-cycle-1-e2e-01/01-07F-PLAN.md
@.planning/phases/01-cycle-1-e2e-01/01-07M-PLAN.md
@.planning/phases/01-cycle-1-e2e-01/01-07Q-PLAN.md
@docs/architecture/intent-design-reference.md
@docs/architecture/memory-design-reference.md
@docs/implementation/e2e01-thin-slice-implementation-spec.md
@docs/implementation/e2e01-thin-slice-multi-agent-plan.md
@src/mini_agent/core/request_processing.py
@src/mini_agent/core/request_understanding.py
@src/mini_agent/core/task_state.py
@tests/component/core/test_request_processing.py

只使用项目受控execution adapter；不得调用stock `gsd-plan-phase`、`gsd-execute-phase`、`gsd-verify-work`、lifecycle mutation或`gsd-ship`。Graphify按用户指令保持闲置：不读取、不运行、不更新，也不作为gate。
</execution_context>

<interfaces>

## 1. Additive exact Core surface

Y在`request_processing.py`的现有v2区域additive增加：

```python
class InitialTaskIdentityAllocationV2(RuntimePrivateModel):
    candidate_ref: UUID
    accepted_delta_id: UUID
    task_id: UUID
    request_unit_id: UUID
    binding_id: UUID


class InitialAcceptedTaskGraphV2(RuntimePrivateModel):
    accepted_delta: AcceptedTaskDeltaV2
    input_binding: InputBinding
    task: TaskRecord
    request_unit: RequestUnitRecord


class InitialRequestNoTaskDecisionV2(RuntimePrivateModel):
    closure: RequestUnderstandingClosureV2


class InitialRequestRoutableTaskGraphDecisionV2(RuntimePrivateModel):
    closure: RequestUnderstandingClosureV2
    task_graph: InitialAcceptedTaskGraphV2
    next_move_candidate_ref: UUID
    next_move_candidate: NextMove


class InitialRequestUnroutedTaskGraphsDecisionV2(RuntimePrivateModel):
    closure: RequestUnderstandingClosureV2
    task_graphs: Annotated[
        tuple[InitialAcceptedTaskGraphV2, ...],
        Field(min_length=1),
    ]


def validate_and_reduce_initial_request_v2(
    *,
    request_input: RequestUnderstandingInput,
    output: RequestUnderstandingOutputV2,
    authoritative_messages: Mapping[UUID, str],
    customer_context: CustomerContext,
    request_understanding_record_id: UUID,
    candidate_identity_allocations: tuple[
        InitialTaskIdentityAllocationV2,
        ...,
    ],
    next_move_candidate_ref: UUID,
    now: datetime,
) -> (
    InitialRequestNoTaskDecisionV2
    | InitialRequestRoutableTaskGraphDecisionV2
    | InitialRequestUnroutedTaskGraphsDecisionV2
): ...


def revalidate_next_move_v2(
    *,
    decision: InitialRequestRoutableTaskGraphDecisionV2,
    current_task: TaskRecord,
    current_request_unit: RequestUnitRecord,
    current_input_binding: InputBinding,
) -> RevalidatedNextMove: ...
```

五个新增record必须通过model validator关闭各自shape：

- `candidate_identity_allocations`以`candidate_ref`绑定actual emitted Candidate，引用集合必须与Candidate ID集合精确相等；每项由可信Runtime预分配，全部record/child/Task/RequestUnit/binding IDs在本invocation内唯一。REJECT对应的预分配IDs不进入closure、Trace或error。
- `InitialAcceptedTaskGraphV2`必须让child、Task、RequestUnit、InputBinding与`base=null/result=1`精确bijective。
- `InitialRequestNoTaskDecisionV2`只接受`accepted_task_deltas=()`、`accepted_delta_refs=()`、零个ACCEPT、`next_move_candidate_ref/proposed/validated=None`。
- `InitialRequestRoutableTaskGraphDecisionV2`只接受“恰好一个emitted且ACCEPT”的active slice；closure、唯一task graph与NextMove ref exact闭合。
- `InitialRequestUnroutedTaskGraphsDecisionV2`保存partial或multi-ACCEPT的全部Task graph，数量与closure全部accepted children精确相等；它没有NextMove fields，防止共享候选被错误绑定到任一Task。
- 函数返回的type union只表示三个互斥、内部闭合的exact Core results；它不是Application persistence command union。01-07Z只消费既有Core records，不能import这些private decision types。
- 不修改或alias `InitialRequestDecision`、`validate_and_reduce_initial_request`、`revalidate_next_move`及其他v1类型；01-07V才拥有v1 Core removal。

## 2. Canonical failure partition

Reducer必须复用现有`build_request_understanding_closure_v2`与其canonical input/output/provenance helpers；不得复制第二套output DTO、quote matcher或closure builder。

只有manifest列出的五个code属于`aggregate_invalid_no_record`：

- `MODEL_INPUT_SCHEMA_INVALID`
- `MODEL_OUTPUT_SCHEMA_INVALID`
- `MODEL_SCHEMA_VERSION_INVALID`
- `TRUSTED_OR_PRIVATE_FIELD_PRESENT`
- `SOURCE_PROVENANCE_INVALID`

Caller identity allocation、UUID/UTC clock、record/child/Task graph或closed result construction失败必须保持`atomic_failure_no_record / DURABLE_CLOSURE_COMMIT_FAILED`。Y是纯Core，不声称产生或捕获数据库`TASK_STATE_CAS_CONFLICT`、`TASK_COMMIT_FAILED`；这些由后续Application/Infrastructure/Runtime owner处理。

Candidate-specific deterministic failure才进入`candidate_reject`。三个bucket不能交叉；任何aggregate或atomic failure都不返回decision/record/InputBinding/Task。异常只携带现有稳定reason code，不得附带raw query、quote、candidate value、CustomerContext、Pydantic diagnostic、cause/context或caller-controlled text。

## 3. Deterministic candidate decision matrix

只在aggregate gate通过后按emitted order独立校验actual Candidate。P0当前可接受`ADD_GOAL` Candidate固定为：

1. Candidate是canonical `ADD_GOAL`，且`goal_patch`为既有non-empty canonical value；
2. 恰有一个`order_id / TARGET_RESOURCE_IDENTIFIER / USER_CLAIM / CURRENT_MESSAGE` input；
3. input value经现有`_normalize_order_id`得到`O-<digits>`，来源quote/provenance已经通过aggregate gate；
4. contextualization中不存在同一`order_id`的`MISSING_REFERENCE`或`MULTIPLE_PLAUSIBLE_REFERENCES` uncertainty。

稳定reason优先级：

| 条件 | decision |
|---|---|
| `order_id` uncertainty = missing | `REJECT / REFERENCE_UNRESOLVED` |
| `order_id` uncertainty = multiple plausible | `REJECT / REFERENCE_AMBIGUOUS` |
| required `order_id` input shape不存在 | `REJECT / REQUIRED_INPUT_MISSING` |
| value不能规范化 | `REJECT / INPUT_VALUE_INVALID` |

Canonical DTO已把unsupported operation、空goal、重复input name、wrong source/authority等结构错误挡在aggregate gate；Y不得用`model_construct`绕过后再把它们降级成Candidate REJECT。Shared NextMove不是Candidate accept/reject依据；若Task decisions使它不再唯一适用，Reducer丢弃NextMove audit，而不是改写有效Goal decision。

Cardinality policy：

- zero Candidate → zero decision / zero child；
- 每个可接受Candidate独立`ACCEPT`并形成自己的child/Task graph；
- 每个不可接受Candidate保留自己的keyed stable `REJECT`；
- zero/all-REJECT → `InitialRequestNoTaskDecisionV2`；
- 恰好一个emitted且ACCEPT → `InitialRequestRoutableTaskGraphDecisionV2`，保留shared NextMove；
- partial或multi-ACCEPT → `InitialRequestUnroutedTaskGraphsDecisionV2`，完整保留全部decision/effect并丢弃shared NextMove。

置信度不是安全阈值。Execution map r2中的“at-most-one-accepted thin-slice decision”只约束当前可进入Z/J active route的exact-one projection；它不能覆盖Intent owner的multi/partial canonical closure。Unrouted result不决定用户结果，也不把multi路径声明为已实现Runtime。

## 4. Per-accepted Candidate Task effect

对每个ACCEPT，使用其keyed可信identity allocation和同一次`now`构造：

- `InputBinding`：normalized order ID、`USER_CLAIM`、`source_refs=(message_ref,)`、`ACCEPTED`、`confirmed_by_user=True`、created/updated均为`now`；
- `AcceptedTaskDeltaV2`：exact candidate/message、`ADD_GOAL`、goal、`input_binding_refs=(binding_id,)`、`task_id`、`base_task_state_version=None`、`result_task_state_version=1`、`accepted_at=now`；
- `TaskRecord`：trusted `customer_context.customer_id`、`ACTIVE/v1`、created/updated=`now`；
- `RequestUnitRecord`：与Task同identity/status/version，goal source与InputBinding exact，created/updated=`now`；
- parent `RequestUnderstandingRecordV2`：独立identity、actual model input/output versions、全部actual contextualization/Candidates/decisions、全部exact child refs与created=`now`。

只有exact-one emitted/accepted result设置parent `next_move_candidate_ref`，并把`proposed_base_task_state_version`逐字取自canonical output、把`validated_task_state_version`设为新Task version `1`。当前scoped `RequestUnderstandingOutputV2`和Thin Slice明确要求首个新目标proposal为`base_task_state_version=None`；Reducer不得硬编码改写模型值。若非正常Adapter以`model_construct`注入non-null base，existing exact output rebuild在Task decision前以`MODEL_OUTPUT_SCHEMA_INVALID` fail early；它不是atomic failure，也不能作为正常Gateway test。

No-task、partial或multi route的parent NextMove audit fields全部为空；未唯一绑定的shared candidate不进入result。所有REJECT allocation IDs同样不进入record/Trace/error。

## 5. Post-write revalidation

`revalidate_next_move_v2`只接受exact `InitialRequestRoutableTaskGraphDecisionV2`与当前已写入的exact Task / RequestUnit / InputBinding：

- owner、identity、status、state version `1`、InputBinding与accepted child闭包必须与decision逐字段一致；
- candidate仍必须是CALL_TOOL且不能含trusted argument field；
- 返回现有`RevalidatedNextMove`，保留原requested tool/arguments与canonical proposed base，独立生成`validated_task_state_version=1`和`argument_binding_refs=(binding_id,)`；
- argument order ID只规范化为`normalized_candidate_order_id`用于Gateway exact binding comparison，不改写arguments、不替换成InputBinding；
- mismatch、stale graph、wrong owner或noncanonical type抛现有bounded `RequestProcessingError`，不返回partial command。

Unknown tool与argument substitution在exact-one CALL_TOOL route中仍由Gateway拒绝。Canonical proposal base为null；stale-state defense由既有受控fault seam在revalidation后、Gateway前改变current Task version来验证。Y不调用Gateway、不创建GateDecision/ToolCall、不读取订单，也不决定用户结果。

</interfaces>

<packet_contract>
repository: `https://github.com/weijie567/mini-agent`
remote: `origin`
head_branch: `codex/e2e01-01-ru-v2-initial-decision`
base_branch: `integration/e2e01-thin`
base_sha: `2b9fde6f0e09308a53b86a4929ea3b639660f82e`
base_tree: `a68738b62695593a114c816cab2264b670494537`
input_barrier: `B_Q`
output_barrier: `B_YZ / ONLY AFTER 01-07Y AND 01-07Z BOTH FEATURE EXACT-HEAD AND LATEST-INTEGRATION OVERLAY REVIEWED-SERIAL-MERGED`
worktree_id: `e2e01-01-ru-v2-initial-decision`
writer: `Request Understanding Core v2 initial-decision sole writer, supervised by /root Integrator`
agent_role: `runtime-engineer / Core-only`
active_routing: `false`

planning_and_owner_provenance:

- exact feature base/tree `B_Q = 2b9fde6f0e09308a53b86a4929ea3b639660f82e` / `a68738b62695593a114c816cab2264b670494537`
- Q Plan / category amendment / feature PR #104/#105/#106 formed exact B_Q
- execution-owner r2 remediation PR #107 reviewed merge `e602bc282c2929cc69a297d991093b236ebad156` / tree `7d5521cf06f0416c4b7cac07fe365cfdf0ae4417`; it authorizes Y but does not replace feature base B_Q
- Intent / Memory / Thin Slice owner blobs `456be9c7d7884e2a58c4d07b867765ed336aa6f5` / `5c27ba3bd2ed74e5164bdd0812133041ed96f242` / `233a9c06ef6ef9300bef1a0e4f86659b0ec26a13`
- execution-map blob at feature base / reviewed r2 planning context `c8970d6195a61064fdf3b4186d338fd8cfe8eee8` / `ff0db79e00795c8f655c92c97c4a7e7de27fb215`
- official 01-07Y Plan merge SHA/blob由Integrator在Plan PR reviewed merge后捕获；Plan或owner merge不替换feature exact base B_Q

owned_files_at_base:

- `src/mini_agent/core/request_processing.py` = `261c6318e60756d57d4d15bfcf62b5c2da236760`
- `tests/component/core/test_request_processing.py` = `fa6b54735983e72d1296c212b467d7d613401989`

owned_files:

- `src/mini_agent/core/request_processing.py`
- `tests/component/core/test_request_processing.py`

allowlist:

- `src/mini_agent/core/request_processing.py`
- `tests/component/core/test_request_processing.py`

forbidden_files: `ALL REPOSITORY FILES OUTSIDE THE TWO-FILE ALLOWLIST`，尤其包括 other `src/mini_agent/core/**`、all `src/mini_agent/application/**`、`src/mini_agent/infrastructure/**`、`src/mini_agent/evaluation/**`、other `tests/**`、`evals/**`、`alembic/**`、`tests/conftest.py`、`pyproject.toml`、`uv.lock`、`compose.yaml`、`docs/**`、`.planning/**`、`AGENTS.md`、`PROJECT_DIRECTION.md`、`README.md`、`graphify-out/**`。

canonical_inputs:

- `docs/architecture/intent-design-reference.md` §10.4、§11.3、§13.1–13.8与P0验收清单。
- `docs/architecture/memory-design-reference.md` Task/InputBinding/owner与atomic closure边界。
- `docs/implementation/e2e01-thin-slice-implementation-spec.md` RU v2 cutover manifest、failure partition、E2E01-01 exact mapping与错误矩阵。
- `docs/implementation/e2e01-thin-slice-multi-agent-plan.md` reviewed r2 `B_Q → {01-07Y,01-07Z} → B_YZ`、Y two-file ownership与barrier nonclaims。
- exact B_Q中的v2 DTO、closure builder、v1 reducer regression与owned source/test blobs。

dependencies:

- `01-07F = REVIEWED_MERGED`：v2 direct-binding DTO和quote-free closure builder存在。
- `01-07Q = REVIEWED_MERGED`：形成exact B_Q，Application active codec mapping已切到RU-v2。
- `01-07Y EXECUTION OWNER = REVIEWED_ALIGNED`：PR #107将缺失Core decision映射为本Packet，target denominator为42。
- `01-07Z`与Y同wave但文件无交集；Y不得导入或等待Z的新Application symbol。
- new external/package/schema/migration dependency: `NONE`。

required_checks:

- Gate A精确branch/worktree/base/tree/two blobs/clean state；feature必须直接从B_Q创建。
- focused baseline `uv run pytest tests/component/core/test_request_processing.py -q`；预期B_Q为`55 passed`。
- RED只改owned test且只因本Packet声明的additive v2 types/functions/behavior缺失而失败；现有v1与closure-builder tests必须保持绿色。
- GREEN后focused Core全绿，并运行`uv run pytest tests/component/core/test_request_understanding_contract.py tests/component/core/test_task_state_contract.py -q`。
- canonical environment可用；`uv run alembic upgrade head`与`uv run pytest` full gate通过。B_Q参考基线为`1901 passed, 1 deselected, 12 warnings`，新增Y tests允许总数只按实际新增增长。
- exact type / undeclared state / source provenance / reason priority / zero-all-partial-multi decision / one-clock / ID binding / no-raw failure / v1 surface regression matrix。
- two-file changed-files、commit-order、no-merge、no-import outside existing Core modules、protected v1 surface与clean Worktree。
- repository-level cross-file impact scan（显式排除`graphify-out/**`）。
- feature exact-head及latest-integration overlay独立review，unresolved `CRITICAL/HIGH/MEDIUM/LOW = 0/0/0/0`。

commit_protocol:

1. RED `test(01-07Y): require ru v2 initial decision`只改owned test，增加success/no-task/all-reject/partial/multi、provenance、bounded failure与revalidation tests；source blob必须仍为base值，失败不得来自fixture、import cycle或环境。
2. GREEN `feat(01-07Y): add ru v2 initial decision`只改owned Core source，复用现有v2 canonical/provenance/closure helpers并增加上述五个record types与两个functions；不得改v1函数、Core DTO owner文件或任何外部boundary。
3. Review finding只用append-only `fix(01-07Y): ...`，始终限两文件；不得amend、rebase或force-push已审历史。每次新head重跑focused/full/containment并重新review。

done_when:

- RED/GREEN及任何fix的SHA、tree、scope、失败/通过原因可复现。
- actual v2 output产生完整keyed decision；aggregate/atomic bucket不被伪装为REJECT。
- zero/all-reject/no-task与exact-one/partial/multi accepted closure分别闭合；多eligible不任意选取，每个ACCEPT都形成自己的Task graph。
- 每个accepted route的record/child/InputBinding/Task/RequestUnit与base-null/result-1精确bijective，single clock与trusted owner成立；只有exact-one emitted/accepted result保留NextMove ref。
- revalidate保留候选、只形成controlled binding projection；argument substitution/unknown tool留给Gateway。
- focused、Core邻接tests、Alembic/full、two-file containment、feature/latest-overlay独立review全部通过。
- Y与Z reviewed serial merge后才形成B_YZ；Y单独merge不解锁AA/J。

contract_changes: `YES / ADDITIVE CORE V2 INITIAL DECISION` — 增加trusted identity allocation、accepted Task graph、三个互斥Core result和两个v2 reducer/revalidation函数；不修改canonical owner、DTO版本、v1 surface、Application/Infra/Runtime/HTTP。
security_impact: `YES / TRUSTED IDENTITY, SOURCE AND BINDING` — customer_id/UUID/time只由caller trusted context提供；authoritative Message/provenance exact；raw quote只用于span/hash后丢弃；NextMove参数不被提升为可信binding；bounded failures无raw diagnostic。
eval_impact: `YES / COMPONENT PREREQUISITE` — 增加Core Component regression覆盖zero/all/partial/multi与security failure；不改EvalCase、Dataset、Grader、Result、threshold、Baseline或lifecycle。
rollback: 合并前关闭PR；合并后用普通revert PR撤销01-07Y feature commits，并阻塞B_YZ、AA、J及全部下游。不得reset/force-push、修改B_Q、回写v1 projection或让Runtime在缺少Y时继续路由v2。

handoff_to: `/root Integrator`
handoff_format: repository/remote/branch/worktree、exact B_Q base/tree、Plan merge/blob、base/head two-file blobs、RED/GREEN/fix SHAs与输出、focused/Core-neighbor/Alembic/full结果、decision/reason/closure/revalidation矩阵、protected-v1 oracle、changed-files/commit containment、cross-file scan、contract/security/Eval nonclaims、feature/overlay review、PR/merge SHA、与Z串行merge后B_YZ tree、风险与rollback。
</packet_contract>

<cross_file_impact>

- `CONFIRMED`：Intent / Thin Slice owner已经批准actual contextualization/Candidate、keyed decision、accepted child/Task effect和failure partition；Y实现现有contract，不需要修改canonical docs。
- `CONFIRMED`：Application records/ports当前只有v1 initial graph command；该缺口由同wave 01-07Z独占，Y不得跨ownership补写。
- `CONFIRMED`：PostgreSQL current writer仍v1-only；由B_YZ后的01-07AA独占。Y完成后仍不可形成durable v2 graph。
- `CONFIRMED`：Runtime仍调用v1 reducer；由B_J_READY后的01-07J独占。Y不得修改AgentRunService或把Component test声称为Runtime success。
- `OPEN / NONCLAIM`：zero/all-REJECT、multi-ACCEPT与atomic write failure的Runtime user outcome没有冻结；Y只返回Core decision，不做Run stop/result mapping。
- `CONFIRMED / DERIVED STATUS DRIFT`：`.planning/PROJECT.md`、Requirements/Roadmap/State/Validation、`PROJECT_DIRECTION.md`与`README.md`仍显示旧B_IP/39快照；不在Y allowlist，由dedicated single writer后续对齐。
- `NOT_FOUND`：没有owner要求Y修改tool catalog、business capability、migration、Provider/Eval或HTTP contract。
</cross_file_impact>

<threat_model>

| threat_id | category | boundary | disposition | mitigation |
|---|---|---|---|---|
| `Y-S01` | Spoofing | model/caller → customer_id、record/Task identity、time | `MITIGATE / BLOCK` | exact CustomerContext/UUID/UTC inputs；output不得携带或覆盖trusted fields |
| `Y-T01` | Tampering | model_construct/undeclared state → canonical output | `MITIGATE / BLOCK` | 复用exact rebuild与undeclared-state gate；aggregate invalid不创建record |
| `Y-T02` | Tampering | candidate REJECT →伪造accepted child/Task effect | `MITIGATE / BLOCK` | candidate/decision/child exact sets、每个ACCEPT与其唯一Task graph bijection及result version checks |
| `Y-T03` | Tampering | NextMove arguments → InputBinding | `MITIGATE / BLOCK` | binding只由validated current-message input生成；revalidate保留candidate并独立投影binding refs |
| `Y-R01` | Repudiation | replay/decision → 无稳定key | `MITIGATE / BLOCK` | actual emitted IDs、keyed decision、trusted record/child IDs、single clock与exact tests |
| `Y-I01` | Information Disclosure | raw quote/query/Pydantic error → exception/Trace | `MITIGATE / BLOCK` | quote只用于span/hash；bounded stable code；cause/context/raw diagnostic不可达 |
| `Y-D01` | Denial of Service | multi Candidate → nondeterminism/incomplete graph | `MITIGATE / BLOCK` | emitted-order independent validation；全部decision/effect exact闭合；partial/multi保留全部Task graphs并丢弃shared NextMove；Y无I/O |
| `Y-E01` | Elevation of Privilege | accepted user claim → business fact/authorization | `MITIGATE / BLOCK` | InputBinding保持USER_CLAIM；不读订单、不授权Tool、不创建GateDecision/ToolCall |

</threat_model>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: RED — freeze exact v2 decision and revalidation behavior</name>
  <files>tests/component/core/test_request_processing.py</files>
  <read_first>Intent §13.3–13.7、Thin Slice cutover manifest/failure partition、execution map Y acceptance、现有v2 closure tests与v1 reducer tests</read_first>
  <action>只改owned test。新增五个record class和两个function的exact signature/type tests；用canonical fixtures覆盖zero、all reject、one emitted/accepted、one ACCEPT + one stable REJECT、two eligible both ACCEPT、uncertainty、invalid value、non-CALL_TOOL revalidation、argument substitution、unknown tool、source/provenance、candidate/allocation exact set、one-clock/trusted IDs、per-ACCEPT Task/InputBinding bijection、revalidation与raw-free bounded errors。partial/multi断言完整保留各自decision/effect并且不携带shared NextMove；保留现有v1行为tests，禁止skip/xfail、数据库、network或Application fake。</action>
  <verify>
    <automated>uv run pytest tests/component/core/test_request_processing.py -q</automated>
    RED必须非零且只因additive Y symbols/behavior缺失；B_Q source blob保持`261c6318e60756d57d4d15bfcf62b5c2da236760`。
  </verify>
  <done>测试把aggregate gate、独立candidate decision、no-task/routable-one/unrouted-partial-multi三条shape和post-write revalidation精确冻结。</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: GREEN — implement pure v2 initial decision</name>
  <files>src/mini_agent/core/request_processing.py</files>
  <read_first>Task 1 RED、现有build_request_understanding_closure_v2、RequestUnderstanding/TaskState v2 DTO、v1 reducer/revalidation protected surface</read_first>
  <action>只改owned Core source。增加trusted identity allocation、accepted Task graph、三个closed result models、candidate reason helper、validate_and_reduce_initial_request_v2与revalidate_next_move_v2；复用现有normalization、canonical/provenance和closure helpers。构造exact zero/all/one/partial/multi closure，并为每个ACCEPT构造自己的InputBinding、Task/RequestUnit与AcceptedTaskDeltaV2；只在exact-one emitted/accepted shape保留shared NextMove。所有failure使用既有bounded类型。不得I/O、random/clock调用、v2→v1 projection、修改DTO owner或捕获raw Exception。</action>
  <verify>
    <automated>uv run pytest tests/component/core/test_request_processing.py -q
uv run pytest tests/component/core/test_request_understanding_contract.py tests/component/core/test_task_state_contract.py -q</automated>
    全部Y与邻接Core tests通过；v1 protected tests保持绿色。
  </verify>
  <done>纯Core可从actual v2 input/output与trusted values形成exact no-task、routable-one或unrouted partial/multi Task graph decision，并可只对写入后的routable exact-one current graph重验NextMove。</done>
</task>

</tasks>

<verification>

Feature Gate A必须在任何RED编辑前从feature Worktree根执行并记录：

```bash
set -euo pipefail

base_sha=2b9fde6f0e09308a53b86a4929ea3b639660f82e
base_tree=a68738b62695593a114c816cab2264b670494537
expected_branch=codex/e2e01-01-ru-v2-initial-decision
expected_worktree_id=e2e01-01-ru-v2-initial-decision
expected_remote=https://github.com/weijie567/mini-agent.git
current_root="$(git rev-parse --show-toplevel)"

test "$(git remote get-url origin)" = "$expected_remote"
test "$(git branch --show-current)" = "$expected_branch"
test "$(basename "$current_root")" = "$expected_worktree_id"
test "$(git rev-parse HEAD)" = "$base_sha"
test "$(git rev-parse HEAD^{tree})" = "$base_tree"
test "$(git rev-parse "${base_sha}:src/mini_agent/core/request_processing.py")" = \
  261c6318e60756d57d4d15bfcf62b5c2da236760
test "$(git rev-parse "${base_sha}:tests/component/core/test_request_processing.py")" = \
  fa6b54735983e72d1296c212b467d7d613401989
test -z "$(git status --short --untracked-files=all)"
uv run pytest tests/component/core/test_request_processing.py -q
```

Gate B / final：

```bash
set -euo pipefail

base_sha=2b9fde6f0e09308a53b86a4929ea3b639660f82e
expected_changed="$(printf '%s\n' \
  src/mini_agent/core/request_processing.py \
  tests/component/core/test_request_processing.py | LC_ALL=C sort)"

git diff --check "$base_sha"...HEAD
actual_changed="$(git diff --name-only "$base_sha"...HEAD | LC_ALL=C sort)"
test "$(printf '%s\n' "$actual_changed" | sed '/^$/d' | wc -l | tr -d ' ')" = 2
test "$actual_changed" = "$expected_changed"
test -z "$(git log --merges --format=%H "$base_sha"..HEAD)"
uv run pytest tests/component/core/test_request_processing.py -q
uv run pytest \
  tests/component/core/test_request_understanding_contract.py \
  tests/component/core/test_task_state_contract.py -q
uv run alembic upgrade head
uv run pytest
```

Repository-level impact scan：

```bash
rg -n \
  'validate_and_reduce_initial_request(_v2)?|revalidate_next_move(_v2)?|InitialRequest.*DecisionV2|RequestUnderstandingClosureV2|CandidateValidationRecordV2|AcceptedTaskDeltaV2|B_Q|B_YZ|01-07[YZJ]' \
  AGENTS.md README.md PROJECT_DIRECTION.md docs .planning src tests evals \
  --glob '!graphify-out/**'
```

scan只报告现有owner、后续Z/AA/J consumer、protected v1 surface与已知derived status drift；Y writer不得越allowlist修正。Feature exact head必须对两项changed files取得独立`PASS / 0/0/0/0` review。Integrator串行merge时若Y不是第二个合入B_YZ的feature，也仍须在latest integration上做patch-identity/no-conflict overlay、重复focused/full/containment与review；只有Y/Z都reviewed merged后才命名共同barrier。

</verification>

<success_criteria>

1. RED/GREEN提交、失败/通过原因、two-file scope、SHA/tree与测试输出可复现。
2. aggregate-invalid、candidate-reject与atomic-failure bucket不交叉；错误raw-free。
3. zero/all/partial/multi exact-set闭包通过；two+ eligible不任意选择，每个ACCEPT都形成且只形成一个Task graph。
4. exact-one accepted route形成独立RU identity、one-clock、one child、one InputBinding/Task/RequestUnit与base-null/result-1 effect；partial/multi完整保留全部Task effect但不携带shared NextMove。
5. post-write revalidation保留NextMove候选并形成独立binding/version projection；不执行Tool或授权资源。
6. focused/Core neighbor/Alembic/full、v1 regression、containment、feature/latest-overlay exact-head review全部通过。
7. Y单独完成不形成B_YZ；只有Y/Z串行reviewed merge才解锁01-07AA。

</success_criteria>

<output>
完成后不创建Summary或共享State。Executor只按`handoff_format`交接；Integrator在Y/Z共同reviewed merge后另行索引B_YZ证据。
</output>
