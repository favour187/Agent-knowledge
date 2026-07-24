#!/usr/bin/env python3
"""
Arena Agent Model Trainer — Laptop Edition

Works on ANY machine:
  - Mac M1/M2/M3 (MPS acceleration)
  - Windows/Linux with NVIDIA GPU (CUDA)
  - CPU only (slow but works)

Run:  python3 train.py
"""
import os
import sys
import json
import time
import platform
from pathlib import Path

# ─── Paths ───────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
ADAPTER_DIR = ROOT / "adapters"
MODEL_DIR = ROOT / "models"

# ─── Step 0: Check & install dependencies ────────────────────────────────
def ensure_deps():
    """Install required packages if missing."""
    required = ["torch", "transformers", "peft", "datasets", "accelerate", "tokenizers"]
    missing = []
    for pkg in required:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)

    if missing:
        print(f"Installing missing packages: {', '.join(missing)}")
        os.system(f"{sys.executable} -m pip install {' '.join(missing)}")
        print()

ensure_deps()

import torch
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    AutoConfig,
    TrainingArguments,
    Trainer,
)
from peft import LoraConfig, get_peft_model, TaskType


# ─── Step 1: Detect hardware ────────────────────────────────────────────
def detect_device():
    """Detect best available device."""
    if torch.cuda.is_available():
        name = torch.cuda.get_device_name(0)
        vram = torch.cuda.get_device_properties(0).total_mem / 1e9
        return "cuda", f"{name} ({vram:.1f} GB VRAM)"
    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps", "Apple Silicon (MPS)"
    else:
        return "cpu", f"CPU ({os.cpu_count()} cores)"


# ─── Step 2: Choose model based on hardware ─────────────────────────────
def pick_model(device):
    """Pick the best model for the available hardware."""
    if device == "cuda":
        vram = torch.cuda.get_device_properties(0).total_mem / 1e9
        if vram >= 20:
            # 24GB GPU — can do 7B with QLoRA 4-bit
            return {
                "name": "Qwen/Qwen2.5-Coder-7B-Instruct",
                "qlora": True,
                "desc": "Qwen2.5-Coder 7B (QLoRA 4-bit) — top coding model",
            }
        elif vram >= 14:
            # 16GB GPU — can do 7B with LoRA
            return {
                "name": "Qwen/Qwen2.5-Coder-7B-Instruct",
                "qlora": False,
                "desc": "Qwen2.5-Coder 7B (LoRA) — top coding model",
            }
        else:
            # Small GPU — use smaller model
            return {
                "name": "microsoft/Phi-3-mini-4k-instruct",
                "qlora": False,
                "desc": "Phi-3 Mini 3.8B (LoRA) — small but capable",
            }
    else:
        # CPU or MPS — use GPT-2 (fast enough to train)
        return {
            "name": "gpt2",
            "qlora": False,
            "desc": "GPT-2 124M (LoRA) — small, fast to train on CPU/MPS",
        }


# ─── Step 3: Load training data ─────────────────────────────────────────
def load_training_data():
    """Load all training data from data/ directory."""
    texts = []

    for fpath in sorted(DATA_DIR.glob("*.jsonl")):
        with open(fpath) as f:
            for line in f:
                if not line.strip():
                    continue
                obj = json.loads(line)
                if "text" in obj:
                    texts.append(obj["text"])
                elif "messages" in obj:
                    chat = ""
                    for msg in obj["messages"]:
                        role = msg.get("role", "user")
                        content = msg.get("content", "")
                        chat += f"{role}: {content}\n"
                    texts.append(chat.strip())

    # Also load .json instruction files
    for fpath in sorted(DATA_DIR.glob("*.json")):
        with open(fpath) as f:
            content = f.read().strip()
            try:
                if content.startswith("["):
                    items = json.loads(content)
                else:
                    items = [json.loads(l) for l in content.splitlines() if l.strip()]
                for item in items:
                    if "text" in item:
                        texts.append(item["text"])
                    elif "instruction" in item:
                        text = f"### Instruction:\n{item['instruction']}\n\n### Response:\n{item.get('response', item.get('output', ''))}"
                        texts.append(text)
            except json.JSONDecodeError:
                pass

    # Filter out very short texts
    texts = [t for t in texts if len(t.strip()) > 20]
    return texts


# ─── Step 4: Build tokenizer (only if model doesn't have one) ──────────
def get_tokenizer(model_name, model_dir):
    """Load or build tokenizer."""
    from tokenizers import Tokenizer, models, pre_tokenizers, trainers
    from transformers import PreTrainedTokenizerFast

    try:
        tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
        return tokenizer
    except Exception:
        pass

    # Can't download — build from training data
    print("  Building tokenizer from training data...")
    texts = load_training_data()

    tok = Tokenizer(models.BPE(unk_token="<unk>"))
    tok.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
    trainer = trainers.BpeTrainer(
        vocab_size=5000,
        min_frequency=1,
        special_tokens=["<unk>", "<pad>", "<bos>", "<eos>"],
    )
    tok.train_from_iterator(texts, trainer=trainer)

    tokenizer = PreTrainedTokenizerFast(
        tokenizer_object=tok,
        unk_token="<unk>",
        pad_token="<pad>",
        bos_token="<bos>",
        eos_token="<eos>",
    )
    tokenizer.save_pretrained(str(model_dir))
    return tokenizer


# ─── Step 5: Load or create model ───────────────────────────────────────
def load_model(model_name, tokenizer, qlora=False):
    """Load pretrained model (or create from config if offline)."""
    try:
        print(f"  Downloading {model_name} from HuggingFace...")
        if qlora:
            from transformers import BitsAndBytesConfig
            bnb_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.bfloat16,
                bnb_4bit_use_double_quant=True,
                bnb_4bit_quant_type="nf4",
            )
            model = AutoModelForCausalLM.from_pretrained(
                model_name,
                quantization_config=bnb_config,
                trust_remote_code=True,
                device_map="auto",
            )
        else:
            model = AutoModelForCausalLM.from_pretrained(
                model_name,
                trust_remote_code=True,
            )
        return model
    except Exception as e:
        print(f"  Download failed: {e}")
        print("  Creating model from config (no pretrained weights)...")
        return None


def create_local_model(tokenizer, device):
    """Create a local model when download fails."""
    vocab_size = max(tokenizer.vocab_size, 5000)
    config = AutoConfig.for_model("gpt2")
    config.vocab_size = vocab_size
    config.n_positions = 512
    config.n_embd = 384
    config.n_layer = 6
    config.n_head = 6
    config.n_inner = 768
    config.bos_token_id = tokenizer.bos_token_id or 0
    config.eos_token_id = tokenizer.eos_token_id or 0
    config.pad_token_id = tokenizer.pad_token_id or 0

    model = AutoModelForCausalLM.from_config(config)
    return model


# ─── Step 6: Apply LoRA ─────────────────────────────────────────────────
def apply_lora(model, model_name):
    """Apply LoRA adapter to the model."""
    model_lower = model_name.lower()
    if any(k in model_lower for k in ("llama", "mistral", "phi", "qwen", "deepseek")):
        target_modules = ["q_proj", "v_proj"]
    else:
        target_modules = ["c_attn", "c_proj"]

    lora_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=16,
        lora_alpha=32,
        lora_dropout=0.05,
        target_modules=target_modules,
        bias="none",
    )

    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()
    return model


# ─── Step 7: Tokenize dataset ───────────────────────────────────────────
def tokenize_data(texts, tokenizer, max_length=512):
    """Tokenize training texts."""
    from datasets import Dataset

    dataset = Dataset.from_dict({"text": texts})

    def tokenize_fn(examples):
        result = tokenizer(
            examples["text"],
            truncation=True,
            max_length=max_length,
            padding=False,
        )
        result["labels"] = result["input_ids"].copy()
        return result

    tokenized = dataset.map(tokenize_fn, batched=True, remove_columns=["text"])
    return tokenized


# ─── Step 8: Train ──────────────────────────────────────────────────────
def train(model, tokenizer, dataset, device, output_dir):
    """Run LoRA training."""
    os.makedirs(output_dir, exist_ok=True)

    args = TrainingArguments(
        output_dir=str(output_dir),
        num_train_epochs=5,
        per_device_train_batch_size=2,
        gradient_accumulation_steps=4,
        learning_rate=3e-4,
        warmup_ratio=0.1,
        lr_scheduler_type="cosine",
        weight_decay=0.01,
        logging_steps=5,
        save_strategy="no",
        fp16=(device == "cuda"),
        bf16=False,
        report_to=[],
        remove_unused_columns=False,
        dataloader_pin_memory=(device == "cuda"),
    )

    trainer = Trainer(
        model=model,
        args=args,
        train_dataset=dataset,
    )

    start = time.time()
    result = trainer.train()
    duration = time.time() - start

    return result, duration


# ─── Step 9: Save adapter ──────────────────────────────────────────────
def save_adapter(model, tokenizer, output_dir):
    """Save the LoRA adapter."""
    adapter_dir = Path(output_dir) / "adapter"
    adapter_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(adapter_dir))
    tokenizer.save_pretrained(str(adapter_dir))
    return adapter_dir


# ─── Step 10: Test inference ────────────────────────────────────────────
def test_inference(model, tokenizer, device):
    """Generate sample output to verify the model works."""
    prompts = [
        "user: Write a Python function to reverse a string.\nassistant:",
        "user: What is a hash map?\nassistant:",
    ]

    model.eval()
    for prompt in prompts:
        inputs = tokenizer(prompt, return_tensors="pt")
        if device != "cpu":
            inputs = {k: v.to(model.device) for k, v in inputs.items()}
        with torch.no_grad():
            output = model.generate(
                **inputs,
                max_new_tokens=80,
                temperature=0.7,
                top_p=0.9,
                do_sample=True,
                repetition_penalty=1.2,
            )
        result = tokenizer.decode(output[0], skip_special_tokens=True)
        generated = result[len(prompt):]
        print(f"  Q: {prompt.split(chr(10))[0].replace('user: ', '')}")
        print(f"  A: {generated[:150]}")
        print()


# ═══════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════
def main():
    print("=" * 60)
    print("  Arena — Model Training")
    print("=" * 60)
    print()

    # Hardware
    device, device_info = detect_device()
    print(f"  Device: {device_info}")
    print(f"  PyTorch: {torch.__version__}")
    print(f"  System: {platform.system()} {platform.machine()}")
    print()

    # Pick model
    model_config = pick_model(device)
    print(f"  Selected model: {model_config['name']}")
    print(f"  Strategy: {'QLoRA 4-bit' if model_config['qlora'] else 'LoRA'}")
    print(f"  Info: {model_config['desc']}")
    print()

    # Load data
    print("── Loading training data ──")
    texts = load_training_data()
    print(f"  Samples: {len(texts)}")
    if len(texts) == 0:
        print("  ERROR: No training data found in data/ directory")
        print("  Add .jsonl or .json files with 'text' or 'messages' fields")
        sys.exit(1)
    print()

    # Load tokenizer
    print("── Loading tokenizer ──")
    tokenizer = get_tokenizer(model_config["name"], MODEL_DIR)
    print(f"  Vocab size: {tokenizer.vocab_size}")
    print()

    # Load model
    print("── Loading model ──")
    model = load_model(model_config["name"], tokenizer, model_config["qlora"])
    if model is None:
        model = create_local_model(tokenizer, device)
        print(f"  Created local model: {sum(p.numel() for p in model.parameters()):,} params")
    else:
        print(f"  Loaded: {sum(p.numel() for p in model.parameters()):,} params")

    # Move to device (skip for QLoRA which uses device_map)
    if not model_config["qlora"]:
        if device == "cuda":
            model = model.to("cuda")
        elif device == "mps":
            model = model.to("mps")
    print()

    # Apply LoRA
    print("── Applying LoRA adapter ──")
    model = apply_lora(model, model_config["name"])
    print()

    # Tokenize
    print("── Tokenizing data ──")
    dataset = tokenize_data(texts, tokenizer, max_length=512)
    print(f"  Tokenized: {len(dataset)} examples")
    print()

    # Train
    print("── Training ──")
    output_dir = ADAPTER_DIR / f"run-{int(time.time())}"
    result, duration = train(model, tokenizer, dataset, device, output_dir)
    print(f"  Loss: {result.training_loss:.4f}")
    print(f"  Duration: {duration:.1f}s ({duration/60:.1f}min)")
    print()

    # Save
    print("── Saving adapter ──")
    adapter_dir = save_adapter(model, tokenizer, output_dir)
    print(f"  Saved to: {adapter_dir}")
    print()

    # Test
    print("── Testing inference ──")
    test_inference(model, tokenizer, device)

    print("=" * 60)
    print("  Training complete!")
    print(f"  Adapter: {adapter_dir}")
    print(f"  Base model: {model_config['name']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
