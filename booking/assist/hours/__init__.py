"""Opening hours for the Amazon Bedrock AgentCore runtime.

The master agent calls ``check_hours`` after a replan moves a stop. This
package does not run that loop. See README.md.
"""

from .hours import check_hours
from .tool import AGENTCORE_TOOL, TOOL_SPEC, handler

__all__ = ["AGENTCORE_TOOL", "TOOL_SPEC", "check_hours", "handler"]
