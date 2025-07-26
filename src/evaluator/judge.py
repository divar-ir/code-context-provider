import os
import pathlib
from typing import List, Optional

from code_context_provider.core import PromptManager
from code_context_provider.evaluator.agent import CodeSnippetResult
from code_context_provider.evaluator.config import JudgeConfig
from pydantic import BaseModel, Field
from pydantic_ai.agent import Agent
from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIModel, OpenAIModelSettings
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings


class EvaluationResult(BaseModel):
    issues: Optional[List[str]] = Field(default=[], description="array of issues with the solution, (empty if none)")
    strengths: Optional[List[str]] = Field(default=[], description="array of positive aspects")
    suggestions: Optional[List[str]] = Field(default=[], description="array of improvements that could be made")
    explanation: str = Field(
        ...,
        description="detailed reason why expected answer is (similar or not) to actual answer",
    )
    is_pass: bool = Field(..., description="Pass or Fail")


class LLMJudge:
    def __init__(self) -> None:
        self.config = JudgeConfig()
        prompt_file_path = pathlib.Path(__file__).parent.parent / "prompts" / "prompts.yaml"
        self._prompt_manager = PromptManager(
            file_path=prompt_file_path,
            section_path="agents.evaluate",
        )

        model, model_settings = self._llm_model
        self._agent = Agent(
            name="code_search_llm_judge_v2",
            model=model,
            model_settings=model_settings,
            output_type=EvaluationResult,
            system_prompt=self._prompt_manager.render_prompt("system_prompt"),
            instrument=self.config.langfuse_enabled,
        )

    async def run(
        self,
        question: str,
        expected_answer: CodeSnippetResult,
        actual_answer: CodeSnippetResult,
    ) -> EvaluationResult:
        result = await self._agent.run(
            self._prompt_manager.render_prompt(
                "user_prompt",
                question=question,
                expected_answer=self._format_answer(expected_answer),
                actual_answer=self._format_answer(actual_answer),
            )
        )

        return result.output

    def _format_answer(self, answer: CodeSnippetResult) -> str:
        result = ""
        result += f"code: \n```{answer.code}```\n"
        result += f"language: ```{answer.language}```\n"
        result += f"description: ```{answer.description}```\n"

        return result

    @property
    def _llm_model(self) -> tuple[Model, ModelSettings]:
        model_kwargs = self.config.get_model_kwargs("llm_judge")
        provider_kwargs = {}
        if "base_url" in model_kwargs:
            provider_kwargs["base_url"] = model_kwargs["base_url"]
        if "api_key" in model_kwargs:
            provider_kwargs["api_key"] = model_kwargs["api_key"]
        else:
            # Use default API key from environment if not provided
            provider_kwargs["api_key"] = os.getenv("OPENAI_API_KEY", "")

        model = OpenAIModel(
            model_name=self.config.llm_judge_model_name,
            provider=OpenAIProvider(**provider_kwargs) if provider_kwargs else None,
        )
        model_settings = OpenAIModelSettings(
            temperature=0.0,
            max_tokens=8192,
            timeout=180,
        )

        return model, model_settings
