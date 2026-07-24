"""
Local Model Provider

Runs inference on locally trained models (LoRA adapters on GPT-2, etc.)
No external API calls. No API keys needed.
"""

from __future__ import annotations

import os
import re
import json
import asyncio
from pathlib import Path
from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)

# Try to load torch — may not be installed
try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False


class LocalModelProvider:
    """
    Inference provider using locally trained models.
    
    Loads a base model + LoRA adapter and generates responses.
    Supports automatic tool detection from model output.
    """

    def __init__(
        self,
        base_model_path: str = "models/gpt2-local",
        adapter_path: Optional[str] = None,
        device: str = "auto",
    ):
        self.base_model_path = base_model_path
        self.adapter_path = adapter_path
        self.device = self._detect_device(device)
        self.model = None
        self.tokenizer = None
        self._loaded = False

    def _detect_device(self, device: str) -> str:
        if device != "auto":
            return device
        if TORCH_AVAILABLE and torch.cuda.is_available():
            return "cuda"
        if TORCH_AVAILABLE and hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
        return "cpu"

    def is_loaded(self) -> bool:
        return self._loaded

    async def load(self) -> None:
        """Load the model and tokenizer in a background thread."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._load_sync)

    def _load_sync(self) -> None:
        """Synchronous model loading."""
        if not TORCH_AVAILABLE:
            logger.warning("torch_not_available")
            return

        from transformers import AutoModelForCausalLM, AutoTokenizer

        base_path = Path(self.base_model_path)
        if not base_path.exists():
            logger.warning("base_model_not_found", path=str(base_path))
            return

        try:
            logger.info("loading_local_model", path=str(base_path))
            self.tokenizer = AutoTokenizer.from_pretrained(str(base_path))
            self.model = AutoModelForCausalLM.from_pretrained(str(base_path))

            # Load LoRA adapter if available
            if self.adapter_path:
                adapter = Path(self.adapter_path)
                if adapter.exists():
                    try:
                        from peft import PeftModel
                        self.model = PeftModel.from_pretrained(self.model, str(adapter))
                        logger.info("lora_adapter_loaded", path=str(adapter))
                    except Exception as e:
                        logger.warning("adapter_load_failed", error=str(e))

            # Move to device
            if self.device != "cpu":
                self.model = self.model.to(self.device)

            self.model.eval()
            self._loaded = True
            total = sum(p.numel() for p in self.model.parameters())
            logger.info("local_model_loaded", params=total, device=self.device)

        except Exception as e:
            logger.error("model_load_failed", error=str(e))

    async def generate(
        self,
        prompt: str,
        max_new_tokens: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.9,
        stop_sequences: Optional[list[str]] = None,
    ) -> str:
        """Generate text from a prompt."""
        if not self._loaded:
            return self._fallback_response(prompt)

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._generate_sync, prompt, max_new_tokens, temperature, top_p
        )

    def _generate_sync(
        self, prompt: str, max_new_tokens: int, temperature: float, top_p: float
    ) -> str:
        """Synchronous generation."""
        try:
            inputs = self.tokenizer(prompt, return_tensors="pt", truncation=True, max_length=1024)
            if self.device != "cpu":
                inputs = {k: v.to(self.device) for k, v in inputs.items()}

            with torch.no_grad():
                output = self.model.generate(
                    **inputs,
                    max_new_tokens=max_new_tokens,
                    temperature=max(temperature, 0.01),
                    top_p=top_p,
                    do_sample=True,
                    repetition_penalty=1.2,
                    pad_token_id=self.tokenizer.eos_token_id,
                )

            generated = self.tokenizer.decode(output[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
            return generated.strip()

        except Exception as e:
            logger.error("generation_failed", error=str(e))
            return f"I encountered an error generating a response: {e}"

    def _fallback_response(self, prompt: str) -> str:
        """Intelligent fallback when model isn't loaded — use rule-based responses."""
        prompt_lower = prompt.lower()

        # Detect what the user wants and route to tools
        if any(w in prompt_lower for w in ["read", "show", "open", "view", "cat "]):
            return '{"tool": "read_file", "arguments": {"path": "README.md"}}'

        if any(w in prompt_lower for w in ["write", "create", "save", "make a file"]):
            return '{"tool": "write_file", "arguments": {"path": "output.txt", "content": "Hello"}}'

        if any(w in prompt_lower for w in ["run", "execute", "python", "script", "code"]):
            # Extract code if present
            code_match = re.search(r'```(?:python)?\n(.*?)```', prompt, re.DOTALL)
            code = code_match.group(1) if code_match else 'print("Hello from Arena")'
            return json.dumps({"tool": "execute_code", "arguments": {"code": code, "language": "python"}})

        if any(w in prompt_lower for w in ["list", "ls", "dir", "files", "directory"]):
            return '{"tool": "list_files", "arguments": {"path": "."}}'

        if any(w in prompt_lower for w in ["search", "find", "google", "look up"]):
            query = re.search(r'(?:search|find|google|look up)\s+(?:for\s+)?(.+?)(?:\.|$)', prompt_lower)
            q = query.group(1).strip() if query else prompt
            return json.dumps({"tool": "web_search", "arguments": {"query": q}})

        if any(w in prompt_lower for w in ["install", "pip", "npm", "package"]):
            return json.dumps({"tool": "execute_code", "arguments": {
                "code": "import subprocess\nresult = subprocess.run(['pip', 'list'], capture_output=True, text=True)\nprint(result.stdout[:2000])",
                "language": "python"
            }})

        # General conversational response
        return (
            "I'm your Arena agent. I can help you with:\n\n"
            "- **Read/write files** — \"read README.md\" or \"create a file called test.py\"\n"
            "- **Run code** — \"run this Python code: ```python\\nprint('hello')\\n```\"\n"
            "- **List files** — \"show me the files in this directory\"\n"
            "- **Search the web** — \"search for Python tutorials\"\n"
            "- **Execute commands** — \"run pip list\"\n\n"
            "What would you like me to do?"
        )


def detect_tool_call(response: str) -> Optional[dict[str, Any]]:
    """
    Parse a model response to detect if it contains a tool call.
    
    Looks for JSON patterns like:
    {"tool": "read_file", "arguments": {"path": "file.txt"}}
    """
    # Try to find JSON in the response
    json_patterns = [
        r'\{[^{}]*"tool"\s*:\s*"[^"]+?"[^{}]*\}',  # Simple tool call
        r'\{[^{}]*"tool"\s*:\s*\'[^\']+?\'[^{}]*\}',  # Single quotes
    ]

    for pattern in json_patterns:
        matches = re.findall(pattern, response, re.DOTALL)
        for match in matches:
            try:
                data = json.loads(match)
                if "tool" in data:
                    return {
                        "tool": data["tool"],
                        "arguments": data.get("arguments", {}),
                    }
            except json.JSONDecodeError:
                continue

    # Try parsing the entire response as JSON
    try:
        data = json.loads(response.strip())
        if isinstance(data, dict) and "tool" in data:
            return {
                "tool": data["tool"],
                "arguments": data.get("arguments", {}),
            }
    except (json.JSONDecodeError, ValueError):
        pass

    return None
