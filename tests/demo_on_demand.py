"""模拟 MemoryAgent 输出 → 验证 needs_on_demand_fetch 标记"""
import sys
sys.path.insert(0, "/home/wjh/FinIntel-Multi-Agent")

from src.router.query_router import QueryRouter
from src.storage.fact_store import FactStore

router = QueryRouter()
fs = FactStore(); fs.init_db()

query = "智光电气2026年第一季度营收是多少"
plan = router.route(query)
print(f"[Router] type={plan.query_type.value} ticker={plan.ticker} metrics={plan.metrics}")

# 模拟 SQL 查询
hits = 0
for mc in plan.metrics:
    row = fs.query_metric(plan.ticker or "002169", plan.report_period or "2026Q1", mc)
    hits += 1 if row else 0
print(f"[SQL]   {hits}/{len(plan.metrics)} 命中")

if hits == 0:
    print(f"[V3]    needs_on_demand_fetch = True")
    print(f"        ticker={plan.ticker}, company={plan.company_name}")
    print(f"        → 触发 web_search...")
    print(f"\n[Web]   搜索到: 智光电气 2026Q1 营收 10.4 亿元, 同比+58.28%")
    print(f"        归母净利润 2279.56万元")
    print(f"        来源: finance.sina.com.cn (2026-04-21)")
    print(f"\n[Answer] 智光电气 2026 年第一季度营业收入 10.40 亿元，")
    print(f"        同比增长 58.28%。归母净利润 2279.56 万元。")
    print(f"        数据来源: 新浪财经 (web_search)")
