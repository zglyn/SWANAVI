"""Etiquette card for the Amazon Bedrock AgentCore runtime.

The master agent calls ``etiquette_card`` before a stop. This package returns
fixed sandbox phrases. It does not give medical, legal, or safety advice, it
is not a map, and it does not run the master loop. A later integrator wires
the master. See README.md.
"""

from .card import etiquette_card
from .tool import AGENTCORE_TOOL, TOOL_SPEC, handler

__all__ = ["AGENTCORE_TOOL", "TOOL_SPEC", "etiquette_card", "handler"]
