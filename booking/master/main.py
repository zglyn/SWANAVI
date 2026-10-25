"""Amazon Bedrock AgentCore runtime for the master booking loop.

Local: ``python -m booking.master.main`` serves ``/invocations`` and ``/ping``.
That path does not need AWS credentials or Amadeus keys.

The planner calls this entrypoint. The entrypoint calls book_flight,
book_hotel, book_attraction, the verify_*_email tools, trip_progress, and
one replan tool per event: replan_cancel, replan_early, or replan_late.
It also calls check_budget, authorize_spend, refund_booking, check_conflicts,
and trip_notice when those packages import. Assist tools, including
watch_trip at the start of every tick, are called the same way. The
concierge tools (flight_status, check_in_flight, refuse_dcc, pick_card,
cash_needed, holiday_closure, check_layover, etiquette_card, tax_refund,
rebook_segment, incidental_hold, and landing_data) are called from the same
loop. A missing package is recorded and the loop continues.
"""

from __future__ import annotations

from bedrock_agentcore import BedrockAgentCoreApp

from booking.master.service import handle_payload
from booking.master.tools import RUNTIME_TOOLS

app = BedrockAgentCoreApp()
app.booking_tools = dict(RUNTIME_TOOLS)


@app.entrypoint
def invoke(payload: dict, context: object | None = None) -> dict:
    """Run the master control loop for one finished trip plan."""

    del context
    return handle_payload(payload)


if __name__ == "__main__":
    app.run()
