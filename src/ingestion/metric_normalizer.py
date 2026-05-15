"""
指标名称归一化器

从原始的中文指标名（若干种变体）映射到标准 metric_code。

Usage:
    from src.ingestion.metric_normalizer import MetricNormalizer
    mn = MetricNormalizer(fact_store)
    mn.build_alias_index()
    code = mn.normalize("归属于上市公司股东的净利润")  # -> "net_profit_parent"
"""

from __future__ import annotations

import logging
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.storage.fact_store import FactStore

logger = logging.getLogger(__name__)


class MetricNormalizer:
    """将原始指标名映射到 metric_code。

    构建策略:
      1. 先从 metric_dictionary 加载所有 alias → code 映射。
      2. 精确匹配优先。
      3. 去除中文标点后再匹配（"一、营业总收入" → "营业总收入"）。
      4. 仍不匹配的返回 None，由上游写入 unknown_metric。
    """

    def __init__(self, fact_store: FactStore):
        self._fs = fact_store
        self._alias_to_code: dict[str, str] = {}
        self._built = False

    def build_alias_index(self) -> dict[str, str]:
        """从数据库 metric_dictionary 构建 alias → code 索引。"""
        if self._built:
            return self._alias_to_code

        try:
            with self._fs._get_conn() as conn:
                rows = conn.execute(
                    "SELECT metric_code, aliases FROM metric_dictionary"
                ).fetchall()
        except AttributeError:
            # 如果没有活跃连接，直接走 FactStore 的方法
            codes = self._fs.get_all_mentric_codes()
            for code in codes:
                md = self._fs.get_metric_def(code)
                if md and md.get("aliases"):
                    for alias in md["aliases"]:
                        self._alias_to_code[_clean(alias)] = code
            self._built = True
            logger.info(f"Alias index built: {len(self._alias_to_code)} aliases → "
                        f"{len(set(self._alias_to_code.values()))} metrics")
            return self._alias_to_code

        for row in rows:
            code = row["metric_code"]
            aliases_str = row["aliases"]
            if not aliases_str:
                continue
            import json
            try:
                aliases = json.loads(aliases_str)
            except (json.JSONDecodeError, TypeError):
                continue
            for alias in aliases:
                self._alias_to_code[_clean(alias)] = code

        self._built = True
        logger.info(f"Alias index built: {len(self._alias_to_code)} aliases → "
                     f"{len(set(self._alias_to_code.values()))} metrics")
        return self._alias_to_code

    def normalize(self, raw_name: str) -> Optional[str]:
        """将原始指标名映射到 metric_code。未识别返回 None。"""
        if not raw_name:
            return None
        key = _clean(raw_name)
        if not key:
            return None
        self.build_alias_index()
        # 1. 阿里别查
        if key in self._alias_to_code:
            return self._alias_to_code[key]
        # 2. 直接是 metric_code 本身
        if self._fs.get_metric_def(key):
            return key
        # 3. 原始名称（未清洗）尝试
        if raw_name != key and raw_name in self._alias_to_code:
            return self._alias_to_code[raw_name]
        return None


def _clean(text: str) -> str:
    """去除中文标点、空白、数字序号前缀（'一、' '1.' 等）。"""
    import re
    # 去除首部序号: "一、" "1." "(一)" 等
    cleaned = re.sub(r'^[（(]?\s*[一二三四五六七八九十\d]+[）).、]\s*', '', text)
    # 先去括号内容 (括号是半结构化边界，先干掉内容再清标点)
    cleaned = re.sub(r'[（(]\s*[^)）]*?[）)]', '', cleaned)
    # 去除常见中文标点 (但不含中英文括号，上面已处理)
    cleaned = re.sub(r'[，。、；：\u201c\u201d\u2018\u2019\u300c\u300d《》【】\s]', '', cleaned)
    # 去除中英文引号残留
    renamed = re.sub(r'["\u201c\u201d\u300c\u300d]', '', cleaned)
    return renamed.strip()
