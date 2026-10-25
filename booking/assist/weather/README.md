# Weather holds

Holds an outdoor stop when the forecast is bad. The master agent calls `check_weather` on the [Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-cli.html) runtime when a forecast signal arrives. A `shift` is handed to the late and early replan agents. The weather agent does not move segments.

Sandbox only. The tool reads `outdoor` and `condition` from the caller. It does not call a weather API, open the network, or call AWS. Replanning the day and the master loop stay with their own tools.

```python
from booking.assist.weather import AGENTCORE_TOOL, TOOL_SPEC, check_weather, handler

# TOOL_SPEC is the AgentCore tool definition (name, description, inputSchema).
# AGENTCORE_TOOL is the inline_function entry to pass on harness invoke.
# When the runtime returns a check_weather tool call, call handler(tool_input).
```

Tool name: `check_weather`.

## Input

| Field | Meaning |
| --- | --- |
| `segmentId` | Segment the forecast is about. |
| `outdoor` | Boolean. `false` skips the forecast. |
| `condition` | Forecast word supplied by the caller: `rain`, `storm`, `snow`, `clear`, or `cloudy`. |

## Output

```json
{
  "segmentId": "attraction-1",
  "ok": false,
  "action": "shift",
  "reason": "storm"
}
```

| Field | Meaning |
| --- | --- |
| `segmentId` | The segment from the input. Empty when it was missing. |
| `ok` | `true` when the segment can stay. |
| `action` | `none`, `shift`, or `swap_indoor`. This tool returns `none` or `shift`. It does not select `swap_indoor`. |
| `reason` | Why that action was chosen. |

## Rules

`outdoor` false: `ok` is true and `action` is `none`, including when `condition` is rain. `reason` is `indoor`.

`outdoor` true and `condition` is rain, storm, or snow: `ok` is false and `action` is `shift`. `reason` is that word. The master hands the shift to the late and early replan agents. This tool does not move the segment.

`outdoor` true and `condition` is clear or cloudy: `ok` is true and `action` is `none`. `reason` is that word.

Any other condition while `outdoor` is true: `ok` is false, `action` is `none`, and `reason` is `unknown_condition`.

Matching ignores case and surrounding spaces. `outdoor` must be a boolean. A missing boolean, an unreadable payload, or a non-string `segmentId` returns a result and does not raise. `reason` is `invalid_input` when `outdoor` is not a boolean.

## Tests

From the repository root:

```bash
python3 -m unittest booking.assist.weather.test_weather
```
