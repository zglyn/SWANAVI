# Early-finish replan

Pulls the rest of a day forward when a segment ends early. The master agent calls `replan_early` on the [Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-cli.html) runtime when a segment ends early. This package does not run that loop, does not book segments, does not check email, and does not replan a cancellation or a late segment.

Sandbox only. The tool rewrites times on the plan it is given. It does not read the wall clock, open the network, or call AWS.

```python
from booking.replan.early import AGENTCORE_TOOL, TOOL_SPEC, handler, replan_early

# TOOL_SPEC is the AgentCore tool definition (name, description, inputSchema).
# AGENTCORE_TOOL is the inline_function entry to pass on harness invoke.
# When the runtime returns a replan_early tool call, call handler(tool_input).
```

Tool name: `replan_early`.

## Input

| Field | Meaning |
| --- | --- |
| `tripId` | Trip id. A missing id does not raise. The plan keeps its own `tripId`. |
| `now` | ISO-8601 timestamp supplied by the caller. |
| `plan` | Trip plan (`flights`, `hotels`, `attractions`). A partial plan does not raise. |
| `disruption` | `{segmentId, kind, event, deltaMinutes}` for the segment that ended early. `event` is `ended_early`. |

`kind` is `flight`, `hotel`, or `attraction`. `deltaMinutes` is how many minutes early the segment ended.

## Output

```json
{
  "segmentId": "attraction-done",
  "event": "ended_early",
  "changed": true,
  "plan": {},
  "notes": [
    "kept attraction-done",
    "shifted attraction-next earlier by 60 minutes"
  ]
}
```

| Field | Meaning |
| --- | --- |
| `segmentId` | The disruption segment. Empty when the disruption has no id. |
| `event` | Always `ended_early`. |
| `changed` | `true` when at least one later segment moved. |
| `plan` | The plan, with shifted segments updated. |
| `notes` | Short strings describing what was kept, shifted, or left in place. |

## Rules

The finished segment stays on the plan with its original times. Each call shifts the plan it is given.

Later same-day segments move earlier by `deltaMinutes`. A segment is later and same-day when its start is on the same UTC date as the finished segment's end, and at or after that end. Each moved segment keeps its duration. The shift stops at `now`: a segment is never given a start before `now`. A segment whose start is already before `now` is not moved. `deltaMinutes` of zero or less returns `changed: false` and the same plan. A disruption whose `event` is not `ended_early` does not change the plan. Missing fields, a partial plan, and an unreadable `now` return a result and do not raise.

Segment times come from the plan. An explicit ISO `start` or `end` wins (`startsAt`, `startAt`, `endsAt`, and `endAt` are aliases). Otherwise:

| Kind | Start | End |
| --- | --- | --- |
| `flight` | `departDate` at 09:00 UTC | 3 hours later |
| `hotel` | `checkIn` at 15:00 UTC | `checkOut` at 11:00 UTC |
| `attraction` | `date` plus `time` when `time` is set, else `date` at 10:00 UTC | 2 hours later |

A `departDate`, `checkIn`, `checkOut`, or `date` that already has a time uses that instant. Date-only values use the clocks above. Comparison is in UTC.

Shifted segments receive `start` and `end` as UTC timestamps (`YYYY-MM-DDTHH:MM:SSZ`). An attraction's `date` and `time` (`HH:MM`) move with the new start. A date-only `departDate`, `checkIn`, or `checkOut` stays `YYYY-MM-DD` and changes only when the calendar date changes; the new clock is in `start` and `end`. A timestamp in those fields moves with the segment. `returnDate` is not the flight's end and is left as stored.

## Tests

From the repository root:

```bash
python3 -m unittest booking.replan.early.test_replan
```
