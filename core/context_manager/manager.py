"""
Context Manager

Manages conversation context and session state.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

import structlog

from core.ai_runtime.engine import Message as AIMessage, MessageRole

logger = structlog.get_logger(__name__)


class ContextWindow(str, Enum):
    """Context window sizes."""
    TINY = "tiny"       # 2-4 messages
    SMALL = "small"    # 8-10 messages
    MEDIUM = "medium"  # 16-20 messages
    LARGE = "large"    # 32-40 messages
    FULL = "full"      # All messages

    @property
    def max_messages(self) -> int:
        """Get max messages for this window size."""
        sizes = {
            ContextWindow.TINY: 4,
            ContextWindow.SMALL: 10,
            ContextWindow.MEDIUM: 20,
            ContextWindow.LARGE: 40,
            ContextWindow.FULL: -1,  # No limit
        }
        return sizes[self]


@dataclass
class SessionContext:
    """
    A session context for a conversation.

    Attributes:
        id: Session ID
        agent_id: Agent ID
        user_id: User ID
        created_at: Session creation time
        messages: Conversation messages
        metadata: Session metadata
        window: Context window size
        system_prompt: System prompt
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: Optional[str] = None
    user_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    messages: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    window: ContextWindow = ContextWindow.MEDIUM
    system_prompt: str = ""
    token_budget: int = 100000  # Max tokens in context

    def add_message(
        self,
        role: MessageRole,
        content: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """Add a message to the session."""
        self.messages.append({
            "role": role.value,
            "content": content,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": metadata or {},
        })
        self.updated_at = datetime.utcnow()

    def get_recent_messages(self, count: int = -1) -> list[dict[str, Any]]:
        """Get recent messages, or all if count is -1."""
        if count < 0:
            return self.messages.copy()
        return self.messages[-count:]

    def get_messages_for_context(self) -> list[AIMessage]:
        """Get messages formatted for AI context."""
        result = []

        # Add system prompt
        if self.system_prompt:
            result.append(AIMessage(
                role=MessageRole.SYSTEM,
                content=self.system_prompt,
            ))

        # Add messages within window
        max_msgs = self.window.max_messages
        if max_msgs > 0:
            window_messages = self.messages[-max_msgs:]
        else:
            window_messages = self.messages

        for msg in window_messages:
            result.append(AIMessage(
                role=MessageRole(msg["role"]),
                content=msg["content"],
            ))

        return result

    def clear_messages(self) -> None:
        """Clear all messages."""
        self.messages.clear()
        self.updated_at = datetime.utcnow()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "user_id": self.user_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "message_count": len(self.messages),
            "metadata": self.metadata,
            "window": self.window.value,
        }


class ContextManager:
    """
    Manages conversation contexts across multiple sessions.

    Features:
    - Session creation and retrieval
    - Context window management
    - Token budgeting
    - Key information extraction
    - Context compression
    """

    def __init__(
        self,
        default_window: ContextWindow = ContextWindow.MEDIUM,
        max_token_budget: int = 100000,
    ):
        self.default_window = default_window
        self.max_token_budget = max_token_budget

        self._sessions: dict[str, SessionContext] = {}
        self._user_sessions: dict[str, list[str]] = {}  # user_id -> session_ids
        self._agent_sessions: dict[str, list[str]] = {}  # agent_id -> session_ids

        # Key information storage
        self._key_info: dict[str, list[dict[str, Any]]] = {}  # session_id -> key facts

        logger.info(
            "context_manager_initialized",
            default_window=default_window.value,
            max_tokens=max_token_budget,
        )

    def create_session(
        self,
        agent_id: Optional[str] = None,
        user_id: Optional[str] = None,
        system_prompt: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> SessionContext:
        """
        Create a new session context.

        Args:
            agent_id: Agent ID
            user_id: User ID
            system_prompt: System prompt
            metadata: Session metadata

        Returns:
            Created SessionContext
        """
        session = SessionContext(
            agent_id=agent_id,
            user_id=user_id,
            system_prompt=system_prompt,
            metadata=metadata or {},
            window=self.default_window,
        )

        self._sessions[session.id] = session

        if user_id:
            if user_id not in self._user_sessions:
                self._user_sessions[user_id] = []
            self._user_sessions[user_id].append(session.id)

        if agent_id:
            if agent_id not in self._agent_sessions:
                self._agent_sessions[agent_id] = []
            self._agent_sessions[agent_id].append(session.id)

        logger.debug(
            "session_created",
            session_id=session.id,
            agent_id=agent_id,
            user_id=user_id,
        )

        return session

    def get_session(self, session_id: str) -> Optional[SessionContext]:
        """Get a session by ID."""
        return self._sessions.get(session_id)

    def get_user_sessions(self, user_id: str) -> list[SessionContext]:
        """Get all sessions for a user."""
        session_ids = self._user_sessions.get(user_id, [])
        return [
            self._sessions[sid]
            for sid in session_ids
            if sid in self._sessions
        ]

    def get_agent_sessions(self, agent_id: str) -> list[SessionContext]:
        """Get all sessions for an agent."""
        session_ids = self._agent_sessions.get(agent_id, [])
        return [
            self._sessions[sid]
            for sid in session_ids
            if sid in self._sessions
        ]

    def add_message(
        self,
        session_id: str,
        role: MessageRole,
        content: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> bool:
        """Add a message to a session."""
        session = self._sessions.get(session_id)
        if not session:
            return False

        session.add_message(role, content, metadata)

        # Extract key information
        self._extract_key_info(session_id, role, content)

        return True

    def _extract_key_info(
        self,
        session_id: str,
        role: MessageRole,
        content: str,
    ) -> None:
        """Extract and store key information from messages."""
        # Simple extraction - in production, use NLP
        if session_id not in self._key_info:
            self._key_info[session_id] = []

        # Store recent key info
        if role == MessageRole.USER:
            self._key_info[session_id].append({
                "type": "user_request",
                "content": content[:200],  # First 200 chars
                "timestamp": datetime.utcnow().isoformat(),
            })

        # Keep only recent key info
        if len(self._key_info[session_id]) > 20:
            self._key_info[session_id] = self._key_info[session_id][-20:]

    def get_key_info(self, session_id: str) -> list[dict[str, Any]]:
        """Get key information for a session."""
        return self._key_info.get(session_id, [])

    def set_window(self, session_id: str, window: ContextWindow) -> bool:
        """Set context window size for a session."""
        session = self._sessions.get(session_id)
        if not session:
            return False

        session.window = window
        return True

    def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        session = self._sessions.get(session_id)
        if not session:
            return False

        # Remove from indexes
        if session.user_id and session_id in self._user_sessions.get(session.user_id, []):
            self._user_sessions[session.user_id].remove(session_id)

        if session.agent_id and session_id in self._agent_sessions.get(session.agent_id, []):
            self._agent_sessions[session.agent_id].remove(session_id)

        # Remove key info
        if session_id in self._key_info:
            del self._key_info[session_id]

        # Remove session
        del self._sessions[session_id]

        logger.debug("session_deleted", session_id=session_id)
        return True

    def get_stats(self) -> dict[str, Any]:
        """Get context manager statistics."""
        total_messages = sum(len(s.messages) for s in self._sessions.values())

        return {
            "total_sessions": len(self._sessions),
            "total_messages": total_messages,
            "sessions_by_user": len(self._user_sessions),
            "sessions_by_agent": len(self._agent_sessions),
            "default_window": self.default_window.value,
        }
