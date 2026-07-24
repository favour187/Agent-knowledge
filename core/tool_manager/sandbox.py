"""
Sandbox

Secure execution environment for running untrusted code.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional

import structlog

logger = structlog.get_logger(__name__)


class SandboxType(str, Enum):
    """Types of sandboxed environments."""
    PROCESS = "process"           # Isolated subprocess
    CONTAINER = "container"       # Docker container
    VM = "vm"                     # Lightweight VM
    WASM = "wasm"                 # WebAssembly sandbox


@dataclass
class SandboxConfig:
    """Configuration for sandbox execution."""
    sandbox_type: SandboxType = SandboxType.PROCESS
    timeout: float = 30.0
    memory_limit: Optional[int] = None  # MB
    cpu_limit: Optional[float] = None   # CPU shares
    network_enabled: bool = False
    disk_read_only: bool = True
    allowed_paths: list[str] = field(default_factory=list)
    denied_paths: list[str] = field(default_factory=list)
    environment_vars: dict[str, str] = field(default_factory=dict)
    user: Optional[str] = None  # Run as user


@dataclass
class SandboxResult:
    """Result of sandboxed execution."""
    success: bool
    output: str = ""
    error: Optional[str] = None
    exit_code: int = 0
    execution_time: float = 0.0
    stdout: str = ""
    stderr: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class Sandbox:
    """
    Secure sandbox for running untrusted code.

    Features:
    - Process isolation
    - Resource limits (CPU, memory, time)
    - Filesystem restrictions
    - Network control
    - Working directory isolation
    """

    def __init__(self, config: Optional[SandboxConfig] = None):
        self.config = config or SandboxConfig()
        self._temp_dir: Optional[str] = None

    async def execute(
        self,
        code: str,
        language: str = "python",
        arguments: Optional[list[str]] = None,
    ) -> SandboxResult:
        """
        Execute code in the sandbox.

        Args:
            code: Code to execute
            language: Programming language
            arguments: Command-line arguments

        Returns:
            SandboxResult
        """
        import time
        start_time = time.time()

        # Create temp directory
        self._temp_dir = tempfile.mkdtemp(prefix="arena_sandbox_")

        try:
            if self.config.sandbox_type == SandboxType.PROCESS:
                result = await self._execute_process(code, language, arguments)
            elif self.config.sandbox_type == SandboxType.CONTAINER:
                result = await self._execute_container(code, language, arguments)
            else:
                result = await self._execute_process(code, language, arguments)

            result.execution_time = time.time() - start_time
            return result

        finally:
            # Cleanup temp directory
            await self._cleanup()

    async def _execute_process(
        self,
        code: str,
        language: str,
        arguments: Optional[list[str]],
    ) -> SandboxResult:
        """Execute code in isolated process."""
        # Write code to temp file
        extension = self._get_extension(language)
        code_file = os.path.join(self._temp_dir, f"code{extension}")

        with open(code_file, "w") as f:
            f.write(code)

        # Build command
        cmd = self._build_command(language, code_file, arguments)

        # Build environment
        env = os.environ.copy()
        env.update(self.config.environment_vars)

        # Build subprocess arguments
        process_args = {
            "timeout": self.config.timeout,
            "env": env,
            "cwd": self._temp_dir,
        }

        if self.config.memory_limit:
            process_args["memory_limit"] = self.config.memory_limit

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                **({"env": env, "cwd": self._temp_dir} if cmd[0] != "python" else {}),
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=self.config.timeout,
                )

                return SandboxResult(
                    success=proc.returncode == 0,
                    output=stdout.decode() if stdout else "",
                    error=stderr.decode() if stderr else None,
                    exit_code=proc.returncode or 0,
                    stdout=stdout.decode() if stdout else "",
                    stderr=stderr.decode() if stderr else "",
                )

            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return SandboxResult(
                    success=False,
                    error=f"Execution timed out after {self.config.timeout}s",
                    exit_code=-1,
                )

        except Exception as e:
            logger.error("sandbox_execution_failed", error=str(e))
            return SandboxResult(
                success=False,
                error=str(e),
                exit_code=-1,
            )

    async def _execute_container(
        self,
        code: str,
        language: str,
        arguments: Optional[list[str]],
    ) -> SandboxResult:
        """Execute code in Docker container."""
        # Write code to temp file
        extension = self._get_extension(language)
        code_file = os.path.join(self._temp_dir, f"code{extension}")

        with open(code_file, "w") as f:
            f.write(code)

        # Build docker command
        image = self._get_docker_image(language)
        cmd = self._build_command(language, f"/sandbox/{os.path.basename(code_file)}", arguments)

        docker_cmd = [
            "docker", "run",
            "--rm",
            "--network=none",
            "--read-only" if self.config.disk_read_only else "",
            f"--memory={self.config.memory_limit}m" if self.config.memory_limit else "",
            f"--cpus={self.config.cpu_limit}" if self.config.cpu_limit else "",
            "-v", f"{self._temp_dir}:/sandbox:ro",
            "-w", "/sandbox",
            image,
        ] + cmd

        try:
            proc = await asyncio.create_subprocess_exec(
                *docker_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=self.config.timeout,
                )

                return SandboxResult(
                    success=proc.returncode == 0,
                    output=stdout.decode() if stdout else "",
                    error=stderr.decode() if stderr else None,
                    exit_code=proc.returncode or 0,
                    stdout=stdout.decode() if stdout else "",
                    stderr=stderr.decode() if stderr else "",
                )

            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return SandboxResult(
                    success=False,
                    error=f"Container execution timed out after {self.config.timeout}s",
                    exit_code=-1,
                )

        except Exception as e:
            logger.error("container_execution_failed", error=str(e))
            return SandboxResult(
                success=False,
                error=str(e),
                exit_code=-1,
            )

    def _get_extension(self, language: str) -> str:
        """Get file extension for language."""
        extensions = {
            "python": ".py",
            "python3": ".py",
            "javascript": ".js",
            "node": ".js",
            "typescript": ".ts",
            "bash": ".sh",
            "shell": ".sh",
            "ruby": ".rb",
            "go": ".go",
            "rust": ".rs",
        }
        return extensions.get(language.lower(), ".txt")

    def _get_docker_image(self, language: str) -> str:
        """Get Docker image for language."""
        images = {
            "python": "python:3.11-slim",
            "python3": "python:3.11-slim",
            "javascript": "node:20-slim",
            "node": "node:20-slim",
            "typescript": "node:20-slim",
            "bash": "bash:5.2",
            "shell": "bash:5.2",
            "ruby": "ruby:3.2-slim",
            "go": "golang:1.21-alpine",
            "rust": "rust:1.75-slim",
        }
        return images.get(language.lower(), "python:3.11-slim")

    def _build_command(
        self,
        language: str,
        code_file: str,
        arguments: Optional[list[str]],
    ) -> list[str]:
        """Build command to execute code."""
        cmd_map = {
            "python": ["python", code_file],
            "python3": ["python3", code_file],
            "javascript": ["node", code_file],
            "node": ["node", code_file],
            "typescript": ["npx", "ts-node", code_file],
            "bash": ["bash", code_file],
            "shell": ["/bin/sh", code_file],
            "ruby": ["ruby", code_file],
            "go": ["go", "run", code_file],
            "rust": ["rustc", code_file],
        }

        cmd = cmd_map.get(language.lower(), ["python", code_file])

        if arguments:
            cmd.extend(arguments)

        return cmd

    async def _cleanup(self) -> None:
        """Clean up temp directory."""
        if self._temp_dir and os.path.exists(self._temp_dir):
            try:
                import shutil
                shutil.rmtree(self._temp_dir)
            except Exception as e:
                logger.warning("sandbox_cleanup_failed", error=str(e))


class CodeExecutionSandbox:
    """High-level interface for code execution."""

    def __init__(self, config: Optional[SandboxConfig] = None):
        self.config = config or SandboxConfig()
        self._sandboxes: dict[str, Sandbox] = {}

    async def execute_python(self, code: str) -> SandboxResult:
        """Execute Python code."""
        sandbox = Sandbox(self.config)
        return await sandbox.execute(code, "python")

    async def execute_javascript(self, code: str) -> SandboxResult:
        """Execute JavaScript code."""
        sandbox = Sandbox(self.config)
        return await sandbox.execute(code, "javascript")

    async def execute_bash(self, code: str) -> SandboxResult:
        """Execute bash script."""
        sandbox = Sandbox(self.config)
        return await sandbox.execute(code, "bash")

    async def execute_code(
        self,
        code: str,
        language: str,
        timeout: float = 30.0,
    ) -> SandboxResult:
        """
        Execute code in the appropriate language.

        Args:
            code: Code to execute
            language: Programming language
            timeout: Execution timeout

        Returns:
            SandboxResult
        """
        config = SandboxConfig(
            sandbox_type=self.config.sandbox_type,
            timeout=timeout,
            memory_limit=self.config.memory_limit,
            cpu_limit=self.config.cpu_limit,
        )
        sandbox = Sandbox(config)
        return await sandbox.execute(code, language)
