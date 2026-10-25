# Cancellation refunds

Records a sandbox refund for one cancelled booking. The master agent calls `refund_booking` after `replan_cancel` on the [Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-cli.html) runtime. This package does not run that loop, does not replan the day, and does not book a replacement.

Sandbox only. The tool does not open the network, charge a card, or call AWS.

```python
from booking.refund import AGENTCORE_TOOL, TOOL_SPEC, handler, refund_booking

# TOOL_SPEC is the AgentCore tool definition (name, description, inputSchema).
# AGENTCORE_TOOL is the inline_function entry to pass on harness invoke.
# When the runtime returns a refund_booking tool call, call handler(tool_input).
```

Tool name: `refund_booking`.

## Input

| Field | Meaning |
| --- | --- |
| `segmentId` | Segment the master just cancelled. |
| `confirmationCode` | Booking code. A refund requires a code that starts with `SANDBOX-`. |
| `amount` | Refund amount. A decimal string or a number. |
| `currency` | Currency code. Echoed when it is a non-empty string. |
| `event` | `cancelled`. The master sets this after `replan_cancel`. |

## Output

```json
{
  "segmentId": "temple",
  "status": "refunded",
  "refundCode": "SANDBOX-REF-0123456789AB",
  "amount": "48.00",
  "currency": "USD",
  "reason": null
}
```

| Field | Meaning |
| --- | --- |
| `segmentId` | From the input. Empty when the input has no id. |
| `status` | `refunded` or `failed` |
| `refundCode` | Starts with `SANDBOX-REF-` when refunded. `null` when failed. |
| `amount` | The input amount when it can be read. |
| `currency` | The input currency when it is a non-empty string, otherwise `null`. |
| `reason` | Why the refund failed. `null` when status is `refunded`. |

## Rules

The refund is recorded only when all three are true:

- `event` is `cancelled`.
- `confirmationCode` is present and starts with `SANDBOX-`.
- `amount` is present and is zero or greater (a non-negative integer, a finite non-negative number, or a decimal string such as `"48.00"`).

Then `status` is `refunded`, `refundCode` starts with `SANDBOX-REF-`, and `amount` is echoed. The same input returns the same refund code.

Anything else returns `status` `failed`, `refundCode` `null`, and a `reason`. A missing confirmation code fails and does not raise. A code that does not start with `SANDBOX-` fails and does not raise. An unreadable input fails and does not raise.

`currency` is not required. It is echoed when the caller sent one.

## Tests

From the repository root:

```bash
python3 -m unittest booking.refund.test_refund
```
