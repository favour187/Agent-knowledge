"""
Context Compression

Reduces context size while preserving key information.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class CompressionResult:
    """Result of context compression."""
    original_length: int
    compressed_length: int
    compression_ratio: float
    preserved_information: list[str]


class ContextCompressor:
    """
    Compresses conversation context while preserving key information.

    Strategies:
    - Message truncation
    - Summarization
    - Key information extraction
    - Redundancy removal
    """

    def __init__(self, ai_runtime: Optional[Any] = None):
        self.ai_runtime = ai_runtime

    async def compress(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int,
    ) -> list[dict[str, Any]]:
        """
        Compress messages to fit within token budget.

        Args:
            messages: List of messages
            max_tokens: Maximum tokens allowed

        Returns:
            Compressed message list
        """
        if not messages:
            return []

        # Estimate current token count
        current_tokens = self._estimate_tokens(messages)

        if current_tokens <= max_tokens:
            return messages

        # Strategy 1: Truncate oldest messages
        compressed = self._truncate_oldest(messages, max_tokens)
        if self._estimate_tokens(compressed) <= max_tokens:
            return compressed

        # Strategy 2: Summarize older messages
        compressed = await self._summarize_old(messages, max_tokens)
        return compressed

    def _estimate_tokens(self, messages: list[dict[str, Any]]) -> int:
        """Estimate token count for messages."""
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            total += len(content) // 4  # Rough estimate: 4 chars per token
        return total

    def _truncate_oldest(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int,
    ) -> list[dict[str, Any]]:
        """Truncate oldest messages to fit budget."""
        result = []
        tokens_used = 0

        # Start from most recent
        for msg in reversed(messages):
            content = msg.get("content", "")
            msg_tokens = len(content) // 4

            if tokens_used + msg_tokens <= max_tokens:
                result.insert(0, msg)
                tokens_used += msg_tokens
            else:
                # Try to keep at least system prompt and recent messages
                if len(result) > 0:
                    break

        return result

    async def _summarize_old(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int,
    ) -> list[dict[str, Any]]:
        """Summarize older messages."""
        if not self.ai_runtime or len(messages) <= 2:
            return self._truncate_oldest(messages, max_tokens)

        # Keep system message if present
        system_msg = None
        if messages[0].get("role") == "system":
            system_msg = messages[0]
            messages = messages[1:]

        # Keep recent half
        recent_count = len(messages) // 2
        recent = messages[-recent_count:]

        # Summarize older half
        older = messages[:-recent_count] if recent_count < len(messages) else []
        
        if older:
            summary = await self._create_summary(older)
            summarized = [{
                "role": "system",
                "content": f"[Previous conversation summary]: {summary}"
            }]
        else:
            summarized = []

        # Combine
        result = []
        if system_msg:
            result.append(system_msg)
        result.extend(summarized)
        result.extend(recent)

        # Final truncation if needed
        return self._truncate_oldest(result, max_tokens)

    async def _create_summary(self, messages: list[dict[str, Any]]) -> str:
        """Create a summary of messages."""
        if not self.ai_runtime:
            return f"{len(messages)} previous messages"

        from core.ai_runtime.engine import Message, MessageRole

        # Build summary prompt
        content_parts = []
        for msg in messages[:20]:  # Limit to first 20
            role = msg.get("role", "unknown")
            content = msg.get("content", "")[:500]  # First 500 chars
            content_parts.append(f"{role}: {content}")

        prompt = f"""Summarize this conversation briefly (2-3 sentences):
        
{chr(10).join(content_parts)}

Summary:"""

        try:
            response = await self.ai_runtime.complete(
                messages=[Message(role=MessageRole.USER, content=prompt)],
                model="gpt-3.5-turbo",
            )
            return response.content
        except Exception as e:
            logger.warning("summary_failed", error=str(e))
            return f"{len(messages)} previous messages"

    def remove_redundancy(
        self,
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Remove redundant messages."""
        if len(messages) < 3:
            return messages

        result = [messages[0]]  # Keep first (usually system)

        for i, msg in enumerate(messages[1:], 1):
            # Check if similar to previous
            prev = result[-1]
            if msg.get("role") == prev.get("role"):
                # Similar role, check content similarity
                if self._content_similarity(
                    msg.get("content", ""),
                    prev.get("content", ""),
                ) > 0.9:
                    # Very similar, skip
                    continue

            result.append(msg)

        return result

    def _content_similarity(self, text1: str, text2: str) -> float:
        """Calculate simple content similarity."""
        if not text1 or not text2:
            return 0.0

        # Simple character-based similarity
        set1 = set(text1.lower().split())
        set2 = set(text2.lower().split())

        if not set1 or not set2:
            return 0.0

        intersection = len(set1 & set2)
        union = len(set1 | set2)

        return intersection / union if union > 0 else 0.0
