# Traveler notices

Builds one message for the traveler. The master agent calls `trip_notice` on the [Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-cli.html) runtime after a replan or a refused overcharge so the traveler gets one message. This package does not run that loop, does not book, does not replan, and does not send the message.

Sandbox only. The tool does not open the network or call AWS.

```python
from booking.notify import AGENTCORE_TOOL, TOOL_SPEC, handler, trip_notice

# TOOL_SPEC is the AgentCore tool definition (name, description, inputSchema).
# AGENTCORE_TOOL is the inline_function entry to pass on harness invoke.
# When the runtime returns a trip_notice tool call, call handler(tool_input).
```

Tool name: `trip_notice`.

## Input

| Field | Meaning |
| --- | --- |
| `tripId` | Trip id. Copied onto the result. This tool does not look it up. |
| `event` | `cancelled`, `ended_early`, `ended_late`, `booked`, or `over_capture_rejected`. |
| `notes` | Strings to include in the one message. An empty list is allowed. |
| `segmentId` | Segment the event is about. Empty when the event is not about one segment. |

`cancelled`, `ended_early`, and `ended_late` follow a replan. `over_capture_rejected` follows a refused overcharge. `booked` follows a booking. Every note goes in the same subject and the same body.

## Output

```json
{
  "tripId": "sample-kyoto",
  "subject": "Trip sample-kyoto: cancelled (temple) — marked temple removed | shifted garden earlier by 120 minutes",
  "body": "Traveler notice for trip sample-kyoto.\nEvent: cancelled.\nA segment on this trip was cancelled.\nSegment: temple.\nNotes:\nmarked temple removed\nshifted garden earlier by 120 minutes"
}
```

| Field | Meaning |
| --- | --- |
| `tripId` | From the input. Empty when the input has no id. |
| `subject` | Names the event and includes each note. |
| `body` | Names the event and includes each note. |

Empty `notes` still return a subject and a body. A partial input returns a result and does not raise. Nothing in this package delivers the message.

## Tests

From the repository root:

```bash
python3 -m unittest booking.notify.test_notice
```
