import argparse
import asyncio
import json
import os
import pathlib
import uuid

from pydantic import BaseModel, Field
from pydantic_ai.agent import Agent
from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIModel, OpenAIModelSettings
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings

from core import PromptManager
from evaluator.config import JudgeConfig
from servers.context.agent import CodeSnippetFinder


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


async def async_main():
    question = input("Enter a question: ")

    async with CodeSnippetFinder(trace_id=str(uuid.uuid4())) as agent:
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
