"""Filesystem Tool - File system operations."""

import os
from pathlib import Path
from typing import Any

import aiofiles

from tools.base import BaseTool, ToolParameter, ParameterType


class FileSystemTool(BaseTool):
    """Tool for filesystem operations."""

    name = "filesystem"
    description = "Perform filesystem operations like reading, writing, and listing files"
    parameters = [
        ToolParameter(
            name="operation",
            type=ParameterType.STRING,
            description="Operation to perform: read, write, list, exists, mkdir, rm",
            required=True,
            enum=["read", "write", "list", "exists", "mkdir", "rm"],
        ),
        ToolParameter(
            name="path",
            type=ParameterType.STRING,
            description="File or directory path",
            required=True,
        ),
        ToolParameter(
            name="content",
            type=ParameterType.STRING,
            description="Content to write (for write operation)",
            required=False,
        ),
    ]

    def _execute(self, operation: str, path: str, content: str = "") -> Any:
        """Execute filesystem operation."""
        path = Path(path)

        if operation == "read":
            if not path.exists():
                return {"error": f"File not found: {path}"}
            if path.is_dir():
                return {"error": "Path is a directory, use 'list' instead"}

            with open(path, "r") as f:
                return {"content": f.read(), "size": path.stat().st_size}

        elif operation == "write":
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w") as f:
                f.write(content)
            return {"path": str(path), "bytes_written": len(content)}

        elif operation == "list":
            if not path.exists():
                return {"error": f"Path not found: {path}"}
            if not path.is_dir():
                return {"error": "Path is not a directory"}

            items = []
            for item in path.iterdir():
                items.append({
                    "name": item.name,
                    "type": "dir" if item.is_dir() else "file",
                    "size": item.stat().st_size if item.is_file() else 0,
                })
            return {"items": items, "count": len(items)}

        elif operation == "exists":
            return {"exists": path.exists(), "is_file": path.is_file(), "is_dir": path.is_dir()}

        elif operation == "mkdir":
            path.mkdir(parents=True, exist_ok=True)
            return {"path": str(path), "created": True}

        elif operation == "rm":
            if not path.exists():
                return {"error": f"Path not found: {path}"}
            if path.is_file():
                path.unlink()
            else:
                import shutil
                shutil.rmtree(path)
            return {"path": str(path), "removed": True}

        return {"error": f"Unknown operation: {operation}"}
