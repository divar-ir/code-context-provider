import os

from dotenv import load_dotenv

load_dotenv()


class AgentConfig:
    def __init__(self) -> None:
        # Query reformater configuration
        self.query_reformater_model_name = os.getenv("QUERY_REFORMATER_MODEL_NAME")
        self.query_reformater_base_url = os.getenv("QUERY_REFORMATER_BASE_URL", "")
        self.query_reformater_api_key = os.getenv("QUERY_REFORMATER_API_KEY", "")

        # Code snippet finder configuration
        self.code_snippet_finder_model_name = os.getenv("CODE_SNIPPET_FINDER_MODEL_NAME")
        self.code_snippet_finder_base_url = os.getenv("CODE_SNIPPET_FINDER_BASE_URL", "")
        self.code_snippet_finder_api_key = os.getenv("CODE_SNIPPET_FINDER_API_KEY", "")

        # MCP server configuration
        self.mcp_server_url = os.getenv("MCP_SERVER_URL")

        # Default limits
        self.default_max_tool_calls = int(os.getenv("DEFAULT_MAX_TOOL_CALLS", "50"))
        self.default_max_tokens = int(os.getenv("DEFAULT_MAX_TOKENS", "190000"))

        # Langfuse configuration
        self.langfuse_enabled = os.getenv("LANGFUSE_ENABLED", "false").lower() == "true"

    def get_model_kwargs(self, model_type: str) -> dict:
        """Get model configuration kwargs for a specific model type.

        Args:
            model_type: One of 'query_reformater' or 'code_snippet_finder'

        Returns:
            Dictionary with model configuration including base_url and api_key if set
        """
        kwargs = {}

        if model_type == "query_reformater":
            if self.query_reformater_base_url:
                kwargs["base_url"] = self.query_reformater_base_url
            if self.query_reformater_api_key:
                kwargs["api_key"] = self.query_reformater_api_key
        elif model_type == "code_snippet_finder":
            if self.code_snippet_finder_base_url:
                kwargs["base_url"] = self.code_snippet_finder_base_url
            if self.code_snippet_finder_api_key:
                kwargs["api_key"] = self.code_snippet_finder_api_key

        return kwargs
