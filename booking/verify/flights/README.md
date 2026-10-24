# Flight confirmation email

Sandbox check that the email a traveler would receive after a flight books matches the segment that was just booked. Nothing is delivered. This package does not open a socket, read a mailbox, or call AWS.

The master agent calls `verify_flight_email` on the [Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/harness-tools.html) runtime after `book_flight`. Register the tool below and let the runtime call `handler`. `handler` calls `verify()`.

```python
from booking.verify.flights import AGENTCORE_TOOL, TOOL_SPEC, handler, sample_email, verify

# TOOL_SPEC is the AgentCore tool definition (name, description, inputSchema).
# AGENTCORE_TOOL is the inline_function entry to pass on harness invoke.
# When the runtime returns a verify_flight_email tool call, call handler(tool_input).
```

Tool name: `verify_flight_email`.

`sample_email(segment, confirmation_code, travelers, trip_id)` builds that email locally. It returns `from`, `to`, `subject`, `body`, and `receivedAt`. `from` and `to` are the sandbox sender and recipient. The sender is on `sandbox.swanavi.invalid`, which is not a real mailbox. The body includes the confirmation code, the route (`from` and `to`), the depart date, and the traveler names.

`verify(email, segment, confirmation_code, travelers)` returns `segmentId`, `kind` (`"flight"`), `verified`, and `reason`. `verified` is true only when every field below appears in the subject or the body. A wrong confirmation code or a missing depart date leaves `verified` false. A bad email does not raise.

`handler` accepts the same fields. `confirmationCode` is accepted as an alias of `confirmation_code`, so the code on a `book_flight` result can be passed through.

## Fields that are checked

Each value has to show up as its own token in `email["subject"]` or `email["body"]`. A shorter code that is only a prefix of the real code does not count. The email headers `from` and `to` are not treated as the route.

| Field | Where it comes from | What must appear |
|---|---|---|
| Confirmation code | `confirmation_code` | The code, such as `SANDBOX-FLIGHT-001` |
| Route | `segment["from"]` and `segment["to"]` | Both airports, such as `JFK` and `KIX` |
| Depart date | `segment["departDate"]` | That date string, such as `2026-11-02` |
| Traveler names | `travelers` | Each full name |

A traveler name is `name`, or `givenName` and `familyName` together. When the segment has `travelerIds`, only those travelers are required. A traveler id on the segment that was not provided is not verified.

## Tests

From the repo root:

```bash
python3 -m unittest booking.verify.flights.test_verify
```
