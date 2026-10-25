# Cancellation replanning

Replans the rest of a day when one segment is cancelled. The master agent calls `replan_cancel` on the [Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-cli.html) runtime when a segment is cancelled. This package does not run that loop, does not book segments, does not check confirmation email, and does not report trip progress.

Sandbox only. The tool uses the caller-supplied `now`. It does not read the wall clock, open the network, or call AWS.

```python
from booking.replan.cancel import AGENTCORE_TOOL, TOOL_SPEC, handler, replan_cancel

# TOOL_SPEC is the AgentCore tool definition (name, description, inputSchema).
# AGENTCORE_TOOL is the inline_function entry to pass on harness invoke.
# When the runtime returns a replan_cancel tool call, call handler(tool_input).
```

Tool name: `replan_cancel`.

## Input

| Field | Meaning |
| --- | --- |
| `tripId` | Trip id. Recorded by the caller. This tool does not look it up. |
| `now` | ISO-8601 timestamp supplied by the caller. |
| `plan` | Trip plan (`flights`, `hotels`, `attractions`). A partial plan does not raise. |
| `disruption` | `{segmentId, kind, event: "cancelled", deltaMinutes \| null}`. |

`deltaMinutes` is accepted and is not the shift. The shift is the cancelled segment's duration (`end - start`).

## Output

```json
{
  "segmentId": "temple",
  "event": "cancelled",
  "changed": true,
  "plan": {},
  "notes": [
    "marked temple removed",
    "shifted garden earlier by 120 minutes"
  ]
}
```

| Field | Meaning |
| --- | --- |
| `segmentId` | From the disruption. Empty when the disruption has no id. |
| `event` | `cancelled` |
| `changed` | `true` when the cancelled segment was marked `removed` on this call |
| `plan` | Copy of the plan with that change applied |
| `notes` | What changed, or why nothing changed |

The cancelled segment stays in its list with `removed: true`. A second call for a segment that is already removed does not shift the day again.

## Rules

Segment times come from the plan. An explicit ISO `start` or `end` wins. Otherwise:

| Kind | Start | End |
| --- | --- | --- |
| `flight` | `departDate` at 09:00 UTC | 3 hours later. `returnDate` is not the end. |
| `hotel` | `checkIn` at 15:00 UTC | `checkOut` at 11:00 UTC |
| `attraction` | `date` plus `time` when `time` is set, else `date` at 10:00 UTC | 2 hours later |

A date-only field is that UTC day. A timestamp is that instant. Comparison is in UTC.

- The cancelled segment is marked `removed: true`. Its own start and end stay as they were.
- Every other segment that starts later on that same UTC day moves earlier by the cancelled duration. Its `start` and `end` are written as ISO-8601 UTC timestamps. An attraction's `date` and `time` follow the new start. A flight's `departDate` follows the new start. A hotel's `checkIn` and `checkOut` follow the new start and end dates.
- A segment whose start is before `now` stays in place. A segment that starts at exactly `now` has not started before `now`, so it can move.
- Segments on other days stay in place. Spacing between moved segments stays the same, because each one moves by the same duration.
- An unknown `segmentId` returns `changed: false` and a note that names the id. It does not raise.
- A missing `segmentId`, an unreadable `now`, a segment with no positive duration, and a partial plan return a result and do not raise. An unreadable `now` or a missing duration still marks a found segment removed, and leaves every other segment in place.

## Tests

From the repository root:

```bash
python3 -m unittest booking.replan.cancel.test_cancel
```
