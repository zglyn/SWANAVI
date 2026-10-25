---
name: verify-mock-checkout-leash
description: "Check that features/dashboard/lib/mock.ts refuses a checkout when a quote breaks the per-item cap, the daily budget, the verified-merchant rule, or the category allowlist. Use when changing evaluate, checkout, or the policy and wallet fields those functions read."
---

# Verify the mock checkout leash

The mock checkout is the money gate the demo runs when `NEXT_PUBLIC_USE_MOCKS` is not `0`. `evaluate` decides. `checkout` must not submit a batch, and must not move the wallet, when that decision is a violation.

## Property

A quote list that breaks `max_per_item`, `max_daily_budget`, `verified_credential`, or `category` is not approved, and `checkout` does not submit it or change the wallet.

## Harm

The traveler pays a merchant the policy forbids. That includes the $500 unverified souvenir the demo is built to block.

## When a change needs this check

Run it when a change touches any of these in `features/dashboard/lib/mock.ts`:

- `evaluate`
- `checkout`
- `state.policy`, `state.spentToday`, `state.balance`, `state.escrows`
- the fields those functions read on a quote: `amount`, `merchant_verified`, `category`, `invoice_id`

A change that only edits copy, the 850ms pause, or a scenario that never calls `checkout` does not need this check.

## Command

From the repo root, with Node 22:

```text
node .cursor/skills/verify-mock-checkout-leash/check.mjs
```

That single command works in Windows PowerShell 5 and in bash. The script installs its pinned TypeScript 5.8.3 if `node_modules` is missing, then runs the check. TypeScript only strips types. The functions that run are the ones in `mock.ts`. One sequential run of the bound finishes in a few seconds.

## How to read the result

`result: PASS` means every violating case in the bound was refused and left the wallet untouched.

`result: FAIL` is a counterexample. Replay it on `evaluate` and `checkout` in order. If a printed step cannot happen in those functions, the harness has drifted. Treat that as a modeling error and fix the harness, not the property. If every step happens in those functions, the code breaks the property. Leave the property alone. Do not change product code from this skill unless the user asks.

`result: HARNESS` means the checker could not load `evaluate` or `checkout`. The usual cause is a rename or a rewrite of the demo pause line the harness replaces. Update the harness so it describes the new code, then run again.

## Show that the check can fail

In `checkout`, the refusal is the early return on `!decision.approved`. Change that condition to `false && !decision.approved` and run the command. The check fails on the fixture trap quote (`GOLD-CAT`, amount `500.00`, unverified, category `shopping`): `evaluate` still refuses, then `checkout` emits `batch.submitted` and `batch.validated` and moves the balance from `250` to `-250`. Restore the condition. The result is `result: PASS` again and `mock.ts` has no diff.

## Coverage

| What | Where |
| --- | --- |
| Decision | `evaluate` in `features/dashboard/lib/mock.ts` |
| Submission and wallet | `checkout` in the same file |
| Rules in the property | `max_per_item`, `max_daily_budget`, `verified_credential`, `category` |
| Sync commit | `82567e7460b32c002446ba195aa6572cce920fb7` |
| `mock.ts` sha256 at that commit | `2e0043d94693a928c01002e4f6156987f076879e82bcf8736928688936e599fe` |

`check.mjs` prints `source_sha256` of `mock.ts` on every run. If that hash differs from the one above, the covered file has changed since the sync commit. Move the sync commit forward only after you confirm that `evaluate`, `checkout`, and this harness still describe that file at the new commit. A green run on a stale harness is not a confirmation.

## Bounds and assumptions

The check calls the real functions on one checkout at a time.

- Quote lists of length 1 or 2, plus the fixture cases named in the output path (the trap quote, bike plus matcha, and matcha under the tight cap).
- Amounts in the grid are cent strings between `0.00` and `500.00`. Spent-today values are `0.00`, `55.00`, `80.00`, and `100.00`.
- Policies are the fixture default, a tight cap (`max_per_item` `20.00`, daily `50.00`, activity and food only), and a wide cap that allows shopping without a verified credential.
- `merchant_verified` is `true`, `false`, or `null`. The oracle treats anything other than `true` as unverified when the policy requires a credential. That matches `!q.merchant_verified` in `evaluate`.
- Category values in the grid are `activity`, `food`, and `shopping`.
- The money oracle is integer cents. A separate numeric sweep checks that `Number` on cent strings from `0.00` through `200.00` agrees with those integers for a single value, a sum of two values, and budget minus spent. The sweep is there so a float false-approve inside that range fails this check instead of hiding in the grid.
- The harness deletes the Next.js import lines. Each `@fixtures/` import becomes its JSON. Every other value import becomes a stub that returns an empty object, so `evaluate` and `checkout` must not read from another module. It replaces the demo `sleep` with an already-resolved promise. Step order inside one `checkout` call stays the same.
- Wallet figures compared on a refusal are `state.balance`, `state.spentToday`, and the escrow map size. The starting balance in the check is `250`.

## What this does not cover

- Overlapping `checkout` calls. This is the closest hole. Measured against the sync commit, with the real `checkout`: policy `max_per_item` `45.00`, `max_daily_budget` `70.00`, credential required, category `food`, `spentToday` `0`, balance `250`. Start a verified `40.00` food quote and start a second `40.00` quote before the first call adds to `spentToday`. Both calls pass `evaluate` while `spentToday` is still `0`, both return `success`, `spentToday` ends at `80`, and the balance ends at `170` with two escrows. Both quotes were submitted under either demo sleep, a resolved promise or a `0` timer. The daily total was `80` against a `70` cap. The book button in `features/dashboard/components/dashboard/TravellerPanel.tsx` is disabled while `busy` is true, so a second click after that render does not call `checkout`. This check does not run the overlapping schedule, and it does not claim the button closes the race.
- Quote signatures, expiry, date window, geofence, and matching an inner transaction to a quote. `evaluate` does not implement those rules.
- The real guardrail service. `features/guardrail` is a stub. This check is about the mock the dashboard runs.
- The inspector reducer in `features/dashboard/lib/useDemo.ts`. `batch.validated` sets the ledger signer to signed without reading the guardrail signer.
- `source_tag_for` in `contracts/python/roam_contracts/models.py`. It claims a unique per-booking tag and uses the first four bytes of the invoice id.
- False refusals. A legal quote that `evaluate` rejects still passes this check.
- Empty quote lists, amounts with more than two decimal places, and more than two quotes in one checkout.
