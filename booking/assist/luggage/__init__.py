"""Hotel luggage drop for the Amazon Bedrock AgentCore runtime.

The master agent calls ``luggage_drop`` when a flight lands before hotel
check-in. This package does not run that loop. See README.md.
"""

from .drop import luggage_drop
from .tool import AGENTCORE_TOOL, TOOL_SPEC, handler

__all__ = ["AGENTCORE_TOOL", "TOOL_SPEC", "handler", "luggage_drop"]
