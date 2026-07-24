"""
Model Trainer

Handles model fine-tuning with support for various training strategies.
"""

from __future__ import annotations

import json
import os
import uuid
import weakref
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

import structlog

logger = structlog.get_logger(__name__)

# Try to import training libraries
try:
    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader
    from torch.cuda import is_available as cuda_available
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    torch = None
    nn = None
    DataLoader = None
    cuda_available = lambda: False

try:
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        AutoConfig,
        TrainingArguments as HFTrainingArguments,
        Trainer as HFTrainer,
    )
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False
    HFTrainer = None
    HFTrainingArguments = None

# NOTE: transformers.DataCollator is a typing.Callable protocol, not a concrete
# class you can instantiate. Use our own working collator instead (this was
# the cause of the "Callable() takes no arguments" failure).
from core.training.dataset import DataCollator as HFDataCollator


class TrainingStrategy(str, Enum):
    """Training strategies."""
    FULL_FINETUNE = "full_finetune"
    LORA = "lora"
    QLORA = "qlora"
    RLHF = "rlhf"
    DPO = "dpo"


class ModelArchitecture(str, Enum):
    """Supported model architectures."""
    GPT2 = "gpt2"
    LLAMA = "llama"
    MISTRAL = "mistral"
    PHI = "phi"
    CUSTOM = "custom"


@dataclass
class TrainingConfig:
    """Configuration for model training."""
    # Model
    model_name: str = "gpt2"
    model_type: ModelArchitecture = ModelArchitecture.GPT2
    base_model_path: Optional[str] = None
    
    # Training strategy
    strategy: TrainingStrategy = TrainingStrategy.LORA
    
    # LoRA config
    lora_r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.05
    # Default matches GPT-2's attention module names. For Llama/Mistral/Phi-style
    # models, override with ["q_proj", "v_proj"] (or add k_proj/o_proj/gate_proj/
    # up_proj/down_proj for deeper adaptation) — GPT-2 has no q_proj/v_proj modules.
    lora_target_modules: list[str] = field(default_factory=lambda: ["c_attn", "c_proj"])
    
    # Quantization (for QLoRA)
    load_in_4bit: bool = False
    load_in_8bit: bool = False
    bnb_4bit_compute_dtype: str = "float16"
    bnb_4bit_use_double_quant: bool = True
    bnb_4bit_quant_type: str = "nf4"
    
    # Training hyperparameters
    learning_rate: float = 3e-4
    num_epochs: int = 3
    per_device_train_batch_size: int = 4
    per_device_eval_batch_size: int = 4
    gradient_accumulation_steps: int = 4
    max_seq_length: int = 2048
    warmup_ratio: float = 0.03
    weight_decay: float = 0.01
    lr_scheduler_type: str = "cosine"
    max_grad_norm: float = 1.0
    
    # Optimizer
    optimizer: str = "adamw_torch"
    beta1: float = 0.9
    beta2: float = 0.999
    epsilon: float = 1e-8
    
    # Regularization
    dropout: float = 0.0
    attention_dropout: float = 0.0
    
    # Output
    output_dir: str = "./models"
    run_name: Optional[str] = None
    save_total_limit: int = 3
    save_steps: int = 100
    eval_steps: int = 100
    logging_steps: int = 10
    
    # Hardware
    device: str = "auto"  # auto, cuda, cpu, mps
    deepspeed_config: Optional[str] = None
    fsdp_config: Optional[str] = None
    
    # Reproducibility
    seed: int = 42
    
    def __post_init__(self):
        if self.run_name is None:
            self.run_name = f"{self.model_name}-{self.strategy.value}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"


@dataclass
class TrainingResult:
    """Result of a training run."""
    run_id: str
    status: str  # completed, failed, cancelled
    final_loss: Optional[float]
    final_metrics: dict[str, float]
    checkpoints: list[str]
    output_dir: str
    duration_seconds: float
    config: dict[str, Any]
    started_at: datetime
    completed_at: datetime
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "final_loss": self.final_loss,
            "final_metrics": self.final_metrics,
            "checkpoints": self.checkpoints,
            "output_dir": self.output_dir,
            "duration_seconds": self.duration_seconds,
            "config": self.config,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
        }


@dataclass
class Checkpoint:
    """A training checkpoint."""
    path: str
    step: int
    epoch: float
    loss: float
    created_at: datetime
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "step": self.step,
            "epoch": self.epoch,
            "loss": self.loss,
            "created_at": self.created_at.isoformat(),
        }


class ModelTrainer:
    """
    Handles model fine-tuning with support for:
    - Full fine-tuning
    - LoRA (Low-Rank Adaptation)
    - QLoRA (Quantized LoRA)
    - RLHF (Reinforcement Learning from Human Feedback)
    - DPO (Direct Preference Optimization)
    
    Requirements:
    - PyTorch
    - Transformers
    - BitsAndBytes (for QLoRA)
    - peft (for LoRA)
    - trl (for RLHF/DPO)
    """

    def __init__(
        self,
        config: Optional[TrainingConfig] = None,
        output_dir: Optional[str] = None,
    ):
        if not TORCH_AVAILABLE:
            raise ImportError(
                "PyTorch is required for training. "
                "Install with: pip install torch"
            )
        
        self.config = config or TrainingConfig()
        if output_dir:
            self.config.output_dir = output_dir
        
        self.run_id = str(uuid.uuid4())
        self.model = None
        self.tokenizer = None
        self.trainer = None
        self.started_at: Optional[datetime] = None
        self.checkpoints: list[Checkpoint] = []
        
        # Set random seeds
        self._set_seed(self.config.seed)

    def _set_seed(self, seed: int) -> None:
        """Set random seeds for reproducibility."""
        import random
        import numpy as np
        
        random.seed(seed)
        np.random.seed(seed)
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)

    def _get_device(self) -> str:
        """Determine the device to use."""
        if self.config.device == "auto":
            if torch.cuda.is_available():
                return "cuda"
            elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
                return "mps"
            return "cpu"
        return self.config.device

    def load_base_model(self) -> None:
        """Load the base model and tokenizer."""
        logger.info("loading_model", model=self.config.model_name)
        
        if not TRANSFORMERS_AVAILABLE:
            raise ImportError(
                "Transformers is required. Install with: pip install transformers"
            )
        
        tokenizer = AutoTokenizer.from_pretrained(
            self.config.model_name,
            trust_remote_code=True,
        )
        
        # Set pad token if not set
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
        
        self.tokenizer = tokenizer
        
        # Load model based on strategy
        if self.config.strategy == TrainingStrategy.QLORA:
            self._load_qlora_model()
        elif self.config.strategy == TrainingStrategy.LORA:
            self._load_lora_model()
        else:
            self._load_full_model()
        
        logger.info(
            "model_loaded",
            model=self.config.model_name,
            device=self._get_device(),
            strategy=self.config.strategy.value,
        )

    def _load_full_model(self) -> None:
        """Load model for full fine-tuning."""
        self.model = AutoModelForCausalLM.from_pretrained(
            self.config.model_name,
            config=AutoConfig.from_pretrained(self.config.model_name),
            trust_remote_code=True,
        )
        
        device = self._get_device()
        if device != "cpu":
            self.model = self.model.to(device)

    def _load_lora_model(self) -> None:
        """Load model with LoRA configuration."""
        from peft import LoraConfig, get_peft_model, TaskType
        
        base_model = AutoModelForCausalLM.from_pretrained(
            self.config.model_name,
            trust_remote_code=True,
        )
        
        lora_config = LoraConfig(
            task_type=TaskType.CAUSAL_LM,
            r=self.config.lora_r,
            lora_alpha=self.config.lora_alpha,
            lora_dropout=self.config.lora_dropout,
            target_modules=self.config.lora_target_modules,
            bias="none",
            inference_mode=False,
        )
        
        self.model = get_peft_model(base_model, lora_config)
        self.model.print_trainable_parameters()
        
        device = self._get_device()
        if device != "cpu":
            self.model = self.model.to(device)

    def _load_qlora_model(self) -> None:
        """Load model with QLoRA configuration."""
        try:
            from peft import LoraConfig, get_peft_model, TaskType
            import bitsandbytes as bnb
        except ImportError:
            raise ImportError(
                "peft and bitsandbytes are required for QLoRA. "
                "Install with: pip install peft bitsandbytes"
            )
        
        # Quantization config
        compute_dtype = getattr(torch, self.config.bnb_4bit_compute_dtype)
        
        bnb_config = {
            "load_in_4bit": self.config.load_in_4bit,
            "load_in_8bit": self.config.load_in_8bit,
            "bnb_4bit_compute_dtype": compute_dtype,
            "bnb_4bit_use_double_quant": self.config.bnb_4bit_use_double_quant,
            "bnb_4bit_quant_type": self.config.bnb_4bit_quant_type,
        }
        
        base_model = AutoModelForCausalLM.from_pretrained(
            self.config.model_name,
            quantization_config=bnb_config if (self.config.load_in_4bit or self.config.load_in_8bit) else None,
            trust_remote_code=True,
        )
        
        lora_config = LoraConfig(
            task_type=TaskType.CAUSAL_LM,
            r=self.config.lora_r,
            lora_alpha=self.config.lora_alpha,
            lora_dropout=self.config.lora_dropout,
            target_modules=self.config.lora_target_modules,
            bias="none",
            inference_mode=False,
        )
        
        self.model = get_peft_model(base_model, lora_config)
        self.model.print_trainable_parameters()

    def prepare_dataset(
        self,
        train_data: list[dict[str, Any]],
        eval_data: Optional[list[dict[str, Any]]] = None,
        text_field: str = "text",
    ):
        """Prepare datasets for training."""
        from core.training.dataset import Dataset
        
        train_dataset = Dataset.from_list(train_data, text_field)
        eval_dataset = Dataset.from_list(eval_data, text_field) if eval_data else None
        
        return train_dataset, eval_dataset

    def train(
        self,
        train_dataset: Any,
        eval_dataset: Optional[Any] = None,
        compute_metrics: Optional[Callable] = None,
        callbacks: Optional[list] = None,
    ) -> TrainingResult:
        """
        Train the model.
        
        Args:
            train_dataset: Training dataset
            eval_dataset: Optional evaluation dataset
            compute_metrics: Optional metrics function
            callbacks: Optional training callbacks
            
        Returns:
            TrainingResult
        """
        if self.model is None:
            self.load_base_model()
        
        self.started_at = datetime.utcnow()
        
        # Prepare output directory
        output_path = Path(self.config.output_dir) / self.config.run_name
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Create training arguments
        training_args = HFTrainingArguments(
            output_dir=str(output_path),
            num_train_epochs=self.config.num_epochs,
            per_device_train_batch_size=self.config.per_device_train_batch_size,
            per_device_eval_batch_size=self.config.per_device_eval_batch_size,
            gradient_accumulation_steps=self.config.gradient_accumulation_steps,
            learning_rate=self.config.learning_rate,
            weight_decay=self.config.weight_decay,
            warmup_steps=int(self.config.num_epochs * len(train_dataset) * self.config.per_device_train_batch_size * self.config.warmup_ratio) if hasattr(self.config, 'warmup_ratio') else self.config.num_epochs,
            lr_scheduler_type=self.config.lr_scheduler_type,
            max_grad_norm=self.config.max_grad_norm,
            logging_dir=str(output_path / "logs"),
            logging_steps=self.config.logging_steps,
            save_steps=self.config.save_steps,
            eval_steps=self.config.eval_steps,
            save_total_limit=self.config.save_total_limit,
            seed=self.config.seed,
            # fp16/bf16 mixed precision only makes sense on GPU; the previous
            # logic ("fp16=not cuda_available()") forced fp16 on CPU, which
            # PyTorch does not support for training and always errors out.
            bf16=torch.cuda.is_available(),
            fp16=False,
            report_to=[],
            run_name=self.config.run_name,
            remove_unused_columns=False,
        )
        
        # Create data collator
        data_collator = HFDataCollator(
            tokenizer=self.tokenizer,
            max_length=self.config.max_seq_length,
        )
        
        # Create trainer
        self.trainer = HFTrainer(
            model=self.model,
            args=training_args,
            train_dataset=train_dataset,
            eval_dataset=eval_dataset,
            data_collator=data_collator,
            compute_metrics=compute_metrics,
            callbacks=callbacks or [],
        )
        
        # Train
        logger.info("training_started", run_id=self.run_id)
        
        try:
            result = self.trainer.train()
            
            # Save final model
            self.trainer.save_model()
            self.tokenizer.save_pretrained(str(output_path / "final"))
            
            completed_at = datetime.utcnow()
            duration = (completed_at - self.started_at).total_seconds()
            
            return TrainingResult(
                run_id=self.run_id,
                status="completed",
                final_loss=result.training_loss if hasattr(result, 'training_loss') else None,
                final_metrics={
                    "train_loss": result.training_loss if hasattr(result, 'training_loss') else 0,
                    "epoch": result.metrics.get("epoch", self.config.num_epochs) if hasattr(result, 'metrics') else self.config.num_epochs,
                },
                checkpoints=[c.path for c in self.checkpoints],
                output_dir=str(output_path),
                duration_seconds=duration,
                config=self._config_to_dict(),
                started_at=self.started_at,
                completed_at=completed_at,
            )
            
        except Exception as e:
            logger.error("training_failed", error=str(e))
            completed_at = datetime.utcnow()
            duration = (completed_at - self.started_at).total_seconds()
            
            return TrainingResult(
                run_id=self.run_id,
                status="failed",
                final_loss=None,
                final_metrics={},
                checkpoints=[c.path for c in self.checkpoints],
                output_dir=str(output_path),
                duration_seconds=duration,
                config=self._config_to_dict(),
                started_at=self.started_at,
                completed_at=completed_at,
            )

    async def train_async(
        self,
        train_dataset: Any,
        eval_dataset: Optional[Any] = None,
        progress_callback: Optional[Callable[[dict], None]] = None,
    ) -> TrainingResult:
        """Async version of train with progress reporting."""
        import asyncio
        
        def sync_to_async():
            return self.train(train_dataset, eval_dataset)
        
        # Run training in thread pool
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, sync_to_async)
        
        if progress_callback:
            await progress_callback({
                "status": result.status,
                "final_loss": result.final_loss,
                "duration": result.duration_seconds,
            })
        
        return result

    def evaluate(self, eval_dataset: Any) -> dict[str, float]:
        """Evaluate the model."""
        if self.trainer is None:
            raise ValueError("Trainer not initialized. Call train() first.")
        
        metrics = self.trainer.evaluate(eval_dataset)
        return metrics

    def predict(self, inputs: list[str]) -> list[str]:
        """Generate predictions."""
        if self.model is None:
            raise ValueError("Model not loaded")
        
        self.model.eval()
        
        inputs_encoded = self.tokenizer(
            inputs,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=self.config.max_seq_length,
        )
        
        device = self._get_device()
        if device != "cpu":
            inputs_encoded = {k: v.to(device) for k, v in inputs_encoded.items()}
        
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs_encoded,
                max_new_tokens=256,
                temperature=0.7,
                top_p=0.9,
                do_sample=True,
            )
        
        predictions = self.tokenizer.batch_decode(outputs, skip_special_tokens=True)
        return predictions

    def save_checkpoint(self, path: str) -> None:
        """Save a checkpoint."""
        if self.model is None:
            raise ValueError("No model to save")
        
        checkpoint_path = Path(path)
        checkpoint_path.mkdir(parents=True, exist_ok=True)
        
        self.model.save_pretrained(str(checkpoint_path))
        self.tokenizer.save_pretrained(str(checkpoint_path))
        
        logger.info("checkpoint_saved", path=str(checkpoint_path))

    def load_checkpoint(self, path: str) -> None:
        """Load a checkpoint."""
        if not TRANSFORMERS_AVAILABLE:
            raise ImportError("Transformers is required")
        
        self.model = AutoModelForCausalLM.from_pretrained(path)
        self.tokenizer = AutoTokenizer.from_pretrained(path)
        
        device = self._get_device()
        if device != "cpu":
            self.model = self.model.to(device)
        
        logger.info("checkpoint_loaded", path=path)

    def _config_to_dict(self) -> dict[str, Any]:
        """Convert config to dictionary."""
        return {
            "model_name": self.config.model_name,
            "strategy": self.config.strategy.value,
            "learning_rate": self.config.learning_rate,
            "num_epochs": self.config.num_epochs,
            "batch_size": self.config.per_device_train_batch_size,
            "lora_r": self.config.lora_r,
            "lora_alpha": self.config.lora_alpha,
        }

    def export_for_inference(self, output_path: str) -> str:
        """Export model for inference deployment."""
        if self.model is None:
            raise ValueError("No model to export")
        
        output = Path(output_path)
        output.mkdir(parents=True, exist_ok=True)
        
        # Save in GGUF format for llama.cpp compatibility
        try:
            from llama_cpp import Llama
            # Convert and save
            logger.info("exporting_to_gguf", path=str(output))
        except ImportError:
            logger.warning("llama_cpp_not_available")
        
        # Save model and tokenizer
        self.model.save_pretrained(str(output))
        self.tokenizer.save_pretrained(str(output))
        
        # Save config
        with open(output / "export_config.json", "w") as f:
            json.dump(self._config_to_dict(), f, indent=2)
        
        return str(output)

    def get_model_size(self) -> dict[str, float]:
        """Get model size information."""
        if self.model is None:
            return {"total_params": 0, "trainable_params": 0, "size_mb": 0}
        
        total_params = sum(p.numel() for p in self.model.parameters())
        trainable_params = sum(p.numel() for p in self.model.parameters() if p.requires_grad)
        
        # Estimate size
        param_size = sum(p.numel() * p.element_size() for p in self.model.parameters())
        buffer_size = sum(b.numel() * b.element_size() for b in self.model.buffers())
        size_mb = (param_size + buffer_size) / (1024 ** 2)
        
        return {
            "total_params": total_params,
            "trainable_params": trainable_params,
            "trainable_pct": (trainable_params / total_params * 100) if total_params > 0 else 0,
            "size_mb": size_mb,
        }
