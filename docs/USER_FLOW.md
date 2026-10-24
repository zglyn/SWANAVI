# Roam402 — User Flow

Revised from the whiteboard sketch. Main change: **prices are locked and guardrails are set before the user says "book"**, and settlement happens through escrow rather than by both sides agreeing manually.

```mermaid
flowchart TD
    %% ---------- Account ----------
    start(["Open Roam402"]) --> auth{"Has account?"}
    auth -- "No" --> signup["Sign up<br/>seedless wallet created"]
    auth -- "Yes" --> login["Log in"]
    signup --> home
    login --> home["Home<br/>past trips · preferences · wallet balance"]

    %% ---------- Plan ----------
    home --> brief["Tell the agent: where, dates, budget, interests<br/>(+ invite friends for a group trip)"]
    brief --> policy["Confirm guardrails<br/>budget cap · per-item cap · dates · area · verified merchants only<br/>(pre-filled from the brief, enforced outside the AI)"]
    policy --> discover["Agent discovers local merchants via MCP<br/>and collects locked 402 quotes — no money moves"]
    discover --> review["Itinerary with exact prices<br/>+ Direct-to-Wallet savings vs. Viator"]
    review --> decide{"Per item:<br/>accept · modify · reject"}
    decide -- "Modify / reject" --> discover
    decide -- "Happy with plan" --> select["Choose what to book<br/>(all or some)"]
    select -- "Items not booked" --> save["Saved to trip as a plan / external link"]

    %% ---------- Pay ----------
    select -- "Items to book" --> funds{"Enough in wallet?"}
    funds -- "No" --> topup["Top up: USD → RLUSD"] --> funds
    funds -- "Yes" --> group{"Group trip?"}
    group -- "Yes" --> approve["Each friend approves their share on their phone"] --> guard
    group -- "No" --> guard{"Guardrail check<br/>quotes vs. policy + merchant credential"}
    guard -- "Violation" --> blocked["Blocked — show which rule and why<br/>nothing signed, nothing spent"] --> review
    guard -- "Pass → co-signed" --> batch{"Atomic batch on XRPL<br/>all-or-nothing"}
    batch -- "Any slot fails" --> reverted["Whole batch reverts — nothing charged<br/>agent offers alternatives"] --> review
    batch -- "Success" --> booked["Booked<br/>funds held in escrow · receipts per merchant"]

    %% ---------- Trip & settlement ----------
    booked --> tripday{"On the day"}
    tripday -- "Check in (tap)" --> release["Escrow releases to merchant"]
    tripday -- "Weather / delay" --> pivot["Refundable escrow cancelled → funds back in seconds<br/>agent proposes in-budget alternative"] --> review
    tripday -- "Cancellation window passes" --> release
    release --> history["Trip saved to history<br/>improves future suggestions"]
    history --> home
```

## Steps

| # | Step | What changed vs. sketch | Owner |
|---|---|---|---|
| 1 | Sign up / log in → home | Wallet created at signup; history shows balance too | B (gateway) / D |
| 2 | Brief the agent | Unchanged; group invite added | B / D |
| 3 | **Confirm guardrails** | **New.** Budget becomes a hard on-ledger rule, not just a sentence to the LLM | A (guardrail) / D |
| 4 | Discover + locked quotes | **New.** Suggestions carry real, signed prices before acceptance | A (merchants) / B |
| 5 | Accept / modify / reject loop | Now per item, and every iteration re-quotes | B / D |
| 6 | Choose what to book | Replaces yes/no: users can book a subset; the rest is saved | D |
| 7 | Wallet check / top-up | **New.** "Funds in wallet" needed a way in | C / D |
| 8 | Group approval | **New.** Each friend signs their share | C (stretch) |
| 9 | Guardrail check | **New.** Failure path back to review with reasons | A |
| 10 | Atomic batch | **New.** Failure path: everything reverts, nothing charged | C |
| 11 | Escrow → release | Replaces "both want to settle": releases on check-in or when the cancellation window passes | C / A |
| 12 | Disruption pivot | **New.** Refund + re-plan loop | B / C |
| 13 | Save to history | Closes the loop with step 1 | B |

## MVP scope (36h demo)

Steps 1, 7 and 8 are slideware. The demo starts logged in with a pre-funded wallet. Steps 2–6 and 9–12 are the live
demo: happy path, the **Malicious Upsell** button (step 9 blocked) and the **Rainstorm** button (step 12).
