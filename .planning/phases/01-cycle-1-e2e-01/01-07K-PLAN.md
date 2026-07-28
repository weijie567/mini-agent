---
phase: 01-cycle-1-e2e-01
plan: 07K
type: tdd
wave: 22
depends_on:
  - 01-07I
  - 01-07P
files_modified:
  - src/mini_agent/infrastructure/persistence/postgres.py
  - src/mini_agent/infrastructure/order/postgres.py
  - tests/integration/test_postgres_record_adapters.py
  - tests/integration/test_postgres_get_order.py
autonomous: true
requirements:
  - E2E01-01
  - E2E01-04
user_setup: []
must_haves:
  truths:
    - "01-07K 只执行 DEPENDENCY_EXPAND 的 Infrastructure reader/producer：实现 ExactRunEvidencePort，并让 PostgreSQL get_order producer 从同一次 owner-scoped 读取生成 authoritative source_version。"
    - "Exact-Run reader 必须在一个 PostgreSQL REPEATABLE READ、READ ONLY transactionally-consistent snapshot 中先做 trusted-owner root filter，再 strict exact-version decode、物理 metadata/reference 对照、RU-v2 provenance replay、relation/cardinality 与数据库 closed-set 验证。"
    - "root 不存在、无权或 payload 读取前无法证明 owner 时统一返回 None；root 一旦选中，任何坏 version、payload、owner、provenance、child、reference、missing/extra/duplicate/cross-run graph 都抛 fresh bounded P0PersistenceIntegrityError，不返回 partial、None 或换 session 重试。"
    - "reader 对 request_understanding_record 只接受 exact request_understanding_record.p0.v2，对其余 closure record family 只接受各自 exact v1；不得 active/default/latest、try-v1、try-other-version、alias、rewrite、backfill或从历史 v1 重建 v2。"
    - "get_order source_version 只能由实际 trusted query customer_id、validated order_id 与同一查询返回并 strict-validated 的 safe projection按 owner算法计算；不得二次查询、扩大 predicate、使用 stored_at/fixture/schema/runtime/Eval version或 caller token。"
    - "missing 与 foreign order 继续完全不可区分且不产 token；payload corruption、order-id drift或计算失败继续是 bounded SYSTEM_FAILURE，不降级为 not-found，不返回部分事实。"
    - "01-07K 不修改 Application/Core/Runtime/Eval、physical schema/migration、active codec/registry、Composition Root、Case lifecycle或 readiness；K 单独完成不形成 B_DEPENDENCY。"
  artifacts:
    - "PostgresRecordAdapter.load_exact_run_evidence_for_owner 的 single-snapshot strict physical reader。"
    - "PostgresGetOrderAdapter 的 exact deterministic source_version producer。"
    - "两份 Integration tests中的 closed-set/provenance/snapshot和source-version固定向量证据。"
  key_links:
    - "01-07I ExactRunEvidencePort/Closure → PostgreSQL one-snapshot implementation。"
    - "Memory §15.2 exact-version、trusted-owner、完整关联闭包与transactional consistency → reader fail-closed gate。"
    - "Thin Slice §6.2.1 source_version authority/canonical bytes → get_order single-read producer。"
    - "P0-RU-V2-EXECUTION-MAP：B_IP → {01-07K,01-07L} → B_DEPENDENCY；K/L文件交集为0且必须串行merge。"
---

# Phase 1 Plan 01-07K｜PostgreSQL strict evidence reader and order source-version producer

> **ISSUED DEPENDENCY_EXPAND TASK PACKET / IMPLEMENTATION NOT STARTED**
> 本 Packet 只冻结 Infrastructure physical reader与`get_order` producer。Plan签发、Integration test或K feature完成都不表示Eval mapper、Runtime v2、active routing、Trajectory / E2E Result或产品ready。

> **DERIVED / NON_NORMATIVE**
> Memory、Thin Slice、Request Understanding与execution order仍由active canonical owner拥有。本Plan只把现行合同映射为一个精确Infrastructure Task Packet，不维护第二套产品或持久化语义。

<objective>
以TDD RED→GREEN实现`ExactRunEvidencePort`的PostgreSQL Adapter和`get_order` authoritative `source_version` producer。

Purpose: 为后续真实Eval SUT提供expectation-free、owner-scoped、single-snapshot exact-Run logical closure，并关闭`GetOrderResult.FOUND` producer仍返回`source_version=None`的迁移缺口。

Output: 一个只改两份Integration test的RED commit、一个只改record adapter的reader GREEN commit和一个只改order adapter的producer GREEN commit；不创建Summary，不修改共享State或canonical owner。
</objective>

<execution_context>
@AGENTS.md
@.planning/GOVERNANCE.md
@.planning/phases/01-cycle-1-e2e-01/01-07G-PLAN.md
@.planning/phases/01-cycle-1-e2e-01/01-07I-PLAN.md
@.planning/phases/01-cycle-1-e2e-01/01-07P-PLAN.md
@docs/architecture/memory-design-reference.md
@docs/architecture/intent-design-reference.md
@docs/implementation/e2e01-thin-slice-implementation-spec.md
@docs/implementation/e2e01-thin-slice-multi-agent-plan.md
@src/mini_agent/application/persistence.py
@src/mini_agent/application/records.py
@src/mini_agent/application/ports.py
@src/mini_agent/infrastructure/persistence/models.py
@src/mini_agent/infrastructure/persistence/postgres.py
@src/mini_agent/infrastructure/order/postgres.py
@tests/integration/test_postgres_record_adapters.py
@tests/integration/test_postgres_get_order.py

只使用项目受控execution adapter；不得调用stock `gsd-plan-phase`、`gsd-execute-phase`、`gsd-verify-work`、lifecycle mutation或`gsd-ship`。Graphify按用户指令保持闲置：不读取、不运行、不更新，也不作为gate。
</execution_context>

<interfaces>

## 1. Exact Port surface and pre-payload indistinguishability

`PostgresRecordAdapter`实现既有Application Port的exact method，不增加第二个public reader：

```python
async def load_exact_run_evidence_for_owner(
    self,
    *,
    owner_scope: TrustedOwnerScope,
    run_id: UUID,
) -> ExactRunEvidenceClosure | None: ...
```

- `owner_scope`必须是服务端构造的exact `TrustedOwnerScope`；`run_id`必须是exact UUID。mapping、subclass、string coercion或persisted owner不能授权。
- 第一个payload-bearing read必须同时限定`record_code=agent_run_record`、exact `run_id`与`scope_owner_customer_id=owner_scope.customer_id`，并使用bounded `LIMIT 2`或等价overflow sentinel。
- 零行只表示absent / unauthorized / ownership-unverified，返回`None`且不再读取同一`run_id`的其他payload或reference，不产生可区分诊断。
- root duplicate、root physical projection漂移或root被选中后的任何失败都使用现有bounded `P0PersistenceIntegrityError`；error只携带stable category与fresh correlation UUID，`__cause__` / `__context__`清空，不含raw SQL、payload、identity、owner、message、Cookie或secret。

## 2. One-snapshot physical read

一次调用只创建一个Session和一个数据库transaction。任何payload query前，在该transaction中建立：

```sql
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY
```

或测试证明语义完全等价的PostgreSQL exact fence。不得：

- 在root read后关闭session再逐Port拼接；
- 对integrity/serialization错误自动换session重试；
- 使用无事务pre-scan、READ COMMITTED多快照或caller持有的stale closure；
- lock、claim、write、repair、backfill、re-encode或修改任何row。

Integration race必须证明：root读取后并发事务修改关联row，reader仍只看到同一snapshot的完整旧投影，不形成old/new hybrid；下一次独立调用可以看到完整新投影。失败或成功后Session/transaction都正常关闭，测试namespace零残留。

## 3. Exact version, decode and physical parity

reader对每一候选row都显式提供`record_code + record_schema_version`调用现有versioned codec：

- `request_understanding_record`只能是`request_understanding_record.p0.v2`，并携带exact `AcceptedTaskDeltaV2` logical children；
- closure其余top-level record code只接受各自`.p0.v1`；
- exact Run graph中出现RU-v1、unknown/wrong pair、missing version、catalog外version或v2 child不闭合都fail closed；不得fallback到active v1 decoder、latest/default、union、try-other-version或read-time migration；
- physical row的code/version/logical identity、owner/conversation/run/task/request-unit/tool-call projection、lifecycle/state/attempt projection、stored envelope与decoded source逐项一致；
- `p0_record_references`必须与envelope内approved top-level/external references逐项、顺序和ordinal精确相等；missing、extra、duplicate、reordered、negative/gap ordinal或cross-owner target均fail closed；
- logical child只来自strict-decoded envelope，不能伪装成第二条top-level row。

现有`P0PersistenceIntegrityCategory`足以表达失败；本Packet不得修改Application enum。version/code/metadata、owner、link、cardinality与child失败分别落在现有最窄类别，不能把所有错误折叠为database system error或safe absence。

## 4. Relation-driven bounded discovery and exact database closed set

K在Infrastructure module内冻结以下**reader safety cap**；这些数值只限制P0 exact-Run审计读取，不把开放的Core多意图/cardinality语义改写成产品上限：

| physical / logical family | exact cap | query / overflow rule |
|---|---:|---|
| `agent_run_record` root、`conversation_record` root | 各1 | `LIMIT 2`；第二行即`LINK_CARDINALITY_MISMATCH` |
| `request_understanding_record` | 1 | `LIMIT 2`；同Run v1/v2或第二条均整体失败 |
| `context_manifest_record`、`model_visible_toolset_artifact` | 各2 | 对应Thin Slice `model_calls <= 2`，每family `LIMIT 3` |
| `gate_decision_record`、`tool_call_record`、`observation_record` | 各1 | 对应Thin Slice `tool_calls/get_order_attempts <= 1`，每family `LIMIT 2` |
| `message_record`、`task_record`、`request_unit_record`、`conversation_task_link_record`、`run_task_link_record`、`input_binding_record`、`trace_event_record` | 各64 | Infrastructure safety cap；每family `LIMIT 65` |
| 每个top-level source的normalized references | 64 | `ORDER BY ordinal, relation, target... LIMIT 65` |
| `accepted_task_delta`、`task_state_transition` logical children | 每family总计64且每parent 64 | decode前先检查raw child count `<=64`；随后strict child closure |
| `tool_attempt_record` logical children | 总计1 | 对应P0无retry / `get_order_attempts <= 1`；`attempt_count`与child exact |

任何cap达到`N+1`都在decode/materialize前抛fresh bounded `P0PersistenceIntegrityError(LINK_CARDINALITY_MISMATCH, correlation_ref)`；不得truncate、分页后拼接、提高cap、retry或用全owner/全Conversation无界扫描。未来需要超过这些reader caps时必须先修订K owner/Plan，不能由executor私设数值。

candidate discovery在同一snapshot内按以下固定顺序执行，并对每个selector分别应用上表的`N+1` overflow probe；同一family从多个selector所得identity先去重，再次要求union size不超过该family cap：

1. **Trusted root selector**：只用`record_code=agent_run_record + exact run_id + scope_owner_customer_id`取得唯一Run；strict decode后取得exact Conversation identity。
2. **Reverse-reference selector**：从root Run identity开始，只沿Thin Slice reference matrix中“source属于本Run descendant、target属于已发现Run/Task/RequestUnit/ToolCall anchor”的registered relation反向找source identity。已发现的`ContextManifest`与`InputBinding`也作为受控anchor，但只允许`GateDecisionRecord.context_manifest_id → context_manifest_record`及`GateDecisionRecord.argument_binding_refs[] → input_binding_record`两类canonical incoming relation，以便没有ToolCall的rejected Gate仍可发现；不得泛化为对Conversation、Message、Manifest、Binding或Toolset dependency的全部incoming traversal，以免把其他Run历史带入。每个新source再按exact `(record_code, logical_identity, scope_owner_customer_id)`取row。
3. **Physical-projection selector**：按family查询`run_id=root run`；对已发现Task/RequestUnit再查询exact `task_id IN (...)` / `request_unit_id IN (...)`；Conversation只取root指定identity，Message只可由approved outgoing source refs发现，不能用`conversation_id`批量猜测。selector结果与reverse-reference union，不相互替代。
4. **Forward-reference selector**：对每个已选source读取normalized outgoing references，按exact code/identity/owner取dependency row；只接受canonical matrix中的top-level reference，payload/local correlation不伪装成top-level。
5. 以visited `(record_code, logical_identity)`集合迭代2–4至fixed point；family cap和每source reference cap使总frontier有确定上界。Eval Result/Failure source、catalog外code/relation或跨owner endpoint一律整体失败，不扩展closure。

union完成后才strict decode并验证：

- root Run、Conversation、RU、`RunTaskLink`、Task、RequestUnit、InputBinding、ConversationTaskLink、Gate、ToolCall/attempt、Observation、Manifest、Toolset artifact、Trace及logical child exact closure；
- Message集合恰为RU v2 contextualization/input provenance、InputBinding/RequestUnit、Manifest和Trace实际引用的source-message set；terminal ASSISTANT Message没有approved ref就不进入；
- physical code/version/identity/owner/run/task/request-unit projection、normalized references与decoded envelope逐项一致；
- 同snapshot重跑三个selector并要求其identity union、每个source reference tuple与decoded expected set byte-for-byte相等；任何missing、extra、duplicate、reordered或新frontier都是integrity failure。

anti-extra RED必须分别证明两个独立发现通道不能被单点篡改绕过：

- 正确`run_id/task_id/request_unit_id` projection但删除或改向root reference的额外row，仍被physical-projection selector发现并拒绝；
- null/wrong physical projection但保留指向root anchor的合法registered reference，仍被reverse-reference selector发现并拒绝；
- expected row由reference发现但其physical projection坏，或由projection发现但normalized reference缺失，均在parity gate失败；
- `GATE_REJECTED`且没有ToolCall时，Gate仍必须通过已发现Manifest/InputBinding的受控reverse relation进入closure；删除任一mandatory Gate relation或注入另一个Gate都失败；
- 对上表每个cap class参数化插入第`N+1`项，并增加“一个通道规避、另一个通道命中”的evasive-extra回归。

同时篡改全部root anchor projection与全部registered reference、因而不再声明属于该Run的孤立row不属于本exact-Run closure；K不得为寻找这类全局孤儿而扫描整个owner namespace。所有family按stable deterministic order构造现有`ExactRunEvidenceClosure`；任何失败整体丢弃，不返回partial closure。

## 5. RU-v2 authoritative Message provenance replay

在同一snapshot中，reader必须从owner-scoped Message row取得authoritative immutable `content`，对RU-v2 durable contextualization与每个durable input candidate逐项验证：

- `source_ref`命中closure中的exact Message；
- `0 <= start < end <= len(content)`；
- `content[start:end].encode("utf-8")`的SHA-256小写hex与`source_quote_sha256` byte-for-byte相同；
- span使用Python Unicode code-point offset，不trim、case-fold、normalize、模糊匹配或从candidate value重新定位；
- raw slice只用于瞬时hash比较，不能进入Trace、error、returned extra field或第二份authority。

zero/multiple textual occurrence不在read时重新推断span；reader只验证持久化的exact span/hash。任一失败使用bounded integrity error，不跳过candidate、不返回partial。

## 6. `get_order` source-version producer

`PostgresGetOrderAdapter.get_order`保留现有唯一SQL：

```python
select(MockOrderModel.order_payload).where(
    MockOrderModel.customer_id == query.customer_id,
    MockOrderModel.order_id == query.order_id,
)
```

owner-scoped query返回一行后，依次：

1. 用现有strict JSON round-trip构造exact `OrderSummaryProjection`；
2. 要求`projection.order_number == query.order_id`；
3. 构造exact canonical payload：

```python
{
    "source_version_schema": "mock-order-source-version.p0.v1",
    "owner_customer_id": query.customer_id,
    "order_id": query.order_id,
    "safe_projection": projection.model_dump(mode="json"),
}
```

4. 使用`json.dumps(..., allow_nan=False, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")`；
5. 返回`mock-order-source-version.p0.v1:sha256:`加SHA-256 lowercase hex。

同一实际safe projection与owner/order得到同一token；任何included field改变得到不同token；A→B→A允许回到A token，不声称monotonic revision或ABA detection。不得使用`stored_at`、`status_updated_at`以外的隐藏column、Fixture/Dataset/schema/registry/runtime/Eval version、randomness、HMAC secret或第二次查询。

固定向量：

- `customer-A / O-1001` → `mock-order-source-version.p0.v1:sha256:861c136b1a41ecef3cd9625dc58524ec452e939b5ca1eb70ebcab69181561c42`
- `customer-B / O-2001` → `mock-order-source-version.p0.v1:sha256:4801da34c67c9405986e368042209dedf87896b16aa5a1eead6031eed5c988be`

FOUND必须由本producer携带non-None exact token；non-FOUND/system failure不得携带。当前Core字段在01-07M前仍保持additive optional，K不能提前修改validator。Token是Runtime-private snapshot metadata，不授权、不进Agent-visible ToolSpec、HTTP、用户文案或普通Trace。

</interfaces>

<packet_contract>
repository: `https://github.com/weijie567/mini-agent`
remote: `origin`
head_branch: `codex/e2e01-01-strict-readers`
base_branch: `integration/e2e01-thin`
base_sha: `bbe14fadc0cd2e14ad35e19177b079fcab685dfc`
base_tree: `65415ff5846892f257e95d8b8bd34f50752980a2`
input_barrier: `B_IP`
output_barrier: `B_DEPENDENCY / ONLY AFTER 01-07K AND 01-07L BOTH REVIEWED-SERIAL-MERGED`
worktree_id: `e2e01-01-strict-readers`
writer: `Infrastructure persistence/read adapter sole writer with owned Integration tests, supervised by /root Integrator`
agent_role: `infra-engineer`
active_routing: `false`

planning_and_owner_provenance:

- final issuance/owner head `726ac109514cb665386b981ac506c816d3abc310`
- exact execution-map blob `ea2b5bcac4cb10c928a9e578c1286febb243c7d6`
- L/J acceptance ownership clarification [PR #93](https://github.com/weijie567/mini-agent/pull/93) reviewed head/merge `510384c9dad24c0f229dd09cc5cf4a9deedfa292` / `726ac109514cb665386b981ac506c816d3abc310`
- exact `B_IP` merge/tree `bbe14fadc0cd2e14ad35e19177b079fcab685dfc` / `65415ff5846892f257e95d8b8bd34f50752980a2`
- 01-07I Plan blob `15e114001cb81fdcf457f12a5156c9ed00085cbd`
- 01-07P Plan blob `1dcf69b2e5538137d526bdea6acf595890514892`
- Thin Slice owner blob `233a9c06ef6ef9300bef1a0e4f86659b0ec26a13`
- Memory owner blob `5c27ba3bd2ed74e5164bdd0812133041ed96f242`
- Intent owner blob `456be9c7d7884e2a58c4d07b867765ed336aa6f5`
- official 01-07K Plan merge SHA/blob由Integrator在Plan PR reviewed merge后捕获；planning merge不替换feature base `B_IP`

owned_files_at_base:

- `src/mini_agent/infrastructure/persistence/postgres.py` = `62bf768242ba141479182121200f6d041a54e5ba`
- `src/mini_agent/infrastructure/order/postgres.py` = `e1909e06bac2e64b8349154f66c2b777164f1847`
- `tests/integration/test_postgres_record_adapters.py` = `aa760d7c5fabf0ebf0b749f43de5a33729658334`
- `tests/integration/test_postgres_get_order.py` = `df6bef3de4c4925f4ccbc2cdf6bc071beb2a0b42`

allowlist:

- `src/mini_agent/infrastructure/persistence/postgres.py`
- `src/mini_agent/infrastructure/order/postgres.py`
- `tests/integration/test_postgres_record_adapters.py`
- `tests/integration/test_postgres_get_order.py`

forbidden_files: `ALL REPOSITORY FILES OUTSIDE THE FOUR-FILE ALLOWLIST`，尤其包括 `src/mini_agent/application/**`、`src/mini_agent/core/**`、`src/mini_agent/evaluation/**`、other `src/mini_agent/infrastructure/**`、`alembic/**`、`tests/conftest.py`、other `tests/**`、`evals/**`、`pyproject.toml`、`uv.lock`、`compose.yaml`、`docs/**`、`.planning/**`、`AGENTS.md`、`PROJECT_DIRECTION.md`、`graphify-out/**`。

protected_surface:

- `postgres.py`在B_IP的58个pre-existing `PostgresRecordAdapter` methods source segment与AST全部不变；K只允许新增imports、module-private constants/helpers和新的reader method，不得重写现有load/save/recovery/Eval方法。
- `order/postgres.py`只允许修改`PostgresGetOrderAdapter.get_order`并新增source-version private helper/import；`__init__`与`seed_mock_order` source/AST exact不变。
- physical models、migration chain、Application Port/DTO/codec、Core validator、Runtime、Eval和active routing全部不变。

commit_contract:

1. RED `test(01-07K): define strict postgres evidence readers`：只改两份owned Integration test；两个source blob仍等于B_IP。focused command必须因reader缺失和legacy `FOUND + None` contract失败，不得因migration、fixture、syntax或环境失败。
2. Reader GREEN `feat(01-07K): add strict postgres evidence reader`：只改`src/mini_agent/infrastructure/persistence/postgres.py`；不重写RED。
3. Producer GREEN `feat(01-07K): add postgres order source version`：只改`src/mini_agent/infrastructure/order/postgres.py`；不重写RED或Reader GREEN。
4. 首个review candidate相对B_IP恰为上述三个commit；final history为这三个固定RED/two-GREEN加零到多笔append-only `fix(01-07K): ...`。Finding修复不得amend/rebase/force-push已审历史，且每笔fix仍只能修改四文件allowlist。

contract_changes: `YES / ADDITIVE INFRASTRUCTURE DEPENDENCY` — 实现既有ExactRunEvidencePort并使唯一get_order producer返回authoritative token；不改Port/DTO/schema/codec active routing。
security_impact: `YES` — trusted-owner prefilter、single snapshot、exact version/provenance/closed set、foreign/absent不可区分、corruption fail-closed、raw diagnostic disposal和single-read token authority。
eval_impact: `YES / INFRASTRUCTURE INPUT ONLY` — 提供后续mapper可消费的expectation-free closure；不构造Case、expectation、safe observable、grader result、Trajectory/E2E状态或Baseline。
new_dependencies: `NONE`
graphify_disposition: `DISABLED_BY_USER / NOT_RUN / NOT_A_GATE`
rollback: 合并前关闭PR；合并后普通revert PR逆序撤销01-07K feature/fix commits，并重新阻塞01-07M及全部active-switch/contract/01-08下游。不得reset、force-push、删除/改写row、backfill、fallback或发明schema/data migration rollback。

handoff_format: branch、exact B_IP/Plan provenance/head/commits/tree、四个base/head blobs、RED/two-GREEN输出、single-snapshot race与fixed-vector结果、protected-method oracle、focused/database/full gate、changed files/commit containment、cross-file scan、contract/security/Eval nonclaims、exact-head/latest-overlay review、风险与merge SHA。
</packet_contract>

<threat_model>

| threat_id | category | boundary | disposition | mitigation |
|---|---|---|---|---|
| `K-S01` | Spoofing | persisted owner/IDs或token → trusted authority | `MITIGATE / BLOCK` | owner只来自TrustedOwnerScope/query；decoded owner exact compare；token只由同一trusted read计算且不授权 |
| `K-T01` | Tampering | wrong version/partial row/reference/child → closure | `MITIGATE / BLOCK` | explicit versioned decode、physical parity、normalized-reference exact-set、logical child与database closed-set整体失败 |
| `K-R01` | Repudiation | multi-session stitch或second-query token | `MITIGATE / BLOCK` | one Session/REPEATABLE READ snapshot、SQL capture、race test、exact RED/GREEN/review evidence |
| `K-I01` | Information Disclosure | foreign/corrupt row/raw SQL/message → caller/error | `MITIGATE / BLOCK` | pre-payload owner filter、None不可区分、fresh bounded error、raw slice瞬时hash后丢弃 |
| `K-D01` | Denial of Service | duplicate/extra/unbounded graph → materialization | `MITIGATE / BLOCK` | root overflow sentinel、relation-driven bounded candidate set、anti-extra probe、无retry/partial |
| `K-E01` | Elevation of Privilege | closure/source_version → authorization或readiness | `MITIGATE / BLOCK` | closure/token均不授权、不路由、不写入；K单独不形成barrier或lifecycle claim |

</threat_model>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: RED — freeze exact-Run PostgreSQL reader and source-version producer</name>
  <files>tests/integration/test_postgres_record_adapters.py, tests/integration/test_postgres_get_order.py</files>
  <action>只改两份Integration test。为record adapter建立RU-v2 exact closure seeds，覆盖minimal INPUT_INVALID no-Task、success/foreign/not-found/gateway/stale-state/presentation等代表性graph；断言owner root不可区分、one Session/REPEATABLE READ、explicit v2 decode、v1/wrong-version拒绝、physical metadata/reference exact parity、Message span/hash replay、missing/extra/duplicate/cross-owner/run/history/reference负例、并发snapshot无hybrid和bounded raw-free error。按Section 4对每个cap class参数化`N+1` overflow，并覆盖projection-only、reverse-reference-only、missing-projection与missing-reference四类evasive extra。为get_order增加A/B固定向量、content change与A→B→A、同一SELECT/owner predicate、missing/foreign无token、corruption system failure与forbidden-version-source断言。不要修改shared fixture/bootstrap或使用skip/xfail。</action>
  <verify>
    <automated>uv run pytest tests/integration/test_postgres_record_adapters.py tests/integration/test_postgres_get_order.py -q</automated>
    RED必须非零且仅因01-07K reader/method behavior与legacy producer尚未实现；两个source blob仍等于B_IP。
  </verify>
  <done>RED精确证明两个missing implementation surface，不因环境、migration或test oracle自身错误失败。</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: GREEN — implement one-snapshot strict closure read</name>
  <files>src/mini_agent/infrastructure/persistence/postgres.py</files>
  <action>只新增reader所需private imports/constants/helpers和`load_exact_run_evidence_for_owner`，复用现有physical models、versioned codec与bounded error。一个REPEATABLE READ/READ ONLY transaction内按Section 4固定caps与root→reverse-reference→physical-projection→forward-reference selector执行bounded union、strict decode、RU-v2 provenance、parity与closed-set校验，最后构造existing ExactRunEvidenceClosure。不得修改58个既有method、调用多个公开Port、自行重建v2、返回raw envelope或写数据库。focused转绿后只提交本文件，subject exact为`feat(01-07K): add strict postgres evidence reader`。</action>
  <verify>
    <automated>uv run pytest tests/integration/test_postgres_record_adapters.py -q</automated>
    reader正负矩阵、concurrency snapshot、bounded error与session cleanup全部通过。
  </verify>
  <done>exact Port在single snapshot中返回完整authoritative logical closure或整体fail closed。</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: GREEN — generate authoritative get_order source version from the same read</name>
  <files>src/mini_agent/infrastructure/order/postgres.py</files>
  <action>在现有`get_order` strict projection/order-id检查后按Thin Slice exact canonical payload/JSON/SHA-256算法生成token并随FOUND返回。保留一条owner-scopedSELECT和所有not-found/system-failure外部行为；不得增加column/query、读取fixture/schema metadata、泄露token或修改Core validator。focused转绿后只提交本文件，subject exact为`feat(01-07K): add postgres order source version`。</action>
  <verify>
    <automated>uv run pytest tests/integration/test_postgres_get_order.py -q</automated>
    两个owner fixed vector、content sensitivity、A→B→A、one-query和negative matrix全部通过。
  </verify>
  <done>唯一PostgreSQL producer对每个valid FOUND都返回从同一read计算的exact runtime-private token。</done>
</task>

</tasks>

<verification>

Feature Worktree必须从仓库根目录运行：

```bash
set -euo pipefail

base_sha=bbe14fadc0cd2e14ad35e19177b079fcab685dfc
base_tree=65415ff5846892f257e95d8b8bd34f50752980a2
expected_branch=codex/e2e01-01-strict-readers
expected_worktree_id=e2e01-01-strict-readers
expected_remote=https://github.com/weijie567/mini-agent.git
current_root="$(git rev-parse --show-toplevel)"

test "$(git remote get-url origin)" = "$expected_remote"
test "$(git branch --show-current)" = "$expected_branch"
test "$(basename "$current_root")" = "$expected_worktree_id"
test "$(git worktree list --porcelain | awk -v root="$current_root" '
  $1 == "worktree" { current = $2 }
  $1 == "branch" && current == root { print $2 }
')" = "refs/heads/$expected_branch"
test "$(git rev-parse HEAD^0)" = "$base_sha" # first edit前
test "$(git merge-base HEAD "$base_sha")" = "$base_sha"
test "$(git rev-parse "$base_sha^{tree}")" = "$base_tree"
test "$(git rev-parse "$base_sha:src/mini_agent/infrastructure/persistence/postgres.py")" = \
  62bf768242ba141479182121200f6d041a54e5ba
test "$(git rev-parse "$base_sha:src/mini_agent/infrastructure/order/postgres.py")" = \
  e1909e06bac2e64b8349154f66c2b777164f1847
test "$(git rev-parse "$base_sha:tests/integration/test_postgres_record_adapters.py")" = \
  aa760d7c5fabf0ebf0b749f43de5a33729658334
test "$(git rev-parse "$base_sha:tests/integration/test_postgres_get_order.py")" = \
  df6bef3de4c4925f4ccbc2cdf6bc071beb2a0b42
test -z "$(git status --short --untracked-files=all)"

uv sync --all-groups
docker compose up --wait -d db
docker compose --profile test up --wait -d db-test
uv run alembic upgrade head

uv run pytest tests/integration/test_postgres_record_adapters.py tests/integration/test_postgres_get_order.py -q
uv run pytest

git diff --check "$base_sha...HEAD"
test "$(git rev-list --count "$base_sha..HEAD")" -ge 3
test "$(git rev-list --merges --count "$base_sha..HEAD")" -eq 0
red_sha="$(git rev-list --reverse "$base_sha..HEAD" | sed -n '1p')"
reader_green_sha="$(git rev-list --reverse "$base_sha..HEAD" | sed -n '2p')"
producer_green_sha="$(git rev-list --reverse "$base_sha..HEAD" | sed -n '3p')"
test "$(git show -s --format=%s "$red_sha")" = \
  "test(01-07K): define strict postgres evidence readers"
test "$(git show -s --format=%s "$reader_green_sha")" = \
  "feat(01-07K): add strict postgres evidence reader"
test "$(git show -s --format=%s "$producer_green_sha")" = \
  "feat(01-07K): add postgres order source version"
test "$(git diff-tree --no-commit-id --name-only -r "$red_sha" | LC_ALL=C sort)" = \
  "$(printf '%s\n' \
    tests/integration/test_postgres_get_order.py \
    tests/integration/test_postgres_record_adapters.py)"
test "$(git diff-tree --no-commit-id --name-only -r "$reader_green_sha")" = \
  src/mini_agent/infrastructure/persistence/postgres.py
test "$(git diff-tree --no-commit-id --name-only -r "$producer_green_sha")" = \
  src/mini_agent/infrastructure/order/postgres.py
test -z "$(git log --reverse --format=%s "$base_sha..HEAD" |
  sed '1,3d' |
  rg -v '^fix\(01-07K\): .+$' || true)"
for fix_sha in $(git rev-list --reverse "$base_sha..HEAD" | sed '1,3d'); do
  test -z "$(git diff-tree --no-commit-id --name-only -r "$fix_sha" |
    rg -v '^(src/mini_agent/infrastructure/(order/postgres|persistence/postgres)\.py|tests/integration/test_postgres_(get_order|record_adapters)\.py)$' ||
    true)"
done
test "$(git diff --name-only "$base_sha...HEAD" | LC_ALL=C sort)" = "$(printf '%s\n' \
  src/mini_agent/infrastructure/order/postgres.py \
  src/mini_agent/infrastructure/persistence/postgres.py \
  tests/integration/test_postgres_get_order.py \
  tests/integration/test_postgres_record_adapters.py)"
test -z "$(git status --short --untracked-files=all)"
```

Protected-method oracle必须作为同一门禁实际运行：

```bash
base_sha=bbe14fadc0cd2e14ad35e19177b079fcab685dfc
uv run python - "$base_sha" <<'PY'
from __future__ import annotations

import ast
from pathlib import Path
import subprocess
import sys

BASE = sys.argv[1]
TARGETS = (
    (
        "src/mini_agent/infrastructure/persistence/postgres.py",
        "PostgresRecordAdapter",
        frozenset(),
        frozenset({"load_exact_run_evidence_for_owner"}),
        58,
    ),
    (
        "src/mini_agent/infrastructure/order/postgres.py",
        "PostgresGetOrderAdapter",
        frozenset({"get_order"}),
        frozenset(),
        3,
    ),
)
FORBIDDEN_CALLS = frozenset({"__import__", "eval", "exec", "globals", "setattr"})


def base_source(path: str) -> str:
    return subprocess.check_output(
        ["git", "show", f"{BASE}:{path}"],
        text=True,
        encoding="utf-8",
    )


def unique_class(tree: ast.Module, name: str) -> ast.ClassDef:
    matches = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == name
    ]
    assert len(matches) == 1, (name, len(matches))
    return matches[0]


def methods(node: ast.ClassDef) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    result: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    for child in node.body:
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert child.name not in result, child.name
            result[child.name] = child
    return result


def exact_segment(source: str, node: ast.AST) -> str:
    start = node.lineno
    decorators = getattr(node, "decorator_list", ())
    if decorators:
        start = min(start, *(item.lineno for item in decorators))
    lines = source.splitlines(keepends=True)
    return "".join(lines[start - 1 : node.end_lineno])


def assert_exact_node(
    base_text: str,
    head_text: str,
    base_node: ast.AST,
    head_node: ast.AST,
) -> None:
    assert exact_segment(head_text, head_node) == exact_segment(base_text, base_node)
    assert ast.dump(head_node, include_attributes=False) == ast.dump(
        base_node,
        include_attributes=False,
    )


def top_level_defs(tree: ast.Module) -> dict[str, ast.AST]:
    result: dict[str, ast.AST] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            assert node.name not in result, node.name
            result[node.name] = node
    return result


def forbidden_call_counts(tree: ast.Module) -> dict[str, int]:
    return {
        name: sum(
            1
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == name
        )
        for name in FORBIDDEN_CALLS
    }


def imported_modules(tree: ast.Module) -> set[str]:
    modules: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return modules


for path, class_name, mutable_methods, additive_methods, expected_count in TARGETS:
    before = base_source(path)
    after = Path(path).read_text(encoding="utf-8")
    before_tree = ast.parse(before)
    after_tree = ast.parse(after)
    before_class = unique_class(before_tree, class_name)
    after_class = unique_class(after_tree, class_name)
    before_methods = methods(before_class)
    after_methods = methods(after_class)
    assert len(before_methods) == expected_count
    assert set(after_methods) == set(before_methods) | set(additive_methods)
    for name, before_method in before_methods.items():
        if name not in mutable_methods:
            assert_exact_node(before, after, before_method, after_methods[name])
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

    before_defs = top_level_defs(before_tree)
    after_defs = top_level_defs(after_tree)
    for name, before_node in before_defs.items():
        if name != class_name:
            assert name in after_defs
            assert_exact_node(before, after, before_node, after_defs[name])
    assert all(
        name.startswith("_")
        for name in set(after_defs) - set(before_defs)
    )
    assert forbidden_call_counts(after_tree) == forbidden_call_counts(before_tree)
    new_imports = imported_modules(after_tree) - imported_modules(before_tree)
    assert not any(name == "importlib" or name.startswith("importlib.") for name in new_imports)

print("01-07K protected surface: PASS (58 + 2 exact)")
PY
```

该oracle证明：

- `PostgresRecordAdapter`全部58个pre-existing methods仍各有唯一同名binding且source segment/AST exact；
- `PostgresGetOrderAdapter.__init__`与`seed_mock_order` exact；只有`get_order`是approved existing-method delta；
- 无dynamic import、`exec/eval/globals/setattr` rebinding、monkeypatch、第二个public evidence reader或第二个order Adapter。

Cross-file impact scan：

```bash
rg -n "ExactRunEvidence(Closure|Port)|load_exact_run_evidence_for_owner|source_version|mock-order-source-version" \
  AGENTS.md README.md PROJECT_DIRECTION.md docs .planning src tests evals \
  --glob '!graphify-out/**'
```

scan只报告后续L/M/Q/J/01-08消费者与owner alignment；本Packet不得越allowlist修正。Feature exact head须对四个changed files做独立canonical/security/test review并得到`PASS / CRITICAL-HIGH-MEDIUM-LOW = 0/0/0/0`。之后由Integrator在最新`integration/e2e01-thin`创建no-conflict overlay，证明patch identity、重复focused/full gate与独立review，再按K/L既定串行顺序merge。K单独merge不得写`B_DEPENDENCY`完成状态。

</verification>

<success_criteria>

1. RED/reader GREEN/producer GREEN提交顺序、四文件scope与失败/通过输出可复现；review fix只可append并逐commit受allowlist约束。
2. ExactRunEvidencePort实现满足owner-root不可区分、single snapshot、fixed per-family caps、双通道selector、exact version/decode/provenance/reference/closed-set及整体fail-closed合同。
3. `get_order`对两个固定向量和content semantics精确，SQL仍恰为同一次owner-scoped read。
4. 58 + 2个protected methods保持exact；allowlist外零改动，无active routing或lifecycle推进。
5. feature与latest-overlay均通过完整门禁和独立review；只有K/L都reviewed串行merge后才形成`B_DEPENDENCY`。

</success_criteria>
