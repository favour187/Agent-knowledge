"""
Tool Registry

Central registry for AI tools with schema validation and documentation.
"""

from __future__ import annotations

import asyncio
import inspect
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional

import structlog

logger = structlog.get_logger(__name__)


class ToolCategory(str, Enum):
    """Categories for organizing tools."""
    FILESYSTEM = "filesystem"
    TERMINAL = "terminal"
    WEB = "web"
    DATA = "data"
    COMMUNICATION = "communication"
    MEDIA = "media"
    CODE = "code"
    UTILITY = "utility"
    CUSTOM = "custom"


class ParameterType(str, Enum):
    """JSON Schema parameter types."""
    STRING = "string"
    NUMBER = "number"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"


@dataclass
class Parameter:
    """A tool parameter definition."""
    name: str
    type: ParameterType
    description: str = ""
    required: bool = False
    default: Any = None
    enum: Optional[list[Any]] = None
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    items: Optional[dict[str, Any]] = None
    properties: Optional[dict[str, Any]] = None

    def to_schema(self) -> dict[str, Any]:
        """Convert to JSON Schema format."""
        schema: dict[str, Any] = {
            "type": self.type.value,
            "description": self.description,
        }

        if self.default is not None:
            schema["default"] = self.default
        if self.enum:
            schema["enum"] = self.enum
        if self.minimum is not None:
            schema["minimum"] = self.minimum
        if self.maximum is not None:
            schema["maximum"] = self.maximum
        if self.items:
            schema["items"] = self.items
        if self.properties:
            schema["properties"] = self.properties

        return schema


@dataclass
class ToolSchema:
    """Schema for a tool's input parameters."""
    parameters: list[Parameter] = field(default_factory=list)

    def to_json_schema(self) -> dict[str, Any]:
        """Convert to OpenAI function calling format."""
        properties = {}
        required = []

        for param in self.parameters:
            properties[param.name] = param.to_schema()
            if param.required:
                required.append(param.name)

        return {
            "type": "object",
            "properties": properties,
            "required": required if required else None,
        }

    def validate(self, arguments: dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Validate arguments against schema."""
        for param in self.parameters:
            if param.required and param.name not in arguments:
                return False, f"Missing required parameter: {param.name}"

            if param.name in arguments:
                value = arguments[param.name]

                # Type checking
                expected_type = param.type.value
                if expected_type == "string" and not isinstance(value, str):
                    return False, f"{param.name} must be a string"
                elif expected_type == "number" and not isinstance(value, (int, float)):
                    return False, f"{param.name} must be a number"
                elif expected_type == "integer" and not isinstance(value, int):
                    return False, f"{param.name} must be an integer"
                elif expected_type == "boolean" and not isinstance(value, bool):
                    return False, f"{param.name} must be a boolean"
                elif expected_type == "array" and not isinstance(value, list):
                    return False, f"{param.name} must be an array"

                # Enum checking
                if param.enum and value not in param.enum:
                    return False, f"{param.name} must be one of: {param.enum}"

                # Range checking
                if isinstance(value, (int, float)):
                    if param.minimum is not None and value < param.minimum:
                        return False, f"{param.name} must be >= {param.minimum}"
                    if param.maximum is not None and value > param.maximum:
                        return False, f"{param.name} must be <= {param.maximum}"

        return True, None


@dataclass
class ToolResult:
    """Result of a tool execution."""
    success: bool
    output: Any = None
    error: Optional[str] = None
    execution_time: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Tool:
    """
    A callable tool that AI models can use.

    Attributes:
        name: Unique tool name
        description: What the tool does
        category: Tool category
        schema: Parameter schema
        function: The async function to execute
        requires_confirmation: Whether to require user confirmation
        rate_limit: Maximum calls per minute
        permissions: Required permissions
        examples: Example usage
    """
    name: str
    description: str
    category: ToolCategory = ToolCategory.UTILITY
    schema: Optional[ToolSchema] = None
    function: Optional[Callable[..., Any]] = None
    requires_confirmation: bool = False
    rate_limit: Optional[int] = None  # calls per minute
    permissions: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    # Internal state
    _call_count: int = 0
    _last_reset: datetime = field(default_factory=datetime.utcnow)
    _call_history: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self):
        """Initialize derived fields."""
        if not self.schema and self.function:
            self.schema = self._infer_schema()

    def _infer_schema(self) -> ToolSchema:
        """Infer schema from function signature."""
        if not self.function:
            return ToolSchema()

        sig = inspect.signature(self.function)
        parameters = []

        for name, param in sig.parameters.items():
            if name in ("self", "context"):
                continue

            # Determine type
            param_type = ParameterType.STRING
            if param.annotation == int:
                param_type = ParameterType.INTEGER
            elif param.annotation == float:
                param_type = ParameterType.NUMBER
            elif param.annotation == bool:
                param_type = ParameterType.BOOLEAN
            elif param.annotation in (list, tuple):
                param_type = ParameterType.ARRAY
            elif param.annotation == dict:
                param_type = ParameterType.OBJECT

            parameters.append(
                Parameter(
                    name=name,
                    type=param_type,
                    description=param.default.__doc__ if param.default else "",
                    required=param.default == inspect.Parameter.empty,
                    default=param.default if param.default != inspect.Parameter.empty else None,
                )
            )

        return ToolSchema(parameters=parameters)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category.value,
            "schema": self.schema.to_json_schema() if self.schema else {},
            "requires_confirmation": self.requires_confirmation,
            "rate_limit": self.rate_limit,
            "examples": self.examples,
            "metadata": self.metadata,
        }

    def to_openai_format(self) -> dict[str, Any]:
        """Convert to OpenAI function format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.schema.to_json_schema() if self.schema else {
                    "type": "object",
                    "properties": {},
                },
            },
        }

    def _record_call(self, arguments: dict[str, Any], result: ToolResult) -> None:
        """Record a tool call for analytics."""
        self._call_count += 1
        self._call_history.append({
            "timestamp": datetime.utcnow().isoformat(),
            "arguments": arguments,
            "success": result.success,
            "execution_time": result.execution_time,
        })

        # Keep only last 100 calls
        if len(self._call_history) > 100:
            self._call_history = self._call_history[-100:]

    def get_stats(self) -> dict[str, Any]:
        """Get tool usage statistics."""
        return {
            "name": self.name,
            "total_calls": self._call_count,
            "recent_calls": len(self._call_history),
            "success_rate": (
                sum(1 for c in self._call_history if c["success"]) / len(self._call_history)
                if self._call_history else 0
            ),
            "avg_execution_time": (
                sum(c["execution_time"] for c in self._call_history) / len(self._call_history)
                if self._call_history else 0
            ),
        }


class ToolRegistry:
    """
    Central registry for AI tools.

    Features:
    - Dynamic tool registration
    - Schema validation
    - Rate limiting
    - Usage tracking
    - Tool discovery
    - Permission management
    """

    def __init__(self):
        self.tools: dict[str, Tool] = {}
        self._rate_limiters: dict[str, asyncio.Semaphore] = {}
        self._lock = asyncio.Lock()
        self._permission_checks: dict[str, Callable] = {}

        # Load built-in tools
        self._register_builtin_tools()

        logger.info("tool_registry_initialized")

    def _register_builtin_tools(self) -> None:
        """Register built-in utility tools from the tools/ package.

        tools.base.BaseTool subclasses already provide a working async
        .execute(**kwargs) -> ToolResult wrapper; we adapt that to the
        Callable[..., Any] shape core.tool_manager.registry.Tool.function
        expects (returning the ToolResult itself so callers get success/error
        info, not just raw output).
        """
        try:
            from tools.filesystem import FileSystemTool
            from tools.web_search import WebSearchTool
        except ImportError as e:
            logger.warning("builtin_tools_unavailable", error=str(e))
            return

        def _adapt(base_tool: Any) -> Callable[..., Any]:
            async def _run(**kwargs: Any) -> Any:
                return await base_tool.execute(**kwargs)
            return _run

        def _schema_from(base_tool: Any) -> ToolSchema:
            # tools.base.ToolParameter -> core.tool_manager.registry.Parameter
            params = []
            for p in base_tool.parameters:
                params.append(
                    Parameter(
                        name=p.name,
                        type=ParameterType(p.type.value),
                        description=p.description,
                        required=p.required,
                        default=p.default,
                        enum=p.enum,
                    )
                )
            return ToolSchema(parameters=params)

        fs_tool = FileSystemTool()
        self.register(
            name=fs_tool.name,
            description=fs_tool.description,
            function=_adapt(fs_tool),
            category=ToolCategory.FILESYSTEM,
            schema=_schema_from(fs_tool),
            requires_confirmation=fs_tool.requires_confirmation,
        )

        web_tool = WebSearchTool()
        self.register(
            name=web_tool.name,
            description=web_tool.description,
            function=_adapt(web_tool),
            category=ToolCategory.WEB,
            schema=_schema_from(web_tool),
            requires_confirmation=web_tool.requires_confirmation,
        )

    def register(
        self,
        name: str,
        description: str,
        function: Callable,
        category: ToolCategory = ToolCategory.UTILITY,
        schema: Optional[ToolSchema] = None,
        **kwargs: Any,
    ) -> Tool:
        """
        Register a new tool.

        Args:
            name: Tool name
            description: Tool description
            function: Async function to execute
            category: Tool category
            schema: Parameter schema
            **kwargs: Additional tool options

        Returns:
            Created Tool
        """
        tool = Tool(
            name=name,
            description=description,
            function=function,
            category=category,
            schema=schema,
            **kwargs,
        )

        self.tools[name] = tool

        if tool.rate_limit:
            self._rate_limiters[name] = asyncio.Semaphore(tool.rate_limit)

        logger.info("tool_registered", name=name, category=category.value)
        return tool

    def register_decorator(
        self,
        name: Optional[str] = None,
        description: str = "",
        category: ToolCategory = ToolCategory.UTILITY,
        **kwargs: Any,
    ) -> Callable:
        """
        Decorator to register a function as a tool.

        Usage:
            @registry.register_decorator(name="my_tool", description="Does something")
            async def my_tool(arg1: str) -> str:
                return f"Processed: {arg1}"
        """
        def decorator(func: Callable) -> Callable:
            tool_name = name or func.__name__
            tool_desc = description or func.__doc__ or ""
            self.register(
                name=tool_name,
                description=tool_desc,
                function=func,
                category=category,
                **kwargs,
            )
            return func
        return decorator

    def get_tool(self, name: str) -> Optional[Tool]:
        """Get a tool by name."""
        return self.tools.get(name)

    def list_tools(
        self,
        category: Optional[ToolCategory] = None,
        has_permission: Optional[Callable[[str], bool]] = None,
    ) -> list[Tool]:
        """List all tools, optionally filtered."""
        tools = list(self.tools.values())

        if category:
            tools = [t for t in tools if t.category == category]

        if has_permission:
            tools = [t for t in tools if has_permission(t.name)]

        return sorted(tools, key=lambda t: t.name)

    def get_tool_schemas(
        self,
        names: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        """Get tool schemas for AI function calling."""
        if names:
            tools = [self.tools[n] for n in names if n in self.tools]
        else:
            tools = list(self.tools.values())

        return [t.to_openai_format() for t in tools]

    def unregister(self, name: str) -> bool:
        """Unregister a tool."""
        if name in self.tools:
            del self.tools[name]
            if name in self._rate_limiters:
                del self._rate_limiters[name]
            logger.info("tool_unregistered", name=name)
            return True
        return False

    async def execute(
        self,
        name: str,
        arguments: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
    ) -> ToolResult:
        """
        Execute a tool.

        Args:
            name: Tool name
            arguments: Tool arguments
            context: Execution context

        Returns:
            ToolResult
        """
        import time
        start_time = time.time()

        tool = self.get_tool(name)
        if not tool:
            return ToolResult(
                success=False,
                error=f"Tool not found: {name}",
            )

        # Check rate limit
        if name in self._rate_limiters:
            try:
                async with asyncio.timeout(1.0):  # 1 second max wait
                    await self._rate_limiters[name].acquire()
            except asyncio.TimeoutError:
                return ToolResult(
                    success=False,
                    error="Rate limit exceeded",
                )

        # Validate schema
        if tool.schema:
            valid, error = tool.schema.validate(arguments)
            if not valid:
                return ToolResult(
                    success=False,
                    error=f"Validation error: {error}",
                )

        # Check permissions
        if tool.permissions:
            for permission in tool.permissions:
                checker = self._permission_checks.get(permission)
                if checker and not checker(name):
                    return ToolResult(
                        success=False,
                        error=f"Permission denied: {permission}",
                    )

        # Execute
        try:
            if asyncio.iscoroutinefunction(tool.function):
                result = await tool.function(**arguments)
            else:
                result = tool.function(**arguments)

            execution_time = time.time() - start_time

            tool_result = ToolResult(
                success=True,
                output=result,
                execution_time=execution_time,
            )

            tool._record_call(arguments, tool_result)
            return tool_result

        except Exception as e:
            execution_time = time.time() - start_time
            logger.error("tool_execution_failed", tool=name, error=str(e))

            tool_result = ToolResult(
                success=False,
                error=str(e),
                execution_time=execution_time,
            )

            tool._record_call(arguments, tool_result)
            return tool_result

    def set_permission_checker(
        self,
        permission: str,
        checker: Callable[[str], bool],
    ) -> None:
        """Set a permission checker function."""
        self._permission_checks[permission] = checker

    def get_stats(self) -> dict[str, Any]:
        """Get registry statistics."""
        by_category = {}
        for tool in self.tools.values():
            cat = tool.category.value
            by_category[cat] = by_category.get(cat, 0) + 1

        return {
            "total_tools": len(self.tools),
            "by_category": by_category,
            "total_calls": sum(t._call_count for t in self.tools.values()),
        }
