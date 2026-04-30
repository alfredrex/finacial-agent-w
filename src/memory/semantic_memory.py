"""
语义记忆管理器 (Semantic Memory)
封装 RAGManager，提供实体关系索引和金融领域术语检索
"""
from typing import List, Optional, Dict, Any
import re

from src.memory.models import (
    MemoryUnit, MemoryQuery, MemorySearchResult,
    MemoryType, MemoryImportance, importance_to_score, score_to_importance,
)
from src.tools.rag_manager import RAGManager
from src.config import settings


# 常见金融实体模式
FINANCIAL_ENTITY_PATTERNS = [
    (r'6\d{5}', 'stock_sh'),      # 沪市股票代码
    (r'0\d{5}', 'stock_sz'),      # 深市股票代码
    (r'3\d{5}', 'stock_cy'),      # 创业板股票代码
    (r'4\d{5}', 'stock_three'),   # 新三板
    (r'8\d{5}', 'stock_bj'),      # 北交所
    (r'[A-Z]+', 'ticker_us'),     # 美股代码
]

FINANCIAL_KEYWORDS = [
    "市盈率", "市净率", "ROE", "ROA", "毛利率", "净利率",
    "营业收入", "净利润", "现金流", "资产负债率",
    "K线", "均线", "MACD", "RSI", "KDJ", "布林带",
    "涨停", "跌停", "成交量", "换手率", "市值",
    "北向资金", "南向资金", "主力资金",
    "白酒", "新能源", "半导体", "医药", "金融", "消费",
]


class SemanticMemoryManager:
    """
    语义记忆管理器
    管理金融领域知识和实体关系
    """

    def __init__(self, collection_name: str = "semantic_memory",
                 chroma_path: Optional[str] = None):
        self._rag = RAGManager(
            collection_name=collection_name,
            persist_directory=chroma_path or settings.CHROMA_DB_PATH,
        )
        self._entity_index: Dict[str, List[str]] = {}  # entity -> list of doc_ids

    def extract_entities(self, text: str) -> List[str]:
        """从文本中提取金融实体"""
        entities = set()

        for pattern, etype in FINANCIAL_ENTITY_PATTERNS:
            matches = re.findall(pattern, text)
            for m in matches:
                entities.add(f"{etype}:{m}")

        for keyword in FINANCIAL_KEYWORDS:
            if keyword in text:
                entities.add(f"concept:{keyword}")

        return list(entities)

    def store_knowledge(self, content: str, source: str = "",
                        entities: List[str] = None) -> str:
        """存储知识文档"""
        entities = entities or self.extract_entities(content)
        metadata = {
            "type": MemoryType.SEMANTIC.value,
            "source": source,
            "entities": ",".join(entities[:20]),
            "timestamp": __import__('datetime').datetime.now().isoformat(),
        }
        count = self._rag.add_texts(texts=[content], metadatas=[metadata])

        doc_id = f"sem_{hash(content) % 10**8}"
        for entity in entities:
            self._entity_index.setdefault(entity, []).append(doc_id)
        return doc_id

    def retrieve(self, query: MemoryQuery) -> List[MemorySearchResult]:
        """从语义记忆中检索"""
        chroma_results = self._rag.similarity_search_with_score(
            query=query.query,
            k=query.limit * 2,
        )

        results = []
        for doc, score in chroma_results:
            meta = doc.metadata or {}
            similarity = 1.0 - score
            if similarity < query.min_score:
                continue

            entities_str = meta.get("entities", "")
            unit = MemoryUnit(
                id=f"sem_{hash(doc.page_content) % 10**8}",
                type=MemoryType.SEMANTIC,
                content=doc.page_content[:1000],
                entities=entities_str.split(",") if entities_str else [],
                timestamp=__import__('datetime').datetime.now(),
                metadata={"source": meta.get("source", "")},
            )
            results.append(MemorySearchResult(
                unit=unit, score=similarity, source="semantic_memory"
            ))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:query.limit]

    def get_entity_context(self, entity: str) -> List[str]:
        """获取与实体相关的所有知识摘要"""
        doc_ids = self._entity_index.get(entity, [])
        if not doc_ids:
            return []
        return [f"实体 {entity} 相关: {did}" for did in doc_ids[:5]]

    def get_stats(self) -> dict:
        return self._rag.get_collection_stats()


# 全局实例
semantic_memory_manager = SemanticMemoryManager()
