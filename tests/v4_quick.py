import sys; sys.path.insert(0, "/home/wjh/FinIntel-Multi-Agent")
from src.router.query_router import QueryRouter
from src.storage.fact_store import FactStore
from src.memory.data_source_pipeline import DataSourcePipeline

router = QueryRouter({"002594":"比亚迪","600519":"贵州茅台","300750":"宁德时代"})
fs = FactStore(); fs.init_db()
pipeline = DataSourcePipeline(fs)

# Test 1: Router
print("=== Router chain ===")
for q in ["比亚迪2026Q1营收","比亚迪股价","比亚迪为什么净利润下降","比亚迪最新新闻"]:
    plan = router.route(q)
    print(f"  {plan.query_type.value:20s} chain={plan.data_source_priority}")

# Test 2: Pipeline SQL only
print("\n=== Pipeline SQL ===")
r = pipeline.execute(["sql"], "002594", "比亚迪", "2026Q1", ["revenue","net_profit"])
print(f"  primary: {r.primary.get('source')} hits={len(r.sql_result.get('data',[])) if r.sql_result else 0}")
for d in r.sql_result.get("data",[])[:3]:
    print(f"    {d['metric_name']}: {d['value']/1e8:.2f}亿")

# Test 3: Missing company
print("\n=== Pipeline missing ===")
r2 = pipeline.execute(["sql"], "000001", "平安银行", "2026Q1", ["revenue"])
print(f"  primary: {r2.primary.get('source','none')} sql_hits={len(r2.sql_result.get('data',[])) if r2.sql_result else 0}")

# Test 4: Conflict
print("\n=== Conflict detection ===")
from src.memory.data_source_pipeline import PipelineResult
conflict = pipeline._detect_conflict(
    PipelineResult(sources=[
        {"source":"sql","data":[{"metric_code":"revenue","value":150e8}]},
        {"source":"api","data":[{"metric_code":"revenue","value":200e8}]},
    ]), "002594", "2026Q1", ["revenue"]
)
print(f"  conflict: {conflict[:80]}..." if conflict else "  no conflict")

print("\nV4 OK")
