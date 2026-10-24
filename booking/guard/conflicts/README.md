# Schedule conflicts

Reports segments whose times overlap. The master agent calls `check_conflicts` on the [Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-cli.html) runtime after a replan.

Sandbox only. The tool reads the plan it is given. It does not read the wall clock, open the network, or call AWS. Booking, replanning, spend checks, and the master loop stay with their own tools.

```python
from booking.guard.conflicts import AGENTCORE_TOOL, TOOL_SPEC, check_conflicts, handler

# TOOL_SPEC is the AgentCore tool definition (name, description, inputSchema).
# AGENTCORE_TOOL is the inline_function entry to pass on harness invoke.
# When the runtime returns a check_conflicts tool call, call handler(tool_input).
```

Tool name: `check_conflicts`.

## Input

| Field | Meaning |
| --- | --- |
| `now` | ISO-8601 timestamp supplied by the caller. Accepted so the master can pass the same clock it used for the replan. This tool does not drop segments because of `now`. |
| `plan` | Trip plan (`flights`, `hotels`, `attractions`). Each segment may carry `start` and `end` as ISO datetimes. A partial plan does not raise. |

A segment with `removed` true is ignored.

## Output

```json
{
  "conflicts": [
    {
      "segmentA": "flight-1",
      "segmentB": "attraction-1",
      "overlapMinutes": 60
    }
  ]
}
```

| Field | Meaning |
| --- | --- |
| `segmentA` | `segmentId` of the earlier segment in plan order. |
| `segmentB` | `segmentId` of the later segment in plan order. |
| `overlapMinutes` | Length of the shared time, in minutes. |

Plan order is `flights`, then `hotels`, then `attractions`, and within each list the order stored on the plan. Each unordered pair is reported once.

## Rules

Two segments conflict when their half-open windows `[start, end)` overlap. A segment that ends at the same instant another starts does not conflict with it.

An explicit ISO `start` or `end` wins. A date-only `start` or `end` is not an instant. Otherwise the clocks match the replan tools. Comparison is in UTC. `returnDate` is not a flight's end.

| Kind | Start | End |
| --- | --- | --- |
| `flight` | `departDate` at 09:00 UTC | 3 hours later |
| `hotel` | `checkIn` at 15:00 UTC | `checkOut` at 11:00 UTC |
| `attraction` | `date` plus `time` when `time` is set, else `date` at 10:00 UTC | 2 hours later |

A `departDate`, `checkIn`, `checkOut`, or `date` that already has a time uses that instant. Date-only values use the clocks above. A segment with no positive window is skipped. Missing fields and a partial plan return `{conflicts: []}` and do not raise. The plan is not modified.

## Tests

From the repository root:

```bash
python3 -m unittest booking.guard.conflicts.test_conflicts
```
