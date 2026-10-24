# Dinner table hold

Holds a dinner table when the traveler will arrive after the reservation. The master agent calls `hold_table` on the [Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-cli.html) runtime when the traveler is late to a meal so the table is held.

Sandbox only. This package does not call OpenTable, open the network, or call AWS. It does not read the wall clock. Rides, luggage, and the master loop stay with their own tools.

```python
from booking.assist.table import AGENTCORE_TOOL, TOOL_SPEC, handler, hold_table

# TOOL_SPEC is the AgentCore tool definition (name, description, inputSchema).
# AGENTCORE_TOOL is the inline_function entry to pass on harness invoke.
# When the runtime returns a hold_table tool call, call handler(tool_input).
```

Tool name: `hold_table`.

## Input

| Field | Meaning |
| --- | --- |
| `segmentId` | Meal segment. Copied onto the result. |
| `venue` | Restaurant. Accepted and not used to choose the hold. |
| `reservationAt` | ISO-8601 reservation time supplied by the caller. |
| `arriveAt` | ISO-8601 arrival time supplied by the caller. |
| `partySize` | Party size. Accepted and not used to choose the hold. |

## Output

```json
{
  "segmentId": "dinner-1",
  "status": "held",
  "heldUntil": "2026-11-03T19:35:00Z",
  "reason": "traveler is late; table held until 15 minutes after arrival"
}
```

| Field | Meaning |
| --- | --- |
| `segmentId` | From the input. Empty when the input has no id. |
| `status` | `on_time`, `held`, or `failed`. |
| `heldUntil` | `reservationAt` when `on_time`. `arriveAt` plus 15 minutes when `held`. Null when `failed`. |
| `reason` | Why that status was chosen. |

A held `heldUntil` is UTC `YYYY-MM-DDTHH:MM:SSZ`. An on-time `heldUntil` is the `reservationAt` string the caller sent.

## Rules

| Arrival | Status | `heldUntil` |
| --- | --- | --- |
| `arriveAt` is at or before `reservationAt` | `on_time` | `reservationAt` |
| `arriveAt` is later | `held` | `arriveAt` plus 15 minutes |
| `reservationAt` or `arriveAt` is missing | `failed` | null |

Clocks are instants. An offset is converted before the comparison, so a later wall-clock string in another zone can still be on time. A missing time, a blank time, or a value that is not an ISO timestamp returns `failed` and does not raise. `venue` and `partySize` do not change the result.

## Tests

From the repository root:

```bash
python3 -m unittest booking.assist.table.test_hold
```
