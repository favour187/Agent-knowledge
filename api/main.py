"""
Arena AI Platform API

FastAPI application for the Arena AI Platform.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core import (
    AIRuntime,
    AgentManager,
    KnowledgeBase,
    MemoryManager,
    MultiAgentOrchestrator,
    PlanningEngine,
    ReasoningEngine,
    SelfEvaluator,
    SelfImprover,
    TaskExecutor,
    ToolRegistry,
)
from core.ai_runtime.engine import ModelProvider
from core.ai_runtime.providers.openai import OpenAIProvider
from core.ai_runtime.providers.anthropic import AnthropicProvider
from core.agent_manager import Agent, AgentConfig
from core.tool_manager import ToolRegistry

from api.state import app_state, get_state
from database.db import init_db

# Import routes
from api.routes import (
    agents,
    agent_chat,
    api_keys,
    audit,
    auth,
    evaluation,
    feedback,
    knowledge,
    memory,
    patterns,
    plans,
    sessions,
    tasks,
    tools,
    training,
    workspace,
)


# Configuration
class Settings:
    """Application settings."""
    app_name: str = "Arena AI Platform"
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"
    api_version: str = "v1"
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    database_url: str = os.getenv("DATABASE_URL", "postgresql://localhost/arena")
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379")


settings = Settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager."""
    # Startup
    await startup()
    yield
    # Shutdown
    await shutdown()


async def startup() -> None:
    """Initialize application on startup."""
    # Create DB tables if they don't exist yet (dev/test convenience; see
    # database/db.py docstring re: real Postgres deployments)
    await init_db()

    # Initialize AI runtime
    ai_runtime = AIRuntime(
        default_provider=ModelProvider.OPENAI,
        default_model="gpt-4-turbo-preview",
    )

    # Register providers
    if settings.openai_api_key:
        ai_runtime.register_provider(
            ModelProvider.OPENAI, OpenAIProvider(api_key=settings.openai_api_key)
        )

    if settings.anthropic_api_key:
        ai_runtime.register_provider(
            ModelProvider.ANTHROPIC, AnthropicProvider(api_key=settings.anthropic_api_key)
        )

    app_state.ai_runtime = ai_runtime

    # Initialize managers
    app_state.tool_registry = ToolRegistry()
    app_state.memory_manager = MemoryManager()
    app_state.knowledge_base = KnowledgeBase()
    app_state.planning_engine = PlanningEngine(ai_runtime)
    app_state.reasoning_engine = ReasoningEngine(ai_runtime)
    app_state.task_executor = TaskExecutor(max_workers=10)
    app_state.multi_agent = MultiAgentOrchestrator()
    app_state.self_evaluator = SelfEvaluator(ai_runtime)
    from core.self_evaluation.evaluator import Rubric as _Rubric
    app_state.self_evaluator.register_rubric(_Rubric.coding())
    app_state.self_improver = SelfImprover(ai_runtime)

    # Initialize agent manager
    app_state.agent_manager = AgentManager(
        ai_runtime=ai_runtime,
        tool_registry=app_state.tool_registry,
        memory_manager=app_state.memory_manager,
    )

    # Start background tasks
    await app_state.memory_manager.start()
    await app_state.agent_manager.start()

    print(f"✅ {settings.app_name} started successfully")


async def shutdown() -> None:
    """Cleanup on shutdown."""
    if app_state.agent_manager:
        await app_state.agent_manager.stop()

    if app_state.memory_manager:
        await app_state.memory_manager.stop()

    print("👋 Arena AI Platform shutdown complete")


# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    description="Comprehensive autonomous AI agent platform",
    version=settings.api_version,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Global exception handler."""
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal server error",
            "detail": str(exc) if settings.debug else None,
        },
    )


# Health check
@app.get("/health")
async def health_check() -> dict[str, Any]:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "app": settings.app_name,
        "version": settings.api_version,
    }


@app.get("/api")
async def root() -> dict[str, str]:
    """API root endpoint."""
    return {
        "name": settings.app_name,
        "version": settings.api_version,
        "docs": "/docs",
    }


# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(agent_chat.router, prefix="/api/agent", tags=["Agent"])
app.include_router(agents.router, prefix="/api/agents", tags=["Agents"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["Tasks"])
app.include_router(memory.router, prefix="/api/memory", tags=["Memory"])
app.include_router(knowledge.router, prefix="/api/knowledge", tags=["Knowledge"])
app.include_router(tools.router, prefix="/api/tools", tags=["Tools"])
app.include_router(sessions.router, prefix="/api/sessions", tags=["Sessions"])
app.include_router(plans.router, prefix="/api/plans", tags=["Plans"])
app.include_router(evaluation.router, prefix="/api/evaluation", tags=["Evaluation"])
app.include_router(feedback.router, prefix="/api/feedback", tags=["Feedback"])
app.include_router(patterns.router, prefix="/api/patterns", tags=["Patterns"])
app.include_router(audit.router, prefix="/api/audit", tags=["Audit"])
app.include_router(api_keys.router, prefix="/api/api-keys", tags=["API Keys"])
app.include_router(training.router, prefix="/api/training", tags=["Training"])
app.include_router(workspace.router, prefix="/api/workspace", tags=["Workspace"])


# ─── Serve frontend static files ─────────────────────────────────────
FRONTEND_DIST = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "dist"
)

if os.path.isdir(FRONTEND_DIST):
    app.mount(
        "/assets",
        StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")),
        name="static-assets",
    )

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        """Serve the React SPA — all non-API routes return index.html."""
        file_path = os.path.join(FRONTEND_DIST, full_path)
        if full_path and os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(FRONTEND_DIST, "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
    )
