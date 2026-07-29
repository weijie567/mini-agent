---
phase: 01-cycle-1-e2e-01
plan: 07T-PHYSICAL-HANDOFF
type: remediation
wave: 30-remediation
depends_on:
  - 01-07X
files_modified:
  - src/mini_agent/infrastructure/persistence/models.py
  - tests/integration/test_database_migrations.py
autonomous: true
requirements:
  - E2E01-01
  - E2E01-04
user_setup: []
must_haves:
  truths:
    - "SQLAlchemy physical p0_records code/version check constraint继续精确允许18个pair：16个非RU v1、RU-v1与RU-v2；其来源不再是Application executable catalog。"
    - "Application active registry保持17个current pair；Application catalog在handoff head可仍为expanded 18-pair，并可由后续01-07T合法收敛为active 17-pair而不改变Infrastructure metadata。"
    - "Migration 0003及其upgrade/downgrade、physical-v1 preservation与v2 downgrade block合同完全不变；本remediation不新增migration。"
    - "physical-v1 admissibility不提供v1 DTO/codec/reader、fallback、backfill、migration或readiness；01-07R继续inactive。"
    - "remediation reviewed merge只形成B_T_PHYSICAL_HANDOFF并替换01-07T acceptance base，不增加42 denominator、不推进Case lifecycle。"
  artifacts:
    - "Infrastructure-owned immutable 18-pair physical allowset与SQLAlchemy check constraint。"
    - "migration integration staged-handoff oracle：active17 ⊆ executable catalog ⊆ physical18，唯一可选差值为RU-v1。"
  key_links:
    - "B_X → 01-07T-PHYSICAL-HANDOFF → B_T_PHYSICAL_HANDOFF。"
    - "P0RecordModel metadata → Infrastructure physical18 allowset；不再依赖P0_RECORD_SCHEMA_VERSION_CATALOG。"
    - "B_T_PHYSICAL_HANDOFF → reissued 01-07T → B_T。"
---

# Phase 1 Plan 01-07T-PHYSICAL-HANDOFF｜Physical catalog ownership remediation

> **ISSUED REMEDIATION TASK PACKET / IMPLEMENTATION NOT STARTED**
> 本Packet只解耦Infrastructure physical allowset与Application executable catalog。Plan、RED/GREEN feature head或execution-owner merge均不形成`B_T_PHYSICAL_HANDOFF`；只有feature从exact `B_X`完成独立review、latest-integration replay、串行merge与post-merge gate后才可命名该barrier。

> **DERIVED / NON_NORMATIVE**
> Physical version admissibility服从Thin Slice与Memory owner；execution拆分服从`p0-ru-v2-execution-map-r4`。本Plan不建立第二套codec、migration或readiness合同。Graphify按用户指令保持闲置。

<objective>
把SQLAlchemy `p0_records` physical code/version check constraint的18-pair来源从Application `P0_RECORD_SCHEMA_VERSION_CATALOG`解耦为Infrastructure-owned exact physical allowset，使后续01-07T可把Application executable catalog从18-pair收敛为17-pair current-only，而不造成ORM metadata与既有migration 0003数据库约束漂移。

Purpose: 01-07T初版Plan的独立review发现，`models.py`直接导入Application catalog生成`_CODE_VERSION_PAIRS`，migration test又要求两者都等于physical 18-pair。T的两文件Application ownership若直接删除RU-v1 catalog pair，会把SQLAlchemy metadata隐式改成17-pair，但数据库constraint仍为18-pair。该跨owner耦合必须先由Infrastructure owner关闭。

Output: 一个双文件remediation feature。RED先冻结“models不导入Application catalog + physical18/current17 staged关系”；GREEN只把models切到exact physical allowset。0003、Application、Core与codec行为均不修改。
</objective>

<preflight_evidence>

- `CONFIRMED`：remediation feature input必须是exact `B_X = 9e8c70db39786b35c1ebea5070a32a1bc36e0df7`，tree `4b01798be73c15ae0b3eda42483078cbd7cdf7dc`。
- `CONFIRMED`：01-07T初版Plan exact `fabc546e21b9001ef7327beb43f9a763ce9b8543`经独立review为`FAIL P0/P1/P2/P3 = 0/1/0/0`并关闭draft PR #137；未修改产品代码。
- `CONFIRMED`：execution-owner r4 reviewed head `d1376d06438b1a18c4b51450b972ed5ba9da2ab1`、tree `83160cfc35134536c4b33c45957cdc1fef41d926`以`PASS 0/0/0/0`通过并由PR #138 merge为`90cea0c40a507b4c86e90a49f836a7355b40abcc`。该merge只授权acceptance route，不替换feature base。
- `CONFIRMED`：owned base blobs为：
  - `src/mini_agent/infrastructure/persistence/models.py = 892e8db7523ce1cd6c1032a9a6ad7d9d656f50fa`
  - `tests/integration/test_database_migrations.py = 6ad203a3337609621b60ac662677eb96cc862339`
- `CONFIRMED`：forbidden migration blob `alembic/versions/20260728_0003_request_understanding_v2_expand.py = bcd7dd85b4c5b82c764942ff0faf019d9e4744d0`。
- `CONFIRMED`：B_X migration focused baseline为`48 passed`；B_X canonical full为`1974 passed, 1 deselected, 12 warnings`。
- `CONFIRMED`：`models.py`只通过`P0_RECORD_SCHEMA_VERSION_CATALOG`构造`_CODE_VERSION_PAIRS`与`ck_p0_records_code_version_closed`；没有第三个Production consumer持有该catalog-to-physical映射。
- `CONFIRMED`：migration 0003自身用literal `_EXPANDED_CODE_VERSION_PAIRS`拥有18-pair数据库约束，包含RU-v1/v2；其downgrade只有在无v2 row时才恢复17-v1约束。
- `CONFIRMED`：Application active registry已经是17 current pairs；expanded catalog相对active唯一多出的pair是`(request_understanding_record, request_understanding_record.p0.v1)`。
- `OPEN / NONCLAIM`：remediation不证明数据库存在或不存在historical v1 row，不扫描或迁移数据，不激活01-07R。

</preflight_evidence>

<execution_context>
@AGENTS.md
@.planning/GOVERNANCE.md
@docs/architecture/memory-design-reference.md
@docs/implementation/e2e01-thin-slice-implementation-spec.md
@docs/implementation/e2e01-thin-slice-multi-agent-plan.md
@src/mini_agent/infrastructure/persistence/models.py
@tests/integration/test_database_migrations.py
@alembic/versions/20260728_0003_request_understanding_v2_expand.py

只使用项目受控execution adapter；不得调用stock GSD lifecycle命令。
</execution_context>

<interfaces>

## 1. Exact feature identity and ownership

repository: `/Users/ming/projects/mini-agent`

remote: `https://github.com/weijie567/mini-agent.git`

feature_branch: `codex/e2e01-01-ru-physical-catalog-handoff`

feature_worktree: `e2e01-01-ru-physical-catalog-handoff`

writer: `/root Integrator / Infrastructure physical catalog two-file sole writer`

pull_request_base: `integration/e2e01-thin`

base_sha: `9e8c70db39786b35c1ebea5070a32a1bc36e0df7`

base_tree: `4b01798be73c15ae0b3eda42483078cbd7cdf7dc`

input_barrier: `B_X`

output_barrier: `B_T_PHYSICAL_HANDOFF / ONLY AFTER REVIEWED FEATURE MERGE AND POST-MERGE GATES`

owned_files_at_base:

- `src/mini_agent/infrastructure/persistence/models.py = 892e8db7523ce1cd6c1032a9a6ad7d9d656f50fa`
- `tests/integration/test_database_migrations.py = 6ad203a3337609621b60ac662677eb96cc862339`

allowlist: exact two paths above.

forbidden_files: `ALL REPOSITORY FILES OUTSIDE THE TWO-FILE ALLOWLIST`，尤其包括`alembic/**`、`src/mini_agent/application/**`、other `src/mini_agent/infrastructure/**`、`src/mini_agent/core/**`、other `tests/**`、`pyproject.toml`、`uv.lock`、`compose.yaml`、`docs/**`、`.planning/**`、`AGENTS.md`、`graphify-out/**`。

Plan merge只记录签发。feature必须从原exact `B_X`创建，不得使用PR #138 execution-owner merge、本Plan merge或status merge作为base。

## 2. Exact physical ownership handoff

`models.py`必须停止导入`P0_RECORD_SCHEMA_VERSION_CATALOG`；可继续导入`P0RecordCode`用于17-code closed set。

Infrastructure source必须定义一个不可变、无runtime mutation的exact physical pair集合，恰为migration 0003 `_EXPANDED_CODE_VERSION_PAIRS`：

- 17个`<record_code>.p0.v1` pair；
- 额外唯一`request_understanding_record.p0.v2` pair；
- 总数18、pair唯一；
- `_CODE_VERSION_PAIRS`保持canonical sorted tuple；
- `_CODE_VERSION_CHECK`与`ck_p0_records_code_version_closed`继续由该18-pair集合生成。

不得从Application catalog、active registry、model type、payload、环境变量、config、数据库反射或migration runtime动态推断physical allowset。不得把migration模块import进Production；physical literal由Infrastructure owner独立持有，并由migration test逐项对照0003。

## 3. Staged Application/physical relationship oracle

`test_database_migrations.py`必须把旧的“physical pairs == Application catalog pairs == expanded18”改为精确staged handoff：

```text
active_pairs = 17 current pairs
physical_pairs = expanded18
catalog_pairs ∈ {active_pairs, physical_pairs}
physical_pairs - active_pairs = {RU-v1}
physical_pairs - catalog_pairs ∈ {∅, {RU-v1}}
```

在remediation head，catalog仍为physical18；在后续T head，catalog应为active17。除此之外的任何missing/extra pair都失败。

test还必须AST证明`models.py`没有import/name/attribute/dynamic lookup Application catalog，且physical exact tuple、SQLAlchemy check text、live database constraint与0003 literal仍一致。

## 4. Preserved physical and security boundary

以下保持不变：

- migration revision/down_revision、upgrade/downgrade source与downgrade block message；
- clean upgrade、0002→0003、physical pair acceptance/rejection、v1 row preservation、v2 row downgrade block；
- record code、index、FK、owner/projection columns与其他check constraints；
- physical RU-v1/v2 row admissibility。

physical allowance只防止数据库层在staged cutover期间拒绝历史row，不授权Application decode，不提供RU-v1 Core DTO、codec、Port或writer，不允许read-time fallback/rewrite/backfill/delete，不代表01-07R或readiness。

## 5. Commit, review and barrier protocol

1. RED commit只修改migration integration test，新增no-import与staged set oracle；B_X source应仅因仍import Application catalog而失败。
2. GREEN commit只修改`models.py`，把physical pair来源切到Infrastructure exact18；不得amend/rebase RED。
3. findings只用append-only allowlist fix commit关闭。
4. exact-head review验证双文件、linear history、B_X parent、0003 blob不变、Application/Core/other Infra不变。
5. PASS后在包含PR #138与Plan merge的latest integration做throwaway overlay，证明docs-only delta未改变owned blobs。
6. reviewed feature串行merge与post-merge canonical gates后才记录`B_T_PHYSICAL_HANDOFF`；然后重新签发T，T base必须是该exact barrier。

</interfaces>

<tasks>

<task type="auto">
  <name>Task 1: RED — 冻结physical18与Application catalog解耦</name>
  <files>tests/integration/test_database_migrations.py</files>
  <action>
    将metadata/catalog equality oracle改为physical18/current17 staged oracle，增加models source AST no-import guard。只提交test并记录B_X source因直接导入Application catalog而RED。
  </action>
  <verify>
    <automated>uv run pytest tests/integration/test_database_migrations.py -q</automated>
  </verify>
  <done>RED精确指向cross-owner import，不要求修改migration或Application。</done>
</task>

<task type="auto">
  <name>Task 2: GREEN — Infrastructure自有exact physical allowset</name>
  <files>src/mini_agent/infrastructure/persistence/models.py</files>
  <action>
    删除Application catalog import，定义与0003逐项一致的exact18 physical pair集合并继续生成同一sorted constraint；不改变table/column/index/FK/其他constraint。
  </action>
  <verify>
    <automated>uv run pytest tests/integration/test_database_migrations.py -q</automated>
  </verify>
  <done>48项migration gate及新增handoff oracle通过，physical metadata不再随Application catalog变化。</done>
</task>

<task type="auto">
  <name>Task 3: exact-head review、overlay与B_T_PHYSICAL_HANDOFF</name>
  <files>exact two-file allowlist</files>
  <action>
    运行scope/commit containment、focused、database/integration/full、independent review与latest overlay；串行merge后复跑canonical gates并记录barrier。不得提前实现T。
  </action>
  <verify>
    <automated>uv run pytest</automated>
  </verify>
  <done>reviewed remediation在共同post-merge tree形成B_T_PHYSICAL_HANDOFF。</done>
</task>

</tasks>

<verification>

```bash
git diff --check
uv run pytest tests/integration/test_database_migrations.py -q
uv run pytest tests/integration/test_postgres_record_adapters.py tests/integration/test_postgres_v2_request_understanding_writes.py -q
uv run pytest tests/integration -q
uv sync --all-groups
docker compose up --wait -d db
docker compose --profile test up --wait -d db-test
uv run alembic upgrade head
uv run pytest
```

额外机械检查：

- first feature commit parent exact B_X，linear/no merge；
- changed files exact双文件；
- `models.py`不引用Application catalog；
- physical pair exact18、active pair exact17、catalog只允许18→17两状态；
- 0003 blob保持`bcd7dd85b4c5b82c764942ff0faf019d9e4744d0`；
- Application、Core、其他Infrastructure blobs相对B_X不变；
- independent review `P0/P1/P2/P3 = 0/0/0/0`；
- overlay与reviewed patch一致；
- post-merge full通过后才记录barrier。

</verification>

<contract_changes>

`SCOPED OWNERSHIP DECOUPLING`：Infrastructure physical18 allowset不再由Application executable catalog派生。Application/codec语义不变，migration physical contract不变，42 denominator不变。

</contract_changes>

<security_impact>

`BOUNDARY PRESERVING`：继续允许historical physical RU-v1 row存在，但不提供消费、授权、fallback或迁移能力。错误与约束不得暴露payload/PII。

</security_impact>

<eval_impact>

`INTEGRATION ORACLE ONLY`：更新migration integration ownership oracle；不修改Dataset、Grader、Trajectory/E2E Result或Case lifecycle。

</eval_impact>

<rollback>

Feature未merge时关闭PR。合并后、T未形成时普通revert handoff merge并复跑migration/full；不得reset/force。

若已有下游barrier，必须按`V → W → T → PHYSICAL-HANDOFF`的实际依赖逆序逐项普通revert，并在每一步复跑对应Core/Application/codec focused、migration与full gate；不得在W/V仍依赖T时先撤T，也不得reset/force。physical数据未被本Packet修改。

</rollback>

<handoff>

交接必须使用以下显式模板：

```text
Task Packet: 01-07T-PHYSICAL-HANDOFF
Base SHA / tree:
Branch / Worktree:
RED commit and expected failure:
GREEN/fix commits:
Reviewed exact head / tree:
Actual changed files:
Commands and exact results:
Allowlist / containment result:
0003 preserved blob:
Contract changes:
Security impact:
Eval impact:
Latest integration overlay evidence:
PR / merge commit:
Post-merge B_T_PHYSICAL_HANDOFF SHA / tree:
Unresolved risks:
Rollback:
Recommended next step:
```

Agent完成不等于`B_T_PHYSICAL_HANDOFF`、`B_T`、`B_RU_V2_CONTRACT`或产品ready。

</handoff>

<cross_file_impact>

- execution-owner r4 PR #138拥有handoff route与双文件scope。
- closed PR #137保留blocked T Plan证据，不得复用。
- 0003历史migration正文不修改。
- T必须在handoff merge后从新exact barrier重新签发。
- Graphify保持闲置。

</cross_file_impact>
