"""Sandbox landing data for the Amazon Bedrock AgentCore runtime.

The master agent calls ``landing_data`` so the phone has data before a ride
is requested. This package does not run that loop and does not buy a plan.
A later integrator wires the master. See README.md.
"""

from .landing import landing_data
from .tool import AGENTCORE_TOOL, TOOL_SPEC, handler

__all__ = ["AGENTCORE_TOOL", "TOOL_SPEC", "handler", "landing_data"]
