"""
联网搜索工具 — 精简版

不依赖 DuckDuckGo。优先用东方财富 API，失败时返回明确提示。
"""

from __future__ import annotations

import re
from typing import List, Dict, Any


def search_financial_data(query: str, max_results: int = 5) -> List[Dict[str, str]]:
    """
    尝试搜索金融数据。
    当前环境不支持直接 HTTPS 搜索，返回空结果。
    部署到有网环境后可用 DuckDuckGo/Bing API。
    """
    return []  # 环境受限，不做不可靠搜索


def extract_financial_metrics(text: str) -> Dict[str, Any]:
    """从文本提取财务指标。"""
    metrics = {}
    for pat, scale in [
        (r'(?:营业[总]?收入|营收|营业额)[^\d]*?([\d,.]+)\s*亿', 1e8),
        (r'(?:营业[总]?收入|营收|营业额)[^\d]*?([\d,.]+)\s*万', 1e4),
    ]:
        m = re.search(pat, text)
        if m:
            try:
                v = float(m.group(1).replace(",", ""))
                metrics["revenue"] = v * scale
            except ValueError:
                pass
            break
    for pat, scale in [
        (r'净利润[^\d]*?([\d,.]+)\s*亿', 1e8),
        (r'净利润[^\d]*?([\d,.]+)\s*万', 1e4),
        (r'净亏损[^\d]*?([\d,.]+)\s*亿', -1e8),
        (r'净亏损[^\d]*?([\d,.]+)\s*万', -1e4),
    ]:
        m = re.search(pat, text)
        if m:
            try:
                v = float(m.group(1).replace(",", ""))
                metrics["net_profit"] = v * scale
            except ValueError:
                pass
            break
    return metrics


def format_search_results(results: list, metrics: dict) -> str:
    """格式化搜索结果为文本。"""
    if not metrics and not results:
        return "（当前环境不支持联网搜索。可尝试：1) 提供股票代码用东方财富API查询 2) 上传财报PDF入库）"
    lines = []
    if metrics:
        for k, v in metrics.items():
            lines.append(f"  {k}: {v}")
    return "\n".join(lines)


def on_demand_search(query: str) -> str:
    """DataAgent 调用入口。"""
    return "（联网搜索暂不可用，请使用 get_financial_data 或上传 PDF）"
