"""
LoRA Configuration and Training

Low-Rank Adaptation (LoRA) and QLoRA implementations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)


class LoRATargetModules(str, Enum):
    """Common LoRA target modules by architecture."""
    LLAMA = "q_proj,v_proj,k_proj,o_proj,gate_proj,up_proj,down_proj"
    MISTRAL = "q_proj,v_proj,k_proj,o_proj,gate_proj,up_proj,down_proj"
    GPT2 = "c_attn,c_proj,c_fc"
    PHI = "q_proj,v_proj,k_proj,dense"
    CUSTOM = ""


@dataclass
class LoRAConfig:
    """
    LoRA (Low-Rank Adaptation) Configuration.
    
    LoRA reduces trainable parameters by decomposing weight updates
    into low-rank matrices, making fine-tuning more efficient.
    """
    # Rank and scaling
    r: int = 16  # Rank of decomposition
    lora_alpha: int = 32  # Scaling factor (usually 2x r)
    lora_dropout: float = 0.05  # Dropout for LoRA layers
    
    # Target modules (which layers to apply LoRA to)
    target_modules: list[str] = field(default_factory=lambda: ["q_proj", "v_proj"])
    
    # Module selection strategies
    modules_to_save: Optional[list[str]] = None  # Layers to train fully
    
    # Bias handling
    bias: str = "none"  # none, all, lora_only
    
    # Task type
    task_type: str = "CAUSAL_LM"  # CAUSAL_LM, SEQ_CLS, etc.
    
    # Inference mode
    inference_mode: bool = False
    
    # For QLoRA specific
    load_in_4bit: bool = False
    load_in_8bit: bool = False
    bnb_4bit_compute_dtype: str = "float16"
    bnb_4bit_quant_type: str = "nf4"
    bnb_4bit_use_double_quant: bool = True
    
    # Advanced
    fan_in_fan_out: bool = False
    modules_to_save_dtype: Optional[str] = None

    @classmethod
    def for_model(cls, model_name: str, **kwargs) -> "LoRAConfig":
        """Create LoRA config optimized for a specific model."""
        config = cls(**kwargs)
        
        # Auto-detect target modules
        model_lower = model_name.lower()
        if "llama" in model_lower:
            config.target_modules = LoRATargetModules.LLAMA.value.split(",")
        elif "mistral" in model_lower or "mixtral" in model_lower:
            config.target_modules = LoRATargetModules.MISTRAL.value.split(",")
        elif "gpt2" in model_lower:
            config.target_modules = LoRATargetModules.GPT2.value.split(",")
        elif "phi" in model_lower:
            config.target_modules = LoRATargetModules.PHI.value.split(",")
        
        return config

    @classmethod
    def qlora_config(cls, model_name: str, **kwargs) -> "LoRAConfig":
        """Create QLoRA config (4-bit quantized LoRA)."""
        config = cls.for_model(model_name, **kwargs)
        config.load_in_4bit = True
        config.bnb_4bit_compute_dtype = "bfloat16"  # Better for training
        return config

    @classmethod
    def efficient_config(cls, **kwargs) -> "LoRAConfig":
        """Create an efficient LoRA config with minimal parameters."""
        return cls(
            r=4,
            lora_alpha=8,
            lora_dropout=0.0,
            **kwargs
        )

    @classmethod
    def quality_config(cls, **kwargs) -> "LoRAConfig":
        """Create a high-quality LoRA config with more parameters."""
        return cls(
            r=64,
            lora_alpha=128,
            lora_dropout=0.1,
            **kwargs
        )

    def to_peft_dict(self) -> dict[str, Any]:
        """Convert to peft library format."""
        return {
            "r": self.r,
            "lora_alpha": self.lora_alpha,
            "lora_dropout": self.lora_dropout,
            "target_modules": self.target_modules if self.target_modules else "all-linear",
            "bias": self.bias,
            "task_type": self.task_type,
            "inference_mode": self.inference_mode,
        }

    def estimate_trainable_params(self, total_params: int) -> dict[str, Any]:
        """
        Estimate trainable parameters for this LoRA config.
        
        Formula: For each target layer, trainable = 2 * r * dim1 + 2 * r * dim2
        Where dim1, dim2 are the dimensions of the original weight matrix
        """
        # Rough estimation
        # Assuming average layer size and that we're targeting attention layers
        lora_params_per_layer = 2 * self.r * 4096 * 2  # Approximate
        
        # For a ~7B model, ~80% of params are in attention layers
        attention_params = total_params * 0.8
        num_layers = attention_params / (2 * 4096 * 4096)
        
        trainable = int(lora_params_per_layer * num_layers)
        
        return {
            "estimated_trainable": trainable,
            "total_params": total_params,
            "trainable_percentage": (trainable / total_params * 100) if total_params > 0 else 0,
            "rank": self.r,
            "compression_ratio": (total_params / trainable) if trainable > 0 else float('inf'),
        }


class LoRATrainer:
    """
    Trainer specialized for LoRA fine-tuning.
    """

    def __init__(
        self,
        config: LoRAConfig,
        model: Any,
        tokenizer: Any,
    ):
        self.config = config
        self.model = model
        self.tokenizer = tokenizer

    def apply_lora(self) -> None:
        """Apply LoRA to the model."""
        try:
            from peft import LoraConfig as PeftLoRAConfig, get_peft_model, TaskType
        except ImportError:
            raise ImportError("peft library required. Install with: pip install peft")
        
        peft_config = PeftLoRAConfig(
            r=self.config.r,
            lora_alpha=self.config.lora_alpha,
            lora_dropout=self.config.lora_dropout,
            target_modules=self.config.target_modules if self.config.target_modules else "all-linear",
            bias=self.config.bias,
            task_type=TaskType.CAUSAL_LM,
        )
        
        self.model = get_peft_model(self.model, peft_config)
        self.model.print_trainable_parameters()

    def merge_lora_weights(self, output_path: Optional[str] = None) -> Any:
        """
        Merge LoRA weights back into the base model.
        
        This creates a single model file without LoRA adapters.
        """
        from peft import PeftModel
        
        if hasattr(self.model, 'merge_and_unload'):
            merged_model = self.model.merge_and_unload()
            
            if output_path:
                merged_model.save_pretrained(output_path)
                self.tokenizer.save_pretrained(output_path)
            
            return merged_model
        
        raise ValueError("Model doesn't support weight merging")

    def get_lora_layers(self) -> list[dict[str, Any]]:
        """Get information about LoRA layers."""
        layers = []
        
        for name, module in self.model.named_modules():
            if "lora_" in name.lower():
                layers.append({
                    "name": name,
                    "type": type(module).__name__,
                })
        
        return layers

    def save_adapter(self, path: str) -> None:
        """Save only the LoRA adapter weights."""
        self.model.save_pretrained(path)
        logger.info("adapter_saved", path=path)

    def load_adapter(self, path: str) -> None:
        """Load LoRA adapter weights."""
        try:
            from peft import PeftModel
        except ImportError:
            raise ImportError("peft library required")
        
        self.model = PeftModel.from_pretrained(self.model, path)
        logger.info("adapter_loaded", path=path)


def calculate_lora_memory(
    model_size_b: float,
    batch_size: int,
    seq_length: int,
    precision: str = "fp16",
    lora_r: int = 16,
) -> dict[str, float]:
    """
    Calculate memory requirements for LoRA training.
    
    Args:
        model_size_b: Model size in billions of parameters
        batch_size: Training batch size
        seq_length: Sequence length
        precision: Model precision (fp16, fp32, bf16)
        lora_r: LoRA rank
    
    Returns:
        Memory estimates in GB
    """
    # Precision bytes
    bytes_per_param = {
        "fp32": 4,
        "fp16": 2,
        "bf16": 2,
        "int8": 1,
        "int4": 0.5,
    }
    bytes_per = bytes_per_param.get(precision, 2)
    
    # Model size: model_size_b is already in billions of params, so bytes-per-param
    # gives GB directly (e.g. 7B params * 4 bytes/param (fp32) = 28 GB).
    model_fp32_gb = model_size_b * bytes_per_param["fp32"]
    model_precision_gb = model_size_b * bytes_per
    
    # LoRA overhead (very small)
    lora_size_gb = 0  # ~a few MB typically
    
    # Activations (approximate)
    # ~6 * batch_size * seq_length * hidden_size * bytes_per_param
    hidden_size = 4096  # Approximate
    activations_gb = (6 * batch_size * seq_length * hidden_size * bytes_per) / 1e9
    
    # Gradients (only the frozen base model's forward activations matter for LoRA;
    # gradients are computed/stored at the requested precision)
    gradients_gb = model_precision_gb
    
    # Optimizer states (Adam: 2x model size, kept in fp32 for numerical stability)
    optimizer_gb = model_fp32_gb * 2
    
    return {
        "model_fp32": model_fp32_gb,
        "model_precision": model_precision_gb,
        "gradients": gradients_gb,
        "optimizer_states": optimizer_gb,
        "activations": activations_gb,
        "lora_overhead": lora_size_gb,
        "total_training": model_precision_gb + gradients_gb + optimizer_gb + activations_gb,
        "recommendation": f"Use QLoRA with 4-bit quantization for ~{model_fp32_gb / 8:.1f}GB required",
    }
