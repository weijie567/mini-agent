---
phase: 01-cycle-1-e2e-01
plan: 07Q
type: tdd
wave: 24
depends_on:
  - 01-07M
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
    - "01-07Q 只执行 ACTIVE_SWITCH 的 Application persistence codec mapping：P0_PERSISTENCE_REGISTRY 保持 immutable 17-code one-current-spec mapping，但 request_understanding_record 的 current spec 从 exact v1 切到 exact v2，其余16项仍为各自v1。"
    - "P0_RECORD_SCHEMA_VERSION_CATALOG 继续恰为18个exact pair：17个v1与唯一RU-v2；RU-v1仍可由显式exact-version compatibility路径访问，但不再是public active mapping。"
    - "encode_persistence_record / decode_persistence_record 的既有v1 signature与行为在01-07T前保持；它们必须固定使用private immutable v1 registry，不能依据active mapping、record type、payload或catalog顺序推断版本。"
    - "encode_persistence_record_versioned / decode_persistence_record_versioned 继续要求caller显式提供record_code与schema_version，允许catalog中的exact v1/v2 pair，禁止default/latest、try-other-version、alias、read-time rewrite或fallback。"
    - "01-07K exact-Run reader对RU只接受v2并fail closed拒绝v1，构成Q所需current-v1 isolation gate；Q不扫描、迁移、回填、删除或重写物理v1 rows。"
    - "01-07Q不修改Runtime、Infrastructure、Provider/Eval、Application records/ports、Core、Composition Root、migration、Case lifecycle或readiness；B_Q只解锁01-07J。"
  artifacts:
    - "src/mini_agent/application/persistence.py 中的17-code active registry、隔离的private v1 compatibility registry与不变的18-pair exact catalog。"
    - "tests/component/application/test_persistence_contract.py 中的active/current、legacy compatibility、exact-pair、non-inference与boundary matrix。"
  key_links:
    - "Thin Slice cutover manifest ACTIVE_SWITCH + current-v1 isolation → Q public active mapping只选择RU-v2。"
    - "01-07E exact-version catalog/API → Q复用18-pair catalog，不创建第二个catalog或新public codec API。"
    - "01-07K strict reader → RU-v1不能进入authoritative exact-Run evidence path。"
    - "P0-RU-V2-EXECUTION-MAP：B_Q_ORACLE_FIX → 01-07Q → B_Q → 01-07J；B_Q_ORACLE_FIX 是 B_DEPENDENCY_M 的reviewed quality-gate remediation descendant，不新增Packet或改变39分母。"
---

# Phase 1 Plan 01-07Q｜Request Understanding v2 codec active switch

> **ISSUED ACTIVE_SWITCH TASK PACKET / IMPLEMENTATION NOT STARTED**
> 本 Packet 只切换 Application persistence codec 的 public active mapping。Plan签发、Component test或Q feature完成都不表示Runtime consumer、PostgreSQL writer、Composition Root、真实HTTP纵向链、Trajectory / E2E Result或产品ready已经切换。

> **DERIVED / NON_NORMATIVE**
> Thin Slice persistence/cutover语义与execution order仍由active canonical owner拥有。本Plan只把现行`ACTIVE_SWITCH` stage映射为一个精确Application codec Task Packet，不维护第二套版本、Memory、Runtime或Eval合同。

<objective>
以TDD RED→GREEN把`P0_PERSISTENCE_REGISTRY`从17项全v1 current mapping切换为“16项v1 + `request_understanding_record.p0.v2`”，同时保留18-pair exact catalog、显式versioned APIs与隔离的v1 compatibility lane。

Purpose: 让后续01-07J可以从唯一public active mapping观察到RU-v2 current selection，同时保证Q/J之间的串行集成窗口和后续01-07T contract closure之前，既有v1调用方仍可复现且不会被静默推断、升级或fallback。

Output: 一个只改owned Component test的RED commit、一个只改Application persistence codec的GREEN commit，以及一个只修正两个既有category oracle的append-only test fix commit；不创建Summary，不修改共享State、canonical owner或任何Runtime/Infrastructure/Eval consumer。
</objective>

<execution_context>
@AGENTS.md
@.planning/GOVERNANCE.md
@.planning/phases/01-cycle-1-e2e-01/01-07E-PLAN.md
@.planning/phases/01-cycle-1-e2e-01/01-07K-PLAN.md
@.planning/phases/01-cycle-1-e2e-01/01-07L-PLAN.md
@.planning/phases/01-cycle-1-e2e-01/01-07M-PLAN.md
@docs/architecture/intent-design-reference.md
@docs/architecture/memory-design-reference.md
@docs/implementation/e2e01-thin-slice-implementation-spec.md
@docs/implementation/e2e01-thin-slice-multi-agent-plan.md
@src/mini_agent/application/persistence.py
@src/mini_agent/infrastructure/persistence/postgres.py
@tests/component/application/test_persistence_contract.py
@tests/integration/test_database_migrations.py
@tests/integration/test_postgres_record_adapters.py

只使用项目受控execution adapter；不得调用stock `gsd-plan-phase`、`gsd-execute-phase`、`gsd-verify-work`、lifecycle mutation或`gsd-ship`。Graphify按用户指令保持闲置：不读取、不运行、不更新，也不作为gate。
</execution_context>

<interfaces>

## 1. Public active mapping

Q完成后，`P0_PERSISTENCE_REGISTRY`继续是`MappingProxyType`、恰含全部17个`P0RecordCode`且iteration order等于enum order。current selection固定为：

| record code | active schema | active source model |
|---|---|---|
| `request_understanding_record` | `request_understanding_record.p0.v2` | `RequestUnderstandingRecordV2` |
| 其余16个code | 各自`<record_code>.p0.v1` | 既有v1 source model |

不得新增第二个public active registry、runtime `register()`、mutable alias、environment/config switch、latest selector或per-call override。RU active spec必须与18-pair catalog的exact v2 entry为同一对象；其余16项必须与catalog对应v1 entry为同一对象。

Public active mapping只表达codec current selection。它不授权、不中介owner lookup、不证明provenance或owner graph、不自动调用数据库，也不代表Runtime已经使用v2。

## 2. Exact catalog and compatibility isolation

`P0_RECORD_SCHEMA_VERSION_CATALOG`保持01-07E合同：

- exactly 18 immutable `(record_code, schema_version)` entries；
- exactly 17 v1 entries；
- only `request_understanding_record`拥有额外v2 entry；
- RU-v1与RU-v2 spec对象均保留，不能覆盖、alias或由另一个版本生成；
- versioned encode/decode继续只按caller显式exact pair lookup；
- unknown/missing/cross-version仍使用既有最窄bounded `P0PersistenceIntegrityCategory`，不得尝试另一个pair。

为保证01-07T前的v1 contract仍可复现，原17项v1 mapping改为private immutable `_P0_V1_PERSISTENCE_REGISTRY`。它只服务既有`encode_persistence_record`、`decode_persistence_record`及其private helper，不导出新的public API，不被称为current，不接受runtime mutation。

既有`P0_LOGICAL_CHILD_SPECS`继续是v1 compatibility child mapping；RU-v2 child只由既有`_REQUEST_UNDERSTANDING_V2_CHILD_SPEC_CATALOG`按exact pair选择。Q不得把v1 child spec和v2 child spec做union/default，也不得删除v1 surface；删除由01-07T独占。

## 3. Legacy API invariance

以下public signatures必须与B_Q_ORACLE_FIX source exact：

```python
def encode_persistence_record(
    record_code: P0RecordCode,
    record: ContractModel,
    *,
    external_references: tuple[P0RecordReference, ...] = (),
    logical_children: tuple[ContractModel, ...] = (),
) -> P0PersistenceEnvelope: ...

def decode_persistence_record(
    envelope: P0PersistenceEnvelope | Mapping[str, object] | str | bytes,
    *,
    expected_record_code: P0RecordCode,
    correlation_ref: UUID,
) -> DecodedP0PersistenceRecord: ...
```

两者在01-07T前继续严格v1-only：

- RU-v1 encode/decode继续成功并byte-for-byte保持既有envelope语义；
- RU-v2传给legacy encode继续`SOURCE_MODEL_MISMATCH`；
- RU-v2 envelope传给legacy decode继续拒绝，不能因public active mapping变成v2而被接受；
- 所有17项v1 identity/owner/reference/child/version/error projection保持；
- legacy helper只能load `_P0_V1_PERSISTENCE_REGISTRY`，不得load public active mapping后按type/payload回退。

需要把`_reference_for_value`、`_validate_external_references`、`_build_envelope`与`_classify_outer`的registry lookup固定到private v1 mapping。不得复制这些函数、增加boolean mode或通过call-site猜测legacy/active。

## 4. Versioned API invariance

`encode_persistence_record_versioned`与`decode_persistence_record_versioned`的签名、exact pair选择与strict closure保持。`P0_RECORD_SCHEMA_VERSION_CATALOG`是唯一pair lookup source。

`_classify_outer_versioned`的known-version分类必须始终来自完整18-pair catalog，不能因expected spec恰为public active entry而缩窄到17项active mapping。对explicit versioned API，catalog中已知但不等于expected pair的版本一律为`RECORD_SCHEMA_VERSION_MISMATCH`：既包括RU-v2 expected + RU-v1 envelope，也包括RU-v1 expected + RU-v2 envelope。Legacy v1 compatibility lane仍可把RU-v2 envelope分类为`UNKNOWN_RECORD_SCHEMA_VERSION`；这是两个入口的有意边界，不是fallback或category drift。Q必须冻结该directed category matrix。

不得：

- 给versioned API增加default或optional schema version；
- 从`record` type、payload mirror、active registry、catalog iteration order或outer envelope推断caller expected pair；
- catch一次失败后尝试legacy、active或另一个catalog pair；
- rewrite/backfill v1 envelope为v2；
-新增第三个codec API、alias、union model或dynamic import。

## 5. Current-v1 isolation and staged handoff

Q的`requires_current_v1_isolation=true`只由已经reviewed的01-07K exact-Run boundary满足：

- authoritative exact-Run reader显式要求RU `request_understanding_record.p0.v2`；
- RU-v1、unknown/wrong pair、missing version或mixed closure均bounded fail closed；
- reader不调用legacy decoder，不fallback、不重建v2；
- `tests/integration/test_postgres_record_adapters.py`的50-test gate必须在Q exact base与feature head均通过。

Q不声称物理数据库不存在历史v1 row，也不负责迁移或删除。Q/J串行窗口中的legacy API是隔离的compatibility lane，不是public current mapping；`B_Q`不是可独立部署或readiness barrier。01-07J才拥有真实Application Runtime consumer switch；01-07X/01-07T随后分别移除Infra/codec v1 surface。

</interfaces>

<packet_contract>
repository: `https://github.com/weijie567/mini-agent`
remote: `origin`
head_branch: `codex/e2e01-01-ru-v2-codec-active-switch`
base_branch: `integration/e2e01-thin`
base_sha: `83bdd112e016850ced35ef0870b78c55bad30a77`
base_tree: `30594eaa1347f817045a66b9a405d7a38ea24cea`
input_barrier: `B_Q_ORACLE_FIX / REVIEWED QUALITY-GATE REMEDIATION DESCENDANT OF B_DEPENDENCY_M`
output_barrier: `B_Q / ONLY AFTER 01-07Q FEATURE EXACT-HEAD AND LATEST-INTEGRATION OVERLAY REVIEWED-MERGED`
worktree_id: `e2e01-01-ru-v2-codec-active-switch`
writer: `Application persistence codec active-switch sole writer with one owned Component test, supervised by /root Integrator`
agent_role: `runtime-engineer / Application-codec-only`
active_routing: `true / CODEC PUBLIC ACTIVE MAPPING ONLY`
runtime_active_routing: `false / OWNED BY 01-07J`
requires_current_v1_isolation: `true / SATISFIED BY REVIEWED 01-07K EXACT-RUN V2-ONLY READER`

planning_and_owner_provenance:

- original exact `B_DEPENDENCY_M` merge/tree `42fa2ec7ef1a61a2edfd78d69ca4e6a5d32aa1c3` / `d8530e665333a6dbc6f8ea53f909dfc3f909d7e6`
- 01-07M feature [PR #101](https://github.com/weijie567/mini-agent/pull/101) reviewed merge `42fa2ec7ef1a61a2edfd78d69ca4e6a5d32aa1c3`
- 01-07M Plan / shell preflight correction [PR #99](https://github.com/weijie567/mini-agent/pull/99) / [PR #100](https://github.com/weijie567/mini-agent/pull/100)
- migration-oracle remediation [PR #102](https://github.com/weijie567/mini-agent/pull/102) reviewed head/merge/tree `17285fdf3e99a4d41dbb6932d2fcc200e0418f99` / `83bdd112e016850ced35ef0870b78c55bad30a77` / `30594eaa1347f817045a66b9a405d7a38ea24cea`，只改migration integration test并形成exact `B_Q_ORACLE_FIX`
- canonical execution-owner remediation [PR #103](https://github.com/weijie567/mini-agent/pull/103) reviewed head/merge/tree `0ef9ca00be512ce003ad5d4e03063b7c3dc93f59` / `9d223de0752e20146e623f1f4034eabc41e503b2` / `00bceef7f3721fe0d11fb015460079d039f68a4d`
- exact `B_Q_ORACLE_FIX` gate observed before issuance: focused codec `233 passed`、current-v1 isolation Integration `50 passed`、migration Integration `48 passed`、full `1901 passed, 1 deselected, 12 warnings`
- Thin Slice owner blob `233a9c06ef6ef9300bef1a0e4f86659b0ec26a13`
- execution-map base/latest-owner blobs `ea2b5bcac4cb10c928a9e578c1286febb243c7d6` / `c8970d6195a61064fdf3b4186d338fd8cfe8eee8`
- migration-oracle test base blob `6ad203a3337609621b60ac662677eb96cc862339`
- 01-07E / K / L / M Plan blobs `7dd2c9047bebcb9ad29435900ee0030922a5973a` / `45a573332136f5954358e6e077f2222b2e932259` / `7bc14608f3312ef17d92ecbb79e0fb42af2259c1` / `17e2d3465ca62b6822d9332614c4d534ad67d5fb`
- planning branch context head/tree `9d223de0752e20146e623f1f4034eabc41e503b2` / `00bceef7f3721fe0d11fb015460079d039f68a4d`
- official 01-07Q Plan merge SHA/blob由Integrator在Plan PR reviewed merge后捕获；planning或owner merge不替换feature exact base `B_Q_ORACLE_FIX`

owned_files_at_base:

- `src/mini_agent/application/persistence.py` = `1e085e066847b69fd4f49e6b8ce6c732391644b3`
- `tests/component/application/test_persistence_contract.py` = `8a87f0bc8dd7e8a7556d897cc57efce982412e91`

owned_files:

- `src/mini_agent/application/persistence.py`
- `tests/component/application/test_persistence_contract.py`

allowlist:

- `src/mini_agent/application/persistence.py`
- `tests/component/application/test_persistence_contract.py`

forbidden_files: `ALL REPOSITORY FILES OUTSIDE THE TWO-FILE ALLOWLIST`，尤其包括 other `src/mini_agent/application/**`、`src/mini_agent/core/**`、`src/mini_agent/infrastructure/**`、`src/mini_agent/evaluation/**`、other `tests/**`、`evals/**`、`alembic/**`、`tests/conftest.py`、`pyproject.toml`、`uv.lock`、`compose.yaml`、`docs/**`、`.planning/**`、`AGENTS.md`、`PROJECT_DIRECTION.md`、`README.md`、`graphify-out/**`。

canonical_inputs:

- `docs/implementation/e2e01-thin-slice-implementation-spec.md` cutover manifest、§10.1 registry与§10.1.4 exact-version codec合同。
- `docs/implementation/e2e01-thin-slice-multi-agent-plan.md` exact `B_Q_ORACLE_FIX → 01-07Q → B_Q → 01-07J` execution map、preflight remediation lineage与two-file ownership。
- `docs/architecture/memory-design-reference.md` exact-version decode、historical record、owner graph与read-time non-migration边界。
- exact B_Q_ORACLE_FIX中的01-07E catalog/API、01-07K v2-only exact reader、01-07M final Core contract、reviewed migration oracle及owned source/test blobs。

dependencies:

- `01-07E = REVIEWED_MERGED`，18-pair catalog与two explicit versioned APIs存在。
- `01-07K = REVIEWED_MERGED`，authoritative exact-Run reader只接受RU-v2并拒绝v1。
- `01-07L = REVIEWED_MERGED`，Provider/Eval v2 consumers保持non-active。
- `01-07M = REVIEWED_MERGED`，形成exact `B_DEPENDENCY_M = 42fa2ec7ef1a61a2edfd78d69ca4e6a5d32aa1c3`。
- `01-07Q PREFLIGHT ORACLE REMEDIATION = REVIEWED_MERGED`，[PR #102](https://github.com/weijie567/mini-agent/pull/102) 形成exact `B_Q_ORACLE_FIX = 83bdd112e016850ced35ef0870b78c55bad30a77`。
- `01-07Q EXECUTION OWNER = REVIEWED_ALIGNED`，[PR #103](https://github.com/weijie567/mini-agent/pull/103) 保留同一Packet、branch/worktree、two-file ownership与39分母。
- new external/package/schema/migration dependency: `NONE`。

required_checks:

- Gate A exact branch/worktree/base/tree/two-blob/clean-state preflight before RED edit。
- focused baseline `233 passed`；首个RED必须只因public active mapping仍是RU-v1而非零。Source-only active-switch commit后，允许且只允许既有两个category oracle暴露full-catalog与legacy lane的分类差异；append-only test fix后focused必须恢复`233 passed`，test collection count不得变化。
- current-v1 isolation Integration gate `50 passed`。
- reviewed migration-oracle Integration gate `48 passed`；Q不得重新引入Application active-registry ownership或放松physical pair/downgrade/locking检查。
- canonical environment：`uv sync --all-groups`、dev/test PostgreSQL healthy、`uv run alembic upgrade head`。
- canonical full `uv run pytest`，预期仍为`1901 passed, 1 deselected, 12 warnings`。
- active registry / exact catalog / legacy compatibility / versioned exact-pair / error-category / no-inference matrix。
- two-file changed-files、commit-order、commit-scope、no-merge、no-new-import与protected-surface oracle。
- repository-level cross-file impact scan（显式排除`graphify-out/**`）与clean Worktree。
- feature exact-head及latest-integration overlay独立review，unresolved `CRITICAL/HIGH/MEDIUM/LOW = 0/0/0/0`。

commit_protocol:

1. RED `test(01-07Q): require ru v2 active codec`只改owned test。保持233个test collection不变：新增一个non-test `_v1_registry()` helper，把既有v1 registry/projection/parity assertions改为从18-pair catalog显式选择17个v1 spec；更新`test_registry_is_exact_immutable_and_closed`与`test_version_catalog_is_exact_immutable_and_only_ru_is_dual`冻结16-v1+RU-v2 active mapping/object identity；把`test_legacy_codec_remains_v1_only_after_codec_expand`重命名为`test_active_switch_preserves_v1_compatibility_until_contract`并同时冻结active-v2、legacy-v1与explicit v1/v2；把`test_codec_expand_has_no_active_consumer_or_authority_claim`重命名为`test_codec_active_switch_has_no_runtime_or_authority_claim`。Source blob仍等于base；focused只能因public active RU仍为v1失败。
2. GREEN `feat(01-07Q): switch ru v2 active codec`只改`src/mini_agent/application/persistence.py`。把原17-v1 mapping保存在private immutable `_P0_V1_PERSISTENCE_REGISTRY`，所有legacy helper固定使用它；18-pair catalog也由它构造。Catalog定义后构造public `P0_PERSISTENCE_REGISTRY`，只把RU替换为既有v2 spec。`_classify_outer_versioned`的known versions统一取完整catalog。不得修改imports、Pydantic models、projection rules、public signatures、error enum或其他module。
3. Implementation feedback已确认base test把RU-v1 expected + RU-v2 envelope误写为unknown，且17项legacy/category parity误把两个入口的分类强制相等。保留以上两个sealed commit，随后以append-only `fix(01-07Q): align full-catalog category expectations`只改owned test中的`test_versioned_decode_rejects_cross_version_and_metadata_confusion`与`test_all_17_v1_versioned_decode_outer_version_categories_match_legacy`：前者冻结explicit known mismatch；后者改为directed matrix，冻结legacy v1 lane unknown与versioned full-catalog mismatch。其他review finding仍只用append-only `fix(01-07Q): ...` commit，始终限两文件并对新exact head重跑全部checks/review；不得amend、rebase或force-push已审历史。

done_when:

- RED/source-only GREEN/category-oracle fix的原因、输出、SHA、tree和两文件containment可复现。
- active mapping恰为16-v1+RU-v2；catalog恰为17-v1+RU-v2；legacy v1与explicit versioned v1/v2均保持预期且无推断/fallback。
- 01-07K v2-only isolation、focused、canonical migration/full suite、protected surface全部通过。
- feature和latest-integration overlay均取得exact-head独立`0/0/0/0` review。
- draft PR精确使用Q head → `integration/e2e01-thin`，由Integrator串行merge并捕获新的exact `B_Q`。
- 只解锁01-07J规划；不推进B_ACTIVE、Case、Requirement、Phase、01-08或产品lifecycle。

contract_changes: `YES / APPLICATION CODEC ACTIVE MAPPING` — public 17-code current mapping中RU从v1切换为v2；18-pair catalog、explicit versioned APIs与private v1 compatibility保留。不修改canonical owner、external HTTP、physical schema或Runtime consumer。
security_impact: `YES / FAIL-CLOSED VERSION SELECTION` — active mapping不再把RU-v1表示为current；strict reader继续隔离v1；legacy lane不可被active/versioned路径fallback；errors保持bounded raw-free。Version validity不授予owner、authority、provenance或business evidence。
eval_impact: `YES / COMPONENT REGRESSION AND 01-07J PREREQUISITE` — codec contract tests切换到active-v2 matrix并运行K isolation/full suite；不改EvalCase、Dataset、Grader、Result、threshold、Baseline或lifecycle。
rollback: 合并前关闭PR；合并后用普通revert PR严格逆序撤销01-07Q feature/fix commits，并重新阻塞`B_Q`、01-07J及全部CONTRACT/01-08/01-08A下游。不得reset、force-push、删除/重写v1 row、修改migration或让Runtime在codec rollback后继续使用v2 active selection。

handoff_to: `/root Integrator`
handoff_format: repository/remote/branch/worktree、exact base/planning/head/tree、Plan blob、two base/head blobs、RED/GREEN/fix SHAs与输出、233 focused/50 isolation/48 migration/canonical full结果、active/catalog/legacy/exact-pair matrix、protected oracle、changed-files/commit containment、cross-file scan、contract/security/Eval nonclaims、feature/overlay review、PR/merge SHA、`B_Q` tree、风险与rollback。
</packet_contract>

<cross_file_impact>

- `CONFIRMED`：Thin Slice owner要求Q在dependency closure与current-v1 isolation后单写Application codec active mapping，随后才由J切换Runtime；execution map PR #103已把reviewed acceptance route精确固定为`B_Q_ORACLE_FIX → 01-07Q → B_Q`，无需再次修改canonical owner。
- `CONFIRMED`：exact B_Q_ORACLE_FIX保留B_DEPENDENCY_M中的18-pair catalog、RU-v2 pure codec、K v2-only exact reader、L v2 Provider/Eval consumers与M final source-version contract，并只修正migration test ownership；Q无需跨ownership补依赖。
- `CONFIRMED`：当前`P0_PERSISTENCE_REGISTRY`在`src/**`中只由owned codec module定义/读取；其他Runtime/Infrastructure/Eval source没有直接消费该public mapping。Q不会借registry import静默切换下游。
- `CONFIRMED / CONTROLLED COMPATIBILITY`：既有Runtime/Infrastructure v1 path在J/X/T前仍通过legacy APIs复现；Q只把它隔离为non-current compatibility lane。B_Q不能被描述为完整active Runtime或可部署cutover。
- `CONFIRMED / DERIVED STATUS DRIFT`：`README.md`、`PROJECT_DIRECTION.md`、`.planning/PROJECT.md`、`.planning/ROADMAP.md`、`.planning/STATE.md`与`.planning/REQUIREMENTS.md`仍停在早期B_IP/K-L/M状态。这些共享派生状态不覆盖exact barrier或本次签发，但不在本Plan allowlist；Integrator必须用独立single-writer status Packet对齐，Q writer不得越界或声称repository-wide status aligned。
- `NOT_FOUND`：没有active owner要求Q修改Application records/ports、Runtime、Infrastructure、Eval、Core、migration、ToolSpec、HTTP或tracked Eval artifacts。
</cross_file_impact>

<threat_model>

| threat_id | category | boundary | disposition | mitigation |
|---|---|---|---|---|
| `Q-S01` | Spoofing | RU-v1或caller-selected payload → current v2 | `MITIGATE / BLOCK` | immutable public active mapping只指向catalog v2 exact object；versioned caller仍必须显式pair |
| `Q-T01` | Tampering | mutable/aliased registry或catalog → version substitution | `MITIGATE / BLOCK` | MappingProxyType、17/18 exact cardinality、object-identity matrix、无register/default/latest |
| `Q-T02` | Tampering | active v2失败 → legacy v1 fallback | `MITIGATE / BLOCK` | active与private legacy mapping分离；versioned API单次exact lookup；directed failure-category tests |
| `Q-R01` | Repudiation | active-switch claim → mapping/consumer不明 | `MITIGATE / BLOCK` | exact base/blobs、RED/GREEN、protected AST、source-reference scan、双exact-head review |
| `Q-I01` | Information Disclosure | raw envelope/version error → caller/Trace | `MITIGATE / BLOCK` | existing bounded error projection exact；不修改Trace/HTTP/Provider或raw exception handling |
| `Q-D01` | Denial of Service | RU-only switch → 16 unrelated codecs break | `MITIGATE / BLOCK` | 17-v1 compatibility matrix、233 focused、50 K isolation与full suite |
| `Q-E01` | Elevation of Privilege | active mapping/version decode → authorization/readiness | `MITIGATE / BLOCK` | registry只选codec spec；owner/provenance/graph仍由K和Memory边界验证，Q不声明B_ACTIVE/readiness |

</threat_model>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: RED — freeze RU-v2 current mapping and isolated v1 compatibility</name>
  <files>tests/component/application/test_persistence_contract.py</files>
  <read_first>Thin Slice cutover manifest/§10.1.4、execution map Q slot及preflight remediation、01-07E tests、exact B_Q_ORACLE_FIX codec source/test blobs</read_first>
  <action>只改owned test。增加non-test `_v1_registry()`，通过`P0_RECORD_SCHEMA_VERSION_CATALOG[(code, f"{code.value}.p0.v1")]`显式构造legacy 17-spec view；把九个现有使用`P0_PERSISTENCE_REGISTRY`表达v1 baseline的test分别改为active或explicit-v1语义。Active assertions要求MappingProxyType、17 enum-order entries、RU exact v2 spec/source/identity、其余16 exact v1、catalog object identity与无runtime register；legacy projection/signature/17 round-trip/category assertions全部使用explicit v1 view。重命名两项stage oracle，冻结legacy API仍v1、versioned API exact v1/v2、active mapping无Runtime/authority claim。不得新增test count、skip/xfail、source修改、network或数据库fixture。</action>
  <verify>
    <automated>uv run pytest tests/component/application/test_persistence_contract.py -q</automated>
    RED必须非零且只因public active RU spec仍为v1；collection仍为233，source blob仍为`1e085e066847b69fd4f49e6b8ce6c732391644b3`。
  </verify>
  <done>测试精确区分current active、explicit catalog与legacy compatibility，不再把全v1 registry误写成Q后的current状态。</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: GREEN — switch only the public RU current spec to v2</name>
  <files>src/mini_agent/application/persistence.py</files>
  <read_first>Task 1 RED/output、01-07E exact catalog/API、K reader exact versions、base source AST</read_first>
  <action>只改owned codec source。把原`P0_PERSISTENCE_REGISTRY = MappingProxyType(_REGISTRY)`改为private `_P0_V1_PERSISTENCE_REGISTRY`；所有legacy registry lookup固定到private mapping。让18-pair catalog从private v1 mapping加既有RU-v2 spec构造；紧随catalog定义public `P0_PERSISTENCE_REGISTRY`为private mapping的immutable copy并只替换RU为既有v2 spec。`_classify_outer_versioned`统一用catalog known versions。除`_reference_for_value`、`_validate_external_references`、`_build_envelope`、`_classify_outer`、`_classify_outer_versioned`和三个registry/catalog assignments外，不改任何pre-existing definition/import/class/constant；不新增public symbol、codec API、fallback或dynamic behavior。</action>
  <verify>
    <automated>uv run pytest tests/component/application/test_persistence_contract.py -q
uv run pytest tests/integration/test_postgres_record_adapters.py -q</automated>
    Source行为切换完成；intermediate focused只允许两个既有category oracle（含17项参数化）暴露full-catalog/legacy分类差异，随后由Task 3恢复233。K isolation保持50。
  </verify>
  <done>public current mapping只把RU切到v2；v1 compatibility被private固定且不会污染active/versioned selection。</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: FIX — align full-catalog and legacy category expectations</name>
  <files>tests/component/application/test_persistence_contract.py</files>
  <read_first>Task 2 intermediate focused output、§4 directed category matrix、exact catalog与legacy private registry</read_first>
  <action>只改`test_versioned_decode_rejects_cross_version_and_metadata_confusion`与`test_all_17_v1_versioned_decode_outer_version_categories_match_legacy`。Explicit versioned RU-v1 expected + RU-v2 envelope改为`RECORD_SCHEMA_VERSION_MISMATCH`；17项matrix分别断言missing、other-v1、RU-v2与unknown-future在legacy/versioned两个入口的directed category，不再强制全量相等。不得修改source、其他test、collection count、fixture或公共合同。</action>
  <verify>
    <automated>uv run pytest tests/component/application/test_persistence_contract.py -q
uv run pytest tests/integration/test_postgres_record_adapters.py -q</automated>
    focused恢复233，K isolation保持50；active/current、catalog、legacy、exact-pair与directed error category全部通过。
  </verify>
  <done>stale category oracle已在append-only test commit中修正，source与初始RED历史未被重写。</done>
</task>

</tasks>

<verification>

Gate A必须在任何RED编辑前从仓库根执行：

```bash
set -euo pipefail

base_sha=83bdd112e016850ced35ef0870b78c55bad30a77
base_tree=30594eaa1347f817045a66b9a405d7a38ea24cea
expected_branch=codex/e2e01-01-ru-v2-codec-active-switch
expected_worktree_id=e2e01-01-ru-v2-codec-active-switch
expected_remote=https://github.com/weijie567/mini-agent.git
current_root="$(git rev-parse --show-toplevel)"

test "$(git remote get-url origin)" = "$expected_remote"
test "$(git branch --show-current)" = "$expected_branch"
test "$(basename "$current_root")" = "$expected_worktree_id"
test "$(git worktree list --porcelain | awk -v root="$current_root" '
  $1 == "worktree" { current = $2 }
  $1 == "branch" && current == root { print $2 }
')" = "refs/heads/$expected_branch"
test "$(git rev-parse HEAD)" = "$base_sha"
test "$(git rev-parse HEAD^{tree})" = "$base_tree"
test "$(git rev-parse "${base_sha}:src/mini_agent/application/persistence.py")" = \
  1e085e066847b69fd4f49e6b8ce6c732391644b3
test "$(git rev-parse "${base_sha}:tests/component/application/test_persistence_contract.py")" = \
  8a87f0bc8dd7e8a7556d897cc57efce982412e91
test -z "$(git status --short --untracked-files=all)"
uv run pytest tests/component/application/test_persistence_contract.py -q
uv run pytest tests/integration/test_postgres_record_adapters.py -q
uv run pytest tests/integration/test_database_migrations.py -q
```

Gate B / post-implementation final不再要求`HEAD == base_sha`，但必须完整重验：

```bash
set -euo pipefail

base_sha=83bdd112e016850ced35ef0870b78c55bad30a77
base_tree=30594eaa1347f817045a66b9a405d7a38ea24cea
expected_branch=codex/e2e01-01-ru-v2-codec-active-switch
expected_worktree_id=e2e01-01-ru-v2-codec-active-switch
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
test "$(git rev-parse "${base_sha}^{tree}")" = "$base_tree"
test "$(git rev-parse "${base_sha}:src/mini_agent/application/persistence.py")" = \
  1e085e066847b69fd4f49e6b8ce6c732391644b3
test "$(git rev-parse "${base_sha}:tests/component/application/test_persistence_contract.py")" = \
  8a87f0bc8dd7e8a7556d897cc57efce982412e91

uv sync --all-groups
export COMPOSE_PROJECT_NAME=mini-agent
docker compose up --wait -d db
docker compose --profile test up --wait -d db-test
uv run alembic upgrade head
uv run pytest tests/component/application/test_persistence_contract.py -q
uv run pytest tests/integration/test_postgres_record_adapters.py -q
uv run pytest tests/integration/test_database_migrations.py -q
uv run pytest

git diff --check "$base_sha...HEAD"
test "$(git rev-list --count "$base_sha..HEAD")" -ge 3
test "$(git rev-list --merges --count "$base_sha..HEAD")" -eq 0
red_sha="$(git rev-list --reverse "$base_sha..HEAD" | sed -n '1p')"
green_sha="$(git rev-list --reverse "$base_sha..HEAD" | sed -n '2p')"
category_fix_sha="$(git rev-list --reverse "$base_sha..HEAD" | sed -n '3p')"
test "$(git show -s --format=%s "$red_sha")" = \
  "test(01-07Q): require ru v2 active codec"
test "$(git show -s --format=%s "$green_sha")" = \
  "feat(01-07Q): switch ru v2 active codec"
test "$(git show -s --format=%s "$category_fix_sha")" = \
  "fix(01-07Q): align full-catalog category expectations"
test "$(git diff-tree --no-commit-id --name-only -r "$red_sha")" = \
  tests/component/application/test_persistence_contract.py
test "$(git diff-tree --no-commit-id --name-only -r "$green_sha")" = \
  src/mini_agent/application/persistence.py
test "$(git diff-tree --no-commit-id --name-only -r "$category_fix_sha")" = \
  tests/component/application/test_persistence_contract.py
uv run python - "$green_sha" "$category_fix_sha" <<'PY'
import ast
import subprocess
import sys

path = "tests/component/application/test_persistence_contract.py"
allowed = {
    "test_versioned_decode_rejects_cross_version_and_metadata_confusion",
    "test_all_17_v1_versioned_decode_outer_version_categories_match_legacy",
}


def load(revision: str) -> ast.Module:
    source = subprocess.run(
        ["git", "show", f"{revision}:{path}"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return ast.parse(source)


def separate(
    tree: ast.Module,
) -> tuple[ast.Module, dict[str, ast.FunctionDef | ast.AsyncFunctionDef]]:
    selected: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    retained: list[ast.stmt] = []
    for node in tree.body:
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name in allowed
        ):
            assert node.name not in selected
            selected[node.name] = node
        else:
            retained.append(node)
    assert set(selected) == allowed
    tree.body = retained
    return tree, selected


before_tree, before_functions = separate(load(sys.argv[1]))
after_tree, after_functions = separate(load(sys.argv[2]))
assert ast.dump(before_tree, include_attributes=False) == ast.dump(
    after_tree,
    include_attributes=False,
)
for name in allowed:
    before = before_functions[name]
    after = after_functions[name]
    assert ast.dump(before, include_attributes=False) != ast.dump(
        after,
        include_attributes=False,
    )
    before.body = [ast.Pass()]
    after.body = [ast.Pass()]
    assert ast.dump(before, include_attributes=False) == ast.dump(
        after,
        include_attributes=False,
    )
PY
uv run python - <<'PY'
import json
import runpy

namespace = runpy.run_path(
    "tests/component/application/test_persistence_contract.py"
)
persistence = namespace["persistence_module"]
category_enum = namespace["P0PersistenceIntegrityCategory"]
integrity_error = namespace["P0PersistenceIntegrityError"]
ru_v2_schema_version = namespace["RU_V2_SCHEMA_VERSION"]
v1_registry = namespace["_v1_registry"]()


def decode_category(call):
    try:
        call()
    except integrity_error as error:
        return error.category
    raise AssertionError("directed category oracle unexpectedly decoded")


expected = (
    (
        "missing",
        category_enum.MISSING_RECORD_SCHEMA_VERSION,
        category_enum.MISSING_RECORD_SCHEMA_VERSION,
    ),
    (
        "other_v1",
        category_enum.RECORD_SCHEMA_VERSION_MISMATCH,
        category_enum.RECORD_SCHEMA_VERSION_MISMATCH,
    ),
    (
        "ru_v2",
        category_enum.UNKNOWN_RECORD_SCHEMA_VERSION,
        category_enum.RECORD_SCHEMA_VERSION_MISMATCH,
    ),
    (
        "future",
        category_enum.UNKNOWN_RECORD_SCHEMA_VERSION,
        category_enum.UNKNOWN_RECORD_SCHEMA_VERSION,
    ),
)
for case in namespace["_record_cases"]():
    envelope = namespace["encode_persistence_record"](
        case.code,
        case.record,
        external_references=case.external_references,
        logical_children=case.logical_children,
    )
    other_v1 = next(
        spec.record_schema_version
        for code, spec in v1_registry.items()
        if code is not case.code
    )
    raws = {}
    missing = json.loads(envelope.model_dump_json())
    missing.pop("record_schema_version")
    raws["missing"] = missing
    for label, version in (
        ("other_v1", other_v1),
        ("ru_v2", ru_v2_schema_version),
        ("future", "unknown-future-record.p0.v99"),
    ):
        raw = json.loads(envelope.model_dump_json())
        raw["record_schema_version"] = version
        raws[label] = raw

    for label, expected_legacy, expected_versioned in expected:
        raw = raws[label]
        actual_legacy = decode_category(
            lambda raw=raw, code=case.code: namespace[
                "decode_persistence_record"
            ](
                raw,
                expected_record_code=code,
                correlation_ref=namespace["_uuid"](299),
            )
        )
        actual_versioned = decode_category(
            lambda raw=raw, code=case.code: (
                persistence.decode_persistence_record_versioned(
                    raw,
                    expected_record_code=code,
                    expected_schema_version=v1_registry[
                        code
                    ].record_schema_version,
                    correlation_ref=namespace["_uuid"](299),
                )
            )
        )
        assert actual_legacy is expected_legacy, (case.code, label)
        assert actual_versioned is expected_versioned, (case.code, label)
PY
test -z "$(git log --reverse --format=%s "$base_sha..HEAD" |
  sed '1,3d' |
  rg -v '^fix\(01-07Q\): .+$' || true)"
for fix_sha in $(git rev-list --reverse "$base_sha..HEAD" | sed '1,3d'); do
  test -z "$(git diff-tree --no-commit-id --name-only -r "$fix_sha" |
    rg -v '^(src/mini_agent/application/persistence\.py|tests/component/application/test_persistence_contract\.py)$' ||
    true)"
done
test "$(git diff --name-only "$base_sha...HEAD" | LC_ALL=C sort)" = "$(printf '%s\n' \
  src/mini_agent/application/persistence.py \
  tests/component/application/test_persistence_contract.py)"
test -z "$(git status --short --untracked-files=all)"
```

Protected-surface oracle必须作为同一Gate B运行：

```bash
base_sha=83bdd112e016850ced35ef0870b78c55bad30a77
uv run python - "$base_sha" <<'PY'
from __future__ import annotations

import ast
import copy
from pathlib import Path
from types import MappingProxyType
import subprocess
import sys

from mini_agent.application import persistence

BASE = sys.argv[1]
SOURCE = "src/mini_agent/application/persistence.py"
TEST = "tests/component/application/test_persistence_contract.py"
RU_CODE = persistence.P0RecordCode.REQUEST_UNDERSTANDING_RECORD
RU_V1 = "request_understanding_record.p0.v1"
RU_V2 = "request_understanding_record.p0.v2"
MUTABLE_SOURCE_FUNCTIONS = {
    "_reference_for_value",
    "_validate_external_references",
    "_build_envelope",
    "_classify_outer",
    "_classify_outer_versioned",
}
MUTABLE_BASE_TEST_FUNCTIONS = {
    "test_registry_is_exact_immutable_and_closed",
    "test_projection_matrices_are_exact_and_reference_targets_are_closed",
    "test_all_projection_decision_signatures_match_the_canonical_matrix",
    "test_version_catalog_is_exact_immutable_and_only_ru_is_dual",
    "test_all_17_v1_pairs_have_legacy_semantic_parity",
    "test_versioned_decode_rejects_cross_version_and_metadata_confusion",
    "test_legacy_codec_remains_v1_only_after_codec_expand",
    "test_codec_expand_has_no_active_consumer_or_authority_claim",
    "test_codec_expand_preserves_all_legacy_projection_counts",
    "test_all_17_v1_versioned_decode_outer_version_categories_match_legacy",
}
MUTABLE_AFTER_TEST_FUNCTIONS = {
    "test_registry_is_exact_immutable_and_closed",
    "test_projection_matrices_are_exact_and_reference_targets_are_closed",
    "test_all_projection_decision_signatures_match_the_canonical_matrix",
    "test_version_catalog_is_exact_immutable_and_only_ru_is_dual",
    "test_all_17_v1_pairs_have_legacy_semantic_parity",
    "test_versioned_decode_rejects_cross_version_and_metadata_confusion",
    "test_active_switch_preserves_v1_compatibility_until_contract",
    "test_codec_active_switch_has_no_runtime_or_authority_claim",
    "test_codec_expand_preserves_all_legacy_projection_counts",
    "test_all_17_v1_versioned_decode_outer_version_categories_match_legacy",
    "_v1_registry",
}
MUTABLE_ASSIGNMENTS = {
    "P0_PERSISTENCE_REGISTRY",
    "_P0_V1_PERSISTENCE_REGISTRY",
    "P0_RECORD_SCHEMA_VERSION_CATALOG",
}
FORBIDDEN_CALLS = frozenset(
    {"__import__", "eval", "exec", "globals", "locals", "setattr"}
)


def base_text(file_name: str) -> str:
    return subprocess.check_output(
        ["git", "show", f"{BASE}:{file_name}"],
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


def single_plain_assignment_name(node: ast.AST) -> str | None:
    if any(isinstance(item, ast.NamedExpr) for item in ast.walk(node)):
        return None
    if isinstance(node, ast.Assign):
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            return node.targets[0].id
        return None
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return node.target.id
    return None


def mutable_assignment_counts(tree: ast.Module) -> dict[str, int]:
    counts = {name: 0 for name in MUTABLE_ASSIGNMENTS}
    for node in tree.body:
        name = single_plain_assignment_name(node)
        if name in counts:
            counts[name] += 1
    return counts


def protected_nodes(
    tree: ast.Module,
    mutable_functions: set[str],
) -> list[ast.AST]:
    result: list[ast.AST] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in mutable_functions:
                continue
        if single_plain_assignment_name(node) in MUTABLE_ASSIGNMENTS:
            continue
        result.append(node)
    return result


before_source = base_text(SOURCE)
after_source = Path(SOURCE).read_text(encoding="utf-8")
before_source_tree = ast.parse(before_source)
after_source_tree = ast.parse(after_source)
assert mutable_assignment_counts(before_source_tree) == {
    "P0_PERSISTENCE_REGISTRY": 1,
    "_P0_V1_PERSISTENCE_REGISTRY": 0,
    "P0_RECORD_SCHEMA_VERSION_CATALOG": 1,
}
assert mutable_assignment_counts(after_source_tree) == {
    "P0_PERSISTENCE_REGISTRY": 1,
    "_P0_V1_PERSISTENCE_REGISTRY": 1,
    "P0_RECORD_SCHEMA_VERSION_CATALOG": 1,
}
for mutant in (
    "P0_PERSISTENCE_REGISTRY = alias = value",
    "P0_PERSISTENCE_REGISTRY, alias = value",
    "[P0_PERSISTENCE_REGISTRY, alias] = value",
    "P0_PERSISTENCE_REGISTRY = (alias := value)",
    "owner.P0_PERSISTENCE_REGISTRY = value",
    "owner['P0_PERSISTENCE_REGISTRY'] = value",
):
    mutant_node = ast.parse(mutant).body[0]
    assert single_plain_assignment_name(mutant_node) is None
before_protected = protected_nodes(
    before_source_tree,
    MUTABLE_SOURCE_FUNCTIONS,
)
after_protected = protected_nodes(
    after_source_tree,
    MUTABLE_SOURCE_FUNCTIONS,
)
assert len(before_protected) == len(after_protected)
for left, right in zip(before_protected, after_protected, strict=True):
    exact(before_source, after_source, left, right)

before_source_functions = {
    node.name: node
    for node in before_source_tree.body
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
}
after_source_functions = {
    node.name: node
    for node in after_source_tree.body
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
}
assert set(before_source_functions) == set(after_source_functions)


class LegacyRegistryRename(ast.NodeTransformer):
    def visit_Name(self, node: ast.Name) -> ast.AST:
        if (
            isinstance(node.ctx, ast.Load)
            and node.id == "P0_PERSISTENCE_REGISTRY"
        ):
            return ast.copy_location(
                ast.Name(
                    id="_P0_V1_PERSISTENCE_REGISTRY",
                    ctx=ast.Load(),
                ),
                node,
            )
        return node


class VersionedKnownVersionsRewrite(ast.NodeTransformer):
    def __init__(self) -> None:
        self.rewrite_count = 0

    def visit_If(self, node: ast.If) -> ast.AST | list[ast.stmt]:
        test = node.test
        if (
            isinstance(test, ast.Compare)
            and isinstance(test.left, ast.Name)
            and test.left.id == "selected_spec"
            and len(test.ops) == len(test.comparators) == 1
            and isinstance(test.ops[0], ast.Is)
            and isinstance(test.comparators[0], ast.Subscript)
            and isinstance(test.comparators[0].value, ast.Name)
            and test.comparators[0].value.id == "P0_PERSISTENCE_REGISTRY"
        ):
            self.rewrite_count += 1
            return [copy.deepcopy(item) for item in node.orelse]
        return self.generic_visit(node)


for function_name in MUTABLE_SOURCE_FUNCTIONS - {"_classify_outer_versioned"}:
    expected = LegacyRegistryRename().visit(
        copy.deepcopy(before_source_functions[function_name])
    )
    ast.fix_missing_locations(expected)
    assert ast.dump(expected, include_attributes=False) == ast.dump(
        after_source_functions[function_name],
        include_attributes=False,
    )

versioned_rewrite = VersionedKnownVersionsRewrite()
expected_versioned = versioned_rewrite.visit(
    copy.deepcopy(before_source_functions["_classify_outer_versioned"])
)
ast.fix_missing_locations(expected_versioned)
assert versioned_rewrite.rewrite_count == 1
assert ast.dump(expected_versioned, include_attributes=False) == ast.dump(
    after_source_functions["_classify_outer_versioned"],
    include_attributes=False,
)

before_test = base_text(TEST)
after_test = Path(TEST).read_text(encoding="utf-8")
before_test_tree = ast.parse(before_test)
after_test_tree = ast.parse(after_test)
before_test_protected = protected_nodes(
    before_test_tree,
    MUTABLE_BASE_TEST_FUNCTIONS,
)
after_test_protected = protected_nodes(
    after_test_tree,
    MUTABLE_AFTER_TEST_FUNCTIONS,
)
assert len(before_test_protected) == len(after_test_protected)
for left, right in zip(
    before_test_protected,
    after_test_protected,
    strict=True,
):
    exact(before_test, after_test, left, right)

after_test_functions = {
    node.name
    for node in after_test_tree.body
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
}
assert "_v1_registry" in after_test_functions
assert (
    "test_active_switch_preserves_v1_compatibility_until_contract"
    in after_test_functions
)
assert (
    "test_codec_active_switch_has_no_runtime_or_authority_claim"
    in after_test_functions
)
assert not (
    MUTABLE_BASE_TEST_FUNCTIONS
    - MUTABLE_AFTER_TEST_FUNCTIONS
) & after_test_functions

for before_tree, after_tree in (
    (before_source_tree, after_source_tree),
    (before_test_tree, after_test_tree),
):
    before_counts = {
        name: sum(
            1
            for node in ast.walk(before_tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == name
        )
        for name in FORBIDDEN_CALLS
    }
    after_counts = {
        name: sum(
            1
            for node in ast.walk(after_tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == name
        )
        for name in FORBIDDEN_CALLS
    }
    assert after_counts == before_counts

active = persistence.P0_PERSISTENCE_REGISTRY
catalog = persistence.P0_RECORD_SCHEMA_VERSION_CATALOG
legacy = persistence._P0_V1_PERSISTENCE_REGISTRY
assert isinstance(active, MappingProxyType)
assert isinstance(catalog, MappingProxyType)
assert isinstance(legacy, MappingProxyType)
assert tuple(active) == tuple(persistence.P0RecordCode)
assert tuple(legacy) == tuple(persistence.P0RecordCode)
assert len(active) == len(legacy) == 17
assert len(catalog) == 18
assert active[RU_CODE] is catalog[(RU_CODE, RU_V2)]
assert legacy[RU_CODE] is catalog[(RU_CODE, RU_V1)]
assert active[RU_CODE] is not legacy[RU_CODE]
for code in persistence.P0RecordCode:
    v1 = f"{code.value}.p0.v1"
    assert legacy[code] is catalog[(code, v1)]
    if code is not RU_CODE:
        assert active[code] is legacy[code]
assert not hasattr(persistence, "_REGISTRY")
assert not hasattr(persistence, "register")
print("01-07Q protected surface: PASS")
PY
```

Repository-level impact scan：

```bash
rg -n \
  'P0_PERSISTENCE_REGISTRY|P0_RECORD_SCHEMA_VERSION_CATALOG|encode_persistence_record(_versioned)?|decode_persistence_record(_versioned)?|request_understanding_record\.p0\.v[12]|B_DEPENDENCY_M|B_Q_ORACLE_FIX|B_Q|01-07[MQJT]' \
  AGENTS.md README.md PROJECT_DIRECTION.md docs .planning src tests evals \
  --glob '!graphify-out/**'
```

scan只报告canonical alignment、existing v1 compatibility consumers、已知derived status drift与J/T下游；feature writer不得越allowlist修正。Feature exact head必须对两项changed files完成独立correctness/security/test review并取得`PASS / CRITICAL-HIGH-MEDIUM-LOW = 0/0/0/0`。随后Integrator在包含01-07Q Plan merge的latest `integration/e2e01-thin`上创建no-conflict overlay，证明patch identity，重复focused/isolation/full/protected gates与独立review，再串行merge。只有该reviewed feature merge SHA才命名为`B_Q`。

</verification>

<success_criteria>

1. RED/source-only GREEN/category-oracle fix三提交的失败/通过原因、scope、SHA与输出可复现；其他review fix只可append并保持两文件allowlist。
2. Public active registry恰为16-v1+RU-v2，18-pair catalog与private 17-v1 compatibility均immutable且object identity精确。
3. Legacy API继续v1-only；versioned API继续explicit exact pair；无default/latest/inference/fallback/rewrite。Explicit RU-v1↔RU-v2 cross-version均为known mismatch，legacy v1 lane中的RU-v2仍为unknown。
4. 01-07K current-v1 isolation 50、focused 233、reviewed migration oracle 48、canonical migration upgrade/full 1901、protected oracle、two-file containment与feature/latest-overlay独立review全部通过。
5. Reviewed feature merge形成exact `B_Q`并只解锁01-07J；不宣告B_ACTIVE、v1 contract removal、01-08或产品完成。

</success_criteria>

<output>
完成后不创建Summary或共享State。Executor只按`handoff_format`交接；Integrator在reviewed merge后另行索引`B_Q`证据并处理derived status alignment。
</output>
