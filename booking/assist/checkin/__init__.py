"""Sandbox flight check-in for the Amazon Bedrock AgentCore runtime.

The master agent calls ``check_in_flight``. This package does not run that
loop. A later integrator wires the master loop. See README.md.
"""

from .checkin import check_in_flight
from .tool import AGENTCORE_TOOL, TOOL_SPEC, handler

__all__ = ["AGENTCORE_TOOL", "TOOL_SPEC", "check_in_flight", "handler"]
