"""Sandbox currency quotes for the Amazon Bedrock AgentCore runtime.

The master agent calls ``quote_fx`` before ``authorize_spend`` when the vendor
currency is not the trip currency. This package does not run that loop.
See README.md.
"""

from .quote import quote_fx
from .tool import AGENTCORE_TOOL, TOOL_SPEC, handler

__all__ = ["AGENTCORE_TOOL", "TOOL_SPEC", "handler", "quote_fx"]
