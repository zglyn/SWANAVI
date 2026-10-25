# features/merchants, owner A

> Full spec in [`SPEC.md`](SPEC.md).

Mock Kyoto and New York shops exposed over MCP and gated with HTTP 402. The parent spec is `docs/SPEC.md` section 4.1.

- Runs on port 8001. One FastAPI app. Discovery, the MCP tools, and this file use one mount, `http://127.0.0.1:8001/mcp`.
- Implements `MerchantDirectory` from `contracts/python/roam_contracts/interfaces.py` as a client, plus `FakeMerchantDirectory`. The fake serves `contracts/fixtures/quotes.json`. New York indoor and refundable flags come from `contracts/fixtures/demo_city.json`.
- Depends on `roam-contracts` only. `MERCHANT_<ID>_ADDRESS` replaces the placeholder XRPL address when it is set.
- Each shop signs with its own ed25519 key, derived from `MERCHANT_SIGNING_SEED` and the merchant id.
- Fake-ledger confirmation sets `settlement` to `sandbox`. The escrow stays in the in-memory ledger.

## First 2 hours
- [ ] `FakeMerchantDirectory` pushed
- [ ] Catalog data for 4 merchants, including the prompt-injected trap description
- [ ] ed25519 key per merchant; sign `roam_contracts.signing.quote_signing_bytes(quote)`

## Done when
List the shops, get a signed 402 quote from each, and confirm a booking with an `X-PAYMENT` proof of a matching validated escrow. Fake-ledger confirmation is `sandbox`.
