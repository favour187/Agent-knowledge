"""Workspace Routes - Sandbox workspace for file management and code execution.

Provides endpoints for:
- Workspace file tree browsing
- File read/write/create/delete
- Sandbox code execution (Python, JS, Bash)
- Workspace-scoped tool execution
"""

from __future__ import annotations

import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.state import app_state
from database.db import get_db
from database.models import ToolExecution

router = APIRouter()

# Workspace root — configurable via env, defaults to a safe directory
WORKSPACE_ROOT = Path(os.getenv("ARENA_WORKSPACE_ROOT", "/tmp/arena-workspace"))
WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)


# ---------- Pydantic models ----------


class FileNode(BaseModel):
    """A file or directory in the workspace tree."""
    name: str
    path: str  # relative to workspace root
    is_dir: bool
    size: Optional[int] = None
    modified: Optional[str] = None
    children: Optional[list["FileNode"]] = None


class FileReadResponse(BaseModel):
    """Response for reading a file."""
    path: str
    content: str
    size: int
    modified: str


class FileWriteRequest(BaseModel):
    """Request to write/create a file."""
    path: str
    content: str


class FileWriteResponse(BaseModel):
    """Response after writing a file."""
    path: str
    size: int
    success: bool


class DirCreateRequest(BaseModel):
    """Request to create a directory."""
    path: str


class FileDeleteRequest(BaseModel):
    """Request to delete a file or directory."""
    path: str


class CodeExecutionRequest(BaseModel):
    """Request to execute code in the sandbox."""
    code: str
    language: str = "python"
    timeout: float = 30.0


class CodeExecutionResponse(BaseModel):
    """Response from sandbox code execution."""
    success: bool
    output: str = ""
    error: Optional[str] = None
    exit_code: int = 0
    execution_time: float = 0.0
    language: str = ""


class WorkspaceStatsResponse(BaseModel):
    """Workspace overview stats."""
    total_files: int
    total_dirs: int
    total_size: int
    recent_files: list[dict[str, Any]]


# ---------- Helpers ----------


def _resolve_safe(rel_path: str) -> Path:
    """Resolve a relative path safely within the workspace root."""
    resolved = (WORKSPACE_ROOT / rel_path).resolve()
    if not str(resolved).startswith(str(WORKSPACE_ROOT.resolve())):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Path traversal not allowed",
        )
    return resolved


def _build_tree(dir_path: Path, rel_base: str = "") -> list[FileNode]:
    """Recursively build a file tree for the given directory."""
    nodes: list[FileNode] = []
    try:
        entries = sorted(dir_path.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
    except PermissionError:
        return nodes

    for entry in entries:
        rel = os.path.join(rel_base, entry.name) if rel_base else entry.name
        if entry.is_dir():
            children = _build_tree(entry, rel)
            nodes.append(
                FileNode(
                    name=entry.name,
                    path=rel,
                    is_dir=True,
                    children=children,
                )
            )
        else:
            stat = entry.stat()
            nodes.append(
                FileNode(
                    name=entry.name,
                    path=rel,
                    is_dir=False,
                    size=stat.st_size,
                    modified=datetime.fromtimestamp(stat.st_mtime).isoformat(),
                )
            )
    return nodes


def _count_tree(nodes: list[FileNode]) -> tuple[int, int, int]:
    """Count files, dirs, and total size from a tree."""
    files, dirs, size = 0, 0, 0
    for n in nodes:
        if n.is_dir:
            dirs += 1
            f, d, s = _count_tree(n.children or [])
            files += f
            dirs += d
            size += s
        else:
            files += 1
            size += n.size or 0
    return files, dirs, size


def _get_recent_files(dir_path: Path, limit: int = 10) -> list[dict[str, Any]]:
    """Get the most recently modified files."""
    all_files: list[tuple[float, Path]] = []
    for root, _, filenames in os.walk(dir_path):
        for fname in filenames:
            fpath = Path(root) / fname
            try:
                all_files.append((fpath.stat().st_mtime, fpath))
            except OSError:
                continue

    all_files.sort(key=lambda x: x[0], reverse=True)
    result = []
    for mtime, fpath in all_files[:limit]:
        rel = str(fpath.relative_to(WORKSPACE_ROOT))
        result.append({
            "name": fpath.name,
            "path": rel,
            "size": fpath.stat().st_size,
            "modified": datetime.fromtimestamp(mtime).isoformat(),
        })
    return result


# ---------- Routes ----------


@router.get("/tree", response_model=list[FileNode])
async def get_file_tree(path: str = "") -> list[FileNode]:
    """Get the workspace file tree."""
    dir_path = _resolve_safe(path) if path else WORKSPACE_ROOT
    if not dir_path.is_dir():
        raise HTTPException(status_code=404, detail="Directory not found")
    return _build_tree(dir_path, rel_base=path)


@router.get("/file", response_model=FileReadResponse)
async def read_file(path: str) -> FileReadResponse:
    """Read a file from the workspace."""
    file_path = _resolve_safe(path)
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read file: {e}")

    stat = file_path.stat()
    return FileReadResponse(
        path=path,
        content=content,
        size=stat.st_size,
        modified=datetime.fromtimestamp(stat.st_mtime).isoformat(),
    )


@router.post("/file", response_model=FileWriteResponse)
async def write_file(request: FileWriteRequest) -> FileWriteResponse:
    """Write/create a file in the workspace."""
    file_path = _resolve_safe(request.path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        file_path.write_text(request.content, encoding="utf-8")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to write file: {e}")

    return FileWriteResponse(
        path=request.path,
        size=file_path.stat().st_size,
        success=True,
    )


@router.post("/directory")
async def create_directory(request: DirCreateRequest) -> dict[str, Any]:
    """Create a directory in the workspace."""
    dir_path = _resolve_safe(request.path)
    dir_path.mkdir(parents=True, exist_ok=True)
    return {"path": request.path, "success": True}


@router.delete("/file")
async def delete_file(path: str) -> dict[str, Any]:
    """Delete a file or empty directory from the workspace."""
    target = _resolve_safe(path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="Path not found")

    try:
        if target.is_dir():
            import shutil
            shutil.rmtree(target)
        else:
            target.unlink()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete: {e}")

    return {"path": path, "success": True}


@router.post("/execute", response_model=CodeExecutionResponse)
async def execute_code(
    request: CodeExecutionRequest,
    db: AsyncSession = Depends(get_db),
) -> CodeExecutionResponse:
    """Execute code in the sandbox environment."""
    from core.tool_manager.sandbox import Sandbox, SandboxConfig

    config = SandboxConfig(timeout=request.timeout)
    sandbox = Sandbox(config)

    start = time.time()
    result = await sandbox.execute(request.code, request.language)
    duration_ms = int((time.time() - start) * 1000)

    # Record execution
    db.add(
        ToolExecution(
            tool_name=f"sandbox:{request.language}",
            input={"code": request.code[:500], "language": request.language},
            output={"stdout": result.stdout[:2000]} if result.stdout else None,
            error=result.error,
            duration_ms=duration_ms,
            success=result.success,
        )
    )
    await db.commit()

    return CodeExecutionResponse(
        success=result.success,
        output=result.output or result.stdout,
        error=result.error,
        exit_code=result.exit_code,
        execution_time=result.execution_time,
        language=request.language,
    )


@router.get("/stats", response_model=WorkspaceStatsResponse)
async def get_stats() -> WorkspaceStatsResponse:
    """Get workspace overview statistics."""
    tree = _build_tree(WORKSPACE_ROOT)
    files, dirs, total_size = _count_tree(tree)
    recent = _get_recent_files(WORKSPACE_ROOT)
    return WorkspaceStatsResponse(
        total_files=files,
        total_dirs=dirs,
        total_size=total_size,
        recent_files=recent,
    )
