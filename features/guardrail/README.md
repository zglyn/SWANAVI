# features/guardrail

> **Full spec: [`SPEC.md`](SPEC.md)**

Deterministic policy co-signer. Holds **only** Key 2 of the trip account's 2-of-2 multi-sig and signs a transaction only
when every rule passes. No LLM, so a prompt injection has nothing to talk to.

## Run

```bash
uv run python -m roam_guardrail.server        # :8002
uv run pytest features/guardrail
```

`GET /status` shows how it's wired (guardrail address, credential source, whether quote signatures are checked).

| Method | Path | |
|---|---|---|
| GET / PUT | `/policy` | the stored policy (PUT validates caps > 0 and per-item ≤ daily) |
| POST | `/cosign` | `CosignRequest` → `CosignResponse`; always 200, `decision.approved` says whether it signed |
| POST | `/evaluate` | same decision as `/cosign`, never signs or counts spend (UI previews) |
| POST | `/reset` | default policy, clears today's spend |

## Code

- `rules.py` — the 9 rules as pure functions. Every violation is returned, not just the first.
- `cosigner.py` — stored policy, today's spend, signs with Key 2 only when approved.
- `sources.py` — merchant keys (`GET {MERCHANTS_URL}/merchants`), credentials (XRPL `ledger_entry` or offline allowlist), Key 2 signing.
- `client.py` — `HttpGuardrail` (talks to `:8002`) and `FakeGuardrail` (same rules in-process, dummy signer blob). The fake starts from the contract default policy. The server starts from the New York activity policy.

## What it never trusts

- **The request's `policy`:** ignored. The stored policy (`PUT /policy`) is the only one that counts, so the
  gateway must forward dashboard policy edits here.
- **The request's `spent_today`:** ignored. The daily total is the spend book. `record_spend` posts a booking or ledger amount, and each co-sign posts its own. Concurrent budget decisions take that book one at a time.
- **The agent's summary of the tx:** every inner `EscrowCreate` is decoded from the raw tx and matched 1:1 to a signed quote.

## Config

| Variable | Default | |
|---|---|---|
| `GUARDRAIL_PORT` | `8002` | |
| `GUARDRAIL_SEED` | — | Key 2, from `.env.guardrail` (written by ledger bootstrap). Without it a throwaway wallet is used. |
| `CREDENTIAL_ISSUER_ADDRESS` | — | from `.env.ledger`. Without it (or with `GUARDRAIL_OFFLINE=1`) credentials come from the allowlist. |
| `GUARDRAIL_VERIFIED_MERCHANTS` | every fixture shop except `lucky-souvenir` | allowlist, comma-separated merchant ids |
| `TRIP_ADDRESS` | — | when set, transactions must spend from this account |
| `XRPL_RPC_URL` | devnet | |
| `MERCHANTS_URL` | `http://localhost:8001` | where quote-signing keys come from |
| `GUARDRAIL_SKIP_QUOTE_SIG` | `0` | `1` skips the signature rule (no merchant server running) |
| `GUARDRAIL_XRP_AS_RLUSD` | `1` | XRP escrows count as RLUSD 1:1 until trust lines exist |
| `GUARDRAIL_POLICY_FILE` | — | persist the policy to this JSON file |

## Still to do

- Submit one real 2-of-2 transaction on devnet once ledger bootstrap exists (SPEC §7 test 5). The signature format is
  already checked locally against `encode_for_multisigning`.
