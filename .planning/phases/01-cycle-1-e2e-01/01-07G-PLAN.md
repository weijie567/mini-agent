---
phase: 01-cycle-1-e2e-01
plan: 07G
type: execute
wave: 15
depends_on:
  - 01-07B
files_modified:
  - docs/implementation/e2e01-thin-slice-implementation-spec.md
autonomous: true
requirements:
  - E2E01-01
  - E2E01-04
user_setup: []
must_haves:
  truths:
    - "P0 get_order FOUND 的 source_version 由 Infra Adapter 在一次 owner-scoped 查询和严格安全投影校验后，基于本次实际读取的可信身份、订单标识与安全投影确定性计算。"
    - "source_version 是 runtime-private、可审计的快照版本元数据，不是授权凭据、secret、Agent-visible Tool output、HTTP字段、用户回复或普通Trace事实。"
    - "FOUND 必须同时携带安全 order_summary 与 non-empty exact source_version；NOT_FOUND_OR_NOT_ACCESSIBLE 和 SYSTEM_FAILURE 均不得携带 source_version 或 Observation/Manifest #2。"
    - "GetOrderResult.source_version → OrderObservation.source_version → ContextManifest VersionedRecordRef.version 必须 byte-for-byte exact copy；Runtime、Eval和下游消费者不得重算、normalize、parse或fallback。"
    - "P0 content version只表示实际可见安全快照；A→B→A可以回到相同token，不声称monotonic revision或ABA detection。若owner要求后两者，必须停止并新增migration Packet。"
    - "本 Packet 只裁决 Thin Slice scoped contract，不修改Core DTO、Memory全局optionality、Runtime、Infra、数据库、ToolSpec、HTTP、Eval或Case lifecycle。"
  artifacts:
    - "Thin Slice Spec 中唯一的 get_order source-version authority、canonical envelope/hash、token format/test vector、outcome matrix、exact-copy和compatibility/rollback contract。"
  key_links:
    - "01-07H消费本裁决实现Core/Order DTO；01-07J消费DTO把版本原样写入Observation/Manifest并删除schema fallback；01-07K在同一次owner-scoped PostgreSQL读取上实现算法。"
    - "01-07D与01-07H只能从01-07C/01-07G均reviewed merge后的共同exact integration SHA签发。"
---

# Phase 1 Plan 01-07G｜P0 get_order source-version ruling

> **ISSUED OWNER-RULING TASK PACKET / IMPLEMENTATION NOT STARTED**
> 当前 `GetOrderResult` 没有 source version，FOUND 路径创建 `OrderObservation` 时也不赋值；Runtime随后把记录schema占位符 `"order-observation.p0.v1"`写入 Context Manifest。与此同时物理 `mock_orders.stored_at` 在upsert更新时不变化，Fixture `fixture_version`又只是数据集版本，二者都不能代表本次实际读取的订单安全快照。本 Packet 只由Thin Slice scoped owner冻结唯一的P0算法与传播规则。

> **DERIVED / NON_NORMATIVE**
> 本 Plan 把 active owner、Memory exact-version规则和当前实现反馈转成一个精确Task Packet，不自行拥有source-version语义。只有feature PR修改后的 `docs/implementation/e2e01-thin-slice-implementation-spec.md` 才能形成scoped canonical裁决。

<objective>
在 Thin Slice scoped owner 中冻结 P0 `get_order` 的server-private source-version authority、确定性content-version算法、outcome矩阵、exact-copy传播和兼容/rollback边界。

Purpose: 让FOUND Observation与Presentation Context Manifest能够引用同一个真实业务快照版本，消除schema-version fallback和Fixture/stored_at伪版本。

Output: 仅修改 `docs/implementation/e2e01-thin-slice-implementation-spec.md` 的一个文档提交；不实现DTO、hash代码、数据库、Runtime或Eval。
</objective>

<execution_context>
@AGENTS.md
@.planning/GOVERNANCE.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/01-cycle-1-e2e-01/01-07C-PLAN.md
@.planning/phases/01-cycle-1-e2e-01/01-07B-SUMMARY.md
@docs/implementation/e2e01-thin-slice-implementation-spec.md
@docs/architecture/memory-design-reference.md
@PROJECT_DIRECTION.md
@src/mini_agent/core/order.py
@src/mini_agent/core/memory.py
@src/mini_agent/application/read_tool_executor.py
@src/mini_agent/application/agent_run_service.py
@src/mini_agent/infrastructure/order/postgres.py
@src/mini_agent/infrastructure/persistence/models.py
@evals/fixtures/e2e01-thin-slice.v1.json
@tests/component/application/test_read_tool_executor.py
@tests/component/application/test_agent_run_service.py
@tests/integration/test_postgres_get_order.py

本 Plan 使用受控 GSD planner / checker adapter，不调用 stock `gsd-plan-phase`、`gsd-execute-phase`、`gsd-verify-work`、lifecycle mutation 或 `gsd-ship`。planning-status PR 必须先reviewed merge；随后Integrator从固定execution base建立feature Worktree，并从official planning merge读取本Plan。Executor只能写唯一owned file。
</execution_context>

<packet_contract>
repository: `https://github.com/weijie567/mini-agent`
remote: `origin`
head_branch: `codex/e2e01-01-get-order-source-version-ruling`
base_branch: `integration/e2e01-thin`
base_sha: `3f0753f7bef87fc02f314e28fe8b07860a819701`
base_tree: `b5214d3b7140ca305566a9cb802a21388a92464c`
owned_base_blob: `08d90f1b02d6e34c2ac333a96615258ce04f0797`
worktree_id: `e2e01-01-get-order-source-version-ruling`
worktree_path: `/Users/ming/projects/mini-agent-worktrees/e2e01-01-get-order-source-version-ruling`
writer: `Thin Slice scoped-contract sole writer, supervised by /root Integrator`
agent_role: `gsd-doc-writer`

owned_files:

- `docs/implementation/e2e01-thin-slice-implementation-spec.md`

forbidden_files:

- every repository path not listed in `owned_files`
- `AGENTS.md`
- `PROJECT_DIRECTION.md`
- `README.md`
- `.planning/**`
- `docs/business-capabilities.md`
- `docs/architecture/**`
- `docs/evaluation/**`
- every other `docs/implementation/**` path
- `src/**`
- `tests/**`
- `evals/**`
- `alembic/**`
- `pyproject.toml`
- `uv.lock`
- `compose.yaml`
- `graphify-out/**`

canonical_inputs:

- `AGENTS.md` identity/resource-ownership/minimum-disclosure/Evidence invariants
- `docs/implementation/e2e01-thin-slice-implementation-spec.md` scoped get_order, Observation/Manifest and Definition-of-Done contract
- `docs/architecture/memory-design-reference.md` source version, VersionedRecordRef and exact-version-only semantics
- current source/tests/fixture at `base_sha` as implementation feedback, never as authority to silently define the contract

dependencies:

- 01-07B reviewed merge and status-aligned fixed execution base `3f0753f7bef87fc02f314e28fe8b07860a819701`
- 01-07C planning PR #46 reviewed merge `f1bf2b3f2c8cd9fa61711dde7c0e94365c54b583`; 01-07C is a same-wave independent owner ruling, not a feature dependency
- Project Direction owner alignment PR #47 reviewed merge `f16eda358a7eb92eb3495ef36d2c19ef5f1d2867`; volatile GSD counts are no longer duplicated by the active owner
- this 01-07G planning-status PR reviewed merge before any C/G feature write
- execution preflight records official `G_PLANNING_CONTRACT_SHA`, Plan blob and immutable C Plan blob, then proves the owned Thin Slice file is byte-identical at `base_sha` and planning head
- 01-07D / 01-07H remain blocked until both C and G feature PRs are serially merged into a common exact integration barrier

required_checks:

- exact execution base/tree/owned blob, branch, merge-base, clean Worktree, planning provenance and C Plan byte-identity preflight
- one and only one feature commit relative to `base_sha`
- changed-file set exactly equals `docs/implementation/e2e01-thin-slice-implementation-spec.md`
- owner freezes `source_version_schema = "mock-order-source-version.p0.v1"`
- authority is only the Infra Adapter after one owner-scoped `customer_id + order_id` query returns a row, JSONB strictly validates as `OrderSummaryProjection`, and `projection.order_number == query.order_id`; user/model/Provider/Fixture/Runtime/Eval cannot supply, override or recompute it
- canonical payload is exactly `{"source_version_schema": schema, "owner_customer_id": trusted_query.customer_id, "order_id": validated_query.order_id, "safe_projection": projection.model_dump(mode="json")}`
- canonical bytes use Python-compatible JSON semantics `allow_nan=False`, `ensure_ascii=False`, `separators=(",", ":")`, `sort_keys=True`, then UTF-8; version is lowercase SHA-256 with exact prefix
- token pattern is exactly `^mock-order-source-version\.p0\.v1:sha256:[0-9a-f]{64}$`
- fixed `customer-A / O-1001` vector is `mock-order-source-version.p0.v1:sha256:861c136b1a41ecef3cd9625dc58524ec452e939b5ca1eb70ebcab69181561c42`
- owner explicitly states content-version semantics: equal owner-scoped safe projection yields equal token, any included field change yields a different token, A→B→A may return to the first token, and the token is neither monotonic nor an event revision
- if monotonic revision, ABA detection, HMAC secrecy, opaque persisted version, new external config, global Memory-required field, Agent-visible output or schema migration is required, the Packet stops and returns a new dependency/denominator decision rather than expanding scope
- FOUND matrix requires both `order_summary` and non-empty exact-pattern `source_version`, forbids `failure_code`, and creates Observation plus Manifest #2
- NOT_FOUND_OR_NOT_ACCESSIBLE forbids `order_summary`, `source_version`, `failure_code`, Observation and Manifest #2; missing and foreign remain indistinguishable
- SYSTEM_FAILURE forbids `order_summary`, `source_version`, Observation and Manifest #2 while permitting only the existing bounded safe failure code
- source_version flows `GetOrderResult → OrderObservation → ContextManifest.VersionedRecordRef.version` byte-for-byte; downstream never parses, normalizes, rehashes, recomputes or substitutes it
- explicitly forbidden substitutes include record/schema versions, `"order-observation.p0.v1"`, `stored_at`, `status_updated_at`, Fixture/Dataset/Tool Registry/artifact/runtime/Eval versions, and any latest/default/placeholder
- token is runtime-private authority/audit metadata, not a secret or authorization capability, and never enters Agent-visible `ToolSpec.output_schema`, model input, HTTP, user response or ordinary Trace
- corrupt payload/version is a bounded system failure and must not collapse to safe not-found; version generation cannot perform a second query or widen the trusted owner predicate
- generic `OrderObservation.source_version?` remains optional outside this scoped FOUND producer/consumer path; no global Memory record-version upgrade, old-record backfill or read-time migration
- old records with `source_version=None` may remain decodable but cannot support a new Presentation Manifest or passing Eval evidence
- cross-file impact scan maps H/J/K and current tests as downstream work without editing them
- task-local automated checks, `git diff --check`, full `uv run pytest`, local links, exact one-file containment, independent exact-head canonical/security review and latest-integration overlay

done_when:

- Thin Slice owner contains one unambiguous authority, canonical envelope/hash, pattern/vector, outcome matrix, exact-copy chain and compatibility/ABA/nonclaim ruling
- one feature commit changes exactly one owned file
- no Core/Memory/Runtime/Infra/DB/ToolSpec/HTTP/Eval/lifecycle change is smuggled into this Packet
- exact feature and latest-integration overlay checks pass
- unresolved `CRITICAL / HIGH / MEDIUM = 0 / 0 / 0`
- draft PR targets `integration/e2e01-thin` and records contract change, nonclaims, checks, risks and rollback
- merge does not advance Case / Requirement / numbered Phase lifecycle

contract_changes: `YES / SCOPED THIN-SLICE CONTRACT` — freezes P0 get_order runtime-private source-version authority, deterministic content algorithm, token/outcome/exact-copy semantics and downstream ownership; no Agent-visible, HTTP, global Memory, physical schema or code change.
security_impact: `YES` — version is generated only after trusted owner-scoped read and strict safe-projection validation; missing/foreign produce no token; token grants no authority and cannot leak to model/user; corruption remains distinguishable from safe not-found only inside bounded runtime failure handling.
eval_impact: `YES / CONTRACT INPUT ONLY` — freezes FOUND trajectory Observation/Manifest exact equality and fixed-vector evidence expected from H/J/K; no Dataset, Grader, threshold, Eval Result or lifecycle change.
new_dependencies: `NONE` unless the owner rejects content-version/ABA semantics or requires migration/global/external scope, in which case this Packet is `BLOCKED` and a new Packet decision is mandatory.
graphify_disposition: `INTEGRATOR POST-MERGE SEMANTIC GATE` — feature writer never modifies `graphify-out/**`; after merge Integrator runs project-supported documentation semantic refresh if available, otherwise records `NOT_RUN` and verifies owner/consumer relations by source scan without claiming semantic graph freshness.
rollback: Close before merge or use a normal revert PR and re-block 01-07D–01-08A. Never reset, force-push, delete data, backfill or invent a migration rollback for this contract-only change.

handoff_to: `/root Integrator`

handoff_format:

- branch, exact base/planning/head/commit/tree, owned base blob, C/G Plan blobs
- exact one-file feature/overlay containment
- canonical payload/bytes/token algorithm, fixed vectors and content/ABA matrix
- outcome and exact-copy propagation matrices
- commands and exact results
- cross-file impact map, contract/security/Eval impact and explicit nonclaims
- independent feature/overlay reviews, unresolved risks and rollback
</packet_contract>

<threat_model>

| threat_id | category | boundary | disposition | mitigation |
|---|---|---|---|---|
| `OSV-S01` | Spoofing | user/model/fixture → source version | `MITIGATE / BLOCK` | only trusted Adapter computes after owner-scoped read and strict projection validation |
| `OSV-T01` | Tampering | DB projection/version → Observation/Manifest | `MITIGATE / BLOCK` | canonical content hash, fixed vector and byte-for-byte propagation; corruption is not safe not-found |
| `OSV-R01` | Repudiation | business snapshot → Eval evidence | `MITIGATE / BLOCK` | deterministic owner-scoped version binds the exact safe snapshot seen by Runtime |
| `OSV-I01` | Information Disclosure | runtime-private version → model/user | `MITIGATE / BLOCK` | no ToolSpec/model/HTTP/reply/ordinary-Trace exposure; token is metadata, not a secret |
| `OSV-D01` | Denial of Service | missing/malformed version → Presentation | `MITIGATE / BOUNDED` | no fallback or retry/second query; bounded system failure and fail-closed Presentation/Eval |
| `OSV-E01` | Elevation of Privilege | version token → authorization | `MITIGATE / BLOCK` | token never grants access; every read independently reuses trusted composite owner predicate |

</threat_model>

<tasks>

<task type="auto">
  <name>Task 1: Freeze source-version authority and deterministic content algorithm</name>
  <files>docs/implementation/e2e01-thin-slice-implementation-spec.md</files>
  <action>
在Thin Slice scoped owner的`get_order` contract附近冻结唯一authority、strict-validation前置、canonical payload/JSON bytes/SHA-256算法、exact token pattern与O-1001 fixed vector。明确content-version与ABA语义、runtime-private exposure边界，以及需要monotonic/HMAC/persistence/migration时必须停止并新增Packet。
  </action>
  <verify>
    <automated>test "$(git diff --name-only 3f0753f7bef87fc02f314e28fe8b07860a819701...HEAD)" = "docs/implementation/e2e01-thin-slice-implementation-spec.md"
rg -n 'mock-order-source-version\.p0\.v1|sha256|861c136b1a41ecef3cd9625dc58524ec452e939b5ca1eb70ebcab69181561c42|sort_keys|allow_nan|ensure_ascii|separators|owner_customer_id|safe_projection|ABA|monotonic' docs/implementation/e2e01-thin-slice-implementation-spec.md >/dev/null</automated>
人工核对算法字节级唯一、fixed vector可复现，且模型/用户/Fixture/Runtime/Eval均不能成为authority。
  </verify>
  <done>
同一owner-scoped安全快照产生同一token、任一included field变化改变token；A→B→A非单调语义和out-of-scope触发条件明确。
  </done>
</task>

<task type="auto">
  <name>Task 2: Freeze outcome, exact-copy, compatibility and rollback matrix</name>
  <files>docs/implementation/e2e01-thin-slice-implementation-spec.md</files>
  <action>
把FOUND/NOT_FOUND_OR_NOT_ACCESSIBLE/SYSTEM_FAILURE的closed field与Observation/Manifest矩阵、Result→Observation→Manifest exact-copy链、fallback denylist、旧record/global Memory非影响及H/J/K下游ownership写入同一owner。不要修改任何consumer文件。
  </action>
  <verify>
    <automated>git diff --check 3f0753f7bef87fc02f314e28fe8b07860a819701...HEAD
rg -n 'FOUND|NOT_FOUND_OR_NOT_ACCESSIBLE|SYSTEM_FAILURE|source_version|byte-for-byte|fallback|stored_at|fixture_version|OrderObservation|ContextManifest|01-07H|01-07J|01-07K|rollback' docs/implementation/e2e01-thin-slice-implementation-spec.md >/dev/null
uv run pytest</automated>
人工核对外部不存在/越权仍不可区分、corruption不伪装成not-found、无第二次query或授权扩大。
  </verify>
  <done>
三类outcome、exact-copy和fail-closed边界唯一；global Memory/schema/migration/Agent-visible contract保持不变。
  </done>
</task>

</tasks>

<verification>

```bash
set -euo pipefail

base_sha=3f0753f7bef87fc02f314e28fe8b07860a819701
base_tree=b5214d3b7140ca305566a9cb802a21388a92464c
owned_file=docs/implementation/e2e01-thin-slice-implementation-spec.md
owned_blob=08d90f1b02d6e34c2ac333a96615258ce04f0797

test "$(git rev-parse "${base_sha}^{tree}")" = "$base_tree"
test "$(git rev-parse "${base_sha}:${owned_file}")" = "$owned_blob"
test "$(git merge-base HEAD "$base_sha")" = "$base_sha"
test "$(git rev-list --count "${base_sha}..HEAD")" -eq 1
test "$(git diff --name-only "${base_sha}...HEAD")" = "$owned_file"
git diff --check "${base_sha}...HEAD"

rg -n \
  'mock-order-source-version|source_version|sha256|861c136b|FOUND|NOT_FOUND_OR_NOT_ACCESSIBLE|SYSTEM_FAILURE|byte-for-byte|fallback|ABA|monotonic|01-07H|01-07J|01-07K' \
  "$owned_file"

rg -n \
  'source_version|order-observation.p0.v1|stored_at|fixture_version|ContextManifest|OrderObservation|GetOrderResult' \
  PROJECT_DIRECTION.md docs src tests evals

uv run pytest
```

Planning provenance、fixed-vector reproduction与latest-integration overlay另按`<packet_contract>`记录。任何required forbidden-file alignment、scope drift、test failure、算法不唯一、owner要求新增migration/global/external scope或unresolved `CRITICAL / HIGH / MEDIUM`都是`BLOCK`。
</verification>

<success_criteria>

1. Thin Slice owner形成可实现、可复现、owner-scoped且fail-closed的source-version裁决。
2. Feature branch相对固定base只有一个commit、一个changed file。
3. Core、Memory、Runtime、Infra、DB、ToolSpec、HTTP、Eval与lifecycle均保持未修改。
4. Feature与latest-integration overlay获得独立exact-head review，阻断finding为零。
5. C/G串行merge后才记录共同barrier并签发01-07D/01-07H。

</success_criteria>

<output>
完成后不创建Summary；Executor按`handoff_format`向Integrator交接。只有reviewed merge、post-merge gate和后续独立status PR才能把01-07G标记为`TASK_PACKET_COMPLETE / EVIDENCE_INDEXED`。
</output>
