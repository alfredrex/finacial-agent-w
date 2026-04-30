"""
长期经验记忆管理器 (Episodic Memory / Long-Term Memory)
使用 ChromaDB 持久化存储历史交互，支持加权检索、重要性管理、记忆合并
"""
import uuid
import hashlib
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from threading import Lock

from src.memory.models import (
    MemoryUnit, MemoryQuery, MemorySearchResult,
    MemoryType, MemoryImportance, importance_to_score, score_to_importance,
)
from src.config import settings
from src.tools.rag_manager import RAGManager


def _compute_importance(state: dict) -> float:
    """根据 state 信息计算交互的重要性分数 (0.0 ~ 1.0)"""
    score = 0.5  # baseline
    if state.get("needs_deep_analysis"):
        score += 0.2
    if state.get("is_deep_qa"):
        score += 0.15
    if state.get("exception_info"):
        score += 0.15  # 异常处理值得记住
    if state.get("data_unavailable"):
        score += 0.1
    if state.get("user_memory_summary"):
        score += 0.1
    return min(score, 1.0)


class EpisodicMemoryManager:
    """
    长期经验记忆管理器
    将完整交互存入 ChromaDB，加权检索 (相似度 + 近因 + 重要性)
    """

    def __init__(self, collection_name: str = "episodic_memory",
                 chroma_path: Optional[str] = None):
        self._rag = RAGManager(
            collection_name=collection_name,
            persist_directory=chroma_path or settings.CHROMA_DB_PATH,
        )
        self._lock = Lock()
        self._id_counter = 0

    def _next_id(self) -> str:
        with self._lock:
            self._id_counter += 1
            ts = datetime.now().strftime("%Y%m%d%H%M%S%f")
            return f"ep_{ts}_{self._id_counter}"

    def _make_document_id(self, query: str) -> str:
        """用 query 的 hash 做去重参考"""
        return f"ep_{hashlib.md5(query.encode()).hexdigest()[:12]}"

    def store(self, query: str, answer: str = "", thought_process: str = "",
              entities: List[str] = None, state: dict = None,
              importance_override: float = None) -> str:
        """
        存储一次交互到长期记忆
        返回 memory_id
        """
        entities = entities or []

        importance = importance_override if importance_override is not None else \
            _compute_importance(state or {})

        summary = f"[Episodic] Query: {query[:100]} | Answer: {answer[:150]}..."

        content_parts = [f"用户问题: {query}"]
        if thought_process:
            content_parts.append(f"思考过程: {thought_process[:500]}")
        if answer:
            content_parts.append(f"回答: {answer[:500]}")
        if entities:
            content_parts.append(f"相关实体: {', '.join(entities)}")
        content = "\n".join(content_parts)

        memory_id = self._next_id()
        metadata = {
            "memory_id": memory_id,
            "type": MemoryType.EPISODIC.value,
            "importance": importance,
            "importance_label": score_to_importance(importance).value,
            "timestamp": datetime.now().isoformat(),
            "entities": ",".join(entities[:10]),
            "query_summary": query[:100],
            "access_count": "0",
        }

        doc_id = self._make_document_id(query)
        self._rag.add_texts(
            texts=[content],
            metadatas=[metadata],
            ids=[doc_id],
        )
        return memory_id

    def retrieve(self, query: MemoryQuery) -> List[MemorySearchResult]:
        """
        加权检索: similarity * w_sim + recency * w_rec + importance * w_imp
        """
        chroma_results = self._rag.similarity_search_with_score(
            query=query.query,
            k=query.limit * 2,
        )

        results = []
        now = datetime.now()

        for doc, score in chroma_results:
            meta = doc.metadata or {}
            importance = float(meta.get("importance", 0.5))

            # 近因子 (24h内全值，之后线性衰减)
            ts_str = meta.get("timestamp", "")
            recency_factor = 0.5
            if ts_str:
                try:
                    ts = datetime.fromisoformat(ts_str)
                    hours_ago = (now - ts).total_seconds() / 3600
                    recency_factor = max(0.1, 1.0 - hours_ago / 720)  # 30天衰减到0.1
                except ValueError:
                    pass

            # 综合评分
            similarity = 1.0 - score  # Chroma 返回 L2 距离，转相似度
            combined = (
                similarity * query.similarity_weight +
                recency_factor * query.recency_weight +
                importance * query.importance_weight
            )

            if combined < query.min_score:
                continue

            unit = MemoryUnit(
                id=meta.get("memory_id", doc.id),
                type=MemoryType.EPISODIC,
                content=doc.page_content[:1000],
                summary=meta.get("query_summary", ""),
                importance=score_to_importance(importance),
                importance_score=importance,
                entities=meta.get("entities", "").split(",") if meta.get("entities") else [],
                timestamp=datetime.fromisoformat(ts_str) if ts_str else datetime.now(),
                access_count=int(meta.get("access_count", 0)),
                metadata={"doc_id": doc.id},
            )
            results.append(MemorySearchResult(unit=unit, score=combined, source="episodic_memory"))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:query.limit]

    def update_importance(self, memory_id: str, delta: float = 0.05):
        """访问时增加/衰减重要性"""
        results = self._rag.similarity_search(f"memory_id:{memory_id}", k=3)
        for doc in results:
            meta = dict(doc.metadata) if doc.metadata else {}
            if meta.get("memory_id") == memory_id:
                current = float(meta.get("importance", 0.5))
                meta["importance"] = max(0.0, min(1.0, current + delta))
                meta["access_count"] = str(int(meta.get("access_count", 0)) + 1)
                self._rag.add_texts(
                    texts=[doc.page_content],
                    metadatas=[meta],
                    ids=[doc.id],
                )
                break

    def consolidate(self, max_age_days: float = 90, min_importance: float = 0.1):
        """
        记忆合并：清理低价值 + 过期的记忆
        """
        vectorstore = self._rag.initialize_vectorstore()
        collection = vectorstore._collection
        all_items = collection.get(limit=100)
        if not all_items or not all_items.get("ids"):
            return 0

        cutoff = datetime.now() - timedelta(days=max_age_days)
        to_delete = []

        for i, doc_id in enumerate(all_items["ids"]):
            meta = all_items["metadatas"][i] if all_items.get("metadatas") else {}
            if not meta:
                continue
            importance = float(meta.get("importance", 0.5))
            ts_str = meta.get("timestamp", "")
            try:
                ts = datetime.fromisoformat(ts_str) if ts_str else datetime.now()
            except (ValueError, TypeError):
                ts = datetime.now()

            if ts < cutoff and importance < min_importance:
                to_delete.append(doc_id)

        if to_delete:
            collection.delete(ids=to_delete)
        return len(to_delete)

    def get_stats(self) -> dict:
        return self._rag.get_collection_stats()

    def clear(self):
        self._rag.clear_collection()


# 全局实例
episodic_memory_manager = EpisodicMemoryManager()
