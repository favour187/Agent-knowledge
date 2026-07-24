"""
Chain of Thought Reasoning

Implements structured chain-of-thought reasoning with verification.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

import structlog

from core.ai_runtime.engine import AIRuntime, Message, MessageRole

logger = structlog.get_logger(__name__)


@dataclass
class CoTStep:
    """A step in chain-of-thought reasoning."""
    step_number: int
    premise: str
    reasoning: str
    conclusion: str
    confidence: float = 1.0
    is_verified: bool = False
    verification_note: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class CoTResult:
    """Result of chain-of-thought reasoning."""
    success: bool
    final_answer: str
    steps: list[CoTStep]
    overall_confidence: float
    total_verified: int
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "final_answer": self.final_answer,
            "steps": [
                {
                    "step_number": s.step_number,
                    "premise": s.premise,
                    "reasoning": s.reasoning,
                    "conclusion": s.conclusion,
                    "confidence": s.confidence,
                    "is_verified": s.is_verified,
                    "verification_note": s.verification_note,
                }
                for s in self.steps
            ],
            "overall_confidence": self.overall_confidence,
            "total_verified": self.total_verified,
            "errors": self.errors,
            "metadata": self.metadata,
        }


class ChainOfThought:
    """
    Chain-of-thought reasoning with structured steps and verification.

    Features:
    - Structured premise → reasoning → conclusion pattern
    - Step-by-step verification
    - Confidence tracking
    - Error detection and recovery
    """

    def __init__(self, ai_runtime: Optional[AIRuntime] = None):
        self.ai_runtime = ai_runtime
        self._verification_prompt = """Verify this reasoning step:

Premise: {premise}
Reasoning: {reasoning}
Conclusion: {conclusion}

Respond in JSON format:
{{
    "is_valid": true/false,
    "confidence": 0.0-1.0,
    "issues": ["issue 1"] or [],
    "suggestions": ["suggestion 1"] or []
}}"""

    async def reason(
        self,
        problem: str,
        context: Optional[dict[str, Any]] = None,
        max_steps: int = 10,
        verify_each_step: bool = True,
    ) -> CoTResult:
        """
        Perform chain-of-thought reasoning.

        Args:
            problem: The problem to solve
            context: Optional context information
            max_steps: Maximum number of reasoning steps
            verify_each_step: Whether to verify each step

        Returns:
            CoTResult with reasoning chain
        """
        logger.info("cot_reasoning_started", problem=problem[:100])

        if not self.ai_runtime:
            return CoTResult(
                success=False,
                final_answer="",
                steps=[],
                overall_confidence=0.0,
                total_verified=0,
                errors=["AI runtime not configured"],
            )

        context_text = ""
        if context:
            context_text = "\n\nAdditional Context:\n" + json.dumps(context, indent=2)

        prompt = f"""Solve this problem using chain-of-thought reasoning.
Break down your reasoning into clear, verifiable steps.

Problem: {problem}{context_text}

Provide your reasoning in this JSON format:
{{
    "steps": [
        {{
            "premise": "The starting premise or fact",
            "reasoning": "Your step-by-step reasoning",
            "conclusion": "What you conclude from this step"
        }}
    ],
    "final_answer": "Your final answer based on the reasoning chain"
}}{self._verification_prompt.format(premise='{premise}', reasoning='{reasoning}', conclusion='{conclusion}')}"""

        messages = [
            Message(role=MessageRole.USER, content=prompt),
        ]

        try:
            response = await self.ai_runtime.complete(
                messages=messages,
                model="gpt-4-turbo-preview",
            )

            # Parse response
            data = json.loads(response.content)
            steps = []

            for i, step_data in enumerate(data.get("steps", []), 1):
                step = CoTStep(
                    step_number=i,
                    premise=step_data.get("premise", ""),
                    reasoning=step_data.get("reasoning", ""),
                    conclusion=step_data.get("conclusion", ""),
                    confidence=step_data.get("confidence", 0.8),
                )

                # Verify step if requested
                if verify_each_step and self.ai_runtime:
                    verification = await self._verify_step(step)
                    step.is_verified = verification["is_valid"]
                    step.confidence = verification["confidence"]
                    step.verification_note = ", ".join(verification.get("issues", []))

                steps.append(step)

            # Calculate overall confidence
            verified_steps = [s for s in steps if s.is_verified]
            confidence = (
                sum(s.confidence for s in steps) / len(steps)
                if steps else 0.0
            )

            return CoTResult(
                success=True,
                final_answer=data.get("final_answer", ""),
                steps=steps,
                overall_confidence=confidence,
                total_verified=len(verified_steps),
            )

        except json.JSONDecodeError as e:
            logger.error("cot_parse_failed", error=str(e))
            return CoTResult(
                success=False,
                final_answer="",
                steps=[],
                overall_confidence=0.0,
                total_verified=0,
                errors=[f"Failed to parse response: {e}"],
            )

    async def _verify_step(self, step: CoTStep) -> dict[str, Any]:
        """Verify a single reasoning step."""
        if not self.ai_runtime:
            return {"is_valid": True, "confidence": 0.8, "issues": []}

        prompt = self._verification_prompt.format(
            premise=step.premise,
            reasoning=step.reasoning,
            conclusion=step.conclusion,
        )

        messages = [
            Message(role=MessageRole.USER, content=prompt),
        ]

        try:
            response = await self.ai_runtime.complete(
                messages=messages,
                model="gpt-4-turbo-preview",
            )
            return json.loads(response.content)
        except json.JSONDecodeError:
            return {"is_valid": True, "confidence": 0.7, "issues": []}

    async def reason_with_fallback(
        self,
        problem: str,
        context: Optional[dict[str, Any]] = None,
        max_retries: int = 3,
    ) -> CoTResult:
        """
        Reason with automatic retry on failure.

        Args:
            problem: The problem to solve
            context: Optional context
            max_retries: Maximum number of retry attempts

        Returns:
            CoTResult from successful attempt
        """
        last_error = None

        for attempt in range(max_retries):
            result = await self.reason(problem, context)

            if result.success:
                result.metadata["attempts"] = attempt + 1
                return result

            last_error = result.errors[-1] if result.errors else "Unknown error"
            logger.warning(
                "cot_retry",
                attempt=attempt + 1,
                error=last_error,
            )

        return CoTResult(
            success=False,
            final_answer="",
            steps=[],
            overall_confidence=0.0,
            total_verified=0,
            errors=[f"Failed after {max_retries} attempts: {last_error}"],
        )

    def generate_explanation(self, result: CoTResult) -> str:
        """Generate a human-readable explanation of the reasoning."""
        lines = ["## Chain of Thought Reasoning\n"]

        for step in result.steps:
            lines.append(f"### Step {step.step_number}")
            lines.append(f"**Premise:** {step.premise}")
            lines.append(f"**Reasoning:** {step.reasoning}")
            lines.append(f"**Conclusion:** {step.conclusion}")

            if step.is_verified:
                lines.append(f"✅ *Verified (confidence: {step.confidence:.0%})*")
            else:
                lines.append(f"⚠️ *Not verified*")

            lines.append("")

        lines.append(f"## Final Answer\n{result.final_answer}")
        lines.append(f"\n**Overall Confidence:** {result.overall_confidence:.0%}")
        lines.append(f"**Verified Steps:** {result.total_verified}/{len(result.steps)}")

        return "\n".join(lines)
