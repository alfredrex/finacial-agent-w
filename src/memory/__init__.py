"""
记忆系统统一入口
组合短期记忆、长期经验记忆、语义记忆、用户偏好记忆
"""
from typing import List, Optional, Dict, Any

from src.memory.models import (
    MemoryUnit, MemoryQuery, MemorySearchResult, MemoryType, MemoryImportance,
)
from src.memory.working_memory import working_memory_manager, WorkingMemoryManager
from src.memory.episodic_memory import episodic_memory_manager, EpisodicMemoryManager
from src.memory.semantic_memory import semantic_memory_manager, SemanticMemoryManager
from src.memory.user_memory import user_memory_manager, UserMemoryManager
from src.memory.consolidator import consolidator


class MemorySystem:
    """
    统一记忆系统入口
    提供 store() / retrieve() / consolidate() 高层接口
    """

    def __init__(self):
        self.working: WorkingMemoryManager = working_memory_manager
        self.episodic: EpisodicMemoryManager = episodic_memory_manager
        self.semantic: SemanticMemoryManager = semantic_memory_manager
        self.user = user_memory_manager

    async def store(self, query: str, answer: str = "", thought_process: str = "",
                    entities: List[str] = None, state: dict = None):
        """将一次交互存储到所有相关记忆中"""
        entities = entities or []
        # 长期经验记忆
        self.episodic.store(
            query=query, answer=answer, thought_process=thought_process,
            entities=entities, state=state,
        )
        # 提取实体存入语义记忆
        sem_entities = self.semantic.extract_entities(query + " " + answer)
        if sem_entities:
            content = f"Q: {query}\nA: {answer}"
            self.semantic.store_knowledge(content=content, entities=sem_entities)

    async def retrieve(self, query_text: str, limit: int = 5) -> Dict[str, List[MemorySearchResult]]:
        """从所有记忆中检索相关内容"""
        mq = MemoryQuery(query=query_text, limit=limit)

        results = {
            "working": self.working.retrieve(mq),
            "episodic": self.episodic.retrieve(mq),
            "semantic": self.semantic.retrieve(mq),
        }

        # 用户偏好
        user_memories = await self.user.search_memory(query_text)
        if user_memories:
            from datetime import datetime
            results["user"] = [
                MemorySearchResult(
                    unit=MemoryUnit(
                        id=f"user_{i}",
                        type=MemoryType.USER_PREFERENCE,
                        content=m.get("content", ""),
                        timestamp=datetime.now(),
                    ),
                    score=0.8,
                    source="user_memory",
                )
                for i, m in enumerate(user_memories[:3])
            ]

        return results

    def get_context_string(self, results: Dict[str, List[MemorySearchResult]],
                           top_k: int = 5) -> str:
        """将检索结果格式化为上下文文本"""
        all_results = []
        for source, items in results.items():
            for item in items:
                all_results.append(item)

        all_results.sort(key=lambda r: r.score, reverse=True)
        top = all_results[:top_k]

        if not top:
            return "暂无相关历史记忆"

        parts = ["【历史相关记忆】"]
        for item in top:
            source_tag = item.source
            content = item.unit.content[:200]
            parts.append(f"  [{source_tag}] (相关度: {item.score:.2f}) {content}")

        return "\n".join(parts)


# 全局实例
memory_system = MemorySystem()


__all__ = [
    'MemorySystem', 'memory_system',
    'WorkingMemoryManager', 'working_memory_manager',
    'EpisodicMemoryManager', 'episodic_memory_manager',
    'SemanticMemoryManager', 'semantic_memory_manager',
    'UserMemoryManager', 'user_memory_manager',
    'consolidator',
]
