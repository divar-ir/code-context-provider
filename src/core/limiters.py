import asyncio
from functools import wraps
from typing import Any

from pydantic_ai.agent import Agent, AgentRunResult
from pydantic_ai.mcp import MCPServerStreamableHTTP
from pydantic_ai.messages import ModelRequest, RetryPromptPart
from pydantic_graph import End


class ToolCallLimiter:
    def __init__(self, max_calls: int = 10):
        if not isinstance(max_calls, int) or max_calls <= 0:
            raise ValueError("max_calls must be a positive integer")
        self.max_calls = max_calls
        self.call_count = 0
        self._original_call_tool = None
        self._limit_reached = False

    def reset(self):
        self.call_count = 0
        self._limit_reached = False

    def wrap_mcp_server(self, mcp_server: MCPServerStreamableHTTP) -> MCPServerStreamableHTTP:
        self._original_call_tool = mcp_server.call_tool

        @wraps(self._original_call_tool)
        async def wrapped_call_tool(
            tool_name: str,
            arguments: dict[str, Any],
            metadata: dict[str, Any] | None = None,
        ):
            self.call_count += 1

            if self.call_count > self.max_calls:
                self._limit_reached = True
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                f"TOOL CALL LIMIT REACHED: You have made {self.max_calls} tool calls, "
                                "which is the maximum allowed. Please provide your final response based on "
                                "the information you have gathered so far. No more tool calls will be processed."
                            ),
                        }
                    ],
                    "isError": False,
                }

            if self.call_count == self.max_calls:
                result = await self._original_call_tool(tool_name, arguments, metadata)
                if isinstance(result, dict) and "content" in result and isinstance(result["content"], list):
                    result["content"].append(
                        {
                            "type": "text",
                            "text": (
                                f"\n\nWARNING: This is your last tool call ({self.max_calls}/{self.max_calls}). "
                                "After this, you must provide your final response."
                            ),
                        }
                    )
                return result

            return await self._original_call_tool(tool_name, arguments, metadata)

        mcp_server.call_tool = wrapped_call_tool
        return mcp_server


class TokenLimiter:
    def __init__(self, max_tokens: int = 190000, buffer_tokens: int = 5000):
        """
        Args:
            max_tokens: Maximum total tokens allowed
            buffer_tokens: Buffer to leave for final response generation
        """
        self.max_tokens = max_tokens
        self.buffer_tokens = buffer_tokens
        self.effective_limit = max_tokens - buffer_tokens

    async def run_with_limit(self, agent: Agent, *args, **kwargs) -> AgentRunResult:
        """Run the agent with token limiting"""
        async with agent.iter(*args, **kwargs) as agent_run:
            limit_reached = False

            async for node in agent_run:
                if not isinstance(node, End):
                    current_usage = agent_run.usage()
                    total_tokens = (
                        current_usage.total_tokens if current_usage and current_usage.total_tokens is not None else 0
                    )

                    if total_tokens >= self.effective_limit and not limit_reached:
                        limit_reached = True

                        limit_message = ModelRequest(
                            parts=[
                                RetryPromptPart(
                                    content=(
                                        f"TOKEN LIMIT WARNING: You have used {total_tokens} tokens out of a maximum {self.max_tokens}. "
                                        f"You are approaching the token limit. Please provide your final response immediately "
                                        f"based on the information you have gathered so far. Keep your response concise to stay "
                                        f"within the remaining {self.max_tokens - total_tokens} tokens."
                                    )
                                )
                            ]
                        )

                        try:
                            await agent_run.send(limit_message)
                        except Exception:
                            pass

                        continue

            return agent_run.result

    def run_sync_with_limit(self, agent: Agent, *args, **kwargs) -> AgentRunResult:
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(self.run_with_limit(agent, *args, **kwargs))
