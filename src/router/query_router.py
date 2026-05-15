"""
Query Router — 规则型路由器

将用户自然语言问题解析为 QueryPlan，决定应调用哪些数据源。

核心原则:
  - 数字是多少 → SQL
  - 为什么/原因 → RAG
  - 最新/今天 → Web/API
  - 我的偏好 → KVStore
  - 对比/排名 → SQL

规则优先，规则不够时才走 LLM fallback (V2)。

Usage:
    from src.router.query_router import QueryRouter
    router = QueryRouter(known_companies={"002594": "比亚迪", ...})
    plan = router.route("比亚迪2026Q1净利润是多少")
    # -> QueryPlan(type=metric_query, ticker="002594", metrics=["net_profit_parent"], needs_sql=True)
"""

from __future__ import annotations

import re
import logging
from typing import Optional, List, Dict, Tuple

from .query_schema import QueryPlan, QueryType

logger = logging.getLogger(__name__)


# ─── 关键词规则 ─────────────────────────────────────

# 精确指标类关键词 → metric_query
METRIC_KEYWORDS = [
    "是多少", "多少", "为多少", "是多大",
    # 指标名称也在 company_metric_map 映射中检测
]

# 特殊指标关键词（直接匹配到 metric_code）
SPECIFIC_METRIC_PATTERNS: list[Tuple[str, str]] = [
    ("营业收入", "revenue"),
    ("营业总收入", "revenue"),
    ("营业成本", "operating_cost"),
    ("营业总成本", "total_cost"),
    ("毛利润", "gross_profit"),
    ("毛利率", "gross_margin"),
    ("净利润", "net_profit"),
    ("归母净利润", "net_profit_parent"),
    ("扣非净利润", "net_profit_deducted"),
    ("扣非归母净利润", "net_profit_deducted"),
    ("经营活动现金流", "operating_cash_flow"),
    ("经营现金流", "operating_cash_flow"),
    ("投资活动现金流", "investing_cash_flow"),
    ("筹资活动现金流", "financing_cash_flow"),
    ("总资产", "total_assets"),
    ("资产总计", "total_assets"),
    ("总负债", "total_liabilities"),
    ("负债合计", "total_liabilities"),
    ("资产负债率", "asset_liability_ratio"),
    ("所有者权益", "equity_parent"),
    ("归母权益", "equity_parent"),
    ("基本每股收益", "eps_basic"),
    ("每股收益", "eps_basic"),
    ("稀释每股收益", "eps_diluted"),
    ("roe", "roe_weighted"),
    ("净资产收益率", "roe_weighted"),
    ("研发费用", "rd_expense"),
    ("研发投入", "rd_expense"),
    ("销售费用", "selling_expense"),
    ("管理费用", "management_expense"),
    ("财务费用", "financial_expense"),
    ("存货", "inventory"),
    ("应收账款", "accounts_receivable"),
    ("短期借款", "short_term_loans"),
    ("长期借款", "long_term_loans"),
    ("税金及附加", "tax_surcharge"),
    ("投资收益", "invest_income"),
    ("营业利润", "operating_profit"),
    ("利润总额", "total_profit"),
    ("货币资金", "cash_equivalents"),
    ("现金", "cash_equivalents"),
    ("固定资产", "fixed_assets"),
]

# 纯比率指标（无直接存储值，必须派生计算）
CALCULATION_ONLY_METRICS = {
    "gross_margin", "net_margin", "asset_liability_ratio",
    "op_cf_to_np_ratio",
}

# 比率指标关键词 → 触发 calculation_query
CALCULATION_METRIC_KEYWORDS = [
    "毛利率", "净利率", "资产负债率", "研发费用率",
]

# 计算/比率类
CALCULATION_KEYWORDS = [
    "净利率", "率是多少", "占.*比例", "比值",
    "同比增长", "同比", "环比", "约等于多少亿",
]

# 对比类
COMPARISON_KEYWORDS = [
    "对比", "相比", "谁更高", "谁更低", "排名", "最高", "最低",
    "前十", "前五", "前3", "top", "哪家", "哪个公司",
    "差异", "差别", "之间",
    "趋势", "近几个季度", "近几个报告期",
    "找出", "筛选",
]

# 解释类
EXPLANATION_KEYWORDS = [
    "为什么", "原因", "如何解释", "影响", "怎么看",
    "管理层", "券商", "观点", "行业逻辑", "产业链",
    "风险", "对策", "意味着什么", "说明什么",
    "变化可能", "可能说明", "如何分析", "因素", "导致",
]

# 最新类
LATEST_KEYWORDS = [
    "最新", "今天", "最近", "刚刚", "新闻",
    "公告", "股价", "行情", "涨跌", "实时",
    "现在", "当前", "今天",
]

# 用户偏好类
USER_PREFERENCE_KEYWORDS = [
    "我的偏好", "我关注的", "适合我吗", "根据我的风格",
    "我的持仓", "我的关注", "我的投资", "我是",
    "我的风险", "适合我",
]

# 报告类
REPORT_KEYWORDS = [
    "生成报告", "投研报告", "分析报告", "给我写",
    "帮我写", "出报告",
]


class QueryRouter:
    """规则型查询路由器。"""

    def __init__(self, known_companies: Optional[Dict[str, str]] = None):
        """
        Args:
            known_companies: {ticker: company_name} 已知公司映射
        """
        self._companies = known_companies or {}
        # 反向映射: company_name → ticker
        self._name_to_ticker: Dict[str, str] = {}
        for ticker, name in self._companies.items():
            self._name_to_ticker[name] = ticker
            # 短名也映射
            short = re.sub(r'[（(].*?[）)]', '', name).strip()
            if short != name:
                self._name_to_ticker[short] = ticker

    def add_company(self, ticker: str, company_name: str):
        self._companies[ticker] = company_name
        self._name_to_ticker[company_name] = ticker
        short = re.sub(r'[（(].*?[）)]', '', company_name).strip()
        if short != company_name:
            self._name_to_ticker[short] = ticker

    def route(self, query: str, report_period: Optional[str] = None) -> QueryPlan:
        """分析用户问题并生成查询计划。"""
        plan = QueryPlan(original_query=query)

        # ── 提取实体/报告期/指标 ──
        plan = self._extract_entities(query, plan)
        if not plan.report_period:
            plan.report_period = report_period or self._extract_period(query)
        plan.metrics = self._extract_metrics(query)

        # ── 判断查询类型 ──
        plan = self._classify(query, plan)

        # ── V4: 填入数据源优先级链 ──
        from .query_schema import SOURCE_PRIORITY
        plan.data_source_priority = SOURCE_PRIORITY.get(
            plan.query_type, ["web", "api", "sql", "rag"]
        )

        return plan

    def _extract_entities(self, query: str, plan: QueryPlan) -> QueryPlan:
        """从查询中提取公司名和 ticker。"""
        # 直接匹配 ticker
        ticker_match = re.search(r'\b(\d{6})\b', query)
        if ticker_match:
            ticker = ticker_match.group(1)
            plan.ticker = ticker
            if ticker in self._companies:
                plan.company_name = self._companies[ticker]
            return plan

        # 匹配公司名
        for name, ticker in sorted(self._name_to_ticker.items(),
                                    key=lambda x: -len(x[0])):  # 长名优先
            if name in query:
                plan.ticker = ticker
                plan.company_name = name
                return plan

        return plan

    def _extract_period(self, query: str) -> Optional[str]:
        """从查询中提取报告期。"""
        # 2026Q1 / 2026年Q1
        m = re.search(r'(\d{4})\s*年?\s*Q([1-4])', query)
        if m:
            return f"{m.group(1)}Q{m.group(2)}"

        # 2026年第一季度
        for q_num, q_str in [("1", "一|1"), ("2", "二|2"), ("3", "三|3"), ("4", "四|4")]:
            if re.search(fr'第[{q_str}]季', query):
                m = re.search(r'(\d{4})', query)
                if m:
                    return f"{m.group(1)}Q{q_num}"

        # 2026年半年报
        if "半年报" in query or "上半年" in query:
            m = re.search(r'(\d{4})', query)
            if m:
                return f"{m.group(1)}H1"

        # 2026年报/2026年度
        if "年报" in query or "年度" in query:
            m = re.search(r'(\d{4})', query)
            if m:
                return f"{m.group(1)}FY"

        return None

    def _extract_metrics(self, query: str) -> List[str]:
        """从查询中提取指标名并映射到 metric_code。"""
        found = []
        for pattern, code in SPECIFIC_METRIC_PATTERNS:
            if pattern in query:
                found.append(code)
        return list(dict.fromkeys(found))  # 去重保序

    def _classify(self, query: str, plan: QueryPlan) -> QueryPlan:
        """根据查询内容判断 query_type 并设置数据源标志。"""
        q = query

        # 检查是否命中用户偏好关键词
        if any(kw in q for kw in USER_PREFERENCE_KEYWORDS):
            plan.query_type = QueryType.USER_MEMORY
            plan.needs_kv = True
            plan.needs_sql = bool(plan.ticker)
            plan.needs_rag = bool(plan.ticker)
            plan.reason = "用户偏好/画像类问题，走 KVStore"
            return plan

        # 检查是否命中报告类关键词
        if any(kw in q for kw in REPORT_KEYWORDS):
            plan.query_type = QueryType.REPORT_GENERATION
            plan.needs_sql = True
            plan.needs_rag = True
            plan.needs_kv = True
            plan.reason = "报告生成类问题，组合所有数据源"
            return plan

        # 检查是否命中对比/排行类关键词
        if any(kw in q for kw in COMPARISON_KEYWORDS):
            plan.query_type = QueryType.COMPARISON_QUERY
            plan.is_comparison = True
            plan.needs_sql = True
            # 有解释需求才加 RAG
            if any(kw in q for kw in EXPLANATION_KEYWORDS):
                plan.needs_rag = True
            plan.reason = "对比/排行/排序类问题，走 SQL FactStore"
            return plan

        # 检查是否命中解释类关键词（在指标匹配之前，因为像"净利润变化的原因"包含指标词但应走RAG）
        has_metric = bool(plan.metrics)
        has_metric_keyword = any(kw in q for kw in METRIC_KEYWORDS)
        has_calculation = any(re.search(kw, q) for kw in CALCULATION_KEYWORDS)
        is_explanation = any(kw in q for kw in EXPLANATION_KEYWORDS)

        # 最新类 — 最高优先级（"最新"+指标词应走web，而非sql）
        if any(kw in q for kw in LATEST_KEYWORDS):
            plan.query_type = QueryType.LATEST_NEWS
            plan.needs_web = True
            plan.needs_kv = True  # cache
            plan.freshness_requirement = "latest"
            # 如果是"最新股价"→实时行情
            if any(w in q for w in ["股价", "行情", "涨跌", "涨幅", "跌幅"]):
                plan.query_type = QueryType.REALTIME_QUOTE
                plan.reason = "实时行情类问题，走 Web/API"
            else:
                plan.reason = "最新信息类问题，走 Web/API + KV cache"
            return plan

        # 解释类 + 有指标 → hybrid_analysis
        if is_explanation and has_metric:
            plan.query_type = QueryType.HYBRID_ANALYSIS
            plan.needs_sql = True
            plan.needs_rag = True
            plan.needs_kv = True
            plan.reason = "解释类问题，需要结构化指标+文本分析"
            return plan

        # 纯解释类（无具体指标） → document_query
        if is_explanation and not has_metric:
            plan.query_type = QueryType.DOCUMENT_QUERY
            plan.needs_rag = True
            plan.needs_sql = has_metric  # 有多家公司或指标涉及
            plan.reason = "解释/分析类问题，主走 RAG"
            return plan

        # 计算/比率类 — 在指标提取之后、精确指标之前判断
        # "净利率"这类词本身就是比率指标，但可能在指标词典中不在，需要特殊处理
        if has_calculation:
            plan.query_type = QueryType.CALCULATION_QUERY
            plan.needs_sql = True
            plan.reason = "计算/比率类问题，走 SQL FactStore"
            return plan

        # 精确指标类 → metric_query
        if has_metric or has_metric_keyword:
            plan.query_type = QueryType.METRIC_QUERY
            plan.needs_sql = True
            plan.reason = "精确财报指标类问题，走 SQL FactStore"
            return plan

        # 有公司名但无指标 → 可能是综合查询
        if plan.ticker and plan.company_name:
            plan.query_type = QueryType.HYBRID_ANALYSIS
            plan.needs_sql = True
            plan.needs_rag = True
            plan.needs_kv = True
            plan.reason = "综合类问题，组合多个数据源"
            return plan

        # 回退到未知
        plan.query_type = QueryType.UNKNOWN
        plan.confidence = 0.3
        plan.reason = "未识别的查询类型"
        return plan
