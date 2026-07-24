# Model Training Guide — Adapter-First Approach

> **Transparency Notice**: Training a large language model from scratch requires thousands of H100/A100 GPUs, petabytes of training data, and millions of dollars in compute. This platform does **not** attempt to train models from scratch. Instead, it provides a production-grade adapter fine-tuning pipeline using **LoRA** and **QLoRA** — the actual method organizations use to customize AI models.

## What This System Actually Does

- **LoRA (Low-Rank Adaptation)**: Trains small adapter matrices (typically <1% of base model parameters) while keeping the base model frozen.
- **QLoRA (Quantized LoRA)**: Combines 4-bit quantization with LoRA adapters, allowing 7B+ parameter models to be fine-tuned on a single consumer GPU (~6-8GB VRAM).
- **Full Fine-Tuning**: Supported but requires substantial GPU resources.

**What it does NOT do**: Train large language models from scratch. That requires infrastructure this project explicitly does not claim to provide.

## Requirements

### Hardware (Realistic for Adapter Training)

| Strategy | Base Model | Recommended VRAM | Example Hardware |
|----------|-----------|-------------------|------------------|
| QLoRA 4-bit | 7B params | ~6-8 GB | RTX 3060 (12GB) |
| LoRA fp16 | 7B params | ~14-16 GB | RTX 4080 (16GB), A100 (40GB) |
| Full fine-tune | 7B params | ~28-32 GB | A100 (80GB), H100 |
| QLoRA 4-bit | 1.5B params | ~4 GB | GTX 1660 (6GB) |

### Software

```bash
pip install -r requirements-training.txt
```

Dependencies include: `torch`, `transformers`, `peft`, `datasets`, `bitsandbytes`, `accelerate`, `structlog`.

Heavier/optional extras (RLHF/DPO training via `trl`, multi-GPU via `deepspeed`/`fairscale`,
experiment tracking via `wandb`/`mlflow`, ONNX/GGUF export, dev/test tooling) live in
`requirements-training-extra.txt` — install that too if you need them:

```bash
pip install -r requirements-training-extra.txt
```

## Quick Start

### 1. Verify Installation

```bash
python3 -c "import torch, transformers, peft; print('Dependencies OK')"
```

### 2. Prepare Data

Create a JSONL file with your training examples:

```jsonl
{"text": "Your training example here."}
{"text": "Another example for fine-tuning."}
```

Sample data is provided in `data/sample_train.jsonl` and `data/sample_chat.jsonl`.

### 3. Train an Adapter

```bash
# Basic LoRA adapter on gpt2 (small, fast, works on CPU)
bash core/training/scripts/run_finetune.sh \
    --model gpt2 \
    --data data/sample_train.jsonl \
    --output ./adapters \
    --strategy lora

# QLoRA on a 7B model (requires GPU with 6GB+ VRAM)
bash core/training/scripts/run_finetune.sh \
    --model meta-llama/Llama-2-7b-hf \
    --data data/sample_instruction.json \
    --output ./adapters \
    --strategy qlora \
    --batch-size 2
```

### 4. Load and Use the Adapter

```python
from core.training.adapters import AdapterManager

manager = AdapterManager("gpt2")
model = manager.load_adapter("./adapters/my-adapter")
```

## Adapter Training Strategies

### LoRA

Best for: Fast iteration, moderate customization, models up to 13B parameters on standard GPUs.

```python
from core.training.config import AdapterTrainingConfig

config = AdapterTrainingConfig(
    base_model="meta-llama/Llama-2-7b-hf",
    adapter_name="my-domain-adapter",
    strategy="lora",
    rank=32,
    alpha=64,
    epochs=3,
    batch_size=4,
)
```

### QLoRA (Quantized LoRA)

Best for: Large models (7B+) on limited GPU memory. Uses 4-bit NormalFloat quantization.

```python
config = AdapterTrainingConfig(
    base_model="meta-llama/Llama-2-7b-hf",
    adapter_name="qlora-adapter",
    strategy="qlora",
    load_in_4bit=True,
    rank=64,
    alpha=128,
    batch_size=2,  # Smaller batch due to quantization overhead
    gradient_accumulation_steps=8,
)
```

### Full Fine-Tuning

Only recommended for small base models (<1B parameters) or with enterprise GPU clusters. Trains all parameters, not just adapters.

## Adapter Management

The `AdapterManager` provides production adapter lifecycle management:

```python
from core.training.adapters import AdapterManager, AdapterRegistry

manager = AdapterManager("meta-llama/Llama-2-7b-hf", adapter_registry=AdapterRegistry("./adapter-registry"))

# Train
adapter_path = manager.train_adapter("./adapters", dataset_path="./data/train.jsonl", strategy="qlora")

# Compare
results = manager.compare_adapters([adapter_path, "./adapters/other"])

# Merge for deployment (removes adapter overhead at inference time)
merged_path = manager.merge_adapter(adapter_path, "./merged-model")

# Export
export_path = manager.export_for_inference(adapter_path, "./deployment/adapters", format="merged")
```

## Adapter Registry

Track all adapters in a project:

```python
from core.training.adapters import AdapterRegistry, AdapterInfo

registry = AdapterRegistry("./adapter-registry")
info = AdapterInfo(adapter_path="./adapters/my-adapter", base_model="gpt2", strategy="lora", rank=16)
registry.register(info)
print(registry.list_adapters())
```

## Memory Estimates

Use the built-in memory calculator:

```python
manager = AdapterManager("meta-llama/Llama-2-7b-hf")
print(manager.estimate_memory(model_size_b=7.0, strategy="qlora"))
```

Output:
```json
{
  "base_model_memory_gb": 3.5,
  "adapter_memory_gb": 0.05,
  "adapter_memory_mb": 51.2,
  "recommended_vram_gb": 5.5,
  "note": "QLoRA allows 7B models on ~8GB VRAM."
}
```

## Evaluation

Evaluate adapter performance with standard NLP metrics:

```python
from core.training.evaluator import AdapterEvaluator

evaluator = AdapterEvaluator(tokenizer)
perplexity = evaluator.perplexity(model, eval_dataset)
accuracy = evaluator.evaluate_accuracy(model, eval_dataset, max_length=512)
```

## Production Deployment

### Export Formats

1. **Adapter Only** (`hf`): Keeps adapter separate. Load with `PeftModel.from_pretrained`. Smallest deployment footprint.
2. **Merged** (`merged`): Merge adapter weights into base model. Slightly larger file, faster inference (no adapter overhead).

### Inference Integration

```python
from arena.core.ai_runtime import AIRuntime

runtime = AIRuntime()
# Load adapter-enhanced model into runtime
# See adapter_manager.load_adapter() for model loading
```

## Monitoring Training

The `TrainingMonitor` tracks adapter training runs:

```python
from core.training.monitoring import TrainingMonitor

monitor = TrainingMonitor(run_id="run-001", adapter_path="./adapters/test")
monitor.start()
monitor.log_checkpoint("./checkpoints/step-100", step=100, epoch=1.0, loss=1.23)
monitor.log_metrics(100, {"loss": 1.23, "learning_rate": 3e-5})
print(monitor.to_summary())
```

## Data Formats

### Plain Text (Recommended for General Fine-Tuning)

```jsonl
{"text": "Your domain-specific text."}
```

### Instruction-Response (Recommended for Instruction Tuning)

```json
{"instruction": "What is X?", "response": "X is..."}
```

### Chat/Conversation (Recommended for Assistant Tuning)

```json
{"messages": [
  {"role": "system", "content": "You are a domain expert."},
  {"role": "user", "content": "Question?"},
  {"role": "assistant", "content": "Answer."}
]}
```

## Advanced Configuration

### Reducing Memory Usage

```python
config = AdapterTrainingConfig(
    strategy="qlora",
    load_in_4bit=True,
    batch_size=1,
    gradient_accumulation_steps=16,
    max_seq_length=512,  # Shorter sequences = less memory
    gradient_checkpointing=True,
)
```

### Improving Adapter Quality

- **Higher rank (`r`)**: More parameters, better adaptation, more memory. Try `r=32`, `r=64`.
- **Higher `alpha`**: Usually set to `2 * r`. Higher values = stronger adapter influence.
- **More data**: Adapters work best with hundreds to thousands of high-quality examples.
- **Target more modules**: Default targets attention layers (`q_proj`, `v_proj`). For deeper customization, include `gate_proj`, `up_proj`, `down_proj`, `o_proj`.

### Distributed Adapter Training

Adapter parameters are small enough that multi-GPU training is usually unnecessary. For very large adapters (`r=256+`) or very large batch requirements, use DeepSpeed or FSDP configurations via the `deepspeed_config` parameter.

## Troubleshooting

### Out of Memory
- Reduce `batch_size` to 1
- Enable `load_in_4bit=True` (QLoRA)
- Reduce `max_seq_length`
- Enable `gradient_checkpointing=True`

### Poor Adapter Performance
- Increase dataset size and quality
- Try a higher rank (`r=32` or `r=64`)
- Ensure data format matches adapter purpose (instruction data for instruction adapters)
- Check that target modules are appropriate for the model architecture

### Adapter Not Loading
- Verify adapter files exist (`adapter_config.json`, adapter weights)
- Check base model path matches what the adapter was trained on
- Ensure `peft` and `transformers` versions are compatible

## What This System Explicitly Does Not Provide

- **Pre-training from scratch**: Not supported, not planned, not feasible without enterprise infrastructure.
- **Massive data pipelines**: Data curation is the user's responsibility. We provide format utilities.
- **Multi-million-dollar compute**: Adapter training is designed for accessible hardware.

## Resources

- [PEFT Library](https://github.com/huggingface/peft)
- [QLoRA Paper](https://arxiv.org/abs/2305.14314)
- [LoRA Paper](https://arxiv.org/abs/2106.09685)
- [Transformers Fine-Tuning Guide](https://huggingface.co/docs/transformers/training)
