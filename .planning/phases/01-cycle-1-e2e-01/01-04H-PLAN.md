---
phase: 01-cycle-1-e2e-01
plan: 04H
type: tdd
wave: 9
depends_on:
  - 01-04G
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
    - "The normative Application Port contract defines a normal COMPLETED Run as authoritative only when one conditional aggregate advances Task/RequestUnit, records TaskStateChanged, persists ASSISTANT Message and mandatory RunStopped, and closes RunTaskLink; the exact AgentRunResult is a validated command/return binding, not a new persistence item. This Packet does not prove a physical transaction."
    - "A FAILED Run has no user-visible terminal result, ASSISTANT Message or terminal Trace projection in this command; the Thin Slice owner clarification shipped by the prerequisite planning-status PR explicitly permits that first-slice exception instead of fabricating a stop reason or user outcome."
    - "The command validates every cross-record identity and semantic projection before an Adapter is invoked."
    - "For a compliant Adapter, APPLIED normatively means the complete terminal turn committed, while PROJECTION_CONFLICT and NOT_APPLICABLE mean none of it committed; physical proof is transferred to 01-06R."
    - "Post-commit best-effort Message or mandatory Trace writes cannot satisfy this contract."
    - "The four-file owner Packet changes no canonical product semantics, Trace vocabulary, persistence registry, codec, table or migration; it consumes the scoped FAILED/RunStopped clarification already merged by its prerequisite planning-status PR."
  artifacts:
    - "FinalizeRunCommand carries the optional exact Task transition, completed result, ASSISTANT Message and closed terminal Trace set under a terminal-mode matrix."
    - "RuntimeRecordPort documents one atomic terminal-turn conditional write."
    - "Application contract tests reject missing, partial, foreign, mismatched and contaminated terminal projections."
  key_links:
    - "terminal_result.run_id equals terminal_record.run_id."
    - "assistant_message binds terminal_record.conversation_id and terminal_result.message."
    - "TaskStateChanged binds the nested Task/RequestUnit transition; RunStopped binds terminal_record.run_id/stop_reason/completed_at and terminal_result.outcome."
    - "Task/RequestUnit/transition, terminal Run/link, Message and terminal Trace are all-or-nothing."
---

<objective>
关闭 PR #28 exact-head review 暴露的 Application contract expressibility gap：当前 Port contract允许 Runtime先提交 `Run(COMPLETED)`，再丢失 `ASSISTANT Message` 或最低必需 `RunStopped`，却仍返回成功。01-04H只让这种partial success对compliant caller / Adapter不可表达；真实Runtime crash path与PostgreSQL rollback仍分别由尚未签发的01-05R / 01-06R关闭并验证。

Purpose: 消费 Memory owner 已冻结的 Conversation 原始消息可靠性与 Thin Slice 已冻结的 Task 状态及最低 Trace 语义，在 Application Port 层补齐一个不可表达 partial success 的 terminal-turn aggregate contract。仅把 Message/RunStopped 加到旧 finalization 仍不充分，因为旧 Runtime 在 finalization 前已单独提交 Task/RequestUnit；本 Packet 必须把该状态迁移一并纳入同一命令。

Output: 两个 Application contract 文件和两个既有 Component contract tests；不实现 Runtime orchestration、PostgreSQL transaction、HTTP、Composition Root、Eval 或 migration。
</objective>

<execution_context>
@AGENTS.md
@.planning/GOVERNANCE.md
@docs/architecture/memory-design-reference.md
@docs/implementation/e2e01-thin-slice-multi-agent-plan.md
@src/mini_agent/application/records.py
@src/mini_agent/application/ports.py
@src/mini_agent/core/trace.py
@tests/component/application/test_record_contracts.py
@tests/component/application/test_ports_contract.py

本 Plan 使用受控 GSD planner / checker adapter。Stock `gsd-plan-phase`、`gsd-execute-phase`、自动 lifecycle mutation 与 GSD 自管 Worktree 均保持禁用。Execution base 固定为本 Plan 编写前已验证的 official integration SHA `ea0a72fdac597a9ae78b2ed6fa34d14ef2c1eb57`；planning-status PR 必须先合并，但不得把未来 merge SHA 留作 `base_sha` 占位符或静默改写本 Packet。Integrator 在 execution preflight 另行记录40位 `PLANNING_CONTRACT_SHA`，它必须等于planning PR合并后的official `origin/integration/e2e01-thin`；Executor必须用 `git show "${PLANNING_CONTRACT_SHA}:.planning/phases/01-cycle-1-e2e-01/01-04H-PLAN.md"` 和 `git show "${PLANNING_CONTRACT_SHA}:docs/implementation/e2e01-thin-slice-implementation-spec.md"` 读取merged Plan与canonical clarification，不能用execution base checkout里的旧Spec替代。
</execution_context>

<task_packet>
repository: `https://github.com/weijie567/mini-agent`
remote: `origin`
head_branch: `codex/e2e01-01-terminal-turn-contract`
base_branch: `integration/e2e01-thin`
base_sha: `ea0a72fdac597a9ae78b2ed6fa34d14ef2c1eb57`
worktree_id: `e2e01-01-terminal-turn-contract`
worktree_path: `/Users/ming/projects/mini-agent-worktrees/e2e01-01-terminal-turn-contract`
writer: `Application terminal-turn contract sole writer, supervised by /root Integrator`
agent_role: `runtime-engineer`

owned_files:

- `src/mini_agent/application/records.py`
- `src/mini_agent/application/ports.py`
- `tests/component/application/test_record_contracts.py`
- `tests/component/application/test_ports_contract.py`

forbidden_files:

- every repository path not listed in `owned_files`
- `AGENTS.md`
- `PROJECT_DIRECTION.md`
- `README.md`
- `.planning/**`
- `docs/**`
- `src/mini_agent/application/persistence.py`
- `src/mini_agent/core/**`
- `src/mini_agent/infrastructure/**`
- `src/mini_agent/evaluation/**`
- every other test file
- `evals/**`
- `alembic/**`
- `pyproject.toml`
- `uv.lock`
- `compose.yaml`
- `graphify-out/**`

canonical_inputs:

- `AGENTS.md` sections 0–8 and graphify
- `.planning/GOVERNANCE.md` Task Packet, lifecycle and post-merge Graphify gates
- `PROJECT_DIRECTION.md` Application/Core Port ownership
- `docs/architecture/memory-design-reference.md` sections 7 and 12.3
- `docs/implementation/e2e01-thin-slice-implementation-spec.md` sections 10.1、10.3 and 11 from the exact `PLANNING_CONTRACT_SHA` blob, not the older execution-base working tree
- current exact `AgentRunResult`, `MessageRecord`, `AgentRunRecord`, `TraceEvent`, `RunTaskLinkRecord` and `TaskRecord` contracts

dependencies:

- PR #28 review finding at exact head `a27141ba902015af34602fe15eeec4ba44482687` is the RED evidence; the old Runtime branch is not an implementation base for this owner Packet
- PR #30 current Adapter remains a consumer and must not write shared Application contracts
- planning-status PR containing this Plan and the scoped Thin Slice FAILED/RunStopped clarification must merge first
- execution still starts from exact `base_sha=ea0a72fdac597a9ae78b2ed6fa34d14ef2c1eb57`; Integrator records the exact 40-hex `PLANNING_CONTRACT_SHA`, merged Plan blob SHA and merged Thin Slice Spec blob SHA, proves both blobs resolve from that commit, and proves the four owned paths are byte-identical between `base_sha` and `PLANNING_CONTRACT_SHA`
- no replacement Runtime/Infra implementation may start under the historical 01-05/01-06 Packets; after this Packet merges, Integrator must issue a separate exact-base 01-05R Packet, and only after Runtime merges may it issue a separate exact-base 01-06R Packet

required_checks:

- exact base/branch/merge-base/clean-worktree preflight plus `PLANNING_CONTRACT_SHA` official-ref equality, Plan/Thin-Slice blob resolution and four-owned-file byte identity
- RED contract tests prove `FinalizeRunCommand` currently accepts a COMPLETED Run without result, ASSISTANT Message or RunStopped
- GREEN adds a closed COMPLETED/FAILED terminal-mode matrix and exact field-surface tests
- exact identity/content/outcome/reason/timestamp/projection validation
- Port docs require APPLIED all-or-nothing and non-APPLIED zero writes
- focused Application contract tests
- full serial offline test suite
- exact-file `compileall`, `git diff --check` and changed-file containment; Ruff is not a required gate because the repository has no pinned or canonical Ruff entry point
- exact four-file containment and repository cross-file impact scan
- independent current-head contract/security review
- post-merge Integrator-only `graphify update .`, graph structural/freshness gate and clean tracked tree

done_when:

- exact four-file Packet has auditable RED and GREEN commits, one reviewed feature head and a PR to `integration/e2e01-thin`
- the command cannot represent COMPLETED without the complete terminal turn
- Port contract明确把返回APPLIED却延后Message或mandatory Trace写入定义为non-compliant；physical Adapter rollback证据仍BLOCK于未来01-06R
- focused/full/mechanical/containment checks pass
- merge and post-merge Graphify evidence are recorded
- downstream Runtime/Infra remain blocked until their own later exact-base replacement Packets are published; that downstream issuance is not part of this Packet's completion
- no Case, Requirement or numbered Phase lifecycle advances

contract_changes: `YES / APPLICATION TERMINAL-TURN ATOMICITY` — consumes the planning prerequisite's scoped Thin Slice clarification; the writer does not modify canonical docs.
security_impact: `YES / CONTRACT MITIGATION ONLY` — removes the Application contract's ability to represent partial success; the physical repudiation/crash window remains blocked until separately issued 01-05R Runtime and 01-06R Infra prove consumption and rollback.
eval_impact: `YES / CONTRACT PREREQUISITE` — later Trajectory/E2E grading can require one durable terminal result/Message/RunStopped projection; this Packet creates no Eval result.
graphify_disposition: `INTEGRATOR POST-MERGE GATE` — writer does not modify `graphify-out/**`; Integrator refreshes and verifies the graph only after merge.
rollback: Close before merge or use a normal revert PR and keep W2 integration blocked. Never reset, force-push, delete shared Worktrees or rewrite history.

handoff_to: `/root Integrator`

handoff_format:

- branch, exact base/`PLANNING_CONTRACT_SHA`/head/commit/tree plus Plan and Thin Slice blob SHAs
- exact four-file containment
- RED/GREEN commands and terminal-mode validator matrix
- Port APPLIED/non-APPLIED atomicity contract and explicit Adapter/Runtime nonclaims
- focused/full/mechanical results, contract/security/Eval impact and cross-file scan
- independent exact-head review, post-merge Graphify disposition, unresolved risks and rollback
</task_packet>

<interfaces>

Extend the existing `FinalizeRunCommand`; do not create a second terminal Port:

```python
task_transition: ApplyTaskTransitionCommand | None = None
terminal_result: AgentRunResult | None = None
assistant_message: MessageRecord | None = None
terminal_trace_events: Annotated[
    tuple[TraceEvent, ...],
    Field(max_length=2),
] = ()
```

For `terminal_record.status is COMPLETED`, the result, Message and exact terminal Trace set are required. The command accepts only the following closed P0 matrix:

| `StopReason` | Task/link present | `AgentOutcome` | next Task / RequestUnit status |
|---|---:|---|---|
| `GOAL_COMPLETED` | yes | `COMPLETED` | `COMPLETED` |
| `NOT_FOUND_OR_NOT_ACCESSIBLE` | yes | `NOT_FOUND_OR_NOT_ACCESSIBLE` | `COMPLETED` |
| `PROVIDER_PROTOCOL_ERROR` | no | `BLOCKED` | n/a |
| `PROVIDER_PROTOCOL_ERROR` | yes | `BLOCKED` | `BLOCKED` |
| `INPUT_INVALID` | no | `BLOCKED` | n/a |
| `GATE_REJECTED` | yes | `BLOCKED` | `BLOCKED` |
| `ORDER_SERVICE_UNAVAILABLE` | yes | `BLOCKED` | `BLOCKED` |
| `PRESENTATION_PLAN_REJECTED` | yes | `BLOCKED` | `BLOCKED` |
| `RENDERER_INVARIANT_FAILED` | yes | `BLOCKED` | `BLOCKED` |

`PROCESS_RESTART_DETECTED`, `ASK_USER`, `NEED_HUMAN`, every matrix cross-product not listed above, and every Task status other than the listed terminal status are rejected. The accepted rows must also satisfy:

- `terminal_result.run_id == terminal_record.run_id`;
- `terminal_record.conversation_id` is present;
- `assistant_message.schema_version == "message_record.p0.v1"`;
- `assistant_message.direction is MessageDirection.ASSISTANT`;
- `assistant_message.conversation_id == terminal_record.conversation_id`;
- `assistant_message.content == terminal_result.message`;
- `assistant_message.received_at == terminal_record.completed_at`;
- `terminal_trace_events` contains exactly one `RunStopped`, bound to `terminal_record.run_id/stop_reason/completed_at` and `terminal_result.outcome`;
- when the Run has no Task/link, `task_transition is None`, `result_task_records` is empty and `terminal_trace_events` contains only `RunStopped`;
- when the Run has one Task/link, `task_transition` is required, its expected/next Task identity equals the link Task, its next Task / RequestUnit have the same terminal `COMPLETED` or `BLOCKED` status/version, `result_task_records` is exactly its next Task, and `terminal_trace_events` is ordered exactly as `(TaskStateChanged, RunStopped)`;
- `TaskStateChanged.run_id == terminal_record.run_id`, and it binds the nested transition Task/RequestUnit identity and `changed_at`; `task_transition.changed_at <= terminal_record.completed_at`;
- `TaskStateChanged` allows only common `trace_event_id/event_type/occurred_at/run_id` plus `task_id/request_unit_id`;
- `RunStopped` allows only common `trace_event_id/event_type/occurred_at/run_id` plus `user_outcome/stop_reason`;
- every unrelated optional Trace projection remains at its canonical empty default, Trace identities are unique, `TaskStateChanged.occurred_at == task_transition.changed_at`, and `RunStopped.occurred_at == terminal_record.completed_at`.

For `terminal_record.status is FAILED`, `task_transition`, `terminal_result`, `assistant_message` and `terminal_trace_events` must all be empty. This path represents the Thin Slice §10.3 uncaught Web/process failure clarified by the prerequisite canonical owner change: it must not fabricate a stop reason, user outcome, Task transition, user-visible result or `RunStopped`. It may still bind the exact current already-persisted Task projection to close an active RunTaskLink, and the terminal link version must equal that unchanged Task version.

Existing exact Run/link/result-Task validation remains in force. `RuntimeRecordPort.finalize_run_if_active` outcome semantics become:

```text
APPLIED
  → exact active Run/link/Task/RequestUnit preconditions matched
  → terminal_result validated as the exact return/message/Trace binding
  → Task/RequestUnit/transition + terminal Run/link + ASSISTANT Message
    + exact terminal Trace committed in one transaction

PROJECTION_CONFLICT | NOT_APPLICABLE
  → zero Task/RequestUnit/transition or terminal Run/link writes
  → zero Message writes
  → zero Trace writes
```

No new persistence item is introduced. The existing 17-item registry already contains `MessageRecord`, `AgentRunRecord`, `RunTaskLinkRecord`, `TaskRecord` and `TraceEventRecord`; physical implementation belongs to the future, separately issued 01-06R Packet.
</interfaces>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: RED — prove the current finalization contract permits a partial terminal turn</name>
  <files>tests/component/application/test_record_contracts.py, tests/component/application/test_ports_contract.py</files>
  <read_first>AGENTS.md; the Plan and docs/implementation/e2e01-thin-slice-implementation-spec.md resolved with `git show` from the recorded exact `PLANNING_CONTRACT_SHA`; local source/test files at execution base: src/mini_agent/application/records.py, src/mini_agent/application/ports.py, src/mini_agent/core/trace.py, tests/component/application/test_record_contracts.py, tests/component/application/test_ports_contract.py</read_first>
  <action>Add contract tests for every accepted row in the closed matrix and directed negative tests for illegal reason/outcome/Task/status cross-products, missing or extra Task transition, foreign Task/RequestUnit/Run/Conversation, USER message direction, altered content, wrong timestamps, missing/duplicate/extra terminal events, per-kind Trace contamination and any new projection on FAILED. Preserve existing Run/link/result-Task closure and public field-surface assertions. Run the focused command before source changes and record RED because the current command permits COMPLETED finalization without the complete result/Message/Trace aggregate.</action>
  <verify>
    <automated>uv run pytest tests/component/application/test_record_contracts.py tests/component/application/test_ports_contract.py -x</automated>
    Before GREEN source changes this command must exit non-zero on the newly asserted terminal-turn contract; record the directed failure and prove it is not a malformed fixture.
  </verify>
  <acceptance_criteria>
    - RED is caused by the absent aggregate fields or validators, not by a malformed fixture
    - all nine accepted COMPLETED rows and representative rejected cross-products are explicit
    - `TaskStateChanged.run_id`, timestamps and exact per-kind field allowlists are asserted
    - FAILED preserves existing Run/link closure while rejecting all four new projections
  </acceptance_criteria>
  <done>The post-commit Message/RunStopped loss and pre-finalization Task transition are mechanically shown to be representable by the old API.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: GREEN / REFACTOR — freeze one atomic terminal-turn command</name>
  <files>src/mini_agent/application/records.py, src/mini_agent/application/ports.py, tests/component/application/test_record_contracts.py, tests/component/application/test_ports_contract.py</files>
  <read_first>AGENTS.md, PROJECT_DIRECTION.md, docs/architecture/memory-design-reference.md; the Plan and docs/implementation/e2e01-thin-slice-implementation-spec.md resolved with `git show` from the recorded exact `PLANNING_CONTRACT_SHA`; local source/test files at execution base: src/mini_agent/application/records.py, src/mini_agent/application/ports.py, src/mini_agent/core/trace.py, tests/component/application/test_record_contracts.py, tests/component/application/test_ports_contract.py</read_first>
  <action>Extend only the existing `FinalizeRunCommand` with the four fields in the interfaces block. Implement the closed COMPLETED matrix, exact cross-record/message/event bindings, exact Trace allowlists and the scoped FAILED empty-projection rule. Update only `RuntimeRecordPort.finalize_run_if_active` documentation so APPLIED means the whole command committed and non-APPLIED means zero writes. Do not add a Port, enum, persistence item, migration or Adapter behavior.</action>
  <verify>
    <automated>uv run pytest tests/component/application/test_record_contracts.py tests/component/application/test_ports_contract.py -x</automated>
    Then run `uv run pytest`, exact-file `uv run python -m compileall -q`, `git diff --check`, exact four-file containment and a read-only cross-file impact scan; all required commands exit 0 and the changed set equals `owned_files` exactly.
  </verify>
  <acceptance_criteria>
    - every accepted matrix row constructs and every omitted cross-product fails validation
    - Task/RequestUnit/transition, terminal Run/link, ASSISTANT Message and terminal Trace are one command projection
    - `terminal_result` is only a validated return/message/Trace binding and does not become a persistence item
    - APPLIED/all-or-nothing and non-APPLIED/zero-write Port wording is explicit
    - all forbidden files remain byte-identical and full regression passes
  </acceptance_criteria>
  <done>The four-file Application contract cannot express a successful partial terminal turn; physical atomicity remains for a separately planned Infra replacement Packet.</done>
</task>

</tasks>

<validation>

Execution provenance preflight（`PLANNING_CONTRACT_SHA`由Integrator在planning PR merge后注入为40位exact SHA）:

```bash
test "$(git rev-parse "${PLANNING_CONTRACT_SHA}^{commit}")" = \
  "$(git rev-parse origin/integration/e2e01-thin^{commit})"
git show \
  "${PLANNING_CONTRACT_SHA}:.planning/phases/01-cycle-1-e2e-01/01-04H-PLAN.md" \
  >/dev/null
git show \
  "${PLANNING_CONTRACT_SHA}:docs/implementation/e2e01-thin-slice-implementation-spec.md" \
  >/dev/null
git diff --quiet \
  ea0a72fdac597a9ae78b2ed6fa34d14ef2c1eb57 \
  "${PLANNING_CONTRACT_SHA}" -- \
  src/mini_agent/application/records.py \
  src/mini_agent/application/ports.py \
  tests/component/application/test_record_contracts.py \
  tests/component/application/test_ports_contract.py
```

Minimum focused gate:

```bash
uv run pytest \
  tests/component/application/test_record_contracts.py \
  tests/component/application/test_ports_contract.py -x
```

Full and mechanical gate:

```bash
uv run pytest
uv run python -m compileall -q \
  src/mini_agent/application/records.py \
  src/mini_agent/application/ports.py \
  tests/component/application/test_record_contracts.py \
  tests/component/application/test_ports_contract.py
git diff --check
```

Downstream issuance gates（不属于 01-04H `done_when`）:

- after 01-04H merges, a new 01-05R Plan/Packet must freeze the exact then-current integration SHA, new branch/Worktree and Runtime review findings before any Runtime replacement write;
- only after 01-05R merges, a new 01-06R Plan/Packet must freeze that exact integration SHA, new branch/Worktree, both Infra review findings and terminal transaction tests before any Infra replacement write;
- the historical 01-05/01-06 Plans and PR #28/#30 remain immutable evidence; they are not silently repurposed, rebased or force-pushed.
</validation>

<threat_model>

| threat_id | category | boundary | disposition | mitigation |
|---|---|---|---|---|
| `TERM-R01` | Repudiation | successful Run → state/Conversation/Trace | `MITIGATE / BLOCK` | Task transition, success, ASSISTANT Message and mandatory terminal Trace share one conditional command |
| `TERM-T01` | Tampering | Runtime command → Adapter | `MITIGATE / BLOCK` | validator binds Task/Unit/Run/result/Conversation/content/outcome/reason/timestamps and rejects extra Trace fields |
| `TERM-I01` | Information disclosure | terminal Message/Trace | `MITIGATE` | only exact user-visible message and allowlisted RunStopped projection enter the aggregate |
| `TERM-D01` | Denial of Service | partial terminal write | `TRANSFER / BLOCK 01-06R` | this command bounds the complete projection; physical Task/Message/Trace insert-failure rollback must be implemented and proved by the separately issued 01-06R Packet |
| `TERM-E01` | Elevation of Privilege | Adapter result → Runtime success | `MITIGATE / BLOCK` | only APPLIED authorizes a returned terminal result; conflicts/not-applicable have zero writes |

</threat_model>
