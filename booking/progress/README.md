# Trip progress

Reports where a booked trip stands. The master agent calls `trip_progress` inside its loop on the [Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-cli.html) runtime. This package does not run that loop, does not book segments, and does not verify email.

Sandbox only. The tool compares segment times on the plan to `now`. It does not read the wall clock, open the network, or call AWS.

```python
from booking.progress import AGENTCORE_TOOL, TOOL_SPEC, handler, trip_progress

# TOOL_SPEC is the AgentCore tool definition (name, description, inputSchema).
# AGENTCORE_TOOL is the inline_function entry to pass on harness invoke.
# When the runtime returns a trip_progress tool call, call handler(tool_input).
```

Tool name: `trip_progress`.

## Input

| Field | Meaning |
| --- | --- |
| `plan` | Trip plan (`flights`, `hotels`, `attractions`). A partial plan does not raise. |
| `results` | One booking result per segment the caller has: `segmentId`, `kind`, `status`, `confirmationCode`, `emailVerified`. |
| `now` | ISO-8601 timestamp supplied by the caller. |

`status` is `booked`, `failed`, `needs_user`, or `finished`. `finished: true` also marks a segment finished. `confirmationCode` is recorded and is not used to decide the phase.

## Output

```json
{
  "phase": "in_progress",
  "onTrack": false,
  "updates": [
    {
      "segmentId": "attraction-1",
      "kind": "attraction",
      "issue": "segment end is more than 45 minutes before now and the segment is not finished",
      "action": "rebook"
    }
  ]
}
```

| Field | Values |
| --- | --- |
| `phase` | `pre_trip`, `in_progress`, or `done` |
| `onTrack` | `false` when any update has action `rebook`. Otherwise `true`. |
| `updates[].action` | `none`, `rebook`, or `verify_email` |

`updates` lists only segments that need a follow-up. On track, and when the trip is done, `updates` is empty.

## Rules

Segment times come from the plan. An explicit ISO `start` or `end` wins. Otherwise:

| Kind | Start | End |
| --- | --- | --- |
| `flight` | `departDate` at 00:00 UTC | `returnDate`, or `departDate` when there is no return |
| `hotel` | `checkIn` at 00:00 UTC | `checkOut` |
| `attraction` | `date` plus `time` (`HH:MM`) when `time` is set, else `date` at 00:00 UTC | that same timestamp when `time` is set, else `date` |

A date with no clock ends at 00:00 UTC the next day. A timestamp is that instant. Comparison is in UTC.

- If a segment's end is more than 45 minutes before `now` and the segment is not finished, `onTrack` is `false` and that segment's action is `rebook`. Exactly 45 minutes is still on track.
- If a booked segment has `emailVerified` false, its action is `verify_email`. That alone leaves `onTrack` true.
- If every segment is finished and `emailVerified` is true, `phase` is `done` and `updates` is empty.
- `phase` is `pre_trip` when `now` is before the earliest segment start. After that, until the trip is done, `phase` is `in_progress`.
- Missing fields, a partial plan, and an unreadable `now` return a result and do not raise.

## Tests

From the repository root:

```bash
python3 -m unittest booking.progress.test_progress
```
