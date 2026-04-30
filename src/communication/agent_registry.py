"""
Agent 注册表 (AgentRegistry)
能力注册与查询、心跳检测、状态管理
"""
from typing import Dict, List, Optional
from datetime import datetime

from src.communication.models import AgentInfo


class AgentRegistry:
    """Agent 注册表"""

    def __init__(self):
        self._agents: Dict[str, AgentInfo] = {}

    def register(self, name: str, description: str,
                 capabilities: List[str]) -> AgentInfo:
        """注册 Agent"""
        info = AgentInfo(
            name=name,
            description=description,
            capabilities=capabilities,
        )
        self._agents[name] = info
        return info

    def unregister(self, name: str):
        """注销 Agent"""
        self._agents.pop(name, None)

    def discover(self, capability: str) -> List[AgentInfo]:
        """按能力查找 Agent"""
        return [
            info for info in self._agents.values()
            if capability in info.capabilities
        ]

    def get(self, name: str) -> Optional[AgentInfo]:
        return self._agents.get(name)

    def get_all(self) -> List[AgentInfo]:
        return list(self._agents.values())

    def set_status(self, name: str, status: str):
        """更新 Agent 状态"""
        info = self._agents.get(name)
        if info:
            info.status = status

    def heartbeat(self, name: str):
        """心跳更新"""
        info = self._agents.get(name)
        if info:
            info.last_heartbeat = datetime.now()

    def get_idle_agents(self) -> List[AgentInfo]:
        """获取空闲 Agent"""
        return [a for a in self._agents.values() if a.status == "idle"]

    @property
    def count(self) -> int:
        return len(self._agents)


# 全局实例
agent_registry = AgentRegistry()
