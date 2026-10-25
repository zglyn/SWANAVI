# Ground transfers

Checks that the time between two consecutive stops covers the ride. The master agent calls `check_transfer` on the [Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-cli.html) runtime between consecutive stops.

Sandbox only. The caller supplies both clocks and the ride length. This package does not read the wall clock, call a maps API, open the network, or call AWS. Booking, replanning, the other assist checks, and the master loop stay with their own tools.

```python
from booking.assist.transfers import AGENTCORE_TOOL, TOOL_SPEC, check_transfer, handler

# TOOL_SPEC is the AgentCore tool definition (name, description, inputSchema).
# AGENTCORE_TOOL is the inline_function entry to pass on harness invoke.
# When the runtime returns a check_transfer tool call, call handler(tool_input).
```

Tool name: `check_transfer`.

## Input

| Field | Meaning |
| --- | --- |
| `fromSegmentId` | `segmentId` of the stop that is ending. |
| `toSegmentId` | `segmentId` of the next stop. |
| `fromEnd` | ISO-8601 instant when the first stop ends. |
| `toStart` | ISO-8601 instant when the next stop starts. |
| `travelMinutes` | Ride length in minutes. The caller supplies this. There is no route lookup. |

## Output

```json
{
  "ok": true,
  "leaveBy": "2026-11-03T10:00:00Z",
  "shortfallMinutes": 0,
  "reason": "enough_time"
}
```

| Field | Meaning |
| --- | --- |
| `ok` | True when the gap is at least `travelMinutes`. |
| `leaveBy` | `fromEnd` when `ok` is true, otherwise `null`. |
| `shortfallMinutes` | Whole minutes still needed. `0` when the ride fits. |
| `reason` | `enough_time`, `shortfall`, `overlap`, or `invalid_input`. |

## Rules

The gap is `toStart - fromEnd` in minutes. Comparison is on the absolute instant, so an offset and a `Z` clock for the same moment agree.

`ok` is true when the gap is greater than or equal to `travelMinutes`. `leaveBy` is then the `fromEnd` value the caller sent.

`shortfallMinutes` is `max(0, travelMinutes - gap)` when the gap is a whole number of minutes. A leftover partial minute counts as one more minute still needed.

A negative gap means the next stop starts before this one ends. That is an overlap: `ok` is false, `leaveBy` is null, and `reason` is `overlap`. A gap of zero is not an overlap. It is a shortfall when the ride is longer than zero.

A partial or unreadable input returns `ok` false, `leaveBy` null, `shortfallMinutes` 0, and `reason` `invalid_input`. It does not raise. A date without a time is not an instant.

| Gap | Ride | Result |
| --- | --- | --- |
| 40 minutes | 30 minutes | `ok` true, `leaveBy` is `fromEnd`, shortfall 0 |
| 10 minutes | 30 minutes | `ok` false, shortfall 20 |
| next stop starts earlier | 30 minutes | `ok` false, `reason` `overlap` |

## Tests

From the repository root:

```bash
python3 -m unittest booking.assist.transfers.test_transfer
```
