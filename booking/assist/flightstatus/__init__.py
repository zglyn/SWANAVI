"""Flight status for the Amazon Bedrock AgentCore runtime.

The master agent calls ``flight_status`` for a flight segment on a tick,
before it replans. This package does not run that loop and does not change
the segment. A later integrator wires the call into the master loop. See
README.md.
"""

from .status import flight_status
from .tool import AGENTCORE_TOOL, TOOL_SPEC, handler

__all__ = ["AGENTCORE_TOOL", "TOOL_SPEC", "flight_status", "handler"]
