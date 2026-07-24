"""
Knowledge Graph

Graph data structure for knowledge representation and traversal.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class Node:
    """A node in the knowledge graph."""
    id: str
    label: str
    type: str = ""
    properties: dict[str, Any] = field(default_factory=dict)
    weight: float = 1.0


@dataclass
class Edge:
    """An edge in the knowledge graph."""
    source: str
    target: str
    label: str = ""
    weight: float = 1.0
    properties: dict[str, Any] = field(default_factory=dict)


class KnowledgeGraph:
    """
    Knowledge graph for efficient traversal and queries.

    Features:
    - Node and edge management
    - BFS/DFS traversal
    - Path finding
    - Shortest path
    - Cycle detection
    """

    def __init__(self):
        self._nodes: dict[str, Node] = {}
        self._edges: dict[str, list[Edge]] = {}  # source -> edges
        self._reverse_edges: dict[str, list[Edge]] = {}  # target -> edges

    def add_node(self, node_id: str, node_type: str = "", **properties: Any) -> None:
        """Add a node to the graph."""
        if node_id not in self._nodes:
            self._nodes[node_id] = Node(id=node_id, label=node_id, type=node_type)
        else:
            self._nodes[node_id].type = node_type
        
        if properties:
            self._nodes[node_id].properties.update(properties)

        if node_id not in self._edges:
            self._edges[node_id] = []
        if node_id not in self._reverse_edges:
            self._reverse_edges[node_id] = []

    def add_edge(
        self,
        source: str,
        target: str,
        label: str = "",
        weight: float = 1.0,
        **properties: Any,
    ) -> None:
        """Add an edge to the graph."""
        # Ensure nodes exist
        self.add_node(source)
        self.add_node(target)

        edge = Edge(
            source=source,
            target=target,
            label=label,
            weight=weight,
            properties=properties,
        )

        self._edges[source].append(edge)
        self._reverse_edges[target].append(edge)

    def remove_node(self, node_id: str) -> bool:
        """Remove a node and its edges."""
        if node_id not in self._nodes:
            return False

        # Remove all edges involving this node
        if node_id in self._edges:
            for edge in self._edges[node_id]:
                target = edge.target
                if target in self._reverse_edges:
                    self._reverse_edges[target] = [
                        e for e in self._reverse_edges[target]
                        if e.source != node_id
                    ]
            del self._edges[node_id]

        if node_id in self._reverse_edges:
            for edge in self._reverse_edges[node_id]:
                source = edge.source
                if source in self._edges:
                    self._edges[source] = [
                        e for e in self._edges[source]
                        if e.target != node_id
                    ]
            del self._reverse_edges[node_id]

        del self._nodes[node_id]
        return True

    def remove_edge(self, source: str, target: str, label: Optional[str] = None) -> bool:
        """Remove an edge from the graph."""
        removed = False

        if source in self._edges:
            edges_to_remove = []
            for edge in self._edges[source]:
                if edge.target == target:
                    if label is None or edge.label == label:
                        edges_to_remove.append(edge)

            for edge in edges_to_remove:
                self._edges[source].remove(edge)
                if target in self._reverse_edges:
                    self._reverse_edges[target] = [
                        e for e in self._reverse_edges[target]
                        if e.source != source or e.label != edge.label
                    ]
                removed = True

        return removed

    def get_node(self, node_id: str) -> Optional[Node]:
        """Get a node by ID."""
        return self._nodes.get(node_id)

    def get_neighbors(self, node_id: str) -> list[str]:
        """Get all neighbors of a node."""
        neighbors = []
        for edge in self._edges.get(node_id, []):
            neighbors.append(edge.target)
        return neighbors

    def get_incoming_edges(self, node_id: str) -> list[Edge]:
        """Get all edges pointing to a node."""
        return self._reverse_edges.get(node_id, [])

    def get_outgoing_edges(self, node_id: str) -> list[Edge]:
        """Get all edges from a node."""
        return self._edges.get(node_id, [])

    def bfs(self, start_id: str, max_depth: int = 10) -> list[str]:
        """
        Breadth-first search from a starting node.

        Args:
            start_id: Starting node ID
            max_depth: Maximum traversal depth

        Returns:
            List of visited node IDs in BFS order
        """
        visited = set()
        queue = deque([(start_id, 0)])
        result = []

        while queue:
            node_id, depth = queue.popleft()

            if node_id in visited or depth > max_depth:
                continue

            visited.add(node_id)
            result.append(node_id)

            for edge in self._edges.get(node_id, []):
                if edge.target not in visited:
                    queue.append((edge.target, depth + 1))

        return result

    def dfs(self, start_id: str, max_depth: int = 10) -> list[str]:
        """
        Depth-first search from a starting node.

        Args:
            start_id: Starting node ID
            max_depth: Maximum traversal depth

        Returns:
            List of visited node IDs in DFS order
        """
        visited = set()
        result = []

        def dfs_recursive(node_id: str, depth: int):
            if node_id in visited or depth > max_depth:
                return

            visited.add(node_id)
            result.append(node_id)

            for edge in self._edges.get(node_id, []):
                if edge.target not in visited:
                    dfs_recursive(edge.target, depth + 1)

        dfs_recursive(start_id, 0)
        return result

    def find_paths(
        self,
        start_id: str,
        end_id: str,
        max_length: int = 5,
    ) -> list[list[str]]:
        """
        Find all paths between two nodes.

        Args:
            start_id: Starting node ID
            end_id: Ending node ID
            max_length: Maximum path length

        Returns:
            List of paths (each path is a list of node IDs)
        """
        paths = []

        def dfs_path(current: str, path: list[str]):
            if len(path) > max_length:
                return
            if current == end_id:
                paths.append(path.copy())
                return

            for edge in self._edges.get(current, []):
                if edge.target not in path:
                    path.append(edge.target)
                    dfs_path(edge.target, path)
                    path.pop()

        dfs_path(start_id, [start_id])
        return paths

    def shortest_path(self, start_id: str, end_id: str) -> Optional[list[str]]:
        """
        Find shortest path between two nodes using BFS.

        Args:
            start_id: Starting node ID
            end_id: Ending node ID

        Returns:
            Shortest path or None if no path exists
        """
        if start_id == end_id:
            return [start_id]

        visited = {start_id}
        queue = deque([(start_id, [start_id])])

        while queue:
            current, path = queue.popleft()

            for edge in self._edges.get(current, []):
                if edge.target == end_id:
                    return path + [edge.target]

                if edge.target not in visited:
                    visited.add(edge.target)
                    queue.append((edge.target, path + [edge.target]))

        return None

    def has_cycle(self) -> bool:
        """Check if the graph has a cycle."""
        visited = set()
        rec_stack = set()

        def dfs_cycle(node_id: str) -> bool:
            visited.add(node_id)
            rec_stack.add(node_id)

            for edge in self._edges.get(node_id, []):
                if edge.target not in visited:
                    if dfs_cycle(edge.target):
                        return True
                elif edge.target in rec_stack:
                    return True

            rec_stack.remove(node_id)
            return False

        for node_id in self._nodes:
            if node_id not in visited:
                if dfs_cycle(node_id):
                    return True

        return False

    def topological_sort(self) -> list[str]:
        """Return nodes in topological order (requires DAG)."""
        if self.has_cycle():
            raise ValueError("Cannot perform topological sort on a graph with cycles")

        in_degree = {node_id: 0 for node_id in self._nodes}
        for edges in self._edges.values():
            for edge in edges:
                in_degree[edge.target] = in_degree.get(edge.target, 0) + 1

        queue = deque([n for n, d in in_degree.items() if d == 0])
        result = []

        while queue:
            node_id = queue.popleft()
            result.append(node_id)

            for edge in self._edges.get(node_id, []):
                in_degree[edge.target] -= 1
                if in_degree[edge.target] == 0:
                    queue.append(edge.target)

        return result

    def subgraph(self, node_ids: set[str]) -> KnowledgeGraph:
        """Extract a subgraph containing only the specified nodes."""
        subgraph = KnowledgeGraph()

        for node_id in node_ids:
            if node_id in self._nodes:
                node = self._nodes[node_id]
                subgraph.add_node(node_id, node.type, **node.properties)

        for source, edges in self._edges.items():
            if source in node_ids:
                for edge in edges:
                    if edge.target in node_ids:
                        subgraph.add_edge(
                            edge.source,
                            edge.target,
                            edge.label,
                            edge.weight,
                            **edge.properties,
                        )

        return subgraph

    def to_adjacency_list(self) -> dict[str, list[tuple[str, str]]]:
        """Convert to adjacency list format."""
        result = {}
        for node_id in self._nodes:
            result[node_id] = [
                (edge.target, edge.label)
                for edge in self._edges.get(node_id, [])
            ]
        return result

    def __len__(self) -> int:
        """Get number of nodes."""
        return len(self._nodes)

    def __contains__(self, node_id: str) -> bool:
        """Check if node exists."""
        return node_id in self._nodes
