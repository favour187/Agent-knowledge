"""
Reasoning Engine

Provides multi-step logical reasoning capabilities including
chain-of-thought and tree-of-thought reasoning strategies.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

import structlog

from core.ai_runtime.engine import AIRuntime, Message, MessageRole

logger = structlog.get_logger(__name__)


class ReasoningStrategy(str, Enum):
    """Available reasoning strategies."""
    CHAIN_OF_THOUGHT = "chain_of_thought"
    TREE_OF_THOUGHT = "tree_of_thought"
    SELF_ASK = "self_ask"
    REFLEXION = "reflexion"
    REACT = "react"


@dataclass
class ThoughtStep:
    """A single step in a reasoning chain."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    thought: str = ""
    action: Optional[str] = None
    action_input: Optional[dict[str, Any]] = None
    observation: Optional[str] = None
    result: Optional[str] = None
    confidence: float = 1.0
    is_final: bool = False
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "thought": self.thought,
            "action": self.action,
            "action_input": self.action_input,
            "observation": self.observation,
            "result": self.result,
            "confidence": self.confidence,
            "is_final": self.is_final,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class ReasoningResult:
    """Result of a reasoning process."""
    success: bool
    answer: str
    confidence: float
    steps: list[ThoughtStep]
    execution_time: float
    strategy_used: ReasoningStrategy
    alternative_paths: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "answer": self.answer,
            "confidence": self.confidence,
            "steps": [s.to_dict() for s in self.steps],
            "execution_time": self.execution_time,
            "strategy_used": self.strategy_used.value,
            "alternative_paths": self.alternative_paths,
            "errors": self.errors,
            "metadata": self.metadata,
        }

    def get_reasoning_chain(self) -> str:
        """Get a formatted reasoning chain."""
        lines = []
        for i, step in enumerate(self.steps):
            if step.thought:
                lines.append(f"Step {i+1}: {step.thought}")
            if step.observation:
                lines.append(f"  → {step.observation}")
        return "\n".join(lines)


class ReasoningEngine:
    """
    Multi-strategy reasoning engine.

    Supports various reasoning strategies including chain-of-thought,
    tree-of-thought, self-ask, and ReAct.
    """

    def __init__(self, ai_runtime: Optional[AIRuntime] = None):
        self.ai_runtime = ai_runtime
        self.strategies: dict[ReasoningStrategy, Any] = {}

    def register_strategy(
        self,
        strategy: ReasoningStrategy,
        implementation: Any,
    ) -> None:
        """Register a custom reasoning strategy."""
        self.strategies[strategy] = implementation

    async def reason(
        self,
        problem: str,
        strategy: ReasoningStrategy = ReasoningStrategy.CHAIN_OF_THOUGHT,
        context: Optional[dict[str, Any]] = None,
        max_steps: int = 10,
    ) -> ReasoningResult:
        """
        Perform reasoning on a problem.

        Args:
            problem: The problem to reason about
            strategy: Reasoning strategy to use
            context: Optional context information
            max_steps: Maximum number of reasoning steps

        Returns:
            ReasoningResult with answer and reasoning steps
        """
        import time
        start_time = time.time()

        logger.info(
            "reasoning_started",
            problem=problem[:100],
            strategy=strategy.value,
        )

        try:
            if strategy == ReasoningStrategy.CHAIN_OF_THOUGHT:
                result = await self._chain_of_thought(problem, context, max_steps)
            elif strategy == ReasoningStrategy.TREE_OF_THOUGHT:
                result = await self._tree_of_thought(problem, context, max_steps)
            elif strategy == ReasoningStrategy.SELF_ASK:
                result = await self._self_ask(problem, context, max_steps)
            elif strategy == ReasoningStrategy.REACT:
                result = await self._react(problem, context, max_steps)
            else:
                result = await self._chain_of_thought(problem, context, max_steps)

            result.execution_time = time.time() - start_time
            return result

        except Exception as e:
            logger.error("reasoning_failed", error=str(e))
            return ReasoningResult(
                success=False,
                answer="",
                confidence=0.0,
                steps=[],
                execution_time=time.time() - start_time,
                strategy_used=strategy,
                errors=[str(e)],
            )

    async def _chain_of_thought(
        self,
        problem: str,
        context: Optional[dict[str, Any]],
        max_steps: int,
    ) -> ReasoningResult:
        """Chain-of-thought reasoning."""
        if not self.ai_runtime:
            return ReasoningResult(
                success=True,
                answer="Chain-of-thought reasoning requires an AI runtime.",
                confidence=0.5,
                steps=[],
                execution_time=0,
                strategy_used=ReasoningStrategy.CHAIN_OF_THOUGHT,
            )

        context_text = ""
        if context:
            context_text = "\n\nContext:\n" + json.dumps(context, indent=2)

        prompt = f"""Solve this problem step by step, showing your reasoning:

Problem: {problem}{context_text}

Provide your answer in this JSON format:
{{
    "steps": [
        {{
            "thought": "What you're thinking about this step",
            "reasoning": "Your logical reasoning",
            "conclusion": "What you conclude from this step"
        }}
    ],
    "answer": "Your final answer",
    "confidence": 0.0-1.0
}}"""

        messages = [
            Message(role=MessageRole.USER, content=prompt),
        ]

        response = await self.ai_runtime.complete(
            messages=messages,
            model="gpt-4-turbo-preview",
        )

        try:
            data = json.loads(response.content)
            steps = []
            for i, step_data in enumerate(data.get("steps", [])):
                step = ThoughtStep(
                    thought=step_data.get("thought", ""),
                    result=step_data.get("conclusion", ""),
                    confidence=1.0 - (i * 0.1),
                )
                steps.append(step)

            return ReasoningResult(
                success=True,
                answer=data.get("answer", ""),
                confidence=data.get("confidence", 0.8),
                steps=steps,
                execution_time=0,
                strategy_used=ReasoningStrategy.CHAIN_OF_THOUGHT,
            )

        except json.JSONDecodeError:
            return ReasoningResult(
                success=True,
                answer=response.content,
                confidence=0.6,
                steps=[],
                execution_time=0,
                strategy_used=ReasoningStrategy.CHAIN_OF_THOUGHT,
            )

    async def _tree_of_thought(
        self,
        problem: str,
        context: Optional[dict[str, Any]],
        max_steps: int,
    ) -> ReasoningResult:
        """Tree-of-thought reasoning with multiple branches."""
        if not self.ai_runtime:
            return ReasoningResult(
                success=True,
                answer="Tree-of-thought reasoning requires an AI runtime.",
                confidence=0.5,
                steps=[],
                execution_time=0,
                strategy_used=ReasoningStrategy.TREE_OF_THOUGHT,
            )

        context_text = ""
        if context:
            context_text = "\n\nContext:\n" + json.dumps(context, indent=2)

        prompt = f"""Explore multiple approaches to solve this problem:

Problem: {problem}{context_text}

Generate 3 different solution paths in this JSON format:
{{
    "paths": [
        {{
            "approach": "Brief description of approach",
            "steps": ["Step 1", "Step 2", "Step 3"],
            "pros": ["Advantage 1"],
            "cons": ["Disadvantage 1"],
            "estimated_confidence": 0.0-1.0
        }}
    ],
    "best_path": 0-2,
    "final_answer": "The answer from the best path"
}}"""

        messages = [
            Message(role=MessageRole.USER, content=prompt),
        ]

        response = await self.ai_runtime.complete(
            messages=messages,
            model="gpt-4-turbo-preview",
        )

        try:
            data = json.loads(response.content)
            steps = []
            alternative_paths = []

            for path_data in data.get("paths", []):
                path_steps = []
                for i, step_text in enumerate(path_data.get("steps", [])):
                    step = ThoughtStep(
                        thought=step_text,
                        result=step_text,
                        confidence=path_data.get("estimated_confidence", 0.7),
                    )
                    path_steps.append(step)
                
                steps.extend(path_steps)
                alternative_paths.append({
                    "approach": path_data.get("approach", ""),
                    "pros": path_data.get("pros", []),
                    "cons": path_data.get("cons", []),
                    "confidence": path_data.get("estimated_confidence", 0.7),
                })

            return ReasoningResult(
                success=True,
                answer=data.get("final_answer", ""),
                confidence=data.get("paths", [])[data.get("best_path", 0)].get(
                    "estimated_confidence", 0.8
                ) if data.get("paths") else 0.7,
                steps=steps,
                execution_time=0,
                strategy_used=ReasoningStrategy.TREE_OF_THOUGHT,
                alternative_paths=alternative_paths,
            )

        except json.JSONDecodeError:
            return ReasoningResult(
                success=True,
                answer=response.content,
                confidence=0.6,
                steps=[],
                execution_time=0,
                strategy_used=ReasoningStrategy.TREE_OF_THOUGHT,
            )

    async def _self_ask(
        self,
        problem: str,
        context: Optional[dict[str, Any]],
        max_steps: int,
    ) -> ReasoningResult:
        """Self-ask questioning reasoning."""
        if not self.ai_runtime:
            return ReasoningResult(
                success=True,
                answer="Self-ask reasoning requires an AI runtime.",
                confidence=0.5,
                steps=[],
                execution_time=0,
                strategy_used=ReasoningStrategy.SELF_ASK,
            )

        context_text = ""
        if context:
            context_text = "\n\nContext:\n" + json.dumps(context, indent=2)

        prompt = f"""Break down this problem by asking and answering follow-up questions:

Problem: {problem}{context_text}

Format your response as a series of questions and answers:

Q1: [First follow-up question]
A1: [Answer to Q1]

Q2: [Second follow-up question based on A1]
A2: [Answer to Q2]

...

Final Answer: [Your conclusion based on the Q&A]"""

        messages = [
            Message(role=MessageRole.USER, content=prompt),
        ]

        response = await self.ai_runtime.complete(
            messages=messages,
            model="gpt-4-turbo-preview",
        )

        # Parse Q&A pairs
        steps = []
        for line in response.content.split("\n"):
            if line.startswith("Q"):
                steps.append(ThoughtStep(thought=line))
            elif line.startswith("A"):
                if steps:
                    steps[-1].result = line
            elif line.startswith("Final Answer:"):
                final_answer = line.replace("Final Answer:", "").strip()

        return ReasoningResult(
            success=True,
            answer=final_answer if "final_answer" in locals() else response.content,
            confidence=0.75,
            steps=steps,
            execution_time=0,
            strategy_used=ReasoningStrategy.SELF_ASK,
        )

    async def _react(
        self,
        problem: str,
        context: Optional[dict[str, Any]],
        max_steps: int,
    ) -> ReasoningResult:
        """ReAct (Reason + Act) reasoning with tool usage."""
        if not self.ai_runtime:
            return ReasoningResult(
                success=True,
                answer="ReAct reasoning requires an AI runtime.",
                confidence=0.5,
                steps=[],
                execution_time=0,
                strategy_used=ReasoningStrategy.REACT,
            )

        context_text = ""
        if context:
            context_text = "\n\nContext:\n" + json.dumps(context, indent=2)

        prompt = f"""Solve this problem using reasoning and actions:

Problem: {problem}{context_text}

Format your response in this pattern:
Thought: [Your reasoning about what to do next]
Action: [The action to take, if any]
Observation: [The result of the action]
... (repeat until you can give the final answer)
Final Answer: [Your conclusion]"""

        messages = [
            Message(role=MessageRole.USER, content=prompt),
        ]

        response = await self.ai_runtime.complete(
            messages=messages,
            model="gpt-4-turbo-preview",
        )

        # Parse ReAct pattern
        steps = []
        current_step = None
        final_answer = ""

        for line in response.content.split("\n"):
            line = line.strip()
            if line.startswith("Thought:"):
                if current_step:
                    steps.append(current_step)
                current_step = ThoughtStep(thought=line.replace("Thought:", "").strip())
            elif line.startswith("Action:"):
                if current_step:
                    current_step.action = line.replace("Action:", "").strip()
            elif line.startswith("Observation:"):
                if current_step:
                    current_step.observation = line.replace("Observation:", "").strip()
            elif line.startswith("Final Answer:"):
                final_answer = line.replace("Final Answer:", "").strip()
                if current_step:
                    current_step.is_final = True
            elif current_step and line:
                # Accumulate text
                if current_step.result:
                    current_step.result += " " + line
                else:
                    current_step.result = line

        if current_step:
            steps.append(current_step)

        return ReasoningResult(
            success=True,
            answer=final_answer or response.content,
            confidence=0.8,
            steps=steps,
            execution_time=0,
            strategy_used=ReasoningStrategy.REACT,
        )

    async def evaluate_answer(
        self,
        problem: str,
        answer: str,
    ) -> dict[str, Any]:
        """Evaluate the quality of an answer."""
        if not self.ai_runtime:
            return {"confidence": 0.5, "feedback": "No evaluation possible"}

        prompt = f"""Evaluate this answer to the problem:

Problem: {problem}

Answer: {answer}

Provide evaluation in JSON format:
{{
    "correctness": 0.0-1.0,
    "completeness": 0.0-1.0,
    "clarity": 0.0-1.0,
    "overall_score": 0.0-1.0,
    "feedback": "Brief feedback on the answer"
}}"""

        messages = [
            Message(role=MessageRole.USER, content=prompt),
        ]

        response = await self.ai_runtime.complete(
            messages=messages,
            model="gpt-4-turbo-preview",
        )

        try:
            return json.loads(response.content)
        except json.JSONDecodeError:
            return {"confidence": 0.5, "feedback": response.content}
