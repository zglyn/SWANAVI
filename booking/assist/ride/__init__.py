"""Ride requests for the Amazon Bedrock AgentCore runtime.

The master calls ``request_ride`` when an attraction is about to end so the
car is there for the next stop. This package does not run that loop.
See README.md.
"""

from .ride import request_ride
from .tool import AGENTCORE_TOOL, TOOL_SPEC, handler

__all__ = ["AGENTCORE_TOOL", "TOOL_SPEC", "handler", "request_ride"]
