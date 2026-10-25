# Opening hours

Checks one stop against the place's hours. The master agent calls `check_hours` on the [Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-cli.html) runtime after a replan moves a stop.

Sandbox only. The tool reads the fields it is given. It does not read the wall clock, open the network, or call AWS. Booking, replanning, and the master loop stay with their own tools.

```python
from booking.assist.hours import AGENTCORE_TOOL, TOOL_SPEC, check_hours, handler

# TOOL_SPEC is the AgentCore tool definition (name, description, inputSchema).
# AGENTCORE_TOOL is the inline_function entry to pass on harness invoke.
# When the runtime returns a check_hours tool call, call handler(tool_input).
```

Tool name: `check_hours`.

## Input

| Field | Meaning |
| --- | --- |
| `segmentId` | Segment id of the stop that was moved. |
| `start` | ISO-8601 start. The weekday and the clock are taken from this timestamp as written. |
| `end` | ISO-8601 end. The clock is taken from this timestamp as written. |
| `open` | Opening time as `HH:MM`. |
| `close` | Closing time as `HH:MM`. |
| `closedWeekdays` | Integers for days the place is closed. Monday is `0` and Sunday is `6`. An empty list means every weekday can be open. |

## Output

```json
{
  "segmentId": "attraction-1",
  "ok": true,
  "reason": "within opening hours"
}
```

| Field | Meaning |
| --- | --- |
| `segmentId` | The `segmentId` that was checked, or `""` when it was missing. |
| `ok` | `true` only when the stop is inside hours. |
| `reason` | Why `ok` is false, or `within opening hours` when it is true. |

## Rules

`ok` is false when the start weekday is in `closedWeekdays`, or the start clock is before `open`, or the end clock is after `close`. Hours are half-open `[open, close)`. A stop that starts at `open` is inside. A stop that touches `close` exactly is not.

The clock and the weekday come from the ISO timestamp itself. `2026-10-26T00:30:00+09:00` is Monday at 00:30, including when that instant is still Sunday in UTC. A `Z` timestamp uses the `Z` clock. A timestamp with no offset uses the numbers written on it. Nothing is shifted into the machine timezone.

| `reason` | When |
| --- | --- |
| `within opening hours` | Start weekday is open, start is at or after `open` and before `close`, and end is after start and before `close`. |
| `closed on Sunday` | Start weekday is in `closedWeekdays`. The weekday name matches Monday=`0` through Sunday=`6`. |
| `starts before opening` | Start clock is before `open`. |
| `ends after closing` | End clock is after `close`. |
| `touches closing time` | Start or end equals `close`. |
| `starts at or after closing` | Start clock is after `close`. |
| `end is not after start` | End clock is at or before the start clock. |
| `missing fields` | A required field is missing or cannot be read. |

Missing or unreadable fields return `ok` false and do not raise. That includes a non-string `segmentId`, a date with no time, an `open` or `close` that is not `HH:MM`, a `closedWeekdays` value that is not a list of integers from 0 to 6, and a `close` that is not after `open`. The input is not modified.

## Tests

From the repository root:

```bash
python3 -m unittest booking.assist.hours.test_hours
```
