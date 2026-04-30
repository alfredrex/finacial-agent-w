"""Agent 通信层"""
from src.communication.models import AgentMessage, MessageType, AgentInfo
from src.communication.message_bus import message_bus, MessageBus
from src.communication.blackboard import blackboard, Blackboard
from src.communication.agent_registry import agent_registry, AgentRegistry

__all__ = [
    'AgentMessage', 'MessageType', 'AgentInfo',
    'MessageBus', 'message_bus',
    'Blackboard', 'blackboard',
    'AgentRegistry', 'agent_registry',
]
