---
phase: 01-cycle-1-e2e-01
plan: 07AA-CODEC-HANDOFF
type: remediation
wave: 26
depends_on:
  - 01-07Q
  - 01-07K
  - 01-07AA-ORACLE-FIX
files_modified:
  - tests/component/application/test_persistence_contract.py
autonomous: true
requirements:
  - E2E01-01
  - E2E01-04
user_setup: []
must_haves:
  truths:
    - "Q 的 codec dependency guard 必须从 pre-writer 状态收敛到只允许 01-07AA PostgreSQL exact-v2 writer chain 与其 01-07K authoritative reader oracle 使用显式 versioned codec；不得把许可扩大到 Runtime active routing。"
    - "PostgresRecordAdapter 中 versioned encoder 只能由 `_ru_v2_write_encode` 直接调用；versioned decoder 只能由 `load_exact_run_evidence_for_owner` 或 `_ru_v2_write_*` private chain 直接调用。"
    - "01-07AA Integration oracle 可以直接调用 exact reader，并只为构造 bounded wrong-owner fixture 直接调用 versioned encoder；该测试文件不成为 codec owner、active registry owner 或 Runtime authority。"
    - "remediation exact feature 自身与叠加 frozen 01-07AA-r1 patch 的 sidecar 都必须通过 dependency guard；只有后者证明 01-07AA 可以从 remediation merge replay，不能把 sidecar 当成 reviewed feature 或 B_J_READY。"
    - "本 Packet 不修改 codec、Application Port、PostgreSQL Adapter、Runtime、migration、Eval、canonical docs 或 active routing。"
  artifacts:
    - "tests/component/application/test_persistence_contract.py 中 scoped codec dependency guard。"
  key_links:
    - "01-07Q active codec registry → scoped dependency guard → 01-07AA exact-v2 PostgreSQL writer。"
    - "01-07K exact reader → 01-07AA authoritative post-commit oracle。"
    - "reviewed B_AA_CODEC_HANDOFF → 后续独立 acceptance-base amendment → 01-07AA-r2 replay。"
---

# Phase 1 Plan 01-07AA-CODEC-HANDOFF｜RU-v2 writer codec dependency guard remediation

> **ISSUED QUALITY-GATE REMEDIATION / IMPLEMENTATION NOT STARTED**
> 本 Packet 只修复 Q 阶段遗留的 dependency guard。Plan、remediation feature 或 sidecar 均不表示 01-07AA 已 reviewed、`B_J_READY` 已形成、01-07J 已切换、Case/E2E 已通过或产品 ready。

> **DERIVED / NON_NORMATIVE**
> Codec 语义服从 Application persistence owner，exact reader 服从 01-07K，writer 语义服从 01-07AA 与 Memory owner。本 Plan 只拥有单个 Component contract guard 文件，不创建第二套 codec、reader 或 writer contract。

<objective>
解除 01-07AA exact-v2 writer 被 Q 的 pre-writer dependency catalog 机械阻断的问题，同时把新增许可限制在既有 exact reader、AA private writer chain 和 AA Integration oracle 内。

已确认的 RED 证据：

- frozen 01-07AA-r1 exact head `5345e70e696942e3b7d4eaed59eaa39b5e258458` / tree `790564947a929ec7624974f784127b84d435ed68`；
- focused writer tests `12 passed`，相邻 PostgreSQL regression `111 passed`；
- canonical full suite `1 failed, 1961 passed, 1 deselected`；
- 唯一首个失败为 `test_codec_active_switch_has_no_runtime_or_authority_claim`，它拒绝 `src/mini_agent/infrastructure/persistence/postgres.py` 和 `tests/integration/test_postgres_v2_request_understanding_writes.py` 的 01-07AA 明文依赖；
- 01-07AA reviewed Plan 又明确要求 writer 全链调用 `encode_persistence_record_versioned` / `decode_persistence_record_versioned`，并要求 01-07K `load_exact_run_evidence_for_owner` 作为成功 oracle，因此不能通过 alias、dynamic lookup、raw SQL、legacy helper 或删除 oracle 绕过该 guard。

Output：一个只修改 Component contract test 的 remediation feature；reviewed merge 形成 `B_AA_CODEC_HANDOFF`。随后另行签发 acceptance-base amendment，从该 exact barrier 创建 01-07AA-r2 并 fresh replay frozen r1 commits。原 r1 branch/worktree 只保留 donor provenance，不 push、不送审、不 merge。
</objective>

<execution_context>
@AGENTS.md
@.planning/GOVERNANCE.md
@.planning/phases/01-cycle-1-e2e-01/01-07Q-PLAN.md
@.planning/phases/01-cycle-1-e2e-01/01-07K-PLAN.md
@.planning/phases/01-cycle-1-e2e-01/01-07AA-PLAN.md
@src/mini_agent/application/persistence.py
@src/mini_agent/application/ports.py
@src/mini_agent/infrastructure/persistence/postgres.py
@tests/component/application/test_persistence_contract.py
@tests/component/application/test_ports_contract.py
@tests/integration/test_postgres_record_adapters.py
@tests/integration/test_postgres_v2_request_understanding_writes.py

只使用项目受控 execution adapter；不得调用 stock GSD lifecycle mutation。Graphify 按用户指令保持闲置：不读取、不运行、不更新，也不作为 gate。
</execution_context>

<interfaces>

## 1. Guard 语义演进

将现有 `test_codec_active_switch_has_no_runtime_or_authority_claim` 重命名为能准确表达当前阶段的 dependency-scope guard，例如：

```python
test_codec_dependencies_are_scoped_without_active_routing_or_authority_claim
```

该测试仍须证明：

- `P0_RECORD_SCHEMA_VERSION_CATALOG`、`P0_PERSISTENCE_REGISTRY` owner 集合不扩大；
- active RU pair 仍是 `request_understanding_record.p0.v2`，其他 16 个 active pair 与 legacy-v1 registry 保持原语义；
- decoded codec output 不携带 authorization、owner graph、business fact、PostgreSQL routing、active routing 或 readiness claim；
- Runtime / Core / provider / HTTP / Eval 文件不能引用 versioned codec 来宣称 active route。

只更新 dependency allow-set：

| symbol family | 新增允许文件 | 精确用途 |
|---|---|---|
| `encode_persistence_record_versioned` | `src/mini_agent/infrastructure/persistence/postgres.py` | 仅 `_ru_v2_write_encode` 直接调用 |
| `encode_persistence_record_versioned` | `tests/integration/test_postgres_v2_request_understanding_writes.py` | 仅构造 bounded wrong-owner fixture |
| `decode_persistence_record_versioned` | 无新文件；`postgres.py` 已在 allow-set | 在既有 exact reader 外，只允许 `_ru_v2_write_*` private chain |
| `load_exact_run_evidence_for_owner` | `tests/integration/test_postgres_v2_request_understanding_writes.py` | 只作为 AA 成功 / 并发 closure oracle |

不得把目录、glob、任意 `tests/integration`、Runtime module 或新的 generic helper 加入 allow-set。

## 2. PostgreSQL AST containment

Guard 必须对 `src/mini_agent/infrastructure/persistence/postgres.py` 做 AST containment：

- versioned encoder / decoder 都只能使用无 alias 的 direct import；
- 禁止 module attribute、dynamic import、`getattr`、name alias 或 callable transfer；
- 每个 encoder `Name` reference 必须是 direct `Call.func`，其 enclosing class 必须为 `PostgresRecordAdapter`，enclosing function 必须精确为 `_ru_v2_write_encode`；
- 每个 decoder `Name` reference 必须是 direct `Call.func`，其 enclosing class 必须为 `PostgresRecordAdapter`，enclosing function必须是 `load_exact_run_evidence_for_owner` 或以 `_ru_v2_write_` 开头的 private method；
- 除 import definition 与上述 direct call 外不得出现额外 reference。

在 remediation feature exact base 尚无 AA writer 时，encoder 可以在 `postgres.py` 中不存在；guard 必须同时支持“尚未 replay”与“AA patch 已叠加”两种状态，但不能因此取消 AST 限制。

## 3. Integration oracle containment

Guard 对 `tests/integration/test_postgres_v2_request_understanding_writes.py` 只做 named-file dependency许可，不把它提升为 owner。AA exact-head review 仍须对该文件逐项确认：

- exact reader 仅用于成功、replay或并发后的 authoritative closure assertion；
- direct versioned encode 仅用于构造 wrong-owner metadata/envelope fixture；
- 测试不得引用 active registry、catalog owner 或 Runtime active-routing symbol；
- 测试不得通过 dynamic lookup 规避 dependency guard。

## 4. Composition sidecar

在 remediation feature exact head 之外，Integrator 必须创建 detached disposable sidecar：

1. base 为 remediation feature exact head；
2. 依次应用 frozen r1 RED `fbc91d1a658ba3506749907502b624e8ed6e30dd` 与 GREEN `5345e70e696942e3b7d4eaed59eaa39b5e258458` 的净 patch，或验证 cumulative stable patch-id 等价；
3. changed files 必须精确为：
   - `tests/component/application/test_persistence_contract.py`（remediation feature）；
   - `src/mini_agent/infrastructure/persistence/postgres.py`（AA overlay）；
   - `tests/integration/test_postgres_v2_request_understanding_writes.py`（AA overlay）；
4. 运行 renamed dependency guard、AA focused tests、Application contract tests、相邻 PostgreSQL regression 与 canonical full suite；
5. sidecar 不 commit、不 push、不创建 PR，也不形成 product barrier。

</interfaces>

<packet_contract>
repository: `https://github.com/weijie567/mini-agent`
remote: `origin`
head_branch: `codex/e2e01-01-ru-v2-codec-handoff`
base_branch: `integration/e2e01-thin`
base_sha: `dc21e906183647c9fdf9aeffa47f256ad1a823ae`
base_tree: `18701f31b96f7bfc04e6bb45152e22981c3f14df`
input_barrier: `B_AA_ACCEPTANCE_PLAN = dc21e906183647c9fdf9aeffa47f256ad1a823ae`
output_barrier: `B_AA_CODEC_HANDOFF / ONLY AFTER EXACT-HEAD AND LATEST-INTEGRATION OVERLAY REVIEWED-SERIAL-MERGED`
worktree_id: `e2e01-01-ru-v2-codec-handoff`
writer: `Application persistence Component contract guard sole writer, supervised by /root Integrator`
agent_role: `runtime-engineer`
active_routing: `false`
denominator_delta: `0`

owned_files_at_base:

- `tests/component/application/test_persistence_contract.py` = `1aa3064c88669acf4af3a1e436dc7f24921e0cfe`

owned_files:

- `tests/component/application/test_persistence_contract.py`

allowlist:

- `tests/component/application/test_persistence_contract.py`

forbidden_files:

- `src/mini_agent/application/persistence.py`
- `src/mini_agent/application/ports.py`
- `src/mini_agent/application/records.py`
- `src/mini_agent/core/**`
- `src/mini_agent/infrastructure/persistence/postgres.py`
- `src/mini_agent/infrastructure/persistence/models.py`
- `src/mini_agent/runtime/**`
- `src/mini_agent/evaluation/**`
- `tests/integration/test_postgres_v2_request_understanding_writes.py`
- `tests/integration/test_postgres_record_adapters.py`
- `tests/component/application/test_ports_contract.py`
- `alembic/**`
- `docs/**`
- `.planning/**`
- `pyproject.toml`
- `uv.lock`
- `AGENTS.md`

dependencies:

- exact base `dc21e906183647c9fdf9aeffa47f256ad1a823ae`
- 01-07Q active codec registry and guard
- 01-07K exact reader implementation
- reviewed 01-07AA Plan plus frozen unpushed r1 donor
- canonical PostgreSQL and full-suite test database

canonical_inputs:

- `AGENTS.md`：项目级 evidence、security、allowlist、Worktree、review 与 merge 纪律；
- `docs/architecture/memory-design-reference.md`：exact owner closure、atomic persistence 与 replay owner；
- `docs/implementation/e2e01-thin-slice-implementation-spec.md`：E2E01-01/04 scoped implementation owner；
- `docs/implementation/e2e01-thin-slice-multi-agent-plan.md`：01-07Q/K/AA ownership、执行顺序与 `B_J_READY` barrier owner；
- `.planning/phases/01-cycle-1-e2e-01/01-07Q-PLAN.md`：active codec registry 与当前 pre-writer dependency guard provenance；
- `.planning/phases/01-cycle-1-e2e-01/01-07K-PLAN.md`：`load_exact_run_evidence_for_owner` scoped reader contract；
- `.planning/phases/01-cycle-1-e2e-01/01-07AA-PLAN.md`：writer exact-version chain、reader oracle、frozen donor 与 acceptance replay contract；
- exact base `dc21e906183647c9fdf9aeffa47f256ad1a823ae` 和 owned-file blob `1aa3064c88669acf4af3a1e436dc7f24921e0cfe`。

required_checks:

```bash
uv sync --all-groups
docker compose up --wait -d db
docker compose --profile test up --wait -d db-test
uv run alembic upgrade head
uv run pytest tests/component/application/test_persistence_contract.py::test_codec_dependencies_are_scoped_without_active_routing_or_authority_claim -q
uv run pytest tests/component/application/test_persistence_contract.py tests/component/application/test_ports_contract.py -q
uv run pytest
```

- precheck：branch/worktree/base SHA/tree/owned blob 精确相等且 worktree clean；
- postcheck：changed files 精确等于单文件 allowlist，无 forbidden file、merge commit、skip/xfail 或 whitespace error；
- expected feature result：renamed guard、Application contracts、Alembic 与 canonical full suite 全部通过；
- expected composition result：frozen AA patch sidecar 的 renamed guard、12 个 AA focused tests、111 个相邻 regression 与 canonical full suite 全部通过；
- review result：feature exact head 与 latest-integration overlay 均为独立 `PASS`，所有 P0/P1/P2/P3 finding 已关闭或由 Integrator 显式阻断。

composition_sidecar_commands:

```bash
uv run pytest tests/component/application/test_persistence_contract.py::test_codec_dependencies_are_scoped_without_active_routing_or_authority_claim tests/integration/test_postgres_v2_request_understanding_writes.py -q
uv run pytest tests/integration/test_postgres_v2_request_understanding_writes.py tests/integration/test_postgres_atomicity.py tests/integration/test_postgres_record_adapters.py -q
uv run pytest
```

contract_changes:

- `YES`：Q 的 pre-writer dependency catalog 追加 scoped 01-07AA writer / oracle 消费者；codec pair、registry owner、authorization、active routing 与 readiness 语义不变。

security_impact:

- `YES / FAIL-CLOSED`：AST guard 阻止 versioned codec 许可扩散到 Runtime 或动态调用；owner/authority 仍由 deterministic PostgreSQL writer 与 exact reader 验证，不由 codec output 授予。

eval_impact:

- `NONE`：不修改 Eval owner、Case、Dataset、Grader、threshold 或报告。

rollback:

- merge 前丢弃 feature branch/worktree；
- merge 后 revert exact remediation merge；
- 不回退 Q、K 或任何已 reviewed product barrier；
- 01-07AA-r2 未形成前继续冻结 r1 donor，不发布半完成 writer。
- 若 acceptance-base amendment branch/PR 已创建但未 merge，关闭 PR 并将其标记为 superseded；不得继续签发 r2。
- 若 amendment 已 merge但 r2 尚未 merge，使用普通 revert PR 撤销 amendment，关闭/作废 r2 branch 与 PR，并撤销 `B_AA_CODEC_HANDOFF` 可供 AA replay 的 claim。
- 若 r2 或后续 `B_J_READY` 已形成，先阻断 01-07J 与所有下游 merge，分别以普通 revert PR 按逆序撤销下游 AA/J merge 与本 remediation；同步撤销 `B_J_READY` / `B_ACTIVE` claim，并重新从最后一个 reviewed unaffected barrier 裁决，禁止 destructive reset 或 force push。

done_when:

- 单文件 guard remediation 在 exact feature head 与 frozen AA composition sidecar 上满足全部 `required_checks`；
- exact-head 与 latest-integration overlay independent review 均为 `PASS`；
- feature draft PR 串行 merge 后 post-merge canonical gate通过并记录 exact merge SHA/tree；
- handoff 明确只命名 `B_AA_CODEC_HANDOFF`，并阻止在另一个 reviewed acceptance-base amendment 前创建 01-07AA-r2。

handoff_to:

- `/root Integrator`：负责 exact-head review、latest-integration overlay、draft PR 串行 merge、post-merge gate 与 `B_AA_CODEC_HANDOFF` 记录；
- 后续独立 planning-status Packet：只负责把 reviewed remediation merge 冻结为 01-07AA-r2 exact acceptance base，不得复用本 Plan 或 Plan merge替代 feature base。

handoff_format:

- branch / exact head / tree / commit subjects；
- actual changed files 与 allowlist containment；
- guard AST 许可集合；
- exact feature verification；
- frozen AA patch composition sidecar verification；
- exact-head reviewer findings `P0/P1/P2/P3`；
- latest-integration overlay head/tree/patch equivalence与 reviewer verdict；
- PR URL、merge SHA/tree；
- `contract_changes` / `security_impact` / `eval_impact`；
- 未执行项、未决风险与 rollback。

</packet_contract>

<tasks>

<task type="auto">
  <name>Task 1: RED — 冻结 pre-writer guard 对合法 01-07AA composition 的阻断</name>
  <files>tests/component/application/test_persistence_contract.py</files>
  <action>
先以 frozen 01-07AA-r1 composition sidecar 复现 dependency guard 失败，并记录 exact failing symbol/file。不得为制造 RED 修改产品代码、AA donor 或 shared bootstrap；不得把 raw SQL / dynamic lookup workaround 当修复。
  </action>
  <verify>
目标 guard 在未修复 sidecar 上因 scoped AA dependencies 被拒绝而失败，其他 AA focused tests保持通过。
  </verify>
  <done>RED 精确证明 guard 的阶段状态落后于 reviewed AA contract。</done>
</task>

<task type="auto">
  <name>Task 2: GREEN — 收窄允许 writer / reader oracle 的 dependency catalog 与 AST</name>
  <files>tests/component/application/test_persistence_contract.py</files>
  <action>
按 Interfaces 更新 guard 名称、exact allow-set 与 Postgres AST containment。不得修改 codec、reader、writer、Runtime、integration tests或active registry；不得使用目录级或通配许可。
  </action>
  <verify>
feature exact base 的 renamed guard、Application contracts与full suite通过；composition sidecar 的 renamed guard、AA focused / neighbor / full suite也通过。
  </verify>
  <done>pre-writer guard 演进为 scoped writer-ready guard，且未形成 active-routing claim。</done>
</task>

</tasks>

<verification>

- exact base SHA/tree 与 Plan 一致；
- changed files 精确等于单文件 allowlist；
- 无 merge commit、无 forbidden file、无 skip/xfail；
- renamed guard 在 feature exact head 与 frozen AA composition sidecar 均通过；
- exact-head independent review 为 `PASS`；
- latest-integration overlay 保持 patch-id / synthetic tree 等价并经第二位 reviewer `PASS`；
- merge 后 canonical full suite通过，才命名 `B_AA_CODEC_HANDOFF`；
- 随后必须另行 reviewed acceptance-base amendment，不能直接把旧 r1 送审或 merge。

</verification>

<success_criteria>

1. Q 的 codec owner / active registry / authority不变量保持。
2. 01-07AA writer 的显式 versioned encode/decode与 01-07K reader oracle 被精确允许。
3. Runtime/Core/provider/HTTP/Eval 未获得 versioned codec active-routing许可。
4. feature exact 与 frozen AA composition sidecar 机械门禁均通过。
5. remediation reviewed merge 后只形成 `B_AA_CODEC_HANDOFF`，不冒充 `B_J_READY`。

</success_criteria>
