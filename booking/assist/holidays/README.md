# Holiday closures

Decides whether one segment is closed for a sandbox public holiday. The master agent calls `holiday_closure` on the [Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-cli.html) runtime. A `shift` is a signal for the master, the same idea as a weather hold. The master is the one that moves the segment. This package leaves the segment where it is.

Sandbox only. The holiday table below is the whole calendar. The tool reads the segment it is given. It does not look up a holiday API, open the network, or call AWS. A later integrator wires `holiday_closure` into the master. This package does not run that loop.

```python
from booking.assist.holidays import AGENTCORE_TOOL, TOOL_SPEC, handler, holiday_closure

# TOOL_SPEC is the AgentCore tool definition (name, description, inputSchema).
# AGENTCORE_TOOL is the inline_function entry to pass on harness invoke.
# When the runtime returns a holiday_closure tool call, call handler(tool_input).
```

Tool name: `holiday_closure`.

## Holiday table

| Country | Accepted names | Date | Holiday |
| --- | --- | --- | --- |
| Japan | `Japan`, `JP` | 2026-11-03 | Culture Day |
| Japan | `Japan`, `JP` | 2026-11-23 | Labor Thanksgiving Day |
| France | `France`, `FR` | 2026-11-11 | Armistice Day |
| United States | `United States`, `US`, `USA` | 2026-11-26 | Thanksgiving Day |

Country matching ignores case and surrounding spaces. `japan`, `Jp`, and ` JP ` are Japan. `united states`, `us`, and `USA` are the United States. Any other country is a normal day.

`2026-11-03` is a Tuesday, and so is `2026-11-10`. Culture Day is the Tuesday in the table. An ordinary Tuesday is open.

## Input

The input is one segment. Pass the object itself, a JSON object, or `{"segment": {...}}`.

| Field | Meaning |
| --- | --- |
| `segmentId` | Segment to check. Copied onto the result. |
| `kind` | `attraction`, `flight`, `hotel`, or `restaurant`. |
| `name` | Place name. Accepted and not used to choose the holiday. |
| `city` | City. Accepted and not used to choose the holiday. |
| `country` | Country token from the table above. |
| `date` | Calendar date as `YYYY-MM-DD`. |

## Output

```json
{
  "segmentId": "attraction-1",
  "closed": true,
  "holiday": "Culture Day",
  "action": "shift"
}
```

| Field | Meaning |
| --- | --- |
| `segmentId` | Segment id from the input. Empty when it was missing. |
| `closed` | `true` only for an attraction on a holiday in the table. |
| `holiday` | Holiday name when `country` and `date` match the table, including when a flight, hotel, or restaurant stays open. `null` on any other date. |
| `action` | `shift` or `none`. `shift` is a signal for the master. This tool leaves the segment on its date. |
| `error` | `invalid_segment` when the segment cannot be read. Omitted when the segment is readable. |

## Rules

An attraction whose country and date match the table: `closed` is true, `action` is `shift`, and `holiday` is that holiday's name.

A flight, hotel, or restaurant on that same holiday: `closed` is false and `action` is `none`. `holiday` is still that holiday's name, so the master can see why the segment was checked. The segment stays where it is.

Any other date, including an ordinary Tuesday: `closed` is false, `action` is `none`, and `holiday` is null.

A bad segment returns `error` `invalid_segment` and `action` `none`. `closed` is false and `holiday` is null. That covers a missing or blank field, a `kind` outside the four names above, a `date` that is not `YYYY-MM-DD`, a non-string `segmentId`, bad JSON, and any other unreadable payload. The call returns a result and does not raise. The input segment is left unchanged.

## Tests

From the repository root:

```bash
PYTHONPATH=. python3 -m unittest booking.assist.holidays.test_holidays
```

The tests cover a Culture Day attraction, a Culture Day hotel that stays open, and an ordinary Tuesday.
