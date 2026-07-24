"""
Agent Communication

Inter-agent messaging and message bus for multi-agent communication.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional

import structlog

from core.agent_manager.agent import Message, MessageRole

logger = structlog.get_logger(__name__)


class ChannelType(str, Enum):
    """Message channel types."""
    DIRECT = "direct"           # One-to-one
    BROADCAST = "broadcast"     # One-to-all
    TOPIC = "topic"             # Pub/sub
    GROUP = "group"             # One-to-group


@dataclass
class MessageEnvelope:
    """A message with routing information."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    channel: str = ""
    channel_type: ChannelType = ChannelType.DIRECT
    sender_id: Optional[str] = None
    recipient_id: Optional[str] = None
    topic: Optional[str] = None
    message: Message = field(default_factory=Message)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    ttl: Optional[float] = None  # Time to live in seconds
    correlation_id: Optional[str] = None  # For request/response
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_expired(self) -> bool:
        """Check if message has expired."""
        if self.ttl is None:
            return False
        return (datetime.utcnow() - self.timestamp).total_seconds() > self.ttl


class MessageBus:
    """
    Message bus for inter-agent communication.

    Features:
    - Direct messaging
    - Broadcast messaging
    - Topic-based pub/sub
    - Group messaging
    - Message filtering
    - Delivery confirmation
    """

    def __init__(self, max_queue_size: int = 1000):
        self.max_queue_size = max_queue_size
        self.queues: dict[str, asyncio.Queue] = {}
        self.subscriptions: dict[str, set[str]] = {}  # topic -> agent_ids
        self.groups: dict[str, set[str]] = {}  # group_name -> agent_ids
        self._lock = asyncio.Lock()
        self._handlers: dict[str, list[Callable]] = {}
        self._running = False

        logger.info("message_bus_initialized")

    async def send_direct(
        self,
        sender_id: str,
        recipient_id: str,
        message: Message,
        ttl: Optional[float] = None,
    ) -> str:
        """
        Send a direct message to an agent.

        Args:
            sender_id: Sender's ID
            recipient_id: Recipient's ID
            message: Message to send
            ttl: Optional time to live

        Returns:
            Message envelope ID
        """
        envelope = MessageEnvelope(
            channel=recipient_id,
            channel_type=ChannelType.DIRECT,
            sender_id=sender_id,
            recipient_id=recipient_id,
            message=message,
            ttl=ttl,
        )

        await self._deliver(envelope)
        return envelope.id

    async def broadcast(
        self,
        sender_id: str,
        message: Message,
        ttl: Optional[float] = None,
    ) -> list[str]:
        """
        Broadcast a message to all agents.

        Args:
            sender_id: Sender's ID
            message: Message to broadcast
            ttl: Optional time to live

        Returns:
            List of message envelope IDs
        """
        envelope = MessageEnvelope(
            channel="__broadcast__",
            channel_type=ChannelType.BROADCAST,
            sender_id=sender_id,
            message=message,
            ttl=ttl,
        )

        # Deliver to all registered queues
        envelope_ids = []
        for channel_id in self.queues:
            if channel_id != sender_id:  # Don't send to self
                msg_copy = MessageEnvelope(
                    channel=channel_id,
                    channel_type=ChannelType.BROADCAST,
                    sender_id=sender_id,
                    recipient_id=channel_id,
                    message=message,
                    ttl=ttl,
                    correlation_id=envelope.id,
                )
                await self._deliver(msg_copy)
                envelope_ids.append(msg_copy.id)

        return envelope_ids

    async def publish(
        self,
        sender_id: str,
        topic: str,
        message: Message,
        ttl: Optional[float] = None,
    ) -> list[str]:
        """
        Publish a message to a topic.

        Args:
            sender_id: Sender's ID
            topic: Topic name
            message: Message to publish
            ttl: Optional time to live

        Returns:
            List of message envelope IDs
        """
        envelope = MessageEnvelope(
            channel=topic,
            channel_type=ChannelType.TOPIC,
            sender_id=sender_id,
            topic=topic,
            message=message,
            ttl=ttl,
        )

        # Deliver to all subscribers
        envelope_ids = []
        subscribers = self.subscriptions.get(topic, set())

        for agent_id in subscribers:
            if agent_id != sender_id:
                msg_copy = MessageEnvelope(
                    channel=agent_id,
                    channel_type=ChannelType.TOPIC,
                    sender_id=sender_id,
                    recipient_id=agent_id,
                    topic=topic,
                    message=message,
                    ttl=ttl,
                    correlation_id=envelope.id,
                )
                await self._deliver(msg_copy)
                envelope_ids.append(msg_copy.id)

        return envelope_ids

    async def send_to_group(
        self,
        sender_id: str,
        group_name: str,
        message: Message,
        ttl: Optional[float] = None,
    ) -> list[str]:
        """
        Send a message to all members of a group.

        Args:
            sender_id: Sender's ID
            group_name: Group name
            message: Message to send
            ttl: Optional time to live

        Returns:
            List of message envelope IDs
        """
        envelope = MessageEnvelope(
            channel=group_name,
            channel_type=ChannelType.GROUP,
            sender_id=sender_id,
            message=message,
            ttl=ttl,
        )

        envelope_ids = []
        members = self.groups.get(group_name, set())

        for agent_id in members:
            if agent_id != sender_id:
                msg_copy = MessageEnvelope(
                    channel=agent_id,
                    channel_type=ChannelType.GROUP,
                    sender_id=sender_id,
                    recipient_id=agent_id,
                    message=message,
                    ttl=ttl,
                    correlation_id=envelope.id,
                )
                await self._deliver(msg_copy)
                envelope_ids.append(msg_copy.id)

        return envelope_ids

    async def subscribe(self, agent_id: str, topic: str) -> None:
        """Subscribe an agent to a topic."""
        async with self._lock:
            if topic not in self.subscriptions:
                self.subscriptions[topic] = set()
            self.subscriptions[topic].add(agent_id)
        logger.debug("agent_subscribed", agent_id=agent_id, topic=topic)

    async def unsubscribe(self, agent_id: str, topic: str) -> None:
        """Unsubscribe an agent from a topic."""
        async with self._lock:
            if topic in self.subscriptions:
                self.subscriptions[topic].discard(agent_id)
        logger.debug("agent_unsubscribed", agent_id=agent_id, topic=topic)

    async def create_group(self, group_name: str) -> None:
        """Create a message group."""
        async with self._lock:
            if group_name not in self.groups:
                self.groups[group_name] = set()
        logger.debug("group_created", group_name=group_name)

    async def add_to_group(self, group_name: str, agent_id: str) -> None:
        """Add an agent to a group."""
        async with self._lock:
            if group_name not in self.groups:
                self.groups[group_name] = set()
            self.groups[group_name].add(agent_id)
        logger.debug("agent_added_to_group", agent_id=agent_id, group_name=group_name)

    async def remove_from_group(self, group_name: str, agent_id: str) -> None:
        """Remove an agent from a group."""
        async with self._lock:
            if group_name in self.groups:
                self.groups[group_name].discard(agent_id)
        logger.debug("agent_removed_from_group", agent_id=agent_id, group_name=group_name)

    def register_queue(self, agent_id: str) -> asyncio.Queue:
        """Register a message queue for an agent."""
        if agent_id not in self.queues:
            self.queues[agent_id] = asyncio.Queue(maxsize=self.max_queue_size)
        return self.queues[agent_id]

    def unregister_queue(self, agent_id: str) -> None:
        """Unregister an agent's message queue."""
        if agent_id in self.queues:
            del self.queues[agent_id]

    async def _deliver(self, envelope: MessageEnvelope) -> None:
        """Deliver a message to its destination."""
        if envelope.recipient_id and envelope.recipient_id in self.queues:
            try:
                self.queues[envelope.recipient_id].put_nowait(envelope)
            except asyncio.QueueFull:
                logger.warning(
                    "message_queue_full",
                    recipient=envelope.recipient_id,
                )

        # Notify handlers
        for handler in self._handlers.get(envelope.channel, []):
            try:
                handler(envelope)
            except Exception as e:
                logger.error("message_handler_failed", error=str(e))

    async def receive(self, agent_id: str, timeout: Optional[float] = None) -> Optional[MessageEnvelope]:
        """
        Receive a message for an agent.

        Args:
            agent_id: Agent's ID
            timeout: Optional timeout in seconds

        Returns:
            MessageEnvelope or None
        """
        if agent_id not in self.queues:
            self.register_queue(agent_id)

        try:
            if timeout:
                return await asyncio.wait_for(
                    self.queues[agent_id].get(),
                    timeout=timeout,
                )
            else:
                return await self.queues[agent_id].get()
        except asyncio.TimeoutError:
            return None

    def on_message(self, channel: str, handler: Callable[[MessageEnvelope], None]) -> None:
        """Register a message handler for a channel."""
        if channel not in self._handlers:
            self._handlers[channel] = []
        self._handlers[channel].append(handler)

    def get_stats(self) -> dict[str, Any]:
        """Get message bus statistics."""
        return {
            "queues": len(self.queues),
            "topics": len(self.subscriptions),
            "groups": len(self.groups),
            "subscriptions": sum(len(s) for s in self.subscriptions.values()),
            "group_members": sum(len(g) for g in self.groups.values()),
        }


class AgentCommunicator:
    """
    Helper class for agent communication.

    Provides a clean interface for agents to communicate
    through the message bus.
    """

    def __init__(self, agent_id: str, message_bus: MessageBus):
        self.agent_id = agent_id
        self.message_bus = message_bus
        self._receive_task: Optional[asyncio.Task] = None
        self._running = False
        self._message_handlers: list[Callable[[Message], None]] = []

    async def start(self) -> None:
        """Start receiving messages."""
        self._running = True
        self._receive_task = asyncio.create_task(self._receive_loop())
        await self.message_bus.subscribe(self.agent_id, f"agent:{self.agent_id}")

    async def stop(self) -> None:
        """Stop receiving messages."""
        self._running = False
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass

    async def send_to(
        self,
        recipient_id: str,
        content: str,
        role: MessageRole = MessageRole.AGENT,
    ) -> str:
        """Send a direct message to another agent."""
        message = Message(role=role, content=content)
        return await self.message_bus.send_direct(
            sender_id=self.agent_id,
            recipient_id=recipient_id,
            message=message,
        )

    async def broadcast(
        self,
        content: str,
        role: MessageRole = MessageRole.AGENT,
    ) -> list[str]:
        """Broadcast a message to all agents."""
        message = Message(role=role, content=content)
        return await self.message_bus.broadcast(
            sender_id=self.agent_id,
            message=message,
        )

    async def publish_to(
        self,
        topic: str,
        content: str,
        role: MessageRole = MessageRole.AGENT,
    ) -> list[str]:
        """Publish a message to a topic."""
        message = Message(role=role, content=content)
        return await self.message_bus.publish(
            sender_id=self.agent_id,
            topic=topic,
            message=message,
        )

    def on_message(self, handler: Callable[[Message], None]) -> None:
        """Register a message handler."""
        self._message_handlers.append(handler)

    async def _receive_loop(self) -> None:
        """Receive messages continuously."""
        while self._running:
            envelope = await self.message_bus.receive(self.agent_id, timeout=1.0)
            if envelope and not envelope.is_expired():
                for handler in self._message_handlers:
                    try:
                        handler(envelope.message)
                    except Exception as e:
                        logger.error("message_handler_failed", error=str(e))
