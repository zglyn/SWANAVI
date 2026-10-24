# Late hotel checkout

The master calls `late_checkout` on [Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-cli.html) on departure morning so the room is held when the flight is late in the day. This package does not run that loop and does not contact the hotel.

Sandbox only. The tool does not open the network or call AWS. It returns the decision. A `requested` result is the hold: two extra hours, not a live hotel call.

```python
from booking.assist.checkout import AGENTCORE_TOOL, TOOL_SPEC, handler, late_checkout

# TOOL_SPEC is the AgentCore tool definition (name, description, inputSchema).
# AGENTCORE_TOOL is the inline_function entry to pass on harness invoke.
# When the runtime returns a late_checkout tool call, call handler(tool_input).
```

Tool name: `late_checkout`.

## Input

| Field | Meaning |
| --- | --- |
| `hotelSegmentId` | Hotel segment whose room may be held past checkout. |
| `checkoutAt` | Scheduled checkout, ISO-8601. |
| `departAt` | Flight departure, ISO-8601. |
| `travelerName` | Traveler named in the reason when a late checkout is requested. |

## Output

```json
{
  "hotelSegmentId": "hotel-kyoto",
  "status": "requested",
  "until": "2026-11-06T12:00:00Z",
  "reason": "Mina Cho's flight departs more than 2 hours after checkout, so the room is held for 2 extra hours."
}
```

| Field | Meaning |
| --- | --- |
| `hotelSegmentId` | From the input. Empty when the input has no id. |
| `status` | `requested`, `not_needed`, or `failed` |
| `until` | When `requested`, `checkoutAt` plus 2 hours. `null` otherwise. A `Z` input stays in UTC with a `Z` suffix. |
| `reason` | Names the traveler when status is `requested`. A short explanation otherwise. |

## Rules

Compare the two instants. A time with no offset is UTC.

- If `departAt` is more than 2 hours after `checkoutAt`, `status` is `requested` and `until` is `checkoutAt` plus 2 hours. The reason names the traveler. A flight 5 hours after checkout requests those 2 extra hours. The hold does not run until the flight.
- If `departAt` is within 2 hours after checkout, or before it, `status` is `not_needed` and `until` is `null`. Exactly 2 hours is within the window. A flight 1 hour after checkout is not needed.
- A missing `checkoutAt` or `departAt`, including a date with no clock time, returns `failed` and does not raise.
- An unreadable timestamp returns `failed` and does not raise.
- An unreadable input returns `failed` and does not raise.

## Tests

From the repository root:

```bash
python3 -m unittest booking.assist.checkout.test_checkout
```

A flight 5 hours after checkout requests 2 extra hours. A flight 1 hour after checkout is not needed.
