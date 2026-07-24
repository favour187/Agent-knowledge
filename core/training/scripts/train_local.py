#!/usr/bin/env python3
"""
Train a local GPT-2 model with LoRA — no internet download needed.
Creates a small GPT-2 from scratch, builds a tokenizer from training data,
then runs the full LoRA training pipeline.
"""
import sys, os, time, json
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO_ROOT)

import torch
from transformers import GPT2Config, GPT2LMHeadModel, AutoTokenizer, PreTrainedTokenizerFast
from tokenizers import Tokenizer, models, pre_tokenizers, trainers

# ---- Step 1: Create a small GPT-2 model locally ----
print("=" * 60)
print("STEP 1: Creating local GPT-2 model (124M params equivalent)")
print("=" * 60)

config = GPT2Config(
    vocab_size=1000,
    n_positions=128,
    n_embd=256,
    n_layer=4,
    n_head=4,
    n_inner=512,
    activation_function="gelu_new",
    resid_pdrop=0.1,
    embd_pdrop=0.1,
    attn_pdrop=0.1,
    layer_norm_epsilon=1e-5,
    initializer_range=0.02,
    bos_token_id=0,
    eos_token_id=0,
    pad_token_id=0,
)

model = GPT2LMHeadModel(config)
save_path = os.path.join(REPO_ROOT, "models", "gpt2-local")
os.makedirs(save_path, exist_ok=True)
model.save_pretrained(save_path)
total_params = sum(p.numel() for p in model.parameters())
print(f"  Model saved to: {save_path}")
print(f"  Total parameters: {total_params:,}")
print(f"  Config: {config.n_layer} layers, {config.n_embd} embd, {config.n_head} heads")
del model

# ---- Step 2: Build a tokenizer from training data ----
print()
print("=" * 60)
print("STEP 2: Building tokenizer from training data")
print("=" * 60)

data_dir = os.path.join(REPO_ROOT, "data")
texts = []
for fname in ["sample_train.jsonl", "sample_chat.jsonl"]:
    fpath = os.path.join(data_dir, fname)
    if os.path.exists(fpath):
        with open(fpath) as f:
            for line in f:
                if line.strip():
                    obj = json.loads(line)
                    if "text" in obj:
                        texts.append(obj["text"])
                    elif "messages" in obj:
                        for msg in obj["messages"]:
                            texts.append(msg.get("content", ""))

# Also load instruction data (JSONL format)
inst_path = os.path.join(data_dir, "sample_instruction.json")
if os.path.exists(inst_path):
    with open(inst_path) as f:
        for line in f:
            if line.strip():
                item = json.loads(line)
                texts.append(item.get("instruction", ""))
                texts.append(item.get("response", ""))

print(f"  Training texts: {len(texts)}")

# Train a BPE tokenizer
tokenizer = Tokenizer(models.BPE(unk_token="<unk>"))
tokenizer.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
trainer = trainers.BpeTrainer(
    vocab_size=1000,
    min_frequency=1,
    special_tokens=["<unk>", "<pad>", "<bos>", "<eos>"],
)
tokenizer.train_from_iterator(texts, trainer=trainer)

# Wrap as PreTrainedTokenizerFast
fast_tokenizer = PreTrainedTokenizerFast(
    tokenizer_object=tokenizer,
    unk_token="<unk>",
    pad_token="<pad>",
    bos_token="<bos>",
    eos_token="<eos>",
)
fast_tokenizer.save_pretrained(save_path)
print(f"  Tokenizer vocab size: {fast_tokenizer.vocab_size}")
print(f"  Tokenizer saved to: {save_path}")

# ---- Step 3: Prepare training data as text field ----
print()
print("=" * 60)
print("STEP 3: Preparing training dataset")
print("=" * 60)

train_data = []
for t in texts:
    if t.strip():
        train_data.append({"text": t})

train_path = os.path.join(data_dir, "_train_local.jsonl")
with open(train_path, "w") as f:
    for item in train_data:
        f.write(json.dumps(item) + "\n")
print(f"  Dataset: {len(train_data)} samples -> {train_path}")

# ---- Step 4: Run LoRA training pipeline ----
print()
print("=" * 60)
print("STEP 4: Running LoRA training pipeline")
print("=" * 60)

from core.training.pretrain import PipelineConfig, run_training_pipeline

config = PipelineConfig(
    project_name="arena-agent-training",
    base_model=save_path,
    train_data_path=train_path,
    output_dir=os.path.join(REPO_ROOT, "adapters"),
    epochs=5,
    batch_size=2,
    strategy="lora",
    lora_r=8,
    lora_alpha=16,
    lora_dropout=0.0,
    lora_target_modules=["c_attn", "c_proj"],
    learning_rate=5e-4,
    max_seq_length=128,
    save_interval=10000,
    eval_interval=10000,
    logging_interval=1,
    gradient_accumulation=1,
)

print(f"  Base model: {config.base_model}")
print(f"  Strategy:   {config.strategy}")
print(f"  LoRA r={config.lora_r}, alpha={config.lora_alpha}")
print(f"  Epochs: {config.epochs}, LR: {config.learning_rate}")
print()

start = time.time()
results = run_training_pipeline(config, dry_run=False)
duration = time.time() - start

# ---- Results ----
print()
print("=" * 60)
print("TRAINING RESULTS")
print("=" * 60)
print(f"  Status:   {results['status']}")
print(f"  Duration: {duration:.1f}s")
print()

for stage_name, stage in results.get("stages", {}).items():
    print(f"  [{stage_name}]")
    print(f"    Status: {stage.get('status', '?')}")
    if "final_loss" in stage:
        print(f"    Final loss: {stage['final_loss']:.4f}")
    if "train_samples" in stage:
        print(f"    Samples: {stage['train_samples']}")
    if "path" in stage:
        print(f"    Output: {stage['path']}")

# Save results
results_file = os.path.join(config.output_dir, config.run_name, "results.json")
if os.path.exists(results_file):
    print(f"\n  Full results: {results_file}")

# Clean up temp file
os.remove(train_path)
print("\n✅ Training complete!")
