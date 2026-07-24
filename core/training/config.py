"""
Adapter Training Configuration

Centralized configuration management for adapter-based fine-tuning.
Replaces scattered config objects with a unified, validated config system.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class AdapterTrainingConfig:
    """Complete adapter training configuration."""
    # Model
    base_model: str = "gpt2"
    adapter_name: str = "my-adapter"
    output_dir: str = "./adapters"

    # Strategy
    strategy: str = "lora"  # lora, qlora, full_finetune
    rank: int = 16
    alpha: int = 32
    dropout: float = 0.05
    target_modules: list[str] = field(default_factory=lambda: ["q_proj", "v_proj"])

    # Quantization (for QLoRA)
    load_in_4bit: bool = False
    load_in_8bit: bool = False
    bnb_4bit_compute_dtype: str = "bfloat16"
    bnb_4bit_quant_type: str = "nf4"
    bnb_4bit_use_double_quant: bool = True

    # Training hyperparameters
    learning_rate: float = 3e-4
    epochs: int = 3
    batch_size: int = 4
    gradient_accumulation_steps: int = 4
    max_seq_length: int = 2048
    warmup_ratio: float = 0.03
    weight_decay: float = 0.01
    lr_scheduler_type: str = "cosine"

    # Data
    train_data_path: str = "./data/train.jsonl"
    eval_split: float = 0.1
    text_column: str = "text"

    # Hardware
    device: str = "auto"
    seed: int = 42
    mixed_precision: str = "bf16"  # fp16, bf16, fp32
    gradient_checkpointing: bool = False

    # Monitoring
    save_steps: int = 100
    eval_steps: int = 100
    logging_steps: int = 10
    save_total_limit: int = 3
    report_to: list[str] = field(default_factory=lambda: ["tensorboard"])

    def __post_init__(self):
        self.output_path = Path(self.output_dir) / self.adapter_name

    def to_dict(self) -> dict[str, Any]:
        return {
            "base_model": self.base_model,
            "adapter_name": self.adapter_name,
            "output_path": str(self.output_path),
            "strategy": self.strategy,
            "rank": self.rank,
            "alpha": self.alpha,
            "dropout": self.dropout,
            "target_modules": self.target_modules,
            "load_in_4bit": self.load_in_4bit,
            "load_in_8bit": self.load_in_8bit,
            "learning_rate": self.learning_rate,
            "epochs": self.epochs,
            "batch_size": self.batch_size,
            "gradient_accumulation_steps": self.gradient_accumulation_steps,
            "max_seq_length": self.max_seq_length,
            "warmup_ratio": self.warmup_ratio,
            "weight_decay": self.weight_decay,
            "lr_scheduler_type": self.lr_scheduler_type,
            "device": self.device,
            "seed": self.seed,
            "mixed_precision": self.mixed_precision,
            "gradient_checkpointing": self.gradient_checkpointing,
            "train_data_path": self.train_data_path,
            "eval_split": self.eval_split,
            "text_column": self.text_column,
        }

    @classmethod
    def from_file(cls, path: str) -> "AdapterTrainingConfig":
        import json
        with open(path) as f:
            data = json.load(f)
        # Filter to only fields defined in the dataclass
        fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in fields}
        return cls(**filtered)

    def save(self, path: str) -> None:
        import json
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
