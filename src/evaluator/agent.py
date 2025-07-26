import argparse
import asyncio
import json
import os
import pathlib
import uuid

from code_context_provider.core import PromptManager
from code_context_provider.evaluator.config import JudgeConfig
from code_context_provider.servers.context.agent import CodeSnippetFinder
from pydantic import BaseModel, Field
from pydantic_ai.agent import Agent
from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIModel, OpenAIModelSettings
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings


class CodeSnippetResult(BaseModel):
    code: str = Field(..., description="sample code snippet")
    language: str = Field(..., description="language of the code snippet")
    description: str = Field(..., description="description of the code snippet")


class CodeAgentTypeParser:
    def __init__(self, trace_id: str = None) -> None:
        self.config = JudgeConfig()
        prompt_file_path = pathlib.Path(__file__).parent.parent / "prompts" / "prompts.yaml"
        self._prompt_manager = PromptManager(
            file_path=prompt_file_path,
            section_path="agents.code_agent_type_parser",
        )

        if trace_id is None:
            trace_id = str(uuid.uuid4())

        model, model_settings = self._llm_model
        self._agent = Agent(
            name="code_agent_type_parser",
            model=model,
            model_settings=model_settings,
            system_prompt=self._prompt_manager.render_prompt("system_prompt"),
            output_type=CodeSnippetResult,
            instrument=self.config.langfuse_enabled,
        )

    async def run(self, user_input: str) -> CodeSnippetResult:
        result = await self._agent.run(self._prompt_manager.render_prompt("user_prompt", user_input=user_input))
        return result.output

    @property
    def _llm_model(self) -> tuple[Model, ModelSettings]:
        model_kwargs = self.config.get_model_kwargs("code_agent_type_parser")
        provider_kwargs = {}
        if "base_url" in model_kwargs:
            provider_kwargs["base_url"] = model_kwargs["base_url"]
        if "api_key" in model_kwargs:
            provider_kwargs["api_key"] = model_kwargs["api_key"]
        else:
            # Use default API key from environment if not provided
            provider_kwargs["api_key"] = os.getenv("OPENAI_API_KEY", "")

        model = OpenAIModel(
            model_name=self.config.code_agent_type_parser_model_name,
            provider=OpenAIProvider(**provider_kwargs) if provider_kwargs else None,
        )
        model_settings = OpenAIModelSettings(
            temperature=0.0,
            max_tokens=8128,
            timeout=60,
        )
        return model, model_settings


async def main():
    parser = argparse.ArgumentParser(description="Code Snippet Finder")
    parser.add_argument("-q", type=str, help="Question to ask the agent")
    parser.add_argument("--trace-id", type=str, help="Trace ID for logging")
    args = parser.parse_args()

    if args.q:
        question = args.q
    else:
        question = input("Enter a question: ")

    async with CodeSnippetFinder(trace_id=args.trace_id) as agent:
        result = await agent.run(question)

    print(f"{'-' * 10}\n{result}\n {'-' * 10}\n")

    with open("question.json", "w") as f:
        json.dump(
            {
                "input": {
                    "question": question,
                },
                "answer": result,
            },
            f,
            indent=2,
            ensure_ascii=True,
        )


def cli_main():
    """CLI entry point wrapper for the async main function."""
    asyncio.run(main())


if __name__ == "__main__":
    cli_main()
