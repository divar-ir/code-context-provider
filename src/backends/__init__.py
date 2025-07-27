"""Search backends for the MCP server."""

from .content_fetcher_factory import ContentFetcherFactory
from .content_fetcher_protocol import ContentFetcherProtocol
from .search_factory import SearchClientFactory
from .search_protocol import SearchClientProtocol

__all__ = [
    "ContentFetcherFactory",
    "ContentFetcherProtocol",
    "SearchClientFactory",
    "SearchClientProtocol",
]
