"""
Query Schema — 查询类型和查询计划的数据结构
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum


class QueryType(str, Enum):
    """查询类型枚举"""
    USER_MEMORY = "user_memory"
    REALTIME_QUOTE = "realtime_quote"
    LATEST_NEWS = "latest_news"
    METRIC_QUERY = "metric_query"
    CALCULATION_QUERY = "calculation_query"
    COMPARISON_QUERY = "comparison_query"
    DOCUMENT_QUERY = "document_query"
    HYBRID_ANALYSIS = "hybrid_analysis"
    REPORT_GENERATION = "report_generation"
    PDF_QA = "pdf_qa"             # 已上传 PDF 问答
    MISSING_REPORT = "missing_report"  # 本地缺失财报
    UNKNOWN = "unknown"


# ─── 数据源优先级链 ───
# 每种查询类型对应一个有序的数据源列表
# "sql" = SQLite FactStore, "api" = get_financial_data,
# "kv" = KVStore cache, "rag" = ChromaDB, "web" = search_financial_web,
# "ingest" = 下载PDF入库

SOURCE_PRIORITY: dict[QueryType, list[str]] = {
    QueryType.REALTIME_QUOTE:      ["api", "kv", "web"],
    QueryType.METRIC_QUERY:        ["sql", "api", "web"],
    QueryType.CALCULATION_QUERY:   ["sql", "api", "web"],
    QueryType.COMPARISON_QUERY:    ["sql", "api", "web"],
    QueryType.PDF_QA:              ["sql", "rag", "api"],
    QueryType.DOCUMENT_QUERY:      ["rag", "sql", "web"],
    QueryType.HYBRID_ANALYSIS:     ["rag", "sql", "web"],
    QueryType.LATEST_NEWS:         ["web", "api", "kv"],
    QueryType.MISSING_REPORT:      ["web", "ingest", "sql", "rag"],
    QueryType.USER_MEMORY:         ["kv", "sql", "rag"],
    QueryType.REPORT_GENERATION:   ["sql", "rag", "api", "kv"],
    QueryType.UNKNOWN:             ["web", "api", "sql", "rag"],
}


@dataclass
class QueryPlan:
    """Router 输出的结构化查询计划。

    示例:
        QueryPlan(
            query_type=QueryType.METRIC_QUERY,
            ticker="002594",
            company_name="比亚迪",
            report_period="2026Q1",
            metrics=["net_profit_parent"],
            needs_sql=True,
            needs_rag=False,
            needs_kv=False,
            needs_web=False,
            reason="用户询问精确财报指标，应走 SQL FactStore",
        )
    """

    # ── 基础信息 ──
    query_type: QueryType = QueryType.UNKNOWN
    original_query: str = ""

    # ── 实体提取 ──
    ticker: Optional[str] = None           # 股票代码
    company_name: Optional[str] = None     # 公司名
    report_period: Optional[str] = None    # 报告期 "2026Q1"

    # ── 指标提取 ──
    metrics: List[str] = field(default_factory=list)  # 标准化 metric_code 列表

    # ── 路由决策 ──
    needs_sql: bool = False
    needs_rag: bool = False
    needs_kv: bool = False
    needs_web: bool = False

    # ── 数据源优先级链 (V4) ──
    data_source_priority: List[str] = field(default_factory=list)
    # e.g. ["sql","api","web"] 表示先查 SQL, 再查 API, 最后 web
    # 值: "sql" | "api" | "kv" | "rag" | "web" | "ingest"

    # ── 附加信息 ──
    reason: str = ""
    freshness_requirement: Optional[str] = None  # "latest" / "recent" / None
    confidence: float = 1.0                     # 路由分类置信度
    is_comparison: bool = False
    comparison_tickers: List[str] = field(default_factory=list)

    @property
    def is_precise_metric(self) -> bool:
        return self.query_type in (QueryType.METRIC_QUERY, QueryType.CALCULATION_QUERY)

    @property
    def needs_factstore(self) -> bool:
        return self.needs_sql

    def to_dict(self) -> dict:
        return {
            "query_type": self.query_type.value,
            "ticker": self.ticker,
            "company_name": self.company_name,
            "report_period": self.report_period,
            "metrics": self.metrics,
            "needs_sql": self.needs_sql,
            "needs_rag": self.needs_rag,
            "needs_kv": self.needs_kv,
            "needs_web": self.needs_web,
            "data_source_priority": self.data_source_priority,
            "reason": self.reason,
        }

    def __repr__(self) -> str:
        parts = [f"QueryPlan(type={self.query_type.value}"]
        if self.ticker:
            parts.append(f"ticker={self.ticker}")
        if self.metrics:
            parts.append(f"metrics={self.metrics}")
        sources = []
        if self.needs_sql: sources.append("sql")
        if self.needs_rag: sources.append("rag")
        if self.needs_kv: sources.append("kv")
        if self.needs_web: sources.append("web")
        parts.append(f"sources=[{'+'.join(sources)}]")
        parts.append(f"reason='{self.reason[:40]}')")
        return " ".join(parts)
