"""Amazon Bedrock AgentCore Runtime entrypoint for trip booking.

Local: ``python -m booking.orchestrator.main`` serves ``/invocations`` and
``/ping`` on port 8080. That path does not need AWS credentials unless
``AGENTCORE_MEMORY_ID`` or ``MEMORY_BOOKINGMEMORY_ID`` is set.

Deploy steps are in ``booking/README.md``. This module does not create AWS
resources.
"""

from __future__ import annotations

from bedrock_agentcore import BedrockAgentCoreApp

from booking.orchestrator.memory import memory_from_env
from booking.orchestrator.service import handle_payload
from booking.orchestrator.tools import register_booking_tools

app = BedrockAgentCoreApp()
register_booking_tools(app)


@app.entrypoint
def invoke(payload: dict, context: object | None = None) -> dict:
    """Book the finished plan by calling the tools registered on this runtime.

    ``context`` is the AgentCore request context. Booking state is keyed by
    ``tripId``. Providers are reached only from ``book_flight``, ``book_hotel``,
    and ``book_attraction``.
    """

    del context
    return handle_payload(payload, memory_from_env(), tools=app.booking_tools)


if __name__ == "__main__":
    app.run()
