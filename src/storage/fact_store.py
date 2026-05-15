"""
SQLite FactStore — 金融事实数据库核心

面向:
  1. 精确查询 metric_query("002594", "2026Q1", "net_profit_parent")
  2. 多公司对比 compare_companies(["002594","300750"], "2026Q1", "rd_expense")
  3. 时序趋势 timeseries("002594", "revenue", ["2025Q1","2025Q2","2026Q1"])
  4. 排行榜 rank("2026Q1", "revenue", industry="新能源车", limit=5)

Usage:
    from src.storage.fact_store import FactStore
    fs = FactStore("data/finintel_factstore.db")
    fs.init_db()
    fs.seed_metric_dictionary()
    fs.upsert_financial_fact(ticker="002594", report_period="2026Q1", ...)
    result = fs.query_metric("002594", "2026Q1", "net_profit_parent")
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

# ─── Trace Logger ─────────────────────────────────────
from src.tracing import trace_logger

logger = logging.getLogger(__name__)

SCHEMA_PATH = Path(__file__).parent / "schema.sql"

DB_DEFAULTS = {
    "db_path": str(Path(__file__).parent.parent.parent / "data" / "finintel_factstore.db"),
    "timeout": 30,
    "isolation_level": None,
}


class FactStore:
    """SQLite 金融事实存储。"""

    def __init__(self, db_path: Optional[str] = None):
        db_path = db_path or DB_DEFAULTS["db_path"]
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    @contextmanager
    def _get_conn(self):
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, timeout=DB_DEFAULTS["timeout"])
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield self._conn
        except Exception:
            self._conn.rollback()
            raise

    def init_db(self) -> FactStore:
        """初始化表结构。"""
        schema = SCHEMA_PATH.read_text()
        with self._get_conn() as conn:
            conn.executescript(schema)
            conn.commit()
        logger.info(f"FactStore initialized: {self.db_path}")
        return self

    # ─────────────────── company ───────────────────

    def upsert_company(self, ticker: str, company_name: str, **kwargs) -> dict:
        now = _now_iso()
        with self._get_conn() as conn:
            cur = conn.execute("SELECT ticker FROM company WHERE ticker=?", (ticker,))
            exists = cur.fetchone()
            if exists:
                conn.execute("""
                    UPDATE company SET company_name=?, exchange=?, industry=?,
                    sector=?, updated_at=? WHERE ticker=?
                """, (company_name, kwargs.get("exchange"), kwargs.get("industry"),
                      kwargs.get("sector"), now, ticker))
            else:
                conn.execute("""
                    INSERT INTO company (ticker,company_name,exchange,industry,sector,created_at,updated_at)
                    VALUES (?,?,?,?,?,?,?)
                """, (ticker, company_name, kwargs.get("exchange"), kwargs.get("industry"),
                      kwargs.get("sector"), now, now))
            conn.commit()
        return {"ticker": ticker, "company_name": company_name}

    def get_company(self, ticker: str) -> Optional[dict]:
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM company WHERE ticker=?", (ticker,)).fetchone()
        return dict(row) if row else None

    # ─────────────────── report_document ───────────────────

    def upsert_report_document(self, doc_id: str, ticker: str, **kwargs) -> dict:
        now = _now_iso()
        with self._get_conn() as conn:
            cur = conn.execute("SELECT doc_id FROM report_document WHERE doc_id=?", (doc_id,))
            exists = cur.fetchone()
            if exists:
                conn.execute("""
                    UPDATE report_document SET ticker=?,company_name=?,report_period=?,
                    report_type=?,file_path=?,source_url=?,parse_status=?,updated_at=?
                    WHERE doc_id=?
                """, (ticker, kwargs.get("company_name"), kwargs.get("report_period"),
                      kwargs.get("report_type"), kwargs.get("file_path"), kwargs.get("source_url"),
                      kwargs.get("parse_status"), now, doc_id))
            else:
                conn.execute("""
                    INSERT INTO report_document (doc_id,ticker,company_name,report_period,
                    report_type,file_path,source_url,upload_time,parse_status,parser_version,created_at,updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """, (doc_id, ticker, kwargs.get("company_name"), kwargs.get("report_period"),
                      kwargs.get("report_type"), kwargs.get("file_path"), kwargs.get("source_url"),
                      now, kwargs.get("parse_status", "pending"), kwargs.get("parser_version", "1.0"), now, now))
            conn.commit()
        return {"doc_id": doc_id, "ticker": ticker}

    def get_report_document(self, doc_id: str) -> Optional[dict]:
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM report_document WHERE doc_id=?", (doc_id,)).fetchone()
        return dict(row) if row else None

    # ─────────────────── metric_dictionary ───────────────────

    def upsert_metric(self, metric_code: str, standard_name: str, **kwargs) -> dict:
        now = _now_iso()
        aliases = kwargs.get("aliases")
        aliases_str = json.dumps(aliases, ensure_ascii=False) if isinstance(aliases, list) else aliases
        with self._get_conn() as conn:
            cur = conn.execute("SELECT metric_code FROM metric_dictionary WHERE metric_code=?", (metric_code,))
            exists = cur.fetchone()
            if exists:
                conn.execute("""
                    UPDATE metric_dictionary SET standard_name=?,aliases=?,statement_type=?,
                    value_type=?,default_unit=?,description=?,updated_at=?
                    WHERE metric_code=?
                """, (standard_name, aliases_str, kwargs.get("statement_type"),
                      kwargs.get("value_type"), kwargs.get("default_unit"),
                      kwargs.get("description"), now, metric_code))
            else:
                conn.execute("""
                    INSERT INTO metric_dictionary (metric_code,standard_name,aliases,statement_type,
                    value_type,default_unit,description,created_at,updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?)
                """, (metric_code, standard_name, aliases_str, kwargs.get("statement_type"),
                      kwargs.get("value_type"), kwargs.get("default_unit"),
                      kwargs.get("description"), now, now))
            conn.commit()
        return {"metric_code": metric_code}

    def get_metric_def(self, metric_code: str) -> Optional[dict]:
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM metric_dictionary WHERE metric_code=?", (metric_code,)).fetchone()
        if not row:
            return None
        d = dict(row)
        if d.get("aliases"):
            try:
                d["aliases"] = json.loads(d["aliases"])
            except (json.JSONDecodeError, TypeError):
                pass
        return d

    def get_all_mentric_codes(self) -> List[str]:
        with self._get_conn() as conn:
            rows = conn.execute("SELECT metric_code FROM metric_dictionary").fetchall()
        return [r["metric_code"] for r in rows]

    # ─────────────────── financial_fact ───────────────────

    def upsert_financial_fact(self, ticker: str, report_period: str, metric_code: str,
                               value: float, source_doc_id: str, **kwargs) -> dict:
        """
        写入（覆盖）一条财务指标。
        唯一约束: (ticker, report_period, metric_code, source_doc_id)

        Args:
            value: 已归一化为"元"的数值
            unit: 原始单位
            raw_value: 原始值字符串
            source_page: 来源页码
            其余字段见 schema
        """
        now = _now_iso()
        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO financial_fact
                (ticker,company_name,report_period,report_type,statement_type,
                 metric_code,metric_name,raw_metric_name,
                 value,raw_value,unit,currency,scale,
                 source_doc_id,source_page,source_table_name,table_id,row_label,column_label,
                 confidence,extraction_method,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(ticker,report_period,metric_code,source_doc_id) DO UPDATE SET
                  value=excluded.value,
                  raw_value=excluded.raw_value,
                  unit=excluded.unit,
                  source_page=excluded.source_page,
                  confidence=excluded.confidence,
                  updated_at=excluded.updated_at
            """, (
                ticker, kwargs.get("company_name"), report_period, kwargs.get("report_type"),
                kwargs.get("statement_type"), metric_code, kwargs.get("metric_name"),
                kwargs.get("raw_metric_name"),
                value, kwargs.get("raw_value"), kwargs.get("unit"), kwargs.get("currency", "CNY"),
                kwargs.get("scale", 1),
                source_doc_id, kwargs.get("source_page"), kwargs.get("source_table_name"),
                kwargs.get("table_id"), kwargs.get("row_label"), kwargs.get("column_label"),
                kwargs.get("confidence"), kwargs.get("extraction_method", "table_parse"),
                now, now,
            ))
            conn.commit()
        return {"ticker": ticker, "report_period": report_period, "metric_code": metric_code, "value": value}

    def query_metric(self, ticker: str, report_period: str, metric_code: str) -> Optional[dict]:
        """精确查询: 某公司某报告期某个指标。"""
        import time as _time
        _start = _time.monotonic()
        with self._get_conn() as conn:
            row = conn.execute("""
                SELECT * FROM financial_fact
                WHERE ticker=? AND report_period=? AND metric_code=?
                ORDER BY updated_at DESC LIMIT 1
            """, (ticker, report_period, metric_code)).fetchone()
        _lat = (_time.monotonic() - _start) * 1000
        result = dict(row) if row else None
        trace_logger.quick_span(
            "sql:query_metric", latency_ms=_lat,
            input_summary=f"{ticker}/{report_period}/{metric_code}",
            output_summary="hit" if result else "miss",
        )
        return result

    def query_metrics_by_company_period(self, ticker: str, report_period: str,
                                         metric_codes: Optional[List[str]] = None) -> List[dict]:
        """查询某公司某报告期的多个指标（不指定则返回全部）。"""
        with self._get_conn() as conn:
            if metric_codes:
                placeholders = ",".join("?" * len(metric_codes))
                rows = conn.execute(f"""
                    SELECT * FROM financial_fact
                    WHERE ticker=? AND report_period=?
                    AND metric_code IN ({placeholders})
                """, (ticker, report_period, *metric_codes)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT * FROM financial_fact
                    WHERE ticker=? AND report_period=?
                """, (ticker, report_period)).fetchall()
        return [dict(r) for r in rows]

    def query_compare_companies(self, tickers: List[str], report_period: str,
                                  metric_code: str) -> List[dict]:
        """多公司对比: 同一指标在不同公司间的值。"""
        with self._get_conn() as conn:
            placeholders = ",".join("?" * len(tickers))
            rows = conn.execute(f"""
                SELECT ticker, company_name, value, unit, source_doc_id, source_page
                FROM financial_fact
                WHERE ticker IN ({placeholders})
                AND report_period=?
                AND metric_code=?
                ORDER BY value DESC
            """, (*tickers, report_period, metric_code)).fetchall()
        return [dict(r) for r in rows]

    def query_metric_timeseries(self, ticker: str, metric_code: str,
                                  periods: List[str]) -> List[dict]:
        """时序查询: 某公司某个指标在多个报告期的值。"""
        with self._get_conn() as conn:
            placeholders = ",".join("?" * len(periods))
            rows = conn.execute(f"""
                SELECT ticker, company_name, report_period, value, unit, source_doc_id
                FROM financial_fact
                WHERE ticker=?
                AND metric_code=?
                AND report_period IN ({placeholders})
                ORDER BY report_period
            """, (ticker, metric_code, *periods)).fetchall()
        return [dict(r) for r in rows]

    def query_rank(self, report_period: str, metric_code: str,
                    industry: Optional[str] = None, limit: int = 10) -> List[dict]:
        """排行榜: 按指标排名。可选行业筛选。"""
        with self._get_conn() as conn:
            if industry:
                rows = conn.execute("""
                    SELECT f.ticker, f.company_name, f.value, f.unit, f.source_doc_id
                    FROM financial_fact f
                    JOIN company c ON f.ticker = c.ticker
                    WHERE f.report_period=? AND f.metric_code=? AND c.industry=?
                    ORDER BY f.value DESC
                    LIMIT ?
                """, (report_period, metric_code, industry, limit)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT ticker, company_name, value, unit, source_doc_id
                    FROM financial_fact
                    WHERE report_period=? AND metric_code=?
                    ORDER BY value DESC
                    LIMIT ?
                """, (report_period, metric_code, limit)).fetchall()
        return [dict(r) for r in rows]

    # ─────────────────── 派生指标计算 ───────────────────

    # 派生指标定义: {输出metric_code → (公式名, [输入metric_code列表], lambda)}
    _DERIVED_METRICS = None

    def _init_derived_metrics(self):
        if self._DERIVED_METRICS is not None:
            return
        self._DERIVED_METRICS = {
            "gross_margin": {
                "name": "毛利率",
                "formula": "(revenue - cost) / revenue",
                "unit": "%",
                "requires": ["revenue", "operating_cost"],
                "compute": lambda rev, cost: ((rev - cost) / rev * 100) if rev else None,
            },
            "net_margin": {
                "name": "净利率",
                "formula": "net_profit / revenue",
                "unit": "%",
                "requires": ["revenue", "net_profit"],
                "compute": lambda rev, np: (np / rev * 100) if rev else None,
            },
            "asset_liability_ratio": {
                "name": "资产负债率",
                "formula": "total_liabilities / total_assets",
                "unit": "%",
                "requires": ["total_assets", "total_liabilities"],
                "compute": lambda ta, tl: (tl / ta * 100) if ta else None,
            },
            "op_cf_to_np_ratio": {
                "name": "经营现金流/净利润",
                "formula": "operating_cash_flow / net_profit",
                "unit": "倍",
                "requires": ["net_profit", "operating_cash_flow"],
                "compute": lambda np, ocf: (ocf / np) if np and np != 0 else None,
            },
        }

    def compute_derived_metrics(self, ticker: str, report_period: str) -> List[dict]:
        """从已有基础指标计算派生指标（毛利率/净利率/资产负债率等）。

        Returns:
            [{"metric_code": "gross_margin", "metric_name": "毛利率",
              "value": 18.8, "unit": "%", "formula": "(revenue - cost) / revenue"}, ...]
        """
        self._init_derived_metrics()
        results = []

        for mc, meta in self._DERIVED_METRICS.items():
            # 检查是否已有直接记录
            existing = self.query_metric(ticker, report_period, mc)
            if existing:
                results.append({
                    "metric_code": mc,
                    "metric_name": meta["name"],
                    "value": existing["value"],
                    "unit": existing.get("unit", meta["unit"]),
                    "source": "sql_direct",
                    "formula": meta["formula"],
                    "source_doc_id": existing.get("source_doc_id", ""),
                    "source_page": existing.get("source_page"),
                })
                continue

            # 计算派生值
            inputs = {}
            for req_mc in meta["requires"]:
                row = self.query_metric(ticker, report_period, req_mc)
                if row:
                    inputs[req_mc] = row["value"]
                else:
                    break  # 缺少输入，跳过

            if len(inputs) == len(meta["requires"]):
                try:
                    val = meta["compute"](*[inputs[r] for r in meta["requires"]])
                    if val is not None:
                        results.append({
                            "metric_code": mc,
                            "metric_name": meta["name"],
                            "value": round(val, 4),
                            "unit": meta["unit"],
                            "source": "computed",
                            "formula": meta["formula"],
                            "source_doc_id": "",
                            "source_page": None,
                        })
                except (ZeroDivisionError, TypeError):
                    pass

        return results

    # ─────────────────── unknown_metric + extraction_error ───────────────────

    def insert_unknown_metric(self, ticker: str, report_period: str,
                                raw_metric_name: str, raw_value: str,
                                source_doc_id: str, **kwargs) -> int:
        now = _now_iso()
        with self._get_conn() as conn:
            cur = conn.execute("""
                INSERT INTO unknown_metric (ticker,company_name,report_period,source_doc_id,
                source_page,source_table_name,raw_metric_name,raw_value,context_text,
                suggested_metric_code,confidence,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (ticker, kwargs.get("company_name"), report_period, source_doc_id,
                  kwargs.get("source_page"), kwargs.get("source_table_name"),
                  raw_metric_name, raw_value, kwargs.get("context_text"),
                  kwargs.get("suggested_metric_code"), kwargs.get("confidence"), now, now))
            conn.commit()
            return cur.lastrowid

    def insert_extraction_error(self, doc_id: str, error_type: str,
                                  message: str, **kwargs) -> int:
        now = _now_iso()
        with self._get_conn() as conn:
            cur = conn.execute("""
                INSERT INTO extraction_error (doc_id,ticker,report_period,page,table_id,
                error_type,raw_text,message,created_at)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (doc_id, kwargs.get("ticker"), kwargs.get("report_period"),
                  kwargs.get("page"), kwargs.get("table_id"),
                  error_type, kwargs.get("raw_text"), message, now))
            conn.commit()
            return cur.lastrowid

    # ─────────────────── ingestion_job ───────────────────

    def start_ingestion_job(self, job_id: str, input_path: str, job_type: str = "batch") -> dict:
        now = _now_iso()
        with self._get_conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO ingestion_job
                (job_id,input_path,job_type,status,started_at,total_docs,success_docs,failed_docs)
                VALUES (?,?,?,'running',?,0,0,0)
            """, (job_id, input_path, job_type, now))
            conn.commit()
        return {"job_id": job_id, "status": "running"}

    def finish_ingestion_job(self, job_id: str, status: str = "done",
                               total: int = 0, success: int = 0, failed: int = 0,
                               error_message: Optional[str] = None) -> dict:
        now = _now_iso()
        with self._get_conn() as conn:
            conn.execute("""
                UPDATE ingestion_job SET status=?,finished_at=?,
                total_docs=?,success_docs=?,failed_docs=?,error_message=?
                WHERE job_id=?
            """, (status, now, total, success, failed, error_message, job_id))
            conn.commit()
        return {"job_id": job_id, "status": status}

    # ─────────────────── seed data ───────────────────

    def seed_metric_dictionary(self) -> int:
        """初始化 20 个核心指标。如果已存在则跳过。"""
        metrics = [
            ("revenue", "营业收入",
             ["营业收入", "营业总收入", "一、营业总收入", "一、营业收入", "主营业务收入"],
             "income", "amount", "元", "企业主营业务收入和其他业务收入之和"),
            ("operating_cost", "营业成本",
             ["营业成本", "一、营业成本", "cost"],
             "income", "amount", "元", "与营业收入直接相关的成本"),
            ("total_cost", "营业总成本",
             ["营业总成本", "total_cost"],
             "income", "amount", "元", "营业总成本"),
            ("gross_profit", "毛利润",
             ["毛利润", "毛利"],
             "income", "amount", "元", "营业收入 - 营业成本"),
            ("gross_margin", "毛利率",
             ["毛利率"],
             "income", "ratio", "%", "毛利润 / 营业收入 × 100%"),
            ("net_profit", "净利润",
             ["净利润", "净利润（净亏损以\"-\"号填列）", "net_profit"],
             "income", "amount", "元", "归属于公司所有者的净利润"),
            ("net_profit_parent", "归母净利润",
             ["归属于上市公司股东的净利润", "归属于母公司所有者的净利润",
              "归属于母公司股东的净利润", "归母净利润", "net_profit_parent"],
             "income", "amount", "元", "归属于母公司股东的净利润"),
            ("net_profit_deducted", "扣非归母净利润",
             ["归属于上市公司股东的扣除非经常性损益的净利润",
              "扣除非经常性损益后归属于母公司股东的净利润", "扣非净利润",
              "net_profit_dedup"],
             "income", "amount", "元", "扣除非经常性损益后的归母净利润"),
            ("operating_cash_flow", "经营活动现金流净额",
             ["经营活动产生的现金流量净额", "经营活动现金流净额",
              "经营活动现金净流量", "oper_cf"],
             "cash_flow", "amount", "元", "经营活动现金流入 - 经营活动现金流出"),
            ("investing_cash_flow", "投资活动现金流净额",
             ["投资活动产生的现金流量净额", "投资活动现金流净额", "invest_cf"],
             "cash_flow", "amount", "元", "投资活动现金流入 - 投资活动现金流出"),
            ("financing_cash_flow", "筹资活动现金流净额",
             ["筹资活动产生的现金流量净额", "筹资活动现金流净额", "fin_cf"],
             "cash_flow", "amount", "元", "筹资活动现金流入 - 筹资活动现金流出"),
            ("total_assets", "总资产",
             ["资产总计", "资产总额", "总资产", "total_assets"],
             "balance_sheet", "amount", "元", "资产负债表中的资产总计"),
            ("total_liabilities", "总负债",
             ["负债合计", "负债总额", "总负债", "total_liability"],
             "balance_sheet", "amount", "元", "资产负债表中的负债合计"),
            ("equity_parent", "归母权益",
             ["归属于母公司所有者权益合计", "归母所有者权益",
              "所有者权益合计", "股东权益合计", "net_assets"],
             "balance_sheet", "amount", "元", "归属于母公司的所有者权益"),
            ("asset_liability_ratio", "资产负债率",
             ["资产负债率"],
             "balance_sheet", "ratio", "%", "总负债 / 总资产 × 100%"),
            ("eps_basic", "基本每股收益",
             ["基本每股收益", "eps"],
             "income", "per_share", "元/股", "净利润 / 总股本"),
            ("eps_diluted", "稀释每股收益",
             ["稀释每股收益", "eps_diluted"],
             "income", "per_share", "元/股", "考虑稀释效应后的每股收益"),
            ("roe_weighted", "加权平均ROE",
             ["加权平均净资产收益率", "加权平均ROE", "roe"],
             "income", "ratio", "%", "加权平均净资产收益率"),
            ("rd_expense", "研发费用",
             ["研发费用", "研究开发费", "研发投入", "rd_expense"],
             "income", "amount", "元", "企业研发支出"),
            ("selling_expense", "销售费用",
             ["销售费用", "营业费用", "sell_expense"],
             "income", "amount", "元", "销售相关费用"),
            ("management_expense", "管理费用",
             ["管理费用", "admin_expense"],
             "income", "amount", "元", "管理相关费用"),
            ("financial_expense", "财务费用",
             ["财务费用", "fin_expense"],
             "income", "amount", "元", "利息支出等财务相关费用"),
            ("inventory", "存货",
             ["存货", "存货净额"],
             "balance_sheet", "amount", "元", "存货账面价值"),
            ("accounts_receivable", "应收账款",
             ["应收账款", "应收票据及应收账款", "应收账款净额", "receivables"],
             "balance_sheet", "amount", "元", "应收款项"),
            ("short_term_loans", "短期借款",
             ["短期借款", "short_loan"],
             "balance_sheet", "amount", "元", "短期借款"),
            ("long_term_loans", "长期借款",
             ["长期借款", "长期借款合计", "long_loan"],
             "balance_sheet", "amount", "元", "长期借款"),
            ("tax_surcharge", "税金及附加",
             ["税金及附加", "营业税金及附加"],
             "income", "amount", "元", "主营业务税金及附加"),
            ("invest_income", "投资收益",
             ["投资收益", "投资净收益", "invest_income"],
             "income", "amount", "元", "投资活动产生的收益"),
            ("operating_profit", "营业利润",
             ["营业利润", "营业利润（亏损以\"-\"号填列）", "oper_profit"],
             "income", "amount", "元", "营业收入 - 营业成本 - 各项费用"),
            ("total_profit", "利润总额",
             ["利润总额", "利润总额（亏损总额以\"-\"号填列）", "total_profit"],
             "income", "amount", "元", "营业利润 + 营业外收入 - 营业外支出"),
            ("cash_equivalents", "现金及等价物",
             ["货币资金", "现金及现金等价物", "现金", "cash"],
             "balance_sheet", "amount", "元", "货币资金余额"),
            ("fixed_assets", "固定资产",
             ["固定资产", "固定资产净值", "fixed_assets"],
             "balance_sheet", "amount", "元", "固定资产净值"),
        ]

        count = 0
        with self._get_conn() as conn:
            existing = {r["metric_code"] for r in conn.execute(
                "SELECT metric_code FROM metric_dictionary").fetchall()}

            for (code, name, aliases, stmt, vtype, unit, desc) in metrics:
                if code in existing:
                    continue
                conn.execute("""
                    INSERT INTO metric_dictionary
                    (metric_code,standard_name,aliases,statement_type,value_type,default_unit,description,created_at,updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?)
                """, (code, name, json.dumps(aliases, ensure_ascii=False), stmt, vtype, unit, desc,
                      _now_iso(), _now_iso()))
                count += 1
            conn.commit()
        logger.info(f"Seeded {count} new metric definitions (total {len(metrics)} defined)")
        return count


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
