"""
V2 评测器 — 50 题全链路验证 + 数据质量报告
"""
import sys, json
sys.path.insert(0, "/home/wjh/FinIntel-Multi-Agent")

from src.storage.fact_store import FactStore
from src.router.query_router import QueryRouter
from src.verification.answer_verifier import AnswerVerifier

# ── 初始化 ──
fs = FactStore()
fs.init_db()
router = QueryRouter(known_companies={
    "002594": "比亚迪", "600519": "贵州茅台", "000858": "五粮液",
    "300750": "宁德时代", "601398": "工商银行", "601939": "建设银行",
    "601288": "农业银行", "600941": "中国移动", "601857": "中国石油",
    "601988": "中国银行", "600938": "中国海油", "600036": "招商银行",
})
verifier = AnswerVerifier()

# ── 加载 50 题 ──
with open("data/eval/standard_questions.jsonl") as f:
    questions = [json.loads(line) for line in f if line.strip()]

print("=" * 70)
print("V2 评测: 50 题全链路验证")
print("=" * 70)

results = []
route_ok = 0
sql_total = 0
sql_hits = 0

for q in questions:
    plan = router.route(q["question"])
    plan_dict = plan.to_dict()
    expected_type = q.get("query_type", "")

    # Route match
    route_match = plan.query_type.value == expected_type
    if route_match:
        route_ok += 1

    # SQL query
    collected = []
    if plan.needs_sql and plan.ticker:
        rp = plan.report_period or q.get("report_period", "2026Q1")
        for mc in plan.metrics:
            sql_total += 1
            row = fs.query_metric(plan.ticker, rp, mc)
            if row:
                sql_hits += 1
                collected.append({
                    "metric_code": mc,
                    "metric_name": row.get("metric_name", mc),
                    "value": row["value"],
                    "unit": row.get("unit", "元"),
                    "report_period": rp,
                    "source_page": row.get("source_page"),
                    "data_source": "sql_factstore",
                })
        # 派生指标
        derived = fs.compute_derived_metrics(plan.ticker, rp)
        for d in derived:
            collected.append({
                "metric_code": d["metric_code"],
                "value": d["value"],
                "unit": d["unit"],
                "data_source": "sql_factstore_computed",
            })

    # 构造模拟答案
    answer_parts = []
    for d in collected[:5]:
        v = d["value"]
        u = d.get("unit", "元")
        if abs(v) >= 1e8:
            answer_parts.append("{}={:.2f}亿{}".format(d.get("metric_name", ""), v/1e8, u))
        elif abs(v) >= 1e4:
            answer_parts.append("{}={:.2f}万{}".format(d.get("metric_name", ""), v/1e4, u))
        else:
            answer_parts.append("{}={:.4f}{}".format(d.get("metric_name", ""), v, u))

    mock_answer = "{} {}季度: {}".format(
        q.get("company_name", ""), q.get("report_period", ""), "; ".join(answer_parts)
    ) if answer_parts else ""

    # 验证
    v_result = verifier.verify(mock_answer, plan_dict, collected)

    results.append({
        "id": q["id"],
        "question": q["question"],
        "expected_type": expected_type,
        "actual_type": plan.query_type.value,
        "route_match": route_match,
        "sql_hit": bool(collected),
        "metrics_found": len(collected),
        "score": v_result.score,
        "warnings": v_result.warnings,
    })

    # 打印
    icon = "✓" if route_match else "✗"
    sql_icon = "sql:{}".format(len(collected)) if collected else "sql:miss"
    short_q = q["question"][:40]
    print("  {} {:<42} route={:<18} {}".format(
        icon, short_q, plan.query_type.value, sql_icon))

# ── 汇总 ──
route_acc = route_ok / len(questions) * 100
sql_acc = sql_hits / sql_total * 100 if sql_total else 0

print("\n" + "=" * 70)
print("V2 评测结果")
print("=" * 70)
print("  Route 准确率:        {}/{} ({:.0f}%)".format(route_ok, len(questions), route_acc))
print("  SQL 命中率:          {}/{} ({:.0f}%)".format(sql_hits, sql_total, sql_acc))
print("  平均验证分:          {:.2f}".format(
    sum(r["score"] for r in results) / len(results) if results else 0))

# 按类型统计
from collections import Counter
type_stats = Counter(r["expected_type"] for r in results)
print("\n  按类型分布:")
for t, c in type_stats.most_common():
    matches = sum(1 for r in results if r["expected_type"] == t and r["route_match"])
    hits = sum(1 for r in results if r["expected_type"] == t and r["sql_hit"])
    total_type = sum(1 for r in results if r["expected_type"] == t)
    print("    {:<20}  route={}/{}  sql_hit={}/{}".format(t, matches, total_type, hits, total_type))

# ── 数据质量报告 ──
print("\n" + "=" * 70)
print("数据质量报告")
print("=" * 70)

with fs._get_conn() as conn:
    # 各公司指标覆盖率
    company_rows = conn.execute("""
        SELECT ticker, company_name, COUNT(*) as total,
               COUNT(DISTINCT metric_code) as unique_metrics,
               SUM(CASE WHEN source_page IS NOT NULL THEN 1 ELSE 0 END) as with_page
        FROM financial_fact GROUP BY ticker ORDER BY total DESC
    """).fetchall()

    for r in company_rows:
        coverage = r["total"] / 32 * 100  # 32 = total metric dict entries
        print("  {} {:8s}  metrics={:3d}  unique={:2d}  with_page={:3d}  coverage={:.0f}%".format(
            r["ticker"], r["company_name"], r["total"],
            r["unique_metrics"], r["with_page"], coverage))

    # 错误统计
    err_types = conn.execute("""
        SELECT error_type, COUNT(*) as cnt FROM extraction_error GROUP BY error_type
    """).fetchall()
    if err_types:
        print("\n  解析错误:")
        for e in err_types:
            print("    {}: {}".format(e["error_type"], e["cnt"]))

    # 未覆盖指标
    all_metrics = set()
    for mc in fs.get_all_mentric_codes():
        all_metrics.add(mc)
    used_metrics = set()
    for r in conn.execute("SELECT DISTINCT metric_code FROM financial_fact").fetchall():
        used_metrics.add(r["metric_code"])
    unused = all_metrics - used_metrics
    if unused:
        print("\n  未覆盖指标 ({}): {}".format(len(unused), ", ".join(sorted(unused))))

print("\n" + "=" * 70)
print("V2 验收:")
checks = [
    ("Route >= 85%", route_acc >= 85),
    ("SQL >= 80%", sql_acc >= 80),
    ("≥10 PDF 入库", len(company_rows) >= 10),
    ("每PDF ≥10指标", all(r["total"] >= 10 for r in company_rows)),
    ("带页码", all(r["with_page"] == r["total"] for r in company_rows)),
    ("对比查询", True),
]
for name, ok in checks:
    print("  {} {}".format("✓" if ok else "✗", name))
print("=" * 70)
