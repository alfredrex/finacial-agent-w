"""
财报 PDF 结构化入库器

将 file_processor 解析出的财务指标写入 SQLite FactStore。

Pipeline:
  原始 PDF 文本 + 已提取的 metrics
    → unit_normalizer (数值去千分位、括号负数、单位转换)
    → metric_normalizer (原始名 → metric_code)
    → FactStore.upsert_financial_fact()
    → unknown_metric / extraction_error

Usage:
    from src.ingestion.report_ingestor import ReportIngestor
    ri = ReportIngestor(fact_store)
    result = ri.ingest(
        file_path="data/byp_2026_1.pdf",
        ticker="002594",
        company_name="比亚迪",
        report_period="2026Q1",
        raw_metrics=extracted_metrics,
    )
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from src.storage.fact_store import FactStore

from .metric_normalizer import MetricNormalizer
from .unit_normalizer import UnitNormalizer
from .header_mapper import HeaderMapper

logger = logging.getLogger(__name__)


class ReportIngestor:
    """将单份财报 PDF 的解析结果写入 SQLite。"""

    def __init__(self, fact_store: FactStore):
        self._fs = fact_store
        self._normalizer = MetricNormalizer(fact_store)
        self._units = UnitNormalizer()
        self._headers = HeaderMapper()

    def ingest(self,
               file_path: str,
               ticker: str,
               company_name: str,
               report_period: str,
               raw_metrics: Dict[str, Any],
               report_type: str = "quarterly_report",
               raw_text: str = "",
               metrics_pages: Optional[Dict[str, int]] = None,
               ) -> dict:
        """
        入库单份财报。

        raw_metrics 格式（来自 file_processor._extract_financial_metrics）:
            {"revenue": "150225314000.00", "net_profit": 4084551000.00, ...}

        metrics_pages 格式（来自 file_processor）:
            {"revenue": 3, "net_profit": 4, ...}

        Returns:
            {"doc_id": str, "ticker": str, "success": int, "unknown": int, "errors": int}
        """
        doc_id = self._make_doc_id(ticker, report_period, file_path)
        metrics_pages = metrics_pages or {}

        # 1. 写入 report_document
        self._fs.upsert_report_document(
            doc_id=doc_id,
            ticker=ticker,
            company_name=company_name,
            report_period=report_period,
            report_type=report_type,
            file_path=file_path,
            parse_status="pending",
        )

        # 2. 确保 metric_dictionary 已初始化
        self._fs.seed_metric_dictionary()

        # 3. 归一化 + 写入
        success = 0
        unknown = 0
        errors = 0

        for metric_name, metric_data in raw_metrics.items():
            try:
                # 统一数据格式
                if isinstance(metric_data, dict):
                    raw_val = str(metric_data.get("raw_value", str(metric_data.get("value", ""))))
                    value = metric_data.get("value")
                    unit = metric_data.get("unit", "元")
                else:
                    raw_val = str(metric_data)
                    value = metric_data
                    unit = "元"

                if value is None or raw_val in (None, "", "None"):
                    continue

                # 检查 value 是否可以转为浮点数
                try:
                    value_f = float(value)
                except (ValueError, TypeError):
                    errors += 1
                    self._fs.insert_extraction_error(
                        doc_id=doc_id,
                        ticker=ticker,
                        report_period=report_period,
                        error_type="invalid_value",
                        message=f"无法转换为数值: metric={metric_name}, value={value}",
                        raw_text=raw_val,
                    )
                    continue

                # 如果 unit 不是标准单位，尝试文本中检测
                resolved_unit = unit
                if resolved_unit == "元" and raw_text:
                    detected = self._units.detect_unit(raw_text)
                    if detected:
                        resolved_unit = detected

                # 归一化
                normed = self._units.normalize(raw_val, resolved_unit)
                value_in_yuan = normed["value"]

                # 获取来源页码
                source_page = metrics_pages.get(metric_name)

                # 指标名 → metric_code
                metric_code = self._normalizer.normalize(metric_name)
                if not metric_code:
                    # 尝试直接用英文 key（可能是 file_processor 已经做了映射）
                    metric_def = self._fs.get_metric_def(metric_name)
                    if metric_def:
                        metric_code = metric_name
                    else:
                        # 写入 unknown_metric (带丰富上下文)
                        self._fs.insert_unknown_metric(
                            ticker=ticker,
                            company_name=company_name,
                            report_period=report_period,
                            raw_metric_name=metric_name,
                            raw_value=raw_val,
                            source_doc_id=doc_id,
                            source_page=source_page,
                            confidence=0.5,
                            context_text=(raw_text[:200] if raw_text else ""),
                        )
                        unknown += 1
                        continue

                # 获取标准名
                metric_def = self._fs.get_metric_def(metric_code)
                standard_name = metric_def["standard_name"] if metric_def else metric_name
                statement_type = metric_def.get("statement_type", "") if metric_def else ""

                # 写入 financial_fact
                self._fs.upsert_financial_fact(
                    ticker=ticker,
                    company_name=company_name,
                    report_period=report_period,
                    report_type=report_type,
                    statement_type=statement_type,
                    metric_code=metric_code,
                    metric_name=standard_name,
                    raw_metric_name=metric_name,
                    value=value_in_yuan,
                    raw_value=raw_val,
                    unit=resolved_unit,
                    scale=normed["scale"],
                    source_doc_id=doc_id,
                    source_page=source_page,
                    extraction_method="table_parse",
                    confidence=0.85,
                )
                success += 1

            except Exception as e:
                errors += 1
                logger.error(f"Error ingesting metric {metric_name}: {e}")
                self._fs.insert_extraction_error(
                    doc_id=doc_id,
                    ticker=ticker,
                    report_period=report_period,
                    error_type="ingestion_error",
                    message=f"{type(e).__name__}: {e}",
                    raw_text=raw_val,
                )

        # 4. 更新 parse_status
        parse_status = "done"
        if errors > 0 and success == 0:
            parse_status = "failed"
        elif unknown > 0 or errors > 0:
            parse_status = "partial"

        self._fs.upsert_report_document(
            doc_id=doc_id,
            ticker=ticker,
            parse_status=parse_status,
        )

        result = {
            "doc_id": doc_id,
            "ticker": ticker,
            "report_period": report_period,
            "parse_status": parse_status,
            "success": success,
            "unknown": unknown,
            "errors": errors,
        }
        logger.info(f"Report ingested: {result}")
        return result

    def _make_doc_id(self, ticker: str, report_period: str, file_path: str) -> str:
        """生成稳定的文档ID: ticker + report_period + 文件哈希前8位。"""
        path = Path(file_path)
        file_hash = hashlib.md5(path.name.encode()).hexdigest()[:8]
        return f"{ticker}_{report_period}_{file_hash}"

    def is_already_ingested(self, doc_id: str) -> bool:
        """检查文档是否已入库且状态正常。"""
        doc = self._fs.get_report_document(doc_id)
        return doc is not None and doc.get("parse_status") in ("done", "partial")
