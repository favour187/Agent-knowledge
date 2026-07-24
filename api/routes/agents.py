"""
Agents Routes

Agent creation, management, and messaging — backed by the real `agents`
table (database/models.py: Agent) via SQLAlchemy.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth_utils import get_current_user_optional
from api.state import app_state
from core.ai_runtime.engine import Message as AIMessage, MessageRole
from database.db import get_db
from database.models import Agent, User

logger = structlog.get_logger(__name__)

router = APIRouter()


class AgentConfig(BaseModel):
    """Agent configuration."""
    name: str = Field(..., min_length=1, max_length=255)
    description: str = ""
    system_prompt: str = ""
    model: str = "gpt-4-turbo-preview"
    temperature: float = Field(default=0.7, ge=0, le=2)
    max_tokens: int = Field(default=4096, ge=1)


class AgentCreate(AgentConfig):
    """Agent creation request."""
    pass


class AgentResponse(BaseModel):
    """Agent response."""
    id: str
    name: str
    description: str
    model: str
    status: str
    created_at: str

    model_config = {"from_attributes": True}


class AgentMessage(BaseModel):
    """Message to agent."""
    content: str


class AgentMessageResponse(BaseModel):
    """Agent message response."""
    content: str
    agent_id: str
    session_id: str


def _to_response(agent: Agent) -> AgentResponse:
    return AgentResponse(
        id=agent.id,
        name=agent.name,
        description=agent.description,
        model=agent.model,
        status=agent.status,
        created_at=agent.created_at.isoformat(),
    )


async def _get_agent_or_404(agent_id: str, db: AsyncSession) -> Agent:
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return agent


@router.get("", response_model=list[AgentResponse])
async def list_agents(db: AsyncSession = Depends(get_db)) -> list[AgentResponse]:
    """List all agents."""
    result = await db.execute(select(Agent).order_by(Agent.created_at.desc()))
    return [_to_response(a) for a in result.scalars().all()]


@router.post("", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(
    config: AgentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
) -> AgentResponse:
    """Create a new agent. Attributed to the current user if authenticated."""
    agent = Agent(
        user_id=current_user.id if current_user else None,
        name=config.name,
        description=config.description,
        system_prompt=config.system_prompt,
        model=config.model,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        status="idle",
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    return _to_response(agent)


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(agent_id: str, db: AsyncSession = Depends(get_db)) -> AgentResponse:
    """Get agent by ID."""
    agent = await _get_agent_or_404(agent_id, db)
    return _to_response(agent)


@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(agent_id: str, config: AgentConfig, db: AsyncSession = Depends(get_db)) -> AgentResponse:
    """Update an agent."""
    agent = await _get_agent_or_404(agent_id, db)
    agent.name = config.name
    agent.description = config.description
    agent.system_prompt = config.system_prompt
    agent.model = config.model
    agent.temperature = config.temperature
    agent.max_tokens = config.max_tokens
    await db.commit()
    await db.refresh(agent)
    return _to_response(agent)


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(agent_id: str, db: AsyncSession = Depends(get_db)) -> None:
    """Delete an agent."""
    agent = await _get_agent_or_404(agent_id, db)
    await db.delete(agent)
    await db.commit()


@router.post("/{agent_id}/start")
async def start_agent(agent_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    """Start an agent."""
    agent = await _get_agent_or_404(agent_id, db)
    agent.status = "running"
    await db.commit()
    return {"status": "started", "agent_id": agent_id}


@router.post("/{agent_id}/stop")
async def stop_agent(agent_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    """Stop an agent."""
    agent = await _get_agent_or_404(agent_id, db)
    agent.status = "idle"
    await db.commit()
    return {"status": "stopped", "agent_id": agent_id}


@router.post("/{agent_id}/message", response_model=AgentMessageResponse)
async def send_message(agent_id: str, message: AgentMessage, db: AsyncSession = Depends(get_db)) -> AgentMessageResponse:
    """Send a message to an agent and get a real model response.

    Persists a session + user/assistant message row, and calls through to
    the shared `AIRuntime` (app_state.ai_runtime) using the agent's
    configured model/system_prompt/temperature/max_tokens — a real
    inference call, not an echo placeholder. Falls back to a clear,
    non-crashing explanatory message if no provider is configured
    (OPENAI_API_KEY / ANTHROPIC_API_KEY) or the call fails.
    """
    agent = await _get_agent_or_404(agent_id, db)

    from database.models import ChatMessage, ChatSession

    session = ChatSession(agent_id=agent_id, title=None, context={})
    db.add(session)
    await db.flush()

    db.add(ChatMessage(session_id=session.id, role="user", content=message.content))

    ai_runtime = app_state.ai_runtime
    if ai_runtime is None or not ai_runtime.providers:
        reply = (
            "No AI provider is configured on the server (set OPENAI_API_KEY "
            "and/or ANTHROPIC_API_KEY) — this is a fallback message, not a "
            "real model response."
        )
    else:
        messages: list[AIMessage] = []
        if agent.system_prompt:
            messages.append(AIMessage(role=MessageRole.SYSTEM, content=agent.system_prompt))
        messages.append(AIMessage(role=MessageRole.USER, content=message.content))

        config = replace(
            ai_runtime.get_model_config(agent.model),
            temperature=agent.temperature,
            max_tokens=agent.max_tokens,
        )

        try:
            response = await ai_runtime.complete(messages=messages, model=agent.model, config=config)
            reply = response.content
        except Exception as exc:  # noqa: BLE001 - deliberately broad: report the failure, don't crash the request
            logger.error("agent_message_completion_failed", agent_id=agent_id, error=str(exc))
            reply = f"AI completion failed: {exc}"

    db.add(ChatMessage(session_id=session.id, role="assistant", content=reply))
    await db.commit()

    return AgentMessageResponse(content=reply, agent_id=agent_id, session_id=session.id)
