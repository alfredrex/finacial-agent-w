"""V4 验证: Router → Pipeline → 冲突检测"""
import sys
sys.path.insert(0, "/home/wjh/FinIntel-Multi-Agent")

from src.router.query_router import QueryRouter
from src.storage.fact_store import FactStore
from src.memory.data_source_pipeline import DataSourcePipeline

router = QueryRouter(known_companies={
    "002594": "比亚迪", "600519": "贵州茅台", "300750": "宁德时代",
})
fs = FactStore(); fs.init_db()
pipeline = DataSourcePipeline(fs)

# ── 测试 1: Router 输出优先级链 ──
print("=== 1. Router 数据源优先级 ===")
tests = [
    ("比亚迪2026Q1营收", "metric_query", ["sql","api","web"]),
    ("比亚迪股价", "realtime_quote", ["api","kv","web"]),
    ("比亚迪为什么净利润下降", "hybrid_analysis", ["rag","sql","web"]),
    ("比亚迪最新新闻", "latest_news", ["web","api","kv"]),
]
for q, etype, echain in tests:
    plan = router.route(q)
    status = "✓" if (plan.query_type.value == etype and plan.data_source_priority == echain) else "✗"
    print(f"  {status} {q[:30]} → {plan.query_type.value} chain={plan.data_source_priority}")

# ── 测试 2: Pipeline 执行 (仅 SQL + web, 跳过 API) ──
print("\n=== 2. Pipeline 多级链 (SQL only) ===")
result = pipeline.execute(
    priority_chain=["sql", "web"],  # 跳过 api 避免网络超时
    ticker="002594", company_name="比亚迪", report_period="2026Q1",
    metrics=["revenue", "net_profit", "rd_expense"],
)
print(f"  primary source: {result.primary.get('source','none')}")
print(f"  sources: {[s['source'] for s in result.sources]}")
print(f"  sql hits: {len(result.sql_result.get('data',[])) if result.sql_result else 0}")
print(f"  conflict: {result.conflict}")
print(f"  needs_ingestion: {result.needs_ingestion}")

# ── 测试 3: 缺失公司的 Pipeline ──
print("\n=== 3. 缺失公司 (平安银行) ===")
result2 = pipeline.execute(
    priority_chain=["sql", "web"],
    ticker="000001", company_name="平安银行", report_period="2026Q1",
    metrics=["revenue"],
)
print(f"  primary source: {result2.primary.get('source','none')}")
print(f"  sources: {[s['source'] for s in result2.sources]}")
print(f"  sql hits: {len(result2.sql_result.get('data',[])) if result2.sql_result else 0}")
print(f"  needs_ingestion: {result2.needs_ingestion}")

# ── 测试 4: 冲突检测 ──
print("\n=== 4. 冲突检测 ===")
conflict = pipeline._detect_conflict(
    PipelineResult(
        sources=[
            {"source": "sql", "data": [
                {"metric_code": "revenue", "metric_name": "营收", "value": 150000000000.0}
            ]},
            {"source": "api", "data": [
                {"metric_code": "revenue", "metric_name": "营收", "value": 200000000000.0}
            ]},
        ]
    ), "002594", "2026Q1", ["revenue"]
)
print(f"  conflict: {conflict[:80] if conflict else 'none'}...")

print("\n✓ V4 验证完成")
