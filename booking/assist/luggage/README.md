# Hotel luggage drop

Asks a hotel desk to hold bags when a flight lands before check-in. The master agent calls `luggage_drop` on the [Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-cli.html) runtime when a flight lands before hotel check-in. This package does not run that loop and does not book the hotel.

Sandbox only. The tool does not open the network or call AWS.

```python
from booking.assist.luggage import AGENTCORE_TOOL, TOOL_SPEC, handler, luggage_drop

# TOOL_SPEC is the AgentCore tool definition (name, description, inputSchema).
# AGENTCORE_TOOL is the inline_function entry to pass on harness invoke.
# When the runtime returns a luggage_drop tool call, call handler(tool_input).
```

Tool name: `luggage_drop`.

## Input

| Field | Meaning |
| --- | --- |
| `hotelSegmentId` | Hotel segment. Copied onto the result. This tool does not look it up. |
| `travelerName` | Traveler the desk note names when a hold is requested. |
| `arriveAt` | ISO-8601 arrival time. The caller supplies it. This tool does not read the wall clock. |
| `checkInAt` | ISO-8601 hotel check-in time. |

## Output

```json
{
  "hotelSegmentId": "hotel-1",
  "status": "drop_requested",
  "deskNote": "Desk: please hold bags for Ada Lovelace until 2026-11-02T15:00:00Z.",
  "reason": null
}
```

| Field | Meaning |
| --- | --- |
| `hotelSegmentId` | From the input. Empty when the input has no id. |
| `status` | `drop_requested`, `not_needed`, or `failed` |
| `deskNote` | Names the traveler and asks the desk to hold bags until `checkInAt` when a drop is requested. Empty otherwise. |
| `reason` | Why the drop failed. `null` when status is `drop_requested` or `not_needed`. |

## Rules

Comparison is in UTC. A timestamp without a zone is read as UTC. A date-only value is midnight UTC.

- `arriveAt` before `checkInAt`, with a traveler name: `status` is `drop_requested`. `deskNote` names the traveler and asks the desk to hold bags until `checkInAt`.
- `arriveAt` at or after `checkInAt`: `status` is `not_needed`.
- A missing `arriveAt` or `checkInAt`, or a blank traveler name on an early arrival, returns `status` `failed` and a `reason`. It does not raise.
- An unreadable input returns `status` `failed` and does not raise.

## Tests

From the repository root:

```bash
python3 -m unittest booking.assist.luggage.test_drop
```
