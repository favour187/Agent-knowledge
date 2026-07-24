"""
Tree of Thought Reasoning

Implements tree-of-thought exploration with multiple reasoning branches.
"""

from __future__ import annotations

import json
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

import structlog

from core.ai_runtime.engine import AIRuntime, Message, MessageRole

logger = structlog.get_logger(__name__)


class NodeStatus(str, Enum):
    """Status of a tree node."""
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    PRUNED = "pruned"
    FAILED = "failed"


@dataclass
class ToTNode:
    """A node in the thought tree."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    parent_id: Optional[str] = None
    thought: str = ""
    reasoning: str = ""
    value: float = 0.0  # Estimated value of this path
    status: NodeStatus = NodeStatus.PENDING
    depth: int = 0
    children: list[str] = field(default_factory=list)
    visits: int = 0
    q_value: float = 0.0  # Average reward
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "parent_id": self.parent_id,
            "thought": self.thought,
            "reasoning": self.reasoning,
            "value": self.value,
            "status": self.status.value,
            "depth": self.depth,
            "children": self.children,
            "visits": self.visits,
            "q_value": self.q_value,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


@dataclass
class ToTResult:
    """Result of tree-of-thought exploration."""
    success: bool
    best_path: list[ToTNode]
    best_answer: str
    all_paths: list[list[ToTNode]]
    explored_nodes: int
    pruned_nodes: int
    execution_time: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "best_path": [n.to_dict() for n in self.best_path],
            "best_answer": self.best_answer,
            "all_paths": [[n.to_dict() for n in path] for path in self.all_paths],
            "explored_nodes": self.explored_nodes,
            "pruned_nodes": self.pruned_nodes,
            "execution_time": self.execution_time,
            "metadata": self.metadata,
        }


class TreeOfThought:
    """
    Tree-of-thought reasoning with Monte Carlo Tree Search (MCTS) style exploration.

    Features:
    - Multiple reasoning branches
    - MCTS-based exploration/exploitation balance
    - Automatic pruning of poor paths
    - Path evaluation and selection
    - Parallel exploration support
    """

    def __init__(
        self,
        ai_runtime: Optional[AIRuntime] = None,
        exploration_constant: float = 1.414,
    ):
        self.ai_runtime = ai_runtime
        self.exploration_constant = exploration_constant
        self.nodes: dict[str, ToTNode] = {}
        self.root_id: Optional[str] = None

    def reset(self) -> None:
        """Reset the tree."""
        self.nodes.clear()
        self.root_id = None

    async def explore(
        self,
        problem: str,
        context: Optional[dict[str, Any]] = None,
        max_depth: int = 5,
        branching_factor: int = 3,
        max_nodes: int = 50,
        prune_threshold: float = 0.3,
    ) -> ToTResult:
        """
        Explore the thought tree.

        Args:
            problem: The problem to solve
            context: Optional context information
            max_depth: Maximum tree depth
            branching_factor: Number of branches per node
            max_nodes: Maximum nodes to explore
            prune_threshold: Prune paths below this value

        Returns:
            ToTResult with best path and alternatives
        """
        import time
        start_time = time.time()

        logger.info(
            "tot_explore_started",
            problem=problem[:100],
            max_depth=max_depth,
            branching_factor=branching_factor,
        )

        self.reset()

        # Create root node
        root = ToTNode(
            thought="Start",
            reasoning=f"Problem: {problem}",
            depth=0,
        )
        self.nodes[root.id] = root
        self.root_id = root.id

        # Generate initial branches
        await self._expand_node(root.id, problem, context, branching_factor)

        # MCTS-style exploration
        explored = 0
        pruned = 0

        while explored < max_nodes and self._has_pending_nodes():
            # Select next node using UCB1
            node_id = self._select_node()
            if not node_id:
                break

            node = self.nodes[node_id]
            node.status = NodeStatus.ACTIVE

            # Expand if not at max depth
            if node.depth < max_depth:
                await self._expand_node(
                    node_id,
                    problem,
                    context,
                    branching_factor,
                )

            # Simulate and backpropagate
            await self._simulate_and_backpropagate(node_id)

            # Prune low-value paths
            pruned += self._prune_paths(prune_threshold)

            explored += 1

        # Find best path
        best_path = self._get_best_path()
        all_paths = self._get_all_completed_paths()

        execution_time = time.time() - start_time

        return ToTResult(
            success=len(best_path) > 0,
            best_path=best_path,
            best_answer=best_path[-1].thought if best_path else "",
            all_paths=all_paths,
            explored_nodes=explored,
            pruned_nodes=pruned,
            execution_time=execution_time,
        )

    def _has_pending_nodes(self) -> bool:
        """Check if there are pending nodes to explore."""
        return any(n.status == NodeStatus.PENDING for n in self.nodes.values())

    def _select_node(self) -> Optional[str]:
        """Select next node using UCB1."""
        pending = [n.id for n in self.nodes.values() if n.status == NodeStatus.PENDING]
        if not pending:
            return None

        # UCB1: exploitation + exploration
        best_id = None
        best_ucb = float('-inf')
        parent_visits = sum(n.visits for n in self.nodes.values())

        for node_id in pending:
            node = self.nodes[node_id]
            if node.visits == 0:
                ucb = float('inf')  # Prioritize unvisited
            else:
                ucb = node.q_value + self.exploration_constant * (
                    (2 * (parent_visits ** 0.5) / node.visits) ** 0.5
                )

            if ucb > best_ucb:
                best_ucb = ucb
                best_id = node_id

        return best_id

    async def _expand_node(
        self,
        node_id: str,
        problem: str,
        context: Optional[dict[str, Any]],
        branching_factor: int,
    ) -> None:
        """Expand a node with child thoughts."""
        node = self.nodes[node_id]

        if not self.ai_runtime:
            return

        context_text = ""
        if context:
            context_text = "\n\nContext:\n" + json.dumps(context, indent=2)

        # Build prompt for generating branches
        prompt = f"""Given the current reasoning state:

Current Thought: {node.thought}
Reasoning: {node.reasoning}
Problem: {problem}{context_text}

Generate {branching_factor} different possible next thoughts or approaches:

Provide in JSON format:
{{
    "branches": [
        {{
            "thought": "Brief description of the next thought",
            "reasoning": "Why this approach might work",
            "estimated_value": 0.0-1.0
        }}
    ]
}}"""

        messages = [
            Message(role=MessageRole.USER, content=prompt),
        ]

        try:
            response = await self.ai_runtime.complete(
                messages=messages,
                model="gpt-4-turbo-preview",
            )

            data = json.loads(response.content)
            branches = data.get("branches", [])

            for branch_data in branches[:branching_factor]:
                child = ToTNode(
                    parent_id=node_id,
                    thought=branch_data.get("thought", ""),
                    reasoning=branch_data.get("reasoning", ""),
                    value=branch_data.get("estimated_value", 0.5),
                    depth=node.depth + 1,
                )
                self.nodes[child.id] = child
                node.children.append(child.id)

            node.status = NodeStatus.COMPLETED
            node.completed_at = datetime.utcnow()

        except (json.JSONDecodeError, Exception) as e:
            logger.warning("tot_expansion_failed", error=str(e))
            node.status = NodeStatus.FAILED

    async def _simulate_and_backpropagate(self, node_id: str) -> None:
        """Simulate outcome and backpropagate value."""
        node = self.nodes[node_id]

        # Evaluate the node
        if self.ai_runtime and node.children:
            # Use best child's value
            best_child = max(
                [self.nodes[cid] for cid in node.children if cid in self.nodes],
                key=lambda n: n.value,
                default=node,
            )
            reward = best_child.value
        else:
            reward = node.value

        # Backpropagate
        current = node
        while current:
            current.visits += 1
            # Update Q-value (running average)
            current.q_value = (
                (current.q_value * (current.visits - 1) + reward) / current.visits
            )
            current = self.nodes.get(current.parent_id) if current.parent_id else None

    def _prune_paths(self, threshold: float) -> int:
        """Prune paths below threshold value."""
        pruned = 0

        for node in self.nodes.values():
            if node.status == NodeStatus.PENDING and node.q_value < threshold:
                node.status = NodeStatus.PRUNED
                pruned += 1

        return pruned

    def _get_best_path(self) -> list[ToTNode]:
        """Get the best path from root to leaf."""
        if not self.root_id:
            return []

        # Find leaf with highest Q-value
        leaves = [
            n for n in self.nodes.values()
            if n.status in (NodeStatus.COMPLETED, NodeStatus.PRUNED)
            and not n.children
        ]

        if not leaves:
            return []

        best_leaf = max(leaves, key=lambda n: n.q_value)

        # Reconstruct path
        path = []
        current = best_leaf
        while current:
            path.insert(0, current)
            current = self.nodes.get(current.parent_id) if current.parent_id else None

        return path

    def _get_all_completed_paths(self) -> list[list[ToTNode]]:
        """Get all completed paths."""
        paths = []

        leaves = [
            n for n in self.nodes.values()
            if n.status == NodeStatus.COMPLETED and not n.children
        ]

        for leaf in leaves:
            path = []
            current = leaf
            while current:
                path.insert(0, current)
                current = self.nodes.get(current.parent_id) if current.parent_id else None
            paths.append(path)

        # Sort by total value
        paths.sort(key=lambda p: sum(n.q_value for n in p), reverse=True)

        return paths[:5]  # Return top 5 paths

    def visualize(self) -> str:
        """Generate ASCII visualization of the tree."""
        if not self.root_id:
            return "Empty tree"

        lines = []
        queue = deque([(self.root_id, 0)])

        while queue:
            node_id, depth = queue.popleft()
            node = self.nodes.get(node_id)
            if not node:
                continue

            prefix = "  " * depth
            status_icon = {
                NodeStatus.PENDING: "○",
                NodeStatus.ACTIVE: "◉",
                NodeStatus.COMPLETED: "✓",
                NodeStatus.PRUNED: "✗",
                NodeStatus.FAILED: "⚠",
            }.get(node.status, "?")

            lines.append(
                f"{prefix}{status_icon} [{node.q_value:.2f}] {node.thought[:50]}"
            )

            for child_id in node.children:
                queue.append((child_id, depth + 1))

        return "\n".join(lines)
