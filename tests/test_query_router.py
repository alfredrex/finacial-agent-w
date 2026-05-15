"""
Query Router 验收测试 — 50条标准问题
"""
import sys
sys.path.insert(0, "/home/wjh/FinIntel-Multi-Agent")

from src.router.query_router import QueryRouter
from src.router.query_schema import QueryType

# 初始化 Router
router = QueryRouter(known_companies={
    "002594": "比亚迪",
    "600519": "贵州茅台",
    "000858": "五粮液",
    "300750": "宁德时代",
})

# ─── 测试问题集 ───
tests = [
    # A. 精确财报指标类 (预期: metric_query → SQL)
    ("比亚迪2026Q1营业收入是多少？", QueryType.METRIC_QUERY, True, False, False),
    ("比亚迪2026Q1净利润是多少？", QueryType.METRIC_QUERY, True, False, False),
    ("比亚迪2026Q1归母净利润是多少？", QueryType.METRIC_QUERY, True, False, False),
    ("比亚迪2026Q1财务费用是多少？", QueryType.METRIC_QUERY, True, False, False),
    ("比亚迪2026Q1经营活动现金流净额是多少？", QueryType.METRIC_QUERY, True, False, False),
    ("比亚迪2026Q1总资产是多少？", QueryType.METRIC_QUERY, True, False, False),
    ("比亚迪2026Q1总负债是多少？", QueryType.METRIC_QUERY, True, False, False),
    ("比亚迪2026Q1研发费用是多少？", QueryType.METRIC_QUERY, True, False, False),
    ("比亚迪2026Q1销售费用是多少？", QueryType.METRIC_QUERY, True, False, False),
    ("比亚迪2026Q1基本每股收益是多少？", QueryType.METRIC_QUERY, True, False, False),

    # B. 同比/环比/计算类 (预期: calculation_query → SQL)
    ("比亚迪2026Q1营业收入同比增长多少？", QueryType.CALCULATION_QUERY, True, False, False),
    ("比亚迪2026Q1净利率是多少？", QueryType.CALCULATION_QUERY, True, False, False),
    ("比亚迪2026Q1资产负债率是多少？", QueryType.CALCULATION_QUERY, True, False, False),
    ("比亚迪2026Q1毛利率是多少？", QueryType.CALCULATION_QUERY, True, False, False),
    ("比亚迪2026Q1财务费用占营业收入比例是多少？", QueryType.CALCULATION_QUERY, True, False, False),

    # C. 多公司对比类 (预期: comparison_query → SQL)
    ("对比比亚迪和贵州茅台2026Q1的营业收入", QueryType.COMPARISON_QUERY, True, False, False),
    ("哪家公司2026Q1研发费用更高", QueryType.COMPARISON_QUERY, True, False, False),
    ("找出2026Q1营业收入最高的5家", QueryType.COMPARISON_QUERY, True, False, False),
    ("对比比亚迪近几个季度的营业收入趋势", QueryType.COMPARISON_QUERY, True, False, False),

    # D. 财报解释和风险类 (预期: document_query 或 hybrid_analysis)
    ("比亚迪2026Q1净利润变化的原因是什么？", QueryType.HYBRID_ANALYSIS, True, True, False),
    ("比亚迪2026Q1管理层讨论了哪些经营重点？", QueryType.DOCUMENT_QUERY, False, True, False),
    ("为什么净利润增长不一定代表现金流也变好？", QueryType.HYBRID_ANALYSIS, True, True, False),
    ("财务费用增加通常有哪些原因？", QueryType.HYBRID_ANALYSIS, True, True, False),

    # E. 最新信息类 (预期: latest_news → Web/API + KV)
    ("比亚迪今天股价是多少？", QueryType.REALTIME_QUOTE, False, False, True),
    ("比亚迪最近有什么新闻？", QueryType.LATEST_NEWS, False, False, True),
    ("比亚迪最近有没有新的公告？", QueryType.LATEST_NEWS, False, False, True),
    ("最近新能源汽车行业有什么重要政策？", QueryType.LATEST_NEWS, False, False, True),

    # F. 用户偏好类（提到具体公司时应组合金融数据）
    ("我的持仓适合买入比亚迪吗？", QueryType.USER_MEMORY, True, True, False),
    ("根据我的风格分析比亚迪", QueryType.USER_MEMORY, True, True, False),

    # G. 报告类
    ("生成比亚迪投研报告", QueryType.REPORT_GENERATION, True, True, False),
]

# ─── 运行测试 ───
passed = 0
failed = 0

print(f"{'问题':<40} {'预期':<20} {'实际':<20} {'结果'}")
print("="*100)

for query, expected_type, expected_sql, expected_rag, expected_web in tests:
    plan = router.route(query)

    # 检查 type
    type_ok = plan.query_type == expected_type
    # 检查数据源标记
    sql_ok = plan.needs_sql == expected_sql
    rag_ok = plan.needs_rag == expected_rag
    web_ok = plan.needs_web == expected_web

    ok = type_ok and sql_ok and rag_ok and web_ok

    if ok:
        passed += 1
        status = "✓"
    else:
        failed += 1
        status = "✗"
        errors = []
        if not type_ok:
            errors.append(f"type={plan.query_type.value}≠{expected_type.value}")
        if not sql_ok:
            errors.append(f"sql={plan.needs_sql}≠{expected_sql}")
        if not rag_ok:
            errors.append(f"rag={plan.needs_rag}≠{expected_rag}")
        if not web_ok:
            errors.append(f"web={plan.needs_web}≠{expected_web}")
        status += " " + " ".join(errors)

    short_query = query[:38]
    print(f"{short_query:<40} {expected_type.value:<20} {plan.query_type.value:<20} {status}")

accuracy = passed / len(tests) * 100 if tests else 0
print(f"\n{'='*100}")
print(f"结果: {passed}/{len(tests)} 通过 ({accuracy:.0f}%)")
if failed > 0:
    print(f"失败: {failed} 条")

# ─── 补充：验证不得错误的场景 ───
print(f"\n关键检查:")
# metric_query 不得走纯 RAG
for q, _, _, _, _ in tests:
    plan = router.route(q)
    if plan.query_type == QueryType.METRIC_QUERY and plan.needs_rag and not plan.needs_sql:
        print(f"  ✗ metric_query 错误走了纯RAG: {q}")
        break
else:
    print(f"  ✓ metric_query 未走纯RAG")

# latest_news 不得只查本地旧知识
for q, _, _, _, _ in tests:
    plan = router.route(q)
    if plan.query_type in (QueryType.LATEST_NEWS, QueryType.REALTIME_QUOTE):
        if not plan.needs_web:
            print(f"  ✗ latest_news 未走web: {q}")
            break
else:
    print(f"  ✓ latest_news 走了web")

# 报告类必须组合多源
for q, _, _, _, _ in tests:
    plan = router.route(q)
    if plan.query_type == QueryType.REPORT_GENERATION:
        if not (plan.needs_sql and plan.needs_rag):
            print(f"  ✗ report 未组合多源: {q}")
            break
else:
    print(f"  ✓ report 组合了多源")
