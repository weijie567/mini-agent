---
phase: 01-cycle-1-e2e-01
plan: 01-07V-EVAL-HANDOFF
type: execute
wave: pre-01-07V
depends_on:
  - B_W
  - p0-ru-v2-execution-map-r5
files_modified:
  - tests/component/evaluation/test_e2e01_artifact_consistency.py
autonomous: true
requirements:
  - E2E01-01
  - E2E01-04
user_setup: []
must_haves:
  truths:
    - "Eval artifact-consistency Component test不再import或construct Core v1 RequestUnderstandingOutput。"
    - "stale new-goal base-version rejection改由exact RequestUnderstandingOutputV2 schema/contextualization验证，并继续因non-null base精确fail closed。"
    - "同一test中的fact-bearing PresentationPlan rejection保持不变。"
    - "本remediation不修改Eval artifacts、Dataset、grader、production source、Core、migration或42 denominator。"
    - "reviewed merge与post-merge gate只形成B_V_READY；01-07V仍未实现，且只能从exact B_V_READY另建feature。"
  artifacts:
    - path: tests/component/evaluation/test_e2e01_artifact_consistency.py
      provides: "v2-only Eval artifact DTO contract consumer"
  key_links:
    - from: "exact B_W"
      to: "01-07V-EVAL-HANDOFF"
      via: "single Eval-owner test file"
    - from: "01-07V-EVAL-HANDOFF reviewed merge"
      to: "B_V_READY"
      via: "latest-integration replay and post-merge full gate"
    - from: "B_V_READY"
      to: "01-07V"
      via: "new exact Core feature base"
---

# Phase 1 Plan 01-07V-EVAL-HANDOFF｜Eval v1 consumer handoff

> 本 Plan 是 execution-map r5 已授权的 denominator-neutral remediation Task Packet。Plan branch/worktree只拥有本 Plan 文件；remediation feature必须从原 exact `B_W` 创建，不能使用 PR #145 merge、本 Plan merge或任何 status/documentation SHA作为feature base。

## 目标

Purpose: exact `B_W` 已关闭 Application codec、records与Ports的RU-v1 executable surface，但Eval owner的artifact-consistency Component test仍直接import并construct Core v1 `RequestUnderstandingOutput`。01-07V不能在自身Core allowlist内删除该type，因此必须先由Eval single writer迁移这一consumer。

Output: 单文件、两提交的RED→GREEN remediation。RED先把测试绑定切到`RequestUnderstandingOutputV2`而保留旧payload，产生可解释的schema/contextualization失败；GREEN补齐exact v2 payload与错误断言，同时保持PresentationPlan拒绝证据不变。

## 事实与边界

- `CONFIRMED`：input barrier为exact `B_W = 556ab06cedccabc5e862647570a47adecab33b90`，tree `f28f7f18376917ccaac4a79279546e1261248582`。
- `CONFIRMED`：execution-owner r5 reviewed merge为`7883d8e6535c54b278e8918d7098dc74ad311be6`，tree `965b1e0722ac65cd53505f64f842fb2b8e4b571c`；它只授权route，不替换feature base。
- `CONFIRMED`：exact `B_W`上的owned test blob为`25cbbc7d1134c4c7c12611f3b0b179e15427e98c`，line 19 import并在line 550 construct v1 `RequestUnderstandingOutput`。
- `CONFIRMED`：同一test的PresentationPlan fact-bearing rejection位于紧随其后的subcase，必须byte-for-byte保留该subcase。
- `CONFIRMED`：Core protected blobs为：
  - `src/mini_agent/core/request_understanding.py = 018ea446517c099cc061de6e99afe55db10e8afb`
  - `src/mini_agent/core/task_state.py = 122b62b7a68ae0b92adfb3208ef9845fdd646fbe`
  - `src/mini_agent/core/request_processing.py = 8453214be8a66b3bd51c77a27ba588f5ee56353e`
- `OPEN / NONCLAIM`：本Packet不删除任何Core v1 type/reducer，不形成`B_RU_V2_CONTRACT`，不解锁01-08，不证明Trajectory/E2E/Case PASS或产品ready。

## Canonical owner

- `docs/implementation/e2e01-thin-slice-multi-agent-plan.md` marker-bounded `p0-ru-v2-execution-map-r5`拥有本Packet顺序、writer、allowlist与barrier。
- `docs/implementation/e2e01-thin-slice-implementation-spec.md`拥有Thin Slice scoped schema与Eval artifact语义。
- `docs/architecture/intent-design-reference.md`拥有Request Understanding v2 output/contextualization规范。
- `docs/evaluation/agent-evaluation-strategy.md`拥有Eval生命周期与grader边界。
- 本 Plan 只拥有执行拆分，不覆盖上述语义owner。

## Task Packet

```text
task_packet: 01-07V-EVAL-HANDOFF
repository: https://github.com/weijie567/mini-agent.git
remote: origin
base_branch: integration/e2e01-thin
base_sha: 556ab06cedccabc5e862647570a47adecab33b90
base_tree: f28f7f18376917ccaac4a79279546e1261248582
branch: codex/e2e01-01-ru-v1-eval-consumer-handoff
worktree: e2e01-01-ru-v1-eval-consumer-handoff
writer: Eval artifact consistency v1-consumer handoff sole writer
allowlist:
  - tests/component/evaluation/test_e2e01_artifact_consistency.py
forbidden:
  - all files outside the one-file allowlist
  - src/**
  - evals/**
  - docs/**
  - .planning/**
  - migrations/**
dependencies:
  - exact B_W reviewed merge and post-merge gates
  - p0-ru-v2-execution-map-r5 reviewed merge
output_barrier: B_V_READY
denominator_delta: 0
```

## 实现合同

1. RED commit只修改owned test：
   - 将Core import与validation target从v1 `RequestUnderstandingOutput`改为`RequestUnderstandingOutputV2`；
   - 将expected error切到v2 new-goal null-base contract；
   - 暂不补`contextualization`且保留旧schema literal，使focused test只因v2 payload尚未对齐而失败；
   - 不修改PresentationPlan subcase。
2. GREEN commit仍只修改owned test：
   - `schema_version`精确为`e2e01-thin-v2`；
   - 增加唯一actual `contextualization`，其`text`、resolved `order_id`、`source_kind=CURRENT_MESSAGE`、`source_ref`、bounded `source_quote`、`confidence`与`source_message_refs`相互闭合；
   - 保留原`TaskDeltaCandidate`与`NextMove`的业务含义，只让`base_task_state_version=1`成为预期拒绝原因；
   - error match精确为`new-goal v2 candidate must use a null base Task version`。
3. 不增加v1 alias、union、fallback、dynamic version selection或测试侧重建production Evidence。
4. 不修改任何JSON artifact、Case、Manifest、Lane、grader、Provider、Harness或production source。

## 验证

```bash
git diff --check
test "$(git rev-parse 556ab06cedccabc5e862647570a47adecab33b90:tests/component/evaluation/test_e2e01_artifact_consistency.py)" = \
  "25cbbc7d1134c4c7c12611f3b0b179e15427e98c"
uv run pytest tests/component/evaluation/test_e2e01_artifact_consistency.py -q
uv run pytest \
  tests/component/evaluation/test_e2e01_artifact_consistency.py \
  tests/component/evaluation/test_e2e01_graders.py \
  tests/component/evaluation/test_e2e01_scripted_model_provider.py \
  tests/component/model/test_e2e01_scripted_scenario_catalog.py \
  tests/component/model/test_qwen_responses_adapter.py -q
uv run pytest tests/component/core/test_request_understanding_contract.py -q
uv run pytest tests/integration/evaluation/test_e2e01_offline_harness.py -q
uv run pytest
```

机械 containment：

```bash
test "$(git merge-base HEAD 556ab06cedccabc5e862647570a47adecab33b90)" = \
  "556ab06cedccabc5e862647570a47adecab33b90"
test "$(git diff --name-only 556ab06cedccabc5e862647570a47adecab33b90...HEAD)" = \
  "tests/component/evaluation/test_e2e01_artifact_consistency.py"
test "$(git rev-list --merges 556ab06cedccabc5e862647570a47adecab33b90..HEAD --count)" = "0"
test "$(git rev-parse HEAD:src/mini_agent/core/request_understanding.py)" = \
  "018ea446517c099cc061de6e99afe55db10e8afb"
test "$(git rev-parse HEAD:src/mini_agent/core/task_state.py)" = \
  "122b62b7a68ae0b92adfb3208ef9845fdd646fbe"
test "$(git rev-parse HEAD:src/mini_agent/core/request_processing.py)" = \
  "8453214be8a66b3bd51c77a27ba588f5ee56353e"
```

Review前还必须证明：

- owned file中不存在v1 `RequestUnderstandingOutput` import、constructor或validation target；
- v2 contextualization真实包含本次message_ref与resolved order source；
- PresentationPlan subcase的AST/文本blob片段与base一致；
- allowlist外文件0变更；
- independent exact-head review为`0/0/0/0`；
- latest-integration overlay的owned blob与patch等于reviewed feature。

## contract_changes

`EVAL COMPONENT CONSUMER HANDOFF ONLY`：artifact-consistency测试从已退役的v1 model-output DTO迁移到current v2 DTO。Thin Slice、Intent、Memory、Tool、Application、Infrastructure、physical schema与production runtime合同不变。

## security_impact

`NONE / BOUNDARY PRESERVING`：不改变trusted identity、resource ownership、minimal disclosure、Evidence、ActionPolicy、atomic write、error redaction或外部系统连接；不新增secret、真实客户数据或PII。

## eval_impact

`COMPONENT CONTRACT ALIGNMENT`：保留同一stale-base与fact-bearing Presentation failure evidence，只移除v1 DTO consumer。不修改或激活Dataset Case，不改变grader、Trajectory/E2E Result、报告、threshold或42 denominator。

## rollback

- 未merge：关闭draft PR并保留RED/GREEN与review evidence。
- handoff已merge且01-07V未merge：普通revert handoff merge，复跑owned Eval、Core neighbor、offline harness与full；revert SHA不得冒充原`B_W`。
- 01-07V已merge：先普通revert V，再revert本handoff；任何downstream status alignment按逆序回退。禁止reset/force。
- 本Packet不迁移或删除physical rows，rollback不得声称恢复数据库内容。

## 交接格式

```text
Task Packet: 01-07V-EVAL-HANDOFF
Base SHA / tree:
Branch / Worktree:
RED commit and expected failure:
GREEN/fix commits:
Reviewed exact head / tree:
Actual changed files:
Commands and exact results:
Allowlist / containment result:
v1 consumer absence / v2 payload closure:
Protected Core blobs:
Contract changes:
Security impact:
Eval impact:
Latest integration overlay:
PR / merge commit:
Post-merge B_V_READY SHA / tree:
Unresolved risks:
Rollback:
Recommended next step:
```

## Cross-file impact

- execution-owner r5已把V feature base改为`B_V_READY`；本 Plan不得再修改canonical execution map。
- `.planning/ROADMAP.md`、`.planning/STATE.md`、`.planning/REQUIREMENTS.md`、W2 Validation、`PROJECT_DIRECTION.md`与`README.md`属于其他single writer，待dedicated status Packet对齐；本 Plan不越权修改。
- 01-07V Core Plan/feature必须等待本Packet reviewed merge与post-merge gate，且只能从exact `B_V_READY`启动。
- Graphify按用户要求保持闲置。
