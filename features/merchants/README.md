# features/merchants — Owner A

> **Full spec: [`SPEC.md`](SPEC.md)** — everything you need to build this feature without waiting on anyone.

Mock Kyoto merchants exposed over MCP and gated with HTTP 402 (`x402-xrpl` or hand-rolled). Spec: `docs/SPEC.md` §4.1.

- Runs on `:8001`. One FastAPI app, one MCP mount per merchant at `/m/{merchant_id}/mcp`.
- Implements `MerchantDirectory` (`contracts/python/roam_contracts/interfaces.py`) as a client + `FakeMerchantDirectory` (serves `contracts/fixtures/quotes.json`).
- Depends on: `roam-contracts` only. Reads merchant XRPL addresses from `.env.ledger` (written by ledger bootstrap); falls back to placeholders.

## First 2 hours
- [ ] `FakeMerchantDirectory` pushed
- [ ] Catalog data for 4 merchants (incl. prompt-injected trap description)
- [ ] ed25519 key per merchant; sign `roam_contracts.signing.quote_signing_bytes(quote)`

## Done when
List merchants, get a signed 402 quote from each, complete a booking with an `X-PAYMENT` proof of a real escrow.
