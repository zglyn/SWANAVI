"""Errors raised by attraction providers. `book` turns them into status failed."""


class AttractionProviderError(Exception):
    """A provider failed. Callers of `book` receive this as a result, not an exception."""
