"""
AI Runtime Engine

Handles AI model inference with support for multiple providers,
streaming responses, token tracking, and cost estimation.
"""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import (
    Any,
    AsyncGenerator,
    Callable,
    Optional,
    Protocol,
    TypeVar,
    Union,
)

import structlog
from tenacity import (
    AsyncRetrying,
    RetryError,
    stop_after_attempt,
    wait_exponential,
)

logger = structlog.get_logger(__name__)

T = TypeVar("T")


class ModelProvider(str, Enum):
    """Supported AI model providers."""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    LOCAL = "local"
    OLLAMA = "ollama"


class MessageRole(str, Enum):
    """Message roles in a conversation."""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class Message:
    """A message in a conversation."""
    role: MessageRole
    content: str
    name: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_calls: Optional[list[dict[str, Any]]] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary format."""
        result: dict[str, Any] = {
            "role": self.role.value,
            "content": self.content,
        }
        if self.name:
            result["name"] = self.name
        if self.tool_call_id:
            result["tool_call_id"] = self.tool_call_id
        if self.tool_calls:
            result["tool_calls"] = self.tool_calls
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Message:
        """Create from dictionary."""
        return cls(
            role=MessageRole(data["role"]),
            content=data["content"],
            name=data.get("name"),
            tool_call_id=data.get("tool_call_id"),
            tool_calls=data.get("tool_calls"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class ToolCall:
    """A tool call requested by the model."""
    id: str
    name: str
    arguments: dict[str, Any]
    output: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary format."""
        return {
            "id": self.id,
            "type": "function",
            "function": {
                "name": self.name,
                "arguments": self.arguments,
            },
        }


@dataclass
class ModelResponse:
    """Response from an AI model."""
    content: str
    model: str
    provider: ModelProvider
    usage: TokenUsage
    finish_reason: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw_response: Optional[dict[str, Any]] = None
    latency_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TokenUsage:
    """Token usage statistics."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def __add__(self, other: TokenUsage) -> TokenUsage:
        """Add two token usages."""
        return TokenUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
        )


@dataclass
class ModelConfig:
    """Configuration for a model."""
    provider: ModelProvider
    model: str
    temperature: float = 0.7
    max_tokens: int = 4096
    top_p: Optional[float] = None
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    stop: Optional[list[str]] = None
    seed: Optional[int] = None

    # Provider-specific settings
    api_key: Optional[str] = None
    base_url: Optional[str] = None

    # Cost tracking (per 1M tokens)
    cost_per_1m_prompt_tokens: float = 0.0
    cost_per_1m_completion_tokens: float = 0.0

    def estimate_cost(self, usage: TokenUsage) -> float:
        """Estimate cost for token usage."""
        prompt_cost = (usage.prompt_tokens / 1_000_000) * self.cost_per_1m_prompt_tokens
        completion_cost = (usage.completion_tokens / 1_000_000) * self.cost_per_1m_completion_tokens
        return prompt_cost + completion_cost


@dataclass
class StreamChunk:
    """A chunk of a streaming response."""
    content: str
    delta: str
    is_final: bool = False
    tool_call: Optional[ToolCall] = None
    usage: Optional[TokenUsage] = None
    finish_reason: Optional[str] = None


class AIProvider(ABC):
    """Abstract base class for AI providers."""

    @abstractmethod
    async def complete(
        self,
        messages: list[Message],
        config: ModelConfig,
        tools: Optional[list[dict[str, Any]]] = None,
    ) -> ModelResponse:
        """Generate a completion."""
        pass

    @abstractmethod
    async def stream(
        self,
        messages: list[Message],
        config: ModelConfig,
        tools: Optional[list[dict[str, Any]]] = None,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Generate a streaming completion."""
        pass

    @abstractmethod
    def count_tokens(self, text: str, model: str) -> int:
        """Count tokens in text."""
        pass


class RateLimiter:
    """Token bucket rate limiter."""

    def __init__(self, rate: float, capacity: float):
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: int = 1) -> float:
        """Acquire tokens, waiting if necessary. Returns wait time in seconds."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            self.last_update = now

            if self.tokens >= tokens:
                self.tokens -= tokens
                return 0.0
            else:
                wait_time = (tokens - self.tokens) / self.rate
                return wait_time


class AIRuntime:
    """
    AI Runtime Engine

    Manages AI model inference with support for multiple providers,
    automatic retries, rate limiting, cost tracking, and streaming.
    """

    def __init__(
        self,
        default_provider: ModelProvider = ModelProvider.OPENAI,
        default_model: str = "gpt-4-turbo-preview",
    ):
        self.default_provider = default_provider
        self.default_model = default_model
        self.providers: dict[ModelProvider, AIProvider] = {}
        self.model_configs: dict[str, ModelConfig] = {}
        self.rate_limiters: dict[str, RateLimiter] = {}
        self._usage_stats: dict[str, TokenUsage] = {}
        self._cost_stats: dict[str, float] = {}
        self._request_hooks: list[Callable[[str, list[Message]], None]] = []
        self._response_hooks: list[Callable[[str, ModelResponse], None]] = []

        # Default model configurations
        self._init_default_configs()

    def _init_default_configs(self) -> None:
        """Initialize default model configurations with pricing."""
        configs = [
            ModelConfig(
                provider=ModelProvider.OPENAI,
                model="gpt-4-turbo-preview",
                temperature=0.7,
                max_tokens=4096,
                cost_per_1m_prompt_tokens=10.0,
                cost_per_1m_completion_tokens=30.0,
            ),
            ModelConfig(
                provider=ModelProvider.OPENAI,
                model="gpt-3.5-turbo",
                temperature=0.7,
                max_tokens=4096,
                cost_per_1m_prompt_tokens=0.5,
                cost_per_1m_completion_tokens=1.5,
            ),
            ModelConfig(
                provider=ModelProvider.ANTHROPIC,
                model="claude-3-opus-20240229",
                temperature=0.7,
                max_tokens=4096,
                cost_per_1m_prompt_tokens=15.0,
                cost_per_1m_completion_tokens=75.0,
            ),
            ModelConfig(
                provider=ModelProvider.ANTHROPIC,
                model="claude-3-sonnet-20240229",
                temperature=0.7,
                max_tokens=4096,
                cost_per_1m_prompt_tokens=3.0,
                cost_per_1m_completion_tokens=15.0,
            ),
            ModelConfig(
                provider=ModelProvider.ANTHROPIC,
                model="claude-3-haiku-20240307",
                temperature=0.7,
                max_tokens=4096,
                cost_per_1m_prompt_tokens=0.25,
                cost_per_1m_completion_tokens=1.25,
            ),
        ]
        for config in configs:
            self.model_configs[config.model] = config

    def register_provider(self, provider_type: ModelProvider, provider: AIProvider) -> None:
        """Register an AI provider under its ModelProvider key (e.g. "openai").

        NOTE: this used to key on `provider.__class__.__name__.lower()`
        (e.g. "openaiprovider"), while `complete()`/`stream()` look providers
        up by `config.provider.value` (e.g. "openai"). Those never matched,
        so every real completion silently failed with "No provider
        registered for ...", even when a provider was registered correctly
        at startup. Fixed by requiring the caller to pass the explicit
        ModelProvider key.
        """
        self.providers[provider_type.value] = provider

    def register_model_config(self, config: ModelConfig) -> None:
        """Register a model configuration."""
        self.model_configs[config.model] = config

    def add_request_hook(self, hook: Callable[[str, list[Message]], None]) -> None:
        """Add a hook called before each request."""
        self._request_hooks.append(hook)

    def add_response_hook(self, hook: Callable[[str, ModelResponse], None]) -> None:
        """Add a hook called after each response."""
        self._response_hooks.append(hook)

    def get_model_config(self, model: Optional[str] = None) -> ModelConfig:
        """Get configuration for a model."""
        model = model or self.default_model
        if model not in self.model_configs:
            # Create default config
            return ModelConfig(
                provider=self.default_provider,
                model=model,
            )
        return self.model_configs[model]

    async def complete(
        self,
        messages: list[Message],
        model: Optional[str] = None,
        config: Optional[ModelConfig] = None,
        tools: Optional[list[dict[str, Any]]] = None,
        user_id: Optional[str] = None,
    ) -> ModelResponse:
        """
        Generate a completion with automatic retries and rate limiting.

        Args:
            messages: Conversation messages
            model: Model identifier (defaults to configured default)
            config: Optional model configuration override
            tools: Optional tool definitions
            user_id: Optional user identifier for tracking

        Returns:
            ModelResponse with content and metadata
        """
        model = model or self.default_model
        config = config or self.get_model_config(model)

        # Apply request hooks
        for hook in self._request_hooks:
            hook(model, messages)

        # Check rate limits
        if model in self.rate_limiters:
            wait_time = await self.rate_limiters[model].acquire(1)
            if wait_time > 0:
                logger.info("rate_limit_wait", model=model, wait_seconds=wait_time)
                await asyncio.sleep(wait_time)

        # Get provider
        provider = self.providers.get(config.provider.value)
        if not provider:
            raise ValueError(f"No provider registered for {config.provider}")

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(3),
                wait=wait_exponential(multiplier=1, min=1, max=10),
                reraise=True,
            ):
                with attempt:
                    start_time = time.monotonic()
                    response = await provider.complete(
                        messages=messages,
                        config=config,
                        tools=tools,
                    )
                    response.latency_ms = (time.monotonic() - start_time) * 1000

            # Track usage
            self._track_usage(model, response.usage, config)

            # Apply response hooks
            for hook in self._response_hooks:
                hook(model, response)

            return response

        except RetryError as e:
            logger.error("ai_completion_failed", model=model, error=str(e))
            raise

    async def stream(
        self,
        messages: list[Message],
        model: Optional[str] = None,
        config: Optional[ModelConfig] = None,
        tools: Optional[list[dict[str, Any]]] = None,
    ) -> AsyncGenerator[StreamChunk, None]:
        """
        Generate a streaming completion.

        Args:
            messages: Conversation messages
            model: Model identifier
            config: Optional model configuration override
            tools: Optional tool definitions

        Yields:
            StreamChunk objects as they're generated
        """
        model = model or self.default_model
        config = config or self.get_model_config(model)

        provider = self.providers.get(config.provider.value)
        if not provider:
            raise ValueError(f"No provider registered for {config.provider}")

        async for chunk in provider.stream(messages, config, tools):
            yield chunk

    def _track_usage(self, model: str, usage: TokenUsage, config: ModelConfig) -> None:
        """Track token usage and costs."""
        if model not in self._usage_stats:
            self._usage_stats[model] = TokenUsage()
        self._usage_stats[model] += usage

        cost = config.estimate_cost(usage)
        self._cost_stats[model] = self._cost_stats.get(model, 0.0) + cost

    def get_usage_stats(self) -> dict[str, Any]:
        """Get usage statistics."""
        total_usage = TokenUsage()
        total_cost = 0.0

        for model, usage in self._usage_stats.items():
            total_usage += usage
            total_cost += self._cost_stats.get(model, 0.0)

        return {
            "by_model": {
                model: {
                    "usage": vars(usage),
                    "cost": self._cost_stats.get(model, 0.0),
                }
                for model, usage in self._usage_stats.items()
            },
            "total": {
                "usage": vars(total_usage),
                "cost": total_cost,
            },
        }

    def reset_stats(self) -> None:
        """Reset usage statistics."""
        self._usage_stats.clear()
        self._cost_stats.clear()
