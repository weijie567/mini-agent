---
phase: 01
phase_name: cycle-1-e2e-01
status: SECURED_WITH_ACCEPTED_RISK
security_gate: PASS
derived_non_normative: true
audit_base_sha: 04442c9262a8a94e9c2c87a89831e99e41aa1418
audit_date: 2026-07-31
asvs_level: 1
asvs_level_basis: INFERRED_FROM_GSD_DEFAULT
block_on: open
plans_read: 49
summaries_read: 24
plans_with_threat_model: 32
plans_without_threat_model: 17
threat_source_occurrences: 236
unique_threat_ids: 212
threats_total_source_occurrences: 236
threats_unique: 212
duplicate_threat_ids: 24
declared_mitigate_occurrences: 228
declared_accept_occurrences: 2
declared_transfer_occurrences: 5
declared_avoid_occurrences: 1
threats_closed: 235
threats_accepted: 1
threats_accounted: 236
threats_open: 0
accepted_risks: 1
accepted_risk_ids:
  - RTA-D01
unregistered_flags: 0
---

# Phase 01 Security Verification

> **DERIVED / NON_NORMATIVE**
>
> 本文件是 Phase 01 已声明威胁与当前实现证据之间的派生核验结果，不是产品、架构、契约或 Eval 语义的 canonical owner。任何语义冲突仍服从项目 active owner。`SECURED_WITH_ACCEPTED_RISK` 只表示 236 个已登记 threat source occurrences 已全部获得当前 disposition：235 个已验证关闭、1 个由 scoped canonical owner 明确接受、0 个开放。它不表示 P0 已完成、已生产就绪或已接入真实电商、支付、退款、物流或 credentialed Qwen 服务。

## SECURED WITH ACCEPTED RISK

**Phase:** 01 — cycle-1-e2e-01

**Closed:** 235/236 source occurrences

**Accepted:** 1/236 — `RTA-D01`

**Open:** 0/236

**Accounted:** 236/236（212 unique IDs）

**ASVS Level:** 1（`INFERRED`：stock GSD 模板默认；项目配置未声明覆盖值）

**Block Policy:** `open`

结论为 **PASS WITH ACCEPTED RISK**。本次审计在 exact base
`04442c9262a8a94e9c2c87a89831e99e41aa1418` 上核验了全部 49 个
`*-PLAN.md`、24 个 `*-SUMMARY.md`、active canonical owners、Phase review /
validation / eval-review、当前实现和测试。32 个 Plan 含 `<threat_model>`，
共有 236 个源记录；按 `(Plan 文件, threat_id)` 保留后得到 236/236 无损映射。
仅按 `threat_id` 去重会得到 212 个 ID，并错误丢失 24 个历史 / replacement
重复记录，因此本报告不以去重数替代 gate 分母。

## 1. 审计边界与结论纪律

### 1.1 权威边界

- P0 业务范围、E2E 和唯一代表性副作用动作服从
  `docs/business-capabilities.md`。
- Runtime、可信身份、最小披露、Memory / Trace 方向服从
  `PROJECT_DIRECTION.md`。
- Request Understanding、Tool、Memory、RAG 和 Eval 语义分别服从对应
  active owner；Plan / Summary 只提供待核验的派生威胁登记，不能自证闭环。
- `docs/implementation/e2e01-thin-slice-implementation-spec.md:1593-1609`
  是 `RTA-D01` 的 scoped canonical owner ruling：关键 Trace 写失败造成的有界
  availability loss 必须保留为 `ACCEPT / BOUNDED` residual risk，不能因
  fail-closed 测试通过而改写为已消除。
- 同一 thin-slice spec 明确把 RAG、Evidence Binding、确认、ActionPolicy、
  `create_refund`、幂等副作用和 `RESULT_UNKNOWN` 排除在 Phase 01 的
  `get_order` thin slice 之外。本报告不把“未进入本切片”误写为“已实现”，也不把
  它们当作当前不存在的 Action surface 的漏洞。

### 1.2 状态含义

| 状态 | 本报告含义 |
|---|---|
| `CONFIRMED` | 当前源码、测试或命令输出可直接复现 |
| `INFERRED` | 由明确默认或多个直接事实推导，已标明推导基础 |
| `ACCEPTED` | canonical owner 明确接受、范围和复审触发完整记录的 residual risk；不等于已消除 |
| `NOT_FOUND` | 在规定范围内未找到该材料或声明 |
| `OPEN` | 已登记威胁既无当前实现 / transfer 闭环，也无有效 canonical acceptance；按本 Phase policy 阻断 |

本次没有 `OPEN`。`01-REVIEW.md` 的 exact reviewed head 早于本次 base，因此只作
支持材料；最终实现证据以本次 base 上的源码核验、focused fault injection 与完整
串行测试为准。`RTA-D01` 的 acceptance 则来自新合并的 canonical owner ruling，
不是 Plan 或测试自证。

### 1.3 机械盘点与会计不变量

| 项目 | 结果 | 状态 |
|---|---:|---|
| `*-PLAN.md` | 49 | `CONFIRMED` |
| `*-SUMMARY.md` | 24 | `CONFIRMED` |
| 含 `<threat_model>` 的 Plan | 32 | `CONFIRMED` |
| 无 `<threat_model>` 的 Plan | 17 | `CONFIRMED`，不伪造零威胁 |
| threat source occurrences | 236 | `CONFIRMED` |
| unique threat IDs | 212 | `CONFIRMED` |
| 重复 threat IDs | 24 个 ID、每个出现 2 次 | `CONFIRMED` |
| Summary `## Threat Flags` | 0/24 找到该节 | `NOT_FOUND`；无 unregistered flag |
| closed / accepted / open | 235 / 1 / 0 | `235 + 1 + 0 = 236` |

声明 disposition 的源记录分类为：228 个 `mitigate`、2 个
`accept / bounded`、5 个 `transfer`、1 个 `avoid`，合计 236。两个 declared
accept 中，`RTA-D01` 依 canonical owner 保持 accepted；`EVB-D01` 因后续 strict
bounded grader 控制而验证关闭。所有记录都在第 8 节逐 Plan 保留。

## 2. Phase 01 信任边界矩阵

| 边界 | 不可信侧 | 确定性控制 / 当前实现 | 失败语义 | 证据 | 状态 |
|---|---|---|---|---|---|
| HTTP / Session → trusted identity | 请求 body、cookie 字符串、模型文本 | body 只允许 `message`；session adapter 在 handler 前认证并构造 `CustomerContext`；`customer_id` 不从 body / model 接受 | 认证失败一致；不进入业务 handler；cookie 不进错误或日志 | `src/mini_agent/api/http.py:12-51`; `src/mini_agent/infrastructure/auth/p0_session.py:13-79`; `tests/integration/test_http_session_adapter.py:72-166` | `CLOSED` |
| Model / Provider → Request Understanding | provider candidate、候选参数、工具名、展示建议 | 模型只产生候选；strict Core records、InputBinding、状态版本、closed schema 和 Control Gateway 重新校验；可信字段注入被拒 | stable typed rejection；无 AuthorizedCommand / ToolCall | `src/mini_agent/core/control_gateway.py:138-297`; `tests/component/core/test_control_gateway.py:269-491`; `docs/architecture/intent-design-reference.md:455-527` | `CLOSED` |
| Runtime / Core → Tool executor | revalidated move、registry snapshot、budget / progress / state | immutable registry snapshot；仅注册 `get_order` READ；toolset hash、schema、binding、owner task、预算和 effect 全部 fail-closed | 非 `ACCEPT` 不执行；无 read / fence / observation | `src/mini_agent/bootstrap.py:431-444`; `src/mini_agent/core/control_gateway.py:138-297`; `tests/component/application/test_read_tool_executor.py:819-916` | `CLOSED` |
| Trusted owner → Order boundary | order ID、数据库行、资源存在性 | `GetOrderQuery` 由 trusted owner 构造；SQL 同时限定 `customer_id` 与 `order_id`；只返回 safe projection；不存在与无权访问统一 | `NOT_FOUND_OR_NOT_ACCESSIBLE`；错误为固定 code | `src/mini_agent/infrastructure/order/postgres.py:46-113`; `tests/integration/test_postgres_get_order.py:114-250` | `CLOSED` |
| Application records → PostgreSQL | envelope、schema version、关系、CAS / fence、并发写 | exact type / version registry、closed child / reference set、owner metadata 一致性、单事务 terminal aggregate、conditional write | opaque typed integrity；冲突 / 不适用零额外写；事务回滚 | `src/mini_agent/application/persistence.py:1017-2166`; `src/mini_agent/infrastructure/persistence/postgres.py:2229-2519`; `tests/integration/test_postgres_atomicity.py:1106-1883` | `CLOSED` |
| PostgreSQL → Recovery / exact-run evidence | 持久化闭包、外来关系、过量 children、并发快照 | exact-run reader 使用 exact owner + exact run root、`REPEATABLE READ, READ ONLY`、每 family frozen cap 和 closed reference graph；restart recovery loader 使用有界查询 / snapshot，apply 加锁后重读 closure / fence 并在单事务内提交 | 缺失 / 完整性 / 状态结果分离；不推断、不 fallback、不 replay Action | `src/mini_agent/infrastructure/persistence/postgres.py:946-1280`; `src/mini_agent/infrastructure/persistence/recovery.py:36-572`; `tests/integration/test_postgres_record_adapters.py:1493-1978`; `tests/integration/test_postgres_recovery.py:216-630`; `tests/component/application/test_restart_recovery_service.py:227-331` | `CLOSED` |
| Observation / source version → presentation | 工具 payload、可伪造 `source_version`、provider 文案 | producer 以 owner + order + safe projection 生成 canonical hash；FOUND 必须带 canonical version；runtime 验证后才写 Observation；renderer 仅使用 allowlisted facts | invalid source/version 变为 safe system failure；不写 Observation / 不展示未经批准事实 | `src/mini_agent/infrastructure/order/postgres.py:21-113`; `src/mini_agent/application/agent_run_service.py:708-769`; `tests/integration/test_postgres_get_order.py:187-250`; `tests/component/application/test_agent_run_service.py:684-2260` | `CLOSED` |
| Runtime records → Trace / Eval | raw provider data、私有 DTO、自报布尔值、篡改 record graph | ordinary Trace allowlist；ContextManifest 仅 refs / versions / counts；grader 对 typed evidence 做递归 strict canonicalization，并从权威图导出 critical failure | typed `ASSERTION_FAILED`；未知 / 重复 / 缺失 grader fail-closed | `src/mini_agent/core/trace.py:91-178`; `src/mini_agent/core/memory.py:78-99`; `src/mini_agent/evaluation/graders.py:454-522`; `tests/component/evaluation/test_e2e01_graders.py:2345-3654` | `CLOSED` |
| Runtime → terminal result / Message / Trace | terminal child write、CAS race、Trace append failure、cancel | terminal Run、Task / RequestUnit、links、assistant message、terminal Trace 在一个 conditional aggregate 中提交；只有 `APPLIED` 后返回 committed result | terminal fault / cancel / conflict 不留下 standalone terminal projection；关键 pre-terminal Trace append 失败会拒绝请求 | `src/mini_agent/application/agent_run_service.py:227-1262`; `src/mini_agent/infrastructure/persistence/postgres.py:2229-2519`; `tests/component/application/test_agent_run_service.py:1959-2227`; `docs/implementation/e2e01-thin-slice-implementation-spec.md:1593-1609` | 原子性控制已验证；availability residual `RTA-D01 ACCEPTED` |
| Credentialed Qwen adapter → network | base URL、API key、HTTP / JSON / provider payload | 只允许 canonical HTTPS URL；secret 以具体 injected value 接受；protocol error 清除 cause / context；测试验证 traceback 不保留 URL、key 或 raw payload | 固定 `ProviderProtocolError`；不暴露 transport / response / secret | `src/mini_agent/infrastructure/model/qwen_responses.py:29-169`; `tests/component/model/test_qwen_responses_adapter.py:270-625` | `CLOSED`（adapter contract）；真实 credentialed lane `NOT_RUN` |
| Phase 01 read slice → P0 Action boundary | `create_refund` 候选或其他副作用工具 | 当前 registry snapshot 只有 `get_order` 且 effect 为 READ；executor 无 action / retry / parallel surface | 未注册 / 非 READ 不产生 AuthorizedCommand；本切片无副作用 | `src/mini_agent/bootstrap.py:431-444`; `src/mini_agent/core/control_gateway.py:226-270`; `tests/component/application/test_read_tool_executor.py:1128-1140`; `docs/implementation/e2e01-thin-slice-implementation-spec.md:58-67` | `CLOSED`（本切片边界）；P0 Action 能力仍为未进入本 Phase 的后续范围 |

## 3. 可复用证据包

第 8 节的 32 行 source-occurrence 表使用下列证据包，避免把同一实现证据机械复制
236 次。每一行仍完整保留 exact threat ID list 和 occurrence 数。

| Evidence pack | 覆盖控制 | 主要源码 | 主要测试 |
|---|---|---|---|
| `E-ID` | trusted identity、owner scope、最小披露、HTTP before-handler auth | `src/mini_agent/api/http.py:12-51`; `src/mini_agent/infrastructure/auth/p0_session.py:13-79`; `src/mini_agent/infrastructure/order/postgres.py:46-113`; `src/mini_agent/application/records.py:87-139` | `tests/integration/test_http_session_adapter.py:72-166`; `tests/integration/test_postgres_get_order.py:114-250` |
| `E-RU` | candidate-only Request Understanding、strict v2 mapping / codec、binding、状态版本、无身份扩大 | `src/mini_agent/core/control_gateway.py:138-297`; `src/mini_agent/application/persistence.py:2088-2925`; `src/mini_agent/infrastructure/persistence/postgres.py:2524-3017` | `tests/component/core/test_control_gateway.py:269-491`; `tests/component/application/test_persistence_contract.py:2312-3065`; `tests/integration/test_postgres_v2_request_understanding_writes.py` |
| `E-REC` | exact record / version / child / relation closure、opaque integrity、owner consistency | `src/mini_agent/application/persistence.py:1017-1905`; `src/mini_agent/infrastructure/persistence/postgres.py:533-1320` | `tests/component/application/test_persistence_contract.py:741-3065`; `tests/component/application/test_record_contracts.py`; `tests/integration/test_postgres_record_adapters.py:1147-1978` |
| `E-TOOL` | immutable tool snapshot、Gateway、durable ToolCall / Attempt、timeouts / cancel、无 retry / action | `src/mini_agent/bootstrap.py:431-444`; `src/mini_agent/core/control_gateway.py:138-297`; `src/mini_agent/application/read_tool_executor.py` | `tests/component/core/test_tool_system_contract.py`; `tests/component/core/test_control_gateway.py:269-491`; `tests/component/application/test_read_tool_executor.py:303-1140` |
| `E-RUN` | runtime stop reasons、task / run transition、terminal aggregate、并发与故障回滚；不消除 `RTA-D01` availability residual | `src/mini_agent/application/agent_run_service.py:227-1262`; `src/mini_agent/infrastructure/persistence/postgres.py:2229-2519` | `tests/component/application/test_agent_run_service.py:1959-2227`; `tests/integration/test_postgres_atomicity.py:1106-1883` |
| `E-RESTART` | recovery classification、bounded exact closure、snapshot / fence、加锁后重读、原子 apply、零 replay、late result / Action boundary | `src/mini_agent/application/restart_recovery_service.py`; `src/mini_agent/infrastructure/persistence/recovery.py:36-572` | `tests/component/application/test_restart_recovery_service.py:227-331`; `tests/integration/test_postgres_recovery.py:216-630` |
| `E-OBS` | safe Observation、canonical source version、provenance、deterministic presentation | `src/mini_agent/core/order.py:19-93`; `src/mini_agent/core/memory.py:26-99`; `src/mini_agent/infrastructure/order/postgres.py:21-113`; `src/mini_agent/application/agent_run_service.py:708-790` | `tests/component/core/test_memory_trace_presentation_contract.py:113-230`; `tests/integration/test_postgres_get_order.py:187-250`; `tests/component/application/test_agent_run_service.py:684-2260` |
| `E-TRACE` | typed Trace / ContextManifest、safe fields、runtime trace ordering、no raw token / payload / PII；关键 append availability risk 另按 `RTA-D01` 接受 | `src/mini_agent/core/trace.py:91-178`; `src/mini_agent/core/memory.py:78-99`; `src/mini_agent/application/agent_run_service.py:227-279` | `tests/component/core/test_memory_trace_presentation_contract.py`; `tests/component/application/test_agent_run_service.py`; `tests/component/evaluation/test_e2e01_graders.py:1699-3654` |
| `E-EVAL` | authenticated artifact loader、oracle isolation、typed evidence、strict graders / harness lifecycle | `src/mini_agent/evaluation/graders.py:454-522`; `src/mini_agent/evaluation/harness.py`; versioned artifact loader / providers | `tests/component/evaluation/test_e2e01_artifact_consistency.py`; `tests/component/evaluation/test_e2e01_graders.py:2345-3654`; `tests/integration/evaluation/test_e2e01_offline_harness.py` |
| `E-QWEN` | HTTPS-only adapter、secret-safe construction / traceback、raw-free protocol failures | `src/mini_agent/infrastructure/model/qwen_responses.py:29-169` | `tests/component/model/test_qwen_responses_adapter.py:270-625` |

## 4. 非普通 disposition 的逐项核验

本节对全部 9 个非普通记录逐一核验。Plan 只提供登记，不可自证 acceptance；
`RTA-D01` 的当前 acceptance 由 scoped canonical owner ruling 建立。

| Source occurrence | Plan disposition | 核验结果 | 当前证据与裁决 |
|---|---|---|---|
| `01-04D / P04D-C01` | `TRANSFER / REQUIRED` | `CLOSED` | Infrastructure restart-recovery adapter 以 `REPEATABLE READ` 加载有界 recovery closure；apply 使用 `SERIALIZABLE`，稳定加锁后重新读取全部 bounded families 并重新计算 closure fence。closure drift、serialization / deadlock 或任一写故障均 rollback / zero-write conflict。`tests/integration/test_postgres_recovery.py:216-630` 证明 transfer 接收方的同 snapshot / fence / closed-set 义务。 |
| `01-04E / CTX-D01` | `AVOID` | `CLOSED` | Context Manifest 只保存 typed refs / versions / optional token counts；实现没有 tokenizer、网络调用或不受限原文扫描。Trace / Eval 只消费 typed bounded fields。 |
| `01-04H / TERM-D01` | `TRANSFER / BLOCK 01-06R` | `CLOSED` | `01-06R` Infrastructure 已实现 terminal aggregate 单事务；terminal child / reference fault 全量回滚，non-applied 零写。focused parameterized tests 在本 base 通过。 |
| `01-05R / RT-D02` | `TRANSFER / BLOCK 01-06R` | `CLOSED` | `finalize_run_if_active()` 使用一个 `session_factory.begin()`，Run / links / Task / RequestUnit / Message / Trace 任一故障使整个 aggregate 回滚。 |
| `01-07A / RTA-D01` | `ACCEPT / BOUNDED` | `ACCEPTED — CANONICAL SCOPED RESIDUAL RISK` | `docs/implementation/e2e01-thin-slice-implementation-spec.md:1593-1609` 明确接受关键 Trace store / append 失败拒绝当前 read-only 请求所造成的有界 availability loss。fail-closed、无部分 terminal projection 等测试是约束控制，不消除该依赖的 availability risk。完整风险记录见第 10 节。 |
| `01-07B / EVB-D01` | `ACCEPT / BOUNDED` | `CLOSED — VERIFIED MITIGATION` | 当前 grader 对 typed evidence 做有限对象图递归、cycle 检测和 strict reconstruction；非 canonical / 未知 / 重复 / 缺失 grader 配置直接 typed fail，不 retry、不联网。fault tests 证明 fail-before-grading；当前无 residual accepted risk。 |
| `01-07H / OSVA-S01` | `TRANSFER / DEFERRED` | `CLOSED` | 下游 `01-07K` producer 用 owner + order + safe projection 生成 canonical `source_version`，`01-07M` / runtime 校验 FOUND version 后才记录 Observation；fixed owner vectors、content sensitivity 与 no-fallback tests 通过。 |
| `01-07I / ERI-D01` | `TRANSFER / BOUNDED` | `CLOSED` | `01-07K` reader 对 exact-run graph 每一 family 设 frozen cap、每次 identity 最多取 2 行、两个 discovery channel 均检查 evasive extras，且单 snapshot 读取；过量在 materialization 前 typed fail。 |
| `01-07M / M-S01` | `MITIGATE / TRANSFER` | `CLOSED` | producer 与 consumer 两端都闭环：数据库 adapter 产生 canonical version；Core `GetOrderResult` 强制 FOUND 携带、非 FOUND 禁止；runtime 不接受 v1 / fallback；模型 schema 不暴露 `source_version`。 |

非普通 disposition 总账：8 个 source occurrences 已验证关闭，1 个
`RTA-D01` 被 canonical owner 接受，0 个开放。`EVB-D01` 的关闭不能用来覆盖
`RTA-D01` 的独立 availability ruling。

## 5. Superseded / replacement 威胁映射

历史 Plan 必须保留在 source-occurrence 分母中，但实现闭环由明确 replacement 接收；
不能删除旧行或把旧行当作独立 active implementation contract。

| 历史 Plan | Replacement | 重复 ID（两个 source occurrence 均保留） | 历史独有 ID 的处理 | 状态 |
|---|---|---|---|---|
| `01-05` | `01-05R` | `RT-D01`, `RT-E01`, `RT-I01`, `RT-I02`, `RT-R01`, `RT-R02`, `RT-R03`, `RT-S01`, `RT-T01`, `RT-T02`, `RT-T03`, `RT-T04` | replacement 新增 `RT-R04`, `RT-T05`, `RT-D02`, `RT-I03`；旧 12 项均由 replacement Runtime + 01-06R Infrastructure 证据包闭环 | 旧 12 + 新 16 source occurrences 均 `CLOSED` |
| `01-06` | `01-06R` | `IF-D01`, `IF-E01`, `IF-I01`, `IF-R03`, `IF-S01`, `IF-T01` | 旧独有 `IF-I02`, `IF-I03`, `IF-T02`, `IF-T03`, `IF-R01`, `IF-R02` 仍映射到 replacement 的 exact persistence / transaction / opaque failure controls；replacement 新增 `IF-T04`, `IF-R04`, `IF-I04`, `IF-D02` | 旧 12 + 新 10 source occurrences 均 `CLOSED` |
| `01-07E` | `01-07N` 后续 remediation / cutover ruling | `RUC-S01`, `RUC-T01`, `RUC-R01`, `RUC-I01`, `RUC-D01`, `RUC-E01` | 两个 Plan 的 6+6 occurrences 均保留；当前 strict v2 codec / active switch / no fallback 证据闭环 | 12/12 `CLOSED` |

## 6. Summary Threat Flags

对 24 个 `*-SUMMARY.md` 的标题级扫描没有找到任何 `## Threat Flags` 节：

- 映射到既有 threat ID 的 flags：`NONE`
- 未注册 flags：`NONE`
- `unregistered_flags`: `0`

这是 `NOT_FOUND` 事实，不等于 Summary 自证没有安全问题；本报告的 gate 结论仍来自
Plan register、canonical acceptance 与实现证据的逐项映射。

## 7. Threat Verification（控制族汇总）

| Threat family | Source occurrences | Disposition class | Evidence | 结果 |
|---|---:|---|---|---|
| Trusted identity / owner / disclosure | 由第 8 节 exact IDs 计入 | mitigate | `E-ID`, `E-RU` | `CLOSED` |
| Persistence schema / relation / integrity | 同上 | mitigate / transfer | `E-REC` | `CLOSED` |
| Tool registry / Gateway / execution | 同上 | mitigate | `E-TOOL` | `CLOSED` |
| Runtime / task / terminal aggregate | 同上 | mitigate / transfer / accept | `E-RUN` | 安全与原子性控制已验证；`RTA-D01 ACCEPTED` |
| Restart / recovery | 同上 | mitigate | `E-RESTART`, `E-REC` | `CLOSED` |
| Observation / version / presentation | 同上 | mitigate / transfer | `E-OBS` | `CLOSED` |
| Trace / Context Manifest | 同上 | mitigate / avoid / accept | `E-TRACE`, `E-RUN` | `RTA-D01 ACCEPTED`；其余 source occurrences 已验证 |
| Eval oracle / typed evidence / harness | 同上 | mitigate / historical accept | `E-EVAL` | `CLOSED`，含 `EVB-D01 VERIFIED MITIGATION` |
| Credentialed adapter contract | 同上 | mitigate | `E-QWEN` | `CLOSED`（real lane `NOT_RUN`） |

## 8. 236/236 无损 source-occurrence 映射

下表每一行以 Plan 文件为 namespace。`IDs` 是 `<threat_model>` 中的 exact ID
顺序；accounting 分母是该文件 occurrence 数，不是去重后的 ID 数。32 行合计
235 closed + 1 accepted + 0 open = 236 accounted。

| Plan source | Occurrences | Exact IDs（source order） | Verified controls | Accounting |
|---|---:|---|---|---:|
| `01-01-PLAN.md` | 5 | `PERSIST-T01`, `PERSIST-E01`, `PERSIST-I01`, `PERSIST-R01`, `TRACE-T01` | `E-ID`, `E-REC`, `E-TRACE` | 5 closed |
| `01-02-PLAN.md` | 6 | `MEM-PERSIST-S01`, `MEM-PERSIST-T01`, `MEM-PERSIST-E01`, `MEM-PERSIST-I01`, `MEM-REC-D01`, `MEM-REC-R01` | `E-ID`, `E-REC` | 6 closed |
| `01-03-PLAN.md` | 8 | `TS-PERSIST-S01`, `TS-PERSIST-T01`, `TS-PERSIST-T02`, `TS-PERSIST-E01`, `TS-PERSIST-I01`, `TS-PERSIST-D01`, `TS-PERSIST-R01`, `TS-PERSIST-T03` | `E-ID`, `E-REC` | 8 closed |
| `01-04-PLAN.md` | 11 | `P04-S01`, `P04-T01`, `P04-T02`, `P04-T03`, `P04-T04`, `P04-T05`, `P04-T06`, `P04-E01`, `P04-I01`, `P04-D01`, `P04-R01` | `E-ID`, `E-RU`, `E-TOOL`, `E-RUN` | 11 closed |
| `01-04D-PLAN.md` | 13 | `P04D-S01`, `P04D-T01`, `P04D-T02`, `P04D-T03`, `P04D-T04`, `P04D-T05`, `P04D-R01`, `P04D-I01`, `P04D-I02`, `P04D-D01`, `P04D-E01`, `P04D-E02`, `P04D-C01` | `E-ID`, `E-REC`, `E-RUN`, `E-RESTART` | 13 closed |
| `01-04E-PLAN.md` | 4 | `CTX-T01`, `CTX-R01`, `CTX-I01`, `CTX-D01` | `E-TRACE` | 4 closed |
| `01-04F-PLAN.md` | 5 | `EVAL-T01`, `EVAL-S01`, `EVAL-R01`, `EVAL-I01`, `EVAL-E01` | `E-EVAL`, `E-ID`, `E-TRACE` | 5 closed |
| `01-04G-PLAN.md` | 5 | `REC-R01`, `REC-T01`, `REC-S01`, `REC-D01`, `REC-E01` | `E-RESTART`, `E-REC` | 5 closed |
| `01-04H-PLAN.md` | 5 | `TERM-R01`, `TERM-T01`, `TERM-I01`, `TERM-D01`, `TERM-E01` | `E-RUN`, `E-REC` | 5 closed |
| `01-05-PLAN.md` | 12 | `RT-S01`, `RT-T01`, `RT-T02`, `RT-E01`, `RT-R01`, `RT-D01`, `RT-I01`, `RT-T03`, `RT-I02`, `RT-R02`, `RT-R03`, `RT-T04` | superseded by `01-05R`; `E-RUN`, `E-TOOL`, `E-TRACE` | 12 closed |
| `01-05R-PLAN.md` | 16 | `RT-S01`, `RT-T01`, `RT-T02`, `RT-E01`, `RT-R01`, `RT-D01`, `RT-I01`, `RT-T03`, `RT-I02`, `RT-R02`, `RT-R03`, `RT-T04`, `RT-R04`, `RT-T05`, `RT-D02`, `RT-I03` | `E-RUN`, `E-TOOL`, `E-TRACE`, `E-REC` | 16 closed |
| `01-06-PLAN.md` | 12 | `IF-S01`, `IF-I01`, `IF-I02`, `IF-I03`, `IF-T01`, `IF-T02`, `IF-T03`, `IF-R01`, `IF-R02`, `IF-R03`, `IF-D01`, `IF-E01` | superseded by `01-06R`; `E-ID`, `E-REC`, `E-RUN`, `E-RESTART` | 12 closed |
| `01-06R-PLAN.md` | 10 | `IF-S01`, `IF-T01`, `IF-T04`, `IF-R03`, `IF-R04`, `IF-I01`, `IF-I04`, `IF-D01`, `IF-D02`, `IF-E01` | `E-ID`, `E-REC`, `E-RUN`, `E-RESTART` | 10 closed |
| `01-07-PLAN.md` | 11 | `EV-T01`, `EV-E01`, `EV-S01`, `EV-I01`, `EV-I03`, `EV-S02`, `EV-E02`, `EV-T02`, `EV-R01`, `EV-R02`, `EV-D01` | `E-EVAL`, `E-OBS`, `E-TRACE`, `E-QWEN` | 11 closed |
| `01-07A-PLAN.md` | 6 | `RTA-T01`, `RTA-T02`, `RTA-R01`, `RTA-I01`, `RTA-D01`, `RTA-E01` | `E-RUN`, `E-TRACE`; `RTA-D01` owner ruling | 5 closed + 1 accepted |
| `01-07B-PLAN.md` | 6 | `EVB-E01`, `EVB-T01`, `EVB-R01`, `EVB-I01`, `EVB-D01`, `EVB-S01` | `E-EVAL`, `E-TRACE` | 6 closed |
| `01-07C-PLAN.md` | 6 | `RUS-S01`, `RUS-T01`, `RUS-R01`, `RUS-I01`, `RUS-D01`, `RUS-E01` | `E-RU`, `E-ID`, `E-REC` | 6 closed |
| `01-07D-PLAN.md` | 6 | `RUM-S01`, `RUM-T01`, `RUM-R01`, `RUM-I01`, `RUM-D01`, `RUM-E01` | `E-RU`, `E-ID`, `E-REC` | 6 closed |
| `01-07E-PLAN.md` | 6 | `RUC-S01`, `RUC-T01`, `RUC-R01`, `RUC-I01`, `RUC-D01`, `RUC-E01` | `E-RU`, `E-ID`, `E-REC` | 6 closed |
| `01-07F-PLAN.md` | 6 | `RUV2-S01`, `RUV2-T01`, `RUV2-R01`, `RUV2-I01`, `RUV2-D01`, `RUV2-E01` | `E-RU`, `E-ID` | 6 closed |
| `01-07G-PLAN.md` | 6 | `OSV-S01`, `OSV-T01`, `OSV-R01`, `OSV-I01`, `OSV-D01`, `OSV-E01` | `E-OBS`, `E-ID` | 6 closed |
| `01-07H-PLAN.md` | 6 | `OSVA-S01`, `OSVA-T01`, `OSVA-R01`, `OSVA-I01`, `OSVA-D01`, `OSVA-E01` | `E-OBS`, `E-ID` | 6 closed |
| `01-07I-PLAN.md` | 6 | `ERI-S01`, `ERI-T01`, `ERI-R01`, `ERI-I01`, `ERI-D01`, `ERI-E01` | `E-REC`, `E-ID`, `E-EVAL` | 6 closed |
| `01-07K-PLAN.md` | 6 | `K-S01`, `K-T01`, `K-R01`, `K-I01`, `K-D01`, `K-E01` | `E-REC`, `E-OBS`, `E-ID` | 6 closed |
| `01-07L-PLAN.md` | 6 | `L-S01`, `L-T01`, `L-R01`, `L-I01`, `L-D01`, `L-E01` | `E-EVAL`, `E-REC`, `E-QWEN` | 6 closed |
| `01-07M-PLAN.md` | 6 | `M-S01`, `M-T01`, `M-R01`, `M-I01`, `M-D01`, `M-E01` | `E-OBS`, `E-ID` | 6 closed |
| `01-07N-PLAN.md` | 6 | `RUC-S01`, `RUC-T01`, `RUC-R01`, `RUC-I01`, `RUC-D01`, `RUC-E01` | `E-RU`, `E-ID`, `E-REC` | 6 closed |
| `01-07O-PLAN.md` | 6 | `RUE-S01`, `RUE-T01`, `RUE-R01`, `RUE-I01`, `RUE-D01`, `RUE-E01` | `E-RU`, `E-ID`, `E-REC` | 6 closed |
| `01-07P-PLAN.md` | 6 | `RUP-S01`, `RUP-T01`, `RUP-R01`, `RUP-I01`, `RUP-D01`, `RUP-E01` | `E-RU`, `E-ID`, `E-REC` | 6 closed |
| `01-07Q-PLAN.md` | 7 | `Q-S01`, `Q-T01`, `Q-T02`, `Q-R01`, `Q-I01`, `Q-D01`, `Q-E01` | `E-RU`, `E-ID`, `E-REC` | 7 closed |
| `01-07Y-PLAN.md` | 8 | `Y-S01`, `Y-T01`, `Y-T02`, `Y-T03`, `Y-R01`, `Y-I01`, `Y-D01`, `Y-E01` | `E-RU`, `E-ID`, `E-REC` | 8 closed |
| `01-07Z-PLAN.md` | 8 | `Z-S01`, `Z-T01`, `Z-T02`, `Z-T03`, `Z-R01`, `Z-I01`, `Z-D01`, `Z-E01` | `E-RU`, `E-ID`, `E-REC` | 8 closed |
| **合计** | **236** | **236 source occurrences / 212 unique IDs** | **235 verified closed + 1 canonical accepted + 0 open** | **236 accounted** |

## 9. 已读取但无 `<threat_model>` 的 Plan

以下 17 个 Plan 已纳入 required-reading inventory，但没有 threat register。按项目治理，
它们不能以“零威胁”单独获得安全通过；Phase gate 由上述 236 个已登记记录、
canonical acceptance 和 active 实现证据共同决定：

1. `01-07AA-CODEC-BOUNDARY-SCOPE-AMENDMENT-PLAN.md`
2. `01-07AA-CODEC-HANDOFF-PLAN.md`
3. `01-07AA-ORACLE-FIX-PLAN.md`
4. `01-07AA-PLAN.md`
5. `01-07AB-PLAN.md`
6. `01-07J-PLAN.md`
7. `01-07S-PLAN.md`
8. `01-07T-PHYSICAL-HANDOFF-PLAN.md`
9. `01-07T-PLAN.md`
10. `01-07U-PLAN.md`
11. `01-07V-EVAL-HANDOFF-PLAN.md`
12. `01-07V-PLAN.md`
13. `01-07W-PLAN.md`
14. `01-07X-PLAN.md`
15. `01-08-PLAN.md`
16. `01-08A-COMPOSITION-HANDOFF-PLAN.md`
17. `01-08A-PLAN.md`

## 10. Accepted Risks Log

| 字段 | `RTA-D01` |
|---|---|
| Canonical owner | `docs/implementation/e2e01-thin-slice-implementation-spec.md:1593-1609`；owner ruling merge `04442c9262a8a94e9c2c87a89831e99e41aa1418`（PR #175） |
| Risk | Trace Store 或适用的关键 Trace append 失败会拒绝当前请求，造成有界 availability loss |
| Disposition | `ACCEPT / BOUNDED` |
| Scope | 仅 `E2E01-01/04` 第一切片的 read-only `get_order` Runtime |
| Rationale | 第一切片宁可拒绝一次只读请求，也不返回缺少关键 Trace、状态或停止证据的不可审计成功；风险接受的是可用性损失，不是审计或原子性放宽 |
| Existing controls | 无自动重试或循环；异常不产生用户成功结果、不伪造 `RunStopped`、不留下部分 terminal projection；错误内容 bounded；terminal aggregate 只有 Run、Task / RequestUnit、Message 与 terminal Trace 全部原子提交后才返回 |
| Non-accepted behavior | 不接受“Trace 写失败但仍返回成功”、伪造补写、丢失已提交状态、泄露 raw payload / Token / PII，或用本裁决放宽任何 Action / Ledger 原子性 |
| Out of scope | 不覆盖真实生产 SLO、其他 Tool、RAG / Evidence、确认、ActionPolicy、`create_refund`、幂等或 `RESULT_UNKNOWN` |
| Mandatory review triggers | 引入任何 Action / 副作用；建立 canonical 产品启动或生产可用性目标；引入 Trace outbox / async delivery；关键事件分类变化；目标 Case 从 `EXECUTABLE` 推进到 `REGRESSION_GATE`；进入任何 release gate 之前 |
| Acceptance authority | scoped canonical owner ruling；不是 `01-07A-PLAN.md` 自证，也不是测试通过推导 |
| Audit date | 2026-07-31 |

`EVB-D01` 虽在 Plan 中同为 `ACCEPT / BOUNDED`，但其当前 strict bounded grader
实现已验证 mitigation，因此不进入本 accepted-risk log。

## 11. 验证命令与结果

所有命令均在 `/private/tmp/phase01-security-audit-r2`、branch
`codex/phase01-security-audit-r2`、HEAD
`04442c9262a8a94e9c2c87a89831e99e41aa1418` 执行。

### 11.1 非普通 disposition / transfer focused set

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -p no:cacheprovider \
  tests/integration/test_postgres_recovery.py::test_recovery_loader_uses_repeatable_snapshot_and_limit_two_queries \
  tests/integration/test_postgres_recovery.py::test_recovery_apply_rereads_bounded_closure_and_fence_after_locks \
  tests/integration/test_postgres_recovery.py::test_closure_drift_and_serialization_failure_are_zero_write_conflicts \
  tests/integration/test_postgres_atomicity.py::test_finalize_run_persists_exact_complete_terminal_projection \
  tests/integration/test_postgres_atomicity.py::test_finalize_run_rolls_back_every_terminal_child_and_reference_fault \
  tests/integration/test_postgres_atomicity.py::test_finalize_run_non_applied_paths_write_nothing \
  tests/integration/test_postgres_atomicity.py::test_finalize_run_concurrent_winner_and_loser_commit_one_aggregate \
  tests/integration/test_postgres_get_order.py::test_source_version_matches_both_fixed_owner_vectors \
  tests/integration/test_postgres_get_order.py::test_source_version_is_content_sensitive_and_allows_aba_replay \
  tests/integration/test_postgres_record_adapters.py::test_exact_run_reader_enforces_every_frozen_cap_class_before_materialization \
  tests/integration/test_postgres_record_adapters.py::test_exact_run_reader_two_discovery_channels_reject_evasive_extras \
  tests/integration/test_postgres_record_adapters.py::test_exact_run_reader_uses_one_repeatable_read_read_only_snapshot \
  tests/component/application/test_agent_run_service.py::test_get_order_agent_visible_schema_does_not_expose_source_version \
  tests/component/application/test_agent_run_service.py::test_active_runtime_source_has_no_v1_or_source_version_fallback \
  tests/component/application/test_agent_run_service.py::test_terminal_aggregate_failure_preserves_render_without_terminal_projection \
  tests/component/application/test_agent_run_service.py::test_terminal_aggregate_cancellation_preserves_render_without_terminal_projection \
  tests/component/evaluation/test_e2e01_graders.py::test_unknown_duplicate_or_missing_grader_configuration_fails_closed \
  tests/component/evaluation/test_e2e01_graders.py::test_every_noncanonical_mixed_v2_bypass_fails_before_grading
```

结果：`79 passed in 19.98s`。参数化用例使 collected count 高于列出的 node ID 数。
这些测试证明 acceptance 周围的约束控制，不证明 `RTA-D01` availability residual
已经消失。

### 11.2 完整串行门禁

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -p no:cacheprovider
```

结果：`2004 passed, 1 deselected, 12 warnings in 137.62s`。

- 1 个 deselected 为 credential-aware external lane；本次按任务边界没有发起真实
  Qwen 网络调用。
- 12 个 warning 为 Starlette / httpx cookie API deprecation，不改变本次 threat
  accounting 或 acceptance 结论。
- `01-EVAL-REVIEW.md` 记录的 lifecycle-valid Trajectory / E2E Result、CI regression
  gate 和真实 credentialed Qwen baseline 缺口仍是 Eval / release readiness 缺口；
  本报告不把它们误写成已完成。

## 12. 最终 Gate 与非声明

### Gate

- `threats_closed: 235`
- `threats_accepted: 1`
- `threats_open: 0`
- `threats_accounted: 236`
- `accepted_risk_ids: [RTA-D01]`
- `unregistered_flags: 0`
- `security_gate: PASS`

会计不变量：`235 closed + 1 accepted + 0 open = 236 accounted`。

### 本报告不声明

- 不声明 accepted risk 已消除，也不把 `PASS` 解释为 production readiness。
- 不声明 canonical 应用启动、生产部署或 P0 产品已完成。
- 不声明 lifecycle-valid Trajectory / E2E Eval Result、回归报告、CI gate 或真实
  credentialed Qwen baseline 已完成。
- 不声明真实电商、支付、退款、物流集成；`create_refund` 仍只允许表示后续 P0 的
  模拟退款动作。
- 不声明 Evidence Binding、精确确认、ActionPolicy、幂等副作用与 `RESULT_UNKNOWN`
  已在本 thin slice 实现；它们仍是进入 Action phase 时必须重新 gate 的 canonical
  安全边界，并触发 `RTA-D01` 强制复审。

**SECURITY.md:** `.planning/phases/01-cycle-1-e2e-01/01-SECURITY.md`
