import os

from dotenv import load_dotenv

load_dotenv()


class JudgeConfig:
    def __init__(self) -> None:
        # Code snippet finder configuration
        self.code_snippet_finder_model_name = os.getenv("CODE_SNIPPET_FINDER_MODEL_NAME", "gpt-4o-mini")

        # Code agent type parser configuration
        self.code_agent_type_parser_model_name = os.getenv("CODE_AGENT_TYPE_PARSER_MODEL_NAME", "gpt-4o-mini")
        self.code_agent_type_parser_base_url = os.getenv("CODE_AGENT_TYPE_PARSER_BASE_URL", "")
        self.code_agent_type_parser_api_key = os.getenv("CODE_AGENT_TYPE_PARSER_API_KEY", "")

        # LLM judge configuration
        self.llm_judge_model_name = os.getenv("LLM_JUDGE_V2_MODEL_NAME", "gpt-4o-mini")
        self.llm_judge_base_url = os.getenv("LLM_JUDGE_V2_BASE_URL", "")
        self.llm_judge_api_key = os.getenv("LLM_JUDGE_V2_API_KEY", "")

        # Langfuse configuration
        self.langfuse_enabled = os.getenv("LANGFUSE_ENABLED", "false").lower() == "true"
        if self.langfuse_enabled:
            self.langfuse_public_key = self._get_required_env("LANGFUSE_PUBLIC_KEY")
            self.langfuse_secret_key = self._get_required_env("LANGFUSE_SECRET_KEY")
            self.langfuse_host = self._get_required_env("LANGFUSE_HOST")
        else:
            self.langfuse_public_key = ""
            self.langfuse_secret_key = ""
            self.langfuse_host = ""
        
        # Evaluation configuration
        self.langfuse_dataset_name = os.getenv("LANGFUSE_DATASET_NAME", "code-search-mcp-agentic-v2")

    @staticmethod
    def _get_required_env(key: str) -> str:
        """Get required environment variable or raise descriptive error."""
        value = os.getenv(key)
        if not value:
            raise ValueError(f"Required environment variable {key} is not set")
        return value

    def get_model_kwargs(self, model_type: str) -> dict:
        """Get model configuration kwargs for a specific model type.

        Args:
            model_type: One of 'code_agent_type_parser' or 'llm_judge'

        Returns:
            Dictionary with model configuration including base_url and api_key if set
        """
        kwargs = {}

        if model_type == "code_agent_type_parser":
            if self.code_agent_type_parser_base_url:
                kwargs["base_url"] = self.code_agent_type_parser_base_url
            if self.code_agent_type_parser_api_key:
                kwargs["api_key"] = self.code_agent_type_parser_api_key
        elif model_type == "llm_judge":
            if self.llm_judge_base_url:
                kwargs["base_url"] = self.llm_judge_base_url
            if self.llm_judge_api_key:
                kwargs["api_key"] = self.llm_judge_api_key

        return kwargs
