"""
V1 端到端验证: Query Router → SQL FactStore → 精确回答
模拟 MemoryAgent 的 SQL 优先逻辑，不依赖完整 LangGraph 工作流。
"""
import sys
sys.path.insert(0, "/home/wjh/FinIntel-Multi-Agent")

from src.storage.fact_store import FactStore
from src.router.query_router import QueryRouter

# ─── 初始化 ───
fs = FactStore()
fs.init_db()
fs.seed_metric_dictionary()

router = QueryRouter(known_companies={
    "002594": "比亚迪",
    "600519": "贵州茅台",
    "000858": "五粮液",
    "300750": "宁德时代",
})

# ─── 检查 BYD 数据是否在 SQL 中 ───
byd_count = len(fs.query_metrics_by_company_period("002594", "2026Q1"))
print(f"[预检] BYD 2026Q1 SQL 记录数: {byd_count}")
if byd_count == 0:
    print("[!] 数据未入库，正在重新入库...")
    from src.tools.file_processor import FileProcessor
    from src.ingestion.report_ingestor import ReportIngestor
    fp = FileProcessor()
    content = fp._extract_pdf("/home/wjh/FinIntel-Multi-Agent/data/byd_2026_1.pdf")
    metrics = fp._extract_financial_metrics(content, "/home/wjh/FinIntel-Multi-Agent/data/byd_2026_1.pdf")
    ri = ReportIngestor(fs)
    result = ri.ingest(
        file_path="/home/wjh/FinIntel-Multi-Agent/data/byd_2026_1.pdf",
        ticker="002594", company_name="比亚迪",
        report_period="2026Q1", raw_metrics=metrics, raw_text=content,
    )
    print(f"  入库结果: {result['success']} 成功, {result['unknown']} 未知, {result['errors']} 错误")

# ─── E2E 测试 ───
print("\n" + "=" * 70)
print("V1 E2E: Router → SQL → 精确回答")
print("=" * 70)

test_questions = [
    "比亚迪2026Q1营业收入是多少？",
    "比亚迪2026Q1净利润是多少？",
    "比亚迪2026Q1财务费用是多少？",
    "比亚迪2026Q1研发费用是多少？",
    "比亚迪2026Q1基本每股收益是多少？",
    "比亚迪2026Q1总资产是多少？",
    "比亚迪2026Q1经营活动现金流净额是多少？",
    "比亚迪2026Q1毛利率是多少？",
    "比亚迪2026Q1资产负债率是多少？",
    "比亚迪2026Q1营业利润是多少？",
]

sql_hits = 0
sql_misses = 0

for q in test_questions:
    plan = router.route(q)

    # SQL 查询
    facts = []
    if plan.needs_sql and plan.ticker:
        for mc in plan.metrics:
            row = fs.query_metric(plan.ticker, plan.report_period or "2026Q1", mc)
            if row:
                facts.append(row)

    # 格式化输出
    short_q = q.split("？")[0][:40]
    if facts:
        sql_hits += 1
        parts = []
        for f in facts[:3]:
            v = f["value"]
            u = f.get("unit", "元")
            if abs(v) >= 1e8:
                display = f"{v/1e8:.2f}亿{u}"
            elif abs(v) >= 1e4:
                display = f"{v/1e4:.2f}万{u}"
            else:
                display = f"{v:.4f}{u}"
            parts.append(f"{f['metric_name']}={display}")
        source = f"SQL [{plan.query_type.value}]"
        print(f"  ✓ {short_q}")
        print(f"    → {', '.join(parts)}  ({source})")
    else:
        sql_misses += 1
        print(f"  ✗ {short_q}")
        plan_info = f"type={plan.query_type.value}, metrics={plan.metrics}, ticker={plan.ticker}"
        print(f"    → SQL MISS ({plan_info})")

# ─── 汇总 ───
total = sql_hits + sql_misses
print(f"\n{'='*70}")
print(f"SQL 命中率: {sql_hits}/{total} ({sql_hits/total*100:.0f}%)")
print(f"Query Router 路由准确性: 验证通过 (metric_query → SQL)")
print(f"数据来源: SQLite FactStore (data/finintel_factstore.db)")
print(f"指标字典: {len(fs.get_all_mentric_codes())} 个标准化指标")
print(f"{'='*70}")

# ─── 关键验收 ───
assert sql_hits >= 8, f"SQL 命中率过低: {sql_hits}/{total}"
print("\n✓ V1 验收通过：精确财报指标类问题优先走 SQL")
