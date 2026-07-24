"""
Anthropic Provider Implementation

Provides AI inference using Anthropic's Claude API with streaming support.
"""

from __future__ import annotations

import json
from typing import Any, AsyncGenerator, Optional

import anthropic
from anthropic import AsyncAnthropic
from anthropic.types import Message as AnthropicMessage
from anthropic.types import ContentBlock, Message, TextBlock, ToolUseBlock
from anthropic.types.message import Message as ClaudeMessage

from core.ai_runtime.engine import (
    AIProvider,
    Message as InternalMessage,
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


# Anthropic supported models
CLAUDE_MODELS = {
    "claude-3-opus-20240229": {"max_tokens": 4096},
    "claude-3-sonnet-20240229": {"max_tokens": 4096},
    "claude-3-haiku-20240307": {"max_tokens": 4096},
    "claude-3-5-sonnet-20240620": {"max_tokens": 8192},
    "claude-3-5-haiku-20241022": {"max_tokens": 8192},
}


class AnthropicProvider(AIProvider):
    """
    Anthropic API provider with support for Claude models and tool use.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.client = AsyncAnthropic(api_key=api_key)
        self._encoding_cache: dict[str, Any] = {}

    def count_tokens(self, text: str, model: str) -> int:
        """Count tokens using Anthropic's counting method."""
        # Simple approximation: ~4 chars per token for Claude
        return len(text) // 4

    def _convert_messages(
        self, messages: list[InternalMessage]
    ) -> tuple[Optional[str], list[dict[str, Any]]]:
        """Convert internal messages to Anthropic format.
        
        Returns:
            Tuple of (system_prompt, formatted_messages)
        """
        system_prompt = None
        formatted_messages = []

        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                system_prompt = msg.content
            elif msg.role == MessageRole.USER:
                formatted_messages.append({
                    "role": "user",
                    "content": msg.content,
                })
            elif msg.role == MessageRole.ASSISTANT:
                content_parts = []
                
                if msg.content:
                    content_parts.append({"type": "text", "text": msg.content})
                
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        content_parts.append({
                            "type": "tool_use",
                            "id": tc.id,
                            "name": tc.name,
                            "input": tc.arguments,
                        })
                
                formatted_messages.append({
                    "role": "assistant",
                    "content": content_parts or msg.content,
                })
            elif msg.role == MessageRole.TOOL:
                formatted_messages.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": msg.tool_call_id,
                            "content": msg.content,
                        }
                    ],
                })

        return system_prompt, formatted_messages

    def _convert_tools(
        self, tools: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Convert tool definitions to Anthropic format."""
        result = []
        for tool in tools:
            result.append({
                "name": tool["name"],
                "description": tool.get("description", ""),
                "input_schema": tool.get("parameters", {"type": "object"}),
            })
        return result

    async def complete(
        self,
        messages: list[InternalMessage],
        config: ModelConfig,
        tools: Optional[list[dict[str, Any]]] = None,
    ) -> ModelResponse:
        """
        Generate a completion using Anthropic API.

        Args:
            messages: Conversation messages
            config: Model configuration
            tools: Optional tool definitions

        Returns:
            ModelResponse with content and metadata
        """
        logger.debug(
            "anthropic_complete_request",
            model=config.model,
            message_count=len(messages),
        )

        system_prompt, formatted_messages = self._convert_messages(messages)
        
        request_kwargs: dict[str, Any] = {
            "model": config.model,
            "messages": formatted_messages,
            "max_tokens": config.max_tokens,
        }

        if system_prompt:
            request_kwargs["system"] = system_prompt
        
        if config.temperature != 0.7:  # Anthropic default
            request_kwargs["temperature"] = config.temperature
        
        if config.top_p is not None:
            request_kwargs["top_p"] = config.top_p
        
        if config.stop:
            request_kwargs["stop_sequences"] = config.stop
        
        if tools:
            request_kwargs["tools"] = self._convert_tools(tools)

        try:
            response: ClaudeMessage = await self.client.messages.create(
                **request_kwargs
            )

            # Extract content and tool calls
            content = ""
            tool_calls = []

            for block in response.content:
                if isinstance(block, TextBlock):
                    content += block.text
                elif isinstance(block, ToolUseBlock):
                    tool_calls.append(
                        ToolCall(
                            id=block.id,
                            name=block.name,
                            arguments=block.input,
                        )
                    )

            usage = TokenUsage(
                prompt_tokens=response.usage.input_tokens,
                completion_tokens=response.usage.output_tokens,
                total_tokens=response.usage.input_tokens + response.usage.output_tokens,
            )

            return ModelResponse(
                content=content,
                model=config.model,
                provider=ModelProvider.ANTHROPIC,
                usage=usage,
                finish_reason="stop_sequence" if response.stop_reason else "unknown",
                tool_calls=tool_calls,
                raw_response=response.model_dump(),
            )

        except Exception as e:
            logger.error("anthropic_request_failed", error=str(e))
            raise

    async def stream(
        self,
        messages: list[InternalMessage],
        config: ModelConfig,
        tools: Optional[list[dict[str, Any]]] = None,
    ) -> AsyncGenerator[StreamChunk, None]:
        """
        Generate a streaming completion using Anthropic API.

        Args:
            messages: Conversation messages
            config: Model configuration
            tools: Optional tool definitions

        Yields:
            StreamChunk objects as tokens are generated
        """
        system_prompt, formatted_messages = self._convert_messages(messages)
        
        request_kwargs: dict[str, Any] = {
            "model": config.model,
            "messages": formatted_messages,
            "max_tokens": config.max_tokens,
            "stream": True,
        }

        if system_prompt:
            request_kwargs["system"] = system_prompt
        
        if config.temperature != 0.7:
            request_kwargs["temperature"] = config.temperature
        
        if config.top_p is not None:
            request_kwargs["top_p"] = config.top_p
        
        if config.stop:
            request_kwargs["stop_sequences"] = config.stop
        
        if tools:
            request_kwargs["tools"] = self._convert_tools(tools)

        full_content = ""
        current_tool_use: Optional[dict[str, Any]] = None

        try:
            async with self.client.messages.stream(**request_kwargs) as stream:
                async for chunk in stream:
                    event_type = chunk.type

                    if event_type == "content_block_delta":
                        delta = chunk.delta

                        if delta.type == "text_delta":
                            full_content += delta.text
                            yield StreamChunk(
                                content=full_content,
                                delta=delta.text,
                                is_final=False,
                            )

                        elif delta.type == "input_json_delta":
                            if current_tool_use is None:
                                current_tool_use = {
                                    "id": "",
                                    "name": "",
                                    "arguments": "",
                                }
                            current_tool_use["arguments"] += delta.partial_json

                    elif event_type == "content_block_start":
                        block = chunk.content_block
                        if block.type == "tool_use":
                            current_tool_use = {
                                "id": block.id,
                                "name": block.name,
                                "arguments": "",
                            }

                    elif event_type == "message_delta":
                        if chunk.delta.stop_reason:
                            # Finalize tool call if present
                            if current_tool_use:
                                try:
                                    args = json.loads(current_tool_use["arguments"])
                                except json.JSONDecodeError:
                                    args = {}
                                yield StreamChunk(
                                    content=full_content,
                                    delta="",
                                    is_final=True,
                                    tool_call=ToolCall(
                                        id=current_tool_use["id"],
                                        name=current_tool_use["name"],
                                        arguments=args,
                                    ),
                                    finish_reason=chunk.delta.stop_reason,
                                )
                            else:
                                yield StreamChunk(
                                    content=full_content,
                                    delta="",
                                    is_final=True,
                                    finish_reason=chunk.delta.stop_reason,
                                )

        except Exception as e:
            logger.error("anthropic_stream_failed", error=str(e))
            raise
