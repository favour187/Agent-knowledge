"""
Task Decomposer

Decomposes complex tasks into simpler subtasks using various strategies.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)


class DecompositionStrategy(str, Enum):
    """Strategy for task decomposition."""
    LINEAR = "linear"           # Sequential steps
    HIERARCHICAL = "hierarchical"  # Tree structure
    PARALLEL = "parallel"       # Independent tasks
    CONDITIONAL = "conditional" # Branching based on conditions
    ITERATIVE = "iterative"      # Loop until condition met


@dataclass
class SubTask:
    """A decomposed subtask."""
    id: str
    title: str
    description: str
    strategy: DecompositionStrategy = DecompositionStrategy.LINEAR
    priority: int = 2
    estimated_duration: int = 300
    conditions: dict[str, Any] = field(default_factory=dict)
    max_iterations: int = 1
    children: list[SubTask] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def flatten(self) -> list[SubTask]:
        """Flatten nested subtasks into a list."""
        result = [self]
        for child in self.children:
            result.extend(child.flatten())
        return result


@dataclass
class DecompositionResult:
    """Result of task decomposition."""
    root_task: SubTask
    all_tasks: list[SubTask]
    strategy_used: DecompositionStrategy
    confidence: float
    estimated_duration: int
    potential_bottlenecks: list[str] = field(default_factory=list)
    parallel_opportunities: list[tuple[str, str]] = field(default_factory=list)


class TaskDecomposer:
    """
    Intelligent task decomposition with multiple strategies.
    """

    def __init__(self):
        self._decomposition_patterns = {
            # Sequential patterns
            r"(?:first|then|next|after that|finally)": DecompositionStrategy.LINEAR,
            r"(?:step \d+|stage \d+)": DecompositionStrategy.LINEAR,
            
            # Parallel patterns
            r"(?:simultaneously|in parallel|at the same time)": DecompositionStrategy.PARALLEL,
            r"(?:and|also|coupled with)": DecompositionStrategy.PARALLEL,
            
            # Conditional patterns
            r"(?:if|when|unless|depending on)": DecompositionStrategy.CONDITIONAL,
            r"(?:optionally|when applicable)": DecompositionStrategy.CONDITIONAL,
            
            # Iterative patterns
            r"(?:repeat|iterate|while|until|for each)": DecompositionStrategy.ITERATIVE,
            r"(?:all of the|every|single)": DecompositionStrategy.ITERATIVE,
        }

    def decompose(
        self,
        task: str,
        strategy: Optional[DecompositionStrategy] = None,
    ) -> DecompositionResult:
        """
        Decompose a task into subtasks.

        Args:
            task: The task to decompose
            strategy: Optional specific strategy to use

        Returns:
            DecompositionResult with subtasks
        """
        # Auto-detect strategy if not specified
        if strategy is None:
            strategy = self._detect_strategy(task)

        logger.debug("decomposing_task", task=task[:100], strategy=strategy.value)

        if strategy == DecompositionStrategy.LINEAR:
            return self._decompose_linear(task)
        elif strategy == DecompositionStrategy.HIERARCHICAL:
            return self._decompose_hierarchical(task)
        elif strategy == DecompositionStrategy.PARALLEL:
            return self._decompose_parallel(task)
        elif strategy == DecompositionStrategy.CONDITIONAL:
            return self._decompose_conditional(task)
        elif strategy == DecompositionStrategy.ITERATIVE:
            return self._decompose_iterative(task)
        else:
            return self._decompose_linear(task)

    def _detect_strategy(self, task: str) -> DecompositionStrategy:
        """Auto-detect the best decomposition strategy."""
        task_lower = task.lower()
        
        scores = {s: 0 for s in DecompositionStrategy}
        
        for pattern, strategy in self._decomposition_patterns.items():
            if re.search(pattern, task_lower):
                scores[strategy] += 1
        
        # Default to hierarchical for complex tasks
        if max(scores.values()) == 0:
            if len(task) > 200:
                return DecompositionStrategy.HIERARCHICAL
            return DecompositionStrategy.LINEAR
        
        return max(scores, key=scores.get)

    def _decompose_linear(self, task: str) -> DecompositionResult:
        """Linear decomposition - sequential steps."""
        # Try to split by common delimiters
        steps = []
        
        # Split by numbered steps
        numbered = re.split(r"(?:\n|^)(?:step\s+\d+[\.:]\s*|^\d+[\.\)]\s*)", task, flags=re.MULTILINE | re.IGNORECASE)
        if len(numbered) > 1:
            steps = [s.strip() for s in numbered if s.strip()]
        
        # Split by sequential words
        if not steps:
            sequential_markers = ["first", "then", "next", "after that", "finally"]
            for marker in sequential_markers:
                if marker in task.lower():
                    parts = re.split(rf"\b{marker}\b[:\s]+", task, flags=re.IGNORECASE)
                    if len(parts) > 1:
                        steps = [p.strip() for p in parts if p.strip()]
                        break
        
        # Default: single task
        if not steps:
            steps = [task]
        
        root = SubTask(
            id="root",
            title="Main Task",
            description=task,
            strategy=DecompositionStrategy.LINEAR,
        )
        
        all_tasks = []
        for i, step in enumerate(steps):
            subtask = SubTask(
                id=f"step_{i+1}",
                title=self._extract_title(step),
                description=step,
                strategy=DecompositionStrategy.LINEAR,
                estimated_duration=self._estimate_duration(step),
            )
            root.children.append(subtask)
            all_tasks.append(subtask)
        
        total_duration = sum(t.estimated_duration for t in all_tasks)
        
        return DecompositionResult(
            root_task=root,
            all_tasks=all_tasks,
            strategy_used=DecompositionStrategy.LINEAR,
            confidence=0.8 if len(steps) > 1 else 0.5,
            estimated_duration=total_duration,
        )

    def _decompose_hierarchical(self, task: str) -> DecompositionResult:
        """Hierarchical decomposition - tree structure."""
        # Identify main phases/themes
        phrases = [
            "aspects of", "parts of", "components of",
            "aspects include", "involves", "includes",
        ]
        
        phases = []
        for phrase in phrases:
            if phrase in task.lower():
                pattern = rf"{phrase}[:\s]+(.+?)(?:\.|$)"
                match = re.search(pattern, task, re.IGNORECASE)
                if match:
                    parts_text = match.group(1)
                    phases = re.split(r"(?:,|and|or)\s+", parts_text)
                    break
        
        if not phases:
            # Split by common topic separators
            separators = r"(?:\n\n|\n\s*[-–—]\s*|\. (?=[A-Z]))"
            parts = re.split(separators, task)
            if len(parts) > 1:
                phases = [p.strip() for p in parts if len(p.strip()) > 20]
        
        if not phases:
            phases = [task]
        
        root = SubTask(
            id="root",
            title="Main Task",
            description=task,
            strategy=DecompositionStrategy.HIERARCHICAL,
        )
        
        all_tasks = []
        for i, phase in enumerate(phases):
            subtask = SubTask(
                id=f"phase_{i+1}",
                title=self._extract_title(phase),
                description=phase,
                strategy=DecompositionStrategy.HIERARCHICAL,
                estimated_duration=self._estimate_duration(phase),
            )
            root.children.append(subtask)
            all_tasks.append(subtask)
        
        total_duration = sum(t.estimated_duration for t in all_tasks)
        
        return DecompositionResult(
            root_task=root,
            all_tasks=all_tasks,
            strategy_used=DecompositionStrategy.HIERARCHICAL,
            confidence=0.7,
            estimated_duration=total_duration,
        )

    def _decompose_parallel(self, task: str) -> DecompositionResult:
        """Parallel decomposition - independent tasks."""
        # Find parallelizable sections
        connectors = ["and", "also", "plus", "along with"]
        
        parts = []
        current = task
        
        for connector in connectors:
            pattern = rf"\s+{connector}\s+"
            split_parts = re.split(pattern, current, flags=re.IGNORECASE)
            if len(split_parts) > 1:
                parts = [p.strip() for p in split_parts if p.strip()]
                break
        
        if not parts:
            parts = [task]
        
        root = SubTask(
            id="root",
            title="Main Task",
            description=task,
            strategy=DecompositionStrategy.PARALLEL,
        )
        
        all_tasks = []
        parallel_pairs = []
        
        for i, part in enumerate(parts):
            subtask = SubTask(
                id=f"parallel_{i+1}",
                title=self._extract_title(part),
                description=part,
                strategy=DecompositionStrategy.PARALLEL,
                estimated_duration=self._estimate_duration(part),
            )
            root.children.append(subtask)
            all_tasks.append(subtask)
            
            # Track parallel opportunities
            for j in range(i + 1, len(parts)):
                parallel_pairs.append((subtask.id, f"parallel_{j+1}"))
        
        # Parallel tasks take max duration (they run concurrently)
        max_duration = max((t.estimated_duration for t in all_tasks), default=0)
        
        return DecompositionResult(
            root_task=root,
            all_tasks=all_tasks,
            strategy_used=DecompositionStrategy.PARALLEL,
            confidence=0.75,
            estimated_duration=max_duration,
            parallel_opportunities=parallel_pairs,
        )

    def _decompose_conditional(self, task: str) -> DecompositionResult:
        """Conditional decomposition - branching paths."""
        # Find conditional statements
        conditions = re.findall(
            r"(if|when|unless|depending on)\s+([^,\.]+)",
            task,
            re.IGNORECASE
        )
        
        branches = []
        
        # Extract the main path
        main_parts = re.split(
            r"(?:if|when|unless|depending on)\s+\w+",
            task,
            flags=re.IGNORECASE
        )
        if main_parts:
            branches.append(("default", main_parts[0].strip()))
        
        for condition_type, condition_expr in conditions:
            branches.append((condition_type, condition_expr.strip()))
        
        root = SubTask(
            id="root",
            title="Main Task",
            description=task,
            strategy=DecompositionStrategy.CONDITIONAL,
        )
        
        all_tasks = []
        bottlenecks = []
        
        for i, (condition_type, branch_content) in enumerate(branches):
            subtask = SubTask(
                id=f"branch_{i+1}",
                title=f"{condition_type.title()} Branch" if i > 0 else "Default Path",
                description=branch_content,
                strategy=DecompositionStrategy.CONDITIONAL,
                conditions={"type": condition_type},
                estimated_duration=self._estimate_duration(branch_content),
            )
            root.children.append(subtask)
            all_tasks.append(subtask)
            
            if i > 0:
                bottlenecks.append(f"Conditional branching at {condition_type}")
        
        total_duration = sum(t.estimated_duration for t in all_tasks)
        
        return DecompositionResult(
            root_task=root,
            all_tasks=all_tasks,
            strategy_used=DecompositionStrategy.CONDITIONAL,
            confidence=0.6,
            estimated_duration=total_duration,
            potential_bottlenecks=bottlenecks,
        )

    def _decompose_iterative(self, task: str) -> DecompositionResult:
        """Iterative decomposition - loops."""
        # Find iteration patterns
        iterations = re.findall(
            r"(?:repeat|iterate)\s+(?:\w+\s+)?(?:\d+)?\s*(?:times)?\s*(?:until|while|for)\s+([^,\.]+)",
            task,
            re.IGNORECASE
        )
        
        if not iterations:
            # Find items to iterate over
            items_pattern = r"(?:for each|every|all)\s+([^,\.]+)"
            items_match = re.search(items_pattern, task, re.IGNORECASE)
            if items_match:
                iterations = [items_match.group(1)]
        
        # Extract the action being iterated
        action_pattern = r"(?:do|perform|execute|run)\s+(?:the\s+)?(.+?)(?:\s+for|\s+until|\s+while|$)"
        action_match = re.search(action_pattern, task, re.IGNORECASE)
        action = action_match.group(1) if action_match else "the action"
        
        root = SubTask(
            id="root",
            title="Iterative Task",
            description=task,
            strategy=DecompositionStrategy.ITERATIVE,
            max_iterations=len(iterations) if iterations else 5,
        )
        
        # Create one iteration subtask
        iteration_task = SubTask(
            id="iteration_1",
            title=f"Iteration of: {action[:50]}",
            description=action,
            strategy=DecompositionStrategy.ITERATIVE,
            estimated_duration=self._estimate_duration(action),
        )
        
        root.children.append(iteration_task)
        
        estimated_per_iteration = iteration_task.estimated_duration
        total_duration = estimated_per_iteration * root.max_iterations
        
        return DecompositionResult(
            root_task=root,
            all_tasks=[root, iteration_task],
            strategy_used=DecompositionStrategy.ITERATIVE,
            confidence=0.65,
            estimated_duration=total_duration,
        )

    def _extract_title(self, text: str) -> str:
        """Extract a short title from text."""
        # Take first sentence or first 60 chars
        first_sentence = re.split(r"[.!?]", text)[0]
        title = first_sentence.strip()
        if len(title) > 60:
            title = title[:57] + "..."
        return title or text[:60]

    def _estimate_duration(self, text: str) -> int:
        """Estimate duration in seconds based on text complexity."""
        # Base duration on word count
        words = len(text.split())
        
        # More complex indicators
        complexity_score = 1.0
        if any(w in text.lower() for w in ["analyze", "research", "investigate"]):
            complexity_score *= 1.5
        if any(w in text.lower() for w in ["create", "build", "develop"]):
            complexity_score *= 1.3
        if any(w in text.lower() for w in ["simple", "quick", "basic"]):
            complexity_score *= 0.5
        if any(w in text.lower() for w in ["complex", "thorough", "detailed"]):
            complexity_score *= 2.0
        
        # Base estimate: 2 seconds per word for simple tasks
        duration = int(words * 2 * complexity_score)
        
        # Clamp to reasonable range
        return max(30, min(duration, 3600))
