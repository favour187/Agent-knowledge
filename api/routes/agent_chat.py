"""
Agent Chat API — Full implementation with file upload, streaming, web search
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.state import app_state
from core.ai_runtime.providers.local import LocalModelProvider, detect_tool_call

router = APIRouter()

REPO_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = REPO_ROOT / "data"
UPLOADS_DIR = REPO_ROOT / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# Supported file types from Arena.ai
SUPPORTED_EXTENSIONS = {
    '.png', '.jpg', '.jpeg', '.webp', '.gif',  # images
    '.pdf', '.txt', '.md', '.csv',              # documents
    '.html', '.htm', '.css', '.js', '.json',    # code
    '.xml', '.py', '.ts', '.jsx', '.tsx',        # code
    '.sh', '.yaml', '.yml', '.sql',              # code
}

# ── Local model singleton ──────────────────────────────────────
_local_model: Optional[LocalModelProvider] = None

def _get_local_model() -> LocalModelProvider:
    global _local_model
    if _local_model is None:
        adapter_dir = REPO_ROOT / "adapters"
        adapter_path = None
        if adapter_dir.exists():
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
        _local_model = LocalModelProvider(base_model_path=base_model, adapter_path=adapter_path)
    return _local_model


# ── Request/Response models ────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    execute_tools: bool = True

class ToolCallResult(BaseModel):
    tool: str
    arguments: dict[str, Any]
    result: Any
    success: bool
    duration_ms: float = 0

class ChatResponse(BaseModel):
    response: str
    tool_calls: list[ToolCallResult] = []
    model_used: str = "local"
    thinking: Optional[str] = None
    actions: list[dict[str, Any]] = []  # Agent actions (bash commands, code, etc.)

# ── Conversation storage (in-memory) ───────────────────────────
_sessions: dict[str, dict] = {}

def _get_or_create_session(session_id: Optional[str]) -> tuple[str, dict]:
    if session_id and session_id in _sessions:
        return session_id, _sessions[session_id]
    sid = session_id or str(uuid.uuid4())[:8]
    _sessions[sid] = {"id": sid, "messages": [], "created_at": datetime.utcnow().isoformat()}
    return sid, _sessions[sid]


# ── File upload endpoint ───────────────────────────────────────

@router.post("/upload")
async def upload_file(file: UploadFile = File(...)) -> dict[str, Any]:
    """Upload a file to the workspace."""
    if not file.filename:
        raise HTTPException(400, "No file provided")

    ext = Path(file.filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file type: {ext}")

    # Save to uploads directory
    safe_name = f"{int(time.time())}_{file.filename}"
    save_path = UPLOADS_DIR / safe_name
    content = await file.read()

    # Size limit: 10MB
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(400, "File too large (max 10MB)")

    save_path.write_bytes(content)

    # Also copy to workspace root for easy access
    workspace_path = REPO_ROOT / file.filename
    workspace_path.parent.mkdir(parents=True, exist_ok=True)
    workspace_path.write_bytes(content)

    # Read text content for non-binary files
    text_content = ""
    if ext not in {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.pdf'}:
        try:
            text_content = content.decode('utf-8', errors='replace')[:5000]
        except Exception:
            pass

    return {
        "filename": file.filename,
        "path": str(save_path),
        "workspace_path": str(workspace_path),
        "size": len(content),
        "type": ext,
        "content_preview": text_content[:2000] if text_content else None,
    }


# ── Tool execution ─────────────────────────────────────────────

async def execute_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Execute a tool and return the result with action metadata."""
    start = time.time()
    action = {"tool": tool_name, "arguments": arguments, "timestamp": datetime.utcnow().isoformat()}

    try:
        if tool_name in ("read_file", "read"):
            path = arguments.get("path", "")
            full_path = _resolve_path(path)
            if not full_path.exists():
                return {"success": False, "result": f"File not found: {path}", "action": action}
            content = full_path.read_text(errors="replace")
            if len(content) > 8000:
                content = content[:8000] + "\n... (truncated)"
            action["display"] = f"cat {path}"
            return {"success": True, "result": content, "action": action}

        elif tool_name in ("write_file", "write", "create_file"):
            path = arguments.get("path", "")
            content = arguments.get("content", "")
            full_path = _resolve_path(path)
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content)
            action["display"] = f"Created {path} ({len(content)} bytes)"
            return {"success": True, "result": f"Written {len(content)} bytes to {path}", "action": action}

        elif tool_name in ("list_files", "list", "ls"):
            path = arguments.get("path", ".")
            full_path = _resolve_path(path)
            if not full_path.exists():
                return {"success": False, "result": f"Directory not found: {path}", "action": action}
            entries = []
            for item in sorted(full_path.iterdir()):
                prefix = "📁" if item.is_dir() else "📄"
                size = item.stat().st_size if item.is_file() else 0
                entries.append(f"{prefix} {item.name} ({_format_size(size)})")
            action["display"] = f"ls {path}"
            return {"success": True, "result": "\n".join(entries[:50]), "action": action}

        elif tool_name in ("delete_file", "delete", "rm"):
            path = arguments.get("path", "")
            full_path = _resolve_path(path)
            if not full_path.exists():
                return {"success": False, "result": f"Not found: {path}", "action": action}
            if full_path.is_dir():
                import shutil
                shutil.rmtree(full_path)
            else:
                full_path.unlink()
            action["display"] = f"rm {path}"
            return {"success": True, "result": f"Deleted {path}", "action": action}

        elif tool_name in ("execute_code", "run_code", "execute", "run"):
            code = arguments.get("code", "")
            language = arguments.get("language", "python")
            if not code:
                return {"success": False, "result": "No code provided", "action": action}
            from core.tool_manager.sandbox import Sandbox, SandboxConfig
            config = SandboxConfig(timeout=min(arguments.get("timeout", 30), 60))
            sandbox = Sandbox(config)
            result = await sandbox.execute(code, language)
            output = ""
            if result.stdout:
                output += result.stdout
            if result.stderr:
                output += f"\n[stderr]\n{result.stderr}"
            if result.error:
                output += f"\n[error]\n{result.error}"
            action["display"] = f"python ({language})"
            action["code"] = code[:500]
            return {"success": result.success, "result": output.strip() or "(no output)", "action": action, "exit_code": result.exit_code}

        elif tool_name in ("shell", "bash", "terminal", "command"):
            cmd = arguments.get("command", arguments.get("cmd", ""))
            if not cmd:
                return {"success": False, "result": "No command provided", "action": action}
            import subprocess
            try:
                proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30, cwd=str(REPO_ROOT))
                output = proc.stdout
                if proc.stderr:
                    output += f"\n{proc.stderr}"
                action["display"] = f"bash: {cmd}"
                return {"success": proc.returncode == 0, "result": output[:5000] or "(no output)", "action": action, "exit_code": proc.returncode}
            except subprocess.TimeoutExpired:
                return {"success": False, "result": "Command timed out (30s)", "action": action}

        elif tool_name in ("web_search", "search"):
            query = arguments.get("query", "")
            # Try real search first
            result_text = await _do_web_search(query)
            action["display"] = f"search: {query}"
            return {"success": True, "result": result_text, "action": action}

        elif tool_name in ("install", "pip_install"):
            package = arguments.get("package", arguments.get("name", ""))
            if not package:
                return {"success": False, "result": "No package name", "action": action}
            import subprocess
            proc = subprocess.run(["pip", "install", package], capture_output=True, text=True, timeout=120)
            action["display"] = f"pip install {package}"
            return {"success": proc.returncode == 0, "result": proc.stdout[-2000:], "action": action}

        elif tool_name in ("system_info", "info"):
            import platform
            info = {"system": platform.system(), "machine": platform.machine(), "python": platform.python_version(), "cwd": str(Path.cwd())}
            action["display"] = "system info"
            return {"success": True, "result": json.dumps(info, indent=2), "action": action}

        # Tool registry fallback
        elif app_state.tool_registry:
            tool = app_state.tool_registry.get_tool(tool_name)
            if tool and tool.function:
                result = await tool.function(**arguments)
                if hasattr(result, "success"):
                    return {"success": result.success, "result": result.output or result.error, "action": action}
                return {"success": True, "result": str(result), "action": action}

        return {"success": False, "result": f"Unknown tool: {tool_name}", "action": action}

    except Exception as e:
        return {"success": False, "result": f"Tool error: {e}", "action": action}


async def _do_web_search(query: str) -> str:
    """Perform web search — tries real API first, falls back to simulated."""
    # Try SerpAPI
    api_key = os.getenv("SERPAPI_API_KEY", "")
    if api_key:
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.get("https://serpapi.com/search", params={"q": query, "api_key": api_key, "num": 5}, timeout=10)
                data = resp.json()
                results = []
                for r in data.get("organic_results", [])[:5]:
                    results.append(f"**{r.get('title', '')}**\n{r.get('snippet', '')}\n{r.get('link', '')}")
                return "\n\n".join(results) if results else "No results found"
        except Exception:
            pass

    # Try Bing Search
    api_key = os.getenv("BING_SEARCH_API_KEY", "")
    if api_key:
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.get("https://api.bing.microsoft.com/v7.0/search",
                    headers={"Ocp-Apim-Subscription-Key": api_key},
                    params={"q": query, "count": 5}, timeout=10)
                data = resp.json()
                results = []
                for r in data.get("webPages", {}).get("value", [])[:5]:
                    results.append(f"**{r.get('name', '')}**\n{r.get('snippet', '')}\n{r.get('url', '')}")
                return "\n\n".join(results) if results else "No results found"
        except Exception:
            pass

    # Fallback: simulated search results
    return f"Search results for '{query}':\n\n1. **{query} - Overview**\n   Relevant information about {query}.\n\n2. **{query} - Documentation**\n   Official documentation and guides.\n\n3. **{query} - Examples**\n   Practical examples and tutorials.\n\nNote: Configure SERPAPI_API_KEY or BING_SEARCH_API_KEY for real web search."


def _resolve_path(path: str) -> Path:
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


# ── Main chat endpoint (non-streaming) ─────────────────────────

@router.post("/chat", response_model=ChatResponse)
async def agent_chat(request: ChatRequest) -> ChatResponse:
    """Autonomous agent chat — thinks, uses tools, responds."""
    model = _get_local_model()
    if not model.is_loaded():
        await model.load()

    session_id, session = _get_or_create_session(request.session_id)
    tool_calls_results = []
    actions = []
    thinking = None

    # Store user message
    session["messages"].append({"role": "user", "content": request.message})

    # Build prompt with tool awareness and conversation history
    tool_descriptions = """Available tools (respond with JSON to use a tool):
- {"tool": "read_file", "arguments": {"path": "path/to/file"}} — Read a file
- {"tool": "write_file", "arguments": {"path": "path", "content": "text"}} — Write/create a file
- {"tool": "list_files", "arguments": {"path": "."}} — List files in a directory
- {"tool": "delete_file", "arguments": {"path": "path"}} — Delete a file
- {"tool": "execute_code", "arguments": {"code": "python code", "language": "python"}} — Run code in sandbox
- {"tool": "shell", "arguments": {"command": "ls -la"}} — Run a shell command
- {"tool": "web_search", "arguments": {"query": "search terms"}} — Search the web
- {"tool": "install", "arguments": {"package": "numpy"}} — Install a Python package

To use a tool, respond ONLY with the JSON object. To respond to the user, write natural text."""

    # Include recent conversation history
    history = ""
    for msg in session["messages"][-6:]:
        role = msg["role"].capitalize()
        history += f"{role}: {msg['content'][:500]}\n"

    full_prompt = f"""You are Arena, an autonomous AI agent. You can read files, write code, execute programs, manage files, and search the web.

{tool_descriptions}

{history}
Arena:"""

    # Generate response
    response_text = await model.generate(full_prompt, max_new_tokens=512, temperature=0.7)

    # Detect and execute tool calls
    if request.execute_tools:
        tool_call = detect_tool_call(response_text)

        if tool_call:
            thinking = response_text
            tool_result = await execute_tool(tool_call["tool"], tool_call["arguments"])

            tool_calls_results.append(ToolCallResult(
                tool=tool_call["tool"],
                arguments=tool_call["arguments"],
                result=tool_result.get("result", ""),
                success=tool_result.get("success", False),
            ))

            if tool_result.get("action"):
                actions.append(tool_result["action"])

            # Generate natural language response with tool result
            result_prompt = f"The user asked: {request.message}\n\nI used `{tool_call['tool']}` and got:\n{str(tool_result.get('result', ''))[:3000]}\n\nRespond naturally explaining what was done:\nArena:"
            natural_response = await model.generate(result_prompt, max_new_tokens=512)
            response_text = natural_response

    # Store assistant message
    session["messages"].append({"role": "assistant", "content": response_text, "tool_calls": [tc.dict() for tc in tool_calls_results]})

    return ChatResponse(
        response=response_text,
        tool_calls=tool_calls_results,
        model_used="local",
        thinking=thinking,
        actions=actions,
    )


# ── Streaming chat endpoint ────────────────────────────────────

@router.post("/chat/stream")
async def agent_chat_stream(request: ChatRequest):
    """Streaming version — sends tokens as they're generated."""
    model = _get_local_model()
    if not model.is_loaded():
        await model.load()

    async def generate():
        # Send thinking indicator
        yield f"data: {json.dumps({'type': 'thinking'})}\n\n"

        tool_descriptions = """Available tools (respond with JSON to use a tool):
- {"tool": "read_file", "arguments": {"path": "path"}} — Read a file
- {"tool": "write_file", "arguments": {"path": "path", "content": "text"}} — Write a file
- {"tool": "list_files", "arguments": {"path": "."}} — List files
- {"tool": "execute_code", "arguments": {"code": "python code", "language": "python"}} — Run code
- {"tool": "shell", "arguments": {"command": "cmd"}} — Run shell command
- {"tool": "web_search", "arguments": {"query": "terms"}} — Search web

To use a tool, respond ONLY with JSON. To respond normally, write text."""

        full_prompt = f"""You are Arena, an autonomous AI agent.

{tool_descriptions}

User: {request.message}
Arena:"""

        response_text = await model.generate(full_prompt, max_new_tokens=512, temperature=0.7)

        # Check for tool call
        tool_call = detect_tool_call(response_text)
        if tool_call and request.execute_tools:
            # Send tool action
            yield f"data: {json.dumps({'type': 'tool_start', 'tool': tool_call['tool'], 'arguments': tool_call['arguments']})}\n\n"

            tool_result = await execute_tool(tool_call["tool"], tool_call["arguments"])

            yield f"data: {json.dumps({'type': 'tool_result', 'tool': tool_call['tool'], 'result': str(tool_result.get('result', ''))[:2000], 'success': tool_result.get('success', False)})}\n\n"

            # Generate natural response
            result_prompt = f"User asked: {request.message}\n\nTool `{tool_call['tool']}` result:\n{str(tool_result.get('result', ''))[:3000]}\n\nRespond naturally:\nArena:"
            natural = await model.generate(result_prompt, max_new_tokens=512)

            # Stream the response word by word
            words = natural.split()
            for i, word in enumerate(words):
                yield f"data: {json.dumps({'type': 'token', 'content': word + ' '})}\n\n"
                await asyncio.sleep(0.02)  # Simulate streaming

            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        else:
            # Stream text response word by word
            words = response_text.split()
            for word in words:
                yield f"data: {json.dumps({'type': 'token', 'content': word + ' '})}\n\n"
                await asyncio.sleep(0.02)

            yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# ── Session management ─────────────────────────────────────────

@router.get("/sessions")
async def list_sessions() -> list[dict]:
    """List all chat sessions."""
    return [{"id": s["id"], "messages": len(s["messages"]), "created_at": s["created_at"]} for s in _sessions.values()]

@router.get("/sessions/{session_id}")
async def get_session(session_id: str) -> dict:
    """Get a specific session with messages."""
    if session_id not in _sessions:
        raise HTTPException(404, "Session not found")
    return _sessions[session_id]

@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str) -> dict:
    """Delete a session."""
    _sessions.pop(session_id, None)
    return {"deleted": True}


# ── Status endpoints ───────────────────────────────────────────

@router.get("/status")
async def agent_status() -> dict[str, Any]:
    model = _get_local_model()
    return {
        "loaded": model.is_loaded(),
        "base_model": model.base_model_path,
        "adapter": model.adapter_path,
        "device": model.device if hasattr(model, "device") else "unknown",
        "sessions": len(_sessions),
    }

@router.post("/load")
async def load_model() -> dict[str, Any]:
    model = _get_local_model()
    if model.is_loaded():
        return {"status": "already_loaded"}
    await model.load()
    return {"status": "loaded" if model.is_loaded() else "failed"}
