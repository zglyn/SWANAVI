"""Early trip watch for the Amazon Bedrock AgentCore runtime.

The master agent calls ``watch_trip`` first on every tick and acts on the
warnings. This package does not run that loop, move the plan, or request a
ride. See README.md.
"""

from .tool import AGENTCORE_TOOL, TOOL_SPEC, handler
from .watch import watch_trip

__all__ = ["AGENTCORE_TOOL", "TOOL_SPEC", "handler", "watch_trip"]
