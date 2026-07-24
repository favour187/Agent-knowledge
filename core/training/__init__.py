"""
Training Module

Fine-tuning and model training infrastructure for the Arena AI Platform.
Supports LoRA, QLoRA, and full fine-tuning approaches.
"""

from core.training.trainer import ModelTrainer, TrainingConfig, TrainingResult
from core.training.dataset import Dataset, DatasetConfig, DataCollator
from core.training.loRA import LoRAConfig, LoRATrainer
from core.training.pretrain import PreTrainingPipeline
from core.training.adapters import AdapterInfo, AdapterRegistry, AdapterManager
from core.training.evaluator import AdapterEvaluator
from core.training.monitoring import TrainingMonitor
from core.training.config import AdapterTrainingConfig

__all__ = [
    "ModelTrainer",
    "TrainingConfig",
    "TrainingResult",
    "Dataset",
    "DatasetConfig",
    "DataCollator",
    "LoRAConfig",
    "LoRATrainer",
    "PreTrainingPipeline",
    "AdapterInfo",
    "AdapterRegistry",
    "AdapterManager",
    "AdapterEvaluator",
    "TrainingMonitor",
    "AdapterTrainingConfig",
]
