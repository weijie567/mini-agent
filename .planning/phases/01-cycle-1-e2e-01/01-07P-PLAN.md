---
phase: 01-cycle-1-e2e-01
plan: 07P
type: tdd
wave: 21
depends_on:
  - 01-07E
  - 01-07F
files_modified:
  - alembic/versions/20260728_0003_request_understanding_v2_expand.py
  - src/mini_agent/infrastructure/persistence/models.py
  - tests/integration/test_database_migrations.py
autonomous: true
requirements:
  - E2E01-01
  - E2E01-04
user_setup: []
must_haves:
  truths:
    - "01-07P 只执行 DEPENDENCY_EXPAND 的 physical admission：把 p0_records 的 exact code/version check 从17个v1 pair扩为18个pair，唯一新增项是(request_understanding_record, request_understanding_record.p0.v2)。"
    - "record_code仍恰为17；table、column、index、FK、unique identity、JSONB envelope shape与既有17个v1 pair全部不变。"
    - "SQLAlchemy metadata从immutable P0_RECORD_SCHEMA_VERSION_CATALOG的key set生成并显式排序18个pair；历史Alembic migration使用self-contained literal，不import运行时代码。"
    - "upgrade只原子替换同名ck_p0_records_code_version_closed并保留已有v1 row；不写、改、删、backfill、reconstruct或read-time rewrite任何payload。"
    - "downgrade在同一migration transaction内锁定p0_records并用bounded EXISTS检查RU-v2 row；存在时用固定无PII诊断fail closed，且revision、row与expanded constraint全部保持0003状态。"
    - "physical v1/v2 admission不等于active registry、codec/read/write routing、多版本Runtime compatibility、owner/provenance/closure validation、data migration或readiness。"
    - "01-07P与01-07I从同一exact B_FE_EXPAND在独立Worktree并行实现，文件交集为0；必须串行review/merge，只有两者共同完成才形成B_IP。"
  artifacts:
    - "单一Alembic revision 20260728_0003及其无损fail-closed downgrade。"
    - "SQLAlchemy exact 18-pair metadata projection与migration-chain integration tests。"
  key_links:
    - "Thin Slice p0-ru-v2-cutover-r1 version catalog / DEPENDENCY_EXPAND → physical code/version admission only。"
    - "Memory §15.2 exact-version/integrity/migration rules → unsupported pair拒绝、无read-time migration、fail-closed downgrade。"
    - "P0-RU-V2-EXECUTION-MAP：B_FE_EXPAND → {01-07I,01-07P} → B_IP。"
---

# Phase 1 Plan 01-07P｜Request Understanding v2 physical expand

> **ISSUED DEPENDENCY_EXPAND TASK PACKET / IMPLEMENTATION NOT STARTED**
> 本 Packet 只扩展 PostgreSQL physical code/version admission。migration、metadata或测试通过都不表示 RU v2 payload、strict reader、Runtime、Provider/Eval、active switch、Trajectory / E2E Result 或产品 readiness 已完成。

> **DERIVED / NON_NORMATIVE**
> Request Understanding语义、exact logical mapping、Memory migration边界与execution order仍由对应active owner拥有。本Plan只冻结Infrastructure mechanics，不反向覆盖owner。

<objective>
以 TDD RED→GREEN 新增 `20260728_0003`，让generic `p0_records` 物理表可容纳exact RU v2 code/version pair，同时保持17项v1 schema与全部其他物理结构不变，并提供无silent-data-loss的fail-closed downgrade。

Purpose: 关闭01-07K strict reader之前的physical schema dependency；不提前接入writer/reader或active registry。

Output: 一个test-only RED commit和一个migration/models GREEN commit；只修改三个owned files，不创建Summary、不修改共享State。
</objective>

<execution_context>
@AGENTS.md
@.planning/GOVERNANCE.md
@.planning/phases/01-cycle-1-e2e-01/01-07E-PLAN.md
@.planning/phases/01-cycle-1-e2e-01/01-07I-PLAN.md
@docs/architecture/memory-design-reference.md
@docs/architecture/intent-design-reference.md
@docs/implementation/e2e01-thin-slice-implementation-spec.md
@docs/implementation/e2e01-thin-slice-multi-agent-plan.md
@src/mini_agent/application/persistence.py
@src/mini_agent/infrastructure/persistence/models.py
@alembic/versions/20260726_0001_initial_persistence.py
@alembic/versions/20260727_0002_p0_records.py
@tests/integration/test_database_migrations.py

只使用项目受控execution adapter；不得调用stock `gsd-plan-phase`、`gsd-execute-phase`、`gsd-verify-work`、lifecycle mutation或`gsd-ship`。Graphify按用户指令保持闲置：不读取、不运行、不更新，也不作为gate。
</execution_context>

<interfaces>

## 1. Exact physical pair sets

v1 set恰为17项：

```python
_V1_CODE_VERSION_PAIRS = tuple(
    (code, f"{code}.p0.v1")
    for code in (
        "agent_run_record",
        "context_manifest_record",
        "conversation_record",
        "conversation_task_link_record",
        "eval_execution_failure_record",
        "eval_result_record",
        "gate_decision_record",
        "input_binding_record",
        "message_record",
        "model_visible_toolset_artifact",
        "observation_record",
        "request_understanding_record",
        "request_unit_record",
        "run_task_link_record",
        "task_record",
        "tool_call_record",
        "trace_event_record",
    )
)
```

expanded set只增加：

```python
(
    "request_understanding_record",
    "request_understanding_record.p0.v2",
)
```

pair比较是exact string equality；禁止alias、prefix、regex family、latest/default、try-other-version、version inference或把schema version跨record code复用。排序只为deterministic SQL/metadata，不赋予active-version优先级。

## 2. SQLAlchemy metadata

`src/mini_agent/infrastructure/persistence/models.py`：

- 保留 `_RECORD_CODES = tuple(code.value for code in P0RecordCode)`，结果仍恰为17。
- 把 `_CODE_VERSION_PAIRS` 的source改为：

```python
_CODE_VERSION_PAIRS = tuple(
    sorted(
        (code.value, schema_version)
        for code, schema_version in P0_RECORD_SCHEMA_VERSION_CATALOG
    )
)
```

- import `P0_RECORD_SCHEMA_VERSION_CATALOG`，不再用active-only `P0_PERSISTENCE_REGISTRY`生成physical pair set。
- `_CODE_VERSION_CHECK` 与 `P0RecordModel.__table_args__` 名称/结构保持不变；只改变其pair值为exact 18-entry catalog key set。
- catalog iteration order不是合同，必须显式排序；不得读取spec value推断key。

五个pre-existing top-level class/function definitions `_sql_values`、`Base`、`P0RecordModel`、`P0RecordReferenceModel`、`MockOrderModel` 的source segment与AST保持不变。允许delta仅为Application import和`_CODE_VERSION_PAIRS` assignment；其他module constants不得改写。

## 3. Alembic revision

新增唯一文件：

```text
alembic/versions/20260728_0003_request_understanding_v2_expand.py
```

revision contract：

```python
revision = "20260728_0003"
down_revision = "20260727_0002"
branch_labels = None
depends_on = None
```

这是 `INFERRED / INFRASTRUCTURE PLAN RULING`：canonical owner冻结了stage/pair，但未预先指定revision ID；本名称沿用现有date-sequence convention并与execution map exact path一致。

历史migration必须self-contained：

- 在文件内literal定义17-pair v1 set与18-pair expanded set；不得import`mini_agent.*`、current catalog/model/codec。
- condition builder只接受文件内常量，生成fully parenthesized exact OR expression。
- `upgrade()`在Alembic transaction中drop同名旧check，再create同名expanded check；PostgreSQL transactional DDL保证失败整体回滚。
- 不新增/删除/重命名table、column、index、FK、unique/check（除同名code/version body）、sequence或extension。
- 不执行`UPDATE`、`DELETE`、payload read/parse、backfill、re-encode或data reconstruction。

## 4. Fail-closed downgrade

`downgrade()`必须：

1. 在migration transaction内对`p0_records`取得阻止并发writer改变检查结果的table lock。
2. 运行只返回boolean的bounded `SELECT EXISTS`，predicate恰为RU code + v2 version；不读取payload、logical identity、owner、row count或PII。
3. 存在RU-v2 row时，在任何constraint DDL前抛固定无caller-controlled值的bounded error；不得删除、改写、隔离、自动转换或fallback。
4. 无RU-v2 row时原子drop expanded check并恢复原17-pair同名check。

失败downgrade的可观察保证：

- Alembic version仍是`20260728_0003`；
- RU-v2 row byte/identity不变；
- expanded 18-pair constraint仍有效，另一个exact v2 physical probe仍可插入；
- exception/日志不包含row identity、payload、owner、count或SQL parameter值。

真实环境若已有v2 row，rollback必须停止并签发owner-approved reverse data migration或使用经验证备份恢复；本Packet禁止silent delete。

## 5. Physical nonclaims

physical direct-insert tests只探测DB constraint，不能称为codec-valid durable record。01-07P不验证或实现：

- outer/inner schema、record identity、logical child、safe projection、Message provenance或owner graph；
- `P0_PERSISTENCE_REGISTRY` active switch、versioned codec调用、PostgreSQL Adapter/read/write path；
- v1→v2 data migration、backfill/reconstruction、current-v1 isolation；
- Runtime/Provider/Eval/Composition Root、授权、Observation/Evidence、recovery/readiness。

</interfaces>

<packet_contract>
repository: `https://github.com/weijie567/mini-agent`
remote: `origin`
head_branch: `codex/e2e01-01-ru-v2-physical-expand`
base_branch: `integration/e2e01-thin`
base_sha: `294ada386ec160ec2a48fc8883b5a38f1880e4ba`
base_tree: `97b0928100edae965004338d52ce87dff7325fd1`
input_barrier: `B_FE_EXPAND`
output_barrier: `B_IP / ONLY AFTER 01-07I AND 01-07P BOTH REVIEWED-SERIAL-MERGED`
worktree_id: `e2e01-01-ru-v2-physical-expand`
writer: `Infrastructure migration-chain sole writer with owned test, supervised by /root Integrator`
agent_role: `infra-engineer`
active_routing: `false`

planning_and_owner_provenance:

- exact 01-07I Plan merge `24451c7103b553023546549aebdeb3e3421cbe8a`，blob `15e114001cb81fdcf457f12a5156c9ed00085cbd`
- exact execution map/status commit before I Plan `dcbba968cb1368d0a5a82e0d0203e4bbb6fc4c63`，multi-agent plan blob `243862e72ab72f885279eda5b1a89548fa2a1159`
- exact `B_FE_EXPAND` merge `294ada386ec160ec2a48fc8883b5a38f1880e4ba`，tree `97b0928100edae965004338d52ce87dff7325fd1`
- Thin Slice owner blob `233a9c06ef6ef9300bef1a0e4f86659b0ec26a13`
- Memory owner blob `5c27ba3bd2ed74e5164bdd0812133041ed96f242`
- 01-07E catalog source blob `1e085e066847b69fd4f49e6b8ce6c732391644b3`
- official 01-07P Plan merge SHA/blob由Integrator在Plan PR reviewed merge后捕获；planning merge不替换feature base `B_FE_EXPAND`

owned_files_at_base:

- `alembic/versions/20260728_0003_request_understanding_v2_expand.py` = `NOT_FOUND / MUST BE NEW REGULAR FILE`
- `src/mini_agent/infrastructure/persistence/models.py` = `a11b31ea8137dcf04b69dccf42489d6f02adeccd`
- `tests/integration/test_database_migrations.py` = `38ef3db1a1ee6cb7131a97f88bce89d9c88892ba`

protected_chain_at_base:

- `alembic/versions/20260726_0001_initial_persistence.py` = `46ad6e4cf5d808fe9db60cd3d9c29f95f9c612dc`
- `alembic/versions/20260727_0002_p0_records.py` = `4e4c214a6f95dcf87997f88ab5478b18ed46d488`
- `alembic/env.py` = `4c32b2cd0603bb04246cce762a34ab6faf52ed1a`
- 上述三文件必须保持exact blob；migration chain只能线性追加0003，不能edit historical revision/env。

allowlist:

- `alembic/versions/20260728_0003_request_understanding_v2_expand.py`
- `src/mini_agent/infrastructure/persistence/models.py`
- `tests/integration/test_database_migrations.py`

forbidden_files: `ALL REPOSITORY FILES OUTSIDE THE THREE-FILE ALLOWLIST`，尤其包括01-07I四文件、`src/mini_agent/application/persistence.py`、`src/mini_agent/infrastructure/persistence/postgres.py`、`tests/conftest.py`、`alembic/env.py`、既有0001/0002 revisions、`compose.yaml`、`pyproject.toml`、`uv.lock`、`docs/**`、`.planning/**`、`evals/**`、`AGENTS.md`、`PROJECT_DIRECTION.md`、`graphify-out/**`。

01-07I overlap gate:

```text
01-07I owned ∩ 01-07P owned = []
count = 0
```

commit_contract:

1. RED `test(01-07P): define request understanding v2 physical expand`：只改`tests/integration/test_database_migrations.py`；migration target仍NOT_FOUND且models blob仍等于base。focused命令只因0003/18-pair/downgrade合同缺失失败。
2. GREEN `feat(01-07P): expand request understanding v2 physical schema`：只新增0003并修改models；不重写RED。
3. 正常feature history相对B_FE_EXPAND恰为上述两个commit。Finding修复只能追加`fix(01-07P): ...`，不得amend/rebase/force-push已审历史。

integration_order_ruling:

- I/P实现可并行，但Integrator先完成01-07I canonical full gate、exact review、latest overlay与serial merge。
- 01-07P开发期只运行disposable `db-test` namespace focused/regression；不得在I gate完成前把共享dev DB升级到0003。
- I merged后，先在P exact feature head运行canonical dev migration/full gate并完成独立review；再基于latest integration创建P overlay，重复canonical full gate与final review后第二个串行merge。该merge的exact SHA/tree才可命名`B_IP`。
- 这是共享canonical DB revision不可被旧I worktree识别所需的execution scheduling，不改变I/P共同feature base或symbolic map。

contract_changes: `YES / PHYSICAL ADDITIVE DEPENDENCY_EXPAND ONLY` — 同名code/version check从17→18 pair；无logical/active/data/reader/writer contract switch。
security_impact: `YES` — exact pair admission、catalog/DDL parity、unsupported pair拒绝、无silent-data-loss downgrade与bounded diagnostics；不改变身份/授权。
eval_impact: `YES / MIGRATION INTEGRATION CONTRACT ONLY` — 增加future E2E01-01/04 physical dependency证据；不改Dataset、Grader、Result、threshold、Case lifecycle、Trajectory/E2E状态。
new_dependencies: `NONE`
graphify_disposition: `DISABLED_BY_USER / NOT_RUN / NOT_A_GATE`
rollback: 合并前关闭PR；合并后若无v2 row且active switch未开始，先阻断downstream/writer、逐环境downgrade到0002，再普通revert PR撤销P；若存在v2 row，downgrade故意BLOCK，必须另签reverse data migration或verified backup restore。禁止delete/rewrite/fallback/reset/force-push/readiness claim。

handoff_format: branch、exact feature base/Plan/head/commits/tree、owned/protected base/head blobs、RED/GREEN输出、18-pair与schema-delta矩阵、downgrade atomicity证据、focused/database/full gate、allowlist/commit containment、feature/overlay review、nonclaims、风险、B_IP merge SHA/tree与rollback。
</packet_contract>

<threat_model>

| threat_id | category | boundary | disposition | mitigation |
|---|---|---|---|---|
| `RUP-S01` | Spoofing | physical pair/row → owner或active authority | `MITIGATE / BLOCK` | exact check只admit representation；不授权、不路由、不证明payload |
| `RUP-T01` | Tampering | catalog/model/migration → DDL drift | `MITIGATE / BLOCK` | 18-pair exact parity、self-contained migration、17 code/only-RU-dual tests |
| `RUP-R01` | Repudiation | revision/RED-GREEN/review → evidence | `MITIGATE / BLOCK` | exact base/blobs、linear chain、atomic commits、upgrade/downgrade matrix、exact-head review |
| `RUP-I01` | Information Disclosure | downgrade failure → row/owner/payload | `MITIGATE / BLOCK` | boolean EXISTS、fixed error、no identity/count/payload diagnostic |
| `RUP-D01` | Denial of Service | concurrent writer/constraint replacement | `MITIGATE / BOUNDED` | transactional table lock、single check replacement、rollback on failure |
| `RUP-E01` | Elevation of Privilege | physical coexistence → multi-version readiness | `MITIGATE / BLOCK` | explicit nonclaims、no Adapter/registry/consumer/data change |

</threat_model>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: RED — freeze exact 18-pair schema and fail-closed migration cycle</name>
  <files>tests/integration/test_database_migrations.py</files>
  <action>只改owned integration test。冻结head=0003、17 code/18 pair/only-RU-dual、metadata/DB parity、已有v1 row无损0002→0003、全部18 pair accept、non-RU-v2/RU-v3/unknown-code reject、无v2 row的0003→0002→0003 cycle、v2 row存在时downgrade fail-closed与atomicity、head idempotence和除constraint body外零schema delta。Direct insert显式命名为physical probe，不调用codec。只使用disposable db-test namespace；取得真实RED并提交。</action>
  <verify>
    <automated>uv run pytest tests/integration/test_database_migrations.py -x -q</automated>
    RED必须非零且只指向缺少0003/18-pair/downgrade合同；models、既有migration/env保持base blob。
  </verify>
  <done>physical behavior先于实现固定，RED原因正确可复现。</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: GREEN — append 0003 and align SQLAlchemy physical metadata</name>
  <files>alembic/versions/20260728_0003_request_understanding_v2_expand.py, src/mini_agent/infrastructure/persistence/models.py</files>
  <action>新增self-contained 0003并把models pair source切到sorted catalog keys；不修改其他schema/Adapter/codec。先运行focused与database regression；共享dev `uv run alembic upgrade head`和full gate必须等待Integrator确认I gate/merge完成，随后在P exact feature head补齐canonical full gate再进入exact review。GREEN提交后运行scope/protected-chain/schema-delta gates。</action>
  <verify>
    <automated>uv run pytest tests/integration/test_database_migrations.py -x -q
uv run pytest tests/integration/test_database_migrations.py tests/integration/test_postgres_record_adapters.py tests/integration/test_postgres_atomicity.py tests/integration/test_postgres_recovery.py tests/integration/test_postgres_get_order.py -x</automated>
  </verify>
  <done>01-07P feature可进入等待队列；未完成I review/merge与P latest-overlay/full review前不形成B_IP。</done>
</task>

</tasks>

<verification>

Feature writer必须先证明exact base/scope：

```bash
set -euo pipefail

base_sha=294ada386ec160ec2a48fc8883b5a38f1880e4ba
base_tree=97b0928100edae965004338d52ce87dff7325fd1
expected_branch=codex/e2e01-01-ru-v2-physical-expand

test "$(git branch --show-current)" = "$expected_branch"
test "$(git rev-parse "${base_sha}^{tree}")" = "$base_tree"
test "$(git merge-base HEAD "$base_sha")" = "$base_sha"
test "$(git rev-parse "${base_sha}:src/mini_agent/infrastructure/persistence/models.py")" = a11b31ea8137dcf04b69dccf42489d6f02adeccd
test "$(git rev-parse "${base_sha}:tests/integration/test_database_migrations.py")" = 38ef3db1a1ee6cb7131a97f88bce89d9c88892ba
test ! -e alembic/versions/20260728_0003_request_understanding_v2_expand.py || \
  test "$(git ls-tree -r --name-only "$base_sha" -- alembic/versions/20260728_0003_request_understanding_v2_expand.py)" = ""
test "$(git rev-parse "${base_sha}:alembic/versions/20260726_0001_initial_persistence.py")" = 46ad6e4cf5d808fe9db60cd3d9c29f95f9c612dc
test "$(git rev-parse "${base_sha}:alembic/versions/20260727_0002_p0_records.py")" = 4e4c214a6f95dcf87997f88ab5478b18ed46d488
test "$(git rev-parse "${base_sha}:alembic/env.py")" = 4c32b2cd0603bb04246cce762a34ab6faf52ed1a

expected_files=$'alembic/versions/20260728_0003_request_understanding_v2_expand.py\nsrc/mini_agent/infrastructure/persistence/models.py\ntests/integration/test_database_migrations.py'
test "$(git diff --name-only "${base_sha}...HEAD" | LC_ALL=C sort)" = "$expected_files"
git diff --check "${base_sha}...HEAD"

test "$(git log --reverse --format=%s "${base_sha}..HEAD" | sed -n '1p')" = \
  "test(01-07P): define request understanding v2 physical expand"
test "$(git log --reverse --format=%s "${base_sha}..HEAD" | sed -n '2p')" = \
  "feat(01-07P): expand request understanding v2 physical schema"
test "$(git log --reverse --format=%s "${base_sha}..HEAD" | sed -n '3,$p' | awk '!/^fix\\(01-07P\\): / {bad++} END {print bad+0}')" -eq 0
```

Focused/database gates：

```bash
uv run pytest tests/integration/test_database_migrations.py -x -q
uv run pytest \
  tests/integration/test_database_migrations.py \
  tests/integration/test_postgres_record_adapters.py \
  tests/integration/test_postgres_atomicity.py \
  tests/integration/test_postgres_recovery.py \
  tests/integration/test_postgres_get_order.py \
  -x
uv run python -m compileall -q src tests
```

Migration tests必须机械证明：

- Alembic single head=`20260728_0003`，linear down revision=`20260727_0002`；
- exact 17 code / 18 pair / only RU dual；
- 0002已有v1 row upgrade后logical identity/envelope/stored fields byte/value不变；
- 所有18 valid pair接受，unsupported cross-pair拒绝；
- table/column/index/FK/unique/check-name set与0002相同，只有`ck_p0_records_code_version_closed` body改变；
- 无v2 row downgrade/upgrade可逆；有v2 row downgrade失败后revision/row/expanded constraint原子保留。

Integrator在I reviewed merge后，先于P exact-head review运行共享canonical gate：

```bash
uv sync --all-groups
docker compose up --wait -d db
docker compose --profile test up --wait -d db-test
uv run alembic upgrade head
uv run pytest
```

通过上述gate后对P exact head做独立review；随后基于latest integration（已含reviewed I）创建P overlay，重复scope、migration matrix、database regression与canonical full gate，再做final overlay review。P第二个串行merge后：

```bash
git diff --name-only \
  294ada386ec160ec2a48fc8883b5a38f1880e4ba...B_IP \
  -- \
  alembic src tests
```

必须恰为I四文件+P三文件；source/test/infra之外的planning/status commits不计入feature ownership。记录exact `B_IP` SHA/tree后才可签发01-07K/01-07L。

</verification>

<success_criteria>

1. RED/GREEN提交、scope与migration evidence可复现。
2. PostgreSQL/metadata恰为17 code / 18 exact pairs，只有RU dual；其他schema零delta。
3. upgrade保留v1 data；downgrade遇v2 data原子fail closed且无PII诊断。
4. 三文件allowlist外零改动；active registry/codec/Adapter/Runtime/Eval均未切换。
5. I/P独立实现、串行review/merge；P latest-overlay final PASS后才形成B_IP。

</success_criteria>
