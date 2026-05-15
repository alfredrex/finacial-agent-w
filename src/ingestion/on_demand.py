"""
On-Demand Ingestion — SQL miss 时自动搜索 → 下载 → 入库

流程:
  Router 判定 metric_query
    → SQL miss
    → 查 CacheService (是否有已下载记录)
    → Cache miss
    → SourceFetcher 搜索 URL
    → 下载 PDF
    → BatchIngestor 入库
    → 回答用户

Usage:
    from src.ingestion.on_demand import OnDemandIngestor
    odi = OnDemandIngestor(fact_store, cache_service)
    result = odi.resolve("601939", "建设银行", "2026Q1")
"""

from __future__ import annotations

import logging
from typing import Optional, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from src.storage.fact_store import FactStore
    from src.memory.cache_service import CacheService
    from src.ingestion.batch_ingestor import BatchIngestor

logger = logging.getLogger(__name__)


class OnDemandIngestor:
    """按需入库：SQL miss 时自动获取并入库。"""

    def __init__(self, fact_store: FactStore,
                 cache_service: Optional[CacheService] = None,
                 download_dir: str = "data/reports"):
        self._fs = fact_store
        self._cache = cache_service
        self._download_dir = download_dir

    def is_available(self, ticker: str, report_period: str) -> bool:
        """检查指定公司/报告期是否已在本地。"""
        cache_key = f"cache:report:available:{ticker}:{report_period}"
        if self._cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return bool(cached)

        # 直接查 SQL
        metrics = self._fs.query_metrics_by_company_period(ticker, report_period)
        available = len(metrics) >= 5  # 至少 5 个指标才算有效

        if self._cache:
            self._cache.set(cache_key, available, data_type="report_index", ttl=86400)

        return available

    def mark_available(self, ticker: str, report_period: str):
        """标记公司/报告期已入库。"""
        cache_key = f"cache:report:available:{ticker}:{report_period}"
        if self._cache:
            self._cache.set(cache_key, True, data_type="report_index", ttl=86400)

    def resolve(self, ticker: str, company_name: str,
                report_period: str) -> Dict[str, Any]:
        """
        尝试解析：先查本地 → 未命中时返回 need_fetch 标记。

        Returns:
            {"status": "local_hit" / "need_fetch" / "error",
             "metrics": [...],  # 如果本地命中
             "message": "..."}
        """
        # 1. 查本地
        metrics = self._fs.query_metrics_by_company_period(ticker, report_period)
        if len(metrics) >= 5:
            return {
                "status": "local_hit",
                "metrics": metrics,
                "message": f"{company_name} {report_period} 已在本地 ({len(metrics)} 指标)",
            }

        # 2. 本地不足 → 需要在线获取
        return {
            "status": "need_fetch",
            "ticker": ticker,
            "company_name": company_name,
            "report_period": report_period,
            "message": (f"{company_name} {report_period} 未入库，"
                        f"当前仅 {len(metrics)} 指标。"
                        f"请搜索财报 PDF 并下载到 data/reports/ 后自动入库。"),
        }

    def search_and_ingest(self, ticker: str, company_name: str,
                          report_period: str,
                          pdf_urls: list = None) -> Dict[str, Any]:
        """
        下载并入库：接受 PDF URL 列表，逐个尝试。

        Args:
            pdf_urls: [{"url": "...", "source": "雪球"}, ...]
                      如果为 None，返回 need_urls 状态
        """
        if not pdf_urls:
            return {
                "status": "need_urls",
                "message": f"请提供 {company_name} {report_period} 财报的 PDF 链接",
            }

        from src.sources.fetcher import SourceFetcher
        from src.ingestion.batch_ingestor import BatchIngestor
        import os

        fetcher = SourceFetcher(
            download_dir=self._download_dir,
            cache_service=self._cache,
        )
        ingestor = BatchIngestor(reports_dir=self._download_dir)

        for url_info in pdf_urls:
            url = url_info.get("url", "")
            if not url:
                continue

            # 下载
            result = fetcher.download_report(url, ticker, company_name, report_period)
            if not result.success:
                logger.warning(f"Download failed: {result.error}")
                continue

            # 入库
            fpath = result.file_path
            if not os.path.exists(fpath):
                continue

            # 找到对应的 PDF 信息
            pdfs = ingestor.discover_pdfs()
            target = None
            for p in pdfs:
                if str(p["path"]) == str(fpath):
                    target = p
                    break

            if target and not target.get("already_ingested"):
                ingest_result = ingestor.ingest_one(target)
                self.mark_available(ticker, report_period)
                return {
                    "status": "ingested",
                    "file_path": fpath,
                    "source_url": url,
                    "source_name": result.source_name,
                    "metrics_ingested": ingest_result.get("metrics_ingested", 0),
                    "message": f"成功入库: {ingest_result.get('metrics_ingested', 0)} 指标",
                }

            # 文件存在但未匹配到
            return {
                "status": "downloaded",
                "file_path": fpath,
                "message": f"PDF 已下载到 {fpath}，但未自动入库。请手动运行 batch_ingestor。",
            }

        return {
            "status": "error",
            "message": f"所有 {len(pdf_urls)} 个链接下载失败",
        }
