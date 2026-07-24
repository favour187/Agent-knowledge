"""
Local Provider Implementation

Provides AI inference using locally hosted models via Ollama or similar APIs.
"""

from __future__ import annotations

import json
from typing import Any, AsyncGenerator, Optional

import httpx

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


class LocalProvider(AIProvider):
    """
    Local model provider supporting Ollama and similar APIs.
    """

    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=120.0)
        self._encoding_cache: dict[str, Any] = {}

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    def count_tokens(self, text: str, model: str) -> int:
        """Estimate token count for local model."""
        # Rough estimate: ~4 chars per token
        return len(text) // 4

    async def _ensure_model_loaded(self, model: str) -> bool:
        """Ensure the model is loaded in Ollama."""
        try:
            response = await self._client.post(
                f"{self.base_url}/api/generate",
                json={"model": model, "keep_alive": "5m"},
            )
            return response.status_code == 200
        except Exception:
            return False

    def _convert_messages(
        self, messages: list[Message]
    ) -> tuple[Optional[str], str]:
        """Convert internal messages to Ollama format.
        
        Returns:
            Tuple of (system_prompt, formatted_prompt)
        """
        system_prompt = None
        prompt_parts = []

        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                system_prompt = msg.content
            elif msg.role == MessageRole.USER:
                prompt_parts.append(f"User: {msg.content}")
            elif msg.role == MessageRole.ASSISTANT:
                prompt_parts.append(f"Assistant: {msg.content}")
            elif msg.role == MessageRole.TOOL:
                prompt_parts.append(
                    f"Tool Result: {msg.content}"
                )

        full_prompt = "\n\n".join(prompt_parts) + "\n\nAssistant:"
        return system_prompt, full_prompt

    async def complete(
        self,
        messages: list[Message],
        config: ModelConfig,
        tools: Optional[list[dict[str, Any]]] = None,
    ) -> ModelResponse:
        """
        Generate a completion using local model via Ollama.

        Args:
            messages: Conversation messages
            config: Model configuration
            tools: Optional tool definitions (limited support)

        Returns:
            ModelResponse with content and metadata
        """
        logger.debug(
            "local_complete_request",
            model=config.model,
            message_count=len(messages),
        )

        system_prompt, prompt = self._convert_messages(messages)

        request_kwargs: dict[str, Any] = {
            "model": config.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": config.temperature,
                "num_predict": config.max_tokens,
            },
        }

        if system_prompt:
            request_kwargs["system"] = system_prompt

        if config.top_p is not None:
            request_kwargs["options"]["top_p"] = config.top_p

        if config.stop:
            request_kwargs["options"]["stop"] = config.stop

        if config.seed is not None:
            request_kwargs["options"]["seed"] = config.seed

        # Note: Ollama has limited tool support
        # For full tool support, use function calling models

        try:
            response = await self._client.post(
                f"{self.base_url}/api/generate",
                json=request_kwargs,
            )
            response.raise_for_status()
            data = response.json()

            content = data.get("response", "")
            
            # Estimate token usage
            prompt_tokens = self.count_tokens(prompt, config.model)
            completion_tokens = self.count_tokens(content, config.model)

            usage = TokenUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            )

            return ModelResponse(
                content=content,
                model=config.model,
                provider=ModelProvider.LOCAL,
                usage=usage,
                finish_reason=data.get("done_reason", "stop"),
                raw_response=data,
            )

        except httpx.HTTPError as e:
            logger.error("local_request_failed", error=str(e))
            raise

    async def stream(
        self,
        messages: list[Message],
        config: ModelConfig,
        tools: Optional[list[dict[str, Any]]] = None,
    ) -> AsyncGenerator[StreamChunk, None]:
        """
        Generate a streaming completion using local model.

        Args:
            messages: Conversation messages
            config: Model configuration
            tools: Optional tool definitions

        Yields:
            StreamChunk objects as tokens are generated
        """
        system_prompt, prompt = self._convert_messages(messages)

        request_kwargs: dict[str, Any] = {
            "model": config.model,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": config.temperature,
                "num_predict": config.max_tokens,
            },
        }

        if system_prompt:
            request_kwargs["system"] = system_prompt

        if config.top_p is not None:
            request_kwargs["options"]["top_p"] = config.top_p

        if config.stop:
            request_kwargs["options"]["stop"] = config.stop

        full_content = ""

        try:
            async with self._client.stream(
                "POST",
                f"{self.base_url}/api/generate",
                json=request_kwargs,
            ) as stream:
                async for line in stream.aiter_lines():
                    if not line:
                        continue
                    
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if "response" in data:
                        delta = data["response"]
                        full_content += delta
                        yield StreamChunk(
                            content=full_content,
                            delta=delta,
                            is_final=False,
                        )

                    if data.get("done", False):
                        yield StreamChunk(
                            content=full_content,
                            delta="",
                            is_final=True,
                            finish_reason=data.get("done_reason", "stop"),
                        )
                        break

        except httpx.HTTPError as e:
            logger.error("local_stream_failed", error=str(e))
            raise

    @classmethod
    async def list_models(cls, base_url: str = "http://localhost:11434") -> list[dict[str, Any]]:
        """List available models from Ollama."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(f"{base_url}/api/tags")
                response.raise_for_status()
                data = response.json()
                return data.get("models", [])
            except httpx.HTTPError:
                return []
