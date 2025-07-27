from backends.search_protocol import SearchClientProtocol
from backends.sourcegraph import SourcegraphClient
from backends.zoekt import Client as ZoektClient


class SearchClientFactory:
    """Factory class for creating search client instances based on configuration."""

    @staticmethod
    def create_client(backend: str, **kwargs) -> SearchClientProtocol:
        """Create a search client based on the specified backend.

        Args:
            backend: Backend type ('zoekt' or 'sourcegraph')
            **kwargs: Additional arguments passed to the client constructor

        Returns:
            SearchClientProtocol: Configured search client instance

        Raises:
            ValueError: If backend is not supported or required config is missing
        """
        if backend == "sourcegraph":
            return SearchClientFactory._create_sourcegraph_client(**kwargs)
        elif backend == "zoekt":
            return SearchClientFactory._create_zoekt_client(**kwargs)
        else:
            raise ValueError(f"Unsupported search backend: {backend}")

    @staticmethod
    def _create_sourcegraph_client(**kwargs) -> SourcegraphClient:
        """Create and configure a Sourcegraph client.

        Args:
            **kwargs: Must include 'endpoint', may include 'token'

        Returns:
            SourcegraphClient: Configured Sourcegraph client

        Raises:
            ValueError: If required configuration is missing
        """
        endpoint = kwargs.get("endpoint")
        token = kwargs.get("token", "")

        if not endpoint:
            raise ValueError("Sourcegraph backend requires endpoint parameter")

        return SourcegraphClient(
            endpoint=endpoint,
            token=token,
            max_line_length=kwargs.get("max_line_length", 300),
            max_output_length=kwargs.get("max_output_length", 100000),
        )

    @staticmethod
    def _create_zoekt_client(**kwargs) -> ZoektClient:
        """Create and configure a Zoekt client.

        Args:
            **kwargs: Must include 'base_url'

        Returns:
            ZoektClient: Configured Zoekt client
        """
        base_url = kwargs.get("base_url")

        if not base_url:
            raise ValueError("Zoekt backend requires base_url parameter")

        return ZoektClient(
            base_url=base_url,
            max_line_length=kwargs.get("max_line_length", 300),
            max_output_length=kwargs.get("max_output_length", 100000),
        )
