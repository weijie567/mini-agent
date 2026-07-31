---
phase: 01-cycle-1-e2e-01
plan: 04D
type: execute
wave: 5
depends_on:
  - 01-04
files_modified:
  - src/mini_agent/application/records.py
  - src/mini_agent/application/ports.py
  - tests/component/application/test_record_contracts.py
  - tests/component/application/test_ports_contract.py
  - tests/component/application/test_persistence_contract.py
autonomous: true
requirements:
  - E2E01-01
  - E2E01-04
user_setup: []
must_haves:
  truths:
    - "Every Application persistence write supplies the complete source record, approved logical children and exact external relation context required by the closed 01-04 codec."
    - "The initial accepted-goal graph crosses one atomic Port boundary: RequestUnderstanding, AcceptedDelta children, initial Task, initial RequestUnit, bound InputBindings, RunTaskLink and ConversationTaskLink."
    - "TaskRecord, RequestUnitRecord and the new TaskStateTransition advance through one conditional aggregate."
    - "A Run becomes terminal only in the same atomic write that finalizes every active RunTaskLink against the exact resulting Task projections."
    - "InputBinding external context and Observation source ToolCall are explicit typed command snapshots and are never inferred from JSONB, ambient state or write order."
    - "Infrastructure can call one frozen Application inbound run handler whose command is Runtime-private and whose result is User-visible, without inventing transport-local Runtime DTOs or trusted identity."
    - "Provider adapters expose only one bounded Application-owned contract violation signal; raw provider payload, prompt, credentials and PII cannot cross that signal."
    - "Restart discovery returns None only for no candidate; strict decode, owner graph, cardinality or closed-set failure raises the existing bounded persistence integrity error and keeps readiness failed."
    - "A recovery apply is conditional on the exact opaque fence for the same strictly decoded owner-consistent closure; closure changes cannot be collapsed into not-applicable or reconciliation-required."
    - "The closure model can validate internal graph consistency but does not claim that the database returned a complete closed set; Infrastructure must prove that under one snapshot/fence."
    - "This Packet declares Application Ports and commands only; it does not implement Runtime behavior, a database transaction, HTTP, Provider, Eval or Composition Root."
  artifacts:
    - "src/mini_agent/application/records.py contains the exact aggregate write, inbound run and recovery closure contracts."
    - "src/mini_agent/application/ports.py exposes relation-aware Runtime writes, a frozen AgentRunHandler and one fenced recovery boundary."
    - "tests/component/application/test_record_contracts.py proves command/closure validators and bounded failure shapes."
    - "tests/component/application/test_ports_contract.py freezes exact Protocol signatures and removes unsafe split capabilities."
    - "tests/component/application/test_persistence_contract.py proves every command carries enough information for the existing strict codec without changing persistence.py."
  key_links:
    - "CreateInitialTaskGraphCommand binds trusted owner scope and exact persisted Conversation/Message/Run roots to RequestUnderstanding, AcceptedDelta, Task, RequestUnit, InputBinding and link projections."
    - "ApplyTaskTransitionCommand binds expected/next TaskRecord, expected/next RequestUnitRecord and one exact TaskStateTransition for one atomic state advance."
    - "FinalizeRunCommand binds the exact active Run, every active RunTaskLink, every terminal link and the exact result Task projections."
    - "SaveInputBindingCommand and SaveObservationCommand cover exactly the five external-required relations frozen by the Thin Slice Spec."
    - "AgentRunHandler accepts trusted CustomerContext plus message and returns existing AgentOutcome plus opaque run_id and safe message."
    - "RestartRecoveryClosure includes ConversationTaskLink, Task transition children and ToolAttempt children; load returns None only when no candidate exists."
    - "ApplyRestartRecoveryCommand binds every Runtime/Core-produced next projection to the exact validated RestartRecoveryClosure and closure_fence for one atomic apply."
---

<objective>
关闭 01-04 codec 与 frozen Application Port 之间的 relation / logical-child / recovery transaction contract gap，并冻结 W2 Runtime、Infra 与 Eval 可以共同消费的最小 Application inbound / provider-failure 边界。

Purpose: 防止 Infra 从 JSONB、写入顺序或环境状态猜测关系，防止 startup recovery 以 stale decode 或不完整 graph claim，也防止 HTTP / Provider Adapter 在各自分支发明第二套 Application contract。

Output: 只修改两个 Application contract 文件与三个既有 Component contract tests；不实现任何 Adapter、Runtime behavior、migration、HTTP、Harness 或 Composition Root。
</objective>

<execution_context>
@AGENTS.md
@.planning/GOVERNANCE.md
@.planning/phases/01-cycle-1-e2e-01/01-04-SUMMARY.md
@docs/implementation/e2e01-thin-slice-implementation-spec.md
@docs/implementation/e2e01-thin-slice-multi-agent-plan.md

不得调用 stock `gsd-import`、`gsd-plan-phase`、`gsd-execute-phase`、`gsd-verify-work`、自动 lifecycle mutation 或 `gsd-ship`。Integrator 已从 exact base 预建 execution Worktree；executor 只写本 Packet 五个 owned files，不写 Summary、共享 State 或任何 canonical doc。
</execution_context>

<context>
Canonical inputs:

@PROJECT_DIRECTION.md
@docs/architecture/memory-design-reference.md
@docs/architecture/intent-design-reference.md
@docs/architecture/tool-calling-design-reference.md
@docs/evaluation/agent-evaluation-strategy.md
@docs/implementation/e2e01-thin-slice-implementation-spec.md

Implementation evidence:

@src/mini_agent/application/records.py
@src/mini_agent/application/ports.py
@src/mini_agent/application/persistence.py
@src/mini_agent/core/identity.py
@src/mini_agent/core/task_state.py
@src/mini_agent/core/tool_system.py
@src/mini_agent/core/trace.py
@tests/component/application/test_record_contracts.py
@tests/component/application/test_ports_contract.py
@tests/component/application/test_persistence_contract.py
</context>

<interfaces>
本 Packet 只能声明下列最小 public surface。命名或字段如需变化，必须由 exact-head Plan Checker 在编码前裁决；executor 不得自行扩展。

Aggregate persistence commands in `application/records.py`:

- `SaveRequestUnderstandingCommand`
  - `record: RequestUnderstandingRecord`
  - `accepted_deltas: tuple[AcceptedTaskDelta, ...]`
  - exact set equality with `record.accepted_delta_refs`
  - every child uses the same `message_ref` and one accepted candidate
- `SaveInputBindingCommand`
  - `record: InputBinding`
  - `request_unit_id: UUID`
- `CreateInitialTaskGraphCommand`
  - `owner_scope: TrustedOwnerScope`
  - `expected_conversation_record: ConversationRecord`
  - `expected_message_record: MessageRecord`
  - `expected_active_run_record: AgentRunRecord`
  - `request_understanding: SaveRequestUnderstandingCommand`
  - `initial_task: CreateTaskCommand`
  - `initial_request_unit: CreateRequestUnitCommand`
  - `input_bindings: tuple[SaveInputBindingCommand, ...]`
  - `conversation_task_link: ConversationTaskLinkRecord`
  - `run_task_link: CreateRunTaskLinkCommand`
  - Conversation owner matches `owner_scope`; Message is the exact USER message in that Conversation; active Run belongs to that Conversation; roots are conditions, not reinserted
  - all new identities and logical children commit atomically or not at all
- `ApplyTaskTransitionCommand`
  - `expected_task_record: TaskRecord`
  - `next_task_record: TaskRecord`
  - `expected_request_unit_record: RequestUnitRecord`
  - `next_request_unit_record: RequestUnitRecord`
  - `task_state_transition: TaskStateTransition`
  - exact Task / RequestUnit linkage, identity, owner, stable fields, base/result version and from/to status binding
- `SaveObservationCommand`
  - `owner_scope: TrustedOwnerScope`
  - `observation_record: OrderObservation`
  - `source_tool_call_record: ToolCallRecord`
  - source ToolCall must be terminal `SUCCEEDED`, `effect is ToolEffect.READ`, canonical `get_order`, and supplies the exact ToolCall / Run / Task / RequestUnit external identities
- `ObservationWriteResult`
  - `INSERTED`
  - `ALREADY_APPLIED`
  - `SOURCE_PROJECTION_CONFLICT`
  - same Observation identity with different payload, canonical envelope or source refs raises the existing bounded `P0PersistenceIntegrityError`
- `FinalizeRunCommand`
  - `expected_active_record: AgentRunRecord`
  - `terminal_record: AgentRunRecord`
  - `expected_active_links: tuple[RunTaskLinkRecord, ...]`
  - `terminal_links: tuple[RunTaskLinkRecord, ...]`
  - `result_task_records: tuple[TaskRecord, ...]`
  - expected Run is exact `RUNNING`; terminal Run is `COMPLETED` or `FAILED`; all linked result versions and exact Task projections commit atomically or not at all

Application inbound / provider boundary:

- `AgentRunCommand`
  - strict `RuntimePrivateModel`
  - `customer_context: CustomerContext`
  - `message: MessageContent`
- `AgentRunResult`
  - strict `UserVisibleModel`
  - `run_id: UUID`
  - `outcome: AgentOutcome`
  - `message: MessageContent`
- `AgentRunHandler.handle(command: AgentRunCommand) -> AgentRunResult`
- `ProviderProtocolError`
  - parameterless bounded Application exception
  - fixed non-sensitive representation
  - no caller-supplied raw payload, prompt, URL, token, customer identity or free text
  - adapter translation suppresses raw exception cause/context

Recovery boundary:

- `TaskRecoveryAggregate`
  - `task_record: TaskRecord`
  - `task_state_transitions: tuple[TaskStateTransition, ...]`
  - transition history is the complete unique contiguous `1 -> ... -> task_record.state_version` chain; version 1 has no transitions
- `ToolCallRecoveryAggregate`
  - `tool_call_record: ToolCallRecord`
  - `tool_attempt_records: tuple[ToolAttemptRecord, ...]`
  - attempts are exact `1..attempt_count` and lifecycle-consistent
- `RestartRecoveryClosure`
  - `closure_fence: UUID`
  - `conversation_record: ConversationRecord`
  - `active_run_record: AgentRunRecord`
  - `conversation_task_links: tuple[ConversationTaskLinkRecord, ...]`
  - `run_task_links: tuple[RunTaskLinkRecord, ...]`
  - `task_aggregates: tuple[TaskRecoveryAggregate, ...]`
  - `request_unit_records: tuple[RequestUnitRecord, ...]`
  - `tool_call_aggregates: tuple[ToolCallRecoveryAggregate, ...]`
- `ApplyRestartRecoveryCommand`
  - `expected_closure: RestartRecoveryClosure`
  - `run_transition: MarkRunIncompleteForRecoveryCommand`
  - `tool_call_transitions: tuple[InterruptToolCallForRecoveryCommand, ...]`
  - `task_transitions: tuple[ApplyTaskTransitionCommand, ...]`
  - `terminal_run_task_links: tuple[RunTaskLinkRecord, ...]`
  - every next projection is produced by Runtime/Core, maps bijectively to the validated closure and is applied atomically or not at all
- `RecoveryWriteResult`
  - exact values `APPLIED`、`CLOSURE_CONFLICT`、`NOT_APPLICABLE`、`RECONCILIATION_REQUIRED`
  - `CLOSURE_CONFLICT` means any decoded projection or fence changed and guarantees zero writes
  - integrity failure is not a result value; it raises the existing bounded `P0PersistenceIntegrityError`

Port replacements:

- `RuntimeRecordPort.start_run_if_created(command: TransitionRunCommand) -> ConditionalWriteResult`
- `start_run_if_created` accepts only `CREATED -> RUNNING`
- `RuntimeRecordPort.finalize_run_if_active(command: FinalizeRunCommand) -> ConditionalWriteResult`
- `RuntimeRecordPort.create_initial_task_graph_if_current(command: CreateInitialTaskGraphCommand) -> ConditionalWriteResult`
- remove the independently committable `save_request_understanding`、`append_accepted_task_delta`、`save_input_binding`、`insert_task`、`insert_request_unit` and `create_run_task_link` capabilities
- remove `ConversationRecordPort.save_conversation_task_link` as an independently committable initial-goal bypass; read capabilities remain
- `RuntimeRecordPort.apply_task_transition_if_current(command: ApplyTaskTransitionCommand) -> ConditionalWriteResult`
- remove the separate normal `append_task_state_transition` + `compare_and_set_task` + `compare_and_set_request_unit` split
- remove `transition_run_if_active` and the separate `compare_and_set_run_task_link`; normal start/finalize use the two controlled Run entry points
- `RuntimeRecordPort.save_observation(command: SaveObservationCommand) -> ObservationWriteResult`
- Observation insert/idempotent replay is conditional on the exact persisted successful ToolCall projection; source drift returns `SOURCE_PROJECTION_CONFLICT`, while same identity with different facts is integrity failure
- `RestartRecoveryPort.load_next_restart_recovery_closure() -> RestartRecoveryClosure | None`
- only no candidate returns `None`; strict decode, owner graph, cardinality or closed-set failure raises bounded `P0PersistenceIntegrityError` and keeps startup readiness failed
- remove `list_runs_pending_restart_recovery`、`list_tool_calls_pending_restart_recovery`、`list_run_task_links_pending_restart_recovery`、`list_tasks_pending_restart_recovery` and `list_request_units_pending_restart_recovery`
- `RestartRecoveryPort.claim_and_apply_restart_recovery(command: ApplyRestartRecoveryCommand) -> RecoveryWriteResult`
- remove `claim_and_mark_run_incomplete_if_active`、`interrupt_tool_call_if_active`、`compare_and_set_run_task_link_for_restart`、`compare_and_set_task_for_restart` and `compare_and_set_request_unit_for_restart`
- the single apply must revalidate the exact closure fence, strict graph and all expected projections before any write

Existing ToolCall commands already bind `ToolCallRecord` and its local-closed `ToolAttemptRecord`; this Packet must not redesign the Tool lifecycle.
</interfaces>

<task_packet>
repository: `https://github.com/weijie567/mini-agent`
remote: `origin`
head_branch: `codex/e2e01-01-application-port-closure`
base_branch: `integration/e2e01-thin`
base_sha: `bde99edec0bbb9ba331c6099c8b467c14fe24e58`
worktree_id: `e2e01-01-application-port-closure`
writer: `Application Port contract sole writer, supervised by /root Integrator`

owned_files:

- `src/mini_agent/application/records.py`
- `src/mini_agent/application/ports.py`
- `tests/component/application/test_record_contracts.py`
- `tests/component/application/test_ports_contract.py`
- `tests/component/application/test_persistence_contract.py`

forbidden_files:

- every repository path not listed in `owned_files`
- `AGENTS.md`
- `PROJECT_DIRECTION.md`
- `README.md`
- `.planning/**`
- `docs/**`
- `src/mini_agent/application/persistence.py`
- `src/mini_agent/application/__init__.py`
- `src/mini_agent/core/**`
- `src/mini_agent/infrastructure/**`
- `src/mini_agent/evaluation/**`
- `src/mini_agent/__init__.py`
- `src/mini_agent/main.py`
- `src/mini_agent/bootstrap.py`
- every test file not listed in `owned_files`
- `tests/conftest.py`
- `tests/integration/**`
- `tests/e2e/**`
- `evals/**`
- `alembic/**`
- `pyproject.toml`
- `uv.lock`
- `compose.yaml`
- `graphify-out/**`

dependencies:

- Plan 01-04 planning merge `390d615be8e4020008c45bce1feec6260e47d361`
- Plan 01-04 feature PR #19 merge / exact execution base `bde99edec0bbb9ba331c6099c8b467c14fe24e58`
- 01-04 final full regression `315 passed`
- Graphify AST + semantic freshness gate `PASS`
- the planning-status PR containing this Plan and `01-04-SUMMARY.md` must merge before implementation writing starts
- because the execution branch is intentionally forked before that planning-status PR, executor must resolve the fresh official integration ref, prove the planning merge is the sole commit after `base_sha`, and read this Plan / Summary through captured Git objects
- planning merge must contain exactly the declared planning-status changed files and leave all five owned implementation/test files byte-identical to `base_sha`

planning_provenance:

- `planning_merge_sha`: `TO_BE_CAPTURED_FROM_OFFICIAL_INTEGRATION_REF_AFTER_PLANNING_STATUS_PR_MERGE`
- `planning_plan_blob`: `TO_BE_CAPTURED:${planning_merge_sha}:.planning/phases/01-cycle-1-e2e-01/01-04D-PLAN.md`
- `planning_summary_blob`: `TO_BE_CAPTURED:${planning_merge_sha}:.planning/phases/01-cycle-1-e2e-01/01-04-SUMMARY.md`
- unresolved placeholder, wrong parent, wrong changed-file set or mismatched blob is `BLOCK`

required_checks:

- branch / exact base HEAD / merge-base / clean-worktree precheck
- official GitHub ref/commit/tree provenance when smart HTTP is unavailable
- exact planning merge SHA / Plan blob / Summary blob and planning-only containment
- exact five-file implementation allowlist and exactly one feature commit
- all Port Protocol signatures inspected exactly; unsafe split capabilities absent
- three codec logical-child families audited; RequestUnderstanding and Task gaps closed without redesigning ToolCall lifecycle
- exactly five external-required relation identities carried by typed commands or the exact terminal ToolCall snapshot
- terminal Run and every RunTaskLink result projection are one atomic conditional write
- inbound handler accepts only trusted `CustomerContext` plus bounded message and returns existing `AgentOutcome`
- provider violation signal has no caller-controlled unsafe diagnostic content
- recovery loader returns None only for no candidate; integrity failure raises the existing bounded error
- closure validators cover owner, run, link, task, RequestUnit, ToolCall, attempt, duplicate and orphan failures
- closure model and Port docs explicitly state database closed-set completeness remains an Infra snapshot/fence obligation
- `git diff --check`, ruff, compileall, focused tests, complete `uv run pytest` and repository cross-file impact scan
- independent exact-head review before PR readiness / merge
- post-merge Integrator-only `graphify update .` gate before 01-05/06/07 planning / dispatch

done_when:

- all tasks complete in exactly the five owned files
- one-commit / five-file containment and all mechanical checks pass
- complete canonical regression passes
- independent exact-head review has no unresolved `CRITICAL / HIGH / MEDIUM`
- feature PR uses the repository template, starts as draft and targets `integration/e2e01-thin`
- merge does not advance Requirements, Case or numbered Phase lifecycle

contract_changes: `YES / APPLICATION PORT DECLARATION ONLY / CONSUMES EXISTING CANONICAL SEMANTICS`

security_impact: `YES` — closes relation guessing, split aggregate writes, trusted inbound identity, unsafe Provider diagnostics, corrupt-candidate skipping and stale recovery claim boundaries.

eval_impact: `YES / CONTRACT ONLY` — unblocks deterministic Runtime / Infra / Eval wiring; creates no Eval Case, result, metric, threshold or lifecycle evidence.

graphify_disposition: `NOT_WRITTEN_IN_FEATURE_WORKTREE` — after exact feature merge, Integrator runs `graphify update .` in root integration checkout and requires a clean tracked tree with no stale marker before W2 planning.

rollback: Close the PR before merge. After merge use a normal revert PR; no reset, force-push, Worktree deletion, data rewrite or migration.
</task_packet>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: 冻结 relation-aware aggregate writes 与原子 Run finalization</name>
  <files>
    src/mini_agent/application/records.py
    src/mini_agent/application/ports.py
    tests/component/application/test_record_contracts.py
    tests/component/application/test_ports_contract.py
    tests/component/application/test_persistence_contract.py
  </files>
  <behavior>
    - RED: current raw-record-only InputBinding / Observation Port signatures cannot construct the existing codec envelope without out-of-band IDs
    - RED: current split RequestUnderstanding/AcceptedDelta and Task/Transition/RequestUnit capabilities cannot guarantee one aggregate write
    - RED: current separate Run terminal transition and RunTaskLink CAS can leave a terminal Run with an incomplete graph that restart recovery will never discover
    - RED: command validators reject owner-scope mismatch, Run/Conversation/Message mismatch, wrong accepted child set, InputBinding source mismatch, Task/RequestUnit identity/version/status mismatch and duplicate children
    - RED: command context maps to exactly five approved external references and no extra relation; Observation owner and refs derive only from trusted scope plus one exact successful READ get_order ToolCall
    - RED: ToolCall.result_ref remains Tool-result-domain payload correlation and is never treated as the Observation identity
    - RED: Observation replay is idempotent only when the complete existing envelope and current source ToolCall projection exactly match
    - RED: source ToolCall drift is a zero-write SOURCE_PROJECTION_CONFLICT, while the same Observation identity with different facts is bounded persistence integrity failure
    - RED: Run finalization rejects missing/extra/stale links, mismatched result Task projections and partial terminal updates
    - RED: existing codec accepts each valid command projection and rejects a missing, swapped or extra relation/child
    - RED: ToolCall/ToolAttempt commands remain unchanged and continue to pass all contract tests
  </behavior>
  <action>
    先写失败测试，再新增 relation/aggregate commands、ObservationWriteResult 与 FinalizeRunCommand，并替换对应 RuntimeRecordPort signatures。只绑定既有 owner records；不创建第二套 payload DTO，不在 Port层复制 codec，不修改 `persistence.py`。使用既有 codec的 public API在测试中证明 command context充分且封闭。
  </action>
  <verify>
    <automated>uv run pytest tests/component/application/test_record_contracts.py tests/component/application/test_ports_contract.py tests/component/application/test_persistence_contract.py -x</automated>
  </verify>
  <done>
    logical child与 external relation不再依赖分离调用或隐式 context；现有 codec surface零修改。
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: 冻结 Application inbound handler 与 bounded Provider violation</name>
  <files>
    src/mini_agent/application/records.py
    src/mini_agent/application/ports.py
    tests/component/application/test_record_contracts.py
    tests/component/application/test_ports_contract.py
  </files>
  <behavior>
    - RED: AgentRunCommand is a strict RuntimePrivateModel, requires a real CustomerContext and rejects mapping/coercion/extra fields
    - RED: AgentRunResult is a strict UserVisibleModel, uses the existing AgentOutcome and exposes only run_id/outcome/message
    - RED: AgentRunHandler has one exact async handle signature
    - RED: ProviderProtocolError cannot receive or reveal caller-controlled text, raw response, prompt, credential, URL or customer data
    - RED: ProviderProtocolError args/str/repr contain only the fixed safe code and adapter translation suppresses raw exception cause/context
    - RED: ModelProvider Protocol documents the bounded signal while candidate DTO behavior remains unchanged
  </behavior>
  <action>
    只声明 Application use-case boundary。HTTP request/response Pydantic DTO仍归 Infra transport；01-05 AgentRunService实现该 Protocol；01-07 Provider Adapter对不可信响应做本地解析后只向上抛parameterless Application-owned ProviderProtocolError。不得创建 HTTP status、FastAPI、Qwen或 Runtime实现。
  </action>
  <verify>
    <automated>uv run pytest tests/component/application/test_record_contracts.py tests/component/application/test_ports_contract.py -x</automated>
  </verify>
  <done>
    Infra与Provider可依赖同一最小 Application contract，且用户/模型/Adapter无法通过该边界注入可信身份或不安全诊断。
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: 冻结完整性可见的 fenced restart recovery boundary</name>
  <files>
    src/mini_agent/application/records.py
    src/mini_agent/application/ports.py
    tests/component/application/test_record_contracts.py
    tests/component/application/test_ports_contract.py
  </files>
  <behavior>
    - RED: only an absent candidate returns None; a corrupt candidate raises the existing bounded P0PersistenceIntegrityError
    - RED: closure rejects inactive/null-conversation Run, owner mismatch, cross-Run/cross-Task/cross-RequestUnit relation, duplicate identity, orphan, non-contiguous Task transition history and ToolAttempt mismatch
    - RED: closure includes every applicable ConversationTaskLink and rejects missing/extra closed-set relations
    - RED: integrity failure exposes only the existing bounded category/correlation shape and never returns a partial closure
    - RED: ApplyRestartRecoveryCommand rejects missing/extra/mismatched Run, ToolCall, Task, RequestUnit, transition or RunTaskLink next projections
    - RED: a changed but valid closure returns CLOSURE_CONFLICT; NOT_APPLICABLE and RECONCILIATION_REQUIRED remain distinct; every failure is zero-write
    - RED: removed independent list and mutation capabilities are absent from RestartRecoveryPort
    - RED: closure docs and tests do not claim a Pydantic tuple proves database closed-set completeness
  </behavior>
  <action>
    建立codec-decoded Task/ToolCall aggregates与opaque fence closure，并用一个 ApplyRestartRecoveryCommand携带Runtime/Core产生的全部next projections。收窄Port为single load + single atomic claim/apply。Application模型只验证它能看到的内部一致性；Port doc明确要求Infra在同一transactionally consistent snapshot或等价fence中strict decode完整owner-root graph，并让apply条件覆盖该 exact graph。只有无候选返回None；任何integrity failure抛既有bounded error，不得写入、跳过候选或形成startup readiness。
  </action>
  <verify>
    <automated>uv run pytest tests/component/application/test_record_contracts.py tests/component/application/test_ports_contract.py -x</automated>
  </verify>
  <done>
    Recovery Port不再允许无锁分项扫描后分裂写入；no-candidate、integrity failure、closure conflict、not-applicable与reconciliation-required保持可区分，atomic apply失败时零写入。
  </done>
</task>

</tasks>

<threat_model>

| threat_id | category | component | disposition | mitigation |
|---|---|---|---|---|
| `P04D-S01` | Spoofing | AgentRunCommand | `MITIGATE/BLOCK` | only strict CustomerContext accepted; no body/model identity fields |
| `P04D-T01` | Tampering | RequestUnderstanding write | `MITIGATE/BLOCK` | parent/accepted-child exact-set and candidate/message binding |
| `P04D-T02` | Tampering | Task transition write | `MITIGATE/BLOCK` | expected/next/transition identity, owner, status and version binding |
| `P04D-T03` | Tampering | external relations | `MITIGATE/BLOCK` | exact RequestUnit or terminal ToolCall snapshots derive five closed refs; no inference or extra relation |
| `P04D-T04` | Tampering | recovery fence | `MITIGATE/BLOCK` | atomic apply requires exact validated closure, opaque fence and Core-produced next projections |
| `P04D-T05` | Tampering | Run finalization | `MITIGATE/BLOCK` | terminal Run and every RunTaskLink result version commit against exact result Task projections in one write |
| `P04D-R01` | Repudiation | recovery outcomes | `MITIGATE/BLOCK` | status/closure/integrity outcomes remain distinct and correlated |
| `P04D-I01` | Information Disclosure | Provider violation | `MITIGATE/BLOCK` | parameterless fixed safe signal; no raw diagnostic content |
| `P04D-I02` | Information Disclosure | integrity failure | `MITIGATE/BLOCK` | opaque UUID only; no owner, record, payload or graph detail |
| `P04D-D01` | Denial of Service | closure validation | `MITIGATE` | bounded typed tuples; no recursive graph walk or payload logging |
| `P04D-E01` | Elevation of Privilege | persisted owner metadata | `MITIGATE/BLOCK` | closure validates consistency but never constructs TrustedOwnerScope |
| `P04D-E02` | Elevation of Privilege | internal recovery authority | `MITIGATE/BLOCK` | discovery/claim contract is separate from user owner-scoped reads |
| `P04D-C01` | Consistency | database closed set | `TRANSFER / REQUIRED` | Infra must prove complete set under one snapshot/fence; model makes no completeness claim |

</threat_model>

<verification>
Preflight:

1. Resolve GitHub official `integration/e2e01-thin`; it must contain planning merge as the sole successor of `bde99ed...`.
2. Prove planning merge changed only the exact planning-status allowlist and left all five owned files byte-identical to execution base.
3. Capture exact planning merge, Plan blob and Summary blob; any placeholder is `BLOCK`.
4. Execution Worktree path is `/Users/ming/projects/mini-agent-worktrees/e2e01-01-application-port-closure`, branch is `codex/e2e01-01-application-port-closure`, HEAD is exact base and status is clean.

Automated:

1. `uv run pytest tests/component/application/test_record_contracts.py tests/component/application/test_ports_contract.py tests/component/application/test_persistence_contract.py -x`
2. `uv run pytest`
3. `uv run ruff check src/mini_agent/application/records.py src/mini_agent/application/ports.py tests/component/application/test_record_contracts.py tests/component/application/test_ports_contract.py tests/component/application/test_persistence_contract.py`
4. `uv run ruff format --check src/mini_agent/application/records.py src/mini_agent/application/ports.py tests/component/application/test_record_contracts.py tests/component/application/test_ports_contract.py tests/component/application/test_persistence_contract.py`
5. `uv run python -m compileall -q src/mini_agent tests`
6. `git diff --check`
7. exact five-file containment and exactly one feature commit
8. repository cross-file impact scan for old split Port calls, unsafe provider exceptions, stale recovery list methods and 01-05/06/07 dependency references

Independent review:

- one contract/security reviewer validates exact remote head and all five files
- one integration reviewer checks that 01-05 Runtime、01-06 Infra、01-07 Eval can consume the surface with zero shared-file write overlap
- unresolved `CRITICAL/HIGH/MEDIUM` blocks PR readiness
</verification>

<success_criteria>

- Five-file allowlist is the complete changed set.
- Existing codec source and canonical docs are byte-unchanged.
- All relation-aware and child-aware command tests pass.
- Unsafe split capabilities are absent; ToolCall lifecycle APIs remain unchanged.
- Run terminal projection and all RunTaskLink terminal projections are atomic and exact-task-conditioned.
- Inbound identity and provider error boundaries are bounded and dependency-safe.
- Recovery candidate absence cannot hide integrity failure.
- Closure/fence claim semantics satisfy the Memory 15.2 declaration boundary without claiming the Adapter implementation exists.
- Full repository tests pass.
- Draft PR targets `integration/e2e01-thin`; no direct push to integration or main.
- Numbered lifecycle remains `0/8`; 01-04D does not mark any Case complete.
</success_criteria>

<handoff>
Executor reports:

- exact execution base / planning merge / Plan blob / Summary blob
- local and published head SHA/tree/blob
- exact changed files and one-commit proof
- focused/full/static command outputs and test counts
- removed/replaced Port capability inventory
- command/codec coverage for logical children and five external relations
- recovery load/closure/fence outcome matrix
- contract/security/Eval impact and non-claims
- unresolved risks, dependency requests and rollback
- draft PR URL with head/base

Executor writes no Summary or shared State. Integrator performs merge, repository validation, Graphify refresh and the next planning-status PR.
</handoff>
