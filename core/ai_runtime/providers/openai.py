"""
OpenAI Provider Implementation

Provides AI inference using OpenAI's API with streaming support.
"""

from __future__ import annotations

import json
from typing import Any, AsyncGenerator, Optional

import tiktoken
from openai import AsyncOpenAI
from openai.types.chat import (
    ChatCompletion,
    ChatCompletionMessage,
    ChatCompletionMessageFunctionToolCall,
    ChatCompletionMessageToolCall,
    ChatCompletionToolParam,
)
from openai.types.chat.chat_completion import Choice
from openai.types.chat.chat_completion_message_tool_call import Function

from core.ai_runtime.engine import (
    AIProvider,
    Message,
    MessageRole,
    ModelConfig,
    ModelProvider,
    ModelResponse,
    StreamChunk,
    TokenUsage,
    ToolCall,
)

import structlog

logger = structlog.get_logger(__name__)


class OpenAIProvider(AIProvider):
    """
    OpenAI API provider with support for GPT-4, GPT-3.5, and function calling.
    """

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
        )
        self._encoding_cache: dict[str, tiktoken.Encoding] = {}

    def _get_encoding(self, model: str) -> tiktoken.Encoding:
        """Get tokenizer encoding for model."""
        if model not in self._encoding_cache:
            try:
                encoding_name = tiktoken.encoding_for_model(model)
            except KeyError:
                encoding_name = "cl100k_base"
            self._encoding_cache[model] = tiktoken.get_encoding(encoding_name)
        return self._encoding_cache[model]

    def count_tokens(self, text: str, model: str) -> int:
        """Count tokens in text using tiktoken."""
        encoding = self._get_encoding(model)
        return len(encoding.encode(text))

    def _convert_messages(
        self, messages: list[Message]
    ) -> list[ChatCompletionMessage]:
        """Convert internal messages to OpenAI format."""
        result = []
        for msg in messages:
            content = msg.content
            if msg.tool_calls:
                # Format as tool calls
                tool_calls = []
                for tc in msg.tool_calls:
                    tool_calls.append(
                        Function(
                            name=tc["function"]["name"],
                            arguments=json.dumps(tc["function"]["arguments"]),
                        )
                    )
                result.append(
                    ChatCompletionMessage(
                        role=msg.role.value,
                        content=content,
                        tool_calls=tool_calls,
                    )
                )
            elif msg.tool_call_id:
                result.append(
                    ChatCompletionMessage(
                        role="tool",
                        content=content,
                        tool_call_id=msg.tool_call_id,
                    )
                )
            else:
                result.append(
                    ChatCompletionMessage(
                        role=msg.role.value,
                        content=content,
                        name=msg.name,
                    )
                )
        return result

    def _convert_tools(
        self, tools: list[dict[str, Any]]
    ) -> list[ChatCompletionToolParam]:
        """Convert tool definitions to OpenAI format."""
        result: list[ChatCompletionToolParam] = []
        for tool in tools:
            result.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool.get("description", ""),
                        "parameters": tool.get("parameters", {"type": "object"}),
                    },
                }
            )
        return result

    def _parse_tool_calls(
        self, choice: Choice
    ) -> tuple[Optional[str], list[ToolCall]]:
        """Parse tool calls from response choice."""
        content = choice.message.content or ""
        tool_calls = []

        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                if isinstance(tc, ChatCompletionMessageFunctionToolCall):
                    tool_calls.append(
                        ToolCall(
                            id=tc.id,
                            name=tc.function.name,
                            arguments=json.loads(tc.function.arguments),
                        )
                    )

        return content, tool_calls

    async def complete(
        self,
        messages: list[Message],
        config: ModelConfig,
        tools: Optional[list[dict[str, Any]]] = None,
    ) -> ModelResponse:
        """
        Generate a completion using OpenAI API.

        Args:
            messages: Conversation messages
            config: Model configuration
            tools: Optional tool definitions

        Returns:
            ModelResponse with content and metadata
        """
        logger.debug(
            "openai_complete_request",
            model=config.model,
            message_count=len(messages),
        )

        openai_messages = self._convert_messages(messages)
        request_kwargs: dict[str, Any] = {
            "model": config.model,
            "messages": [m.model_dump() for m in openai_messages],
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
        }

        if config.top_p is not None:
            request_kwargs["top_p"] = config.top_p
        if config.frequency_penalty != 0:
            request_kwargs["frequency_penalty"] = config.frequency_penalty
        if config.presence_penalty != 0:
            request_kwargs["presence_penalty"] = config.presence_penalty
        if config.stop:
            request_kwargs["stop"] = config.stop
        if config.seed is not None:
            request_kwargs["seed"] = config.seed
        if tools:
            request_kwargs["tools"] = self._convert_tools(tools)
            request_kwargs["tool_choice"] = "auto"

        try:
            response: ChatCompletion = await self.client.chat.completions.create(
                **request_kwargs
            )

            choice = response.choices[0]
            content, tool_calls = self._parse_tool_calls(choice)

            usage = TokenUsage(
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
                total_tokens=response.usage.total_tokens,
            )

            return ModelResponse(
                content=content,
                model=config.model,
                provider=ModelProvider.OPENAI,
                usage=usage,
                finish_reason=choice.finish_reason or "unknown",
                tool_calls=tool_calls,
                raw_response=response.model_dump(),
            )

        except Exception as e:
            logger.error("openai_request_failed", error=str(e))
            raise

    async def stream(
        self,
        messages: list[Message],
        config: ModelConfig,
        tools: Optional[list[dict[str, Any]]] = None,
    ) -> AsyncGenerator[StreamChunk, None]:
        """
        Generate a streaming completion using OpenAI API.

        Args:
            messages: Conversation messages
            config: Model configuration
            tools: Optional tool definitions

        Yields:
            StreamChunk objects as tokens are generated
        """
        openai_messages = self._convert_messages(messages)
        request_kwargs: dict[str, Any] = {
            "model": config.model,
            "messages": [m.model_dump() for m in openai_messages],
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "stream": True,
        }

        if config.top_p is not None:
            request_kwargs["top_p"] = config.top_p
        if config.frequency_penalty != 0:
            request_kwargs["frequency_penalty"] = config.frequency_penalty
        if config.presence_penalty != 0:
            request_kwargs["presence_penalty"] = config.presence_penalty
        if tools:
            request_kwargs["tools"] = self._convert_tools(tools)
            request_kwargs["tool_choice"] = "auto"

        full_content = ""
        current_tool_calls: dict[str, dict[str, Any]] = {}

        try:
            async with self.client.chat.completions.create(
                **request_kwargs
            ) as stream:
                async for chunk in stream:
                    if not chunk.choices:
                        continue

                    delta = chunk.choices[0].delta

                    # Handle content delta
                    if delta.content:
                        full_content += delta.content
                        yield StreamChunk(
                            content=full_content,
                            delta=delta.content,
                            is_final=False,
                        )

                    # Handle tool call deltas
                    if delta.tool_calls:
                        for tc_delta in delta.tool_calls:
                            if tc_delta.index not in current_tool_calls:
                                current_tool_calls[tc_delta.index] = {
                                    "id": "",
                                    "function": {"name": "", "arguments": ""},
                                }
                            
                            tc = current_tool_calls[tc_delta.index]
                            if tc_delta.id:
                                tc["id"] = tc_delta.id
                            if tc_delta.function:
                                if tc_delta.function.name:
                                    tc["function"]["name"] = tc_delta.function.name
                                if tc_delta.function.arguments:
                                    tc["function"]["arguments"] += (
                                        tc_delta.function.arguments
                                    )

                    # Handle finish
                    if chunk.choices[0].finish_reason:
                        # Finalize tool calls
                        tool_calls = []
                        for tc_data in current_tool_calls.values():
                            try:
                                args = json.loads(tc_data["function"]["arguments"])
                            except json.JSONDecodeError:
                                args = {}
                            tool_calls.append(
                                ToolCall(
                                    id=tc_data["id"],
                                    name=tc_data["function"]["name"],
                                    arguments=args,
                                )
                            )

                        yield StreamChunk(
                            content=full_content,
                            delta="",
                            is_final=True,
                            tool_call=tool_calls[0] if tool_calls else None,
                            finish_reason=chunk.choices[0].finish_reason,
                        )

        except Exception as e:
            logger.error("openai_stream_failed", error=str(e))
            raise
