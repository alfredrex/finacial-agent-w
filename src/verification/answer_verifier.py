"""
Answer Verifier — 轻量答案验证器

检查 QAAgent 输出的答案是否符合 V1 规范:
  1. 精确指标类答案必须带: 公司, 报告期, 指标, 数值, 单位
  2. 如果有 source_page，必须带来源页码
  3. 数字来源必须是 SQL，不能是 RAG 猜测
  4. 最新类问题必须带更新时间
  5. 缓存数据检查新鲜度

Usage:
    from src.verification.answer_verifier import AnswerVerifier
    verifier = AnswerVerifier()
    result = verifier.verify(answer_text, query_plan, collected_data)
    # {"verified": True/False, "warnings": [...], "score": 0.85}
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
import re


@dataclass
class VerificationResult:
    verified: bool
    score: float = 0.0           # 0.0～1.0
    warnings: List[str] = field(default_factory=list)
    passes: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)


class AnswerVerifier:
    """验证答案是否满足 V1 规范。"""

    def verify(self,
               answer: str,
               query_plan: Optional[Dict[str, Any]] = None,
               collected_data: Optional[List[Dict]] = None,
               ) -> VerificationResult:
        """
        Args:
            answer: QAAgent 输出的最终答案文本
            query_plan: Query Router 输出的 plan dict
            collected_data: MemoryAgent/DataAgent 收集的数据

        Returns:
            VerificationResult with score and warnings
        """
        warnings = []
        passes = []
        score = 1.0

        if not answer:
            return VerificationResult(verified=False, score=0.0,
                                      warnings=["答案为空"])

        # ── 1. 财务数字来源检查 ──
        has_number = bool(re.search(r'[\d,]+(?:\.\d+)?\s*[万亿]?[元%倍股]', answer))
        if has_number:
            # 如果有数字，检查是否来自 SQL
            if query_plan:
                qtype = query_plan.get("query_type", "")
                is_metric = qtype in ("metric_query", "calculation_query", "comparison_query")
                if is_metric:
                    if collected_data:
                        sql_sources = [d for d in collected_data
                                       if d.get("data_source", "").startswith("sql_factstore")]
                        if sql_sources:
                            passes.append("数字来源为 SQL FactStore")
                        else:
                            score -= 0.3
                            warnings.append("答案中包含财务数字，但未找到对应 SQL 来源")
                    else:
                        score -= 0.1
                        warnings.append("答案含数字但无可验证的 collected_data")
            else:
                score -= 0.05
                warnings.append("答案含数字但无 query_plan 可验证")

        # ── 2. 单位和报告期检查 ──
        if query_plan and query_plan.get("report_period"):
            period = query_plan["report_period"]
            if period in answer or self._period_in_text(period, answer):
                passes.append(f"报告期正确: {period}")
            else:
                score -= 0.15
                warnings.append(f"缺少报告期 ({period})")

        if query_plan and query_plan.get("expected_unit"):
            unit = query_plan["expected_unit"]
            if unit in answer:
                passes.append(f"单位正确: {unit}")
            else:
                score -= 0.05
                warnings.append(f"可能缺少单位 ({unit})")

        # ── 3. 公司名检查 ──
        if query_plan and query_plan.get("company_name"):
            company = query_plan["company_name"]
            if company in answer:
                passes.append(f"公司名正确: {company}")
            else:
                score -= 0.1
                warnings.append(f"缺少公司名 ({company})")

        # ── 4. 来源页码检查 ──
        if collected_data:
            for d in collected_data:
                sp = d.get("source_page")
                if sp and str(sp) in answer:
                    passes.append(f"含来源页码: 第{sp}页")
                    break
            else:
                # 不是必须的（V1 不强求页码出现在答案中）
                pass

        # ── 5. 最新类问题新鲜度检查 ──
        if query_plan and query_plan.get("freshness_requirement") == "latest":
            time_words = ["今天", "最新", "刚刚", "实时", "当前",
                          r'\d{4}年\d{1,2}月\d{1,2}日',
                          r'\d{2}:\d{2}']
            has_time = any(re.search(w, answer) for w in time_words)
            if has_time:
                passes.append("含时间标注")
            else:
                score -= 0.1
                warnings.append("最新类问题缺少更新时间")

        # ── 6. 缓存过期检查 ──
        for d in (collected_data or []):
            if d.get("data_source") == "kv_cache" and d.get("cache_expired"):
                score -= 0.2
                warnings.append("缓存数据已过期")

        # ── 最终判定 ──
        verified = score >= 0.6
        result = VerificationResult(
            verified=verified,
            score=max(0.0, min(1.0, score)),
            warnings=warnings,
            passes=passes,
            details={
                "answer_length": len(answer),
                "has_numbers": has_number,
                "query_type": query_plan.get("query_type") if query_plan else "unknown",
                "sql_sources_count": sum(1 for d in (collected_data or [])
                                         if d.get("data_source", "").startswith("sql")),
            },
        )
        return result

    def _period_in_text(self, period: str, text: str) -> bool:
        """宽松的报告期匹配。 "2026Q1" → 匹配 "2026Q1" 或 "2026年第一季" 或 "2026年一季度" """
        m = re.match(r'(\d{4})Q(\d)', period)
        if m:
            year, q = m.group(1), m.group(2)
            q_map = {"1": "一|1", "2": "二|2", "3": "三|3", "4": "四|4"}
            return bool(re.search(fr'{year}.*?第?[{q_map[q]}]季', text))
        return period in text

    def verify_all(self,
                    answers: List[Dict[str, Any]],
                    ) -> List[VerificationResult]:
        """批量验证多条答案。"""
        results = []
        for item in answers:
            result = self.verify(
                answer=item.get("answer", ""),
                query_plan=item.get("query_plan"),
                collected_data=item.get("collected_data"),
            )
            results.append(result)
        return results

    def summary(self, results: List[VerificationResult]) -> Dict[str, Any]:
        """生成批量验证摘要。"""
        total = len(results)
        if total == 0:
            return {"total": 0}
        verified = sum(1 for r in results if r.verified)
        avg_score = sum(r.score for r in results) / total
        all_warnings = []
        for r in results:
            all_warnings.extend(r.warnings)
        return {
            "total": total,
            "verified": verified,
            "failed": total - verified,
            "pass_rate": verified / total if total else 0,
            "avg_score": round(avg_score, 3),
            "common_warnings": _top_warnings(all_warnings, 5),
        }


def _top_warnings(warnings: List[str], n: int = 5) -> List[Dict[str, Any]]:
    from collections import Counter
    counts = Counter(warnings)
    return [{"warning": w, "count": c} for w, c in counts.most_common(n)]
