---
phase: 01-cycle-1-e2e-01
plan: 01-07V
type: tdd
wave: ru-v1-contract-final
depends_on:
  - B_V_READY
  - 01-07V-EVAL-HANDOFF
files_modified:
  - src/mini_agent/core/request_understanding.py
  - src/mini_agent/core/task_state.py
  - src/mini_agent/core/request_processing.py
  - tests/component/core/test_control_gateway.py
  - tests/component/core/test_identity_contract.py
  - tests/component/core/test_request_understanding_contract.py
  - tests/component/core/test_task_state_contract.py
  - tests/component/core/test_request_processing.py
autonomous: true
requirements:
  - E2E01-01
  - E2E01-04
user_setup: []
must_haves:
  truths:
    - "Core不再定义、导入、导出或动态暴露RequestUnderstandingOutput v1、AcceptedTaskDelta v1、CandidateValidationRecord v1、RequestUnderstandingRecord v1、InitialRequestDecision、validate_and_reduce_initial_request或revalidate_next_move。"
    - "RequestUnderstandingInput、共享candidate/NextMove合同、全部V2类型、v2 reducer/closure/seal/pickle恢复与revalidate_next_move_v2保持current且可执行。"
    - "Control Gateway的schema、binding、trusted identity、owner、state-version、budget与progress fail-closed证据迁移到真实v2 exact-one Core decision，不以删除测试代替迁移。"
    - "feature启动前allowlist外Python源码与测试对上述v1 symbols的direct AST consumer为0；quoted catalog/absence labels不冒充executable consumer，也不由V越权删除。"
    - "reviewed feature merge与post-merge canonical gate形成B_RU_V2_CONTRACT；只解锁01-08签发，不证明Composition Root、HTTP Trajectory/E2E、Case PASS或P0产品ready。"
  artifacts:
    - "Core current-v2-only Request Understanding output、durable record/child与reducer surface。"
    - "结构化AST/API/runtime absence oracle及迁移后的v2 Control Gateway/Core Component证据。"
  key_links:
    - "B_V_READY → 01-07V → B_RU_V2_CONTRACT。"
    - "RequestUnderstandingInput → RequestUnderstandingOutputV2 → validate_and_reduce_initial_request_v2 → InitialRequestRoutableTaskGraphDecisionV2 → revalidate_next_move_v2 → Control Gateway。"
    - "B_RU_V2_CONTRACT → 01-08 issuance；不得跳过独立Plan、review、overlay与post-merge gate。"
---

# Phase 1 Plan 01-07V｜Request Understanding Core v1-contract closure

> **ISSUED CONTRACT-CLOSURE TASK PACKET / IMPLEMENTATION NOT STARTED**
> 本Plan从exact `B_V_READY`签发。Plan merge、execution-owner merge、旧`B_W`、handoff feature head或任何status SHA都不得替换feature base。只有01-07V feature通过独立exact-head review、latest-integration overlay、串行merge及post-merge canonical gate后，才可命名`B_RU_V2_CONTRACT`。

> **DERIVED / NON_NORMATIVE**
> Request Understanding、Memory、安全、Eval与产品结果语义仍由active canonical owner拥有。本Plan只消费`p0-ru-v2-execution-map-r5`已经批准的最后一个Core closure Packet，不建立第二套合同。Graphify按用户要求保持闲置。

## 目标

删除Core中已经没有allowlist外direct consumer的RU-v1 output DTO、durable parent/child records与initial reducer surface，并把五份owned Core Component tests迁移/收敛到current v2 contracts。

本Packet必须保留`RequestUnderstandingInput`。它仍是current ModelProviderV2输入，且其`e2e01-thin-v1` schema literal不是本次待删除的output-v1合同。不得因名称或版本字符串相似而误删。

## Preflight evidence

- `CONFIRMED`：input barrier为exact `B_V_READY = d005ca94fc772c1a8704fd9e18317aff21e050fb`，tree `2e354a6904437e50f5df6bf512904efa05cbcdd9`。
- `CONFIRMED`：01-07V-EVAL-HANDOFF reviewed feature PR #147已merge；feature、latest overlay与post-merge gate均为`P0/P1/P2/P3 = 0/0/0/0`，post-merge full为`1966 passed, 1 deselected, 12 warnings`。
- `CONFIRMED`：exact `B_V_READY`上8个owned blobs：
  - `src/mini_agent/core/request_understanding.py = 018ea446517c099cc061de6e99afe55db10e8afb`
  - `src/mini_agent/core/task_state.py = 122b62b7a68ae0b92adfb3208ef9845fdd646fbe`
  - `src/mini_agent/core/request_processing.py = 8453214be8a66b3bd51c77a27ba588f5ee56353e`
  - `tests/component/core/test_control_gateway.py = ca746b727e1a2be744bff53e8aa337e3d99e6b62`
  - `tests/component/core/test_identity_contract.py = b54e0bd555748ddb114cba0fb32e254782e8b833`
  - `tests/component/core/test_request_understanding_contract.py = 627d22681050985e8c10c2c8bd2d33cfbc6ae93d`
  - `tests/component/core/test_task_state_contract.py = 466a694cede64f7ae55ce0fe8a0a7e7b41d90192`
  - `tests/component/core/test_request_processing.py = 0587e98e3eebac5730ef2cd1feb657fb0c5f189d`
- `CONFIRMED`：5份owned tests focused baseline为`143 passed`；`tests/component/core` baseline为`245 passed`。
- `CONFIRMED`：对`src/**/*.py`与`tests/**/*.py`排除上述8个owned files进行AST扫描，`RequestUnderstandingOutput`、`AcceptedTaskDelta`、`CandidateValidationRecord`、`RequestUnderstandingRecord`、`InitialRequestDecision`、`validate_and_reduce_initial_request`与`revalidate_next_move`的direct ImportFrom / Name / Attribute consumer为`0`。
- `CONFIRMED`：allowlist外仍出现的部分exact字符串属于Application/Infrastructure的family catalog或legacy-absence guard，不是可执行Core import/type/call；V不得越权修改它们。
- `CONFIRMED`：`CandidateValidationDecision`同时被`CandidateValidationRecordV2`、Application、Eval与Infrastructure使用，必须保留；只删除unversioned `CandidateValidationRecord` class。
- `CONFIRMED`：`RequestProcessingError`、`RevalidatedNextMove`、`_normalize_order_id`、`_candidate_order_id_or_none`、v2 closure/seal/pickle helpers与`revalidate_next_move_v2`属于current v2路径，必须保留。
- `CONFIRMED`：v2 `TaskRecord` / `RequestUnitRecord`的initial `state_version=1`以及错误文本`ACTIVE/v1`表达Task状态版本，不等于RU output/record v1合同；不得做模糊字符串删除。
- `OPEN / NONCLAIM`：本Packet不迁移、回填或删除historical physical RU-v1 rows，不修改migration/codec/registry/Repository，不激活01-07R。
- `OPEN / NONCLAIM`：`B_RU_V2_CONTRACT`仍不证明canonical Composition Root、真实HTTP→Runtime→PostgreSQL→Eval、credentialed Qwen、Trajectory/E2E Result或产品ready。

## Task Packet

```yaml
task_id: 01-07V
goal: 删除Core RU-v1 output、record/child与initial reducer direct surface，并把owned Core contracts迁移到唯一current v2路径。
repository: weijie567/mini-agent
remote: origin
head_branch: codex/e2e01-01-ru-v1-core-contract
base_branch: integration/e2e01-thin
base_sha: d005ca94fc772c1a8704fd9e18317aff21e050fb
base_tree: 2e354a6904437e50f5df6bf512904efa05cbcdd9
worktree_id: e2e01-01-ru-v1-core-contract
agent_role: runtime-engineer
owned_files:
  - src/mini_agent/core/request_understanding.py
  - src/mini_agent/core/task_state.py
  - src/mini_agent/core/request_processing.py
  - tests/component/core/test_control_gateway.py
  - tests/component/core/test_identity_contract.py
  - tests/component/core/test_request_understanding_contract.py
  - tests/component/core/test_task_state_contract.py
  - tests/component/core/test_request_processing.py
forbidden_files:
  - all repository files outside the exact eight-file owned_files allowlist
  - src/mini_agent/application/**
  - src/mini_agent/evaluation/**
  - src/mini_agent/infrastructure/**
  - other src/mini_agent/core/**
  - other tests/**
  - evals/**
  - migrations/**
  - docs/**
  - .planning/**
  - pyproject.toml
  - uv.lock
  - compose.yaml
  - AGENTS.md
  - PROJECT_DIRECTION.md
  - README.md
  - graphify-out/**
canonical_inputs:
  - AGENTS.md
  - docs/implementation/e2e01-thin-slice-multi-agent-plan.md#P0-RU-V2-EXECUTION-MAP
  - docs/implementation/e2e01-thin-slice-implementation-spec.md
  - docs/architecture/intent-design-reference.md
  - docs/architecture/memory-design-reference.md
  - docs/architecture/tool-calling-design-reference.md
  - docs/evaluation/agent-evaluation-strategy.md
dependencies:
  - exact B_V_READY = d005ca94fc772c1a8704fd9e18317aff21e050fb with post-merge canonical full PASS
  - p0-ru-v2-execution-map-r5 reviewed merge = 7883d8e6535c54b278e8918d7098dc74ad311be6; route authorization only, never feature base
  - 01-07V-EVAL-HANDOFF Plan merge = 11172b61160362ccebb698d1a28e6473d370a97b and feature merge = d005ca94fc772c1a8704fd9e18317aff21e050fb
contract_changes: SCOPED / EXECUTION-MAP AUTHORIZED; remove Core RU-v1 output DTO、durable parent/child records、initial decision/reducer/revalidation surface，保留RequestUnderstandingInput与全部current v2 contracts。
security_impact: BOUNDARY PRESERVING / DEFENSE IN DEPTH; 删除fallback-capable legacy入口，保留trusted identity、owner isolation、source provenance、state CAS、atomic closure、bounded errors与Control Gateway复验。
eval_impact: CORE COMPONENT CONTRACT UPDATE ONLY; 迁移owned Core tests到v2，不修改或激活Dataset Case、grader、Trajectory/E2E Result、threshold或42 denominator。
required_checks:
  - exact B_V_READY head/tree、8 base blobs、clean branch、first feature parent、all commits、zero merge、eight-file containment与range diff-check全部PASS
  - pre-feature non-owned direct v1 AST consumers = 0
  - RED tests-only commit在base source上只因legacy definitions/exports/direct surface仍存在而FAIL
  - GREEN/fix后legacy exact static/runtime/reflection surface为0，RequestUnderstandingInput、shared types与全部v2 surface存在
  - uv sync --all-groups PASS
  - docker compose up --wait -d db PASS且db healthy
  - docker compose --profile test up --wait -d db-test PASS且db-test healthy
  - uv run alembic upgrade head PASS
  - owned focused、tests/component/core、Application/Eval/model neighbors、integration与uv run pytest全部PASS
  - independent exact-head review P0/P1/P2/P3 = 0/0/0/0
  - latest-integration overlay与reviewed feature的8 owned blobs及patch一致，post-merge canonical gates PASS
done_when:
  - feature从exact B_V_READY启动，至少保留独立RED与GREEN commits，所有fix均append-only且逐commit不越allowlist
  - 7个legacy targets在3个owned production modules及5个owned tests中无definition/import/direct/alias/star/reflection/runtime export
  - Control Gateway tests使用真实v2 exact-one decision与revalidate_next_move_v2，原安全边界断言未被删减
  - all non-owned direct v1 consumers仍为0，inert historical/absence strings保持owner边界
  - reviewed feature串行merge且post-merge full PASS，形成唯一exact B_RU_V2_CONTRACT SHA/tree
rollback:
  - 未merge时关闭draft PR并保留RED/GREEN、review与overlay evidence
  - V已merge且无01-08或更下游merge时普通revert V并复跑全部required_checks；revert SHA不得冒充原B_V_READY
  - 已有01-08、01-08A或更下游implementation/Plan/status merge时，先按严格逆依赖顺序revert全部下游，再revert V；如还需回退handoff，则必须在V之后回退
  - 禁止reset、force push或声称恢复/删除physical database rows
handoff_to: tech-lead
handoff_format: docs/implementation/e2e01-thin-slice-multi-agent-plan.md#10-handoff-模板
output_barrier: B_RU_V2_CONTRACT
```

## Exact deletion and preservation boundary

删除：

- `request_understanding.py`：`RequestUnderstandingOutput`。
- `task_state.py`：`AcceptedTaskDelta`、`CandidateValidationRecord`、`RequestUnderstandingRecord`。
- `request_processing.py`：
  - v1-only imports；
  - `InitialRequestDecision`；
  - `validate_and_reduce_initial_request`；
  - `revalidate_next_move`；
  - 只服务上述v1 reducer的owned test helpers、fixtures与cases。

保留：

- `RequestUnderstandingInput`与`THIN_SLICE_REQUEST_SCHEMA_VERSION`；
- `InputAuthority`、`InputSourceKind`、`InputCandidate`、`TaskDeltaOperation`、`TaskDeltaCandidate`、`NextMoveKind`、`NextMove`；
- `RequestUnderstandingOutputV2`及contextualization/reference/uncertainty全部v2 contracts；
- `CandidateValidationDecision`、`InputBinding`、Task/RequestUnit/transition current records；
- `CandidateValidationRecordV2`、`AcceptedTaskDeltaV2`、`RequestUnderstandingRecordV2`与所有durable v2 child types/failure codes；
- `RequestProcessingError`、`RevalidatedNextMove`、v2 decision/closure/reducer/seal/pickle恢复及`revalidate_next_move_v2`；
- identity、source provenance、trusted-field、owner/state/version、zero/all-REJECT、multi-ACCEPT、atomic failure与Control Gateway fail-closed证据。

不得新增unversioned alias、v1 compatibility wrapper、union/fallback、dynamic latest selector、module `__getattr__`、v2→v1 projection或测试侧production重实现。

## Test migration

1. RED只修改owned tests，增加结构化absence/presence oracle：
   - exact `ImportFrom` name/alias、star import；
   - class/function definition、`Name` / `Attribute` direct reference；
   - `getattr` / `hasattr` / `setattr`、`vars` / `globals` / module `__dict__`、`__import__` / `import_module`；
   - compile-time folded target string与runtime module export；
   - target literal只允许集中出现在oracle的唯一target set，V2后缀不得被substring误报。
2. GREEN在8文件内删除production v1 surface并迁移tests：
   - `test_control_gateway.py`以`RequestUnderstandingInput`、`RequestUnderstandingOutputV2`、`InitialTaskIdentityAllocationV2`、`validate_and_reduce_initial_request_v2`与`revalidate_next_move_v2`构造真实exact-one accepted graph；原schema/binding/owner/state/budget/progress断言保留。
   - `test_identity_contract.py`的model-visible identity scan以`RequestUnderstandingOutputV2`替代v1 output。
   - `test_request_understanding_contract.py`删除v1 output helper/cases，保留input/shared candidate/NextMove与全部v2 cases并加入v1 output absence evidence。
   - `test_task_state_contract.py`保留shared `CandidateValidationDecision`和全部v2/task tests，加入3个v1 durable type absence evidence。
   - `test_request_processing.py`删除v1 decision/reducer helpers/cases，保留shared error/revalidated DTO及全部v2 reducer/closure/revalidation/security tests，并加入3个v1 processing target absence evidence。
3. findings只通过append-only allowlist fix commits关闭，不amend/rebase掉RED。

## Verification

```bash
git diff --check
uv sync --all-groups
docker compose up --wait -d db
docker compose --profile test up --wait -d db-test
uv run alembic upgrade head
uv run pytest \
  tests/component/core/test_control_gateway.py \
  tests/component/core/test_identity_contract.py \
  tests/component/core/test_request_understanding_contract.py \
  tests/component/core/test_task_state_contract.py \
  tests/component/core/test_request_processing.py -q
uv run pytest tests/component/core -q
uv run pytest tests/component/application -q
uv run pytest tests/component/evaluation tests/component/model -q
uv run pytest tests/integration -q
uv run pytest
```

机械 containment：

```bash
test "$(git rev-parse d005ca94fc772c1a8704fd9e18317aff21e050fb^{tree})" = \
  "2e354a6904437e50f5df6bf512904efa05cbcdd9"
test "$(git merge-base HEAD d005ca94fc772c1a8704fd9e18317aff21e050fb)" = \
  "d005ca94fc772c1a8704fd9e18317aff21e050fb"
first_feature_commit="$(git rev-list --reverse \
  d005ca94fc772c1a8704fd9e18317aff21e050fb..HEAD | head -1)"
test "$(git rev-parse "${first_feature_commit}^")" = \
  "d005ca94fc772c1a8704fd9e18317aff21e050fb"
git log --format='%H %P %s' \
  d005ca94fc772c1a8704fd9e18317aff21e050fb..HEAD
test "$(git rev-list --merges \
  d005ca94fc772c1a8704fd9e18317aff21e050fb..HEAD --count)" = "0"
git diff --check d005ca94fc772c1a8704fd9e18317aff21e050fb...HEAD
git diff --name-only d005ca94fc772c1a8704fd9e18317aff21e050fb...HEAD
```

Review还必须证明：

- first feature parent精确为`B_V_READY`，不是Plan/execution-owner merge；全部commits、逐commit changed-files与8-file allowlist闭合。
- feature开始前与reviewed head上的allowlist外direct v1 AST consumer均为0。
- 7个legacy target在owned production/tests的definition/import/reference/reflection/runtime export为0。
- current input/shared/v2 target完整存在，Control Gateway安全断言未通过删除用例降级。
- independent exact-head review为`0/0/0/0`。
- latest integration overlay的8 owned blobs与reviewed feature相同，patch等价；post-merge full通过后才记录barrier。

## Cross-file impact

- execution-owner r5已拥有`B_V_READY → 01-07V → B_RU_V2_CONTRACT`；本Plan不得修改该owner。
- `.planning/STATE.md`、Roadmap、Requirements、W2 Validation、`PROJECT_DIRECTION.md`与`README.md`仍是stale derived evidence，且不在本Packet ownership内；后续只能由dedicated status Packet对齐。
- historical physical-v1 family labels与absence guard由Application/Infrastructure/Eval owner维护；V只证明它们不是direct Core consumer，不越权删除。
- active canonical owner无需语义变更；本Packet只实施已批准的contract closure。
- Graphify保持闲置。

## Handoff

```text
Task Packet: 01-07V
Base SHA / tree:
Branch / Worktree:
RED commit and expected failure:
GREEN/fix commits:
Reviewed exact head / tree:
Actual changed files:
Commands and exact results:
Allowlist / lineage / containment:
Non-owned direct consumer preflight:
Legacy absence / current-v2 preservation:
Control Gateway v2 migration:
Contract changes:
Security impact:
Eval impact:
Latest integration overlay:
PR / merge commit:
Post-merge B_RU_V2_CONTRACT SHA / tree:
Unresolved risks:
Rollback:
Recommended next step:
```

Agent完成不等于`B_RU_V2_CONTRACT`、01-08、Trajectory/E2E Case PASS或P0产品完成。
