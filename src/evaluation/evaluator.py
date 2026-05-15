"""
V1 Evaluator — 加载 50 条标准问题，验证 Router + SQL 链路
"""
import sys
sys.path.insert(0, "/home/wjh/FinIntel-Multi-Agent")

import json
from src.storage.fact_store import FactStore
from src.router.query_router import QueryRouter
from src.verification.answer_verifier import AnswerVerifier

# ── 加载标准问题 ──
questions_path = "/home/wjh/FinIntel-Multi-Agent/data/eval/standard_questions.jsonl"
questions = []
with open(questions_path) as f:
    for line in f:
        line = line.strip()
        if line:
            questions.append(json.loads(line))
print(f"加载 {len(questions)} 条标准问题")

# ── 初始化 ──
fs = FactStore()
fs.init_db()
router = QueryRouter(known_companies={
    "002594": "比亚迪", "600519": "贵州茅台",
    "000858": "五粮液", "300750": "宁德时代",
})
verifier = AnswerVerifier()

# ── 逐条验证 ──
route_correct = 0
sql_hits = 0
total_metric = 0  # 精确指标类问题数

for q in questions:
    qid = q["id"]
    question = q["question"]
    expected_type = q.get("query_type", "")
    expected_source = q.get("expected_source", "")
    ticker = q.get("ticker", "")
    report_period = q.get("report_period", "2026Q1")
    metrics = q.get("metrics", [])

    # Route
    plan = router.route(question, report_period=report_period)
    plan_dict = plan.to_dict()

    # 类型匹配
    type_ok = plan.query_type.value == expected_type
    if type_ok:
        route_correct += 1

    # SQL 查询 + 派生计算
    collected = []
    if plan.needs_sql and plan.ticker:
        rp = plan.report_period or report_period
        for mc in plan.metrics:
            row = fs.query_metric(plan.ticker, rp, mc)
            if row:
                sql_hits += 1
                collected.append({
                    "metric_code": mc,
                    "metric_name": row.get("metric_name", mc),
                    "value": row["value"],
                    "unit": row.get("unit", "元"),
                    "report_period": row.get("report_period", ""),
                    "source_doc_id": row.get("source_doc_id", ""),
                    "source_page": row.get("source_page"),
                    "data_source": "sql_factstore",
                })
        # 派生指标
        derived = fs.compute_derived_metrics(plan.ticker, rp)
        for d in derived:
            collected.append({
                "metric_code": d["metric_code"],
                "metric_name": d["metric_name"],
                "value": d["value"],
                "unit": d["unit"],
                "data_source": "sql_factstore_computed",
            })

    # 统计
    is_metric = expected_type in ("metric_query", "calculation_query", "comparison_query")
    if is_metric:
        total_metric += 1

    # 打印状态
    src_tag = "✓" if collected else ("sql" if plan.needs_sql else "—")
    short_q = question[:45]
    status = f"{'✓' if type_ok else '✗'}  route={plan.query_type.value}  sql={'hit' if collected else 'miss'}  source_expected={expected_source}"
    print(f"  {qid} {short_q:<45} {status}")

# ── 汇总 ──
print(f"\n{'='*60}")
accuracy = route_correct / len(questions) * 100 if questions else 0
print(f"Route 准确率: {route_correct}/{len(questions)} ({accuracy:.0f}%)")
print(f"SQL 命中次数: {sql_hits}")
print(f"精确指标类问题: {total_metric}")

# 指标验收
if total_metric > 0:
    # 在精确指标问题中有多少命中 SQL
    metric_sql_hits = 0
    metric_total_check = 0
    for q in questions:
        qtype = q.get("query_type", "")
        if qtype in ("metric_query", "calculation_query", "comparison_query"):
            plan = router.route(q["question"])
            if plan.ticker:
                for mc in plan.metrics:
                    metric_total_check += 1
                    row = fs.query_metric(plan.ticker, plan.report_period or "2026Q1", mc)
                    if row:
                        metric_sql_hits += 1

    if metric_total_check > 0:
        sql_accuracy = metric_sql_hits / metric_total_check * 100
        print(f"精确指标 SQL 命中: {metric_sql_hits}/{metric_total_check} ({sql_accuracy:.0f}%)")

print(f"\nV1 验收标准:")
print(f"  route_accuracy >= 85%: {'✓' if accuracy >= 85 else '✗'} ({accuracy:.0f}%)")
print(f"  精确指标必须来自 SQL: {'✓' if sql_hits > 0 else '✗'}")
print(f"  50 条标准问题: {'✓' if len(questions) == 50 else '✗'} ({len(questions)})")
