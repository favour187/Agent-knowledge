"""
Adapter Management System

Production-grade adapter (LoRA/QLoRA) management for model customization.
This is how organizations customize AI models in production — not by training
from scratch, but by training lightweight adapters on top of frozen base models.

Key capabilities:
- Save / load adapter weights independently of base models
- Merge adapters back into base models for deployment
- Compare adapter performance
- Manage multiple adapter versions
- Export adapters in standard formats (PEFT, Safetensors, GGUF adapter)

Usage:
    from core.training.adapters import AdapterManager
    manager = AdapterManager("meta-llama/Llama-2-7b-hf")
    adapter_path = manager.train_adapter("./data", strategy="qlora")
    manager.merge_adapter(adapter_path, "./merged-model")
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)


class AdapterInfo:
    """Metadata for a trained adapter."""

    def __init__(
        self,
        adapter_path: str,
        base_model: str,
        strategy: str,
        rank: int = 16,
        alpha: int = 32,
        target_modules: Optional[list[str]] = None,
        trainable_params: int = 0,
        total_params: int = 0,
        dataset_samples: int = 0,
        epochs: int = 3,
    ):
        self.adapter_path = adapter_path
        self.base_model = base_model
        self.strategy = strategy  # lora, qlora, full_finetune
        self.rank = rank
        self.alpha = alpha
        self.target_modules = target_modules or []
        self.trainable_params = trainable_params
        self.total_params = total_params
        self.dataset_samples = dataset_samples
        self.epochs = epochs

        # Derived
        self.trainable_pct = (trainable_params / total_params * 100) if total_params > 0 else 0
        self.name = Path(adapter_path).name

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapter_path": self.adapter_path,
            "base_model": self.base_model,
            "name": self.name,
            "strategy": self.strategy,
            "rank": self.rank,
            "alpha": self.alpha,
            "target_modules": self.target_modules,
            "trainable_params": self.trainable_params,
            "total_params": self.total_params,
            "trainable_pct": round(self.trainable_pct, 4),
            "dataset_samples": self.dataset_samples,
            "epochs": self.epochs,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AdapterInfo":
        return cls(
            adapter_path=data.get("adapter_path", ""),
            base_model=data.get("base_model", ""),
            strategy=data.get("strategy", "lora"),
            rank=data.get("rank", 16),
            alpha=data.get("alpha", 32),
            target_modules=data.get("target_modules"),
            trainable_params=data.get("trainable_params", 0),
            total_params=data.get("total_params", 0),
            dataset_samples=data.get("dataset_samples", 0),
            epochs=data.get("epochs", 3),
        )

    def save_metadata(self, path: Optional[str] = None) -> str:
        target = path or Path(self.adapter_path) / "adapter_info.json"
        Path(target).parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
        logger.info("adapter_metadata_saved", path=str(target))
        return str(target)

    @classmethod
    def load_metadata(cls, path: str) -> "AdapterInfo":
        with open(path, "r") as f:
            return cls.from_dict(json.load(f))


class AdapterRegistry:
    """Registry for tracking all adapters in a project."""

    def __init__(self, registry_dir: str = "./adapters"):
        self.registry_dir = Path(registry_dir)
        self.registry_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.registry_dir / "index.json"
        self.index = self._load_index()

    def _load_index(self) -> dict[str, Any]:
        if self.index_path.exists():
            with open(self.index_path) as f:
                return json.load(f)
        return {"adapters": {}}

    def _save_index(self) -> None:
        with open(self.index_path, "w") as f:
            json.dump(self.index, f, indent=2)

    def register(self, adapter_info: AdapterInfo) -> None:
        self.index["adapters"][adapter_info.name] = adapter_info.to_dict()
        self._save_index()
        adapter_info.save_metadata()
        logger.info("adapter_registered", name=adapter_info.name)

    def list_adapters(self) -> list[AdapterInfo]:
        result = []
        for name, data in self.index.get("adapters", {}).items():
            result.append(AdapterInfo.from_dict(data))
        return result

    def get_adapter(self, name: str) -> Optional[AdapterInfo]:
        data = self.index.get("adapters", {}).get(name)
        return AdapterInfo.from_dict(data) if data else None

    def unregister(self, name: str) -> None:
        if name in self.index.get("adapters", {}):
            del self.index["adapters"][name]
            self._save_index()
            logger.info("adapter_unregistered", name=name)


class AdapterManager:
    """
    High-level adapter manager for fine-tuning and deployment.

    This is the production interface for adapter-based customization.
    It handles training, merging, comparison, and export.
    """

    def __init__(
        self,
        base_model: str,
        adapter_registry: Optional[AdapterRegistry] = None,
        device: str = "auto",
    ):
        self.base_model = base_model
        self.device = device
        self.registry = adapter_registry or AdapterRegistry()

        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
            from peft import PeftModel
            self._torch = torch
            self._AutoModel = AutoModelForCausalLM
            self._AutoTokenizer = AutoTokenizer
            self._PeftModel = PeftModel
            self._dependencies_available = True
        except ImportError:
            self._dependencies_available = False
            logger.warning("training_dependencies_not_installed", message="Install with: pip install -r requirements-training.txt")

    def is_available(self) -> bool:
        return self._dependencies_available

    def estimate_memory(
        self,
        model_size_b: float = 7.0,
        batch_size: int = 4,
        seq_length: int = 2048,
        strategy: str = "qlora",
        rank: int = 16,
    ) -> dict[str, Any]:
        """Estimate memory for adapter training."""
        # Base model in 4-bit (QLoRA) or fp16 (LoRA)
        bytes_per_param = 0.5 if strategy == "qlora" else 2.0
        model_memory_gb = model_size_b * (bytes_per_param if strategy == "qlora" else 2.0)
        # For QLoRA on 7B: ~6GB. For LoRA fp16: ~14GB
        # Adapter overhead is minimal (~few MB per rank)
        adapter_memory_mb = (rank * 4096 * 2 * 4) / (1024 ** 2)  # Approximate
        # Gradients + optimizer for adapter only
        adapter_trainable_gb = adapter_memory_mb / 1024 * 0.1  # Very small

        return {
            "base_model_memory_gb": model_memory_gb,
            "adapter_memory_gb": adapter_memory_mb / 1024,
            "adapter_trainable_mb": adapter_memory_mb,
            "recommended_vram_gb": model_memory_gb + 2,  # Some overhead for training
            "note": "QLoRA allows 7B models on ~8GB VRAM. LoRA requires ~14GB for 7B fp16.",
        }

    def train_adapter(
        self,
        output_path: str,
        dataset_path: str,
        strategy: str = "lora",
        rank: int = 16,
        alpha: int = 32,
        epochs: int = 3,
        batch_size: int = 4,
        **kwargs,
    ) -> Optional[str]:
        """Train an adapter using the full pipeline."""
        if not self.is_available():
            raise RuntimeError(
                "Training dependencies not installed. "
                "Run: pip install -r requirements-training.txt"
            )

        from core.training.pretrain import PipelineConfig, run_training_pipeline
        from core.training.dataset import Dataset

        # Load dataset for metadata
        dataset = Dataset.from_json(dataset_path)
        dataset_samples = len(dataset)

        config = PipelineConfig(
            project_name="adapter-training",
            base_model=self.base_model,
            train_data_path=dataset_path,
            output_dir=output_path,
            epochs=epochs,
            batch_size=batch_size,
            strategy=strategy,
            lora_r=rank,
            lora_alpha=alpha,
        )

        logger.info(
            "adapter_training_started",
            base_model=self.base_model,
            strategy=strategy,
            output=output_path,
            dataset_samples=dataset_samples,
            rank=rank,
        )

        results = run_training_pipeline(config, dry_run=False)

        if results.get("status") == "completed":
            # The pipeline writes the final exported adapter to
            # output_path/run_name/export/hf (see PreTrainingPipeline.export()).
            # A previous version of this method pointed adapter_path at
            # output_path directly, which contains only adapter_info.json —
            # loading an adapter from there would fail with a missing
            # adapter_config.json/adapter_model.safetensors error.
            export_stage = results.get("stages", {}).get("export", {})
            adapter_path = export_stage.get("path") or str(Path(output_path) / config.run_name / "export" / "hf")

            adapter_info = AdapterInfo(
                adapter_path=str(adapter_path),
                base_model=self.base_model,
                strategy=strategy,
                rank=rank,
                alpha=alpha,
                dataset_samples=dataset_samples,
                epochs=epochs,
            )

            # Try to estimate params from saved model
            adapter_info.save_metadata(str(Path(adapter_path) / "adapter_info.json"))
            self.registry.register(adapter_info)
            logger.info("adapter_training_completed", path=str(adapter_path))
            return str(adapter_path)
        else:
            logger.error("adapter_training_failed", error=results.get("error"), results=results)
            return None

    def load_adapter(
        self,
        adapter_path: str,
        merge: bool = False,
    ) -> Any:
        """Load an adapter onto the base model."""
        if not self.is_available():
            raise RuntimeError("Dependencies not installed")
        from transformers import AutoModelForCausalLM
        from peft import PeftModel

        base_model = AutoModelForCausalLM.from_pretrained(
            self.base_model,
            trust_remote_code=True,
        )
        model = PeftModel.from_pretrained(base_model, adapter_path)
        logger.info("adapter_loaded", adapter_path=adapter_path, merge=merge)
        if merge:
            model = model.merge_and_unload()
        return model

    def merge_adapter(
        self,
        adapter_path: str,
        output_path: str,
        save_tokenizer: bool = True,
    ) -> str:
        """Merge adapter weights into base model and save."""
        if not self.is_available():
            raise RuntimeError("Dependencies not installed")
        from transformers import AutoTokenizer
        from peft import PeftModel
        from core.training.trainer import ModelTrainer, TrainingConfig

        # Load via trainer for simplicity
        trainer = ModelTrainer(TrainingConfig(model_name=self.base_model))
        # Actually load adapter on a model instance
        import torch
        model = self.load_adapter(adapter_path, merge=True)

        output = Path(output_path)
        output.mkdir(parents=True, exist_ok=True)
        model.save_pretrained(str(output))

        if save_tokenizer:
            tokenizer = AutoTokenizer.from_pretrained(self.base_model)
            tokenizer.save_pretrained(str(output))

        # Save adapter info
        info_path = Path(adapter_path) / "adapter_info.json"
        info = AdapterInfo.load_metadata(str(info_path)) if info_path.exists() else AdapterInfo(
            adapter_path=adapter_path,
            base_model=self.base_model,
            strategy="unknown",
        )
        info.adapter_path = str(output)
        info.save_metadata(str(output / "adapter_info.json"))

        logger.info("adapter_merged", adapter_path=adapter_path, output=output_path)
        return str(output)

    def compare_adapters(
        self,
        adapter_paths: list[str],
        eval_dataset_path: Optional[str] = None,
    ) -> dict[str, Any]:
        """Compare multiple adapters on the same evaluation dataset."""
        if not self.is_available():
            raise RuntimeError("Dependencies not installed")
        from core.training.trainer import ModelTrainer, TrainingConfig

        results = {}
        for path in adapter_paths:
            info_path = Path(path) / "adapter_info.json"
            info = AdapterInfo.load_metadata(str(info_path)) if info_path.exists() else AdapterInfo(
                adapter_path=path,
                base_model=self.base_model,
                strategy="unknown",
            )
            results[Path(path).name] = {
                "adapter_info": info.to_dict(),
                "exists": Path(path).exists(),
                "size_mb": sum(f.stat().st_size for f in Path(path).rglob("*") if f.is_file()) / (1024**2),
            }
        return results

    def export_for_inference(
        self,
        adapter_path: str,
        output_path: str,
        format: str = "hf",
    ) -> str:
        """Export adapter for deployment."""
        output = Path(output_path)
        output.mkdir(parents=True, exist_ok=True)

        if format == "hf":
            # For adapters, just copy adapter files
            adapter_dir = Path(adapter_path)
            for item in adapter_dir.iterdir():
                if item.is_file():
                    shutil.copy2(str(item), str(output / item.name))
            # Also save adapter config
            adapter_config = adapter_dir / "adapter_config.json"
            if adapter_config.exists():
                shutil.copy2(str(adapter_config), str(output / "adapter_config.json"))
        elif format == "merged":
            return self.merge_adapter(adapter_path, str(output))
        else:
            raise ValueError(f"Unknown export format: {format}")

        logger.info("adapter_exported", adapter_path=adapter_path, output=str(output), format=format)
        return str(output)
