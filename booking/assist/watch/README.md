# Early trip watch

Flags problems before the traveler is in them. The master agent calls `watch_trip` first on every tick on the [Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-cli.html) runtime and acts immediately. This package does not run that loop, does not move the plan, and does not request a ride.

Sandbox only. The tool compares the plan and the signals to `now`. It does not read the wall clock, open the network, or call AWS. A partial input returns a result and does not raise.

```python
from booking.assist.watch import AGENTCORE_TOOL, TOOL_SPEC, handler, watch_trip

# TOOL_SPEC is the AgentCore tool definition (name, description, inputSchema).
# AGENTCORE_TOOL is the inline_function entry to pass on harness invoke.
# When the runtime returns a watch_trip tool call, call handler(tool_input).
```

Tool name: `watch_trip`.

## Input

| Field | Meaning |
| --- | --- |
| `now` | ISO-8601 timestamp supplied by the caller. |
| `plan` | Trip plan. `flights`, `hotels`, and `attractions` carry `start` and `end`. |
| `rides` | `{fromSegmentId, status}` rows the master already has. |
| `signals` | `{segmentId, event, condition, deltaMinutes}` for this tick. |

`start` and `end` are ISO-8601 datetimes. Comparison is in UTC. A date with no clock is not a time. `outdoor: true` marks an outdoor stop. `indoor: false` is the same fact. `removed: true` drops that segment from stop checks. `deltaMinutes` is accepted and is not applied.

`status` `requested` means the master has already asked for a ride from that segment.

## Output

```json
{
  "ok": false,
  "warnings": [
    {
      "segmentId": "temple",
      "issue": "outdoor segment has rain before the traveler arrives",
      "severity": "act",
      "action": "shift"
    }
  ]
}
```

| Field | Values |
| --- | --- |
| `ok` | `false` when any warning has severity `act`. `true` when `warnings` is empty. |
| `warnings[].severity` | `watch` or `act`. The rules below all use `act`. |
| `warnings[].action` | `replan`, `shift`, `request_ride`, or `check_transfer`. |

The plan in the input is not changed. No ride is added.

## Rules

Warnings follow signal order, then ride checks in plan order (flights, hotels, attractions), then transfers in start-time order.

- A signal `event` of `cancelled`, `ended_early`, or `ended_late` is severity `act`, action `replan`. `ok` is false. The segment does not have to be on the plan.
- An outdoor segment whose signal `condition` is `rain`, `storm`, or `snow`, and whose `start` is still after `now`, is severity `act`, action `shift`. That is before the traveler is there. A start equal to `now` is not shifted. An indoor segment is not shifted.
- An attraction whose `end` is `now` or up to 20 minutes after `now`, with another stop that starts at or after that end on the same UTC day, and no ride `status` `requested` for that `fromSegmentId`, is severity `act`, action `request_ride`.
- Two stops that follow each other in start-time order, where the next start is at or after this end and the gap is under 30 minutes, are severity `act`, action `check_transfer` on the earlier stop. A gap of exactly 30 minutes is clear. An overlap is not this warning.
- Anything else is `ok` true and `warnings` empty.

## Tests

From the repository root:

```bash
python3 -m unittest booking.assist.watch.test_watch
```
