#!/bin/bash
# Training Setup Script for Arena AI Platform
# Sets up the environment and starts training

set -e

echo "================================================"
echo "Arena AI Platform - Training Setup"
echo "================================================"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check Python version
echo -e "\n${YELLOW}Checking Python version...${NC}"
PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1,2)
if [[ $(echo "$PYTHON_VERSION >= 3.9" | bc -l) -eq 1 ]]; then
    echo -e "${GREEN}✓ Python $PYTHON_VERSION${NC}"
else
    echo -e "${RED}✗ Python 3.9+ required${NC}"
    exit 1
fi

# Check for CUDA
echo -e "\n${YELLOW}Checking GPU availability...${NC}"
if command -v nvidia-smi &> /dev/null; then
    nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv
    echo -e "${GREEN}✓ NVIDIA GPU detected${NC}"
else
    echo -e "${YELLOW}⚠ No NVIDIA GPU detected (CPU training only)${NC}"
fi

# Create virtual environment
echo -e "\n${YELLOW}Setting up virtual environment...${NC}"
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo -e "${GREEN}✓ Virtual environment created${NC}"
fi

source venv/bin/activate

# Install core dependencies
echo -e "\n${YELLOW}Installing core dependencies...${NC}"
pip install --upgrade pip setuptools wheel

# Install PyTorch (with CUDA support)
echo -e "\n${YELLOW}Installing PyTorch...${NC}"
if command -v nvidia-smi &> /dev/null; then
    pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
    echo -e "${GREEN}✓ PyTorch with CUDA support${NC}"
else
    pip install torch torchvision torchaudio
    echo -e "${GREEN}✓ PyTorch (CPU)${NC}"
fi

# Install training dependencies
echo -e "\n${YELLOW}Installing training dependencies...${NC}"
pip install -r requirements-training.txt
echo -e "${GREEN}✓ Training dependencies installed${NC}"

# Install arena platform
echo -e "\n${YELLOW}Installing Arena Platform...${NC}"
pip install -e .
echo -e "${GREEN}✓ Arena Platform installed${NC}"

# Create directories
echo -e "\n${YELLOW}Creating directories...${NC}"
mkdir -p data models output checkpoints logs
echo -e "${GREEN}✓ Directories created${NC}"

# Verify installation
echo -e "\n${YELLOW}Verifying installation...${NC}"
python -c "
import torch
import transformers
import peft
print(f'PyTorch: {torch.__version__}')
print(f'Transformers: {transformers.__version__}')
print(f'PEFT: {peft.__version__}')
print(f'CUDA available: {torch.cuda.is_available()}')
if torch.cuda.is_available():
    print(f'GPU: {torch.cuda.get_device_name(0)}')
"

echo -e "\n${GREEN}================================================"
echo "Training environment ready!"
echo "================================================"
echo ""
echo "To start training:"
echo "  1. Add your training data to ./data/"
echo "  2. Run: python -m core.training.cli train --data ./data/train.jsonl"
echo ""
echo "For more options:"
echo "  python -m core.training.cli --help"
echo ""
