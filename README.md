# Arena AI Platform

A comprehensive autonomous AI agent platform with multi-agent orchestration, persistent memory, advanced reasoning, and self-improvement capabilities.

## Features

### Core AI Components
- **AI Runtime**: Support for OpenAI, Anthropic, and local models with streaming and rate limiting
- **Planning Engine**: Task decomposition, dependency management, and adaptive planning
- **Reasoning Engine**: Chain-of-thought, tree-of-thought, and ReAct reasoning strategies
- **Task Manager**: Priority queues, retries, timeouts, and execution tracking
- **Agent Manager**: Multi-agent lifecycle and orchestration
- **Tool Manager**: Dynamic tool registry with schema validation and sandboxed execution

### Memory & Knowledge
- **Memory Manager**: Episodic, semantic, and procedural memory with vector embeddings
- **Knowledge Base**: Entity management, relationship graphs, and semantic search
- **Context Manager**: Conversation context with compression and windowing

### Multi-Agent
- **Multi-Agent Orchestrator**: Team coordination and collaborative task execution
- **Consensus Builder**: Voting and consensus building among agents

### Quality & Improvement
- **Self-Evaluator**: Multi-dimensional output quality assessment
- **Self-Improver**: Pattern learning and performance optimization

## Quick Start

### Prerequisites
- Python 3.11+
- PostgreSQL 16+ with pgvector extension
- Redis 7+
- Docker (optional)

### Installation

```bash
# Clone the repository
git clone https://github.com/arena-ai/platform.git
cd arena-ai-platform

# Install dependencies
pip install -e .

# Set environment variables
export OPENAI_API_KEY="your-api-key"
export DATABASE_URL="postgresql://localhost:5432/arena"
export REDIS_URL="redis://localhost:6379"

# Initialize database
psql -d arena -f database/migrations/001_initial_schema.sql

# Run the application
uvicorn api.main:app --reload
```

### Frontend (local dev)

```bash
cd frontend
npm install
npm run dev
```

This starts the Vite dev server on `http://localhost:5173` and proxies `/api`
requests to the backend at `http://localhost:8000` (see `vite.config.js`).
Register an account at `/register`, then sign in — every resource (agents,
sessions, tasks, plans, memory, knowledge, patterns, tools, evaluation,
feedback, audit log, API keys) is manageable from the UI.

### Using Docker Compose

```bash
# Set environment variables
export OPENAI_API_KEY="your-api-key"

# Start all services
docker-compose -f infrastructure/docker/docker-compose.yml up -d

# View logs
docker-compose -f infrastructure/docker/docker-compose.yml logs -f
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Frontend (React)                        │
└─────────────────────────────────────────────────────────────────┘
                                  │
┌─────────────────────────────────────────────────────────────────┐
│                      REST API (FastAPI)                         │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐  │
│  │  Auth   │ │ Agents  │ │  Tasks  │ │ Memory  │ │Knowledge│  │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘  │
└─────────────────────────────────────────────────────────────────┘
                                  │
┌─────────────────────────────────────────────────────────────────┐
│                        Core Services                             │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐            │
│  │   AI Runtime │ │  Planner     │ │   Reasoner   │            │
│  └──────────────┘ └──────────────┘ └──────────────┘            │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐            │
│  │    Agent     │ │    Task      │ │    Tool      │            │
│  │   Manager    │ │   Executor   │ │   Registry   │            │
│  └──────────────┘ └──────────────┘ └──────────────┘            │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐            │
│  │   Memory     │ │  Knowledge   │ │   Context   │            │
│  │   Manager    │ │    Base      │ │   Manager   │            │
│  └──────────────┘ └──────────────┘ └──────────────┘            │
└─────────────────────────────────────────────────────────────────┘
                                  │
┌─────────────────────────────────────────────────────────────────┐
│                      Data Layer                                  │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐                   │
│  │ PostgreSQL │ │   Redis    │ │  Vector DB │                   │
│  │ (primary)  │ │  (cache)   │ │(embeddings)│                   │
│  └────────────┘ └────────────┘ └────────────┘                   │
└─────────────────────────────────────────────────────────────────┘
```

## API Documentation

Once the server is running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Development

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=core --cov-report=html
```

### Project Structure

```
arena-ai-platform/
├── core/                    # Core AI components
│   ├── ai_runtime/         # AI inference engine
│   ├── planning_engine/     # Task planning
│   ├── reasoning_engine/    # Reasoning
│   ├── task_manager/        # Task execution
│   ├── agent_manager/       # Agent orchestration
│   ├── tool_manager/        # Tool registry
│   ├── memory_manager/      # Memory systems
│   ├── knowledge_base/      # Knowledge management
│   ├── context_manager/     # Context handling
│   ├── multi_agent/         # Multi-agent coordination
│   ├── self_evaluation/     # Quality assessment
│   └── self_improvement/    # Learning
├── database/               # Database layer
│   └── migrations/          # SQL migrations
├── api/                    # FastAPI application
│   └── routes/             # API endpoints
├── frontend/               # React frontend
├── infrastructure/         # Docker, K8s, CI/CD
└── tests/                  # Test suite
```

### Adapter Training (Fine-Tuning with LoRA / QLoRA)

This platform includes a complete adapter fine-tuning pipeline. It does **not** train large language models from scratch (which requires thousands of GPUs, petabytes of data, and millions of dollars). Instead, it trains lightweight adapters (LoRA/QLoRA) on top of frozen pre-trained models — exactly how production AI customization works.

```bash
# Quick adapter training on gpt2
bash core/training/scripts/run_finetune.sh \
    --model gpt2 --data data/sample_train.jsonl --output ./adapters

# Load and use the adapter
python3 -c "
from core.training.adapters import AdapterManager
manager = AdapterManager('gpt2')
model = manager.load_adapter('./adapters/my-adapter')
"
```

See `docs/TRAINING.md` for the full adapter training guide, memory estimates, evaluation metrics, and production deployment instructions.

## License

MIT License - see LICENSE file for details.
