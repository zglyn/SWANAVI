# features/agent — Owner B

> **Full spec: [`SPEC.md`](SPEC.md)** — everything you need to build this feature without waiting on anyone.

The LLM agent (MCP client), the orchestrator, scripted demo scenarios, and the HTTP gateway the dashboard calls. Spec: `docs/SPEC.md` §4.4.

- Runs on `:8000`. API contract: `contracts/ts/api.ts` (`API` constant).
- Only component that emits `InspectorEvent`s (SSE at `/api/events`).
- Picks real vs. fake features with `ROAM_FAKES=merchants,guardrail,ledger`.
- The agent has **no payment tool**: it only gathers quotes; the orchestrator runs `build_checkout → sign_as_agent → /cosign → submit_multisigned → confirm`.

## Scenarios
`happy-path`, `malicious-upsell`, `rainstorm`, `reset` — scripted so the demo never depends on LLM luck.

## Done when
All scenarios pass with all fakes, then with all real.
