"""
Base Tool Classes

Base classes and utilities for tool implementations.
"""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional

import structlog

logger = structlog.get_logger(__name__)


class ParameterType(str, Enum):
    """Parameter types."""
    STRING = "string"
    NUMBER = "number"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"


@dataclass
class ToolParameter:
    """Definition of a tool parameter."""
    name: str
    type: ParameterType
    description: str = ""
    required: bool = False
    default: Any = None
    enum: Optional[list[Any]] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "type": self.type.value,
            "description": self.description,
        }
        if self.default is not None:
            result["default"] = self.default
        if self.enum:
            result["enum"] = self.enum
        return result


@dataclass
class ToolResult:
    """Result of a tool execution."""
    success: bool
    output: Any = None
    error: Optional[str] = None
    execution_time: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseTool:
    """
    Base class for all tools.

    Attributes:
        name: Tool name
        description: What the tool does
        parameters: List of parameter definitions
        requires_confirmation: Whether to require user confirmation
    """

    name: str = ""
    description: str = ""
    parameters: list[ToolParameter] = []
    requires_confirmation: bool = False

    def __init__(self):
        if not self.name:
            self.name = self.__class__.__name__

    async def execute(self, **kwargs: Any) -> ToolResult:
        """
        Execute the tool.

        Args:
            **kwargs: Tool arguments

        Returns:
            ToolResult
        """
        import time
        start_time = time.time()

        try:
            # Validate parameters
            for param in self.parameters:
                if param.required and param.name not in kwargs:
                    return ToolResult(
                        success=False,
                        error=f"Missing required parameter: {param.name}",
                    )

            # Execute
            if asyncio.iscoroutinefunction(self._execute):
                output = await self._execute(**kwargs)
            else:
                output = self._execute(**kwargs)

            return ToolResult(
                success=True,
                output=output,
                execution_time=time.time() - start_time,
            )

        except Exception as e:
            logger.error("tool_execution_error", tool=self.name, error=str(e))
            return ToolResult(
                success=False,
                error=str(e),
                execution_time=time.time() - start_time,
            )

    def _execute(self, **kwargs: Any) -> Any:
        """Internal execute method to override."""
        raise NotImplementedError("Subclasses must implement _execute")

    def get_schema(self) -> dict[str, Any]:
        """Get the tool schema."""
        properties = {}
        required = []

        for param in self.parameters:
            properties[param.name] = param.to_dict()
            if param.required:
                required.append(param.name)

        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required if required else None,
            },
        }
