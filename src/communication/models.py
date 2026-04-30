"""Agent 通信数据模型"""
from dataclasses import dataclass, field
from typing import Any, Optional, List
from datetime import datetime
from enum import Enum


class MessageType(str, Enum):
    QUERY = "query"              # Agent A → Agent B: 请求信息
    RESPONSE = "response"        # Agent B → Agent A: 回复 QUERY
    DELEGATE = "delegate"        # Coordinator → Worker: 分配子任务
    REPORT = "report"            # Worker → Coordinator: 报告完成
    BROADCAST = "broadcast"      # 发布信息给所有订阅者
    COORDINATE = "coordinate"    # Agent间协商/共识
    STATUS = "status"            # 心跳/状态更新


@dataclass
class AgentMessage:
    """Agent间消息"""
    id: str
    from_agent: str
    to_agent: str  # "__broadcast__" 表示广播
    type: MessageType
    content: Any
    thread_id: Optional[str] = None  # 会话线程ID，用于追踪消息链
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict = field(default_factory=dict)


@dataclass
class AgentInfo:
    """Agent 注册信息"""
    name: str
    description: str
    capabilities: List[str]  # ["data_collection", "analysis", "visualization", ...]
    status: str = "idle"  # idle | busy | error
    last_heartbeat: datetime = field(default_factory=datetime.now)


@dataclass
class BlackboardEntry:
    """黑板条目"""
    namespace: str
    key: str
    value: Any
    version: int = 1
    timestamp: datetime = field(default_factory=datetime.now)
    updated_by: Optional[str] = None
