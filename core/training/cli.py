#!/usr/bin/env python3
"""
Training CLI

Command-line interface for model training.
"""

import argparse
import json
import sys
from pathlib import Path

from core.training.pretrain import PreTrainingPipeline, PipelineConfig, run_training_pipeline


def main():
    parser = argparse.ArgumentParser(
        description="Train AI models with Arena Platform"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # Train command
    train_parser = subparsers.add_parser("train", help="Run training pipeline")
    train_parser.add_argument("--config", type=str, help="Path to config file")
    train_parser.add_argument("--model", type=str, default="gpt2", help="Base model name")
    train_parser.add_argument("--data", type=str, required=True, help="Training data path")
    train_parser.add_argument("--output", type=str, default="./output", help="Output directory")
    train_parser.add_argument("--epochs", type=int, default=3, help="Number of epochs")
    train_parser.add_argument("--batch-size", type=int, default=4, help="Batch size")
    train_parser.add_argument("--lr", type=float, default=3e-4, help="Learning rate")
    train_parser.add_argument("--strategy", type=str, default="lora", 
                            choices=["full", "lora", "qlora"], help="Training strategy")
    train_parser.add_argument("--lora-r", type=int, default=16, help="LoRA rank")
    train_parser.add_argument("--dry-run", action="store_true", help="Validate without training")
    
    # Prepare command
    prepare_parser = subparsers.add_parser("prepare", help="Prepare data")
    prepare_parser.add_argument("--input", type=str, required=True, help="Input data path")
    prepare_parser.add_argument("--output", type=str, required=True, help="Output path")
    prepare_parser.add_argument("--format", type=str, default="jsonl", help="Output format")
    
    # Export command
    export_parser = subparsers.add_parser("export", help="Export trained model")
    export_parser.add_argument("--checkpoint", type=str, required=True, help="Checkpoint path")
    export_parser.add_argument("--output", type=str, required=True, help="Output path")
    export_parser.add_argument("--format", type=str, default="hf", 
                             choices=["hf", "onnx", "gguf"], help="Export format")
    
    # Info command
    info_parser = subparsers.add_parser("info", help="Show model information")
    info_parser.add_argument("--model", type=str, required=True, help="Model name")
    
    args = parser.parse_args()
    
    if args.command == "train":
        run_train(args)
    elif args.command == "prepare":
        run_prepare(args)
    elif args.command == "export":
        run_export(args)
    elif args.command == "info":
        run_info(args)
    else:
        parser.print_help()
        sys.exit(1)


def run_train(args):
    """Run adapter training pipeline."""
    # Load config from file if provided
    config_data = {}
    if args.config and Path(args.config).exists():
        with open(args.config) as f:
            config_data = json.load(f)
    
    # Create pipeline config
    # Note: This pipeline trains adapters (LoRA/QLoRA) on pre-trained models.
    # It does NOT train models from scratch — that requires massive
    # GPU clusters, petabytes of data, and months of compute.
    config = PipelineConfig(
        project_name=Path(args.data).stem,
        base_model=args.model,
        train_data_path=args.data,
        output_dir=args.output,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.lr,
        strategy=args.strategy,
        lora_r=args.lora_r,
        **{k: v for k, v in config_data.items() if hasattr(PipelineConfig, k)},
    )
    
    print(f"Starting training pipeline...")
    print(f"  Model: {config.base_model}")
    print(f"  Strategy: {config.strategy}")
    print(f"  Data: {config.train_data_path}")
    print(f"  Output: {config.output_dir}")
    
    results = run_training_pipeline(config, dry_run=args.dry_run)
    
    if args.dry_run:
        print("\n✅ Dry run completed successfully")
        print(f"  Train samples: {results['stages']['data_preparation']['train_samples']}")
    else:
        print("\n✅ Training completed!")
        print(f"  Status: {results['status']}")
        if "training" in results["stages"]:
            print(f"  Final loss: {results['stages']['training'].get('final_loss')}")
            print(f"  Duration: {results['stages']['training'].get('duration')}s")


def run_prepare(args):
    """Prepare data."""
    from core.training.dataset import Dataset, prepare_instruction_dataset
    
    print(f"Loading data from {args.input}...")
    
    path = Path(args.input)
    if path.suffix == ".jsonl":
        data = Dataset.from_json(str(path))
    elif path.suffix == ".json":
        with open(path) as f:
            data = Dataset.from_list(json.load(f))
    else:
        print(f"Unsupported format: {path.suffix}")
        sys.exit(1)
    
    print(f"Loaded {len(data)} samples")
    print(f"Saving to {args.output}...")
    
    # Save in requested format
    if args.format == "jsonl":
        with open(args.output, "w") as f:
            for item in data:
                f.write(json.dumps(item) + "\n")
    else:
        data.save_to_disk(args.output)
    
    print(f"✅ Data prepared: {args.output}")


def run_export(args):
    """Export model."""
    from core.training.trainer import ModelTrainer, TrainingConfig
    
    print(f"Loading checkpoint from {args.checkpoint}...")
    
    trainer = ModelTrainer(TrainingConfig())
    trainer.load_checkpoint(args.checkpoint)
    
    print(f"Exporting to {args.output}...")
    export_path = trainer.export_for_inference(args.output)
    
    print(f"✅ Model exported: {export_path}")


def run_info(args):
    """Show model information."""
    from core.training.loRA import calculate_lora_memory, LoRAConfig
    
    print(f"\nModel: {args.model}")
    print("\nLoRA Memory Estimates (approximate):")
    
    estimates = calculate_lora_memory(
        model_size_b=7,  # 7B model
        batch_size=4,
        seq_length=2048,
    )
    
    for key, value in estimates.items():
        if isinstance(value, float):
            print(f"  {key}: {value:.2f} GB")
        else:
            print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
