import os
import pathlib
import uuid
from typing import List

from code_context_provider.core import PromptManager
from code_context_provider.core.limiters import TokenLimiter, ToolCallLimiter
from code_context_provider.servers.context.config import AgentConfig
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pydantic_ai.agent import Agent
from pydantic_ai.mcp import MCPServerStreamableHTTP
from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIModel, OpenAIModelSettings
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings

load_dotenv()


class QueryReformaterResult(BaseModel):
    suggested_queries: List[str] = Field(..., description="list of suggested queries")


class QueryReformater:
    def __init__(self, trace_id: str = None, max_tool_calls: int = None, max_tokens: int = None) -> None:
        self.config = AgentConfig()
        prompt_file_path = pathlib.Path(__file__).parent.parent.parent / "prompts" / "prompts.yaml"

        self._prompt_manager = PromptManager(
            file_path=prompt_file_path,
            section_path="agents.query_reformater",
        )
        self._mcp_context = None

        # Use provided values or fall back to config defaults
        max_tool_calls = max_tool_calls or self.config.default_max_tool_calls
        max_tokens = max_tokens or self.config.default_max_tokens

        self._tool_limiter = ToolCallLimiter(max_calls=max_tool_calls)
        self._token_limiter = TokenLimiter(max_tokens=max_tokens)
        self._max_tool_calls = max_tool_calls
        self._max_tokens = max_tokens

        if trace_id is None:
            trace_id = str(uuid.uuid4())

        headers = {"X-TRACE-ID": trace_id}

        model, model_settings = self._llm_model

        mcp_server = MCPServerStreamableHTTP(
            url=self.config.mcp_server_url,
            headers=headers,
            timeout=30,
        )

        self._mcp_server = self._tool_limiter.wrap_mcp_server(mcp_server)

        system_prompt = self._prompt_manager.render_prompt("system_prompt")
        system_prompt += (
            f"\n\nIMPORTANT RESOURCE LIMITS:\n"
            f"1. TOOL CALLS: You have a maximum of {max_tool_calls} tool calls available.\n"
            f"2. TOKENS: You have a maximum of {max_tokens} tokens available (including input and output).\n"
            f"3. When you receive a 'TOOL CALL LIMIT REACHED' or 'TOKEN LIMIT WARNING' message, "
            f"you MUST provide your final response immediately.\n"
            f"4. Plan your tool usage strategically to gather the most important information within these limits."
        )

        self._agent = Agent(
            name="query_reformater",
            model=model,
            model_settings=model_settings,
            output_type=QueryReformaterResult,
            system_prompt=system_prompt,
            instrument=self.config.langfuse_enabled,
            mcp_servers=[self._mcp_server],
        )

    async def __aenter__(self):
        self._mcp_context = self._agent.run_mcp_servers()
        await self._mcp_context.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._mcp_context:
            result = await self._mcp_context.__aexit__(exc_type, exc_val, exc_tb)
            return result

    async def run(self, question: str) -> QueryReformaterResult:
        self._tool_limiter.reset()

        result = await self._token_limiter.run_with_limit(
            self._agent, self._prompt_manager.render_prompt("user_prompt", question=question)
        )
        return result.output

    @property
    def _llm_model(self) -> tuple[Model, ModelSettings]:
        model_kwargs = self.config.get_model_kwargs("query_reformater")
        provider_kwargs = {}
        if "base_url" in model_kwargs:
            provider_kwargs["base_url"] = model_kwargs["base_url"]
        if "api_key" in model_kwargs:
            provider_kwargs["api_key"] = model_kwargs["api_key"]
        else:
            # Use default API key from environment if not provided
            provider_kwargs["api_key"] = os.getenv("OPENAI_API_KEY", "")

        model = OpenAIModel(
            model_name=self.config.query_reformater_model_name,
            provider=OpenAIProvider(**provider_kwargs) if provider_kwargs else None,
        )
        model_settings = OpenAIModelSettings(
            temperature=0.0,
            max_tokens=8192,
            timeout=120,
        )

        return model, model_settings


class CodeSnippetFinder:
    def __init__(self, trace_id: str = None, max_tool_calls: int = None, max_tokens: int = None) -> None:
        self.config = AgentConfig()
        prompt_file_path = pathlib.Path(__file__).parent.parent.parent / "prompts" / "prompts.yaml"
        self._prompt_manager = PromptManager(
            file_path=prompt_file_path,
            section_path="agents.code_snippet_finder",
        )
        self._mcp_context = None

        # Use provided values or fall back to config defaults
        max_tool_calls = max_tool_calls or self.config.default_max_tool_calls
        max_tokens = max_tokens or self.config.default_max_tokens

        self._tool_limiter = ToolCallLimiter(max_calls=max_tool_calls)
        self._token_limiter = TokenLimiter(max_tokens=max_tokens)
        self._max_tool_calls = max_tool_calls
        self._max_tokens = max_tokens

        if trace_id is None:
            trace_id = str(uuid.uuid4())

        headers = {"X-TRACE-ID": trace_id}

        model, model_settings = self._llm_model

        mcp_server = MCPServerStreamableHTTP(
            url=self.config.mcp_server_url,
            headers=headers,
            timeout=30,
        )

        self._mcp_server = self._tool_limiter.wrap_mcp_server(mcp_server)

        system_prompt = self._prompt_manager.render_prompt("system_prompt")
        system_prompt += (
            f"\n\nIMPORTANT RESOURCE LIMITS:\n"
            f"1. TOOL CALLS: You have a maximum of {max_tool_calls} tool calls available.\n"
            f"2. TOKENS: You have a maximum of {max_tokens} tokens available (including input and output).\n"
            f"3. When you receive a 'TOOL CALL LIMIT REACHED' or 'TOKEN LIMIT WARNING' message, "
            f"you MUST provide your final response immediately.\n"
            f"4. Plan your tool usage strategically to gather the most important information within these limits."
        )

        self._agent = Agent(
            name="code_snippet_finder",
            model=model,
            model_settings=model_settings,
            system_prompt=system_prompt,
            instrument=self.config.langfuse_enabled,
            retries=2,
            mcp_servers=[self._mcp_server],
        )

    async def __aenter__(self):
        self._mcp_context = self._agent.run_mcp_servers()
        await self._mcp_context.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._mcp_context:
            result = await self._mcp_context.__aexit__(exc_type, exc_val, exc_tb)
            return result

    async def run(self, question: str) -> str:
        self._tool_limiter.reset()

        result = await self._token_limiter.run_with_limit(
            self._agent, self._prompt_manager.render_prompt("user_prompt", question=question)
        )
        return result.output

    @property
    def _llm_model(self) -> tuple[Model, ModelSettings]:
        model_kwargs = self.config.get_model_kwargs("code_snippet_finder")
        provider_kwargs = {}
        if "base_url" in model_kwargs:
            provider_kwargs["base_url"] = model_kwargs["base_url"]
        if "api_key" in model_kwargs:
            provider_kwargs["api_key"] = model_kwargs["api_key"]
        else:
            # Use default API key from environment if not provided
            provider_kwargs["api_key"] = os.getenv("OPENAI_API_KEY", "")

        model = OpenAIModel(
            model_name=self.config.code_snippet_finder_model_name,
            provider=OpenAIProvider(**provider_kwargs) if provider_kwargs else None,
        )
        model_settings = OpenAIModelSettings(
            temperature=0.0,
            max_tokens=8192,
            timeout=120,
        )

        return model, model_settings
