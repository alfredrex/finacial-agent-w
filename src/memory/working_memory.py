"""
短期记忆管理器 (Working Memory / Short-Term Memory)
管理当前会话内的对话缓冲和Agent决策轨迹，超出窗口时自动压缩
"""
import copy
from typing import List, Optional, Dict, Any
from datetime import datetime
from collections import deque

from src.memory.models import (
    ConversationTurn, AgentTrace, MemoryQuery, MemorySearchResult,
    MemoryUnit, MemoryType, MemoryImportance,
    importance_to_score,
)


class ConversationBuffer:
    """可配置窗口大小的对话缓冲，带自动摘要压缩"""

    def __init__(self, max_turns: int = 20):
        self.max_turns = max_turns
        self._turns: deque[ConversationTurn] = deque(maxlen=max_turns)
        self._summaries: List[str] = []
        self._compressed_count = 0

    def add_turn(self, turn: ConversationTurn):
        if len(self._turns) >= self.max_turns:
            self._summarize_oldest()
        self._turns.append(turn)

    def _summarize_oldest(self):
        """压缩最早的部分对话为一句话摘要"""
        oldest_turns = [self._turns.popleft() for _ in range(min(3, len(self._turns)))]
        summary = f"[压缩摘要 #{self._compressed_count + 1}] " + \
                  " | ".join(f"{t.role}: {t.content[:60]}" for t in oldest_turns)
        self._summaries.append(summary)
        self._compressed_count += 1

    def get_context(self, max_recent: int = 5) -> str:
        """返回格式化后的短期记忆上下文"""
        parts = []
        if self._summaries:
            parts.append("【历史摘要】")
            parts.extend(f"  {s}" for s in self._summaries[-3:])
            parts.append("")
        if self._turns:
            recent = list(self._turns)[-max_recent:]
            parts.append("【最近对话】")
            for t in recent:
                role_tag = "用户" if t.role == "user" else "助手"
                parts.append(f"  {role_tag}: {t.content[:200]}")
        return "\n".join(parts)

    def get_recent_turns(self, n: int = 5) -> List[ConversationTurn]:
        return list(self._turns)[-n:]

    def clear(self):
        self._turns.clear()
        self._summaries.clear()
        self._compressed_count = 0

    @property
    def turn_count(self) -> int:
        return len(self._turns)

    def to_dict(self) -> dict:
        return {
            "turns": [
                {"role": t.role, "content": t.content[:100],
                 "timestamp": t.timestamp.isoformat()}
                for t in self._turns
            ],
            "summaries": self._summaries,
        }


class AgentTraceBuffer:
    """Agent 决策轨迹缓冲"""

    def __init__(self, max_traces: int = 30):
        self.max_traces = max_traces
        self._traces: deque[AgentTrace] = deque(maxlen=max_traces)

    def add_trace(self, trace: AgentTrace):
        self._traces.append(trace)

    def get_recent(self, agent_name: Optional[str] = None, n: int = 10) -> List[AgentTrace]:
        if agent_name:
            filtered = [t for t in self._traces if t.agent_name == agent_name]
            return filtered[-n:]
        return list(self._traces)[-n:]

    def to_dict(self) -> list:
        return [
            {"agent": t.agent_name, "thought": t.thought[:100],
             "action": t.action[:100], "iteration": t.iteration}
            for t in list(self._traces)[-20:]
        ]


class WorkingMemoryManager:
    """短期记忆管理器：对话缓冲 + Agent轨迹 + 摘要压缩"""

    def __init__(self, max_conversation_turns: int = 20, max_agent_traces: int = 30):
        self.conversation = ConversationBuffer(max_turns=max_conversation_turns)
        self.traces = AgentTraceBuffer(max_traces=max_agent_traces)
        self._metadata: Dict[str, Any] = {}

    def add_user_message(self, content: str):
        self.conversation.add_turn(ConversationTurn(role="user", content=content))

    def add_assistant_message(self, content: str, agent_name: Optional[str] = None):
        self.conversation.add_turn(
            ConversationTurn(role="assistant", content=content, agent_name=agent_name)
        )

    def add_agent_trace(self, agent_name: str, thought: str, action: str,
                        observation: str, iteration: int = 0, tool_results=None):
        self.traces.add_trace(AgentTrace(
            agent_name=agent_name, thought=thought, action=action,
            observation=observation, iteration=iteration,
            tool_results=tool_results,
        ))

    def get_context(self, max_recent_turns: int = 5, max_recent_traces: int = 5) -> str:
        """获取格式化后的完整短期记忆上下文"""
        parts = ["===== 短期记忆 ====="]
        parts.append(self.conversation.get_context(max_recent=max_recent_turns))
        parts.append("")
        traces = self.traces.get_recent(n=max_recent_traces)
        if traces:
            parts.append("【近期Agent决策】")
            for t in traces:
                parts.append(f"  [{t.agent_name}] Step {t.iteration}: {t.thought[:80]}")
        return "\n".join(parts)

    def retrieve(self, query: MemoryQuery) -> List[MemorySearchResult]:
        """从短期记忆中检索相关内容"""
        results = []
        recent_turns = self.conversation.get_recent_turns(n=query.limit)
        for i, turn in enumerate(recent_turns):
            query_lower = query.query.lower()
            if query_lower in turn.content.lower():
                unit = MemoryUnit(
                    id=f"stm_turn_{i}",
                    type=MemoryType.WORKING,
                    content=turn.content[:500],
                    timestamp=turn.timestamp,
                    metadata={"role": turn.role, "agent": turn.agent_name},
                )
                results.append(MemorySearchResult(
                    unit=unit, score=0.6 - i * 0.05, source="working_memory"
                ))
        return results[:query.limit]

    def clear(self):
        self.conversation.clear()
        self.traces._traces.clear()

    def set_metadata(self, key: str, value: Any):
        self._metadata[key] = value

    def get_metadata(self, key: str, default=None) -> Any:
        return self._metadata.get(key, default)


# 全局实例
working_memory_manager = WorkingMemoryManager()
