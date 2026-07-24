"""
Self-Evaluator

Evaluates AI outputs for quality, correctness, and alignment.
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


class QualityDimension(str, Enum):
    """Dimensions of quality."""
    CORRECTNESS = "correctness"
    COMPLETENESS = "completeness"
    COHERENCE = "coherence"
    HELPFULNESS = "helpfulness"
    SAFETY = "safety"
    EFFICIENCY = "efficiency"


@dataclass
class Rubric:
    """Evaluation rubric with criteria."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    dimensions: dict[QualityDimension, float] = field(default_factory=dict)
    thresholds: dict[str, float] = field(default_factory=dict)  # dimension -> minimum score

    @classmethod
    def default(cls) -> Rubric:
        """Get default evaluation rubric."""
        return cls(
            name="Default Rubric",
            description="Standard evaluation for general responses",
            dimensions={
                QualityDimension.CORRECTNESS: 0.3,
                QualityDimension.COMPLETENESS: 0.2,
                QualityDimension.COHERENCE: 0.2,
                QualityDimension.HELPFULNESS: 0.2,
                QualityDimension.SAFETY: 0.1,
            },
            thresholds={
                QualityDimension.SAFETY.value: 0.8,  # Safety is critical
                QualityDimension.CORRECTNESS.value: 0.6,
            },
        )

    @classmethod
    def coding(cls) -> Rubric:
        """Get rubric for code evaluation."""
        return cls(
            name="Code Evaluation Rubric",
            description="Evaluation for code generation",
            dimensions={
                QualityDimension.CORRECTNESS: 0.35,
                QualityDimension.EFFICIENCY: 0.25,
                QualityDimension.COHERENCE: 0.2,
                QualityDimension.COMPLETENESS: 0.2,
            },
            thresholds={
                QualityDimension.CORRECTNESS.value: 0.7,
            },
        )


@dataclass
class EvaluationResult:
    """Result of an evaluation."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    overall_score: float = 0.0
    dimension_scores: dict[str, float] = field(default_factory=dict)
    passed: bool = True
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    evaluation_time: float = 0.0
    rubric_name: str = ""
    evaluated_at: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "overall_score": self.overall_score,
            "dimension_scores": self.dimension_scores,
            "passed": self.passed,
            "issues": self.issues,
            "suggestions": self.suggestions,
            "evaluation_time": self.evaluation_time,
            "rubric_name": self.rubric_name,
            "evaluated_at": self.evaluated_at.isoformat(),
            "metadata": self.metadata,
        }

    def summary(self) -> str:
        """Get a summary string."""
        status = "PASSED" if self.passed else "FAILED"
        return f"[{status}] Score: {self.overall_score:.2f}/1.0 - {len(self.issues)} issues"


class SelfEvaluator:
    """
    Evaluates AI outputs using configurable rubrics.

    Features:
    - Multi-dimensional evaluation
    - Configurable rubrics
    - Issue detection
    - Improvement suggestions
    - Historical tracking
    """

    def __init__(
        self,
        ai_runtime: Optional[AIRuntime] = None,
        default_rubric: Optional[Rubric] = None,
    ):
        self.ai_runtime = ai_runtime
        self.default_rubric = default_rubric or Rubric.default()
        self._rubrics: dict[str, Rubric] = {"default": self.default_rubric}
        self._history: list[EvaluationResult] = []

    def register_rubric(self, rubric: Rubric) -> None:
        """Register a new rubric."""
        self._rubrics[rubric.id] = rubric
        self._rubrics[rubric.name.lower()] = rubric

    def get_rubric(self, name_or_id: str) -> Optional[Rubric]:
        """Get a rubric by name or ID."""
        return self._rubrics.get(name_or_id) or self._rubrics.get(name_or_id.lower())

    async def evaluate(
        self,
        output: str,
        task: str,
        rubric: Optional[Rubric] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> EvaluationResult:
        """
        Evaluate an output.

        Args:
            output: The output to evaluate
            task: The original task
            rubric: Rubric to use (defaults to default rubric)
            context: Additional context

        Returns:
            EvaluationResult
        """
        import time
        start_time = time.time()

        rubric = rubric or self.default_rubric
        context_text = ""
        if context:
            context_text = "\n\nContext:\n" + json.dumps(context, indent=2)

        if not self.ai_runtime:
            # Simple heuristic evaluation
            result = self._heuristic_evaluate(output, task, rubric)
            result.evaluation_time = time.time() - start_time
            result.rubric_name = rubric.name
            self._history.append(result)
            return result

        # AI-powered evaluation
        prompt = f"""Evaluate this output based on the following rubric:

Task: {task}{context_text}

Output to evaluate:
{output}

Rubric dimensions:
{json.dumps({d.value: w for d, w in rubric.dimensions.items()}, indent=2)}

Provide your evaluation in JSON format:
{{
    "dimension_scores": {{
        "correctness": 0.0-1.0,
        "completeness": 0.0-1.0,
        "coherence": 0.0-1.0,
        "helpfulness": 0.0-1.0,
        "safety": 0.0-1.0,
        "efficiency": 0.0-1.0
    }},
    "issues": ["issue 1", "issue 2"],
    "suggestions": ["suggestion 1", "suggestion 2"],
    "overall_assessment": "Brief summary"
}}"""

        from core.ai_runtime.engine import Message, MessageRole

        try:
            response = await self.ai_runtime.complete(
                messages=[Message(role=MessageRole.USER, content=prompt)],
                model="gpt-4-turbo-preview",
            )

            data = json.loads(response.content)
            dimension_scores = data.get("dimension_scores", {})

            # Calculate weighted overall score
            overall_score = sum(
                dimension_scores.get(d.value, 0.5) * weight
                for d, weight in rubric.dimensions.items()
            )

            # Check if passed based on thresholds
            passed = True
            issues = data.get("issues", [])

            for dim, min_score in rubric.thresholds.items():
                score = dimension_scores.get(dim, 1.0)
                if score < min_score:
                    passed = False
                    issues.append(f"Below threshold on {dim}: {score:.2f} < {min_score:.2f}")

            result = EvaluationResult(
                overall_score=overall_score,
                dimension_scores=dimension_scores,
                passed=passed,
                issues=issues,
                suggestions=data.get("suggestions", []),
                evaluation_time=time.time() - start_time,
                rubric_name=rubric.name,
                metadata={"assessment": data.get("overall_assessment", "")},
            )

        except json.JSONDecodeError:
            result = EvaluationResult(
                overall_score=0.5,
                dimension_scores={},
                issues=["Failed to parse evaluation"],
                rubric_name=rubric.name,
                evaluation_time=time.time() - start_time,
            )

        self._history.append(result)
        return result

    def _heuristic_evaluate(
        self,
        output: str,
        task: str,
        rubric: Rubric,
    ) -> EvaluationResult:
        """Simple heuristic evaluation without AI."""
        dimension_scores = {}

        # Very basic heuristics
        if len(output) < 10:
            dimension_scores["completeness"] = 0.2
            dimension_scores["helpfulness"] = 0.1
        else:
            dimension_scores["completeness"] = 0.7
            dimension_scores["helpfulness"] = 0.6

        dimension_scores["correctness"] = 0.5  # Unknown without AI
        dimension_scores["coherence"] = 0.6 if output else 0.0
        dimension_scores["safety"] = 0.9 if output else 0.0
        dimension_scores["efficiency"] = 0.5

        overall_score = sum(
            dimension_scores.get(d.value, 0.5) * weight
            for d, weight in rubric.dimensions.items()
        )

        issues = []
        if dimension_scores.get("completeness", 1.0) < 0.5:
            issues.append("Output seems incomplete")
        if dimension_scores.get("safety", 1.0) < 0.5:
            issues.append("Potential safety concern")

        return EvaluationResult(
            overall_score=overall_score,
            dimension_scores=dimension_scores,
            passed=overall_score >= 0.5,
            issues=issues,
            rubric_name=rubric.name,
        )

    async def evaluate_with_retry(
        self,
        output: str,
        task: str,
        max_attempts: int = 3,
        min_score: float = 0.7,
    ) -> tuple[EvaluationResult, bool]:
        """
        Evaluate with automatic retry if below threshold.

        Args:
            output: The output to evaluate
            task: The original task
            max_attempts: Maximum evaluation attempts
            min_score: Minimum acceptable score

        Returns:
            Tuple of (result, improved)
        """
        result = await self.evaluate(output, task)
        improved = False

        for attempt in range(1, max_attempts):
            if result.overall_score >= min_score:
                break

            logger.info(
                "evaluation_retry",
                attempt=attempt,
                score=result.overall_score,
            )

            result = await self.evaluate(output, task)
            improved = True

        return result, improved

    def get_history(
        self,
        limit: int = 100,
        min_score: Optional[float] = None,
    ) -> list[EvaluationResult]:
        """Get evaluation history."""
        results = self._history[-limit:]

        if min_score is not None:
            results = [r for r in results if r.overall_score >= min_score]

        return results

    def get_stats(self) -> dict[str, Any]:
        """Get evaluation statistics."""
        if not self._history:
            return {
                "total_evaluations": 0,
                "avg_score": 0.0,
                "pass_rate": 0.0,
            }

        total = len(self._history)
        passed = sum(1 for r in self._history if r.passed)
        avg_score = sum(r.overall_score for r in self._history) / total

        return {
            "total_evaluations": total,
            "passed": passed,
            "failed": total - passed,
            "pass_rate": passed / total,
            "avg_score": avg_score,
            "avg_evaluation_time": sum(r.evaluation_time for r in self._history) / total,
        }
