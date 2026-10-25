# Same-day segment rebook

Replaces one cancelled segment with the same kind on the same day. The master agent calls `rebook_segment` on the [Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-cli.html) runtime after that segment is cancelled. This package does not run that loop. A later integrator wires the master. This tool does not call the planner.

Sandbox only. The tool reads the segment it is given and writes a sandbox confirmation code. It does not call Amadeus, open the network, or call AWS. It does not build a new itinerary, change city, or add stops.

```python
from booking.assist.rebook import AGENTCORE_TOOL, TOOL_SPEC, handler, rebook_segment

# TOOL_SPEC is the AgentCore tool definition (name, description, inputSchema).
# AGENTCORE_TOOL is the inline_function entry to pass on harness invoke.
# When the runtime returns a rebook_segment tool call, call handler(tool_input).
```

Tool name: `rebook_segment`.

## Input

| Field | Meaning |
| --- | --- |
| `tripId` | Trip the segment belongs to. |
| `now` | ISO-8601 instant supplied by the caller, in UTC (`Z`). This tool does not read the wall clock. |
| `segment` | One flight, hotel, or attraction. Fields already used in this repo. |
| `travelers` | Party on the segment. Kept. |
| `cancelled` | `true` to replace the segment. `false` leaves it alone. |

Flight fields: `segmentId`, `kind`, `from`, `to`, `departDate`. `returnDate`, `cabin`, and `travelerIds` are copied when present.

Hotel fields: `segmentId`, `kind`, `city`, `checkIn`, `checkOut`. `rooms` and `guests` are copied when present.

Attraction fields: `segmentId`, `kind`, `name`, `city`, `date`, `time`. `partySize` is copied when present.

`price` is `{amount, currency}` when the segment has one.

## Output

```json
{
  "segmentId": "seg-fushimi-1",
  "changed": true,
  "reason": "rebooked",
  "replacement": {
    "segmentId": "seg-fushimi-1",
    "kind": "attraction",
    "name": "Fushimi Inari Taisha",
    "city": "Kyoto",
    "date": "2026-11-06",
    "time": "14:40",
    "partySize": 2,
    "status": "booked",
    "confirmationCode": "SANDBOX-RB-0123456789AB",
    "price": {"amount": "36.00", "currency": "USD"},
    "error": null
  },
  "notes": ["moved the start to 2026-11-06 14:40 UTC"]
}
```

| Field | Meaning |
| --- | --- |
| `segmentId` | Segment id from the input. Empty when it is not a string. |
| `changed` | `true` only when `cancelled` is `true` and a replacement was booked. |
| `reason` | `not_cancelled`, `rebooked`, or `unreadable`. |
| `replacement` | The same segment booked again, or `null` when nothing was booked. |
| `notes` | What the tool did. |

`replacement.status` is `booked`. `replacement.confirmationCode` starts with `SANDBOX-RB-`. `replacement.error` is `null`. `replacement.price` is the segment price when it has `amount` and `currency`, otherwise `null`.

## Rules

Same-day, same-kind replacement only. The replacement keeps `segmentId`, `kind`, the cities (`from`/`to` or `city`), and the party. It does not move the segment to another city.

`cancelled` false returns `changed` false, `replacement` null, and `reason` `not_cancelled`.

`cancelled` true books the same segment again.

The start is the instant the existing fields can name:

| Kind | Start |
| --- | --- |
| flight | `departDate` at 00:00 UTC |
| hotel | `checkIn` at 00:00 UTC |
| attraction | `date` plus `time` when `time` is present, otherwise `date` at 00:00 UTC |

A start that is still at or after `now` is kept. A start before `now` becomes `now` plus 30 minutes.

That new instant is written with the same calendar fields:

| Kind | What can change |
| --- | --- |
| flight | `departDate`. `returnDate` moves by the same number of days when `departDate` moves. |
| hotel | `checkIn`. `checkOut` moves by the same number of days, so the stay length stays. |
| attraction | `date` and `time` (`HH:MM`). |

A date-only field changes only when `now` plus 30 minutes falls on another UTC date. The city and the kind never change.

Clocks are UTC. A `Z` suffix and a numeric offset are the same instant. A timestamp with no offset is read as UTC. A date with no time is not a valid `now`.

A partial payload returns a result and does not raise. The input is not modified.

## Tests

From the repository root:

```bash
PYTHONPATH=. python3 -m unittest booking.assist.rebook.test_rebook
```
