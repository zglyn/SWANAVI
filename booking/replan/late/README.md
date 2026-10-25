# Late-finish replan

Shifts the rest of a day when one segment ends late. The master agent calls `replan_late` on the [Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-cli.html) runtime when a segment ends late.

Sandbox only. The tool compares segment times on the plan to `now`. It does not read the wall clock, open the network, or call AWS. Booking, email checks, trip progress, and the master loop stay with their own tools.

```python
from booking.replan.late import AGENTCORE_TOOL, TOOL_SPEC, handler, replan_late

# TOOL_SPEC is the AgentCore tool definition (name, description, inputSchema).
# AGENTCORE_TOOL is the inline_function entry to pass on harness invoke.
# When the runtime returns a replan_late tool call, call handler(tool_input).
```

Tool name: `replan_late`.

## Input

| Field | Meaning |
| --- | --- |
| `tripId` | Trip being replanned. The plan keeps its own `tripId`. |
| `now` | ISO-8601 timestamp supplied by the caller. |
| `plan` | Trip plan (`flights`, `hotels`, `attractions`). A partial plan does not raise. |
| `disruption` | `segmentId`, `kind`, `event` (`ended_late`), and `deltaMinutes`. |

`kind` is `flight`, `hotel`, or `attraction`.

## Output

```json
{
  "segmentId": "attraction-1",
  "event": "ended_late",
  "changed": true,
  "plan": {},
  "notes": [
    "kept finished segment attraction-1",
    "shifted attraction-2 later by 60 minutes"
  ]
}
```

| Field | Meaning |
| --- | --- |
| `segmentId` | The segment that ended late. |
| `event` | Always `ended_late`. |
| `changed` | `true` when a later same-day segment moved. |
| `plan` | The plan, with those segments shifted. |
| `notes` | One string per decision. |

## Rules

The finished segment stays as it was. Later segments on the same UTC day move later by `deltaMinutes`. Each one moves by that same amount. A segment on another day stays put.

A segment whose start is before `now` stays put. `deltaMinutes` of zero or less leaves the whole plan unchanged (`changed` is false). Missing fields, a partial plan, an unknown segment, and an unreadable `now` return a result and do not raise.

Clocks are UTC. An explicit ISO `start` or `end` wins. Otherwise:

| Kind | Start | End |
| --- | --- | --- |
| `flight` | `departDate` at 09:00 UTC | 3 hours later |
| `hotel` | `checkIn` at 15:00 UTC | `checkOut` at 11:00 UTC |
| `attraction` | `date` plus `time` when `time` is set, else `date` at 10:00 UTC | 2 hours later |

A date-only `departDate`, `checkIn`, or `checkOut` keeps that calendar day. The shifted clock is written to `start` and `end` (`YYYY-MM-DDTHH:MM:SSZ`). An attraction `time` (`HH:MM`) moves with the new start, and its `date` moves when the shift crosses midnight.

"Later" means the other segment's start is at or after the finished segment's end. "Same day" is the UTC date of that end.

## Tests

From the repository root:

```bash
python3 -m unittest booking.replan.late.test_replan
```
