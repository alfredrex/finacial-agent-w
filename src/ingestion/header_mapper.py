"""
表头映射器

识别财报表格中的列名映射关系，确定哪一列是"本期金额"、哪一列是"上期金额"等。

Usage:
    from src.ingestion.header_mapper import HeaderMapper
    hm = HeaderMapper()
    mapping = hm.map_headers(["项目", "本期金额", "上期金额"])
    # -> {"current": 1, "previous": 2, "header_pattern": "standard_period"}
"""

from __future__ import annotations

import re
import logging
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)

# ─── 列类型 ──────────────────────────────────────────

CURRENT_PERIOD_COL = "current"
PREVIOUS_PERIOD_COL = "previous"
CURRENT_BALANCE_COL = "current_balance"
PREVIOUS_BALANCE_COL = "previous_balance"
YOY_COL = "yoy"              # 同比增减
ITEM_COL = "item"             # 科目名列

# ─── 关键词字典 ─────────────────────────────────────

CURRENT_PERIOD_KEYWORDS = [
    "本期金额", "本期", "本报告期", "本期发生额",
    "本期数", "本季度", "2026年1-3月", "2026年1-3月份",
]

PREVIOUS_PERIOD_KEYWORDS = [
    "上期金额", "上期", "上年同期", "上期发生额",
    "上年同期金额", "上年数", "2025年1-3月", "2025年1-3月份",
    "2024年1-3月", "2024年1-3月份",
]

CURRENT_BALANCE_KEYWORDS = [
    "期末余额", "期末", "本报告期末", "2026年3月31日",
]

PREVIOUS_BALANCE_KEYWORDS = [
    "期初余额", "期初", "上年度末", "年初余额",
    "2025年1月1日", "2025年12月31日", "2024年12月31日",
]

YOY_KEYWORDS = [
    "同比增减", "同比", "增减幅度", "变动比例",
    "增减(%", "变动率", "增减（%", "同比（%",
    "比上年同期增减", "变动幅度",
]

ITEM_KEYWORDS = [
    "项目", "科目", "指标", "",
    "会计科目", "报表项目",
]

# ─── 表格类型推断 ────────────────────────────────────

INCOME_STATEMENT_KEYWORDS = [
    "营业收入", "营业成本", "销售费用", "管理费用", "研发费用",
    "财务费用", "投资收益", "营业利润", "利润总额", "净利润",
    "税金及附加", "资产减值损失", "信用减值损失",
    "其他收益", "公允价值变动", "营业外收入", "营业外支出",
]

BALANCE_SHEET_KEYWORDS = [
    "货币资金", "应收账款", "存货", "固定资产", "无形资产",
    "短期借款", "长期借款", "应付账款", "预收款项",
    "资产总计", "负债合计", "所有者权益",
    "流动资产", "非流动资产", "流动负债", "非流动负债",
    "资产总额", "负债总额",
]

CASH_FLOW_KEYWORDS = [
    "经营活动产生的现金流量", "投资活动产生的现金流量",
    "筹资活动产生的现金流量", "现金及现金等价物",
    "销售商品、提供劳务收到的现金", "购买商品、接受劳务支付的现金",
    "经营活动现金流入", "经营活动现金流出",
    "现金流量净额", "期初现金余额", "期末现金余额",
]


class HeaderMapper:
    """将财报表头映射到标准列名。"""

    def map_headers(self, headers: List[str]) -> Dict[str, int]:
        """返回 {类型: 列索引} 的映射。

        未识别的列不会出现在结果中。
        输入示例: ["项目", "本期金额", "上期金额"]
        输出: {"item": 0, "current": 1, "previous": 2}
        """
        result = {}
        for idx, h in enumerate(headers):
            h_clean = h.strip().replace("\n", " ")
            if not h_clean:
                continue
            col_type = self._classify_header(h_clean)
            if col_type:
                result[col_type] = idx
        return result

    def _classify_header(self, header: str) -> Optional[str]:
        """将单个表头分类。"""
        if not header:
            return None
        # yoy 先检查（因为可能包含"同比增减"但同时也含"上期"前缀）
        for kw in YOY_KEYWORDS:
            if kw in header:
                return YOY_COL
        for kw in CURRENT_PERIOD_KEYWORDS:
            if kw in header:
                return CURRENT_PERIOD_COL
        for kw in PREVIOUS_PERIOD_KEYWORDS:
            if kw in header:
                return PREVIOUS_PERIOD_COL
        for kw in CURRENT_BALANCE_KEYWORDS:
            if kw in header:
                return CURRENT_BALANCE_COL
        for kw in PREVIOUS_BALANCE_KEYWORDS:
            if kw in header:
                return PREVIOUS_BALANCE_COL
        return None

    def infer_statement_type(self, table_text: str) -> Optional[str]:
        """根据表格文本内容推断表格类型。

        Returns: "income" / "balance_sheet" / "cash_flow" / None
        """
        # 按权重计分
        scores = {"income": 0, "balance_sheet": 0, "cash_flow": 0}
        for kw in INCOME_STATEMENT_KEYWORDS:
            if kw in table_text:
                scores["income"] += 1
        for kw in BALANCE_SHEET_KEYWORDS:
            if kw in table_text:
                scores["balance_sheet"] += 1
        for kw in CASH_FLOW_KEYWORDS:
            if kw in table_text:
                scores["cash_flow"] += 1

        best = max(scores, key=scores.get)
        if scores[best] == 0:
            return None
        return best

    def detect_period_from_header(self, headers_str: str) -> Optional[str]:
        """从表头文本中自动检测报告期。

        e.g. "2026年1-3月" → "2026Q1"
             "2025年度" → "2025FY"
        """
        # 季度检测
        q_match = re.search(r'(\d{4})年\s*\d{1,2}\s*[-至]\s*\d{1,2}\s*月', headers_str)
        if q_match:
            year = q_match.group(1)
            if "1-3" in headers_str or "1至3" in headers_str:
                return f"{year}Q1"
            if "4-6" in headers_str or "4至6" in headers_str:
                return f"{year}Q2"
            if "7-9" in headers_str or "7至9" in headers_str:
                return f"{year}Q3"
            # 默认 Q1（1-3月最常见于Q1季报）
            return f"{year}Q1"

        # 年度
        y_match = re.search(r'(\d{4})年度?', headers_str)
        if y_match:
            return f"{y_match.group(1)}FY"

        return None
