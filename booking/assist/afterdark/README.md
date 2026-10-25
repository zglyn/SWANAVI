# After dark

Decides whether a walk should become a ride after sunset. The master agent calls `after_dark` on the [Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-cli.html) runtime. When the result `action` is `request_ride`, the master calls the ride agent. This package does not request the ride and does not run that loop.

Sandbox only. The caller supplies `segmentId`, `mode`, `now`, and `sunset`. The tool does not read the wall clock, look up the segment, open the network, or call AWS.

```python
from booking.assist.afterdark import AGENTCORE_TOOL, TOOL_SPEC, after_dark, handler

# TOOL_SPEC is the AgentCore tool definition (name, description, inputSchema).
# AGENTCORE_TOOL is the inline_function entry to pass on harness invoke.
# When the runtime returns an after_dark tool call, call handler(tool_input).
```

Tool name: `after_dark`.

## Input

| Field | Meaning |
| --- | --- |
| `segmentId` | Segment the master is checking. Echoed on the result. Not looked up. |
| `mode` | `walk` or `ride`. |
| `now` | ISO-8601 instant supplied by the caller. This tool does not read the wall clock. |
| `sunset` | ISO-8601 sunset instant supplied by the caller. |

## Output

```json
{
  "segmentId": "walk-fushimi",
  "ok": false,
  "action": "request_ride",
  "reason": "walk is at or after sunset"
}
```

| Field | Meaning |
| --- | --- |
| `segmentId` | Segment id from the input. Empty when the caller did not send one. |
| `ok` | `true` when the segment can stay as it is. |
| `action` | `none` or `request_ride`. `request_ride` tells the master to call the ride agent. This tool does not call it. |
| `reason` | Why the segment is fine, or why the master should call the ride agent. |

## Rules

`now` and `sunset` are compared as instants. A `Z` suffix and a numeric offset are the same clock. A time with no offset is read as UTC. The comparison is `now >= sunset`.

- `mode` `ride` returns `ok` true and `action` `none`. The traveler is already on a ride, including after sunset.
- `mode` `walk` and `now` before `sunset` returns `ok` true and `action` `none`.
- `mode` `walk` and `now` at or after `sunset` returns `ok` false and `action` `request_ride`. The master calls the ride agent. This tool does not.
- A missing or unreadable `now` or `sunset` on a walk returns `ok` false and `action` `none`.
- Any other `mode`, a partial payload, bad JSON, and any other input return a result and do not raise.

## Tests

From the repository root:

```bash
python3 -m unittest booking.assist.afterdark.test_afterdark
```
