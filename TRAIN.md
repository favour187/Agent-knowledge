# Train Your Own Coding Model

## Quick Start (3 commands)

```bash
# 1. Install Python 3.10+ from python.org if you don't have it

# 2. Install dependencies
pip install torch transformers peft datasets accelerate

# 3. Run training
python3 train.py
```

That's it. The script auto-detects your hardware and picks the best model.

---

## What it does

1. Detects your hardware (GPU / Apple Silicon / CPU)
2. Picks the best model for your machine
3. Downloads the pretrained model from HuggingFace (one-time)
4. Loads your training data from `data/` directory
5. Applies LoRA adapter (trains ~4% of parameters)
6. Trains and saves the adapter
7. Tests inference

---

## Hardware Requirements

| Your machine | Model chosen | Time | Quality |
|---|---|---|---|
| NVIDIA GPU (24GB+) | Qwen2.5-Coder 7B (QLoRA 4-bit) | ~30 min | Excellent |
| NVIDIA GPU (16GB) | Qwen2.5-Coder 7B (LoRA) | ~45 min | Excellent |
| NVIDIA GPU (8GB) | Phi-3 Mini 3.8B (LoRA) | ~30 min | Very good |
| Mac M1/M2/M3 | GPT-2 124M (LoRA) | ~10 min | Basic |
| Any CPU | GPT-2 124M (LoRA) | ~30 min | Basic |

For better quality on Mac/CPU, change the model in the script.

---

## Adding Your Own Training Data

Put `.jsonl` files in the `data/` directory. Any of these formats work:

### Chat format
```json
{"messages": [{"role": "system", "content": "You are a coding assistant."}, {"role": "user", "content": "Write a for loop in Python."}, {"role": "assistant", "content": "Here's a for loop:\n```python\nfor i in range(10):\n    print(i)\n```"}]}
```

### Text format
```json
{"text": "A for loop in Python iterates over a sequence:\n```python\nfor item in items:\n    print(item)\n```"}
```

### Instruction format
```json
{"instruction": "Write a for loop in Python.", "response": "```python\nfor i in range(10):\n    print(i)\n```"}
```

### Tips for good training data
- More data = better (aim for 1000+ samples minimum)
- Include questions AND answers
- Cover the topics you want the model to know
- Clean, correct code examples are essential
- Mix topics: Python, JavaScript, SQL, algorithms, debugging, etc.

---

## No Restrictions — Full Control

The model runs 100% locally on your machine. No API keys. No internet needed after download. No content filters. No rate limits. No logging. Your data never leaves your laptop.

### Change the model
Edit `train.py`, line in `pick_model()`:
```python
# Any HuggingFace model works:
"name": "mistralai/Mistral-7B-v0.1"
"name": "meta-llama/Llama-3.1-8B"
"name": "Qwen/Qwen2.5-Coder-7B-Instruct"
"name": "deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct"
"name": "codellama/CodeLlama-7b-hf"
```

### Adjust training
```python
num_train_epochs = 10       # more epochs = learns more (but overfits on small data)
per_device_train_batch_size = 4  # increase if you have GPU memory
learning_rate = 1e-4        # lower = more stable, higher = learns faster
lora_r = 32                 # higher = more expressive, more params
```

### Use a GPU (if you have one)
```bash
# Check if CUDA is available
python3 -c "import torch; print(torch.cuda.is_available())"

# If True, the script auto-uses it. If False, you're on CPU/MPS.
```

### Google Colab (free GPU)
1. Go to https://colab.research.google.com
2. Runtime > Change runtime type > T4 GPU
3. Upload `train.py` and the `data/` folder
4. Run: `!pip install torch transformers peft datasets accelerate`
5. Run: `!python3 train.py`
6. Download the adapter from `adapters/` folder

---

## After Training

Your adapter is saved in `adapters/run-<timestamp>/adapter/`.

### Load and use it:
```python
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

# Load base model
model = AutoModelForCausalLM.from_pretrained("gpt2")  # or whatever base you used
tokenizer = AutoTokenizer.from_pretrained("gpt2")

# Attach your trained adapter
model = PeftModel.from_pretrained(model, "adapters/run-1234567890/adapter")

# Generate
inputs = tokenizer("Write a Python function to sort a list:", return_tensors="pt")
output = model.generate(**inputs, max_new_tokens=200)
print(tokenizer.decode(output[0], skip_special_tokens=True))
```

### Merge adapter into base model (for deployment):
```python
merged = model.merge_and_unload()
merged.save_pretrained("./merged-model")
tokenizer.save_pretrained("./merged-model")
# Now use merged-model like any HuggingFace model
```

---

## FAQ

**Q: Can I use Claude/GPT-4/Gemini as the base?**
A: No — their weights are proprietary. Use open models (Qwen, Llama, Mistral, DeepSeek).

**Q: How much data do I need?**
A: 50-100 samples for basic fine-tuning. 1000+ for good results. 10,000+ for excellent results.

**Q: Will this work offline?**
A: Yes, after the first run downloads the model. Or create a local model if download fails.

**Q: Can I use this commercially?**
A: Yes — all models listed are permissive licenses (Apache 2.0, MIT, or similar).

**Q: How do I add this model to my Arena agent?**
A: Point your agent's model config to the merged model directory.
