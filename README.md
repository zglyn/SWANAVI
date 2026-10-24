# Roam402

AI travel agent that books local merchants directly over MCP + `x402`, with XRPL multi-sig guardrails, credentials, atomic `Batch` checkout and escrows.

**Read first:** [`docs/SPEC.md`](docs/SPEC.md)

```
contracts/            shared models, interfaces, TS types, fixtures — the ONLY cross-feature dependency
features/merchants    (A) mock merchant MCP servers + 402 quotes        :8001
features/guardrail    (A) deterministic policy co-signer (Key 2)        :8002
features/ledger       (C) xrpl-py: multi-sig, credentials, Batch, escrow
features/agent        (B) LLM agent, orchestrator, gateway API, scenarios :8000
features/dashboard    (D) Next.js split-screen UI                        :3000
```

Rules: never import another feature's code; build against fakes (`ROAM_FAKES=...`) and fixtures; contract changes go in one PR touching Python + TS + fixtures.

Python: `uv sync` at the repo root. Regenerate fixtures: `uv run python contracts/fixtures/generate.py`.
