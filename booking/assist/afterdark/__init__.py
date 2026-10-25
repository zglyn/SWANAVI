"""After-dark ride check for the Amazon Bedrock AgentCore runtime.

The master agent calls ``after_dark`` on Bedrock AgentCore. When the action
is ``request_ride``, the master calls the ride agent. This package does not
request the ride and does not run that loop. See README.md.
"""

from .afterdark import after_dark
from .tool import AGENTCORE_TOOL, TOOL_SPEC, handler

__all__ = ["AGENTCORE_TOOL", "TOOL_SPEC", "after_dark", "handler"]
