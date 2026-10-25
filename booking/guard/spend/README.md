# Spend guard

Pays only the amount the traveler already authorized. This is the Mastercard Agent Pay style limit. The master agent calls `authorize_spend` on the [Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-cli.html) runtime before a charge. The traveler is not asked to dispute the extra.

Sandbox only. The tool compares two amounts the caller supplies. It does not charge a card, submit an XRPL transaction, or call AWS. Budget checks, schedule conflicts, refunds, traveler notices, booking, and the master loop stay with their own tools.

```python
from booking.guard.spend import AGENTCORE_TOOL, TOOL_SPEC, authorize_spend, handler

# TOOL_SPEC is the AgentCore tool definition (name, description, inputSchema).
# AGENTCORE_TOOL is the inline_function entry to pass on harness invoke.
# When the runtime returns an authorize_spend tool call, call handler(tool_input).
```

Tool name: `authorize_spend`.

## Input

| Field | Meaning |
| --- | --- |
| `segmentId` | Segment the charge would pay for. |
| `currency` | Currency code, passed through unchanged. |
| `authorizedAmount` | Limit the traveler already approved. Number or decimal string. |
| `requestedAmount` | Amount the merchant asked to capture. Number or decimal string. |
| `reason` | Caller reason. Kept when the request is within the limit. |

## Output

```json
{
  "segmentId": "hotel-1",
  "decision": "pay",
  "payAmount": 10,
  "currency": "USD",
  "reason": "over_capture_rejected"
}
```

| Field | Meaning |
| --- | --- |
| `segmentId` | The segment from the input. Empty when it was missing. |
| `decision` | `pay` or `reject`. |
| `payAmount` | The amount that may be captured. `0` when `decision` is `reject`. |
| `currency` | The currency from the input. |
| `reason` | `over_capture_rejected` when the request was above the limit. `invalid_amount` when an amount is negative or missing. Otherwise the caller reason. |

## Rules

`requestedAmount` less than or equal to `authorizedAmount`: `decision` is `pay` and `payAmount` is `requestedAmount`. An authorized `$10` against a requested `$8` pays `$8`.

`requestedAmount` greater than `authorizedAmount`: `decision` is still `pay`, `payAmount` is `authorizedAmount`, and `reason` is `over_capture_rejected`. An authorized `$10` against a requested `$12` pays `$10`. The extra is not captured, and the traveler is not asked to approve it.

A negative amount, a missing amount, or an amount that is not a finite number: `decision` is `reject` and `payAmount` is `0`. Zero is allowed. A partial payload returns a result and does not raise.

## Tests

From the repository root:

```bash
python3 -m unittest booking.guard.spend.test_spend
```
