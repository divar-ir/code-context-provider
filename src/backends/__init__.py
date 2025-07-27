"""Search backends for the MCP server."""

from .content_fetcher import AbstractContentFetcher, ContentFetcherFactory
from .search import AbstractSearchClient, SearchClientFactory

__all__ = [
    "ContentFetcherFactory",
    "AbstractContentFetcher",
    "SearchClientFactory",
    "AbstractSearchClient",
]
