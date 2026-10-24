# features/guardrail — Owner A

> **Full spec: [`SPEC.md`](SPEC.md)** — everything you need to build this feature without waiting on anyone.

Deterministic Policy Co-Signer. Holds **only** Key 2 of the trip account's 2-of-2 multi-sig. No LLM. Spec: `docs/SPEC.md` §4.2.

- Runs on `:8002`: `POST /cosign`, `GET/PUT /policy`.
- Implements `Guardrail` as an HTTP client + `FakeGuardrail` (same rules, returns a dummy signer blob).
- Rules: quote signature/expiry, tx↔quote exact match, `max_per_item`, `max_daily_budget`, `verified_credential`, `category`, `date_window`, `geofence`.
- Reads its seed from `.env.guardrail` only. Credential checks are direct read-only XRPL `account_objects` calls (no import of `roam_ledger`).

## Done when
Approves bike+matcha from `contracts/fixtures/quotes.json`, rejects the souvenir with violations, and its signature is accepted on-ledger.
