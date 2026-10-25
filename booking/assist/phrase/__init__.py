"""Driver phrase card for the Amazon Bedrock AgentCore runtime.

The master agent calls ``phrase_card`` when it requests a ride. This package
does not run that loop. Place, address, and arrival are copied as given.
See README.md.
"""

from .phrase import phrase_card
from .tool import AGENTCORE_TOOL, TOOL_SPEC, handler

__all__ = ["AGENTCORE_TOOL", "TOOL_SPEC", "handler", "phrase_card"]
