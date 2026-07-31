---
phase: 01-cycle-1-e2e-01
plan: 07O
type: execute
wave: 18
depends_on:
  - 01-07N
files_modified:
  - docs/implementation/e2e01-thin-slice-multi-agent-plan.md
autonomous: true
requirements:
  - E2E01-01
  - E2E01-04
user_setup: []
must_haves:
  truths:
    - "execution-plan owner 以唯一 marker-bounded JSON map 把 canonical `CORE_EXPAND → CODEC_EXPAND → DEPENDENCY_EXPAND → ACTIVE_SWITCH → CONTRACT` 映射为精确 Packet、writer、branch、logical Worktree、owned files、symbolic barrier 与串行集成顺序；prose 不维护第二套映射。"
    - "`01-07F` 是 `CORE_EXPAND`，从 status-aligned `B_O_STATUS` 执行并先形成 `B_F`；`01-07E` 是 `CODEC_EXPAND`，只能从 `B_F` 执行并形成 `B_FE_EXPAND`。两者使用不同 Worktree，但不再同 base 并行写入。"
    - "`B_FE_EXPAND` 只证明 additive Core v2 types 与 exact-version codec catalog/API；active registry、既有 codec API、PostgreSQL、Runtime routing、Provider/Eval consumers、v1 contract 与 readiness 都保持未切换。"
    - "`DEPENDENCY_EXPAND` 完整通过且 current v1 rows 已隔离前不得进入 `ACTIVE_SWITCH`；Provider/Eval、Runtime、Application codec、Core 的 `CONTRACT` 必须逐 owner 收缩，Core v1 surface 最后关闭。"
    - "原目标分母29增加 `01-07N/O/P/Q/S/T/U/V/W/X` 十个 Packet 后固定为39；条件式 physical v1 representation retirement 只在 owner 裁决要求时激活 `01-07R` 并把分母变为40。"
    - "01-07O reviewed merge后必须先由 dedicated planning-status single writer 对齐 PROJECT、REQUIREMENTS、ROADMAP、STATE、W2 Validation 与 N/O Summary，再由 Project Direction sole writer 独立对齐 active owner；两道 PR 均 reviewed merge形成 `B_O_STATUS` 前不得签发01-07F。"
    - "本 Packet 只修改 multi-agent execution-plan owner；不修改 Thin Slice、Intent、Memory、源码、测试、migration、Eval、共享 planning 状态或 lifecycle。"
  artifacts:
    - "docs/implementation/e2e01-thin-slice-multi-agent-plan.md 中唯一 P0 RU v2 execution map、阶段说明与实时状态纠偏。"
  key_links:
    - "01-07O feature 从 exact 01-07N merge `a4b1edb...` 执行；01-07N owner manifest 与 Plan blob作为 immutable canonical inputs。"
    - "01-07O reviewed merge只授权 dedicated planning-status alignment；status reviewed merge后才可分别签发F Plan和F feature。"
---

# Phase 1 Plan 01-07O｜Request Understanding v2 execution-plan alignment

> **ISSUED EXECUTION-PLAN ALIGNMENT TASK PACKET / FEATURE NOT STARTED**
> 01-07N 已关闭 nested DTO、rejection partition、provenance responsibility 与 owner-neutral cutover protocol，但明确不拥有执行拆分。本 Packet 只把该 protocol 映射为可串行全绿的 owner Packet；它不实现任何 v2 Python、codec、migration、consumer 或 contract removal。

> **DERIVED / NON_NORMATIVE**
> 本 Plan 与 owned execution-plan 都不能覆盖 Thin Slice、Intent、Memory、Tool、Business 或 Eval owner。所有 future Packet 在签发时必须重新冻结实际 exact base SHA；本文中的 future barrier 名称只表示依赖关系，不伪造尚未产生的 commit。

<objective>
关闭 01-07N 后仍存在的 execution ownership blocker：撤销旧的 E/F 同 base 并行授权，把五阶段 cutover 映射为精确、single-writer、可独立审查的 Task Packets，并固定分母与状态对齐 barrier。

Purpose: 让 Integrator 可以先签发并实现 `01-07F CORE_EXPAND`，再签发并实现 `01-07E CODEC_EXPAND`，且每一步保持默认 full suite 全绿、active runtime 不变。

Output: 恰好一个 owner commit，只修改 `docs/implementation/e2e01-thin-slice-multi-agent-plan.md`；不修改 canonical semantic owner、源码、测试、migration、Eval、`.planning/`共享状态或 lifecycle。
</objective>

<execution_context>
@AGENTS.md
@.planning/GOVERNANCE.md
@.planning/phases/01-cycle-1-e2e-01/01-07N-PLAN.md
@docs/architecture/intent-design-reference.md
@docs/architecture/memory-design-reference.md
@docs/implementation/e2e01-thin-slice-implementation-spec.md
@docs/implementation/e2e01-thin-slice-multi-agent-plan.md

不得调用 stock `gsd-plan-phase`、`gsd-execute-phase`、`gsd-verify-work`、lifecycle mutation 或 `gsd-ship`。不得把 scoped owner manifest、Plan、当前 v1 源码或 Graphify 输出当作 execution ownership owner。
</execution_context>

<packet_contract>
repository: `https://github.com/weijie567/mini-agent`
remote: `origin`
head_branch: `codex/e2e01-01-ru-v2-execution-alignment`
base_branch: `integration/e2e01-thin`
base_sha: `a4b1edb4c50a2e3e826571194bac58f7b31eab6d`
base_tree: `469e26460c1041d9ca5042d39ae9a57ded7d5442`
planning_context_sha: `a4b1edb4c50a2e3e826571194bac58f7b31eab6d`
planning_context_tree: `469e26460c1041d9ca5042d39ae9a57ded7d5442`
worktree_id: `e2e01-01-ru-v2-execution-alignment`
writer: `multi-agent execution-plan sole writer, supervised by /root Integrator`
agent_role: `gsd-doc-writer`

物理 Worktree path 只由 Integrator 私下 dispatch，不写入 Plan、commit 或 PR。

owned_files:

- `docs/implementation/e2e01-thin-slice-multi-agent-plan.md`

forbidden_files:

- every repository path not listed in `owned_files`
- `AGENTS.md`
- `PROJECT_DIRECTION.md`
- `README.md`
- `.planning/**`
- `docs/business-capabilities.md`
- `docs/architecture/**`
- `docs/implementation/e2e01-thin-slice-implementation-spec.md`
- every other `docs/implementation/**` path
- `docs/evaluation/**`
- `src/**`
- `tests/**`
- `evals/**`
- `alembic/**`
- `pyproject.toml`
- `uv.lock`
- `compose.yaml`
- `graphify-out/**`

canonical_inputs:

- exact 01-07N reviewed merge / tree：`a4b1edb4c50a2e3e826571194bac58f7b31eab6d` / `469e26460c1041d9ca5042d39ae9a57ded7d5442`
- 01-07N Plan blob：`f679872c424a53e9acbe59a4d5bc116d13b1dcc1`
- Thin Slice owner blob：`233a9c06ef6ef9300bef1a0e4f86659b0ec26a13`
- execution-plan owner blob：`734e05be55f9b465020445069495245a212ddb38`
- Intent / Memory owner blobs：`456be9c7d7884e2a58c4d07b867765ed336aa6f5` / `5c27ba3bd2ed74e5164bdd0812133041ed96f242`
- Governance / project rules blobs：`bd5c92a7e5369cbeb1d152caa3eed736938e94c4` / `e4742ea091b963e6ff77508d43c8d1c9863f69c1`
- stale derived status blobs（只作 impact input，不由本 Packet 修改）：ROADMAP `77825f1fe4e4f78e972b363f743ccee12e44c2d6`、STATE `b3016e9e48f5f75a9b32c47113be09f654a2ecb8`、W2 Validation `a9f7f7d650edb17a521e8bc4928bdb19894c43f1`

dependencies:

- 本 Plan planning PR 必须先取得 independent exact-head `PASS` 并 reviewed merge；Executor记录 official planning commit与本 Plan blob。
- feature Worktree必须从固定 `base_sha` clean创建；planning merge只作为 captured Git object读取，不改变execution base。
- preflight必须证明feature HEAD/tree恰为exact 01-07N merge，Thin Slice / execution-plan / Plan / governance blobs匹配；任一 drift 都 `BLOCK`。
- feature reviewed merge后先建立 dedicated planning-status Worktree，只允许 `.planning/PROJECT.md`、`.planning/REQUIREMENTS.md`、`.planning/ROADMAP.md`、`.planning/STATE.md`、`.planning/phases/01-cycle-1-e2e-01/01-W2-VALIDATION.md`、`01-07N-SUMMARY.md` 与 `01-07O-SUMMARY.md`，reviewed merge形成 `B_O_PLANNING_STATUS`。
- `PROJECT_DIRECTION.md` 必须随后由独立 active-owner Worktree / PR 单写并reviewed merge；只有该第二道merge同时包含execution-plan、planning-status与Project Direction对齐时才实例化 `B_O_STATUS` 并解锁01-07F planning。
- 01-07F reviewed merge形成 `B_F` 前，01-07E planning/feature均 `BLOCK`。E Worktree不得从 `B_DH`、01-07N head、01-07O head或未审 F branch创建。
- `B_FE_EXPAND` 后续只能按 execution map推进；单边 branch head、planning artifact、overlay或 codec decode success都不构成下一stage barrier。

expected_execution_map:

下列 marker-bounded JSON 是本 Plan 对 feature writer 的 closed expected value。feature只能逐字转录到execution-plan owner的 `P0-RU-V2-EXECUTION-MAP` marker并添加必要解释；不得新增、删除、重命名或重排 JSON member / array。future symbolic barrier只在对应reviewed serial merge发生后实例化，future Packet签发时仍须冻结当时exact SHA。

<!-- P0-RU-V2-EXPECTED-EXECUTION-MAP:START -->
```json
{
  "manifest_version": "p0-ru-v2-execution-map-r1",
  "canonical_input": {
    "owner_path": "docs/implementation/e2e01-thin-slice-implementation-spec.md",
    "manifest_version": "p0-ru-v2-cutover-r1",
    "stages": [
      "CORE_EXPAND",
      "CODEC_EXPAND",
      "DEPENDENCY_EXPAND",
      "ACTIVE_SWITCH",
      "CONTRACT"
    ]
  },
  "lineage": {
    "root_barrier": "B_DH",
    "root_sha": "4a7e802e8aebc54e0582a1e4d99f140b56e7b131",
    "remediation_packet": "01-07N",
    "remediation_merge_sha": "a4b1edb4c50a2e3e826571194bac58f7b31eab6d",
    "alignment_packet": "01-07O"
  },
  "pre_core_status_chain": [
    {
      "gate": "B_O_PLANNING_STATUS",
      "writer": "planning-status sole writer",
      "owned_files": [
        ".planning/PROJECT.md",
        ".planning/REQUIREMENTS.md",
        ".planning/ROADMAP.md",
        ".planning/STATE.md",
        ".planning/phases/01-cycle-1-e2e-01/01-W2-VALIDATION.md",
        ".planning/phases/01-cycle-1-e2e-01/01-07N-SUMMARY.md",
        ".planning/phases/01-cycle-1-e2e-01/01-07O-SUMMARY.md"
      ],
      "advances_lifecycle": false
    },
    {
      "gate": "B_O_STATUS",
      "writer": "Project Direction sole writer",
      "owned_files": [
        "PROJECT_DIRECTION.md"
      ],
      "requires": "B_O_PLANNING_STATUS",
      "advances_lifecycle": false
    }
  ],
  "stages": [
    {
      "stage": "CORE_EXPAND",
      "waves": [
        {
          "input_barrier": "B_O_STATUS",
          "output_barrier": "B_F",
          "packets": [
            {
              "packet_id": "01-07F",
              "writer": "Request Understanding Core sole writer",
              "branch": "codex/e2e01-01-ru-v2-core-expand",
              "worktree_id": "e2e01-01-ru-v2-core-expand",
              "owned_files": [
                "src/mini_agent/core/request_understanding.py",
                "src/mini_agent/core/task_state.py",
                "src/mini_agent/core/request_processing.py",
                "tests/component/core/test_request_understanding_contract.py",
                "tests/component/core/test_task_state_contract.py",
                "tests/component/core/test_request_processing.py"
              ],
              "active_routing": false,
              "protected_v1_surface": {
                "mode": "all-preexisting-top-level-definitions",
                "base_sha": "a4b1edb4c50a2e3e826571194bac58f7b31eab6d",
                "files": [
                  "src/mini_agent/core/request_understanding.py",
                  "src/mini_agent/core/task_state.py",
                  "src/mini_agent/core/request_processing.py"
                ],
                "allow_changed_existing_symbols": []
              }
            }
          ]
        }
      ]
    },
    {
      "stage": "CODEC_EXPAND",
      "waves": [
        {
          "input_barrier": "B_F",
          "output_barrier": "B_FE_EXPAND",
          "packets": [
            {
              "packet_id": "01-07E",
              "writer": "Application persistence codec sole writer",
              "branch": "codex/e2e01-01-ru-v2-codec-expand",
              "worktree_id": "e2e01-01-ru-v2-codec-expand",
              "owned_files": [
                "src/mini_agent/application/persistence.py",
                "tests/component/application/test_persistence_contract.py"
              ],
              "active_routing": false,
              "protected_v1_surface": {
                "mode": "all-preexisting-top-level-definitions",
                "base_barrier": "B_F",
                "files": [
                  "src/mini_agent/application/persistence.py"
                ],
                "allow_changed_existing_symbols": []
              }
            }
          ]
        }
      ]
    },
    {
      "stage": "DEPENDENCY_EXPAND",
      "waves": [
        {
          "input_barrier": "B_FE_EXPAND",
          "output_barrier": "B_IP",
          "packets": [
            {
              "packet_id": "01-07I",
              "writer": "Application Port declaration sole writer",
              "branch": "codex/e2e01-01-exact-run-evidence-port",
              "worktree_id": "e2e01-01-exact-run-evidence-port",
              "owned_files": [
                "src/mini_agent/application/records.py",
                "src/mini_agent/application/ports.py",
                "tests/component/application/test_record_contracts.py",
                "tests/component/application/test_ports_contract.py"
              ],
              "active_routing": false
            },
            {
              "packet_id": "01-07P",
              "writer": "Infrastructure migration-chain sole writer",
              "branch": "codex/e2e01-01-ru-v2-physical-expand",
              "worktree_id": "e2e01-01-ru-v2-physical-expand",
              "owned_files": [
                "alembic/versions/20260728_0003_request_understanding_v2_expand.py",
                "src/mini_agent/infrastructure/persistence/models.py",
                "tests/integration/test_database_migrations.py"
              ],
              "active_routing": false
            }
          ]
        },
        {
          "input_barrier": "B_IP",
          "output_barrier": "B_DEPENDENCY",
          "packets": [
            {
              "packet_id": "01-07K",
              "writer": "Infrastructure persistence/read adapter sole writer",
              "branch": "codex/e2e01-01-strict-readers",
              "worktree_id": "e2e01-01-strict-readers",
              "owned_files": [
                "src/mini_agent/infrastructure/persistence/postgres.py",
                "src/mini_agent/infrastructure/order/postgres.py",
                "tests/integration/test_postgres_record_adapters.py",
                "tests/integration/test_postgres_get_order.py"
              ],
              "active_routing": false
            },
            {
              "packet_id": "01-07L",
              "writer": "Eval Provider and mapper sole writer",
              "branch": "codex/e2e01-01-eval-mapper",
              "worktree_id": "e2e01-01-eval-mapper",
              "owned_files": [
                "src/mini_agent/evaluation/harness.py",
                "src/mini_agent/evaluation/graders.py",
                "src/mini_agent/evaluation/scripted_provider.py",
                "src/mini_agent/infrastructure/model/qwen_responses.py",
                "tests/component/evaluation/test_e2e01_artifact_consistency.py",
                "tests/component/evaluation/test_e2e01_graders.py",
                "tests/component/evaluation/test_e2e01_scripted_model_provider.py",
                "tests/component/model/test_qwen_responses_adapter.py",
                "tests/integration/evaluation/test_e2e01_offline_harness.py"
              ],
              "active_routing": false
            }
          ]
        },
        {
          "input_barrier": "B_DEPENDENCY",
          "output_barrier": "B_DEPENDENCY_M",
          "packets": [
            {
              "packet_id": "01-07M",
              "writer": "Order Core contract sole writer",
              "branch": "codex/e2e01-01-order-source-version-closure",
              "worktree_id": "e2e01-01-order-source-version-closure",
              "owned_files": [
                "src/mini_agent/core/order.py",
                "tests/component/core/test_memory_trace_presentation_contract.py"
              ],
              "active_routing": false
            }
          ]
        }
      ]
    },
    {
      "stage": "ACTIVE_SWITCH",
      "waves": [
        {
          "input_barrier": "B_DEPENDENCY_M",
          "output_barrier": "B_Q",
          "packets": [
            {
              "packet_id": "01-07Q",
              "writer": "Application persistence codec active-switch sole writer",
              "branch": "codex/e2e01-01-ru-v2-codec-active-switch",
              "worktree_id": "e2e01-01-ru-v2-codec-active-switch",
              "owned_files": [
                "src/mini_agent/application/persistence.py",
                "tests/component/application/test_persistence_contract.py"
              ],
              "active_routing": true,
              "requires_current_v1_isolation": true
            }
          ]
        },
        {
          "input_barrier": "B_Q",
          "output_barrier": "B_ACTIVE",
          "packets": [
            {
              "packet_id": "01-07J",
              "writer": "Application Runtime consumer sole writer",
              "branch": "codex/e2e01-01-runtime-v2-switch",
              "worktree_id": "e2e01-01-runtime-v2-switch",
              "owned_files": [
                "src/mini_agent/application/agent_run_service.py",
                "src/mini_agent/application/read_tool_executor.py",
                "tests/component/application/test_agent_run_service.py",
                "tests/component/application/test_read_tool_executor.py"
              ],
              "active_routing": true
            }
          ]
        }
      ]
    },
    {
      "stage": "CONTRACT",
      "waves": [
        {
          "input_barrier": "B_ACTIVE",
          "output_barrier": "B_SU",
          "packets": [
            {
              "packet_id": "01-07S",
              "writer": "Eval Provider v1-contract sole writer",
              "branch": "codex/e2e01-01-ru-v1-provider-contract",
              "worktree_id": "e2e01-01-ru-v1-provider-contract",
              "owned_files": [
                "src/mini_agent/evaluation/harness.py",
                "src/mini_agent/evaluation/graders.py",
                "src/mini_agent/evaluation/scripted_provider.py",
                "src/mini_agent/infrastructure/model/qwen_responses.py",
                "tests/component/evaluation/test_e2e01_artifact_consistency.py",
                "tests/component/evaluation/test_e2e01_graders.py",
                "tests/component/evaluation/test_e2e01_scripted_model_provider.py",
                "tests/component/model/test_qwen_responses_adapter.py",
                "tests/integration/evaluation/test_e2e01_offline_harness.py"
              ],
              "removes_v1_surface": true
            },
            {
              "packet_id": "01-07U",
              "writer": "Application Runtime v1-contract sole writer",
              "branch": "codex/e2e01-01-ru-v1-runtime-contract",
              "worktree_id": "e2e01-01-ru-v1-runtime-contract",
              "owned_files": [
                "src/mini_agent/application/agent_run_service.py",
                "src/mini_agent/application/read_tool_executor.py",
                "tests/component/application/test_agent_run_service.py",
                "tests/component/application/test_read_tool_executor.py"
              ],
              "removes_v1_surface": true
            }
          ]
        },
        {
          "input_barrier": "B_SU",
          "output_barrier": "B_X",
          "packets": [
            {
              "packet_id": "01-07X",
              "writer": "Infrastructure persistence adapter v1-contract sole writer",
              "branch": "codex/e2e01-01-ru-v1-infra-contract",
              "worktree_id": "e2e01-01-ru-v1-infra-contract",
              "owned_files": [
                "src/mini_agent/infrastructure/persistence/postgres.py",
                "tests/integration/test_postgres_record_adapters.py"
              ],
              "removes_v1_surface": true
            }
          ]
        },
        {
          "input_barrier": "B_X",
          "output_barrier": "B_T",
          "packets": [
            {
              "packet_id": "01-07T",
              "writer": "Application persistence codec v1-contract sole writer",
              "branch": "codex/e2e01-01-ru-v1-codec-contract",
              "worktree_id": "e2e01-01-ru-v1-codec-contract",
              "owned_files": [
                "src/mini_agent/application/persistence.py",
                "tests/component/application/test_persistence_contract.py"
              ],
              "removes_v1_surface": true
            }
          ]
        },
        {
          "input_barrier": "B_T",
          "output_barrier": "B_W",
          "packets": [
            {
              "packet_id": "01-07W",
              "writer": "Application Port and records v1-contract sole writer",
              "branch": "codex/e2e01-01-ru-v1-application-contract",
              "worktree_id": "e2e01-01-ru-v1-application-contract",
              "owned_files": [
                "src/mini_agent/application/records.py",
                "src/mini_agent/application/ports.py",
                "tests/component/application/test_record_contracts.py",
                "tests/component/application/test_ports_contract.py"
              ],
              "removes_v1_surface": true
            }
          ]
        },
        {
          "input_barrier": "B_W",
          "output_barrier": "B_RU_V2_CONTRACT",
          "packets": [
            {
              "packet_id": "01-07V",
              "writer": "Request Understanding Core v1-contract sole writer",
              "branch": "codex/e2e01-01-ru-v1-core-contract",
              "worktree_id": "e2e01-01-ru-v1-core-contract",
              "owned_files": [
                "src/mini_agent/core/request_understanding.py",
                "src/mini_agent/core/task_state.py",
                "src/mini_agent/core/request_processing.py",
                "tests/component/core/test_control_gateway.py",
                "tests/component/core/test_identity_contract.py",
                "tests/component/core/test_request_understanding_contract.py",
                "tests/component/core/test_task_state_contract.py",
                "tests/component/core/test_request_processing.py"
              ],
              "removes_v1_surface": true,
              "must_be_last": true
            }
          ]
        }
      ]
    }
  ],
  "serial_order": [
    "01-07F",
    "01-07E",
    "01-07I+01-07P",
    "01-07K+01-07L",
    "01-07M",
    "01-07Q",
    "01-07J",
    "01-07S+01-07U",
    "01-07X",
    "01-07T",
    "01-07W",
    "01-07V"
  ],
  "denominator": {
    "previous_target": 29,
    "added_packets": [
      "01-07N",
      "01-07O",
      "01-07P",
      "01-07Q",
      "01-07S",
      "01-07T",
      "01-07U",
      "01-07V",
      "01-07W",
      "01-07X"
    ],
    "target": 39,
    "conditional_packet": {
      "packet_id": "01-07R",
      "status": "INACTIVE_OWNER_RULING_REQUIRED",
      "purpose": "physical-v1-representation-retirement",
      "activation_requires_execution_map_revision": true,
      "target_if_activated": 40
    }
  },
  "barrier_nonclaims": {
    "B_FE_EXPAND": [
      "active-registry-not-switched",
      "legacy-codec-api-unchanged",
      "postgresql-not-routed-to-v2",
      "runtime-provider-eval-not-routed-to-v2",
      "v1-contract-not-removed",
      "readiness-not-proven"
    ]
  },
  "next_after_contract": "01-08"
}
```
<!-- P0-RU-V2-EXPECTED-EXECUTION-MAP:END -->

required_checks:

- exact branch/base/tree/merge-base/clean state、Plan/owner/governance blobs与唯一planning provenance preflight
- 相对exact `base_sha` 恰好一个feature commit、changed-file set恰好等于唯一owned file
- execution-plan中恰好一个 marker-bounded `P0-RU-V2-EXECUTION-MAP` JSON；parser验证manifest version、五stage顺序与symbolic barriers
- map中01-07F/E顺序恰为 `B_O_STATUS → F → B_F → E → B_FE_EXPAND`，两个owned-file集合交集为0，F/E均禁止Application active consumer、Infra、Eval与migration
- F map必须以exact `a4b1edb...`为oracle、E map必须以reviewed `B_F`为oracle，分别保护三个Core owned source与Application codec source中全部pre-existing top-level definition的AST；允许新增显式v2 symbol但不允许修改、删除、重绑定任何existing definition，F/E Plan都必须提供对应机械snapshot gate
- map验证 01-07I/P/K/L/M/Q/J/S/U/T/V 的 exact writer、branch、logical Worktree、owned files、base barrier、output barrier与wave内文件交集
- map验证 `DEPENDENCY_EXPAND` 全部完成且 current v1 isolation gate通过后才出现Q/J；J不得早于K/L/M
- map验证 `CONTRACT` 顺序为 `{S,U} → X → T → W → V`；active consumers已在S/U迁移后，Infra先关闭v1 adapter、codec再关闭v1 API/test、Application Port/records最后关闭v1 command/Port，避免任何Packet依赖已删除的下游合同，Core v1最后关闭；conditional 01-07R默认inactive
- CONTRACT consumer inventory必须覆盖当前所有直接引用retiring RU v1 direct-binding type的Application、Infra、Eval与Core source/tests；01-07V签发前重复`rg`必须证明V owned Core files以外为`NOT_FOUND`
- 分母parser验证 previous=29、added恰为N/O/P/Q/S/T/U/V/W/X、target=39；只有R激活时target=40
- 删除或纠正所有仍声称 D/H未执行、E/F从B_DH同base并行、29为当前目标分母、Graphify未覆盖N的 active execution-plan状态
- dedicated planning-status follow-up清单恰含PROJECT、REQUIREMENTS、ROADMAP、STATE、W2 Validation、01-07N Summary与01-07O Summary；随后独立Project Direction one-file owner PR；两者均明确不推进canonical lifecycle
- local links、术语scan、`git diff --check` 与 full `uv run pytest`
- repository-wide impact scan记录所有仍消费旧顺序、旧分母或v1-only RU的active files，只记录不修改forbidden files
- independent exact-head canonical/ownership/security review；unresolved `CRITICAL / HIGH / MEDIUM = 0 / 0 / 0`
- latest-integration overlay不改写feature lineage，重复map parser、diff-check、focused scan与full suite

done_when:

- execution-plan owner拥有唯一可机械验证的五阶段执行映射
- F/E先后、各自allowlist、base/barrier与`B_FE_EXPAND` nonclaim无歧义
- 后续dependency/switch/contract没有继续沿用旧的J-before-K/L顺序
- 一个commit只改一个owned file，所有required checks通过
- reviewed merge只解锁 dedicated planning-status alignment；F仍等该status barrier

contract_changes: `YES / EXECUTION OWNERSHIP ONLY` — 撤销旧E/F同base并行与旧J-before-dependencies顺序，增加P/Q/S/T/U/V/W/X及conditional R映射，并把目标分母29更新为39；不改变Thin Slice、Intent、Memory、Business或Eval语义。
security_impact: `YES` — 通过owner/stage barrier阻断version confusion、v2未隔离即active routing、codec越权I/O、raw quote持久化、Provider/Runtime先切换、v1 contract过早移除与Core先于consumer收缩。
eval_impact: `YES / EXECUTION ORDER ONLY` — 后续Provider/Eval consumers必须在DEPENDENCY_EXPAND与CONTRACT各自Packet中迁移；本Packet不修改Dataset、Grader、Result、threshold、Case或lifecycle。
new_dependencies: `NONE`
nonclaims: `NO IMPLEMENTATION CLAIM` — 不声称F/E或任一future Packet已签发/实现，不声称database、Runtime、Provider、Eval、Trajectory/E2E、Qwen或P0产品ready。
graphify_disposition: `INTEGRATOR POST-MERGE SEMANTIC GATE` — feature writer不得修改`graphify-out/**`；reviewed merge后由Integrator运行AST + semantic refresh并核对Thin Slice manifest → execution map关系。失败时记录`NOT_RUN`并保持status/F blocked。
rollback: 合并前关闭PR；合并后普通revert PR并重新阻塞status alignment、F/E及全部cutover Packet。不得reset、force-push或恢复旧同base并行路径。

handoff_to: `/root Integrator`

handoff_format:

- repository / remote / branch / logical worktree / writer
- exact base/tree/planning/head/commit/tree、Plan/owner/governance blobs
- exact one-file feature与overlay containment
- stage→Packet map、F/E dependency、39 denominator、conditional R与所有barrier/nonclaims
- commands / exact results、cross-file impact、contract/security/Eval impact
- independent feature/overlay reviews、residual risks与rollback
</packet_contract>

<threat_model>

| threat_id | category | boundary | disposition | mitigation |
|---|---|---|---|---|
| `RUE-S01` | Spoofing | future Packet / branch → reviewed barrier | `MITIGATE / BLOCK` | exact base、single writer、exact-head review、symbolic barrier只由merge事实实例化 |
| `RUE-T01` | Tampering | stage / denominator / owner map | `MITIGATE / BLOCK` | marker-bounded JSON、exact parser、closed added set、unknown field拒绝 |
| `RUE-R01` | Repudiation | planning/branch head → completion claim | `MITIGATE / BLOCK` | reviewed merge、Summary与status evidence分离；branch head/overlay不升级状态 |
| `RUE-I01` | Information Disclosure | codec/Core Packet → message/diagnostics | `MITIGATE / BLOCK` | F纯Core、E pure codec zero-I/O；authoritative reads与diagnostics留给明确dependency owner |
| `RUE-D01` | Denial of Service | incompatible stage merge → permanent red suite | `MITIGATE / BOUNDED` | F→E串行、dependency-before-switch、每Packet full suite |
| `RUE-E01` | Elevation of Privilege | additive v2 → active/readiness | `MITIGATE / BLOCK` | `B_FE_EXPAND` non-routable nonclaim、current-v1 isolation与active switch独立review |

</threat_model>

<tasks>

<task type="auto">
  <name>Task 1: Freeze one exact execution map</name>
  <files>docs/implementation/e2e01-thin-slice-multi-agent-plan.md</files>
  <action>
在W3 RU closure段加入且只加入一个 `P0-RU-V2-EXECUTION-MAP` marker-bounded JSON。

JSON必须至少封闭：

1. `manifest_version = p0-ru-v2-execution-map-r1`；
2. `root_lineage = B_DH` 与 `remediation_merge = a4b1edb...`；
3. 五个stage按canonical顺序；
4. 每个Packet的ID、writer、branch、logical worktree、exact owned files、symbolic input/output barrier、active-routing布尔值；
5. required serial order与允许并行的wave；同wave owned-file交集为0；
6. denominator 29 + exact十项 = 39，以及默认inactive的conditional 01-07R / 40；
7. `B_FE_EXPAND`的closed nonclaims；
8. dedicated status follow-up exact file list。

不得把owner语义复制进map；用owner path + manifest version引用。
  </action>
  <verify>
使用Python从markers解析唯一JSON，拒绝prose-only、duplicate marker、unknown stage、错误F/E顺序、错误分母、文件重叠、J早于dependency、V非最后、active E/F或漏失status barrier。
    <automated>set -euo pipefail
test -n "${PLANNING_CONTRACT_SHA:-}"
uv run python - <<'PY'
import copy
import json
import os
import re
import subprocess
from pathlib import Path

PLAN_PATH = ".planning/phases/01-cycle-1-e2e-01/01-07O-PLAN.md"
OWNER = Path("docs/implementation/e2e01-thin-slice-multi-agent-plan.md")
EXPECTED_START = "<!-- P0-RU-V2-EXPECTED-EXECUTION-MAP:START -->"
EXPECTED_END = "<!-- P0-RU-V2-EXPECTED-EXECUTION-MAP:END -->"
ACTUAL_START = "<!-- P0-RU-V2-EXECUTION-MAP:START -->"
ACTUAL_END = "<!-- P0-RU-V2-EXECUTION-MAP:END -->"

def parse(text, start, end):
    lines = text.splitlines()
    assert lines.count(start) == 1 and lines.count(end) == 1
    match = re.search(
        re.escape(start) + r"\n```json\n(?P<body>.*?)\n```\n" + re.escape(end),
        text,
        re.S,
    )
    assert match is not None
    return json.loads(match.group("body"))

plan = subprocess.check_output(
    ["git", "show", f"{os.environ['PLANNING_CONTRACT_SHA']}:{PLAN_PATH}"],
    text=True,
)
expected = parse(plan, EXPECTED_START, EXPECTED_END)
actual = parse(OWNER.read_text(), ACTUAL_START, ACTUAL_END)
assert actual == expected
assert [item["stage"] for item in actual["stages"]] == [
    "CORE_EXPAND",
    "CODEC_EXPAND",
    "DEPENDENCY_EXPAND",
    "ACTIVE_SWITCH",
    "CONTRACT",
]
for stage in actual["stages"]:
    for wave in stage["waves"]:
        seen = set()
        for packet in wave["packets"]:
            owned = set(packet["owned_files"])
            assert len(owned) == len(packet["owned_files"])
            assert seen.isdisjoint(owned)
            seen.update(owned)
assert actual["serial_order"] == [
    "01-07F", "01-07E", "01-07I+01-07P", "01-07K+01-07L",
    "01-07M", "01-07Q", "01-07J", "01-07S+01-07U",
    "01-07X", "01-07T", "01-07W", "01-07V",
]
assert actual["denominator"]["previous_target"] + len(
    actual["denominator"]["added_packets"]
) == actual["denominator"]["target"] == 39
contract_files = {
    path
    for wave in actual["stages"][4]["waves"]
    for packet in wave["packets"]
    for path in packet["owned_files"]
}
required_contract_consumers = {
    "src/mini_agent/application/agent_run_service.py",
    "src/mini_agent/application/persistence.py",
    "src/mini_agent/application/ports.py",
    "src/mini_agent/application/records.py",
    "src/mini_agent/infrastructure/persistence/postgres.py",
    "src/mini_agent/evaluation/graders.py",
    "src/mini_agent/evaluation/scripted_provider.py",
    "src/mini_agent/infrastructure/model/qwen_responses.py",
    "src/mini_agent/core/request_understanding.py",
    "src/mini_agent/core/task_state.py",
    "src/mini_agent/core/request_processing.py",
    "tests/component/application/test_agent_run_service.py",
    "tests/component/application/test_persistence_contract.py",
    "tests/component/application/test_ports_contract.py",
    "tests/component/application/test_record_contracts.py",
    "tests/integration/test_postgres_record_adapters.py",
    "tests/component/evaluation/test_e2e01_artifact_consistency.py",
    "tests/component/evaluation/test_e2e01_graders.py",
    "tests/component/evaluation/test_e2e01_scripted_model_provider.py",
    "tests/component/model/test_qwen_responses_adapter.py",
    "tests/integration/evaluation/test_e2e01_offline_harness.py",
    "tests/component/core/test_control_gateway.py",
    "tests/component/core/test_identity_contract.py",
    "tests/component/core/test_request_understanding_contract.py",
    "tests/component/core/test_task_state_contract.py",
    "tests/component/core/test_request_processing.py",
}
assert required_contract_consumers <= contract_files

mutations = []
def mutate(name, fn):
    item = copy.deepcopy(expected)
    fn(item)
    mutations.append((name, item))

mutate("stage-reorder", lambda x: x["stages"].reverse())
mutate("f-wrong-input", lambda x: x["stages"][0]["waves"][0].update(input_barrier="B_DH"))
mutate("e-wrong-input", lambda x: x["stages"][1]["waves"][0].update(input_barrier="B_O_STATUS"))
mutate("f-active", lambda x: x["stages"][0]["waves"][0]["packets"][0].update(active_routing=True))
mutate("e-active", lambda x: x["stages"][1]["waves"][0]["packets"][0].update(active_routing=True))
mutate("q-j-swap", lambda x: x["serial_order"].__setitem__(5, "01-07J"))
mutate("v-not-last", lambda x: x["serial_order"].reverse())
mutate("denominator-38", lambda x: x["denominator"].update(target=38))
mutate("missing-status-file", lambda x: x["pre_core_status_chain"][0]["owned_files"].pop())
mutate("missing-project-direction", lambda x: x["pre_core_status_chain"].pop())
mutate("f-extra-owner", lambda x: x["stages"][0]["waves"][0]["packets"][0]["owned_files"].append("src/mini_agent/application/agent_run_service.py"))
mutate("f-v1-protection-disabled", lambda x: x["stages"][0]["waves"][0]["packets"][0].pop("protected_v1_surface"))
mutate("e-v1-protection-disabled", lambda x: x["stages"][1]["waves"][0]["packets"][0].pop("protected_v1_surface"))
mutate("missing-application-contract", lambda x: x["serial_order"].remove("01-07W"))
mutate("missing-infra-contract", lambda x: x["serial_order"].remove("01-07X"))
mutate("missing-eval-consumer-test", lambda x: x["stages"][4]["waves"][0]["packets"][0]["owned_files"].remove("tests/component/evaluation/test_e2e01_artifact_consistency.py"))
mutate("wave-file-collision", lambda x: x["stages"][2]["waves"][0]["packets"][1]["owned_files"].append("src/mini_agent/application/ports.py"))
mutate("conditional-r-active", lambda x: x["denominator"]["conditional_packet"].update(status="ACTIVE"))
for name, mutant in mutations:
    assert mutant != expected, name
print(f"execution_map=PASS mutations={len(mutations)} packets=15 target=39")
PY</automated>
  </verify>
  <done>
execution ownership、stage/barrier和分母可由一个JSON机械重放，旧流程不再可被误读为仍有效。
  </done>
</task>

<task type="auto">
  <name>Task 2: Align explanatory flow and live execution status</name>
  <files>docs/implementation/e2e01-thin-slice-multi-agent-plan.md</files>
  <action>
围绕JSON只保留必要解释：

- 记录N Plan/feature PR #62/#63及reviewed merge `a4b1edb...`；
- 明确D/H已完成，原 `{E,F}` 并行箭头被N/O supersede；
- 明确F/E独立Worktree但串行执行与merge；
- 把旧 `J → {K,L}` 更新为dependency complete后Q/J active switch；
- 把目标分母、formal Plan数、completed evidence与Graphify状态改为当前可证据化值；
- 明确下一步只允许dedicated status alignment，不直接签发F；
- 列出后续status PR exact allowlist和不推进lifecycle声明。

不得修改其他owner或宣称future implementation。
  </action>
  <verify>
`rg`不得再命中旧的D/H未dispatch、E/F同base并行、target 29 current或Graphify未覆盖N陈述；链接与PR/SHA必须可解析。
    <automated>set -euo pipefail
owner="docs/implementation/e2e01-thin-slice-multi-agent-plan.md"
test "$(rg -c '<!-- P0-RU-V2-EXECUTION-MAP:START -->' "$owner")" -eq 1
test "$(rg -c '<!-- P0-RU-V2-EXECUTION-MAP:END -->' "$owner")" -eq 1
! rg -F '当前没有D/H Summary、feature branch、feature commit或feature PR' "$owner"
! rg -F '下一步从`B_CG = 327b39d' "$owner"
! rg -F '目标Task Packet完成证据仍是16/29' "$owner"
! rg -F '01-07E/F的planning prerequisite现已满足，但两份Plan尚未签发' "$owner"
! rg -F 'Graphify最近完成点`676980e' "$owner"
for stale in \
  .planning/PROJECT.md \
  .planning/REQUIREMENTS.md \
  .planning/ROADMAP.md \
  .planning/STATE.md \
  .planning/phases/01-cycle-1-e2e-01/01-W2-VALIDATION.md \
  PROJECT_DIRECTION.md
do
  test -f "$stale"
done
rg -n '01-07E|01-07F|B_DH|16/29|18/29|Graphify|D/H' \
  .planning/PROJECT.md \
  .planning/REQUIREMENTS.md \
  .planning/ROADMAP.md \
  .planning/STATE.md \
  .planning/phases/01-cycle-1-e2e-01/01-W2-VALIDATION.md \
  PROJECT_DIRECTION.md >/dev/null
python3 - <<'PY'
from pathlib import Path
text = Path("docs/implementation/e2e01-thin-slice-multi-agent-plan.md").read_text()
for token in (
    "B_O_PLANNING_STATUS",
    "B_O_STATUS",
    "B_F",
    "B_FE_EXPAND",
    "B_RU_V2_CONTRACT",
    "a4b1edb4c50a2e3e826571194bac58f7b31eab6d",
    "https://github.com/weijie567/mini-agent/pull/62",
    "https://github.com/weijie567/mini-agent/pull/63",
):
    assert token in text, token
print("live_execution_status=PASS stale_consumers=6")
PY</automated>
  </verify>
  <done>
execution-plan prose与唯一JSON一致，且实时状态不再误导下一位Integrator。
  </done>
</task>

<task type="auto">
  <name>Task 3: Prove containment and repository-wide impact</name>
  <files>docs/implementation/e2e01-thin-slice-multi-agent-plan.md</files>
  <action>
执行exact one-file containment、JSON equality/mutation parser、links/terms、`git diff --check`与default full suite。扫描ROADMAP、STATE、W2 Validation、source/tests/evals/migration中旧顺序、旧分母和v1 consumers；只报告forbidden consumers，不在本Packet修改。
  </action>
  <verify>
feature exact head及latest-integration overlay均通过全部checks；independent reviewer对canonical/ownership/security给出当前exact head的`PASS`且CRITICAL/HIGH/MEDIUM为0。
    <automated>set -euo pipefail
base_sha="a4b1edb4c50a2e3e826571194bac58f7b31eab6d"
owner="docs/implementation/e2e01-thin-slice-multi-agent-plan.md"
test "$(git merge-base "$base_sha" HEAD)" = "$base_sha"
test "$(git rev-list --count "$base_sha..HEAD")" -eq 1
test "$(git diff --name-only "$base_sha...HEAD")" = "$owner"
test "$(git log -1 --format=%s)" = "docs(01-07O): align RU v2 execution map"
git diff --check "$base_sha"...HEAD
uv run pytest
rg -n \
  'RequestUnderstanding(Output|Record)|e2e01-thin-v1|request_understanding_record\.p0\.v1|P0_PERSISTENCE_REGISTRY|ck_p0_records_code_version_closed|01-07E|01-07F|29' \
  PROJECT_DIRECTION.md docs src tests evals alembic .planning >/dev/null
test -z "$(git status --short)"
echo "containment=PASS full_suite=PASS impact_scan=RECORDED"</automated>
  </verify>
  <done>
一个commit只改execution-plan owner；status follow-up与后续F/E blockers均显式、可复现。
  </done>
</task>

</tasks>

<verification>

从仓库根目录执行：

```bash
git status --short --branch
git rev-parse HEAD^{commit}
git rev-parse HEAD^{tree}
git merge-base HEAD a4b1edb4c50a2e3e826571194bac58f7b31eab6d
git diff --check
uv run pytest
```

另执行本Plan定义的manifest parser、至少12个negative mutations、one-file containment、active-link检查、旧状态scan与independent exact-head review。所有输出记录exact命令、数量、SHA与结论。

</verification>

<success_criteria>

- 01-07O feature只修改multi-agent execution-plan owner；
- JSON map唯一、exact且五阶段顺序与canonical manifest一致；
- F→E、dependency-before-switch、完整consumer-before-Core-contract与39 denominator均机械通过；
- stale live status从execution-plan owner移除，forbidden status consumers列入dedicated follow-up；
- default full suite通过；
- exact feature与latest integration overlay均review PASS；
- merge后只解锁status alignment，不解锁F实现。
</success_criteria>
