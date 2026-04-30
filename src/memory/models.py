"""记忆系统数据模型"""
from dataclasses import dataclass, field
from typing import List, Optional, Any
from datetime import datetime
from enum import Enum


class MemoryType(str, Enum):
    EPISODIC = "episodic"
    WORKING = "working"
    SEMANTIC = "semantic"
    USER_PREFERENCE = "user_preference"


class MemoryImportance(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class MemoryUnit:
    """单个记忆单元"""
    id: str
    type: MemoryType
    content: str
    summary: Optional[str] = None
    importance: MemoryImportance = MemoryImportance.MEDIUM
    importance_score: float = 0.5  # 0.0 ~ 1.0
    entities: List[str] = field(default_factory=list)
    query: Optional[str] = None
    answer: Optional[str] = None
    thought_process: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    last_access: datetime = field(default_factory=datetime.now)
    access_count: int = 0
    metadata: dict = field(default_factory=dict)


@dataclass
class MemoryQuery:
    """记忆检索请求"""
    query: str
    types: List[MemoryType] = field(default_factory=lambda: list(MemoryType))
    limit: int = 5
    recency_weight: float = 0.3
    importance_weight: float = 0.2
    similarity_weight: float = 0.5
    entities: Optional[List[str]] = None
    min_score: float = 0.3


@dataclass
class MemorySearchResult:
    """记忆检索结果"""
    unit: MemoryUnit
    score: float
    source: str  # which memory manager returned this


@dataclass
class ConversationTurn:
    """单轮对话"""
    role: str  # "user" | "assistant" | "system"
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    agent_name: Optional[str] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class AgentTrace:
    """Agent 决策轨迹"""
    agent_name: str
    thought: str
    action: str
    observation: str
    timestamp: datetime = field(default_factory=datetime.now)
    iteration: int = 0
    tool_results: Optional[Any] = None


IMPORTANCE_VALUE_MAP = {
    MemoryImportance.LOW: 0.2,
    MemoryImportance.MEDIUM: 0.5,
    MemoryImportance.HIGH: 0.8,
    MemoryImportance.CRITICAL: 1.0,
}


def importance_to_score(importance: MemoryImportance) -> float:
    return IMPORTANCE_VALUE_MAP.get(importance, 0.5)


def score_to_importance(score: float) -> MemoryImportance:
    if score >= 0.8:
        return MemoryImportance.CRITICAL
    elif score >= 0.6:
        return MemoryImportance.HIGH
    elif score >= 0.3:
        return MemoryImportance.MEDIUM
    return MemoryImportance.LOW
