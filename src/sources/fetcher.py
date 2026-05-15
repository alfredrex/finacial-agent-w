"""
Source Fetcher — 在线财报/新闻搜索与下载

V3 核心：当本地 SQL miss 时，自动搜索 → 下载 → 入库。

支持:
  - 财报搜索: ticker + "2026年第一季度报告" → 找 PDF → 下载
  - 新闻搜索: company_name + 关键词 → 返回文本
  - 公告搜索: ticker + "公告" → 返回链接

Usage:
    from src.sources.fetcher import SourceFetcher
    sf = SourceFetcher(cache_service, download_dir="data/reports")
    result = await sf.fetch_report("601939", "建设银行", "2026Q1")
    # → {"path": "data/reports/601939_建设银行_2026Q1.pdf", "source_url": "...", ...}
"""

from __future__ import annotations

import os, re, time, hashlib, logging
from pathlib import Path
from typing import Optional, Dict, Any, List, TYPE_CHECKING
from dataclasses import dataclass, field

if TYPE_CHECKING:
    from src.memory.cache_service import CacheService

logger = logging.getLogger(__name__)


@dataclass
class FetchResult:
    """搜索结果。"""
    success: bool
    file_path: str = ""
    source_url: str = ""
    source_name: str = ""
    fetched_at: str = ""
    content_type: str = ""  # "quarterly_report" / "news" / "announcement"
    confidence: float = 0.0
    error: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class SourceFetcher:
    """在线财报/新闻获取器。

    依赖外部工具调用 web_search / web_extract / terminal(curl)。
    这些工具在 Agent 环境中可用，本类封装调用逻辑。
    """

    # 已知的 PDF 源模式
    PDF_SOURCE_PATTERNS = [
        (r"stockmc\.xueqiu\.com/\d+/(\d+)_\d+_\w+\.pdf", "雪球 stockmc"),
        (r"static\.cninfo\.com\.cn/finalpage/[\d\-]+/[\d]+\.PDF", "巨潮资讯"),
        (r"pdf\.dfcfw\.com/pdf/[\w_]+\.pdf", "东方财富"),
        (r"\.petrochina\.com\.cn/.*?\.pdf", "中国石油官网"),
        (r"\.sse\.com\.cn/.*?\.pdf", "上交所"),
    ]

    def __init__(self, download_dir: str = "data/reports",
                 cache_service: CacheService = None):
        self._download_dir = Path(download_dir)
        self._download_dir.mkdir(parents=True, exist_ok=True)
        self._cache = cache_service

    def search_report_urls(self, ticker: str, company_name: str,
                           period: str = "2026Q1") -> List[Dict[str, str]]:
        """搜索财报 PDF 链接。

        Returns:
            [{"url": "...", "source": "雪球 stockmc", "title": "..."}, ...]

        NOTE: 此方法返回候选 URL 列表。实际下载需调用 download_report()。
              在 Agent 环境中，调用方应使用 web_search 工具获取结果，
              然后将 URL 列表传入 download_report()。
        """
        # 此方法在 Agent 工具链中由调用方实现
        # 这里提供接口规范
        return []

    def download_report(self, url: str, ticker: str, company_name: str,
                        period: str = "2026Q1") -> FetchResult:
        """下载并保存财报 PDF。

        Args:
            url:  PDF 直链 URL
            ticker, company_name, period: 用于命名
        """
        fname = f"{ticker}_{company_name}_{period}.pdf"
        fpath = str(self._download_dir / fname)

        # 判断来源
        source_name = "unknown"
        for pattern, name in self.PDF_SOURCE_PATTERNS:
            if re.search(pattern, url):
                source_name = name
                break

        try:
            import requests
            headers = {"User-Agent": "Mozilla/5.0 (compatible; FinIntel/1.0)"}
            r = requests.get(url, timeout=60, stream=True, headers=headers)
            r.raise_for_status()

            content_type = r.headers.get("Content-Type", "")
            if "pdf" not in content_type.lower() and not url.lower().endswith(".pdf"):
                # 验证是否是 PDF
                first_bytes = r.raw.read(1024)
                if b"%PDF" not in first_bytes:
                    return FetchResult(
                        success=False,
                        error=f"URL 不是 PDF: content_type={content_type}",
                        source_url=url, source_name=source_name,
                    )
                # 重新 seek
                import io
                r.raw = io.BytesIO(first_bytes + r.raw.read())

            with open(fpath, "wb") as f:
                for chunk in r.iter_content(8192):
                    f.write(chunk)

            file_size = os.path.getsize(fpath)
            if file_size < 5000:
                os.remove(fpath)
                return FetchResult(
                    success=False, error=f"文件过小 ({file_size} bytes)",
                    source_url=url, source_name=source_name,
                )

            logger.info(f"Downloaded: {fname} ({file_size} bytes) from {source_name}")
            return FetchResult(
                success=True,
                file_path=fpath,
                source_url=url,
                source_name=source_name,
                content_type="quarterly_report",
                confidence=0.9,
                metadata={"file_size": file_size, "ticker": ticker},
            )

        except Exception as e:
            logger.error(f"Download failed: {url} → {e}")
            return FetchResult(
                success=False, error=str(e),
                source_url=url, source_name=source_name,
            )

    def search_news(self, company_name: str, keyword: str = "",
                    max_results: int = 5) -> List[Dict[str, str]]:
        """搜索公司最新新闻（接口规范）。

        NOTE: 实际搜索由 Agent 调用 web_search 工具实现。
        """
        return []

    def get_latest_announcement(self, ticker: str) -> Optional[Dict[str, str]]:
        """获取最新公告（接口规范）。"""
        return None
