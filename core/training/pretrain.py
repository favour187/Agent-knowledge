"""
Pre-training Pipeline

End-to-end training pipeline with data preparation,
training, evaluation, and deployment.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class PipelineConfig:
    """Configuration for the training pipeline."""
    # Project
    project_name: str = "arena-model"
    run_name: Optional[str] = None
    
    # Model
    base_model: str = "gpt2"
    model_type: str = "causal_lm"
    
    # Training
    strategy: str = "lora"
    epochs: int = 3
    batch_size: int = 4
    gradient_accumulation: int = 4
    learning_rate: float = 3e-4
    warmup_steps: int = 100
    max_seq_length: int = 2048
    
    # LoRA
    lora_r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.05
    lora_target_modules: list[str] = field(default_factory=lambda: ["c_attn", "c_proj"])
    
    # Data
    train_data_path: str = "./data/train.jsonl"
    eval_data_path: Optional[str] = None
    test_data_path: Optional[str] = None
    
    # Output
    output_dir: str = "./output"
    checkpoint_dir: str = "./checkpoints"
    
    # Evaluation
    eval_interval: int = 500
    save_interval: int = 1000
    logging_interval: int = 10
    
    # Hardware
    device: str = "auto"
    num_workers: int = 4
    prefetch_factor: int = 2
    
    # Optimization
    use_wandb: bool = False
    wandb_project: Optional[str] = None
    use_tensorboard: bool = True

    def __post_init__(self):
        if self.run_name is None:
            self.run_name = f"{self.project_name}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"


class PreTrainingPipeline:
    """
    End-to-end pre-training pipeline.
    
    Stages:
    1. Data preparation and preprocessing
    2. Training with checkpointing
    3. Evaluation and metrics
    4. Model export and deployment
    """

    def __init__(self, config: PipelineConfig):
        self.config = config
        self.run_dir = Path(config.output_dir) / config.run_name
        self.run_dir.mkdir(parents=True, exist_ok=True)
        
        self.trainer = None
        self.metrics_history = []
        self.best_checkpoint = None

    def prepare_data(self) -> tuple[Any, Optional[Any], Optional[Any]]:
        """
        Stage 1: Prepare and preprocess training data.
        
        Returns:
            Tuple of (train_dataset, eval_dataset, test_dataset)
        """
        logger.info("preparing_data", config=self.config)
        
        from core.training.dataset import Dataset, prepare_instruction_dataset, prepare_chat_dataset
        
        # Load training data
        train_path = Path(self.config.train_data_path)
        if not train_path.exists():
            raise FileNotFoundError(f"Training data not found: {train_path}")
        
        # Detect format and load
        if train_path.suffix == ".jsonl":
            train_data = Dataset.from_json(str(train_path))
        elif train_path.suffix == ".json":
            # Try loading as a JSON array first; fall back to line-by-line
            # JSON objects (some datasets use a .json extension for JSONL content).
            with open(train_path) as f:
                data_content = f.read().strip()
            try:
                if data_content.startswith('['):
                    parsed = json.loads(data_content)
                    train_data = Dataset.from_list(parsed, text_column="text")
                else:
                    data = [json.loads(line) for line in data_content.splitlines() if line.strip()]
                    train_data = Dataset.from_list(data, text_column="text")
            except json.JSONDecodeError:
                data = [json.loads(line) for line in data_content.splitlines() if line.strip()]
                train_data = Dataset.from_list(data, text_column="text")
        elif train_path.suffix == ".csv":
            train_data = Dataset.from_csv(str(train_path))
        else:
            raise ValueError(f"Unsupported data format: {train_path.suffix}")
        
        # Auto-detect data format (handle DatasetDict from HF datasets)
        dataset_for_sample = train_data
        if hasattr(train_data, 'keys') and 'train' in train_data:
            # DatasetDict - select train split
            dataset_for_sample = train_data['train']
        
        sample = dataset_for_sample[0] if len(dataset_for_sample) > 0 else {}
        
        if "messages" in sample:
            logger.info("detected_chat_format")
            # Convert chat/conversation examples into a flat "text" field
            if hasattr(train_data, '_dataset'):
                train_data._dataset = train_data._dataset.map(
                    lambda x: {
                        "text": "\n".join([
                            f"{m['role']}: {m['content']}"
                            for m in x.get("messages", [])
                        ])
                    },
                    remove_columns=["messages"]
                )
        elif "instruction" in sample:
            logger.info("detected_instruction_format")
            # Convert instruction/response examples into a flat "text" field
            # (previously this branch only logged and never produced the "text"
            # column that the tokenizer step requires, causing a KeyError: 'text')
            if hasattr(train_data, '_dataset'):
                remove_cols = [c for c in ("instruction", "response", "output", "input") if c in sample]
                train_data._dataset = train_data._dataset.map(
                    lambda x: {
                        "text": (
                            f"### Instruction:\n{x.get('instruction', '')}\n\n"
                            + (f"### Input:\n{x.get('input', '')}\n\n" if x.get('input') else "")
                            + f"### Response:\n{x.get('response', x.get('output', ''))}"
                        )
                    },
                    remove_columns=remove_cols,
                )
        
        # Split data
        eval_data = None
        test_data = None
        
        if len(train_data) > 100:
            train_data, temp_data = train_data.split(train_size=0.9)
            eval_data, test_data = temp_data.split(train_size=0.5)
        
        # Save data stats
        self._save_metadata({
            "train_samples": len(train_data),
            "eval_samples": len(eval_data) if eval_data else 0,
            "test_samples": len(test_data) if test_data else 0,
        })
        
        logger.info(
            "data_prepared",
            train=len(train_data),
            eval=len(eval_data) if eval_data else 0,
        )
        
        return train_data, eval_data, test_data

    def train(
        self,
        train_dataset: Any,
        eval_dataset: Optional[Any] = None,
    ) -> dict[str, Any]:
        """
        Stage 2: Train the model.
        
        Returns:
            Training metrics and checkpoint paths
        """
        logger.info("starting_training", config=self.config)
        
        from core.training.trainer import TrainingConfig, ModelTrainer
        
        # Map strategy string to TrainingStrategy enum
        from core.training.trainer import TrainingStrategy
        strategy_str = self.config.strategy.lower()
        if strategy_str == "full_finetune" or strategy_str == "full":
            strategy_enum = TrainingStrategy.FULL_FINETUNE
        elif strategy_str == "lora":
            strategy_enum = TrainingStrategy.LORA
        elif strategy_str == "qlora":
            strategy_enum = TrainingStrategy.QLORA
        elif strategy_str == "rlhf":
            strategy_enum = TrainingStrategy.RLHF
        elif strategy_str == "dpo":
            strategy_enum = TrainingStrategy.DPO
        else:
            strategy_enum = TrainingStrategy.LORA
        
        # Create training config
        train_config = TrainingConfig(
            model_name=self.config.base_model,
            strategy=strategy_enum,
            num_epochs=self.config.epochs,
            per_device_train_batch_size=self.config.batch_size,
            per_device_eval_batch_size=self.config.batch_size,
            gradient_accumulation_steps=self.config.gradient_accumulation,
            learning_rate=self.config.learning_rate,
            max_seq_length=self.config.max_seq_length,
            warmup_ratio=self.config.warmup_steps / (len(train_dataset) * self.config.epochs) if len(train_dataset) > 0 else 0.1,
            lora_r=self.config.lora_r,
            lora_alpha=self.config.lora_alpha,
            lora_dropout=self.config.lora_dropout,
            lora_target_modules=self.config.lora_target_modules,
            output_dir=str(self.run_dir / "checkpoints"),
            run_name=self.config.run_name,
            save_steps=self.config.save_interval,
            eval_steps=self.config.eval_interval,
            logging_steps=self.config.logging_interval,
        )
        
        # Create trainer
        trainer = ModelTrainer(train_config)
        
        # Load model
        trainer.load_base_model()
        
        # Tokenize datasets
        from transformers import AutoTokenizer
        tokenizer = AutoTokenizer.from_pretrained(self.config.base_model)
        tokenizer.pad_token = tokenizer.eos_token
        
        def tokenize_function(examples):
            result = tokenizer(
                examples["text"],
                truncation=True,
                max_length=self.config.max_seq_length,
                padding=False,
            )
            result["labels"] = result["input_ids"].copy()
            return result
        
        # Convert to HF datasets if needed
        train_ds = train_dataset
        # If it's a DatasetDict (dictionary of splits), select the 'train' split
        if hasattr(train_ds, 'keys') and 'train' in train_ds:
            train_ds = train_ds['train']
        
        if hasattr(train_ds, '_dataset'):
            train_ds = train_ds._dataset
        eval_ds = eval_dataset
        if eval_dataset and hasattr(eval_dataset, '_dataset'):
            eval_ds = eval_dataset._dataset
        if hasattr(eval_dataset, 'keys') and 'train' in eval_dataset:
            # If eval_dataset is also a DatasetDict, select appropriate split
            # For simplicity, use 'test' or 'validation' if available, else 'train'
            split_key = 'test' if 'test' in eval_dataset else ('validation' if 'validation' in eval_dataset else 'train')
            eval_ds = eval_dataset[split_key] if split_key in eval_dataset else eval_ds
        
        # Tokenize
        train_ds = train_ds.map(
            tokenize_function,
            batched=True,
            remove_columns=["text"] if "text" in (train_ds.column_names if hasattr(train_ds, 'column_names') else []) else [],
        )
        if eval_ds:
            eval_ds = eval_ds.map(
                tokenize_function,
                batched=True,
                remove_columns=["text"] if "text" in (eval_ds.column_names if hasattr(eval_ds, 'column_names') else []) else [],
            )
        
        # Train
        result = trainer.train(train_ds, eval_ds)
        
        # Store results
        self.trainer = trainer
        self.metrics_history.append(result.to_dict())
        
        logger.info("training_completed", result=result.to_dict())
        
        return result.to_dict()

    def evaluate(self, test_dataset: Optional[Any] = None) -> dict[str, Any]:
        """
        Stage 3: Evaluate the trained model.
        """
        logger.info("evaluating_model")
        
        if self.trainer is None:
            raise ValueError("Model not trained yet")
        
        # Use test dataset if provided
        eval_ds = test_dataset
        if eval_ds and hasattr(eval_ds, '_dataset'):
            eval_ds = eval_ds._dataset
        
        metrics = self.trainer.evaluate(eval_ds)
        
        # Save metrics
        self._save_metadata({"evaluation": metrics})
        
        logger.info("evaluation_completed", metrics=metrics)
        
        return metrics

    def export(
        self,
        format: str = "hf",
        output_path: Optional[str] = None,
    ) -> str:
        """
        Stage 4: Export model for deployment.
        
        Args:
            format: Export format (hf, onnx, gguf)
            output_path: Custom output path
        
        Returns:
            Path to exported model
        """
        logger.info("exporting_model", format=format)
        
        if self.trainer is None:
            raise ValueError("Model not trained yet")
        
        output = output_path or str(self.run_dir / "export" / format)
        
        if format == "hf":
            # HuggingFace format
            self.trainer.export_for_inference(output)
        
        elif format == "onnx":
            # ONNX format for inference
            self._export_onnx(output)
        
        elif format == "gguf":
            # GGUF format for llama.cpp
            self._export_gguf(output)
        
        logger.info("export_completed", path=output)
        
        return output

    def _export_onnx(self, output_path: str) -> None:
        """Export to ONNX format."""
        try:
            from optimum.onnxruntime import ORTModelForCausalLM
            logger.info("onnx_export_not_fully_implemented")
        except ImportError:
            logger.warning("optimum_not_installed")

    def _export_gguf(self, output_path: str) -> None:
        """Export to GGUF format for llama.cpp."""
        # This would use llama.cpp's conversion tools
        logger.info("gguf_export_requires_llama_cpp")

    def _save_metadata(self, data: dict[str, Any]) -> None:
        """Save metadata to run directory."""
        metadata_path = self.run_dir / "metadata.json"
        
        existing = {}
        if metadata_path.exists():
            with open(metadata_path) as f:
                existing = json.load(f)
        
        existing.update(data)
        
        with open(metadata_path, "w") as f:
            json.dump(existing, f, indent=2)

    def cleanup_checkpoints(self, keep_last: int = 3) -> None:
        """Remove old checkpoints, keeping only the most recent ones."""
        checkpoint_dir = Path(self.config.checkpoint_dir) / self.config.run_name
        
        if not checkpoint_dir.exists():
            return
        
        checkpoints = sorted(
            checkpoint_dir.iterdir(),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        
        for checkpoint in checkpoints[keep_last:]:
            shutil.rmtree(checkpoint)
            logger.info("checkpoint_removed", path=str(checkpoint))


def run_training_pipeline(
    config: PipelineConfig,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Run the complete training pipeline.
    
    Args:
        config: Pipeline configuration
        dry_run: If True, only validate setup without training
    
    Returns:
        Pipeline results
    """
    pipeline = PreTrainingPipeline(config)
    
    results = {
        "config": config.__dict__,
        "stages": {},
        "completed_at": None,
        "status": "running",
    }
    
    try:
        # Stage 1: Prepare data
        logger.info("stage_1_data_preparation")
        train_data, eval_data, test_data = pipeline.prepare_data()
        results["stages"]["data_preparation"] = {
            "status": "completed",
            "train_samples": len(train_data),
            "eval_samples": len(eval_data) if eval_data else 0,
        }
        
        if dry_run:
            results["status"] = "dry_run_completed"
            return results
        
        # Stage 2: Training
        logger.info("stage_2_training")
        training_result = pipeline.train(train_data, eval_data)
        results["stages"]["training"] = {
            "status": "completed",
            "final_loss": training_result.get("final_loss"),
            "duration": training_result.get("duration_seconds"),
        }
        
        # Stage 3: Evaluation
        if test_data:
            logger.info("stage_3_evaluation")
            metrics = pipeline.evaluate(test_data)
            results["stages"]["evaluation"] = {
                "status": "completed",
                "metrics": metrics,
            }
        
        # Stage 4: Export
        logger.info("stage_4_export")
        export_path = pipeline.export()
        results["stages"]["export"] = {
            "status": "completed",
            "path": export_path,
        }
        
        results["status"] = "completed"
        
    except Exception as e:
        logger.error("pipeline_failed", error=str(e))
        results["status"] = "failed"
        results["error"] = str(e)
    
    results["completed_at"] = datetime.utcnow().isoformat()
    
    # Save results
    with open(pipeline.run_dir / "results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)
    
    return results
