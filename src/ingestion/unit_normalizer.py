"""
单位归一化器

将财报中的"元""万元""亿元"等统一转换为"元"数值。

Usage:
    from src.ingestion.unit_normalizer import UnitNormalizer
    un = UnitNormalizer()
    result = un.normalize("1,502,253.14", "万元")
    # -> {"value": 15022531400.0, "raw_value": "1,502,253.14", "unit": "万元", "scale": 10000}
"""

from __future__ import annotations

import re
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


# 单位 → 相对于"元"的倍率
UNIT_SCALE = {
    "元":    1,
    "千元":  1_000,
    "万元":  10_000,
    "百万元": 1_000_000,
    "亿元":  100_000_000,
    "十亿元": 1_000_000_000,
    # 比率类
    "%":     1,       # 百分比存原始值，不乘100
    "bps":   0.0001,  # 基点
    # 每股
    "元/股": 1,
    "元每股": 1,

    # 英文
    "CNY":   1,
    "RMB":   1,
    "yuan":  1,
}


# 单位关键词匹配（用于从文本中检测单位）
_UNIT_DETECT_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'单位[：:]\s*([万亿千百十亿百万万千]?元[/每股]*|%)'), "explicit"),
    (re.compile(r'（单位[：:]\s*([万亿千百十亿百万万千]?元[/每股]*|%)）'), "explicit"),
    (re.compile(r'\b(亿元|万元|千元|百万元|元)\b'), "inline"),
]


class UnitNormalizer:
    """将财报原始值归一化为标准"元"值。"""

    def normalize(self, raw_value: str, unit: Optional[str] = None) -> dict:
        """
        Args:
            raw_value: 原始数值字符串, e.g. "1,502,253.14"
            unit: 单位, e.g. "万元". 如果为None则推测。

        Returns:
            {"value": float, "raw_value": str, "unit": str, "scale": int}
        """
        scale = 1
        resolved_unit = unit or "元"

        if unit:
            resolved_unit = unit.strip()
            scale = self._get_scale(resolved_unit)

        # 解析数值（去千分位逗号、中文数字）
        parsed = self._parse_number(raw_value)
        if parsed is None:
            return {
                "value": 0.0,
                "raw_value": raw_value,
                "unit": resolved_unit,
                "scale": scale,
                "error": f"无法解析数值: {raw_value}",
            }

        value = parsed * scale
        return {
            "value": value,
            "raw_value": raw_value,
            "unit": resolved_unit,
            "scale": scale,
        }

    def detect_unit(self, text: str) -> Optional[str]:
        """从文本中检测单位声明。"""
        for pattern, _ in _UNIT_DETECT_PATTERNS:
            m = pattern.search(text)
            if m:
                unit = m.group(1)
                return unit
        return None

    def _get_scale(self, unit: str) -> int:
        """获取单位相对于'元'的倍率。"""
        unit_clean = unit.strip().rstrip("。;.,")
        return UNIT_SCALE.get(unit_clean, 1)

    def _parse_number(self, raw: str) -> Optional[float]:
        """解析数字字符串（支持千分位逗号、括号负数、中文单位后缀）。"""
        if not raw or not raw.strip():
            return None

        s = raw.strip()

        # 括号负数: (123.45) → -123.45
        negative = False
        if s.startswith("(") and s.endswith(")"):
            negative = True
            s = s[1:-1]
        elif s.startswith("（") and s.endswith("）"):
            negative = True
            s = s[1:-1]
        elif s.startswith("-"):
            negative = True
            s = s[1:]

        # 去除中文单位后缀和备注
        s = re.sub(r'[万亿千百十亿百万万千]?元', '', s)
        s = re.sub(r'%$', '', s)
        # 去除千分位逗号
        s = s.replace(",", "")
        s = s.strip()

        try:
            val = float(s)
        except ValueError:
            logger.warning(f"Cannot parse number: {raw!r}")
            return None

        return -val if negative else val
