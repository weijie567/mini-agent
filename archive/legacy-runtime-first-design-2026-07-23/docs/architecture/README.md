# Mini Agent Architecture Artifacts

## Current proposed P0 target (v3)

- Editable draw.io source: `mini-agent-modular-monolith-architecture.drawio`
- Stable SVG export: `mini-agent-modular-monolith-architecture.svg`
- Versioned review exports: `mini-agent-modular-monolith-architecture-v3.svg`
  and `mini-agent-modular-monolith-architecture-v3.png`

The draw.io file and the SVG review rendering use the same v3 module structure.
The SVG preserves the original v3 presentation; when the architecture changes,
update the draw.io model and the SVG snapshot together and visually compare them.

These artifacts describe the proposed P0 modular-monolith dependency architecture.
They are planning artifacts, not evidence of implemented code or proof that the
Runtime is already generic.

The modular-monolith boundary contains Bootstrap, Interfaces, Application, Agent
Runtime Core, Reference Application, and Infrastructure Adapters. Only External
Systems are outside that deployment boundary.

The P0 port baseline is deliberately small:

- Runtime-owned: `ModelPort`, `RunStateStorePort`, `MemoryStorePort`, `TraceSink`,
  and `TraceQueryPort`.
- Reference-Application-owned: `OrderReaderPort`, `ShipmentReaderPort`,
  `DeliveryPolicySearchPort`, and `SupportCaseServicePort`.
- `ToolHandler` and `ActionPolicy` are Runtime extension contracts, not outbound
  ports. P0 has no `ToolInvokerPort`, generic `RetrievalPort`, or `ApprovalPort`.
- Every tool call is validated. `READ_TOOL` may proceed from validation to the
  `Tool Executor`; only `ACTION_TOOL` must additionally pass the `Action Gate`.
- Evaluation specifications and cases belong to the Reference Application and
  test harness, not to the Runtime extension API.

## Legacy and supporting artifacts

- `mini-agent-architecture.drawio` is the earlier combined source containing the
  legacy high-level system architecture page and the business-flow page.
- `mini-agent-modular-monolith-architecture-v2.svg`,
  `mini-agent-system-architecture.svg`, and `.png` are legacy exports superseded
  by the proposed modular-monolith architecture above.
- `mini-agent-business-flow.svg` and `.png` remain the request-processing flow
  view. They describe execution sequence rather than module dependencies.

The proposed dependency architecture and the business-flow view intentionally
serve different purposes and should not be interpreted as implementation status.
