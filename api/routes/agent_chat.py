"""
Autonomous Agent Chat API

The agent receives a message, thinks, decides what tools to use,
executes them automatically, and returns the result.

This is the core "it just works" endpoint — like Arena.ai.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.state import app_state
from core.ai_runtime.providers.local import LocalModelProvider, detect_tool_call

router = APIRouter()

# ── Local model singleton ──────────────────────────────────────────
_local_model: Optional[LocalModelProvider] = None

REPO_ROOT = Path(__file__).parent.parent.parent


def _get_local_model() -> LocalModelProvider:
    global _local_model
    if _local_model is None:
        # Find the best available adapter
        adapter_dir = REPO_ROOT / "adapters"
        adapter_path = None
        if adapter_dir.exists():
            # Find the most recent adapter
            adapters = sorted(adapter_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
            for adir in adapters:
                export_path = adir / "export" / "hf"
                if export_path.exists() and (export_path / "adapter_config.json").exists():
                    adapter_path = str(export_path)
                    break
                adapter_file = adir / "adapter"
                if adapter_file.exists() and (adapter_file / "adapter_config.json").exists():
                    adapter_path = str(adapter_file)
                    break

        base_model = os.getenv("ARENA_BASE_MODEL", str(REPO_ROOT / "models" / "gpt2-local"))
        _local_model = LocalModelProvider(
            base_model_path=base_model,
            adapter_path=adapter_path,
        )
    return _local_model


# ── Request/Response models ────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    execute_tools: bool = True  # Auto-execute tools


class ToolCallResult(BaseModel):
    tool: str
    arguments: dict[str, Any]
    result: Any
    success: bool
    duration_ms: float


class ChatResponse(BaseModel):
    response: str
    tool_calls: list[ToolCallResult] = []
    model_used: str = "local"
    thinking: Optional[str] = None


# ── Tool execution ─────────────────────────────────────────────────

async def execute_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Execute a tool and return the result."""
    start = time.time()

    try:
        # ── Workspace / Filesystem tools ──
        if tool_name in ("read_file", "read"):
            path = arguments.get("path", "")
            full_path = _resolve_path(path)
            if not full_path.exists():
                return {"success": False, "result": f"File not found: {path}"}
            content = full_path.read_text(errors="replace")
            if len(content) > 5000:
                content = content[:5000] + "\n... (truncated)"
            return {"success": True, "result": content}

        elif tool_name in ("write_file", "write", "create_file"):
            path = arguments.get("path", "")
            content = arguments.get("content", "")
            full_path = _resolve_path(path)
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content)
            return {"success": True, "result": f"Written {len(content)} bytes to {path}"}

        elif tool_name in ("list_files", "list", "ls"):
            path = arguments.get("path", ".")
            full_path = _resolve_path(path)
            if not full_path.exists():
                return {"success": False, "result": f"Directory not found: {path}"}
            entries = []
            for item in sorted(full_path.iterdir()):
                prefix = "📁" if item.is_dir() else "📄"
                size = item.stat().st_size if item.is_file() else 0
                entries.append(f"{prefix} {item.name} ({_format_size(size)})")
            return {"success": True, "result": "\n".join(entries[:50])}

        elif tool_name in ("delete_file", "delete", "rm"):
            path = arguments.get("path", "")
            full_path = _resolve_path(path)
            if not full_path.exists():
                return {"success": False, "result": f"Not found: {path}"}
            if full_path.is_dir():
                import shutil
                shutil.rmtree(full_path)
            else:
                full_path.unlink()
            return {"success": True, "result": f"Deleted {path}"}

        # ── Code execution ──
        elif tool_name in ("execute_code", "run_code", "execute", "run"):
            code = arguments.get("code", "")
            language = arguments.get("language", "python")

            if not code:
                return {"success": False, "result": "No code provided"}

            # Use the sandbox
            from core.tool_manager.sandbox import Sandbox, SandboxConfig
            timeout = arguments.get("timeout", 30)
            config = SandboxConfig(timeout=min(timeout, 60))
            sandbox = Sandbox(config)
            result = await sandbox.execute(code, language)

            output = ""
            if result.stdout:
                output += result.stdout
            if result.stderr:
                output += f"\n[stderr]\n{result.stderr}"
            if result.error:
                output += f"\n[error]\n{result.error}"

            return {
                "success": result.success,
                "result": output.strip() or "(no output)",
                "exit_code": result.exit_code,
            }

        # ── Web search ──
        elif tool_name in ("web_search", "search"):
            query = arguments.get("query", "")
            try:
                from tools.web_search import WebSearchTool
                tool = WebSearchTool()
                result = await tool.execute(query=query)
                if hasattr(result, "output"):
                    return {"success": True, "result": result.output}
                return {"success": True, "result": str(result)}
            except Exception as e:
                return {"success": False, "result": f"Search failed: {e}"}

        # ── System info ──
        elif tool_name in ("system_info", "info"):
            import platform
            info = {
                "system": platform.system(),
                "machine": platform.machine(),
                "python": platform.python_version(),
                "cwd": str(Path.cwd()),
            }
            return {"success": True, "result": json.dumps(info, indent=2)}

        # ── Shell command ──
        elif tool_name in ("shell", "bash", "terminal", "command"):
            cmd = arguments.get("command", arguments.get("cmd", ""))
            if not cmd:
                return {"success": False, "result": "No command provided"}
            import subprocess
            try:
                proc = subprocess.run(
                    cmd, shell=True, capture_output=True, text=True, timeout=30,
                    cwd=str(REPO_ROOT),
                )
                output = proc.stdout
                if proc.stderr:
                    output += f"\n{proc.stderr}"
                return {
                    "success": proc.returncode == 0,
                    "result": output[:5000] or "(no output)",
                    "exit_code": proc.returncode,
                }
            except subprocess.TimeoutExpired:
                return {"success": False, "result": "Command timed out (30s)"}

        # ── Install package ──
        elif tool_name in ("install", "pip_install"):
            package = arguments.get("package", arguments.get("name", ""))
            if not package:
                return {"success": False, "result": "No package name provided"}
            import subprocess
            proc = subprocess.run(
                ["pip", "install", package], capture_output=True, text=True, timeout=120
            )
            return {"success": proc.returncode == 0, "result": proc.stdout[-2000:]}

        # ── Tool registry tools ──
        elif app_state.tool_registry:
            tool = app_state.tool_registry.get_tool(tool_name)
            if tool and tool.function:
                result = await tool.function(**arguments)
                if hasattr(result, "success"):
                    return {"success": result.success, "result": result.output or result.error}
                return {"success": True, "result": str(result)}

        return {"success": False, "result": f"Unknown tool: {tool_name}"}

    except Exception as e:
        return {"success": False, "result": f"Tool error: {e}"}


def _resolve_path(path: str) -> Path:
    """Resolve a path relative to repo root, with safety check."""
    full = (REPO_ROOT / path).resolve() if not Path(path).is_absolute() else Path(path)
    if not str(full).startswith(str(REPO_ROOT.resolve())):
        raise ValueError("Path traversal blocked")
    return full


def _format_size(size: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.0f}{unit}" if unit == "B" else f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"


# ── The autonomous agent loop ─────────────────────────────────────

@router.post("/chat", response_model=ChatResponse)
async def agent_chat(request: ChatRequest) -> ChatResponse:
    """
    Autonomous agent chat — the agent receives a message, thinks,
    automatically executes tools if needed, and returns the result.
    
    This is the Arena-style "it just works" endpoint.
    """
    model = _get_local_model()

    # Load model if not loaded
    if not model.is_loaded():
        await model.load()

    tool_calls_results = []
    thinking = None

    # Step 1: Build the prompt with tool awareness
    tool_descriptions = """
Available tools (respond with JSON to use a tool):
- {"tool": "read_file", "arguments": {"path": "path/to/file"}} — Read a file
- {"tool": "write_file", "arguments": {"path": "path", "content": "text"}} — Write/create a file
- {"tool": "list_files", "arguments": {"path": "."}} — List files in a directory
- {"tool": "delete_file", "arguments": {"path": "path"}} — Delete a file
- {"tool": "execute_code", "arguments": {"code": "python code", "language": "python"}} — Run code in sandbox
- {"tool": "shell", "arguments": {"command": "ls -la"}} — Run a shell command
- {"tool": "web_search", "arguments": {"query": "search terms"}} — Search the web
- {"tool": "install", "arguments": {"package": "numpy"}} — Install a Python package
- {"tool": "system_info", "arguments": {}} — Get system information

To use a tool, respond ONLY with the JSON. To respond normally, just write text.
"""

    full_prompt = f"""You are Arena, an autonomous AI agent. You can read files, write code, execute programs, manage files, and search the web.

{tool_descriptions}

User: {request.message}
Arena:"""

    # Step 2: Generate response
    response_text = await model.generate(
        full_prompt,
        max_new_tokens=512,
        temperature=0.7,
    )

    # Step 3: Check if the response contains a tool call
    if request.execute_tools:
        tool_call = detect_tool_call(response_text)

        if tool_call:
            thinking = response_text  # Show the model's "thinking" (the tool call JSON)

            # Execute the tool
            tool_result = await execute_tool(tool_call["tool"], tool_call["arguments"])

            tool_calls_results.append(ToolCallResult(
                tool=tool_call["tool"],
                arguments=tool_call["arguments"],
                result=tool_result.get("result", ""),
                success=tool_result.get("success", False),
                duration_ms=0,
            ))

            # Step 4: Generate a natural language response with the tool result
            result_prompt = f"""The user asked: {request.message}

I used the tool `{tool_call['tool']}` and got this result:
{tool_result.get('result', 'No result')[:3000]}

Now respond to the user naturally, explaining what I found/did. Be helpful and concise.
Arena:"""

            natural_response = await model.generate(result_prompt, max_new_tokens=512)
            response_text = natural_response

    # Step 5: If response is still a raw tool call JSON (model didn't generate natural language)
    if response_text.strip().startswith("{") and "tool" in response_text:
        try:
            # Try to execute it one more time
            tool_call = detect_tool_call(response_text)
            if tool_call and not tool_calls_results:
                tool_result = await execute_tool(tool_call["tool"], tool_call["arguments"])
                tool_calls_results.append(ToolCallResult(
                    tool=tool_call["tool"],
                    arguments=tool_call["arguments"],
                    result=tool_result.get("result", ""),
                    success=tool_result.get("success", False),
                    duration_ms=0,
                ))
                response_text = f"Executed `{tool_call['tool']}`:\n\n{tool_result.get('result', 'No result')[:3000]}"
        except Exception:
            pass

    return ChatResponse(
        response=response_text,
        tool_calls=tool_calls_results,
        model_used="local",
        thinking=thinking,
    )


@router.get("/status")
async def agent_status() -> dict[str, Any]:
    """Get the local model status."""
    model = _get_local_model()
    return {
        "loaded": model.is_loaded(),
        "base_model": model.base_model_path,
        "adapter": model.adapter_path,
        "device": model.device if hasattr(model, "device") else "unknown",
    }


@router.post("/load")
async def load_model() -> dict[str, Any]:
    """Explicitly load the model."""
    model = _get_local_model()
    if model.is_loaded():
        return {"status": "already_loaded"}
    await model.load()
    return {"status": "loaded" if model.is_loaded() else "failed"}
