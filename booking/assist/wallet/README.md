# Trip wallet

Lists every confirmation the traveler already has. The master agent calls `trip_wallet` on the [Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-cli.html) runtime at the end of a tick so the traveler has one list of booking, refund, and ride codes. This package does not run that loop, does not book, does not refund, and does not request a ride.

Sandbox only. The tool does not open the network or call AWS.

```python
from booking.assist.wallet import AGENTCORE_TOOL, TOOL_SPEC, handler, trip_wallet

# TOOL_SPEC is the AgentCore tool definition (name, description, inputSchema).
# AGENTCORE_TOOL is the inline_function entry to pass on harness invoke.
# When the runtime returns a trip_wallet tool call, call handler(tool_input).
```

Tool name: `trip_wallet`.

## Input

| Field | Meaning |
| --- | --- |
| `tripId` | Trip these codes belong to. |
| `items` | Booking, refund, and ride rows. An empty list is allowed. |

Each item:

| Field | Meaning |
| --- | --- |
| `kind` | `booking`, `refund`, or `ride`. Null is left off the line. |
| `segmentId` | Segment this code belongs to. Null is left off the line. |
| `code` | Confirmation code. An item with no code is left off the list. |
| `amount` | Decimal string or number. Null is left off the line. |
| `currency` | Currency code. Null is left off the line. |

## Output

```json
{
  "tripId": "sample-kyoto",
  "lines": [
    "booking flight-1 SANDBOX-FLIGHT 120.00 USD",
    "refund hotel-1 SANDBOX-REF-1 USD",
    "ride ride-1 SANDBOX-RIDE 18.00 USD"
  ],
  "count": 3
}
```

| Field | Meaning |
| --- | --- |
| `tripId` | From the input. Empty when the input has no id. |
| `lines` | One string per item that has a code. |
| `count` | Number of items that have a code. Same as the number of lines. |

## Rules

Each line is `kind`, `segmentId`, `code`, `amount`, and `currency`, in that order, joined by single spaces. Null and blank fields are left out, so a refund with no amount is `refund hotel-1 SANDBOX-REF-1` and not a line with an empty slot.

`count` counts only items with a code. An item with no code is omitted from `lines` and omitted from `count`.

Empty `items` returns `count` 0 and `lines` `[]`. A missing list is empty. Unreadable input returns that same empty result and does not raise.

## Tests

From the repository root:

```bash
python3 -m unittest booking.assist.wallet.test_wallet
```
