"""
Self-Improvement

Learns from feedback and optimizes performance over time.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

import structlog

from core.ai_runtime.engine import AIRuntime

logger = structlog.get_logger(__name__)


class FeedbackType(str, Enum):
    """Types of feedback."""
    CORRECTION = "correction"     # Output was wrong
    PREFERENCE = "preference"     # User preference
    OUTCOME = "outcome"          # Task outcome
    EVALUATION = "evaluation"     # Quality evaluation
    ERROR = "error"             # Error occurred


@dataclass
class LearnedPattern:
    """A learned pattern from feedback."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    pattern: str = ""
    context: str = ""
    response: str = ""
    success_rate: float = 0.0
    usage_count: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)

    def record_success(self) -> None:
        """Record a successful use of this pattern."""
        self.usage_count += 1
        # Update success rate with exponential moving average
        alpha = 0.1
        self.success_rate = alpha * 1.0 + (1 - alpha) * self.success_rate
        self.updated_at = datetime.utcnow()

    def record_failure(self) -> None:
        """Record a failed use of this pattern."""
        self.usage_count += 1
        alpha = 0.1
        self.success_rate = alpha * 0.0 + (1 - alpha) * self.success_rate
        self.updated_at = datetime.utcnow()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "pattern": self.pattern,
            "context": self.context,
            "response": self.response,
            "success_rate": self.success_rate,
            "usage_count": self.usage_count,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class ImprovementSuggestion:
    """A suggested improvement."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: str = ""
    description: str = ""
    rationale: str = ""
    expected_impact: float = 0.0
    confidence: float = 0.0
    created_at: datetime = field(default_factory=datetime.utcnow)
    implemented: bool = False
    implemented_at: Optional[datetime] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "type": self.type,
            "description": self.description,
            "rationale": self.rationale,
            "expected_impact": self.expected_impact,
            "confidence": self.confidence,
            "created_at": self.created_at.isoformat(),
            "implemented": self.implemented,
            "implemented_at": self.implemented_at.isoformat() if self.implemented_at else None,
            "metadata": self.metadata,
        }


class SelfImprover:
    """
    Learns from feedback and suggests/implements improvements.

    Features:
    - Pattern learning from feedback
    - Error pattern detection
    - Prompt optimization
    - Strategy refinement
    - Success rate tracking
    - Improvement suggestions
    """

    def __init__(
        self,
        ai_runtime: Optional[AIRuntime] = None,
        learning_rate: float = 0.1,
    ):
        self.ai_runtime = ai_runtime
        self.learning_rate = learning_rate

        # Pattern storage
        self._patterns: dict[str, LearnedPattern] = {}
        self._feedback_history: list[dict[str, Any]] = []

        # Configuration
        self.min_pattern_confidence: float = 0.6
        self.max_patterns: int = 1000
        self.consolidation_threshold: int = 10

        logger.info("self_improver_initialized")

    async def learn_from_feedback(
        self,
        feedback_type: FeedbackType,
        context: str,
        output: str,
        expected: Optional[str] = None,
        success: bool = True,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Optional[LearnedPattern]:
        """
        Learn from feedback.

        Args:
            feedback_type: Type of feedback
            context: Context where feedback occurred
            output: The output that was given
            expected: Expected/correct output
            success: Whether the outcome was successful
            metadata: Additional metadata

        Returns:
            LearnedPattern if a new one was created/updated
        """
        # Store feedback
        self._feedback_history.append({
            "type": feedback_type.value,
            "context": context,
            "output": output,
            "expected": expected,
            "success": success,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": metadata or {},
        })

        # Keep only recent feedback
        if len(self._feedback_history) > 1000:
            self._feedback_history = self._feedback_history[-500:]

        # Generate pattern key
        pattern_key = self._generate_pattern_key(context, output)

        if pattern_key in self._patterns:
            # Update existing pattern
            pattern = self._patterns[pattern_key]
            if success:
                pattern.record_success()
            else:
                pattern.record_failure()
            return pattern

        # Create new pattern
        if len(self._patterns) >= self.max_patterns:
            await self._consolidate_patterns()

        pattern = LearnedPattern(
            pattern=pattern_key,
            context=context,
            response=output,
            success_rate=1.0 if success else 0.0,
        )
        self._patterns[pattern_key] = pattern

        logger.debug(
            "pattern_learned",
            pattern_id=pattern.id,
            success=success,
        )

        return pattern

    def _generate_pattern_key(self, context: str, output: str) -> str:
        """Generate a pattern key from context and output."""
        # Simple hash-based key
        import hashlib
        content = f"{context[:100]}|{output[:100]}"
        return hashlib.md5(content.encode()).hexdigest()

    async def detect_error_patterns(self) -> list[dict[str, Any]]:
        """
        Detect patterns in errors and failures.

        Returns:
            List of detected error patterns
        """
        if not self.ai_runtime:
            return []

        # Get recent failures
        failures = [
            f for f in self._feedback_history
            if not f.get("success", True)
        ]

        if len(failures) < 3:
            return []

        # Analyze failures
        context_text = "\n".join([
            f"Context: {f.get('context', '')[:200]}\n"
            f"Output: {f.get('output', '')[:200]}\n"
            f"Expected: {f.get('expected', 'N/A')[:200]}\n"
            for f in failures[:10]
        ])

        prompt = f"""Analyze these failures and identify common patterns:

{context_text}

Provide patterns in JSON format:
{{
    "patterns": [
        {{
            "description": "Common issue description",
            "frequency": "how often it occurs",
            "likely_cause": "probable cause",
            "suggested_fix": "how to fix"
        }}
    ]
}}"""

        from core.ai_runtime.engine import Message, MessageRole

        try:
            response = await self.ai_runtime.complete(
                messages=[Message(role=MessageRole.USER, content=prompt)],
                model="gpt-4-turbo-preview",
            )

            data = json.loads(response.content)
            return data.get("patterns", [])

        except json.JSONDecodeError:
            return []

    async def suggest_improvements(
        self,
        goal: Optional[str] = None,
    ) -> list[ImprovementSuggestion]:
        """
        Generate improvement suggestions based on learning.

        Args:
            goal: Optional goal to focus improvements on

        Returns:
            List of improvement suggestions
        """
        suggestions = []

        # Analyze low-success patterns
        low_success = [
            p for p in self._patterns.values()
            if p.success_rate < 0.5 and p.usage_count >= 3
        ]

        for pattern in low_success[:5]:
            suggestion = ImprovementSuggestion(
                type="pattern_improvement",
                description=f"Improve response for pattern: {pattern.context[:50]}...",
                rationale=f"Success rate only {pattern.success_rate:.1%} with {pattern.usage_count} uses",
                expected_impact=1.0 - pattern.success_rate,
                confidence=min(0.9, pattern.usage_count / 20),
                metadata={"pattern_id": pattern.id},
            )
            suggestions.append(suggestion)

        # Analyze error patterns
        error_patterns = await self.detect_error_patterns()
        for ep in error_patterns:
            suggestion = ImprovementSuggestion(
                type="error_prevention",
                description=ep.get("suggested_fix", "Fix identified issue"),
                rationale=ep.get("likely_cause", "Common error pattern"),
                expected_impact=0.3,
                confidence=0.7,
                metadata=ep,
            )
            suggestions.append(suggestion)

        # Sort by expected impact
        suggestions.sort(key=lambda s: s.expected_impact * s.confidence, reverse=True)

        return suggestions[:10]

    async def optimize_prompt(
        self,
        original_prompt: str,
        task: str,
        examples: Optional[list[dict[str, str]]] = None,
    ) -> str:
        """
        Optimize a prompt based on feedback.

        Args:
            original_prompt: The original prompt
            task: The task description
            examples: Optional examples of good/bad outputs

        Returns:
            Optimized prompt
        """
        if not self.ai_runtime:
            return original_prompt

        examples_text = ""
        if examples:
            examples_text = "\n\nExamples:\n" + "\n".join([
                f"Input: {e.get('input', '')}\nOutput: {e.get('output', '')}"
                for e in examples[:5]
            ])

        prompt = f"""Optimize this prompt based on the task and feedback:

Original Prompt:
{original_prompt}

Task:
{task}{examples_text}

Provide an optimized prompt that addresses common issues and improves performance.
Respond with only the optimized prompt."""

        from core.ai_runtime.engine import Message, MessageRole

        try:
            response = await self.ai_runtime.complete(
                messages=[Message(role=MessageRole.USER, content=prompt)],
                model="gpt-4-turbo-preview",
            )

            return response.content

        except Exception as e:
            logger.warning("prompt_optimization_failed", error=str(e))
            return original_prompt

    async def _consolidate_patterns(self) -> None:
        """Consolidate similar patterns."""
        # Simple consolidation: remove lowest success rate patterns
        patterns = list(self._patterns.values())
        patterns.sort(key=lambda p: p.success_rate)

        # Remove bottom 10%
        to_remove = len(patterns) // 10
        for pattern in patterns[:to_remove]:
            del self._patterns[pattern.id]

        logger.info("patterns_consolidated", removed=to_remove)

    def get_pattern(self, pattern_id: str) -> Optional[LearnedPattern]:
        """Get a pattern by ID."""
        for pattern in self._patterns.values():
            if pattern.id == pattern_id:
                return pattern
        return None

    def get_best_patterns(self, limit: int = 10) -> list[LearnedPattern]:
        """Get best performing patterns."""
        patterns = list(self._patterns.values())
        patterns.sort(key=lambda p: p.success_rate, reverse=True)
        return patterns[:limit]

    def get_stats(self) -> dict[str, Any]:
        """Get improvement statistics."""
        patterns = list(self._patterns.values())
        avg_success = (
            sum(p.success_rate for p in patterns) / len(patterns)
            if patterns else 0
        )

        return {
            "total_patterns": len(patterns),
            "avg_success_rate": avg_success,
            "total_feedback": len(self._feedback_history),
            "recent_failures": sum(
                1 for f in self._feedback_history[-100:]
                if not f.get("success", True)
            ),
            "high_confidence_patterns": sum(
                1 for p in patterns if p.success_rate >= 0.8 and p.usage_count >= 5
            ),
        }
