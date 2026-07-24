#!/bin/bash
# Complete Adapter Training Script for Arena AI Platform
# This script trains LoRA/QLoRA adapters — NOT models from scratch.
# Adapter training requires:
#   - A pre-trained base model (e.g., gpt2, meta-llama/Llama-2-7b-hf)
#   - A small dataset (hundreds to thousands of examples)
#   - A single GPU with 6-24GB VRAM (depending on model size and strategy)
#
# What this does NOT do:
#   - Train a large language model from scratch (requires thousands of GPUs,
#     petabytes of data, and millions of dollars)
#
# Usage:
#   bash core/training/scripts/run_finetune.sh --model gpt2 --data data/sample_train.jsonl --strategy lora --output ./adapters

set -e

# Default values
MODEL="gpt2"
DATA="data/sample_train.jsonl"
OUTPUT="./adapters"
STRATEGY="lora"
EPOCHS=3
BATCH_SIZE=4
LR=3e-4
LORA_R=16

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --model) MODEL="$2"; shift 2 ;;
        --data) DATA="$2"; shift 2 ;;
        --output) OUTPUT="$2"; shift 2 ;;
        --strategy) STRATEGY="$2"; shift 2 ;;
        --epochs) EPOCHS="$2"; shift 2 ;;
        --batch-size) BATCH_SIZE="$2"; shift 2 ;;
        --lr) LR="$2"; shift 2 ;;
        --lora-r) LORA_R="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

echo "=========================================="
echo "Arena Adapter Training Pipeline"
echo "=========================================="
echo "Base model:    $MODEL"
echo "Strategy:       $STRATEGY"
echo "Data:           $DATA"
echo "Output:         $OUTPUT"
echo "Epochs:         $EPOCHS"
echo "Batch size:     $BATCH_SIZE"
echo "Learning rate:  $LR"
echo "LoRA rank:      $LORA_R"
echo ""
echo "NOTE: This trains an adapter on a pre-trained model."
echo "It does NOT train a model from scratch."
echo ""

# Check for data file
if [ ! -f "$DATA" ]; then
    echo "❌ Data file not found: $DATA"
    echo "   Create sample data with: echo '{\"text\":\"...\"}' > $DATA"
    exit 1
fi

# Check Python environment
if ! command -v python3 &> /dev/null; then
    echo "❌ python3 not found"
    exit 1
fi

# Check if dependencies are available
python3 -c "
import torch
import transformers
import peft
print(f'PyTorch: {torch.__version__}')
print(f'Transformers: {transformers.__version__}')
print(f'PEFT: {peft.__version__}')
print(f'CUDA available: {torch.cuda.is_available()}')
" || {
    echo "❌ Training dependencies missing."
    echo "   Install with: pip install -r requirements-training.txt"
    exit 1
}

# Create output directory
mkdir -p "$OUTPUT"

# Run training
python3 -m core.training.cli train \
    --model "$MODEL" \
    --data "$DATA" \
    --output "$OUTPUT" \
    --strategy "$STRATEGY" \
    --epochs "$EPOCHS" \
    --batch-size "$BATCH_SIZE" \
    --lr "$LR" \
    --lora-r "$LORA_R"

echo ""
echo "✅ Adapter training completed. Results saved under: $OUTPUT/<run_name>/"
echo "   (adapter weights: $OUTPUT/<run_name>/export/hf/)"
echo ""
echo "To load the adapter:"
echo "  from core.training.adapters import AdapterManager"
echo "  manager = AdapterManager('$MODEL')"
echo "  model = manager.load_adapter('$OUTPUT/<run_name>/export/hf')"
echo ""
echo "(If you used AdapterManager.train_adapter(...) directly instead of this"
echo " script, it returns the correct adapter path for you automatically.)"
