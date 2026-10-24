"""Weather holds for the Amazon Bedrock AgentCore runtime.

The master agent calls ``check_weather`` when a forecast signal arrives.
A shift is handed to the late and early replan agents. This package does
not move segments and does not run the master loop. See README.md.
"""

from .tool import AGENTCORE_TOOL, TOOL_SPEC, handler
from .weather import check_weather

__all__ = ["AGENTCORE_TOOL", "TOOL_SPEC", "check_weather", "handler"]
