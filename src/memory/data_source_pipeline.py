"""
DataSourcePipeline — V4 多级数据获取链

按 QueryRouter 指定的 data_source_priority 依次尝试:
  1. SQL FactStore (本地已入库指标, O(1))
  2. get_financial_data (东方财富/新浪/腾讯 API)
  3. ChromaDB RAG (文本证据)
  4. KVStore cache (带 TTL 检查)
  5. search_financial_web (discovery only, 不直接取信)

每层命中后判断是否需要继续查下层。如果 SQL 和 API 都有数据但冲突，
输出专业的不一致提示，不静默覆盖。

Usage:
    pipeline = DataSourcePipeline(fact_store, cache_service)
    result = pipeline.execute(plan, ticker, report_period)
    # → {"primary": {...}, "sources_checked": [...], "conflict": None/str}
"""

from __future__ import annotations

import logging
from typing import Optional, Dict, Any, List, TYPE_CHECKING
from dataclasses import dataclass, field

if TYPE_CHECKING:
    from src.storage.fact_store import FactStore
    from src.memory.cache_service import CacheService

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """多级链查询结果。"""
    # 主要答案（最高优先级命中）
    primary: Dict[str, Any] = field(default_factory=dict)
    # 所有命中的数据源和结果
    sources: List[Dict[str, Any]] = field(default_factory=list)
    # 冲突信息
    conflict: Optional[str] = None
    # 标记 web 结果是否需要进一步入库
    needs_ingestion: bool = False
    found_pdf_url: Optional[str] = None
    # 错误累积
    errors: List[str] = field(default_factory=list)

    def has_data(self) -> bool:
        return bool(self.primary)

    @property
    def sql_result(self) -> Optional[Dict]:
        for s in self.sources:
            if s["source"] == "sql":
                return s
        return None

    @property
    def api_result(self) -> Optional[Dict]:
        for s in self.sources:
            if s["source"] == "api":
                return s
        return None


class DataSourcePipeline:
    """按优先级链执行多级数据获取。"""

    def __init__(self, fact_store: FactStore,
                 cache_service: Optional[CacheService] = None):
        self._fs = fact_store
        self._cache = cache_service

    def execute(self,
                priority_chain: List[str],
                ticker: str,
                company_name: str = "",
                report_period: str = "2026Q1",
                metrics: List[str] = None,
                query: str = "",
                ) -> PipelineResult:
        """
        按优先级链执行数据获取。

        Args:
            priority_chain: ["sql","api","web"] 等
            ticker: 股票代码
            company_name: 公司名
            report_period: 报告期
            metrics: 需要的指标列表
            query: 原始查询 (用于 web search)
        """
        result = PipelineResult()
        metrics = metrics or []
        rp = report_period

        for source in priority_chain:
            if source == "sql":
                self._try_sql(result, ticker, rp, metrics)
            elif source == "api":
                self._try_api(result, ticker, rp, metrics, company_name)
            elif source == "rag":
                self._try_rag(result, ticker, company_name, rp, query)
            elif source == "kv":
                self._try_kv(result, ticker, rp)
            elif source == "web":
                self._try_web(result, ticker, company_name, rp, query)
            elif source == "ingest":
                self._try_ingest(result, ticker, company_name, rp)

            # SQL 命中 + 指标满足 → 短路（但继续查 API 做冲突检测）
            if source == "sql" and result.sql_result:
                continue  # 继续查下一个源，不做短路

        # ── 冲突检测 ──
        result.conflict = self._detect_conflict(result, ticker, rp, metrics)

        return result

    def _try_sql(self, result: PipelineResult, ticker: str, rp: str, metrics: List[str]):
        """查 SQLite FactStore。"""
        try:
            if metrics:
                rows = self._fs.query_metrics_by_company_period(ticker, rp, metrics)
            else:
                rows = self._fs.query_metrics_by_company_period(ticker, rp)

            if rows:
                data = []
                for r in rows:
                    data.append({
                        "metric_code": r["metric_code"],
                        "metric_name": r.get("metric_name", ""),
                        "value": r["value"],
                        "unit": r.get("unit", "元"),
                        "report_period": r.get("report_period", rp),
                        "source_page": r.get("source_page"),
                        "source_doc_id": r.get("source_doc_id", ""),
                    })
                result.sources.append({
                    "source": "sql",
                    "count": len(data),
                    "data": data,
                })
                if not result.primary:
                    result.primary = {"source": "sql", "data": data}
        except Exception as e:
            result.errors.append(f"SQL error: {e}")

    def _try_api(self, result: PipelineResult, ticker: str, rp: str,
                 metrics: List[str], company_name: str):
        """查 get_financial_data API。"""
        try:
            from src.tools.enhanced_data_collector import enhanced_data_collector
            data = enhanced_data_collector.get_financial_data(ticker, "all")
            if data and "error" not in data:
                api_metrics = self._extract_api_metrics(data, ticker, rp)
                if api_metrics:
                    result.sources.append({
                        "source": "api",
                        "count": len(api_metrics),
                        "data": api_metrics,
                        "raw": data,
                        "timestamp": data.get("timestamp", ""),
                    })
                    if not result.primary:
                        result.primary = {"source": "api", "data": api_metrics}
        except Exception as e:
            result.errors.append(f"API error: {e}")

    def _try_rag(self, result: PipelineResult, ticker: str, company_name: str,
                  rp: str, query: str):
        """查 ChromaDB RAG。此处返回占位，实际注入由 MemoryAgent 完成。"""
        # RAG 检索在 MemoryAgent 中完成，这里仅为标记
        result.sources.append({"source": "rag", "count": 0, "data": []})

    def _try_kv(self, result: PipelineResult, ticker: str, rp: str):
        """查 KVStore 缓存。"""
        if self._cache:
            cache_key = f"cache:quote:{ticker}"
            cached = self._cache.get(cache_key)
            if cached:
                result.sources.append({
                    "source": "kv",
                    "data": cached,
                    "meta": self._cache.get_meta(cache_key) or {},
                })

    def _try_web(self, result: PipelineResult, ticker: str, company_name: str,
                  rp: str, query: str):
        """联网搜索 (discovery only)。"""
        try:
            from src.tools.web_search_tool import (
                search_financial_data, extract_financial_metrics
            )
            name = company_name or ticker
            sq = query or f"{name} {rp} 营收 净利润 财务数据"
            web_results = search_financial_data(sq, max_results=5)
            all_text = " ".join(r.get("snippet", "") for r in web_results)
            extracted = extract_financial_metrics(all_text)

            if extracted or web_results:
                result.sources.append({
                    "source": "web_discovery",
                    "needs_ingestion": True,
                    "data": extracted,
                    "urls": [r.get("url", "") for r in web_results[:3]],
                    "raw_results": web_results,
                })
                # web 结果标记为需要入库，不作为 primary
                result.needs_ingestion = True
        except Exception as e:
            result.errors.append(f"Web error: {e}")

    def _try_ingest(self, result: PipelineResult, ticker: str, company_name: str, rp: str):
        """尝试入库（从 web discovery 获得的 PDF URL）。"""
        result.sources.append({
            "source": "ingest",
            "status": "pending",
            "message": f"请手动提供 {ticker} {company_name} {rp} 财报PDF路径",
        })

    def _extract_api_metrics(self, api_data: dict, ticker: str, rp: str) -> List[dict]:
        """从 API 返回的原始数据中提取标准化指标。"""
        api_metrics = []
        # 利润表
        profit = api_data.get("profit", [])
        if isinstance(profit, list) and profit:
            latest = profit[0] if profit else {}
            if latest.get("revenue"):
                api_metrics.append({
                    "metric_code": "revenue",
                    "metric_name": "营业收入",
                    "value": latest["revenue"] * 1e8,  # API 返回的是亿
                    "unit": "元",
                    "report_period": rp,
                    "source": "eastmoney_api",
                })
            if latest.get("net_profit"):
                api_metrics.append({
                    "metric_code": "net_profit",
                    "metric_name": "净利润",
                    "value": latest["net_profit"] * 1e8,
                    "unit": "元",
                    "report_period": rp,
                    "source": "eastmoney_api",
                })
        # 指标
        indicator = api_data.get("indicator", [])
        if isinstance(indicator, list) and indicator:
            latest_ind = indicator[0] if indicator else {}
            for mc, name in [("roe_weighted", "ROE"), ("gross_margin", "毛利率"),
                              ("net_margin", "净利率")]:
                key_map = {"roe_weighted": "roe", "gross_margin": "gross_margin",
                           "net_margin": "net_margin"}
                val = latest_ind.get(key_map.get(mc, mc))
                if val is not None:
                    api_metrics.append({
                        "metric_code": mc,
                        "metric_name": name,
                        "value": val,
                        "unit": "%",
                        "report_period": rp,
                        "source": "eastmoney_api",
                    })
        return api_metrics

    def _detect_conflict(self, result: PipelineResult, ticker: str,
                          rp: str, metrics: List[str]) -> Optional[str]:
        """检测 SQL 和 API 之间的数据冲突。"""
        sql = result.sql_result
        api = result.api_result
        if not sql or not api:
            return None

        sql_data = {d["metric_code"]: d for d in sql.get("data", [])}
        api_data = {d["metric_code"]: d for d in api.get("data", [])}

        conflicts = []
        for mc in set(list(sql_data.keys()) + list(api_data.keys())):
            sv = sql_data.get(mc)
            av = api_data.get(mc)
            if sv and av and sv.get("value") and av.get("value"):
                diff_pct = abs(sv["value"] - av["value"]) / max(abs(sv["value"]), 1) * 100
                if diff_pct > 5:  # 差异超过 5%
                    conflicts.append({
                        "metric": mc,
                        "metric_name": sv.get("metric_name", mc),
                        "sql_value": sv["value"],
                        "api_value": av["value"],
                        "diff_pct": round(diff_pct, 1),
                    })

        if conflicts:
            lines = [
                "本地财报解析结果与第三方 API 返回值不一致。",
                "当前答案优先采用已入库财报 PDF 的结构化结果，API 数据作为参考。",
                "建议检查报告期、单位和口径是否一致。",
                "",
                "不一致项：",
            ]
            for c in conflicts:
                sql_display = f"{c['sql_value']/1e8:.2f}亿" if abs(c['sql_value']) >= 1e8 else str(c['sql_value'])
                api_display = f"{c['api_value']/1e8:.2f}亿" if abs(c['api_value']) >= 1e8 else str(c['api_value'])
                lines.append(f"  {c['metric_name']}: SQL={sql_display} vs API={api_display} (差异 {c['diff_pct']}%)")
            return "\n".join(lines)

        return None
