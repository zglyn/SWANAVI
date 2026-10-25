"""Trip progress for the Amazon Bedrock AgentCore runtime.

The master agent calls ``trip_progress`` inside its loop. This package does not
run that loop. See README.md.
"""

from .progress import trip_progress
from .tool import AGENTCORE_TOOL, TOOL_SPEC, handler

__all__ = ["AGENTCORE_TOOL", "TOOL_SPEC", "handler", "trip_progress"]
