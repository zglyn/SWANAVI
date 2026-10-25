"""Holiday closures for the Amazon Bedrock AgentCore runtime.

The master agent calls ``holiday_closure`` with one segment. A shift is a
signal for the master, the same idea as a weather hold. This package leaves
the segment where it is and does not run the master loop. A later integrator
wires the master. See README.md.
"""

from .holidays import holiday_closure
from .tool import AGENTCORE_TOOL, TOOL_SPEC, handler

__all__ = ["AGENTCORE_TOOL", "TOOL_SPEC", "handler", "holiday_closure"]
