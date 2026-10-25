"""Traveler notices for the Amazon Bedrock AgentCore runtime.

The master agent calls ``trip_notice`` after a replan or a refused overcharge
so the traveler gets one message. This package does not run that loop and
does not deliver the message. See README.md.
"""

from .notice import trip_notice
from .tool import AGENTCORE_TOOL, TOOL_SPEC, handler

__all__ = ["AGENTCORE_TOOL", "TOOL_SPEC", "handler", "trip_notice"]
