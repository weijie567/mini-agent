---
phase: 01-cycle-1-e2e-01
plan: 07AA-ORACLE-FIX
type: tdd
wave: 26-remediation
depends_on:
  - 01-07Z
files_modified:
  - src/mini_agent/application/records.py
  - tests/component/application/test_record_contracts.py
autonomous: true
requirements:
  - E2E01-01
  - E2E01-04
user_setup: []
---

# Phase 1 Plan 01-07AA Oracle Fix｜RU-v2 normalized binding closure alignment

> **ISSUED QUALITY-GATE REMEDIATION / IMPLEMENTATION NOT STARTED**
> 本Packet修复既有Application closure validator与reviewed Z command的实现不一致；不新增execution-map Packet、不改变42分母、不实现AA writer、不形成`B_J_READY`或`B_ACTIVE`。

> **DERIVED / NON_NORMATIVE**
> canonical语义仍由Intent / Thin Slice以及reviewed 01-07Z拥有：durable candidate保留原始safe value，`InputBinding.normalized_value`保存确定性canonical order ID。此Packet只让现有`ExactRunEvidenceClosure`消费同一normalize规则。

<objective>
以TDD RED→GREEN关闭AA preflight暴露的Application oracle bug：合法Z graph中candidate value为`o-1001`、binding normalized value为`O-1001`，Z command已经按`_normalize_order_id`接受，但`ExactRunEvidenceClosure`错误地直接比较两者并拒绝，导致01-07K无法回读任何合法initial graph。

Output: Component RED证明`ExactRunEvidenceClosure`接受reviewed Z exact graph并拒绝真正normalized mismatch/invalid candidate；GREEN只在existing closure validator复用已有`_normalize_order_id`。不修改Core、Infrastructure、Runtime、codec、Port、migration、canonical docs或shared State。
</objective>

<execution_context>
@AGENTS.md
@.planning/GOVERNANCE.md
@.planning/phases/01-cycle-1-e2e-01/01-07Z-PLAN.md
@.planning/phases/01-cycle-1-e2e-01/01-07AA-PLAN.md
@docs/architecture/intent-design-reference.md
@docs/implementation/e2e01-thin-slice-implementation-spec.md
@src/mini_agent/application/records.py
@tests/component/application/test_record_contracts.py

只使用项目受控execution adapter；不得调用stock GSD lifecycle workflow。Graphify继续闲置：不读取、不运行、不更新。
</execution_context>

<interfaces>

## Confirmed contradiction

- `CreateInitialTaskGraphV2Command`在`records.py`已有reviewed规则：

```python
normalized_candidate_value = _normalize_order_id(
    candidate_input.candidate_value
)
binding.normalized_value == normalized_candidate_value
```

- 同文件`ExactRunEvidenceClosure`却使用：

```python
binding.normalized_value == expected_inputs[name].candidate_value
```

- 真实复现：用`_initial_v2_graph()`直接构造closure，现有validator返回`accepted child bindings must preserve validated input values`。writer尚未提交时即可复现，故`CONFIRMED`为Application oracle实现缺陷，不是PostgreSQL写入漂移。

## Exact repair

closure validator必须对每个expected candidate input调用同一个existing Core-owned `_normalize_order_id`，再与binding比较：

- lowercase / surrounding-space形式按既有normalizer形成canonical `O-...`并接受；
- binding仍须匹配name、authority和包含exact source ref；
- invalid candidate value在normalizer处fail closed，转换为现有bounded closure `ValueError`，不得保留raw value/exception context；
- already-canonical candidate行为不变；
- 不修改normalizer、Z command、DTO field、Port、codec、reader或writer。

Component test必须直接用reviewed `_initial_v2_graph()` family构造完整`ExactRunEvidenceClosure`，并覆盖：

- `o-1001 → O-1001`合法；
- already canonical合法；
- wrong normalized binding拒绝；
- invalid candidate拒绝且error不含raw input；
- candidate/binding authority、source ref等既有负例仍绿。

</interfaces>

<packet_contract>
repository: `https://github.com/weijie567/mini-agent`
remote: `origin`
head_branch: `codex/e2e01-01-ru-v2-closure-oracle-fix`
base_branch: `integration/e2e01-thin`
base_sha: `3d0d3d557960bbfd3267d321d485ad623f035924`
base_tree: `92af39bd07dc6821268e76abbdbfc208f38cd4d9`
worktree_id: `e2e01-01-ru-v2-closure-oracle-fix`
writer: `Application record-contract sole writer, supervised by /root Integrator`
agent_role: `runtime-engineer / Application-contract-only`
denominator_delta: `0`
active_routing: `false`

owned_files:

- `src/mini_agent/application/records.py`
- `tests/component/application/test_record_contracts.py`

owned_files_at_base:

- `src/mini_agent/application/records.py` = `a8448b3d57a4af7b8e72d5ae7de773382c1a320c`
- `tests/component/application/test_record_contracts.py` = `feb98df37ddea84f02864255e97a762e5cd0cf2a`

forbidden_files: `ALL REPOSITORY FILES OUTSIDE THE TWO-FILE ALLOWLIST`，尤其包括all Infrastructure/Core/Runtime/Eval、other tests、migration、docs、other `.planning/**`、project metadata、Graphify。

canonical_inputs:

- reviewed 01-07Z normalized InputBinding projection；
- Intent/Thin Slice raw safe candidate versus canonical binding distinction；
- existing `_normalize_order_id` implementation；
- `ExactRunEvidenceClosure` closed graph contract；
- observed AA focused failure: writer tests `10 passed, 2 failed`，两个失败均为K reader closure construction。

dependencies:

- 01-07Z exact command validator and builders；
- 01-07K exact reader consumes `ExactRunEvidenceClosure`；
- AA当前RED/GREEN donor branch仍源自exact `B_YZ=d704b874...`，但它的exact head因缺少本Application修复而不具备可接受性；本remediation reviewed merge后，Integrator必须用append-only AA Plan amendment把该merge冻结为AA replacement/replay acceptance base，再从该exact base新建clean AA feature并重放同一two-file RED→GREEN patch。禁止silent rebase、禁止把Application修复cherry-pick进AA allowlist、禁止把donor head送审或merge。

required_checks:

- `preflight`: exact repo/branch/worktree/base SHA/tree、clean、two blobs、single writer；预期PASS。
- `RED`: test-only commit，focused new regression non-zero且只因closure raw-vs-normalized direct comparison；source blob unchanged。
- `GREEN focused`: `uv run pytest tests/component/application/test_record_contracts.py -q`；预期exit 0、zero skip/xfail。
- `Z neighbors`: `uv run pytest tests/component/application/test_record_contracts.py tests/component/application/test_ports_contract.py -q`；预期exit 0。
- `AA composition sidecar`: 在AA feature patch overlay或等价temporary tree运行`uv run pytest tests/integration/test_postgres_v2_request_understanding_writes.py -q`；预期reader round-trip两项转绿且全部12项通过。
- `canonical environment/full`: `uv sync --all-groups`、healthy dev/test DB、`uv run alembic upgrade head`、`uv run pytest`；预期exit 0，既有credentialed deselection可保留。
- `containment`: diff-check、linear RED→GREEN、base→head changed-files精确2项、无contract/field/signature/normalizer漂移。
- `review/integration`: exact-head与latest-integration overlay分别独立`0/0/0/0 PASS`；reviewed overlay tree等于merge tree；post-merge gates通过。
- `AA acceptance-base handoff`: remediation merge SHA/tree固定后，先合并dedicated append-only AA Plan amendment，明确`original_input_barrier=B_YZ`、`acceptance_base_sha/tree=<remediation merge>`、原donor branch只作patch provenance；随后从replacement exact base创建clean AA feature。amendment未reviewed merge前AA保持`BLOCK`。

done_when:

- direct closure regression证明reviewed Z graph可构造且wrong/invalid值fail closed；
- source只将closure comparator对齐到existing normalizer；
- two-file containment、focused/neighbors/AA composition/Alembic/full全部通过；
- exact-head及latest-overlay独立PASS并串行merge；
- remediation merge只形成AA replacement-base候选，不形成`B_J_READY`；
- AA Plan amendment reviewed merge并授权replacement/replay base后，AA clean feature才可重放；原B_YZ donor不得送审或merge。

handoff_to: `/root Integrator`

handoff_format:

- base/head/tree/commits/branch/worktree；
- expected/actual changed-files与blob containment；
- RED、focused、neighbors、AA composition、Alembic、full命令/结果；
- exact-head/overlay reviewer、finding、verdict；
- contract/security/eval/cross-file impact、risks、rollback；
- PR/merge SHA/tree；AA amendment所需replacement-base字段与donor冻结状态；明确`denominator_delta=0`且不claim B_J_READY。

contract_changes: `NONE；实现对齐reviewed Z与existing normalizer。`
security_impact: `YES — fail-closed closure validation；raw invalid input不得进入error context。身份/owner范围不变。`
eval_impact: `YES — 修复K reader可消费合法RU-v2 initial graph的Component/Integration oracle；不推进Case lifecycle。`
rollback: `Revert remediation merge；撤销/作废任何引用该merge的AA replacement-base amendment与clean replay branch；AA的K-reader round-trip重新阻断，01-07AA不得merge或形成B_J_READY。`
</packet_contract>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: RED — freeze normalized candidate/binding closure contract</name>
  <files>tests/component/application/test_record_contracts.py</files>
  <action>append test直接用`_initial_v2_graph()`构造完整closure，覆盖raw lowercase→canonical binding、canonical、wrong与invalid/raw-free matrix。只提交test。</action>
  <verify><automated>uv run pytest tests/component/application/test_record_contracts.py -q</automated></verify>
  <done>失败只定位closure direct comparator。</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: GREEN — reuse canonical order-id normalizer in closure</name>
  <files>src/mini_agent/application/records.py</files>
  <action>在closure validator先bounded normalize expected candidate value，再做既有name/value/authority/source检查。不得修改其他owner surface。</action>
  <verify><automated>uv run pytest tests/component/application/test_record_contracts.py tests/component/application/test_ports_contract.py -q</automated></verify>
  <done>focused/neighbor与AA composition全部转绿。</done>
</task>

</tasks>
