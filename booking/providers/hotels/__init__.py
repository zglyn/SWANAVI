"""Hotel booking tool for the Amazon Bedrock AgentCore runtime."""

from .book import book
from .tool import TOOL_SPEC, handler

__all__ = ["TOOL_SPEC", "book", "handler"]
