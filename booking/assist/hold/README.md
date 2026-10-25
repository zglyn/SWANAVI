# Hotel incidental hold

Explains a hotel incidental authorization. The hold is not a charge. `incidental_hold` says how much of that hold is still uncaptured, and the sandbox date the remainder releases. It does not capture, does not charge, and does not contact a card network.

A later integrator wires this tool into the master. This package does not. It does not call `authorize_spend` and it does not run the master loop.

Sandbox only. The tool does not open the network and does not call AWS. Nothing in this package is charged.

```python
from booking.assist.hold import AGENTCORE_TOOL, TOOL_SPEC, handler, incidental_hold

# TOOL_SPEC is the AgentCore tool definition (name, description, inputSchema).
# AGENTCORE_TOOL is the inline_function entry to pass on harness invoke.
# When the runtime returns an incidental_hold tool call, call handler(tool_input).
```

Tool name: `incidental_hold`.

## Hold versus capture

`authorizedHold` is the incidental authorization a hotel may place. Placing it does not take money. `capturedAmount` is what was later captured against that authorization. This tool does not perform either step. It only explains the difference.

`releaseAmount` is the part of the hold that was not captured. That remainder is what a sandbox release returns. `payAmount` is the amount that counts as paid: the smaller of the capture and the hold, when both numbers are usable. A capture above the hold is not accepted. The extra is not paid and is not added to the hold.

| Hold | Capture | What it means |
| --- | --- | --- |
| 200 | 0 | Nothing was captured. The hold is still not a charge. `releaseAmount` is 200 and `payAmount` is 0. |
| 200 | 40 | 40 counts as paid. `releaseAmount` is 160. `reason` is `held`. |
| 200 | 200 | The capture used the whole hold. `releaseAmount` is 0. `reason` is `captured_in_full`. `payAmount` is 200. |
| 200 | 250 | The extra 50 is not accepted. `releaseAmount` is 0, `payAmount` is 200, and `reason` is `over_capture`. |

## Seven-day sandbox release

`releaseBy` is `checkoutAt` plus 7 days. Checkout `2026-11-06T11:00:00Z` releases on `2026-11-13T11:00:00Z`. That date is a sandbox explanation of when the uncaptured remainder would drop. It is not sent to a card network, and it does not move money.

`releaseBy` is set whenever both amounts are usable and `checkoutAt` is an ISO-8601 timestamp, including when `releaseAmount` is 0. It is null when an amount is negative or otherwise unusable, and null when `checkoutAt` is missing or not an ISO timestamp. The tool does not read the wall clock.

## Input

| Field | Meaning |
| --- | --- |
| `authorizedHold` | Incidental authorization. A number or a decimal string. Not a charge. |
| `capturedAmount` | Amount captured against the hold. A number or a decimal string. This tool does not capture it. |
| `currency` | Currency code, passed through with surrounding space removed. `JPY` rounds to 0 decimals. Every other currency rounds to 2. |
| `checkoutAt` | Checkout instant, ISO-8601. `releaseBy` is this instant plus 7 days. |

## Output

```json
{
  "authorizedHold": 200,
  "capturedAmount": 40,
  "releaseAmount": 160,
  "currency": "USD",
  "releaseBy": "2026-11-13T11:00:00Z",
  "payAmount": 40,
  "reason": "held"
}
```

| Field | Meaning |
| --- | --- |
| `authorizedHold` | Hold, rounded half up. |
| `capturedAmount` | Capture, rounded the same way. On an over-capture the extra is still shown here. |
| `releaseAmount` | `authorizedHold - capturedAmount` when the capture is within the hold. 0 when the capture equals or exceeds the hold. 0 when an amount is negative. |
| `currency` | Currency from the input. Empty when the caller did not send one. |
| `releaseBy` | `checkoutAt` plus 7 days, or null. Sandbox date only. Nothing is charged. |
| `payAmount` | Amount that counts as paid: `min(capturedAmount, authorizedHold)` when both numbers are usable. On `over_capture` this is `authorizedHold`. 0 when an amount is not usable. |
| `reason` | `held`, `captured_in_full`, `over_capture`, or `invalid_amount`. |

## Rules

Compare the amounts after rounding. Each amount rounds half up to 2 decimals. `JPY` (any casing) rounds half up to 0 decimals. The subtraction uses those rounded amounts.

`reason` is `held` when the rounded capture is below the rounded hold. `releaseBy` is checkout plus 7 days.

`reason` is `captured_in_full` when the rounded amounts are equal. `releaseAmount` is 0 and `payAmount` is the hold.

`reason` is `over_capture` when the rounded capture is above the hold. `releaseAmount` is 0 and `payAmount` is the hold. The extra is not accepted.

`reason` is `invalid_amount` when either amount is missing, not a finite number, or negative. `releaseAmount` is 0, `payAmount` is 0, and `releaseBy` is null.

A partial payload, bad JSON, and any other input return a result and do not raise.

## Tests

From the repository root:

```bash
PYTHONPATH=. python3 -m unittest booking.assist.hold.test_hold
```

The tests cover a hold of 200 with a capture of 40 (`releaseAmount` 160), a capture of 200 (`releaseAmount` 0), and a capture of 250 on a 200 hold (`over_capture`, `payAmount` 200).
