"""
批量财报入库器 — 扫描 data/reports/ 目录，全自动结构化入库。

文件命名规范: {ticker}_{company_name}_{period}.pdf
  例: 002594_比亚迪_2026Q1.pdf

Usage:
    python -m src.ingestion.batch_ingestor
    python -m src.ingestion.batch_ingestor --input_dir data/reports --period 2026Q1
"""

from __future__ import annotations

import os, sys, re, json, time, logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.storage.fact_store import FactStore
from src.tools.file_processor import FileProcessor
from src.ingestion.report_ingestor import ReportIngestor
from src.router.query_router import QueryRouter

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# 文件名解析正则: {ticker}_{name}_{period}.pdf
_FILENAME_RE = re.compile(r'^(\d{6})_(.+?)_(\d{4}Q[1-4])\.pdf$')


class BatchIngestor:
    """批量财报入库器。"""

    def __init__(self, db_path: str = None, reports_dir: str = None):
        db_path = db_path or str(Path(__file__).parent.parent.parent / "data" / "finintel_factstore.db")
        reports_dir = reports_dir or str(Path(__file__).parent.parent.parent / "data" / "reports")

        self.fs = FactStore(db_path)
        self.fs.init_db()
        self.fs.seed_metric_dictionary()

        self.fp = FileProcessor()
        self.ri = ReportIngestor(self.fs)
        self.reports_dir = Path(reports_dir)

        self.router = QueryRouter()
        self.results: List[dict] = []

    def discover_pdfs(self) -> List[dict]:
        """扫描目录，返回待处理的 PDF 列表。"""
        pdfs = []
        for fpath in sorted(self.reports_dir.glob("*.pdf")):
            m = _FILENAME_RE.match(fpath.name)
            if m:
                ticker, name, period = m.group(1), m.group(2), m.group(3)
            else:
                # 尝试宽松匹配
                ticker, name, period = "000000", fpath.stem, "2026Q1"

            doc_id = self.ri._make_doc_id(ticker, period, str(fpath))

            # 检查是否已入库
            already = self.ri.is_already_ingested(doc_id)
            pdfs.append({
                "path": str(fpath),
                "ticker": ticker,
                "company_name": name,
                "report_period": period,
                "doc_id": doc_id,
                "already_ingested": already,
            })
        return pdfs

    def ingest_one(self, pdf_info: dict) -> dict:
        """入库单个 PDF。"""
        fpath = pdf_info["path"]
        ticker = pdf_info["ticker"]
        name = pdf_info["company_name"]
        period = pdf_info["report_period"]

        if pdf_info["already_ingested"]:
            logger.info(f"Skip {name}: already ingested")
            return {"status": "skipped", "reason": "already_ingested", **pdf_info}

        logger.info(f"Ingesting {name} ({ticker})...")

        try:
            # 注册公司
            self.fs.upsert_company(ticker, name)
            self.router.add_company(ticker, name)

            # FileProcessor: 逐页提取 + 指标
            pages = self.fp._extract_pdf_pages(fpath)
            content = "\n".join(t for _, t in pages)
            metrics, metrics_pages = self.fp._extract_financial_metrics(content, fpath, pages)

            # Chunk for RAG
            chunks = self.fp.chunk_financial(content) if self.fp._is_financial_doc(fpath, content) else self.fp.chunk_text(content)

            # 入库 SQL
            ingest_result = self.ri.ingest(
                file_path=fpath,
                ticker=ticker,
                company_name=name,
                report_period=period,
                raw_metrics=metrics,
                raw_text=content,
                metrics_pages=metrics_pages,
            )

            # 入库 RAG (ChromaDB)
            rag_count = 0
            if ingest_result["success"] > 0:
                try:
                    from src.tools.rag_manager import rag_manager
                    meta = {
                        "ticker": ticker,
                        "company_name": name,
                        "report_period": period,
                        "doc_type": "quarterly_report",
                        "source": "batch_ingestor",
                    }
                    rag_count = rag_manager.add_documents(
                        {"file_path": fpath, "file_type": "pdf", "chunks": chunks},
                        metadata=meta,
                    )
                except Exception as e:
                    logger.warning(f"  RAG skip: {e}")

            result = {
                "status": ingest_result["parse_status"],
                "ticker": ticker,
                "company_name": name,
                "report_period": period,
                "doc_id": ingest_result["doc_id"],
                "metrics_extracted": len(metrics),
                "metrics_ingested": ingest_result["success"],
                "unknown_metrics": ingest_result["unknown"],
                "errors": ingest_result["errors"],
                "chunks_rag": len(chunks),
                "rag_stored": rag_count,
            }
            logger.info(f"  {name}: {result['metrics_ingested']} metrics, {ingest_result['unknown']} unknown")
            return result

        except Exception as e:
            logger.error(f"  {name} FAILED: {e}")
            import traceback
            traceback.print_exc()
            return {"status": "error", "error": str(e), **pdf_info}

    def run(self, input_dir: str = None) -> dict:
        """批量入库主流程。"""
        if input_dir:
            self.reports_dir = Path(input_dir)

        pdfs = self.discover_pdfs()
        if not pdfs:
            logger.warning(f"No PDFs found in {self.reports_dir}")
            return {"total": 0, "results": []}

        total = len(pdfs)
        new_count = sum(1 for p in pdfs if not p["already_ingested"])
        logger.info(f"Found {total} PDFs ({new_count} new, {total - new_count} already ingested)")

        self.results = []
        for i, pdf_info in enumerate(pdfs):
            result = self.ingest_one(pdf_info)
            self.results.append(result)

        return self._summary()

    def _summary(self) -> dict:
        total = len(self.results)
        success = sum(1 for r in self.results if r.get("status") in ("done", "partial"))
        failed = sum(1 for r in self.results if r.get("status") == "error")
        skipped = sum(1 for r in self.results if r.get("status") == "skipped")
        total_metrics = sum(r.get("metrics_ingested", 0) for r in self.results)
        total_unknown = sum(r.get("unknown_metrics", 0) for r in self.results)
        total_errors = sum(r.get("errors", 0) for r in self.results)
        total_chunks = sum(r.get("chunks_rag", 0) for r in self.results)

        return {
            "total": total,
            "success": success,
            "failed": failed,
            "skipped": skipped,
            "total_metrics_ingested": total_metrics,
            "total_unknown_metrics": total_unknown,
            "total_extraction_errors": total_errors,
            "total_rag_chunks": total_chunks,
            "results": self.results,
        }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="批量财报入库")
    parser.add_argument("--input_dir", type=str, default=None,
                        help="财报 PDF 目录 (默认 data/reports/)")
    parser.add_argument("--db", type=str, default=None,
                        help="SQLite 数据库路径 (默认 data/finintel_factstore.db)")
    args = parser.parse_args()

    ingestor = BatchIngestor(
        db_path=args.db,
        reports_dir=args.input_dir,
    )

    summary = ingestor.run()
    print("\n" + "=" * 60)
    print("Batch Ingestion Summary")
    print("=" * 60)
    print(f"  Total PDFs:              {summary['total']}")
    print(f"  Success:                 {summary['success']}")
    print(f"  Failed:                  {summary['failed']}")
    print(f"  Skipped (already done):  {summary['skipped']}")
    print(f"  Total metrics ingested:  {summary['total_metrics_ingested']}")
    print(f"  Unknown metrics:         {summary['total_unknown_metrics']}")
    print(f"  Extraction errors:       {summary['total_extraction_errors']}")
    print(f"  RAG chunks:              {summary['total_rag_chunks']}")

    # 各公司明细
    print(f"\n  Per-company:")
    for r in summary["results"]:
        status_icon = {"done": "✓", "partial": "~", "failed": "✗", "skipped": "⏭", "error": "✗"}.get(r.get("status", ""), "?")
        print(f"    {status_icon} {r.get('company_name','?'):8s} ({r.get('ticker','')}) "
              f"metrics={r.get('metrics_ingested',0)}/{r.get('metrics_extracted',0)} "
              f"unknown={r.get('unknown_metrics',0)} err={r.get('errors',0)} "
              f"chunks={r.get('chunks_rag',0)}")

    print("=" * 60)


if __name__ == "__main__":
    main()
