from backends.content_fetcher_protocol import ContentFetcherProtocol
from backends.sourcegraph.fetcher import SourcegraphContentFetcher
from backends.zoekt.fetcher import ZoektContentFetcher


class ContentFetcherFactory:
    """Factory class for creating content fetcher instances based on configuration."""

    @staticmethod
    def create_fetcher(backend: str, **kwargs) -> ContentFetcherProtocol:
        """Create a content fetcher based on the specified backend.

        Args:
            backend: Backend type ('zoekt' or 'sourcegraph')
            **kwargs: Additional arguments passed to the fetcher constructor

        Returns:
            ContentFetcherProtocol: Configured content fetcher instance

        Raises:
            ValueError: If backend is not supported or required config is missing
        """
        if backend == "sourcegraph":
            return ContentFetcherFactory._create_sourcegraph_fetcher(**kwargs)
        elif backend == "zoekt":
            return ContentFetcherFactory._create_zoekt_fetcher(**kwargs)
        else:
            raise ValueError(f"Unsupported content fetcher backend: {backend}")

    @staticmethod
    def _create_sourcegraph_fetcher(**kwargs) -> SourcegraphContentFetcher:
        """Create and configure a Sourcegraph content fetcher.

        Args:
            **kwargs: Must include 'endpoint', may include 'token'

        Returns:
            SourcegraphContentFetcher: Configured Sourcegraph content fetcher

        Raises:
            ValueError: If required configuration is missing
        """
        endpoint = kwargs.get("endpoint")
        token = kwargs.get("token", "")

        if not endpoint:
            raise ValueError("Sourcegraph backend requires endpoint parameter")

        return SourcegraphContentFetcher(endpoint=endpoint, token=token)

    @staticmethod
    def _create_zoekt_fetcher(**kwargs) -> ZoektContentFetcher:
        """Create and configure a Zoekt content fetcher.

        Args:
            **kwargs: Must include 'zoekt_url'

        Returns:
            ZoektContentFetcher: Configured Zoekt content fetcher
        """
        zoekt_url = kwargs.get("zoekt_url")

        if not zoekt_url:
            raise ValueError("Zoekt backend requires zoekt_url parameter")

        return ZoektContentFetcher(zoekt_url=zoekt_url)
