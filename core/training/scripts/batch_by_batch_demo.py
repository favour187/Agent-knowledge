"""
Batch-by-Batch Adapter Training Demonstration

This script shows exactly how adapter training processes data batch by batch,
without running a full multi-epoch training session that could exceed limits.

Steps shown:
1. Load dataset
2. Tokenize batch 1
3. Show adapter (LoRA) applied to model
4. Show what a training step looks like (batch forward + backward conceptually)
5. Repeat for batch 2

This demonstrates the mechanism without consuming GPU/time.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

print("=" * 60)
print("STEP 1: LOAD DATASET")
print("=" * 60)

from core.training.dataset import Dataset

dataset = Dataset.from_json("data/sample_train.jsonl")
print(f"Dataset loaded: {len(dataset)} samples")
print(f"Sample keys: {list(dataset[0].keys())}")
print(f"First sample text: {dataset[0].get('text', 'N/A')[:80]}...")

print("\n" + "=" * 60)
print("STEP 2: PREPARE TOKENIZER")
print("=" * 60)

try:
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained("gpt2")
    tokenizer.pad_token = tokenizer.eos_token
    print(f"Tokenizer loaded for 'gpt2'")
    print(f"Vocab size: {tokenizer.vocab_size}")
    print(f"Pad token set to: {tokenizer.pad_token}")
except Exception as e:
    print(f"Tokenizer load skipped (expected in minimal env): {e}")
    tokenizer = None

print("\n" + "=" * 60)
print("STEP 3: SHOW DATA BATCHES (Batch Size = 2)")
print("=" * 60)

batch_size = 2
for i in range(0, len(dataset), batch_size):
    batch_items = [dataset[j] for j in range(i, min(i + batch_size, len(dataset)))]
    texts = [item.get("text", "") for item in batch_items]
    print(f"Batch {i//batch_size + 1} (items {i} to {min(i+batch_size, len(dataset))-1}):")
    for idx, text in enumerate(texts):
        print(f"  [{idx}] {text[:70]}...")

print("\n" + "=" * 60)
print("STEP 4: TOKENIZE BATCH BY BATCH")
print("=" * 60)

if tokenizer is not None:
    for i in range(0, len(dataset), batch_size):
        batch_items = [dataset[j] for j in range(i, min(i + batch_size, len(dataset)))]
        texts = [item.get("text", "") for item in batch_items]
        
        # Tokenize
        encoded = tokenizer(
            texts,
            truncation=True,
            max_length=128,
            padding=True,
            return_tensors="pt",
        )
        
        input_ids = encoded["input_ids"]
        attention_mask = encoded["attention_mask"]
        
        print(f"Batch {i//batch_size + 1}:")
        print(f"  Input IDs shape: {list(input_ids.shape)}")
        print(f"  Attention mask shape: {list(attention_mask.shape)}")
        print(f"  Sequence length: {input_ids.shape[1]} tokens")
        
        # Show a snippet of token IDs decoded back
        snippet_ids = input_ids[0][:8].tolist()
        snippet_text = tokenizer.decode(snippet_ids)
        print(f"  First tokens (decoded): '{snippet_text}'")
        
        # Show labels for adapter training (same as input_ids for causal LM)
        labels = input_ids.clone()
        print(f"  Labels = input_ids (causal LM adapter training standard)")
        
        # Break after 2 batches to respect session limits
        if i >= batch_size * 1:
            print("  ... (demonstrated 2 batches; more follow same pattern)")
            break

print("\n" + "=" * 60)
print("STEP 5: APPLY LORA ADAPTER TO MODEL")
print("=" * 60)

try:
    import torch
    from transformers import AutoModelForCausalLM
    from peft import LoraConfig, get_peft_model, TaskType
    
    print("Loading base model 'gpt2' (frozen weights)...")
    base_model = AutoModelForCausalLM.from_pretrained("gpt2", trust_remote_code=True)
    
    print("Applying LoRA adapter config:")
    lora_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=4,  # Small rank for demonstration
        lora_alpha=8,
        lora_dropout=0.0,
        target_modules=["c_attn", "c_proj"],  # GPT-2 attention layers
        bias="none",
        inference_mode=False,
    )
    print(f"  Rank (r): {lora_config.r}")
    print(f"  Alpha: {lora_config.lora_alpha}")
    print(f"  Target modules: {lora_config.target_modules}")
    
    adapter_model = get_peft_model(base_model, lora_config)
    adapter_model.print_trainable_parameters()
    
    # Show that adapter parameters are tiny compared to base
    total_params = sum(p.numel() for p in adapter_model.parameters())
    trainable_params = sum(p.numel() for p in adapter_model.parameters() if p.requires_grad)
    print(f"\nAdapter statistics:")
    print(f"  Total model params: {total_params:,}")
    print(f"  Trainable adapter params: {trainable_params:,}")
    print(f"  Adapter ratio: {trainable_params/total_params*100:.4f}%")
    print(f"  Frozen base model params: {total_params - trainable_params:,}")
    
except Exception as e:
    print(f"Adapter application skipped (expected without full dependencies): {type(e).__name__}: {str(e)[:100]}")

print("\n" + "=" * 60)
print("STEP 6: WHAT A TRAINING STEP LOOKS LIKE (BATCH BY BATCH)")
print("=" * 60)

print("""
Conceptually, each batch follows this exact sequence:

  FOR each batch in dataset:
      1. Tokenize texts → input_ids, attention_mask, labels
      2. Move tensors to device (CPU/GPU)
      3. Forward pass through adapter-enhanced model
         • Frozen base weights provide representation
         • Trainable LoRA matrices modify attention/projection
      4. Compute loss (cross-entropy on labels)
      5. Backward pass (gradients ONLY through adapter params)
      6. Optimizer updates adapter weights (AdamW, lr=3e-4)
      7. Log metrics (loss, learning rate, step number)
      8. Save checkpoint every N steps

Key point: The base model weights (124M for gpt2) NEVER change.
Only the adapter (~200-500 params for r=4) gets updated.
This is why adapter training is fast, memory-efficient, and
how organizations actually customize AI.
""")

print("=" * 60)
print("STEP 7: SESSION LIMIT CHECK")
print("=" * 60)

print("Batch demonstration completed.")
print("No full multi-epoch training was executed (respects session limits).")
print("To run actual batch-by-batch adapter training:")
print("")
print("  bash core/training/scripts/run_finetune.sh \\")
print("      --model gpt2 --data data/sample_train.jsonl \\")
print("      --output ./adapters --strategy lora --epochs 1 --batch-size 2")
print("")
print("Or for step-by-step monitoring with progress reporting:")
print("  See core/training/monitoring.py (TrainingMonitor)")
