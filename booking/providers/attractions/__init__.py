"""Attraction-ticket booking for the Amazon Bedrock AgentCore runtime.

See README.md. The supported invoke path is the ``book_attraction`` tool.
"""

from .book import book
from .tool import BOOK_ATTRACTION_TOOL, book_attraction

__all__ = ["BOOK_ATTRACTION_TOOL", "book", "book_attraction"]
