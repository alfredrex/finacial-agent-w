"""
消息总线 (MessageBus)
Agent间异步消息传递：发送、广播、订阅、消息队列
"""
import uuid
from typing import Dict, List, Optional, Callable, Any
from collections import defaultdict
from datetime import datetime

from src.communication.models import AgentMessage, MessageType


class MessageBus:
    """内存消息总线"""

    def __init__(self):
        self._queues: Dict[str, List[AgentMessage]] = defaultdict(list)  # agent → messages
        self._subscriptions: Dict[str, List[Callable]] = defaultdict(list)  # msg_type → callbacks
        self._all_messages: List[AgentMessage] = []
        self._threads: Dict[str, List[AgentMessage]] = defaultdict(list)

    def send(self, from_agent: str, to_agent: str, type: MessageType,
             content: Any, thread_id: Optional[str] = None,
             metadata: dict = None) -> str:
        """发送消息到指定 Agent"""
        msg_id = f"msg_{uuid.uuid4().hex[:12]}"
        msg = AgentMessage(
            id=msg_id,
            from_agent=from_agent,
            to_agent=to_agent,
            type=type,
            content=content,
            thread_id=thread_id or msg_id,
            metadata=metadata or {},
        )
        self._queues[to_agent].append(msg)
        self._all_messages.append(msg)
        if msg.thread_id:
            self._threads[msg.thread_id].append(msg)
        # 触发回调
        for callback in self._subscriptions.get(type.value, []):
            try:
                callback(msg)
            except Exception:
                pass
        return msg_id

    def broadcast(self, from_agent: str, type: MessageType,
                  content: Any, metadata: dict = None) -> List[str]:
        """广播消息给所有 Agent"""
        ids = []
        for agent_name in list(self._queues.keys()):
            msg_id = self.send(from_agent, agent_name, type, content,
                               metadata=metadata)
            ids.append(msg_id)
        return ids

    def get_messages(self, agent_name: str, mark_read: bool = True) -> List[AgentMessage]:
        """拉取 Agent 的未读消息"""
        msgs = list(self._queues.get(agent_name, []))
        if mark_read:
            self._queues[agent_name] = []
        return msgs

    def get_thread(self, thread_id: str) -> List[AgentMessage]:
        """获取完整消息线程"""
        return self._threads.get(thread_id, [])

    def subscribe(self, message_type: str, callback: Callable):
        """订阅特定类型的消息"""
        self._subscriptions[message_type].append(callback)

    def get_all_messages(self, limit: int = 100) -> List[AgentMessage]:
        return self._all_messages[-limit:]

    def register_agent(self, agent_name: str):
        """注册 Agent 的消息队列"""
        if agent_name not in self._queues:
            self._queues[agent_name] = []

    def get_queue_sizes(self) -> Dict[str, int]:
        return {name: len(msgs) for name, msgs in self._queues.items()}


# 全局实例
message_bus = MessageBus()
