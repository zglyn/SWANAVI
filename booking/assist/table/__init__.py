"""Dinner table hold for the Amazon Bedrock AgentCore runtime.

The master agent calls ``hold_table`` when the traveler is late to a meal so
the table is held. This package does not run that loop, does not call
OpenTable, and does not book a ride or track luggage. See README.md.
"""

from .hold import hold_table
from .tool import AGENTCORE_TOOL, TOOL_SPEC, handler

__all__ = ["AGENTCORE_TOOL", "TOOL_SPEC", "handler", "hold_table"]
