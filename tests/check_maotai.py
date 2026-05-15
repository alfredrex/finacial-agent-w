import sys
sys.path.insert(0, "/home/wjh/FinIntel-Multi-Agent")
from src.storage.fact_store import FactStore
fs = FactStore(); fs.init_db()

# 检查茅台有哪些指标
print("茅台 Q1 指标:")
for r in fs.query_metrics_by_company_period("600519", "2026Q1"):
    print(f"  {r['metric_code']:25s} = {r['value']:.2f} ({r.get('raw_metric_name','?')})")

# 检查比亚迪
print("\n比亚迪 Q1 利润率相关:")
for mc in ["gross_margin","net_margin","gross_profit"]:
    r = fs.query_metric("002594", "2026Q1", mc)
    print(f"  {mc}: {'✓' if r else '✗'}")
